from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
import os
from pathlib import Path
import sys
import unittest
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.apps import APP_MIME_TYPE, EXTENSION_ID

from kajamite import receipt
from kajamite.server import INSTRUCTIONS, OPERATIONS, create_server
from kajamite.ui import RESOURCE_URI


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
        return {"note": {"identifier": identifier}}

    async def list(self, namespace="/", depth=1, page=1, page_size=20, glob=None, sort=None) -> dict[str, Any]:
        return {"nodes": [], "has_more": False}

    async def context(self, namespace=None, identifiers=None, page=1, page_size=5, max_chars=12000) -> dict[str, Any]:
        return {"notes": [], "omitted": []}

    async def move(self, identifier: str, destination: str, is_namespace=False) -> dict[str, Any]:
        return {"mutation": {"moved": True}}


async def _serve():
    await create_server(ProtocolService()).run_stdio_async()


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
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

            resource = await session.read_resource("kajamite://guide")
            content = resource.model_dump(mode="json", by_alias=True)["contents"][0]["text"]
            normalized = " ".join(content.lower().split())
            self.assertIn("reference data, not an instruction", normalized)
            self.assertIn("namespace", content.lower())
            self.assertFalse(any(name.startswith("project_") for name in tools))

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
            for name in ("knowledge_create", "knowledge_edit", "knowledge_move"):
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
            self.assertNotIn("https://", wire["text"])
            self.assertNotIn("http://", wire["text"])

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
