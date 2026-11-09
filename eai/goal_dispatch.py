"""Strict two-domain read-only goal router, using pre-registered local CPU solvers."""
import hashlib
import json
from pathlib import Path

from .decision_engine import validate_choice_goal, execute_choice_goal
from .plan_engine import AuditGoal, CPUPlanExecutor
from .receipt_guard import verify_goal_receipt
from .task_portfolio import validate_task_goal, execute_task_goal, render_task_plan
from .task_schedule import validate_schedule_goal, execute_schedule_goal, render_schedule
from .csv_quality import validate_quality_goal, execute_quality_goal, render_quality

MAX_GOAL_BYTES = 64 * 1024
ROUTER_VERSION = 'eai.goal.dispatch.v1'
ROUTED_KINDS = frozenset({'choose_options', 'csv_audit', 'plan_tasks', 'schedule_tasks', 'csv_quality'})


def _read_spec(path: Path) -> tuple[dict, str]:
    if not path.is_file() or path.stat().st_size > MAX_GOAL_BYTES:
        raise ValueError('JSON goal must be a regular file of at most 64 KiB')
    with path.open('rb') as f:
        binary = f.read(MAX_GOAL_BYTES + 1)
    if len(binary) > MAX_GOAL_BYTES:
        raise ValueError('JSON goal exceeds 64 KiB')

    def pairs_to_dict(items):
        result = {}
        for key, val in items:
            if key in result:
                raise ValueError('duplicate keys in goal JSON')
            result[key] = val
        return result

    try:
        parsed = json.loads(binary.decode('utf-8-sig'), object_pairs_hook=pairs_to_dict)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('invalid UTF-8 JSON goal document') from exc
    if type(parsed) is not dict:
        raise ValueError('goal must be a JSON object')
    return parsed, hashlib.sha256(binary).hexdigest()


def _path_relative_to_spec(spec: Path, supplied: object) -> Path:
    if type(supplied) is not str or not 1 <= len(supplied) <= 512 or '\x00' in supplied:
        raise ValueError('CSV paths must be explicitly provided as short strings')
    path = Path(supplied).expanduser()
    return (spec.parent / path).resolve(strict=True) if not path.is_absolute() else path.resolve(strict=True)


def _compile_csv_goal(spec: Path, data: dict) -> AuditGoal:
    required = {'version', 'kind', 'left', 'right', 'key', 'values'}
    optional = {'tolerance', 'encoding', 'max_seconds'}
    if type(data) is not dict or not required <= set(data) or set(data) - (required | optional):
        raise ValueError('unsupported CSV audit goal attributes')
    if type(data['version']) is not int or data['version'] != 1 or data['kind'] != 'csv_audit':
        raise ValueError('unsupported CSV audit goal version')
    return AuditGoal(
        left=_path_relative_to_spec(spec, data['left']),
        right=_path_relative_to_spec(spec, data['right']),
        key=data['key'], values=data['values'],
        tolerance=data.get('tolerance', '0'),
        encoding=data.get('encoding', 'utf-8-sig'),
        max_seconds=data.get('max_seconds', 60)
    )


def execute_goal_document(path: str | Path) -> dict:
    """Dispatch fixed goal types only, preserve source hash and verify final receipt."""
    source_path = Path(path).expanduser().resolve(strict=True)
    data, before = _read_spec(source_path)
    kind = data.get('kind')
    if type(kind) is not str or kind not in ROUTED_KINDS:
        raise ValueError('unknown goal kind: allowed choose_options, csv_audit, plan_tasks, schedule_tasks or csv_quality')
    if kind == 'choose_options':
        goal = validate_choice_goal(data)
        result = execute_choice_goal(goal)
        skill_id = 'decision.select.v1'
    elif kind == 'csv_audit':
        goal = _compile_csv_goal(source_path, data)
        result = CPUPlanExecutor().execute(goal)
        skill_id = 'csv.audit_plan.v1'
    elif kind == 'plan_tasks':
        goal = validate_task_goal(data)
        result = execute_task_goal(goal)
        skill_id = 'task.portfolio.v1'
    elif kind == 'schedule_tasks':
        goal = validate_schedule_goal(data)
        result = execute_schedule_goal(goal)
        skill_id = 'task.critical_path.v1'
    else:
        goal = validate_quality_goal(data, source_path)
        result = execute_quality_goal(goal)
        skill_id = 'csv.quality_gate.v1'
    if not isinstance(result, dict) or type(result.get('status')) is not str:
        raise ValueError('solver did not produce a valid decision receipt')
    # Detect a spec changed on disk during the original decision; no file writes.
    _, after = _read_spec(source_path)
    if before != after:
        raise ValueError('goal document changed during execution')
    verified_receipt = verify_goal_receipt(kind, goal, result)
    return {
        'dispatcher_version': ROUTER_VERSION, 'kind': kind, 'status': result['status'],
        'input': {'filename': source_path.name, 'sha256': before},
        'route': skill_id, 'verification': verified_receipt,
        'steps': [
            {'step': 'classify_goal', 'skill': 'goal.schema_router.v1', 'status': 'PASS'},
            {'step': 'run_domain_solver', 'skill': skill_id, 'status': result['status']},
            {'step': 'verify_goal_document', 'skill': 'goal.sha256.v1', 'status': 'PASS'},
        ],
        'result': result,
        'scope': ('정해진 다섯 도메인 목표만 CPU에서 처리합니다. 사용자 제공 숫자와 원본 데이터의 '
                  '실세계 진실성이나 작성자의 신뢰성은 검증하지 않습니다.'),
    }


def render_goal_document(report: dict) -> str:
    result = report['result']
    lines = [f"EAI P7 목표 실행: {report['status']} / {report['kind']}",
             f"실행 스킬: {report['route']}",
             f"목표 파일: {report['input']['filename']} / SHA256 {report['input']['sha256']}",
             f"결과 독립 검사: {report['verification']['status']} / {report['verification']['version']}"]
    if report['kind'] == 'choose_options':
        from .decision_engine import render_decision
        lines.append(render_decision(result))
    elif report['kind'] == 'csv_audit':
        from .plan_engine import render_plan_report
        lines.append(render_plan_report(result))
    elif report['kind'] == 'plan_tasks':
        lines.append(render_task_plan(result))
    elif report['kind'] == 'schedule_tasks':
        lines.append(render_schedule(result))
    else:
        lines.append(render_quality(result))
    diag = report['verification']['diagnostics']
    if diag['type'] != 'NONE':
        lines.append('추가 확인 필요: ' + diag['type'])
        if diag.get('hint'):
            lines.append(diag['hint'])
    return '\n'.join(lines)
