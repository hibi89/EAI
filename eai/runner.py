"""End-to-end independent EAI: parse -> CPU solve -> own renderer -> persist."""
from dataclasses import dataclass
from .cognition import CognitiveEngine, ResponseEngine, ResultSpec
from .intent import RuleIntentParser
from .storage import Store


@dataclass
class Answer:
    text: str
    result: ResultSpec
    parser_fallback: bool = False


class EAIRunner:
    def __init__(self, store: Store, parser=None, search_tool=None):
        self.store = store
        self.parser = parser or RuleIntentParser()
        self.rules = RuleIntentParser()
        self.cognition = CognitiveEngine(store, search_tool)
        self.renderer = ResponseEngine()

    def ask(self, question: str, *, allow_online: bool = False) -> Answer:
        fallback = False
        try:
            intent = self.parser.parse(question)
        except (ValueError, OSError, TimeoutError, ConnectionError, KeyError, TypeError) as exc:
            intent = self.rules.parse(question)
            fallback = True
        result = self.cognition.solve(intent, online_consent=allow_online)
        if fallback:
            result.warnings.append('Qwen 입력 분류 실패: 규칙 기반 CPU 분류기로 전환했습니다.')
        rendered = self.renderer.render(result)
        self.store.add_turn('user', question)
        self.store.add_turn('assistant', rendered)
        return Answer(text=rendered, result=result, parser_fallback=fallback)
