import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from . import __version__
from .config import Settings
try:
    from .backend import connect
    from .server import OPERATIONS, create_server, guide
    from .service import KnowledgeService
except ModuleNotFoundError as error:
    if error.name == "mcp":
        raise SystemExit("The note frontend requires the MCP extra. Install 'kajamite[mcp]'.") from None
    raise


async def execute(args):
    settings = Settings.load(args.config)
    async with connect(settings) as backend:
        service = KnowledgeService(backend)
        if args.command == "serve":
            await backend.check()
            await create_server(service).run_stdio_async()
        elif args.command == "doctor":
            print(json.dumps(await backend.check()))
        else:
            arguments = json.loads(Path(args.arguments).read_text(encoding="utf-8") if args.arguments else "{}")
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be a JSON object")
            method = OPERATIONS[args.operation][0]
            print(json.dumps(await getattr(service, method)(**arguments), ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Knowledge continuity over your existing Basic Memory project")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", default=os.environ.get("KAJAMITE_CONFIG"), help="TOML backend configuration (or KAJAMITE_CONFIG)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="Run the stdio MCP server")
    commands.add_parser("doctor", help="Read-only backend capability and project check")
    commands.add_parser("skill", help="Print the reusable skill for installation in your client")
    call = commands.add_parser("call", help="Call the same operations as MCP")
    call.add_argument("operation", choices=OPERATIONS)
    call.add_argument("--arguments", help="Path to a JSON object of operation arguments")
    args = parser.parse_args()
    if args.command == "skill":
        print(guide())
        return 0
    if not args.config:
        parser.error("--config or KAJAMITE_CONFIG is required")
    try:
        asyncio.run(execute(args))
        return 0
    except (Exception, BaseExceptionGroup) as error:
        # Exception groups from transport shutdown can contain private backend output.
        if isinstance(error, BaseExceptionGroup):
            print("Kajamite backend session failed; inspect configuration and backend availability. A pending change may have committed; read it before retrying.", file=sys.stderr)
        else:
            print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
