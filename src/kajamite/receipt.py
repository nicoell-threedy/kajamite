"""Deterministic, operation-scoped evidence for successful knowledge writes."""

from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
from typing import Any


SCHEMA_VERSION = 1
VALUE_PREVIEW_CHARS = 2_000
CLAIM_DIFF_MAX_LINES = 500
CLAIM_CONTEXT_CHARS = 80
INLINE_DIFF_MAX_TOKENS = 1_000
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
    result = {"identifier": _identifier(note), "content_sha256": _sha256(content)}
    title = display_title(note)
    if title:
        result["title"] = title
    return result


def display_title(note: dict[str, Any]) -> str:
    """Use a governed topic's leading H1 without changing its stored address."""
    if "kajamite_record" in _metadata(note):
        heading = re.match(r"# ([^\r\n]+)", str(note.get("content", "")).lstrip("\r\n"))
        if heading and heading[1].strip():
            return heading[1].strip()
    title = note.get("title")
    return title if isinstance(title, str) else ""


def _comparison(before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:
    """Annotate preview changes with Unicode code-point ranges, without copying text."""
    pair = {"before": before, "after": after}
    if before is None or after is None:
        return pair
    if before["preview"] == after["preview"]:
        before["changed_ranges"], after["changed_ranges"] = [], []
        return pair
    tokens = [list(re.finditer(r"\w+|\s+|[^\w\s]", item["preview"])) for item in (before, after)]
    if max(map(len, tokens)) > INLINE_DIFF_MAX_TOKENS:
        # ponytail: bounded quadratic matching; the renderer retains its broad-span fallback.
        return pair
    before["changed_ranges"], after["changed_ranges"] = [], []
    for tag, a, b, c, d in SequenceMatcher(None, [m.group() for m in tokens[0]],
                                         [m.group() for m in tokens[1]], autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        for item, matches, start, end in ((before, tokens[0], a, b), (after, tokens[1], c, d)):
            if start != end:
                item["changed_ranges"].append([matches[start].start(), matches[end - 1].end()])
    return pair


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


def record_changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """Project validated records for review; complete metadata stays in the receipt."""
    result = []
    changes = _metadata_changes({"metadata": before}, {"metadata": after})
    for change in sorted(changes, key=lambda item: ({"status": 0, "scope": 1}.get(item["key"], 2), item["key"])):
        key = change["key"]
        if key in {"type", "schema_version", "record_id", "record_revision", "claim", "events"}:
            continue
        if key in {"scope", "verification"}:
            for field in _metadata_changes({"metadata": before.get(key, {})}, {"metadata": after.get(key, {})}):
                if key == "verification" and field["key"] == "record_revision":
                    continue
                if key == "verification" and field["key"] == "outcome" and field["after"] == after.get("status"):
                    continue
                result.append(field | {"key": key + "." + field["key"]})
        elif key == "evidence":
            old, new = before.get(key, {}), after.get(key, {})
            added, removed = len(new.keys() - old.keys()), len(old.keys() - new.keys())
            updated = sum(old[source] != new[source] for source in old.keys() & new.keys())
            result.append({"key": key, "message": f"Sources: {added} added, {removed} removed, {updated} changed. Exact values are in the raw receipt."})
        elif key == "observations":
            result.append({"key": key, "message": f"Observation support changed ({len(after.get(key, []))} current observations). Exact values are in the raw receipt."})
        else:
            result.append(change)
    return result


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
            **_comparison(_value(find_text), _value(replacement)),
        }
    return _base(
        "edit", before, after,
        body_change=body_change,
        metadata_changes=_metadata_changes(before, after, metadata_keys),
        affected_notes=1,
        affected_notes_exact=True,
        verification="readback_verified",
    )


def for_revise(
    before: dict[str, Any], after: dict[str, Any], replacements: list[dict[str, str]],
) -> dict[str, Any]:
    return _base(
        "revise", before, after,
        body_change={
            "kind": "grouped_exact_replacement",
            "replacements": [
                _comparison(_value(item["find_text"]), _value(item["replacement"]))
                for item in replacements
            ],
        },
        metadata_changes=[],
        affected_notes=1,
        affected_notes_exact=True,
        verification="readback_verified",
    )


def changed_claim_passages(before: str, after: str) -> dict[str, Any]:
    """Show changed line blocks from a complete claim within a bounded line diff."""
    old_lines, new_lines = before.splitlines(keepends=True), after.splitlines(keepends=True)
    if max(len(old_lines), len(new_lines)) > CLAIM_DIFF_MAX_LINES:
        # ponytail: bounded quadratic line matching; use a larger-document diff only if passage previews need it.
        return {"kind": "exact_replacement", **_comparison(_value(before), _value(after))}

    passages = []
    for tag, old_start, old_end, new_start, new_end in SequenceMatcher(
        None, old_lines, new_lines, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            continue
        context = 1 if old_start and new_start else 0
        old = "".join(old_lines[old_start - context:old_end])
        new = "".join(new_lines[new_start - context:new_end])
        prefix = 0
        while prefix < min(len(old), len(new)) and old[prefix] == new[prefix]:
            prefix += 1
        suffix = 0
        while suffix < min(len(old), len(new)) - prefix and old[-suffix - 1] == new[-suffix - 1]:
            suffix += 1
        left = max(0, prefix - CLAIM_CONTEXT_CHARS)

        def evidence(value: str) -> dict[str, Any]:
            result = _value(value)
            right = min(len(value), len(value) - suffix + CLAIM_CONTEXT_CHARS)
            preview = ("…" if left else "") + value[left:right] + ("…" if right < len(value) else "")
            if len(preview) > VALUE_PREVIEW_CHARS:
                preview = preview[:VALUE_PREVIEW_CHARS - 1] + "…"
            result["preview"] = preview
            result["truncated"] = left > 0 or right < len(value) or len(preview) < len(value)
            return result

        passages.append(_comparison(evidence(old), evidence(new)))
    return {"kind": "grouped_exact_replacement", "replacements": passages}


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
        values = [("Previous value", "before", body.get("before")), ("Current value", "after", body.get("after"))]
        if body.get("kind") == "grouped_exact_replacement":
            values = [
                value
                for index, item in enumerate(body["replacements"])
                for value in (
                    (f"Replacement {index + 1} previous value", "before", item["before"]),
                    (f"Replacement {index + 1} current value", "after", item["after"]),
                )
            ]
        for label, _, evidence in values:
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
