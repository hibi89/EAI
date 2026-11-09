"""P10 typed exact task planning and independent postcondition verification."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.task_portfolio import validate_task_goal, execute_task_goal
from eai.goal_dispatch import execute_goal_document, render_goal_document
from eai.receipt_guard import verify_goal_receipt


def fixture():
    return {'version':1,'kind':'plan_tasks','goal':'Project priorities',
            'max_hours':'5','max_cost':'10','tasks':[
                {'id':'A','hours':'4','cost':'5','value':'6','requires':[]},
                {'id':'B','hours':'3','cost':'4','value':'5','requires':[]},
                {'id':'C','hours':'2','cost':'4','value':'4','requires':[]},
            ]}


class TaskPortfolioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'goal.json'
    def tearDown(self):
        self.tmp.cleanup()
    def run_goal(self, raw):
        self.path.write_text(json.dumps(raw),encoding='utf-8')
        return execute_goal_document(self.path)
    def test_exact_optimum_not_greedy_single(self):
        report=self.run_goal(fixture())
        self.assertEqual(report['result']['selected'],['B','C'])
        self.assertEqual(report['result']['best_value'],'9')
        self.assertEqual(report['verification']['status'],'PASS')
        self.assertIn('exact_optimum',report['verification']['checks'])
    def test_dependency_prevents_fake_best(self):
        raw=fixture()
        raw['tasks'][2]['requires']=['A']
        report=self.run_goal(raw)
        self.assertEqual(report['result']['selected'],['A'])
    def test_multi_step_dependency_chain(self):
        raw=fixture()
        raw['max_hours']='10'
        raw['max_cost']='20'
        raw['tasks'][0]['requires']=['B']
        raw['tasks'][1]['requires']=['C']
        self.assertEqual(self.run_goal(raw)['result']['selected'],['A','B','C'])
    def test_exact_decimal_boundary(self):
        raw=fixture()
        raw['max_hours']=raw['max_cost']='0.3'
        raw['tasks']=[{'id':'a','hours':'0.1','cost':'0.1','value':'1','requires':[]},
                      {'id':'b','hours':'0.2','cost':'0.2','value':'2','requires':[]}]
        self.assertEqual(self.run_goal(raw)['result']['selected'],['a','b'])
    def test_tie_requires_human_selection(self):
        raw=fixture()
        raw['max_hours']='2'
        raw['tasks']=[{'id':x,'hours':'2','cost':'1','value':'4','requires':[]} for x in ('A','B')]
        report=self.run_goal(raw)
        self.assertEqual(report['status'],'TIE')
        self.assertEqual(report['result']['selected'],[])
        self.assertEqual(report['result']['candidate_count'],2)
        self.assertEqual(report['verification']['diagnostics']['type'],'TIE_REVIEW')
    def test_no_positive_feasible_plan(self):
        raw=fixture()
        raw['max_hours']='0'
        r=self.run_goal(raw)
        self.assertEqual(r['status'],'UNAVAILABLE')
        self.assertEqual(r['verification']['diagnostics']['type'],'NO_FEASIBLE_POSITIVE_PLAN')
    def test_zero_valued_work_not_recommended(self):
        raw=fixture()
        for t in raw['tasks']:t['value']='0'
        self.assertEqual(self.run_goal(raw)['status'],'UNAVAILABLE')
    def test_invalid_and_cyclic_dependencies(self):
        for req in ('missing','A'):
            raw=fixture();raw['tasks'][0]['requires']=[req]
            with self.subTest(req=req),self.assertRaises(ValueError):self.run_goal(raw)
        raw=fixture();raw['tasks'][0]['requires']=['B'];raw['tasks'][1]['requires']=['A']
        with self.assertRaisesRegex(ValueError,'cyclic'):self.run_goal(raw)
    def test_unknown_fields_or_float_denied(self):
        raw=fixture();raw['exec']='shell'
        with self.assertRaises(ValueError):self.run_goal(raw)
        raw=fixture();raw['tasks'][0]['cost']=3.2
        with self.assertRaises(ValueError):self.run_goal(raw)
    def test_more_than_twelve_denied(self):
        raw=fixture()
        raw['tasks']=[{'id':'t'+str(i),'hours':'1','cost':'1','value':'1','requires':[]}
                      for i in range(13)]
        with self.assertRaises(ValueError):self.run_goal(raw)
    def test_forged_winner_denied(self):
        g=validate_task_goal(fixture());r=execute_task_goal(g);r['selected']=['A']
        with self.assertRaisesRegex(ValueError,'영수증'):verify_goal_receipt('plan_tasks',g,r)
    def test_forged_best_value_denied(self):
        g=validate_task_goal(fixture());r=execute_task_goal(g);r['best_value']='100'
        with self.assertRaisesRegex(ValueError,'영수증'):verify_goal_receipt('plan_tasks',g,r)
    def test_forged_resources_denied(self):
        g=validate_task_goal(fixture());r=execute_task_goal(g);r['max_cost']='100'
        with self.assertRaisesRegex(ValueError,'영수증'):verify_goal_receipt('plan_tasks',g,r)
    def test_forged_candidate_count_denied(self):
        g=validate_task_goal(fixture());r=execute_task_goal(g);r['candidate_count']=100
        with self.assertRaisesRegex(ValueError,'영수증'):verify_goal_receipt('plan_tasks',g,r)
    def test_forged_candidate_evidence_denied(self):
        g=validate_task_goal(fixture());r=execute_task_goal(g);r['candidates'][0]['hours']='0'
        with self.assertRaisesRegex(ValueError,'영수증'):verify_goal_receipt('plan_tasks',g,r)
    def test_original_bytes_preserved_no_network(self):
        self.path.write_text(json.dumps(fixture()),encoding='utf-8')
        before=self.path.read_bytes()
        with patch('eai.network.fetch_json',side_effect=AssertionError('network attempt')):
            r=execute_goal_document(self.path)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertIn('선택:',render_goal_document(r))
    def test_cli_json_contract(self):
        self.path.write_text(json.dumps(fixture()),encoding='utf-8')
        root=Path(__file__).resolve().parent.parent
        p=subprocess.run([sys.executable,'-m','eai','solve-goal',str(self.path),'--json'],
                         cwd=root,capture_output=True,text=True,timeout=20)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['result']['selected'],['B','C'])
    def test_sample_goal(self):
        root=Path(__file__).resolve().parent.parent
        path=root/'examples'/'sample_task_portfolio_goal.json'
        before=path.read_bytes()
        self.assertEqual(execute_goal_document(path)['verification']['status'],'PASS')
        self.assertEqual(path.read_bytes(),before)


    def test_max_precision_decimal_resources_not_rounded(self):
        raw=fixture()
        raw['max_hours']='100000000000000000000000.000000000002'
        raw['max_cost']='0'
        raw['tasks']=[
            {'id':'a','hours':'100000000000000000000000.000000000001',
             'cost':'0','value':'1','requires':[]},
            {'id':'b','hours':'0.000000000001','cost':'0','value':'1','requires':[]},
        ]
        result=self.run_goal(raw)
        self.assertEqual(result['status'],'DECIDED')
        self.assertEqual(result['result']['selected'],['a','b'])
        self.assertEqual(result['result']['candidates'][0]['hours'],
                         '100000000000000000000000.000000000002')
        self.assertEqual(result['verification']['status'],'PASS')

if __name__=='__main__':
    unittest.main()
