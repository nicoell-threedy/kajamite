# Validation

## Search continuation after native index changes

Changed native totals invalidate ranked offsets. At the end of traversal, the
returned cursor restarts at the first page, with the same query, scope, and
per-call page budget. The cursor preserves recovery between calls. A separate
oscillating-total control checks that later pages progress before recovery.
Recovery runs once; further changes remain partial without endless rescans.
The changed-index warning remains set. Repeated identities require caller
deduplication, and exhaustion does not establish a stable snapshot.

The regression removes an earlier row after the first 250 results. The target
then moves before the saved offset. The 0.8.0 baseline ends with no target;
the corrected continuation returns it. Existing changed-total, legacy-cursor,
filter-binding, and bounded-scan checks remain intact.

On Windows Python 3.12, the source suite runs 124 tests: 118 pass and six skip.
All five browser checks pass separately. The UI source and shipped bundle are
unchanged. Native indexing duplicates and equal-total changes remain backend
limitations; this correction does not repair the backend index.

A native deletion control moves the target before the saved offset. Windows
and Linux Python 3.12 both recover it in two continuations. Both traversals
finish with `partial=true` and `complete_scope_search=false`.

## Search and collection descriptions

Tool descriptions distinguish native-stream exhaustion from a complete inventory.
They identify `partial` and `index_changed` and retain the live-snapshot limitation.
All 119 source checks pass, including browser checks. This description change
does not modify pagination, persistence, or receipt rendering.

## Changing search totals

Search carries the last reported native total and any observed change through its
cursor. A changed total sets `index_changed`, withholds complete-search status,
and marks engine search and collection inspection partial, including at exhaustion.
Synthetic controls cover changes within and between calls, continued warnings,
legacy cursors, malformed cursor fields, and absent totals. The installed-wheel
suite passes 119 tests with one expected packaged source-history skip. The source
suite passes with four browser checks skipped; those checks run in the wheel suite.
The UI bundle is unchanged. Stable or missing totals do not prove snapshot
consistency, and this safeguard does not repair native indexing or qualify an
earlier failed continuation check.

## Verification outcome diagnostics

Unrecognized verification outcomes in revise and revalidate requests are rejected
before backend access. The diagnostic lists the four schema values and declares
that no write was attempted. Lifecycle-specific validation remains unchanged.
Synthetic controls cover strings and non-string values without echoing rejected
input. Native checks preserve the record and accept a corrected request with the
same operation ID. All 116 source and installed-wheel checks pass, with one
expected packaged source-history skip. All three native commissioning phases and
an embedding MCP probe pass. Desktop and 320px review show the actionable error
without a pending-write warning. The UI bundle is unchanged.

## Revision conflict outcomes

Stale expected revisions report the requested and observed numbers and an
explicit no-write outcome. Source controls preserve note bytes and write-call
counts. Standalone and embedding MCP paths retain the signal, while operation-ID
conflicts and uncertain errors keep their existing handling. Native governed
commissioning and shared-host desktop/320px inspection confirm the result.
All 115 source and installed-wheel checks pass, with one expected packaged
source-history skip. The UI bundle is unchanged.

## Named support changes and narrow wrapping

Source and observation summaries identify changed entries and omit zero-count
groups. Synthetic controls retain additions, removals, rebinding, independent
statement edits, order changes, and explicit omitted-entry counts. Rechecks and
proven prose mirrors remain suppressed without changing records or raw metadata.
The browser checks cover long unbroken IDs and JSON values in collapsed and
expanded 320px views. The shared wrapping class keeps both within the frame.
All 115 source and installed-wheel checks pass, with one expected packaged
source-history skip. Native governed commissioning and the UI build, formatting,
and type checks pass. Installed-client acceptance remains separate from the
shared-host view.

## Explicit claim mirrors

Revision requests can explicitly select whole-claim observations for an atomic
statement update. Synthetic controls preserve unselected equal-text observations,
independent statements, evidence bindings, history, and original replay inputs.
Empty, duplicate, missing, nonmatching, and conflicting selections reject without
changing stored state or consuming the operation ID. Verification remains required.
All 113 source and installed-wheel checks pass, with one expected packaged
source-history skip. All three native commissioning phases pass, including MCP
mutation, independent record readback, and replay of an explicit mirror revision.
Shared-host desktop and 320px receipt inspection retains precise passage edits
and secondary audit details. No UI bundle or record schema changes are required.

## Observation input diagnostics

Revision requests with empty, non-list, non-object, or incomplete observations
fail before authorization and backend calls. Diagnostics name the entry index
and missing fields without echoing submitted values. Native controls verify
unchanged records after rejection and successful corrected submission and replay.
All 111 source and installed-wheel checks pass, with one expected packaged
source-history skip. All three native commissioning phases pass. These checks
establish input diagnostics, not automatic synchronization of claim and observation text.

## Duplicate creation outcomes

