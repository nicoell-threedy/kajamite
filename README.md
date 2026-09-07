# Kajamite

Shared knowledge and project continuity for AI assistants, built on Basic Memory.

Kajamite helps an assistant continue work across conversations and directories.
Projects, decisions, open questions, next actions and shared knowledge remain
ordinary Markdown notes in your existing Basic Memory project. The MCP supplies
consistent operations; the accompanying skill teaches when and how to use them.

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
| `knowledge_search` | Find shared or project-associated notes with pagination |
| `knowledge_read` | Read exact notes with explicit content bounds |
| `knowledge_create` | Capture a focused note without overwriting another |
| `knowledge_edit` | Correct one exact previously read passage |
| `project_create` | Start an undertaking inside the existing knowledge base |
| `project_list` | Discover active projects, or include other lifecycle states |
| `project_resume` | Recover project state, associated notes and linked context |
| `project_update` | Revise state or mark a project paused/completed/cancelled |

`kajamite call TOOL --arguments /path/to/arguments.json` invokes the same operations
from a JSON argument file. Use `--config` before `call`. The CLI returns JSON and
a nonzero exit code on failure. A completed project remains readable and searchable.

## Ownership and operation

Kajamite stores no knowledge database and does not install, repoint, or delete
Basic Memory projects. The consumer owns the backend, credentials, backups,
source integrations, scheduling and durable binary artifacts. Existing notes
work unchanged; project metadata is introduced only when you create projects.

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
