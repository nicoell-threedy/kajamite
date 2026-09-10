# Kajamite

Shared knowledge access through namespaces, built on Basic Memory.

Kajamite gives assistants explicit namespace access to an existing Markdown
knowledge base. A namespace is an ordinary directory: no registration, mandatory
overview, project object or lifecycle is required. Work with one note or several,
link related knowledge, and preserve useful context across conversations.

## Install

Use Python 3.11 or newer on Windows or Linux. Install and configure Basic Memory
separately; this release is tested against 0.23.0. Select an existing project.
Disable Basic Memory auto-update for a version-managed deployment.

Clone this repository and create a virtual environment:

```sh
python -m venv .venv
```

Use `.venv/bin/python` on Linux or `.venv/Scripts/python.exe` on Windows:

```sh
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-deps .
```

In those two commands, replace `python` with the virtual environment's interpreter.
For development with uv, `uv sync --locked` uses the checked-in dependency lock.

Create a private TOML configuration outside version control:

```toml
[backend]
command = "basic-memory"
args = ["mcp", "--project", "personal"]
project = "personal"
timeout = 60

[backend.env]
BASIC_MEMORY_AUTO_UPDATE = "false"
```

Replace `personal` with your existing Basic Memory project. An absolute command
path is recommended. Set `project_id` too when a UUID is needed to disambiguate
projects. Configuration executes an operator-selected command, never note content.
TOML Windows paths should use literal single-quoted strings or escaped backslashes.

Run `kajamite --config /path/to/config.toml doctor`, then register this stdio
command in your MCP client:

```text
kajamite --config /path/to/config.toml serve
```

Use the installed executable's absolute path in client configuration.
`KAJAMITE_CONFIG` is an alternative to `--config`. Keep stdio private; for remote
use, run the same command through an existing authenticated SSH connection.
Kajamite opens no network listener.

## Teach the assistant

Install [skills/kajamite/SKILL.md](skills/kajamite/SKILL.md) using your client's
project-local skill mechanism, or run `kajamite skill` to print it. The same guide
is available as the `kajamite://guide` MCP resource. No particular client plugin
or lifecycle hook is required.

## Tools

| Tool | Purpose |
| --- | --- |
| `knowledge_list` | Browse notes and child namespaces with depth and pagination |
| `knowledge_search` | Full-text search explicit namespaces with honest scan continuation |
| `knowledge_read` | Read an exact note with content bounds |
| `knowledge_context` | Gather several notes under one shared body-character budget |
| `knowledge_create` | Write supplied content/metadata into an explicit namespace |
| `knowledge_edit` | Guarded body edits and/or metadata merges |
| `knowledge_move` | Move a note or namespace through the backend |

Creation takes `namespace`, not a local filesystem directory. Search requires
`namespaces`; `recursive=true` includes descendants. `namespaces=["/"]` with
`recursive=true` selects the entire configured base. A context request takes
one namespace or a list of exact identifiers, without implicitly following links.
Use canonical returned paths, including their case. Bare note titles are not
addresses. Metadata edits merge top-level keys; supplied values replace those
keys. The backend does not support deleting keys or changing reserved
title/type/permalink fields through metadata edits.

## Mutation receipts and optional UI

Each successful create, edit, or move returns a deterministic
`knowledge_change` receipt plus a labeled `knowledge_change_text` rendering.
Receipts identify the operation and affected path, show bounded readable changed
values and metadata, include full-value hashes, state whether readback verified
the result, and label their coverage as the current Kajamite operation only.
They are evidence from the tool result, independent of the assistant's summary.

Compatible MCP Apps hosts can render the same receipt in a compact read-only
card. The packaged card makes no network requests and offers no mutation actions.
Clients without custom UI—including mobile surfaces where it is unavailable—use
the structured and labeled text result. Kajamite does not store a receipt history;
Git remains the durable backstop for all repository changes, including writes
made outside Kajamite.

`kajamite call TOOL --arguments /path/to/arguments.json` invokes the same operations
from a JSON argument file. Use `--config` before `call`. The CLI returns JSON and
a nonzero exit code on failure. Metadata does not implicitly hide notes or select a lifecycle.

## Search and context limits

Basic Memory 0.23.0 exposes no directory filter on its MCP search tool. Kajamite
therefore uses explicit **full-text** retrieval, pages through ranked results,
and matches physical file paths to the selected namespaces. Each call scans at
most five native pages of 50 results. When incomplete it returns `has_more=true`
and `next_cursor`, even if no scoped match has been found yet. Continue with the
same search arguments and cursor before concluding there are no matches.

This supports late matches without a second index or copied membership metadata.
It is not scoped semantic search, and broad sparse queries may take several
calls. Cursors are live pagination, not immutable snapshots: concurrent backend
changes can change ranking. Lists use native page pagination. Context budgets
cover note-body characters; structured metadata and listing overhead are separate.

## Upgrading

Version 0.2 removes the four `project_*` tools and the special `project` argument.
Use namespaces, normal note links and optional metadata instead. No note migration
runs: existing `type: project`, status values and legacy membership fields remain
readable user data. Update the skill and client tool approvals with the package.
Version 0.3 keeps those tool contracts and adds mutation receipt fields plus an
optional MCP Apps presentation; it performs no data migration.

## Ownership and operation

Kajamite stores no knowledge database and does not install, repoint, or delete
Basic Memory projects. The consumer owns the backend, credentials, backups,
source integrations, scheduling and durable binary artifacts. Existing folders and notes work unchanged. No namespace metadata is injected.

Cooperating writes serialize on the Kajamite host. Use one canonical host and
one shared `state_dir` for deployments addressing the same backend through
different command aliases. Direct backend tools and human editors do not honor
that lock; guarded text replacement is not universal compare-and-swap. Read
current state after an interrupted write before retrying.

Telemetry is off by default. An optional top-level `telemetry_file` path records
operation names, outcomes and durations only. Operators control its retention.
Telemetry failure never prevents knowledge access.

Uninstalling Kajamite leaves your notes and Basic Memory intact. Restore a direct
Basic Memory client connection to continue using the same Markdown.

## Development and validation

Run `python -m unittest discover -s tests` in the installed environment.
[Design and research](docs/design.md) describe the contract and limits;
[validation](docs/validation.md) records tested behavior and how to repeat it.
Tests use synthetic data in temporary directories, with no bundled knowledge corpus.

Kajamite takes its name from Kaja'mite in Warcraft lore. This independent project
contains no game assets and is not affiliated with Blizzard Entertainment.

Licensed under [MIT](LICENSE).

### Publication checks

Enable the local commit and push checks in each developer clone:

```sh
git config core.hooksPath .githooks
```

Run `python tools/check_publication.py HEAD` to check reachable history.
The normal test suite checks the index and available checkout history.
CI uses a shallow checkout, so local pre-push checks provide the full-history check.
These checks detect known private identifiers and selected credential, address,
and machine-path patterns. They do not replace review for private context or
comprehensive secret scanning. Commit author names and email addresses are allowed.
