"""Independent, bounded C14/C16 evidence binding.

A caller-provided receipt is untrusted. Re-run the independent verifier against
the exact problem, AXNODE chain and synthetic fixture family before review.
Neither matching digests nor a successful CPU comparison grant learning,
execution, VERIFIED or ACTIVE rights.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import io
import re

from .axnode_store import AXNodeStore
from .contracts import ProblemSpec, canonical_bytes, canonical_sha256, strict_json
from .logic_oracle import SyntheticComparison, _records
from .logic_synthesis import SynthesisCandidate
from .logic_verifier import StructuralVerifier
from .solver_reference_check import _expected
from .synthetic_candidate_interpreter import (
    SyntheticCandidateExecution, interpret_synthetic_candidate,
)
from .synthetic_candidate_verifier import (
    SyntheticCandidateReceipt, verify_synthetic_interpretation,
)

LOCAL_RECONCILIATION_SCOPE = "local.csv.keyed_numeric.v1"
_ID = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_NONCE = re.compile(r"[a-zA-Z0-9_-]{16,64}\Z")
_REVIEW_TTL = 300
_POLICY_TTL = 7 * 24 * 60 * 60
_POLICY_LIMIT = 32 * 1024
_ENVELOPE_LIMIT = 64 * 1024


def _is_digest(value: object) -> bool:
    return type(value) is str and _HASH.fullmatch(value) is not None


def _is_identifier(value: object) -> bool:
    return type(value) is str and _ID.fullmatch(value) is not None


def _ed25519_failure(public_key: bytes, document: bytes, signature: bytes) -> str | None:
    if (type(public_key) is not bytes or len(public_key) != 32
            or type(signature) is not bytes or len(signature) != 64):
        return "HOLD_INVALID_DETACHED_SIGNATURE"
    try:
        from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return "HOLD_CRYPTOGRAPHIC_VERIFIER_NOT_INSTALLED"
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, document)
    except (InvalidSignature, UnsupportedAlgorithm, ValueError):
        return "HOLD_INVALID_DETACHED_SIGNATURE"
    return None


def _detached_binding(
    key_sha256: str, envelope: bytes, signature: bytes, nonce: str,
) -> tuple[str, str]:
    return (
        canonical_sha256({
            "schema": "eai.candidate.detached.binding.v1",
            "key_sha256": key_sha256,
            "envelope_sha256": hashlib.sha256(envelope).hexdigest(),
            "signature_sha256": hashlib.sha256(signature).hexdigest(),
        }),
        canonical_sha256({
            "schema": "eai.candidate.detached.nonce.v1",
            "key_sha256": key_sha256,
            "nonce": nonce,
        }),
    )


def _signed_document(document: bytes, max_bytes: int, fields: set[str]) -> dict:
    if type(document) is not bytes or not 1 <= len(document) <= max_bytes:
        raise ValueError("bounded signed document required")
    raw = strict_json(document, max_bytes=max_bytes)
    if set(raw) != fields or canonical_bytes(raw) != document:
        raise ValueError("unexpected fields or non-canonical signed document")
    return raw


def _valid_window(issued: object, expires: object, limit: int) -> bool:
    return (type(issued) is int and type(expires) is int
            and 0 < issued < expires <= issued + limit)


@dataclass(frozen=True)
class _OwnerVerifierPolicy:
    revision: int
    sha256: str
    issued_at: int
    expires_at: int
    problem_sha256: str
    case_manifest_sha256: str
    baseline_sha256: str
    producers: tuple[tuple[str, str], ...]
    reviewers: tuple[tuple[str, bytes], ...]
    revoked_key_sha256: frozenset[str]

    @property
    def reviewer_key_hashes(self) -> frozenset[str]:
        return frozenset(hashlib.sha256(key).hexdigest() for _, key in self.reviewers)


def _verify_owner_policy(
    document: bytes, signature: bytes, owner_key: bytes, journal_id: str,
) -> _OwnerVerifierPolicy:
    """Policy revision is authenticated with the journal host's pinned owner key."""
    raw = _signed_document(document, _POLICY_LIMIT, {
        "schema", "journal_id", "scope", "purpose", "revision", "issued_at",
        "expires_at", "problem_sha256", "case_manifest_sha256", "baseline_sha256",
        "producers", "reviewers", "revoked_key_sha256",
    })
    if (raw["schema"] != "eai.owner.verifier.policy.v1"
            or raw["journal_id"] != journal_id
            or raw["scope"] != LOCAL_RECONCILIATION_SCOPE
            or raw["purpose"] != "LOCAL_ADVISORY_LEARNING"
            or type(raw["revision"]) is not int or not 1 <= raw["revision"] <= 256
            or not _valid_window(raw["issued_at"], raw["expires_at"], _POLICY_TTL)
            or not _is_digest(raw["problem_sha256"])
            or not _is_digest(raw["case_manifest_sha256"])):
        raise PermissionError("owner policy does not authorize this journal and scope")
    producers, reviewers, revoked = (
        raw["producers"], raw["reviewers"], raw["revoked_key_sha256"])
    if (type(producers) is not dict or not 2 <= len(producers) <= 4
            or any(not _is_digest(digest) or not _is_identifier(name)
                   for digest, name in producers.items())
            or not _is_digest(raw["baseline_sha256"])
            or raw["baseline_sha256"] not in producers
            or type(reviewers) is not dict or len(reviewers) > 8
            or type(revoked) is not list or len(revoked) > 256
            or any(not _is_digest(key) for key in revoked)
            or len(set(revoked)) != len(revoked)):
        raise ValueError("invalid owner reviewer or candidate inventory")
    if _ed25519_failure(owner_key, document, signature) is not None:
        raise PermissionError("missing or invalid owner policy signature")
    keys = []
    for name, encoded in reviewers.items():
        if (not _is_identifier(name) or name in producers.values()
                or not _is_digest(encoded)):
            raise PermissionError("reviewer must be distinct from candidate producers")
        key = bytes.fromhex(encoded)
        if key == owner_key or hashlib.sha256(key).hexdigest() in revoked:
            raise PermissionError("owner key or revoked reviewer key cannot review")
        keys.append((name, key))
    if len({key for _, key in keys}) != len(keys):
        raise PermissionError("reviewer key cannot be shared across identities")
    return _OwnerVerifierPolicy(
        raw["revision"], hashlib.sha256(document).hexdigest(),
        raw["issued_at"], raw["expires_at"], raw["problem_sha256"],
        raw["case_manifest_sha256"], raw["baseline_sha256"],
        tuple(sorted(producers.items())), tuple(sorted(keys)), frozenset(revoked))


