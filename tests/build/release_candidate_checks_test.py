#!/usr/bin/env python3
"""Actual cut/source/snapshot and subprocesses; small content gates are fixtures."""
from copy import deepcopy
from hashlib import sha256
import json
import os
import unittest
from unittest.mock import patch

import release_candidate_cut_test as cut_fixture
from tools.release.candidate_checks import CandidateTaskChecks, CandidateChecksError
from tools.release.model import canonical_json, canonical_sha256


SCRIPT = cut_fixture.SCRIPT.replace("*) exit 64 ;;", '''check)
  printf 'check\\n' >> .fixture-check-calls
  printf 'portal fixture\\n'
  test ! -f .fixture-check-fail || exit 23
  ;;
*) exit 64 ;;''')


class ChecksFixture(cut_fixture.CutFixture):
    def _prepare_seed(self):
        material = cut_fixture.snapshot_fixture.fixture_module.material_fixture.MaterialTest
        original = material.commit
        def commit(fixture):
            filename = fixture.root / "tests/build/ci_change_scope_test.py"
            filename.parent.mkdir(parents=True, exist_ok=True)
            filename.write_text("print('ownership fixture')\n")
            return original(fixture)
        with patch.object(material, "commit", commit), patch.object(cut_fixture, "SCRIPT", SCRIPT):
            super()._prepare_seed()

    def setUp(self):
        super().setUp()
        self.check_auth = []
        self.checks = self.new_checks()

    def new_checks(self, **changes):
        arguments = dict(control_revision=self.fixture.base, authorize=self.check_auth.append, path=os.environ["PATH"])
        arguments.update(changes)
        return CandidateTaskChecks(self.cut, **arguments)

    def prepare_checks(self):
        return self.checks.prepare(request=self.request, source=self.source, snapshot_sha256=self.receipt["sha256"],
            author_name="Fixture", author_email="fixture@example.invalid", timestamp=2000000000)

    def check_state(self):
        return json.loads((self.journal / self.checks.STATE).read_bytes())

    def check_calls(self):
        filename = self.root / ".fixture-check-calls"
        return filename.read_text().splitlines() if filename.exists() else []

    def spec(self, result):
        cut = result["cut"]
        return dict(operation_id=self.source["operation_id"], request_sha256=self.source["request_sha256"],
            repository_id=12, actor_id=34, base_revision=cut["base_revision"], head_sha=cut["commit"],
            tree_sha=cut["tree"], product_build=cut["product_build"], source_sha=cut["source_commit"],
            cut_binding_sha256=sha256((self.journal / "cut-binding.json").read_bytes()).hexdigest(),
            snapshot_sha256=cut["snapshot_sha256"], task_evidence_sha256=result["checks"]["sha256"])


class ChecksLifecycleTest(ChecksFixture):
    def test_six_actual_results_and_cold_resume_without_replay(self):
        snapshot = (self.journal / "snapshot-state.json").read_bytes()
        outputs = []
        def execute(journal, vector, timeout):
            self.assertIs(journal, self.tool._journal)
            result, raw = self.checks.executor._execute_output(journal, vector, timeout, capture_limit=65536)
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
            self.assertEqual(rows[offset + 2]["arguments"][-1], self.source["base_revision"])
        self.assertEqual(result["checks"]["sha256"], canonical_sha256(self.check_state()))
        history = (self.journal / self.checks.STATE).read_bytes()
        self.checks = self.new_checks()
        self.assertEqual(self.checks.verify(self.spec(result)), result["checks"])
        self.assertEqual(self.prepare_checks(), result)
        self.assertEqual((self.journal / self.checks.STATE).read_bytes(), history)
        self.assertEqual(self.check_calls(), ["check", "check"])
        self.assertEqual((self.journal / "snapshot-state.json").read_bytes(), snapshot)
        self.assertEqual(self.commands(), ["version", "resume"])
        self.assertEqual(self.tool.revision("HEAD"), result["cut"]["commit"])
        self.assertEqual(self.tool.revision(result["cut"]["source_retention_ref"]), self.source["commit"])


