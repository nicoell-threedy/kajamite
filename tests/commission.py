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
from kajamite.config import Settings


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
    shared = await call(config, "knowledge_create", {"title": "Access", "namespace": "Personal", "kind": "preference", "content": "Prefer step-free routes."})
    created = await call(config, "knowledge_create", {"title": "Plan", "namespace": "Visits/Observatory", "content": "Day: Saturday. Budget: 80 units.\n- [ ] Reserve admission.", "metadata": {"status": "tentative", "custom": {"keep": True}}})
    identifier = created["note"]["identifier"]
    await call(config, "knowledge_create", {"title": "Transport", "namespace": "Visits/Observatory", "content": "Take the evening shuttle."})
    await call(config, "knowledge_create", {"title": "Plan", "namespace": "Visits/Observatory-old", "content": "Day: Friday."})
    listing = await call(config, "knowledge_list", {"namespace": "Visits/Observatory"})
    assert len(listing["nodes"]) == 2
    context = await call(config, "knowledge_context", {"namespace": "Visits/Observatory"})
    assert len(context["notes"]) == 2
    assert all(note["file_path"].startswith("Visits/Observatory/") for note in context["notes"])
    await call(config, "knowledge_edit", {"identifier": identifier, "metadata": {"status": "booked"}})
    await asyncio.gather(
        call(config, "knowledge_edit", {"identifier": identifier, "find_text": "Saturday", "replacement": "Sunday"}),
        call(config, "knowledge_edit", {"identifier": identifier, "find_text": "80 units", "replacement": "90 units"}),
    )
    corrected = await call(config, "knowledge_read", {"identifier": identifier})
    assert "Sunday" in corrected["content"] and "90 units" in corrected["content"]
    assert corrected["metadata"]["custom"] == {"keep": True}
    assert corrected["metadata"]["status"] == "booked"
    assert "kajamite_project" not in corrected["metadata"]
    await call(config, "knowledge_move", {"identifier": "Visits/Observatory/Transport.md", "destination": "Visits/Observatory/Logistics.md"})
    try:
        await call(config, "knowledge_move", {"identifier": "Visits/Observatory/Logistics.md", "destination": identifier})
    except Exception:
        pass
    else:
        raise AssertionError("move overwrote an existing note")
    await call(config, "knowledge_move", {"identifier": "Visits/Observatory", "destination": "Archive/Observatory", "is_namespace": True})
    assert not (wiki / "Visits/Observatory/Plan.md").exists()
    assert (wiki / "Archive/Observatory/Plan.md").exists()
    assert "evening shuttle" in (wiki / "Archive/Observatory/Logistics.md").read_text(encoding="utf-8")
    results = await call(config, "knowledge_search", {"namespaces": ["Archive/Observatory"], "query": "Sunday", "recursive": True})
    assert len(results["results"]) == 1 and results["exhausted"]
    assert results["results"][0]["identifier"] == "Archive/Observatory/Plan.md"
    moved = await call(config, "knowledge_read", {"identifier": "Archive/Observatory/Plan.md"})
    assert moved["metadata"]["custom"] == {"keep": True}
    bundle = await call(config, "knowledge_context", {"identifiers": [moved["identifier"], shared["note"]["identifier"]], "max_chars": 20})
    assert sum(len(note["content"]) for note in bundle["notes"]) <= 20
    assert bundle["omitted"] or any(note["truncated"] for note in bundle["notes"])
    assert "step-free" in (wiki / shared["note"]["file_path"]).read_text(encoding="utf-8")
    assert len(list(wiki.rglob("*.md"))) == 4
    # Prove the fallback against the real FTS index, beyond a global top-k page.
    outside = wiki / "Outside"
    outside.mkdir()
    for index in range(260):
        (outside / f"noise-{index:03}.md").write_text(f"---\ntitle: quasar noise {index}\ntype: note\n---\nquasar\n", encoding="utf-8")
    scope = wiki / "Late"
    scope.mkdir()
    (scope / "Target.md").write_text("---\ntitle: Target\ntype: note\n---\n" + "filler " * 200 + "quasar\n", encoding="utf-8")
    settings = Settings.load(config)
    refreshed = await asyncio.to_thread(subprocess.run, [settings.command, "reindex", "--full", "--search", "--project", "acceptance"], env=os.environ | settings.env, capture_output=True, timeout=120)
    if refreshed.returncode:
        raise RuntimeError("Synthetic search corpus reindex failed")
    first = await call(config, "knowledge_search", {"namespaces": ["Late"], "query": "quasar"})
    assert not first["results"] and first["has_more"] and first["scan_limited"]
    later = await call(config, "knowledge_search", {"namespaces": ["Late"], "query": "quasar", "cursor": first["next_cursor"]})
    assert [row["identifier"] for row in later["results"]] == ["Late/Target.md"]
    assert later["exhausted"]
    return {"status": "passed", "checks": ["multi-note namespaces", "same-title separation", "metadata-only edits", "concurrent writers", "collision refusal", "note and namespace moves", "search by moved path", "bounded shared context", "plain Markdown", "native FTS continuation beyond 250 outside hits"]}


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
