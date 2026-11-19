"""C23 fail-closed Windows-friendly local CPU resource observations.

This policy never spawns workers, changes priority, calls a GPU, or enables
a model. Actual RSS observation uses only the current process; caller-provided
synthetic measurements are advisory and cannot prove machine performance.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import sys

_MAX_BYTES = 32 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class LocalResourceBudget:
    max_rss_mib: int = 1024
    max_elapsed_ms: int = 30000
    max_steps: int = 32
    max_concurrent: int = 1
    profile: str = "CPU_ECO"

    def __post_init__(self) -> None:
        if (type(self.max_rss_mib) is not int
                or not 128 <= self.max_rss_mib <= 8192
                or type(self.max_elapsed_ms) is not int
                or not 50 <= self.max_elapsed_ms <= 300000
                or type(self.max_steps) is not int
                or not 1 <= self.max_steps <= 64
                or type(self.max_concurrent) is not int
                or self.max_concurrent != 1
                or type(self.profile) is not str
                or self.profile not in ("CPU_ECO", "CPU_STANDARD")):
            raise ValueError("unbounded or privileged local resource budget")


@dataclass(frozen=True)
class LocalResourceSample:
    rss_bytes: int | None
    elapsed_ms: int
    steps_completed: int
    running_tasks: int = 1
    cancelled: bool = False
    cold_start_ms: int | None = None
    source: str = "CALLER_UNVERIFIED"


@dataclass(frozen=True)
class LocalBudgetDecision:
    status: str
    reason_codes: tuple[str, ...]
    observed_rss_mib_ceiling: int | None
    observed_elapsed_ms: int
    measured_cold_start_ms: int | None
    gpu_required: bool = False
    may_start_external_process: bool = False
    may_write_original: bool = False


def observe_own_process_rss_bytes() -> int | None:
    """Measure current-process resident working set, never scan other PIDs.

    Returns None when an OS does not expose a reliable measurement. No
    memory usage is invented in that case; the budget gate fails closed.
    """
    if os.name == "nt":
        try:
            import ctypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]
            memory = ProcessMemoryCounters()
            memory.cb = ctypes.sizeof(memory)
            # WinDLL is Windows-only; absence must never produce a fake
            # memory measurement or an approving resource verdict.
            win_dll = getattr(ctypes, "WinDLL", None)
            if win_dll is None:
                return None
            kernel = win_dll("kernel32", use_last_error=True)
            psapi = win_dll("psapi", use_last_error=True)
            kernel.GetCurrentProcess.restype = ctypes.c_void_p
            psapi.GetProcessMemoryInfo.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(ProcessMemoryCounters),
                ctypes.c_ulong,
            ]
            psapi.GetProcessMemoryInfo.restype = ctypes.c_int
            if psapi.GetProcessMemoryInfo(
                    kernel.GetCurrentProcess(), ctypes.byref(memory),
                    ctypes.sizeof(memory)) != 1:
                return None
            return int(memory.WorkingSetSize) if memory.WorkingSetSize else None
        except (OSError, AttributeError, ValueError, ImportError):
            return None
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/status", encoding="ascii") as status:
                for line in status:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        if len(parts) == 3 and parts[2] == "kB":
                            return int(parts[1]) * 1024
        except (OSError, ValueError, UnicodeError):
            return None
    return None


def evaluate_local_budget(
    budget: LocalResourceBudget, sample: LocalResourceSample
) -> LocalBudgetDecision:
    if type(budget) is not LocalResourceBudget or type(sample) is not LocalResourceSample:
        raise ValueError("typed CPU budget and sample required")
    # Never treat a missing/forged caller-supplied observation as a resource PASS.
    if (type(sample.elapsed_ms) is not int or sample.elapsed_ms < 0
            or type(sample.steps_completed) is not int
            or not 0 <= sample.steps_completed <= 64
            or type(sample.running_tasks) is not int
            or not 0 <= sample.running_tasks <= 64
            or type(sample.cancelled) is not bool
            or type(sample.source) is not str
            or sample.source not in ("PROCESS_RSS_LOCAL",
                                    "CALLER_UNVERIFIED", "SYNTHETIC_TEST")
            or (sample.cold_start_ms is not None and
                (type(sample.cold_start_ms) is not int or
                 not 0 <= sample.cold_start_ms <= 300000))
            or (sample.rss_bytes is not None and
                (type(sample.rss_bytes) is not int
                 or not 0 <= sample.rss_bytes <= _MAX_BYTES))):
        raise ValueError("invalid local telemetry")
    rss = sample.rss_bytes
    reasons = []
    if sample.cancelled:
        reasons.append("CANCELLED")
    if sample.source != "PROCESS_RSS_LOCAL" or rss is None:
        reasons.append("REAL_RSS_NOT_ESTABLISHED")
    if rss is not None and rss > budget.max_rss_mib * 1024 * 1024:
        reasons.append("RSS_BUDGET_EXCEEDED")
    if sample.elapsed_ms > budget.max_elapsed_ms:
        reasons.append("TIME_BUDGET_EXCEEDED")
    # A completed count equal to the cap is valid; only work beyond the cap
    # exceeds the budget. Callers must account for the aggregate journey count.
    if sample.steps_completed > budget.max_steps:
        reasons.append("STEP_BUDGET_EXHAUSTED")
    if sample.running_tasks > budget.max_concurrent:
        reasons.append("CONCURRENCY_BUDGET_EXCEEDED")
    return LocalBudgetDecision(
        "CPU_LOCAL_BUDGET_AVAILABLE_NOT_EXECUTION_AUTHORITY" if not reasons
        else "HOLD_LOCAL_RESOURCE_BUDGET",
        tuple(sorted(reasons)),
        (rss + (1024 * 1024 - 1)) // (1024 * 1024)
        if rss is not None else None,
        sample.elapsed_ms, sample.cold_start_ms,
    )


@dataclass(frozen=True)
class LocalPlanPreflight:
    """Structural safety check only: not proof of runtime latency or permission."""
    status: str
    plan_sha256: str
    reason_codes: tuple[str, ...]
    permits_real_execution: bool = False
    permits_original_writes: bool = False


def inspect_plan_resource_preflight(
    problem: object, plan: object,
    budget: LocalResourceBudget, sample: LocalResourceSample,
) -> LocalPlanPreflight:
    from .contracts import ProblemSpec, PlanSpec
    from .policy_gate import evaluate_plan_policy
    if type(problem) is not ProblemSpec or type(plan) is not PlanSpec:
        raise ValueError("typed problem and plan required")
    policy = evaluate_plan_policy(problem, plan)
    observation = evaluate_local_budget(budget, sample)
    reasons = set(policy.reason_codes) | set(observation.reason_codes)
    if policy.disposition != "PURE_SYNTHETIC_PREVIEW_ONLY":
        reasons.add("PLAN_POLICY_DENIED")
    # A declared ceiling is NOT a runtime benchmark; requiring it within
    # bounds is deliberately conservative until exact local profiling.
    if (plan.budget[0] > budget.max_steps
            or plan.budget[1] * 1000 > budget.max_elapsed_ms):
        reasons.add("DECLARED_PLAN_BUDGET_EXCEEDS_CPU_POLICY")
    return LocalPlanPreflight(
        "PURE_SYNTHETIC_PLAN_PREFLIGHT_ONLY" if not reasons
        else "HOLD_PLAN_RESOURCE_PREFLIGHT",
        policy.plan_sha256, tuple(sorted(reasons)))


def observe_plan_resource_preflight(
    problem: object, plan: object, budget: LocalResourceBudget,
    *, elapsed_ms: int, steps_completed: int,
) -> LocalPlanPreflight:
    rss = observe_own_process_rss_bytes()
    sample = LocalResourceSample(
        rss, elapsed_ms, steps_completed,
        source="PROCESS_RSS_LOCAL" if rss is not None else "CALLER_UNVERIFIED")
    return inspect_plan_resource_preflight(problem, plan, budget, sample)


def observe_and_evaluate_local_budget(
    budget: LocalResourceBudget, *, elapsed_ms: int, steps_completed: int,
    running_tasks: int = 1, cancelled: bool = False,
    cold_start_ms: int | None = None,
) -> LocalBudgetDecision:
    rss = observe_own_process_rss_bytes()
    return evaluate_local_budget(budget, LocalResourceSample(
        rss, elapsed_ms, steps_completed, running_tasks, cancelled,
        cold_start_ms, "PROCESS_RSS_LOCAL" if rss is not None
        else "CALLER_UNVERIFIED"))


# EAI-SWU-032: current-process RSS and elapsed time, postflight decision gate.
def review_local_journey_postflight(
    budget: LocalResourceBudget, *, elapsed_ms: int,
    cancelled: bool = False, steps_completed: int = 0,
) -> LocalBudgetDecision:
    """Observe actual own-process RSS; caller cannot substitute fake samples."""
    if type(cancelled) is not bool:
        raise ValueError("typed cancellation required")
    return observe_and_evaluate_local_budget(
        budget, elapsed_ms=elapsed_ms, steps_completed=steps_completed,
        running_tasks=1, cancelled=cancelled)
