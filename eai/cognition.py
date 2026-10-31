"""Independent EAI CPU solving and evidence handling. No generative LLM synthesis."""
import ast
from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Any

from .intent import IntentSpec
from .storage import Store
from .tools import SearchHit, ToolRegistry
from .workflows import WorkflowRegistry


@dataclass
class ResultSpec:
    status: str
    task: str
    data: dict[str, Any] = field(default_factory=dict)
    sources: list[SearchHit] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    cache_hit: bool = False


def exact_calculate(expression: str) -> str:
    """Fraction-based exact arithmetic, decimal result rendered on CPU."""
    if not isinstance(expression, str) or not 1 <= len(expression) <= 160:
        raise ValueError('invalid expression length')
    if any(c not in '0123456789.+-*/() \t' for c in expression):
        raise ValueError('only + - * / parentheses and decimal constants allowed')
    try:
        tree = ast.parse(expression, mode='eval')
    except (SyntaxError, RecursionError) as exc:
        raise ValueError('invalid arithmetic expression') from exc
    if len(list(ast.walk(tree))) > 60:
        raise ValueError('expression too complex')

    def evaluate(node, depth=0) -> Fraction:
        if depth > 24:
            raise ValueError('expression nesting too deep')
        if isinstance(node, ast.Expression):
            return evaluate(node.body, depth+1)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            lexeme = ast.get_source_segment(expression, node)
            if lexeme is None or len(lexeme) > 32 or 'e' in lexeme.lower():
                raise ValueError('numeric literal too long')
            return Fraction(Decimal(lexeme))
        if isinstance(node, ast.UnaryOp) and type(node.op) in (ast.UAdd, ast.USub):
            v = evaluate(node.operand, depth+1)
            return v if isinstance(node.op, ast.UAdd) else -v
        if isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub, ast.Mult, ast.Div):
            a, b = evaluate(node.left, depth+1), evaluate(node.right, depth+1)
            if isinstance(node.op, ast.Add): out = a+b
            elif isinstance(node.op, ast.Sub): out = a-b
            elif isinstance(node.op, ast.Mult): out = a*b
            else:
                if not b: raise ValueError('division by zero')
                out = a/b
            if max(out.numerator.bit_length(), out.denominator.bit_length()) > 512:
                raise ValueError('result exceeds resource bounds')
            return out
        raise ValueError('unsupported arithmetic syntax')

    answer = evaluate(tree)
    if not answer.denominator:
        raise ValueError('division by zero')
    with localcontext() as ctx:
        ctx.prec = 34
        n = Decimal(answer.numerator) / Decimal(answer.denominator)
        rendered = format(n, 'f').rstrip('0').rstrip('.') if '.' in format(n, 'f') else str(n)
    return rendered if rendered and rendered != '-0' else '0'


