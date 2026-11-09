"""P13 offline self-diagnostic checks, no external access or private data."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from eai.offline_doctor import run_offline_doctor, render_doctor


class OfflineDoctorTests(unittest.TestCase):
    def test_full_install_bundle_smoke_passes(self):
        report=run_offline_doctor()
        self.assertEqual(report['status'],'PASS',report)
        self.assertEqual(report['summary'],{'passed':8,'failed':0,'total':8})
        self.assertEqual(report['checks'][-1]['name'],'goal_batch')
        self.assertEqual(report['checks'][-1]['observed'],'COMPLETE')

    def test_report_avoids_home_and_customer_paths(self):
        output=run_offline_doctor()
        self.assertNotIn(str(Path.home()),json.dumps(output))
        self.assertNotIn('token',json.dumps(output).lower())
        self.assertIn('오프라인 자체 진단',render_doctor(output))

    def test_missing_project_examples_fail_without_traceback(self):
        with tempfile.TemporaryDirectory() as temp:
            report=run_offline_doctor(temp)
        self.assertEqual(report['status'],'FAIL')
        self.assertEqual(report['summary']['passed'],2)
        self.assertEqual(report['summary']['failed'],6)

    def test_fake_goal_guard_fails_diagnostic(self):
        with patch('eai.offline_doctor.execute_goal_document',
                   return_value={'kind':'choose_options','status':'DECIDED',
                                 'verification':{'status':'FAIL'}}):
            report=run_offline_doctor()
        self.assertEqual(report['status'],'FAIL')
        self.assertEqual(report['summary']['failed'],4)
        self.assertTrue(all(x['error']=='ValueError' for x in report['checks'][2:6]))

    def test_fake_batch_guard_failure_reports_fail(self):
        with patch('eai.offline_doctor.execute_batch_document',
                   return_value={'status':'COMPLETE','verification':{'status':'FAIL'}}):
            result=run_offline_doctor()
        self.assertEqual(result['summary']['failed'],1)
        self.assertEqual(result['checks'][-1]['error'],'ValueError')

    def test_sqlite_failure_is_isolated(self):
        with patch('eai.offline_doctor.sqlite3.connect',
                   side_effect=__import__('sqlite3').OperationalError('unavailable')):
            result=run_offline_doctor()
        self.assertEqual(result['summary']['failed'],1)
        self.assertEqual(result['checks'][1]['name'],'sqlite_memory')

    def test_python_version_gate_fails_closed(self):
        from collections import namedtuple
        Version=namedtuple('Version','major minor micro releaselevel serial')
        with patch('eai.offline_doctor.sys.version_info',Version(3,10,15,'final',0)):
            result=run_offline_doctor()
        self.assertEqual(result['summary']['failed'],1)
        self.assertEqual(result['checks'][0]['status'],'FAIL')

    def test_no_network_fetch(self):
        with patch('eai.network.fetch_json',side_effect=AssertionError('network call')):
            self.assertEqual(run_offline_doctor()['status'],'PASS')

    def test_cli_json_pass_and_platform(self):
        root=Path(__file__).resolve().parent.parent
        proc=subprocess.run([sys.executable,'-m','eai','doctor','--json'],
                            cwd=root,capture_output=True,text=True,timeout=40)
        self.assertEqual(proc.returncode,0,proc.stderr)
        output=json.loads(proc.stdout)
        self.assertEqual(output['status'],'PASS')
        self.assertEqual(output['platform'],sys.platform)

    def test_cli_text_output(self):
        root=Path(__file__).resolve().parent.parent
        proc=subprocess.run([sys.executable,'-m','eai','doctor'],
                            cwd=root,capture_output=True,text=True,timeout=40)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertIn('오프라인 자체 진단: PASS',proc.stdout)

    def test_cli_invalid_root_exit_four(self):
        root=Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as temp:
            proc=subprocess.run([sys.executable,'-m','eai','doctor','--root',temp,'--json'],
                                cwd=root,capture_output=True,text=True,timeout=40)
        self.assertEqual(proc.returncode,4,proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['status'],'FAIL')

    def test_windows_launcher_mentions_offline_doctor(self):
        root=Path(__file__).resolve().parent.parent
        cmd=(root/'RUN_EAI_DOCTOR.cmd').read_text(encoding='utf-8')
        self.assertIn('doctor --json',cmd)
        self.assertIn('py -3.11',cmd)
        self.assertNotIn('curl',cmd)


    def test_wrong_but_guarded_sample_status_is_not_health_pass(self):
        from eai.offline_doctor import execute_goal_document as original
        def altered(path):
            output = original(path)
            if path.name == 'sample_hardware_decision.json':
                output['status'] = 'UNAVAILABLE'
            return output
        with patch('eai.offline_doctor.execute_goal_document', side_effect=altered):
            result = run_offline_doctor()
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['summary']['failed'], 1)
        self.assertEqual(next(x for x in result['checks'] if x['name'] == 'choose_options')['error'],
                         'ValueError')

    def test_pipeline_failure_reports_one_failed_check(self):
        with patch('eai.offline_doctor.execute_pipeline_document',
                   return_value={'status':'COMPLETE','verification':{'status':'FAIL'}}):
            result = run_offline_doctor()
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['summary']['failed'], 1)
        self.assertEqual(result['checks'][-1]['name'], 'goal_pipeline')
        self.assertEqual(result['checks'][-1]['error'], 'ValueError')

if __name__=='__main__':
    unittest.main()