@dataclass(frozen=True)
class CandidateEvidenceReview:
    status: str
    problem_sha256: str
    candidate_sha256: str
    fixture_sha256: str
    review_sha256: str
    reason_codes: tuple[str, ...]
    counterexample_families: tuple[str, ...]
    permits_promotion: bool = False
    permits_learning: bool = False
    permits_real_execution: bool = False


def review_candidate_evidence(
    store: AXNodeStore, problem: ProblemSpec,
    candidate: SynthesisCandidate, fixtures: tuple[SyntheticComparison, ...],
    execution: SyntheticCandidateExecution, claimed: SyntheticCandidateReceipt,
) -> CandidateEvidenceReview:
    """Recompute from source inputs. Never trust an externally supplied receipt."""
    if (type(store) is not AXNodeStore or type(problem) is not ProblemSpec
            or type(candidate) is not SynthesisCandidate
            or type(fixtures) is not tuple or not 2 <= len(fixtures) <= 12
            or type(execution) is not SyntheticCandidateExecution
            or type(claimed) is not SyntheticCandidateReceipt):
        raise ValueError("explicit bounded typed evidence required")
    # The independent verifier validates family uniqueness, exact candidate
    # structure, witness hashes and the disposable legacy CPU comparison.
    checked = verify_synthetic_interpretation(
        store, problem, candidate, fixtures, execution)
    family_payload = []
    for item in fixtures:
        if type(item) is not SyntheticComparison:
            raise ValueError("untrusted fixture type")
        family_payload.append([
            item.family, [list(row) for row in item.left],
            [list(row) for row in item.right], list(item.claimed_different),
        ])
    fixture_sha = hashlib.sha256(canonical_bytes({
        "schema": "eai.synthetic.fixture.binding.v1",
        "families": family_payload,
    })).hexdigest()
    reasons = []
    # The receipt's "executed" flag is not proof of actual interpreter use.
    # Execute the bounded candidate again on the same fixtures, rather than
    # accepting a claimant-created witness as execution provenance.
    replayed_witness_sha = None
    try:
        replay = interpret_synthetic_candidate(store, problem, candidate, fixtures)
        replayed_witness_sha = replay.witness_sha256
        if replay != execution:
            reasons.append("EXECUTION_WITNESS_NOT_REPRODUCIBLE")
    except (ValueError, KeyError):
        reasons.append("INDEPENDENT_SYNTHETIC_REPLAY_REJECTED")
    if claimed != checked:
        reasons.append("CLAIMED_RECEIPT_DIFFERS_FROM_INDEPENDENT_RECOMPUTATION")
    if (claimed.real_world_verified or claimed.permits_promotion
            or claimed.permits_learning):
        reasons.append("FORGED_RECEIPT_AUTHORITY")
    if (execution.real_world_verified or execution.permits_promotion
            or execution.permits_external_action):
        reasons.append("FORGED_EXECUTION_AUTHORITY")
    if checked.status != "SYNTHETIC_CANDIDATE_CPU_MATCH_UNVERIFIED":
        reasons.append("INDEPENDENT_CPU_OR_STRUCTURE_DID_NOT_MATCH")
    if not checked.independent_cpu_executed or not checked.interpretation_executed:
        reasons.append("REQUIRED_EXECUTION_EVIDENCE_MISSING")
    if len(checked.checked_families) != len(fixtures):
        reasons.append("INCOMPLETE_HELDOUT_FAMILY_COVERAGE")
    if checked.counterexample_families:
        reasons.append("COUNTEREXAMPLE_PRESENT")
    status = ("SYNTHETIC_REVIEW_ONLY_NOT_AUTHORIZED" if not reasons
              else "QUARANTINE_UNTRUSTED_SYNTHETIC_RECEIPT")
    reasons = tuple(sorted(set(reasons)))
    payload = {
        "schema": "eai.candidate.evidence.review.v1",
        "problem_sha256": problem.digest(),
        "candidate_sha256": candidate.candidate_sha256,
        "nodes": list(candidate.node_hashes),
        "fixture_sha256": fixture_sha,
        "witness_sha256": execution.witness_sha256,
        "replayed_witness_sha256": replayed_witness_sha,
        "independent_status": checked.status,
        "checked_families": list(checked.checked_families),
        "counterexamples": list(checked.counterexample_families),
        "disposition": status,
        "reasons": list(reasons),
    }
    review_sha = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    return CandidateEvidenceReview(
        status, problem.digest(), candidate.candidate_sha256,
        fixture_sha, review_sha, reasons, checked.counterexample_families)


