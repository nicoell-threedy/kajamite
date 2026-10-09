# Namespaces and explicit knowledge access

All public note and record operations use `KnowledgeEngine`.
The [engine contract](engine-contract.md) defines persistence, eligibility, and consumer hooks.
`RecordEngine` validates portable records and lifecycle history inside that engine.
The MCP frontend is optional. The Basic Memory adapter uses a public MCP client.
The engine itself has no third-party runtime dependency.

Namespaces, notes, observations, and relations remain useful knowledge units.
Governed claims add explicit evidence, scope, revisions, and lifecycle transitions.
Plain notes retain caller-defined meaning and remain visibly unreviewed.

## Namespace semantics

A namespace is a canonical relative directory within the configured knowledge
base. Existing directories already qualify; first writes create missing parents.
Namespaces may nest. There is no registry, mandatory overview, membership field,
status enum, default project template, or current-namespace session state.

A note has one location. Links express relationships across locations; metadata
supplies caller-defined descriptions. A namespace is an organization/retrieval
scope, not an authorization boundary or a separate Basic Memory installation.
An optional overview is an ordinary note and never becomes executable policy.

Every scoped operation supplies its namespace explicitly. Recursive search is
opt-in. Path-segment boundaries distinguish a folder from similarly prefixed
siblings. Search scope uses file paths, not permalinks, because native moves may
preserve permalink identity. Return actual identifiers/paths for follow-up calls.
Namespace matching preserves canonical path case; use paths returned by listing
or mutation rather than guessing case or slugs. Bare ambiguous titles are not
accepted as note addresses. A directory-qualified wiki target may omit `.md` only
when the returned physical path matches that exact qualified stem.

## Search implementation

The engine now exposes observation/category filters and native graph discovery.
See the [versioned capability audit](basic-memory-capability-audit.md).
Every returned candidate passes current-note and eligibility checks.
Semantic/hybrid modes require explicit backend configuration.


The installed Basic Memory 0.23.0 public MCP tool lacks a directory search filter.
Text and permalink glob are alternative search modes; neither supports combining
text relevance with physical path filtering natively. This release uses a truthful
full-text scan fallback, keeping the backend and its index independently owned.

Native pages contain 50 entity results. At most five pages are visited per call.
The cursor records the next global result offset and a fingerprint of query/scope.
Within-page offsets prevent skipping extra matches when a requested result page
fills. A cursor from another query is rejected. Overlapping scopes never duplicate
notes. No HMAC or registry is needed: cursors do not grant access to other bases.

An empty result with has_more=true is inconclusive. next_cursor continues the
scan, and exhausted=true alone indicates the native stream is exhausted. There
is no invented scoped total or semantic-search claim. Filtering only the first
global top-k would miss relevant scoped notes; duplicating path membership into
metadata would drift under ordinary edits. Both approaches are rejected.

A future native path-filtered search before ranking/pagination can replace the
fallback without changing namespace meaning. The cost today is extra backend
pages for sparse scopes. Pagination is live and does not guarantee a stable
snapshot during concurrent changes.

When reported native totals change within a scan or its cursor continuation,
`index_changed=true` withholds `complete_scope_search` and marks engine search
and collection inspection partial. Exhaustion does not establish absence from
a changing index. Equal or
missing totals cannot prove stability. Legacy cursors have no earlier total to
compare. A changed total invalidates the offset. At the end of traversal,
`next_cursor` starts one recovery pass at the first native page, and `exhausted=false` keeps
traversal open. The cursor preserves this recovery requirement between calls.
Deferred recovery lets later pages progress during index changes. Callers follow it
explicitly within the unchanged per-call scan budget. Earlier matches can repeat;
deduplicate accumulated identities. The changed-index warning remains set after
recovery, so exhaustion does not certify a snapshot. Further changes during
recovery retain that warning without another recovery pass.

## Context and mutations

knowledge_context selects either one namespace page or explicit note identifiers.
It returns structured notes within a total body-character budget, omitted notes,
read errors and per-note continuation. It does not follow links implicitly or produce a hidden-model summary.
`knowledge_related` performs explicit bounded native graph discovery. Metadata/listing overhead is outside the body budget.
Cross-namespace references can be selected explicitly alongside the working notes.

Creation uses overwrite=false and inserts no content or relationships. Editing
merges generic metadata and/or replaces exactly one current body passage. Native
reserved metadata keys that the backend ignores are rejected instead of silently
pretending they changed. Arbitrary user status/type conventions do not certify support.
Reserved engine metadata requires the record operations.

Editorial judgment belongs to the calling agent, while the engine supplies
bounded retrieval and faithful mutations. See [editorial composition and
maintenance](editorial-design.md). `knowledge_revise` is the ordinary-note path
for several connected exact replacements: it requires a complete-body SHA-256
returned by read/context, preserves unselected bytes, and rechecks that hash
before a preview or write. It does not change metadata or
governed records. `knowledge_edit` remains the compatible one-replacement and
metadata-merge operation.