class ChecksFailureTest(ChecksFixture):
    def test_failed_command_retains_result_without_replay(self):
        filename = self.root / ".fixture-check-fail"
        filename.touch()
        with self.assertRaises(CandidateChecksError): self.prepare_checks()
        rows = self.check_state()["commands"]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["status"], rows[0]["result"]),
                         ("finished", [23, sha256(b"portal fixture\n").hexdigest(), 15]))
        self.assertEqual(self.tool.revision("HEAD"), self.source["commit"])
        filename.unlink()
        with self.assertRaises(CandidateChecksError): self.prepare_checks()
        self.assertEqual(self.check_calls(), ["check"])

    def test_controller_death_after_command_is_unknown(self):
        pid = os.fork()
        if pid == 0:
            execute = self.checks.executor._execute
            def crash(*args):
                execute(*args)
                os._exit(38)
            self.checks.executor._execute = crash
            self.prepare_checks()
            os._exit(99)
        _, result = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(result), 38)
        self.assertEqual(self.check_state()["commands"][0]["status"], "started")
        self.assertIsNone(self.check_state()["commands"][0]["result"])
        with self.assertRaises(CandidateChecksError): self.prepare_checks()
        self.assertEqual(self.check_calls(), ["check"])

    def test_final_authority_loss_keeps_zero_exit_unconfirmed(self):
        execute = self.checks.executor._execute
        def lose(*args):
            result = execute(*args)
            def refuse(scope): raise CandidateChecksError("SECRET")
            self.checks.authorize = refuse
            return result
        self.checks.executor._execute = lose
        with self.assertRaises(CandidateChecksError) as caught: self.prepare_checks()
        self.assertNotIn("SECRET", str(caught.exception))
        row = self.check_state()["commands"][0]
        self.assertEqual((row["status"], row["result"][0]), ("finished", 0))
        self.checks = self.new_checks()
        with self.assertRaises(CandidateChecksError): self.prepare_checks()
        self.assertEqual(self.check_calls(), ["check"])

    def test_snapshot_history_loss_after_command_is_not_verified(self):
        filename = self.journal / "snapshot-state.json"
        original = filename.read_bytes()
        execute = self.checks.executor._execute
        def lose(*args):
            result = execute(*args)
            filename.unlink()
            return result
        self.checks.executor._execute = lose
        with self.assertRaises(CandidateChecksError): self.prepare_checks()
        self.assertEqual(self.check_state()["commands"][0]["status"], "finished")
        filename.write_bytes(original)
        self.checks = self.new_checks()
        with self.assertRaises(CandidateChecksError): self.prepare_checks()
        self.assertEqual(self.check_calls(), ["check"])

    def test_tracked_drift_after_command_is_not_verified(self):
        filename = self.root / "products/lmdj/version.json"
        original = filename.read_bytes()
        execute = self.checks.executor._execute
        def drift(*args):
            result = execute(*args)
            filename.write_bytes(b"drift")
            return result
        self.checks.executor._execute = drift
        with self.assertRaises(CandidateChecksError): self.prepare_checks()
        self.assertEqual(self.check_state()["commands"][0]["status"], "finished")
        filename.write_bytes(original)
        self.checks = self.new_checks()
        with self.assertRaises(CandidateChecksError): self.prepare_checks()
        self.assertEqual(self.check_calls(), ["check"])


class ChecksReaderTest(ChecksFixture):
    def test_missing_enrolled_history_cannot_reset_budget(self):
        result = self.prepare_checks()
        filename = self.journal / self.checks.STATE
        filename.unlink()
        with self.assertRaises(CandidateChecksError): self.prepare_checks()
        with self.assertRaises(CandidateChecksError): self.checks.verify(self.spec(result))
        self.assertFalse(filename.exists())
        self.assertEqual(self.check_calls(), ["check", "check"])

    def test_committed_cut_cannot_invent_staged_checks(self):
        self.prepare_cut()
        with self.assertRaises(CandidateChecksError): self.prepare_checks()
        self.assertFalse((self.journal / self.checks.MARKER).exists())
        self.assertEqual(self.check_calls(), [])

    def test_pr_digest_and_cut_identity_must_match(self):
        result = self.prepare_checks()
        for key, value in (("task_evidence_sha256", "a" * 64), ("head_sha", "b" * 40),
                           ("source_sha", "c" * 40), ("snapshot_sha256", "d" * 64)):
            with self.subTest(key=key):
                spec = self.spec(result)
                spec[key] = value
                with self.assertRaises(CandidateChecksError): self.checks.verify(spec)
        self.assertEqual(self.check_calls(), ["check", "check"])

    def test_rebound_command_or_control_is_refused(self):
        result = self.prepare_checks()
        original = self.check_state()
        changed = deepcopy(original)
        changed["commands"][0]["arguments"] = ["true"]
        filename = self.journal / self.checks.STATE
        filename.write_bytes(canonical_json(changed))
        spec = self.spec(result)
        spec["task_evidence_sha256"] = canonical_sha256(changed)
        with self.assertRaisesRegex(CandidateChecksError, "command identity changed"):
            self.checks.verify(spec)
        filename.write_bytes(canonical_json(original))
        with self.assertRaises(CandidateChecksError):
            self.new_checks(control_revision="b" * 40).verify(self.spec(result))

    def test_reader_authority_cannot_remove_history(self):
        result = self.prepare_checks()
        filename = self.journal / self.checks.STATE
        self.checks.authorize = lambda _: filename.unlink()
        with self.assertRaises(CandidateChecksError): self.checks.verify(self.spec(result))
        self.assertFalse(filename.exists())
        self.assertEqual(self.check_calls(), ["check", "check"])


class ChecksResumeTest(ChecksFixture):
    def test_death_after_cut_commit_continues_unstarted_committed_phase(self):
        pid = os.fork()
        if pid == 0:
            original = self.tool.git
            def crash(*args, **kwargs):
                result = original(*args, **kwargs)
                if args[:2] == ("update-ref", "refs/heads/" + self.branch): os._exit(39)
                return result
            self.tool.git = crash
            self.prepare_checks()
            os._exit(99)
        _, result = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(result), 39)
        self.assertEqual([row["phase"] for row in self.check_state()["commands"]], ["staged"] * 3)
        self.assertNotEqual(self.tool.revision("HEAD"), self.source["commit"])
        completed = self.prepare_checks()
        self.assertEqual(len(self.check_state()["commands"]), 6)
        self.assertEqual(self.checks.verify(self.spec(completed)), completed["checks"])
        self.assertEqual(self.check_calls(), ["check", "check"])


if __name__ == "__main__":
    unittest.main()
