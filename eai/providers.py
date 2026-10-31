"""Local Ollama connector. Never forwards questions to cloud APIs."""
from .network import fetch_json, local_base_url


class OllamaChat:
    def __init__(self, model: str = "qwen2.5:3b", url: str = "http://127.0.0.1:11434"):
        self.model = model
        self.url = local_base_url(url)

    def respond(self, messages: list[dict[str, str]]) -> str:
        result = fetch_json(
            self.url + "/api/chat",
            payload={"model": self.model, "messages": messages, "stream": False},
            timeout=120.0,
        )
        message = result.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ValueError("Ollama returned an invalid chat response")
        return message["content"]
