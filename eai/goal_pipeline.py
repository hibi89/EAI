"""P14 deterministic, SHA-pinned read-only dependency-gated goal pipeline."""
import csv
from pathlib import Path

from .decision_engine import ID_RE
from .goal_batch import _validate, _hash_file, GOOD, REVIEW, SHA_RE
from .goal_dispatch import _read_spec, execute_goal_document, ROUTED_KINDS

VERSION = 'eai.goal_pipeline.v1'
SCOPE = ('명시된 의존성의 앞 목표가 검증된 DECIDED/AGREE 상태인 경우에만 '
         '다음 로컬 목표를 실행합니다. REVIEW/ERROR는 자동 승인되지 않으며 '
         '파일 쓰기·네트워크·자동 복구·작업 실행은 하지 않습니다.')


def _prepare(path: Path, manifest: dict):
    if type(manifest) is not dict or set(manifest) != {
        'version','kind','continue_on_error','items'
    } or type(manifest['version']) is not int or manifest['version'] != 1 or (
        manifest['kind'] != 'goal_pipeline' or
        type(manifest['continue_on_error']) is not bool
    ):
        raise ValueError('invalid goal_pipeline contract')
    items = manifest['items']
    if type(items) is not list or not 1 <= len(items) <= 6:
        raise ValueError('pipeline needs 1-6 explicit goals')
    converted = []
    dependencies = {}
    for item in items:
        if type(item) is not dict or set(item) != {'id','goal','sha256','requires'}:
            raise ValueError('invalid pipeline item fields')
        req = item['requires']
        if type(req) is not list or len(req) > 5 or any(
            type(x) is not str or not ID_RE.fullmatch(x) for x in req
        ) or len(set(req)) != len(req):
            raise ValueError('invalid pipeline dependencies')
        dependencies[item['id']] = tuple(sorted(req))
        converted.append({key:item[key] for key in ('id','goal','sha256')})
    converted_manifest = {'version':1,'kind':'goal_batch',
                          'continue_on_error':manifest['continue_on_error'],
                          'items':converted}
    entries = _validate(path,converted_manifest)
    paths = {item['id']:(item,target) for item,target in entries}
    if any(key in deps or any(dep not in paths for dep in deps)
           for key,deps in dependencies.items()):
        raise ValueError('pipeline unknown or self prerequisite')
    pending = set(paths)
    finished = set()
    order = []
    while pending:
        ready = sorted(key for key in pending if set(dependencies[key]) <= finished)
        if not ready:
            raise ValueError('cyclic pipeline dependencies')
        order.extend(ready)
        finished.update(ready)
        pending.difference_update(ready)
    return paths, dependencies, tuple(order)


def _aggregate(rows):
    completed = sum(item['status'] in GOOD for item in rows)
    review = sum(item['status'] in REVIEW for item in rows)
    errors = sum(item['status']=='ERROR' for item in rows)
    skipped = sum(item['status']=='SKIPPED' for item in rows)
    state = ('PARTIAL' if completed or review else 'FAILED') if errors else (
        'REVIEW' if review or skipped else 'COMPLETE'
    )
    return {'status':state,'count':len(rows),'completed':completed,
            'review':review,'errors':errors,'skipped':skipped}


