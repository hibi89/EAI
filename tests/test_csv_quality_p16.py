"""P16 independent read-only CSV quality domain, provenance and exact receipt tests."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.csv_quality import validate_quality_goal, execute_quality_goal, render_quality
from eai.quality_receipt import verify_quality_receipt
from eai.goal_dispatch import execute_goal_document
from eai.goal_batch import execute_batch_document
from eai.goal_pipeline import execute_pipeline_document
from eai.manifest_builder import build_goal_manifest


def specification():
    return {'version':1,'kind':'csv_quality','goal':'Invoice quality',
            'source':'dataset.csv','encoding':'utf-8-sig',
            'required':['rowid','amount'],'unique_by':['rowid'],
            'numeric_rules':[{'column':'amount','min':'0','max':'1000'}]}


BAD_CSV = ('rowid,amount,category\nA,10,ok\nB,-1,ok\nB,10,ok\n'
           'C,NaN,ok\nD,,ok\nE,1200,ok\n,2,ok\n')
GOOD_CSV = 'rowid,amount,category\nA,10,ok\nB,50,ok\n'


class CsvQualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.source=self.root/'dataset.csv'
        self.source.write_text(BAD_CSV,encoding='utf-8')
        self.spec=self.root/'quality.json'
        self.write(specification())

    def tearDown(self):
        self.tmp.cleanup()

    def write(self,data):
        self.spec.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')

    def run_goal(self,data=None):
        if data is not None:
            self.write(data)
        return execute_goal_document(self.spec)

    def test_synthetic_violations_and_independent_guard(self):
        result=self.run_goal()
        self.assertEqual(result['status'],'CONFLICT')
        self.assertEqual(result['route'],'csv.quality_gate.v1')
        self.assertEqual(result['verification']['status'],'PASS')
        self.assertEqual(result['verification']['diagnostics']['type'],'QUALITY_REVIEW')
        report=result['result']
        self.assertEqual(report['rows'],7)
        self.assertEqual(report['affected_records'],6)
        self.assertEqual(report['counts'],{
            'MISSING_REQUIRED':2,'DUPLICATE_KEY':1,'NOT_NUMERIC':1,
            'BELOW_MIN':1,'ABOVE_MAX':1})
        self.assertEqual(report['samples'][0],{'record':2,'code':'BELOW_MIN','column':'amount'})
        self.assertEqual(len(report['samples']),6)
        self.assertIn('레코드 2',render_quality(report))

    def test_clean_csv_agrees(self):
        self.source.write_text(GOOD_CSV)
        result=self.run_goal()
        self.assertEqual(result['status'],'AGREE')
        self.assertEqual(result['result']['affected_records'],0)
        self.assertEqual(result['result']['samples'],[])

    def test_header_only_never_claims_quality_success(self):
        self.source.write_text('rowid,amount,category\n')
        result=self.run_goal()
        self.assertEqual(result['status'],'UNAVAILABLE')
        self.assertEqual(result['verification']['diagnostics']['type'],'QUALITY_EMPTY')
        self.assertEqual(result['result']['rows'],0)

    def test_blank_optional_numeric_not_treated_as_zero(self):
        raw=specification()
        raw['required']=['rowid']
        self.source.write_text('rowid,amount,category\nA,,ok\n')
        result=self.run_goal(raw)
        self.assertEqual(result['status'],'AGREE')
        self.assertTrue(all(value==0 for value in result['result']['counts'].values()))

    def test_empty_keys_flagged_but_not_false_duplicate(self):
        self.source.write_text('rowid,amount,category\n,10,ok\n,20,ok\n')
        result=self.run_goal()
        self.assertEqual(result['result']['counts']['MISSING_REQUIRED'],2)
        self.assertEqual(result['result']['counts']['DUPLICATE_KEY'],0)

    def test_multi_column_key_uses_tuple_not_concat(self):
        raw=specification()
        raw['required']=['rowid','category','amount']
        raw['unique_by']=['rowid','category']
        self.source.write_text('rowid,amount,category\nA,10,BC\nAB,11,C\nA,12,BC\n')
        result=self.run_goal(raw)
        self.assertEqual(result['result']['counts']['DUPLICATE_KEY'],1)

    def test_exact_decimal_boundary(self):
        raw=specification()
        raw['numeric_rules']=[{'column':'amount','min':'0.3','max':'0.3'}]
        self.source.write_text('rowid,amount,category\nA,0.3,ok\n')
        self.assertEqual(self.run_goal(raw)['status'],'AGREE')
        self.source.write_text('rowid,amount,category\nA,0.300000000001,ok\n')
        self.assertEqual(self.run_goal(raw)['result']['counts']['ABOVE_MAX'],1)

    def test_supported_cp949_input(self):
        raw=specification()
        raw['encoding']='cp949'
        self.source.write_bytes('rowid,amount,category\nA,10,정상\n'.encode('cp949'))
        self.assertEqual(self.run_goal(raw)['status'],'AGREE')

    def test_raw_customer_values_do_not_leak_into_receipt(self):
        secret='CUSTOMER_SECRET_VALUE_XXYZ449'
        self.source.write_text('rowid,amount,category\n'+secret+',wat,private\n')
        output=json.dumps(self.run_goal(),ensure_ascii=False)
        self.assertNotIn(secret,output)
        self.assertNotIn('private',output)
        self.assertIn('NOT_NUMERIC',output)

    def test_extra_command_and_float_bounds_denied(self):
        raw=specification()
        raw['write_to']='data.csv'
        with self.assertRaises(ValueError):self.run_goal(raw)
        raw=specification()
        raw['numeric_rules'][0]['min']=0.0
        with self.assertRaises(ValueError):self.run_goal(raw)

    def test_unknown_column_and_duplicate_range_denied(self):
        raw=specification()
        raw['numeric_rules'][0]['column']='missing'
        with self.assertRaisesRegex(ValueError,'unknown column'):self.run_goal(raw)
        raw=specification()
        raw['numeric_rules'].append(deepcopy(raw['numeric_rules'][0]))
        with self.assertRaisesRegex(ValueError,'duplicate numeric'):self.run_goal(raw)

    def test_reversed_range_denied(self):
        raw=specification()
        raw['numeric_rules'][0]['min']='1001'
        with self.assertRaisesRegex(ValueError,'minimum exceeds'):self.run_goal(raw)

    def test_unique_by_must_be_required(self):
        raw=specification()
        raw['required']=['amount']
        with self.assertRaisesRegex(ValueError,'also be required'):self.run_goal(raw)

    def test_duplicate_or_unknown_csv_headers_denied(self):
        for content in ('rowid,rowid,amount\nA,A,10\n',
                        'rowid,ROWID,amount\nA,A,10\n',
                        'rowid,amount,amount\nA,10,10\n'):
            self.source.write_text(content)
            with self.subTest(content=content),self.assertRaises(ValueError):self.run_goal()
        self.source.write_text('other,amount\nA,10\n')
        with self.assertRaisesRegex(ValueError,'unknown column'):self.run_goal()

    def test_wrong_field_count_and_bad_csv_rejected(self):
        for text in ('rowid,amount,category\nA,10\n',
                     'rowid,amount,category\nA,10,ok,extra\n',
                     'rowid,amount,category\n"broken,10,ok\n'):
            self.source.write_text(text)
            with self.subTest(text=text),self.assertRaises((ValueError,__import__('csv').Error)):
                self.run_goal()

    def test_bounded_max_rows_and_field_length(self):
        self.source.write_text('rowid,amount,category\n'+'A,1,ok\n'*20001)
        with self.assertRaisesRegex(ValueError,'20000'):self.run_goal()
        self.source.write_text('rowid,amount,category\nA,1,'+'z'*4097+'\n')
        with self.assertRaises((ValueError,__import__('csv').Error)):self.run_goal()

    def test_bounded_max_file_size(self):
        self.source.write_bytes(b'a'*(5*1024*1024+1))
        with self.assertRaisesRegex(ValueError,'5MiB'):self.run_goal()

    def test_parent_and_absolute_source_paths_denied(self):
        for invalid in ('../private.csv','/tmp/private.csv','C:\\secret.csv'):
            raw=specification()
            raw['source']=invalid
            with self.subTest(path=invalid),self.assertRaises(ValueError):self.run_goal(raw)

    def test_symlink_escape_denied(self):
        outside=self.root.parent/(self.root.name+'.external.csv')
        outside.write_text(GOOD_CSV)
        try:
            link=self.root/'link.csv'
            try:link.symlink_to(outside)
            except (OSError,NotImplementedError):self.skipTest('symlinks not supported')
            raw=specification()
            raw['source']='link.csv'
            with self.assertRaisesRegex(ValueError,'escapes'):self.run_goal(raw)
        finally:
            outside.unlink(missing_ok=True)

    def test_mutated_source_during_scan_denied(self):
        from eai.csv_quality import source_snapshot as actual
        calls=[0]
        def tamper(path):
            calls[0]+=1
            result=actual(path)
            if calls[0]==1:
                self.source.write_text(self.source.read_text()+' ')
            return result
        with patch('eai.csv_quality.source_snapshot',side_effect=tamper):
            with self.assertRaisesRegex(ValueError,'source changed'):self.run_goal()

    def test_independent_guard_rejects_source_after_solver(self):
        goal=validate_quality_goal(specification(),self.spec)
        result=execute_quality_goal(goal)
        self.source.write_text(self.source.read_text()+'X')
        with self.assertRaisesRegex(ValueError,'quality receipt'):
            verify_quality_receipt(goal,result)

    def test_forged_status_count_samples_and_sha_rejected(self):
        goal=validate_quality_goal(specification(),self.spec)
        original=execute_quality_goal(goal)
        variations=[
            ('status','AGREE'),('counts',{'MISSING_REQUIRED':0}),
            ('samples',[]),('sha256','0'*64),('rows',1),
            ('affected_records',1),('columns',['different']),
            ('rules',{'required':[]}),('scope','trusted world')
        ]
        for key,value in variations:
            report=deepcopy(original)
            report[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'quality receipt'):
                verify_quality_receipt(goal,report)

    def test_bad_solver_cannot_fake_a_passed_goal(self):
        from eai.goal_dispatch import execute_quality_goal as actual
        def forge(goal):
            result=actual(goal)
            result['counts']['DUPLICATE_KEY']=0
            return result
        with patch('eai.goal_dispatch.execute_quality_goal',side_effect=forge):
            with self.assertRaisesRegex(ValueError,'quality receipt'):self.run_goal()

    def test_batch_quality_conflict_is_review_not_success(self):
        manifest=build_goal_manifest('batch',self.root,['quality=quality.json'])
        filename=self.root/'batch.json'
        filename.write_text(json.dumps(manifest))
        result=execute_batch_document(filename)
        self.assertEqual(result['status'],'REVIEW')
        self.assertEqual(result['items'][0]['kind'],'csv_quality')
        self.assertEqual(result['verification']['status'],'PASS')

    def test_pipeline_conflict_blocks_dependents(self):
        other=self.root/'schedule.json'
        other.write_text(json.dumps({'version':1,'kind':'schedule_tasks','goal':'Review',
                                     'deadline_hours':'1',
                                     'tasks':[{'id':'a','hours':'1','requires':[]}]}))
        manifest=build_goal_manifest('pipeline',self.root,
                                     ['quality=quality.json','next=schedule.json'],
                                     ['next=quality'])
        path=self.root/'pipe.json'
        path.write_text(json.dumps(manifest))
        report=execute_pipeline_document(path)
        self.assertEqual(report['status'],'REVIEW')
        self.assertEqual([x['status'] for x in report['items']],['CONFLICT','SKIPPED'])
        self.assertEqual(report['items'][1]['blocked_by'],['quality'])

    def test_readonly_and_network_not_called(self):
        before=self.source.read_bytes()
        with patch('eai.network.fetch_json',side_effect=AssertionError('network call')):
            result=self.run_goal()
        self.assertEqual(result['verification']['status'],'PASS')
        self.assertEqual(before,self.source.read_bytes())

    def test_cli_conflict_clean_empty_exit_codes(self):
        root=Path(__file__).resolve().parent.parent
        cmd=[sys.executable,'-m','eai','solve-goal',str(self.spec),'--json']
        for content,code,status in ((BAD_CSV,2,'CONFLICT'),
                                    (GOOD_CSV,0,'AGREE'),
                                    ('rowid,amount,category\n',3,'UNAVAILABLE')):
            self.source.write_text(content)
            completed=subprocess.run(cmd,cwd=root,text=True,capture_output=True,timeout=30)
            self.assertEqual(completed.returncode,code,completed.stderr)
            self.assertEqual(json.loads(completed.stdout)['status'],status)

    def test_checked_in_sample_and_doctor(self):
        root=Path(__file__).resolve().parent.parent
        data=root/'examples'/'sample_csv_quality_goal.json'
        csv_file=root/'examples'/'sample_quality.csv'
        before=csv_file.read_bytes()
        output=execute_goal_document(data)
        self.assertEqual(output['status'],'CONFLICT')
        self.assertEqual(output['verification']['status'],'PASS')
        self.assertEqual(csv_file.read_bytes(),before)
        doctor=subprocess.run([sys.executable,'-m','eai','doctor','--json'],
                              cwd=root,text=True,capture_output=True,timeout=35)
        self.assertEqual(doctor.returncode,0,doctor.stderr)
        parsed=json.loads(doctor.stdout)
        self.assertEqual(parsed['summary'],{'passed':9,'failed':0,'total':9})
        self.assertIn('csv_quality',[x['name'] for x in parsed['checks']])


if __name__ == '__main__':
    unittest.main()
