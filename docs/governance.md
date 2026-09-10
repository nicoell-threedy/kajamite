# Portable governed records

`RecordEngine` validates and transforms evidence-backed records. It does not
open files, connect to Basic Memory, run a model, or configure telemetry.

`KnowledgeEngine` uses this record validator for persistent operations.
Install `kajamite` for the engine. Install `kajamite[mcp]` for the optional MCP frontend.
The frontend's MCP dependency does not constrain an engine-only consumer.

## Create and review a record

This example runs with only the installed engine:

```python
from kajamite.governance import RecordEngine

engine = RecordEngine()
observed_at = "2026-01-01T00:00:00.000000Z"
record = engine.create_record(
    "service-port", "The example service uses port 8080.",
    {"system": "example", "version": "1"},
    [{"observation_id": "manual", "statement": "The manual specifies port 8080.",
      "evidence_ids": ["source"]}],
    {"source": {"kind": "document", "reference": "example:manual@1",
                "observed_at": observed_at}},
    {"record_revision": 1, "verified_at": observed_at, "verifier": "reviewer",
     "outcome": "supported", "evidence_ids": ["source"]},
    timestamp=observed_at, actor="reviewer", reason="Manual reviewed",
    event_id="created",
)
markdown = engine.serialize_record(record)
assert engine.parse_record(markdown) == record
changed = engine.apply_evidence_health(
    record, "changed", condition_id="manual-revision-2",
    timestamp="2026-01-01T00:00:01.000000Z", actor="source-checker",
    reason="The manual revision changed",
)
assert changed["record"]["status"] == "needs_revalidation"
assert changed["record"]["claim"] == record["claim"]
assert record["status"] == "supported"
```

The example declares synthetic evidence. It does not establish source validity.
`supported` records require a current source check before ordinary retrieval.

## Consumer contract

Each engine instance has an independent `record_type` and `permalink_prefix`.
These settings preserve a consumer's schema identity without global state.
The default type is `governed-record`; the default prefix is `records`.

An optional `evidence_validator` receives a defensive copy of each evidence map.
It must raise an exception for an invalid source-specific anchor. Validation
applies to current evidence and historical event snapshots. This callback checks
anchor structure. Current authorization and source access remain consumer work.

The default frontmatter decoder is `json.loads`. Serialized records contain
JSON frontmatter, which is also valid YAML. A consumer can provide a safe YAML
decoder when its backend normalizes frontmatter. Never use an unsafe YAML loader.

Verification references must cover observations and bind a valid record revision.
Evidence with `observed_at` cannot be newer than its semantic verification.
Events have strictly increasing timestamps and complete snapshots. Each lifecycle
action can change only its defined fields. Superseded and retracted records are
terminal. Deterministic source changes preserve claim meaning.

The standalone `RecordEngine` helper returns defensive copies without persistence.
`KnowledgeEngine` coordinates writes, expected revisions, dependency checks, and removal evidence.
A consumer that uses only the helper must supply those operations itself.
`compute_etag` supplies a hash; it does not perform a compare-and-swap transaction.

Generic note access must not bypass the consumer's governance boundary. The unified engine applies these protections to public note operations.
Using `RecordEngine` alone provides validation without persistence or retrieval policy.

## Telemetry

`change_summary(record)` returns action, prior and current status, record revision,
evidence count, and dependency count. It contains no claim, source reference,
record identifier, actor, or reason. It does not prove that persistence succeeded.

The consumer can attach these facts to its existing trace after persistence.
The engine creates no exporter, event store, or trace context. Serialized records
and normal change receipts contain knowledge and must not become telemetry.

## Persistent engine API

Create `KnowledgeEngine(backend, authorize=..., evidence_checker=...)` for persistence and retrieval.
Both callbacks can be synchronous or asynchronous.
`authorize(identifier, request_scope)` returns an explicit boolean before a selected note is read.
The default allows local access. The callback is consumer policy, not a namespace permission system.

`evidence_checker(record, request_scope)` returns `True` or an outcome object.
An outcome of `unchanged` allows source reuse.
Other outcomes include `changed`, `missing`, `removed`, `inaccessible`, and `unknown`.
A missing callback withholds supported claims. Callback errors produce an inaccessible-check result.
The engine checks record scope and lifecycle independently of the callback.

Dependency revisions bind to semantic verification.
A changed dependency revision withholds reuse before batch maintenance runs.
Maintenance persists the resulting review state without changing the claim.

Direct removal of all engine metadata can erase record identity.
The engine cannot authenticate history against deliberate replacement of the whole Markdown record.
Version control and consumer backup procedures remain necessary for that recovery case.
