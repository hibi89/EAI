"""Deterministic CPU-owned evidence verification, security and CLI exit contracts."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.verify_csv import (verify_csv_claims, load_claims, validate_claims,
                            render_verification, _file_digest)


class CsvClaimVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.file = self.base / 'sample.csv'
        self.file.write_text('period,sales,orders,category\n2023,100,10,alpha\n2024,120,12,beta\n2025,132,13,gamma\n', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def claim(metric, expected, column='sales', **extras):
        return {'column': column, 'metric': metric, 'expected': expected, **extras}

    def test_exact_sum_verified_and_digest_matches(self):
        before = self.file.read_bytes()
        result = verify_csv_claims(self.file, [self.claim('sum', '352')])
        self.assertEqual(result['status'], 'VERIFIED')
        self.assertEqual(result['source']['sha256'], hashlib.sha256(before).hexdigest())
        self.assertEqual(result['source']['rows'], 3)
        self.assertEqual(self.file.read_bytes(), before)
        self.assertIn('주어진 CSV 파일', render_verification(result))

    def test_claim_conflicts_with_actual_data(self):
        result = verify_csv_claims(self.file, [self.claim('sum', '350')])
        self.assertEqual(result['status'], 'CONFLICT')
        self.assertEqual(result['claims'][0]['actual'], '352')
        self.assertEqual(result['claims'][0]['absolute_delta'], '2')

    def test_tolerance_is_explicit_and_bounded(self):
        ok = verify_csv_claims(self.file, [self.claim('sum', '350.5', tolerance='1.5')])
        fail = verify_csv_claims(self.file, [self.claim('sum', '350.5', tolerance='1.49')])
        self.assertEqual(ok['status'], 'VERIFIED')
        self.assertEqual(fail['status'], 'CONFLICT')

    def test_multiple_claims_one_source_profile(self):
        claims = [self.claim('sum', '352'), self.claim('min', '100'),
                  self.claim('max', '132'), self.claim('avg', '117.333333'),
                  self.claim('missing', '0'),
                  self.claim('numeric_count', '3', column='orders'),
                  self.claim('text_count', '3', column='category')]
        report = verify_csv_claims(self.file, claims)
        self.assertEqual(report['status'], 'VERIFIED')
        self.assertEqual(len(report['claims']), 7)

    def test_unknown_column_is_unavailable_not_false_verified(self):
        result = verify_csv_claims(self.file, [self.claim('sum', '0', column='missing')])
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertIsNone(result['claims'][0]['actual'])

    def test_text_sum_not_misreported_as_zero(self):
        result = verify_csv_claims(self.file, [self.claim('sum', '0', column='category')])
        self.assertEqual(result['status'], 'UNAVAILABLE')

    def test_mixed_type_count_allowed_while_sum_disallowed(self):
        self.file.write_text('mixed\n1\ntext\n2\n', encoding='utf-8')
        report = verify_csv_claims(self.file, [self.claim('numeric_count', '2', column='mixed'),
                                               self.claim('sum', '3', column='mixed')])
        self.assertEqual([c['status'] for c in report['claims']], ['VERIFIED', 'UNAVAILABLE'])
        self.assertEqual(report['status'], 'UNAVAILABLE')

    def test_conflict_precedes_unavailable_in_overall_result(self):
        report = verify_csv_claims(self.file, [self.claim('sum', '0'),
                                               self.claim('sum', '0', column='unknown')])
        self.assertEqual(report['status'], 'CONFLICT')

    def test_rounded_average_is_disclosed(self):
        result = verify_csv_claims(self.file, [self.claim('avg', '117.333333')])
        self.assertEqual(result['status'], 'VERIFIED')
        self.assertIn('6자리', result['precision'])
        self.assertNotIn('외부', result['claims'][0])

    def test_invalid_structures_rejected_before_file_reads(self):
        invalid = [None, [], [{}], [self.claim('sum', 1)],
                   [self.claim('sum', '352', hack='python')],
                   [self.claim('sum', 'NaN')],
                   [self.claim('sum', '352', tolerance='-0.1')],
                   [self.claim('sum', '352', tolerance='1e20')],
                   [self.claim('sum', '352', column=' sales')],
                   [self.claim('xyz', '0')],
                   [self.claim('sum', '0')] * 25]
        for item in invalid:
            with self.subTest(claims=item), self.assertRaises(ValueError):
                validate_claims(item)

    def test_invalid_csv_content_fails_closed(self):
        self.file.write_text('key,value\n1,2,3\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            verify_csv_claims(self.file, [self.claim('sum', '2', column='value')])

    def test_no_network_or_llm_call_on_verification(self):
        with patch('eai.network.fetch_json', side_effect=AssertionError('network not allowed')):
            output = verify_csv_claims(self.file, [self.claim('sum', '352')])
        self.assertEqual(output['status'], 'VERIFIED')

    def test_detects_input_change_between_scans(self):
        original = _file_digest
        attempts = [0]

        def mutate(path):
            attempts[0] += 1
            if attempts[0] == 2:
                path.write_text('period,sales,orders,category\n2023,101,10,alpha\n', encoding='utf-8')
            return original(path)
        with patch('eai.verify_csv._file_digest', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, '변경'):
                verify_csv_claims(self.file, [self.claim('sum', '352')])

    def test_json_claim_file_and_duplicate_keys(self):
        payload = self.base / 'claims.json'
        payload.write_text(json.dumps([self.claim('sum', '352')]), encoding='utf-8')
        loaded = load_claims(payload)
        self.assertEqual(loaded[0]['expected'], 352)
        payload.write_text('[{"column":"sales","column":"orders","metric":"sum","expected":"352"}]')
        with self.assertRaises(ValueError):
            load_claims(payload)

    def test_json_claims_limit_and_no_unsafe_floats(self):
        p = self.base / 'too_large.json'
        p.write_text(' ' * (32768 + 1), encoding='utf-8')
        with self.assertRaises(ValueError):
            load_claims(p)
        p.write_text('[{"column":"sales","metric":"sum","expected":352}]', encoding='utf-8')
        with self.assertRaises(ValueError):
            load_claims(p)

    def test_cli_verified_conflict_and_unavailable_exit_codes(self):
        root = Path(__file__).resolve().parent.parent
        def execute(column, expected):
            return subprocess.run([sys.executable, '-m', 'eai', 'verify-csv', str(self.file),
                                   '--column', column, '--metric', 'sum', '--expected', expected,
                                   '--json'], cwd=root, capture_output=True, text=True, timeout=12)
        success, conflict, missing = execute('sales', '352'), execute('sales', '300'), execute('unknown', '0')
        self.assertEqual([success.returncode, conflict.returncode, missing.returncode], [0, 2, 3])
        self.assertEqual(json.loads(success.stdout)['status'], 'VERIFIED')
        self.assertEqual(json.loads(conflict.stdout)['status'], 'CONFLICT')
        self.assertEqual(json.loads(missing.stdout)['status'], 'UNAVAILABLE')
        self.assertNotIn('Traceback', success.stderr + conflict.stderr + missing.stderr)

    def test_cli_batch_claims(self):
        root = Path(__file__).resolve().parent.parent
        payload = self.base / 'claims.json'
        payload.write_text(json.dumps([self.claim('sum', '352'), self.claim('max', '132')]))
        p = subprocess.run([sys.executable, '-m', 'eai', 'verify-csv', str(self.file),
                            '--claims', str(payload)], cwd=root, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('VERIFIED', p.stdout)
        self.assertIn('max', p.stdout)

    def test_cli_bad_args_fail_without_traceback(self):
        root = Path(__file__).resolve().parent.parent
        p = subprocess.run([sys.executable, '-m', 'eai', 'verify-csv', str(self.file),
                            '--column', 'sales', '--metric', 'sum', '--expected', 'nan'],
                           cwd=root, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn('EAI VERIFY ERROR', p.stderr)
        self.assertNotIn('Traceback', p.stderr)

    def test_csv_unchanged_after_conflict(self):
        original = self.file.read_bytes()
        verify_csv_claims(self.file, [self.claim('sum', '800')])
        self.assertEqual(self.file.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
