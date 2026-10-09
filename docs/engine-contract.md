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
on its next transition. Record results retain the complete record contract by default.
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
For a changed body supplied through replacements, the receipt preserves those
passages in the existing grouped-replacement shape. The backend write remains
atomic, and the receipt retains governed metadata changes and readback identity.
Supplying a complete claim produces grouped changed-line passages in the
existing receipt shape. Each passage includes one preceding line of context
when available. Long changed lines omit shared text around the edit while
retaining the full passage length and hash and marking the preview truncated.
For claims over 500 lines on either side, the receipt uses the bounded
whole-body preview. Broad replacements can still truncate at 2,000 characters.
This passage extraction applies only to governed complete-claim revisions.
Replacement previews may include `changed_ranges`: ordered, non-overlapping
`[start, end]` Unicode code-point offsets into that exact preview, with an
exclusive end. Word, punctuation, and whitespace comparison preserves retained
phrases across reflow without copying the prose again. Matching is limited to
1,000 tokens per side; larger comparisons omit the ranges and use broad-span
highlighting. The ranges describe preview text, not omitted note content.
Receipt identities include a display title when available. Governed topics use
a leading level-one Markdown heading from their current body; topics without
that heading retain the stored title. Reads, searches, lists, and context bundles
use the same display label. Ordinary notes keep their explicit backend title.
Display titles do not rename files, change record IDs, or become aliases for
subsequent operations. No additional title metadata is persisted.
Primary record-change rows omit verification timestamps, evidence observation
times, and observation statements that mirror their respective before/after
claims. Complete values remain in raw record metadata and history. Source
reference changes, evidence additions/removals, independent observation text,
and changed support bindings remain reviewable. A source-reference update does
not by itself establish that source behavior changed. Audit-only saves remain
explicit in both single-note and batch summaries.
One changed observation statement can also mirror a claim passage: both passages
must be unique, including overlapping occurrences, and replacing the old passage
must reproduce the complete new claim exactly. Its duplicate support notice is
omitted, while changed bindings remain visible. Ambiguous passages, independent
statements, unchanged-body reassignment, and multiple changed statements retain
the support notice. Stored observations and complete raw record metadata are
unchanged; only the semantic projection and its summary change.
The plain-text fallback uses these semantic rows when present instead of printing
the complete journal again. It retains passage hashes, coverage, saved record
state, and committed revision. Full structured records and receipt metadata stay
unchanged; legacy receipts without semantic rows retain their metadata fallback.
The replacements use the same one-to-100 exact, unique, disjoint selection rules
against the current complete claim body. The expected record revision, body and
history checks, operation identity, and cooperating-writer lock still apply.
Without fresh verification, a revised claim becomes `needs_revalidation`.
The original transition request determines replay identity.
A revision mismatch rejects the attempted transition before a write. Its error
reports the expected and observed revisions with `mutation_outcome=not_started`.
This signal describes the rejected attempt; another writer can have changed the
record. Read the current record before rebuilding the transition. Unknown errors
and uncertain mutations retain their conservative outcome handling.
For observations deliberately maintained as whole-claim mirrors, a revision can
set `mirror_observations` to their existing IDs. Supply a claim or replacements,
and do not also supply observations. Every selected statement must equal the
current complete claim. The engine resolves the selection inside the revision
lock and updates those statements with the revised claim in the same write.
Unselected statements and all evidence bindings remain unchanged. Equal text
alone never selects an observation. Missing, duplicate, or nonmatching selections
reject the revision. Normal verification and replay requirements still apply.
Revision input accepts claim, replacements, scope, observations, evidence,
verification, depends_on, and mirror_observations. Unsupported fields and incomplete supplied
verification objects are rejected before authorization or backend access.
Supplied observations must be a non-empty list of objects with observation_id,
statement, and evidence_ids. Missing fields identify the list index without
echoing submitted values. Missing verification fields are reported together. These checks do not infer
verification values or weaken revision, timestamp, evidence, or replay checks.
For supersession, changes can contain successor_identifier and successor_revision.
The engine authorizes and reads that stored record under the same mutation lock,
checks its revision and namespace, and applies the existing support, scope, and
acyclic-dependency requirements. The complete successor object remains supported
for compatibility. Compact references avoid copying a second record and its history.
A rejected reference leaves the original unchanged. Replays resolve by the original
request fingerprint before checking the successor again.

## Compact mutation results

Record creation and transitions accept `include_history=false` to omit only
`record.events` from the returned projection and set `history_included=false`.
The current claim, evidence, scope, verification, status, and committed revision
remain present. The complete operation receipt, its raw audit metadata, and its
plain-text rendering remain unchanged. This reduces response duplication; it
changes neither stored history nor the receipt's audit coverage.
The compact record is a current projection, not a portable complete record.
Use `knowledge_read(identifier, mode="inspect")` for validated full history.
A later read can include subsequent revisions; compare its revision with the
mutation's `committed_revision` before treating it as that same snapshot.
The Boolean option is validated before mutation and is not part of replay
identity. Switching the response view on a retry never authorizes another write.
Default responses and conflict, uncertain-write, and readback checks are unchanged.

## Retrieval

Namespace scope controls retrieval, not authorization.
Consumers supply authorization independently.
Native search results and graph neighbors are candidates.
The engine checks current knowledge before returning governed content.

