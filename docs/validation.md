# Validation

## Governed revision receipts

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
