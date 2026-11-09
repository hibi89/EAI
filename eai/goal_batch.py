"""P12 read-only SHA256-pinned batch of already verified local typed goals."""
import csv
import hashlib
from pathlib import Path
import re

from .decision_engine import ID_RE
from .goal_dispatch import _read_spec, execute_goal_document, MAX_GOAL_BYTES, ROUTED_KINDS

VERSION = 'eai.goal_batch.v1'
MAX_ITEMS = 6
SHA_RE = re.compile(r'^[0-9a-f]{64}$')
GOOD = frozenset({'DECIDED','AGREE'})
REVIEW = frozenset({'TIE','CONFLICT','UNAVAILABLE'})
SCOPE = ('서로 독립적인 로컬 CPU 목표만 검증합니다. 실제 작업·결제·파일 수정·외부 전송을 하지 않습니다. '
         '완료는 입력한 데이터로 각 솔버가 판단을 마쳤다는 뜻이며 현실 프로젝트의 완수는 아닙니다.')


def _hash_file(path: Path) -> str:
    if not path.is_file() or path.stat().st_size > MAX_GOAL_BYTES:
        raise ValueError('batch child must be a regular file <=64KiB')
    with path.open('rb') as reader:
        content = reader.read(MAX_GOAL_BYTES + 1)
    if len(content) > MAX_GOAL_BYTES:
        raise ValueError('batch child exceeds 64KiB')
    return hashlib.sha256(content).hexdigest()


def _validate(path: Path, manifest: object) -> tuple:
    if type(manifest) is not dict or set(manifest) != {
        'version','kind','continue_on_error','items'
    } or type(manifest['version']) is not int or manifest['version'] != 1 or (
        manifest['kind'] != 'goal_batch' or type(manifest['continue_on_error']) is not bool
    ):
        raise ValueError('invalid goal_batch contract')
    items = manifest['items']
    if type(items) is not list or not 1 <= len(items) <= MAX_ITEMS:
        raise ValueError('batch needs 1-6 goal entries')
    base = path.parent.resolve(strict=True)
    names, paths, targets = set(), set(), []
    for item in items:
        if type(item) is not dict or set(item) != {'id','goal','sha256'}:
            raise ValueError('invalid batch entry schema')
        name, relative, digest = item['id'], item['goal'], item['sha256']
        if type(name) is not str or not ID_RE.fullmatch(name) or name in names:
            raise ValueError('invalid or duplicate batch ID')
        if type(relative) is not str or not 1 <= len(relative) <= 512 or any(
            ord(char) < 32 or char in '\\:' for char in relative
        ):
            raise ValueError('batch goal path must be a short relative POSIX path')
        loc = Path(relative)
        if loc.is_absolute() or '..' in loc.parts:
            raise ValueError('batch path traversal denied')
        if type(digest) is not str or not SHA_RE.fullmatch(digest):
            raise ValueError('batch entry must include lowercase SHA256')
        target = (base/loc).resolve(strict=True)
        if not target.is_relative_to(base) or target == path or target in paths:
            raise ValueError('batch goal escapes directory, refers to self or duplicates a file')
        names.add(name)
        paths.add(target)
        targets.append((item, target))
    return tuple(targets)


def _aggregate(rows: list[dict]) -> dict:
    completed = sum(x['status'] in GOOD for x in rows)
    review = sum(x['status'] in REVIEW for x in rows)
    errors = sum(x['status'] == 'ERROR' for x in rows)
    skipped = sum(x['status'] == 'SKIPPED' for x in rows)
    status = ('PARTIAL' if completed or review else 'FAILED') if errors or skipped else (
        'REVIEW' if review else 'COMPLETE'
    )
    return {'status':status,'count':len(rows),'completed':completed,
            'review':review,'errors':errors,'skipped':skipped}


