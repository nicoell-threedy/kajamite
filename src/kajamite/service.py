"""Bounded note and namespace operations over Basic Memory's public MCP tools."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any

from .backend import BackendError


class KnowledgeError(RuntimeError):
    """The requested knowledge operation could not be completed safely."""


class KnowledgeService:
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
    ) -> dict[str, Any]:
        if not isinstance(namespaces, list) or not namespaces:
            raise ValueError("namespaces must be a nonempty list")
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100")
        scopes = list(dict.fromkeys(self._namespace(value) for value in namespaces))
        criteria = [str(getattr(self.backend, "project", "")), query, scopes, recursive, kind, metadata]
        fingerprint = hashlib.sha256(
            json.dumps(criteria, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        offset = self._decode_cursor(cursor, fingerprint) if cursor else 0
        native_page, skip = divmod(offset, self._native_page_size)
        native_page += 1
        results: list[dict[str, Any]] = []
        scanned = pages = 0
        exhausted = False

        while pages < self._native_page_budget:
            arguments: dict[str, Any] = {
                "query": query,
                "search_type": "text",
                "entity_types": ["entity"],
                "page": native_page,
                "page_size": self._native_page_size,
            }
            if kind is not None:
                arguments["note_types"] = [kind]
            if metadata is not None:
                arguments["metadata_filters"] = metadata
            payload = await self.backend.call("search_notes", arguments)
            rows = payload.get("results")
            if not isinstance(rows, list):
                raise KnowledgeError("search_notes returned invalid results")
            pages += 1
            stopped = False
            for index, row in enumerate(rows):
                if index < skip:
                    continue
                offset = (native_page - 1) * self._native_page_size + index + 1
                scanned += 1
                item = self._search_item(row)
                if item and self._in_scopes(item["file_path"], scopes, recursive):
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
        return {
            "results": results,
            "next_cursor": None if exhausted else self._encode_cursor(offset, fingerprint),
            "has_more": not exhausted,
            "exhausted": exhausted,
            "retrieval_mode": "text",
            "scanned_results": scanned,
            "scan_limited": scan_limited,
        }

    async def read(self, identifier: str, offset: int = 0, limit: int = 12_000) -> dict[str, Any]:
        if offset < 0 or limit < 1:
            raise ValueError("offset must be >= 0 and limit must be >= 1")
        return self._public_note(await self._read_full(identifier), offset, min(limit, 12_000))

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
            result = await self.backend.call(
                "write_note",
                {"title": title, "content": content, "directory": directory,
                 "note_type": kind, "metadata": metadata, "overwrite": False},
            )
            note = await self._read_full(self._mutation_identifier(result))
            return {"mutation": result, "note": self._public_note(note)}

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
            result = await self.backend.call("edit_note", arguments)
            after = await self._read_full(self._identifier(before))
            if after["content"] != expected or any(
                self._metadata(after).get(key) != value for key, value in (metadata or {}).items()
            ):
                raise KnowledgeError("edit readback did not match the requested changes")
            return {"mutation": result, "note": self._public_note(after)}

    async def list(
        self,
        namespace: str = "/",
        depth: int = 1,
        page: int = 1,
        page_size: int = 20,
        glob: str | None = None,
        sort: str | None = None,
    ) -> dict[str, Any]:
        if depth < 1 or depth > 10 or page < 1 or page_size < 1 or page_size > 200:
            raise ValueError("depth must be 1..10, page >= 1, and page_size 1..200")
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

    async def move(
        self, identifier: str, destination: str, is_namespace: bool = False
    ) -> dict[str, Any]:
        destination = self._relative_path(destination)
        if is_namespace:
            source = self._namespace(identifier)
            if source == "/":
                raise ValueError("the root namespace cannot be moved")
            async with self.backend.mutation():
                result = await self.backend.call(
                    "move_note",
                    {"identifier": source.lstrip("/"), "destination_path": destination,
                     "is_directory": True},
                )
                if result.get("moved") is not True:
                    raise KnowledgeError("Basic Memory did not confirm the namespace move")
                if self._relative_path(str(result.get("destination", ""))) != destination:
                    raise KnowledgeError("the namespace did not move to the requested path")
                return {"mutation": result, "namespace": "/" + destination.strip("/")}

        async with self.backend.mutation():
            before = await self._read_full(identifier)
            result = await self.backend.call(
                "move_note",
                {"identifier": self._identifier(before), "destination_path": destination,
                 "is_directory": False},
            )
            if result.get("moved") is not True:
                raise KnowledgeError("Basic Memory did not confirm the note move")
            actual = result.get("file_path") or destination
            if self._relative_path(str(actual)) != destination:
                raise KnowledgeError("the note did not move to the requested path")
            after = await self._read_full(destination)
            if after["content"] != before["content"] or any(
                self._metadata(after).get(key) != value
                for key, value in self._metadata(before).items() if key != "permalink"
            ):
                raise KnowledgeError("move readback did not preserve the note")
            return {"mutation": result, "note": self._public_note(after)}

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
            "content": content[offset:end], "metadata": cls._metadata(note), "offset": offset,
            "next_offset": end if end < len(content) else None, "truncated": end < len(content),
            "content_is_data": True,
        }

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
            raise KnowledgeError("mutation returned no usable identifier")
        return value

    @classmethod
    def _matches(cls, requested: str, note: dict[str, Any]) -> bool:
        requested = requested.strip().replace("\\", "/").lstrip("/")
        candidates = {str(value).replace("\\", "/").lstrip("/")
                      for value in (note.get("file_path"), note.get("permalink")) if value}
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
    def _encode_cursor(offset: int, fingerprint: str) -> str:
        raw = json.dumps({"offset": offset, "fingerprint": fingerprint}, separators=(",", ":"))
        return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str, fingerprint: str) -> int:
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            value = json.loads(raw)
            offset = value["offset"]
            if value["fingerprint"] != fingerprint or not isinstance(offset, int) or offset < 0:
                raise ValueError
            return offset
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("cursor is invalid or belongs to another search") from error


__all__ = ["BackendError", "KnowledgeError", "KnowledgeService"]