class CognitiveEngine:
    def __init__(self, store: Store, search_tool=None):
        self.store = store
        self.tools = ToolRegistry()
        self.workflows = WorkflowRegistry()
        if search_tool is not None:
            self.tools.register('web.search.v1', search_tool)

    def solve(self, intent: IntentSpec, *, online_consent: bool = False, note_consent: bool = False) -> ResultSpec:
        if intent.version != 1:
            raise ValueError('unsupported intent contract version')
        if intent.task == 'calculate':
            try:
                value = exact_calculate(intent.expression)
                return ResultSpec('OK', 'calculate', {'expression': intent.expression, 'value': value},
                                  trace=['CPU: fraction arithmetic', 'CPU: decimal render'])
            except (ValueError, OverflowError, ArithmeticError) as exc:
                return ResultSpec('ERROR', 'calculate', warnings=[str(exc)], trace=['CPU: validation rejected'])
        if intent.task == 'help':
            return ResultSpec('OK', 'help', trace=['CPU: fixed capability listing'])
        if intent.task == 'remember':
            if not note_consent:
                return ResultSpec('DENIED', 'remember',
                                  warnings=['메모 저장은 명시적 기억해/메모추가 명령이 필요합니다.'],
                                  trace=['CPU: note write permission denied'])
            try:
                note_id, new = self.store.add_note(intent.query)
                return ResultSpec('OK', 'remember', {'note_id': note_id, 'created': new},
                                  trace=['CPU: authorized SQLite note write'])
            except ValueError as exc:
                return ResultSpec('ERROR', 'remember', warnings=[str(exc)])
        if intent.task == 'notes':
            notes = self.store.list_notes()
            return ResultSpec('OK' if notes else 'UNAVAILABLE', 'notes', {'notes': notes},
                              trace=['CPU: SQLite note list'])
        if intent.task == 'recall':
            notes = self.store.search_notes(intent.query)
            hits = self.store.recall(intent.query)
            return ResultSpec('OK' if hits or notes else 'UNAVAILABLE', 'recall',
                              {'notes': notes}, sources=hits,
                              trace=['CPU: local SQLite note/source lookup'])
        if intent.task == 'search':
            if not online_consent:
                return ResultSpec('UNAVAILABLE', 'search',
                                  warnings=['온라인 검색은 --online 승인이 필요합니다.'],
                                  trace=['CPU: permission gate denied external lookup'])
            if 'web.search.v1' not in self.tools.names():
                return ResultSpec('UNAVAILABLE', 'search',
                                  warnings=['로컬 SearXNG 서버가 설정되지 않았습니다.'])
            cached = self.store.read_search_cache(intent.query)
            if cached is not None:
                return ResultSpec('OK' if cached else 'UNAVAILABLE', 'search',
                                  sources=cached, cache_hit=True,
                                  warnings=['캐시된 결과이며 현재 시점의 최신성은 재확인하지 않았습니다.'],
                                  trace=['CPU: SQLite cache hit'])
            try:
                hits = self.workflows.execute('research.web.v1', self.tools, intent.query,
                                              allow_online=True)
                self.store.save_search(intent.query, hits)
                return ResultSpec('OK' if hits else 'UNAVAILABLE', 'search', sources=hits,
                                  warnings=['검색 결과는 아직 독립적으로 검증되지 않았습니다.'] if hits else
                                           ['검색 결과를 확보하지 못했습니다.'],
                                  trace=['CPU: approved HTTP search', 'CPU: SQLite cache/store'])
            except Exception as exc:
                return ResultSpec('UNAVAILABLE', 'search',
                                  warnings=[f'온라인 조회 실패: {type(exc).__name__}'],
                                  trace=['CPU: provider failed safely'])
        return ResultSpec('UNSUPPORTED', 'unsupported',
                          warnings=['현재 독립 EAI 엔진은 계산·검색·기억 조회·로컬 메모 저장만 지원합니다.'],
                          trace=['CPU: unsupported task, no model-written answer'])


class ResponseEngine:
    """Fixed EAI response templates, never a Qwen generation call."""
    @staticmethod
    def render(result: ResultSpec) -> str:
        if result.task == 'calculate' and result.status == 'OK':
            return f"계산 결과: {result.data['expression']} = {result.data['value']}"
        if result.task == 'help':
            return ('EAI CPU 독립 엔진: 계산 12*(3+4) / 기억해 프로젝트 목표 / 메모목록 / '
                    '기억검색 목표 / 검색 최신 AI 모델 / 도움말. 온라인 검색은 --online '
                    '및 별도 실행 중인 로컬 SearXNG가 필요합니다.')
        if result.task == 'remember' and result.status == 'OK':
            nid = result.data['note_id']
            return (f'로컬 메모 저장됨: #{nid}' if result.data['created']
                    else f'동일한 로컬 메모가 이미 있습니다: #{nid}')
        if result.task in {'notes', 'recall'} and result.data.get('notes'):
            lines = ['사용자 로컬 메모 (사용자 입력, 사실 검증 아님):']
            for item in result.data['notes']:
                lines.append(f"#{item['id']}: {item['content'][:600]}")
            if result.sources:
                lines.append('이전 웹 검색 자료 (원문 미검증):')
                for i, hit in enumerate(result.sources, 1):
                    lines.append(f'{i}. {hit.title}\n   {hit.url}\n   {hit.snippet[:320]}')
            return '\n'.join(lines)
        if result.task == 'notes' and not result.data.get('notes'):
            return '저장된 로컬 메모가 없습니다.'
        if result.task in {'search', 'recall'} and result.sources:
            lines = ['검색 결과 (원문 미검증):' if result.task == 'search' else '저장된 자료 (원문 미검증):']
            for i, hit in enumerate(result.sources, 1):
                lines.append(f'{i}. {hit.title}\n   {hit.url}\n   {hit.snippet[:320]}')
            return '\n'.join(lines)
        if result.warnings:
            return '\n'.join(result.warnings)
        return '처리 가능한 결과가 없습니다.'
