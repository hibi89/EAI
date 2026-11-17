"""Isolated append-only candidate reviews and owner-governed verifier policy."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import secrets
import sqlite3
from time import time

from .candidate_evidence_review import (
    CandidateEvidenceReview, _OwnerVerifierPolicy, _verify_owner_policy,
)
from .contracts import canonical_bytes, canonical_sha256, strict_json
from .episode_replay_fence import (
    _fingerprint_digest, _reserve_verified_fingerprints, _verified_fingerprint_digests,
)

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_STATES = frozenset({"REVIEW_HOLD", "QUARANTINED", "WITHDRAWN_FROM_REVIEW"})
_VERIFIED_STATE = "LOCAL_OUTCOME_REVIEWED"
_ENTRY_LIMIT = 10000


@dataclass(frozen=True)
class JournalEntry:
    sequence: int
    candidate_sha256: str
    evidence_sha256: str
    state: str
    previous_active_sha256: str | None
    previous_entry_sha256: str
    entry_sha256: str
    permits_promotion: bool = False
    changes_active_node: bool = False
    detached_binding_sha256: str | None = None
    detached_nonce_sha256: str | None = None
    verified_fingerprints_sha256: str | None = None
    owner_policy_sha256: str | None = None
    review_expires_at: int | None = None


@dataclass(frozen=True)
class _VerifiedJournalRecord:
    candidate_sha256: str
    evidence_sha256: str
    binding_sha256: str
    nonce_sha256: str
    fingerprints: tuple[str, ...]
    expires_at: int


@dataclass(frozen=True)
class VerifiedAdvisorySelection:
    selection_sha256: str
    policy_sha256: str
    candidate_sha256: str | None
    fallback_sha256: str | None
    valid_until: int
    journal_entry_sha256: tuple[str, ...]
    preceding_selection_sha256: str | None = None


def _digest(value: str) -> str:
    if type(value) is not str or not _HASH.fullmatch(value):
        raise ValueError("invalid journal hash")
    return value


def _entry_hash(seq: int, candidate: str, evidence: str, state: str,
                active: str | None, previous: str,
                detached_binding: str | None = None,
                detached_nonce: str | None = None,
                verified_fingerprints: str | None = None,
                owner_policy: str | None = None,
                expires_at: int | None = None) -> str:
    payload = {
        "schema": "eai.candidate.review.entry.v1",
        "sequence": seq, "candidate_sha256": candidate,
        "evidence_sha256": evidence, "state": state,
        "previous_active_sha256": active,
        "previous_entry_sha256": previous,
    }
    if detached_binding is not None:
        payload.update(schema="eai.candidate.review.entry.v2",
                       detached_binding_sha256=detached_binding,
                       detached_nonce_sha256=detached_nonce)
    if verified_fingerprints is not None:
        payload.update(schema="eai.candidate.review.entry.v3",
                       verified_fingerprints_sha256=verified_fingerprints,
                       owner_policy_sha256=owner_policy, review_expires_at=expires_at)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


class CandidateReviewJournal:
    """Owner mode requires a fresh journal and a host-pinned owner Ed25519 key.

    The trusted host supplies the same isolated, access-controlled path and
    out-of-band root key on every open. This protects against input/receipt
    forgery. The host must protect the journal, SQLite sidecars and clock
    against replacement, including restore from an older filesystem snapshot.
    No policy, root key or journal path is obtained from a candidate request.
    """

    def __init__(self, path: str | Path, *, create: bool = False,
                 owner_public_key: bytes | None = None):
        if type(create) is not bool:
            raise ValueError("explicit journal creation flag required")
        if owner_public_key is not None and (
                type(owner_public_key) is not bytes or len(owner_public_key) != 32):
            raise ValueError("32-byte host-pinned Ed25519 owner key required")
        path = Path(path).expanduser()
        if (path.is_symlink() or not path.parent.is_dir()
                or path.parent.is_symlink()
                or (path.exists() and (not path.is_file() or create))
                or (not path.exists() and not create)):
            raise ValueError("safe explicit review journal path required")
        self.path = path.resolve(strict=False)
        self._owner_key = owner_public_key
        self._owner_journal_id: str | None = None
        if create:
            # Exclusive creation closes the time-of-check/time-of-use overwrite
            # window: SQLite's ordinary connect can otherwise follow a new link.
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        self.db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=3)
        try:
            self.db.execute("PRAGMA busy_timeout=3000")
            self.db.execute("PRAGMA trusted_schema=OFF")
            self.db.execute("PRAGMA foreign_keys=ON")
            if owner_public_key is not None:
                self.db.execute("PRAGMA synchronous=FULL")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if create:
                if version != 0:
                    raise ValueError("journal already initialized")
                self.db.execute("PRAGMA journal_mode=WAL")
                self.db.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE entries (
                        sequence INTEGER PRIMARY KEY,
                        candidate_sha256 TEXT NOT NULL,
                        evidence_sha256 TEXT NOT NULL,
                        state TEXT NOT NULL,
                        previous_active_sha256 TEXT,
                        previous_entry_sha256 TEXT NOT NULL,
                        entry_sha256 TEXT NOT NULL UNIQUE,
                        detached_binding_sha256 TEXT,
                        detached_nonce_sha256 TEXT UNIQUE,
                        CHECK ((detached_binding_sha256 IS NULL) =
                               (detached_nonce_sha256 IS NULL))
                    );
                    PRAGMA user_version=2;
                """)
                version = 2
                if owner_public_key is not None:
                    self._create_owner_tables(owner_public_key)
                    version = 3
                self.db.commit()
                os.chmod(self.path, 0o600)
            elif version not in (1, 2, 3):
                raise ValueError("unknown journal version")
            self._version = version
            columns = {row[1] for row in self.db.execute("PRAGMA table_info(entries)")}
            expected = {
                "sequence", "candidate_sha256", "evidence_sha256", "state",
                "previous_active_sha256", "previous_entry_sha256", "entry_sha256",
            }
            if self.supports_detached_bindings:
                expected.update({"detached_binding_sha256", "detached_nonce_sha256"})
            if version == 3:
                expected.update({"verified_fingerprints_sha256", "owner_policy_sha256",
                                 "review_expires_at"})
                self._open_owner_tables()
            elif owner_public_key is not None:
                raise PermissionError("owner mode requires a new dedicated journal")
            if columns != expected or self.db.execute(
                    "PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("unsafe journal schema/integrity")
            self.verify_chain()
        except Exception:
            self.db.close()
            raise

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "CandidateReviewJournal":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @property
    def supports_detached_bindings(self) -> bool:
        return self._version >= 2

    @property
    def owner_journal_id(self) -> str | None:
        """Identity to put in independently signed owner policy documents."""
        return self._owner_journal_id

    def _create_owner_tables(self, owner_key: bytes) -> None:
        # Execute in the same transaction as creation of the base journal.
        self.db.execute("ALTER TABLE entries ADD COLUMN verified_fingerprints_sha256 TEXT")
        self.db.execute("ALTER TABLE entries ADD COLUMN owner_policy_sha256 TEXT")
        self.db.execute("ALTER TABLE entries ADD COLUMN review_expires_at INTEGER")
        self.db.execute(
            "CREATE TABLE owner_anchor (single INTEGER PRIMARY KEY CHECK(single=1),"
            "journal_id TEXT NOT NULL, key_sha256 TEXT NOT NULL, last_seen INTEGER NOT NULL,"
            "policy_revision INTEGER NOT NULL)")
        self.db.execute(
            "CREATE TABLE owner_policy (revision INTEGER PRIMARY KEY,"
            "document BLOB NOT NULL, signature BLOB NOT NULL)")
        self.db.execute(
            "CREATE TABLE verified_replays (fingerprint TEXT PRIMARY KEY,"
            "sequence INTEGER NOT NULL REFERENCES entries(sequence))")
        self.db.execute(
            "CREATE TABLE verified_selections ("
            "policy_revision INTEGER NOT NULL REFERENCES owner_policy(revision),"
            "generation INTEGER NOT NULL CHECK(generation IN (1,2)),"
            "document BLOB NOT NULL, selection_sha256 TEXT NOT NULL UNIQUE,"
            "PRIMARY KEY(policy_revision,generation))")
        self.db.execute(
            "INSERT INTO owner_anchor VALUES (1,?,?,0,0)",
            (secrets.token_hex(32), hashlib.sha256(owner_key).hexdigest()))
        self.db.execute("PRAGMA user_version=3")

    def _open_owner_tables(self) -> None:
        if self._owner_key is None:
            raise PermissionError("out-of-band owner key required for this journal")
        anchors = self.db.execute(
            "SELECT single,journal_id,key_sha256,last_seen FROM owner_anchor LIMIT 2"
        ).fetchall()
        if (len(anchors) != 1 or anchors[0][0] != 1
                or anchors[0][2] != hashlib.sha256(self._owner_key).hexdigest()
                or type(anchors[0][3]) is not int or anchors[0][3] < 0):
            raise PermissionError("journal owner anchor mismatch")
        self._owner_journal_id = _digest(anchors[0][1])
        self._stored_owner_policy()

    def _stored_owner_policy(self) -> _OwnerVerifierPolicy | None:
        row = self.db.execute(
            "SELECT p.revision,p.document,p.signature,a.policy_revision,"
            "(SELECT count(*) FROM owner_policy) "
            "FROM owner_anchor AS a LEFT JOIN owner_policy AS p "
            "ON p.revision=a.policy_revision WHERE a.single=1",
        ).fetchone()
        if row is None:
            raise ValueError("owner journal policy anchor missing")
        revision, document, signature, high_water, count = row
        if high_water == count == 0 and revision is None:
            return None
        if type(high_water) is not int or revision != high_water or revision != count:
            raise ValueError("owner policy revision history diverged")
        policy = _verify_owner_policy(
            document, signature, self._owner_key, self._owner_journal_id)
        if revision != policy.revision:
            raise ValueError("owner policy revision history diverged")
        return policy

    def _observe_owner_clock(self) -> int:
        now = int(time())
        clock = self.db.execute(
            "SELECT last_seen FROM owner_anchor WHERE single=1").fetchone()
        if (clock is None or type(clock[0]) is not int or now <= 0
                or now < clock[0]):
            raise PermissionError("owner journal clock moved backwards")
        self.db.execute("UPDATE owner_anchor SET last_seen=? WHERE single=1", (now,))
        return now

    def install_owner_policy(self, document: bytes, signature: bytes) -> str:
        """Append an owner-signed scope and reviewer enrollment/revocation snapshot.

        Revisions start at one and advance by one. A removed key must be
        explicitly and permanently revoked. An expired policy cannot be used
        for admission but can be replaced with the next signed revision.
        """
        if self._owner_journal_id is None or self.db.in_transaction:
            raise PermissionError("dedicated owner journal required")
        policy = _verify_owner_policy(
            document, signature, self._owner_key, self._owner_journal_id)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            now = self._observe_owner_clock()
            previous = self._stored_owner_policy()
            revision = 1 if previous is None else previous.revision + 1
            if policy.revision != revision or not policy.issued_at <= now < policy.expires_at:
                raise PermissionError("stale or out-of-order owner policy revision")
            if previous is not None:
                removed = previous.reviewer_key_hashes - policy.reviewer_key_hashes
                known_names = {key: name for name, key in previous.reviewers}
                if (policy.issued_at < previous.issued_at
                        or not (previous.revoked_key_sha256 | removed)
                        <= policy.revoked_key_sha256
                        or any(key in known_names and name != known_names[key]
                               for name, key in policy.reviewers)):
                    raise PermissionError("owner policy cannot revive revoked reviewer authority")
            self.db.execute("INSERT INTO owner_policy VALUES (?,?,?)",
                            (revision, document, signature))
            self.db.execute("UPDATE owner_anchor SET policy_revision=? WHERE single=1",
                            (revision,))
        return policy.sha256

    @contextmanager
    def _owner_transaction(self):
        if self._owner_journal_id is None or self.db.in_transaction:
            raise PermissionError("dedicated owner journal required")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            now = self._observe_owner_clock()
            policy = self._stored_owner_policy()
            if policy is None or not policy.issued_at <= now < policy.expires_at:
                raise PermissionError("current signed owner approval required")
            yield policy, now
            if self._observe_owner_clock() >= policy.expires_at:
                raise PermissionError("owner approval expired during review")

    def entries(self) -> tuple[JournalEntry, ...]:
        detached_columns = ("detached_binding_sha256,detached_nonce_sha256"
                            if self.supports_detached_bindings else "NULL,NULL")
        owner_columns = ("verified_fingerprints_sha256,owner_policy_sha256,review_expires_at"
                         if self._version == 3 else "NULL,NULL,NULL")
        rows = self.db.execute(
            "SELECT sequence,candidate_sha256,evidence_sha256,state,"
            "previous_active_sha256,previous_entry_sha256,entry_sha256,"
            + detached_columns + "," + owner_columns + " FROM entries ORDER BY sequence LIMIT ?",
            (_ENTRY_LIMIT + 1,)
        ).fetchall()
        if len(rows) > _ENTRY_LIMIT:
            raise ValueError("bounded review journal exceeded")
        return tuple(JournalEntry(*row[:7], detached_binding_sha256=row[7],
                                  detached_nonce_sha256=row[8],
                                  verified_fingerprints_sha256=row[9],
                                  owner_policy_sha256=row[10], review_expires_at=row[11])
                     for row in rows)

    def _verified_entries(self) -> tuple[JournalEntry, ...]:
        if self._version == 3 and not self.db.in_transaction:
            # Journal entries and the replay index must share one read snapshot.
            with self.db:
                self.db.execute("BEGIN")
                return self._read_verified_entries()
        return self._read_verified_entries()

    def _read_verified_entries(self) -> tuple[JournalEntry, ...]:
        entries = self.entries()
        replay_digests = (_verified_fingerprint_digests(self.db)
                          if self._version == 3 else {})
        previous = "0" * 64
        nonces = set()
        for index, item in enumerate(entries, 1):
            binding, nonce = item.detached_binding_sha256, item.detached_nonce_sha256
            replay_sha = item.verified_fingerprints_sha256
            owner_policy, expires_at = item.owner_policy_sha256, item.review_expires_at
            if item.state == _VERIFIED_STATE:
                if (nonce is None or replay_sha is None or item.previous_active_sha256 is not None
                        or replay_digests.pop(index, None) != replay_sha
                        or type(expires_at) is not int or expires_at <= 0):
                    raise ValueError("verified episode replay fence integrity failure")
                _digest(owner_policy)
            elif item.state not in _STATES or (replay_sha, owner_policy, expires_at) != (
                    None, None, None):
                raise ValueError("invalid review journal state")
            if (binding is None) != (nonce is None):
                raise ValueError("incomplete detached journal binding")
            if nonce is not None:
                _digest(binding)
                if _digest(nonce) in nonces:
                    raise ValueError("replayed detached journal binding")
                nonces.add(nonce)
            if (item.sequence != index or item.previous_entry_sha256 != previous
                    or (item.previous_active_sha256 is not None
                        and not _HASH.fullmatch(item.previous_active_sha256))
                    or _digest(item.candidate_sha256) != item.candidate_sha256
                    or _digest(item.evidence_sha256) != item.evidence_sha256
                    or item.entry_sha256 != _entry_hash(
                        index, item.candidate_sha256, item.evidence_sha256,
                        item.state, item.previous_active_sha256, previous,
                        binding, nonce, replay_sha, owner_policy, expires_at)):
                raise ValueError("journal chain integrity failure")
            previous = item.entry_sha256
        if replay_digests:
            raise ValueError("orphaned verified episode replay rows")
        return entries

    def verify_chain(self) -> bool:
        self._verified_entries()
        return True

    def entry_at(self, sequence: int) -> JournalEntry | None:
        entries = self._verified_entries()
        return entries[sequence - 1] if 1 <= sequence <= len(entries) else None

    def latest_for(self, candidate_sha256: str) -> JournalEntry | None:
        """Read-only current review state; never a promotion decision."""
        _digest(candidate_sha256)
        for entry in reversed(self._verified_entries()):
            if entry.candidate_sha256 == candidate_sha256:
                return entry
        return None

    def record(self, review: CandidateEvidenceReview, *,
               state: str, previous_active_sha256: str | None = None,
               detached_binding_sha256: str | None = None,
               detached_nonce_sha256: str | None = None,
               ) -> JournalEntry:
        if type(review) is not CandidateEvidenceReview:
            raise ValueError("explicit untrusted review required")
        if (review.permits_promotion or review.permits_learning
                or review.permits_real_execution):
            raise ValueError("untrusted promotion or learning authority denied")
        if type(state) is not str or state not in _STATES:
            raise ValueError("only non-active review states supported")
        _digest(review.candidate_sha256)
        _digest(review.review_sha256)
        _digest(review.problem_sha256)
        _digest(review.fixture_sha256)
        if previous_active_sha256 is not None:
            _digest(previous_active_sha256)
        if (detached_binding_sha256 is None) != (detached_nonce_sha256 is None):
            raise ValueError("complete detached journal binding required")
        if detached_binding_sha256 is not None:
            if not self.supports_detached_bindings:
                raise ValueError("detached binding requires a new journal")
            _digest(detached_binding_sha256)
            _digest(detached_nonce_sha256)
        if state == "REVIEW_HOLD" and (
                review.status != "SYNTHETIC_REVIEW_ONLY_NOT_AUTHORIZED"
                or review.reason_codes):
            raise ValueError("untrusted review cannot return to hold")
        # A user may note an existing ACTIVE pointer, but this module cannot
        # change it. The pointer is audit metadata, never an authorization.
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            existing = self._verified_entries()
            return self._append_entry(
                existing, review.candidate_sha256, review.review_sha256, state,
                previous_active_sha256, detached_binding_sha256, detached_nonce_sha256)

    def _record_verified_batch(
        self, policy: _OwnerVerifierPolicy, records: tuple[_VerifiedJournalRecord, ...],
    ) -> tuple[JournalEntry, ...]:
        if self._version != 3 or not self.db.in_transaction:
            raise PermissionError("current owner transaction required")
        existing = self._verified_entries()
        written = []
        for record in records:
            entry = self._append_entry(
                existing, record.candidate_sha256, record.evidence_sha256,
                _VERIFIED_STATE, None, record.binding_sha256, record.nonce_sha256,
                _fingerprint_digest(record.fingerprints), policy.sha256, record.expires_at)
            _reserve_verified_fingerprints(self.db, entry.sequence, record.fingerprints)
            existing += (entry,)
            written.append(entry)
        if self._verified_entries() != existing:
            raise ValueError("verified review journal readback diverged")
        return tuple(written)

    def _write_selection(
        self, policy: _OwnerVerifierPolicy, *,
        candidate: str | None, fallback: str | None, valid_until: int,
        proofs: tuple[str, ...], previous: str | None = None,
    ) -> VerifiedAdvisorySelection:
        if self._version != 3 or not self.db.in_transaction:
            raise PermissionError("current owner transaction required")
        document = {
            "schema": "eai.local.verified.strategy.v1",
            "policy_sha256": policy.sha256,
            "candidate_sha256": candidate,
            "fallback_sha256": fallback,
            "valid_until": valid_until,
            "journal_entry_sha256": list(proofs),
            "preceding_selection_sha256": previous,
        }
        generation = 1 if previous is None else 2
        digest = canonical_sha256(document)
        self.db.execute("INSERT INTO verified_selections VALUES (?,?,?,?)",
                        (policy.revision, generation, canonical_bytes(document), digest))
        selection = self._read_selection(policy)
        if selection is None or selection.selection_sha256 != digest:
            raise ValueError("verified strategy selection readback diverged")
        return selection

    def _read_selection(self, policy: _OwnerVerifierPolicy) -> VerifiedAdvisorySelection | None:
        rows = self.db.execute(
            "SELECT generation,document,selection_sha256 FROM verified_selections "
            "WHERE policy_revision=? ORDER BY generation LIMIT 3",
            (policy.revision,),
        ).fetchall()
        if not rows:
            return None
        checked = self._verified_entries()
        entries = {entry.entry_sha256: entry for entry in checked}
        inventory = set(dict(policy.producers))
        selection = None
        for index, (generation, document, digest) in enumerate(rows, 1):
            raw = strict_json(document, max_bytes=2048)
            if (index != generation or index > 2 or canonical_bytes(raw) != document
                    or _digest(digest) != canonical_sha256(raw)
                    or set(raw) != {
                        "schema", "policy_sha256", "candidate_sha256", "fallback_sha256",
                        "valid_until", "journal_entry_sha256", "preceding_selection_sha256",
                    }
                    or raw["schema"] != "eai.local.verified.strategy.v1"
                    or raw["policy_sha256"] != policy.sha256
                    or type(raw["valid_until"]) is not int
                    or not policy.issued_at < raw["valid_until"] <= policy.expires_at):
                raise ValueError("invalid verified strategy history")
            candidate, fallback = raw["candidate_sha256"], raw["fallback_sha256"]
            proofs, previous = raw["journal_entry_sha256"], raw["preceding_selection_sha256"]
            if ((candidate is not None and _digest(candidate) not in inventory)
                    or fallback not in (None, policy.baseline_sha256)
                    or type(proofs) is not list or len(proofs) != len(inventory)
                    or any(_digest(proof) not in entries or entries[proof].state != _VERIFIED_STATE
                           or entries[proof].owner_policy_sha256 != policy.sha256
                           for proof in proofs)
                    or {entries[proof].candidate_sha256 for proof in proofs} != inventory):
                raise ValueError("verified strategy lacks exact candidate review chain")
            proof_entries = [entries[proof] for proof in proofs]
            first_sequence = proof_entries[0].sequence
            if (any(entry.sequence != first_sequence + offset
                    for offset, entry in enumerate(proof_entries))
                    or min(entry.review_expires_at for entry in proof_entries)
                    != raw["valid_until"]):
                raise ValueError("strategy proof entries must be from one admitted batch")
            if selection is None:
                if previous is not None:
                    raise ValueError("verified strategy history is missing prior selection")
            elif (previous != selection.selection_sha256
                    or candidate not in (None, selection.fallback_sha256)
                    or fallback != selection.fallback_sha256
                    or raw["valid_until"] != selection.valid_until
                    or tuple(proofs) != selection.journal_entry_sha256):
                raise ValueError("invalid advisory rollback parent")
            selection = VerifiedAdvisorySelection(
                digest, policy.sha256, candidate, fallback, raw["valid_until"],
                tuple(proofs), previous)
        return selection

    def _is_available_selection_candidate(self, candidate_sha256: str | None) -> bool:
        if candidate_sha256 is None:
            return True
        latest = self.latest_for(candidate_sha256)
        return latest is not None and latest.state not in ("QUARANTINED", "WITHDRAWN_FROM_REVIEW")

    def current_verified_selection(self) -> VerifiedAdvisorySelection | None:
        """Reopen a local advisory selection under the current signed policy."""
        with self._owner_transaction() as (policy, _):
            selection = self._read_selection(policy)
            if (selection is not None
                    and self._is_available_selection_candidate(selection.candidate_sha256)
                    and self._observe_owner_clock() < selection.valid_until):
                return selection
        return None

    def rollback_verified_selection(
        self, *, expected_selection_sha256: str,
    ) -> VerifiedAdvisorySelection:
        """Append a compare-and-swap rollback to the checked baseline or HOLD."""
        _digest(expected_selection_sha256)
        with self._owner_transaction() as (policy, now):
            current = self._read_selection(policy)
            if current is None or now >= current.valid_until:
                raise PermissionError("current verified advisory selection required")
            fallback = current.fallback_sha256
            if not self._is_available_selection_candidate(fallback):
                fallback = None
            if expected_selection_sha256 not in (
                    current.selection_sha256, current.preceding_selection_sha256):
                raise ValueError("verified strategy head changed")
            if current.preceding_selection_sha256 is not None:
                if (current.candidate_sha256 != fallback
                        or self._observe_owner_clock() >= current.valid_until):
                    raise PermissionError("advisory rollback is no longer usable")
                return current
            if current.candidate_sha256 == fallback:
                if self._observe_owner_clock() >= current.valid_until:
                    raise PermissionError("verified advisory selection expired during rollback")
                return current
            rolled_back = self._write_selection(
                policy, candidate=fallback,
                fallback=current.fallback_sha256, valid_until=current.valid_until,
                proofs=current.journal_entry_sha256, previous=current.selection_sha256)
            if self._observe_owner_clock() >= rolled_back.valid_until:
                raise PermissionError("verified advisory selection expired during rollback")
            return rolled_back

    def _append_entry(
        self, existing: tuple[JournalEntry, ...], candidate: str, evidence: str,
        state: str, active: str | None, binding: str | None, nonce: str | None,
        fingerprints: str | None = None, owner_policy: str | None = None,
        expires_at: int | None = None,
    ) -> JournalEntry:
        if len(existing) >= _ENTRY_LIMIT:
            raise ValueError("bounded review journal full")
        if nonce is not None and any(entry.detached_nonce_sha256 == nonce for entry in existing):
            raise ValueError("detached verifier nonce already journalled")
        latest = next((item for item in reversed(existing)
                       if item.candidate_sha256 == candidate), None)
        if latest is None and state == "WITHDRAWN_FROM_REVIEW":
            raise ValueError("candidate not previously reviewed")
        if latest is not None:
            if latest.previous_active_sha256 != active:
                raise ValueError("existing ACTIVE pointer evidence changed")
            if latest.state == "WITHDRAWN_FROM_REVIEW":
                raise ValueError("withdrawn review cannot be resurrected")
            if latest.state == "QUARANTINED" and state in ("REVIEW_HOLD", _VERIFIED_STATE):
                raise ValueError("quarantined review cannot self-reinstate")
            if latest.state == state and latest.evidence_sha256 == evidence:
                raise ValueError("duplicate journal event")
        index = len(existing) + 1
        previous = existing[-1].entry_sha256 if existing else "0" * 64
        digest = _entry_hash(index, candidate, evidence, state, active, previous,
                             binding, nonce, fingerprints, owner_policy, expires_at)
        values = (index, candidate, evidence, state, active, previous, digest)
        if self._version == 3:
            self.db.execute("INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                            (*values, binding, nonce, fingerprints, owner_policy, expires_at))
        elif self.supports_detached_bindings:
            self.db.execute("INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?)",
                            (*values, binding, nonce))
        else:
            self.db.execute("INSERT INTO entries VALUES(?,?,?,?,?,?,?)", values)
        return JournalEntry(*values, detached_binding_sha256=binding,
                            detached_nonce_sha256=nonce,
                            verified_fingerprints_sha256=fingerprints,
                            owner_policy_sha256=owner_policy, review_expires_at=expires_at)
