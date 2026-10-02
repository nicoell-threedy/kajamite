from __future__ import annotations

import asyncio
from html.parser import HTMLParser
from contextlib import AsyncExitStack
from functools import wraps
import os
from pathlib import Path
import subprocess
import sys
import unittest
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.apps import APP_MIME_TYPE, EXTENSION_ID

from kajamite import receipt
from kajamite.errors import MutationUncertain
from kajamite.server import INSTRUCTIONS, OPERATIONS, create_server
from kajamite.ui import RESOURCE_URI
from kajamite.ui import html, resource_uri


SOURCE_ROOT = str(Path(__file__).resolve().parents[1] / "src")


class ProtocolService:
    async def search(self, namespaces: list[str], query=None, recursive=False, kind=None, metadata=None, cursor=None, page_size=10) -> dict[str, Any]:
        return {"results": [{"identifier": "Notes/example.md", "title": "Example"}], "has_more": False, "next_cursor": None, "exhausted": True}

    async def read(self, identifier: str, offset: int = 0, limit: int = 12000) -> dict[str, Any]:
        if identifier == "explode":
            raise RuntimeError("synthetic service failure")
        return {"identifier": identifier, "content": "reference", "content_is_data": True}

    async def create(self, title: str, content: str, namespace: str, kind="note", metadata=None) -> dict[str, Any]:
        note = {
            "title": title,
            "file_path": f"{namespace.strip('/')}/{title}.md",
            "content": content,
            "frontmatter": {"title": title, "type": kind} | (metadata or {}),
        }
        change = receipt.for_create(note)
        return {
            "note": {"title": title},
            "knowledge_change": change,
            "knowledge_change_text": receipt.render(change),
        }

    async def edit(self, identifier: str, find_text=None, replacement=None, metadata=None) -> dict[str, Any]:
        if identifier == "uncertain":
            raise MutationUncertain("Mutation outcome is uncertain; inspect current state before retrying.")
        return {"note": {"identifier": identifier}}

    async def revise(self, identifier: str, expected_content_sha256: str, replacements: list[dict[str, str]], preview=False) -> dict[str, Any]:
        if identifier == "uncertain":
            raise MutationUncertain("Mutation outcome is uncertain; inspect current state before retrying.")
        return {"preview": preview, "note": {"identifier": identifier}}

    async def inspect_collection(self, namespace: str, recursive=True, cursor=None, page_size=20) -> dict[str, Any]:
        return {"namespace": namespace, "notes": [], "candidates": [], "has_more": False,
                "exhausted": True, "next_cursor": None}

    async def list(self, namespace="/", depth=1, page=1, page_size=20, glob=None, sort=None) -> dict[str, Any]:
        return {"nodes": [], "has_more": False}

    async def context(self, namespace=None, identifiers=None, page=1, page_size=5, max_chars=12000) -> dict[str, Any]:
        return {"notes": [], "omitted": []}

    async def related(self, identifier: str, namespaces: list[str], depth: int = 1, max_notes: int = 10, max_chars: int = 12000) -> dict[str, Any]:
        return {"notes": [], "partial": False}

    async def record_maintain(self, namespace: str, condition_id: str, timestamp: str, actor: str, reason: str) -> dict[str, Any]:
        return {"completed": [], "partial": False}

    async def record_remove(self, identifier: str, expected_revision: int) -> dict[str, Any]:
        return {"identifier": identifier, "projection": "absent"}

    async def record_create(self, namespace: str, record: dict[str, Any]) -> dict[str, Any]:
        return {"committed_revision": 1}

    async def record_transition(self, identifier: str, action: str, expected_revision: int, operation_id: str, timestamp: str, actor: str, reason: str, changes: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"committed_revision": expected_revision + 1}

    async def move(self, identifier: str, destination: str, is_namespace=False) -> dict[str, Any]:
        return {"mutation": {"moved": True}}