An existing governed ID is rejected before a note write. Synthetic controls
verify unchanged stored records and the absence of write calls. The explicit
`not_started` marker survives embedding wrappers and standalone MCP serialization;
uncertain or unmarked errors retain conservative behavior.

All 111 source and installed-wheel checks pass, with one expected packaged
source-history skip. Native commissioning passes, including duplicate rejection
and independent record readback. Desktop and 320px shared-host inspection show
the error and explicit no-write message without a pending-write warning. The
rendered bundle is unchanged. Installed-client acceptance remains separate.

## Mirrored passage support

A single observation statement that exactly mirrors a unique body replacement
does not add a duplicate support-change notice. Synthetic controls retain notices
for changed evidence bindings, independent statements, unchanged-body reassignment,
multiple changed statements, and ambiguous or overlapping passage occurrences.
Projection leaves both input records unchanged. Native commissioning checks the
saved statement, original history, and complete raw metadata independently.
The 109-test source and installed-wheel suites pass, with one expected packaged
source-history skip. Focused overlap controls and all three native commissioning
phases pass. Two preserved multi-observation revisions were reprojected without
changing their body diffs, record values, or raw metadata. Shared-host desktop
and 320px views retain source and verifier changes while omitting the duplicate
support notice. Installed-client acceptance remains separate.

## Revision input diagnostics

Unsupported revision fields and incomplete supplied verification objects fail
before authorization or backend operations. The diagnostic lists supported fields
or all missing verification fields without echoing arbitrary input values.
Timestamp, revision, evidence-binding, and replay checks remain enforced.

All 108 source checks and 108 installed-wheel checks pass, with one expected
packaged source-history skip. All three native commissioning phases pass,
including rejected input, preserved readback, corrected same-ID submission, and
replay. A separate native MCP probe verifies delivery of the grouped diagnostic
and unchanged note bytes after rejection. These controls do not measure model
repair success or authorize a deployment.

## Maintenance state visibility

The collapsed maintenance view reports how many newly saved notes need
revalidation, including notes outside the first three visible entries. It counts
distinct note identifiers only from readback-verified status changes. Replayed
and unverified outcomes do not imply a new saved state; partial failures retain
the retry warning. Known lifecycle labels are readable words, while raw values
remain intact in the receipt.

The same five-dependent-note engine payload was inspected before and after the
presentation change at desktop and narrow widths. All 107 source checks and
107 installed-wheel checks pass, with one expected packaged source-history skip.
Frontend formatting, types, bundle checks, and four browser checks pass. Backend
Python code is unchanged from `e2ba5f3`; native commissioning was not repeated for
this presentation-only change. Installed-client acceptance remains open.

## Read failures and directory ordering

Read-only MCP backend failures report a read failure and no attempted knowledge
write. Mutation backend failures retain the pending-write warning. Explicit
mutation uncertainty takes precedence even when raised during a read. Live
stdio tests verify these distinctions and suppress private backend details.

The listing schema exposes the four supported orderings. Invalid ordering is
rejected before backend access; valid ordering is forwarded unchanged.
All 107 source checks pass, including four browser checks run separately.
All 107 installed-wheel checks pass with one expected source-history skip.
No receipt UI code changes are included.
All three isolated native commissioning phases pass. A separate native read
probe rejects an unsupported sort, accepts a supported sort, and reports disabled
hybrid retrieval as a read failure. The probe preserves the seeded note bytes.

## Pre-write rejection

The shared error view accepts an explicit `error.mutation_outcome="not_started"`
marker when no completion evidence contradicts it. The input problem remains
visible and the view says that no write was attempted. Unknown errors, unknown
markers, receipts, completed items, mutation results, committed revisions, replay,
and accepted-state evidence retain the uncertainty warning.

All 107 source checks and 107 isolated installed-wheel checks pass, with one
expected packaged source-history skip. Browser checks cover the rejection and
contradiction cases; frontend formatting, types, and bundled assets pass checks.
An actual pre-write error envelope is readable in shared-host desktop and 320px
views. This does not establish installed-client acceptance or classify other
exceptions as pre-write failures. Backend behavior is unchanged.

## Graph continuation

Native CI at `cca6d58` returns the expected linked notes but advertises another
primary page. Related discovery follows bounded primary pagination and preserves
partial flags for page, note, related-result, and namespace limits. Synthetic
checks cover later neighbors, repeated paths, exhaustion, scope exclusions, and
continuation failure. All 107 source checks and all three native commissioning
phases pass. The native acceptance assertion
is unchanged; the cause of the backend's additional primary result remains open.

## Creation summaries

New-note summaries count affected notes without describing initialized metadata as
field updates or the new body as a text edit. Saved content leads the overview;
initial note fields remain available in their own disclosure. Existing-edit counts
and comparisons are unchanged. All 104 source checks and frontend build checks
pass. Shared-host desktop and 320px inspection confirms the content-first view and
field disclosure. Installed-client acceptance remains separate.

