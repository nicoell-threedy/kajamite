"""Real-backend acceptance using only synthetic, isolated temporary knowledge.

Run with Kajamite installed: python tests/commission.py --basic-memory /path/to/basic-memory
The harness owns its temporary backend project; normal Kajamite never creates one.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from kajamite.backend import unpack


async def call(config, name, arguments):
    params = StdioServerParameters(command=sys.executable, args=["-m", "kajamite", "--config", str(config), "serve"])
    with open(os.devnull, "w") as err:
        async with stdio_client(params, errlog=err) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=90) as session:
                await session.initialize()
                return unpack(await session.call_tool(name, arguments))


def prepare(root, command):
    env = os.environ | {
        "BASIC_MEMORY_CONFIG_DIR": str(root / "backend-config"),
        "BASIC_MEMORY_HOME": str(root / "default"),
        "BASIC_MEMORY_FORCE_LOCAL": "true", "BASIC_MEMORY_AUTO_UPDATE": "false",
        "BASIC_MEMORY_NO_PROMOS": "1", "BASIC_MEMORY_LOGFIRE_ENABLED": "false",
    }
    wiki = root / "notes"
    wiki.mkdir(exist_ok=True)
    result = subprocess.run([command, "project", "add", "acceptance", str(wiki)], env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Isolated backend project setup failed: " + result.stderr[-1500:])
    config = root / "kajamite.toml"
    values = {key: value for key, value in env.items() if key.startswith("BASIC_MEMORY_")}
    config.write_text(f'state_dir = {json.dumps(str(root / "locks"))}\n[backend]\ncommand = {json.dumps(command)}\nargs = ["mcp", "--project", "acceptance"]\nproject = "acceptance"\ntimeout = 90\n[backend.env]\n' + "\n".join(f'{key} = {json.dumps(value)}' for key, value in values.items()), encoding="utf-8")
    return config, wiki


async def run(config, wiki):
    created = await call(config, "project_create", {"title": "Observatory visit", "objective": "Plan an accessible evening visit."})
    identifier = created["note"]["identifier"]
    await call(config, "project_update", {"identifier": identifier, "find_text": "Active.", "replacement": "Decision: Saturday.\nBudget for this project: 80 units.\n- [ ] Reserve admission."})
    shared = await call(config, "knowledge_create", {"title": "Access preference", "kind": "preference", "content": "Prefer step-free routes."})
    await call(config, "knowledge_create", {"title": "Visit transport", "content": "Use the evening shuttle.", "project": identifier})
    resumed = await call(config, "project_resume", {"identifier": identifier})
    assert "Saturday" in resumed["project"]["content"]
    assert any(item["title"] == "Visit transport" for item in resumed["related"]["results"])
    assert "kajamite_project" not in shared["note"]["metadata"]
    # Separate processes must retain disjoint edits even when they start together.
    await asyncio.gather(
        call(config, "project_update", {"identifier": identifier, "find_text": "Saturday", "replacement": "Sunday"}),
        call(config, "project_update", {"identifier": identifier, "find_text": "80 units", "replacement": "90 units"}),
    )
    corrected = await call(config, "knowledge_read", {"identifier": identifier})
    assert "Sunday" in corrected["content"] and "90 units" in corrected["content"]
    assert "Saturday" not in corrected["content"]
    # A stale patch is an error, not a successful no-op or overwrite.
    try:
        await call(config, "project_update", {"identifier": identifier, "find_text": "Saturday", "replacement": "Monday"})
    except Exception:
        pass
    else:
        raise AssertionError("stale edit succeeded")
    await call(config, "project_update", {"identifier": identifier, "status": "completed"})
    active = await call(config, "project_list", {})
    assert all(row["identifier"] != identifier for row in active["results"])
    complete = await call(config, "project_resume", {"identifier": identifier})
    assert complete["project"]["metadata"]["status"] == "completed"
    assert "Sunday" in complete["project"]["content"]
    # Independently inspect Markdown, not only the wrapper's assertions.
    markdown = (wiki / complete["project"]["file_path"]).read_text(encoding="utf-8")
    assert "status: completed" in markdown and "Sunday" in markdown and "90 units" in markdown
    assert len(list(wiki.rglob("*.md"))) == 3
    return {"status": "passed", "project": identifier,
            "checks": ["fresh-session resume", "scoped notes", "shared preference", "concurrent writers", "stale patch rejection", "completion retention", "plain Markdown"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--basic-memory", required=True)
    parser.add_argument("--keep", action="store_true", help="Keep isolated synthetic data for agent evaluation")
    args = parser.parse_args()
    if args.keep:
        root = Path(tempfile.mkdtemp(prefix="kajamite-acceptance-"))
        config, wiki = prepare(root, args.basic_memory)
        result = asyncio.run(run(config, wiki))
        print(json.dumps(result | {"config": str(config), "root": str(root)}))
    else:
        with tempfile.TemporaryDirectory(prefix="kajamite-acceptance-") as directory:
            config, wiki = prepare(Path(directory), args.basic_memory)
            print(json.dumps(asyncio.run(run(config, wiki))))


if __name__ == "__main__":
    main()
