#!/usr/bin/env python3
"""Real witness/Task and child processes; small content checks are fixtures."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import release_candidate_witness_task_test as task_fixture
import release_candidate_witness_test as witness_fixture
from tools.release.model import canonical_json, canonical_sha256
from tools.release.witness_checks import WitnessTaskChecks, WitnessChecksError


SCRIPT = witness_fixture.SCRIPT.replace("*) exit 64 ;;", '''check)
  printf 'check\\n' >> .fixture-check-calls
  printf 'portal fixture\\n'
  test ! -f .fixture-check-fail || exit 23
  ;;
*) exit 64 ;;''')


class ChecksFixture(task_fixture.TaskFixture):
    def _prepare_seed(self):
        material = witness_fixture.cut_fixture.snapshot_fixture.fixture_module.material_fixture.MaterialTest
        original = material.commit
        def commit(fixture):
            name = fixture.root / "tests/build/ci_change_scope_test.py"
            name.parent.mkdir(parents=True, exist_ok=True)
            name.write_text("print('ownership fixture')\n")
            return original(fixture)
        with patch.object(material, "commit", commit), patch.object(witness_fixture, "SCRIPT", SCRIPT):
            super()._prepare_seed()

    def setUp(self):
        super().setUp()
        self.check_auth = []
        self.checks = self.new_checks()

    def new_checks(self, **changes):
        args = dict(control_revision=self.fixture.base, authorize=self.check_auth.append, path=os.environ["PATH"])
        args.update(changes)
        return WitnessTaskChecks(self.task, **args)

    def prepare_checks(self):
        return self.checks.prepare(receipt=self.receipt, base_revision=self.base, request=self.request,
            source=self.source, cut=self.cut_receipt, frozen=self.fixture.frozen, merge_revision=self.merged,
            author_name="Fixture", author_email="fixture@example.invalid", timestamp=2100000000)

    def check_state(self):
        return json.loads((self.task_journal / self.checks.STATE).read_bytes())

    def check_calls(self):
        name = self.destination / ".fixture-check-calls"
        return name.read_text().splitlines() if name.exists() else []

    def spec(self, result):
        task = result["task"]
        return dict(operation_id=task["operation_id"], request_sha256=task["request_sha256"],
            repository_id=12, actor_id=34, base_revision=task["base_revision"], head_sha=task["commit"],
            tree_sha=task["tree"], product_build=self.source["product_build"], target_revision=task["target_revision"],
            source_sha=self.source["commit"], witness_receipt_sha256=task["receipt_sha256"],
            task_binding_sha256=sha256((self.task_journal / "binding.json").read_bytes()).hexdigest(),
            task_evidence_sha256=result["checks"]["sha256"], witness=task["witness"])


class ChecksLifecycleTest(ChecksFixture):
    def test_actual_six_commands_bind_output_and_cold_resume_does_not_replay(self):
        original = self.tool.revision("HEAD"), (self.journal / "witness-state.json").read_bytes(), self.artifact.read_bytes()
        outputs = []
        def execute(journal, vector, timeout, *, retained_locks):
            self.assertEqual(journal.lock, self.task._journal.lock)
            self.assertEqual(retained_locks, (self.task.witness.local._journal.lock,))
            result, raw = self.checks.executor._execute_output(journal, vector, timeout,
                capture_limit=65536, retained_locks=retained_locks)
            self.assertIsNotNone(raw)
            outputs.append(raw)
            return result
        self.checks.executor._execute = execute
        result = self.prepare_checks()
        rows = self.check_state()["commands"]
        self.assertEqual([row["phase"] for row in rows], ["staged"] * 3 + ["committed"] * 3)
        self.assertEqual([row["status"] for row in rows], ["verified"] * 6)
        self.assertEqual(len(outputs), 6)
        for row, raw in zip(rows, outputs):
            self.assertEqual(row["result"], [0, sha256(raw).hexdigest(), len(raw)])
        for offset in (0, 3):
            self.assertEqual(outputs[offset:offset + 2], [b"portal fixture\n", b"ownership fixture\n"])
            # Actual Git may emit version-dependent deprecation diagnostics.
            # Authenticate the real combined bytes above, never assume silence.
            self.assertEqual(rows[offset + 2]["arguments"][-1], self.base)
        self.assertEqual(result["checks"]["sha256"], canonical_sha256(self.check_state()))
        spec = self.spec(result)
        self.checks = self.new_checks()
        self.assertEqual(self.checks.verify(spec), result["checks"])
        self.assertEqual(self.prepare_checks(), result)
        self.assertEqual(self.check_calls(), ["check", "check"])
        self.assertEqual(self.task.revision("HEAD"), result["task"]["commit"])
        self.assertEqual((self.tool.revision("HEAD"), (self.journal / "witness-state.json").read_bytes(), self.artifact.read_bytes()), original)
        self.assertEqual(self.witness_calls(), ["generate", "verify"])


class ChecksFailureTest(ChecksFixture):
    def test_failed_command_preserves_real_result_and_never_replays(self):
        (self.destination / ".fixture-check-fail").touch()
        with self.assertRaises(WitnessChecksError): self.prepare_checks()
        rows = self.check_state()["commands"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "finished")
        self.assertEqual(rows[0]["result"], [23, sha256(b"portal fixture\n").hexdigest(), 15])
        self.assertEqual(self.task.revision("HEAD"), self.base)
        (self.destination / ".fixture-check-fail").unlink()
        with self.assertRaises(WitnessChecksError): self.prepare_checks()
        self.assertEqual(self.check_calls(), ["check"])

    def test_missing_enrolled_state_never_resets_command_budget(self):
        result = self.prepare_checks()
        filename = self.task_journal / self.checks.STATE
        filename.unlink()
        with self.assertRaises(WitnessChecksError): self.prepare_checks()
        self.assertFalse(filename.exists())
        with self.assertRaises(WitnessChecksError): self.checks.verify(self.spec(result))
        self.assertEqual(self.check_calls(), ["check", "check"])

    def test_controller_death_after_actual_command_is_unknown_not_replayed(self):
        pid = os.fork()
        if pid == 0:
            execute = self.checks.executor._execute
            def crash(*args, **kwargs):
                execute(*args, **kwargs)
                os._exit(38)
            self.checks.executor._execute = crash
            self.prepare_checks()
            os._exit(99)
        _, result = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(result), 38)
        row = self.check_state()["commands"][0]
        self.assertEqual((row["status"], row["result"]), ("started", None))
        with self.assertRaises(WitnessChecksError): self.prepare_checks()
        self.assertEqual(self.check_calls(), ["check"])

    def test_final_authority_loss_keeps_exit_zero_unconfirmed(self):
        execute = self.checks.executor._execute
        def lose(*args, **kwargs):
            result = execute(*args, **kwargs)
            self.checks.authorize = lambda _: (_ for _ in ()).throw(PermissionError("SECRET"))
            return result
        self.checks.executor._execute = lose
        with self.assertRaises(WitnessChecksError) as caught: self.prepare_checks()
        self.assertNotIn("SECRET", str(caught.exception))
        row = self.check_state()["commands"][0]
        self.assertEqual((row["status"], row["result"][0]), ("finished", 0))
        self.checks = self.new_checks()
        with self.assertRaises(WitnessChecksError): self.prepare_checks()
        self.assertEqual(self.check_calls(), ["check"])

    def test_tracked_drift_after_command_is_not_verified(self):
        execute = self.checks.executor._execute
        name = self.destination / "docs/plans/later.md"
        original = name.read_bytes()
        def drift(*args, **kwargs):
            result = execute(*args, **kwargs)
            name.write_bytes(b"drift")
            return result
        self.checks.executor._execute = drift
        with self.assertRaises(WitnessChecksError): self.prepare_checks()
        self.assertEqual(self.check_state()["commands"][0]["status"], "finished")
        name.write_bytes(original)
        self.checks = self.new_checks()
        with self.assertRaises(WitnessChecksError): self.prepare_checks()
        self.assertEqual(self.check_calls(), ["check"])


class ChecksReaderTest(ChecksFixture):
    def test_same_type_authority_exception_cannot_expose_secret(self):
        result = self.prepare_checks()
        def refuse(scope): raise WitnessChecksError("SECRET-CALLBACK")
        self.checks.authorize = refuse
        with self.assertRaises(WitnessChecksError) as caught:
            self.checks.verify(self.spec(result))
        self.assertIn("authority is unavailable", str(caught.exception))
        self.assertNotIn("SECRET", str(caught.exception))

    def test_forged_pr_digest_is_not_actual_command_evidence(self):
        result = self.prepare_checks()
        spec = self.spec(result)
        spec["task_evidence_sha256"] = "a" * 64
        with self.assertRaisesRegex(WitnessChecksError, "PR command evidence digest changed"):
            self.checks.verify(spec)
        self.assertEqual(self.check_calls(), ["check", "check"])

    def test_reader_authority_cannot_delete_then_recreate_history(self):
        result = self.prepare_checks()
        spec = self.spec(result)
        filename = self.task_journal / self.checks.STATE
        def lose(scope): filename.unlink()
        self.checks.authorize = lose
        with self.assertRaises(WitnessChecksError): self.checks.verify(spec)
        self.assertFalse(filename.exists())
        self.assertEqual(self.check_calls(), ["check", "check"])

    def test_committed_fixture_without_staged_commands_cannot_claim_them(self):
        self.prepare_task()
        with self.assertRaises(WitnessChecksError): self.prepare_checks()
        self.assertFalse((self.task_journal / self.checks.MARKER).exists())
        self.assertEqual(self.check_calls(), [])

    def test_rebound_command_or_control_is_rejected(self):
        result = self.prepare_checks()
        spec = self.spec(result)
        original = self.check_state()
        changed = deepcopy(original)
        changed["commands"][0]["arguments"] = ["true"]
        (self.task_journal / self.checks.STATE).write_bytes(canonical_json(changed))
        spec["task_evidence_sha256"] = canonical_sha256(changed)
        with self.assertRaisesRegex(WitnessChecksError, "command identity changed"):
            self.checks.verify(spec)
        (self.task_journal / self.checks.STATE).write_bytes(canonical_json(original))
        with self.assertRaises(WitnessChecksError):
            self.new_checks(control_revision="b" * 40).verify(self.spec(result))


class ChecksResumeTest(ChecksFixture):
    def test_death_after_task_commit_continues_only_unstarted_committed_phase(self):
        pid = os.fork()
        if pid == 0:
            original = self.task.git
            def crash(*args, **kwargs):
                result = original(*args, **kwargs)
                if args[0] == "update-ref": os._exit(39)
                return result
            self.task.git = crash
            self.prepare_checks()
            os._exit(99)
        _, result = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(result), 39)
        rows = self.check_state()["commands"]
        self.assertEqual([row["phase"] for row in rows], ["staged"] * 3)
        self.assertEqual([row["status"] for row in rows], ["verified"] * 3)
        self.assertNotEqual(self.task.revision("HEAD"), self.base)
        completed = self.prepare_checks()
        self.assertEqual(len(self.check_state()["commands"]), 6)
        self.assertEqual(self.checks.verify(self.spec(completed)), completed["checks"])
        self.assertEqual(self.check_calls(), ["check", "check"])


if __name__ == "__main__":
    unittest.main()
