# Unified knowledge engine

Kajamite owns knowledge operations and their reusable consistency rules.
Python, CLI, and MCP consumers use the same engine.
The MCP frontend is optional.

## Responsibilities

| Component | Responsibility |
| --- | --- |
| Knowledge engine | Capture, lifecycle transitions, expected revisions, current readback, eligibility, and change receipts. |
| Backend adapter | Public storage operations, indexing, observation search, and graph discovery. |
| Consumer | Source access, authorization, evidence checks, domain policy, and editorial judgment. |
| Frontend | Argument transport and result presentation. |

The engine does not certify truth.
A supported claim still needs a current evidence check before ordinary reuse.
Source inaccessibility differs from source change.
A request can exclude a current record because its scope does not match.

## Knowledge representation

Plain notes remain ordinary Markdown with caller-defined kinds and metadata.
A preference can record a user report without independent verification.
A proposal remains a proposal. Arbitrary status metadata cannot establish verified support.

Governed claims carry a versioned record in reserved `kajamite_record` metadata.
The note body presents the current claim. New writes store `journal-v1` metadata:
`format`, `type`, `schema_version`, the SHA-256 of the normalized current body,
and ordered events. Each event retains its identity, action, time, actor, reason,
and status transition. Its `changes` contain the top-level snapshot fields that
changed since the previous event; the first event contains a complete snapshot.
A claim equal to the current body uses `{"from_body": true}`. An observation
statement equal to its snapshot claim uses `{"from_claim": true}`. Other values,
including source and evidence fields, remain unchanged. Decoding restores complete
event snapshots and the current projection, then validates the full record.
Legacy complete-record metadata remains readable and is written as `journal-v1`
on its next transition. Record results retain the complete record contract.
Readers before version 0.7 cannot read journal metadata. Upgrade all readers of
a shared store before enabling writes from this version. Retain a store backup
before rollout; reverting the package alone does not revert written notes.
The separate `kajamite_operations` replay metadata keeps its existing format.
Backend title, type, and permalink metadata remain outside that record.
The engine normalizes line endings and accepts only the existing optional single
newline body framing when checking the body hash. It preserves claim whitespace
and rejects a body that does not match the hash.
A malformed record or conflicting external edit requires inspection and repair.

Generic note edits cannot replace reserved engine metadata or bypass lifecycle transitions.
Inspection can expose history to an authorized consumer.
Ordinary reuse excludes historical snapshots and unsuitable claims.

## Consistency

An expected revision protects against stale cooperating writers.
A shared backend lock covers comparison, write, and readback.
Basic Memory does not expose an atomic revision-compare operation.
Direct backend tools and human edits remain outside the cooperating lock.

Operation identity supports safe replay of committed transitions.
A repeated identity with different arguments is a conflict.
A transport failure does not prove that a write failed.
After an uncertain result, inspect current state before another write.

A successful receipt identifies the committed revision and readback evidence.
A content-free summary alone never proves persistence.
An index can lag behind committed Markdown.
Search and deletion results must report projection limitations honestly.

For ordinary-note multi-passage revision, the expected revision is the
lowercase SHA-256 of the complete current UTF-8 body, named
`expected_content_sha256`. It matches the complete-body hashes already used in
change receipts, not a paged content preview or metadata. The revision operation
does not mutate metadata, so metadata is outside that particular precondition.
It validates all exact selections against one original body, rejects ambiguity or
overlap before a write, and copies unselected bytes unchanged. Preview repeats
the same calculation without mutation; application always rechecks the hash.
Generic revision cannot bypass governed-record lifecycle rules.
For a governed record, `knowledge_record_transition` with `action="revise"`
accepts either a complete `changes.claim` or `changes.replacements`, never both.
The replacements use the same one-to-100 exact, unique, disjoint selection rules
against the current complete claim body. The expected record revision, body and
history checks, operation identity, and cooperating-writer lock still apply.
Without fresh verification, a revised claim becomes `needs_revalidation`.
The original transition request determines replay identity.

## Retrieval

Namespace scope controls retrieval, not authorization.
Consumers supply authorization independently.
Native search results and graph neighbors are candidates.
The engine checks current knowledge before returning governed content.

Observation categories and typed relations come from Basic Memory.
Graph expansion uses physical paths and explicit namespace bounds.
Relation labels alone do not establish evidence dependencies.
Context limits apply after candidate selection, with explicit omissions.

Text search retains bounded native pagination.
Semantic and hybrid modes require explicit backend configuration.
A ranked candidate set cannot prove that no relevant knowledge exists.

Collection inspection is an explicit, live, bounded namespace scan. Its cursor
is scoped to the selected namespace, recursion setting, and page size; results identify the
notes actually read and their complete-body hashes, continuation, and omissions.
Only an exhausted scan is complete for that invocation. Exact equal bodies are
candidates for caller review, not automatic consolidation; the engine makes no
semantic-overlap claim and no cross-note atomicity guarantee.

## Dependency boundary

The engine depends on the standard library and an injected backend object.
The Basic Memory adapter uses the MCP SDK as a client dependency.
The optional MCP frontend uses that SDK to expose the engine as a server.
An embedded application needs no Kajamite server or ambient session scope.

Source evidence and policy belong to the consumer.
The package contains no provider credentials, model, scheduler, or telemetry exporter.

## Embedded MCP frontend

`kajamite.server.create_server(engine, name="Example", version="1", instructions="...")`
returns an MCP server with the complete knowledge tool catalog, receipt UI, guide,
and text fallback. Add application tools with the returned server's `tool` decorator.
The optional `wrap_operation(name, callable)` hook wraps each knowledge operation.
Use `functools.wraps` to retain its argument schema. A host can add context parameters
with an explicit callable signature when needed by the MCP SDK.
The wrapped callable translates deliberate engine errors to MCP tool errors.
Return receipt fields at the top level when adding host receipt IDs or other metadata.
Preserve error status; an uncertain mutation must not become a success receipt.
Compatible presentation updates come from the installed Kajamite package.
The frontend requires the `mcp` extra; engine-only imports remain dependency-free.

Reuse checks source evidence for actual premises, including transitive premises.
Each premise is checked once per reuse decision. Ordinary note links are not premises.
A failed premise check withholds the dependent with a `dependency_` reason.
Inaccessible evidence does not alter the stored claim or its history; inspection
remains available and must not be presented as freshly verified reuse.

## Body edits through Basic Memory

Governed inspection includes complete history by default. Use
`read(identifier, mode="inspect", include_history=False)` for current-state
inspection without event snapshots. The result marks `history_included: false`.
The engine validates the complete stored history before returning either view.
Compact inspection is not a portable record export and does not establish reuse
eligibility. Ordinary reads and governed reuse retain their existing results.

Basic Memory's native text replacement searches the whole Markdown file, including
frontmatter. The adapter reads the full Markdown and qualifies the replacement with
the closing frontmatter delimiter and complete current body. Claim text repeated in
record history therefore remains unchanged. Generic note edits use the same path.
This costs one additional read before a body edit. The existing mutation lock and
post-write readback remain in effect; unrelated writers still require reconciliation.
