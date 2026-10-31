"""Compatibility boundary: use QwenIntentParser for input, not output."""
from .intent import QwenIntentParser


class OllamaChat:
    """Deprecated unsafe API; retained to fail visibly instead of silently synthesizing."""
    def __init__(self, *args, **kwargs):
        raise RuntimeError('Qwen is input-only. Use QwenIntentParser.parse instead.')


__all__ = ['QwenIntentParser']
