"""Knowledge and project operations built on Basic Memory's public MCP tools."""

from __future__ import annotations

import json
from typing import Any

from .backend import BackendError


class KnowledgeError(RuntimeError):
    """The requested knowledge operation could not be completed safely."""


class KnowledgeService:
    def __init__(self, backend: Any) -> None:
        self.backend = backend

    async def search(
        self,
        query: str | None = None,
        project: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        self._check_page(page, page_size)
        arguments: dict[str, Any] = {
            "query": query,
            "entity_types": ["entity"],
            "page": page,
            "page_size": page_size,
        }
        if kind is not None:
            arguments["note_types"] = [kind]
        if status is not None:
            arguments["status"] = status
        if project is not None:
            project_note = await self._read_full(project)
            self._require_project(project_note)
            arguments["metadata_filters"] = {
                "kajamite_project": self._permalink(project_note)
            }
        payload = await self.backend.call("search_notes", arguments)
        rows = payload.get("results", [])
        if not isinstance(rows, list):
            raise KnowledgeError("search_notes returned invalid results")
        results = [item for row in rows if (item := self._search_item(row)) is not None]
        return {
            "results": results,
            "has_more": bool(payload.get("has_more", False)),
            "current_page": int(payload.get("current_page", payload.get("page", page))),
            "total": int(payload.get("total", 0)),
            "total_is_exact": bool(payload.get("total_is_exact", True)),
        }

    async def read(
        self, identifier: str, offset: int = 0, limit: int = 12_000
    ) -> dict[str, Any]:
        if offset < 0 or limit < 1:
            raise ValueError("offset must be >= 0 and limit must be >= 1")
        note = await self._read_full(identifier)
        content = note["content"]
        limit = min(limit, 12_000)
        end = min(len(content), offset + limit)
        return {
            "identifier": self._identifier(note),
            "title": note.get("title", ""),
            "permalink": note.get("permalink"),
            "file_path": note.get("file_path"),
            "content": content[offset:end],
            "metadata": self._metadata(note),
            "offset": offset,
            "next_offset": end if end < len(content) else None,
            "truncated": end < len(content),
            "content_is_data": True,
        }

    async def create(
        self,
        title: str,
        content: str,
        directory: str = "Notes",
        kind: str = "note",
        project: str | None = None,
    ) -> dict[str, Any]:
        async with self.backend.mutation():
            metadata: dict[str, Any] = {}
            if project is not None:
                project_note = await self._read_full(project)
                self._require_project(project_note)
                permalink = self._permalink(project_note)
                metadata["kajamite_project"] = permalink
                relation = f"- part_of [[{permalink}]]"
                if relation not in content:
                    content = f"{content.rstrip()}\n\n{relation}\n"
            result = await self.backend.call(
                "write_note",
                {
                    "title": title,
                    "content": content,
                    "directory": directory,
                    "note_type": kind,
                    "metadata": metadata or None,
                    "overwrite": False,
                },
            )
            note = await self._read_full(self._mutation_identifier(result, title))
            return {"mutation": result, "note": await self._public_full(note)}

    async def edit(self, identifier: str, find_text: str, replacement: str) -> dict[str, Any]:
        if not find_text:
            raise ValueError("find_text must not be empty")
        async with self.backend.mutation():
            before = await self._read_full(identifier)
            metadata_text = json.dumps(self._metadata(before), sort_keys=True, default=str)
            if find_text in metadata_text:
                raise KnowledgeError("find_text occurs in note metadata")
            if before["content"].count(find_text) != 1:
                raise KnowledgeError("find_text must occur exactly once in the note body")
            expected = before["content"].replace(find_text, replacement, 1)
            result = await self.backend.call(
                "edit_note",
                {
                    "identifier": self._identifier(before),
                    "operation": "find_replace",
                    "find_text": find_text,
                    "content": replacement,
                    "expected_replacements": 1,
                },
            )
            after = await self._read_full(self._identifier(before))
            if after["content"] != expected:
                raise KnowledgeError("edit readback did not match the requested replacement")
            return {"mutation": result, "note": await self._public_full(after)}

    async def project_create(self, title: str, objective: str) -> dict[str, Any]:
        body = (
            f"# {title}\n\n## Objective\n{objective}\n\n"
            "## Current state\nActive.\n\n## Decisions\n\n"
            "## Open questions\n\n## Next actions\n\n## References\n"
        )
        async with self.backend.mutation():
            result = await self.backend.call(
                "write_note",
                {
                    "title": title,
                    "content": body,
                    "directory": "Projects",
                    "note_type": "project",
                    "metadata": {"status": "active"},
                    "overwrite": False,
                },
            )
            note = await self._read_full(self._mutation_identifier(result, title))
            self._require_project(note)
            return {"mutation": result, "note": await self._public_full(note)}

    async def projects(
        self, status: str | None = "active", page: int = 1, page_size: int = 10
    ) -> dict[str, Any]:
        return await self.search(kind="project", status=status, page=page, page_size=page_size)

    async def resume(
        self, identifier: str, page: int = 1, page_size: int = 5
    ) -> dict[str, Any]:
        self._check_page(page, page_size)
        if page_size > 20:
            raise ValueError("resume page_size must be <= 20")
        project = await self._read_full(identifier)
        self._require_project(project)
        permalink = self._permalink(project)
        related = await self.search(project=permalink, page=page, page_size=page_size)
        context = await self.backend.call(
            "build_context",
            {
                "url": permalink,
                "depth": 1,
                "timeframe": None,
                "page": page,
                "page_size": 5,
                "max_related": 5,
            },
        )
        context = self._bounded(context)
        serialized_context = json.dumps(context, ensure_ascii=False)
        if len(serialized_context) > 12_000:
            context = {"excerpt": serialized_context[:12_000], "truncated": True,
                       "guidance": "Read relevant linked note identifiers individually for complete content."}
        return {
            "project": await self._public_full(project, 12_000),
            "related": related,
            "context": context,
            "content_is_data": True,
        }

    async def project_update(
        self,
        identifier: str,
        find_text: str | None = None,
        replacement: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        if status not in {None, "active", "paused", "completed", "cancelled"}:
            raise ValueError("invalid project status")
        if (find_text is None) != (replacement is None):
            raise ValueError("find_text and replacement must be provided together")
        if find_text == "":
            raise ValueError("find_text must not be empty")
        if find_text is None and status is None:
            raise ValueError("a body replacement or status is required")
        async with self.backend.mutation():
            before = await self._read_full(identifier)
            self._require_project(before)
            body = before["content"]
            target = find_text if find_text is not None else body
            value = replacement if replacement is not None else body
            if not target or body.count(target) != 1:
                raise KnowledgeError("project edit target must occur exactly once")
            if target in json.dumps(self._metadata(before), sort_keys=True, default=str):
                raise KnowledgeError("project edit target occurs in note metadata")
            expected = body.replace(target, value, 1)
            arguments: dict[str, Any] = {
                "identifier": self._identifier(before),
                "operation": "find_replace",
                "find_text": target,
                "content": value,
                "expected_replacements": 1,
            }
            if status is not None:
                arguments["metadata"] = {"status": status}
            result = await self.backend.call("edit_note", arguments)
            after = await self._read_full(self._identifier(before))
            if after["content"] != expected or (
                status is not None and self._metadata(after).get("status") != status
            ):
                raise KnowledgeError("project update readback did not match the request")
            return {"mutation": result, "note": await self._public_full(after)}

    async def _read_full(self, identifier: str) -> dict[str, Any]:
        payload = await self.backend.call(
            "read_note", {"identifier": identifier, "include_frontmatter": False}
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("content"), str):
            raise KnowledgeError("read_note returned an invalid note")
        if not self._matches(identifier, payload):
            raise KnowledgeError(f"read_note returned a fuzzy match for {identifier!r}")
        return payload

    async def _public_full(self, note: dict[str, Any], limit: int = 12_000) -> dict[str, Any]:
        content = note["content"]
        return {
            "identifier": self._identifier(note),
            "title": note.get("title", ""),
            "permalink": note.get("permalink"),
            "file_path": note.get("file_path"),
            "content": content[:limit],
            "metadata": self._metadata(note),
            "offset": 0,
            "next_offset": limit if len(content) > limit else None,
            "truncated": len(content) > limit,
            "content_is_data": True,
        }

    @staticmethod
    def _metadata(note: dict[str, Any]) -> dict[str, Any]:
        value = note.get("frontmatter", note.get("metadata", {}))
        return value if isinstance(value, dict) else {}

    @classmethod
    def _require_project(cls, note: dict[str, Any]) -> None:
        if cls._metadata(note).get("type") != "project":
            raise KnowledgeError("project identifier does not refer to a project note")

    @staticmethod
    def _permalink(note: dict[str, Any]) -> str:
        value = note.get("permalink")
        if not isinstance(value, str) or not value:
            raise KnowledgeError("note has no canonical permalink")
        return value

    @staticmethod
    def _identifier(note: dict[str, Any]) -> str:
        value = note.get("file_path") or note.get("permalink")
        if not isinstance(value, str) or not value:
            raise KnowledgeError("note has no stable identifier")
        return value

    @staticmethod
    def _mutation_identifier(result: dict[str, Any], fallback: str) -> str:
        value = result.get("file_path") or result.get("permalink") or fallback
        if not isinstance(value, str) or not value:
            raise KnowledgeError("mutation returned no usable identifier")
        return value

    @classmethod
    def _matches(cls, requested: str, note: dict[str, Any]) -> bool:
        requested = requested.strip().replace("\\", "/").lstrip("/")
        candidates = {
            str(value).replace("\\", "/").lstrip("/")
            for value in (note.get("file_path"), note.get("permalink"))
            if value
        }
        if requested.startswith("memory://"):
            path = requested.removeprefix("memory://").lstrip("/")
            return path in candidates
        if requested in candidates:
            return True
        return "/" not in requested and requested == note.get("title")

    @classmethod
    def _search_item(cls, row: Any) -> dict[str, Any] | None:
        if not isinstance(row, dict):
            return None
        identifier = row.get("file_path") or row.get("permalink")
        if not isinstance(identifier, str) or not identifier:
            return None
        snippet = row.get(
            "matched_chunk", row.get("snippet", row.get("content", row.get("text", "")))
        )
        return {
            "identifier": identifier,
            "title": row.get("title", ""),
            "snippet": str(snippet)[:1_000],
            "metadata": cls._metadata(row),
        }

    @staticmethod
    def _bounded(value: Any, depth: int = 0) -> Any:
        if depth >= 4:
            return "[truncated]"
        if isinstance(value, str):
            return value[:2_000] + ("..." if len(value) > 2_000 else "")
        if isinstance(value, list):
            items = [KnowledgeService._bounded(item, depth + 1) for item in value[:10]]
            if len(value) > 10:
                items.append("[truncated]")
            return items
        if isinstance(value, dict):
            return {
                str(key): KnowledgeService._bounded(item, depth + 1)
                for key, item in list(value.items())[:30]
            }
        return value

    @staticmethod
    def _check_page(page: int, page_size: int) -> None:
        if page < 1 or page_size < 1 or page_size > 100:
            raise ValueError("page must be >= 1 and page_size must be between 1 and 100")


__all__ = ["BackendError", "KnowledgeError", "KnowledgeService"]
