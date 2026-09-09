import unittest
from unittest.mock import AsyncMock, Mock, patch

import commission


class CleanupTests(unittest.TestCase):
    def test_windows_cleanup_waits_for_transient_handles_but_preserves_failures(self):
        temporary = Mock()
        temporary.cleanup.side_effect = [PermissionError("open handle"), None]
        with patch.object(commission.os, "name", "nt"), patch.object(commission.time, "sleep") as sleep:
            commission.cleanup(temporary)
        self.assertEqual(temporary.cleanup.call_count, 2)
        sleep.assert_called_once_with(0.25)

        temporary.cleanup.side_effect = PermissionError("persistent failure")
        temporary.cleanup.reset_mock()
        with patch.object(commission.os, "name", "nt"), patch.object(commission.time, "sleep"):
            with self.assertRaisesRegex(PermissionError, "persistent failure"):
                commission.cleanup(temporary)
        self.assertEqual(temporary.cleanup.call_count, 20)


class IndexReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_for_the_expected_native_search_path(self):
        backend = Mock()
        backend.call = AsyncMock(side_effect=[
            {"results": []},
            {"results": [{"file_path": "Late/Target.md"}]},
        ])
        sleep = AsyncMock()
        with patch.object(commission.asyncio, "sleep", sleep):
            await commission.wait_for_indexed_path(
                backend, "quasartargetready", "Late/Target.md", attempts=2
            )
        self.assertEqual(backend.call.await_count, 2)
        sleep.assert_awaited_once_with(0.25)

    async def test_fails_after_a_bounded_number_of_attempts(self):
        backend = Mock()
        backend.call = AsyncMock(return_value={"results": []})
        with patch.object(commission.asyncio, "sleep", AsyncMock()):
            with self.assertRaisesRegex(AssertionError, "did not expose"):
                await commission.wait_for_indexed_path(
                    backend, "quasartargetready", "Late/Target.md", attempts=2
                )
        self.assertEqual(backend.call.await_count, 2)
