"""EAI independent engine CLI: works without Ollama for known narrow tasks."""
import argparse
import csv
import io
import os
import json
import sqlite3
from pathlib import Path
import sys
from typing import NoReturn

from . import __version__
from .intent import QwenIntentParser
from .csv_analysis import inspect_csv, render_csv_summary
from .verify_csv import verify_csv_claims, load_claims, render_verification, METRICS
from .reconcile_csv import reconcile_csv, render_reconciliation
from .diagnose_csv import diagnose_csv, render_diagnosis
from .plan_engine import AuditGoal, CPUPlanExecutor, render_plan_report
from .goal_dispatch import execute_goal_document, render_goal_document
from .csv_advisor import advise_csv, render_csv_advice
from .goal_selector import select_goal, render_selection
from .report_export import build_report, render_report_html
from .customer_review import create_review, verify_review, CustomerReviewError
from .approved_run import run_approved
from .quick_goal import quick_goal, render_quick
from .goal_batch import execute_batch_document, render_batch
from .offline_doctor import run_offline_doctor, render_doctor
from .goal_pipeline import execute_pipeline_document, render_pipeline
from .manifest_builder import build_goal_manifest
from .runner import EAIRunner
from .storage import Store
from .tools import SearxNGSearch


class _PrivateCLIArgumentParser(argparse.ArgumentParser):
    """Argparse normally echoes invalid owner-provided argument values.

    Preserve standard exit-code 2 without revealing the rejected input,
    filesystem path, command text or pasted secret in stderr.
    """
    def error(self, message: str) -> NoReturn:
        # The content of message is untrusted and MUST NOT be printed.
        self.exit(2, f"{self.prog}: error: EAI_ARGUMENT_REJECTED\n")


