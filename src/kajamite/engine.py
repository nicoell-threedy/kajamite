"""Persistent governed records over the ordinary note operations.

``authorize(identifier, request_scope)`` may return a bool or an awaitable bool;
it runs before a note is fetched.  ``evidence_checker(record, request_scope)``
may likewise be synchronous or asynchronous and returns whether a supported
record is currently reusable.  Omitting either callback allows local access;
omitting the evidence checker leaves supported records unavailable for reuse.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
from typing import Any, Callable, Mapping

from . import receipt
from .errors import BackendError, MutationUncertain
from .governance import RecordEngine, RecordError
from .service import KnowledgeError, NoteOperations
from .maintenance import MaintenanceOperations


class AccessDenied(KnowledgeError):
    """The consumer denied access without disclosing note details."""


class KnowledgeEngine(MaintenanceOperations, NoteOperations):
    """Note operations with explicit, validated governed-record lifecycle writes."""

    _record_key = "kajamite_record"
    _operations_key = "kajamite_operations"
    _engine_metadata = frozenset({_record_key, _operations_key})
    _governed_kind = "governed-record"
    _inventory_limit = 5

    def __init__(
        self,
        backend: Any,
        *,
        record_engine: RecordEngine | None = None,
        authorize: Callable[[str, Mapping[str, Any] | None], bool] | None = None,
        evidence_checker: Callable[[Mapping[str, Any], Mapping[str, Any] | None], bool] | None = None,
    ) -> None:
        super().__init__(backend)
        self.records = record_engine or RecordEngine()
        self.authorize = authorize
        self.evidence_checker = evidence_checker

    async def _call_guard(self, callback: Callable[..., Any] | None, *arguments: Any) -> bool:
        if callback is None:
            return True
        value = callback(*arguments)
        if inspect.isawaitable(value):
            value = await value
        return value is True

    async def _authorize(self, identifier: str, request_scope: Mapping[str, Any] | None) -> None:
        if not await self._call_guard(self.authorize, identifier, request_scope):
            raise AccessDenied("access denied by authorization policy")

    @classmethod
    def _metadata_without_engine(cls, note: Mapping[str, Any]) -> dict[str, Any]:
        return {key: copy.deepcopy(value) for key, value in cls._metadata(dict(note)).items()
                if key not in cls._engine_metadata}

    def _record_from_note(self, note: Mapping[str, Any]) -> dict[str, Any] | None:
        raw = self._metadata(dict(note)).get(self._record_key)
        if raw is None:
            if self._metadata(dict(note)).get("type") == self._governed_kind or self._operations_key in self._metadata(dict(note)):
                raise KnowledgeError("governed record metadata is missing")
            return None
        if not isinstance(raw, dict):
            raise KnowledgeError("governed record metadata is invalid")
        try:
            record = self.records.validate_record(raw)
        except RecordError as error:
            raise KnowledgeError("governed record metadata is invalid") from error
        if not self._body_matches(str(note.get("content", "")), record["claim"]):
            raise KnowledgeError("governed record body does not match its claim")
        return record

    async def _reuse_allowed(
        self, record: Mapping[str, Any], request_scope: Mapping[str, Any] | None, namespace: str | None = None
    ) -> tuple[bool, str | None]:
        if request_scope is None:
            return False, "unknown_scope"
        if any(request_scope.get(key) != value for key, value in record["scope"].items()):
            return False, "scope_mismatch"
        if record["status"] != "supported":
            return False, f"record_status_{record['status']}"
        if record["depends_on"]:
            if namespace is None:
                return False, "dependency_scope_unknown"
            try:
                inventory = {}
                for item in await self._governed_inventory(namespace):
                    if item["record_id"] in inventory:
                        return False, "dependency_ambiguous"
                    inventory[item["record_id"]] = item
                pending, seen = [record], set()
                while pending:
                    item = pending.pop()
                    if item["record_id"] in seen:
                        continue
                    seen.add(item["record_id"])
                    revisions = item["verification"].get("dependency_revisions", {})
                    for dependency in item["depends_on"]:
                        target = inventory.get(dependency)
                        if target is None or target["status"] != "supported":
                            return False, "dependency_unavailable"
                        if revisions.get(dependency) != target["record_revision"]:
                            return False, "dependency_changed"
                        pending.append(target)
            except (BackendError, KnowledgeError):
                return False, "dependency_check_incomplete"
        if self.evidence_checker is None:
            return False, "source_check_unknown"
        try:
            checked = self.evidence_checker(copy.deepcopy(record), copy.deepcopy(request_scope))
            if inspect.isawaitable(checked):
                checked = await checked
        except Exception:
            return False, "source_check_inaccessible"
        if isinstance(checked, Mapping):
            outcome = checked.get("outcome", "unknown")
            if outcome != "unchanged":
                return False, "source_" + outcome if outcome in {"changed", "missing", "removed", "inaccessible", "unknown"} else "source_check_unknown"
        elif checked is not True:
            return False, "source_check_failed"
        return True, None

    async def create(self, title: str, content: str, namespace: str, kind: str = "note",
                     metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if content.lstrip().startswith("---\n"):
            raise ValueError("supply note metadata through the metadata argument, not body frontmatter")
        if kind == self._governed_kind or self._engine_metadata & set(metadata or {}):
            raise ValueError("generic create cannot set governed record fields")
        await self._authorize(self._namespace(namespace).rstrip("/") + "/" + title, None)
        return await super().create(title, content, namespace, kind, metadata)

    async def edit(self, identifier: str, find_text: str | None = None,
                   replacement: str | None = None,
                   metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._engine_metadata & set(metadata or {}):
            raise ValueError("generic edit cannot set governed record fields")
        await self._authorize(identifier, None)
        return await super().edit(identifier, find_text, replacement, metadata)

    async def _check_generic_note(self, note: dict[str, Any]) -> None:
        if self._record_key in self._metadata(note) or self._metadata(note).get("type") == self._governed_kind:
            raise KnowledgeError("governed records require an explicit lifecycle transition")

    async def _check_namespace_move(self, namespace: str) -> None:
        if await self._namespace_has_governed(namespace):
            raise KnowledgeError("cannot move a namespace containing governed records")

    async def move(self, identifier: str, destination: str, is_namespace: bool = False) -> dict[str, Any]:
        await self._authorize(identifier, None)
        await self._authorize(destination, None)
        return await super().move(identifier, destination, is_namespace)

    async def _namespace_has_governed(self, namespace: str) -> bool:
        """Read a bounded recursive inventory; incompleteness blocks the move."""
        return bool(await self._governed_inventory(namespace))

    async def _governed_inventory(self, namespace: str) -> list[dict[str, Any]]:
        pending = [self._namespace(namespace)]
        seen: set[str] = set()
        records: list[dict[str, Any]] = []
        requests = 0
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            page = 1
            while True:
                if requests >= self._inventory_limit:
                    raise KnowledgeError("namespace inventory is incomplete; operation was not started")
                requests += 1
                listing = await super().list(current, depth=1, page=page, page_size=200)
                for node in listing["nodes"]:
                    if node.get("type") == "directory" and isinstance(node.get("directory_path"), str):
                        pending.append(node["directory_path"])
                    identifier = node.get("file_path")
                    if node.get("type") == "file" and isinstance(identifier, str):
                        await self._authorize(identifier, None)
                        note = await self._read_full(identifier)
                        if self._record_key in self._metadata(note) or self._metadata(note).get("type") == self._governed_kind:
                            record = self._record_from_note(note)
                            if record is None:
                                raise KnowledgeError("governed record metadata is invalid")
                            records.append(record)
                if not listing["has_more"]:
                    break
                page += 1
        return records

    async def record_create(self, namespace: str, record: Mapping[str, Any]) -> dict[str, Any]:
        try:
            value = self.records.validate_record(record)
        except RecordError as error:
            raise KnowledgeError("record creation input is invalid") from error
        if value["record_revision"] != 1 or value["events"][0]["action"] != "create":
            raise KnowledgeError("record_create requires a revision-one create record")
        directory = self._namespace(namespace).lstrip("/")
        await self._authorize((directory + "/" if directory else "") + value["record_id"] + ".md", None)
        metadata = {self._record_key: value, self._operations_key: {}}
        async with self.backend.mutation():
            if any(item["record_id"] == value["record_id"] for item in await self._governed_inventory(namespace)):
                raise KnowledgeError("record ID is already present in this namespace")
            dependencies = await self._validate_dependencies(namespace, value)
            self._bind_dependencies(value, dependencies)
            result = await self._call_mutation("write_note", {
            "title": value["record_id"], "content": value["claim"], "directory": directory,
                "note_type": self._governed_kind, "metadata": metadata, "overwrite": False,
            })
            identifier = self._mutation_identifier(result)
            if not self._in_scopes(identifier, [self._namespace(namespace)], False):
                raise MutationUncertain("Create returned a different namespace; a write may have committed. Inspect current state before retrying.")
            after = await self._read_after_mutation(identifier)
            try:
                persisted = self._record_from_note(after)
            except KnowledgeError as error:
                raise MutationUncertain("Record readback is invalid; a write may have committed. Inspect current state before retrying.") from error
            if persisted != value:
                raise MutationUncertain("Record create readback did not match; a write may have committed. Inspect current state before retrying.")
            change = receipt.for_create(after)
            return self._record_result(result, after, persisted, change, replayed=False)

    async def record_transition(
        self, identifier: str, action: str, expected_revision: int, operation_id: str,
        timestamp: str, actor: str, reason: str, changes: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 1:
            raise ValueError("expected_revision must be a positive integer")
        if not isinstance(operation_id, str) or not operation_id:
            raise ValueError("operation_id must be non-empty text")
        if changes is not None and not isinstance(changes, Mapping):
            raise ValueError("changes must be an object")
        await self._authorize(identifier, None)
        fingerprint = self._fingerprint(action, expected_revision, timestamp, actor, reason, changes)
        async with self.backend.mutation():
            before = await self._read_full(identifier)
            record = self._record_from_note(before)
            if record is None:
                raise KnowledgeError("note is not a governed record")
            operations = self._operations(before)
            prior = operations.get(operation_id)
            if prior is not None:
                if prior.get("fingerprint") != fingerprint:
                    raise KnowledgeError("operation ID was already used with different inputs")
                return self._record_result(None, before, record, None, replayed=True) | {"operation_revision": prior.get("committed_revision")}
            if record["record_revision"] != expected_revision:
                raise KnowledgeError("record revision conflict; read the current record before retrying")
            if action == "evidence_health":
                health = self._evidence_health(record, timestamp, actor, reason, changes)
                if not health["mutated"]:
                    result = self._record_result(None, before, record, None, replayed=False)
                    result.update(outcome=health["outcome"], mutated=False, transient=health["transient"])
                    return result
            updated = self._transition(record, action, timestamp, actor, reason, operation_id, changes)
            if action in {"revise", "revalidate", "supersede"}:
                dependencies = await self._validate_dependencies(self._note_namespace(before), updated)
                if updated["status"] == "supported":
                    self._bind_dependencies(updated, dependencies)
            metadata = {self._record_key: updated,
                        self._operations_key: {**operations, operation_id: {"fingerprint": fingerprint, "committed_revision": updated["record_revision"]}}}
            body_changed = updated["claim"] != record["claim"]
            arguments: dict[str, Any] = {"identifier": self._identifier(before), "metadata": metadata}
            if body_changed:
                arguments.update(operation="find_replace", find_text=record["claim"],
                                 content=updated["claim"], expected_replacements=1)
            else:
                arguments.update(operation="append", content="")
            result = await self._call_mutation("edit_note", arguments)
            after = await self._read_after_mutation(self._identifier(before))
            try:
                persisted = self._record_from_note(after)
            except KnowledgeError as error:
                raise MutationUncertain("Record readback is invalid; a write may have committed. Inspect current state before retrying.") from error
            if persisted != updated or self._operations(after).get(operation_id, {}).get("fingerprint") != fingerprint:
                raise MutationUncertain("Record transition readback did not match; a write may have committed. Inspect current state before retrying.")
            change = receipt.for_edit(before, after,
                                      find_text=record["claim"] if body_changed else None,
                                      replacement=updated["claim"] if body_changed else None,
                                      metadata_keys={self._record_key, self._operations_key})
            return self._record_result(result, after, persisted, change, replayed=False)

    def _transition(self, record: Mapping[str, Any], action: str, timestamp: str, actor: str,
                    reason: str, operation_id: str, changes: Mapping[str, Any] | None) -> dict[str, Any]:
        changes = dict(changes or {})
        event = {"timestamp": timestamp, "actor": actor, "reason": reason, "event_id": operation_id}
        try:
            if action == "revise":
                return self.records.revise(record, **changes, **event)
            if action == "dispute":
                if changes:
                    raise KnowledgeError("dispute does not accept changes")
                return self.records.dispute(record, **event)
            if action == "revalidate":
                return self.records.revalidate(record, changes.pop("verification"), **event) if set(changes) == {"verification"} else self._invalid_transition()
            if action == "retract":
                if changes:
                    raise KnowledgeError("retract does not accept changes")
                return self.records.retract(record, **event)
            if action == "supersede":
                return self.records.supersede(record, changes.pop("successor"), **event) if set(changes) == {"successor"} else self._invalid_transition()
            if action == "dependency_health":
                if set(changes) != {"condition_id"}:
                    return self._invalid_transition()
                return self.records.mark_needs_revalidation(record, cause="dependency", condition_id=changes["condition_id"], timestamp=timestamp, actor=actor, reason=reason)
            if action == "evidence_health":
                return self._evidence_health(record, timestamp, actor, reason, changes)["record"]
        except (RecordError, KeyError, TypeError) as error:
            raise KnowledgeError("record transition is invalid") from error
        raise KnowledgeError("record transition action is invalid")

    def _evidence_health(self, record: Mapping[str, Any], timestamp: str, actor: str,
                         reason: str, changes: Mapping[str, Any] | None) -> dict[str, Any]:
        changes = dict(changes or {})
        if set(changes) != {"outcome", "condition_id"}:
            self._invalid_transition()
        try:
            return self.records.apply_evidence_health(record, changes["outcome"],
                                                      condition_id=changes["condition_id"],
                                                      timestamp=timestamp, actor=actor, reason=reason)
        except RecordError as error:
            raise KnowledgeError("record transition is invalid") from error

    @staticmethod
    def _invalid_transition() -> dict[str, Any]:
        raise KnowledgeError("record transition changes are invalid")

    @staticmethod
    def _fingerprint(action: str, revision: int, timestamp: str, actor: str, reason: str,
                     changes: Mapping[str, Any] | None) -> str:
        payload = {"action": action, "expected_revision": revision, "timestamp": timestamp,
                   "actor": actor, "reason": reason, "changes": changes or {}}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=False).encode("utf-8")).hexdigest()

    def _operations(self, note: Mapping[str, Any]) -> dict[str, Any]:
        value = self._metadata(dict(note)).get(self._operations_key, {})
        if not isinstance(value, dict):
            raise KnowledgeError("governed record operation metadata is invalid")
        return copy.deepcopy(value)

    @staticmethod
    def _note_namespace(note: Mapping[str, Any]) -> str:
        path = str(note.get("file_path", "")).strip("/")
        return "/" + path.rsplit("/", 1)[0] if "/" in path else "/"

    async def _validate_dependencies(self, namespace: str, candidate: Mapping[str, Any]) -> dict[str, int]:
        """Require local dependencies to resolve once and remain acyclic."""
        if not candidate["depends_on"] and not candidate.get("superseded_by"):
            return {}
        inventory: dict[str, dict[str, Any]] = {candidate["record_id"]: dict(candidate)}
        for record in await self._governed_inventory(namespace):
            record_id = record["record_id"]
            if record_id == candidate["record_id"]:
                continue
            if record_id in inventory:
                raise KnowledgeError("record dependency ID is ambiguous in this namespace")
            inventory[record_id] = record
        targets = [*candidate["depends_on"]]
        if candidate.get("superseded_by"):
            targets.append(candidate["superseded_by"])
        missing = [dependency for dependency in targets if dependency not in inventory]
        if missing:
            raise KnowledgeError("record dependency is missing in this namespace")
        successor = candidate.get("superseded_by")
        if successor and (inventory[successor]["status"] != "supported" or inventory[successor]["scope"] != candidate["scope"]):
            raise KnowledgeError("successor must be a current supported record in the same scope")
        visiting: set[str] = set()
        visited: set[str] = set()
        def visit(record_id: str) -> None:
            if record_id in visiting:
                raise KnowledgeError("record dependencies contain a cycle")
            if record_id in visited or record_id not in inventory:
                return
            visiting.add(record_id)
            targets = list(inventory[record_id]["depends_on"])
            if inventory[record_id].get("superseded_by"):
                targets.append(inventory[record_id]["superseded_by"])
            for dependency in targets:
                if dependency not in inventory:
                    raise KnowledgeError("record dependency is missing in this namespace")
                visit(dependency)
            visiting.remove(record_id)
            visited.add(record_id)
        visit(candidate["record_id"])
        return {key: inventory[key]["record_revision"] for key in candidate["depends_on"]}

    @staticmethod
    def _bind_dependencies(record: dict[str, Any], revisions: dict[str, int]) -> None:
        if revisions:
            record["verification"]["dependency_revisions"] = revisions
            record["events"][-1]["snapshot"]["verification"] = copy.deepcopy(record["verification"])

    def _record_result(self, mutation: Any, note: Mapping[str, Any], record: Mapping[str, Any],
                       change: dict[str, Any] | None, *, replayed: bool) -> dict[str, Any]:
        result: dict[str, Any] = {"mutation": mutation, "record": copy.deepcopy(record),
                                  "identifier": self._identifier(dict(note)),
                                  "committed_revision": record["record_revision"], "replayed": replayed}
        if change is not None:
            change["record_revision"] = record["record_revision"]
            result.update(knowledge_change=change, knowledge_change_text=receipt.render(change) + "\nCommitted record revision: " + str(record["record_revision"]))
        return result

    async def read(self, identifier: str, offset: int = 0, limit: int = 12_000, *,
                   mode: str = "reuse", request_scope: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if mode not in {"reuse", "inspect"}:
            raise ValueError("mode must be reuse or inspect")
        if offset < 0 or limit < 1:
            raise ValueError("offset must be >= 0 and limit must be >= 1")
        await self._authorize(identifier, request_scope)
        note = await self._read_full(identifier)
        record = self._record_from_note(note)
        if record is None:
            value = self._public_note(note, offset, min(limit, 12_000))
            value["review_status"] = "unreviewed"
            return value
        if mode == "inspect":
            return {"identifier": self._identifier(note), "record": record, "mode": "inspect"}
        allowed, reason = await self._reuse_allowed(record, request_scope, self._note_namespace(note))
        if not allowed:
            return {"identifier": self._identifier(note), "withheld": True, "reason": reason,
                    "content_is_data": True}
        return self._governed_public(note, record, offset, min(limit, 12_000))

    def _governed_public(self, note: Mapping[str, Any], record: Mapping[str, Any],
                         offset: int, limit: int) -> dict[str, Any]:
        content = record["claim"]
        end = min(len(content), offset + limit)
        return {"identifier": self._identifier(dict(note)), "title": note.get("title", ""),
                "permalink": note.get("permalink"), "file_path": note.get("file_path"),
                "content": content[offset:end], "metadata": self._metadata_without_engine(note),
                "offset": offset, "next_offset": end if end < len(content) else None,
                "truncated": end < len(content), "content_is_data": True,
                "record_status": record["status"], "record_revision": record["record_revision"],
                "scope": copy.deepcopy(record["scope"]), "verification": copy.deepcopy(record["verification"]),
                "evidence": copy.deepcopy(record["evidence"])}

    async def search(self, namespaces: list[str], query: str | None = None,
                     recursive: bool = False, kind: str | None = None,
                     metadata: dict[str, Any] | None = None, cursor: str | None = None,
                     page_size: int = 10, retrieval_mode: str = "text",
                     item_types: list[str] | None = None, categories: list[str] | None = None,
                     *, mode: str = "reuse",
                     request_scope: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if mode not in {"reuse", "inspect"}:
            raise ValueError("mode must be reuse or inspect")
        result = await super().search(namespaces, query, recursive, kind, metadata, cursor,
                                      page_size, retrieval_mode, item_types, categories)
        kept, excluded = [], []
        for row in result["results"]:
            identifier = row["identifier"]
            try:
                await self._authorize(identifier, request_scope)
                note = await self._read_full(identifier)
                record = self._record_from_note(note)
                if record is None:
                    kept.append({**row, "snippet": row["snippet"] if row["snippet"] and row["snippet"] in note["content"] else note["content"][:1000],
                                 "metadata": self._metadata_without_engine(note), "review_status": "unreviewed"})
                    continue
                allowed, reason = await self._reuse_allowed(record, request_scope, self._note_namespace(note))
                if mode == "inspect" or allowed:
                    kept.append({"identifier": identifier, "file_path": row["file_path"],
                                 "title": row.get("title", ""), "governed": True,
                                 "record_status": record["status"], "record_revision": record["record_revision"],
                                 "snippet": record["claim"][:1000] if allowed and mode == "reuse" else ""})
                else:
                    excluded.append({"identifier": identifier, "reason": reason})
            except AccessDenied:
                excluded.append({"reason": "access_denied"})
            except (BackendError, KnowledgeError) as error:
                excluded.append({"identifier": identifier, "reason": str(error)})
        result["results"] = kept
        result["excluded"] = excluded
        result["partial"] = bool(excluded or result["has_more"])
        return result

    async def list(self, namespace: str = "/", depth: int = 1, page: int = 1,
                   page_size: int = 20, glob: str | None = None, sort: str | None = None,
                   *, mode: str = "reuse",
                   request_scope: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if mode not in {"reuse", "inspect"}:
            raise ValueError("mode must be reuse or inspect")
        result = await super().list(namespace, depth, page, page_size, glob, sort)
        nodes, excluded = [], []
        async def filter_node(node: dict[str, Any]) -> dict[str, Any] | None:
            node = copy.deepcopy(node)
            if node.get("type") == "directory":
                try:
                    await self._authorize(node.get("directory_path", ""), request_scope)
                except AccessDenied:
                    excluded.append({"reason": "access_denied"})
                    return None
                children = []
                for child in node.get("children", []):
                    filtered = await filter_node(child)
                    if filtered is not None:
                        children.append(filtered)
                node["children"] = children
                return node
            identifier = node.get("file_path")
            if node.get("type") != "file" or not isinstance(identifier, str):
                return node
            try:
                await self._authorize(identifier, request_scope)
                note = await self._read_full(identifier)
                record = self._record_from_note(note)
                if record is None:
                    return node
                allowed, reason = await self._reuse_allowed(record, request_scope, self._note_namespace(note))
                if mode == "inspect" or allowed:
                    return node
                else:
                    excluded.append({"identifier": identifier, "reason": reason})
            except AccessDenied:
                excluded.append({"reason": "access_denied"})
            except (BackendError, KnowledgeError) as error:
                excluded.append({"identifier": identifier, "reason": str(error)})
            return None
        for node in result["nodes"]:
            filtered = await filter_node(node)
            if filtered is not None:
                nodes.append(filtered)
        result["nodes"] = nodes
        result["excluded"] = excluded
        result["partial"] = bool(excluded or result["has_more"])
        return result

    async def context(self, namespace: str | None = None, identifiers: list[str] | None = None,
                      page: int = 1, page_size: int = 5, max_chars: int = 12_000, *,
                      mode: str = "reuse",
                      request_scope: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if (namespace is None) == (identifiers is None):
            raise ValueError("provide exactly one of namespace or identifiers")
        if mode not in {"reuse", "inspect"}:
            raise ValueError("mode must be reuse or inspect")
        if page < 1 or page_size < 1 or page_size > 20 or max_chars < 1 or max_chars > 50_000:
            raise ValueError("invalid context page, page_size, or max_chars")
        listing = None
        if namespace is not None:
            listing = await self.list(namespace, depth=1, page=page, page_size=page_size,
                                      mode=mode, request_scope=request_scope)
            omitted = list(listing["excluded"])
            selected = []
            for node in listing["nodes"]:
                identifier = node.get("file_path")
                if node.get("type") == "file" and isinstance(identifier, str):
                    if identifier.lower().endswith(".md"):
                        selected.append(identifier)
                    else:
                        omitted.append({"identifier": identifier, "reason": "not_markdown"})
        else:
            if not isinstance(identifiers, list) or not identifiers or len(identifiers) > 20:
                raise ValueError("identifiers must contain between 1 and 20 entries")
            selected, omitted = list(dict.fromkeys(identifiers)), []
        notes: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        used = 0
        for index, identifier in enumerate(selected):
            if used >= max_chars:
                omitted.extend({"identifier": item, "reason": "character_budget"}
                               for item in selected[index:])
                break
            try:
                public = await self.read(identifier, 0, max_chars - used,
                                         mode=mode, request_scope=request_scope)
            except (BackendError, KnowledgeError) as error:
                errors.append({"identifier": identifier, "error": str(error)})
                continue
            if public.get("withheld"):
                omitted.append({"identifier": identifier, "reason": public["reason"]})
                continue
            if mode == "inspect":
                encoded = json.dumps(public["record"], ensure_ascii=False, sort_keys=True)
                available = max_chars - used
                end = min(len(encoded), available)
                notes.append({"identifier": identifier, "content": encoded[:end], "offset": 0,
                              "next_offset": end if end < len(encoded) else None,
                              "truncated": end < len(encoded), "mode": "inspect",
                              "content_is_data": True})
                used += end
                continue
            used += len(public["content"])
            notes.append(public)
        return {"listing": listing, "notes": notes, "omitted": omitted, "errors": errors,
                "used_chars": used, "max_chars": max_chars,
                "partial": bool(omitted or errors or any(note["truncated"] for note in notes)
                                or (listing and listing["has_more"])),
                "content_is_data": True}

    async def related(self, identifier: str, namespaces: list[str], depth: int = 1,
                      max_notes: int = 10, max_chars: int = 12_000, *, mode: str = "reuse",
                      request_scope: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Discover relationships natively while applying engine policy to every read."""
        if not namespaces or not isinstance(namespaces, list):
            raise ValueError("namespaces must be a nonempty list")
        if not 1 <= depth <= 3 or not 1 <= max_notes <= 20 or not 1 <= max_chars <= 50_000:
            raise ValueError("depth must be 1..3, max_notes 1..20, and max_chars 1..50000")
        await self._authorize(identifier, request_scope)
        seed = await self._read_full(identifier)
        scopes = [self._namespace(value) for value in namespaces]
        if not self._in_scopes(self._identifier(seed), scopes, True):
            raise ValueError("the starting note is outside the requested namespaces")
        native = await self.backend.call("build_context", {
            "url": seed.get("permalink") or identifier, "depth": depth, "timeframe": None,
            "page": 1, "page_size": 1, "max_related": 100,
        })
        selected, excluded = [self._identifier(seed)], 0
        for result in native.get("results", []):
            for item in [result.get("primary_result", {}), *result.get("related_results", [])]:
                path = item.get("file_path")
                if not isinstance(path, str) or item.get("type") != "entity":
                    continue
                if not self._in_scopes(path, scopes, True):
                    excluded += 1
                elif path not in selected:
                    selected.append(path)
        limited = (len(selected) > max_notes or bool(native.get("has_more"))
                   or native.get("metadata", {}).get("related_count", 0) >= 100)
        bundle = await self.context(identifiers=selected[:max_notes], max_chars=max_chars,
                                    mode=mode, request_scope=request_scope)
        return bundle | {"graph": {"depth": depth, "selected_notes": len(selected[:max_notes]),
                                    "excluded_outside_scope": excluded, "limited": limited,
                                    "source": "basic_memory_relations"},
                         "partial": bool(bundle["partial"] or limited or excluded)}


__all__ = ["KnowledgeEngine"]
