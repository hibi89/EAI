"""C16 read-only prior/batch replay detection; NO training permissions."""
from dataclasses import replace
import unittest

from eai.contracts import ProblemSpec
from eai.candidate_evidence_review import CandidateEvidenceReview
from eai.episode_replay import EpisodeReplayDecision
from eai.episode_replay_dedup import screen_episodes_for_manual_review
from eai.logic_synthesis import SynthesisCandidate


class EpisodeReplayDedupTests(unittest.TestCase):
    def setUp(self):
        self.problem = ProblemSpec.validate({
            "version": 1, "id": "synthetic.episode",
            "goal": "PRIVATE", "domain": "data",
            "state_refs": [], "assumptions": [],
            "hard_constraints": [], "objectives": ["safety"],
            "oracle": "synthetic", "permissions": ["local.read"],
            "budget": {"max_steps": 4, "max_seconds": 20}, "risk": "LOW",
        })
        self.candidate = SynthesisCandidate(
            self.problem.digest(), ("a" * 64, "b" * 64),
            2, 10, "c" * 64)
        self.evidence = CandidateEvidenceReview(
            "SYNTHETIC_REVIEW_ONLY_NOT_AUTHORIZED",
            self.problem.digest(), self.candidate.candidate_sha256,
            "e" * 64, "f" * 64, (), ())
        self.episode = EpisodeReplayDecision(
            "data.review", "1" * 64, "a" * 64, "PROCEDURAL",
            "SUPPORTED_UNVERIFIED", "REPLAYED_UNVERIFIED_FOR_MANUAL_REVIEW")

    def screen(self, episodes=None, **overrides):
        return screen_episodes_for_manual_review(
            self.problem, self.candidate,
            (self.episode,) if episodes is None else episodes,
            self.evidence, **overrides)

    def test_supported_observation_is_only_manual(self):
        result = self.screen()
        self.assertEqual(result.status, "SYNTHETIC_EPISODE_MANUAL_REVIEW_ONLY")
        self.assertEqual(len(result.reviewed_fingerprints), 1)
        self.assertFalse(result.admits_training)
        self.assertFalse(result.grants_execution)

    def test_duplicate_same_batch_is_quarantined(self):
        result = self.screen((self.episode, self.episode))
        self.assertIn("DUPLICATE_OR_REPLAYED_EPISODE", result.reasons)
        self.assertEqual(result.status, "HOLD_UNTRUSTED_OR_REPLAYED_EPISODES")

    def test_prior_batch_fingerprint_is_not_admitted_again(self):
        fingerprint = self.screen().reviewed_fingerprints[0]
        result = self.screen(prior_fingerprints=(fingerprint,))
        self.assertIn("DUPLICATE_OR_REPLAYED_EPISODE", result.reasons)
        self.assertEqual(result.reviewed_fingerprints, ())

    def test_negative_or_stale_episode_cannot_be_success(self):
        for invalid in (
            replace(self.episode, evidence_state="STALE_UNVERIFIED"),
            replace(self.episode, disposition="HOLD_CONTRADICTED_EVIDENCE"),
            replace(self.episode, source_node_sha256="d" * 64),
            replace(self.episode, automated_learning_allowed=True),
        ):
            with self.subTest(invalid=invalid):
                result = self.screen((invalid,))
                self.assertIn("NEGATIVE_OR_UNSUPPORTED_EPISODE", result.reasons)
                self.assertFalse(result.admits_training)

    def test_unrelated_or_forged_candidate_evidence_denied(self):
        altered = replace(self.evidence, permits_learning=True)
        result = screen_episodes_for_manual_review(
            self.problem, self.candidate, (self.episode,), altered)
        self.assertEqual(result.reviewed_fingerprints, ())
        self.assertIn("UNTRUSTED_OR_UNRELATED_SYNTHETIC_REVIEW", result.reasons)

    def test_rejected_batch_exposes_no_accepted_subset(self):
        another = replace(self.episode, memory_sha256="2" * 64)
        result = self.screen((self.episode, another, self.episode))
        self.assertIn("DUPLICATE_OR_REPLAYED_EPISODE", result.reasons)
        self.assertEqual(result.reviewed_fingerprints, ())

    def test_duplicate_prior_index_rejected_as_untrusted(self):
        old = self.screen().reviewed_fingerprints[0]
        with self.assertRaises(ValueError):
            self.screen(prior_fingerprints=(old, old))


if __name__ == "__main__":
    unittest.main()
