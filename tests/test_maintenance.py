"""Synthetic coverage for bounded governed-record maintenance and removal."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from kajamite.engine import KnowledgeEngine
from kajamite.errors import BackendError
from kajamite.governance import RecordEngine
from kajamite.maintenance import MaintenanceOperations
from test_service import FakeBackend


STAMP = "2026-01-01T00:00:00.000000Z"


def record(identifier, depends_on=None):
    return RecordEngine().create_record(
        identifier, f"Synthetic claim for {identifier}.", {"system": "example"},
        [{"observation_id": "observed", "statement": "Synthetic observation.", "evidence_ids": ["source"]}],
        {"source": {"kind": "document", "reference": "example:manual@1", "observed_at": STAMP}},
        {"record_revision": 1, "verified_at": STAMP, "verifier": "reviewer",
         "outcome": "supported", "evidence_ids": ["source"]},
        depends_on=depends_on or [], timestamp=STAMP, actor="reviewer", reason="Evidence reviewed",
        event_id=f"create-{identifier}",
    )


class MaintenanceBackend(FakeBackend):
    def __init__(self):
        super().__init__()
        self.stale_projection = None
        self.projection_error = False

    async def call(self, name, arguments):
        if name == "delete_note":
            note = self._lookup(arguments["identifier"])
            del self.notes[note["file_path"]]
            return {"deleted": True, "file_path": note["file_path"]}
        if name == "search_notes" and self.projection_error:
            raise BackendError("projection unavailable")
        if name == "search_notes" and self.stale_projection is not None:
            return {"results": [copy.deepcopy(self.stale_projection)], "has_more": False}
        return await super().call(name, arguments)


MaintenanceEngine = KnowledgeEngine


class MaintenanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend = MaintenanceBackend()
        self.engine = MaintenanceEngine(self.backend)

    async def test_maintenance_marks_transitive_supported_dependents_and_replays_safely(self):
        await self.engine.record_create("facts", record("target"))
        dependent = await self.engine.record_create("facts", record("dependent", ["target"]))
        await self.engine.record_transition(
            "facts/target.md", "retract", 1, "retract-target", "2026-01-01T00:00:00.000001Z",
            "reviewer", "Target removed",
        )
        result = await self.engine.record_maintain(
            "facts", "dependency-scan", "2026-01-01T00:00:00.000002Z", "reviewer", "Dependency stale",
        )
        self.assertEqual(["dependent"], [item["record_id"] for item in result["completed"]])
        self.assertFalse(result["partial"])
        current = await self.engine.read(dependent["identifier"], mode="inspect")
        self.assertEqual("needs_revalidation", current["record"]["status"])
        replay = await self.engine.record_maintain(
            "facts", "dependency-scan", "2026-01-01T00:00:00.000002Z", "reviewer", "Dependency stale",
        )
        self.assertEqual([], replay["completed"])
        self.assertFalse(replay["partial"])

    async def test_maintenance_reports_duplicate_ids_without_guessing_a_target(self):
        first = await self.engine.record_create("facts/a", record("duplicate"))
        second = await self.engine.record_create("facts/b", record("duplicate"))
        result = await self.engine.record_maintain("facts", "dependency-scan", STAMP, "reviewer", "Check")
        self.assertTrue(result["partial"])
        self.assertEqual([], result["completed"])
        self.assertEqual("ambiguous record ID in namespace", result["errors"][0]["error"])
        self.assertNotEqual(first["identifier"], second["identifier"])

    async def test_supported_dependency_revision_change_is_withheld_before_maintenance(self):
        await self.engine.record_create("facts", record("target"))
        dependent = await self.engine.record_create("facts", record("dependent", ["target"]))
        engine = KnowledgeEngine(self.backend, evidence_checker=lambda record, scope: True)
        scope = {"system": "example"}
        self.assertIn("content", await engine.read(dependent["identifier"], request_scope=scope))
        verification = {**record("target")["verification"], "record_revision": 2,
                        "verified_at": "2026-01-01T00:00:00.000001Z"}
        await engine.record_transition("facts/target.md", "revise", 1, "revision-2",
                                       "2026-01-01T00:00:00.000001Z", "reviewer", "Reviewed change",
                                       {"claim": "Updated target.", "verification": verification})
        self.assertEqual("dependency_changed", (await engine.read(dependent["identifier"], request_scope=scope))["reason"])
        result = await engine.record_maintain("facts", "target-revision-2",
                                             "2026-01-01T00:00:00.000002Z", "reviewer", "Dependency changed")
        self.assertEqual(["dependent"], [item["record_id"] for item in result["completed"]])

    async def test_removal_projection_error_does_not_erase_committed_result(self):
        created = await self.engine.record_create("facts", record("remove-me"))
        self.backend.projection_error = True
        result = await self.engine.record_remove(created["identifier"], 1)
        self.assertEqual("unknown", result["projection"])
        self.assertTrue(result["mutation"]["deleted"])
        self.assertTrue(result["partial"])

    async def test_duplicate_descendant_identity_withholds_existing_dependent(self):
        await self.engine.record_create("facts/a", record("target"))
        dependent = await self.engine.record_create("facts", record("dependent", ["target"]))
        await self.engine.record_create("facts/b", record("target"))
        engine = KnowledgeEngine(self.backend, evidence_checker=lambda record, scope: True)
        result = await engine.read(dependent["identifier"], request_scope={"system": "example"})
        self.assertTrue(result["withheld"])
        self.assertEqual("dependency_ambiguous", result["reason"])

    async def test_remove_reports_backend_confirmation_and_bounded_projection_state(self):
        created = await self.engine.record_create("facts", record("remove-me"))
        self.backend.stale_projection = copy.deepcopy(self.backend.notes[created["identifier"]])
        removed = await self.engine.record_remove(created["identifier"], 1)
        self.assertEqual("pending", removed["projection"])
        self.assertTrue(removed["partial"])
        receipt = removed["knowledge_change"]
        self.assertEqual("remove_note", receipt["operation"])
        self.assertEqual("backend_confirmed", receipt["verification"])
        self.assertFalse(receipt["readback_verified"])


if __name__ == "__main__":
    unittest.main()
