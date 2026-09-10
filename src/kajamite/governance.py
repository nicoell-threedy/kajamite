"""Pure, embeddable lifecycle and Markdown codec for evidence-backed records."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

SCHEMA_VERSION = 1
STATUSES = frozenset(
    {
        "supported",
        "disputed",
        "needs_revalidation",
        "unverifiable",
        "superseded",
        "retracted",
    }
)
_CREATION_STATUSES = frozenset({"supported", "disputed", "unverifiable"})
_TERMINAL_STATUSES = frozenset({"superseded", "retracted"})
_ACTIONS = frozenset({"create", "revise", "dispute", "revalidate", "supersede", "retract", "source_change", "dependency_change"})
_EVIDENCE_OUTCOMES = frozenset({"unchanged", "changed", "missing", "inaccessible", "removed"})
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


class RecordError(ValueError):
    """A record or transition violates the governed contract."""


class RecordEngine:
    """Validate and transform records; callers own persistence and source access."""

    def __init__(self, *, record_type: str = "governed-record",
                 permalink_prefix: str = "records",
                 evidence_validator: Callable[[dict[str, Any]], None] | None = None,
                 decode_frontmatter: Callable[[str], Any] = json.loads):
        self._require_id(record_type, "record type")
        if not isinstance(permalink_prefix, str) or not permalink_prefix or any(
            not _ID.fullmatch(part) for part in permalink_prefix.split("/")
        ):
            raise RecordError("permalink prefix must contain safe relative path segments")
        self.record_type = record_type
        self.permalink_prefix = permalink_prefix
        self.evidence_validator = evidence_validator
        self.decode_frontmatter = decode_frontmatter

    def change_summary(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """Return content-free lifecycle facts, not persistence confirmation."""
        value = self.validate_record(record)
        event = value["events"][-1]
        return {"action": event["action"], "prior_status": event["prior_status"],
                "status": value["status"], "record_revision": value["record_revision"],
                "evidence_count": len(value["evidence"]),
                "dependency_count": len(value["depends_on"])}

    def _error(self, message: str) -> None:
        raise RecordError(message)

    def _clone(self, value: Any) -> Any:
        return copy.deepcopy(value)

    def _require_id(self, value: Any, label: str) -> str:
        if not isinstance(value, str) or not _ID.fullmatch(value):
            self._error(f'{label} must be a safe identifier')
        return value

    def _require_text(self, value: Any, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            self._error(f'{label} must be non-empty text')
        return value

    def _canonical_claim(self, value: Any) -> str:
        """Normalize Markdown line endings without changing its body boundaries."""
        return self._require_text(value, 'claim').replace('\r\n', '\n').replace('\r', '\n')

    def _require_utc(self, value: Any, label: str) -> str:
        value = self._require_text(value, label)
        if not _UTC_TIMESTAMP.fullmatch(value):
            self._error(f'{label} must use canonical UTC microseconds')
        try:
            datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%fZ')
        except ValueError as exc:
            raise RecordError(f'{label} must use canonical UTC microseconds') from exc
        return value

    def _utc_datetime(self, value: Any, label: str) -> datetime:
        return datetime.fromisoformat(self._require_utc(value, label).replace('Z', '+00:00'))

    def _format_utc(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')

    def next_event_timestamp(self, record: Mapping[str, Any] | None, timestamp: str, verification: Mapping[str, Any] | None=None) -> str:
        """Return an automatic event time after history and at its verification time or later."""
        candidates = [self._utc_datetime(timestamp, 'event timestamp')]
        if record is not None:
            candidates.append(self._utc_datetime(record['events'][-1]['timestamp'], 'prior event timestamp') + timedelta(microseconds=1))
            verification = verification or record['verification']
        if verification is not None:
            candidates.append(self._utc_datetime(verification.get('verified_at'), 'verification.verified_at'))
        return self._format_utc(max(candidates))

    def _nonempty(self, value: Any) -> bool:
        if value is None or value == '':
            return False
        if isinstance(value, (list, tuple, dict)):
            return bool(value) and all((self._nonempty(item) for item in value)) if isinstance(value, (list, tuple)) else bool(value) and all((self._nonempty(key) and self._nonempty(item) for key, item in value.items()))
        return True

    def _validate_scope(self, scope: Any) -> None:
        if not isinstance(scope, dict) or not self._nonempty(scope):
            self._error('scope must be a non-empty structured object')
        if any((not isinstance(key, str) or not key.strip() for key in scope)):
            self._error('scope keys must be non-empty text')

    def _validate_evidence(self, evidence):
        if not isinstance(evidence, dict) or not evidence:
            self._error('evidence must be a non-empty object')
        for evidence_id, anchor in evidence.items():
            self._require_id(evidence_id, 'evidence ID')
            if not isinstance(anchor, dict):
                self._error('each evidence anchor must be an object')
            self._require_text(anchor.get('kind'), 'evidence kind')
            if 'observed_at' in anchor:
                self._require_utc(anchor['observed_at'], 'evidence observed_at')
        if self.evidence_validator is not None:
            self.evidence_validator(self._clone(evidence))

    def _validate_observations(self, observations: Any, evidence: Mapping[str, Any]) -> None:
        if not isinstance(observations, list) or not observations:
            self._error('observations must be a non-empty list')
        observation_ids: set[str] = set()
        for observation in observations:
            if not isinstance(observation, dict):
                self._error('each observation must be an object')
            observation_id = self._require_id(observation.get('observation_id'), 'observation ID')
            if observation_id in observation_ids:
                self._error(f'duplicate observation ID: {observation_id}')
            observation_ids.add(observation_id)
            self._require_text(observation.get('statement'), f'observation {observation_id}.statement')
            references = observation.get('evidence_ids')
            if not isinstance(references, list) or not references:
                self._error(f'observation {observation_id} needs evidence IDs')
            for evidence_id in references:
                self._require_id(evidence_id, 'observation evidence ID')
                if evidence_id not in evidence:
                    self._error(f'observation {observation_id} references unknown evidence: {evidence_id}')

    def _validate_verification(self, verification: Any, evidence: Mapping[str, Any], observations: list[Mapping[str, Any]], revision: int) -> None:
        if not isinstance(verification, dict):
            self._error('verification must be an object')
        verified_at = self._utc_datetime(verification.get('verified_at'), 'verification.verified_at')
        self._require_text(verification.get('verifier'), 'verification.verifier')
        outcome = self._require_text(verification.get('outcome'), 'verification.outcome')
        if outcome not in {'supported', 'disputed', 'needs_revalidation', 'unverifiable'}:
            self._error('verification.outcome is invalid')
        bound_revision = verification.get('record_revision')
        if not isinstance(bound_revision, int) or isinstance(bound_revision, bool) or (not 1 <= bound_revision <= revision):
            self._error('verification.record_revision must bind an existing record revision')
        references = verification.get('evidence_ids')
        if not isinstance(references, list) or not references:
            self._error('verification needs evidence IDs')
        for evidence_id in references:
            self._require_id(evidence_id, 'verification evidence ID')
            if evidence_id not in evidence:
                self._error(f'verification references unknown evidence: {evidence_id}')
        observed = {evidence_id for observation in observations for evidence_id in observation['evidence_ids']}
        if not observed <= set(references):
            self._error('verification.evidence_ids must cover every observed evidence ID')
        for evidence_id in observed:
            anchor = evidence[evidence_id]
            if 'observed_at' in anchor and self._utc_datetime(anchor['observed_at'], f'evidence {evidence_id}.observed_at') > verified_at:
                self._error(f'evidence {evidence_id}.observed_at cannot be later than verification.verified_at')

    def _validate_action_delta(self, action: str, prior: Mapping[str, Any], current: Mapping[str, Any]) -> None:
        semantic = ('claim', 'scope', 'observations', 'evidence')
        if action in {'source_change', 'dependency_change'}:
            preserved = (*semantic, 'depends_on', 'superseded_by')
            if any((current[key] != prior[key] for key in preserved)):
                self._error(f'{action} changed fields it does not own')
            if {key: value for key, value in current['verification'].items() if key != 'outcome'} != {key: value for key, value in prior['verification'].items() if key != 'outcome'}:
                self._error('deterministic revalidation must preserve semantic verification')
        elif action in {'dispute', 'revalidate'}:
            if any((current[key] != prior[key] for key in (*semantic, 'depends_on', 'superseded_by'))):
                self._error(f'{action} changed fields it does not own')
        elif action == 'supersede':
            if any((current[key] != prior[key] for key in (*semantic, 'verification', 'depends_on'))):
                self._error('supersede changed fields it does not own')
        elif action == 'retract':
            if any((current[key] != prior[key] for key in (*semantic, 'verification', 'depends_on', 'superseded_by'))):
                self._error('retract changed fields it does not own')
        elif action == 'revise' and current['superseded_by'] != prior['superseded_by']:
            self._error('revise cannot set a successor')

    def _snapshot(self, record: Mapping[str, Any]) -> dict[str, Any]:
        return {'record_id': record['record_id'], 'record_revision': record['record_revision'], 'status': record['status'], 'claim': record['claim'], 'scope': self._clone(record['scope']), 'observations': self._clone(record['observations']), 'evidence': self._clone(record['evidence']), 'verification': self._clone(record['verification']), 'depends_on': self._clone(record['depends_on']), 'superseded_by': record['superseded_by']}

    def _validate_snapshot(self, snapshot: Any, record_id: str, revision: int) -> None:
        if not isinstance(snapshot, dict):
            self._error('event snapshot must be an object')
        expected = {'record_id', 'record_revision', 'status', 'claim', 'scope', 'observations', 'evidence', 'verification', 'depends_on', 'superseded_by'}
        if set(snapshot) != expected:
            self._error('event snapshot is incomplete')
        if snapshot['record_id'] != record_id or snapshot['record_revision'] != revision:
            self._error('event snapshot identity or revision is invalid')
        self._validate_projection({'type': self.record_type, 'schema_version': SCHEMA_VERSION, **snapshot}, check_events=False)

    def _validate_projection(self, record: Mapping[str, Any], *, check_events: bool) -> None:
        if record.get('type') != self.record_type:
            self._error('record type is invalid')
        if record.get('schema_version') != SCHEMA_VERSION:
            self._error('schema version is unsupported')
        record_id = self._require_id(record.get('record_id'), 'record ID')
        revision = record.get('record_revision')
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            self._error('record_revision must be a positive integer')
        status = record.get('status')
        if status not in STATUSES:
            self._error('status is invalid')
        self._require_text(record.get('claim'), 'claim')
        self._validate_scope(record.get('scope'))
        evidence = record.get('evidence')
        self._validate_evidence(evidence)
        observations = record.get('observations')
        self._validate_observations(observations, evidence)
        self._validate_verification(record.get('verification'), evidence, observations, revision)
        depends_on = record.get('depends_on')
        if not isinstance(depends_on, list) or len(set(depends_on)) != len(depends_on):
            self._error('depends_on must be a list of unique record IDs')
        for dependency in depends_on:
            self._require_id(dependency, 'dependency ID')
            if dependency == record_id:
                self._error('record cannot depend on itself')
        successor = record.get('superseded_by')
        if successor is not None:
            self._require_id(successor, 'successor ID')
            if successor == record_id:
                self._error('record cannot supersede itself')
        if status == 'superseded' and successor is None:
            self._error('superseded record needs a successor')
        if status != 'superseded' and successor is not None:
            self._error('only a superseded record can have a successor')
        outcome = record['verification']['outcome']
        if status in {'supported', 'disputed', 'needs_revalidation', 'unverifiable'} and outcome != status:
            self._error('verification outcome must match the current non-terminal status')
        if check_events:
            events = record.get('events')
            if not isinstance(events, list) or len(events) != revision:
                self._error('events must contain one entry for every record revision')
            previous_status: str | None = None
            previous_timestamp: datetime | None = None
            previous_snapshot: Mapping[str, Any] | None = None
            event_ids: set[str] = set()
            for expected_revision, event in enumerate(events, 1):
                if not isinstance(event, dict) or set(event) != {'event_id', 'action', 'timestamp', 'actor', 'reason', 'prior_status', 'resulting_status', 'snapshot'}:
                    self._error('event is incomplete')
                event_id = self._require_id(event.get('event_id'), 'event ID')
                if event_id in event_ids:
                    self._error(f'duplicate event ID: {event_id}')
                event_ids.add(event_id)
                action = event.get('action')
                if action not in _ACTIONS:
                    self._error('event action is invalid')
                event_timestamp = self._utc_datetime(event.get('timestamp'), 'event timestamp')
                if previous_timestamp is not None and event_timestamp <= previous_timestamp:
                    self._error('event timestamps must strictly increase')
                self._require_text(event.get('actor'), 'event actor')
                self._require_text(event.get('reason'), 'event reason')
                if event.get('prior_status') != previous_status or event.get('resulting_status') not in STATUSES:
                    self._error('event status sequence is invalid')
                prior = event['prior_status']
                resulting = event['resulting_status']
                if expected_revision == 1 and (action != 'create' or resulting not in _CREATION_STATUSES):
                    self._error('first event must create a valid initial status')
                if expected_revision > 1:
                    valid_action = {'revise': prior not in _TERMINAL_STATUSES and resulting in {'supported', 'disputed', 'needs_revalidation', 'unverifiable'}, 'dispute': prior in {'supported', 'needs_revalidation', 'unverifiable'} and resulting == 'disputed', 'revalidate': prior in {'needs_revalidation', 'disputed', 'unverifiable'} and resulting == 'supported', 'supersede': prior == 'supported' and resulting == 'superseded', 'retract': prior not in _TERMINAL_STATUSES and resulting == 'retracted', 'source_change': prior == 'supported' and resulting == 'needs_revalidation', 'dependency_change': prior == 'supported' and resulting == 'needs_revalidation'}.get(action, False)
                    if not valid_action:
                        self._error('event action and status transition are unsafe')
                self._validate_snapshot(event.get('snapshot'), record_id, expected_revision)
                if previous_snapshot is not None:
                    self._validate_action_delta(action, previous_snapshot, event['snapshot'])
                verification = event['snapshot']['verification']
                self._require_verification_not_after_event(verification, event['timestamp'])
                if action in {'create', 'revise', 'dispute', 'revalidate'} and verification['record_revision'] != expected_revision:
                    self._error('semantic verification must bind the resulting record revision')
                if action in {'revise', 'dispute', 'revalidate'}:
                    self._require_fresh_verification(previous_snapshot['verification'], verification, expected_revision)
                if event['snapshot']['status'] != event['resulting_status']:
                    self._error('event result and snapshot status differ')
                previous_status = event['resulting_status']
                previous_timestamp = event_timestamp
                previous_snapshot = event['snapshot']
            if events[-1]['resulting_status'] != status or events[-1]['snapshot'] != self._snapshot(record):
                self._error('current projection differs from the last event')

    def validate_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """Validate and return a defensive copy of a complete record."""
        value = self._clone(dict(record))
        expected = {'type', 'schema_version', 'record_id', 'record_revision', 'status', 'claim', 'scope', 'observations', 'evidence', 'verification', 'depends_on', 'superseded_by', 'events'}
        if set(value) != expected:
            self._error('record projection is incomplete or has unknown fields')
        value['claim'] = self._canonical_claim(value['claim'])
        events = value.get('events')
        if isinstance(events, list):
            for event in events:
                if isinstance(event, dict) and isinstance(event.get('snapshot'), dict) and 'claim' in event['snapshot']:
                    event['snapshot']['claim'] = self._canonical_claim(event['snapshot']['claim'])
        self._validate_projection(value, check_events=True)
        return value

    def _event(self, record: Mapping[str, Any], action: str, *, prior_status: str | None, timestamp: str, actor: str, reason: str, event_id: str) -> dict[str, Any]:
        return {'event_id': self._require_id(event_id, 'event ID'), 'action': action, 'timestamp': self._require_utc(timestamp, 'event timestamp'), 'actor': self._require_text(actor, 'event actor'), 'reason': self._require_text(reason, 'event reason'), 'prior_status': prior_status, 'resulting_status': record['status'], 'snapshot': self._snapshot(record)}

    def _finish(self, record: Mapping[str, Any], action: str, *, timestamp: str, actor: str, reason: str, event_id: str, prior_status: str | None) -> dict[str, Any]:
        result = self._clone(dict(record))
        prior_revision = result['record_revision']
        result['record_revision'] = prior_revision + 1
        self._require_verification_not_after_event(result['verification'], timestamp)
        result.setdefault('events', []).append(self._event(result, action, prior_status=prior_status, timestamp=timestamp, actor=actor, reason=reason, event_id=event_id))
        return self.validate_record(result)

    def create_record(self, record_id: str, claim: str, scope: Mapping[str, Any], observations: list[Mapping[str, Any]], evidence: Mapping[str, Any], verification: Mapping[str, Any], *, status: str='supported', depends_on: list[str] | None=None, timestamp: str, actor: str, reason: str, event_id: str) -> dict[str, Any]:
        """Create a record with revision one and one complete create snapshot."""
        if status not in _CREATION_STATUSES:
            self._error('creation status is invalid')
        record: dict[str, Any] = {'type': self.record_type, 'schema_version': SCHEMA_VERSION, 'record_id': record_id, 'record_revision': 1, 'status': status, 'claim': self._canonical_claim(claim), 'scope': self._clone(dict(scope)), 'observations': self._clone(observations), 'evidence': self._clone(dict(evidence)), 'verification': self._clone(dict(verification)), 'depends_on': self._clone(depends_on or []), 'superseded_by': None, 'events': []}
        self._validate_projection(record, check_events=False)
        self._require_verification_not_after_event(record['verification'], timestamp)
        record['events'].append(self._event(record, 'create', prior_status=None, timestamp=timestamp, actor=actor, reason=reason, event_id=event_id))
        return self.validate_record(record)

    def _require_fresh_verification(self, prior: Mapping[str, Any], current: Mapping[str, Any], target_revision: int) -> None:
        if current.get('record_revision') != target_revision:
            self._error(f'verification.record_revision must be {target_revision}')
        prior_time = self._utc_datetime(prior.get('verified_at'), 'prior verification.verified_at')
        current_time = self._utc_datetime(current.get('verified_at'), 'verification.verified_at')
        if current_time <= prior_time:
            self._error('verification.verified_at must be newer than the prior semantic verification')

    def _require_verification_not_after_event(self, verification: Mapping[str, Any], timestamp: str) -> None:
        verified_at = self._utc_datetime(verification.get('verified_at'), 'verification.verified_at')
        event_time = self._utc_datetime(timestamp, 'event timestamp')
        if verified_at > event_time:
            self._error('verification.verified_at cannot be later than the event timestamp')

    def _editable(self, record: Mapping[str, Any]) -> dict[str, Any]:
        value = self.validate_record(record)
        if value['status'] in _TERMINAL_STATUSES:
            self._error(f"{value['status']} records are terminal")
        return value

    def revise(self, record: Mapping[str, Any], *, claim: str | None=None, scope: Mapping[str, Any] | None=None, observations: list[Mapping[str, Any]] | None=None, evidence: Mapping[str, Any] | None=None, verification: Mapping[str, Any] | None=None, depends_on: list[str] | None=None, timestamp: str, actor: str, reason: str, event_id: str) -> dict[str, Any]:
        """Revise current claim data; changed data needs fresh verification."""
        result = self._editable(record)
        if claim is None and scope is None and (observations is None) and (evidence is None) and (verification is None) and (depends_on is None):
            self._error('revise needs a changed field or verification')
        changed = any((value is not None for value in (claim, scope, observations, evidence, depends_on)))
        target_revision = result['record_revision'] + 1
        if claim is not None:
            result['claim'] = self._canonical_claim(claim)
        if scope is not None:
            result['scope'] = self._clone(dict(scope))
        if observations is not None:
            result['observations'] = self._clone(observations)
        if evidence is not None:
            result['evidence'] = self._clone(dict(evidence))
        if depends_on is not None:
            result['depends_on'] = self._clone(depends_on)
        if verification is None:
            if changed:
                result['status'] = 'needs_revalidation'
                result['verification'] = {'record_revision': target_revision, 'verified_at': timestamp, 'verifier': actor, 'outcome': 'needs_revalidation', 'evidence_ids': sorted({evidence_id for observation in result['observations'] for evidence_id in observation.get('evidence_ids', [])})}
        else:
            result['verification'] = self._clone(dict(verification))
            result['status'] = result['verification'].get('outcome')
        self._require_fresh_verification(record['verification'], result['verification'], target_revision)
        return self._finish(result, 'revise', timestamp=timestamp, actor=actor, reason=reason, event_id=event_id, prior_status=record['status'])

    def dispute(self, record: Mapping[str, Any], *, timestamp: str, actor: str, reason: str, event_id: str) -> dict[str, Any]:
        """Mark an unresolved claim dispute without changing its claim text."""
        result = self._editable(record)
        if result['status'] == 'disputed':
            self._error('record is already disputed')
        result['status'] = 'disputed'
        result['verification'] = {**result['verification'], 'record_revision': result['record_revision'] + 1, 'verified_at': timestamp, 'verifier': actor, 'outcome': 'disputed'}
        self._require_fresh_verification(record['verification'], result['verification'], result['record_revision'] + 1)
        return self._finish(result, 'dispute', timestamp=timestamp, actor=actor, reason=reason, event_id=event_id, prior_status=record['status'])

    def revalidate(self, record: Mapping[str, Any], verification: Mapping[str, Any], *, timestamp: str, actor: str, reason: str, event_id: str) -> dict[str, Any]:
        """Apply a fresh semantic verification, normally restoring support."""
        result = self._editable(record)
        if result['status'] not in {'needs_revalidation', 'disputed', 'unverifiable'}:
            self._error('only non-current records can be revalidated')
        result['verification'] = self._clone(dict(verification))
        if result['verification'].get('outcome') != 'supported':
            self._error('successful revalidation requires supported verification')
        self._require_fresh_verification(record['verification'], result['verification'], result['record_revision'] + 1)
        result['status'] = 'supported'
        return self._finish(result, 'revalidate', timestamp=timestamp, actor=actor, reason=reason, event_id=event_id, prior_status=record['status'])

    def supersede(self, record: Mapping[str, Any], successor: Mapping[str, Any], *, timestamp: str, actor: str, reason: str, event_id: str) -> dict[str, Any]:
        """Mark a supported record superseded by a supported successor."""
        result = self._editable(record)
        successor_value = self.validate_record(successor)
        if result['status'] != 'supported':
            self._error('only a supported record can be superseded')
        if successor_value['status'] != 'supported':
            self._error('supersession requires a supported successor')
        if successor_value['record_id'] == result['record_id']:
            self._error('record cannot supersede itself')
        result['status'] = 'superseded'
        result['superseded_by'] = successor_value['record_id']
        return self._finish(result, 'supersede', timestamp=timestamp, actor=actor, reason=reason, event_id=event_id, prior_status=record['status'])

    def retract(self, record: Mapping[str, Any], *, timestamp: str, actor: str, reason: str, event_id: str) -> dict[str, Any]:
        """Logically retract a non-terminal record while retaining its history."""
        result = self._editable(record)
        result['status'] = 'retracted'
        return self._finish(result, 'retract', timestamp=timestamp, actor=actor, reason=reason, event_id=event_id, prior_status=record['status'])

    def serialize_record(self, record: Mapping[str, Any]) -> str:
        """Serialize a validated record as inspectable Markdown with JSON frontmatter."""
        value = self.validate_record(record)
        frontmatter = {'permalink': f"{self.permalink_prefix}/{value['record_id']}", **{key: self._clone(item) for key, item in value.items() if key != 'claim'}}
        return '---\n' + json.dumps(frontmatter, indent=2, ensure_ascii=False, sort_keys=True) + '\n---\n' + value['claim']

    def parse_record(self, text: str) -> dict[str, Any]:
        """Parse and validate one serialized governed Markdown record."""
        if not isinstance(text, str):
            self._error('record must start with YAML frontmatter')
        text = text.replace('\r\n', '\n')
        if not text.startswith('---\n'):
            self._error('record must start with YAML frontmatter')
        delimiter = text.find('\n---\n', 4)
        if delimiter < 0:
            self._error('record frontmatter is not closed')
        raw_frontmatter = text[4:delimiter]
        try:
            frontmatter = self.decode_frontmatter(raw_frontmatter)
        except Exception as exc:
            raise RecordError('frontmatter must be JSON-compatible YAML') from exc
        if not isinstance(frontmatter, dict):
            self._error('frontmatter must be an object')
        permalink = frontmatter.pop('permalink', None)
        claim = text[delimiter + 5:]
        value = dict(frontmatter)
        value['claim'] = claim
        record = self.validate_record(value)
        if permalink is not None and permalink != f"{self.permalink_prefix}/{record['record_id']}":
            self._error('record permalink does not match its ID')
        return record

    def compute_etag(self, value: str | Mapping[str, Any]) -> str:
        """Return the SHA-256 etag for serialized record bytes."""
        text = value if isinstance(value, str) else self.serialize_record(value)
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def mark_needs_revalidation(self, record: Mapping[str, Any], *, cause: str, condition_id: str, timestamp: str, actor: str, reason: str) -> dict[str, Any]:
        """Record one deterministic source or dependency condition without changing claim meaning."""
        result = self.validate_record(record)
        action = {'source': 'source_change', 'dependency': 'dependency_change'}.get(cause)
        if action is None:
            self._error('revalidation cause must be source or dependency')
        condition_id = self._require_id(condition_id, 'condition ID')
        for event in result['events']:
            if event['event_id'] == condition_id:
                if event['action'] != action:
                    self._error('condition ID already belongs to another action')
                return result
        if result['status'] != 'supported':
            return result
        prior_status = result['status']
        claim = result['claim']
        result['status'] = 'needs_revalidation'
        result['verification'] = {**result['verification'], 'outcome': 'needs_revalidation'}
        updated = self._finish(result, action, timestamp=timestamp, actor=actor, reason=reason, event_id=condition_id, prior_status=prior_status)
        if updated['claim'] != claim:
            self._error('deterministic revalidation cannot change claim meaning')
        return updated

    def apply_evidence_health(self, record: Mapping[str, Any], outcome: str, *, condition_id: str, timestamp: str, actor: str, reason: str) -> dict[str, Any]:
        """Apply one explicit evidence outcome and report whether it changes durable state."""
        if outcome not in _EVIDENCE_OUTCOMES:
            self._error('evidence outcome is invalid')
        value = self.validate_record(record)
        if outcome in {'unchanged', 'inaccessible'}:
            return {'outcome': outcome, 'record': value, 'mutated': False, 'transient': outcome == 'inaccessible'}
        updated = self.mark_needs_revalidation(value, cause='source', condition_id=condition_id, timestamp=timestamp, actor=actor, reason=reason)
        return {'outcome': outcome, 'record': updated, 'mutated': updated != value, 'transient': False}
