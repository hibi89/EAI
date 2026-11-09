# EAI P18 — independent read-only SQLite table audit

2026-11-10 KST. Seventh typed, CPU-owned goal: `sqlite_table_audit`.

## Alternatives and decision

A. Accept arbitrary owner-entered SQL under a SQLite read-only connection. Flexible, but arbitrary SQL and views introduce unpredictable access, resource and information-disclosure risk; separate postcondition verification is difficult.
B. Accept an exact, versioned table/rule contract: one selected **ordinary local SQLite table**; count missing required values and repeated single/composite keys; rescan with a separate column-first receipt guard. **Selected**: predictable cost, no SQL expressions from user input, no external API, integration with pinned P12 batch/P14 pipeline.

## Input contract

```json
{
  "version": 1,
  "kind": "sqlite_table_audit",
  "goal": "Review orders before processing",
  "source": "orders.sqlite3",
  "table": "orders",
  "required": ["order_id", "amount"],
  "unique_by": ["order_id"]
}
```

Save this JSON next to the explicitly owner-selected `orders.sqlite3`, then run:
`python -m eai solve-goal path/to/goal.json --json`

Statuses: `AGREE` exit 0 if nonempty and all rules hold; `CONFLICT` exit 2 if required fields are null/blank or a nonblank key repeats; `UNAVAILABLE` exit 3 if table has no rows. A schema/security/input failure is exit 1. These statuses are local quality checks, **not business correctness or database integrity_check**.

## Safety and resource boundary

- The source is a relative path contained inside its goal directory. Parent traversal, absolute path, drive notation and symlink escapes rejected. DB <=16 MiB, <=20,000 data records, <=32 ordinary columns, up to 8 required and 3 composite key columns.
- ASCII identifiers only; SQLite internal tables, views, virtual tables, generated/hidden columns and ambiguous column names rejected. Blank means SQL NULL or whitespace/empty string or BLOB; numeric zero is valid. Duplicate-key equality is Python's exact equality for SQLite-returned value types, not a claim of DB collation equivalence.
- Open SQLite by URI `mode=ro&immutable=1`, with `query_only=ON`, `trusted_schema=OFF`, a SELECT/one-table READ authorizer, and a bounded query/CPU progress callback. An existing `-wal` or `-journal` sidecar causes fail-closed rejection rather than silently ignoring recent changes. Running against an actively updated DB without sidecars cannot guarantee a transactionally consistent snapshot; take an owner-authorized frozen copy for production use.
- The engine reads one fixed `SELECT *` with deterministic all-column ordering, no user-provided SQL, no writes, and no network. A SHA-256 is checked before/after the primary scan and independently before/after the verification scan.
- Receipt includes source filename/hash, table and column names, row count, violation counts, affected record count and up to 10 **1-based ordered audit record indexes**. It never displays actual SQLite cell values, key values or source SQL. Record indexes are audit-order positions, not physical SQLite rowid values.
- P18's separate verifier reconstructs missing records column-first and duplicates using a Counter, compares exact receipt fields, and blocks forged/mismatched evidence. Existing P12 batch/P14 pipeline gate downstream goals after `CONFLICT`.
- P18 uses synthetic temporary SQLite files in dedicated unit/integration tests. P13 doctor continues to check its six committed text fixtures (10 checks); it does not yet exercise P18 on a Windows-owned DB. No checked-in real or binary customer database.

## Verification gates

At initial feature commit: **pending exact-source GitHub Actions**. Check `python -m compileall -q eai tests`, `python -m unittest discover -s tests -v`, `python -m eai doctor --json`, and a synthetic P18 CLI test. Record the verified code SHA and GitHub Actions run in `STATUS.md`/`HANDOFF.md` only after seeing the logs.

Unverified: customer database correctness, Windows native, Ollama/Qwen, SearXNG, installing/retail release. Production/Vercel not applicable. RELEASE HOLD.
