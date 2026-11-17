"""No synthetic CPU baseline or self-observation can self-authorize learning."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from eai.axnode_store import AXNodeStore
from eai.axnode_memory import AXNodeMemory
from eai.evidence_ledger import EvidenceLedger
from eai.contracts import ProblemSpec
from eai.logic_oracle import SyntheticComparison
from eai.logic_synthesis import LogicSynthesizer
from eai.solver_reference_check import review_candidate_with_cpu_baseline
from eai.episode_replay import replay_memory_evidence
from eai.experience_admission import inspect_learning_admission
from eai.candidate_evidence_review import CandidateEvidenceReview


class ExperienceAdmissionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)/"axnodes"
        self.store = AXNodeStore(self.root)
        self.addCleanup(self.store.close)
        self.a = self.store.import_node(json.dumps(self.node("data.first", [])))
        self.b = self.store.import_node(json.dumps(self.node("data.second", [self.a])))
        self.problem = ProblemSpec.validate({
            "version":1, "id":"synthetic.exp",
            "goal":"PRIVATE user goal must not leak", "domain":"data",
            "state_refs":[], "assumptions":[], "hard_constraints":[],
            "objectives":["safe_learning"],"oracle":"synthetic.oracle",
            "permissions":["local.read"],
            "budget":{"max_steps":5,"max_seconds":60}, "risk":"LOW",
        })
        self.candidate = LogicSynthesizer(self.store).compose(self.problem,
                                                              (self.a,self.b))
        self.fixtures = (
            SyntheticComparison("family.same",(("a","1.0"),),
                                (("a","1.00"),),()),
            SyntheticComparison("family.diff",(("a","1"),("b","2")),
                                (("a","5"),("c","2")),("a","b","c")),
        )
        self.audit = review_candidate_with_cpu_baseline(
            self.store,self.problem,self.candidate,self.fixtures)
        self.memory = AXNodeMemory(self.store)
        self.addCleanup(self.memory.close)
        self.memory.remember(tier="PROCEDURAL", anchor_sha=self.a,
                             label="data.review",captured_at=100,
                             outcome="SUCCESS_OBSERVED")
        self.evidence = EvidenceLedger(self.store,create=True)
        self.addCleanup(self.evidence.close)
        self.evidence.append(claim_id="data.review",source_sha256=self.a,
                             polarity="SUPPORT",observed_at=100,
                             expires_at=200,now=150)

    def replay(self, *, evidence=True):
        return replay_memory_evidence(
            self.memory,self.evidence if evidence else None,"data",now=150)

    def inspect(self, *, episodes=None, audit=None, candidate=None):
        return inspect_learning_admission(
            self.store,self.problem,
            self.candidate if candidate is None else candidate,
            self.audit if audit is None else audit,
            self.replay() if episodes is None else episodes)

    def test_good_synthetic_observation_only_enters_manual_review(self):
        r=self.inspect()
        self.assertEqual(r.disposition,"SYNTHETIC_REVIEW_ONLY_NOT_TRAINING")
        self.assertEqual(len(r.eligible_memory_hashes),1)
        self.assertFalse(r.eligible_for_learning)
        self.assertFalse(r.eligible_for_execution)
        self.assertFalse(r.candidate_semantically_verified)
        self.assertIn("ACTUAL_COMPOSED_CANDIDATE_INDEPENDENT_ORACLE_MISSING",
                      r.reason_codes)
        self.assertEqual(len(r.review_fingerprint),64)

    def test_absent_evidence_cannot_be_used_as_training_reward(self):
        r=self.inspect(episodes=self.replay(evidence=False))
        self.assertEqual(r.disposition,"HOLD_UNTRUSTED_OR_INCOMPLETE_EXPERIENCE")
        self.assertEqual(r.eligible_memory_hashes,())

    def test_refuted_observation_is_held(self):
        self.evidence.append(claim_id="data.review",source_sha256=self.b,
                             polarity="REFUTE",observed_at=110,
                             expires_at=200,now=150)
        r=self.inspect()
        self.assertEqual(r.disposition,"HOLD_UNTRUSTED_OR_INCOMPLETE_EXPERIENCE")
        self.assertIn("NEGATIVE_STALE_OR_UNSUPPORTED_EPISODE",r.reason_codes)

    def test_tampered_candidate_proof_hash_rejected(self):
        forged=replace(self.candidate,candidate_sha256="0"*64)
        r=self.inspect(candidate=forged)
        self.assertIn("CANDIDATE_STRUCTURE_NOT_REVERIFIED",r.reason_codes)
        self.assertIn("BASELINE_CANDIDATE_SHA_MISMATCH",r.reason_codes)
        self.assertFalse(r.eligible_for_learning)

    def test_forged_baseline_authority_is_denied(self):
        forged=replace(self.audit,composed_candidate_executed=True,
                       semantic_verified=True,permits_promotion=True)
        r=self.inspect(audit=forged)
        self.assertIn("UNTRUSTED_AUTHORITY_ASSERTED",r.reason_codes)
        self.assertFalse(r.eligible_for_learning)

    def test_forged_episode_authority_is_denied(self):
        episode=replace(self.replay()[0],automated_learning_allowed=True,
                        independent_verification="VERIFIED")
        r=self.inspect(episodes=(episode,))
        self.assertIn("FORGED_EPISODE_AUTHORITY",r.reason_codes)

    def test_duplicate_memory_reference_is_not_twice_training(self):
        episode=self.replay()[0]
        r=self.inspect(episodes=(episode,episode))
        self.assertIn("DUPLICATE_EPISODE_PROVENANCE",r.reason_codes)
        self.assertEqual(r.eligible_memory_hashes,())

    def test_record_from_other_node_cannot_credit_candidate(self):
        other=self.store.import_node(json.dumps(self.node("data.third",[])))
        self.memory.remember(tier="EPISODIC",anchor_sha=other,
                             label="data.review",captured_at=102)
        r=self.inspect()
        self.assertIn("EPISODE_NODE_OUTSIDE_CANDIDATE",r.reason_codes)

    def synthetic_review(self):
        return CandidateEvidenceReview(
            "SYNTHETIC_REVIEW_ONLY_NOT_AUTHORIZED",
            self.problem.digest(), self.candidate.candidate_sha256,
            "3" * 64, "4" * 64, (), ())

    def test_matching_candidate_review_is_still_manual_only(self):
        verified_synthetic = self.synthetic_review()
        result = inspect_learning_admission(
            self.store, self.problem, self.candidate, self.audit,
            self.replay(), candidate_review=verified_synthetic)
        self.assertEqual(result.disposition, "SYNTHETIC_REVIEW_ONLY_NOT_TRAINING")
        self.assertFalse(result.eligible_for_learning)
        self.assertFalse(result.candidate_semantically_verified)
        self.assertNotEqual(result.review_fingerprint, self.inspect().review_fingerprint)

    def test_cross_candidate_review_reuse_is_held(self):
        forged = replace(self.synthetic_review(), candidate_sha256="f" * 64)
        result = inspect_learning_admission(
            self.store, self.problem, self.candidate, self.audit,
            self.replay(), candidate_review=forged)
        self.assertEqual(result.disposition, "HOLD_UNTRUSTED_OR_INCOMPLETE_EXPERIENCE")
        self.assertIn("UNTRUSTED_OR_UNRELATED_CANDIDATE_REVIEW", result.reason_codes)

    def test_forged_synthetic_review_cannot_grant_training(self):
        forged = replace(self.synthetic_review(), permits_learning=True)
        result = inspect_learning_admission(
            self.store, self.problem, self.candidate, self.audit,
            self.replay(), candidate_review=forged)
        self.assertFalse(result.eligible_for_learning)
        self.assertIn("UNTRUSTED_OR_UNRELATED_CANDIDATE_REVIEW", result.reason_codes)

    def test_private_user_goal_is_never_persisted_or_rendered(self):
        r=self.inspect()
        self.assertNotIn("PRIVATE",str(r))
        self.assertEqual(r,self.inspect())

    @staticmethod
    def node(name,parents):
        return {
            "schema":"eai.axnode.v1","id":name,"version":1,
            "kind":"strategy","status":"CANDIDATE",
            "signature":{"inputs":{"source":"csv_ref",
                                   "prior":"difference_receipt"},
                         "output":"difference_receipt"},
            "pre":["authorized_only"],"post":["independent_check"],
            "steps":[{"skill":"csv.reconcile.v1"}],
            "capabilities":["local.read"],"parent_hashes":parents,
            "tests":{"unit":[],"heldout":[],"negative":[]},"evidence":[],
            "provenance":{"author":"eai_synthetic","source":"local_only"},
            "budget":{"max_steps":2,"max_seconds":20},
        }


if __name__=="__main__":
    unittest.main()
