"""P6 independent CPU goal planner, bounded execution and evidence guards."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.plan_engine import (AuditGoal, CPUPlanExecutor, PLAN_VERSION,
                             RuleGoalPlanner, render_plan_report)


class PlanEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.a = self.root / 'source-a.csv'
        self.b = self.root / 'source-b.csv'
        self.a.write_text('key,sales,orders\nA,100,10\nB,120,12\n', encoding='utf-8')
        self.b.write_text('key,sales,orders\nB,110,11\nA,110,11\n', encoding='utf-8')
        self.planner = RuleGoalPlanner()
        self.executor = CPUPlanExecutor()

    def tearDown(self):
        self.tmp.cleanup()

    def goal(self, values=None, **kwargs):
        return AuditGoal(self.a, self.b, 'key', values or ['sales'], **kwargs)

    def test_compiler_selects_single_reconcile(self):
        plan = self.planner.compile(self.goal())
        self.assertEqual(plan.version, PLAN_VERSION)
        self.assertEqual(plan.strategy, 'SINGLE_RECONCILE')
        self.assertEqual(plan.steps[1].skill, 'csv.reconcile.v1')
        self.assertEqual(len(plan.steps), 5)

    def test_compiler_selects_multi_diagnose(self):
        plan = self.planner.compile(self.goal(['sales', 'orders']))
        self.assertEqual(plan.strategy, 'MULTI_DIAGNOSE')
        self.assertEqual(plan.steps[1].skill, 'csv.diagnose.v1')

    def test_single_conflict_escalates_to_independent_diagnosis(self):
        report = self.executor.execute(self.goal())
        self.assertEqual(report['status'], 'CONFLICT')
        self.assertEqual([x['step'] for x in report['steps']],
                         ['anchor_sources', 'primary_solve', 'conflict_escalation', 'verify_receipt'])
        self.assertIsNotNone(report['escalation'])
        self.assertEqual(report['escalation']['candidates'][0]['hypothesis_code'],
                         'SINGLE_METRIC_DIFFERENCE')
        self.assertIn('충돌 세부 진단', render_plan_report(report))

    def test_multi_conflict_does_not_reexecute_unneeded_diagnostic(self):
        report = self.executor.execute(self.goal(['sales', 'orders']))
        self.assertEqual(report['status'], 'CONFLICT')
        self.assertEqual(len(report['steps']), 3)
        self.assertIsNone(report['escalation'])
        self.assertEqual(report['strategy'], 'MULTI_DIAGNOSE')
        self.assertIn('verify_receipt', [v['step'] for v in report['steps']])

    def test_agree_path_no_fallback(self):
        self.b.write_text('key,sales,orders\nB,120,12\nA,100,10\n', encoding='utf-8')
        report = self.executor.execute(self.goal())
        self.assertEqual(report['status'], 'AGREE')
        self.assertIsNone(report['escalation'])
        self.assertIsNone(report['unavailable_inspection'])
        self.assertEqual(len(report['steps']), 3)

    def test_multi_agree_path_no_fallback(self):
        self.b.write_text('key,sales,orders\nB,120,12\nA,100,10\n', encoding='utf-8')
        report = self.executor.execute(self.goal(['sales', 'orders']))
        self.assertEqual(report['status'], 'AGREE')
        self.assertEqual(report['steps'][-1]['status'], 'PASS')

    def test_missing_field_selects_schema_fallback_and_preserves_unavailable(self):
        report = self.executor.execute(self.goal(['missing_field']))
        self.assertEqual(report['status'], 'UNAVAILABLE')
        self.assertIsNotNone(report['unavailable_inspection'])
        self.assertIn('unavailable_fallback', [r['step'] for r in report['steps']])
        self.assertEqual(report['unavailable_inspection'][0]['rows'], 2)
        self.assertEqual([x['name'] for x in report['unavailable_inspection'][0]['columns']],
                         ['key', 'sales', 'orders'])
        self.assertIn('CSV 열 구조', render_plan_report(report))

    def test_missing_multi_metric_selects_schema_fallback(self):
        report = self.executor.execute(self.goal(['sales', 'missing']))
        self.assertEqual(report['status'], 'CONFLICT')
        self.assertIsNone(report['unavailable_inspection'])
        # Conflict outranks unavailable, schema inspection is not a cure for contradiction.
        self.assertEqual(report['primary']['status'], 'CONFLICT')

    def test_same_content_different_paths_unavailable(self):
        self.b.write_bytes(self.a.read_bytes())
        report = self.executor.execute(self.goal())
        self.assertEqual(report['status'], 'UNAVAILABLE')
        self.assertEqual(report['steps'][-2]['step'], 'unavailable_fallback')

    def test_no_numeric_matched_rows_must_not_agree(self):
        self.a.write_text('key,sales,orders\n', encoding='utf-8')
        self.b.write_text('key,sales,orders\nB,120,12\n', encoding='utf-8')
        result = self.executor.execute(self.goal())
        self.assertEqual(result['status'], 'CONFLICT')
        self.assertEqual(result['primary']['counts']['right_only'], 1)

    def test_empty_sources_with_different_raw_bytes_are_unavailable(self):
        self.a.write_text('key,sales,orders\n', encoding='utf-8')
        self.b.write_text('key,sales,orders\r\n', encoding='utf-8')
        result = self.executor.execute(self.goal())
        self.assertEqual(result['status'], 'UNAVAILABLE')

    def test_validate_bad_goal_before_file_reads(self):
        cases = [
            AuditGoal(self.a, self.b, 'key', ['sales'], max_seconds=0),
            AuditGoal(self.a, self.b, 'key', ['sales'], max_seconds=121),
            AuditGoal(self.a, self.b, 'key', [], max_seconds=10),
            AuditGoal(self.a, self.b, 'key', ['sales'] * 2),
            AuditGoal(self.a, self.b, 'key', ['v'+str(i) for i in range(9)]),
            AuditGoal(self.a, self.b, 'key', ['sales'], tolerance='-0.001'),
            AuditGoal(self.a, self.b, 'key', ['sales'], encoding='utf-16'),
        ]
        with patch('eai.plan_engine._file_digest', side_effect=AssertionError('read invoked')):
            for case in cases:
                with self.subTest(case=case), self.assertRaises(ValueError):
                    self.executor.execute(case)

    def test_identical_resolved_path_is_denied(self):
        with self.assertRaisesRegex(ValueError, '동일한'):
            self.executor.execute(AuditGoal(self.a, self.a, 'key', ['sales']))

    def test_budget_is_a_stage_admission_guard(self):
        with patch('eai.plan_engine.monotonic', side_effect=[0.0, 10.0]):
            with self.assertRaises(TimeoutError):
                self.executor.execute(self.goal(max_seconds=1))

    def test_source_change_is_detected_even_after_successful_primary(self):
        from eai.plan_engine import _file_digest
        original = _file_digest
        count = [0]

        def changed(path):
            count[0] += 1
            if count[0] == 4:
                self.b.write_text('key,sales,orders\nA,999,9\n', encoding='utf-8')
            return original(path)

        with patch('eai.plan_engine._file_digest', side_effect=changed):
            with self.assertRaisesRegex(ValueError, '변경'):
                self.executor.execute(self.goal())

    def test_malicious_or_inconsistent_receipt_is_denied(self):
        bad = {'status': 'AGREE', 'counts': {'agree': 2}, 'sources': [
            {'sha256': 'not_a_hash'}, {'sha256': 'forged'}]}
        with patch('eai.plan_engine.reconcile_csv', return_value=bad):
            with self.assertRaisesRegex(ValueError, '해시'):
                self.executor.execute(self.goal())

    def test_no_llm_network_or_local_db_for_cpu_plan(self):
        with patch('eai.network.fetch_json', side_effect=AssertionError('no network')):
            r = self.executor.execute(self.goal())
        self.assertEqual(r['status'], 'CONFLICT')

    def test_sources_are_never_modified(self):
        before = (self.a.read_bytes(), self.b.read_bytes())
        self.executor.execute(self.goal(['sales', 'orders']))
        self.assertEqual((self.a.read_bytes(), self.b.read_bytes()), before)

    def test_cli_conflict_and_json_traces(self):
        result = self.cli('--values', 'sales', 'orders', '--json')
        self.assertEqual(result.returncode, 2, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['status'], 'CONFLICT')
        self.assertEqual(data['plan_version'], PLAN_VERSION)
        self.assertEqual(data['steps'][-1]['status'], 'PASS')

    def test_cli_agree_and_unavailable_status_codes(self):
        self.b.write_text('key,sales,orders\nB,120,12\nA,100,10\n', encoding='utf-8')
        self.assertEqual(self.cli('--values', 'sales').returncode, 0)
        self.assertEqual(self.cli('--values', 'missing_field').returncode, 3)

    def test_cli_invalid_input_returns_error_no_traceback(self):
        r = self.cli('--values', 'sales', '--tolerance', '-0.01')
        self.assertEqual(r.returncode, 1)
        self.assertIn('EAI PLAN ERROR', r.stderr)
        self.assertNotIn('Traceback', r.stderr)

    def test_unsupported_goal_input_rejected_without_unsafe_dispatch(self):
        with self.assertRaises(ValueError):
            self.planner.compile('import os; os.system("rm -rf /")')

    def test_cpu_workflow_does_not_require_ollama(self):
        r = self.cli('--values', 'sales', '--json')
        self.assertIn('status', json.loads(r.stdout))
        self.assertEqual(r.returncode, 2)

    def test_schema_fallback_displays_column_types_not_rows(self):
        r = self.cli('--values', 'unknown', '--json')
        data = json.loads(r.stdout)
        self.assertEqual(data['status'], 'UNAVAILABLE')
        inspection = data['unavailable_inspection']
        self.assertEqual(inspection[0]['columns'][1]['type'], 'numeric')
        self.assertNotIn('100,10', r.stdout)

    def cli(self, *args):
        return subprocess.run([
            sys.executable, '-m', 'eai', 'solve-csv', str(self.a), str(self.b),
            '--key', 'key', *args
        ], cwd=Path(__file__).resolve().parent.parent, text=True,
            capture_output=True, timeout=20)


if __name__ == '__main__':
    unittest.main()
