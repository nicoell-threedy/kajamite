# Validation

Source contracts use `python -m unittest discover -s tests` in the installed
environment. The tests exercise synthetic notes and transport results, not a
shipped knowledge corpus. OS lock tests cover cooperating processes.

Real-backend commissioning uses Basic Memory 0.23.0 in an isolated temporary
configuration and project. It creates and updates a project across fresh MCP
sessions, verifies direct Markdown/native reads, retains completed work, and
checks concurrent cooperating writes. Run instructions and observed platform
results are added when commissioning is complete.

Agent evaluation is distinct from deterministic tests: a fresh session receives
the skill and a continuity task without the previous conversation. It must find
the correct project, retain scoped versus shared information, cite its notes,
and persist a meaningful correction without following instructions embedded in
retrieved content. A small acceptance case is evidence of that scenario, not a
general statistical claim about model quality.

Current status: implementation and commissioning in progress. No live or agent
evaluation is claimed by the existence of this document.