# EAI-SWU-020: external receipt is untrusted until local independent replay.
@dataclass(frozen=True)
class CandidateReceiptIntake:
    status: str
    candidate_sha256: str
    independent_review_sha256: str
    journal_entry_sha256: str | None
    reason_codes: tuple[str, ...]
    source_authenticated: bool = False
    verified_real_world: bool = False
    permits_learning: bool = False
    permits_execution: bool = False
    permits_promotion: bool = False
    detached_binding_sha256: str | None = None


def intake_candidate_receipt_for_review(
    store: AXNodeStore, problem: ProblemSpec, candidate: SynthesisCandidate,
    fixtures: tuple[SyntheticComparison, ...],
    execution: SyntheticCandidateExecution, claimed: SyntheticCandidateReceipt,
    journal, *, record_locally: bool = False,
    detached_envelope: bytes | None = None,
    detached_signature: bytes | None = None,
    pinned_public_key: bytes | None = None,
    pinned_key_sha256: str | None = None,
) -> CandidateReceiptIntake:
    """Recompute candidate effects, then optionally write only a quarantine log.

    A SHA and a caller-supplied receipt never authenticate the claim's sender.
    This API deliberately cannot assert an external verifier's authority.
    """
    from .candidate_review_journal import CandidateReviewJournal
    if (type(store) is not AXNodeStore or type(journal) is not CandidateReviewJournal or
            type(record_locally) is not bool):
        raise ValueError("typed existing isolated journal and explicit option required")
    if journal.path.is_relative_to(store.root) or (
            journal.path.is_symlink()
            or not journal.path.is_file()):
        raise ValueError("review journal must not be stored in live AXNODE root")
    review = review_candidate_evidence(
        store, problem, candidate, fixtures, execution, claimed)
    if review.status not in (
            "SYNTHETIC_REVIEW_ONLY_NOT_AUTHORIZED",
            "QUARANTINE_UNTRUSTED_SYNTHETIC_RECEIPT"):
        raise ValueError("unexpected independent CPU review status")
    if review.permits_promotion or review.permits_learning or review.permits_real_execution:
        raise PermissionError("untrusted receipt cannot authorize actions")
    state = ("REVIEW_HOLD" if
             review.status == "SYNTHETIC_REVIEW_ONLY_NOT_AUTHORIZED"
             else "QUARANTINED")
    # Signed payloads require all four independent parameters. Never
    # downgrade a failed signature to an unsigned successful journal write.
    supplied = (detached_envelope, detached_signature,
                pinned_public_key, pinned_key_sha256)
    detached = None
    if any(value is not None for value in supplied):
        if any(value is None for value in supplied):
            raise ValueError("partial detached signature inputs rejected")
        detached = verify_detached_candidate_signature(
            review, detached_envelope, detached_signature,
            pinned_public_key=pinned_public_key,
            trusted_public_key_sha256=pinned_key_sha256)
        if detached.status != (
                "DETACHED_SIGNATURE_MATCHES_PIN_UNVERIFIED_INDEPENDENCE"):
            return CandidateReceiptIntake(
                "HOLD_UNAUTHENTICATED_DETACHED_REVIEW",
                candidate.candidate_sha256, review.review_sha256,
                None, (detached.status, "NO_INDEPENDENT_SEMANTIC_PROOF"))
        if record_locally and not journal.supports_detached_bindings:
            return CandidateReceiptIntake(
                "HOLD_SIGNED_REVIEW_REQUIRES_NEW_JOURNAL",
                candidate.candidate_sha256, review.review_sha256,
                None, ("LEGACY_JOURNAL_HAS_NO_DETACHED_BINDING",))
    written = None
    if record_locally:
        binding = detached.binding_sha256 if detached else None
        nonce = detached.nonce_sha256 if detached else None
        written = journal.record(review, state=state,
                                 detached_binding_sha256=binding,
                                 detached_nonce_sha256=nonce)
        # Read back this event, even if another writer has appended after it.
        if (journal.entry_at(written.sequence) != written
                or written.evidence_sha256 != review.review_sha256
                or written.candidate_sha256 != candidate.candidate_sha256
                or written.state != state
                or written.detached_binding_sha256 != binding
                or written.detached_nonce_sha256 != nonce):
            raise ValueError("review journal write/readback diverged")
    reason = ("INDEPENDENT_EXTERNAL_ORACLE_UNAVAILABLE",)
    if detached:
        reason += ("REVIEWER_INDEPENDENCE_NOT_PROVEN",)
    return CandidateReceiptIntake(
        "LOCAL_SYNTHETIC_REVIEW_JOURNALLED_NOT_VERIFIED" if written else
        "HOLD_RECORD_REQUIRES_EXPLICIT_OPT_IN",
        candidate.candidate_sha256, review.review_sha256,
        written.entry_sha256 if written else None,
        tuple(sorted(set(review.reason_codes) | set(reason))),
        detached_binding_sha256=detached.binding_sha256 if detached else None)


