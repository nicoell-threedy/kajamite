"""Synthetic MCP host used only by the native engine commission test."""
import argparse
import asyncio

from kajamite.backend import connect
from kajamite.config import Settings
from kajamite.engine import KnowledgeEngine
from kajamite.server import create_server


SCOPE = {"system": "example", "version": "1"}


def checker(record, scope):
    evidence = record.get("evidence", {}).get("manual", {})
    return {"outcome": "unchanged"} if scope == SCOPE and evidence.get("reference") == "example:manual@1" else {"outcome": "missing"}


async def main(config):
    settings = Settings.load(config)
    async with connect(settings) as backend:
        await create_server(KnowledgeEngine(backend, evidence_checker=checker)).run_stdio_async()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    arguments = parser.parse_args()
    asyncio.run(main(arguments.config))
