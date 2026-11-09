"""P14 read-only DAG pipeline and independent receipt gate regression."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.goal_pipeline import execute_pipeline_document, verify_pipeline_receipt


def options():
    return {'version':1,'kind':'choose_options','goal':'A vs B',
            'criteria':[{'id':'price','direction':'min','unit':'USD','weight':'1',
                         'score_min':'0','score_max':'100'}],
            'options':[{'id':'A','values':{'price':'10'}},
                       {'id':'B','values':{'price':'20'}}]}


def schedule():
    return {'version':1,'kind':'schedule_tasks','goal':'Schedule',
            'deadline_hours':'3','tasks':[
                {'id':'start','hours':'2','requires':[]},
                {'id':'finish','hours':'1','requires':['start']} ]}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.manifest=self.root/'pipeline.json'
        self.entries=[]
        self.add('first','choice.json',options(),[])
        self.add('second','schedule.json',schedule(),['first'])

    def tearDown(self):
        self.tmp.cleanup()

    def add(self,ident,name,data,requires):
        source=self.root/name
        source.write_text(json.dumps(data),encoding='utf-8')
        self.entries.append({'id':ident,'goal':name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                             'requires':requires})

    def write(self,allow=True,items=None):
        raw={'version':1,'kind':'goal_pipeline','continue_on_error':allow,
             'items':deepcopy(self.entries if items is None else items)}
        self.manifest.write_text(json.dumps(raw),encoding='utf-8')
        return raw

    def test_verified_chain_executes(self):
        self.write()
        out=execute_pipeline_document(self.manifest)
        self.assertEqual(out['status'],'COMPLETE')
        self.assertEqual(out['execution_order'],['first','second'])
        self.assertEqual(out['summary']['completed'],2)
        self.assertEqual(out['verification']['status'],'PASS')

    def test_out_of_order_input_toposorted(self):
        self.write(items=[self.entries[1],self.entries[0]])
        self.assertEqual(execute_pipeline_document(self.manifest)['execution_order'],
                         ['first','second'])

    def test_review_blocks_dependent_but_independent_proceeds(self):
        data=schedule()
        data['deadline_hours']='1'
        self.entries=[]
        self.add('first','first.json',data,[])
        self.add('second','second.json',options(),['first'])
        self.add('third','third.json',options(),[])
        self.write()
        out=execute_pipeline_document(self.manifest)
        rows={x['id']:x for x in out['items']}
        self.assertEqual(out['status'],'REVIEW')
        self.assertEqual(rows['first']['status'],'UNAVAILABLE')
        self.assertEqual(rows['second']['status'],'SKIPPED')
        self.assertEqual(rows['second']['blocked_by'],['first'])
        self.assertEqual(rows['third']['status'],'DECIDED')

    def test_continue_after_error_runs_independent(self):
        self.entries=[]
        self.add('bad','bad.json',{'kind':'shell'},[])
        self.add('dependent','dep.json',options(),['bad'])
        self.add('other','other.json',options(),[])
        self.write(True)
        out=execute_pipeline_document(self.manifest)
        rows={x['id']:x for x in out['items']}
        self.assertEqual(out['status'],'PARTIAL')
        self.assertEqual(rows['bad']['status'],'ERROR')
        self.assertEqual(rows['dependent']['error'],'DEPENDENCY_NOT_READY')
        self.assertEqual(rows['other']['status'],'DECIDED')

    def test_stop_after_error_holds_all(self):
        self.entries=[]
        self.add('a','bad.json',{'kind':'shell'},[])
        self.add('b','good.json',options(),[])
        self.write(False)
        out=execute_pipeline_document(self.manifest)
        self.assertEqual(out['status'],'FAILED')
        self.assertEqual([x['status'] for x in out['items']],['ERROR','SKIPPED'])
        self.assertEqual(out['items'][1]['error'],'STOP_ON_ERROR')

    def test_preflight_sha_mismatch_blocks_everything(self):
        self.write()
        (self.root/'schedule.json').write_text('{}')
        with patch('eai.goal_pipeline.execute_goal_document',side_effect=AssertionError('executed')):
            with self.assertRaisesRegex(ValueError,'preflight SHA256'):
                execute_pipeline_document(self.manifest)

    def test_unknown_and_cyclic_dependencies_denied(self):
        for requires in (['missing'],['first']):
            items=deepcopy(self.entries)
            items[0]['requires']=requires
            self.write(items=items)
            with self.assertRaises(ValueError):
                execute_pipeline_document(self.manifest)
        items=deepcopy(self.entries)
        items[0]['requires']=['second']
        self.write(items=items)
        with self.assertRaisesRegex(ValueError,'cyclic'):
            execute_pipeline_document(self.manifest)

    def test_duplicate_and_extra_instruction_denied(self):
        items=deepcopy(self.entries)
        items[0]['requires']=['second','second']
        self.write(items=items)
        with self.assertRaises(ValueError):
            execute_pipeline_document(self.manifest)
        items=deepcopy(self.entries)
        items[0]['shell']='run'
        self.write(items=items)
        with self.assertRaises(ValueError):
            execute_pipeline_document(self.manifest)

    def test_duplicate_goal_file_and_path_escape_denied(self):
        for name in ('choice.json','../outside.json','C:\\private\\file.json'):
            items=deepcopy(self.entries)
            items[1]['goal']=name
            self.write(items=items)
            with self.assertRaises(ValueError):
                execute_pipeline_document(self.manifest)

    def test_forged_pipeline_summary_denied(self):
        spec=self.write()
        out=execute_pipeline_document(self.manifest)
        out['summary']['completed']=99
        with self.assertRaisesRegex(ValueError,'aggregate'):
            verify_pipeline_receipt(spec,out)

    def test_forged_dependency_gate_denied(self):
        data=schedule()
        data['deadline_hours']='1'
        self.entries=[]
        self.add('first','first.json',data,[])
        self.add('second','second.json',options(),['first'])
        spec=self.write()
        out=execute_pipeline_document(self.manifest)
        out['items'][1]['status']='DECIDED'
        with self.assertRaisesRegex(ValueError,'gated execution'):
            verify_pipeline_receipt(spec,out)

    def test_forged_provenance_denied(self):
        spec=self.write()
        out=execute_pipeline_document(self.manifest)
        out['items'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'provenance'):
            verify_pipeline_receipt(spec,out)

    def test_cli_completed_and_review_exit_codes(self):
        self.write()
        root=Path(__file__).resolve().parent.parent
        cmd=[sys.executable,'-m','eai','pipeline-goals',str(self.manifest),'--json']
        done=subprocess.run(cmd,cwd=root,capture_output=True,text=True,timeout=30)
        self.assertEqual(done.returncode,0,done.stderr)
        self.assertEqual(json.loads(done.stdout)['status'],'COMPLETE')
        data=schedule()
        data['deadline_hours']='1'
        self.entries=[]
        self.add('first','first.json',data,[])
        self.add('second','second.json',options(),['first'])
        self.write()
        review=subprocess.run(cmd,cwd=root,capture_output=True,text=True,timeout=30)
        self.assertEqual(review.returncode,2,review.stderr)
        self.assertEqual(json.loads(review.stdout)['status'],'REVIEW')

    def test_original_files_unchanged_and_no_network(self):
        self.write()
        source=[self.manifest,self.root/'choice.json',self.root/'schedule.json']
        before=[x.read_bytes() for x in source]
        with patch('eai.network.fetch_json',side_effect=AssertionError('network')):
            result=execute_pipeline_document(self.manifest)
        self.assertEqual(result['status'],'COMPLETE')
        self.assertEqual([x.read_bytes() for x in source],before)

    def test_checked_in_pipeline_example(self):
        root=Path(__file__).resolve().parent.parent
        out=execute_pipeline_document(root/'examples'/'sample_goal_pipeline.json')
        self.assertEqual(out['status'],'COMPLETE')
        self.assertEqual(out['verification']['status'],'PASS')


    def test_postcondition_manifest_digest_mutation_rejected(self):
        spec = self.write()
        out = execute_pipeline_document(self.manifest)
        original_sha = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        out['manifest']['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'original manifest SHA256'):
            verify_pipeline_receipt(spec, out, original_sha256=original_sha)

    def test_noncanonical_independent_order_rejected(self):
        self.entries = []
        self.add('zeta', 'z.json', options(), [])
        self.add('alpha', 'a.json', options(), [])
        spec = self.write()
        out = execute_pipeline_document(self.manifest)
        self.assertEqual(out['execution_order'], ['alpha', 'zeta'])
        out['execution_order'].reverse()
        out['items'].reverse()
        with self.assertRaisesRegex(ValueError, 'noncanonical execution order'):
            verify_pipeline_receipt(spec, out)

    def test_nonstring_execution_order_is_fail_closed(self):
        spec = self.write()
        out = execute_pipeline_document(self.manifest)
        out['execution_order'][0] = []
        with self.assertRaisesRegex(ValueError, 'execution order'):
            verify_pipeline_receipt(spec, out)

if __name__=='__main__':
    unittest.main()
