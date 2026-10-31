"""Minimal CLI; no browser/server exposed to the local network."""
import argparse
import os
from pathlib import Path
import sys

from . import __version__
from .app import EAI
from .providers import OllamaChat
from .storage import Store
from .tools import SearxNGSearch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eai", description="EAI local-first AI (CLI MVP)")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--db", default=os.getenv("EAI_DB", str(Path.home() / ".eai" / "eai.sqlite3")))
    parser.add_argument("--model", default=os.getenv("EAI_MODEL", "qwen2.5:3b"))
    parser.add_argument("--ollama-url", default=os.getenv("EAI_OLLAMA_URL", "http://127.0.0.1:11434"))
    parser.add_argument("--searxng-url", default=os.getenv("EAI_SEARXNG_URL", ""))
    parser.add_argument("--online", action="store_true", help="explicit opt-in to local metasearch (forwards query externally)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("chat", help="interactive chat (quit to exit)")
    ask = sub.add_parser("ask", help="ask one question")
    ask.add_argument("question")
    sub.add_parser("health", help="show configuration, without making network requests")
    args = parser.parse_args(argv)

    if args.command == "health":
        print("EAI local-only configuration")
        print("model:", args.model)
        print("Ollama:", args.ollama_url)
        print("online permitted:", args.online)
        print("SearXNG configured:", bool(args.searxng_url))
        print("database:", args.db)
        return 0

    try:
        model = OllamaChat(args.model, args.ollama_url)
        search = SearxNGSearch(args.searxng_url) if args.searxng_url else None
        store = Store(args.db)
        try:
            eai = EAI(store, model, search)
            if args.command == "ask":
                questions = [args.question]
            else:
                questions = None
                print("EAI CLI — type 'quit' to exit")
            while True:
                if questions is not None:
                    if not questions:
                        break
                    question = questions.pop()
                else:
                    try:
                        question = input("You> ").strip()
                    except (EOFError, KeyboardInterrupt):
                        print()
                        break
                    if question.lower() in {"quit", "exit"}:
                        break
                    if not question:
                        continue
                answer = eai.ask(question, allow_online=args.online)
                print("EAI>", answer.text)
                if answer.warning:
                    print("NOTICE:", answer.warning)
                for i, item in enumerate(answer.sources, 1):
                    print(f"SOURCE {i}: {item.title} — {item.url}")
                if answer.cache_hit:
                    print("CACHE: reused search results")
                if questions is not None:
                    break
        finally:
            store.close()
    except Exception as exc:
        print(f"EAI ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