Collection maintenance has no hidden registry or quality score. The read-only
`knowledge_inspect_collection` fills the specific gap between listing
and context: a bounded explicit namespace inventory with complete-body hashes,
continuation, and honest omissions. It can report exact duplicate candidates
within its inspected page, never semantic duplication or a claim that a partial
scan is complete. Callers make consolidation decisions and use explicit
per-note revisions; Kajamite has no cross-note transaction or automatic cleanup.

Note and namespace moves delegate to native move_note. Root/path traversal moves
are invalid; destinations cannot overwrite unrelated notes. Returned addresses
and backend move results are authoritative; Kajamite does not promise universal
external-link rewriting or a multi-note transaction. Existing notes are never
reorganized automatically based on their type or legacy metadata.

Cooperating processes share an OS mutation lock. Readback verifies note changes;
uncertain writes are not retried blindly. Direct backend writers and human editors
remain outside that lock. Installation, credentials, backups and source-provider access remain consumer responsibilities.
The engine coordinates record persistence and revision checks within this writer boundary. No knowledge shadow store is created.

## Knowledge change receipts

Every successful create, edit, note move, and namespace move returns a
`knowledge_change` object and a labeled `knowledge_change_text` rendering. Both
are generated from service inputs, readback, and backend confirmation rather
than model-authored prose. The schema version is 1 and its coverage is explicitly
`kajamite_operation`: it does not rule out concurrent or out-of-band changes.

For note creates and exact replacements, readable changed values are capped at
2,000 characters. The receipt always says when a preview is truncated and
includes the complete value's character count and SHA-256 hash. Metadata changes
include the requested keys with previous and current JSON values. Before/current
note identities include canonical paths and hashes of complete readback content.
Note moves use those identities to prove content preservation.

Namespace moves cannot truthfully claim the same per-note readback. Their
receipt reports backend confirmation and the backend's exact affected-file count
when supplied, with `readback_verified=false`. Failed, rejected, or uncertain
mutations never receive a success receipt. Receipts are returned to the caller
only; they are not stored in telemetry or a new history database. Git remains
the durable repository-wide record.

Mutation tools also advertise a shared read-only MCP Apps resource at
`ui://kajamite/knowledge-change.html`. It renders the structured receipt without
external network access or executable actions. Hosts without MCP Apps support
still receive the complete structured result and labeled text fallback. The UI
is presentation, not authority, and is not required for a successful operation.

An error producer can set `error.mutation_outcome="not_started"` only when it
knows the operation failed before a write attempt. The UI then directs the caller
to correct the input. It retains the uncertainty warning when that marker is
absent, unknown, or contradicted by completed-state evidence. Exception type alone
does not establish whether a write started.

## Agent behavior and observability

The reusable skill teaches discovery, selective context retrieval, checkpoint
capture and organization without requiring a particular domain or note layout.
Retrieved text is reference data, never instructions granting tool authority.
The calling agent supplies judgment; Kajamite has no model or transcript reader.

Optional telemetry contains only operation names, outcomes and durations. It is
disabled by default and cannot block knowledge access. It measures operations,
not answer quality. Test outcomes are recorded in validation.md.

## Research and compatibility

Reviewed against installed Basic Memory 0.23.0 and MCP SDK 2.1.1 on 2026-09-09.
list_directory supplies nodes, depth, sorting and pagination. Listing accepts
`title_asc`, `title_desc`, `updated_asc`, and `updated_desc`; omit sorting for the
backend default. Unsupported values are rejected before backend access.
Read-only MCP backend failures report a read failure without implying a pending
knowledge write. Explicit mutation uncertainty remains visible, including when
raised during a read. Unexpected backend details are not exposed.
write_note accepts
a directory; edit_note merges metadata; move_note handles directories and notes.
Native results can be wrapped in structuredContent.result or returned as JSON
text. Search total may be inexact, so continuation uses has_more.

- [Basic Memory tools](https://docs.basicmemory.com/reference/mcp-tools-reference)
- [Basic Memory assistant guide](https://docs.basicmemory.com/reference/ai-assistant-guide)
- [Official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [MCP pagination](https://modelcontextprotocol.io/specification/2025-11-25/server/utilities/pagination)

## Upgrade boundary

The project-specific 0.1 API was removed in 0.2. Version 0.3 adds receipt fields
to successful mutation results and MCP Apps metadata/resources without changing
tool names or required arguments. Existing project-era Markdown and metadata
remain user data and can be read or explicitly edited with ordinary
tools. No automatic data migration, compatibility aliases or namespace manifests
are introduced. Consumers update their skill, tool vocabulary and package pin.

## Unified engine upgrade

Version 0.4 routes Python, CLI, and MCP operations through one engine.
Governed records use reserved nested metadata and a readable claim body.
Generic writes cannot bypass record transitions.
The engine withholds records with stale revisions, unsuitable scope, or unresolved evidence checks.
Full removal reports backend and active-index evidence separately.
It does not claim removal from backups or external copies.