## Cross-process lock coordination

The contention test holds the subprocess lock until an explicit release event.
Timeout and cancellation are checked while that holder remains active; acquisition
is checked again after release. All 104 source checks pass. A delayed contender
is denied while the holder stays alive beyond the former fixed hold interval.
This test change does not modify the lock implementation or establish the cause
of every earlier concurrent-operation failure.

## Replay context

Replay results without a change receipt identify the returned note and distinguish
the original operation revision from the returned record revision. They show no
invented diff and preserve warnings on the returned record state. Missing revision
fields remain absent. All 104 source checks and the UI build pass, including
ordinary receipt and fullscreen behavior. Desktop and 320px inspection confirms
the replay context remains readable. Installed-client acceptance remains separate.

## Compact-summary review

All 104 source checks pass. The UI verifies the exact snapshot digest and operation
bindings before restoring full receipt review from MCP metadata. Browser checks
cover matching and absent metadata, mismatched identity/revision/status, altered
content, wire errors, unavailable audit readback, ordinary results, and narrow
layout. Delayed digest checks cannot overwrite newer input or cancellation.
Format, type, bundle, and mechanical source checks pass. Synthetic-host inspection
confirms actual before/after rows and explicit fallback. Engine response defaults
are unchanged; installed-client metadata forwarding remains unqualified.

## Related-topic completeness diagnostics

Native CI at `b41619a` finds both expected related notes but fails the assertion
that the result is complete on Linux Python 3.12. Failure output includes the
returned bundle and native graph responses, preserving the exact assertion and
avoiding automatic retries. Local governed-engine commissioning and all 103
source checks pass. These results do not establish the cause of the CI failure.

## Complete creation snapshots

All 103 source checks pass. Governed creation binds the returned claim with a
claim-specific digest and committed revision. The shared UI verifies these fields
before exposing the complete note, without copying the claim into its receipt.
Browser checks retain excerpts for altered claims, mismatched revisions, missing
digests, and unverified readback. Unicode content beyond the receipt limit remains
readable. Backend framing and all three native commissioning phases pass.
The built view is inspected at desktop and 320px widths without horizontal overflow.
This snapshot describes the completed operation; it is not a fresh note read.

## New-note review

New-note receipts lead with the added prose. Initialized fields have a separate
`Note fields` disclosure; all values and raw audit data remain available. Existing
note edits retain their before/after comparisons. Added and removed content summaries
allow 300 characters, matching other prose summaries. All 102 source checks pass,
including Chromium disclosure, reset, existing-edit, and narrow-layout controls.
The UI build and mechanical source scan pass. This does not establish installed-client
acceptance or full-note reading: truncated receipts still expose only excerpts.

## Governed record identifiers

All 102 source checks pass. New `.md` and `.MD` record IDs are rejected before
backend access, with guidance to use a bare ID and a separate namespace. Synthetic
legacy records with such IDs remain readable and support lifecycle transitions.
The native commissioning fixture also exercises the creation rejection.

## Passage summaries

Receipt counts distinguish text edits from field updates. Collapsed text comparisons
retain up to 300 characters per side around the edit; larger passages keep explicit
truncation and remain available in details. Narrow comparisons stack Before/After
labels above their text at widths up to 420 pixels. Chromium checks cover mixed
counts, a complete bounded correction, retained field disclosure, and narrow layout.
Desktop and narrow synthetic-host inspection confirms the same behavior. The
mechanical source scan reports no findings; this is not a full accessibility audit
or installed-client acceptance.

## Evidence revision diagnostics

All 101 source checks pass. Invalid evidence lists and dangling observation
references return specific, value-free diagnostics before mutation. The native
backend check confirms that rejected revisions leave the complete note unchanged.
Tool guidance distinguishes evidence-ID validity from observation statement support;
this does not establish that an autonomous author keeps every intermediate revision
semantically consistent.

## Related-topic orientation

All 100 source checks pass. Native governed-engine commissioning confirms that
a detail note can discover an overview through an incoming link across namespaces.
Both inspected bodies fit in their exact combined prose budget and remain marked
`reuse_checked=false`. A narrow namespace returns only the starting topic,
reports the excluded neighbor, and marks the result partial. Tool descriptions
explain the starting note, incoming links, and explicit root-scope selection.
This establishes retrieval behavior, not reliable autonomous tool selection.

## Compact mutation projection

All 100 source checks pass, including three Chromium checks. The focused engine
checks cover compact creation, transitions, transient no-write outcomes, invalid
option rejection before mutation, stale revisions, and replay across response
views. Full native commissioning passes through the public backend and MCP.
The native protocol advertises a Boolean option with a true default, preserves
complete receipts, and returns full history on a separate inspection read.
Rendered desktop and narrow review retain the same edited passage and audit
disclosure. Stored history and default responses remain unchanged.

## Native pagination investigation

