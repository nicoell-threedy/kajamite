"""Public MCP adapter. Knowledge never passes through a local shadow store."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import PaginatedRequestParams

from .config import Settings


from .errors import BackendError


def unpack(result):
    data = result.model_dump(mode="json", by_alias=True)
    if data.get("isError"):
        raise BackendError("Basic Memory rejected the operation. Read the current note before retrying a change.")
    payload = data.get("structuredContent")
    if isinstance(payload, dict) and set(payload) == {"result"}:
        payload = payload["result"]
    if not isinstance(payload, dict):
        payload = None
        for item in data.get("content", []):
            if item.get("type") == "text":
                try:
                    candidate = json.loads(item["text"])
                except (ValueError, TypeError):
                    continue
                if isinstance(candidate, dict):
                    payload = candidate
                    break
    if not isinstance(payload, dict):
        raise BackendError("Basic Memory returned no structured result; check backend compatibility.")
    if payload.get("error") or payload.get("status") == "error":
        raise BackendError("Basic Memory reported an operation error; read current state before retrying.")
    return payload


@asynccontextmanager
async def file_lock(path, timeout=60):
    """Serialize cooperating processes on this host; never lock note files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    acquired = False
    try:
        if handle.seek(0, 2) == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = time.monotonic() + timeout
        while not acquired:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError:
                if time.monotonic() >= deadline:
                    raise BackendError("Another knowledge mutation is still running; no new write was started.")
                await asyncio.sleep(0.05)
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


class Backend:
    def __init__(self, session, settings):
        self.session = session
        self.settings = settings
        self.project = settings.project

    def mutation(self):
        return file_lock(self.settings.lock_path(), self.settings.timeout)

    async def call(self, name, arguments):
        if name == "search_notes" and arguments.get("search_type") in {"semantic", "hybrid", "vector"} and not self.settings.semantic_search:
            raise BackendError("Semantic retrieval requires explicit backend.semantic_search=true and a configured backend model.")
        args = dict(arguments)
        args.update(project=self.project, output_format="json")
        if self.settings.project_id:
            args["project_id"] = self.settings.project_id
        start = time.monotonic()
        outcome = "error"
        try:
            result = await self.session.call_tool(name, args, read_timeout_seconds=self.settings.timeout)
            payload = unpack(result)
            outcome = "ok"
            return payload
        except BackendError:
            raise
        except Exception as error:
            mutation = name in {"write_note", "edit_note", "move_note", "delete_note"}
            detail = " A change may have committed; read the note before retrying." if mutation else " No result is available."
            raise BackendError("Basic Memory transport failed." + detail) from error
        finally:
            self._telemetry(name, outcome, (time.monotonic() - start) * 1000)

    def _telemetry(self, name, outcome, duration):
        path = self.settings.telemetry_file
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"operation": name, "outcome": outcome,
                                         "duration_ms": round(duration, 2)}) + "\n")
        except OSError:
            pass  # Optional observability must not prevent knowledge access.

    async def check(self):
        catalog, cursor = {}, None
        while True:
            result = await self.session.list_tools(params=PaginatedRequestParams(cursor=cursor) if cursor else None)
            for tool in result.tools:
                catalog[tool.name] = tool.model_dump(by_alias=True)["inputSchema"]
            cursor = result.model_dump(by_alias=True).get("nextCursor")
            if not cursor:
                break
        required = {"search_notes": {"metadata_filters", "output_format"},
                    "read_note": {"output_format"}, "write_note": {"metadata", "overwrite"},
                    "edit_note": {"metadata", "expected_replacements"},
                    "list_directory": {"dir_name", "page", "page_size", "output_format"},
                    "move_note": {"destination_path", "is_directory", "output_format"}}
        for name, fields in required.items():
            if not fields <= set(catalog.get(name, {}).get("properties", {})):
                raise BackendError(f"Basic Memory tool {name} is missing required parameters.")
        await self.call("search_notes", {"query": None, "page_size": 1, "entity_types": ["entity"]})
        return {"status": "ready", "backend": "Basic Memory", "project": self.project,
                "tools": sorted(required),
                "capabilities": {
                    "observation_search": "entity_types" in catalog.get("search_notes", {}).get("properties", {}),
                    "category_filter": "categories" in catalog.get("search_notes", {}).get("properties", {}),
                    "graph_context": "build_context" in catalog,
                    "delete_note": "delete_note" in catalog,
                    "native_path_filter": False,
                    "atomic_compare_and_swap": False,
                    "semantic_search": "enabled_by_consumer" if self.settings.semantic_search else "disabled",
                }}


@asynccontextmanager
async def connect(settings: Settings):
    parameters = StdioServerParameters(command=settings.command, args=settings.args,
                                       env=os.environ | settings.env)
    # Backend stdout remains protocol-only; raw backend stderr could contain note data.
    with open(os.devnull, "w") as errors:
        async with stdio_client(parameters, errlog=errors) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=settings.timeout) as session:
                await session.initialize()
                yield Backend(session, settings)
