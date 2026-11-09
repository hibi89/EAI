"""P11 genuine CLI CPU critical-path workflow and independent evidence mutation tests."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.task_schedule import execute_schedule_goal, validate_schedule_goal
from eai.goal_dispatch import execute_goal_document, render_goal_document
from eai.receipt_guard import verify_goal_receipt


def goal_fixture():
    return {
        'version':1,'kind':'schedule_tasks','goal':'Build verified release',
        'deadline_hours':'10',
        'tasks':[
            {'id':'extract','hours':'2','requires':[]},
            {'id':'models','hours':'3','requires':['extract']},
            {'id':'tests','hours':'4','requires':['models']},
            {'id':'docs','hours':'1','requires':['extract']},
            {'id':'ship','hours':'1','requires':['docs','tests']},
        ],
    }


class ScheduleTaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'schedule.json'

    def tearDown(self):
        self.tmp.cleanup()

    def run_goal(self, value):
        self.path.write_text(json.dumps(value), encoding='utf-8')
        return execute_goal_document(self.path)

    def test_cpm_critical_path_and_slack(self):
        out=self.run_goal(goal_fixture())
        self.assertEqual(out['status'],'DECIDED')
        self.assertEqual(out['result']['critical_path'],['extract','models','tests','ship'])
        self.assertEqual(out['result']['minimum_finish_hours'],'10')
        self.assertEqual(out['result']['deadline_margin_hours'],'0')
        self.assertEqual(out['result']['critical_tasks'],['extract','models','ship','tests'])
        docs=next(row for row in out['result']['tasks'] if row['id']=='docs')
        self.assertEqual(docs['slack'],'6')
        self.assertEqual(docs['earliest_start'],'2')
        self.assertEqual(docs['latest_start'],'8')
        self.assertEqual(out['verification']['status'],'PASS')

    def test_missed_deadline_is_unavailable_with_diagnostic(self):
        raw=goal_fixture();raw['deadline_hours']='9.5'
        out=self.run_goal(raw)
        self.assertEqual(out['status'],'UNAVAILABLE')
        self.assertEqual(out['result']['deadline_margin_hours'],'-0.5')
        self.assertEqual(out['verification']['diagnostics']['type'],'DEADLINE_EXCEEDED')
        self.assertIn('DEADLINE_EXCEEDED',render_goal_document(out))

    def test_exact_decimal_boundary(self):
        raw=goal_fixture()
        raw['tasks']=[{'id':'a','hours':'0.1','requires':[]},
                      {'id':'b','hours':'0.2','requires':['a']}]
        raw['deadline_hours']='0.3'
        self.assertEqual(self.run_goal(raw)['status'],'DECIDED')
        self.assertEqual(self.run_goal(raw)['result']['minimum_finish_hours'],'0.3')

    def test_parallel_branches_not_summed(self):
        raw=goal_fixture()
        raw['tasks']=[{'id':'a','hours':'3','requires':[]},
                      {'id':'b','hours':'5','requires':[]},
                      {'id':'c','hours':'2','requires':['a','b']}]
        raw['deadline_hours']='7'
        out=self.run_goal(raw)
        self.assertEqual(out['result']['minimum_finish_hours'],'7')
        self.assertEqual(out['result']['critical_path'],['b','c'])

    def test_lexical_representative_when_equal_critical_paths(self):
        raw=goal_fixture()
        raw['tasks']=[{'id':'b','hours':'2','requires':[]},
                      {'id':'a','hours':'2','requires':[]},
                      {'id':'done','hours':'1','requires':['b','a']}]
        raw['deadline_hours']='3'
        out=self.run_goal(raw)
        self.assertEqual(out['result']['critical_path'],['a','done'])
        self.assertEqual(out['result']['critical_tasks'],['a','b','done'])

    def test_zero_duration_and_zero_deadline(self):
        raw=goal_fixture()
        raw['tasks']=[{'id':'b','hours':'0','requires':['a']},
                      {'id':'a','hours':'0','requires':[]}]
        raw['deadline_hours']='0'
        self.assertEqual(self.run_goal(raw)['status'],'DECIDED')

    def test_one_task_and_no_dependency(self):
        raw=goal_fixture()
        raw['tasks']=[{'id':'alone','hours':'2','requires':[]}]
        self.assertEqual(self.run_goal(raw)['result']['critical_path'],['alone'])

    def test_unknown_self_and_cyclic_dependency_denied(self):
        for req in ('no','extract'):
            raw=goal_fixture();raw['tasks'][0]['requires']=[req]
            with self.subTest(req=req),self.assertRaises(ValueError):self.run_goal(raw)
        raw=goal_fixture()
        raw['tasks'][0]['requires']=['models']
        with self.assertRaisesRegex(ValueError,'cyclic'):self.run_goal(raw)

    def test_duplicates_denied(self):
        raw=goal_fixture()
        raw['tasks'][0]['requires']=['ship','ship']
        with self.assertRaises(ValueError):self.run_goal(raw)
        raw=goal_fixture()
        raw['tasks'][1]['id']='extract'
        with self.assertRaises(ValueError):self.run_goal(raw)

    def test_untrusted_extra_actions_denied(self):
        raw=goal_fixture();raw['execute']='shell'
        with self.assertRaises(ValueError):self.run_goal(raw)
        raw=goal_fixture();raw['tasks'][0]['write']='yes'
        with self.assertRaises(ValueError):self.run_goal(raw)

    def test_float_negative_and_boolean_denied(self):
        for invalid in (2.0,-1,True):
            raw=goal_fixture();raw['tasks'][0]['hours']=invalid
            with self.subTest(value=invalid),self.assertRaises(ValueError):self.run_goal(raw)
        raw=goal_fixture();raw['deadline_hours']='-0.1'
        with self.assertRaises(ValueError):self.run_goal(raw)

    def test_oversized_task_list_denied(self):
        raw=goal_fixture()
        raw['tasks']=[{'id':'t'+str(i),'hours':'1','requires':[]} for i in range(25)]
        with self.assertRaises(ValueError):self.run_goal(raw)

    def test_forced_fake_early_time_rejected(self):
        goal=validate_schedule_goal(goal_fixture())
        out=execute_schedule_goal(goal)
        next(x for x in out['tasks'] if x['id']=='ship')['earliest_start']='2'
        with self.assertRaisesRegex(ValueError,'영수증'):verify_goal_receipt('schedule_tasks',goal,out)

    def test_forged_critical_path_rejected(self):
        goal=validate_schedule_goal(goal_fixture())
        out=execute_schedule_goal(goal)
        out['critical_path']=['extract','docs','ship']
        with self.assertRaisesRegex(ValueError,'영수증'):verify_goal_receipt('schedule_tasks',goal,out)

    def test_forged_slack_and_deadline_rejected(self):
        goal=validate_schedule_goal(goal_fixture())
        for key,value in [('deadline_margin_hours','9'),('minimum_finish_hours','2')]:
            with self.subTest(key=key):
                out=execute_schedule_goal(goal);out[key]=value
                with self.assertRaisesRegex(ValueError,'영수증'):verify_goal_receipt('schedule_tasks',goal,out)
        out=execute_schedule_goal(goal);out['tasks'][0]['slack']='-1'
        with self.assertRaisesRegex(ValueError,'영수증'):verify_goal_receipt('schedule_tasks',goal,out)

    def test_original_file_preserved_no_network_or_model(self):
        self.path.write_text(json.dumps(goal_fixture()),encoding='utf-8')
        before=self.path.read_bytes()
        with patch('eai.network.fetch_json',side_effect=AssertionError('network attempted')):
            out=execute_goal_document(self.path)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(out['verification']['status'],'PASS')

    def test_cli_json_and_unavailable_status(self):
        root=Path(__file__).resolve().parent.parent
        for limit, expected_exit, expected_status in [('10',0,'DECIDED'),('9',3,'UNAVAILABLE')]:
            raw=goal_fixture();raw['deadline_hours']=limit
            self.path.write_text(json.dumps(raw),encoding='utf-8')
            process=subprocess.run([sys.executable,'-m','eai','solve-goal',str(self.path),'--json'],
                                   cwd=root,capture_output=True,text=True,timeout=20)
            self.assertEqual(process.returncode,expected_exit,process.stderr)
            self.assertEqual(json.loads(process.stdout)['status'],expected_status)

    def test_sample_doc_cli_is_read_only(self):
        root=Path(__file__).resolve().parent.parent
        example=root/'examples'/'sample_task_schedule_goal.json'
        before=example.read_bytes()
        out=execute_goal_document(example)
        self.assertEqual(out['verification']['status'],'PASS')
        self.assertEqual(example.read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
