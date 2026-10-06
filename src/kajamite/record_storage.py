"""Lossless journal metadata for governed records stored beside Markdown bodies."""

from __future__ import annotations

import copy
import hashlib
from typing import Any, Mapping

from .governance import RecordEngine, RecordError


_SNAPSHOT_KEYS = frozenset({
    "record_id", "record_revision", "status", "claim", "scope", "observations",
    "evidence", "verification", "depends_on", "superseded_by",
})
_EVENT_KEYS = ("event_id", "action", "timestamp", "actor", "reason",
               "prior_status", "resulting_status")
_FROM_BODY = {"from_body": True}
_FROM_CLAIM = {"from_claim": True}


def _marker(value: Any, name: str) -> bool:
    return isinstance(value, dict) and set(value) == {name} and value[name] is True


def _canonical(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _body_claim(body: str, digest: str) -> str:
    if not isinstance(body, str) or not isinstance(digest, str) or len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise RecordError("journal body hash is invalid")
    body = _canonical(body)
    candidates = (body, body[1:] if body.startswith("\n") else body,
                  body[:-1] if body.endswith("\n") else body,
                  body[1:-1] if body.startswith("\n") and body.endswith("\n") else body)
    for candidate in candidates:
        if hashlib.sha256(candidate.encode("utf-8")).hexdigest() == digest:
            return candidate
    raise RecordError("journal body hash does not match")


def _transform(snapshot: Mapping[str, Any], body_claim: str) -> dict[str, Any]:
    result = copy.deepcopy(dict(snapshot))
    if result["claim"] == body_claim:
        result["claim"] = _FROM_BODY.copy()
    for observation in result["observations"]:
        if observation["statement"] == snapshot["claim"]:
            observation["statement"] = _FROM_CLAIM.copy()
    return result


def encode_record(record: Mapping[str, Any], body: str, engine: RecordEngine) -> dict[str, Any]:
    """Validate and encode a complete record without changing its public shape."""
    value = engine.validate_record(record)
    claim = _canonical(body)
    if claim != value["claim"]:
        raise RecordError("journal body does not match the current claim")
    events = []
    prior: dict[str, Any] = {}
    for event in value["events"]:
        snapshot = _transform(event["snapshot"], claim)
        changes = {key: item for key, item in snapshot.items() if key not in prior or item != prior[key]}
        events.append({key: copy.deepcopy(event[key]) for key in _EVENT_KEYS} | {"changes": changes})
        prior = snapshot
    return {"format": "journal-v1", "type": value["type"],
            "schema_version": value["schema_version"],
            "body_sha256": hashlib.sha256(claim.encode("utf-8")).hexdigest(),
            "events": events}


def decode_record(raw: Mapping[str, Any], body: str, engine: RecordEngine) -> dict[str, Any]:
    """Expand journal metadata or validate a legacy complete record."""
    if not isinstance(raw, dict):
        raise RecordError("governed record metadata is invalid")
    if "format" not in raw:
        return engine.validate_record(raw)
    if set(raw) != {"format", "type", "schema_version", "body_sha256", "events"} or raw["format"] != "journal-v1":
        raise RecordError("journal header is invalid")
    claim = _body_claim(body, raw["body_sha256"])
    encoded_events = raw["events"]
    if not isinstance(encoded_events, list) or not encoded_events:
        raise RecordError("journal history is missing")
    events = []
    prior: dict[str, Any] = {}
    for index, event in enumerate(encoded_events):
        if not isinstance(event, dict) or set(event) != set(_EVENT_KEYS) | {"changes"}:
            raise RecordError("journal event is invalid")
        changes = event["changes"]
        if not isinstance(changes, dict) or not changes or not set(changes) <= _SNAPSHOT_KEYS:
            raise RecordError("journal changes are invalid")
        if index == 0 and set(changes) != _SNAPSHOT_KEYS:
            raise RecordError("first journal event needs a full snapshot")
        if index and any(prior[key] == item for key, item in changes.items()):
            raise RecordError("journal changes contain an unchanged value")
        snapshot = copy.deepcopy(prior)
        snapshot.update(copy.deepcopy(changes))
        if set(snapshot) != _SNAPSHOT_KEYS:
            raise RecordError("journal snapshot is incomplete")
        prior = snapshot
        expanded = copy.deepcopy(snapshot)
        if isinstance(expanded["claim"], dict):
            if not _marker(expanded["claim"], "from_body"):
                raise RecordError("journal claim marker is invalid")
            expanded["claim"] = claim
        if not isinstance(expanded["observations"], list):
            raise RecordError("journal observations are invalid")
        for observation in expanded["observations"]:
            if not isinstance(observation, dict):
                raise RecordError("journal observation is invalid")
            if isinstance(observation.get("statement"), dict):
                if not _marker(observation["statement"], "from_claim"):
                    raise RecordError("journal observation marker is invalid")
                observation["statement"] = expanded["claim"]
        events.append({key: copy.deepcopy(event[key]) for key in _EVENT_KEYS} | {"snapshot": expanded})
    record = {"type": raw["type"], "schema_version": raw["schema_version"],
              **copy.deepcopy(events[-1]["snapshot"]), "events": events}
    result = engine.validate_record(record)
    if result["claim"] != claim:
        raise RecordError("journal current claim does not match the body")
    return result
