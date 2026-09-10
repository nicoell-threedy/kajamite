"""Synthetic acceptance coverage for persistent governed record operations."""
import asyncio
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from kajamite.engine import KnowledgeEngine
from kajamite.errors import BackendError, MutationUncertain
from kajamite.governance import RecordEngine
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

    async def test_evidence_health_noop_is_explicit_without_a_write(self):
        created = await self.engine.record_create("facts", source_record())
        calls = len(self.backend.calls)
        unchanged = await self.engine.record_transition(
            created["identifier"], "evidence_health", 1, "health-1",
            "2026-01-01T00:00:00.000001Z", "reviewer", "Source unavailable",
            {"outcome": "inaccessible", "condition_id": "source-check"},
        )
        self.assertFalse(unchanged["mutated"])
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

    async def test_transition_is_atomic_idempotent_and_detects_conflicts(self):
        created = await self.engine.record_create("facts", source_record())
        identifier = created["identifier"]
        updated = await self.engine.record_transition(
            identifier, "revise", 1, "revise-1", "2026-01-01T00:00:00.000001Z",
            "reviewer", "Clarified", {"claim": "Revised synthetic claim.\n"},
        )
        self.assertEqual(2, updated["committed_revision"])
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
