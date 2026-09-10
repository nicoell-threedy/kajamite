"""Measure native entity retrieval against focused observation retrieval on synthetic notes."""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import time

from commission import cleanup, prepare, wait_for_indexed_path
from kajamite.backend import connect
from kajamite.config import Settings
from kajamite.engine import KnowledgeEngine
from kajamite.service import NoteOperations


MARKER = "retrieval-marker-7f5d"


class CountingBackend:
    def __init__(self, backend):
        self._backend = backend
        self.calls = 0

    def mutation(self):
        return self._backend.mutation()

    async def call(self, name, arguments):
        self.calls += 1
        return await self._backend.call(name, arguments)

    def __getattr__(self, name):
        return getattr(self._backend, name)


async def measure(service, method, *arguments, **keywords):
    service.backend.calls = 0
    started = time.perf_counter()
    result = await method(*arguments, **keywords)
    return result, {"backend_calls": service.backend.calls,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)}


async def run(config):
    async with connect(Settings.load(config)) as native:
        backend = CountingBackend(native)
        long_body = ("irrelevant narrative " * 900 + "\n## Observations\n"
                     f"- [fact] The synthetic benchmark fact is {MARKER}.\n")
        seeds = [("Long source", long_body),
                 ("Linked source", "## Relations\n- depends_on [[Long source]]\n")]
        seeds.extend((f"Irrelevant {number}", f"ordinary unrelated text {number}") for number in range(8))
        paths = {}
        for title, body in seeds:
            written = await backend.call("write_note", {
                "title": title, "content": body, "directory": "Benchmark", "overwrite": False,
            })
            paths[title] = written["file_path"]
            await wait_for_indexed_path(backend, title.split()[0].lower(), written["file_path"])
        await wait_for_indexed_path(backend, MARKER, paths["Long source"])

        legacy = NoteOperations(backend)
        engine = KnowledgeEngine(backend)
        entity, entity_metrics = await measure(
            legacy, legacy.search, ["Benchmark"], MARKER, recursive=True)
        observation, observation_metrics = await measure(
            engine, engine.search, ["Benchmark"], MARKER, recursive=True,
            item_types=["observation"], categories=["fact"])
        legacy_paths = [item["file_path"] for item in entity["results"]]
        observation_paths = [item["file_path"] for item in observation["results"]]
        assert paths["Long source"] in legacy_paths
        assert paths["Long source"] in observation_paths
        snippet = next(item["snippet"] for item in observation["results"]
                       if item["file_path"] == paths["Long source"])
        assert MARKER in snippet and len(snippet) < len(long_body)
        related = await legacy.related(paths["Linked source"], ["Benchmark"])
        assert paths["Long source"] in [note["identifier"] for note in related["notes"]]
        return {"status": "passed", "corpus": {"notes": len(seeds), "marker": MARKER},
                "entity_default": entity_metrics | {"relevant_path_recovered": paths["Long source"] in legacy_paths,
                                                      "returned_snippet_chars": sum(len(item["snippet"]) for item in entity["results"])},
                "observation_fact": observation_metrics | {"relevant_path_recovered": paths["Long source"] in observation_paths,
                                                             "returned_snippet_chars": sum(len(item["snippet"]) for item in observation["results"])},
                "linked_target_recovered": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--basic-memory", required=True)
    arguments = parser.parse_args()
    temporary = tempfile.TemporaryDirectory(prefix="kajamite-retrieval-benchmark-")
    try:
        config, _ = prepare(Path(temporary.name), arguments.basic_memory)
        print(json.dumps(asyncio.run(run(config))))
    finally:
        cleanup(temporary)


if __name__ == "__main__":
    main()
