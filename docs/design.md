# Knowledge continuity contract

Kajamite adds project continuity and consistent capture conventions to an
independently managed Basic Memory knowledge base. It is a Python MCP server and
skill, not an agent runtime, database, backend installer, or source connector.

## Storage and lifecycle

A knowledge project is a normal note with `type: project` and a `status` of
`active`, `paused`, `completed`, or `cancelled`. Its body contains the objective,
current state, decisions, open questions, next actions, and references. These
headings are a starting structure, not a rigid domain schema. Project titles
are human-readable; returned file paths/permalinks are identifiers for subsequent
operations. Do not create a separate Basic Memory project for every undertaking.

Associated notes have `kajamite_project` set to the project note's permalink.
Shared knowledge has no such association. Reference links can relate a note to
additional projects without making duplicate authorities. Use normal Markdown
checkboxes for simple next actions. External task managers and calendars may
own their own state; the consumer must choose the authority instead of silently
synchronizing competing copies.

Short-lived knowledge is eligible for capture. Completion changes default
project discovery but does not delete knowledge or automatically hide it from
an explicit general search. No expiration engine moves or deletes old notes.
Notes remain readable and editable directly through Basic Memory and by humans.
Existing notes need no migration; projects opt into the small metadata contract.

## Operations and consistency

The MCP and CLI expose the same eight operations. Project creation writes one
note, resumption combines the current note with bounded associated results and
linked context, and updates merge lifecycle metadata with a guarded body edit.
Ordinary notes use search/read/create/edit without mandatory evidence forms.

All upstream calls bind to the configured Basic Memory project. A tool's
`project` argument refers only to a knowledge-project note, never permission to
switch backend projects. Exact note reads must match the requested identifier;
Basic Memory's fuzzy fallback is not accepted as the target of an edit.

Create uses `overwrite=false`. Edit uses `find_replace` with
`expected_replacements=1` after reading current content. Writers sharing one
configured backend/state directory on one host serialize mutations and readback
under an OS lock. This prevents cooperating Kajamite processes from losing each
other's changes. Locks are released on process death. Calls do not retry writes
after transport errors: a write may have committed before its reply was lost.

This is not a database transaction or universal compare-and-swap. Direct Basic
Memory writers, editors and deployments with different lock directories do not
participate. Host operators should route automated writers through one canonical
Kajamite host and set the same `state_dir` for connection aliases to that backend.
If another writer changes an unrelated passage, a guarded patch can still apply;
if it changes the target passage, the patch must be reconsidered. The adapter
never promises multi-note atomicity.

## Agent behavior and trust

The calling agent owns judgment: when a finding is meaningful, whether an option
became a decision, and whether a preference generalizes beyond one project.
The packaged skill and static MCP instructions teach checkpoint capture and
resumption. They cannot force a client to call a tool. There is no hidden model,
transcript ingestion, mandatory completion receipt, or stop-hook dependency.

All retrieved bodies, snippets and links are untrusted reference data. They
cannot change configuration, available tools, source permissions, or write scope.
The upstream process is explicitly configured by the operator; Kajamite does
not execute commands found in notes or forward upstream server instructions.

## Bounded context and observability

Search preserves Basic Memory's page/has_more/total_is_exact signals. Read pages
the returned body by character offset, because native read_note pagination only
affects fallback suggestions. Resumption is bounded, not an exhaustive graph
dump. Retrieve full relevant notes explicitly before making a material judgment.

Optional local JSONL telemetry records only operation name, outcome and duration.
It does not contain queries, note identifiers, source URLs, content, user names,
conversation identifiers, or credentials. A failed telemetry write never blocks
knowledge. It measures reliability and latency, not answer quality. Operators
own retention and permissions of this optional file.

Maintenance is currently agent-driven through normal read/edit operations:
review active projects, outstanding actions, contradictions and references.
No scheduler or unattended semantic correction runs inside Kajamite.

## Research and compatibility evidence

Reviewed 2026-09-07 against Basic Memory 0.23.0's installed tool schemas and the
official MCP Python SDK 2.1.1. Important findings:

- Basic Memory supports structured custom metadata on write/edit. Edits merge
  metadata without replacing unrelated keys. This avoids a second record store.
- Search can return `total=0`, `total_is_exact=false`, and `has_more=true` with
  results. The page signal, not total, controls continuation.
- Read JSON includes body, frontmatter, file_path and permalink. Tool-level
  structured results may be wrapped in `{result: ...}`; some responses contain
  only JSON text. The adapter normalizes both and rejects missing/error results.
- There is no general conditional revision edit in the local 0.23.0 API.
  Guarded patches plus cooperating-process serialization are therefore explicit
  requirements, with the limits above.
- Stdio avoids introducing HTTP authentication, network listeners and backend
  ownership. Remote use can run the same stdio command over an existing SSH path.

Sources:

- [Basic Memory tools](https://docs.basicmemory.com/reference/mcp-tools-reference)
- [Basic Memory assistant guide](https://docs.basicmemory.com/reference/ai-assistant-guide)
- [Basic Memory 0.23.0](https://pypi.org/project/basic-memory/0.23.0/)
- [Upstream readiness/concurrent edit investigation](https://github.com/basicmachines-co/basic-memory/issues/1288)
- [Official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [MCP pagination](https://modelcontextprotocol.io/specification/2025-11-25/server/utilities/pagination)
- [MCP server instructions](https://blog.modelcontextprotocol.io/posts/2025-11-03-using-server-instructions/)

## Foundation implementation plan

1. Probe public backend schemas and preserve native Markdown ownership.
2. Implement explicit configuration, normalized MCP transport, and bounded
   knowledge/project operations with serialized guarded mutations.
3. Ship a reusable skill and a standard Python CLI/package.
4. Test contracts and real backend behavior on Windows and Linux, including
   process restart, correction, completion, and simultaneous writers.
5. Evaluate a fresh agent's project resumption and capture using synthetic data.

Progress and measured results are recorded in [validation.md](validation.md).