A Linux Python 3.12 CI run failed the existing native FTS continuation assertion:
the final scoped page reported exhaustion without returning the seeded target.
Local full commissioning passes. The cause is not established. Failure output
includes ordered native page paths, totals, and continuation flags to distinguish
backend ordering/index changes from adapter filtering. The original pagination
assertions and acceptance conditions remain unchanged.

## Plain-text receipt projection

All 99 source checks pass, including preservation of full structured history,
legacy metadata fallback, passage hashes, and saved state when the state did not
change. Native governed-engine commissioning verifies an audit-only update with
concise text and complete structured audit data. This reduces duplicated response
text; it does not change stored records or establish a model-token saving.

## Primary changes and audit information

All 98 source checks pass, including browser coverage for audit-only single and
batch saves. Native governed-engine commissioning verifies that unchanged-source
rechecks retain their evidence, verification, history, and reuse eligibility.
Projection controls keep changed source references, fingerprints, support
bindings, and independent observations visible. A heading-only receipt displays
one primary change while its original audit fields remain available in raw
disclosure. This presentation change does not reduce persisted history.

## Reflow and readable receipt subjects

All 97 source checks pass, including three Chromium tests, and frontend format,
type, and generated-bundle checks pass. Native governed-engine commissioning
verifies retained phrases across a line break with a changed value, preserved
history, and stored titles in receipts. Synthetic checks cover Unicode offsets,
the token ceiling, malformed range fallback, and inert source text.
Rendered desktop and narrow test-host views preserve unchanged wording while
highlighting the edited number and added list structure. Stable paths remain
visible below display titles. Governed topics derive the label from a leading
level-one heading in the current body; read, search, list, context, and receipt
checks preserve the original identifier and stored bytes. Ordinary notes retain
their explicit titles. This does not establish installed desktop-host acceptance.

## Required verification fields

Missing verification timestamps return a specific field error before mutation.
Synthetic rejection checks preserve stored bytes and keep unrelated private
diagnostics opaque. All 95 source checks pass across the main suite and separate
three-test Chromium run. Native governed-engine commissioning passes.
Package validation remains recorded at the inspection-context revision below.

## Governed revision receipts

Governed passage receipts use validated before/after claims when Markdown line
endings are normalized. This includes a replacement ending in carriage return
beside an existing line feed. The 91-test source suite passes, including canonical
preview/hash checks and the three Chromium tests.

On 2026-10-01, the 89-test source suite passed: 86 passed and three browser
checks skipped. Synthetic checks cover complete-claim edits after 2,000
characters, distant edits with unchanged middle lines, a Unicode edit near the
end of a long line, insertion, deletion, broad-replacement truncation, the
500-line fallback, unchanged claims, and operation replay. Full passage hashes,
record readback, and metadata changes remain in the receipt. An isolated native
MCP complete-claim revision also confirms two distant changes, exact readback,
retained history, and operation replay. Both changes are visible in collapsed
and expanded views of the packaged frontend in a synthetic host. This does not
establish desktop-host acceptance or correct the remaining metadata layout.

An isolated native MCP selected-replacement revision changes two small passages
in a 6,362-character topic, preserves its original history, and reads back the
exact updated record. Both old/new passage pairs remain in the receipt and are
visible in the packaged frontend's collapsed view in a synthetic host. Desktop
host rendering remains unverified. No frontend bundle changes are required.

## Compact governed-record metadata

On 2026-10-01, 87 source tests ran on Windows Python 3.12: 84 passed and three
browser checks were skipped.
Synthetic checks cover complete multi-revision round trips, create/revise/read
and operation replay, legacy read and upgrade on transition, body tampering,
malformed journals, and leading/trailing newline preservation. A synthetic
four-revision record measured 3,992 JSON bytes as a complete record and 2,315
JSON bytes as `journal-v1`, using the same serialization settings: 1,677 bytes
(42.0%) less metadata. This is a record-level measurement, not a backend storage
or retrieval benchmark.

Exact governed passage repair checks cover disjoint replacements, preserved
history, stale revisions, rejected selections, and operation replay. Compact
inspection checks preserve every current field, omit only history on request,
reject invalid history, and leave stored data unchanged.

Native Basic Memory commissioning also passed on Windows against version 0.23.0.
It covers the governed codec, request scope, restart continuity, source-change
withholding, revalidation, replay, MCP lifecycle operations, CLI inspection,
dependency maintenance, and removal. The MCP test subprocesses explicitly select
the same package directory as their parent. Source-checkout runs set `PYTHONPATH`
to the checkout's `src` directory.

The 0.7.0 source distribution builds a wheel that installs in a separate virtual
environment with the hashed dependency lock. In an isolated fixture with the
wheel installed into `src` and no checkout package source, 87 tests run: 83 pass,
three browser checks are skipped, and the source-history publication check is
skipped because the fixture has no Git history. This layout prevents test import
paths from selecting checkout code. Native
commissioning also passes against the installed wheel, including concurrent
writers and the governed lifecycle. Browser acceptance and client deployment
remain unverified for this release.