def _public_failure_code(exc: BaseException) -> str:
    """Privacy-safe public CLI category; never echo owner exception contents."""
    if isinstance(exc, PermissionError):
        return "LOCAL_ACCESS_DENIED"
    if isinstance(exc, UnicodeError):
        return "INPUT_TEXT_ENCODING_REJECTED"
    if isinstance(exc, TimeoutError):
        return "LOCAL_RESOURCE_TIMEOUT"
    if isinstance(exc, csv.Error):
        return "INVALID_CSV_FORMAT"
    if isinstance(exc, sqlite3.DatabaseError):
        return "LOCAL_DATABASE_REJECTED"
    if isinstance(exc, OSError):
        return "LOCAL_IO_REJECTED"
    if isinstance(exc, (ValueError, KeyError)):
        return "INPUT_CONTRACT_REJECTED"
    return "LOCAL_OPERATION_REJECTED"


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        # Windows redirected streams may use cp1252/cp949 and either
        # strict *or* surrogateescape error handlers. Preserve the selected
        # code page but escape characters it cannot encode, so JSON receipts,
        # exit codes, and Korean report summaries never crash on print().
        for stream in (sys.stdout, sys.stderr):
            if isinstance(stream, io.TextIOWrapper) and stream.errors != 'backslashreplace':
                stream.reconfigure(errors='backslashreplace')
    p = _PrivateCLIArgumentParser(prog='eai', description='Independent, CPU-first EAI MVP')
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
    goal_cmd = sub.add_parser('solve-goal', help='CPU goal router: verified local choice, CSV relations, SQLite and tasks')
    goal_cmd.add_argument('spec', help='explicit local goal JSON file, <=64KiB')
    goal_cmd.add_argument('--json', action='store_true', help='structured receipt and source hash')
    batch_cmd = sub.add_parser('batch-goals', help='offline SHA256-pinned sequence of 1-6 goals')
    batch_cmd.add_argument('manifest', help='explicit local batch manifest')
    batch_cmd.add_argument('--json', action='store_true', help='structured verified batch receipt')
    doctor_cmd = sub.add_parser('doctor', help='no-network self-test of bundled typed goals')
    doctor_cmd.add_argument('--root', help='optional installed project root to inspect')
    doctor_cmd.add_argument('--json', action='store_true', help='structured offline evidence')
    pipeline_cmd = sub.add_parser('pipeline-goals', help='bounded dependency-gated offline goals')
    pipeline_cmd.add_argument('manifest', help='versioned goal pipeline manifest')
    pipeline_cmd.add_argument('--json', action='store_true', help='structured verified pipeline')
    manifest_cmd = sub.add_parser('make-manifest', help='stdout-only pinned manifest builder')
    manifest_cmd.add_argument('--mode', choices=['batch','pipeline'], required=True)
    manifest_cmd.add_argument('--root', default='.', help='local directory containing goal JSON files')
    manifest_cmd.add_argument('--goal', action='append', required=True, help='ID=relative.json (repeat 1-6)')
    manifest_cmd.add_argument('--requires', action='append', default=[], help='child=parent1,parent2 (pipeline only)')
    manifest_cmd.add_argument('--stop-on-error', action='store_true')
    advisor_cmd = sub.add_parser('advise-csv', help='read-only source-first CSV goal draft advisor')
    advisor_cmd.add_argument('--root', default='.', help='explicit local source directory')
    advisor_cmd.add_argument('--source', required=True, help='single relative CSV path inside root')
    advisor_cmd.add_argument('--encoding', choices=['utf-8-sig','utf-8','cp949'], default='utf-8-sig')
    advisor_cmd.add_argument('--json', action='store_true', help='print editable typed goal drafts')
    select_cmd = sub.add_parser('select-goal', help='propose a SHA-pinned owner-selected goal; never execute')
    select_cmd.add_argument('--manifest', required=True)
    select_cmd.add_argument('--request', required=True, help='1-500 character user request')
    select_cmd.add_argument('--qwen-select', action='store_true', help='explicit local Qwen INPUT-only classification')
    select_cmd.add_argument('--json', action='store_true')
    export_cmd = sub.add_parser('export-report', help='static verified local report to stdout only')
    export_cmd.add_argument('spec', help='explicit goal, batch or pipeline JSON')
    export_cmd.add_argument('--format', choices=['html','json'], default='html')
    approved_cmd = sub.add_parser('run-approved', help='explicit SHA-bound owner run; no model execution authority')
    approved_cmd.add_argument('--manifest', required=True)
    approved_cmd.add_argument('--id', required=True)
    approved_cmd.add_argument('--manifest-sha256', required=True)
    approved_cmd.add_argument('--goal-sha256', required=True)
    approved_cmd.add_argument('--json', action='store_true')
    quick_cmd = sub.add_parser('quick-goal', help='run existing read-only CPU goal from explicit flags')
    quick_cmd.add_argument('--kind',choices=['csv_relationships','csv_robust_outliers','local_evidence_search'],required=True)
    quick_cmd.add_argument('--root',default='.')
    quick_cmd.add_argument('--source')
    quick_cmd.add_argument('--sources',nargs='+')
    quick_cmd.add_argument('--columns',nargs='+')
    quick_cmd.add_argument('--terms',nargs='+')
    quick_cmd.add_argument('--encoding',choices=['utf-8-sig','utf-8','cp949'],default='utf-8-sig')
    quick_cmd.add_argument('--min-rows',type=int,default=5)
    quick_cmd.add_argument('--threshold',default='3')
    quick_cmd.add_argument('--max-results',type=int,default=10)
    quick_cmd.add_argument('--include-snippets',action='store_true')
    quick_cmd.add_argument('--json',action='store_true')
    explain_cmd = sub.add_parser('explain-preview',
        help='sanitized offline Architect/Player uncertainty and source trace')
    explain_cmd.add_argument('--kind', choices=['architect', 'player'], required=True)
    explain_cmd.add_argument('--problem-file', required=True)
    explain_cmd.add_argument('--axnode-root', help='existing local AXNODE store for architect')
    explain_cmd.add_argument('--plan-file', help='typed local PlanSpec for Player')
    explain_cmd.add_argument('--max-expansions', type=int, default=8)
    explain_cmd.add_argument('--format', choices=['json', 'text'],
                             default='json')
    adapter_cmd = sub.add_parser('adapter-preview',
        help='schema-only local adapter handshake; executor always disabled')
    adapter_cmd.add_argument('--problem-file', required=True)
    adapter_cmd.add_argument('--plan-file', required=True)
    adapter_cmd.add_argument('--handshake-file', required=True)
    resource_cmd = sub.add_parser('resource-preview',
        help='local process RSS budget gate; no process creation or GPU')
    resource_cmd.add_argument('--max-rss-mib', type=int, default=1024)
    resource_cmd.add_argument('--max-elapsed-ms', type=int, default=30000)
    resource_cmd.add_argument('--max-steps', type=int, default=32)
    resource_cmd.add_argument('--elapsed-ms', type=int, default=0)
    resource_cmd.add_argument('--steps-completed', type=int, default=0)
    resource_cmd.add_argument('--problem-file',
                              help='optional bounded local EAI ProblemSpec')
    resource_cmd.add_argument('--plan-file',
                              help='optional bounded local PlanSpec; requires --problem-file')
    journey_cmd = sub.add_parser('journey-preview',
        help='offline Architect->PolicyGate->CPU->pure Player, no real actions')
    journey_cmd.add_argument('--problem-file', required=True)
    journey_cmd.add_argument('--axnode-root', required=True)
    journey_cmd.add_argument('--max-expansions', type=int, default=8)
    journey_cmd.add_argument('--max-rss-mib', type=int, default=1024)
    journey_cmd.add_argument('--max-elapsed-ms', type=int, default=300000)
    journey_cmd.add_argument('--interpret-pure', action='store_true',
                             help='explicit pure synthetic no-op only')
    decide_cmd = sub.add_parser('decide-local',
        help='CPU-only EAI advisory decision or abstention; no external actions')
    decide_cmd.add_argument('--problem-file', required=True,
                            help='explicit bounded local V3 ProblemSpec JSON')
    decide_cmd.add_argument('--axnode-root', required=True,
                            help='existing owned AXNODE library')
    decide_cmd.add_argument('--max-expansions', type=int, default=8)
    decide_cmd.add_argument('--max-rss-mib', type=int, default=1024)
    decide_cmd.add_argument('--max-elapsed-ms', type=int, default=300000)
    decide_cmd.add_argument('--interpret-pure', action='store_true',
                            help='only the pure synthetic noop interpreter')
    decide_cmd.add_argument('--cancel-before-start', action='store_true',
                            help='report cancellation without reading sources')
    decide_cmd.add_argument('--format', choices=['json','text'],
                            default='text')
    architect_cmd = sub.add_parser('architect-preview', help='local-only V3 advisory design/plan; never execute')
    architect_cmd.add_argument('--problem-file', required=True, help='explicit local V3 ProblemSpec JSON <=32KiB')
    architect_cmd.add_argument('--axnode-root', required=True, help='existing explicit local AXNODE library')
    architect_cmd.add_argument('--max-expansions', type=int, default=8, help='bounded candidate expansions 1..8')
    player_cmd = sub.add_parser('player-preview', help='pure local synthetic no-op EAI Player (no real actions)')
    player_cmd.add_argument('--problem-file', required=True, help='explicit local ProblemSpec JSON')
    player_cmd.add_argument('--plan-file', required=True, help='explicit local bounded PlanSpec JSON')
    player_cmd.add_argument('--cancel-before-step', help='optional plan step to cancel before')
    rank_cmd = sub.add_parser('strategy-preview',
                              help='offline synthetic cost ranking, not learning')
    rank_cmd.add_argument('--problem-file', required=True)
    rank_cmd.add_argument('--axnode-root', required=True)
    rank_cmd.add_argument('--node-hashes', required=True)
    rank_cmd.add_argument('--seed', type=int, default=0)
    b0_cmd = sub.add_parser('b0-preview', help='strict offline B0 CPU baseline on synthetic fixtures only')
    b0_cmd.add_argument('--problem-file', required=True, help='local EAI ProblemSpec JSON')
    b0_cmd.add_argument('--axnode-root', required=True, help='existing local AXNODE store')
    b0_cmd.add_argument('--fixture-file', required=True, help='bounded public/synthetic JSON manifest')
    b0_cmd.add_argument('--node-hashes', required=True, help='2-4 comma-separated pinned AXNODE hashes')
    b1_cmd = sub.add_parser('b1-preview', help='offline B1 AXNODE synthetic steps versus B0 CPU (no promotion)')
    b1_cmd.add_argument('--problem-file', required=True, help='local EAI ProblemSpec JSON')
    b1_cmd.add_argument('--axnode-root', required=True, help='existing local AXNODE store')
    b1_cmd.add_argument('--fixture-file', required=True, help='bounded synthetic train/heldout JSON')
    b1_cmd.add_argument('--node-hashes', required=True, help='2-4 comma-separated pinned AXNODE hashes')
    review_cmd = sub.add_parser('customer-review', help='create a NEW offline HTML/JSON integrity-checked review folder')
    review_cmd.add_argument('--spec', required=True, help='owner-authorized local goal/manifest JSON')
    review_cmd.add_argument('--output-dir', required=True, help='unused local output directory')
    review_cmd.add_argument('--ack-authorized-local', action='store_true', help='explicit source handling acknowledgement; not provenance proof')
    check_cmd = sub.add_parser('verify-review', help='read-only verify existing review folder (unsigned)')
    check_cmd.add_argument('--output-dir', required=True)
    args = p.parse_args(argv)
    if args.command == 'decide-local':
        if args.cancel_before_start:
            print(json.dumps({
                'status':'CANCELLED',
                'reason':'OWNER_CANCELLED_BEFORE_LOCAL_DECISION',
                'real_execution_authorized':False}))
            return 130
        try:
            from .local_scheduler import LocalResourceBudget
            from .offline_journey import decide_scheduled_local_journey
            from .trace_renderer import (
                render_local_decision_explanation, render_local_decision_text)
            budget = LocalResourceBudget(
                max_rss_mib=args.max_rss_mib,
                max_elapsed_ms=args.max_elapsed_ms, max_steps=64)
            raw = decide_scheduled_local_journey(
                args.problem_file, args.axnode_root,
                max_expansions=args.max_expansions, budget=budget,
                interpret_pure_noop=args.interpret_pure)
            result = render_local_decision_explanation(raw)
            print(json.dumps(result, ensure_ascii=True, indent=2)
                  if args.format == 'json'
                  else render_local_decision_text(result), end='\n')
            return 0 if result['status'] == 'ADVISORY_CPU_SELECTION_UNVERIFIED' else 2
        except KeyboardInterrupt:
            print(json.dumps({
                'status':'CANCELLED', 'reason':'OWNER_INTERRUPTED_LOCAL_DECISION',
                'real_execution_authorized':False}), file=sys.stderr)
            return 130
        except (ValueError, KeyError, OSError, UnicodeError, PermissionError,
                sqlite3.DatabaseError):
            print(json.dumps({
                'status':'REJECTED', 'reason':'LOCAL_CPU_DECISION_REJECTED',
                'real_execution_authorized':False}), file=sys.stderr)
            return 1
    if args.command == 'journey-preview':
        try:
            from .local_scheduler import LocalResourceBudget
            from .offline_journey import preview_offline_journey
            budget = LocalResourceBudget(
                max_rss_mib=args.max_rss_mib,
                max_elapsed_ms=args.max_elapsed_ms, max_steps=64)
            report = preview_offline_journey(
                args.problem_file, args.axnode_root,
                max_expansions=args.max_expansions,
                budget=budget, interpret_pure_noop=args.interpret_pure)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report['architect_status'] in (
                'CANDIDATES_UNVERIFIED', 'PARTIAL_UNVERIFIED'
            ) else 2
        except KeyboardInterrupt:
            print(json.dumps({'status': 'CANCELLED',
                              'reason': 'OFFLINE_JOURNEY_INTERRUPTED'}),
                  file=sys.stderr)
            return 130
        except (ValueError, KeyError, OSError, UnicodeError,
                PermissionError, sqlite3.DatabaseError):
            print(json.dumps({'status': 'REJECTED',
                              'reason': 'OFFLINE_JOURNEY_PREVIEW_REJECTED'}),
                  file=sys.stderr)
            return 1
    if args.command == 'resource-preview':
        try:
            from dataclasses import asdict
            from .local_scheduler import (
                LocalBudgetDecision, LocalPlanPreflight, LocalResourceBudget, observe_and_evaluate_local_budget)
            decision: LocalBudgetDecision | LocalPlanPreflight
            budget = LocalResourceBudget(
                max_rss_mib=args.max_rss_mib,
                max_elapsed_ms=args.max_elapsed_ms,
                max_steps=args.max_steps)
            if args.problem_file is not None or args.plan_file is not None:
                if not args.problem_file or not args.plan_file:
                    raise ValueError('both local typed contracts required')
                from .player_cli import _read_local_contract
                from .contracts import ProblemSpec, PlanSpec
                from .local_scheduler import observe_plan_resource_preflight
                problem = ProblemSpec.validate(
                    _read_local_contract(args.problem_file))
                plan = PlanSpec.validate(
                    _read_local_contract(args.plan_file))
                decision = observe_plan_resource_preflight(
                    problem, plan, budget, elapsed_ms=args.elapsed_ms,
                    steps_completed=args.steps_completed)
                expected = 'PURE_SYNTHETIC_PLAN_PREFLIGHT_ONLY'
            else:
                decision = observe_and_evaluate_local_budget(
                    budget, elapsed_ms=args.elapsed_ms,
                    steps_completed=args.steps_completed)
                expected = 'CPU_LOCAL_BUDGET_AVAILABLE_NOT_EXECUTION_AUTHORITY'
            print(json.dumps(asdict(decision), ensure_ascii=False, indent=2))
            return 0 if decision.status == expected else 2
        except (ValueError, KeyError, OSError, UnicodeError):
            print(json.dumps({'status': 'REJECTED',
                              'reason': 'LOCAL_RESOURCE_PREVIEW_REJECTED'}),
                  file=sys.stderr)
            return 1
    if args.command == 'adapter-preview':
        try:
            from dataclasses import asdict
            from .adapter_stub import AdapterHandshake, inspect_adapter_handshake
            from .player_cli import _read_local_contract
            from .contracts import ProblemSpec, PlanSpec
            source = Path(args.handshake_file).expanduser()
            if source.is_symlink() or not source.is_file() or source.stat().st_size > 2048:
                raise ValueError('explicit bounded local adapter handshake required')
            hand = AdapterHandshake.from_json(source.read_bytes())
            problem = ProblemSpec.validate(_read_local_contract(args.problem_file))
            plan = PlanSpec.validate(_read_local_contract(args.plan_file))
            review = inspect_adapter_handshake(problem, plan, hand)
            print(json.dumps(asdict(review), ensure_ascii=False, indent=2))
            return 2   # A valid stub is STILL disabled, never a remote success
        except (ValueError, OSError, UnicodeError, KeyError):
            print(json.dumps({'status': 'REJECTED',
                              'reason': 'ADAPTER_STUB_PREVIEW_REJECTED'}),
                  file=sys.stderr)
            return 1
    if args.command == 'explain-preview':
        try:
            from .trace_renderer import (
                render_architect_explanation, render_player_explanation)
            if args.kind == 'architect':
                if args.plan_file is not None or not args.axnode_root:
                    raise ValueError('architect requires existing local root')
                from .architect_runtime import preview_architecture
                architect_source = preview_architecture(
                    args.problem_file, args.axnode_root,
                    max_expansions=args.max_expansions)
                summary = render_architect_explanation(architect_source)
            else:
                if args.axnode_root is not None or not args.plan_file:
                    raise ValueError('player requires explicit PlanSpec')
                from .player_cli import player_preview
                player_source = player_preview(args.problem_file, args.plan_file)
                summary = render_player_explanation(player_source)
            if args.format == 'text':
                from .trace_renderer import render_explanation_text
                print(render_explanation_text(summary), end='')
            else:
                print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0 if summary['status'] in (
                'CANDIDATES_UNVERIFIED',
                'PURE_SYNTHETIC_INTERPRETED_UNVERIFIED') else 2
        except (ValueError, KeyError, OSError, UnicodeError, PermissionError,
                sqlite3.DatabaseError):
            print(json.dumps({'status': 'REJECTED',
                              'reason': 'EXPLANATION_PREVIEW_REJECTED'}),
                  file=sys.stderr)
            return 1
    if args.command == 'player-preview':
        try:
            from .player_cli import player_preview
            report = player_preview(args.problem_file, args.plan_file,
                                    cancel_before_step=args.cancel_before_step)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report['status'] == 'PURE_SYNTHETIC_INTERPRETED_UNVERIFIED' else 2
        except (ValueError, OSError, UnicodeError, PermissionError):
            print(json.dumps({'status': 'REJECTED',
                              'reason': 'PLAYER_PREVIEW_INVALID_OR_UNAVAILABLE'}),
                  file=sys.stderr)
            return 1
    if args.command == 'architect-preview':
        try:
            from .architect_runtime import preview_architecture
            report = preview_architecture(args.problem_file, args.axnode_root,
                                          max_expansions=args.max_expansions)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report['status'] == 'CANDIDATES_UNVERIFIED' else 2
        except (ValueError, OSError, UnicodeError) as exc:
            # Keep private problem paths and payloads out of diagnostic output.
            print(json.dumps({'status':'REJECTED', 'reason':'ARCHITECT_PREVIEW_INVALID_OR_UNAVAILABLE'}),
                  file=sys.stderr)
            return 1
    if args.command == 'strategy-preview':
        try:
            from .research_rank_cli import preview_strategy
            report = preview_strategy(
                args.problem_file, args.axnode_root,
                args.node_hashes, seed=args.seed)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report['status'] == 'SYNTHETIC_COST_ORDER_ONLY_NOT_LEARNING' else 2
        except (ValueError, KeyError, OSError, UnicodeError, sqlite3.DatabaseError):
            print(json.dumps({'status': 'REJECTED',
                              'reason': 'STRATEGY_PREVIEW_INVALID_OR_UNAVAILABLE'}),
                  file=sys.stderr)
            return 1
    if args.command == 'b0-preview':
        try:
            from .b0_cli import b0_preview
            report = b0_preview(args.problem_file, args.axnode_root,
                                args.fixture_file, args.node_hashes)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return (0 if report['baseline']['status'] ==
                    'B0_SYNTHETIC_HELDOUT_MATCH_UNVERIFIED' else 2)
        except (ValueError, KeyError, OSError, UnicodeError,
                csv.Error, sqlite3.DatabaseError) as exc:
            # A malformed manifest may contain private data: never echo inputs.
            print(json.dumps({'status':'REJECTED',
                              'reason':'B0_SYNTHETIC_PREVIEW_REJECTED'}),
                  file=sys.stderr)
            return 1
    if args.command == 'b1-preview':
        try:
            from .b1_cli import b1_preview
            report = b1_preview(args.problem_file, args.axnode_root,
                                args.fixture_file, args.node_hashes)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return (0 if report['comparison']['status'] ==
                    'B1_SYNTHETIC_PARITY_WITH_B0_UNVERIFIED' else 2)
        except (ValueError, KeyError, OSError, UnicodeError,
                csv.Error, sqlite3.DatabaseError):
            print(json.dumps({'status':'REJECTED',
                              'reason':'B1_SYNTHETIC_PREVIEW_REJECTED'}),
                  file=sys.stderr)
            return 1
    if args.command == 'customer-review':
        try:
            result = create_review(args.spec, args.output_dir,
                                   acknowledge=args.ack_authorized_local)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except (CustomerReviewError, OSError, ValueError, UnicodeError) as exc:
            code = str(exc) if isinstance(exc, CustomerReviewError) else 'CUSTOMER_REVIEW_REJECTED'
            print(json.dumps({'status':'REJECTED','error_code':code}), file=sys.stderr)
            return 1
    if args.command == 'verify-review':
        try:
            print(json.dumps(verify_review(args.output_dir), ensure_ascii=False, indent=2))
            return 0
        except (CustomerReviewError, OSError, ValueError, UnicodeError) as exc:
            code = str(exc) if isinstance(exc, CustomerReviewError) else 'VERIFY_REVIEW_REJECTED'
            print(json.dumps({'status':'REJECTED','error_code':code}), file=sys.stderr)
            return 1
    if args.command == 'quick-goal':
        try:
            report=quick_goal(args.kind,args.root,source=args.source,sources=args.sources,
                              columns=args.columns,terms=args.terms,encoding=args.encoding,
                              min_rows=args.min_rows,threshold=args.threshold,
                              max_results=args.max_results,
                              include_snippets=args.include_snippets)
            print(json.dumps(report,ensure_ascii=False,indent=2) if args.json
                  else render_quick(report))
            return {'AGREE':0,'CONFLICT':2,'UNAVAILABLE':3}[report['status']]
        except (ValueError,OSError,UnicodeError,csv.Error,TimeoutError) as exc:
            print('EAI QUICK ERROR:',type(exc).__name__,_public_failure_code(exc),file=sys.stderr)
            return 1
    if args.command == 'run-approved':
        try:
            report = run_approved(args.manifest, args.id,
                                  args.manifest_sha256, args.goal_sha256)
            print(json.dumps(report,ensure_ascii=False,indent=2) if args.json
                  else render_goal_document(report['receipt']))
            return {'DECIDED':0,'TIE':0,'AGREE':0,
                    'CONFLICT':2,'UNAVAILABLE':3}[report['status']]
        except (ValueError,OSError,UnicodeError,csv.Error,TimeoutError) as exc:
            print('EAI APPROVAL ERROR:',type(exc).__name__,_public_failure_code(exc),file=sys.stderr)
            return 1
    if args.command == 'export-report':
        try:
            summary = build_report(args.spec)
            print(json.dumps(summary, ensure_ascii=False, indent=2) if args.format == 'json'
                  else render_report_html(summary))
            return {'AGREE': 0, 'DECIDED': 0, 'COMPLETE': 0,
                    'TIE': 2, 'CONFLICT': 2, 'REVIEW': 2,
                    'UNAVAILABLE': 3, 'PARTIAL': 3,
                    'FAILED': 1}[summary['status']]
        except (ValueError, OSError, UnicodeError, csv.Error, TimeoutError) as exc:
            print('EAI EXPORT ERROR:', type(exc).__name__, _public_failure_code(exc), file=sys.stderr)
            return 1
    if args.command == 'select-goal':
        try:
            report = select_goal(args.manifest, args.request,
                                 use_qwen=args.qwen_select, model=args.model,
                                 ollama_url=args.ollama_url)
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.json
                  else render_selection(report))
            return 0 if report['status'] == 'PROPOSED' else 3
        except (ValueError, OSError, UnicodeError, csv.Error) as exc:
            print('EAI SELECT ERROR:', type(exc).__name__, _public_failure_code(exc), file=sys.stderr)
            return 1
    if args.command == 'advise-csv':
        try:
            report = advise_csv(args.root, args.source, encoding=args.encoding)
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.json
                  else render_csv_advice(report))
            return 0 if report['status'] == 'DRAFT_READY' else 3
        except (ValueError, OSError, UnicodeError, csv.Error) as exc:
            print('EAI ADVISOR ERROR:', type(exc).__name__, _public_failure_code(exc), file=sys.stderr)
            return 1
    if args.command == 'health':
        print('EAI independent CPU-first engine v0.1')
        print('parser:', 'Qwen input-only' if args.use_qwen_intent else 'CPU rules')
        print('profile:', args.profile)
        print('search:', 'enabled by consent' if args.online else 'disabled')
        print('SearXNG configured:', bool(args.searxng_url))
        print('SQLite:', args.db)
        return 0
    if args.command == 'make-manifest':
        try:
            manifest = build_goal_manifest(
                args.mode, args.root, args.goal, args.requires,
                continue_on_error=not args.stop_on_error)
            print(json.dumps(manifest,ensure_ascii=True,indent=2))
            return 0
        except (ValueError,OSError,UnicodeError) as exc:
            print('EAI MANIFEST ERROR:',type(exc).__name__,_public_failure_code(exc),file=sys.stderr)
            return 1
    if args.command == 'pipeline-goals':
        try:
            output=execute_pipeline_document(args.manifest)
            print(json.dumps(output,ensure_ascii=False,indent=2) if args.json
                  else render_pipeline(output))
            return {'COMPLETE':0,'REVIEW':2,'PARTIAL':3,'FAILED':1}[output['status']]
        except (ValueError,OSError,UnicodeError,csv.Error,TimeoutError) as exc:
            print('EAI PIPELINE ERROR:',type(exc).__name__,_public_failure_code(exc),file=sys.stderr)
            return 1
    if args.command == 'doctor':
        report = run_offline_doctor(args.root)
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json
              else render_doctor(report))
        return 0 if report['status'] == 'PASS' else 4
    if args.command == 'batch-goals':
        try:
            output = execute_batch_document(args.manifest)
            print(json.dumps(output, ensure_ascii=False, indent=2) if args.json
                  else render_batch(output))
            return {'COMPLETE':0, 'REVIEW':2, 'PARTIAL':3, 'FAILED':1}[output['status']]
        except (ValueError, OSError, UnicodeError, csv.Error, TimeoutError) as exc:
            print('EAI BATCH ERROR:', type(exc).__name__, _public_failure_code(exc), file=sys.stderr)
            return 1
    if args.command == 'solve-goal':
        try:
            report = execute_goal_document(args.spec)
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.json
                  else render_goal_document(report))
            return {'DECIDED': 0, 'TIE': 0, 'AGREE': 0,
                    'CONFLICT': 2, 'UNAVAILABLE': 3}[report['status']]
        except (ValueError, OSError, UnicodeError, csv.Error, TimeoutError) as exc:
            print('EAI GOAL ERROR:', type(exc).__name__, _public_failure_code(exc), file=sys.stderr)
            return 1
    if args.command == 'analyze-csv':
        try:
            print(render_csv_summary(inspect_csv(args.path, encoding=args.encoding)))
            return 0
        except (ValueError, OSError, UnicodeError, csv.Error) as exc:
            print('EAI CSV ERROR:', type(exc).__name__, _public_failure_code(exc), file=sys.stderr)
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
            print('EAI VERIFY ERROR:', type(exc).__name__, _public_failure_code(exc), file=sys.stderr)
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
            print('EAI PLAN ERROR:', type(exc).__name__, _public_failure_code(exc), file=sys.stderr)
            return 1
    if args.command == 'diagnose-csv':
        try:
            report = diagnose_csv(args.left, args.right, key=args.key, values=args.values,
                                  tolerance=args.tolerance, encoding=args.encoding)
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.json
                  else render_diagnosis(report))
            return {'AGREE': 0, 'CONFLICT': 2, 'UNAVAILABLE': 3}[report['status']]
        except (ValueError, OSError, UnicodeError, csv.Error) as exc:
            print('EAI DIAGNOSE ERROR:', type(exc).__name__, _public_failure_code(exc), file=sys.stderr)
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
            print('EAI RECONCILE ERROR:', type(exc).__name__, _public_failure_code(exc), file=sys.stderr)
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
        print('EAI ERROR:', type(exc).__name__, _public_failure_code(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
