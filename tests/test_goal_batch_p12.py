"""P12 true CLI and source-integrity tests for local bounded batch."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.goal_batch import execute_batch_document, verify_batch_receipt, render_batch


def sample_choice():
    return {'version':1,'kind':'choose_options','goal':'Local choice',
            'criteria':[{'id':'cost','direction':'min','unit':'USD','weight':'1',
                         'score_min':'0','score_max':'100'}],
            'options':[{'id':'local','values':{'cost':'0'}},
                       {'id':'cloud','values':{'cost':'20'}}]}


def sample_schedule():
    return {'version':1,'kind':'schedule_tasks','goal':'Release',
            'deadline_hours':'3','tasks':[
                {'id':'build','hours':'2','requires':[]},
                {'id':'verify','hours':'1','requires':['build']} ]}


class GoalBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.manifest=self.root/'batch.json'
        self.entries=[]
        self.add('choice','choice.json',sample_choice())
        self.add('schedule','schedule.json',sample_schedule())

    def tearDown(self):
        self.tmp.cleanup()

    def add(self,ident,filename,data):
        p=self.root/filename
        p.write_text(json.dumps(data),encoding='utf-8')
        self.entries.append({'id':ident,'goal':filename,
                             'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})

    def write(self,cont=True,items=None):
        spec={'version':1,'kind':'goal_batch','continue_on_error':cont,
              'items':deepcopy(self.entries if items is None else items)}
        self.manifest.write_text(json.dumps(spec),encoding='utf-8')
        return spec

    def test_two_goals_verified_and_read_only(self):
        self.write()
        paths=[self.manifest,self.root/'choice.json',self.root/'schedule.json']
        before=[p.read_bytes() for p in paths]
        output=execute_batch_document(self.manifest)
        self.assertEqual(output['status'],'COMPLETE')
        self.assertEqual(output['summary']['completed'],2)
        self.assertEqual(output['verification']['status'],'PASS')
        self.assertEqual([p.read_bytes() for p in paths],before)
        self.assertIn('완료 2',render_batch(output))

    def test_mixed_review_is_not_complete(self):
        data=sample_schedule()
        data['deadline_hours']='1'
        self.entries=[]
        self.add('late','late.json',data)
        self.write()
        out=execute_batch_document(self.manifest)
        self.assertEqual(out['status'],'REVIEW')
        self.assertEqual(out['summary']['review'],1)

    def test_continue_on_error_isolates_failure(self):
        self.add('bad','bad.json',{'kind':'shell'})
        items=[self.entries[2],self.entries[0]]
        self.write(True,items)
        out=execute_batch_document(self.manifest)
        self.assertEqual(out['status'],'PARTIAL')
        self.assertEqual([x['status'] for x in out['items']],['ERROR','DECIDED'])
        self.assertEqual(out['verification']['status'],'PASS')

    def test_stop_on_error_leaves_remaining_unexecuted(self):
        self.add('bad','bad.json',{'kind':'shell'})
        self.write(False,[self.entries[2],self.entries[0]])
        out=execute_batch_document(self.manifest)
        self.assertEqual(out['status'],'FAILED')
        self.assertEqual([x['status'] for x in out['items']],['ERROR','SKIPPED'])

    def test_checksum_preflight_prevents_any_execution(self):
        self.write()
        (self.root/'schedule.json').write_text('{}')
        with patch('eai.goal_batch.execute_goal_document',side_effect=AssertionError('launched')):
            with self.assertRaisesRegex(ValueError,'preflight SHA256'):
                execute_batch_document(self.manifest)

    def test_rejects_invalid_or_duplicate_ids(self):
        for key in ('id','goal'):
            items=deepcopy(self.entries)
            items[1][key]=items[0][key]
            self.write(items=items)
            with self.subTest(key=key),self.assertRaises(ValueError):
                execute_batch_document(self.manifest)

    def test_rejects_outside_absolute_and_windows_path(self):
        for path in ('../escape.json','/tmp/outside.json','C:\\Users\\secret.json'):
            items=deepcopy(self.entries)
            items[0]['goal']=path
            self.write(items=items)
            with self.subTest(path=path),self.assertRaises(ValueError):
                execute_batch_document(self.manifest)

    def test_rejects_excessive_count_and_bad_hash(self):
        extra=[{'id':'t'+str(i),'goal':'t'+str(i)+'.json','sha256':'0'*64}
               for i in range(5)]
        self.write(items=self.entries+extra)
        with self.assertRaisesRegex(ValueError,'1-6'):
            execute_batch_document(self.manifest)
        items=deepcopy(self.entries)
        items[0]['sha256']='X'*64
        self.write(items=items)
        with self.assertRaises(ValueError):
            execute_batch_document(self.manifest)

    def test_rejects_unknown_fields_and_bool_as_int(self):
        spec=self.write()
        spec['untrusted_shell']='echo'
        self.manifest.write_text(json.dumps(spec))
        with self.assertRaises(ValueError):
            execute_batch_document(self.manifest)
        spec.pop('untrusted_shell')
        spec['continue_on_error']=1
        self.manifest.write_text(json.dumps(spec))
        with self.assertRaises(ValueError):
            execute_batch_document(self.manifest)

    def test_symlink_escape_denied_if_supported(self):
        outside=self.root.parent/(self.root.name+'.outside.json')
        outside.write_text(json.dumps(sample_choice()))
        try:
            link=self.root/'link.json'
            try:link.symlink_to(outside)
            except (OSError,NotImplementedError):self.skipTest('symlink permission unavailable')
            items=deepcopy(self.entries)
            items[0]['goal']='link.json'
            items[0]['sha256']=hashlib.sha256(outside.read_bytes()).hexdigest()
            self.write(items=items)
            with self.assertRaisesRegex(ValueError,'escapes'):
                execute_batch_document(self.manifest)
        finally:
            outside.unlink(missing_ok=True)

    def test_rejects_self_reference(self):
        self.write()
        items=deepcopy(self.entries)
        items[0]['goal']='batch.json'
        self.write(items=items)
        with self.assertRaisesRegex(ValueError,'self'):
            execute_batch_document(self.manifest)

    def test_manifest_changed_during_run_fails_closed(self):
        self.write()
        from eai.goal_batch import execute_goal_document as original
        def injected(path):
            result=original(path)
            self.manifest.write_text(self.manifest.read_text()+' ')
            return result
        with patch('eai.goal_batch.execute_goal_document',side_effect=injected):
            with self.assertRaisesRegex(ValueError,'manifest changed'):
                execute_batch_document(self.manifest)

    def test_child_changed_during_run_fails_closed(self):
        self.write()
        from eai.goal_batch import execute_goal_document as original
        def injected(path):
            result=original(path)
            if path.name=='choice.json':
                path.write_text(path.read_text()+' ')
            return result
        with patch('eai.goal_batch.execute_goal_document',side_effect=injected):
            with self.assertRaisesRegex(ValueError,'child changed'):
                execute_batch_document(self.manifest)

    def test_forged_summary_detected(self):
        spec=self.write()
        result=execute_batch_document(self.manifest)
        result['summary']['completed']=50
        with self.assertRaisesRegex(ValueError,'forged aggregate'):
            verify_batch_receipt(spec,result)

    def test_forged_child_digest_detected(self):
        spec=self.write()
        result=execute_batch_document(self.manifest)
        result['items'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'provenance'):
            verify_batch_receipt(spec,result)

    def test_forged_child_guard_detected(self):
        spec=self.write()
        result=execute_batch_document(self.manifest)
        result['items'][0]['result']['verification']['status']='FAIL'
        with self.assertRaisesRegex(ValueError,'child guard'):
            verify_batch_receipt(spec,result)

    def test_cli_json_success(self):
        self.write()
        root=Path(__file__).resolve().parent.parent
        call=subprocess.run([sys.executable,'-m','eai','batch-goals',str(self.manifest),'--json'],
                            cwd=root,capture_output=True,text=True,timeout=30)
        self.assertEqual(call.returncode,0,call.stderr)
        self.assertEqual(json.loads(call.stdout)['status'],'COMPLETE')

    def test_cli_review_and_error_codes(self):
        data=sample_schedule()
        data['deadline_hours']='1'
        self.entries=[]
        self.add('late','late.json',data)
        self.write()
        root=Path(__file__).resolve().parent.parent
        cmd=[sys.executable,'-m','eai','batch-goals',str(self.manifest),'--json']
        report=subprocess.run(cmd,cwd=root,capture_output=True,text=True,timeout=30)
        self.assertEqual(report.returncode,2,report.stderr)
        self.assertEqual(json.loads(report.stdout)['status'],'REVIEW')
        self.manifest.write_text('{"bad":1}')
        invalid=subprocess.run(cmd,cwd=root,capture_output=True,text=True,timeout=30)
        self.assertEqual(invalid.returncode,1)
        self.assertNotIn('Traceback',invalid.stderr)

    def test_no_network_in_batch(self):
        self.write()
        with patch('eai.network.fetch_json',side_effect=AssertionError('network')):
            self.assertEqual(execute_batch_document(self.manifest)['status'],'COMPLETE')

    def test_checked_in_sample_receipt(self):
        root=Path(__file__).resolve().parent.parent
        sample=root/'examples'/'sample_goal_batch.json'
        before=sample.read_bytes()
        receipt=execute_batch_document(sample)
        self.assertEqual(receipt['status'],'COMPLETE')
        self.assertEqual(receipt['verification']['status'],'PASS')
        self.assertEqual(sample.read_bytes(),before)


if __name__=='__main__':
    unittest.main()
