"""P17 local two-source CSV schema drift detection, validation and receipt tests."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.csv_schema_drift import validate_drift_goal, execute_drift_goal, render_drift
from eai.drift_receipt import verify_drift_receipt
from eai.goal_dispatch import execute_goal_document
from eai.manifest_builder import build_goal_manifest
from eai.goal_batch import execute_batch_document
from eai.goal_pipeline import execute_pipeline_document


def drift_spec():
    return {'version':1,'kind':'csv_schema_drift','goal':'Compare two CSV releases',
            'baseline':'base.csv','current':'new.csv','encoding':'utf-8-sig'}


BASE='id,amount,status\nA,10,active\nB,20,closed\n'
CHANGED='id,amount,notes\nA,10,ok\nB,not_numeric,note\n'


class CsvSchemaDriftTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.left=self.root/'base.csv'
        self.right=self.root/'new.csv'
        self.left.write_text(BASE,encoding='utf-8')
        self.right.write_text(CHANGED,encoding='utf-8')
        self.spec=self.root/'drift.json'
        self.write(drift_spec())

    def tearDown(self):
        self.tmp.cleanup()

    def write(self,raw):
        self.spec.write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')

    def run_goal(self,raw=None):
        if raw is not None:self.write(raw)
        return execute_goal_document(self.spec)

    def test_synthetic_schema_change_and_guard(self):
        out=self.run_goal()
        self.assertEqual(out['status'],'CONFLICT')
        self.assertEqual(out['route'],'csv.schema_drift.v1')
        self.assertEqual(out['verification']['status'],'PASS')
        self.assertEqual(out['verification']['diagnostics']['type'],'SCHEMA_DRIFT_REVIEW')
        d=out['result']['changes']
        self.assertEqual(d['added'],['notes'])
        self.assertEqual(d['removed'],['status'])
        self.assertFalse(d['reordered'])
        self.assertEqual(d['type_changes'],[
            {'column':'amount','before':'numeric','after':'mixed'}])
        self.assertIn('notes',render_drift(out['result']))
        self.assertEqual(out['result']['baseline']['rows'],2)
        self.assertEqual(out['result']['current']['rows'],2)

    def test_same_schema_with_different_rows_agrees(self):
        self.right.write_text('id,amount,status\nA,1,ok\nB,2,ok\nC,3,ok\n')
        out=self.run_goal()
        self.assertEqual(out['status'],'AGREE')
        self.assertEqual(out['result']['changes']['type_changes'],[])
        self.assertEqual(out['result']['current']['rows'],3)

    def test_order_change_is_detected_without_false_add_remove(self):
        self.right.write_text('status,amount,id\nok,10,A\nclosed,20,B\n')
        out=self.run_goal()
        self.assertEqual(out['status'],'CONFLICT')
        d=out['result']['changes']
        self.assertTrue(d['reordered'])
        self.assertEqual(d['added'],[])
        self.assertEqual(d['removed'],[])
        self.assertEqual(d['type_changes'],[])

    def test_missing_column_and_extra_column_detected(self):
        self.right.write_text('id,amount,extra\nA,10,ok\n')
        out=self.run_goal()
        self.assertEqual(out['result']['changes']['removed'],['status'])
        self.assertEqual(out['result']['changes']['added'],['extra'])

    def test_type_only_change_detected(self):
        self.right.write_text('id,amount,status\nA,abc,active\nB,def,closed\n')
        d=self.run_goal()['result']['changes']
        self.assertEqual(d['type_changes'],[
            {'column':'amount','before':'numeric','after':'text'}])

    def test_header_only_both_is_unavailable(self):
        self.left.write_text('id,amount,status\n')
        self.right.write_text('id,amount,status\n')
        out=self.run_goal()
        self.assertEqual(out['status'],'UNAVAILABLE')
        self.assertEqual(out['verification']['diagnostics']['type'],
                         'SCHEMA_EVIDENCE_INCOMPLETE')

    def test_all_empty_column_stays_unavailable_even_with_rows(self):
        self.left.write_text('id,amount,status\nA,1,\n')
        self.right.write_text('id,amount,status\nB,2,\n')
        out=self.run_goal()
        self.assertEqual(out['status'],'UNAVAILABLE')
        self.assertEqual(out['result']['baseline']['profiles'][-1]['type'],'empty')

    def test_empty_column_against_nonempty_is_conflict(self):
        self.left.write_text('id,amount,status\nA,1,\n')
        self.right.write_text('id,amount,status\nB,2,active\n')
        out=self.run_goal()
        self.assertEqual(out['status'],'CONFLICT')
        self.assertEqual(out['result']['changes']['type_changes'][0]['column'],'status')

    def test_header_only_left_with_different_columns_is_conflict(self):
        self.left.write_text('id,amount\n')
        self.right.write_text('id,status\nA,ok\n')
        out=self.run_goal()
        self.assertEqual(out['status'],'CONFLICT')
        self.assertIn('status',out['result']['changes']['added'])

    def test_numeric_types_exact_fixed_point_syntax(self):
        self.left.write_text('id,amount,status\nA,0.3,ok\n')
        self.right.write_text('id,amount,status\nB,0.300000000001,ok\n')
        self.assertEqual(self.run_goal()['status'],'AGREE')
        self.assertEqual(self.run_goal()['result']['current']['profiles'][1]['type'],'numeric')

    def test_mixed_column_reported_without_actual_data_values(self):
        private='PRIVATE_CUSTOMER_NOTE_482948'
        self.right.write_text('id,amount,status\nA,10,ok\nB,20,'+private+'\n')
        out=json.dumps(self.run_goal(),ensure_ascii=False)
        self.assertNotIn(private,out)
        self.assertNotIn('PRIVATE_CUSTOMER',out)

    def test_cp949_encoding(self):
        raw=drift_spec()
        raw['encoding']='cp949'
        content='id,amount,status\n가,10,진행\n'
        self.left.write_bytes(content.encode('cp949'))
        self.right.write_bytes(content.encode('cp949'))
        self.assertEqual(self.run_goal(raw)['status'],'AGREE')

    def test_rejects_same_file_and_parent_paths(self):
        for source in ('base.csv','../private.csv','/tmp/private.csv','C:\\private.csv'):
            raw=drift_spec()
            raw['current']=source
            with self.subTest(source=source),self.assertRaises(ValueError):self.run_goal(raw)

    def test_rejects_extra_actions_and_invalid_encoding(self):
        raw=drift_spec()
        raw['execute']='rm'
        with self.assertRaises(ValueError):self.run_goal(raw)
        raw=drift_spec()
        raw['encoding']='latin-1'
        with self.assertRaisesRegex(ValueError,'encoding'):self.run_goal(raw)

    def test_rejects_duplicate_or_invalid_headers(self):
        for source in ('id,id,status\nA,1,x\n',
                       'id,ID,status\nA,1,x\n',
                       'id,amount,\nA,1,x\n',
                       'id,amount,status,extra,STATUS\nA,1,x,y,z\n'):
            self.left.write_text(source)
            with self.subTest(source=source),self.assertRaises(ValueError):self.run_goal()

    def test_rejects_malformed_row_and_quoted_csv(self):
        for text in ('id,amount,status\nA,1\n',
                     'id,amount,status\nA,1,x,extra\n',
                     'id,amount,status\n"unclosed,1,x\n'):
            self.left.write_text(text)
            with self.subTest(text=text),self.assertRaises((ValueError,__import__('csv').Error)):
                self.run_goal()

    def test_enforces_max_rows_file_and_cell(self):
        self.left.write_text('id,amount,status\n'+'A,1,x\n'*20001)
        with self.assertRaisesRegex(ValueError,'bound'):self.run_goal()
        self.left.write_text('id,amount,status\nA,1,'+'x'*4097+'\n')
        with self.assertRaises((ValueError,__import__('csv').Error)):self.run_goal()
        self.left.write_bytes(b'x'*(5*1024*1024+1))
        with self.assertRaisesRegex(ValueError,'5MiB'):self.run_goal()

    def test_symlink_escape_denied_if_supported(self):
        outside=self.root.parent/(self.root.name+'.outside.csv')
        outside.write_text(BASE)
        try:
            link=self.root/'link.csv'
            try:link.symlink_to(outside)
            except (OSError,NotImplementedError):self.skipTest('symlinks restricted')
            raw=drift_spec()
            raw['current']='link.csv'
            with self.assertRaisesRegex(ValueError,'escapes'):self.run_goal(raw)
        finally:
            outside.unlink(missing_ok=True)

    def test_forged_receipt_status_profiles_changes_hash_denied(self):
        goal=validate_drift_goal(drift_spec(),self.spec)
        base=execute_drift_goal(goal)
        mutations=[('status','AGREE'),('changes',{}),('baseline',{'rows':100}),
                   ('scope','trust'),('current',{'filename':'fake.csv'}),
                   ('encoding','cp949')]
        for key,value in mutations:
            fake=deepcopy(base)
            fake[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'schema drift receipt'):
                verify_drift_receipt(goal,fake)

    def test_source_tamper_after_scan_denied(self):
        from eai.csv_schema_drift import source_snapshot as real
        count=[0]
        def mutate(path):
            count[0]+=1
            raw=real(path)
            if count[0]==1:
                self.left.write_text(self.left.read_text()+' ')
            return raw
        with patch('eai.csv_schema_drift.source_snapshot',side_effect=mutate):
            with self.assertRaisesRegex(ValueError,'input changed during scan'):self.run_goal()

    def test_independent_guard_detects_source_changed(self):
        goal=validate_drift_goal(drift_spec(),self.spec)
        report=execute_drift_goal(goal)
        self.right.write_text(self.right.read_text()+'x')
        with self.assertRaisesRegex(ValueError,'schema drift receipt'):
            verify_drift_receipt(goal,report)

    def test_forged_solver_cannot_get_verified_pass(self):
        from eai.goal_dispatch import execute_drift_goal as original
        def fake(goal):
            result=original(goal)
            result['changes']['added']=[]
            return result
        with patch('eai.goal_dispatch.execute_drift_goal',side_effect=fake):
            with self.assertRaisesRegex(ValueError,'schema drift receipt'):self.run_goal()

    def test_batch_conflict_requires_review(self):
        manifest=build_goal_manifest('batch',self.root,['drift=drift.json'])
        path=self.root/'batch.json'
        path.write_text(json.dumps(manifest))
        out=execute_batch_document(path)
        self.assertEqual(out['status'],'REVIEW')
        self.assertEqual(out['items'][0]['kind'],'csv_schema_drift')

    def test_pipeline_conflict_holds_dependent(self):
        schedule=self.root/'schedule.json'
        schedule.write_text(json.dumps({'version':1,'kind':'schedule_tasks',
                                        'goal':'delivery','deadline_hours':'1',
                                        'tasks':[{'id':'x','hours':'1','requires':[]}]}))
        manifest=build_goal_manifest('pipeline',self.root,
                                     ['drift=drift.json','delivery=schedule.json'],
                                     ['delivery=drift'])
        path=self.root/'pipeline.json'
        path.write_text(json.dumps(manifest))
        result=execute_pipeline_document(path)
        self.assertEqual(result['status'],'REVIEW')
        self.assertEqual([x['status'] for x in result['items']],['SKIPPED','CONFLICT']
                         if result['execution_order']==['delivery','drift']
                         else ['CONFLICT','SKIPPED'])
        self.assertEqual(next(x for x in result['items'] if x['id']=='delivery')['blocked_by'],
                         ['drift'])

    def test_no_network_source_bytes_remain_unchanged(self):
        left,right=self.left.read_bytes(),self.right.read_bytes()
        with patch('eai.network.fetch_json',side_effect=AssertionError('network')):
            result=self.run_goal()
        self.assertEqual(result['verification']['status'],'PASS')
        self.assertEqual(left,self.left.read_bytes())
        self.assertEqual(right,self.right.read_bytes())

    def test_cli_status_exit_codes(self):
        root=Path(__file__).resolve().parent.parent
        cmd=[sys.executable,'-m','eai','solve-goal',str(self.spec),'--json']
        for left,right,exitcode,status in (
            (BASE,CHANGED,2,'CONFLICT'),
            (BASE,'id,amount,status\nA,30,ok\n',0,'AGREE'),
            ('id,amount,status\n','id,amount,status\n',3,'UNAVAILABLE'),
        ):
            self.left.write_text(left)
            self.right.write_text(right)
            run=subprocess.run(cmd,cwd=root,text=True,capture_output=True,timeout=30)
            self.assertEqual(run.returncode,exitcode,run.stderr)
            self.assertEqual(json.loads(run.stdout)['status'],status)

    def test_checked_in_example_and_doctor_ten_checks(self):
        root=Path(__file__).resolve().parent.parent
        spec=root/'examples'/'sample_csv_schema_drift_goal.json'
        a=root/'examples'/'sample_drift_baseline.csv'
        b=root/'examples'/'sample_drift_current.csv'
        before=(a.read_bytes(),b.read_bytes())
        result=execute_goal_document(spec)
        self.assertEqual(result['status'],'CONFLICT')
        self.assertEqual(result['verification']['status'],'PASS')
        self.assertEqual((a.read_bytes(),b.read_bytes()),before)
        doctor=subprocess.run([sys.executable,'-m','eai','doctor','--json'],
                              cwd=root,text=True,capture_output=True,timeout=40)
        self.assertEqual(doctor.returncode,0,doctor.stderr)
        obj=json.loads(doctor.stdout)
        self.assertEqual(obj['summary'],{'passed':10,'failed':0,'total':10})
        self.assertIn('csv_schema_drift',[c['name'] for c in obj['checks']])


if __name__=='__main__':
    unittest.main()