def verify_pipeline_receipt(manifest: dict, report: dict, *, original_sha256: str | None = None) -> dict:
    """Validate DAG gates, status, immutable provenance and aggregate claims."""
    mandatory={'version','status','manifest','continue_on_error','execution_order',
               'items','summary','scope','verification'}
    if type(report) is not dict or set(report) != mandatory or (
        report['version'] != VERSION or report['scope'] != SCOPE or
        report['continue_on_error'] is not manifest['continue_on_error']
    ):
        raise ValueError('EAI pipeline receipt mismatch: contract')
    if type(report['manifest']) is not dict or set(report['manifest']) != {
        'filename','sha256'
    } or type(report['manifest']['sha256']) is not str or (
        not SHA_RE.fullmatch(report['manifest']['sha256']) or
        type(report['manifest']['filename']) is not str or
        not 1 <= len(report['manifest']['filename']) <= 512
    ):
        raise ValueError('EAI pipeline receipt mismatch: manifest')
    if original_sha256 is not None and (
        type(original_sha256) is not str or
        not SHA_RE.fullmatch(original_sha256) or
        report['manifest']['sha256'] != original_sha256
    ):
        raise ValueError('EAI pipeline receipt mismatch: original manifest SHA256')
    specification = {item['id']:item for item in manifest['items']}
    order = report['execution_order']
    rows = report['items']
    if type(order) is not list or any(type(key) is not str for key in order) or (
        len(order) != len(specification) or len(set(order)) != len(order) or
        set(order) != set(specification) or type(rows) is not list or
        len(rows) != len(order)
    ):
        raise ValueError('EAI pipeline receipt mismatch: execution order')
    # The verifier separately reconstructs the canonical topological layers.
    remaining, confirmed, canonical = set(specification), set(), []
    while remaining:
        ready = sorted(key for key in remaining
                       if set(specification[key]['requires']) <= confirmed)
        if not ready:
            raise ValueError('EAI pipeline receipt mismatch: cyclic dependencies')
        canonical.extend(ready)
        confirmed.update(ready)
        remaining.difference_update(ready)
    if order != canonical:
        raise ValueError('EAI pipeline receipt mismatch: noncanonical execution order')
    processed = {}
    aborted = False
    for key,row in zip(order,rows):
        expected = specification[key]
        deps = tuple(sorted(expected['requires']))
        if not set(deps) <= set(processed):
            raise ValueError('EAI pipeline receipt mismatch: dependency ordering')
        if type(row) is not dict or set(row) != {
            'id','goal','sha256','requires','status','kind','verification',
            'result','error','blocked_by'
        } or (row['id'],row['goal'],row['sha256'],row['requires']) != (
            key,expected['goal'],expected['sha256'],list(deps)
        ):
            raise ValueError('EAI pipeline receipt mismatch: entry provenance')
        blocking = sorted(dep for dep in deps if processed[dep]['status'] not in GOOD)
        if aborted or blocking:
            reason = 'STOP_ON_ERROR' if aborted else 'DEPENDENCY_NOT_READY'
            anticipated_block = [] if aborted else blocking
            if row['status']!='SKIPPED' or row['error']!=reason or (
                row['blocked_by']!=anticipated_block or row['kind'] is not None or
                row['verification']!='NOT_RUN' or row['result'] is not None
            ):
                raise ValueError('EAI pipeline receipt mismatch: unauthorized gated execution')
        elif row['status']=='ERROR':
            if row['kind'] is not None or row['result'] is not None or (
                row['verification']!='NOT_RUN' or type(row['error']) is not str or
                not 1 <= len(row['error']) <= 200 or row['blocked_by'] != []
            ):
                raise ValueError('EAI pipeline receipt mismatch: error envelope')
            if not manifest['continue_on_error']:
                aborted = True
        else:
            child=row['result']
            if row['status'] not in GOOD | REVIEW or type(child) is not dict or (
                row['error'] is not None or row['blocked_by']!=[] or
                row['kind'] not in ROUTED_KINDS or row['verification']!='PASS' or
                child.get('kind') != row['kind'] or child.get('status')!=row['status']
            ):
                raise ValueError('EAI pipeline receipt mismatch: result envelope')
            provenance = child.get('input')
            validation = child.get('verification')
            if type(provenance) is not dict or type(validation) is not dict or (
                provenance.get('sha256')!=row['sha256'] or validation.get('status')!='PASS'
            ):
                raise ValueError('EAI pipeline receipt mismatch: child guard')
        processed[key] = row
    summary = _aggregate(rows)
    if report['summary'] != summary or report['status'] != summary['status']:
        raise ValueError('EAI pipeline receipt mismatch: aggregate status')
    return {'version':'eai.pipeline_receipt.v1','status':'PASS',
            'checks':['manifest','dag_order','dependency_gates','child_guards','summary'],
            'policy':'READ_ONLY;NO_REMOTE;NO_RETRY;DEPENDENCY_HOLD'}


def execute_pipeline_document(manifest_file: str | Path) -> dict:
    source = Path(manifest_file).expanduser().resolve(strict=True)
    manifest,original_sha = _read_spec(source)
    paths,deps,order = _prepare(source,manifest)
    for item,target in paths.values():
        if _hash_file(target)!=item['sha256']:
            raise ValueError('pipeline preflight SHA256 mismatch: no goals executed')
    outputs = []
    processed = {}
    stopped = False
    for key in order:
        item,target = paths[key]
        blocked_by = sorted(dep for dep in deps[key] if processed[dep]['status'] not in GOOD)
        row = {'id':key,'goal':item['goal'],'sha256':item['sha256'],
               'requires':list(deps[key]),'status':None,'kind':None,
               'verification':'NOT_RUN','result':None,'error':None,'blocked_by':[]}
        if stopped:
            row.update(status='SKIPPED',error='STOP_ON_ERROR')
        elif blocked_by:
            row.update(status='SKIPPED',error='DEPENDENCY_NOT_READY',
                       blocked_by=blocked_by)
        else:
            try:
                if _hash_file(target)!=item['sha256']:
                    raise ValueError('pipeline goal changed after preflight')
                child=execute_goal_document(target)
                if child['input']['sha256']!=item['sha256'] or (
                    child['verification']['status']!='PASS' or
                    _hash_file(target)!=item['sha256']
                ):
                    raise ValueError('pipeline child evidence mismatch')
                row.update(status=child['status'],kind=child['kind'],
                           verification='PASS',result=child)
            except (ValueError,OSError,UnicodeError,csv.Error,TimeoutError) as exc:
                row.update(status='ERROR',
                           error=(type(exc).__name__+': '+str(exc))[:200])
                if not manifest['continue_on_error']:
                    stopped=True
        processed[key]=row
        outputs.append(row)
    _,end_sha=_read_spec(source)
    if end_sha!=original_sha:
        raise ValueError('pipeline manifest changed during execution')
    for item,target in paths.values():
        if _hash_file(target)!=item['sha256']:
            raise ValueError('pipeline child changed during execution')
    summary=_aggregate(outputs)
    report={'version':VERSION,'status':summary['status'],
            'manifest':{'filename':source.name,'sha256':original_sha},
            'continue_on_error':manifest['continue_on_error'],
            'execution_order':list(order),'items':outputs,'summary':summary,
            'scope':SCOPE,'verification':None}
    report['verification']=verify_pipeline_receipt(manifest,report,
                                                   original_sha256=original_sha)
    return report


def render_pipeline(report: dict) -> str:
    summary=report['summary']
    lines=[f"EAI 목표 의존성 파이프라인: {report['status']}",
           f"완료 {summary['completed']} / 검토 {summary['review']} / "
           f"오류 {summary['errors']} / 보류 {summary['skipped']}"]
    for row in report['items']:
        lines.append(f"{row['id']}: {row['status']}"+
                     (f" (선행 단계: {', '.join(row['blocked_by'])})" if row['blocked_by'] else ''))
    lines.append(report['scope'])
    return '\n'.join(lines)
