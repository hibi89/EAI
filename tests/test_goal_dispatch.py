"""P7 multi-domain goal router with strict file provenance and no execution injection."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.goal_dispatch import execute_goal_document, render_goal_document, _read_spec


class GoalRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.path = self.dir / 'goal.json'
        self.options = {
            'version':1,'kind':'choose_options','goal':'buy hardware',
            'criteria':[{'id':'cost','direction':'min','unit':'USD','weight':'1',
                         'score_min':'0','score_max':'1000', 'hard_max':'900'}],
            'options':[{'id':'A','values':{'cost':'500'}},
                       {'id':'B','values':{'cost':'600'}}],
        }

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, payload):
        self.path.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
        return self.path

    def call_cli(self, *args):
        root = Path(__file__).resolve().parent.parent
        return subprocess.run([sys.executable,'-m','eai','solve-goal',str(self.path),*args],
                              cwd=root,text=True,capture_output=True,timeout=20)

    def test_dispatch_options_winner_and_file_sha(self):
        self.write(self.options)
        result = execute_goal_document(self.path)
        self.assertEqual(result['status'], 'DECIDED')
        self.assertEqual(result['result']['winners'], ['A'])
        self.assertEqual(result['route'], 'decision.select.v1')
        self.assertEqual(result['input']['sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(len(result['steps']), 3)
        self.assertIn('최고 점수', render_goal_document(result))

    def test_dispatch_csv_domain_reuses_p6(self):
        a,b=self.dir/'a.csv',self.dir/'b.csv'
        a.write_text('key,value\nA,10\nB,20\n')
        b.write_text('key,value\nA,11\nB,19\n')
        self.write({'version':1,'kind':'csv_audit','left':'a.csv','right':'b.csv',
                    'key':'key','values':['value']})
        result=execute_goal_document(self.path)
        self.assertEqual(result['status'],'CONFLICT')
        self.assertEqual(result['route'],'csv.audit_plan.v1')
        self.assertEqual(result['result']['strategy'],'SINGLE_RECONCILE')
        self.assertEqual(result['result']['steps'][-1]['status'],'PASS')
        self.assertTrue(result['result']['escalation'])
        self.assertIn('충돌 세부 진단',render_goal_document(result))

    def test_dispatch_csv_agree(self):
        a,b=self.dir/'a.csv',self.dir/'b.csv'
        a.write_text('key,value\nA,10\nB,20\n')
        b.write_text('key,value\nB,20\nA,10\n')
        self.write({'version':1,'kind':'csv_audit','left':'a.csv','right':'b.csv',
                    'key':'key','values':['value']})
        self.assertEqual(execute_goal_document(self.path)['status'],'AGREE')

    def test_invalid_or_arbitrary_goal_kind_is_denied(self):
        for kind in ['shell.execute', 'arbitrary', None, [], 1]:
            raw=deepcopy(self.options);raw['kind']=kind
            self.write(raw)
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                execute_goal_document(self.path)

    def test_extra_parameters_must_not_be_ignored(self):
        raw=deepcopy(self.options);raw['exec']='python evil.py'
        self.write(raw)
        with self.assertRaises(ValueError):
            execute_goal_document(self.path)

    def test_duplicate_object_keys_rejected(self):
        self.path.write_text('{"version":1,"version":1,"kind":"choose_options"}')
        with self.assertRaisesRegex(ValueError,'duplicate'):
            execute_goal_document(self.path)

    def test_invalid_json_and_binary_rejected(self):
        for value in ['', '{bad}', '[]', 'true', '\x00', 'a'*65537]:
            self.path.write_text(value)
            with self.subTest(size=len(value)),self.assertRaises(ValueError):
                execute_goal_document(self.path)

    def test_too_large_goal_rejected_without_execution(self):
        self.path.write_bytes(b' '*65537)
        with patch('eai.goal_dispatch.execute_choice_goal',side_effect=AssertionError('executed')):
            with self.assertRaises(ValueError):
                execute_goal_document(self.path)

    def test_goal_spec_tamper_before_receipt_is_rejected(self):
        self.write(self.options)
        from eai.goal_dispatch import _read_spec as orig
        times=[0]
        def checked(path):
            times[0]+=1
            if times[0]==2:
                path.write_text(path.read_text()+' ')
            return orig(path)
        with patch('eai.goal_dispatch._read_spec',side_effect=checked):
            with self.assertRaisesRegex(ValueError,'changed'):
                execute_goal_document(self.path)

    def test_no_arbitrary_network_call(self):
        self.write(self.options)
        with patch('eai.network.fetch_json',side_effect=AssertionError('internet attempted')):
            self.assertEqual(execute_goal_document(self.path)['status'],'DECIDED')

    def test_cli_solved_and_json_receipt(self):
        self.write(self.options)
        run=self.call_cli('--json')
        self.assertEqual(run.returncode,0,run.stderr)
        result=json.loads(run.stdout)
        self.assertEqual(result['status'],'DECIDED')
        self.assertEqual(result['result']['winners'],['A'])

    def test_cli_all_infeasible_returns_code_3(self):
        data=deepcopy(self.options)
        data['criteria'][0]['hard_max']='100'
        self.write(data)
        run=self.call_cli('--json')
        self.assertEqual(run.returncode,3,run.stderr)
        self.assertEqual(json.loads(run.stdout)['status'],'UNAVAILABLE')

    def test_cli_tie_returns_code_zero_with_tie_explicit(self):
        data=deepcopy(self.options)
        data['options'][1]['values']['cost']='500'
        self.write(data)
        run=self.call_cli('--json')
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(run.stdout)['status'],'TIE')

    def test_cli_invalid_goal_is_error_code_1(self):
        self.write({'version':1,'kind':'shell'})
        result=self.call_cli()
        self.assertEqual(result.returncode,1)
        self.assertIn('EAI GOAL ERROR',result.stderr)
        self.assertNotIn('Traceback',result.stderr)

    def test_cli_csv_conflict_exit_2(self):
        a,b=self.dir/'a.csv',self.dir/'b.csv'
        a.write_text('key,value\nA,10\n')
        b.write_text('key,value\nA,11\n')
        self.write({'version':1,'kind':'csv_audit','left':'a.csv','right':'b.csv',
                    'key':'key','values':['value']})
        run=self.call_cli('--json')
        self.assertEqual(run.returncode,2,run.stderr)
        self.assertEqual(json.loads(run.stdout)['status'],'CONFLICT')

    def test_samples_work_and_no_extra_writes(self):
        root=Path(__file__).resolve().parent.parent
        sample=root/'examples'/'sample_hardware_decision.json'
        before=sample.read_bytes()
        result=execute_goal_document(sample)
        self.assertEqual(result['status'],'DECIDED')
        self.assertEqual(sample.read_bytes(),before)
        self.assertIn('balanced',result['pareto_frontier'] if 'pareto_frontier' in result else result['result']['pareto_frontier'])


if __name__=='__main__':
    unittest.main()
