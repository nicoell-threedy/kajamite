# Basic Memory capability audit

This audit targets Basic Memory 0.23.0 through its public MCP tools.
The installed Python package and tool schemas supplied the interface evidence.
`tests/capability_audit.py` supplied isolated runtime evidence on Linux Python 3.12.
It used synthetic notes and disabled semantic indexing explicitly.

| Capability | Observed interface and behavior | Engine use or limit |
| --- | --- | --- |
| Observation retrieval | `search_notes`, `entity_types=["observation"]`, `categories=["fact"]` returned the matching observation and note path. | Expose item types and exact category filters. |
| Typed relations | `build_context` returned a `depends_on` relation and resolved target. | Use native graph discovery. Ordinary relation labels do not establish evidence dependencies. |
| Graph context | Related entities include physical note paths. `timeframe=None` removes the default seven-day window. | Read current notes through engine policy after graph discovery. Bound depth and output. |
| Metadata | `write_note` and `read_note` preserved a nested metadata object. | Keep the engine envelope separate from backend title, type, and permalink fields. |
| Full-text search | Explicit `search_type="text"` supports the synthetic corpus. | Retain bounded continuation for sparse namespace matches. |
| Directory filtering | The public search schema has no physical-directory parameter. | Filter canonical paths after native pages. Never claim a partial scan proves absence. |
| Semantic and hybrid search | The schema accepts these modes. They require backend model configuration. | Expose explicit opt-in modes without enabling or downloading a model through Kajamite. No semantic recall claim follows from schema support. |
| Stable addresses | Reads and graph results supply physical paths and permalinks. | Validate exact readback. Preserve returned addresses across moves. |
| Native deletion | `delete_note` returned `deleted=true` with the removed physical path. | Remove one exact selected note. Check the active projection separately. |
| Revision compare | `edit_note` has replacement-count validation but no expected-revision parameter. | Serialize cooperating writers and compare before writing. Do not claim protection from external writers. |
| Index convergence | A new readable note can precede its search result. | Use bounded convergence checks in acceptance. Distinguish durable content from the search projection. |
| Schema tools | The tool catalog includes schema tools. | Schema validation does not replace lifecycle, evidence, or request policy. No runtime dependency on backend schemas is needed. |

## Replay

From an installed development environment, run:

```sh
python tests/capability_audit.py --basic-memory /path/to/basic-memory
```

Expected result: `status: passed` and five named capability checks.
The harness owns temporary projects and removes only its synthetic state.
The ordinary commissioning suite retains move, concurrent-writer, and pagination checks.

## Configuration boundary

Basic Memory can enable semantic search by default in a new configuration.
A native indexing request can then load a local embedding model.
The acceptance harness disables this behavior for deterministic full-text tests.
Model configuration, credentials, and model downloads remain backend deployment concerns.

Kajamite uses a public MCP client for this adapter.
An embedded application does not run the Kajamite MCP server.
The engine and its backend protocol do not import the MCP SDK.
A consumer can supply another backend implementation without installing the MCP extra.

## Sources

- https://docs.basicmemory.com/reference/mcp-tools-reference
- https://docs.basicmemory.com/concepts/observations-and-relations
- https://docs.basicmemory.com/concepts/semantic-search
- Basic Memory 0.23.0 public tool catalog and isolated acceptance, 2026-09-10.

Current website documentation can describe newer behavior.
The versioned runtime evidence above controls this adapter contract.
