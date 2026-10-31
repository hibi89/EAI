"""P7 deterministic CPU option selection: bounded, explainable, and never a market claim.

All numbers, weights, score bounds, hard requirements and alternatives originate in
an explicit JSON specification. EAI does not fetch specs or decide their truth.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
import re
from typing import Any

from .analysis import _NUMBER, _render_decimal

DECISION_VERSION = 'eai.goal.choose_options.v1'
MAX_CRITERIA = 8
MAX_OPTIONS = 24
ID_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{0,31}$')


def _num(raw: object, field: str) -> Decimal:
    if type(raw) is not str or not _NUMBER.fullmatch(raw):
        raise ValueError(f'{field}: fixed-point decimal STRING required')
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f'{field}: invalid decimal') from exc
    if not value.is_finite():
        raise ValueError(f'{field}: non-finite values are not allowed')
    return value


def _strict_fields(raw: object, required: set[str], optional: set[str], label: str) -> dict:
    if type(raw) is not dict or not required <= set(raw) or set(raw) - (required | optional):
        raise ValueError(f'{label}: invalid or missing fields')
    return raw


def _valid_id(raw: object, label: str) -> str:
    if type(raw) is not str or not ID_RE.fullmatch(raw):
        raise ValueError(f'{label}: ID must contain 1-32 ASCII letters, digits, _ or - and start with a letter')
    return raw


@dataclass(frozen=True)
class Criterion:
    id: str
    direction: str
    unit: str
    weight: Decimal
    score_min: Decimal
    score_max: Decimal
    hard_min: Decimal | None
    hard_max: Decimal | None


@dataclass(frozen=True)
class Option:
    id: str
    values: dict[str, Decimal | None]


@dataclass(frozen=True)
class ChoiceGoal:
    goal: str
    criteria: tuple[Criterion, ...]
    options: tuple[Option, ...]


def validate_choice_goal(raw: object) -> ChoiceGoal:
    goal = _strict_fields(raw, {'version', 'kind', 'goal', 'criteria', 'options'}, set(), 'goal')
    if type(goal['version']) is not int or goal['version'] != 1 or goal['kind'] != 'choose_options':
        raise ValueError('unsupported goal version or kind')
    title = goal['goal']
    if type(title) is not str or not 1 <= len(title.strip()) <= 120 or any(ord(c) < 32 for c in title):
        raise ValueError('goal name must be 1-120 characters without control characters')
    criteria = goal['criteria']
    options = goal['options']
    if type(criteria) is not list or not 1 <= len(criteria) <= MAX_CRITERIA:
        raise ValueError('1-8 criteria required')
    if type(options) is not list or not 2 <= len(options) <= MAX_OPTIONS:
        raise ValueError('2-24 options required')

    parsed_criteria = []
    criteria_names = set()
    for item in criteria:
        c = _strict_fields(item, {'id', 'direction', 'unit', 'weight', 'score_min', 'score_max'},
                           {'hard_min', 'hard_max'}, 'criterion')
        identifier = _valid_id(c['id'], 'criterion')
        if identifier in criteria_names:
            raise ValueError('duplicate criterion ID')
        criteria_names.add(identifier)
        if type(c['direction']) is not str or c['direction'] not in ('min', 'max'):
            raise ValueError('direction must be min or max')
        if type(c['unit']) is not str or not 1 <= len(c['unit']) <= 16 or (
                any(ord(ch) < 32 or ord(ch) > 126 for ch in c['unit'])):
            raise ValueError('unit must be explicit printable ASCII, 1-16 chars')
        weight = _num(c['weight'], 'weight')
        low = _num(c['score_min'], 'score_min')
        high = _num(c['score_max'], 'score_max')
        if weight <= 0 or low >= high:
            raise ValueError('positive weight and score_min < score_max required')
        hmin = _num(c['hard_min'], 'hard_min') if 'hard_min' in c else None
        hmax = _num(c['hard_max'], 'hard_max') if 'hard_max' in c else None
        if hmin is not None and hmax is not None and hmin > hmax:
            raise ValueError('hard_min cannot exceed hard_max')
        parsed_criteria.append(Criterion(identifier, c['direction'], c['unit'], weight,
                                         low, high, hmin, hmax))

    parsed_options = []
    option_names = set()
    for item in options:
        o = _strict_fields(item, {'id', 'values'}, set(), 'option')
        identifier = _valid_id(o['id'], 'option')
        if identifier in option_names:
            raise ValueError('duplicate option ID')
        option_names.add(identifier)
        if type(o['values']) is not dict or set(o['values']) - criteria_names:
            raise ValueError('option contains unsupported value keys')
        parsed_values = {}
        for key in criteria_names:
            raw_value = o['values'].get(key)
            parsed_values[key] = None if raw_value is None else _num(raw_value, f'{identifier}.{key}')
        parsed_options.append(Option(identifier, parsed_values))
    return ChoiceGoal(title.strip(), tuple(parsed_criteria), tuple(parsed_options))


def _pair_dominates(left: Option, right: Option, criteria: tuple[Criterion, ...]) -> bool:
    """Raw numerical Pareto dominance, independent of weights and score ranges."""
    non_worse = True
    strict = False
    for c in criteria:
        a, b = left.values[c.id], right.values[c.id]
        if a is None or b is None:
            raise ValueError('Pareto comparison requires complete evidence')
        if c.direction == 'max':
            if a < b:
                non_worse = False
            if a > b:
                strict = True
        else:
            if a > b:
                non_worse = False
            if a < b:
                strict = True
    return non_worse and strict


def execute_choice_goal(goal: ChoiceGoal) -> dict[str, Any]:
    """Validate constraints -> score valid options -> verify dominance -> receipt."""
    if type(goal) is not ChoiceGoal:
        raise ValueError('unvalidated choice goal')
    steps = [
        {'step': 'validate_options', 'skill': 'decision.constraints.v1', 'status': 'DONE'},
    ]
    entries = []
    feasible: list[Option] = []
    with localcontext() as context:
        context.prec = 90
        total_weight = sum((c.weight for c in goal.criteria), Decimal(0))
        if total_weight <= 0:
            raise ValueError('invalid total weight')
        for option in goal.options:
            missing = [c.id for c in goal.criteria if option.values[c.id] is None]
            breaches = []
            for c in goal.criteria:
                val = option.values[c.id]
                if val is None:
                    continue
                if c.hard_min is not None and val < c.hard_min:
                    breaches.append({'criterion': c.id, 'rule': 'hard_min',
                                     'required': _render_decimal(c.hard_min), 'actual': _render_decimal(val)})
                if c.hard_max is not None and val > c.hard_max:
                    breaches.append({'criterion': c.id, 'rule': 'hard_max',
                                     'required': _render_decimal(c.hard_max), 'actual': _render_decimal(val)})
            # Explicitly exclude infeasible or incomplete options; no invented values.
            status = 'UNAVAILABLE' if missing else 'EXCLUDED' if breaches else 'FEASIBLE'
            item: dict[str, Any] = {'id': option.id, 'status': status, 'missing': sorted(missing),
                                   'constraint_breaches': breaches, 'score': None,
                                   'per_criterion': [], 'dominated_by': []}
            if status == 'FEASIBLE':
                feasible.append(option)
                weighted_score = Decimal(0)
                for c in goal.criteria:
                    v = option.values[c.id]
                    assert v is not None
                    frac = ((v - c.score_min) / (c.score_max - c.score_min) if c.direction == 'max'
                            else (c.score_max - v) / (c.score_max - c.score_min))
                    clamped = max(Decimal(0), min(Decimal(1), frac))
                    weighted_score += c.weight * clamped
                    item['per_criterion'].append({
                        'id': c.id, 'unit': c.unit, 'actual': _render_decimal(v),
                        'normalized': _render_decimal((clamped * 100).quantize(Decimal('0.01'))),
                        'weight': _render_decimal(c.weight),
                        'outside_score_bounds': v < c.score_min or v > c.score_max,
                    })
                item['_raw_score'] = weighted_score / total_weight * 100
                item['score'] = _render_decimal(item['_raw_score'].quantize(Decimal('0.01')))
            entries.append(item)
        steps.append({'step': 'weighted_scoring', 'skill': 'decision.fixed_scale.v1', 'status': 'DONE'})

        by_id = {o.id: o for o in feasible}
        entries_by_id = {o['id']: o for o in entries}
        for option in feasible:
            entries_by_id[option.id]['dominated_by'] = sorted(
                other.id for other in feasible if other.id != option.id
                and _pair_dominates(other, option, goal.criteria)
            )
        frontier = sorted(o.id for o in feasible if not entries_by_id[o.id]['dominated_by'])
        steps.append({'step': 'pareto_verification', 'skill': 'decision.pareto.v1', 'status': 'PASS'})

        # No arbitrary tie-break winner; scores compare *unrounded* values.
        ranked = sorted(feasible, key=lambda opt: (-entries_by_id[opt.id]['_raw_score'], opt.id))
        winners = []
        if ranked:
            high_score = entries_by_id[ranked[0].id]['_raw_score']
            winners = [o.id for o in ranked if entries_by_id[o.id]['_raw_score'] == high_score]
        overall = 'UNAVAILABLE' if not feasible else 'TIE' if len(winners) > 1 else 'DECIDED'
        if not feasible:
            steps.append({'step': 'explain_infeasibility',
                          'skill': 'decision.explain_limits.v1', 'status': 'DONE'})

        for item in entries:
            item.pop('_raw_score', None)
        result = {
            'plan_version': DECISION_VERSION, 'goal': goal.goal, 'kind': 'choose_options',
            'status': overall, 'winners': winners, 'ranking': [o.id for o in ranked],
            'pareto_frontier': frontier, 'options': entries,
            'criteria': [{'id': c.id, 'direction': c.direction, 'unit': c.unit,
                          'weight': _render_decimal(c.weight),
                          'score_min': _render_decimal(c.score_min),
                          'score_max': _render_decimal(c.score_max),
                          'hard_min': None if c.hard_min is None else _render_decimal(c.hard_min),
                          'hard_max': None if c.hard_max is None else _render_decimal(c.hard_max)}
                         for c in goal.criteria],
            'steps': [*steps, {'step': 'verify_decision_receipt',
                              'skill': 'decision.receipt.v1', 'status': 'PASS'}],
            'scope': ('사용자가 입력한 수치·가중치·절대 평가 범위만으로 결정했습니다. '
                      '시장 최신성·제품 스펙의 진위·선호의 타당성은 검증하지 않았습니다. '
                      '점수 범위 밖 수치는 0~100으로 절단합니다. '
                      'Pareto 집합은 가중치가 아닌 원시 지표로 계산합니다.'),
        }
        return result


def render_decision(report: dict) -> str:
    lines = [f"EAI 독립 선택지 평가: {report['status']}", f"목표: {report['goal']}"]
    if report['winners']:
        lines.append('최고 점수 선택지(동점 모두): ' + ', '.join(report['winners']))
    else:
        lines.append('결정 보류: 필수 입력이 부족하거나 모든 후보가 제약조건을 위반합니다.')
    if report['pareto_frontier']:
        lines.append('Pareto 비지배 후보: ' + ', '.join(report['pareto_frontier']))
    for row in report['options']:
        lines.append(f"{row['id']}: {row['status']} / 점수 {row['score'] if row['score'] is not None else 'N/A'}")
        for reason in row['constraint_breaches']:
            lines.append(f"  제약 위반: {reason['criterion']} {reason['rule']}={reason['required']}, 실제 {reason['actual']}")
        if row['missing']:
            lines.append('  증거 부족: ' + ', '.join(row['missing']))
    lines.append(report['scope'])
    return '\n'.join(lines)
