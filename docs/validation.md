# Validation

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
