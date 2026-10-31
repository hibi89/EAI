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
        # A model's classification is NEVER sufficient authority to save user data.
        # Explicit note commands are parsed directly from the original text on CPU.
        literal = self.rules.parse(question)
        if literal.task == 'remember':
            intent = literal
        else:
            try:
                intent = self.parser.parse(question)
            except (ValueError, OSError, TimeoutError, ConnectionError, KeyError, TypeError):
                intent = literal
                fallback = True
        result = self.cognition.solve(intent, online_consent=allow_online,
                                      note_consent=(literal.task == 'remember'))
        if fallback:
            result.warnings.append('Qwen 입력 분류 실패: 규칙 기반 CPU 분류기로 전환했습니다.')
        rendered = self.renderer.render(result)
        self.store.add_turn('user', question)
        self.store.add_turn('assistant', rendered)
        return Answer(text=rendered, result=result, parser_fallback=fallback)
