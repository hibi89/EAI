"""C23 CPU-only resource budget tests with zero external actions."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from eai.local_scheduler import (
    LocalResourceBudget, LocalResourceSample,
    evaluate_local_budget, observe_and_evaluate_local_budget,
)


class LocalSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.budget = LocalResourceBudget(
            max_rss_mib=512, max_elapsed_ms=5000, max_steps=8)

    def sample(self, **changes):
        sample = LocalResourceSample(
            256 * 1024 * 1024, 100, 1, source="PROCESS_RSS_LOCAL")
        return replace(sample, **changes)

    def test_bounded_cpu_synthetic_observation_does_not_grant_action(self):
        decision = evaluate_local_budget(self.budget, self.sample())
        self.assertEqual(decision.status,
                         "CPU_LOCAL_BUDGET_AVAILABLE_NOT_EXECUTION_AUTHORITY")
        self.assertEqual(decision.observed_rss_mib_ceiling, 256)
        self.assertFalse(decision.gpu_required)
        self.assertFalse(decision.may_start_external_process)
        self.assertFalse(decision.may_write_original)

    def test_memory_cap_exceeded_holds(self):
        d = evaluate_local_budget(
            self.budget, self.sample(rss_bytes=600 * 1024 * 1024))
        self.assertIn("RSS_BUDGET_EXCEEDED", d.reason_codes)

    def test_unavailable_or_caller_rss_not_trusted(self):
        for sample in (self.sample(rss_bytes=None),
                       self.sample(source="CALLER_UNVERIFIED"),
                       self.sample(source="SYNTHETIC_TEST")):
            with self.subTest(source=sample.source):
                d = evaluate_local_budget(self.budget, sample)
                self.assertIn("REAL_RSS_NOT_ESTABLISHED", d.reason_codes)

    def test_timeout_and_step_exhaustion_are_separate_holds(self):
        d = evaluate_local_budget(
            self.budget, self.sample(elapsed_ms=5001, steps_completed=8))
        self.assertIn("TIME_BUDGET_EXCEEDED", d.reason_codes)
        self.assertIn("STEP_BUDGET_EXHAUSTED", d.reason_codes)

    def test_cancelled_or_parallel_work_denied(self):
        d = evaluate_local_budget(
            self.budget, self.sample(running_tasks=2, cancelled=True))
        self.assertIn("CANCELLED", d.reason_codes)
        self.assertIn("CONCURRENCY_BUDGET_EXCEEDED", d.reason_codes)

    def test_prohibited_resource_profile_is_rejected(self):
        for bad in ({"profile": "GPU_UNBOUNDED"},
                    {"max_rss_mib": 20000},
                    {"max_concurrent": 2},
                    {"max_elapsed_ms": True},
                    {"max_steps": 0}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                LocalResourceBudget(**bad)

    def test_invalid_boolean_or_overflow_telemetry_rejected(self):
        for change in ({"elapsed_ms": True},
                       {"rss_bytes": -1},
                       {"steps_completed": 65},
                       {"running_tasks": True},
                       {"cancelled": 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                evaluate_local_budget(self.budget, self.sample(**change))

    def test_no_reported_rss_fails_closed_in_real_probe(self):
        with patch("eai.local_scheduler.observe_own_process_rss_bytes",
                   return_value=None):
            result = observe_and_evaluate_local_budget(
                self.budget, elapsed_ms=1, steps_completed=1)
        self.assertEqual(result.status, "HOLD_LOCAL_RESOURCE_BUDGET")
        self.assertIn("REAL_RSS_NOT_ESTABLISHED", result.reason_codes)

    def test_mocked_local_probe_has_no_external_side_effect(self):
        with patch("eai.local_scheduler.observe_own_process_rss_bytes",
                   return_value=128 * 1024 * 1024):
            result = observe_and_evaluate_local_budget(
                self.budget, elapsed_ms=200, steps_completed=2,
                cold_start_ms=40)
        self.assertEqual(result.observed_rss_mib_ceiling, 128)
        self.assertEqual(result.measured_cold_start_ms, 40)
        self.assertEqual(result.status,
                         "CPU_LOCAL_BUDGET_AVAILABLE_NOT_EXECUTION_AUTHORITY")
