import asyncio
import json
import multiprocessing
from pathlib import Path
import tempfile
import time
import unittest

from mcp.types import CallToolResult, TextContent

from kajamite.backend import Backend, BackendError, file_lock, unpack
from kajamite.config import Settings


def _hold_lock(path, ready, seconds):
    async def hold():
        async with file_lock(Path(path)):
            ready.set()
            await asyncio.sleep(seconds)

    asyncio.run(hold())


class RecordingSession:
    def __init__(self, result=None, error=None):
        self.result = result or CallToolResult(content=[], structuredContent={"result": {"ok": True}})
        self.error = error
        self.calls = []

    async def call_tool(self, name, arguments, read_timeout_seconds=None):
        self.calls.append((name, arguments, read_timeout_seconds))
        if self.error:
            raise self.error
        return self.result


class UnpackTests(unittest.TestCase):
    def test_unwraps_structured_and_text_json(self):
        wrapped = CallToolResult(content=[], structuredContent={"result": {"value": 3}})
        self.assertEqual({"value": 3}, unpack(wrapped))

        text = CallToolResult(content=[TextContent(text='{"value": 4}')])
        self.assertEqual({"value": 4}, unpack(text))

    def test_rejects_tool_errors_and_malformed_results(self):
        cases = [
            CallToolResult(content=[TextContent(text='{"ok": true}')], isError=True),
            CallToolResult(content=[TextContent(text="not json")]),
            CallToolResult(content=[], structuredContent={"result": {"error": "bad"}}),
            CallToolResult(content=[], structuredContent={"status": "error"}),
        ]
        for result in cases:
            with self.subTest(result=result), self.assertRaises(BackendError):
                unpack(result)


class BackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_call_injects_backend_scope_and_numeric_timeout(self):
        session = RecordingSession()
        settings = Settings("bm", ["mcp"], "shared", "uuid-1", timeout=2.5)
        result = await Backend(session, settings).call(
            "search_notes", {"query": "needle", "project": "wrong", "output_format": "text"}
        )
        self.assertEqual({"ok": True}, result)
        name, arguments, timeout = session.calls[0]
        self.assertEqual("search_notes", name)
        self.assertEqual("shared", arguments["project"])
        self.assertEqual("uuid-1", arguments["project_id"])
        self.assertEqual("json", arguments["output_format"])
        self.assertIsInstance(timeout, (int, float))
        self.assertEqual(2.5, timeout)

    async def test_semantic_search_requires_explicit_consumer_configuration(self):
        session = RecordingSession()
        backend = Backend(session, Settings("bm", [], "shared"))
        with self.assertRaisesRegex(BackendError, "explicit"):
            await backend.call("search_notes", {"query": "example", "search_type": "semantic"})
        self.assertEqual([], session.calls)
        enabled = Backend(session, Settings("bm", [], "shared", semantic_search=True))
        await enabled.call("search_notes", {"query": "example", "search_type": "hybrid"})
        self.assertEqual("hybrid", session.calls[-1][1]["search_type"])

    async def test_telemetry_is_optional_content_free_and_nonblocking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            telemetry = root / "metrics.jsonl"
            backend = Backend(
                RecordingSession(), Settings("bm", [], "shared", telemetry_file=telemetry)
            )
            await backend.call("search_notes", {"query": "private test phrase"})
            metric = json.loads(telemetry.read_text(encoding="utf-8"))
            self.assertEqual({"operation", "outcome", "duration_ms"}, set(metric))
            self.assertNotIn("private test phrase", telemetry.read_text(encoding="utf-8"))

            blocker = root / "file"
            blocker.write_text("x", encoding="utf-8")
            broken_path = blocker / "metrics.jsonl"
            failing = Backend(
                RecordingSession(), Settings("bm", [], "shared", telemetry_file=broken_path)
            )
            self.assertEqual({"ok": True}, await failing.call("read_note", {"identifier": "x"}))

            disabled = Backend(RecordingSession(), Settings("bm", [], "shared"))
            self.assertEqual({"ok": True}, await disabled.call("read_note", {}))

    async def test_transport_failure_is_honest_about_mutation_uncertainty(self):
        backend = Backend(RecordingSession(error=TimeoutError()), Settings("bm", [], "shared"))
        with self.assertRaisesRegex(BackendError, "may have committed"):
            await backend.call("write_note", {"title": "x"})
        with self.assertRaisesRegex(BackendError, "No result"):
            await backend.call("search_notes", {"query": "x"})


class ConfigurationAndLockTests(unittest.IsolatedAsyncioTestCase):
    async def test_config_validates_args_and_resolves_shared_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = root / "valid.toml"
            valid.write_text(
                'state_dir="state"\n[backend]\ncommand="bm"\nargs=["mcp"]\n'
                'project="shared"\n',
                encoding="utf-8",
            )
            first = Settings.load(valid)
            second = Settings.load(valid)
            self.assertEqual((root / "state" / "mutation.lock").resolve(), first.lock_path())
            self.assertEqual(first.lock_path(), second.lock_path())

            invalid = root / "invalid.toml"
            invalid.write_text(
                '[backend]\ncommand="bm"\nargs="mcp"\nproject="shared"\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "list of strings"):
                Settings.load(invalid)

    async def test_file_lock_serializes_processes_times_out_and_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutation.lock"
            context = multiprocessing.get_context("spawn")
            ready = context.Event()
            process = context.Process(target=_hold_lock, args=(str(path), ready, 0.5))
            process.start()
            try:
                self.assertTrue(await asyncio.to_thread(ready.wait, 5))
                with self.assertRaisesRegex(BackendError, "still running"):
                    async with file_lock(path, timeout=0.1):
                        self.fail("a second process acquired the held lock")

                waiter = asyncio.create_task(self._wait_forever(path))
                await asyncio.sleep(0.05)
                waiter.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await waiter
            finally:
                await asyncio.to_thread(process.join, 5)
                if process.is_alive():
                    process.terminate()
                    process.join()
            self.assertEqual(0, process.exitcode)
            async with file_lock(path, timeout=0.2):
                self.assertTrue(path.exists())

    @staticmethod
    async def _wait_forever(path):
        async with file_lock(path, timeout=5):
            return


if __name__ == "__main__":
    unittest.main()
