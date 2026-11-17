"""EAI removable external research gate. Fail-closed, default fully local."""
from dataclasses import dataclass
from enum import Enum


class ResearchMode(str, Enum):
    OFF = "OFF"
    RESEARCH_OPT_IN = "RESEARCH_OPT_IN"


@dataclass(frozen=True)
class ResearchPolicy:
    mode: ResearchMode = ResearchMode.OFF
    free_only: bool = True
    paid_budget_usd: int = 0
    external_sends_approved: bool = False
    free_tier_verified: bool = False

    def __post_init__(self):
        if type(self.mode) is not ResearchMode:
            raise ValueError("unknown research mode")
        if (type(self.free_only) is not bool or not self.free_only or
                type(self.paid_budget_usd) is not int or self.paid_budget_usd != 0 or
                type(self.external_sends_approved) is not bool or
                type(self.free_tier_verified) is not bool):
            raise ValueError("EAI research cannot silently enable paid access")

    def allows_remote_proposal(self) -> bool:
        return (self.mode is ResearchMode.RESEARCH_OPT_IN
                and self.external_sends_approved and self.free_tier_verified)
