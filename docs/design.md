# Namespaces and explicit knowledge access

Kajamite 0.2 exposes generic capabilities above an externally managed Basic
Memory project. Its units are namespaces (directories), notes, links and optional
metadata. Domain workflows belong in the consuming skill, not in tool schemas.

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
accepted as note addresses.

## Search implementation

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

## Context and mutations

knowledge_context selects either one namespace page or explicit note identifiers.
It returns structured notes within a total body-character budget, omitted notes,
read errors and per-note continuation. It does not follow links or produce a
hidden-model summary. Metadata/listing overhead is outside the body budget.
Cross-namespace references can be selected explicitly alongside the working notes.

Creation uses overwrite=false and inserts no content or relationships. Editing
merges generic metadata and/or replaces exactly one current body passage. Native
reserved metadata keys that the backend ignores are rejected instead of silently
pretending they changed. Arbitrary user status/type conventions are not enforced.

Note and namespace moves delegate to native move_note. Root/path traversal moves
are invalid; destinations cannot overwrite unrelated notes. Returned addresses
and backend move results are authoritative; Kajamite does not promise universal
external-link rewriting or a multi-note transaction. Existing notes are never
reorganized automatically based on their type or legacy metadata.

Cooperating processes share an OS mutation lock. Readback verifies note changes;
uncertain writes are not retried blindly. Direct backend writers and human editors
remain outside that lock. Installation, credentials, backups and source-provider
access remain consumer responsibilities. No knowledge shadow store is created.

## Agent behavior and observability

The reusable skill teaches discovery, selective context retrieval, checkpoint
capture and organization without requiring a particular domain or note layout.
Retrieved text is reference data, never instructions granting tool authority.
The calling agent supplies judgment; Kajamite has no model or transcript reader.

Optional telemetry contains only operation names, outcomes and durations. It is
disabled by default and cannot block knowledge access. It measures operations,
not answer quality. Test outcomes are recorded in validation.md.

## Research and compatibility

Reviewed against installed Basic Memory 0.23.0 and MCP SDK 2.1.1 on 2026-09-08.
list_directory supplies nodes, depth, sorting and pagination; write_note accepts
a directory; edit_note merges metadata; move_note handles directories and notes.
Native results can be wrapped in structuredContent.result or returned as JSON
text. Search total may be inexact, so continuation uses has_more.

- [Basic Memory tools](https://docs.basicmemory.com/reference/mcp-tools-reference)
- [Basic Memory assistant guide](https://docs.basicmemory.com/reference/ai-assistant-guide)
- [Official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [MCP pagination](https://modelcontextprotocol.io/specification/2025-11-25/server/utilities/pagination)

## Upgrade boundary

The project-specific 0.1 API is removed in 0.2. Existing project-era Markdown and
metadata remain user data and can be read or explicitly edited with ordinary
tools. No automatic data migration, compatibility aliases or namespace manifests
are introduced. Consumers update their skill, tool vocabulary and package pin.
