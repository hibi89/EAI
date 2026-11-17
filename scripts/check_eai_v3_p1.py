"""Fast, stdlib-only V3 implementation safety smoke (NOT full P2 CI).

Usage: python scripts/check_eai_v3_p1.py
Runs syntax compilation and focused offline unit fixtures without GUI, model,
external providers, owner files or complete legacy acceptance suite.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "eai/contracts.py", "eai/axnode_schema.py", "eai/axnode_store.py",
    "eai/axnode_maintenance.py", "eai/axnode_retrieval.py",
    "eai/axnode_memory.py", "eai/axnode_recovery.py",
    "eai/axnode_sidecar_backup.py", "eai/sidecar_recovery_audit.py",
    "eai/episode_replay.py", "eai/experience_admission.py",
    "eai/axnode_memory_review.py", "eai/problem_model.py", "eai/design_engine.py",
    "eai/hierarchical_planner.py", "eai/architect_runtime.py",
    "eai/evidence_ledger.py", "eai/logic_synthesis.py",
    "eai/logic_verifier.py", "eai/logic_counterexamples.py",
    "eai/logic_oracle.py", "eai/logic_validation_pipeline.py",
    "eai/solver_reference_check.py", "eai/synthetic_holdout.py",
    "eai/synthetic_candidate_interpreter.py",
    "eai/synthetic_candidate_verifier.py",
    "eai/candidate_evidence_review.py",
    "eai/policy_gate.py",
    "eai/player_runtime.py",
    "eai/episode_replay_dedup.py",
    "eai/episode_replay_fence.py",
    "eai/research_candidates.py",
    "eai/dual_mode_ablation.py",
    "eai/candidate_activation_preflight.py",
    "eai/player_cli.py",
    "eai/candidate_review_journal.py",
    "eai/sidecar_coherence_review.py",
    "eai/synthetic_candidate_benchmark.py",
    "eai/synthetic_curriculum.py", "eai/strategy_research_ranker.py",
    "eai/b0_cli.py", "eai/b1_cli.py", "eai/__main__.py",
    "eai/research_policy.py",
    "eai/research_providers.py", "eai/hydrogen_packet.py",
    "eai/research_quota.py", "eai/research_mock_transport.py",
)
TESTS = (
    "test_contracts_v3.py", "test_axnode_schema.py",
    "test_axnode_store.py", "test_axnode_maintenance.py",
    "test_axnode_retrieval.py", "test_axnode_memory.py",
    "test_axnode_recovery.py", "test_axnode_sidecar_backup.py",
    "test_sidecar_recovery_audit.py",
    "test_axnode_memory_review.py", "test_episode_replay.py",
    "test_experience_admission.py",
    "test_design_engine.py", "test_hierarchical_planner.py",
    "test_architect_runtime.py", "test_evidence_ledger.py",
    "test_evidence_append.py", "test_evidence_architect.py",
    "test_logic_synthesis.py", "test_logic_counterexamples.py",
    "test_logic_oracle.py", "test_logic_validation_pipeline.py",
    "test_solver_reference_check.py", "test_synthetic_holdout.py",
    "test_synthetic_candidate_execution.py",
    "test_candidate_evidence_review.py",
    "test_policy_gate_player.py",
    "test_episode_replay_dedup.py",
    "test_episode_replay_fence.py",
    "test_research_candidates.py",
    "test_dual_mode_ablation.py",
    "test_candidate_activation_preflight.py",
    "test_player_cli.py",
    "test_candidate_review_journal.py",
    "test_sidecar_coherence_review.py",
    "test_synthetic_candidate_benchmark.py",
    "test_synthetic_curriculum.py", "test_strategy_research_ranker.py",
    "test_b0_cli.py", "test_b1_cli.py",
    "test_hydrogen_policy.py",
    "test_research_mock_transport.py", "test_research_offline.py",
)


def main() -> int:
    failed = []
    for relative in SOURCES:
        file = ROOT / relative
        try:
            compile(file.read_bytes(), str(file), "exec")
        except (OSError, SyntaxError, ValueError) as exc:
            failed.append(f"{relative}:{type(exc).__name__}")
    if failed:
        for error in failed:
            print("P1_SYNTAX_FAIL", error, file=sys.stderr)
        return 1
    print("P1_SYNTAX_PASS", len(SOURCES))
    tests_root = ROOT / "tests"
    if not tests_root.is_dir():
        print("P1_TESTS_MISSING", file=sys.stderr)
        return 1
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for filename in TESTS:
        if not (tests_root / filename).is_file():
            print("P1_TEST_FILE_MISSING", filename, file=sys.stderr)
            return 1
        suite.addTests(loader.discover(
            start_dir=str(tests_root), pattern=filename,
            top_level_dir=str(tests_root)))
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    print("P1_TARGETED_TESTS", result.testsRun,
          "FAIL", len(result.failures), "ERROR", len(result.errors),
          "SKIP", len(result.skipped))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