# EAI-SWU-020: detached signing can prove possession of a pinned verifier key,
# but never prove the verifier's independence, the test's truth or owner GO.
@dataclass(frozen=True)
class DetachedCandidateSignatureReview:
    status: str
    candidate_sha256: str
    evidence_review_sha256: str
    verifier_id: str
    signature_sha256: str
    signer_key_sha256: str
    independently_verified_real_world: bool = False
    trusted_for_training: bool = False
    permits_active_promotion: bool = False
    grants_real_player_execution: bool = False
    binding_sha256: str | None = None
    nonce_sha256: str | None = None


def verify_detached_candidate_signature(
    review: CandidateEvidenceReview, envelope: bytes, signature: bytes,
    *, pinned_public_key: bytes, trusted_public_key_sha256: str,
) -> DetachedCandidateSignatureReview:
    """Fail-closed ED25519 verification against a separately pinned key.

    Caller-selected or self-signed keys are not a configured trust authority.
    A valid signature only binds bounded, canonical, local review metadata.
    Proof of reviewer independence and semantic correctness remains external.
    """
    from hashlib import sha256
    if (type(review) is not CandidateEvidenceReview
            or type(envelope) is not bytes or not 1 <= len(envelope) <= 2048
            or type(signature) is not bytes or len(signature) != 64
            or type(pinned_public_key) is not bytes
            or len(pinned_public_key) != 32
            or not _is_digest(trusted_public_key_sha256)
            or sha256(pinned_public_key).hexdigest() != trusted_public_key_sha256):
        raise ValueError("independent externally pinned verifier input required")
    raw = strict_json(envelope, max_bytes=2048)
    if (type(raw) is not dict or set(raw) != {
            "schema", "candidate_sha256", "review_sha256",
            "fixture_sha256", "problem_sha256", "verifier_id",
            "disposition", "nonce"}
            or raw["schema"] != "eai.candidate.detached.review.v1"
            or raw["candidate_sha256"] != review.candidate_sha256
            or raw["review_sha256"] != review.review_sha256
            or raw["fixture_sha256"] != review.fixture_sha256
            or raw["problem_sha256"] != review.problem_sha256
            or raw["disposition"] != "REVIEW_METADATA_ONLY"
            or not _is_identifier(raw["verifier_id"])
            or type(raw["nonce"]) is not str
            or not _NONCE.fullmatch(raw["nonce"])
            or canonical_bytes(raw) != envelope):
        raise ValueError("detached review must bind canonical exact evidence")
    failure = _ed25519_failure(pinned_public_key, envelope, signature)
    if failure is not None:
        return DetachedCandidateSignatureReview(
            failure,
            review.candidate_sha256, review.review_sha256,
            raw["verifier_id"], sha256(signature).hexdigest(),
            trusted_public_key_sha256)
    signature_sha256 = sha256(signature).hexdigest()
    binding_sha256, nonce_sha256 = _detached_binding(
        trusted_public_key_sha256, envelope, signature, raw["nonce"])
    return DetachedCandidateSignatureReview(
        "DETACHED_SIGNATURE_MATCHES_PIN_UNVERIFIED_INDEPENDENCE",
        review.candidate_sha256, review.review_sha256,
        raw["verifier_id"], signature_sha256, trusted_public_key_sha256,
        binding_sha256=binding_sha256, nonce_sha256=nonce_sha256)


