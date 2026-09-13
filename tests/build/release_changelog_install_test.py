#!/usr/bin/env python3
"""Real native install, sync ordering and hard process-exit boundaries."""
import errno
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.release import install_changelog_page as installer


class InstallTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'stage').mkdir()
        (self.root / 'pages').mkdir()
        self.source = self.root / 'stage/page'
        self.target = self.root / 'pages/1.0.1.0.mdx'
        self.content = b'complete frozen page\n'
        self.source.write_bytes(self.content)
        self.digest = hashlib.sha256(self.content).hexdigest()

    def run_install(self):
        installer.install(self.source, self.target, self.digest)

    def test_real_install_and_exclusive_refusal_preserve_bytes(self):
        self.run_install()
        self.assertEqual(self.target.read_bytes(), self.content)
        self.assertEqual(self.target.stat().st_nlink, 1)
        self.assertFalse(self.source.exists())
        self.source.write_bytes(self.content)
        with self.assertRaises(FileExistsError):
            self.run_install()
        self.assertEqual(self.target.read_bytes(), self.content)
        self.assertEqual(self.source.read_bytes(), self.content)

    def test_digest_failure_occurs_before_install(self):
        self.source.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            self.run_install()
        self.assertFalse(self.target.exists())

    def test_unsupported_exclusive_rename_never_falls_back_to_copy(self):
        with patch.object(installer, '_rename_exclusive', side_effect=OSError(errno.EXDEV, 'fixture device boundary')):
            with self.assertRaises(OSError):
                self.run_install()
        self.assertEqual(self.source.read_bytes(), self.content)
        self.assertFalse(self.target.exists())

    def test_real_fsync_order_surrounds_native_rename(self):
        events = []
        original_sync, original_rename = os.fsync, installer._rename_exclusive
        def synced(fd):
            events.append(('sync', os.fstat(fd).st_ino))
            original_sync(fd)
        def renamed(*args):
            events.append(('rename',))
            original_rename(*args)
        expected = [('sync', self.source.stat().st_ino),
                    ('sync', self.source.parent.stat().st_ino), ('rename',),
                    ('sync', self.target.parent.stat().st_ino),
                    ('sync', self.source.parent.stat().st_ino)]
        with patch.object(installer.os, 'fsync', side_effect=synced), patch.object(installer, '_rename_exclusive', side_effect=renamed):
            self.run_install()
        self.assertEqual(events, expected)

    def _crash(self, after):
        child = os.fork()
        if child == 0:
            original = installer._rename_exclusive
            def stopped(*args):
                if after:
                    original(*args)
                os._exit(73)
            installer._rename_exclusive = stopped
            self.run_install()
            os._exit(74)
        _, result = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(result), 73)
        if after:
            self.assertFalse(self.source.exists())
            self.assertEqual(self.target.read_bytes(), self.content)
            self.assertEqual(self.target.stat().st_nlink, 1)
        else:
            self.assertFalse(self.target.exists())
            self.run_install()
            self.assertEqual(self.target.read_bytes(), self.content)

    def test_process_exit_before_rename_leaves_no_partial_target(self):
        self._crash(False)

    def test_process_exit_after_rename_leaves_complete_single_link_target(self):
        self._crash(True)


if __name__ == '__main__':
    unittest.main()
