import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from kajamite.backend import BackendError
from kajamite.service import KnowledgeError, KnowledgeService


class FakeBackend:
    project = "configured-store"

    def __init__(self):
        self.notes = {}
        self.search_rows = None
        self.calls = []
        self.lock = asyncio.Lock()
        self.fail_move = False
        self.fuzzy = None
        self.directory_destination = None

    @asynccontextmanager
    async def mutation(self):
        async with self.lock:
            yield

    async def call(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if name == "write_note":
            slug = arguments["title"].lower().replace(" ", "-") + ".md"
            path = "/".join(filter(None, [arguments["directory"], slug]))
            if path in self.notes and not arguments["overwrite"]:
                raise BackendError("already exists")
            frontmatter = dict(arguments.get("metadata") or {})
            frontmatter.update(title=arguments["title"], type=arguments["note_type"])
            self.notes[path] = self._note(path, arguments["title"], arguments["content"], frontmatter)
            return {"moved": True, "file_path": path, "permalink": path.removesuffix(".md")}
        if name == "read_note":
            return dict(self.fuzzy or self._lookup(arguments["identifier"]))
        if name == "edit_note":
            note = self._lookup(arguments["identifier"])
            if arguments["operation"] == "find_replace":
                find = arguments["find_text"]
                if note["content"].count(find) != arguments["expected_replacements"]:
                    raise BackendError("stale replacement")
                note["content"] = note["content"].replace(find, arguments["content"])
            else:
                note["content"] += arguments["content"]
            note["frontmatter"].update(arguments.get("metadata") or {})
            return {"file_path": note["file_path"], "permalink": note["permalink"]}
        if name == "search_notes":
            rows = list(self.search_rows if self.search_rows is not None else self.notes.values())
            query = arguments.get("query")
            if query:
                rows = [row for row in rows if query.lower() in (row["title"] + row["content"]).lower()]
            kinds = arguments.get("note_types")
            if kinds:
                rows = [row for row in rows if row["frontmatter"].get("type") in kinds]
            for key, value in arguments.get("metadata_filters", {}).items():
                rows = [row for row in rows if row["frontmatter"].get(key) == value]
            page, size = arguments["page"], arguments["page_size"]
            start = (page - 1) * size
            return {"results": [dict(row) for row in rows[start:start + size]],
                    "has_more": start + size < len(rows), "total": len(rows),
                    "page": page, "page_size": size}
        if name == "list_directory":
            namespace = arguments["dir_name"].strip("/")
            nodes = []
            seen_dirs = set()
            for path, note in self.notes.items():
                relative = path[len(namespace) + 1:] if namespace and path.startswith(namespace + "/") else path
                if namespace and not path.startswith(namespace + "/"):
                    continue
                first = relative.split("/", 1)[0]
                if "/" in relative:
                    directory = "/" + "/".join(filter(None, [namespace, first]))
                    if directory not in seen_dirs:
                        seen_dirs.add(directory)
                        nodes.append({"type": "directory", "name": first, "file_path": None,
                                      "directory_path": directory, "children": []})
                else:
                    nodes.append({"type": "file", "name": first, "file_path": path,
                                  "directory_path": "/" + namespace, "children": [],
                                  "title": note["title"], "permalink": note["permalink"],
                                  "external_id": "id-" + first, "note_type": note["frontmatter"]["type"],
                                  "content_type": "text/markdown", "updated_at": "2026-01-01"})
            page, size = arguments["page"], arguments["page_size"]
            start = (page - 1) * size
            return {"nodes": nodes[start:start + size], "page": page, "page_size": size,
                    "total": len(nodes), "has_more": start + size < len(nodes)}
        if name == "move_note":
            if self.fail_move:
                raise BackendError("native move failed")
            source, destination = arguments["identifier"].strip("/"), arguments["destination_path"]
            if arguments["is_directory"]:
                moved = [(path, note) for path, note in self.notes.items()
                         if path.startswith(source + "/")]
                for path, note in moved:
                    del self.notes[path]
                    new_path = destination + path[len(source):]
                    note.update(file_path=new_path, permalink=new_path.removesuffix(".md"))
                    self.notes[new_path] = note
                return {"moved": bool(moved), "source": source,
                        "destination": self.directory_destination or destination,
                        "is_directory": True, "total_files": len(moved)}
            note = self._lookup(source)
            del self.notes[note["file_path"]]
            note.update(file_path=destination, permalink=destination.removesuffix(".md"))
            self.notes[destination] = note
            return {"moved": True, "file_path": destination, "permalink": note["permalink"]}
        raise AssertionError(name)

    @staticmethod
    def _note(path, title, content, metadata=None):
        return {"title": title, "file_path": path, "permalink": path.removesuffix(".md"),
                "content": content, "frontmatter": metadata or {"title": title, "type": "note"}}

    def _lookup(self, identifier):
        clean = identifier.removeprefix("memory://").strip("/")
        for note in self.notes.values():
            if clean in {note["file_path"], note["permalink"]}:
                return note
        raise BackendError("missing note")


class KnowledgeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend = FakeBackend()
        self.service = KnowledgeService(self.backend)

    async def test_create_is_literal_and_same_titles_are_folder_distinct(self):
        first = await self.service.create("Record", "literal body", "/alpha", metadata={"status": "odd"})
        second = await self.service.create("Record", "other body", "beta", kind="project")
        self.assertEqual("alpha/record.md", first["note"]["identifier"])
        self.assertEqual("beta/record.md", second["note"]["identifier"])
        self.assertEqual("literal body", first["note"]["content"])
        self.assertEqual("odd", first["note"]["metadata"]["status"])
        self.assertNotIn("status", second["note"]["metadata"])
        self.assertEqual("project", (await self.service.read("beta/record.md"))["metadata"]["type"])
        with self.assertRaisesRegex(ValueError, "reserved"):
            await self.service.create("Bad", "body", "/", metadata={"permalink": "ignored"})
        with self.assertRaises(BackendError):
            await self.service.read("Record")

    async def test_edit_guards_body_and_merges_arbitrary_metadata(self):
        created = await self.service.create("Draft", "old once", "/", metadata={"keep": 1})
        identifier = created["note"]["identifier"]
        changed = await self.service.edit(identifier, "old once", "new", {"status": "custom"})
        self.assertEqual("new", changed["note"]["content"])
        self.assertEqual(1, changed["note"]["metadata"]["keep"])
        self.assertEqual("custom", changed["note"]["metadata"]["status"])
        metadata_only = await self.service.edit(identifier, metadata={"rating": 5})
        self.assertEqual("new", metadata_only["note"]["content"])
        with self.assertRaisesRegex(ValueError, "reserved"):
            await self.service.edit(identifier, metadata={"type": "changed"})
        self.backend.notes[identifier]["content"] = "same same"
        with self.assertRaisesRegex(KnowledgeError, "exactly once"):
            await self.service.edit(identifier, "same", "x")

    async def test_native_list_preserves_namespace_nodes_and_arguments(self):
        await self.service.create("One", "body", "foo")
        await self.service.create("Two", "body", "foo/nested")
        result = await self.service.list("foo", depth=2, page=1, page_size=20,
                                         glob="*.md", sort="updated_desc")
        self.assertEqual({"file", "directory"}, {node["type"] for node in result["nodes"]})
        directory = next(node for node in result["nodes"] if node["type"] == "directory")
        self.assertIsNone(directory["file_path"])
        call = [item for item in self.backend.calls if item[0] == "list_directory"][-1][1]
        self.assertEqual({"dir_name": "/foo", "depth": 2, "file_name_glob": "*.md",
                          "sort": "updated_desc", "page": 1, "page_size": 20}, call)

    async def test_namespace_search_boundaries_overlap_and_cursor_offset(self):
        paths = ["foo/a.md", "foobar/no.md", "foo/nested/b.md", "root.md", "foo/c.md"]
        self.backend.search_rows = [FakeBackend._note(path, path, "match") for path in paths]
        flat = await self.service.search(["foo"], "match", recursive=False, page_size=1)
        self.assertEqual("foo/a.md", flat["results"][0]["file_path"])
        continued = await self.service.search(["foo"], "match", recursive=False,
                                              cursor=flat["next_cursor"], page_size=5)
        self.assertEqual(["foo/c.md"], [row["file_path"] for row in continued["results"]])
        nested = await self.service.search(["foo", "foo/nested"], "match", recursive=True)
        self.assertEqual(["foo/a.md", "foo/nested/b.md", "foo/c.md"],
                         [row["file_path"] for row in nested["results"]])
        root = await self.service.search(["/"], "match", recursive=False)
        self.assertEqual(["root.md"], [row["file_path"] for row in root["results"]])
        with self.assertRaisesRegex(ValueError, "another search"):
            await self.service.search(["beta"], "match", cursor=flat["next_cursor"])
        self.backend.search_rows = [{"title": "bad", "content": "match", "frontmatter": {}}]
        with self.assertRaisesRegex(KnowledgeError, "physical file path"):
            await self.service.search(["foo"], "match")
        self.assertTrue(all(call[1]["search_type"] == "text" for call in self.backend.calls
                            if call[0] == "search_notes"))

    async def test_search_scan_budget_continues_after_250_outside_rows(self):
        outside = [FakeBackend._note(f"elsewhere/{index}.md", str(index), "needle")
                   for index in range(260)]
        self.backend.search_rows = outside + [FakeBackend._note("wanted/hit.md", "hit", "needle")]
        first = await self.service.search(["wanted"], "needle")
        self.assertEqual([], first["results"])
        self.assertEqual(250, first["scanned_results"])
        self.assertTrue(first["scan_limited"])
        self.assertTrue(first["has_more"])
        self.assertFalse(first["exhausted"])
        second = await self.service.search(["wanted"], "needle", cursor=first["next_cursor"])
        self.assertEqual("wanted/hit.md", second["results"][0]["file_path"])
        self.assertTrue(second["exhausted"])

    async def test_context_is_bounded_preserves_listing_and_reports_partial_errors(self):
        await self.service.create("Long", "a" * 20, "docs")
        self.backend.notes["docs/data.bin"] = FakeBackend._note("docs/data.bin", "data", "binary")
        folder = await self.service.context(namespace="docs", max_chars=10)
        self.assertEqual(2, folder["listing"]["total"])
        self.assertEqual(10, folder["used_chars"])
        self.assertTrue(folder["notes"][0]["truncated"])
        self.assertTrue(folder["partial"])
        self.assertEqual("not_markdown", folder["omitted"][0]["reason"])

        self.backend.notes["docs/version-1.2.md"] = FakeBackend._note(
            "docs/version-1.2.md", "Version", "markdown"
        )
        selected = await self.service.context(
            identifiers=["docs/version-1.2", "missing.md", "docs/data.bin"], max_chars=30
        )
        self.assertEqual("docs/version-1.2.md", selected["notes"][0]["identifier"])
        self.assertEqual("missing.md", selected["errors"][0]["identifier"])
        self.assertTrue(selected["partial"])
        with self.assertRaises(ValueError):
            await self.service.context(namespace="docs", identifiers=["docs/long.md"])

    async def test_move_uses_native_paths_preserves_note_and_reports_failures(self):
        created = await self.service.create("Move me", "body", "inbox", metadata={"keep": True})
        moved = await self.service.move(created["note"]["identifier"], "archive/move-me.md")
        self.assertEqual("archive/move-me.md", moved["note"]["identifier"])
        self.assertTrue(moved["note"]["metadata"]["keep"])
        await self.service.create("Nested", "body", "source")
        directory = await self.service.move("/source", "archive/source", is_namespace=True)
        self.assertEqual("/archive/source", directory["namespace"])
        await self.service.create("Again", "body", "source-two")
        self.backend.directory_destination = "wrong/place"
        with self.assertRaisesRegex(KnowledgeError, "requested path"):
            await self.service.move("source-two", "archive/source-two", is_namespace=True)
        self.backend.directory_destination = None
        self.backend.fail_move = True
        with self.assertRaises(BackendError):
            await self.service.move("archive/move-me.md", "other/move-me.md")
        for invalid in ("../escape.md", "/root.md", "C:/drive.md"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                await self.service.move("archive/move-me.md", invalid)
        with self.assertRaisesRegex(ValueError, "root namespace"):
            await self.service.move("/", "elsewhere", is_namespace=True)


if __name__ == "__main__":
    unittest.main()
