"""Public API for the independent EAI engine. Qwen cannot author final answers."""
from .runner import EAIRunner as EAI, Answer

__all__ = ['EAI', 'Answer']
