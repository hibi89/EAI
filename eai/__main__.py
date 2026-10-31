"""EAI independent engine CLI: works without Ollama for known narrow tasks."""
import argparse
import csv
import os
from pathlib import Path
import sys

from . import __version__
from .intent import QwenIntentParser
from .csv_analysis import inspect_csv, render_csv_summary
from .runner import EAIRunner
from .storage import Store
from .tools import SearxNGSearch


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog='eai', description='Independent, CPU-first EAI MVP')
    p.add_argument('--version', action='version', version=__version__)
    p.add_argument('--db', default=os.environ.get('EAI_DB', str(Path.home() / '.eai' / 'eai.sqlite3')))
    p.add_argument('--model', default=os.environ.get('EAI_MODEL', 'qwen2.5:3b'))
    p.add_argument('--ollama-url', default=os.environ.get('EAI_OLLAMA_URL', 'http://127.0.0.1:11434'))
    p.add_argument('--searxng-url', default=os.environ.get('EAI_SEARXNG_URL', ''))
    p.add_argument('--use-qwen-intent', action='store_true', help='Qwen parses intent ONLY; otherwise CPU rule parser')
    p.add_argument('--profile', choices=['CPU_ECO', 'OLLAMA_DEFAULT'], default='CPU_ECO')
    p.add_argument('--online', action='store_true', help='consent: forward search query via local SearXNG')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('chat', help='interactive narrow-task CLI')
    a = sub.add_parser('ask', help='one task')
    a.add_argument('question')
    sub.add_parser('health', help='display offline-only configuration')
    csv_cmd = sub.add_parser('analyze-csv', help='read-only local CSV numeric profile (no model/network)')
    csv_cmd.add_argument('path', help='explicit local CSV path')
    csv_cmd.add_argument('--encoding', choices=['utf-8-sig','utf-8','cp949'], default='utf-8-sig')
    args = p.parse_args(argv)
    if args.command == 'health':
        print('EAI independent CPU-first engine v0.1')
        print('parser:', 'Qwen input-only' if args.use_qwen_intent else 'CPU rules')
        print('profile:', args.profile)
        print('search:', 'enabled by consent' if args.online else 'disabled')
        print('SearXNG configured:', bool(args.searxng_url))
        print('SQLite:', args.db)
        return 0
    if args.command == 'analyze-csv':
        try:
            print(render_csv_summary(inspect_csv(args.path, encoding=args.encoding)))
            return 0
        except (ValueError, OSError, UnicodeError, csv.Error) as exc:
            print('EAI CSV ERROR:', type(exc).__name__, str(exc), file=sys.stderr)
            return 1
    try:
        parser = (QwenIntentParser(args.model, args.ollama_url, args.profile)
                  if args.use_qwen_intent else None)
        search = SearxNGSearch(args.searxng_url) if args.searxng_url else None
        store = Store(args.db)
        try:
            runner = EAIRunner(store, parser, search)
            if args.command == 'ask':
                questions = [args.question]
            else:
                questions = None
                print('EAI independent engine (help: 도움말 / exit: quit)')
            while True:
                if questions is not None:
                    if not questions: break
                    question = questions.pop()
                else:
                    try: question = input('You> ').strip()
                    except (EOFError, KeyboardInterrupt):
                        print()
                        break
                    if question.lower() in ('quit', 'exit'): break
                    if not question: continue
                answer = runner.ask(question, allow_online=args.online)
                print('EAI>', answer.text)
                for note in answer.result.warnings:
                    if note not in answer.text:
                        print('NOTICE:', note)
                if questions is not None: break
        finally:
            store.close()
    except Exception as exc:
        print('EAI ERROR:', type(exc).__name__, str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