Known verification timestamp and revision errors identify the invalid field.
Synthetic checks preserve the stored record on rejection and keep other
diagnostics opaque. A focused native wheel check confirms the timestamp message
and unchanged record. The complete native commissioning result above precedes
this diagnostic-only change.

One native run returned an operation error during concurrent edits. A complete
rerun passed. The commissioning helper exposes synthetic tool errors for further
diagnosis; the intermittent failure's cause is not established.

## Governed record engine development

On 2026-09-10, all 30 source/protocol tests passed on Windows with Python
3.12.14 and MCP SDK 2.1.1. Six independent governance tests cover lifecycle
history, source validation callbacks, schema isolation, Markdown round trips,
changed versus inaccessible evidence, and content-free summaries.

The wheel installed into a separate environment with no runtime dependencies.
All six governance tests passed there. A separate interpreter with site packages
disabled imported the engine without MCP, YAML, or OpenTelemetry modules.
The documentation example ran successfully. Wheel inspection found the engine
and no development caches. The frontend reports a missing MCP extra without
a traceback; its version command works when that extra is installed.

The native Basic Memory acceptance suite and Linux checks were not rerun for
this increment. Note operations and backend protocol behavior did not change.
The engine produces validated record values; these checks do not prove atomic
persistence, authorization, retrieval filtering, or physical erasure.

## Publication checks

On 2026-09-10, all 24 source/protocol tests passed on Linux with MCP SDK 2.1.1.
Four publication tests cover private-identifier matching, safe diagnostic output,
staged content, and sensitive content removed by a later commit. The publication
scanner also passed against the complete branch and release-tag history.

## Version 0.3.2

Run source and protocol checks with:

```text
python -m unittest discover -s tests -v
```

Run isolated native-backend acceptance with an independently installed Basic
Memory 0.23.0 executable:

```text
python tests/commission.py --basic-memory /absolute/path/to/basic-memory
```

On Windows supply basic-memory.exe. The harness owns only its temporary synthetic
project/configuration. --keep retains that synthetic state for a fresh-agent test.
No personal knowledge corpus is shipped.

Acceptance additionally checks deterministic create/edit/move receipts, labeled
text fallback, exact replacement and metadata values, content-hash preservation,
truthful namespace-move confirmation, and affected-note counts. Source and wire
cases check 2,000-character preview bounds, full-value hashes, mutation tool UI
metadata, the packaged `text/html;profile=mcp-app` resource, and its explicit
no-network CSP. The wheel build is inspected to ensure the HTML, receipt module,
skill, and UI loader are included.

Observed 2026-09-09 on Linux: all 20 source/protocol tests pass with MCP SDK
2.1.1, both packaged skill copies are identical, Python compilation succeeds,
and the 0.3.2 wheel contains all UI and receipt assets. The initial v0.3.0 CI
acceptance assertion assumed the stored body started with caller-supplied text;
Basic Memory legitimately adds normalized Markdown before that text. Version
0.3.1 checks that the verified stored preview contains the value instead.
GitHub Actions run 34398398576 passed all six Ubuntu/Windows Python
3.11/3.12/3.14 jobs. Its Python 3.12 jobs passed the isolated Basic Memory
0.23.0 commissioning suite, including the new receipt behavior, on both
platforms. The same isolated suite subsequently passed on a separate Linux host
with an independently installed Basic Memory executable and temporary synthetic
state. Its canonical knowledge project was unavailable during this check.

The first v0.3.1 release-commit run then exposed a distinct intermittent Windows
acceptance failure: the final synthetic note was not yet visible in Basic
Memory's asynchronous FTS projection. Version 0.3.2 waits for that exact target
with a 30-second bound before testing continuation beyond 250 outside results;
it does not weaken the pagination assertion.

## Version 0.2

Acceptance covers multi-note namespaces, same titles in different folders,
metadata-only updates, cooperating concurrent edits, move collision refusal,
native note/namespace moves, search using moved physical paths, and budgeted
context spanning scoped and shared notes. Source cases also test continuation
past more than 250 outside-scope hits, nested/similar/overlapping namespaces,
legacy metadata preservation and incomplete context/error disclosure.

Observed 2026-09-08: all 15 source/protocol tests pass on Windows and native
Linux, along with ten real-backend checks for namespace listing, metadata,
moves, physical-path search and structured context. The native FTS stress case
passes on both hosts: an empty first scoped page scans 250 outside hits and the
next cursor reaches the relevant note. Move collisions preserve both notes.

A fresh agent using only the new tools recovered four facts from three notes
and completed the requested action. Independent Markdown readback verified
preserved metadata and a byte-identical shared preference note. This is one
continuity acceptance scenario, not a general claim about all models.

