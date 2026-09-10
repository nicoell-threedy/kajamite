"""Publication checks use synthetic fixtures and never print matched values."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publication', ROOT / 'tools/check_publication.py')
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


class PublicationTests(unittest.TestCase):
    def test_private_identifier_case_and_separators(self):
        fingerprint = hashlib.sha256(b'syntheticprivate').hexdigest()
        self.assertEqual(publication.reasons(b'SYNTHETICPRIVATE_core', {fingerprint}), ['private identifier'])
        self.assertEqual(publication.reasons(b'normal public example', {fingerprint}), [])

    def test_values_are_not_returned(self):
        data = b'ghp_' + b'A' * 30
        self.assertEqual(publication.reasons(data), ['credential token'])

    def test_repository_snapshot_and_available_history(self):
        # Source archives have no Git history. CI checkouts and developer clones do.
        if not (ROOT / '.git').exists():
            self.skipTest('source archive')
        original = publication.git
        publication.git = lambda *args: subprocess.check_output(['git', '-C', str(ROOT), *args])
        try:
            self.assertEqual(publication.check(), [])
            self.assertEqual(publication.check(staged=True), [])
        finally:
            publication.git = original

    def test_deleted_content_in_history_and_staged_content(self):
        with tempfile.TemporaryDirectory() as folder:
            def git(*args):
                return subprocess.check_output(['git', '-C', folder, *args], stderr=subprocess.DEVNULL)
            git('init')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.com')
            target = Path(folder) / 'sample.txt'
            target.write_bytes(b'ghp_' + b'A' * 30)
            git('add', '.')
            original = publication.git
            publication.git = git
            try:
                self.assertTrue(publication.check(staged=True))
                git('commit', '-m', 'Synthetic fixture')
                target.write_text('Public example\n')
                git('add', '.')
                git('commit', '-m', 'Replace fixture')
                self.assertEqual(publication.check(staged=True), [])
                self.assertTrue(publication.check())
            finally:
                publication.git = original