@dataclass(frozen=True)
class ReconciliationCase:
    """Owner-approved read-only CSV bytes, one case per scenario family.

    Columns are exactly key,value; keys are unique and values are bounded
    finite decimals. The oracle adjudicates reconciliation of these inputs.
    """

    family: str
    partition: str
    left_csv: bytes
    right_csv: bytes


@dataclass(frozen=True)
class SignedReconciliationReview:
    """Untrusted detached reviewer envelope and Ed25519 signature."""

    envelope: bytes
    signature: bytes


@dataclass(frozen=True)
class _ReconciliationTruth:
    family: str
    partition: str
    case_sha256: str
    semantic_case_sha256: str
    expected_output_sha256: str


@dataclass(frozen=True)
class _RecheckedOutcome:
    case: _ReconciliationTruth
    observed_output_sha256: str

@dataclass(frozen=True)
class _RecheckedCandidateReceipt:
    expires_at: int
    binding_sha256: str
    nonce_sha256: str
    outcomes: tuple[_RecheckedOutcome, ...]


def _csv_records(data: bytes) -> dict:
    if type(data) is not bytes or not 1 <= len(data) <= 4096 or b"\x00" in data:
        raise ValueError("bounded read-only CSV bytes required")
    try:
        reader = csv.reader(io.StringIO(data.decode("utf-8"), newline=""), strict=True)
        if next(reader, None) != ["key", "value"]:
            raise ValueError("unsupported reconciliation columns")
        return _records(tuple(tuple(row) for row in reader))
    except (UnicodeError, csv.Error) as exc:
        raise ValueError("malformed reconciliation source") from exc


