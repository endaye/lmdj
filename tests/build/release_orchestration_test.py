#!/usr/bin/env python3
"""Real filesystem/process tests for durable release intent-before-effect ordering."""

import json
import os
import select
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.orchestration import JournalError, RequestJournal, STEPS


def request():
    return {"id": "release-1", "repository": "example/product", "actor_id": 123,
            "authority_ref": "thread:release-1", "policy_digest": "a" * 64,
            "control_revision": "b" * 40, "base_revision": "c" * 40,
            "mode": "new", "requested_tag": None}


EVIDENCE = {"sha256": "d" * 64, "reference": "run:123:1"}


class RequestJournalTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "journal"

    def test_same_request_is_idempotent_and_returns_unshared_data(self):
        with RequestJournal(self.root) as journal:
            first = journal.create(request())
            self.assertEqual(first, journal.create(request()))
            first["request"]["base_revision"] = "e" * 40
            self.assertEqual(journal.read("release-1")["request"], request())

    def test_request_id_cannot_be_rebound(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            changed = request()
            changed["base_revision"] = "e" * 40
            with self.assertRaisesRegex(JournalError, "rebound"):
                journal.create(changed)

    def test_new_id_cannot_duplicate_unfinished_repository_release(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            changed = request()
            changed["id"] = "release-2"
            with self.assertRaisesRegex(JournalError, "unfinished"):
                journal.create(changed)

    def test_repository_identity_requires_canonical_case(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            with self.assertRaisesRegex(JournalError, "repository"):
                journal.create(dict(request(), id="release-2", repository="Example/Product"))

    def test_context_cannot_be_used_by_another_thread(self):
        errors = []
        with RequestJournal(self.root) as journal:
            journal.create(request())

            def writer():
                try:
                    journal.begin("release-1", "candidate")
                except JournalError as error:
                    errors.append(str(error))

            thread = threading.Thread(target=writer)
            thread.start()
            thread.join()
            self.assertEqual(len(errors), 1)
            self.assertIn("owning process and thread", errors[0])
            self.assertEqual(journal.read("release-1")["transitions"], [])

    def test_inherited_fork_context_cannot_write(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            child = os.fork()
            if child == 0:
                try:
                    journal.begin("release-1", "candidate")
                except JournalError:
                    os._exit(23)
                os._exit(0)
            _, result = os.waitpid(child, 0)
            self.assertEqual(os.waitstatus_to_exitcode(result), 23)
            self.assertEqual(journal.read("release-1")["transitions"], [])

    def test_fork_child_cleanup_does_not_unlock_parent_or_retain_its_lock(self):
        ready_read, ready_write = os.pipe()
        finish_read, finish_write = os.pipe()
        child = None
        try:
            with RequestJournal(self.root) as journal:
                child = os.fork()
                if child == 0:
                    try:
                        os.close(ready_read)
                        os.close(finish_write)
                        journal.__exit__(None, None, None)
                        os.write(ready_write, b"ready")
                        if select.select([finish_read], [], [], 5)[0]:
                            os.read(finish_read, 1)
                            os._exit(0)
                    except BaseException:
                        pass
                    os._exit(1)
                os.close(ready_write)
                ready_write = None
                os.close(finish_read)
                finish_read = None
                self.assertTrue(select.select([ready_read], [], [], 5)[0])
                self.assertEqual(os.read(ready_read, 5), b"ready")
                with self.assertRaisesRegex(JournalError, "another writer"):
                    with RequestJournal(self.root):
                        pass
            # Child remains alive but no longer retains the parent's lock.
            with RequestJournal(self.root):
                self.assertEqual(os.waitpid(child, os.WNOHANG), (0, 0))
        finally:
            if child:
                os.write(finish_write, b"x")
                _, result = os.waitpid(child, 0)
            for fd in (ready_read, ready_write, finish_read, finish_write):
                if fd is not None:
                    os.close(fd)
        self.assertEqual(os.waitstatus_to_exitcode(result), 0)

    def test_pending_intent_survives_process_crash_and_prevents_duplicate_effect(self):
        # The subprocess simulates the driver's actual external side effect then
        # dies before recording its verification. Reopening must not run it again.
        far_side = self.root.parent / "external-effects"
        script = """
import os, sys
from pathlib import Path
from tools.release.orchestration import RequestJournal
import json
with RequestJournal(Path(sys.argv[1])) as journal:
    journal.create(json.loads(sys.argv[3]))
    journal.begin('release-1', 'candidate')
    with open(sys.argv[2], 'wb') as output:
        output.write(b'one-external-effect')
        output.flush()
        os.fsync(output.fileno())
    os._exit(17)
"""
        child = subprocess.run([sys.executable, "-c", script, str(self.root),
                                str(far_side), json.dumps(request())], cwd=ROOT)
        self.assertEqual(child.returncode, 17)
        with RequestJournal(self.root) as journal:
            state = journal.read("release-1")
            self.assertEqual(state["transitions"][-1]["status"], "intent")
            with self.assertRaisesRegex(JournalError, "reconciliation"):
                journal.begin("release-1", "candidate")
            self.assertEqual(far_side.read_bytes(), b"one-external-effect")
            operation = state["transitions"][-1]["operation_id"]
            journal.confirm("release-1", operation, EVIDENCE)
        with RequestJournal(self.root) as journal:
            self.assertEqual(journal.read("release-1")["transitions"][-1]["evidence"], EVIDENCE)
            journal.begin("release-1", "verification")
        self.assertEqual(far_side.read_bytes(), b"one-external-effect")

    def test_step_order_and_confirmation_identity_are_enforced(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            with self.assertRaisesRegex(JournalError, "next release step"):
                journal.begin("release-1", "publication")
            record = journal.begin("release-1", "candidate")
            with self.assertRaisesRegex(JournalError, "does not match"):
                journal.confirm("release-1", "e" * 64, EVIDENCE)
            journal.confirm("release-1", record["operation_id"], EVIDENCE)
            journal.confirm("release-1", record["operation_id"], EVIDENCE)
            with self.assertRaisesRegex(JournalError, "immutable"):
                journal.confirm("release-1", record["operation_id"], dict(EVIDENCE, sha256="e" * 64))

    def test_all_steps_survive_reopen_and_complete_request_allows_next(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
        for step in STEPS:
            with RequestJournal(self.root) as journal:
                record = journal.begin("release-1", step)
                journal.confirm("release-1", record["operation_id"], EVIDENCE)
        with RequestJournal(self.root) as journal:
            self.assertEqual([r["step"] for r in journal.read("release-1")["transitions"]], list(STEPS))
            journal.create(dict(request(), id="release-2"))

    def test_another_process_cannot_enter_while_writer_is_live(self):
        with RequestJournal(self.root):
            script = """
from pathlib import Path
from tools.release.orchestration import RequestJournal, JournalError
import sys
try:
    with RequestJournal(Path(sys.argv[1])): pass
except JournalError:
    sys.exit(19)
sys.exit(0)
"""
            child = subprocess.run([sys.executable, "-c", script, str(self.root)], cwd=ROOT)
            self.assertEqual(child.returncode, 19)
        with RequestJournal(self.root):
            pass

    def test_use_after_context_exit_is_rejected(self):
        journal = RequestJournal(self.root)
        with journal:
            journal.create(request())
        with self.assertRaisesRegex(JournalError, "exclusive context"):
            journal.begin("release-1", "candidate")

    def test_symlink_or_insecure_root_is_rejected(self):
        self.root.mkdir(mode=0o755)
        with self.assertRaises(JournalError):
            with RequestJournal(self.root): pass
        self.root.rmdir()
        destination = self.root.parent / "other"
        destination.mkdir(mode=0o700)
        self.root.symlink_to(destination)
        with self.assertRaisesRegex(JournalError, "symlink"):
            with RequestJournal(self.root): pass

    def test_replaced_writer_lock_fences_original_process(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            (self.root / "writer.lock").rename(self.root / "old.lock")
            (self.root / "writer.lock").touch(mode=0o600)
            with self.assertRaisesRegex(JournalError, "replaced"):
                journal.begin("release-1", "candidate")

    def test_corrupt_state_is_not_recreated(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            location = self.root / "release-1.json"
            original = location.read_bytes()
            location.write_bytes(original.replace(b'"actor_id":123', b'"actor_id":124'))
            corrupted = location.read_bytes()
            with self.assertRaisesRegex(JournalError, "digest differs"):
                journal.create(request())
            self.assertEqual(location.read_bytes(), corrupted)

    def test_symlink_and_hardlink_requests_are_rejected(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            location = self.root / "release-1.json"
            other = self.root / "saved-state"
            location.rename(other)
            location.symlink_to(other)
            with self.assertRaises(JournalError):
                journal.read("release-1")
            location.unlink()
            os.link(other, location)
            with self.assertRaises(JournalError):
                journal.read("release-1")

    def test_directory_fsync_failure_leaves_reconcilable_intent_not_a_repeat(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            real_fsync = os.fsync

            def fail_directory(fd):
                if fd == journal.directory:
                    raise OSError("directory durability uncertain")
                real_fsync(fd)

            with patch("tools.release.orchestration.os.fsync", side_effect=fail_directory):
                with self.assertRaises(OSError):
                    journal.begin("release-1", "candidate")
        with RequestJournal(self.root) as journal:
            self.assertEqual(journal.read("release-1")["transitions"][-1]["status"], "intent")
            with self.assertRaisesRegex(JournalError, "reconciliation"):
                journal.begin("release-1", "candidate")

    def test_fsync_failure_prevents_intent_commit(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            before = (self.root / "release-1.json").read_bytes()
            with patch("tools.release.orchestration.os.fsync", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    journal.begin("release-1", "candidate")
            self.assertEqual((self.root / "release-1.json").read_bytes(), before)

    def test_request_and_evidence_are_closed(self):
        with RequestJournal(self.root) as journal:
            for changed in (dict(request(), id="../bad"), dict(request(), actor_id=True),
                            dict(request(), secret="not-allowed"), dict(request(), mode="stable")):
                with self.subTest(changed=changed):
                    with self.assertRaises(JournalError):
                        journal.create(changed)
            journal.create(request())
            record = journal.begin("release-1", "candidate")
            with self.assertRaises(JournalError):
                journal.confirm("release-1", record["operation_id"], dict(EVIDENCE, token="not-allowed"))

    def test_oversized_create_is_rejected_before_any_record_write(self):
        with RequestJournal(self.root) as journal:
            oversized = dict(request(), repository="a" * (1024 * 1024) + "/product")
            with self.assertRaisesRegex(JournalError, "size limit"):
                journal.create(oversized)
            self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["writer.lock"])
            journal.create(request())
        with RequestJournal(self.root) as journal:
            self.assertEqual(journal.read("release-1")["request"], request())

    def test_oversized_update_preserves_previous_readable_record(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            location = self.root / "release-1.json"
            before = location.read_bytes()
            with patch("tools.release.orchestration._MAX_BYTES", len(before)):
                with self.assertRaisesRegex(JournalError, "size limit"):
                    journal.begin("release-1", "candidate")
                self.assertEqual(location.read_bytes(), before)
                self.assertEqual(journal.read("release-1")["transitions"], [])
            self.assertEqual(sorted(p.name for p in self.root.iterdir()),
                             ["release-1.json", "writer.lock"])
        with RequestJournal(self.root) as journal:
            self.assertEqual(journal.read("release-1")["transitions"], [])


if __name__ == "__main__":
    unittest.main()
