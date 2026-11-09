"""EAI independent engine CLI: works without Ollama for known narrow tasks."""
import argparse
import csv
import os
import json
from pathlib import Path
import sys

from . import __version__
from .intent import QwenIntentParser
from .csv_analysis import inspect_csv, render_csv_summary
from .verify_csv import verify_csv_claims, load_claims, render_verification, METRICS
from .reconcile_csv import reconcile_csv, render_reconciliation
from .diagnose_csv import diagnose_csv, render_diagnosis
from .plan_engine import AuditGoal, CPUPlanExecutor, render_plan_report
from .goal_dispatch import execute_goal_document, render_goal_document
from .goal_batch import execute_batch_document, render_batch
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
    verify_cmd = sub.add_parser('verify-csv', help='independent read-only numeric claim verification against local CSV')
    verify_cmd.add_argument('path', help='explicit local CSV path')
    verify_cmd.add_argument('--claims', help='local JSON array of claims (read-only, maximum 24)')
    verify_cmd.add_argument('--column', help='CSV column for a single claim')
    verify_cmd.add_argument('--metric', choices=sorted(METRICS))
    verify_cmd.add_argument('--expected', help='expected finite decimal as TEXT')
    verify_cmd.add_argument('--tolerance', default='0', help='nonnegative absolute decimal tolerance')
    verify_cmd.add_argument('--encoding', choices=['utf-8-sig', 'utf-8', 'cp949'], default='utf-8-sig')
    verify_cmd.add_argument('--json', action='store_true', help='emit structured result as JSON')
    reconcile_cmd = sub.add_parser('reconcile-csv', help='CPU-only read-only two-CSV keyed cross-verification')
    reconcile_cmd.add_argument('left', help='first explicitly selected local CSV')
    reconcile_cmd.add_argument('right', help='second explicitly selected local CSV')
    reconcile_cmd.add_argument('--key', required=True, help='common unique key column')
    reconcile_cmd.add_argument('--value', required=True, help='numeric value column')
    reconcile_cmd.add_argument('--tolerance', default='0', help='nonnegative absolute decimal tolerance')
    reconcile_cmd.add_argument('--encoding', choices=['utf-8-sig', 'utf-8', 'cp949'], default='utf-8-sig')
    reconcile_cmd.add_argument('--json', action='store_true', help='structured read-only report')
    diagnose_cmd = sub.add_parser('diagnose-csv', help='CPU multi-metric discrepancy and candidate-cause analysis')
    diagnose_cmd.add_argument('left', help='first explicit local CSV')
    diagnose_cmd.add_argument('right', help='second explicit local CSV')
    diagnose_cmd.add_argument('--key', required=True, help='unique key in both CSVs')
    diagnose_cmd.add_argument('--values', nargs='+', required=True, help='1-8 distinct numeric columns')
    diagnose_cmd.add_argument('--tolerance', default='0', help='shared absolute tolerance applied independently per field')
    diagnose_cmd.add_argument('--encoding', choices=['utf-8-sig', 'utf-8', 'cp949'], default='utf-8-sig')
    diagnose_cmd.add_argument('--json', action='store_true', help='structured diagnostic output')
    solve_cmd = sub.add_parser('solve-csv', help='CPU-owned goal planning, verification and fallback on two local CSVs')
    solve_cmd.add_argument('left', help='explicit local CSV A')
    solve_cmd.add_argument('right', help='explicit local CSV B')
    solve_cmd.add_argument('--key', required=True, help='unique key column')
    solve_cmd.add_argument('--values', nargs='+', required=True, help='one to eight numeric columns')
    solve_cmd.add_argument('--tolerance', default='0', help='absolute numeric tolerance')
    solve_cmd.add_argument('--encoding', choices=['utf-8-sig', 'utf-8', 'cp949'], default='utf-8-sig')
    solve_cmd.add_argument('--max-seconds', type=int, default=60, help='maximum elapsed seconds before starting each stage')
    solve_cmd.add_argument('--json', action='store_true', help='structured plan, trace, evidence and fallback')
    goal_cmd = sub.add_parser('solve-goal', help='CPU goal router: CSV audit, options, task portfolio or critical-path schedule')
    goal_cmd.add_argument('spec', help='explicit local goal JSON file, <=64KiB')
    goal_cmd.add_argument('--json', action='store_true', help='structured receipt and source hash')
    batch_cmd = sub.add_parser('batch-goals', help='offline SHA256-pinned sequence of 1-6 goals')
    batch_cmd.add_argument('manifest', help='explicit local batch manifest')
    batch_cmd.add_argument('--json', action='store_true', help='structured verified batch receipt')
    args = p.parse_args(argv)
    if args.command == 'health':
        print('EAI independent CPU-first engine v0.1')
        print('parser:', 'Qwen input-only' if args.use_qwen_intent else 'CPU rules')
        print('profile:', args.profile)
        print('search:', 'enabled by consent' if args.online else 'disabled')
        print('SearXNG configured:', bool(args.searxng_url))
        print('SQLite:', args.db)
        return 0
    if args.command == 'batch-goals':
        try:
            output = execute_batch_document(args.manifest)
            print(json.dumps(output, ensure_ascii=False, indent=2) if args.json
                  else render_batch(output))
            return {'COMPLETE':0, 'REVIEW':2, 'PARTIAL':3, 'FAILED':1}[output['status']]
        except (ValueError, OSError, UnicodeError, csv.Error, TimeoutError) as exc:
            print('EAI BATCH ERROR:', type(exc).__name__, str(exc), file=sys.stderr)
            return 1
    if args.command == 'solve-goal':
        try:
            report = execute_goal_document(args.spec)
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.json
                  else render_goal_document(report))
            return {'DECIDED': 0, 'TIE': 0, 'AGREE': 0,
                    'CONFLICT': 2, 'UNAVAILABLE': 3}[report['status']]
        except (ValueError, OSError, UnicodeError, csv.Error, TimeoutError) as exc:
            print('EAI GOAL ERROR:', type(exc).__name__, str(exc), file=sys.stderr)
            return 1
    if args.command == 'analyze-csv':
        try:
            print(render_csv_summary(inspect_csv(args.path, encoding=args.encoding)))
            return 0
        except (ValueError, OSError, UnicodeError, csv.Error) as exc:
            print('EAI CSV ERROR:', type(exc).__name__, str(exc), file=sys.stderr)
            return 1
    if args.command == 'verify-csv':
        try:
            if args.claims:
                if args.column is not None or args.metric is not None or args.expected is not None or args.tolerance != '0':
                    raise ValueError('--claims cannot be combined with single-claim options')
                claims = load_claims(args.claims)
                raw_claims = [dict(column=v['column'], metric=v['metric'],
                                   expected=format(v['expected'], 'f'),
                                   tolerance=format(v['tolerance'], 'f')) for v in claims]
            else:
                if args.column is None or args.metric is None or args.expected is None:
                    raise ValueError('single claim requires --column, --metric and --expected')
                raw_claims = [dict(column=args.column, metric=args.metric,
                                   expected=args.expected, tolerance=args.tolerance)]
            report = verify_csv_claims(args.path, raw_claims, encoding=args.encoding)
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.json
                  else render_verification(report))
            return {'VERIFIED': 0, 'CONFLICT': 2, 'UNAVAILABLE': 3}[report['status']]
        except (ValueError, OSError, UnicodeError, csv.Error) as exc:
            print('EAI VERIFY ERROR:', type(exc).__name__, str(exc), file=sys.stderr)
            return 1
    if args.command == 'solve-csv':
        try:
            goal = AuditGoal(args.left, args.right, args.key, args.values,
                             tolerance=args.tolerance, encoding=args.encoding,
                             max_seconds=args.max_seconds)
            report = CPUPlanExecutor().execute(goal)
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.json
                  else render_plan_report(report))
            return {'AGREE': 0, 'CONFLICT': 2, 'UNAVAILABLE': 3}[report['status']]
        except (ValueError, OSError, UnicodeError, csv.Error, TimeoutError) as exc:
            print('EAI PLAN ERROR:', type(exc).__name__, str(exc), file=sys.stderr)
            return 1
    if args.command == 'diagnose-csv':
        try:
            report = diagnose_csv(args.left, args.right, key=args.key, values=args.values,
                                  tolerance=args.tolerance, encoding=args.encoding)
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.json
                  else render_diagnosis(report))
            return {'AGREE': 0, 'CONFLICT': 2, 'UNAVAILABLE': 3}[report['status']]
        except (ValueError, OSError, UnicodeError, csv.Error) as exc:
            print('EAI DIAGNOSE ERROR:', type(exc).__name__, str(exc), file=sys.stderr)
            return 1
    if args.command == 'reconcile-csv':
        try:
            report = reconcile_csv(args.left, args.right, key=args.key,
                                   value=args.value, tolerance=args.tolerance,
                                   encoding=args.encoding)
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.json
                  else render_reconciliation(report))
            return {'AGREE': 0, 'CONFLICT': 2, 'UNAVAILABLE': 3}[report['status']]
        except (ValueError, OSError, UnicodeError, csv.Error) as exc:
            print('EAI RECONCILE ERROR:', type(exc).__name__, str(exc), file=sys.stderr)
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
