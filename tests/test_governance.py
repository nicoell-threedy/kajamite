"""Independent, synthetic acceptance for the embeddable record engine."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from kajamite.governance import RecordEngine, RecordError


STAMP = "2026-01-01T00:00:00.000000Z"


def record(engine, identifier="claim"):
    return engine.create_record(
        identifier, "Synthetic claim.", {"system": "example"},
        [{"observation_id": "observed", "statement": "Synthetic observation.",
          "evidence_ids": ["source"]}],
        {"source": {"kind": "document", "reference": "example:manual@1", "observed_at": STAMP}},
        {"record_revision": 1, "verified_at": STAMP, "verifier": "reviewer",
         "outcome": "supported", "evidence_ids": ["source"]},
        timestamp=STAMP, actor="reviewer", reason="Evidence reviewed", event_id="created",
    )


def event(number):
    return {"timestamp": f"2026-01-01T00:00:00.{number:06d}Z",
            "actor": "reviewer", "reason": "Synthetic review", "event_id": f"event-{number}"}


class GovernanceTests(unittest.TestCase):
    def test_lifecycle_preserves_history_and_requires_new_verification(self):
        engine = RecordEngine()
        original = record(engine)
        disputed = engine.dispute(original, **event(1))
        verified = engine.revalidate(disputed, {
            **disputed["verification"], "record_revision": 3,
            "verified_at": event(2)["timestamp"], "outcome": "supported",
        }, **event(2))
        revised = engine.revise(verified, claim="Changed claim.", **event(3))
        self.assertEqual(revised["status"], "needs_revalidation")
        self.assertEqual(revised["events"][:3], verified["events"])
        self.assertEqual(original["status"], "supported")
        self.assertEqual(engine.parse_record(engine.serialize_record(revised)), revised)
        retracted = engine.retract(revised, **event(4))
        with self.assertRaises(RecordError):
            engine.revise(retracted, claim="Cannot revive.", **event(5))
        successor = record(engine, "replacement")
        self.assertEqual(engine.supersede(original, successor, **event(1))["superseded_by"], "replacement")
        with self.assertRaises(RecordError):
            engine.revalidate(disputed, disputed["verification"], **event(2))

    def test_claim_markdown_round_trips_with_canonical_line_endings_and_boundaries(self):
        engine = RecordEngine()
        claim = "\r\n# Synthetic claim\r\n\r\nA paragraph.\r\n\r\n"
        created = engine.create_record(
            "bounded-claim", claim, {"system": "example"},
            [{"observation_id": "observed", "statement": "Synthetic observation.",
              "evidence_ids": ["source"]}],
            {"source": {"kind": "document", "reference": "example:manual@1", "observed_at": STAMP}},
            {"record_revision": 1, "verified_at": STAMP, "verifier": "reviewer",
             "outcome": "supported", "evidence_ids": ["source"]},
            timestamp=STAMP, actor="reviewer", reason="Evidence reviewed", event_id="created-boundary",
        )
        self.assertEqual(created["claim"], "\n# Synthetic claim\n\nA paragraph.\n\n")
        markdown = engine.serialize_record(created)
        self.assertTrue(markdown.endswith(created["claim"]))
        self.assertEqual(engine.parse_record(markdown.replace("\n", "\r\n")), created)
        revised = engine.revise(created, claim="\r\nRevised claim.\r\n\r\n", **event(1))
        self.assertEqual(engine.parse_record(engine.serialize_record(revised)), revised)

    def test_imported_semantic_history_rejects_stale_verification(self):
        engine = RecordEngine()
        disputed = engine.dispute(record(engine), **event(1))
        revalidated = engine.revalidate(disputed, {
            **disputed["verification"], "record_revision": 3,
            "verified_at": event(2)["timestamp"], "outcome": "supported",
        }, **event(2))
        forged = copy.deepcopy(revalidated)
        stale = forged["events"][1]["snapshot"]["verification"]["verified_at"]
        forged["events"][2]["snapshot"]["verification"]["verified_at"] = stale
        forged["verification"]["verified_at"] = stale
        with self.assertRaisesRegex(RecordError, "newer than the prior semantic verification"):
            engine.validate_record(forged)

    def test_changed_evidence_is_distinct_from_inaccessible_evidence(self):
        engine = RecordEngine()
        original = record(engine)
        options = {"condition_id": "source-change", **{k: v for k, v in event(1).items() if k != "event_id"}}
        unavailable = engine.apply_evidence_health(original, "inaccessible", **options)
        self.assertTrue(unavailable["transient"])
        self.assertFalse(unavailable["mutated"])
        changed = engine.apply_evidence_health(original, "changed", **options)
        self.assertTrue(changed["mutated"])
        self.assertEqual(changed["record"]["claim"], original["claim"])
        self.assertEqual(changed["record"]["status"], "needs_revalidation")
        self.assertEqual(changed["record"]["verification"]["verified_at"], STAMP)
        self.assertFalse(engine.apply_evidence_health(changed["record"], "changed", **options)["mutated"])

    def test_consumer_validation_applies_to_current_and_historical_evidence(self):
        seen = []
        def validate(evidence):
            seen.append(evidence)
            if any(not anchor.get("reference", "").startswith("example:") for anchor in evidence.values()):
                raise RecordError("Unrecognized source reference")
            evidence.clear()  # The callback cannot rewrite the engine's record.
        engine = RecordEngine(evidence_validator=validate)
        original = record(engine)
        self.assertTrue(original["evidence"])
        self.assertGreaterEqual(len(seen), 2)
        forged = copy.deepcopy(original)
        forged["events"][0]["snapshot"]["evidence"]["source"]["reference"] = "untrusted:source"
        with self.assertRaises(RecordError):
            engine.validate_record(forged)
        later = copy.deepcopy(original)
        later["evidence"]["source"]["observed_at"] = event(1)["timestamp"]
        with self.assertRaises(RecordError):
            engine.validate_record(later)

    def test_independent_configurations_do_not_change_each_others_format(self):
        first = RecordEngine()
        second = RecordEngine(record_type="reviewed-fact", permalink_prefix="research/facts")
        a, b = record(first), record(second)
        self.assertIn('"permalink": "records/claim"', first.serialize_record(a))
        self.assertIn('"permalink": "research/facts/claim"', second.serialize_record(b))
        with self.assertRaises(RecordError):
            first.parse_record(second.serialize_record(b))
        self.assertEqual(first.compute_etag(a), first.compute_etag(first.serialize_record(a)))
        malformed = first.serialize_record(a).replace('"records/claim"', '"records/other"')
        with self.assertRaises(RecordError):
            first.parse_record(malformed)
        with self.assertRaises(RecordError):
            RecordEngine(permalink_prefix="../records")

    def test_summary_contains_only_bounded_operation_facts(self):
        engine = RecordEngine()
        value = engine.dispute(record(engine), **event(1))
        summary = engine.change_summary(value)
        self.assertEqual(summary, {"action": "dispute", "prior_status": "supported",
                                  "status": "disputed", "record_revision": 2,
                                  "evidence_count": 1, "dependency_count": 0})
        encoded = json.dumps(summary)
        for private_value in (value["claim"], value["record_id"], "example:manual", "reviewer"):
            self.assertNotIn(private_value, encoded)

    def test_engine_import_needs_only_the_standard_library(self):
        source = str(Path(__file__).resolve().parents[1] / "src")
        program = ("import sys; sys.path.insert(0, sys.argv[1]); "
                   "from kajamite.governance import RecordEngine; RecordEngine(); "
                   "assert not any(n.split('.')[0] in {'mcp', 'yaml', 'opentelemetry'} for n in sys.modules)")
        subprocess.run([sys.executable, "-I", "-S", "-c", program, source], check=True)
        command = "import sys; sys.path.insert(0, sys.argv[1]); import kajamite.__main__"
        result = subprocess.run([sys.executable, "-I", "-S", "-c", command, source],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
