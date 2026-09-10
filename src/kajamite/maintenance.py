"""Bounded maintenance and removal operations for a governed knowledge engine."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from . import receipt
from .errors import BackendError, MutationUncertain
from .service import KnowledgeError, NoteOperations


class MaintenanceOperations:
    """Mixin for an engine exposing the record and authorization helper methods."""

    _maintenance_inventory_limit = 5

    async def _maintenance_inventory(self, namespace: str) -> list[tuple[str, dict[str, Any]]]:
        pending = [self._namespace(namespace)]
        seen: set[str] = set()
        requests = 0
        records: list[tuple[str, dict[str, Any]]] = []
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            page = 1
            while True:
                if requests >= self._maintenance_inventory_limit:
                    raise KnowledgeError("maintenance inventory is incomplete; no transitions were started")
                requests += 1
                listing = await NoteOperations.list(self, current, depth=1, page=page, page_size=200)
                for node in listing["nodes"]:
                    if node.get("type") == "directory" and isinstance(node.get("directory_path"), str):
                        pending.append(node["directory_path"])
                    identifier = node.get("file_path")
                    if node.get("type") != "file" or not isinstance(identifier, str):
                        continue
                    await self._authorize(identifier, None)
                    note = await self._read_full(identifier)
                    record = self._record_from_note(note)
                    if record is not None:
                        records.append((identifier, record))
                if not listing["has_more"]:
                    break
                page += 1
        return records

    @staticmethod
    def _maintenance_id(prefix: str, *parts: str) -> str:
        return prefix + "-" + hashlib.sha256("\x1f".join(parts).encode()).hexdigest()

    async def record_maintain(self, namespace: str, condition_id: str, timestamp: str,
                              actor: str, reason: str) -> dict[str, Any]:
        """Mark supported dependents stale when an in-scope dependency is unavailable."""
        inventory = await self._maintenance_inventory(namespace)
        by_id: dict[str, tuple[str, dict[str, Any]]] = {}
        failures: list[dict[str, str]] = []
        for identifier, record in inventory:
            record_id = record["record_id"]
            if record_id in by_id:
                failures.append({"record_id": record_id, "error": "ambiguous record ID in namespace"})
            else:
                by_id[record_id] = (identifier, record)
        if failures:
            return {"completed": [], "errors": failures, "partial": True}
        cycles = self._dependency_cycles(by_id)
        if cycles:
            return {"completed": [], "errors": [{"record_id": item, "error": "dependency cycle"}
                                                     for item in sorted(cycles)], "partial": True}

        completed: list[dict[str, Any]] = []
        current = {record_id: dict(record) for record_id, (_, record) in by_id.items()}
        while True:
            candidates: list[tuple[str, str]] = []
            for record_id, record in current.items():
                if record["status"] != "supported":
                    continue
                invalid = [dependency for dependency in record["depends_on"]
                           if dependency not in current or current[dependency]["status"] != "supported"
                           or record["verification"].get("dependency_revisions", {}).get(dependency) != current[dependency]["record_revision"]]
                if invalid:
                    candidates.append((record_id, sorted(invalid)[0]))
            if not candidates:
                break
            for record_id, target in sorted(candidates):
                identifier, _ = by_id[record_id]
                record = current[record_id]
                operation_id = self._maintenance_id("maintenance", condition_id, record_id, target)
                target_condition = self._maintenance_id("dependency", condition_id, target)
                try:
                    result = await self.record_transition(
                        identifier, "dependency_health", record["record_revision"], operation_id,
                        timestamp, actor, reason, {"condition_id": target_condition},
                    )
                    current[record_id] = result["record"]
                    completed.append({"record_id": record_id, "identifier": identifier,
                                      "committed_revision": result["committed_revision"],
                                      "replayed": bool(result.get("replayed")),
                                      "knowledge_change": result.get("knowledge_change"),
                                      "knowledge_change_text": result.get("knowledge_change_text")})
                    if current[record_id]["status"] == "supported":
                        failures.append({"record_id": record_id, "error": "maintenance made no progress; use a new condition ID for a new source change"})
                except (BackendError, KnowledgeError, ValueError) as error:
                    failures.append({"record_id": record_id, "error": str(error)})
            if failures:
                break
        return {"completed": completed, "errors": failures,
                "partial": bool(failures)}

    @staticmethod
    def _dependency_cycles(records: Mapping[str, tuple[str, Mapping[str, Any]]]) -> set[str]:
        visiting: set[str] = set()
        visited: set[str] = set()
        cycles: set[str] = set()
        def visit(record_id: str, trail: list[str]) -> None:
            if record_id in visiting:
                cycles.update(trail[trail.index(record_id):])
                return
            if record_id in visited or record_id not in records:
                return
            visiting.add(record_id)
            for dependency in records[record_id][1]["depends_on"]:
                visit(dependency, trail + [dependency])
            visiting.remove(record_id)
            visited.add(record_id)
        for record_id in records:
            visit(record_id, [record_id])
        return cycles

    async def record_remove(self, identifier: str, expected_revision: int) -> dict[str, Any]:
        """Delete one exact governed note and report only bounded projection evidence."""
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 1:
            raise ValueError("expected_revision must be a positive integer")
        await self._authorize(identifier, None)
        async with self.backend.mutation():
            before = await self._read_full(identifier)
            record = self._record_from_note(before)
            if record is None:
                raise KnowledgeError("note is not a governed record")
            if record["record_revision"] != expected_revision:
                raise KnowledgeError("record revision conflict; read the current record before retrying")
            result = await self._call_mutation("delete_note", {
                "identifier": self._identifier(before), "is_directory": False,
            })
            if not isinstance(result, dict) or result.get("deleted") is not True:
                raise MutationUncertain("Deletion outcome is uncertain; the record may be removed. Inspect current state before retrying.")
        projection = await self._removal_projection(self._identifier(before))
        change = self._removal_receipt(before)
        return {"mutation": result, "identifier": self._identifier(before),
                "committed_revision": record["record_revision"], "knowledge_change": change,
                "knowledge_change_text": receipt.render(change), "projection": projection,
                "partial": projection != "absent"}

    async def _removal_projection(self, identifier: str) -> str:
        for page in range(1, self._maintenance_inventory_limit + 1):
            try:
                payload = await self.backend.call("search_notes", {
                    "query": None, "search_type": "text", "entity_types": ["entity"],
                    "page": page, "page_size": 50,
                })
            except BackendError:
                return "unknown"
            rows = payload.get("results") if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                return "unknown"
            if any(isinstance(row, dict) and row.get("file_path") == identifier for row in rows):
                return "pending"
            if payload.get("has_more") is False and payload.get("total_is_exact", True) is True:
                return "absent"
            if not payload.get("has_more", False):
                return "unknown"
        return "unknown"

    @staticmethod
    def _removal_receipt(before: Mapping[str, Any]) -> dict[str, Any]:
        content = before["content"]
        value = {"preview": content[:receipt.VALUE_PREVIEW_CHARS], "characters": len(content),
                 "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                 "truncated": len(content) > receipt.VALUE_PREVIEW_CHARS}
        return {"schema_version": receipt.SCHEMA_VERSION, "operation": "remove_note",
                "coverage": receipt.COVERAGE, "coverage_notice": receipt.COVERAGE_NOTICE,
                "before": {"identifier": before["file_path"], "content_sha256": value["sha256"]},
                "after": None, "body_change": {"kind": "removed", "before": value, "after": None},
                "metadata_changes": [], "affected_notes": 1, "affected_notes_exact": True,
                "verification": "backend_confirmed", "readback_verified": False}


__all__ = ["MaintenanceOperations"]
