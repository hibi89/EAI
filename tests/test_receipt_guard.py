"""P8 independent postcondition validation and bounded failure diagnostics."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.decision_engine import validate_choice_goal, execute_choice_goal
from eai.goal_dispatch import execute_goal_document, render_goal_document
from eai.plan_engine import AuditGoal, CPUPlanExecutor
from eai.receipt_guard import verify_goal_receipt, GUARD_VERSION


def options_fixture():
    return {
        'version': 1, 'kind': 'choose_options', 'goal': 'CPU local hardware choice',
        'criteria': [
            {'id': 'price', 'direction': 'min', 'unit': 'KRW', 'weight': '2',
             'score_min': '0', 'score_max': '1000', 'hard_max': '900'},
            {'id': 'ram', 'direction': 'max', 'unit': 'GB', 'weight': '1',
             'score_min': '0', 'score_max': '64', 'hard_min': '16'},
        ],
        'options': [
            {'id': 'fast', 'values': {'price': '750', 'ram': '32'}},
            {'id': 'cheap', 'values': {'price': '500', 'ram': '16'}},
            {'id': 'expensive', 'values': {'price': '1200', 'ram': '64'}},
            {'id': 'unknown', 'values': {'price': '600'}},
        ],
    }


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        self.spec = self.directory / 'goal.json'
        self.left, self.right = self.directory / 'left.csv', self.directory / 'right.csv'
        self.left.write_text('id,price,ram\nX,10,32\nY,20,64\n', encoding='utf-8')
        self.right.write_text('id,price,ram\nY,25,64\nX,10,32\n', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, goal):
        self.spec.write_text(json.dumps(goal, ensure_ascii=False), encoding='utf-8')

    def test_choice_receipt_verified_on_input_not_just_status(self):
        self.write(options_fixture())
        result = execute_goal_document(self.spec)
        self.assertEqual(result['verification']['status'], 'PASS')
        self.assertEqual(result['verification']['version'], GUARD_VERSION)
        self.assertIn('ranking', result['verification']['checks'])
        self.assertEqual(result['verification']['diagnostics']['type'], 'NONE')
        self.assertIn('결과 독립 검사: PASS', render_goal_document(result))

    def test_choice_receipt_rejects_false_winner(self):
        g = validate_choice_goal(options_fixture())
        result = execute_choice_goal(g)
        result['winners'] = ['expensive']
        with self.assertRaisesRegex(ValueError, '영수증 검증 실패'):
            verify_goal_receipt('choose_options', g, result)

    def test_choice_receipt_rejects_score_inflation(self):
        g = validate_choice_goal(options_fixture())
        result = execute_choice_goal(g)
        target = next(x for x in result['options'] if x['id'] == 'fast')
        target['score'] = '99.99'
        with self.assertRaisesRegex(ValueError, '가중치 점수'):
            verify_goal_receipt('choose_options', g, result)

    def test_choice_receipt_rejects_modified_pareto(self):
        g = validate_choice_goal(options_fixture())
        result = execute_choice_goal(g)
        result['pareto_frontier'] = ['expensive']
        with self.assertRaisesRegex(ValueError, 'Pareto'):
            verify_goal_receipt('choose_options', g, result)

    def test_choice_receipt_rejects_concealed_hard_constraint(self):
        g = validate_choice_goal(options_fixture())
        result = execute_choice_goal(g)
        target = next(x for x in result['options'] if x['id'] == 'expensive')
        target['status'] = 'FEASIBLE'
        with self.assertRaisesRegex(ValueError, '제약 판정'):
            verify_goal_receipt('choose_options', g, result)

    def test_choice_receipt_rejects_dropped_option(self):
        g = validate_choice_goal(options_fixture())
        result = execute_choice_goal(g)
        result['options'].pop()
        with self.assertRaisesRegex(ValueError, '후보 개수'):
            verify_goal_receipt('choose_options', g, result)

    def test_choice_receipt_rejects_wrong_status_and_kind(self):
        g = validate_choice_goal(options_fixture())
        for status in ('AGREE','ERROR','EXECUTED','',None):
            result = execute_choice_goal(g)
            result['status'] = status
            with self.subTest(status=status), self.assertRaises(ValueError):
                verify_goal_receipt('choose_options', g, result)

    def test_no_feasible_receipt_recommends_review_without_relaxing(self):
        goal=options_fixture()
        goal['criteria'][0]['hard_max']='1'
        self.write(goal)
        report=execute_goal_document(self.spec)
        self.assertEqual(report['status'], 'UNAVAILABLE')
        diag=report['verification']['diagnostics']
        self.assertEqual(diag['type'], 'NO_FEASIBLE_OPTION')
        self.assertTrue(diag['action_required'])
        self.assertTrue(any(x['code']=='HARD_CONSTRAINT' for x in diag['items']))
        self.assertIn('NO_FEASIBLE_OPTION', render_goal_document(report))
        self.assertNotIn('AUTOMATIC_REPAIR', diag.get('type',''))

    def test_tie_receipt_does_not_make_up_winner(self):
        goal=options_fixture()
        goal['options'][1]['values']={'price':'750','ram':'32'}
        self.write(goal)
        report=execute_goal_document(self.spec)
        self.assertEqual(report['status'], 'TIE')
        self.assertEqual(len(report['result']['winners']), 2)
        self.assertEqual(report['verification']['diagnostics']['type'],'TIE_REVIEW')

    def test_csv_receipt_source_hash_and_skill_allowlist(self):
        goal=AuditGoal(self.left,self.right,'id',['price'])
        result=CPUPlanExecutor().execute(goal)
        verified=verify_goal_receipt('csv_audit',goal,result)
        self.assertEqual(verified['status'],'PASS')
        self.assertIn('provenance',verified['checks'])
        self.assertEqual(verified['diagnostics']['type'],'CONFLICT_REVIEW')

    def test_csv_receipt_rejects_forged_source(self):
        goal=AuditGoal(self.left,self.right,'id',['price'])
        result=CPUPlanExecutor().execute(goal)
        result['sources'][0]['sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'원본 파일의 해시'):
            verify_goal_receipt('csv_audit',goal,result)

    def test_csv_receipt_rejects_skipped_verification(self):
        goal=AuditGoal(self.left,self.right,'id',['price'])
        result=CPUPlanExecutor().execute(goal)
        result['steps'].pop()
        with self.assertRaisesRegex(ValueError,'원본 검증 영수증'):
            verify_goal_receipt('csv_audit',goal,result)

    def test_csv_receipt_rejects_unknown_skill(self):
        goal=AuditGoal(self.left,self.right,'id',['price'])
        result=CPUPlanExecutor().execute(goal)
        result['steps'][0]['skill']='subprocess.shell.execute'
        with self.assertRaisesRegex(ValueError,'미승인 스킬'):
            verify_goal_receipt('csv_audit',goal,result)

    def test_csv_receipt_rejects_primary_status_upgrade(self):
        goal=AuditGoal(self.left,self.right,'id',['price'])
        result=CPUPlanExecutor().execute(goal)
        result['status']='AGREE'
        with self.assertRaisesRegex(ValueError, '최종 상태'):
            verify_goal_receipt('csv_audit',goal,result)

    def test_csv_receipt_unavailable_explains_schema(self):
        goal=AuditGoal(self.left,self.right,'id',['missing_column'])
        report=CPUPlanExecutor().execute(goal)
        assert report['status']=='UNAVAILABLE'
        verify=verify_goal_receipt('csv_audit',goal,report)
        self.assertEqual(verify['diagnostics']['type'],'SOURCE_SCHEMA_REVIEW')

    def test_csv_receipt_detects_mutated_bytes(self):
        goal=AuditGoal(self.left,self.right,'id',['ram'])
        report=CPUPlanExecutor().execute(goal)
        self.right.write_text('id,price,ram\nY,25,999\nX,10,32\n')
        with self.assertRaisesRegex(ValueError, '해시'):
            verify_goal_receipt('csv_audit', goal, report)

    def test_dispatch_integration_with_csv_goal(self):
        self.write({'version':1,'kind':'csv_audit','left':'left.csv','right':'right.csv',
                    'key':'id','values':['price']})
        report=execute_goal_document(self.spec)
        self.assertEqual(report['status'],'CONFLICT')
        self.assertEqual(report['verification']['status'],'PASS')
        self.assertEqual(report['verification']['diagnostics']['type'],'CONFLICT_REVIEW')

    def test_guard_rejects_mocked_solver_receipt(self):
        self.write(options_fixture())
        forged={'status':'DECIDED','goal':'CPU local hardware choice','kind':'choose_options',
                'winners':['A'],'options':[]}
        with patch('eai.goal_dispatch.execute_choice_goal',return_value=forged):
            with self.assertRaisesRegex(ValueError,'영수증 검증 실패'):
                execute_goal_document(self.spec)

    def test_cli_receipt_json_and_status_codes(self):
        goal=options_fixture()
        self.write(goal)
        root=Path(__file__).resolve().parent.parent
        cmd=[sys.executable,'-m','eai','solve-goal',str(self.spec),'--json']
        run=subprocess.run(cmd,cwd=root,text=True,capture_output=True,timeout=15)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(run.stdout)['verification']['status'],'PASS')
        goal['criteria'][0]['hard_max']='1'
        self.write(goal)
        run=subprocess.run(cmd,cwd=root,text=True,capture_output=True,timeout=15)
        self.assertEqual(run.returncode,3,run.stderr)
        self.assertEqual(json.loads(run.stdout)['verification']['diagnostics']['type'],
                         'NO_FEASIBLE_OPTION')

    def test_no_network_or_model_calls_during_guard(self):
        g=validate_choice_goal(options_fixture())
        r=execute_choice_goal(g)
        with patch('eai.network.fetch_json',side_effect=AssertionError('network forbidden')):
            self.assertEqual(verify_goal_receipt('choose_options',g,r)['status'],'PASS')

    def test_no_mutation_of_user_original_files(self):
        a,b=self.left.read_bytes(),self.right.read_bytes()
        self.write({'version':1,'kind':'csv_audit','left':'left.csv','right':'right.csv',
                    'key':'id','values':['price','ram']})
        execute_goal_document(self.spec)
        self.assertEqual((self.left.read_bytes(),self.right.read_bytes()),(a,b))


if __name__=='__main__':
    unittest.main()