CI exercises Windows and Ubuntu with Python 3.11, 3.12 and 3.14; 3.12 jobs also
run native-backend acceptance. Release CI evidence is linked by the repository's
commit checks; consumer-specific rollout details remain with each consumer.

## Previous release evidence

Version 0.1 passed its 15 source/protocol tests, native Windows/Linux commissioning,
and a single fresh-agent project-continuity case. Those results established the
old interface's behavior, not the suitability of its project abstraction. They
are not evidence that the namespace replacement has passed its new cases.

## Unified engine acceptance

On 2026-09-10, all 54 source and protocol tests passed on Linux Python 3.12.
The suite includes revision conflicts, current-record filtering, dependency changes,
removal projection errors, and an engine-only restart with site packages disabled.
The original native Basic Memory 0.23.0 commissioning suite also passed.
It retained namespace moves, concurrent writes, receipts, and continuation beyond 250 outside hits.

The capability audit passed observation/category retrieval, nested metadata,
typed relations, graph neighbor paths, and native deletion.
The first native engine scenario passed persistence, restart, scope checks,
source-change withholding, revalidation, and operation replay.
The installed cross-frontend scenario also passed Python/MCP revision parity,
MCP lifecycle changes, CLI inspection, dependency maintenance, and removal evidence.
Independent review led to stricter duplicate-identity and mutation-readback checks.
Unconfirmed writes raise `MutationUncertain`; callers must inspect before retrying.

The fixed retrieval corpus returned a 54-character observation versus a
1000-character entity preview. Both searches recovered the relevant source.
The engine's current-note check added one backend call in this fixture.
See `docs/retrieval-evaluation.md` for measurements and limits.

Native CI exposed repeated entity rows with identical paths and IDs. Search
now deduplicates candidates within each call, including its native page scan.
Distinct observations and relations remain separate. Offset cursors still do
not promise a stable snapshot across concurrent projection changes.

## Embedded frontend and premise checks

On 2026-09-11, all 56 source and protocol tests passed on Windows Python 3.12
with MCP SDK 2.1.1. The embedding host exposes the same knowledge schemas,
annotations, receipt resource, and guide as the standalone frontend. Its wrapper
adds a host receipt ID while preserving mutation receipts, text fallback, and errors.
Premise checks cover unchanged, changed, inaccessible, missing, and deleted evidence.
These protocol checks do not establish visible rendering in any particular client.
The installed native engine commissioning also passed against Basic Memory 0.23.0
in separate Python environments. It covered restart, source-change withholding,
revalidation, operation replay, Python/MCP revision parity, CLI inspection,
dependency maintenance, and native removal evidence.

Release review on 2026-09-11 also passed all 56 source/protocol tests on Linux.
An independent diamond-dependency probe checked each shared premise once and
withheld the root for inaccessible indirect evidence without changing stored notes.
PR revision `4d918fabdd1b6d70dea46cfd5a58e59d3cab7854` passed all six
Windows/Linux jobs in Actions run 34578345303, including native commissioning
on both Python 3.12 platforms. Version 0.5.0 adds the compatible frontend API
and strengthens premise eligibility; it changes no dependency pins or record schema.

## Body replacement acceptance

On 2026-09-11, 57 source/protocol tests passed on Windows Python 3.12.
The Basic Memory 0.23.0 engine commissioning passed a claim-body revision while
preserving the original event snapshot. The adapter regression also covers repeated
metadata text, plain Markdown, CRLF framing, and rejection of ambiguous body matches.
Body edits perform one additional full-Markdown read before the guarded native edit.

## Version 0.5.1

PR #3 passed all six Windows/Linux CI jobs (run 34585749834), including native
Basic Memory 0.23.0 acceptance. A separate native engine check confirmed that
claim correction preserves the original history event. All 57 tests passed
with the installed 0.5.1 package.

## Editorial composition and maintenance

Working-tree verification on 2026-09-13 used the pinned Kajamite interpreter
with `PYTHONPATH=src`. The full source/protocol suite passed 66 tests. It covers
the shared Python, CLI, and MCP operation catalog; byte-identical packaged skill
copies; the CLI `skill` output; the MCP guide resource; existing `knowledge_edit`
compatibility; generic/governed separation; grouped revision preview, stale-hash,
readback, receipt, and text-fallback behavior; and bounded collection inspection.
Inspection cases cover scope/recursion/page-size cursor binding, incomplete empty
pages, exact duplicates as page-scoped candidates, and governed or unauthorized
omissions. A synthetic two-note walkthrough injects the second write's uncertain
failure, rereads its source hash, and resumes only the still-valid outstanding
revision.

The working tree was also built and installed into a disposable virtual
environment with the hashed dependency lock. Its packaged guide matched the
source guide byte-for-byte, and all 66 tests passed against the installed wheel.