def verify_batch_receipt(manifest: dict, report: dict) -> dict:
    """Fail closed on forged batch metadata; child solvers own their math checks."""
    keys = {'version','status','manifest','continue_on_error','items','summary',
            'scope','verification'}
    if type(report) is not dict or set(report) != keys or report['version'] != VERSION or (
        report['scope'] != SCOPE or report['continue_on_error'] is not manifest['continue_on_error']
    ):
        raise ValueError('batch receipt mismatch: contract')
    entries = report['items']
    if type(entries) is not list or len(entries) != len(manifest['items']) or (
        type(report['manifest']) is not dict or
        set(report['manifest']) != {'filename','sha256'} or
        type(report['manifest']['sha256']) is not str or
        not SHA_RE.fullmatch(report['manifest']['sha256'])
    ):
        raise ValueError('batch receipt mismatch: manifest or entries')
    stopped = False
    for expect, item in zip(manifest['items'], entries):
        if type(item) is not dict or set(item) != {
            'id','goal','sha256','status','kind','verification','result','error'
        } or (item['id'],item['goal'],item['sha256']) != (
            expect['id'],expect['goal'],expect['sha256']
        ):
            raise ValueError('batch receipt mismatch: entry provenance')
        status = item['status']
        if stopped:
            if status != 'SKIPPED' or item['error'] != 'STOP_ON_ERROR' or (
                item['kind'] is not None or item['result'] is not None or
                item['verification'] != 'NOT_RUN'
            ):
                raise ValueError('batch receipt mismatch: stop policy')
        elif status == 'ERROR':
            if item['result'] is not None or item['kind'] is not None or (
                item['verification'] != 'NOT_RUN' or type(item['error']) is not str or
                not 1 <= len(item['error']) <= 200
            ):
                raise ValueError('batch receipt mismatch: error envelope')
            if not manifest['continue_on_error']:
                stopped = True
        elif status == 'SKIPPED':
            raise ValueError('batch receipt mismatch: unauthorized skip')
        else:
            child = item['result']
            if status not in GOOD | REVIEW or type(child) is not dict or (
                item['error'] is not None or item['verification'] != 'PASS' or
                item['kind'] not in ROUTED_KINDS or child.get('kind') != item['kind'] or
                child.get('status') != status
            ):
                raise ValueError('batch receipt mismatch: child result')
            info = child.get('input')
            check = child.get('verification')
            if type(info) is not dict or type(check) is not dict or (
                info.get('sha256') != item['sha256'] or check.get('status') != 'PASS'
            ):
                raise ValueError('batch receipt mismatch: child guard')
    summary = _aggregate(entries)
    if report['summary'] != summary or report['status'] != summary['status']:
        raise ValueError('batch receipt mismatch: forged aggregate')
    return {'version':'eai.batch_receipt.v1','status':'PASS',
            'checks':['provenance','order','child_guard','summary','stop_policy'],
            'policy':'READ_ONLY;NO_REMOTE;NO_RETRY'}


def execute_batch_document(manifest_file: str | Path) -> dict:
    path = Path(manifest_file).expanduser().resolve(strict=True)
    manifest, digest = _read_spec(path)
    entries = _validate(path, manifest)
    for item, goal in entries:
        if _hash_file(goal) != item['sha256']:
            raise ValueError('batch preflight SHA256 mismatch: nothing executed')
    rows, stop = [], False
    for item, goal in entries:
        row = {'id':item['id'],'goal':item['goal'],'sha256':item['sha256'],
               'status':None,'kind':None,'verification':'NOT_RUN',
               'result':None,'error':None}
        if stop:
            row['status'],row['error'] = 'SKIPPED','STOP_ON_ERROR'
        else:
            try:
                if _hash_file(goal) != item['sha256']:
                    raise ValueError('child changed since preflight')
                child = execute_goal_document(goal)
                if child['input']['sha256'] != item['sha256'] or (
                    child['verification']['status'] != 'PASS' or
                    _hash_file(goal) != item['sha256']
                ):
                    raise ValueError('child provenance or guard mismatch')
                row['status'],row['kind'],row['verification'],row['result'] = (
                    child['status'],child['kind'],'PASS',child
                )
            except (ValueError,OSError,UnicodeError,csv.Error,TimeoutError) as exc:
                row['status'] = 'ERROR'
                row['error'] = (type(exc).__name__+': '+str(exc))[:200]
                if not manifest['continue_on_error']:
                    stop = True
        rows.append(row)
    _, final_digest = _read_spec(path)
    if digest != final_digest:
        raise ValueError('batch manifest changed during execution')
    for item,goal in entries:
        if _hash_file(goal) != item['sha256']:
            raise ValueError('batch child changed during execution')
    summary = _aggregate(rows)
    output = {'version':VERSION,'status':summary['status'],
              'manifest':{'filename':path.name,'sha256':digest},
              'continue_on_error':manifest['continue_on_error'],
              'items':rows,'summary':summary,'scope':SCOPE,'verification':None}
    output['verification'] = verify_batch_receipt(manifest,output)
    return output


def render_batch(report: dict) -> str:
    summary = report['summary']
    lines = [f"EAI 로컬 목표 배치: {report['status']}",
             f"파일: {report['manifest']['filename']} / SHA256 {report['manifest']['sha256']}",
             f"검증: {report['verification']['status']}",
             f"완료 {summary['completed']}, 검토 {summary['review']}, "
             f"오류 {summary['errors']}, 미실행 {summary['skipped']}"]
    for item in report['items']:
        lines.append(item['id']+': '+item['status']+
                     (f" ({item['error']})" if item['error'] else ''))
    lines.append(report['scope'])
    return '\n'.join(lines)
