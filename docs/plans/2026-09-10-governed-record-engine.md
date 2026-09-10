# Governed Record Engine Implementation Plan

**Goal:** Let Python consumers maintain evidence-backed records with portable history and deterministic lifecycle transitions.

**Approach:** Add an optional in-process record engine with consumer-supplied evidence validation and serialization identity. Keep ordinary note operations unchanged.

**Context:** Note tools currently treat all status metadata as ordinary caller data. A separate explicit engine can enforce governed-record semantics without making every note a governed record.

### Task 1: Independent record lifecycle

**Files:** Create `src/kajamite/governance.py` and `tests/test_governance.py`.

- [x] Implement creation, revision, dispute, revalidation, supersession, retraction, deterministic source-change transitions, and Markdown round trips.
- [x] Validate complete event snapshots, verification revisions, timestamps, and evidence references.
- [x] Supply generic defaults and explicit consumer hooks without importing a server, model, credentials, or exporter.
- [x] Demonstrate two independent engine configurations and content-free operation summaries.

### Task 2: Embedding and compatibility

- [x] Document the Python API and its persistence and retrieval boundaries.
- [x] Keep the existing note/protocol tests passing.
- [x] Verify engine-only installation independently from MCP frontend dependencies.
- [x] Run `python -m unittest discover -s tests`: all 30 tests passed on Windows.
- [x] Complete staged-content and full reachable-history publication checks.

### Outcome

The engine supports an independent Python consumer with no runtime dependencies.
The MCP frontend is available through the `mcp` extra. Six synthetic engine
tests and the existing 24 tests passed. No native-backend or Linux rerun is
claimed for this increment.

### Adoption boundary

The initial engine produces validated values; the consumer owns atomic persistence, authorization, projection updates, and retrieval filtering. Ordinary Basic Memory tools must not be presented as governance enforcement. Shared storage and governed retrieval require their own acceptance evidence before becoming public tool behavior.
