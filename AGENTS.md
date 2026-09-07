# Kajamite development

Read `docs/design.md` before changing storage or operation semantics. Keep the
package independent of its consumers and access Basic Memory through public MCP
tools. Notes remain ordinary Markdown owned by the configured backend.

Use the standard library before adding dependencies. Keep the MCP surface small,
with explicit argument/result semantics and honest pagination and mutation errors.
No source credentials, personal knowledge, deployment configuration, logs or
provider exports belong in this repository. Use synthetic data for tests.

Run `python -m unittest discover -s tests` in the installed environment. For
backend behavior changes run `python tests/commission.py --basic-memory <path>`
against a separately installed Basic Memory; it creates only isolated test state.
Keep `docs/validation.md` accurate about what was actually tested.

The packaged `src/kajamite/SKILL.md` and installable `skills/kajamite/SKILL.md`
must stay identical. Dependency changes update `uv.lock` and regenerate the
hashed pip lock using `uv export --locked --no-emit-project --no-header --format
requirements-txt --output-file requirements.lock`. Never put machine paths in
generated lock headers.
