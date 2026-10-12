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

    def test_a_deep_missing_parent_chain_is_created_private(self):
        # The entry composes request journals under
        # <gitdir>/lmdj-release-requests/operations/<id>/<step> — parents that
        # exist only after this creation, each at 0700 (mkdir's mode applies
        # per level). A symlinked ancestor still fails closed; only absent
        # plain directories are created.
        deep = self.root / "operations" / "request-id" / "candidate-preparation" / "source-setup"
        with RequestJournal(deep) as journal:
            journal.create(request())
        import os
        for level in (self.root, *deep.parents)[:4]:
            mode = oct(os.lstat(level).st_mode & 0o777)
            self.assertEqual(mode, "0o700")

    def test_a_symlinked_ancestor_is_refused(self):
        import os
        real = self.root / "real"
        real.mkdir(parents=True, mode=0o700)
        link = self.root / "link"
        os.symlink(real, link)
        with self.assertRaisesRegex(JournalError, "symlink"):
            with RequestJournal(link / "journal"):
                pass

    def test_a_non_directory_ancestor_is_refused(self):
        import os
        (self.root / "file").parent.mkdir(parents=True, exist_ok=True)
        (self.root / "file").write_text("x")
        with self.assertRaisesRegex(JournalError, "unsafe"):
            with RequestJournal(self.root / "file" / "journal"):
                pass

    RETIREMENT = {"superseded_by": "lmdj-v1.0.61.0", "identity": "1.0.61.0",
                  "observed_utc": "2026-09-28T00:00:00Z",
                  "audit": ["[ok] lmdj-v1.0.61.0: remote tag matches canonical intent"]}

    UNRELEASED = {"superseded_by_build": "1.0.65.0", "identity": "1.0.64.0",
                  "main_revision": "e" * 40, "observed_utc": "2026-09-28T00:00:00Z",
                  "evidence": ["[ok] lmdj-v1.0.64.0: no remote tag at 2026-09-28T00:00:00Z"]}

    def test_unreleased_retirement_frees_admission(self):
        with RequestJournal(self.root) as journal:
            original = journal.create(request())
            record = journal.retire("release-1", self.UNRELEASED)
            self.assertEqual(record["original"], original)
            self.assertEqual(record["retirement"], self.UNRELEASED)
            self.assertIsNone(journal.read("release-1"))
            journal.create(dict(request(), id="release-2"))
        with RequestJournal(self.root) as journal:
            self.assertEqual(journal.read_retirement("release-1")["retirement"], self.UNRELEASED)

    def test_unreleased_retirement_requires_a_later_build_and_tag_absence(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            for bad in (dict(self.UNRELEASED, superseded_by_build="1.0.64.0"),
                        dict(self.UNRELEASED, superseded_by_build="1.0.63.0"),
                        dict(self.UNRELEASED, superseded_by_build="1.1.65.0"),
                        dict(self.UNRELEASED, superseded_by_build="1.0.65.1"),
                        dict(self.UNRELEASED, main_revision="main"),
                        dict(self.UNRELEASED, evidence=["[ok] main: carries 1.0.65.0"]),
                        dict(self.UNRELEASED, evidence=[]),
                        dict(self.UNRELEASED, superseded_by="lmdj-v1.0.64.0")):
                with self.assertRaises(JournalError):
                    journal.retire("release-1", bad)
            self.assertIsNotNone(journal.read("release-1"))

    def test_retirement_frees_admission_and_retains_the_original(self):
        with RequestJournal(self.root) as journal:
            original = journal.create(request())
            with self.assertRaisesRegex(JournalError, "unfinished"):
                journal.create(dict(request(), id="release-2"))
            record = journal.retire("release-1", self.RETIREMENT)
            self.assertEqual(record["original"], original)
            self.assertIsNone(journal.read("release-1"))
            self.assertEqual(journal.read_retirement("release-1"), record)
            self.assertIsNone(journal.resolve_active(dict(request(), id="release-2", control_revision="e" * 40)))
            journal.create(dict(request(), id="release-2"))

    def test_retirement_is_idempotent_and_cannot_be_rebound(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            first = journal.retire("release-1", self.RETIREMENT)
            self.assertEqual(journal.retire("release-1", self.RETIREMENT), first)
            with self.assertRaisesRegex(JournalError, "rebound"):
                journal.retire("release-1", dict(self.RETIREMENT, observed_utc="2026-09-29T00:00:00Z"))
        with RequestJournal(self.root) as journal:
            self.assertEqual(journal.read_retirement("release-1"), first)

    def test_crash_between_record_and_unlink_finishes_on_repeat(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            real_unlink = os.unlink

            def crash_on_original(path, *args, **kwargs):
                if path == "release-1.json":
                    raise OSError("crash")
                return real_unlink(path, *args, **kwargs)

            with patch("tools.release.orchestration.os.unlink", side_effect=crash_on_original):
                with self.assertRaises(OSError):
                    journal.retire("release-1", self.RETIREMENT)
            # Both survive the crash; admission still counts the original.
            self.assertIsNotNone(journal.read("release-1"))
            self.assertIsNotNone(journal.read_retirement("release-1"))
            journal.retire("release-1", self.RETIREMENT)
            self.assertIsNone(journal.read("release-1"))

    def test_an_original_that_differs_from_the_record_is_not_removed(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            real_read = journal.read
            calls = []

            def changed_on_recheck(request_id):
                calls.append(request_id)
                state = real_read(request_id)
                if len(calls) == 2 and state is not None:
                    state = dict(state, request=dict(state["request"], authority_ref="thread:other"))
                return state

            with patch.object(journal, "read", side_effect=changed_on_recheck):
                with self.assertRaisesRegex(JournalError, "changed before retirement"):
                    journal.retire("release-1", self.RETIREMENT)
            self.assertIsNotNone(journal.read("release-1"))
            # The withdrawn record leaves a clean retry, not a rebinding refusal.
            self.assertIsNone(journal.read_retirement("release-1"))
            journal.retire("release-1", self.RETIREMENT)
            self.assertIsNone(journal.read("release-1"))

    def test_retirement_is_bound_to_the_request_its_proof_was_made_for(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            with self.assertRaisesRegex(JournalError, "changed after its supersession"):
                journal.retire("release-1", self.RETIREMENT,
                               expected_request=dict(request(), authority_ref="thread:other"))
            self.assertIsNotNone(journal.read("release-1"))
            journal.retire("release-1", self.RETIREMENT, expected_request=request())
            self.assertIsNone(journal.read("release-1"))

    def test_an_outstanding_intent_needs_reconciliation_unless_the_build_is_published(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            record = journal.begin("release-1", STEPS[0])
            with self.assertRaisesRegex(JournalError, "outstanding intent"):
                journal.retire("release-1", self.UNRELEASED)
            # The published, audited Build settles what the intent worked toward;
            # the retirement keeps the intent in its retained original state.
            record = journal.retire("release-1", self.RETIREMENT)
            self.assertIsNone(journal.read("release-1"))
            self.assertEqual(record["original"]["transitions"][-1]["status"], "intent")

    def settled_intent(self, **overrides):
        settled = {"step": "candidate", "operation_id": "f" * 64, "pull_request": 2073,
                   "head_sha": "a" * 40, "state": "closed", "merged": False,
                   "merge_commit_sha": None}
        settled.update(overrides)
        return settled

    def test_a_terminal_cut_pull_request_settles_an_outstanding_candidate_intent(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            begun = journal.begin("release-1", STEPS[0])
            assert begun["step"] == "candidate"
            retirement = dict(self.UNRELEASED,
                              settled_intent=self.settled_intent(operation_id=begun["operation_id"]))
            with self.assertRaisesRegex(JournalError, "outstanding intent"):
                # A settled proof bound to another operation settles nothing.
                journal.retire("release-1", dict(retirement,
                                                 settled_intent=self.settled_intent()))
            for bad in (self.settled_intent(state="open", operation_id=begun["operation_id"]),
                        self.settled_intent(merged=True, merge_commit_sha=None, operation_id=begun["operation_id"]),
                        self.settled_intent(merged=False, merge_commit_sha="b" * 40, operation_id=begun["operation_id"]),
                        self.settled_intent(step="verification", operation_id=begun["operation_id"]),
                        self.settled_intent(head_sha="not-a-sha", operation_id=begun["operation_id"]),
                        self.settled_intent(pull_request=0, operation_id=begun["operation_id"])):
                with self.assertRaisesRegex(JournalError, "settled intent|outstanding intent"):
                    journal.retire("release-1", dict(self.UNRELEASED, settled_intent=bad))
            record = journal.retire("release-1", retirement)
            self.assertIsNone(journal.read("release-1"))
            self.assertEqual(record["original"]["transitions"][-1]["status"], "intent")
            self.assertEqual(record["retirement"]["settled_intent"]["pull_request"], 2073)
            # A merged cut is equally terminal and settles the same way, with
            # its merge commit pinned.
            journal.create(dict(request(), id="release-3"))
            begun = journal.begin("release-3", STEPS[0])
            merged = dict(self.UNRELEASED, identity="1.0.66.0", superseded_by_build="1.0.67.0",
                          settled_intent=self.settled_intent(
                              operation_id=begun["operation_id"], merged=True,
                              merge_commit_sha="b" * 40))
            merged["evidence"] = ["[ok] lmdj-v1.0.66.0: no remote tag at 2026-09-28T00:00:00Z"]
            record = journal.retire("release-3", merged)
            self.assertIsNone(journal.read("release-3"))
            self.assertTrue(record["retirement"]["settled_intent"]["merged"])
            # The settled retirement frees admission for a new request.
            self.assertIsNotNone(journal.create(dict(request(), id="release-2")))

    def test_completed_requests_are_not_retired(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            for step in STEPS:
                record = journal.begin("release-1", step)
                journal.confirm("release-1", record["operation_id"], EVIDENCE)
            with self.assertRaisesRegex(JournalError, "completed release"):
                journal.retire("release-1", self.RETIREMENT)

    def test_retirement_must_name_the_reserved_identity_and_audit(self):
        with RequestJournal(self.root) as journal:
            journal.create(request())
            for bad in (dict(self.RETIREMENT, identity="1.0.62.0"),
                        dict(self.RETIREMENT, identity=["1.0.61.0"]),
                        dict(self.RETIREMENT, identity="1.0.61"),
                        dict(self.RETIREMENT, superseded_by="v1.0.61.0", identity="1.0.61.0"),
                        dict(self.RETIREMENT, audit=[]),
                        dict(self.RETIREMENT, audit=["[ok] lmdj-v1.0.60.0: unrelated release"]),
                        {k: v for k, v in self.RETIREMENT.items() if k != "audit"}):
                with self.assertRaises(JournalError):
                    journal.retire("release-1", bad)
            self.assertIsNotNone(journal.read("release-1"))
            with self.assertRaisesRegex(JournalError, "missing"):
                journal.retire("release-9", self.RETIREMENT)

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