def _normalized_source_sha256(records: dict) -> str:
    rows = []
    for key, value in sorted(records.items()):
        number = format(value, "f")
        if "." in number:
            number = number.rstrip("0").rstrip(".")
        rows.append([key, "0" if value == 0 else number])
    return canonical_sha256({"schema": "eai.csv.numeric.rows.v1", "rows": rows})


def _recompute_reconciliation_cases(
    cases: tuple[ReconciliationCase, ...],
) -> tuple[str, tuple[_ReconciliationTruth, ...]]:
    if (type(cases) is not tuple or not 4 <= len(cases) <= 8
            or any(type(case) is not ReconciliationCase
                   or not _is_identifier(case.family)
                   or type(case.partition) is not str
                   or case.partition not in ("TRAIN", "HELD_OUT")
                   for case in cases)
            or len({case.family for case in cases}) != len(cases)):
        raise ValueError("bounded, unique reconciliation families required")
    sources = {"TRAIN": set(), "HELD_OUT": set()}
    counts_by_partition = dict.fromkeys(sources, 0)
    semantic_cases, truths = set(), []
    for case in sorted(cases, key=lambda entry: entry.family):
        left, right = _csv_records(case.left_csv), _csv_records(case.right_csv)
        if case.left_csv == case.right_csv:
            raise ValueError("identical source bytes are outside the verified scope")
        sides = sorted((_normalized_source_sha256(left), _normalized_source_sha256(right)))
        semantic_sha = canonical_sha256({
            "schema": "eai.csv.keyed_numeric.case.values.v1", "source_sha256": sides})
        if semantic_sha in semantic_cases:
            raise ValueError("duplicate reconciliation content")
        semantic_cases.add(semantic_sha)
        sources[case.partition].update(sides)
        counts_by_partition[case.partition] += 1
        case_sha = canonical_sha256({
            "schema": "eai.csv.keyed_numeric.case.v1",
            "family": case.family,
            "partition": case.partition,
            "left_sha256": hashlib.sha256(case.left_csv).hexdigest(),
            "right_sha256": hashlib.sha256(case.right_csv).hexdigest(),
        })
        # Existing independently implemented Decimal reference, with no call
        # to the claimant, candidate operator, or synthetic parity runner.
        status, counts, differences = _expected(left, right)
        output_sha = canonical_sha256({
            "status": status, "counts": counts,
            "differences": [list(item) for item in differences],
        })
        truths.append(_ReconciliationTruth(
            case.family, case.partition, case_sha, semantic_sha, output_sha))
    if (min(counts_by_partition.values()) < 2
            or sources["TRAIN"] & sources["HELD_OUT"]):
        raise ValueError("independent train and held-out source families required")
    manifest = canonical_sha256({
        "schema": "eai.csv.keyed_numeric.case_manifest.v1",
        "case_sha256": [item.case_sha256 for item in truths],
    })
    return manifest, tuple(truths)


def reconciliation_case_manifest_sha256(cases: tuple[ReconciliationCase, ...]) -> str:
    """Compute the exact ordered-source and partition binding for owner review."""
    digest, _ = _recompute_reconciliation_cases(cases)
    return digest