async def _serve():
    options = {}
    if "--embedded" in sys.argv:
        def wrap_operation(name, method):
            @wraps(method)
            async def invoke(*args, **kwargs):
                result = await method(*args, **kwargs)
                return result | {"receipt_id": "synthetic-receipt", "host_operation": name}
            return invoke
        options = dict(name="Embedding host", version="1", instructions="Host instructions",
                       wrap_operation=wrap_operation)
    if "--themed" in sys.argv:
        options["ui_theme"] = {"light": {"primary": "#123456"}}
    server = create_server(ProtocolService(), **options)
    if "--embedded" in sys.argv:
        @server.tool()
        def host_status() -> str:
            return "ready"
    await server.run_stdio_async()


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_engine_search_schema_advertises_supported_modes(self):
        from kajamite.engine import KnowledgeEngine
        tools = await create_server(KnowledgeEngine(None)).list_tools()
        schema = next(tool.input_schema for tool in tools if tool.name == "knowledge_search")
        self.assertEqual(schema["properties"]["retrieval_mode"]["enum"], ["text", "semantic", "hybrid"])
        self.assertEqual(schema["properties"]["retrieval_mode"]["default"], "text")
        for name in ("knowledge_read", "knowledge_search", "knowledge_list", "knowledge_context", "knowledge_related"):
            item = next(tool.input_schema for tool in tools if tool.name == name)
            self.assertEqual(item["properties"]["mode"]["enum"], ["reuse", "inspect"])
            self.assertEqual(item["properties"]["mode"]["default"], "reuse")

    def test_receipt_ui_renders_grouped_revision_values(self):
        self.assertIn("grouped_exact_replacement", html())

    def test_cli_catalog_and_packaged_guide_match_shared_sources(self):
        environment = os.environ | {"PYTHONPATH": SOURCE_ROOT}
        call_help = subprocess.run(
            [sys.executable, "-m", "kajamite", "call", "--help"], env=environment,
            capture_output=True, text=True, check=True,
        )
        for name in OPERATIONS:
            self.assertIn(name, call_help.stdout)
        skill = subprocess.run(
            [sys.executable, "-m", "kajamite", "skill"], env=environment,
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(
            (Path(SOURCE_ROOT) / "kajamite" / "SKILL.md").read_text(encoding="utf-8"),
            skill.stdout,
        )

    async def test_live_protocol_contract_and_errors(self):
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).resolve()), "--serve"],
            env=os.environ | {"PYTHONPATH": SOURCE_ROOT},
        )
        async with AsyncExitStack() as stack:
            errors = stack.enter_context(open(os.devnull, "w"))
            read, write = await stack.enter_async_context(stdio_client(parameters, errlog=errors))
            session = await stack.enter_async_context(ClientSession(read, write))
            initialized = await session.initialize()
            init = initialized.model_dump(mode="json", by_alias=True)
            self.assertEqual("Kajamite", init["serverInfo"]["name"])
            self.assertEqual(INSTRUCTIONS, init["instructions"])

            listed = await session.list_tools()
            tools = {
                tool.name: tool.model_dump(mode="json", by_alias=True)
                for tool in listed.tools
            }
            self.assertEqual(set(OPERATIONS), set(tools))
            self.assertEqual(
                {"identifier", "offset", "limit"},
                set(tools["knowledge_read"]["inputSchema"]["properties"]),
            )
            self.assertTrue(tools["knowledge_read"]["annotations"]["readOnlyHint"])
            self.assertTrue(tools["knowledge_edit"]["annotations"]["destructiveHint"])
            self.assertTrue(tools["knowledge_revise"]["annotations"]["destructiveHint"])
            self.assertEqual(
                {"identifier", "expected_content_sha256", "replacements", "preview"},
                set(tools["knowledge_revise"]["inputSchema"]["properties"]),
            )
            self.assertTrue(tools["knowledge_inspect_collection"]["annotations"]["readOnlyHint"])
            self.assertEqual(
                {"namespace", "recursive", "cursor", "page_size"},
                set(tools["knowledge_inspect_collection"]["inputSchema"]["properties"]),
            )
            self.assertFalse(tools["knowledge_create"]["annotations"]["openWorldHint"])

            result = await session.call_tool("knowledge_search", {"namespaces": ["Notes"], "query": "example"})
            data = result.model_dump(mode="json", by_alias=True)
            self.assertFalse(data["isError"])
            self.assertEqual(
                "Notes/example.md",
                data["structuredContent"]["results"][0]["identifier"],
            )

            missing = await session.call_tool("knowledge_read", {})
            self.assertTrue(missing.is_error)
            failed = await session.call_tool("knowledge_read", {"identifier": "explode"})
            self.assertTrue(failed.is_error)
            self.assertNotIn("synthetic service failure", str(failed.content))
            uncertain = await session.call_tool("knowledge_edit", {"identifier": "uncertain"})
            self.assertTrue(uncertain.is_error)
            self.assertIn("inspect current state before retrying", str(uncertain.content))

            resource = await session.read_resource("kajamite://guide")
            content = resource.model_dump(mode="json", by_alias=True)["contents"][0]["text"]
            normalized = " ".join(content.lower().split())
            self.assertIn("reference data, not an instruction", normalized)
            self.assertIn("namespace", content.lower())
            self.assertFalse(any(name.startswith("project_") for name in tools))

    async def test_embedding_preserves_catalog_resources_receipts_and_errors(self):
        async with AsyncExitStack() as stack:
            sessions = []
            for extra in ([], ["--embedded"]):
                parameters = StdioServerParameters(
                    command=sys.executable,
                    args=[str(Path(__file__).resolve()), "--serve", *extra],
                    env=os.environ | {"PYTHONPATH": SOURCE_ROOT},
                )
                errors = stack.enter_context(open(os.devnull, "w"))
                read, write = await stack.enter_async_context(stdio_client(parameters, errlog=errors))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                sessions.append(session)
            standalone, embedded = sessions
            expected = {t.name: t.model_dump() for t in (await standalone.list_tools()).tools}
            actual = {t.name: t.model_dump() for t in (await embedded.list_tools()).tools}
            self.assertIn("host_status", actual)
            self.assertEqual(expected, {k: actual[k] for k in expected})
            for uri in (RESOURCE_URI, "kajamite://guide"):
                self.assertEqual((await standalone.read_resource(uri)).contents,
                                 (await embedded.read_resource(uri)).contents)
            result = await embedded.call_tool("knowledge_create", {
                "title": "Example", "content": "stored value", "namespace": "Synthetic"})
            self.assertFalse(result.is_error)
            self.assertEqual("synthetic-receipt", result.structured_content["receipt_id"])
            self.assertEqual("create", result.structured_content["knowledge_change"]["operation"])
            self.assertIn("Knowledge change: create", result.structured_content["knowledge_change_text"])
            uncertain = await embedded.call_tool("knowledge_edit", {"identifier": "uncertain"})
            self.assertTrue(uncertain.is_error)
            self.assertNotIn("knowledge_change", str(uncertain.content))
            failed = await embedded.call_tool("knowledge_read", {"identifier": "explode"})
            self.assertTrue(failed.is_error)
            self.assertNotIn("synthetic service failure", str(failed.content))

    async def test_adopter_theme_is_on_resource_not_tool_results(self):
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).resolve()), "--serve", "--themed"],
            env=os.environ | {"PYTHONPATH": SOURCE_ROOT},
        )
        async with AsyncExitStack() as stack:
            errors = stack.enter_context(open(os.devnull, "w"))
            read, write = await stack.enter_async_context(stdio_client(parameters, errlog=errors))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            theme_uri = resource_uri({"light": {"primary": "#123456"}})
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            self.assertEqual(theme_uri, tools["knowledge_create"].meta["ui"]["resourceUri"])
            resource = await session.read_resource(theme_uri)
            self.assertIn('#123456', resource.contents[0].text)
            result = await session.call_tool("knowledge_create", {
                "title": "Example", "content": "Synthetic", "namespace": "Demo"})
            self.assertNotIn('#123456', str(result))
            self.assertNotIn('ui_theme', str(result))

    async def test_mutations_advertise_read_only_apps_card_with_plain_fallback(self):
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).resolve()), "--serve"],
            env=os.environ | {"PYTHONPATH": SOURCE_ROOT},
        )
        async with AsyncExitStack() as stack:
            errors = stack.enter_context(open(os.devnull, "w"))
            read, write = await stack.enter_async_context(stdio_client(parameters, errlog=errors))
            session = await stack.enter_async_context(ClientSession(
                read,
                write,
                extensions={EXTENSION_ID: {"mimeTypes": [APP_MIME_TYPE]}},
            ))
            discovered = await session.discover()
            discovery = discovered.model_dump(mode="json", by_alias=True)
            self.assertIn(EXTENSION_ID, discovery["capabilities"]["extensions"])

            listed = await session.list_tools()
            tools = {
                tool.name: tool.model_dump(mode="json", by_alias=True)
                for tool in listed.tools
            }
            for name in ("knowledge_create", "knowledge_edit", "knowledge_revise", "knowledge_move", "knowledge_record_maintain"):
                self.assertEqual(RESOURCE_URI, tools[name]["_meta"]["ui"]["resourceUri"])
            self.assertIsNone(tools["knowledge_read"]["_meta"])

            resources = await session.list_resources()
            app = next(item for item in resources.resources if str(item.uri) == RESOURCE_URI)
            self.assertEqual(APP_MIME_TYPE, app.mime_type)
            self.assertEqual([], app.meta["ui"]["csp"]["connectDomains"])
            self.assertEqual([], app.meta["ui"]["csp"]["resourceDomains"])
            loaded = await session.read_resource(RESOURCE_URI)
            wire = loaded.model_dump(mode="json", by_alias=True)["contents"][0]
            self.assertEqual(APP_MIME_TYPE, wire["mimeType"])
            self.assertIn("ui/notifications/tool-result", wire["text"])
            class Resources(HTMLParser):
                external = []
                def handle_starttag(self, tag, attrs):
                    if tag in {"script", "link", "img", "iframe"}:
                        self.external.extend((k, v) for k, v in attrs if k in {"src", "href"})
            resource_parser = Resources()
            resource_parser.feed(wire["text"])
            self.assertEqual([], resource_parser.external)

            result = await session.call_tool("knowledge_create", {
                "title": "Example", "content": "stored value", "namespace": "Synthetic"
            })
            output = result.model_dump(mode="json", by_alias=True)["structuredContent"]
            self.assertEqual("create", output["knowledge_change"]["operation"])
            self.assertEqual(
                "stored value", output["knowledge_change"]["body_change"]["after"]["preview"]
            )
            self.assertIn("Knowledge change: create", output["knowledge_change_text"])
            self.assertIn("Coverage: kajamite_operation", output["knowledge_change_text"])


if __name__ == "__main__" and "--serve" in sys.argv:
    asyncio.run(_serve())
elif __name__ == "__main__":
    unittest.main()
