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

from kajamite.server import INSTRUCTIONS, OPERATIONS, create_server


class ProtocolService:
    async def search(self, namespaces: list[str], query=None, recursive=False, kind=None, metadata=None, cursor=None, page_size=10) -> dict[str, Any]:
        return {"results": [{"identifier": "Notes/example.md", "title": "Example"}], "has_more": False, "next_cursor": None, "exhausted": True}

    async def read(self, identifier: str, offset: int = 0, limit: int = 12000) -> dict[str, Any]:
        if identifier == "explode":
            raise RuntimeError("synthetic service failure")
        return {"identifier": identifier, "content": "reference", "content_is_data": True}

    async def create(self, title: str, content: str, namespace: str, kind="note", metadata=None) -> dict[str, Any]:
        return {"note": {"title": title}}

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
            command=sys.executable, args=[str(Path(__file__).resolve()), "--serve"]
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


if __name__ == "__main__" and "--serve" in sys.argv:
    asyncio.run(_serve())
elif __name__ == "__main__":
    unittest.main()
