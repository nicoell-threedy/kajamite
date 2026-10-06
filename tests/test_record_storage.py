"""Synthetic checks for lossless governed-record journal metadata."""

import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from kajamite.engine import KnowledgeEngine
from kajamite.governance import RecordEngine, RecordError
from kajamite.record_storage import decode_record, encode_record
from kajamite.service import KnowledgeError
from test_engine import source_record
from test_service import FakeBackend


def stamp(microsecond):
    return f"2026-01-01T00:00:00.{microsecond:06d}Z"


class RecordStorageTests(unittest.TestCase):
    def setUp(self):
        self.engine = RecordEngine()

    def test_multirevision_roundtrip_and_size(self):
        record = source_record()
        record["observations"][0]["statement"] = record["claim"]
        record["events"][0]["snapshot"]["observations"][0]["statement"] = record["claim"]
        record = self.engine.validate_record(record)
        record = self.engine.revise(
            record, claim="\nRevised synthetic claim.\n\n",
            observations=[{"observation_id": "observed", "statement": "\nRevised synthetic claim.\n\n",
                           "evidence_ids": ["source"]}],
            timestamp=stamp(1), actor="reviewer", reason="New source reading", event_id="revised")
        record = self.engine.dispute(record, timestamp=stamp(2), actor="reviewer",
                                     reason="Conflicting reading", event_id="disputed")
        record = self.engine.revalidate(
            record, {**record["verification"], "record_revision": 4,
                     "verified_at": stamp(3), "outcome": "supported"},
            timestamp=stamp(3), actor="reviewer", reason="Conflict resolved", event_id="revalidated")
        stored = encode_record(record, record["claim"], self.engine)
        self.assertEqual(record, decode_record(stored, record["claim"], self.engine))
        self.assertEqual(record, decode_record(stored, "\n" + record["claim"] + "\n", self.engine))
        self.assertEqual(record, decode_record(record, record["claim"], self.engine))
        self.assertEqual({"from_body": True}, stored["events"][1]["changes"]["claim"])
        self.assertEqual({"from_claim": True}, stored["events"][0]["changes"]["observations"][0]["statement"])
        before = len(json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        after = len(json.dumps(stored, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        self.assertLess(after, before)

    def test_body_and_journal_tampering_is_rejected(self):
        record = source_record()
        stored = encode_record(record, record["claim"], self.engine)
        with self.assertRaisesRegex(RecordError, "body hash"):
            decode_record(stored, record["claim"] + "changed", self.engine)
        bad_values = []
        bad = copy.deepcopy(stored)
        bad["format"] = "journal-v2"
        bad_values.append(bad)
        bad = copy.deepcopy(stored)
        bad["extra"] = True
        bad_values.append(bad)
        bad = copy.deepcopy(stored)
        bad["events"] = []
        bad_values.append(bad)
        bad = copy.deepcopy(stored)
        del bad["events"][0]["changes"]["evidence"]
        bad_values.append(bad)
        bad = copy.deepcopy(stored)
        bad["events"][0]["changes"]["claim"] = {"from_body": 1}
        bad_values.append(bad)
        bad = copy.deepcopy(stored)
        bad["events"][0]["changes"]["observations"][0]["statement"] = {"from_claim": True, "other": 1}
        bad_values.append(bad)
        for bad in bad_values:
            with self.subTest(bad=bad), self.assertRaises(RecordError):
                decode_record(bad, record["claim"], self.engine)


class RecordStorageIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_revise_read_replay_and_legacy_upgrade(self):
        backend = FakeBackend()
        engine = KnowledgeEngine(backend)
        initial = source_record()
        created = await engine.record_create("facts", initial)
        identifier = created["identifier"]
        raw = backend.notes[identifier]["frontmatter"]["kajamite_record"]
        self.assertEqual("journal-v1", raw["format"])
        self.assertEqual({}, backend.notes[identifier]["frontmatter"]["kajamite_operations"])
        backend.notes[identifier]["frontmatter"]["kajamite_record"] = copy.deepcopy(initial)
        self.assertEqual(initial, (await engine.read(identifier, mode="inspect"))["record"])
        revised = await engine.record_transition(identifier, "revise", 1, "revise-1", stamp(1),
                                                 "reviewer", "Clarify", {"claim": "\nNew claim.\n\n"})
        self.assertEqual("journal-v1", backend.notes[identifier]["frontmatter"]["kajamite_record"]["format"])
        self.assertEqual(revised["record"], (await engine.read(identifier, mode="inspect"))["record"])
        replay = await engine.record_transition(identifier, "revise", 1, "revise-1", stamp(1),
                                                "reviewer", "Clarify", {"claim": "\nNew claim.\n\n"})
        self.assertTrue(replay["replayed"])
        self.assertEqual(revised["record"], replay["record"])
        backend.notes[identifier]["content"] += "external edit"
        with self.assertRaisesRegex(KnowledgeError, "metadata is invalid"):
            await engine.read(identifier, mode="inspect")


if __name__ == "__main__":
    unittest.main()