Observation categories and typed relations come from Basic Memory.
Graph expansion uses physical paths and explicit namespace bounds.
Related reads include the starting note and can follow incoming links.
Discovery follows at most five native primary pages, deduplicating note paths.
The result remains partial when page, note, or related-result limits are reached.
Continuation errors propagate; an incomplete read is not reported as complete.
Use the root namespace only when the task permits context across the base.
Narrower namespace filters can exclude linked topics; the result reports their
count and marks the bundle partial without broadening the request.
Relation labels alone do not establish evidence dependencies.
Context limits apply after candidate selection, with explicit omissions.

Text search retains bounded native pagination.
Semantic and hybrid modes require explicit backend configuration.
A ranked candidate set cannot prove that no relevant knowledge exists.

Collection inspection is an explicit, live, bounded namespace scan. Its cursor
is scoped to the selected namespace, recursion setting, and page size; results identify the
notes actually read and their complete-body hashes, continuation, and omissions.
Changed native totals require recovery after traversal ends. The cursor then
restarts at the first page. Callers deduplicate
repeated identities. Exhaustion with `partial=true` or `index_changed=true`
does not establish completeness. Exact equal bodies are
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

Hosts can use the optional `kajamite-mutation-summary/1` presentation format without
changing the engine's default results. The structured summary contains `ok=true`,
`readback_verified=true`, `operation`, `receipt_id`, `identifier`,
`committed_revision`, `record_status`, `replayed`, `change_summary`, and
`audit.sha256`. Partial or failed operations do not qualify for this format.
The complete original result, with top-level receipt fields, travels as a JSON
string in MCP `_meta.audit_snapshot`. Its exact UTF-8 bytes produce `audit.sha256`;
the UI hashes that string before parsing it, so no cross-language JSON
canonicalization is required. The digest checks consistency, not producer identity.

The UI also matches operation identity, committed/record/receipt revisions, saved
status, replay state, and readback identity. Matching metadata restores ordinary
change review and raw audit disclosure. Missing, malformed, altered, or mismatched
metadata leaves an explicit summary-only view that preserves the reported completed
outcome. `audit.available=false` means server readback is unavailable; forwarded
metadata can still support review. An unavailable audit never means a write should
be repeated. Hosts must separately qualify model delivery, retention, access control,
and client metadata forwarding. Default tool responses remain unchanged.

Governed create and transition receipts include optional `record_changes` derived
from validated before/after records. Scope and verification changes have individual
field entries; status and dependency changes retain their values. Evidence and
observation summaries name added, removed, and updated IDs. Zero-count groups
are omitted. Each group shows at most three whole IDs within a bounded label
budget and states how many additional IDs are omitted. Evidence rechecks that
change only observation times remain secondary. Proven prose mirrors do not add
duplicate support notices, and unchanged observations are not named as updated.
Complete values remain in
`metadata_changes` and raw receipt disclosure. The UI replaces the full record row
only when this projection is present; older receipts retain their metadata view.

Governed creation receipts also carry `record_claim_sha256`, the UTF-8 SHA-256 of
the validated claim returned with the operation. This digest is separate from the
stored Markdown body's digest, which can include backend framing. The UI offers
the complete captured claim only when its digest, note identifier, and committed
revision match a readback-verified creation receipt. This is the operation snapshot,
not a fresh read of the current note. Older or mismatched results retain the bounded
excerpt and its truncation notice; no extra note read or duplicate claim is added.
This projection describes a saved operation, not current source freshness.

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
eligibility. In context and related bundles, inspect mode returns Markdown claim
text with current status, scope, verification, and evidence beside it. Only body
characters consume max_chars; history and repeated observations are excluded.
Inspection bundles mark reuse_checked=false and do not grant current eligibility.
Plain notes remain unreviewed in mixed bundles. Use an explicit inspect read for
the complete record and history. Truncated governed inspection previews do not
provide a paging cursor: read with mode="inspect", include_history=False for the
complete current claim. Ordinary reads and governed reuse retain their existing results.

Basic Memory's native text replacement searches the whole Markdown file, including
frontmatter. The adapter reads the full Markdown and qualifies the replacement with
the closing frontmatter delimiter and complete current body. Claim text repeated in
record history therefore remains unchanged. Generic note edits use the same path.
This costs one additional read before a body edit. The existing mutation lock and
post-write readback remain in effect; unrelated writers still require reconciliation.

Evidence replacement in `record_transition(action="revise")` uses an object keyed
by evidence ID. Existing observation references must remain present, or the same
revision must update observations to reference the replacement IDs. Review observation
statements for consistency with the revised claim; valid references alone do not
establish semantic support. Invalid shapes
and dangling observation references return actionable errors before any write;
errors do not expose the record's identifiers or evidence values.

New governed creation requires a bare `record_id` without a `.md` suffix. Directory
segments belong in `namespace`; the backend supplies the Markdown extension.
Filename-shaped IDs fail before backend access. Existing records with such IDs
remain readable and can still receive lifecycle transitions; no IDs are rewritten.

An existing governed ID found during creation preflight raises `KnowledgeError`
with `mutation_outcome="not_started"`. No note write is attempted on this path.
The MCP adapter preserves this marker on translated errors for embedding wrappers
and emits it in structured standalone tool errors alongside the unchanged text.
Other failures retain their existing semantics; explicit mutation uncertainty
takes precedence.
