import unittest
from unittest.mock import Mock, patch

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