The complete isolated commission entrypoint then passed against Basic Memory
0.23.0. Its ordinary-note scenario exercised grouped revision, its receipt and
text fallback, bounded collection inspection, existing edit/move behavior, and
native full-text continuation. The capability and governed-engine scenarios also
passed. All state was synthetic and temporary. This establishes backend operation
behavior, not editorial usefulness or compatibility with every future Basic
Memory release.

The editorial design is source-informed by inspected upstream mechanisms and
historical failure reports. Deterministic tests establish operation mechanics,
not that prose is readable, correctly scoped, or useful. The documentation was
reviewed for coherent purpose, boundaries, useful-detail preservation, and
honest limitations; that is human editorial judgment, not a universal score or
usability study.

## Kajamite 0.6.0 review validation

The adapted editorial change passed 68 source tests, including real Chromium
acceptance with a simulated MCP Apps host. The UI checks cover compact initial
layout, incremental disclosure, display-mode negotiation, refusal, timeout,
resize notifications, narrow width, inert source text, and operation states.
The compact and expanded synthetic layouts were also visually inspected.
These checks do not establish rendering in an actual Codex or ChatGPT account.

Revision regression coverage rejects overlapping occurrences of one selection
before either preview or mutation. Maintenance now exposes its receipt UI.
The Python dependency set is unchanged, and the updated package lock passes
`uv lock --check --offline`.

One native commissioning attempt passed mutations and grouped revisions but
failed the existing large-search continuation assertion. A retained-corpus run
passed unchanged, followed by three successful continuation checks on that corpus.
The native query returned 276 rows for 261 unique paths. Pagination remains live,
and this observation does not prove the exact cause of the initial failure.
No search assertion was weakened and no production retrieval code was changed.

The installed 0.6.0 wheel matches the reviewed UI and guide. Its independent
capability audit and governed-engine commissioning both passed against Basic
Memory 0.23.0. Together with the retained-corpus run, these cover all three native
commissioning components. This is separate-run evidence, not a claim that the
first complete commissioning invocation passed.

## Configurable shadcn UI validation

The shadcn UI candidate passed 77 source tests, including both real Chromium
checks with a simulated MCP Apps host. Thirteen protocol, theme, and browser
tests also passed against the installed wheel outside the source tree.

A clean `npm ci --ignore-scripts` followed by `npm run check` reproduced the
packaged HTML and notices. Type checking and formatting passed. The bundle is
300,237 bytes, or 92,862 bytes with gzip; MCP transport compression is host-owned.
The npm audit reported zero known vulnerabilities on 2026-09-14.

The Python build produced a source distribution, then built the wheel from it.
Node and npm commands were replaced with failing sentinels during this check;
neither was invoked. The installed wheel includes the UI and third-party notices.
Source/artifact mismatch tests reject stale, missing, and modified build inputs.

Theme tests cover CSS exports, tweakcn registry maps including shared typography,
relative configuration paths, separate resource cache keys, host/adopter precedence,
light/dark changes, and rejection of rules, URLs, escapes, and unsupported tokens.
A current tweakcn registry export also loaded successfully. Browser tests verified
no external asset requests. Synthetic default, dark, and themed layouts were
visually inspected. Receipt payloads retain their existing operation semantics.

Actual Codex and ChatGPT rendering remains unverified. Native backend commissioning
was not rerun locally for this presentation/configuration change; the existing
CI backend checks remain enabled. The earlier live-search limitation remains.

The publication check now requires four octets for private IPv4 addresses.
Regression tests distinguish dependency versions from all three private ranges;
the previous expression incorrectly classified npm version 10.9.8 as an address.

The first UI CI job passed. Windows exposed a test expectation that compared
a temporary-directory alias with its resolved path. The expectation now resolves
the path, matching the configuration contract; production path handling is unchanged.

## Change presentation redesign

The redesigned candidate passes 78 source tests, including three real Chromium
checks. New checks cover labeled field transitions, hidden revision counters,
visible partial failures, summaries around changed words after long shared text,
bounded excerpt disclosure, and transparent document backgrounds with opaque
cards. Existing host fallback, theme replacement, inert text, and 320px checks
also pass. A separate synthetic gallery exercises all 20 outcome scenarios.

The reproducible bundle is 309,347 bytes (95,257 gzip bytes). Frontend formatting,
type checks, artifact hashes, and publication guards pass. Light, dark, and narrow
screenshots were inspected. This redesign has source/browser evidence; the prior
installed-wheel and CI evidence above describes the preceding candidate. Actual
host rendering and user acceptance remain separate from synthetic validation.

## Clipped receipt fallback

Identical truncated before/after previews display an explicit unavailable-passage
message in both summary and details. They remain counted as a saved change.
The view does not highlight identical text or offer excerpt expansion for a
short fallback message. Raw receipt data remains available.

All 89 source tests passed, including the three Chromium tests. The three browser
tests passed again after the final disclosure adjustment. Frontend formatting,
type checks, and reproducible bundle checks passed. Synthetic desktop and 320px
receipt views were inspected. Actual client-host rendering remains unverified.

