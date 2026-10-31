"""Actual CPU local CSV reconciliation, edge cases and CLI contracts."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.reconcile_csv import reconcile_csv, render_reconciliation


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.a = self.dir / 'a.csv'
        self.b = self.dir / 'b.csv'
        self.a.write_text('id,amount,note\nA,100,x\nB,120,y\nC,132,z\n', encoding='utf-8')
        self.b.write_text('id,amount,note\nC,132,z\nA,100,x\nB,120,y\n', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def run_reconcile(self, **kwargs):
        return reconcile_csv(self.a, self.b, key='id', value='amount', **kwargs)

    def test_agreement_even_if_file_row_order_differs(self):
        report = self.run_reconcile()
        self.assertEqual(report['status'], 'AGREE')
        self.assertEqual(report['counts']['agree'], 3)
        self.assertEqual(report['counts']['different'], 0)
        self.assertNotEqual(report['sources'][0]['sha256'], report['sources'][1]['sha256'])

    def test_detects_value_swap_despite_same_aggregate_sum(self):
        self.b.write_text('id,amount,note\nA,100,x\nB,132,y\nC,120,z\n')
        report = self.run_reconcile()
        self.assertEqual(report['status'], 'CONFLICT')
        self.assertEqual(report['counts']['different'], 2)
        self.assertEqual(report['counts']['agree'], 1)
        self.assertEqual(report['differences'][0]['absolute_delta'], '12')
        self.assertIn('키=', render_reconciliation(report))

    def test_decimal_tolerance_compares_exact_values(self):
        self.b.write_text('id,amount,note\nA,100.01,x\nB,120.05,y\nC,132,z\n')
        self.assertEqual(self.run_reconcile(tolerance='0.05')['status'], 'AGREE')
        self.assertEqual(self.run_reconcile(tolerance='0.049')['status'], 'CONFLICT')

    def test_missing_items_are_conflicts(self):
        self.b.write_text('id,amount,note\nA,100,x\nB,120,y\nD,999,z\n')
        r = self.run_reconcile()
        self.assertEqual((r['counts']['left_only'], r['counts']['right_only']), (1, 1))
        self.assertEqual(r['status'], 'CONFLICT')

    def test_non_numeric_does_not_fake_zero_agreement(self):
        self.b.write_text('id,amount,note\nA,100,x\nB,INVALID,y\nC,132,z\n')
        r = self.run_reconcile()
        self.assertEqual(r['status'], 'UNAVAILABLE')
        self.assertEqual(r['counts']['non_numeric'], 1)
        self.assertEqual(r['counts']['agree'], 2)

    def test_conflict_wins_over_non_numeric(self):
        self.b.write_text('id,amount,note\nA,999,x\nB,INVALID,y\nC,132,z\n')
        self.assertEqual(self.run_reconcile()['status'], 'CONFLICT')

    def test_missing_column_returns_unavailable(self):
        self.b.write_text('id,other,note\nA,10,x\nB,20,y\nC,30,z\n')
        r = self.run_reconcile()
        self.assertEqual(r['status'], 'UNAVAILABLE')
        self.assertEqual(r['sources'][1]['missing_columns'], ['amount'])

    def test_identical_contents_not_independent_evidence(self):
        self.b.write_bytes(self.a.read_bytes())
        r = self.run_reconcile()
        self.assertEqual(r['status'], 'UNAVAILABLE')
        self.assertTrue(any('독립' in w for w in r['warnings']))

    def test_explicit_same_path_rejected(self):
        with self.assertRaises(ValueError):
            reconcile_csv(self.a, self.a, key='id', value='amount')

    def test_duplicate_keys_rejected(self):
        self.b.write_text('id,amount,note\nA,100,x\nA,100,y\n')
        with self.assertRaisesRegex(ValueError, '중복'):
            self.run_reconcile()

    def test_empty_control_and_oversize_keys_rejected(self):
        for item in ('', ' ' , 'x' * 121, ' x', 'x '):
            self.b.write_text(f'id,amount,note\n{item},100,x\n')
            with self.subTest(item=item[:10]), self.assertRaises(ValueError):
                self.run_reconcile()

    def test_invalid_columns_and_tolerance(self):
        for kw in ({'key': 'id', 'value': 'id'}, {'key': 'bad\nkey', 'value': 'amount'},
                   {'key': 'id', 'value': 'amount', 'tolerance': '-1'},
                   {'key': 'id', 'value': 'amount', 'tolerance': 'NaN'},
                   {'key': 'id', 'value': 'amount', 'tolerance': '1e50'}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                reconcile_csv(self.a, self.b, **kw)

    def test_source_files_unchanged_and_sha256_grounded(self):
        before = [p.read_bytes() for p in (self.a, self.b)]
        r = self.run_reconcile()
        for p, data, source in zip((self.a, self.b), before, r['sources']):
            self.assertEqual(p.read_bytes(), data)
            self.assertEqual(source['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(source['filename'], p.name)

    def test_detect_modified_source_during_processing(self):
        from eai import reconcile_csv as module
        original = module._file_digest
        calls = {'n': 0}
        def changed(file):
            calls['n'] += 1
            if calls['n'] == 2:
                self.a.write_text('id,amount,note\nA,999,x\n')
            return original(file)
        with patch('eai.reconcile_csv._file_digest', side_effect=changed):
            with self.assertRaisesRegex(ValueError, '변경'):
                self.run_reconcile()

    def test_no_network_or_llm_call(self):
        with patch('eai.network.fetch_json', side_effect=AssertionError('network called')):
            self.assertEqual(self.run_reconcile()['status'], 'AGREE')

    def test_large_detail_list_is_bounded(self):
        self.a.write_text('id,amount\n'+'\n'.join(f'item{i},1' for i in range(80))+'\n')
        self.b.write_text('id,amount\n'+'\n'.join(f'item{i},2' for i in range(80))+'\n')
        r = self.run_reconcile()
        self.assertEqual(r['counts']['different'], 80)
        self.assertEqual(len(r['differences']), 20)
        self.assertEqual(r['truncated'], 60)
        self.assertEqual(r['status'], 'CONFLICT')

    def test_encoding_cp949(self):
        self.a.write_bytes('항목,금액\n가,100\n나,200\n'.encode('cp949'))
        self.b.write_bytes('항목,금액\n나,200\n가,100\n'.encode('cp949'))
        r = reconcile_csv(self.a, self.b, key='항목', value='금액', encoding='cp949')
        self.assertEqual(r['status'], 'AGREE')

    def test_invalid_encoding_fails(self):
        with self.assertRaises(ValueError):
            self.run_reconcile(encoding='utf-16')

    def test_invalid_csv_rows_fail_closed(self):
        self.b.write_text('id,amount\nA,100,EXTRA\n')
        with self.assertRaises(ValueError):
            self.run_reconcile()

    def test_input_oversize_fails_closed(self):
        self.b.write_text('id,amount\n' + ('x' * (5 * 1024 * 1024)))
        with self.assertRaises(ValueError):
            self.run_reconcile()

    def test_cli_status_codes(self):
        root = Path(__file__).resolve().parent.parent
        def run(r):
            return subprocess.run([sys.executable, '-m', 'eai', 'reconcile-csv',
                                   str(self.a), str(self.b), '--key', 'id',
                                   '--value', 'amount', '--json'], cwd=root,
                                  capture_output=True, text=True, timeout=12)
        ok = run(0)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)['status'], 'AGREE')
        self.b.write_text('id,amount,note\nA,0,x\nB,120,y\nC,132,z\n')
        conflict = run(1)
        self.assertEqual(conflict.returncode, 2)
        self.assertEqual(json.loads(conflict.stdout)['status'], 'CONFLICT')
        self.b.write_text('id,amount,note\nA,NONNUM,x\nB,120,y\nC,132,z\n')
        unavailable = run(2)
        self.assertEqual(unavailable.returncode, 3)
        self.assertEqual(json.loads(unavailable.stdout)['status'], 'UNAVAILABLE')

    def test_cli_invalid_args_do_not_traceback(self):
        root = Path(__file__).resolve().parent.parent
        r = subprocess.run([sys.executable, '-m', 'eai', 'reconcile-csv',
                            str(self.a), str(self.b), '--key', 'id',
                            '--value', 'amount', '--tolerance', 'bad'], cwd=root,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn('EAI RECONCILE ERROR', r.stderr)
        self.assertNotIn('Traceback', r.stderr)

    def test_cli_sample_mismatch_same_totals(self):
        root = Path(__file__).resolve().parent.parent
        sample = root / 'examples/sample_sales.csv'
        counterpart = root / 'examples/sample_sales_source_b.csv'
        result = subprocess.run([sys.executable, '-m', 'eai', 'reconcile-csv',
                                str(sample), str(counterpart), '--key', 'year',
                                '--value', 'sales', '--json'], cwd=root,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['counts']['different'], 2)
        self.assertEqual(report['status'], 'CONFLICT')


if __name__ == '__main__':
    unittest.main()
