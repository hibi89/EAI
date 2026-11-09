"""P9: fail-closed verification of displayed choice evidence and solver trace.

P8 independently verifies winners, raw weighted scores, and Pareto membership.
This check additionally binds visible criterion details and trace to the
original validated goal, without network access or mutation.
"""
from decimal import Decimal, localcontext

from .analysis import _render_decimal
from .decision_engine import DECISION_VERSION


def _check(condition: bool, field: str) -> None:
    if not condition:
        raise ValueError('EAI 영수증 검증 실패: ' + field)


def _dominated_by(option, feasible, criteria) -> list[str]:
    dominated = []
    for other in feasible:
        if other.id == option.id:
            continue
        no_worse, strictly_better = True, False
        for criterion in criteria:
            theirs, ours = other.values[criterion.id], option.values[criterion.id]
            if criterion.direction == 'min':
                no_worse &= theirs <= ours
                strictly_better |= theirs < ours
            else:
                no_worse &= theirs >= ours
                strictly_better |= theirs > ours
        if no_worse and strictly_better:
            dominated.append(other.id)
    return sorted(dominated)


def verify_choice_display_evidence(goal, report: dict) -> None:
    """Validate every user-visible detail after P8's primary proof has passed.

    `goal` is the already validated ChoiceGoal; `report` is the bounded P7
    solver receipt. A disagreement raises ValueError and blocks PASS.
    """
    _check(report.get('plan_version') == DECISION_VERSION, '선택지 계획 버전 불일치')
    expected_criteria = [
        {'id': c.id, 'direction': c.direction, 'unit': c.unit,
         'weight': _render_decimal(c.weight),
         'score_min': _render_decimal(c.score_min),
         'score_max': _render_decimal(c.score_max),
         'hard_min': None if c.hard_min is None else _render_decimal(c.hard_min),
         'hard_max': None if c.hard_max is None else _render_decimal(c.hard_max)}
        for c in goal.criteria
    ]
    _check(report.get('criteria') == expected_criteria, '평가 기준 표시값 불일치')
    entries = {entry['id']: entry for entry in report['options']}
    feasible = [opt for opt in goal.options if entries[opt.id]['status'] == 'FEASIBLE']
    for opt in goal.options:
        actual = entries[opt.id]
        if actual['status'] == 'FEASIBLE':
            with localcontext() as ctx:
                ctx.prec = 90
                expected_details = []
                for c in goal.criteria:
                    value = opt.values[c.id]
                    fraction = ((value - c.score_min) / (c.score_max - c.score_min)
                                if c.direction == 'max' else
                                (c.score_max - value) / (c.score_max - c.score_min))
                    clamped = max(Decimal(0), min(Decimal(1), fraction))
                    expected_details.append({
                        'id': c.id, 'unit': c.unit,
                        'actual': _render_decimal(value),
                        'normalized': _render_decimal((clamped * 100).quantize(Decimal('0.01'))),
                        'weight': _render_decimal(c.weight),
                        'outside_score_bounds': value < c.score_min or value > c.score_max,
                    })
            expected_dominated_by = _dominated_by(opt, feasible, goal.criteria)
        else:
            expected_details = []
            expected_dominated_by = []
        _check(actual.get('per_criterion') == expected_details,
               f'{opt.id} 기준별 표시 증거 불일치')
        _check(actual.get('dominated_by') == expected_dominated_by,
               f'{opt.id} Pareto 지배 근거 불일치')
        breaches = actual.get('constraint_breaches')
        expected_breaches = []
        for c in goal.criteria:
            value = opt.values[c.id]
            if value is None:
                continue
            if c.hard_min is not None and value < c.hard_min:
                expected_breaches.append({
                    'criterion': c.id, 'rule': 'hard_min',
                    'required': _render_decimal(c.hard_min),
                    'actual': _render_decimal(value),
                })
            if c.hard_max is not None and value > c.hard_max:
                expected_breaches.append({
                    'criterion': c.id, 'rule': 'hard_max',
                    'required': _render_decimal(c.hard_max),
                    'actual': _render_decimal(value),
                })
        _check(breaches == expected_breaches, f'{opt.id} 제약 표시 수치 불일치')

    expected_steps = [
        {'step': 'validate_options', 'skill': 'decision.constraints.v1', 'status': 'DONE'},
        {'step': 'weighted_scoring', 'skill': 'decision.fixed_scale.v1', 'status': 'DONE'},
        {'step': 'pareto_verification', 'skill': 'decision.pareto.v1', 'status': 'PASS'},
    ]
    if not feasible:
        expected_steps.append({'step': 'explain_infeasibility',
                               'skill': 'decision.explain_limits.v1', 'status': 'DONE'})
    expected_steps.append({'step': 'verify_decision_receipt',
                           'skill': 'decision.receipt.v1', 'status': 'PASS'})
    _check(report.get('steps') == expected_steps, '실행 단계 기록 불일치')
