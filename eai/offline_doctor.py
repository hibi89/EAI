"""P13 portable, no-network diagnostic of EAI installed source functionality.

Never probes cloud accounts or local Ollama; never changes user files or DB.
Tests only checked-in public-to-owner synthetic examples and SQLite in-memory.
"""
import hashlib
from pathlib import Path
import sqlite3
import sys

from .goal_dispatch import execute_goal_document
from .goal_batch import execute_batch_document
from .goal_pipeline import execute_pipeline_document

DOCTOR_VERSION = 'eai.offline_doctor.v1'
SAMPLES = (
    ('choose_options','sample_hardware_decision.json'),
    ('csv_audit','sample_csv_audit_goal.json'),
    ('plan_tasks','sample_task_portfolio_goal.json'),
    ('schedule_tasks','sample_task_schedule_goal.json'),
    ('csv_quality','sample_csv_quality_goal.json'),
    ('csv_schema_drift','sample_csv_schema_drift_goal.json'),
)
EXPECTED_STATUS = {
    'choose_options': 'DECIDED',
    'csv_audit': 'CONFLICT',
    'plan_tasks': 'DECIDED',
    'schedule_tasks': 'DECIDED',
    'csv_quality': 'CONFLICT',
    'csv_schema_drift': 'CONFLICT',
    'goal_batch': 'COMPLETE',
    'goal_pipeline': 'COMPLETE',
}

DOCTOR_SCOPE = ('오프라인 샘플, Python 및 임시 메모리 SQLite만 검사했습니다. '
                '실제 Windows PC, 사용자 데이터, Ollama/Qwen, SearXNG, GPU, '
                '외부 연결, 설치 프로그램과 상용 준비 상태는 검증하지 않습니다.')


def _file_sha256(source: Path, root: Path) -> str:
    resolved = source.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError('sample path escapes the verified directory')
    if not resolved.is_file() or resolved.stat().st_size > 64*1024:
        raise ValueError('expected an example file <=64 KiB')
    with resolved.open('rb') as stream:
        data = stream.read(64*1024+1)
    if len(data)>64*1024:
        raise ValueError('example exceeds 64 KiB')
    return hashlib.sha256(data).hexdigest()


def run_offline_doctor(project_root: str | Path | None = None) -> dict:
    """Test six bundled text-fixture goals + batch and pipeline; SQLite-file P18 is covered by CI."""
    root = (Path(project_root) if project_root is not None else
            Path(__file__).resolve().parent.parent).expanduser().resolve()
    checks = []
    py_ok = sys.version_info >= (3,11)
    checks.append({'name':'python_3_11','status':'PASS' if py_ok else 'FAIL',
                   'observed':sys.version.split()[0],'source_sha256':None,'error':None})
    try:
        connection = sqlite3.connect(':memory:')
        try:
            ok = connection.execute('SELECT 2+3').fetchone() == (5,)
        finally:
            connection.close()
        if not ok:
            raise ValueError('SQLite memory query mismatch')
        checks.append({'name':'sqlite_memory','status':'PASS','observed':'SQLITE_MEMORY_OK',
                       'source_sha256':None,'error':None})
    except (ValueError,OSError,sqlite3.Error) as exc:
        checks.append({'name':'sqlite_memory','status':'FAIL','observed':None,
                       'source_sha256':None,'error':type(exc).__name__})
    for kind,filename in (*SAMPLES,('goal_batch','sample_goal_batch.json'),
                          ('goal_pipeline','sample_goal_pipeline.json')):
        entry = {'name':kind,'status':'FAIL','observed':None,
                 'source_sha256':None,'error':None}
        source = root/'examples'/filename
        try:
            before = _file_sha256(source,root)
            result = (execute_batch_document(source) if kind == 'goal_batch'
                      else execute_pipeline_document(source) if kind == 'goal_pipeline'
                      else execute_goal_document(source))
            after = _file_sha256(source,root)
            verification = result.get('verification')
            if type(verification) is not dict or verification.get('status') != 'PASS':
                raise ValueError('sample independent receipt guard did not PASS')
            if result.get('status') != EXPECTED_STATUS[kind]:
                raise ValueError('bundled sample status does not match its acceptance contract')
            if kind not in {'goal_batch','goal_pipeline'} and (
                result.get('kind') != kind or
                result.get('input',{}).get('sha256') != before
            ):
                raise ValueError('typed goal result or source provenance mismatch')
            if before != after:
                raise ValueError('sample file changed during diagnosis')
            entry.update(status='PASS',observed=result['status'],source_sha256=before)
        except (ValueError,OSError,UnicodeError,TimeoutError,KeyError,TypeError) as exc:
            entry['error'] = type(exc).__name__
        checks.append(entry)
    passed = sum(x['status']=='PASS' for x in checks)
    return {'version':DOCTOR_VERSION,'status':'PASS' if passed==len(checks) else 'FAIL',
            'platform':sys.platform,'python':sys.version.split()[0],
            'checks':checks,'summary':{'passed':passed,'failed':len(checks)-passed,
                                        'total':len(checks)},'scope':DOCTOR_SCOPE}


def render_doctor(report: dict) -> str:
    lines = [f"EAI 오프라인 자체 진단: {report['status']}",
             f"플랫폼: {report['platform']} / Python: {report['python']}",
             f"PASS {report['summary']['passed']} / FAIL {report['summary']['failed']}"]
    for check in report['checks']:
        lines.append(f"{check['name']}: {check['status']}"+
                     (f" ({check['error']})" if check['error'] else ''))
    lines.append(report['scope'])
    return '\n'.join(lines)
