"""P15 stdout-only manifest builder for real pinned batch/pipeline CLI workflows."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.manifest_builder import build_goal_manifest
from eai.goal_batch import execute_batch_document
from eai.goal_pipeline import execute_pipeline_document


def choice():
    return {'version':1,'kind':'choose_options','goal':'Pick a',
            'criteria':[{'id':'cost','direction':'min','unit':'USD','weight':'1',
                         'score_min':'0','score_max':'10'}],
            'options':[{'id':'a','values':{'cost':'1'}},
                       {'id':'b','values':{'cost':'2'}}]}


def schedule():
    return {'version':1,'kind':'schedule_tasks','goal':'Finish',
            'deadline_hours':'3','tasks':[
                {'id':'first','hours':'1','requires':[]},
                {'id':'last','hours':'1','requires':['first']} ]}


class ManifestBuilderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.dir=Path(self.tmp.name)
        self.choice=self.dir/'choice.json'
        self.schedule=self.dir/'schedule.json'
        self.choice.write_text(json.dumps(choice()),encoding='utf-8')
        self.schedule.write_text(json.dumps(schedule()),encoding='utf-8')
        self.specs=['choose=choice.json','schedule=schedule.json']

    def tearDown(self):
        self.tmp.cleanup()

    def test_batch_builds_exact_source_hashes(self):
        data=build_goal_manifest('batch',self.dir,self.specs)
        self.assertEqual(data['kind'],'goal_batch')
        self.assertEqual(data['items'][0]['sha256'],
                         hashlib.sha256(self.choice.read_bytes()).hexdigest())
        self.assertEqual(data['items'][1]['sha256'],
                         hashlib.sha256(self.schedule.read_bytes()).hexdigest())

    def test_printed_batch_is_executable_after_explicit_user_save(self):
        data=build_goal_manifest('batch',self.dir,self.specs)
        target=self.dir/'run.json'
        target.write_text(json.dumps(data),encoding='utf-8')
        result=execute_batch_document(target)
        self.assertEqual(result['status'],'COMPLETE')
        self.assertEqual(result['verification']['status'],'PASS')

    def test_pipeline_dependencies_execute_after_explicit_save(self):
        data=build_goal_manifest('pipeline',self.dir,self.specs,
                                 requires=['schedule=choose'])
        self.assertEqual(data['items'][1]['requires'],['choose'])
        target=self.dir/'pipeline.json'
        target.write_text(json.dumps(data),encoding='utf-8')
        report=execute_pipeline_document(target)
        self.assertEqual(report['status'],'COMPLETE')
        self.assertEqual(report['execution_order'],['choose','schedule'])
        self.assertEqual(report['verification']['status'],'PASS')

    def test_output_is_read_only(self):
        original={x.name:x.read_bytes() for x in self.dir.iterdir()}
        build_goal_manifest('pipeline',self.dir,self.specs,['schedule=choose'])
        self.assertEqual({x.name:x.read_bytes() for x in self.dir.iterdir()},original)

    def test_rejects_unknown_goal_id_and_duplicates(self):
        for goals in (['a=choice.json','a=schedule.json'],
                      ['bad-name!.json'],['a=choice.json','b=choice.json']):
            with self.subTest(goals=goals),self.assertRaises(ValueError):
                build_goal_manifest('batch',self.dir,goals)

    def test_rejects_absolute_drive_and_parent_path(self):
        for spec in ('a=/tmp/outside.json','a=C:\\secret.json','a=../foo.json'):
            with self.subTest(spec=spec),self.assertRaises(ValueError):
                build_goal_manifest('batch',self.dir,[spec])

    def test_rejects_unknown_or_cyclic_dependencies(self):
        for deps in (['schedule=unknown'],['choose=schedule','schedule=choose'],
                     ['schedule=schedule'],['schedule=choose,choose']):
            with self.subTest(deps=deps),self.assertRaises(ValueError):
                build_goal_manifest('pipeline',self.dir,self.specs,deps)

    def test_batch_dependency_args_are_denied(self):
        with self.assertRaisesRegex(ValueError,'pipeline'):
            build_goal_manifest('batch',self.dir,self.specs,['schedule=choose'])

    def test_pipeline_duplicate_dependency_rule_denied(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):
            build_goal_manifest('pipeline',self.dir,self.specs,
                                ['schedule=choose','schedule=choose'])

    def test_unknown_goal_kind_denied(self):
        self.schedule.write_text(json.dumps({'version':1,'kind':'execute_shell'}))
        with self.assertRaisesRegex(ValueError,'unknown typed'):
            build_goal_manifest('batch',self.dir,self.specs)

    def test_rejects_seven_or_zero_items(self):
        with self.assertRaisesRegex(ValueError,'1-6'):
            build_goal_manifest('batch',self.dir,[])
        with self.assertRaisesRegex(ValueError,'1-6'):
            build_goal_manifest('batch',self.dir,['a=choice.json']*7)

    def test_oversized_file_denied(self):
        self.choice.write_text(' '*65537)
        with self.assertRaises(ValueError):
            build_goal_manifest('batch',self.dir,['a=choice.json'])

    def test_invalid_root_denied(self):
        with self.assertRaises(OSError):
            build_goal_manifest('batch',self.dir/'missing',self.specs)

    def test_mismatched_source_mid_build_denied(self):
        from eai.manifest_builder import _read_spec as original
        def mutate(path):
            parsed,digest=original(path)
            if path.name=='choice.json':
                path.write_text(path.read_text()+' ')
            return parsed,digest
        with patch('eai.manifest_builder._read_spec',side_effect=mutate):
            with self.assertRaisesRegex(ValueError,'changed'):
                build_goal_manifest('batch',self.dir,self.specs)

    def test_rejects_symlink_escape_if_supported(self):
        outside=self.dir.parent/(self.dir.name+'.external.json')
        outside.write_text(json.dumps(choice()))
        try:
            link=self.dir/'link.json'
            try:link.symlink_to(outside)
            except (OSError,NotImplementedError):self.skipTest('Symlinks restricted by OS')
            with self.assertRaisesRegex(ValueError,'escapes'):
                build_goal_manifest('batch',self.dir,['x=link.json'])
        finally:
            outside.unlink(missing_ok=True)

    def test_cli_build_batch_stdout_only(self):
        root=Path(__file__).resolve().parent.parent
        before=set(self.dir.iterdir())
        proc=subprocess.run([sys.executable,'-m','eai','make-manifest',
                             '--mode','batch','--root',str(self.dir),
                             '--goal',self.specs[0],'--goal',self.specs[1]],
                            cwd=root,capture_output=True,text=True,timeout=20)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['kind'],'goal_batch')
        self.assertEqual(set(self.dir.iterdir()),before)

    def test_cli_pipeline_stop_on_error_and_dependency(self):
        root=Path(__file__).resolve().parent.parent
        proc=subprocess.run([sys.executable,'-m','eai','make-manifest',
                             '--mode','pipeline','--root',str(self.dir),
                             '--goal',self.specs[0],'--goal',self.specs[1],
                             '--requires','schedule=choose','--stop-on-error'],
                            cwd=root,capture_output=True,text=True,timeout=20)
        self.assertEqual(proc.returncode,0,proc.stderr)
        data=json.loads(proc.stdout)
        self.assertFalse(data['continue_on_error'])
        self.assertEqual(data['items'][1]['requires'],['choose'])

    def test_cli_invalid_spec_returns_one_without_traceback(self):
        root=Path(__file__).resolve().parent.parent
        proc=subprocess.run([sys.executable,'-m','eai','make-manifest',
                             '--mode','batch','--root',str(self.dir),
                             '--goal','invalid'],cwd=root,capture_output=True,
                            text=True,timeout=20)
        self.assertEqual(proc.returncode,1)
        self.assertIn('EAI MANIFEST ERROR',proc.stderr)
        self.assertNotIn('Traceback',proc.stderr)

    def test_no_model_or_network_required(self):
        with patch('eai.network.fetch_json',side_effect=AssertionError('network')):
            data=build_goal_manifest('batch',self.dir,self.specs)
        self.assertEqual(data['kind'],'goal_batch')


if __name__=='__main__':
    unittest.main()
