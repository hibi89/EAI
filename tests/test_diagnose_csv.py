"""P5 multi-metric CPU diagnostics, file safety, evidence and CLI contracts."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.diagnose_csv import diagnose_csv, render_diagnosis, MAX_CANDIDATES


class DiagnoseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.a = self.root / 'a.csv'
        self.b = self.root / 'b.csv'
        self.a.write_text('id,sales,orders,margin\nA,100,10,20\nB,120,12,30\nC,132,13,40\n', encoding='utf-8')
        self.b.write_text('id,sales,orders,margin\nC,132,13,40\nA,100,10,20\nB,120,12,30\n', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def run_diagnose(self, values=None, **kwargs):
        return diagnose_csv(self.a, self.b, key='id',
                            values=['sales', 'orders', 'margin'] if values is None else values,
                            **kwargs)

    def test_agreement_and_reordered_source(self):
        report = self.run_diagnose()
        self.assertEqual(report['status'], 'AGREE')
        self.assertEqual(len(report['metrics']), 3)
        self.assertEqual(report['candidates'], [])
        self.assertEqual(report['metrics'][0]['counts']['agree'], 3)
        self.assertNotEqual(report['sources'][0]['sha256'], report['sources'][1]['sha256'])

    def test_two_metrics_conflict_for_same_key(self):
        self.b.write_text('id,sales,orders,margin\nA,100,10,20\nB,130,11,30\nC,122,13,50\n')
        report = self.run_diagnose()
        self.assertEqual(report['status'], 'CONFLICT')
        self.assertEqual(len(report['candidates']), 2)
        each = {v['key']: v for v in report['candidates']}
        self.assertEqual(each['B']['affected_metrics'], ['orders', 'sales'])
        self.assertEqual(each['C']['affected_metrics'], ['margin', 'sales'])
        self.assertEqual(each['B']['hypothesis_code'], 'MULTI_METRIC_DRIFT')
        self.assertIn('자료 버전', each['B']['investigation_hint'])

    def test_identical_aggregate_does_not_hide_changed_keys(self):
        self.b.write_text('id,sales,orders,margin\nA,100,10,20\nB,130,12,30\nC,122,13,40\n')
        report = self.run_diagnose(['sales'])
        self.assertEqual(report['status'], 'CONFLICT')
        self.assertEqual([v['key'] for v in report['candidates']], ['B', 'C'])
        self.assertEqual(report['metrics'][0]['counts']['different'], 2)

    def test_missing_key_not_replaced_with_zero(self):
        self.b.write_text('id,sales,orders,margin\nA,100,10,20\nB,120,12,30\nD,132,13,40\n')
        report = self.run_diagnose(['sales', 'orders'])
        self.assertEqual(report['status'], 'CONFLICT')
        kindsets = {v['key']: {e['kind'] for e in v['evidence']}
                    for v in report['candidates']}
        self.assertEqual(kindsets['C'], {'LEFT_ONLY'})
        self.assertEqual(kindsets['D'], {'RIGHT_ONLY'})
        self.assertTrue(all(v['hypothesis_code'] == 'KEY_COVERAGE_DIFFERENCE'
                            for v in report['candidates']))

    def test_nonnumeric_column_warns_without_fake_agreement(self):
        self.b.write_text('id,sales,orders,margin\nA,100,10,20\nB,120,INVALID,30\nC,132,13,40\n')
        report = self.run_diagnose(['orders'])
        self.assertEqual(report['status'], 'UNAVAILABLE')
        self.assertEqual(report['candidates'][0]['hypothesis_code'], 'VALUE_TYPE_ISSUE')
        self.assertEqual(report['metrics'][0]['counts']['non_numeric'], 1)

    def test_conflict_dominates_unavailable(self):
        self.b.write_text('id,sales,orders,margin\nA,200,10,20\nB,120,INVALID,30\nC,132,13,40\n')
        report = self.run_diagnose(['sales', 'orders'])
        self.assertEqual(report['status'], 'CONFLICT')
        self.assertEqual([v['status'] for v in report['metrics']], ['CONFLICT', 'UNAVAILABLE'])

    def test_missing_column_is_unavailable(self):
        report = self.run_diagnose(['sales', 'not_in_source'])
        self.assertEqual(report['status'], 'UNAVAILABLE')
        self.assertEqual(report['metrics'][1]['missing_columns'], [['not_in_source'], ['not_in_source']])

    def test_duplicate_bytes_never_called_independent(self):
        self.b.write_bytes(self.a.read_bytes())
        self.assertEqual(self.run_diagnose()['status'], 'UNAVAILABLE')

    def test_same_path_fails_closed(self):
        with self.assertRaises(ValueError):
            diagnose_csv(self.a, self.a, key='id', values=['sales'])

    def test_duplicate_record_keys_fail_closed(self):
        self.b.write_text('id,sales,orders,margin\nA,1,2,3\nA,4,5,6\n')
        with self.assertRaisesRegex(ValueError, '중복'):
            self.run_diagnose()

    def test_invalid_metric_array_and_key(self):
        for values in ([], ['sales'] * 2, ['id'], ['sales'] * 9,
                       ['sales', 'orders', 'sales'], [' sales'], ['bad\nfield'], 'sales',
                       [123], [None]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.run_diagnose(values)
        for key in ('', ' id', 'id ', 'id\n', 'x' * 61):
            with self.subTest(key=key), self.assertRaises(ValueError):
                diagnose_csv(self.a, self.b, key=key, values=['sales'])

    def test_invalid_decimal_tolerance(self):
        for tol in ('-0.01', 'NaN', 'Infinity', '1e9', 'bad', '1' * 1000):
            with self.subTest(tol=tol), self.assertRaises(ValueError):
                self.run_diagnose(tolerance=tol)

    def test_per_metric_tolerance_is_applied_consistently(self):
        self.b.write_text('id,sales,orders,margin\nA,100.05,10.05,20\nB,120,12,30\nC,132,13,40\n')
        self.assertEqual(self.run_diagnose(tolerance='0.05')['status'], 'AGREE')
        self.assertEqual(self.run_diagnose(tolerance='0.049')['status'], 'CONFLICT')

    def test_encoding_cp949_non_ascii_key(self):
        self.a.write_bytes('항목,매출,주문\n가,100,10\n나,200,20\n'.encode('cp949'))
        self.b.write_bytes('항목,매출,주문\n나,200,20\n가,100,10\n'.encode('cp949'))
        report = diagnose_csv(self.a, self.b, key='항목', values=['매출', '주문'], encoding='cp949')
        self.assertEqual(report['status'], 'AGREE')

    def test_no_external_calls_or_model(self):
        with patch('eai.network.fetch_json', side_effect=AssertionError('no network')):
            report = self.run_diagnose()
        self.assertEqual(report['status'], 'AGREE')

    def test_detect_cross_metric_source_mutation(self):
        from eai.diagnose_csv import reconcile_csv as original
        calls = []
        def mutate(*args, **kwargs):
            result = original(*args, **kwargs)
            calls.append(1)
            if len(calls) == 1:
                self.b.write_text('id,sales,orders,margin\nA,999,10,20\n')
            return result
        with patch('eai.diagnose_csv.reconcile_csv', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, '변경'):
                self.run_diagnose()

    def test_detect_final_mutation_without_more_metrics(self):
        from eai.diagnose_csv import _file_digest as original
        calls = [0]
        def mutate(path):
            calls[0] += 1
            if calls[0] == 3:
                self.a.write_text('id,sales,orders,margin\nA,999,10,20\n')
            return original(path)
        with patch('eai.diagnose_csv._file_digest', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, '변경'):
                self.run_diagnose(['sales'])

    def test_candidates_are_bounded_and_truncation_disclosed(self):
        records_a = 'id,sales,orders\n' + ''.join(f'k{i:04d},100,10\n' for i in range(80))
        records_b = 'id,sales,orders\n' + ''.join(f'k{i:04d},200,20\n' for i in range(79, -1, -1))
        self.a.write_text(records_a)
        self.b.write_text(records_b)
        report = self.run_diagnose(['sales', 'orders'])
        self.assertEqual(report['status'], 'CONFLICT')
        self.assertEqual(report['metrics'][0]['counts']['different'], 80)
        self.assertEqual(len(report['candidates']), MAX_CANDIDATES)
        self.assertEqual(report['truncated_per_metric']['sales'], 60)
        self.assertIn('아닐 수 있습니다', report['sampling_limitations'])

    def test_candidates_never_assign_source_truth(self):
        self.b.write_text('id,sales,orders,margin\nA,200,10,20\nB,120,12,30\nC,132,13,40\n')
        report = self.run_diagnose(['sales'])
        self.assertIn('어느 쪽이 맞는지', report['scope'])
        self.assertIn('후보', report['candidates'][0]['investigation_hint'])
        self.assertNotIn('source_is_wrong', report['candidates'][0])

    def test_raw_files_unchanged_and_provenance_hashes(self):
        original = [self.a.read_bytes(), self.b.read_bytes()]
        report = self.run_diagnose()
        for p, data, src in zip((self.a, self.b), original, report['sources']):
            self.assertEqual(p.read_bytes(), data)
            self.assertEqual(src['sha256'], hashlib.sha256(data).hexdigest())

    def test_text_renderer_contains_evidence_and_limit(self):
        self.b.write_text('id,sales,orders,margin\nA,200,10,20\nB,120,12,30\nC,132,13,40\n')
        text = render_diagnosis(self.run_diagnose(['sales']))
        self.assertIn('CONFLICT', text)
        self.assertIn('key=A', text)
        self.assertIn('SHA256', text)
        self.assertIn('실제 원인', text)

    def test_cli_exit_codes_and_machine_json(self):
        workdir = Path(__file__).resolve().parent.parent
        def cli(*fields):
            return subprocess.run([sys.executable, '-m', 'eai', 'diagnose-csv',
                                   str(self.a), str(self.b), '--key', 'id', '--values',
                                   *fields, '--json'], cwd=workdir, text=True,
                                  capture_output=True, timeout=15)
        success = cli('sales', 'orders')
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertEqual(json.loads(success.stdout)['status'], 'AGREE')
        self.b.write_text('id,sales,orders,margin\nA,200,10,20\nB,120,12,30\nC,132,13,40\n')
        conflict = cli('sales', 'orders')
        self.assertEqual(conflict.returncode, 2, conflict.stderr)
        self.assertEqual(json.loads(conflict.stdout)['status'], 'CONFLICT')
        unavailable = cli('missing_column')
        self.assertEqual(unavailable.returncode, 3, unavailable.stderr)
        self.assertEqual(json.loads(unavailable.stdout)['status'], 'UNAVAILABLE')

    def test_bundled_example_two_metrics_drift_same_aggregate_totals(self):
        root = Path(__file__).resolve().parent.parent
        report = diagnose_csv(root / 'examples/sample_sales.csv',
                              root / 'examples/sample_sales_multi_drift.csv',
                              key='year', values=['sales', 'orders'])
        self.assertEqual(report['status'], 'CONFLICT')
        self.assertEqual(report['metrics'][0]['counts']['different'], 2)
        self.assertEqual(report['metrics'][1]['counts']['different'], 2)
        self.assertEqual([c['key'] for c in report['candidates']], ['2024', '2025'])
        self.assertTrue(all(len(c['affected_metrics']) == 2 for c in report['candidates']))
        self.assertEqual(sum((100, 120, 132)), sum((100, 130, 122)))
        self.assertEqual(sum((10, 12, 13)), sum((10, 11, 14)))

    def test_cli_invalid_metrics_fail_without_traceback(self):
        workdir = Path(__file__).resolve().parent.parent
        p = subprocess.run([sys.executable, '-m', 'eai', 'diagnose-csv',
                            str(self.a), str(self.b), '--key', 'id',
                            '--values', 'sales', 'sales'], cwd=workdir, text=True,
                           capture_output=True, timeout=15)
        self.assertEqual(p.returncode, 1)
        self.assertIn('EAI DIAGNOSE ERROR', p.stderr)
        self.assertNotIn('Traceback', p.stderr)

    def test_empty_source_is_unavailable_not_evidence(self):
        self.a.write_text('id,sales,orders\n')
        self.b.write_text('orders,id,sales\n')
        self.assertEqual(self.run_diagnose(['sales'])['status'], 'UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