## Saved record state

Successful single-record receipts show disputed, needs-revalidation, unverifiable,
superseded, and retracted states in the primary view. The label describes the saved
record, not current source freshness. Failure warnings take precedence; replays
do not announce a new saved state. Plain notes and supported records gain no
attention message.

All 89 tests passed, including Chromium checks for each state, failure precedence,
and replay handling. Frontend formatting, types, and reproducible bundle checks
passed. A synthetic native receipt was inspected at desktop and 320px widths.
Maintenance batches and legacy receipts without a top-level record remain outside
this presentation change. Actual client-host rendering remains unverified.

## Replay bookkeeping disclosure

The reserved `kajamite_operations` field is excluded from primary review rows and
their change count. Raw receipts retain the complete field. A bookkeeping-only
receipt still states that record tracking changed; it is not reported as a no-op.
Semantic metadata remains visible. This changes presentation, not stored bytes.

All 89 tests passed, including Chromium checks for semantic-field visibility,
review counts, raw-receipt preservation, and bookkeeping-only outcomes. All three
browser tests passed again after the singular-count wording adjustment. Frontend
checks passed. A synthetic governed receipt showed both text edits and its saved
state while its review count decreased from four to three. Full record metadata
projection and actual client-host acceptance remain open.

## Semantic record changes

Governed receipts project meaningful fields from validated records without decoding
stored journals in the frontend. The primary review separates text edits, status,
scope, evidence-change counts, and verification fields. History and replay objects
remain in raw receipt disclosure. Legacy receipts retain their full metadata row.
This changes review presentation, not stored bytes or source-verification policy.

The 90-test suite passed, including three Chromium tests. Coverage includes scope
addition/removal, stable-ID evidence corrections, create/transition receipts, and
legacy fallback. Frontend formatting, types, and reproducible bundle checks passed.
Native engine commissioning passed persistence, reconnect, revalidation, replay,
MCP/CLI routing, maintenance, and removal checks. A separate synthetic native receipt
showed a text correction, removed scope constraint, evidence correction, and a
scope-only revision with exact readback after reconnect. Its expanded primary view
had matching 320px client and scroll widths. Actual client-host acceptance remains
unverified.
The complete native commissioning entrypoint also passed note operations,
capability checks, and governed engine commissioning. The final three browser
tests passed with maintenance projection coverage enabled.

## Compact supersession references

The 92-test source suite passes, including three Chromium checks. Supersession
can resolve a stored successor by identifier and expected revision. Synthetic
checks cover stale revisions, namespace and scope mismatches, self-supersession,
unchanged records after rejection, preserved history, and operation replay.
Complete native commissioning passes, including compact references through MCP
and readback after reconnect. Installed-package validation for this addition is
tracked separately from the earlier receipt-review wheel.

## Qualified links and search schema

The 94-test source suite passes, including three browser checks. Exact physical
paths with a directory component can omit the Markdown suffix; unrelated fuzzy
matches and bare-title guesses remain rejected. Tests include mutation readback
through a qualified alias. The MCP search schema advertises text, semantic, and
hybrid modes with text as the default; backend capability requirements remain.
Complete native commissioning passes with alias readback and enum assertions.

## Prose-oriented inspection bundles

The 95-test source suite passes, including browser checks and mixed ordinary /
governed inspection. Context budgets count prose rather than serialized history.
Current status, scope, verification, and evidence remain separate; reuse_checked
is false. Complete history remains available through explicit inspection reads.
A clipped governed preview has no paging cursor; callers can request the complete
current record. Full native commissioning passes mixed inspection budgeting.
The read/search/list/context/related schemas expose reuse and inspect explicitly.

## Shared comparison release

Version 0.8.0 adds shared inline/detail line comparison, word-level highlights,
local disclosure with stable focus and reading position, wrapped source text,
unified/split layouts and updated UI resource identity. The knowledge engine,
receipt schema and journal format are unchanged.

Frontend formatting, TypeScript and reproducible bundle checks pass. Sequence
validation preserves exact source and token strings across Unicode, whitespace,
empty values, multiline reflow and the large-input fallback. Browser acceptance
uses real-time Chrome DevTools Protocol through the pinned Node development
runtime. Synthetic host tests retain digest/identity checks, delayed result
ordering, complete claim binding, host refusal/timeouts, themes, source escaping,
semantic fields, partial outcomes and narrow layouts. Pointer and keyboard
checks verify focused-control identity and reading anchors in the packaged UI.

The current pinned build tools have development-only denial-of-service advisories
in `braces` and `source-map-js`. Watcher and source-map packages are not bundled
in the released browser runtime. Builds operate on reviewed repository inputs;
no frontend dependency update is included in this release.

Native host rendering remains a separate observation; synthetic host acceptance
does not establish every client’s placement or accessibility behavior.
