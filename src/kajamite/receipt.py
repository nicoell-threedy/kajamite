"""Deterministic, operation-scoped evidence for successful knowledge writes."""

from __future__ import annotations

import hashlib
import json
from typing import Any


SCHEMA_VERSION = 1
VALUE_PREVIEW_CHARS = 2_000
COVERAGE = "kajamite_operation"
COVERAGE_NOTICE = (
    "This receipt covers this Kajamite operation only; it does not exclude "
    "changes made by other tools, processes, or people."
)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _value(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "preview": value[:VALUE_PREVIEW_CHARS],
        "characters": len(value),
        "sha256": _sha256(value),
        "truncated": len(value) > VALUE_PREVIEW_CHARS,
    }


def _identifier(note: dict[str, Any]) -> str:
    value = note.get("file_path") or note.get("identifier") or note.get("permalink")
    if not isinstance(value, str) or not value:
        raise ValueError("receipt subject has no identifier")
    return value


def _identity(note: dict[str, Any]) -> dict[str, Any]:
    content = note.get("content")
    if not isinstance(content, str):
        raise ValueError("receipt note has no complete content")
    return {"identifier": _identifier(note), "content_sha256": _sha256(content)}


def _metadata(note: dict[str, Any]) -> dict[str, Any]:
    value = note.get("frontmatter", note.get("metadata", {}))
    return value if isinstance(value, dict) else {}


def _metadata_changes(
    before: dict[str, Any], after: dict[str, Any], keys: set[str] | None = None
) -> list[dict[str, Any]]:
    old, new = _metadata(before), _metadata(after)
    candidates = old.keys() | new.keys() if keys is None else keys
    return [
        {
            "key": key,
            "before": old.get(key),
            "after": new.get(key),
            "before_present": key in old,
            "after_present": key in new,
        }
        for key in sorted(candidates)
        if old.get(key) != new.get(key) or (key in old) != (key in new)
    ]


def _base(
    operation: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    *,
    body_change: dict[str, Any] | None,
    metadata_changes: list[dict[str, Any]],
    affected_notes: int | None,
    affected_notes_exact: bool,
    verification: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "operation": operation,
        "coverage": COVERAGE,
        "coverage_notice": COVERAGE_NOTICE,
        "before": None if before is None else _identity(before),
        "after": None if after is None else _identity(after),
        "body_change": body_change,
        "metadata_changes": metadata_changes,
        "affected_notes": affected_notes,
        "affected_notes_exact": affected_notes_exact,
        "verification": verification,
        "readback_verified": verification == "readback_verified",
    }


def for_create(after: dict[str, Any]) -> dict[str, Any]:
    return _base(
        "create", None, after,
        body_change={"kind": "created", "before": None, "after": _value(after["content"])},
        metadata_changes=_metadata_changes({}, after),
        affected_notes=1,
        affected_notes_exact=True,
        verification="readback_verified",
    )


def for_edit(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    find_text: str | None,
    replacement: str | None,
    metadata_keys: set[str],
) -> dict[str, Any]:
    body_change = None
    if find_text is not None:
        body_change = {
            "kind": "exact_replacement",
            "before": _value(find_text),
            "after": _value(replacement),
        }
    return _base(
        "edit", before, after,
        body_change=body_change,
        metadata_changes=_metadata_changes(before, after, metadata_keys),
        affected_notes=1,
        affected_notes_exact=True,
        verification="readback_verified",
    )


def for_note_move(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return _base(
        "move_note", before, after,
        body_change=None,
        metadata_changes=[],
        affected_notes=1,
        affected_notes_exact=True,
        verification="readback_verified",
    )


def for_namespace_move(source: str, destination: str, result: dict[str, Any]) -> dict[str, Any]:
    count = result.get("total_files")
    exact = isinstance(count, int) and not isinstance(count, bool) and count >= 0
    return {
        "schema_version": SCHEMA_VERSION,
        "operation": "move_namespace",
        "coverage": COVERAGE,
        "coverage_notice": COVERAGE_NOTICE,
        "before": {"identifier": source},
        "after": {"identifier": destination},
        "body_change": None,
        "metadata_changes": [],
        "affected_notes": count if exact else None,
        "affected_notes_exact": exact,
        "verification": "backend_confirmed",
        "readback_verified": False,
    }


def render(receipt: dict[str, Any]) -> str:
    before = receipt.get("before") or {}
    after = receipt.get("after") or {}
    lines = [
        f"Knowledge change: {receipt['operation']}",
        f"Before: {before.get('identifier', 'none')}",
        f"Current: {after.get('identifier', 'none')}",
        f"Verification: {receipt['verification']}",
        f"Coverage: {receipt['coverage']}",
    ]
    count = receipt.get("affected_notes")
    lines.append(f"Affected notes: {count if count is not None else 'not reported'}")
    body = receipt.get("body_change")
    if body:
        for label, key in (("Previous value", "before"), ("Current value", "after")):
            evidence = body.get(key)
            if evidence is None:
                lines.append(f"{label}: none")
            else:
                suffix = " (preview; truncated)" if evidence["truncated"] else ""
                lines.append(f"{label}{suffix}: {evidence['preview']!r}")
                lines.append(f"{label} SHA-256: {evidence['sha256']}")
    for change in receipt.get("metadata_changes", []):
        before_value = (
            json.dumps(change["before"], ensure_ascii=False, sort_keys=True)
            if change.get("before_present", True) else "<absent>"
        )
        after_value = (
            json.dumps(change["after"], ensure_ascii=False, sort_keys=True)
            if change.get("after_present", True) else "<absent>"
        )
        lines.append(
            f"Metadata {change['key']}: {before_value} -> {after_value}"
        )
    lines.append(receipt["coverage_notice"])
    return "\n".join(lines)
