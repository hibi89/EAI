"""File-opt-in CSV test matrix: streaming, privacy, bounds and exact numbers."""
import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from eai.csv_analysis import inspect_csv, render_csv_summary


class CSVTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.file = self.folder / 'sample.csv'

    def tearDown(self):
        self.temp.cleanup()

    def test_numeric_profile_with_missingness_and_text(self):
        self.file.write_text('year,sales,label\n2023,0.1,A\n2024,0.2,B\n2025,,C\n', encoding='utf-8')
        report = inspect_csv(self.file)
        self.assertEqual((report['rows'], report['columns']), (3, 3))
        self.assertEqual(report['stats'][1]['sum'], '0.3')
        self.assertEqual(report['stats'][1]['avg'], '0.15')
        self.assertEqual(report['stats'][1]['missing'], 1)
        self.assertEqual(report['stats'][2]['type'], 'text')
        self.assertNotIn('A\n2024', render_csv_summary(report))

    def test_negative_numeric_and_mixed(self):
        self.file.write_text('value,comment\n-10,ok\n2.5,5\n,ignore\n', encoding='utf-8')
        report = inspect_csv(self.file)
        self.assertEqual(report['stats'][0]['sum'], '-7.5')
        self.assertEqual(report['stats'][1]['type'], 'mixed')
        self.assertIsNone(report['stats'][1]['avg'])

    def test_cp949_opt_in(self):
        self.file.write_bytes('매출,메모\n100,가게\n200,가게\n'.encode('cp949'))
        report = inspect_csv(self.file, encoding='cp949')
        self.assertEqual(report['stats'][0]['sum'], '300')
        with self.assertRaises(UnicodeError):
            inspect_csv(self.file)

    def test_large_file_is_rejected(self):
        with self.file.open('wb') as f:
            f.truncate(5 * 1024 * 1024 + 1)
        with self.assertRaises(ValueError):
            inspect_csv(self.file)

    def test_duplicate_or_invalid_header_rejected(self):
        for body in ['A,a\n1,2\n', ',B\n1,2\n', 'A,B\n1,2,3\n',
                     'A,B\n1\n', 'A,B\n1,2\n3,4,5\n']:
            self.file.write_text(body)
            with self.subTest(body=body), self.assertRaises(ValueError):
                inspect_csv(self.file)

    def test_resource_bounds_field_and_row_count(self):
        self.file.write_text('txt\n' + 'x' * 4097 + '\n', encoding='utf-8')
        with self.assertRaises(csv.Error):
            inspect_csv(self.file)
        self.file.write_text('A\n' + '1\n' * 20001, encoding='utf-8')
        with self.assertRaises(ValueError):
            inspect_csv(self.file)

    def test_read_only_and_stdout_does_not_leak_row_values(self):
        self.file.write_text('name,score\nprivate-sensitive-value,25\n', encoding='utf-8')
        original = self.file.read_bytes()
        result = inspect_csv(self.file)
        output = render_csv_summary(result)
        self.assertEqual(self.file.read_bytes(), original)
        self.assertNotIn('private-sensitive-value', output)

    def test_cli_runs_without_any_model_or_database(self):
        self.file.write_text('A,B\n1,2\n3,4\n', encoding='utf-8')
        root = Path(__file__).resolve().parents[1]
        done = subprocess.run([sys.executable, '-m', 'eai', 'analyze-csv', str(self.file)],
                              cwd=root, capture_output=True, text=True, timeout=10)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('합계 4', done.stdout)
        self.assertIn('평균 3', done.stdout)


if __name__ == '__main__':
    unittest.main()