def _check_supported_reconciliation_candidate(
    store: AXNodeStore, problem: ProblemSpec, candidate: SynthesisCandidate, reviewer_id: str,
) -> None:
    if (problem.risk != "LOW" or problem.version != 1 or problem.domain != "data"
            or problem.oracle != LOCAL_RECONCILIATION_SCOPE
            or problem.assumptions or problem.state_refs or problem.hard_constraints
            or "accuracy" not in problem.objectives
            or not set(problem.objectives) <= {"accuracy", "operator_count"}
            or "local.read" not in problem.permissions
            or not set(problem.permissions) <= {"local.read", "pure"}
            or StructuralVerifier(store).check(problem, candidate).status
            != "STRUCTURE_ONLY_UNVERIFIED"):
        raise PermissionError("unsupported reconciliation problem or composition")
    for index, digest in enumerate(candidate.node_hashes):
        node = store.get(digest).as_dict()
        if node["provenance"]["author"].lower() == reviewer_id:
            raise PermissionError("candidate author cannot be its independent verifier")
        types = set(node["signature"]["inputs"].values())
        expected = {"csv_ref", "difference_receipt"} if index else {"csv_ref"}
        if (types != expected
                or node["signature"]["output"] != "difference_receipt"
                or node["steps"] != [{"skill": "csv.reconcile.v1"}]
                or node["pre"] or node["post"]):
            raise PermissionError("unsupported reconciliation node semantics")


_COUNT_KEYS = {"agree", "different", "left_only", "right_only", "non_numeric"}


def _checked_observation_sha256(output: object) -> str:
    if type(output) is not dict or set(output) != {"status", "counts", "differences"}:
        raise ValueError("exact reconciliation output required")
    counts, differences = output["counts"], output["differences"]
    if (output["status"] not in ("AGREE", "CONFLICT")
            or type(counts) is not dict or set(counts) != _COUNT_KEYS
            or any(type(count) is not int or not 0 <= count <= 48
                   for count in counts.values())
            or type(differences) is not list or len(differences) > 48
            or any(type(row) is not list or len(row) != 2
                   or row[0] not in ("DIFFERENT", "LEFT_ONLY", "RIGHT_ONLY")
                   or not _is_identifier(row[1]) for row in differences)):
        raise ValueError("unproven or unsupported reconciliation output")
    return canonical_sha256(output)


def _recheck_signed_reconciliation(
    store: AXNodeStore, problem: ProblemSpec,
    candidate: SynthesisCandidate, truths: tuple[_ReconciliationTruth, ...],
    review: SignedReconciliationReview, policy: _OwnerVerifierPolicy, now: int,
) -> _RecheckedCandidateReceipt:
    raw = _signed_document(review.envelope, _ENVELOPE_LIMIT, {
        "schema", "scope", "policy_sha256", "problem_sha256", "candidate_sha256",
        "case_manifest_sha256", "verifier_id", "nonce", "issued_at", "expires_at",
        "outputs",
    })
    if (raw["schema"] != "eai.candidate.detached.reconciliation.v1"
            or raw["scope"] != LOCAL_RECONCILIATION_SCOPE
            or raw["policy_sha256"] != policy.sha256
            or raw["problem_sha256"] != policy.problem_sha256
            or raw["candidate_sha256"] != candidate.candidate_sha256
            or raw["case_manifest_sha256"] != policy.case_manifest_sha256
            or not _is_identifier(raw["verifier_id"])
            or type(raw["nonce"]) is not str or not _NONCE.fullmatch(raw["nonce"])
            or not _valid_window(raw["issued_at"], raw["expires_at"], _REVIEW_TTL)
            or not policy.issued_at <= raw["issued_at"] <= now
            < raw["expires_at"] <= policy.expires_at):
        raise PermissionError("stale or incorrectly bound reviewer envelope")
    key = dict(policy.reviewers).get(raw["verifier_id"])
    if key is None or _ed25519_failure(key, review.envelope, review.signature) is not None:
        raise PermissionError("missing, revoked or unauthenticated independent verifier")
    _check_supported_reconciliation_candidate(store, problem, candidate, raw["verifier_id"])
    outputs = raw["outputs"]
    if type(outputs) is not dict or set(outputs) != {case.family for case in truths}:
        raise ValueError("every signed case must have an outcome")
    outcomes = tuple(_RecheckedOutcome(case, _checked_observation_sha256(outputs[case.family]))
                     for case in truths)
    binding, nonce = _detached_binding(
        hashlib.sha256(key).hexdigest(), review.envelope, review.signature, raw["nonce"])
    return _RecheckedCandidateReceipt(raw["expires_at"], binding, nonce, outcomes)
