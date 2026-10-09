import asyncio
import base64
import copy
import hashlib
import json
from contextlib import asynccontextmanager
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from kajamite.backend import BackendError
from kajamite.service import KnowledgeError, NoteOperations as KnowledgeService


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
        self.corrupt_edit = False
        self.fail_next_edit = False

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
            return copy.deepcopy(self.fuzzy or self._lookup(arguments["identifier"]))
        if name == "edit_note":
            if self.fail_next_edit:
                self.fail_next_edit = False
                raise BackendError("synthetic interrupted edit")
            note = self._lookup(arguments["identifier"])
            if arguments["operation"] == "find_replace":
                find = arguments["find_text"]
                if note["content"].count(find) != arguments["expected_replacements"]:
                    raise BackendError("stale replacement")
                note["content"] = note["content"].replace(find, arguments["content"])
            else:
                note["content"] += arguments["content"]
            note["frontmatter"].update(arguments.get("metadata") or {})
            if self.corrupt_edit:
                note["content"] = "corrupt readback"
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

    async def test_qualified_wiki_path_matches_only_its_physical_note(self):
        note = {"file_path": "notes/topic.md", "permalink": "project/notes/topic",
                "title": "Topic", "content": "original", "frontmatter": {}}
        self.backend.notes[note["file_path"]] = note
        self.backend.fuzzy = note
        self.assertEqual((await self.service.read("notes/topic"))["identifier"], "notes/topic.md")
        changed = await self.service.edit("notes/topic", "original", "corrected")
        self.assertEqual(changed["knowledge_change"]["after"]["identifier"], "notes/topic.md")
        for identifier in ("topic", "other/topic", "notes/wrong", "Notes/topic", "notes/topic.md.backup"):
            with self.subTest(identifier=identifier), self.assertRaisesRegex(KnowledgeError, "fuzzy match"):
                await self.service.read(identifier)

    async def test_create_is_literal_and_same_titles_are_folder_distinct(self):
        first = await self.service.create("Record", "literal body", "/alpha", metadata={"status": "odd"})
        second = await self.service.create("Record", "other body", "beta", kind="project")
        self.assertEqual("alpha/record.md", first["note"]["identifier"])
        self.assertEqual("beta/record.md", second["note"]["identifier"])
        self.assertEqual("literal body", first["note"]["content"])
        self.assertEqual("odd", first["note"]["metadata"]["status"])
        change = first["knowledge_change"]
        self.assertEqual("create", change["operation"])
        self.assertIsNone(change["before"])
        self.assertEqual("alpha/record.md", change["after"]["identifier"])
        self.assertEqual("literal body", change["body_change"]["after"]["preview"])
        self.assertTrue(change["readback_verified"])
        self.assertIn("This receipt covers this Kajamite operation only", first["knowledge_change_text"])
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
        change = changed["knowledge_change"]
        self.assertEqual("exact_replacement", change["body_change"]["kind"])
        self.assertEqual("old once", change["body_change"]["before"]["preview"])
        self.assertEqual("new", change["body_change"]["after"]["preview"])
        self.assertEqual("status", change["metadata_changes"][0]["key"])
        self.assertIsNone(change["metadata_changes"][0]["before"])
        self.assertEqual("custom", change["metadata_changes"][0]["after"])
        self.assertFalse(change["metadata_changes"][0]["before_present"])
        self.assertTrue(change["metadata_changes"][0]["after_present"])
        self.assertNotEqual(change["before"]["content_sha256"], change["after"]["content_sha256"])
        metadata_only = await self.service.edit(identifier, metadata={"rating": 5})
        self.assertEqual("new", metadata_only["note"]["content"])
        self.assertIsNone(metadata_only["knowledge_change"]["body_change"])
        with self.assertRaisesRegex(ValueError, "reserved"):
            await self.service.edit(identifier, metadata={"type": "changed"})
        self.backend.notes[identifier]["content"] = "same same"
        with self.assertRaisesRegex(KnowledgeError, "exactly once"):
            await self.service.edit(identifier, "same", "x")

    async def test_revise_preserves_unselected_markdown_and_guards_every_selection(self):
        body = (
            "# Plan\n\n## Repeated\nalpha beta gamma\n\n"
            "Name  Score\nAda   8\n\n```text\nkeep --literal\n```\n\n"
            "## Repeated\nÜnicode stays.\n"
        )
        created = await self.service.create("Revision", body, "notes", metadata={"keep": True})
        identifier = created["note"]["identifier"]
        read = await self.service.read(identifier, limit=8)
        self.assertTrue(read["truncated"])
        self.assertEqual(hashlib.sha256(body.encode("utf-8")).hexdigest(), read["content_sha256"])
        context = await self.service.context(identifiers=[identifier], max_chars=8)
        self.assertEqual(read["content_sha256"], context["notes"][0]["content_sha256"])
        replacements = [
            {"find_text": "alpha beta gamma", "replacement": "alpha delta gamma"},
            {"find_text": "Ada   8", "replacement": "Ada   9"},
        ]
        preview = await self.service.revise(identifier, read["content_sha256"], replacements, preview=True)
        self.assertTrue(preview["preview"])
        self.assertNotIn("knowledge_change", preview)
        self.assertEqual(body, self.backend.notes[identifier]["content"])
        applied = await self.service.revise(identifier, read["content_sha256"], replacements)
        expected = body.replace("alpha beta gamma", "alpha delta gamma").replace("Ada   8", "Ada   9")
        self.assertEqual(expected, applied["note"]["content"])
        self.assertIn("```text\nkeep --literal\n```", applied["note"]["content"])
        self.assertIn("## Repeated\nÜnicode stays.", applied["note"]["content"])
        change = applied["knowledge_change"]
        self.assertEqual("revise", change["operation"])
        self.assertEqual("grouped_exact_replacement", change["body_change"]["kind"])
        self.assertEqual(2, len(change["body_change"]["replacements"]))
        self.assertIn("Replacement 1 previous value", applied["knowledge_change_text"])
        self.assertEqual({"keep": True, "title": "Revision", "type": "note"}, applied["note"]["metadata"])

        writes = len([call for call in self.backend.calls if call[0] == "edit_note"])
        with self.assertRaisesRegex(KnowledgeError, "overlap"):
            await self.service.revise(identifier, applied["note"]["content_sha256"], [
                {"find_text": "alpha delta", "replacement": "one"},
                {"find_text": "delta gamma", "replacement": "two"},
            ])
        with self.assertRaisesRegex(KnowledgeError, "exactly once"):
            await self.service.revise(identifier, applied["note"]["content_sha256"], [
                {"find_text": "## Repeated", "replacement": "## Changed"},
            ])
        with self.assertRaisesRegex(ValueError, "between 1 and 100"):
            await self.service.revise(identifier, applied["note"]["content_sha256"], [
                {"find_text": "alpha", "replacement": "beta"}
            ] * 101)
        self.assertEqual(writes, len([call for call in self.backend.calls if call[0] == "edit_note"]))

        current_hash = applied["note"]["content_sha256"]
        stale_preview = await self.service.revise(identifier, current_hash, [
            {"find_text": "Ünicode", "replacement": "Unicode"},
        ], preview=True)
        self.assertTrue(stale_preview["preview"])
        self.backend.notes[identifier]["content"] += "changed elsewhere\n"
        with self.assertRaisesRegex(KnowledgeError, "revision conflict"):
            await self.service.revise(identifier, current_hash, [{"find_text": "Ünicode", "replacement": "Unicode"}])
        self.assertEqual(writes, len([call for call in self.backend.calls if call[0] == "edit_note"]))

    async def test_revise_rejects_overlapping_occurrences_of_one_selection(self):
        created = await self.service.create("Ambiguous", "aaa", "notes")
        identifier = created["note"]["identifier"]
        current = await self.service.read(identifier)
        for preview in (True, False):
            with self.assertRaisesRegex(KnowledgeError, "exactly once"):
                await self.service.revise(identifier, current["content_sha256"], [
                    {"find_text": "aa", "replacement": "b"},
                ], preview=preview)
        self.assertFalse(any(name == "edit_note" for name, _ in self.backend.calls))
        self.assertEqual("aaa", self.backend.notes[identifier]["content"])

    async def test_revise_allows_no_change_and_reports_uncertain_readback(self):
        created = await self.service.create("No change", "keep Ω", "notes")
        identifier = created["note"]["identifier"]
        current = await self.service.read(identifier)
        unchanged = await self.service.revise(identifier, current["content_sha256"], [
            {"find_text": "keep Ω", "replacement": "keep Ω"},
        ])
        self.assertEqual(unchanged["knowledge_change"]["before"]["content_sha256"], unchanged["knowledge_change"]["after"]["content_sha256"])
        self.backend.corrupt_edit = True
        current = await self.service.read(identifier)
        with self.assertRaisesRegex(BackendError, "write may have committed"):
            await self.service.revise(identifier, current["content_sha256"], [
                {"find_text": "keep Ω", "replacement": "updated Ω"},
            ])
        self.assertEqual("corrupt readback", self.backend.notes[identifier]["content"])

    async def test_inspect_collection_is_bounded_and_reports_page_scoped_duplicates(self):
        first = await self.service.create("First", "same body", "collection")
        second = await self.service.create("Second", "same body", "collection")
        await self.service.create("Third", "other body", "collection")
        page = await self.service.inspect_collection("collection", page_size=2)
        self.assertFalse(page["exhausted"])
        self.assertTrue(page["has_more"])
        self.assertEqual(2, len(page["notes"]))
        self.assertEqual({first["note"]["identifier"], second["note"]["identifier"]},
                         set(page["candidates"][0]["identifiers"]))
        self.assertEqual("exact_duplicate", page["candidates"][0]["kind"])
        self.assertEqual("returned_page", page["candidates"][0]["scope"])
        self.assertTrue(all(len(note["content_sha256"]) == 64 for note in page["notes"]))
        with self.assertRaisesRegex(ValueError, "another collection inspection"):
            await self.service.inspect_collection("other", page_size=2, cursor=page["next_cursor"])
        with self.assertRaisesRegex(ValueError, "another collection inspection"):
            await self.service.inspect_collection("collection", page_size=1, cursor=page["next_cursor"])
        with self.assertRaisesRegex(ValueError, "another collection inspection"):
            await self.service.inspect_collection("collection", recursive=False, page_size=2,
                                                  cursor=page["next_cursor"])
        with self.assertRaisesRegex(ValueError, "invalid"):
            await self.service.inspect_collection("collection", cursor="a")
        final = await self.service.inspect_collection("collection", page_size=2, cursor=page["next_cursor"])
        self.assertTrue(final["exhausted"])
        self.assertFalse(final["candidates"])

    async def test_inspect_collection_keeps_incomplete_empty_pages_honest(self):
        self.backend.search_rows = [FakeBackend._note(f"outside/{index}.md", str(index), "body")
                                    for index in range(260)]
        last = FakeBackend._note("wanted/last.md", "Last", "body")
        self.backend.search_rows.append(last)
        self.backend.notes["wanted/last.md"] = last
        first = await self.service.inspect_collection("wanted", page_size=5)
        self.assertEqual([], first["notes"])
        self.assertTrue(first["has_more"])
        self.assertFalse(first["exhausted"])
        self.assertTrue(first["partial"])
        later = await self.service.inspect_collection("wanted", page_size=5, cursor=first["next_cursor"])
        self.assertEqual(["wanted/last.md"], [note["identifier"] for note in later["notes"]])

    async def test_consolidation_walkthrough_rereads_after_second_write_failure(self):
        target = await self.service.create("Canonical", "rule: original", "collection")
        source = await self.service.create("Duplicate", "rule: original", "collection")
        inventory = await self.service.inspect_collection("collection")
        expected = {note["identifier"]: note["content_sha256"] for note in inventory["notes"]}
        await self.service.revise(target["note"]["identifier"], expected[target["note"]["identifier"]], [
            {"find_text": "original", "replacement": "current"},
        ])
        self.backend.fail_next_edit = True
        with self.assertRaisesRegex(BackendError, "write may have committed"):
            await self.service.revise(source["note"]["identifier"], expected[source["note"]["identifier"]], [
                {"find_text": "rule: original", "replacement": "See Canonical."},
            ])
        reread = await self.service.read(source["note"]["identifier"])
        self.assertEqual(expected[source["note"]["identifier"]], reread["content_sha256"])
        resumed = await self.service.revise(source["note"]["identifier"], reread["content_sha256"], [
            {"find_text": "rule: original", "replacement": "See Canonical."},
        ])
        self.assertEqual("See Canonical.", resumed["note"]["content"])

    async def test_native_list_preserves_namespace_nodes_and_arguments(self):
        before = len(self.backend.calls)
        with self.assertRaisesRegex(ValueError, "sort must be title_asc"):
            await self.service.list("foo", sort="name")
        self.assertEqual(before, len(self.backend.calls))
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

    async def test_search_changed_totals_survive_continuation_and_withhold_completeness(self):
        from kajamite.engine import KnowledgeEngine

        for count in (60, 260):
            with self.subTest(count=count):
                self.backend.search_rows = [FakeBackend._note(f"outside/{i}.md", str(i), "needle")
                                            for i in range(count)]
                native = self.backend.call
                changed = False

                async def changing(name, arguments):
                    nonlocal changed
                    if name == "search_notes" and arguments["page"] > 1 and not changed:
                        self.backend.search_rows.pop()
                        changed = True
                    return await native(name, arguments)

                self.backend.call = changing
                engine = KnowledgeEngine(self.backend)
                result = await engine.search(["wanted"], "needle")
                self.assertTrue(result["index_changed"])
                for _ in range(3):
                    if not result["next_cursor"]:
                        break
                    result = await engine.search(["wanted"], "needle", cursor=result["next_cursor"])
                self.assertTrue(result["exhausted"])
                self.assertFalse(result["has_more"])
                self.assertFalse(result["complete_scope_search"])
                self.assertTrue(result["index_changed"])
                self.assertTrue(result["partial"])
                changed = False
                inventory = await engine.inspect_collection("wanted")
                for _ in range(3):
                    if not inventory["next_cursor"]:
                        break
                    inventory = await engine.inspect_collection("wanted", cursor=inventory["next_cursor"])
                self.assertTrue(inventory["partial"])
                self.assertTrue(inventory["index_changed"])
                self.backend.call = native

    async def test_search_total_changes_between_calls_and_legacy_cursors(self):
        self.backend.search_rows = [FakeBackend._note(f"outside/{i}.md", str(i), "needle")
                                    for i in range(260)]
        first = await self.service.search(["wanted"], "needle")
        self.assertFalse(first["index_changed"])
        self.backend.search_rows.pop()
        last = await self.service.search(["wanted"], "needle", cursor=first["next_cursor"])
        self.assertTrue(last["index_changed"])
        self.assertFalse(last["complete_scope_search"])
        self.assertFalse(last["exhausted"])
        restarted = json.loads(base64.urlsafe_b64decode(last["next_cursor"] + "=" * (-len(last["next_cursor"]) % 4)))
        self.assertEqual(restarted["offset"], 0)
        cursor = first["next_cursor"]
        legacy = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        legacy.pop("native_total")
        legacy.pop("index_changed")
        legacy.pop("restart")
        legacy.pop("recovering")
        encode = lambda value: base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
        last = await self.service.search(["wanted"], "needle", cursor=encode(legacy))
        self.assertFalse(last["index_changed"])
        self.assertTrue(last["complete_scope_search"])
        for fields in ({"native_total": -1}, {"native_total": True}, {"index_changed": "false"}, {"restart": "false"}, {"recovering": "false"}):
            with self.assertRaises(ValueError):
                await self.service.search(["wanted"], "needle", cursor=encode(legacy | fields))

    async def test_search_restarts_when_a_target_shifts_before_the_cursor(self):
        self.backend.search_rows = [FakeBackend._note(f"outside/{i}.md", str(i), "needle")
                                    for i in range(250)]
        self.backend.search_rows.append(FakeBackend._note("wanted/target.md", "Target", "needle"))
        first = await self.service.search(["wanted"], "needle")
        self.assertEqual(first["results"], [])
        self.assertTrue(first["scan_limited"])
        self.backend.search_rows.pop(0)
        shifted = await self.service.search(["wanted"], "needle", cursor=first["next_cursor"])
        self.assertEqual(shifted["results"], [])
        self.assertTrue(shifted["has_more"])
        self.assertTrue(shifted["index_changed"])
        recovered = await self.service.search(["wanted"], "needle", cursor=shifted["next_cursor"])
        self.assertEqual([row["identifier"] for row in recovered["results"]], ["wanted/target.md"])
        self.assertTrue(recovered["exhausted"])
        self.assertFalse(recovered["complete_scope_search"])
        calls = [args for name, args in self.backend.calls if name == "search_notes"]
        self.assertEqual([args["page"] for args in calls], [1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5])

    async def test_changed_totals_do_not_starve_later_pages_before_recovery(self):
        self.backend.search_rows = [FakeBackend._note(f"outside/{i}.md", str(i), "needle")
                                    for i in range(250)]
        self.backend.search_rows.append(FakeBackend._note("wanted/target.md", "Target", "needle"))
        native = self.backend.call

        async def changing(name, arguments):
            result = await native(name, arguments)
            if name == "search_notes":
                result["total"] += arguments["page"] % 2
            return result

        self.backend.call = changing
        first = await self.service.search(["wanted"], "needle")
        cursor = json.loads(base64.urlsafe_b64decode(first["next_cursor"] + "=" * (-len(first["next_cursor"]) % 4)))
        self.assertEqual(cursor["offset"], 250)
        self.assertTrue(cursor["restart"])
        later = await self.service.search(["wanted"], "needle", cursor=first["next_cursor"])
        self.assertEqual([row["identifier"] for row in later["results"]], ["wanted/target.md"])
        self.assertTrue(later["has_more"])
        self.assertFalse(later["exhausted"])
        self.assertTrue(later["index_changed"])
        cursor = json.loads(base64.urlsafe_b64decode(later["next_cursor"] + "=" * (-len(later["next_cursor"]) % 4)))
        self.assertEqual(cursor["offset"], 0)
        self.assertFalse(cursor["restart"])
        self.assertTrue(cursor["recovering"])
        for _ in range(2):
            later = await self.service.search(["wanted"], "needle", cursor=later["next_cursor"])
        self.assertTrue(later["exhausted"])
        self.assertIsNone(later["next_cursor"])
        self.assertFalse(later["complete_scope_search"])

    async def test_search_missing_totals_do_not_invent_a_change(self):
        self.backend.search_rows = [FakeBackend._note(f"outside/{i}.md", str(i), "needle")
                                    for i in range(60)]
        native = self.backend.call

        async def without_total(name, arguments):
            result = await native(name, arguments)
            if name == "search_notes":
                result.pop("total")
            return result

        self.backend.call = without_total
        result = await self.service.search(["wanted"], "needle")
        self.assertFalse(result["index_changed"])
        self.assertTrue(result["complete_scope_search"])

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
        change = moved["knowledge_change"]
        self.assertEqual("move_note", change["operation"])
        self.assertEqual("inbox/move-me.md", change["before"]["identifier"])
        self.assertEqual("archive/move-me.md", change["after"]["identifier"])
        self.assertEqual(change["before"]["content_sha256"], change["after"]["content_sha256"])
        await self.service.create("Nested", "body", "source")
        directory = await self.service.move("/source", "archive/source", is_namespace=True)
        self.assertEqual("/archive/source", directory["namespace"])
        namespace_change = directory["knowledge_change"]
        self.assertEqual("move_namespace", namespace_change["operation"])
        self.assertEqual(1, namespace_change["affected_notes"])
        self.assertTrue(namespace_change["affected_notes_exact"])
        self.assertFalse(namespace_change["readback_verified"])
        self.assertEqual("backend_confirmed", namespace_change["verification"])
        await self.service.create("Again", "body", "source-two")
        self.backend.directory_destination = "wrong/place"
        with self.assertRaisesRegex(BackendError, "requested path"):
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

    async def test_receipt_value_previews_are_bounded_and_hashed(self):
        content = "x" * 2_100
        created = await self.service.create("Long receipt", content, "notes")
        value = created["knowledge_change"]["body_change"]["after"]
        self.assertEqual(2_000, len(value["preview"]))
        self.assertEqual(2_100, value["characters"])
        self.assertTrue(value["truncated"])
        self.assertEqual(64, len(value["sha256"]))
        self.assertIn("preview; truncated", created["knowledge_change_text"])


if __name__ == "__main__":
    unittest.main()
