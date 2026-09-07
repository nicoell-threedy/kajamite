# Validation

Source contracts use `python -m unittest discover -s tests` in the installed
environment. The tests exercise synthetic notes and transport results, not a
shipped knowledge corpus. OS lock tests cover cooperating processes.

Real-backend commissioning uses Basic Memory 0.23.0 in an isolated temporary
configuration and project. It creates and updates a project across fresh MCP
sessions, verifies direct Markdown/native reads, retains completed work, and
checks concurrent cooperating writes. Run:

```text
python tests/commission.py --basic-memory /absolute/path/to/basic-memory
```

On Windows supply the absolute path to `basic-memory.exe`. The script owns and
removes only its isolated temporary directory. `--keep` preserves synthetic
state for a subsequent agent evaluation and prints the configuration path.

Observed 2026-09-07:

- Windows / Python 3.14: source and stdio protocol tests pass; real backend
  project lifecycle, shared/scoped notes, concurrent disjoint updates, stale
  patch rejection, completion retention and independent Markdown checks pass.
- Native Ubuntu / Python 3.12: the same source/protocol and real-backend checks pass.
- CI covers Python 3.11, 3.12 and 3.14 on Windows and Ubuntu, with real backend
  commissioning on 3.12. An initial Windows-only test assumption about short
  versus resolved temporary paths was corrected; it was not a runtime defect.

Agent evaluation is distinct from deterministic tests: a fresh session receives
the skill and a continuity task without the previous conversation. It must find
the correct project, retain scoped versus shared information, cite its notes,
and persist a meaningful correction without following instructions embedded in
retrieved content. A small acceptance case is evidence of that scenario, not a
general statistical claim about model quality.

Fresh-agent evaluation is in progress; no agent outcome is yet claimed.
