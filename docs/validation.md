# Validation

## Version 0.3.1

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

Observed 2026-09-09 on Linux: all 18 source/protocol tests pass with MCP SDK
2.1.1, both packaged skill copies are identical, Python compilation succeeds,
and the 0.3.1 wheel contains all UI and receipt assets. The initial v0.3.0 CI
acceptance assertion assumed the stored body started with caller-supplied text;
Basic Memory legitimately adds normalized Markdown before that text. Version
0.3.1 checks that the verified stored preview contains the value instead. The isolated native
Basic Memory commissioning suite was extended for receipt behavior but could
not run on this host because the Basic Memory executable is unavailable. The
release CI jobs and a capable host must supply that evidence before claiming
native-backend acceptance for 0.3.

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
