"""Synthetic acceptance coverage for persistent governed record operations."""
import asyncio
import copy
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from kajamite.engine import KnowledgeEngine
from kajamite import receipt
from kajamite.errors import BackendError, MutationUncertain
from kajamite.governance import RecordEngine, RecordError
from kajamite.service import KnowledgeError
from test_service import FakeBackend


STAMP = "2026-01-01T00:00:00.000000Z"


def source_record():
    return RecordEngine().create_record(
        "synthetic-fact", "\nA synthetic governed claim.\n\n", {"system": "example"},
        [{"observation_id": "observed", "statement": "Synthetic observation.",
          "evidence_ids": ["source"]}],
        {"source": {"kind": "document", "reference": "example:manual@1", "observed_at": STAMP}},
        {"record_revision": 1, "verified_at": STAMP, "verifier": "reviewer",
         "outcome": "supported", "evidence_ids": ["source"]},
        timestamp=STAMP, actor="reviewer", reason="Evidence reviewed", event_id="created",
    )


class FramingBackend(FakeBackend):
    """Models a backend that adds one blank newline around native Markdown bodies."""

    async def call(self, name, arguments):
        result = await super().call(name, arguments)
        if name == "read_note":
            result["content"] = "\n" + result["content"] + "\n"
        return result


class KnowledgeEngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend = FakeBackend()
        self.engine = KnowledgeEngine(self.backend)

    async def test_creation_claim_digest_preserves_markdown_framing(self):
        record = source_record()
        result = await KnowledgeEngine(FramingBackend()).record_create('facts', record)
        change = result['knowledge_change']
        self.assertEqual(hashlib.sha256(record['claim'].encode('utf-8')).hexdigest(), change['record_claim_sha256'])
        self.assertNotEqual(change['record_claim_sha256'], change['after']['content_sha256'])
        self.assertEqual(record['claim'], result['record']['claim'])
        self.assertEqual(result['committed_revision'], change['record_revision'])

    async def test_duplicate_creation_reports_no_write_started(self):
        await self.engine.record_create('facts', source_record())
        before = copy.deepcopy(self.backend.notes)
        self.backend.calls.clear()
        with self.assertRaisesRegex(KnowledgeError, 'already present') as caught:
            await self.engine.record_create('facts', source_record())
        self.assertEqual('not_started', caught.exception.mutation_outcome)
        self.assertEqual(before, self.backend.notes)
        self.assertTrue(all(name in {'list_directory', 'read_note'} for name, _ in self.backend.calls))

    async def test_creation_rejects_markdown_suffix_without_breaking_existing_ids(self):
        for identifier in ("topic.md", "topic.MD"):
            record = source_record()
            record["record_id"] = record["events"][0]["snapshot"]["record_id"] = identifier
            with self.assertRaisesRegex(KnowledgeError, "omit the .md suffix"):
                await self.engine.record_create("facts", record)
        self.assertEqual([], self.backend.calls)
        legacy = source_record()
        legacy["record_id"] = legacy["events"][0]["snapshot"]["record_id"] = "legacy.md"
        await self.backend.call("write_note", {"title": "legacy.md", "content": legacy["claim"],
            "directory": "facts", "note_type": "governed-record", "overwrite": False,
            "metadata": {"kajamite_record": legacy, "kajamite_operations": {}}})
        self.assertEqual(legacy, (await self.engine.read("facts/legacy.md.md", mode="inspect"))["record"])
        changed = await self.engine.record_transition("facts/legacy.md.md", "dispute", 1, "review",
            "2026-01-01T00:00:01.000000Z", "reviewer", "Synthetic review")
        self.assertEqual("disputed", changed["record"]["status"])

    async def test_compact_mutations_preserve_receipts_history_and_replay(self):
        for invalid in (None, 0, "false"):
            with self.assertRaisesRegex(ValueError, "include_history"):
                await self.engine.record_create("facts", source_record(), include_history=invalid)
            with self.assertRaisesRegex(ValueError, "include_history"):
                await self.engine.record_transition("facts/missing.md", "dispute", 1, "bad",
                    STAMP, "reviewer", "Check", include_history=invalid)
        self.assertEqual({}, self.backend.notes)
        created = await self.engine.record_create("facts", source_record(), include_history=False)
        self.assertIs(created["history_included"], False)
        self.assertNotIn("events", created["record"])
        full = await self.engine.read(created["identifier"], mode="inspect")
        self.assertEqual(source_record(), full["record"])
        args = (created["identifier"], "dispute", 1, "disputed",
                "2026-01-01T00:00:01.000000Z", "reviewer", "Conflicting evidence")
        changed = await self.engine.record_transition(*args, include_history=False)
        record = (await self.engine.read(created["identifier"], mode="inspect"))["record"]
        self.assertEqual({k: v for k, v in record.items() if k != "events"}, changed["record"])
        self.assertEqual("disputed", changed["record"]["status"])
        self.assertEqual(2, len(record["events"]))
        complete = self.engine._record_result(changed["mutation"], {"file_path": created["identifier"]},
            record, copy.deepcopy(changed["knowledge_change"]), replayed=False)
        for key in ("knowledge_change", "knowledge_change_text", "committed_revision", "replayed"):
            self.assertEqual(complete[key], changed[key])
        stored = copy.deepcopy(self.backend.notes)
        replay = await self.engine.record_transition(*args)
        self.assertTrue(replay["replayed"])
        self.assertEqual(record, replay["record"])
        self.assertNotIn("history_included", replay)
        compact_replay = await self.engine.record_transition(*args, include_history=False)
        self.assertTrue(compact_replay["replayed"])
        self.assertEqual(2, compact_replay["operation_revision"])
        self.assertEqual(changed["record"], compact_replay["record"])
        with self.assertRaisesRegex(KnowledgeError, "revision conflict"):
            await self.engine.record_transition(created["identifier"], "dispute", 1, "stale",
                STAMP, "reviewer", "Stale revision", include_history=False)
        self.assertEqual(stored, self.backend.notes)

    async def test_governed_heading_is_a_display_title_without_changing_identity(self):
        original = source_record()
        record = self.engine.records.create_record('stable-id', '# Resource retry policy\n\n' + original['claim'],
            original['scope'], original['observations'], original['evidence'], original['verification'],
            timestamp=STAMP, actor='reviewer', reason='Source reviewed', event_id='created')
        created = await self.engine.record_create('facts', record)
        identifier = created['identifier']
        self.assertEqual('facts/stable-id.md', identifier)
        self.assertEqual('Resource retry policy', created['knowledge_change']['after']['title'])
        self.engine.evidence_checker = lambda record, scope: True
        snapshot = copy.deepcopy(self.backend.notes)
        self.assertEqual('Resource retry policy', (await self.engine.read(identifier, mode='inspect'))['title'])
        self.assertEqual('Resource retry policy', (await self.engine.read(identifier, request_scope=record['scope']))['title'])
        self.assertEqual('Resource retry policy', (await self.engine.search(['facts'], 'Resource', mode='inspect'))['results'][0]['title'])
        self.assertEqual('Resource retry policy', (await self.engine.list('facts', mode='inspect'))['nodes'][0]['title'])
        self.assertEqual('Resource retry policy', (await self.engine.context(identifiers=[identifier], mode='inspect'))['notes'][0]['title'])
        self.assertEqual(snapshot, self.backend.notes)
        self.assertEqual('stable-id', self.backend.notes[identifier]['title'])
        self.assertEqual(record, (await self.engine.read(identifier, mode='inspect'))['record'])
        ordinary = {'title': 'Explicit note title', 'content': '# Different heading'}
        self.assertEqual('Explicit note title', receipt.display_title(ordinary))
        self.assertEqual('Explicit note title', receipt.display_title(ordinary | {'content': '    # Code', 'frontmatter': {'kajamite_record': {}}}))

    async def test_inspection_context_budgets_prose_and_keeps_history_in_explicit_reads(self):
        created = await self.engine.record_create("facts", source_record())
        changed = await self.engine.record_transition(created["identifier"], "revise", 1, "revise",
            "2026-01-01T00:00:01.000000Z", "reviewer", "Correct the explanation", {"claim": "Current explanation."})
        plain = await self.engine.create("Route", "Read the explanation.", "facts")
        identifiers = [created["identifier"], plain["note"]["identifier"]]
        size = len(changed["record"]["claim"]) + len("Read the explanation.")
        bundle = await self.engine.context(identifiers=identifiers, mode="inspect", max_chars=size)
        self.assertEqual([note["content"] for note in bundle["notes"]], ["Current explanation.", "Read the explanation."])
        self.assertEqual(bundle["used_chars"], size)
        self.assertFalse(bundle["partial"])
        governed, ordinary = bundle["notes"]
        self.assertEqual(governed["record_status"], "needs_revalidation")
        self.assertEqual(governed["evidence"], changed["record"]["evidence"])
        self.assertFalse(governed["history_included"])
        self.assertTrue(all(note["mode"] == "inspect" and note["reuse_checked"] is False for note in bundle["notes"]))
        self.assertEqual(ordinary["review_status"], "unreviewed")
        self.assertNotIn("record", governed)
        clipped = await self.engine.context(identifiers=identifiers, mode="inspect", max_chars=5)
        self.assertEqual(clipped["notes"][0]["content"], "Curre")
        self.assertTrue(clipped["notes"][0]["truncated"])
        self.assertIsNone(clipped["notes"][0]["next_offset"])
        self.assertEqual(clipped["omitted"][0]["reason"], "character_budget")
        full = await self.engine.read(created["identifier"], mode="inspect")
        self.assertEqual(full["record"], changed["record"])
        self.assertGreater(len(full["record"]["events"]), 1)

    async def test_supersession_resolves_a_pinned_local_successor_and_replays(self):
        original = source_record()
        created = await self.engine.record_create("facts", original)
        successor = self.engine.records.create_record(
            "replacement", "Replacement explanation.", original["scope"], original["observations"],
            original["evidence"], original["verification"], timestamp=STAMP,
            actor="reviewer", reason="Evidence reviewed", event_id="replacement-created")
        target = await self.engine.record_create("facts", successor)
        changes = {"successor_identifier": target["identifier"], "successor_revision": 1}
        async def transition(payload, operation="supersede"):
            return await self.engine.record_transition(created["identifier"], "supersede", 1, operation,
                "2026-01-01T00:00:01.000000Z", "reviewer", "Consolidate supported explanations", payload)
        for payload, message in (
            ({"successor": target["identifier"]}, "complete successor record"),
            ({"successor_identifier": target["identifier"]}, "successor_revision"),
            (changes | {"successor_revision": True}, "positive integer"),
            (changes | {"successor_revision": 2}, "successor revision conflict"),
            (changes | {"successor_identifier": created["identifier"]}, "cannot supersede itself"),
        ):
            with self.assertRaisesRegex(KnowledgeError, message):
                await transition(payload)
            self.assertEqual((await self.engine.read(created["identifier"], mode="inspect"))["record"], original)
        other = await self.engine.record_create("other", successor)
        with self.assertRaisesRegex(KnowledgeError, "same namespace"):
            await transition(changes | {"successor_identifier": other["identifier"]})
        incompatible = self.engine.records.create_record(
            "different-scope", "Different applicability.", {"system": "different"}, original["observations"],
            original["evidence"], original["verification"], timestamp=STAMP,
            actor="reviewer", reason="Evidence reviewed", event_id="different-created")
        different = await self.engine.record_create("facts", incompatible)
        with self.assertRaisesRegex(KnowledgeError, "same scope"):
            await transition(changes | {"successor_identifier": different["identifier"]})
        self.assertEqual((await self.engine.read(created["identifier"], mode="inspect"))["record"], original)
        result = await transition(changes)
        self.assertEqual(result["record"]["status"], "superseded")
        self.assertEqual(result["record"]["superseded_by"], "replacement")
        self.assertEqual(result["record"]["events"][0], original["events"][0])
        self.assertTrue((await transition(changes))["replayed"])

    async def test_reuse_checks_actual_premises_and_withholds_stale_snippets(self):
        premise = source_record()
        await self.engine.record_create("facts", premise)
        dependent = self.engine.records.create_record(
            "dependent", "Dependent synthetic claim.", premise["scope"],
            premise["observations"], premise["evidence"], premise["verification"],
            depends_on=[premise["record_id"]], timestamp=STAMP,
            actor="reviewer", reason="Evidence reviewed", event_id="dependent-created")
        created = await self.engine.record_create("facts", dependent)
        calls = []
        outcome = "unchanged"
        def check(record, scope):
            calls.append(record["record_id"])
            return {"outcome": outcome if record["record_id"] == premise["record_id"] else "unchanged"}
        self.engine.evidence_checker = check
        scope = premise["scope"]
        visible = await self.engine.read(created["identifier"], request_scope=scope)
        self.assertEqual(dependent["claim"], visible["content"])
        self.assertEqual([premise["record_id"], "dependent"], calls)
        for outcome in ("changed", "inaccessible", "missing"):
            with self.subTest(outcome=outcome):
                calls.clear()
                withheld = await self.engine.read(created["identifier"], request_scope=scope)
                self.assertTrue(withheld["withheld"])
                self.assertEqual("dependency_source_" + outcome, withheld["reason"])
                context = await self.engine.context(identifiers=[created["identifier"]], request_scope=scope)
                self.assertNotIn(dependent["claim"], str(context))
        del self.backend.notes["facts/synthetic-fact.md"]
        withheld = await self.engine.read(created["identifier"], request_scope=scope)
        self.assertEqual("dependency_unavailable", withheld["reason"])

    async def test_create_without_acknowledged_identity_is_uncertain(self):
        original = self.backend.call
        async def lose_acknowledgment(name, arguments):
            result = await original(name, arguments)
            return {} if name == "write_note" else result
        self.backend.call = lose_acknowledgment
        with self.assertRaises(MutationUncertain):
            await self.engine.create("Committed", "Synthetic content.", "facts")
        self.assertTrue(self.backend.notes)

    async def test_plain_notes_remain_unreviewed_and_cannot_claim_governance(self):
        ordinary = await self.engine.create("Preference", "Tea", "personal", metadata={"status": "supported"})
        read = await self.engine.read(ordinary["note"]["identifier"])
        self.assertEqual("Tea", read["content"])
        self.assertEqual("unreviewed", read["review_status"])
        with self.assertRaisesRegex(ValueError, "governed"):
            await self.engine.create("Bad", "body", "personal", kind="governed-record")
        with self.assertRaisesRegex(ValueError, "governed"):
            await self.engine.create("Bad", "body", "personal", metadata={"kajamite_record": {}})

    async def test_revise_authorizes_plain_notes_and_rejects_governed_records(self):
        ordinary = await self.engine.create("Draft", "old and stable", "facts")
        identifier = ordinary["note"]["identifier"]
        changed = await self.engine.revise(
            identifier, hashlib.sha256(b"old and stable").hexdigest(),
            [{"find_text": "old", "replacement": "new"}],
        )
        self.assertEqual("new and stable", changed["note"]["content"])
        governed = await self.engine.record_create("facts", source_record())
        with self.assertRaisesRegex(KnowledgeError, "lifecycle transition"):
            await self.engine.revise(
                governed["identifier"], "0" * 64,
                [{"find_text": "synthetic", "replacement": "changed"}],
            )

    async def test_collection_inspection_omits_governed_and_unauthorized_notes(self):
        allowed = await self.engine.create("Allowed", "ordinary", "facts")
        await self.engine.create("Denied", "ordinary", "facts")
        await self.engine.record_create("facts", source_record())
        self.engine.authorize = lambda identifier, scope: not identifier.endswith("denied.md")
        result = await self.engine.inspect_collection("facts")
        self.assertEqual([allowed["note"]["identifier"]], [note["identifier"] for note in result["notes"]])
        reasons = [item["reason"] for item in result["omissions"]]
        self.assertIn("access_denied", reasons)
        self.assertIn("governed_record", reasons)

    async def test_evidence_health_noop_is_explicit_without_a_write(self):
        created = await self.engine.record_create("facts", source_record())
        calls = len(self.backend.calls)
        unchanged = await self.engine.record_transition(
            created["identifier"], "evidence_health", 1, "health-1",
            "2026-01-01T00:00:00.000001Z", "reviewer", "Source unavailable",
            {"outcome": "inaccessible", "condition_id": "source-check"}, include_history=False,
        )
        self.assertFalse(unchanged["mutated"])
        self.assertFalse(unchanged["history_included"])
        self.assertNotIn("events", unchanged["record"])
        self.assertTrue(unchanged["transient"])
        self.assertEqual(calls + 1, len(self.backend.calls))  # The current record was read, not written.

    async def test_record_persistence_body_framing_and_reuse_guard(self):
        framing = KnowledgeEngine(FramingBackend())
        created = await framing.record_create("facts", source_record())
        self.assertEqual(1, created["committed_revision"])
        identifier = created["identifier"]
        withheld = await framing.read(identifier)
        self.assertTrue(withheld["withheld"])
        self.assertEqual("unknown_scope", withheld["reason"])
        inspected = await framing.read(identifier, mode="inspect")
        self.assertEqual("synthetic-fact", inspected["record"]["record_id"])

        reusable = KnowledgeEngine(framing.backend, evidence_checker=lambda record, scope: True)
        visible = await reusable.read(identifier, request_scope={"system": "example"})
        self.assertEqual(source_record()["claim"], visible["content"])
        self.assertNotIn("kajamite_record", visible["metadata"])

    async def test_inspect_can_omit_history_without_skipping_validation(self):
        created = await self.engine.record_create("facts", source_record())
        identifier = created["identifier"]
        full = await self.engine.read(identifier, mode="inspect")
        self.assertEqual(full, await self.engine.read(identifier, mode="inspect", include_history=True))
        before = copy.deepcopy(self.backend.notes[identifier])
        compact = await self.engine.read(identifier, mode="inspect", include_history=False)
        expected_record = {key: value for key, value in full["record"].items() if key != "events"}
        self.assertEqual(expected_record, compact["record"])
        self.assertEqual({"identifier": full["identifier"], "title": full["title"], "record": expected_record,
                          "mode": "inspect", "history_included": False}, compact)
        self.assertEqual(before, self.backend.notes[identifier])

        corrupt = copy.deepcopy(before)
        corrupt["frontmatter"]["kajamite_record"]["events"] = []
        self.backend.notes[identifier] = corrupt
        with self.assertRaisesRegex(KnowledgeError, "metadata is invalid"):
            await self.engine.read(identifier, mode="inspect", include_history=False)

    async def test_read_rejects_non_bool_include_history(self):
        ordinary = await self.engine.create("Plain", "ordinary", "facts")
        for value in (None, 0, 1, "false", []):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "include_history must be a bool"):
                await self.engine.read(ordinary["note"]["identifier"], include_history=value)

    async def test_transition_is_atomic_idempotent_and_detects_conflicts(self):
        created = await self.engine.record_create("facts", source_record())
        identifier = created["identifier"]
        updated = await self.engine.record_transition(
            identifier, "revise", 1, "revise-1", "2026-01-01T00:00:00.000001Z",
            "reviewer", "Clarified", {"claim": "Revised synthetic claim.\n"},
        )
        self.assertEqual(2, updated["committed_revision"])
        self.assertIn("scope.system", [field["key"] for field in created["knowledge_change"]["record_changes"]])
        self.assertEqual(["status"],
                         [field["key"] for field in updated["knowledge_change"]["record_changes"]])
        self.assertEqual("Revised synthetic claim.\n", updated["record"]["claim"])
        edits = len([name for name, _ in self.backend.calls if name == "edit_note"])
        replay = await self.engine.record_transition(
            identifier, "revise", 1, "revise-1", "2026-01-01T00:00:00.000001Z",
            "reviewer", "Clarified", {"claim": "Revised synthetic claim.\n"},
        )
        self.assertTrue(replay["replayed"])
        self.assertEqual(edits, len([name for name, _ in self.backend.calls if name == "edit_note"]))
        with self.assertRaisesRegex(KnowledgeError, "different inputs"):
            await self.engine.record_transition(
                identifier, "revise", 1, "revise-1", "2026-01-01T00:00:00.000001Z",
                "reviewer", "Different", {"claim": "Other claim."},
            )
        with self.assertRaisesRegex(KnowledgeError, "revision conflict"):
            await self.engine.record_transition(
                identifier, "retract", 1, "retract-1", "2026-01-01T00:00:00.000002Z",
                "reviewer", "Retract",
            )

    async def test_plain_receipt_projects_changes_and_keeps_saved_state_and_raw_audit(self):
        created = await self.engine.record_create('facts', source_record())
        changed = await self.engine.record_transition(created['identifier'], 'revise', 1, 'first',
            '2026-01-01T00:00:01.000000Z', 'reviewer', 'Clarify', {'claim': 'First corrected explanation.'})
        updated = await self.engine.record_transition(created['identifier'], 'revise', 2, 'second',
            '2026-01-01T00:00:02.000000Z', 'reviewer', 'Clarify again', {'claim': 'Second corrected explanation.'})
        self.assertEqual('needs_revalidation', changed['record']['status'])
        self.assertEqual('needs_revalidation', updated['record']['status'])
        text = updated['knowledge_change_text']
        self.assertIn('First corrected explanation.', text)
        self.assertIn('Second corrected explanation.', text)
        self.assertIn('Saved record state: needs_revalidation', text)
        self.assertIn('Committed record revision: 3', text)
        self.assertNotIn('kajamite_record', text)
        self.assertNotIn('kajamite_operations', text)
        self.assertEqual(updated['record'], self.engine.records.validate_record(updated['record']))
        self.assertEqual(3, len(updated['record']['events']))
        change = updated['knowledge_change']
        snapshot = copy.deepcopy(change)
        rendered = receipt.render(change)
        self.assertEqual(snapshot, change)
        self.assertIn('Full record metadata and history', rendered)
        self.assertIn('SHA-256', rendered)
        legacy = copy.deepcopy(change)
        del legacy['record_changes']
        self.assertIn('Metadata kajamite_record', receipt.render(legacy))
        status_text = changed['knowledge_change_text']
        self.assertIn('Record status:', status_text)
        self.assertIn('needs_revalidation', status_text)

    async def test_record_review_omits_rechecks_and_mirrors_but_retains_support_changes(self):
        original = source_record()
        claim = 'An existing explanation.'
        record = self.engine.records.create_record('review', claim, original['scope'],
            [{'observation_id': 'claim', 'statement': claim, 'evidence_ids': ['source']}],
            original['evidence'], original['verification'], timestamp=STAMP,
            actor='reviewer', reason='Source reviewed', event_id='created')
        created = await self.engine.record_create('facts', record)
        evidence = copy.deepcopy(record['evidence'])
        evidence['source']['observed_at'] = '2026-01-01T00:00:01.000000Z'
        verification = record['verification'] | {'record_revision': 2, 'verified_at': evidence['source']['observed_at']}
        current_claim = '# A readable title\n\n' + claim
        observations = [record['observations'][0] | {'statement': current_claim}]
        updated = await self.engine.record_transition(created['identifier'], 'revise', 1, 'heading',
            verification['verified_at'], 'reviewer', 'Name the topic',
            {'claim': current_claim, 'evidence': evidence, 'verification': verification, 'observations': observations})
        self.assertEqual([], updated['knowledge_change']['record_changes'])
        self.assertEqual(evidence, updated['record']['evidence'])
        self.assertEqual(verification, updated['record']['verification'])
        self.assertEqual(observations, updated['record']['observations'])
        self.assertEqual(record['events'], updated['record']['events'][:1])
        self.assertTrue(updated['knowledge_change']['metadata_changes'])
        snapshot = copy.deepcopy(updated['record'])
        for field, value in [('reference', 'example:manual@2'), ('excerpt_sha256', 'a' * 64)]:
            changed = copy.deepcopy(snapshot)
            changed['evidence']['source'][field] = value
            rows = receipt.record_changes(snapshot, changed)
            self.assertIn('1 updated', next(row['message'] for row in rows if row['key'] == 'evidence'))
        changed = copy.deepcopy(snapshot)
        changed['observations'][0]['evidence_ids'] = ['different-source']
        self.assertEqual(['observations'], [row['key'] for row in receipt.record_changes(snapshot, changed)])
        changed['observations'][0]['evidence_ids'] = ['source']
        changed['observations'][0]['statement'] = 'An independently changed observation.'
        self.assertEqual(['observations'], [row['key'] for row in receipt.record_changes(snapshot, changed)])
        self.assertEqual(snapshot, updated['record'])

    def test_record_receipt_suppresses_only_proven_single_passage_mirrors(self):
        records = RecordEngine()
        source = source_record()
        old, new = 'Retry after 60 seconds.', 'Retry after 20 seconds.'
        observations = [dict(observation_id='purpose', statement='Purpose remains.', evidence_ids=['source']),
                        dict(observation_id='retry', statement=old, evidence_ids=['source'])]
        before = records.create_record('passages', 'Purpose remains.\n\n' + old, source['scope'],
            observations, source['evidence'], source['verification'],
            timestamp=STAMP, actor='reviewer', reason='Synthetic passages', event_id='created')
        verification = source['verification'] | {'record_revision': 2, 'verified_at': '2026-01-01T00:00:01.000000Z'}
        def revise(claim, items, **fields):
            return records.revise(before, claim=claim, observations=items, verification=verification,
                timestamp=verification['verified_at'], actor='reviewer', reason='Synthetic correction', event_id='revised', **fields)
        after = revise(before['claim'].replace(old, new), [observations[0], observations[1] | {'statement': new}])
        original = copy.deepcopy((before, after))
        self.assertEqual([], receipt.record_changes(before, after))
        self.assertEqual(original, (before, after))
        for claim, items in [
            (before['claim'], [observations[0] | {'statement': old}, observations[1]]),
            (after['claim'], [observations[0], observations[1] | {'statement': 'Independent support changed.'}]),
            (after['claim'].replace('Purpose remains.', 'Purpose clarified.'),
                [observations[0] | {'statement': 'Purpose clarified.'}, observations[1] | {'statement': new}]),
        ]:
            self.assertIn('observations', [row['key'] for row in receipt.record_changes(before, revise(claim, items))])
        extra = source['evidence'] | {'extra': source['evidence']['source'] | {'reference': 'example:other'}}
        verification['evidence_ids'] = ['source', 'extra']
        rebound = revise(after['claim'], [observations[0], observations[1] | {'statement': new, 'evidence_ids': ['extra']}], evidence=extra)
        self.assertIn('observations', [row['key'] for row in receipt.record_changes(before, rebound)])
        ambiguous_before = {'claim': old + '\n' + old, 'observations': [observations[1]]}
        ambiguous_after = {'claim': new + '\n' + old, 'observations': [observations[1] | {'statement': new}]}
        self.assertIn('observations', [row['key'] for row in receipt.record_changes(ambiguous_before, ambiguous_after)])
        for before_claim, after_claim, old_text, new_text in [('aaa', 'aba', 'aa', 'ab'), ('baa', 'aaa', 'ba', 'aa')]:
            original = {'claim': before_claim, 'observations': [observations[1] | {'statement': old_text}]}
            changed = {'claim': after_claim, 'observations': [observations[1] | {'statement': new_text}]}
            self.assertIn('observations', [row['key'] for row in receipt.record_changes(original, changed)])

    async def test_record_receipt_projects_scope_and_same_count_evidence_changes(self):
        record = source_record()
        created = await self.engine.record_create("facts", record)
        evidence = copy.deepcopy(record["evidence"])
        evidence["source"]["reference"] = "example:manual@2"
        updated = await self.engine.record_transition(
            created["identifier"], "revise", 1, "scope-evidence", "2026-01-01T00:00:00.000001Z",
            "reviewer", "Updated scope and evidence", {"scope": {"product": "example"}, "evidence": evidence})
        fields = {item["key"]: item for item in updated["knowledge_change"]["record_changes"]}
        self.assertEqual("needs_revalidation", fields["status"]["after"])
        self.assertFalse(fields["scope.system"]["after_present"])
        self.assertFalse(fields["scope.product"]["before_present"])
        self.assertIn("1 updated: source", fields["evidence"]["message"])
        self.assertNotIn("0 added", fields["evidence"]["message"])
        self.assertNotIn("events", fields)
        self.assertNotIn("record_revision", fields)
        self.assertIn("kajamite_record", [item["key"] for item in updated["knowledge_change"]["metadata_changes"]])
        self.assertEqual(evidence, updated["record"]["evidence"])

    def test_record_review_names_only_changed_support_and_source_entries(self):
        before = {"claim": "Old prose.", "evidence": {
            "steady": {"reference": "example:stable", "observed_at": STAMP},
            "moved": {"reference": "example:old"}, "removed": {"reference": "example:removed"}},
            "observations": [
                {"observation_id": "mirror", "statement": "Old prose.", "evidence_ids": ["steady"]},
                {"observation_id": "detail", "statement": "Old independent statement.", "evidence_ids": ["steady"]},
                {"observation_id": "untouched", "statement": "Old prose.", "evidence_ids": ["steady"]}]}
        after = copy.deepcopy(before)
        after["claim"] = "New prose."
        after["observations"][0]["statement"] = "New prose."
        after["observations"][1]["statement"] = "New independent statement."
        after["evidence"]["steady"]["observed_at"] = "2026-01-01T00:00:01.000000Z"
        after["evidence"]["moved"]["reference"] = "example:new"
        del after["evidence"]["removed"]
        after["evidence"]["added"] = {"reference": "example:added"}
        saved = copy.deepcopy((before, after))
        messages = {row["key"]: row["message"] for row in receipt.record_changes(before, after)}
        self.assertIn("1 added: added; 1 removed: removed; 1 updated: moved", messages["evidence"])
        self.assertNotIn("steady", messages["evidence"])
        self.assertIn("1 updated: detail", messages["observations"])
        self.assertNotIn("mirror", messages["observations"])
        self.assertNotIn("untouched", messages["observations"])
        self.assertEqual(saved, (before, after))

    def test_record_review_bounds_named_entries_and_distinguishes_reordering(self):
        short = {f"source-{index:02}": {"reference": f"example:{index}"} for index in range(12)}
        message = receipt.record_changes({}, {"evidence": short})[0]["message"]
        self.assertIn("12 added: source-00, source-01, source-02 (+9 more)", message)
        self.assertNotIn("source-03", message)
        evidence = {"source-" + "x" * 115 + f"-{index:02}": {"reference": f"example:{index}"} for index in range(12)}
        message = receipt.record_changes({}, {"evidence": evidence})[0]["message"]
        self.assertIn("12 added:", message)
        self.assertIn("(+11 more)", message)
        self.assertIn(sorted(evidence)[0], message)
        self.assertNotIn(sorted(evidence)[1], message)
        self.assertLess(len(message), 250)
        before = {"observations": [{"observation_id": key, "statement": key, "evidence_ids": ["source"]} for key in ["one", "two"]]}
        after = {"observations": list(reversed(before["observations"]))}
        self.assertIn("Observation order changed.", receipt.record_changes(before, after)[0]["message"])

    async def test_transition_explains_safe_verification_errors_without_mutation(self):
        created = await self.engine.record_create("facts", source_record())
        identifier = created["identifier"]
        verification = {**source_record()["verification"], "record_revision": 2,
                        "verified_at": "2026-01-01T00:00:01.000000Z"}
        cases = [
            ({key: value for key, value in verification.items() if key != "verified_at"}, "verification is missing fields: verified_at"),
            ({**verification, "verified_at": "2026-01-01T00:00:01.000Z"}, "verification.verified_at must use canonical UTC microseconds"),
            ({**verification, "record_revision": 1}, "verification.record_revision must be 2"),
        ]
        before = copy.deepcopy(self.backend.notes[identifier])
        for invalid, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(KnowledgeError, message):
                await self.engine.record_transition(identifier, "revise", 1, "invalid",
                    "2026-01-01T00:00:01.000000Z", "reviewer", "Clarify",
                    {"claim": "Clarified claim.", "verification": invalid})
            self.assertEqual(before, self.backend.notes[identifier])
        with patch.object(self.engine.records, "revise", side_effect=RecordError("private diagnostic")):
            with self.assertRaisesRegex(KnowledgeError, "^record transition is invalid$"):
                await self.engine.record_transition(identifier, "revise", 1, "opaque",
                    "2026-01-01T00:00:01.000000Z", "reviewer", "Clarify", {"claim": "Clarified claim."})

    async def test_revision_shape_rejected_before_backend_access(self):
        verification = {"verifier": "reviewer", "outcome": "supported", "evidence_ids": ["source"]}
        for changes, message in [
            ({"status": "supported"}, "revision changes accept only"),
            ({"superseded_by": "replacement"}, "revision changes accept only"),
            ({"synthetic_extra": "hidden value"}, "revision changes accept only"),
            ({"verification": []}, "verification must be an object"),
            ({"verification": verification}, "verification is missing fields: record_revision, verified_at"),
            ({"observations": None}, "observations must be a non-empty list"),
            ({"observations": []}, "observations must be a non-empty list"),
            ({"observations": "hidden value"}, "observations must be a non-empty list"),
            ({"observations": ["hidden value"]}, r"observations\[0\] must be an object"),
            ({"observations": [{"statement": "hidden value", "evidence_ids": ["source"]}]},
             r"observations\[0\] is missing fields: observation_id"),
            ({"observations": [source_record()["observations"][0], {}]},
             r"observations\[1\] is missing fields: evidence_ids, observation_id, statement"),
        ]:
            with self.subTest(changes=changes), self.assertRaisesRegex(KnowledgeError, message) as rejected:
                await self.engine.record_transition("facts/missing.md", "revise", 1, "invalid-shape",
                    "2026-01-01T00:00:01.000000Z", "reviewer", "Clarify", changes)
            self.assertNotIn("hidden value", str(rejected.exception))
            self.assertEqual([], self.backend.calls)

    async def test_explicit_claim_mirrors_preserve_unselected_observations_and_replay(self):
        base = source_record()
        observations = [
            {"observation_id": "selected", "statement": base["claim"], "evidence_ids": ["source"]},
            {"observation_id": "equal-but-unselected", "statement": base["claim"], "evidence_ids": ["source"]},
            base["observations"][0],
        ]
        record = self.engine.records.create_record("mirrors", base["claim"], base["scope"], observations,
            base["evidence"], base["verification"], timestamp=STAMP, actor="reviewer", reason="Reviewed", event_id="created")
        created = await self.engine.record_create("facts", record)
        changes = {"replacements": [{"find_text": "synthetic governed", "replacement": "corrected governed"}],
                   "mirror_observations": ["selected"]}
        arguments = (created["identifier"], "revise", 1, "mirror-update", "2026-01-01T00:00:01.000000Z",
                     "reviewer", "Correct prose and selected support", changes)
        updated = await self.engine.record_transition(*arguments)
        actual = updated["record"]
        self.assertEqual(observations[0] | {"statement": actual["claim"]}, actual["observations"][0])
        self.assertEqual(observations[1:], actual["observations"][1:])
        self.assertEqual(record["events"], actual["events"][:-1])
        self.assertEqual(record["evidence"], actual["evidence"])
        self.assertEqual("needs_revalidation", actual["status"])
        saved = copy.deepcopy(self.backend.notes)
        replay = await self.engine.record_transition(*arguments)
        self.assertTrue(replay["replayed"])
        self.assertEqual(actual, replay["record"])
        self.assertEqual(saved, self.backend.notes)
        self.assertNotIn("claim", changes)

    async def test_invalid_claim_mirrors_leave_revision_and_operation_identity_available(self):
        record = source_record()
        created = await self.engine.record_create("facts", record)
        before = copy.deepcopy(self.backend.notes)
        invalid = [{"claim": "Changed", "mirror_observations": value} for value in
                   (None, [], "observed", [None], ["observed", "observed"], ["missing"], ["observed"])]
        invalid += [{"mirror_observations": ["observed"]},
                    {"claim": "Changed", "mirror_observations": ["observed"], "observations": record["observations"]}]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(KnowledgeError):
                await self.engine.record_transition(created["identifier"], "revise", 1, "correctable",
                    "2026-01-01T00:00:01.000000Z", "reviewer", "Correct support", changes)
            self.assertEqual(before, self.backend.notes)
        corrected = await self.engine.record_transition(created["identifier"], "revise", 1, "correctable",
            "2026-01-01T00:00:01.000000Z", "reviewer", "Correct support", {"claim": "Changed"})
        self.assertEqual(2, corrected["record"]["record_revision"])
        self.assertEqual(record["observations"], corrected["record"]["observations"])

    async def test_transition_explains_evidence_shape_and_binding_without_mutation(self):
        created = await self.engine.record_create("facts", source_record())
        identifier = created["identifier"]
        before = copy.deepcopy(self.backend.notes[identifier])
        anchor = source_record()["evidence"]["source"]
        for evidence, message in [
            ([anchor], "changes.evidence must be an object keyed by evidence ID"),
            ({"replacement": anchor}, "observations reference unknown evidence IDs; preserve referenced IDs or update observations with the evidence mapping"),
        ]:
            with self.subTest(evidence=evidence), self.assertRaises(KnowledgeError) as error:
                await self.engine.record_transition(identifier, "revise", 1, "invalid-evidence",
                    "2026-01-01T00:00:01.000000Z", "reviewer", "Update support", {"evidence": evidence})
            self.assertEqual(message, str(error.exception))
            self.assertEqual(before, self.backend.notes[identifier])

    async def test_governed_revise_replaces_disjoint_passages_and_preserves_history(self):
        original = source_record()
        body = "# Claim\n\n" + "Unchanged introduction.\n" * 150 + "First finding.\n\n" + "Unchanged context.\n" * 150 + "| Name | Value |\n| ---- | ----- |\n| Ada  | 8     |\n\nLast line.\n"
        record = self.engine.records.create_record(
            "selective", body, original["scope"], original["observations"],
            original["evidence"], original["verification"],
            timestamp=STAMP, actor="reviewer", reason="Source reviewed", event_id="created-selective",
        )
        created = await self.engine.record_create("facts", record)
        identifier = created["identifier"]
        changes = {"replacements": [
            {"find_text": "First finding.", "replacement": "Updated finding."},
            {"find_text": "| Ada  | 8     |", "replacement": "| Ada  | 9     |"},
        ]}
        revised = await self.engine.record_transition(
            identifier, "revise", 1, "selective-1", "2026-01-01T00:00:00.000001Z",
            "reviewer", "Source changed", changes,
        )
        expected = body.replace("First finding.", "Updated finding.").replace("| Ada  | 8     |", "| Ada  | 9     |")
        self.assertEqual(expected, revised["record"]["claim"])
        self.assertEqual(expected, self.backend.notes[identifier]["content"])
        self.assertEqual("needs_revalidation", revised["record"]["status"])
        self.assertEqual("needs_revalidation", revised["record"]["verification"]["outcome"])
        self.assertEqual(body, revised["record"]["events"][0]["snapshot"]["claim"])
        self.assertEqual(revised["record"], (await self.engine.read(identifier, mode="inspect"))["record"])
        change = revised["knowledge_change"]
        self.assertEqual("grouped_exact_replacement", change["body_change"]["kind"])
        passages = change["body_change"]["replacements"]
        self.assertEqual(["First finding.", "| Ada  | 8     |"], [p["before"]["preview"] for p in passages])
        self.assertEqual(["Updated finding.", "| Ada  | 9     |"], [p["after"]["preview"] for p in passages])
        self.assertFalse(any(p[side]["truncated"] for p in passages for side in ("before", "after")))
        self.assertEqual({"kajamite_record", "kajamite_operations"}, {item["key"] for item in change["metadata_changes"]})
        self.assertIn("Updated finding.", revised["knowledge_change_text"])
        self.assertNotIn("Unchanged introduction.", str(change["body_change"]))
        writes = len([name for name, _ in self.backend.calls if name == "edit_note"])
        replay = await self.engine.record_transition(
            identifier, "revise", 1, "selective-1", "2026-01-01T00:00:00.000001Z",
            "reviewer", "Source changed", changes,
        )
        self.assertTrue(replay["replayed"])
        self.assertEqual(writes, len([name for name, _ in self.backend.calls if name == "edit_note"]))
        with self.assertRaisesRegex(KnowledgeError, "revision conflict"):
            await self.engine.record_transition(
                identifier, "revise", 1, "selective-stale", "2026-01-01T00:00:00.000002Z",
                "reviewer", "Source changed", changes,
            )

    async def test_governed_passage_receipt_uses_canonical_persisted_text(self):
        for index, replacement in enumerate((
            {"find_text": "synthetic governed", "replacement": "revised\r\nstructured"},
            {"find_text": "A synthetic governed claim.", "replacement": "A revised claim.\r"},
        )):
            with self.subTest(index=index):
                created = await self.engine.record_create(f"case-{index}", source_record())
                revised = await self.engine.record_transition(
                    created["identifier"], "revise", 1, "canonical-edit", "2026-01-01T00:00:00.000001Z",
                    "reviewer", "Revise synthetic passage", {"replacements": [replacement]})
                passage = revised["knowledge_change"]["body_change"]["replacements"][0]
                for side, record in (("before", created["record"]), ("after", revised["record"])):
                    self.assertNotIn("\r", passage[side]["preview"])
                    self.assertIn(passage[side]["preview"], record["claim"])
                    self.assertEqual(hashlib.sha256(passage[side]["preview"].encode()).hexdigest(), passage[side]["sha256"])

    def test_receipt_word_ranges_preserve_reflowed_phrases_and_unicode(self):
        old = "Keep shared resource 💡 café. Retry after 10 seconds. Retain instance state."
        new = "# Retry policy\n\n- Keep shared resource 💡 café.\n- Retry after 20 seconds.\n- Retain instance state."
        before = {"file_path": "facts/stable-id.md", "title": "Resource retry policy", "content": old}
        after = before | {"content": new}
        variants = [receipt.for_edit(before, after, find_text=old, replacement=new, metadata_keys=set())["body_change"],
                    receipt.for_revise(before, after, [{"find_text": old, "replacement": new}])["body_change"]["replacements"][0],
                    receipt.changed_claim_passages(old, new)["replacements"][0]]
        for pair in variants:
            marked = {side: "".join(pair[side]["preview"][a:b] for a, b in pair[side]["changed_ranges"]) for side in ("before", "after")}
            self.assertEqual("10", "".join(marked["before"].split()))
            self.assertIn("20", marked["after"])
            self.assertNotIn("shared resource", marked["after"])
            self.assertNotIn("café", marked["after"])
            self.assertEqual(old, pair["before"]["preview"])
            self.assertEqual(new, pair["after"]["preview"])
        self.assertEqual("Resource retry policy", receipt.for_create(after)["after"]["title"])
        dense = receipt.changed_claim_passages("a " * 600, "b " * 600)["replacements"][0]
        self.assertNotIn("changed_ranges", dense["before"])

    async def test_complete_claim_receipt_shows_distant_changes(self):
        original = source_record()
        body = "# Claim\n" + "Stable introduction.\n" * 120 + "First finding.\n" + "Stable context.\n" * 120 + "Second finding.\n"
        record = self.engine.records.create_record(
            "complete", body, original["scope"], original["observations"],
            original["evidence"], original["verification"],
            timestamp=STAMP, actor="reviewer", reason="Source reviewed", event_id="created-complete",
        )
        created = await self.engine.record_create("facts", record)
        identifier = created["identifier"]
        updated = body.replace("First finding.", "Updated first finding.").replace("Second finding.", "Updated second finding.")
        changes = {"claim": updated}
        revised = await self.engine.record_transition(
            identifier, "revise", 1, "complete-1", "2026-01-01T00:00:00.000001Z",
            "reviewer", "Source changed", changes,
        )
        change = revised["knowledge_change"]
        self.assertEqual("edit", change["operation"])
        self.assertEqual("grouped_exact_replacement", change["body_change"]["kind"])
        passages = change["body_change"]["replacements"]
        self.assertEqual(2, len(passages))
        self.assertIn("Updated first finding.", passages[0]["after"]["preview"])
        self.assertIn("Updated second finding.", passages[1]["after"]["preview"])
        self.assertEqual(2, str(change["body_change"]).count("Stable introduction."))
        self.assertEqual({"kajamite_record", "kajamite_operations"}, {item["key"] for item in change["metadata_changes"]})
        self.assertEqual(hashlib.sha256(updated.encode()).hexdigest(), change["after"]["content_sha256"])
        self.assertIn("Updated second finding.", revised["knowledge_change_text"])
        self.assertEqual(updated, self.backend.notes[identifier]["content"])
        replay = await self.engine.record_transition(
            identifier, "revise", 1, "complete-1", "2026-01-01T00:00:00.000001Z",
            "reviewer", "Source changed", changes,
        )
        self.assertTrue(replay["replayed"])

    async def test_complete_claim_receipt_handles_long_lines_edits_and_noop(self):
        old = "Heading\n" + "a" * 2_500 + " old 🙂 " + "z" * 120 + "\nTail\n"
        new = old.replace(" old 🙂 ", " new 🚀 ")
        passage = receipt.changed_claim_passages(old, new)["replacements"][0]
        self.assertIn("old 🙂", passage["before"]["preview"])
        self.assertIn("new 🚀", passage["after"]["preview"])
        self.assertNotIn("a" * 2_000, passage["after"]["preview"])
        self.assertTrue(passage["before"]["truncated"])
        self.assertEqual(hashlib.sha256(("Heading\n" + "a" * 2_500 + " old 🙂 " + "z" * 120 + "\n").encode()).hexdigest(), passage["before"]["sha256"])

        inserted = receipt.changed_claim_passages("One\nThree\n", "One\nTwo\nThree\n")
        deleted = receipt.changed_claim_passages("One\nTwo\nThree\n", "One\nThree\n")
        self.assertIn("Two\n", inserted["replacements"][0]["after"]["preview"])
        self.assertIn("Two\n", deleted["replacements"][0]["before"]["preview"])
        broad = receipt.changed_claim_passages("a" * 3_000, "b" * 3_000)
        self.assertTrue(broad["replacements"][0]["before"]["truncated"])
        self.assertEqual(2_000, len(broad["replacements"][0]["after"]["preview"]))
        long_document = receipt.changed_claim_passages("alpha line\n" * 501, "bravo line\n" * 501)
        self.assertEqual("exact_replacement", long_document["kind"])
        self.assertTrue(long_document["before"]["truncated"])

        created = await self.engine.record_create("facts", source_record())
        unchanged = await self.engine.record_transition(
            created["identifier"], "revise", 1, "same-claim", "2026-01-01T00:00:00.000001Z",
            "reviewer", "Verification refreshed", {"claim": source_record()["claim"]},
        )
        self.assertIsNone(unchanged["knowledge_change"]["body_change"])

    async def test_governed_revise_refuses_invalid_selections_before_write(self):
        created = await self.engine.record_create("facts", source_record())
        identifier = created["identifier"]
        invalid = [
            ("missing", [{"find_text": "absent", "replacement": "other"}]),
            ("exactly once", [{"find_text": "n", "replacement": "other"}]),
            ("overlap", [{"find_text": "synthetic governed", "replacement": "first"},
                         {"find_text": "governed claim", "replacement": "second"}]),
        ]
        for index, (message, replacements) in enumerate(invalid):
            with self.subTest(message=message), self.assertRaisesRegex(KnowledgeError, message):
                await self.engine.record_transition(
                    identifier, "revise", 1, f"invalid-{index}", "2026-01-01T00:00:00.000001Z",
                    "reviewer", "Invalid selection", {"replacements": replacements},
                )
        with self.assertRaisesRegex(KnowledgeError, "cannot be supplied together"):
            await self.engine.record_transition(
                identifier, "revise", 1, "invalid-mixed", "2026-01-01T00:00:00.000001Z",
                "reviewer", "Invalid selection", {"claim": "Other", "replacements": invalid[0][1]},
            )
        self.assertFalse(any(name == "edit_note" for name, _ in self.backend.calls))

    async def test_governed_revise_accepts_explicit_fresh_verification(self):
        created = await self.engine.record_create("facts", source_record())
        verification = {**source_record()["verification"], "record_revision": 2,
                        "verified_at": "2026-01-01T00:00:00.000001Z"}
        revised = await self.engine.record_transition(
            created["identifier"], "revise", 1, "verified-selective",
            "2026-01-01T00:00:00.000001Z", "reviewer", "Source verified",
            {"replacements": [{"find_text": "synthetic", "replacement": "verified"}],
             "verification": verification},
        )
        self.assertEqual("supported", revised["record"]["status"])
        self.assertEqual("A verified governed claim.", revised["record"]["claim"].strip())

    async def test_generic_mutation_and_namespace_move_cannot_bypass_lifecycle(self):
        created = await self.engine.record_create("facts", source_record())
        identifier = created["identifier"]
        with self.assertRaisesRegex(KnowledgeError, "lifecycle"):
            await self.engine.edit(identifier, "synthetic", "other")
        with self.assertRaisesRegex(KnowledgeError, "lifecycle"):
            await self.engine.move(identifier, "archive/synthetic-fact.md")
        with self.assertRaisesRegex(KnowledgeError, "containing governed"):
            await self.engine.move("facts", "archive/facts", is_namespace=True)

    async def test_authorization_precedes_read_and_search_withholds_governed_snippets(self):
        denied = KnowledgeEngine(self.backend, authorize=lambda identifier, scope: False)
        with self.assertRaisesRegex(KnowledgeError, "authorization"):
            await denied.read("unknown.md", request_scope={"purpose": "reuse"})
        self.assertEqual([], self.backend.calls)

        created = await self.engine.record_create("facts", source_record())
        result = await self.engine.search(["facts"], "synthetic")
        self.assertEqual([], result["results"])
        self.assertEqual(created["identifier"], result["excluded"][0]["identifier"])
        self.assertEqual("unknown_scope", result["excluded"][0]["reason"])

    async def test_sparse_native_metadata_cannot_bypass_current_record_guards(self):
        created = await self.engine.record_create("facts", source_record())
        row = copy.deepcopy(self.backend.notes[created["identifier"]])
        row["frontmatter"] = {"note_type": "governed-record"}
        row["content"] = "stale private snippet"
        self.backend.search_rows = [row]
        result = await self.engine.search(["facts"], request_scope={"system": "example"})
        self.assertEqual([], result["results"])
        self.assertNotIn("stale private snippet", str(result))
        self.assertEqual("source_check_unknown", result["excluded"][0]["reason"])

    async def test_two_writers_cannot_both_commit_the_same_expected_revision(self):
        created = await self.engine.record_create("facts", source_record())
        async def retract(operation):
            return await self.engine.record_transition(created["identifier"], "retract", 1, operation,
                "2026-01-01T00:00:00.000001Z", "reviewer", "Withdraw")
        results = await asyncio.gather(retract("one"), retract("two"), return_exceptions=True)
        self.assertEqual(1, sum(isinstance(item, dict) for item in results))
        self.assertEqual(1, sum(isinstance(item, KnowledgeError) for item in results))

    async def test_committed_transport_failure_and_altered_create_are_uncertain(self):
        original_call = self.backend.call
        async def committed_then_failed(name, arguments):
            result = await original_call(name, arguments)
            if name == "write_note":
                raise BackendError("connection interrupted after commit")
            return result
        self.backend.call = committed_then_failed
        with self.assertRaises(MutationUncertain):
            await self.engine.record_create("facts", source_record())
        self.assertIn("facts/synthetic-fact.md", self.backend.notes)
        async def altered(name, arguments):
            if name == "write_note":
                arguments = {**arguments, "content": "different body"}
            return await original_call(name, arguments)
        self.backend.call = altered
        with self.assertRaises(MutationUncertain):
            await self.engine.create("Altered", "expected body", "notes")

    async def test_invalid_embedded_record_is_withheld_and_uncertain_write_is_explicit(self):
        created = await self.engine.record_create("facts", source_record())
        identifier = created["identifier"]
        forged = copy.deepcopy(self.backend.notes[identifier])
        forged["frontmatter"]["kajamite_record"]["claim"] = "Forged claim"
        self.backend.notes[identifier] = forged
        with self.assertRaisesRegex(KnowledgeError, "metadata is invalid|does not match"):
            await self.engine.read(identifier, mode="inspect")

        self.backend.notes[identifier]["frontmatter"]["kajamite_record"] = source_record()
        original_call = self.backend.call
        async def fail_edit(name, arguments):
            if name == "edit_note":
                raise BackendError("connection interrupted")
            return await original_call(name, arguments)
        self.backend.call = fail_edit
        with self.assertRaisesRegex(MutationUncertain, "uncertain"):
            await self.engine.record_transition(
                identifier, "retract", 1, "retract-1", "2026-01-01T00:00:00.000001Z",
                "reviewer", "Retract",
            )


if __name__ == "__main__":
    unittest.main()
