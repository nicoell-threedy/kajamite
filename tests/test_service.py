import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from kajamite.backend import BackendError
from kajamite.service import KnowledgeError, KnowledgeService


class FakeBackend:
    project = "backend-space"

    def __init__(self):
        self.notes = {}
        self.calls = []
        self.lock = asyncio.Lock()
        self.fail = None
        self.fuzzy = None
        self.stale_edit = False

    @asynccontextmanager
    async def mutation(self):
        async with self.lock:
            yield

    async def call(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if self.fail == name:
            raise BackendError("synthetic upstream failure")
        if name == "write_note":
            slug = arguments["title"].lower().replace(" ", "-")
            path = f'{arguments["directory"]}/{slug}.md'
            if path in self.notes and not arguments.get("overwrite"):
                raise BackendError("already exists")
            metadata = dict(arguments.get("metadata") or {})
            metadata.update(title=arguments["title"], type=arguments["note_type"])
            self.notes[path] = {
                "title": arguments["title"],
                "file_path": path,
                "permalink": path.removesuffix(".md").lower(),
                "content": arguments["content"],
                "frontmatter": metadata,
            }
            return {"file_path": path, "permalink": self.notes[path]["permalink"]}
        if name == "read_note":
            if self.fuzzy is not None:
                return dict(self.fuzzy)
            return dict(self._lookup(arguments["identifier"]))
        if name == "search_notes":
            rows = list(self.notes.values())
            types = arguments.get("note_types")
            if types:
                rows = [row for row in rows if row["frontmatter"].get("type") in types]
            if arguments.get("status") is not None:
                rows = [
                    row
                    for row in rows
                    if row["frontmatter"].get("status") == arguments["status"]
                ]
            for key, value in arguments.get("metadata_filters", {}).items():
                rows = [row for row in rows if row["frontmatter"].get(key) == value]
            query = arguments.get("query")
            if query:
                rows = [
                    row
                    for row in rows
                    if query.lower() in (row["title"] + row["content"]).lower()
                ]
            page, size = arguments["page"], arguments["page_size"]
            start = (page - 1) * size
            return {
                "results": [dict(row) for row in rows[start : start + size]],
                "current_page": page,
                "total": len(rows),
                "total_is_exact": True,
                "has_more": start + size < len(rows),
            }
        if name == "edit_note":
            note = self._lookup(arguments["identifier"])
            if self.stale_edit:
                note["content"] = "changed elsewhere"
            find = arguments["find_text"]
            if note["content"].count(find) != arguments["expected_replacements"]:
                raise BackendError("stale replacement")
            note["content"] = note["content"].replace(find, arguments["content"])
            note["frontmatter"].update(arguments.get("metadata") or {})
            return {"file_path": note["file_path"], "permalink": note["permalink"]}
        if name == "build_context":
            return {"results": [{"content": "x" * 5_000} for _ in range(30)]}
        raise AssertionError(name)

    def _lookup(self, identifier):
        clean = identifier.removeprefix("memory://").strip("/")
        for path, note in self.notes.items():
            if clean in {path, note["permalink"], note["title"]} or clean.endswith(
                "/" + note["permalink"]
            ):
                return note
        raise BackendError("missing")


class KnowledgeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend = FakeBackend()
        self.service = KnowledgeService(self.backend)

    async def test_create_revise_resume_and_complete_project(self):
        created = await self.service.project_create("Garden plan", "Grow herbs")
        project_id = created["note"]["identifier"]
        await self.service.create(
            "Watering decision", "Water weekly", project=project_id, kind="decision"
        )
        await self.service.create("Tool list", "Buy a trowel", project=project_id)

        scoped = await self.service.search(project=project_id, page_size=1)
        self.assertEqual(["Watering decision"], [row["title"] for row in scoped["results"]])
        self.assertTrue(scoped["has_more"])
        search_call = [call for call in self.backend.calls if call[0] == "search_notes"][-1][1]
        self.assertEqual("projects/garden-plan", search_call["metadata_filters"]["kajamite_project"])
        self.assertNotIn("project", search_call)  # This is a note scope, not a BM project.

        revised = await self.service.project_update(
            project_id, "Grow herbs", "Grow herbs and tomatoes", status="paused"
        )
        self.assertIn("tomatoes", revised["note"]["content"])
        self.assertTrue(
            all(
                call[1]["include_frontmatter"] is False
                for call in self.backend.calls
                if call[0] == "read_note"
            )
        )
        resumed = await self.service.resume(project_id)
        self.assertEqual("paused", resumed["project"]["metadata"]["status"])
        self.assertEqual("Watering decision", resumed["related"]["results"][0]["title"])
        self.assertTrue(resumed["content_is_data"])

        await self.service.project_update(project_id, status="completed")
        self.assertEqual(0, (await self.service.projects())["total"])
        self.assertEqual(1, (await self.service.projects(status=None))["total"])

    async def test_ordinary_notes_do_not_become_projects_or_preferences(self):
        note = await self.service.create("Tea", "Enjoys oolong")
        self.assertEqual("note", note["note"]["metadata"]["type"])
        self.assertNotIn("status", note["note"]["metadata"])
        self.assertEqual(0, (await self.service.projects())["total"])

    async def test_guarded_edits_reject_ambiguous_and_metadata_matches(self):
        note = await self.service.create("Draft", "same and same")
        identifier = note["note"]["identifier"]
        with self.assertRaisesRegex(KnowledgeError, "exactly once"):
            await self.service.edit(identifier, "same", "new")

        self.backend.notes[identifier]["frontmatter"]["owner"] = "marker"
        with self.assertRaisesRegex(KnowledgeError, "metadata"):
            await self.service.edit(identifier, "marker", "changed")

        unique = await self.service.create("Fresh", "old value")
        self.backend.stale_edit = True
        with self.assertRaises(BackendError):
            await self.service.edit(unique["note"]["identifier"], "old value", "new value")

    async def test_project_status_update_preserves_unknown_metadata(self):
        created = await self.service.project_create("Launch", "Ship safely")
        identifier = created["note"]["identifier"]
        self.backend.notes[identifier]["frontmatter"]["custom"] = {"keep": True}
        result = await self.service.project_update(identifier, status="cancelled")
        self.assertEqual({"keep": True}, result["note"]["metadata"]["custom"])
        self.assertEqual("cancelled", result["note"]["metadata"]["status"])

    async def test_read_and_context_disclose_bounds_and_pagination(self):
        note = await self.service.create("Long", "a" * 13_000)
        first = await self.service.read(note["note"]["identifier"])
        self.assertEqual(12_000, len(first["content"]))
        self.assertEqual(12_000, first["next_offset"])
        self.assertTrue(first["truncated"])
        second = await self.service.read(note["note"]["identifier"], offset=12_000)
        self.assertEqual(1_000, len(second["content"]))
        self.assertIsNone(second["next_offset"])

        project = await self.service.project_create("Bounded", "Keep context small")
        resumed = await self.service.resume(project["note"]["identifier"])
        self.assertTrue(resumed["context"]["truncated"])
        self.assertLessEqual(len(resumed["context"]["excerpt"]), 12_000)

    async def test_fuzzy_read_and_upstream_errors_are_explicit(self):
        self.backend.fuzzy = {
            "title": "Different",
            "file_path": "Notes/different.md",
            "permalink": "notes/different",
            "content": "wrong",
            "frontmatter": {"type": "note"},
        }
        with self.assertRaisesRegex(KnowledgeError, "fuzzy"):
            await self.service.read("Wanted")

        self.backend.fuzzy = None
        self.backend.fail = "search_notes"
        with self.assertRaises(BackendError):
            await self.service.search("anything")


if __name__ == "__main__":
    unittest.main()
