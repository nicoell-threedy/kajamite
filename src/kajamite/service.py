"""Bounded note and namespace operations over Basic Memory's public MCP tools."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from typing import Any, Literal

from .errors import BackendError, MutationUncertain
from . import receipt


class KnowledgeError(RuntimeError):
    """The requested knowledge operation could not be completed safely."""


def apply_exact_replacements(body: str, replacements: list[dict[str, str]]) -> str:
    """Replace disjoint exact passages selected from one original body."""
    if not isinstance(replacements, list) or not 1 <= len(replacements) <= 100:
        raise ValueError("replacements must contain between 1 and 100 entries")
    selections = []
    for index, item in enumerate(replacements):
        if not isinstance(item, dict) or set(item) != {"find_text", "replacement"}:
            raise ValueError("each replacement must contain only find_text and replacement")
        if not isinstance(item["find_text"], str) or not item["find_text"]:
            raise ValueError("replacement find_text must be nonempty text")
        if not isinstance(item["replacement"], str):
            raise ValueError("replacement value must be text")
        start = body.find(item["find_text"])
        if start < 0:
            raise KnowledgeError("replacement find_text is missing from the current note body")
        if body.find(item["find_text"], start + 1) != -1:
            raise KnowledgeError("replacement find_text must occur exactly once in the current note body")
        selections.append((start, start + len(item["find_text"]), index, item))
    selections.sort()
    for previous, current in zip(selections, selections[1:]):
        if current[0] < previous[1]:
            raise KnowledgeError("replacement selections overlap in the current note body")
    parts: list[str] = []
    position = 0
    for start, end, _, item in selections:
        parts.extend((body[position:start], item["replacement"]))
        position = end
    parts.append(body[position:])
    return "".join(parts)


class NoteOperations:
    _native_page_size = 50
    _native_page_budget = 5
    _reserved_metadata = {"title", "type", "permalink"}

    def __init__(self, backend: Any) -> None:
        self.backend = backend

    async def search(
        self,
        namespaces: list[str],
        query: str | None = None,
        recursive: bool = False,
        kind: str | None = None,
        metadata: dict[str, Any] | None = None,
        cursor: str | None = None,
        page_size: int = 10,
        retrieval_mode: Literal["text", "semantic", "hybrid"] = "text",
        item_types: list[str] | None = None,
        categories: list[str] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(namespaces, list) or not namespaces:
            raise ValueError("namespaces must be a nonempty list")
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100")
        if retrieval_mode not in {"text", "semantic", "hybrid"}:
            raise ValueError("retrieval_mode must be text, semantic, or hybrid")
        item_types = item_types or ["entity"]
        if not isinstance(item_types, list) or not item_types or any(item not in {"entity", "observation", "relation"} for item in item_types):
            raise ValueError("item_types must select entity, observation, or relation")
        if categories is not None and (not isinstance(categories, list) or not categories or any(not isinstance(item, str) or not item for item in categories)):
            raise ValueError("categories must be a nonempty list of strings")
        scopes = list(dict.fromkeys(self._namespace(value) for value in namespaces))
        criteria = [str(getattr(self.backend, "project", "")), query, scopes, recursive, kind, metadata, retrieval_mode, item_types, categories]
        fingerprint = hashlib.sha256(
            json.dumps(criteria, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        offset, native_total, index_changed, restart, recovering = self._decode_cursor(cursor, fingerprint) if cursor else (0, None, False, False, False)
        native_page, skip = divmod(offset, self._native_page_size)
        native_page += 1
        results: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        scanned = pages = 0
        exhausted = False

        while pages < self._native_page_budget:
            arguments: dict[str, Any] = {
                "query": query,
                "search_type": retrieval_mode,
                "entity_types": item_types,
                "page": native_page,
                "page_size": self._native_page_size,
            }
            if categories is not None:
                arguments["categories"] = categories
            if kind is not None:
                arguments["note_types"] = [kind]
            if metadata is not None:
                arguments["metadata_filters"] = metadata
            payload = await self.backend.call("search_notes", arguments)
            rows = payload.get("results")
            if not isinstance(rows, list):
                raise KnowledgeError("search_notes returned invalid results")
            total = payload.get("total")
            if type(total) is int and total >= 0:
                restart = restart or (native_total is not None and total != native_total)
                index_changed = index_changed or restart
                native_total = total
            pages += 1
            stopped = False
            for index, row in enumerate(rows):
                if index < skip:
                    continue
                offset = (native_page - 1) * self._native_page_size + index + 1
                scanned += 1
                item = self._search_item(row)
                if item and self._in_scopes(item["file_path"], scopes, recursive):
                    # Native projections can repeat entities, including across pages.
                    # Keep distinct observations/relations within the same note.
                    detail = "" if item["item_type"] == "entity" else str((item["item_id"], item["category"], item["snippet"]))
                    identity = (item["file_path"], str(item["item_type"]), detail)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    results.append(item)
                    if len(results) == page_size:
                        stopped = True
                        exhausted = index + 1 == len(rows) and not payload.get("has_more", False)
                        break
            if stopped:
                break
            if not payload.get("has_more", False):
                exhausted = True
                break
            offset = native_page * self._native_page_size
            native_page += 1
            skip = 0

        scan_limited = pages == self._native_page_budget and not exhausted
        if restart and exhausted and not recovering:
            # One recovery pass preserves forward progress while keeping index uncertainty visible.
            offset, exhausted, restart, recovering = 0, False, False, True
        return {
            "results": results,
            "next_cursor": None if exhausted else self._encode_cursor(offset, fingerprint, native_total, index_changed, restart, recovering),
            "has_more": not exhausted,
            "exhausted": exhausted,
            "retrieval_mode": retrieval_mode,
            "complete_scope_search": exhausted and retrieval_mode == "text" and not index_changed,
            "index_changed": index_changed,
            "scanned_results": scanned,
            "scan_limited": scan_limited,
        }

    async def read(self, identifier: str, offset: int = 0, limit: int = 12_000) -> dict[str, Any]:
        if offset < 0 or limit < 1:
            raise ValueError("offset must be >= 0 and limit must be >= 1")
        return self._public_note(await self._read_full(identifier), offset, min(limit, 12_000))

    async def inspect_collection(
        self, namespace: str, recursive: bool = True, cursor: str | None = None,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Return a live, bounded inventory of ordinary notes in one scope."""
        scope = self._namespace(namespace)
        if not isinstance(recursive, bool):
            raise ValueError("recursive must be a boolean")
        if not isinstance(page_size, int) or isinstance(page_size, bool) or not 1 <= page_size <= 100:
            raise ValueError("page_size must be between 1 and 100")
        fingerprint = hashlib.sha256(json.dumps(
            [str(getattr(self.backend, "project", "")), scope, recursive, page_size],
            separators=(",", ":"),
        ).encode()).hexdigest()
        search_cursor = self._decode_collection_cursor(cursor, fingerprint) if cursor else None
        scan = await self._collection_search(scope, recursive, search_cursor, page_size)
        notes: list[dict[str, Any]] = []
        omissions = list(scan.get("excluded", []))
        errors: list[dict[str, str]] = []
        for item in scan["results"]:
            identifier = item["identifier"]
            try:
                note, omission = await self._inspection_note(identifier)
            except (BackendError, KnowledgeError) as error:
                errors.append({"identifier": identifier, "error": str(error)})
                continue
            if omission is not None:
                omissions.append(omission)
                continue
            if not str(note.get("file_path", "")).lower().endswith(".md"):
                omissions.append({"identifier": identifier, "reason": "not_markdown"})
                continue
            notes.append({
                "identifier": self._identifier(note), "file_path": note.get("file_path"),
                "permalink": note.get("permalink"), "title": note.get("title", ""),
                "content_sha256": self._content_sha256(note["content"]),
            })
        duplicates: dict[str, list[str]] = {}
        for note in notes:
            duplicates.setdefault(note["content_sha256"], []).append(note["identifier"])
        candidates = [
            {"kind": "exact_duplicate", "scope": "returned_page", "content_sha256": digest,
             "identifiers": identifiers}
            for digest, identifiers in duplicates.items() if len(identifiers) > 1
        ]
        exhausted = bool(scan["exhausted"])
        return {
            "namespace": scope, "recursive": recursive, "notes": notes,
            "candidates": candidates, "omissions": omissions, "errors": errors,
            "next_cursor": None if exhausted else self._encode_collection_cursor(scan["next_cursor"], fingerprint),
            "has_more": not exhausted, "exhausted": exhausted,
            "scanned_notes": len(scan["results"]), "partial": bool(not exhausted or omissions or errors or scan.get("index_changed")),
            "index_changed": bool(scan.get("index_changed")),
            "live": True,
        }

    async def _collection_search(
        self, scope: str, recursive: bool, cursor: str | None, page_size: int,
    ) -> dict[str, Any]:
        return await self.search([scope], query=None, recursive=recursive, cursor=cursor,
                                 page_size=page_size)

    async def _inspection_note(self, identifier: str) -> tuple[dict[str, Any], dict[str, str] | None]:
        return await self._read_full(identifier), None

    async def create(
        self,
        title: str,
        content: str,
        namespace: str,
        kind: str = "note",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        reserved = self._reserved_metadata & set(metadata or {})
        if reserved:
            raise ValueError("metadata cannot set reserved fields: " + ", ".join(sorted(reserved)))
        directory = self._namespace(namespace).lstrip("/")
        async with self.backend.mutation():
            result = await self._call_mutation(
                "write_note",
                {"title": title, "content": content, "directory": directory,
                 "note_type": kind, "metadata": metadata, "overwrite": False},
            )
            identifier = self._mutation_identifier(result)
            if not self._in_scopes(identifier, [self._namespace(namespace)], False):
                raise MutationUncertain("Create returned a different namespace; a write may have committed. Inspect current state before retrying.")
            note = await self._read_after_mutation(identifier)
            if not self._body_matches(note["content"], content) or any(self._metadata(note).get(key) != value for key, value in (metadata or {}).items()):
                raise MutationUncertain("Create readback did not match requested content or metadata; a write may have committed. Inspect current state before retrying.")
            change = receipt.for_create(note)
            return {
                "mutation": result, "note": self._public_note(note),
                "knowledge_change": change, "knowledge_change_text": receipt.render(change),
            }

    async def edit(
        self,
        identifier: str,
        find_text: str | None = None,
        replacement: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if (find_text is None) != (replacement is None):
            raise ValueError("find_text and replacement must be provided together")
        if find_text == "":
            raise ValueError("find_text must not be empty")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        reserved = self._reserved_metadata & set(metadata or {})
        if reserved:
            raise ValueError("metadata cannot change reserved fields: " + ", ".join(sorted(reserved)))
        if find_text is None and not metadata:
            raise ValueError("a body replacement or metadata is required")
        async with self.backend.mutation():
            before = await self._read_full(identifier)
            await self._check_generic_note(before)
            body = before["content"]
            if find_text is not None and body.count(find_text) != 1:
                raise KnowledgeError("find_text must occur exactly once in the note body")
            expected = body if find_text is None else body.replace(find_text, replacement or "", 1)
            arguments: dict[str, Any] = {
                "identifier": self._identifier(before),
                "operation": "append" if find_text is None else "find_replace",
                "content": "" if find_text is None else replacement,
            }
            if find_text is not None:
                arguments.update(find_text=find_text, expected_replacements=1)
            if metadata:
                arguments["metadata"] = metadata
            result = await self._call_mutation("edit_note", arguments)
            after = await self._read_after_mutation(self._identifier(before))
            if after["content"] != expected or any(
                self._metadata(after).get(key) != value for key, value in (metadata or {}).items()
            ):
                raise MutationUncertain("edit readback did not match the requested changes; a write may have committed. Inspect current state before retrying.")
            change = receipt.for_edit(
                before, after, find_text=find_text, replacement=replacement,
                metadata_keys=set(metadata or {}),
            )
            return {
                "mutation": result, "note": self._public_note(after),
                "knowledge_change": change, "knowledge_change_text": receipt.render(change),
            }

    async def revise(
        self,
        identifier: str,
        expected_content_sha256: str,
        replacements: list[dict[str, str]],
        preview: bool = False,
    ) -> dict[str, Any]:
        """Apply connected exact replacements against one current note body."""
        if not isinstance(expected_content_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_content_sha256):
            raise ValueError("expected_content_sha256 must be a lowercase SHA-256 digest")
        if not isinstance(preview, bool):
            raise ValueError("preview must be a boolean")
        async with self.backend.mutation():
            before = await self._read_full(identifier)
            await self._check_generic_note(before)
            body = before["content"]
            if self._content_sha256(body) != expected_content_sha256:
                raise KnowledgeError("content revision conflict; read the current complete note before retrying")
            expected = apply_exact_replacements(body, replacements)
            if preview:
                return {
                    "preview": True, "identifier": self._identifier(before),
                    "expected_content_sha256": expected_content_sha256,
                    "proposed_content": expected,
                    "proposed_content_sha256": self._content_sha256(expected),
                }
            result = await self._call_mutation("edit_note", {
                "identifier": self._identifier(before), "operation": "find_replace",
                "find_text": body, "content": expected, "expected_replacements": 1,
            })
            after = await self._read_after_mutation(self._identifier(before))
            if after["content"] != expected:
                raise MutationUncertain("revise readback did not match the requested changes; a write may have committed. Inspect current state before retrying.")
            change = receipt.for_revise(before, after, replacements)
            return {
                "mutation": result, "note": self._public_note(after),
                "knowledge_change": change, "knowledge_change_text": receipt.render(change),
            }

    async def list(
        self,
        namespace: str = "/",
        depth: int = 1,
        page: int = 1,
        page_size: int = 20,
        glob: str | None = None,
        sort: Literal["title_asc", "title_desc", "updated_asc", "updated_desc"] | None = None,
    ) -> dict[str, Any]:
        if depth < 1 or depth > 10 or page < 1 or page_size < 1 or page_size > 200:
            raise ValueError("depth must be 1..10, page >= 1, and page_size 1..200")
        if sort is not None and sort not in {"title_asc", "title_desc", "updated_asc", "updated_desc"}:
            raise ValueError("sort must be title_asc, title_desc, updated_asc, updated_desc, or omitted")
        payload = await self.backend.call(
            "list_directory",
            {"dir_name": self._namespace(namespace), "depth": depth,
             "file_name_glob": glob, "sort": sort, "page": page, "page_size": page_size},
        )
        nodes = payload.get("nodes")
        if not isinstance(nodes, list):
            raise KnowledgeError("list_directory returned invalid nodes")
        return {
            "nodes": [self._directory_node(node) for node in nodes],
            "page": int(payload.get("page", page)),
            "page_size": int(payload.get("page_size", page_size)),
            "total": int(payload.get("total", 0)),
            "has_more": bool(payload.get("has_more", False)),
        }

    async def context(
        self,
        namespace: str | None = None,
        identifiers: list[str] | None = None,
        page: int = 1,
        page_size: int = 5,
        max_chars: int = 12_000,
    ) -> dict[str, Any]:
        if (namespace is None) == (identifiers is None):
            raise ValueError("provide exactly one of namespace or identifiers")
        if page < 1 or page_size < 1 or page_size > 20 or max_chars < 1 or max_chars > 50_000:
            raise ValueError("invalid context page, page_size, or max_chars")
        listing = None
        omitted: list[dict[str, str]] = []
        if namespace is not None:
            listing = await self.list(namespace, depth=1, page=page, page_size=page_size)
            selected = []
            for node in listing["nodes"]:
                path = node.get("file_path")
                if node.get("type") == "file" and isinstance(path, str):
                    if path.lower().endswith(".md"):
                        selected.append(path)
                    else:
                        omitted.append({"identifier": path, "reason": "not_markdown"})
        else:
            if not isinstance(identifiers, list) or not identifiers or len(identifiers) > 20:
                raise ValueError("identifiers must contain between 1 and 20 entries")
            selected = list(dict.fromkeys(identifiers))

        notes: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        used = 0
        for index, identifier in enumerate(selected):
            if used >= max_chars:
                omitted.extend({"identifier": item, "reason": "character_budget"}
                               for item in selected[index:])
                break
            try:
                note = await self._read_full(identifier)
            except (BackendError, KnowledgeError) as error:
                errors.append({"identifier": identifier, "error": str(error)})
                continue
            if not str(note.get("file_path", "")).lower().endswith(".md"):
                omitted.append({"identifier": identifier, "reason": "not_markdown"})
                continue
            available = max_chars - used
            public = self._public_note(note, 0, available)
            used += len(public["content"])
            notes.append(public)
        return {
            "listing": listing,
            "notes": notes,
            "omitted": omitted,
            "errors": errors,
            "used_chars": used,
            "max_chars": max_chars,
            "partial": bool(omitted or errors or any(note["truncated"] for note in notes)
                            or (listing and listing["has_more"])),
            "content_is_data": True,
        }

    async def related(
        self, identifier: str, namespaces: list[str], depth: int = 1,
        max_notes: int = 10, max_chars: int = 12_000,
    ) -> dict[str, Any]:
        """Discover native graph neighbors, then read current scoped knowledge."""
        if not namespaces or not isinstance(namespaces, list):
            raise ValueError("namespaces must be a nonempty list")
        if not 1 <= depth <= 3 or not 1 <= max_notes <= 20 or not 1 <= max_chars <= 50_000:
            raise ValueError("depth must be 1..3, max_notes 1..20, and max_chars 1..50000")
        scopes = [self._namespace(value) for value in namespaces]
        seed = await self._read_full(identifier)
        if not self._in_scopes(self._identifier(seed), scopes, True):
            raise ValueError("the starting note is outside the requested namespaces")
        selected, excluded, limited = await self._related_paths(seed, identifier, scopes, depth, max_notes)
        bundle = await self.context(identifiers=selected[:max_notes], max_chars=max_chars)
        return bundle | {"graph": {"depth": depth, "selected_notes": len(selected[:max_notes]),
                                   "excluded_outside_scope": excluded, "limited": limited,
                                   "source": "basic_memory_relations"},
                         "partial": bool(bundle["partial"] or limited or excluded)}

    async def _related_paths(self, seed, identifier, scopes, depth, max_notes):
        """Follow bounded primary pagination without hiding related-result limits."""
        selected, excluded, limited = [self._identifier(seed)], set(), False
        for page in range(1, 6):
            native = await self.backend.call("build_context", {
                "url": seed.get("permalink") or identifier, "depth": depth,
                "timeframe": None, "page": page, "page_size": 1, "max_related": 100,
            })
            limited |= native.get("metadata", {}).get("related_count", 0) >= 100
            for result in native.get("results", []):
                for item in [result.get("primary_result", {}), *result.get("related_results", [])]:
                    path = item.get("file_path")
                    if not isinstance(path, str) or item.get("type") != "entity":
                        continue
                    if not self._in_scopes(path, scopes, True):
                        excluded.add(path)
                    elif path not in selected:
                        selected.append(path)
            if len(selected) > max_notes:
                limited = True
                break
            if not native.get("has_more"):
                break
        else:
            limited = True
        return selected, len(excluded), limited

    async def move(
        self, identifier: str, destination: str, is_namespace: bool = False
    ) -> dict[str, Any]:
        destination = self._relative_path(destination)
        if is_namespace:
            source = self._namespace(identifier)
            if source == "/":
                raise ValueError("the root namespace cannot be moved")
            async with self.backend.mutation():
                await self._check_namespace_move(source)
                result = await self._call_mutation(
                    "move_note",
                    {"identifier": source.lstrip("/"), "destination_path": destination,
                     "is_directory": True},
                )
                if result.get("moved") is not True:
                    raise MutationUncertain("Basic Memory did not confirm the namespace move; a write may have committed. Inspect current state before retrying.")
                if self._relative_path(str(result.get("destination", ""))) != destination:
                    raise MutationUncertain("the namespace did not move to the requested path; a write may have committed. Inspect current state before retrying.")
                namespace = "/" + destination.strip("/")
                change = receipt.for_namespace_move(source, namespace, result)
                return {
                    "mutation": result, "namespace": namespace,
                    "knowledge_change": change, "knowledge_change_text": receipt.render(change),
                }

        async with self.backend.mutation():
            before = await self._read_full(identifier)
            await self._check_generic_note(before)
            result = await self._call_mutation(
                "move_note",
                {"identifier": self._identifier(before), "destination_path": destination,
                 "is_directory": False},
            )
            if result.get("moved") is not True:
                raise MutationUncertain("Basic Memory did not confirm the note move; a write may have committed. Inspect current state before retrying.")
            actual = result.get("file_path") or destination
            if self._relative_path(str(actual)) != destination:
                raise MutationUncertain("the note did not move to the requested path; a write may have committed. Inspect current state before retrying.")
            after = await self._read_after_mutation(destination)
            if after["content"] != before["content"] or any(
                self._metadata(after).get(key) != value
                for key, value in self._metadata(before).items() if key != "permalink"
            ):
                raise MutationUncertain("move readback did not preserve the note; a write may have committed. Inspect current state before retrying.")
            change = receipt.for_note_move(before, after)
            return {
                "mutation": result, "note": self._public_note(after),
                "knowledge_change": change, "knowledge_change_text": receipt.render(change),
            }

    @staticmethod
    def _body_matches(body: str, expected: str) -> bool:
        body = body.replace("\r\n", "\n").replace("\r", "\n")
        expected = expected.replace("\r\n", "\n").replace("\r", "\n")
        return expected in {body, body[1:] if body.startswith("\n") else body,
                            body[:-1] if body.endswith("\n") else body,
                            body[1:-1] if body.startswith("\n") and body.endswith("\n") else body}

    async def _call_mutation(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await self.backend.call(name, arguments)
            if not isinstance(result, dict):
                raise MutationUncertain("Mutation returned an invalid acknowledgment; inspect current state before retrying.")
            return result
        except BackendError as error:
            raise MutationUncertain("Mutation outcome is uncertain; a write may have committed. Inspect current state before retrying.") from error

    async def _read_after_mutation(self, identifier: str) -> dict[str, Any]:
        try:
            return await self._read_full(identifier)
        except (BackendError, KnowledgeError) as error:
            raise MutationUncertain("Readback failed after a mutation; a write may have committed. Inspect current state before retrying.") from error

    async def _check_generic_note(self, note: dict[str, Any]) -> None:
        """Internal mutation hook, called while the backend lock is held."""

    async def _check_namespace_move(self, namespace: str) -> None:
        """Internal namespace hook, called while the backend lock is held."""

    async def _read_full(self, identifier: str) -> dict[str, Any]:
        payload = await self.backend.call(
            "read_note", {"identifier": identifier, "include_frontmatter": False}
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("content"), str):
            raise KnowledgeError("read_note returned no exact note")
        if not self._matches(identifier, payload):
            raise KnowledgeError(f"read_note returned a fuzzy match for {identifier!r}")
        return payload

    @staticmethod
    def _metadata(note: dict[str, Any]) -> dict[str, Any]:
        value = note.get("frontmatter", note.get("metadata", {}))
        return value if isinstance(value, dict) else {}

    @classmethod
    def _public_note(
        cls, note: dict[str, Any], offset: int = 0, limit: int = 12_000
    ) -> dict[str, Any]:
        content = note["content"]
        end = min(len(content), offset + limit)
        return {
            "identifier": cls._identifier(note), "title": note.get("title", ""),
            "permalink": note.get("permalink"), "file_path": note.get("file_path"),
            "content": content[offset:end], "content_sha256": cls._content_sha256(content),
            "metadata": cls._metadata(note), "offset": offset,
            "next_offset": end if end < len(content) else None, "truncated": end < len(content),
            "content_is_data": True,
        }

    @staticmethod
    def _content_sha256(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _encode_collection_cursor(search_cursor: str | None, fingerprint: str) -> str:
        if not isinstance(search_cursor, str):
            raise KnowledgeError("collection scan did not return a continuation cursor")
        raw = json.dumps({"search_cursor": search_cursor, "fingerprint": fingerprint}, separators=(",", ":"))
        return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

    @staticmethod
    def _decode_collection_cursor(cursor: str, fingerprint: str) -> str:
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            value = json.loads(raw)
            if value["fingerprint"] != fingerprint or not isinstance(value["search_cursor"], str):
                raise ValueError
            return value["search_cursor"]
        except (binascii.Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("cursor is invalid or belongs to another collection inspection") from error

    @staticmethod
    def _identifier(note: dict[str, Any]) -> str:
        value = note.get("file_path") or note.get("permalink")
        if not isinstance(value, str) or not value:
            raise KnowledgeError("note has no stable identifier")
        return value

    @staticmethod
    def _mutation_identifier(result: dict[str, Any]) -> str:
        value = result.get("file_path") or result.get("permalink")
        if not isinstance(value, str) or not value:
            raise MutationUncertain("Mutation returned no usable identifier; a write may have committed. Inspect the requested namespace before retrying.")
        return value

    @classmethod
    def _matches(cls, requested: str, note: dict[str, Any]) -> bool:
        requested = requested.strip().replace("\\", "/").lstrip("/")
        candidates = {str(value).replace("\\", "/").lstrip("/")
                      for value in (note.get("file_path"), note.get("permalink")) if value}
        path = str(note.get("file_path", "")).replace("\\", "/").lstrip("/")
        if "/" in path and path.endswith(".md"):
            candidates.add(path.removesuffix(".md"))
        if requested.startswith("memory://"):
            return requested.removeprefix("memory://").lstrip("/") in candidates
        return requested in candidates

    @classmethod
    def _search_item(cls, row: Any) -> dict[str, Any] | None:
        if not isinstance(row, dict) or not isinstance(row.get("file_path"), str):
            raise KnowledgeError("search_notes returned an entity without a physical file path")
        snippet = row.get("matched_chunk") or row.get("content") or row.get("text") or ""
        return {
            "identifier": row["file_path"], "file_path": row["file_path"],
            "title": row.get("title", ""), "permalink": row.get("permalink"),
            "snippet": str(snippet)[:1_000], "metadata": cls._metadata(row),
            "item_type": row.get("type", row.get("entity_type", "entity")),
            "item_id": row.get("observation_id", row.get("relation_id", row.get("external_id"))),
            "category": row.get("category"),
        }

    @classmethod
    def _directory_node(cls, node: Any) -> dict[str, Any]:
        if not isinstance(node, dict) or node.get("type") not in {"file", "directory"}:
            raise KnowledgeError("list_directory returned an invalid node")
        children = node.get("children", [])
        if not isinstance(children, list):
            raise KnowledgeError("list_directory returned invalid children")
        return {key: (None if key == "file_path" and node["type"] == "directory" else node.get(key))
                for key in ("type", "file_path", "directory_path", "name", "title", "permalink",
                            "external_id", "note_type", "content_type", "updated_at")} | {
            "children": [cls._directory_node(child) for child in children]
        }

    @staticmethod
    def _namespace(value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("namespace must be a string")
        raw = value.strip().replace("\\", "/")
        if raw in {"", "/"}:
            return "/"
        if re.match(r"^[A-Za-z]:", raw) or "//" in raw:
            raise ValueError("namespace must be a project-relative logical path")
        parts = raw.strip("/").split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("namespace cannot contain empty, dot, or parent segments")
        return "/" + "/".join(parts)

    @staticmethod
    def _relative_path(value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("destination must be a string")
        raw = value.strip().replace("\\", "/")
        if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw) or "//" in raw:
            raise ValueError("destination must be a nonempty relative path")
        parts = raw.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("destination cannot contain empty, dot, or parent segments")
        return "/".join(parts)

    @staticmethod
    def _in_scopes(file_path: str, scopes: list[str], recursive: bool) -> bool:
        path = file_path.replace("\\", "/").lstrip("/")
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        for scope in scopes:
            directory = scope.lstrip("/")
            if parent == directory or recursive and (not directory or parent.startswith(directory + "/")):
                return True
        return False

    @staticmethod
    def _encode_cursor(offset: int, fingerprint: str, native_total: int | None = None, index_changed: bool = False, restart: bool = False, recovering: bool = False) -> str:
        raw = json.dumps({"offset": offset, "fingerprint": fingerprint,
                          "native_total": native_total, "index_changed": index_changed,
                          "restart": restart, "recovering": recovering}, separators=(",", ":"))
        return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str, fingerprint: str) -> tuple[int, int | None, bool, bool, bool]:
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            value = json.loads(raw)
            offset = value["offset"]
            if value["fingerprint"] != fingerprint or not isinstance(offset, int) or offset < 0:
                raise ValueError
            total = value.get("native_total")
            changed = value.get("index_changed", False)
            restart = value.get("restart", False)
            recovering = value.get("recovering", False)
            if total is not None and (type(total) is not int or total < 0) or any(type(flag) is not bool for flag in (changed, restart, recovering)):
                raise ValueError
            return offset, total, changed, restart, recovering
        except (binascii.Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("cursor is invalid or belongs to another search") from error


__all__ = ["BackendError", "KnowledgeError", "KnowledgeService"]


def __getattr__(name):
    # Preserve the previous Python entrypoint while routing through the engine.
    if name == "KnowledgeService":
        from .engine import KnowledgeEngine
        return KnowledgeEngine
    raise AttributeError(name)
