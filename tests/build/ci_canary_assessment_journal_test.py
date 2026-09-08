"""Real Journal/outbox composition; fake API authority is not live acceptance."""
from copy import deepcopy
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.canary import assessment_journal as storage, assessment as a, records as r
import ci_canary_assessment_runtime_test as runtime_fixture
from ci_batch_controller_test import Memory
from ci_self_test_report_test import FakeGitHubApi
from incremental_batch_journal import Journal
import report_outbox


class Crash(BaseException):
    pass


class AssessmentJournalTests(unittest.TestCase):
    def setUp(self):
        self.fixture = runtime_fixture.RuntimeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.context = self.fixture.context
        self.owner = {"run_id": 100, "attempt": 1, "control_sha": self.context["control_sha"]}
        self.memory, self.reports = Memory(), Memory()
        self.api = FakeGitHubApi()

    def fresh(self, epoch="assessment-epoch"):
        return storage.Assessments(self.memory.journal(), lambda: self.memory.lock, epoch)

    def outbox(self):
        journal = Journal(783, self.reports, self.reports, lambda *args: True, lambda: self.reports.lock)
        return report_outbox.Outbox(journal, lambda: self.reports.lock, "report-epoch")

    def result(self, blocked=False):
        if blocked:
            self.fixture.credentials = {}
        else:
            self.fixture.answer()
        self.memory.lock = False
        try:
            return self.fixture.execute()
        finally:
            self.memory.lock = True

    def terminal(self, blocked=False):
        self.fresh().claim(self.context, self.owner)
        result = self.result(blocked)
        self.fresh().complete(self.context["digest"], self.owner, result)
        return result

    def posts(self):
        return [c for c in self.api.calls if c[0] in {"create_issue", "create_comment"}]

    def test_claim_execution_completion_reopens_complete_bytes(self):
        claim = self.fresh().claim(self.context, self.owner)
        self.assertEqual(claim["action"], "execute")
        self.assertEqual(claim["context"], self.context)
        self.assertEqual(self.fresh().claim(self.context, self.owner)["action"], "pending")
        result = self.result()
        self.fresh().complete(self.context["digest"], self.owner, result)
        reopened = self.fresh().claim(self.context, self.owner)
        self.assertEqual(reopened["action"], "terminal")
        self.assertEqual(reopened["result"], result)
        self.assertEqual(reopened["context"], self.context)
        self.assertEqual(len(self.memory.comments), 4)

    def test_second_executor_cannot_steal_claim(self):
        self.fresh().claim(self.context, self.owner)
        other = {**self.owner, "run_id": 101}
        self.assertEqual(self.fresh().claim(self.context, other)["action"], "pending")
        with self.assertRaises(r.CanaryError):
            self.fresh().complete(self.context["digest"], other, self.result())

    def test_terminal_replay_rejects_boolean_attempt_alias(self):
        self.terminal()
        events = self.memory.journal().load()
        state = storage.Assessments(Memory().journal(), lambda: True, "assessment-epoch").load()
        for event in events[:-1]:
            state = storage.reduce(state, event)
        changed = deepcopy(events[-1])
        changed["data"]["executor"]["attempt"] = True
        with self.assertRaisesRegex(r.CanaryError, "executor identity differs"):
            storage.reduce(state, changed)

    def test_identical_completion_is_idempotent_but_changed_result_rejected(self):
        result = self.terminal()
        self.fresh().complete(self.context["digest"], self.owner, result)
        self.assertEqual(len(self.memory.comments), 4)
        changed = self.result(blocked=True)
        with self.assertRaises(r.CanaryError):
            self.fresh().complete(self.context["digest"], self.owner, changed)

    def test_claim_response_loss_never_returns_execute_on_restart(self):
        self.memory.fail = ("claim", "after")
        with self.assertRaises(r.CanaryError):
            self.fresh().claim(self.context, self.owner)
        self.assertEqual(self.fresh().claim(self.context, self.owner)["action"], "pending")
        self.assertEqual(len(self.memory.comments), 2)

    def test_terminal_response_loss_recovers_without_reexecution(self):
        self.fresh().claim(self.context, self.owner)
        result = self.result()
        self.memory.fail = ("complete", "after")
        with self.assertRaises(r.CanaryError):
            self.fresh().complete(self.context["digest"], self.owner, result)
        self.assertEqual(self.fresh().claim(self.context, self.owner)["result"], result)
        self.fresh().complete(self.context["digest"], self.owner, result)
        self.assertEqual(len(self.memory.comments), 4)

    def test_failed_assessment_reopens_and_delivers_one_issue(self):
        result = self.terminal(blocked=True)
        first = self.fresh().report(self.context["digest"], self.outbox(), self.api)
        second = self.fresh().report(self.context["digest"], self.outbox(), self.api)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "delivered")
        self.assertEqual(len(self.posts()), 1)
        report = self.fresh().pending_reports()[0]
        self.assertIn(result["digest"], report.summary)
        self.assertIn(self.context["target_sha"], report.summary)
        self.assertEqual([e["type"] for e in self.outbox().journal.load()], ["queue", "claim", "ack", "delivered"])

    def test_issue_post_crash_recovers_exact_receipt_without_another_post(self):
        self.terminal(blocked=True)
        original = self.api.create_issue

        def crash(**kwargs):
            original(**kwargs)
            raise Crash()

        self.api.create_issue = crash
        with self.assertRaises(Crash):
            self.fresh().report(self.context["digest"], self.outbox(), self.api)
        self.api.create_issue = original
        receipt = self.fresh().report(self.context["digest"], self.outbox(), self.api)
        self.assertEqual(receipt["status"], "delivered")
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual(receipt["receipt"]["issue_number"], self.api.issues[0]["number"])

    def test_uncertain_claim_before_business_post_is_not_retried(self):
        self.terminal(blocked=True)
        self.reports.fail = ("claim", "after")
        with self.assertRaises(report_outbox.OutboxBlocked):
            self.fresh().report(self.context["digest"], self.outbox(), self.api)
        self.assertEqual(self.fresh().report(self.context["digest"], self.outbox(), self.api)["status"], "needs-reconciliation")
        self.assertFalse(self.posts())

    def test_claimed_and_advised_inputs_do_not_report_failures(self):
        self.fresh().claim(self.context, self.owner)
        self.assertFalse(self.fresh().pending_reports())
        self.assertEqual(self.fresh().report(self.context["digest"], self.outbox(), self.api)["status"], "pending")
        self.fresh().complete(self.context["digest"], self.owner, self.result())
        self.assertFalse(self.fresh().pending_reports())
        self.assertEqual(self.fresh().report(self.context["digest"], self.outbox(), self.api)["status"], "not-applicable")
        self.assertFalse(self.posts())
        self.assertFalse(self.reports.comments)

    def test_missing_claim_and_forged_terminal_seal_fail(self):
        with self.assertRaises(r.CanaryError):
            self.fresh().complete(self.context["digest"], self.owner, self.result())
        self.fresh().claim(self.context, self.owner)
        result = self.result()
        result["state"] = "blocked"
        with self.assertRaises(r.CanaryError):
            self.fresh().complete(self.context["digest"], self.owner, r.seal(result))

    def test_lost_lock_cannot_append_or_deliver(self):
        self.memory.lock = False
        with self.assertRaises(r.CanaryError):
            self.fresh().claim(self.context, self.owner)
        self.assertFalse(self.memory.comments)

    def test_epoch_change_cannot_bootstrap_existing_journal(self):
        self.fresh().claim(self.context, self.owner)
        with self.assertRaises(r.CanaryError):
            self.fresh("wrong-epoch").load()

    def test_edited_journal_is_not_an_empty_store(self):
        self.fresh().claim(self.context, self.owner)
        self.memory.comments[0]["edited"] = True
        with self.assertRaises(r.CanaryError):
            self.fresh().load()

    def test_outbox_cannot_alias_assessment_journal(self):
        self.terminal(blocked=True)
        outbox = self.outbox()
        outbox.journal.issue_id = self.memory.journal().issue_id
        with self.assertRaises(r.CanaryError):
            self.fresh().report(self.context["digest"], outbox, self.api)
        self.assertFalse(self.posts())

    def test_packed_payload_checks_digest_length_truncation_and_trailing_bytes(self):
        packed = storage.pack(self.context)
        self.assertEqual(storage.unpack(packed), self.context)
        for key, value in (("sha256", "f" * 64), ("bytes", packed["bytes"] + 1),
                           ("body", packed["body"][:-4]), ("body", packed["body"] + "AAAA")):
            with self.subTest(key=key, value=str(value)[:30]), self.assertRaises(r.CanaryError):
                storage.unpack({**packed, key: value})

    def test_oversized_uncompressed_input_and_compression_bomb_rejected(self):
        with self.assertRaises(r.CanaryError):
            storage.pack({"text": "x" * storage.MAX_RAW_BYTES})
        packed = storage.pack({"text": "x" * 10000})
        packed["bytes"] = 10
        with self.assertRaises(r.CanaryError):
            storage.unpack(packed)

    def test_complete_large_git_context_is_chunked_not_truncated(self):
        git = self.fixture.fixture
        git.write("apps/creator-web/src/random.txt", random.Random(0).randbytes(70000).hex())
        git.target = git.commit()
        self.context = git.collect()
        self.fixture.context = self.context
        result = self.terminal(blocked=True)
        reopened = self.fresh().claim(self.context, self.owner)
        self.assertEqual(reopened["context"], self.context)
        self.assertEqual(reopened["result"], result)
        events = self.memory.journal().load()
        self.assertGreater(len([event for event in events if event["type"] == "blob"]), 2)
        self.assertTrue(all(len(r.canonical(event)) <= storage.MAX_EVENT_BYTES for event in events))

    def test_partial_chunk_response_loss_resumes_before_claim_not_model(self):
        self.memory.fail = ("blob", "after")
        with self.assertRaises(r.CanaryError):
            self.fresh().claim(self.context, self.owner)
        self.assertFalse(self.fresh().load()["assessments"])
        self.assertEqual(self.fresh().claim(self.context, self.owner)["action"], "execute")
        self.assertEqual([event["type"] for event in self.memory.journal().load()], ["blob", "claim"])

    def test_compatibility_issue_omits_untrusted_model_prose_but_keeps_full_result(self):
        self.fresh().claim(self.context, self.owner)
        advice = self.fixture.fixture.advice()
        advice["components"][0]["unknowns"] = ["@everyone <script>credential-like-text</script>"]
        self.fixture.answer(advice=advice)
        result = self.fixture.execute()
        self.fresh().complete(self.context["digest"], self.owner, result)
        report = self.fresh().pending_reports()[0]
        self.assertEqual(report.key, "canary-assessment-compatibility-review")
        self.assertNotIn("credential-like-text", report.issue_body("endaye"))
        self.assertEqual(self.fresh().claim(self.context, self.owner)["result"], result)

    def test_reporting_cannot_reinvoke_model_and_requires_outbox_lock(self):
        self.terminal(blocked=True)
        self.reports.lock = False
        with patch.object(runtime_fixture.runtime, "execute", side_effect=AssertionError("model invoked")):
            with self.assertRaises(report_outbox.OutboxBlocked):
                self.fresh().report(self.context["digest"], self.outbox(), self.api)
            self.reports.lock = True
            self.assertEqual(self.fresh().report(self.context["digest"], self.outbox(), self.api)["status"], "delivered")
        self.assertEqual(len(self.posts()), 1)

    def test_missing_history_is_not_empty_success(self):
        self.terminal()
        self.memory.comments.pop()
        with self.assertRaises(r.CanaryError):
            self.fresh().load()

    def test_chunk_reordering_and_incomplete_reference_fail_closed(self):
        self.fresh().claim(self.context, self.owner)
        events = self.memory.journal().load()
        state = storage.Assessments(Memory().journal(), lambda: True, "assessment-epoch").load()
        bad = deepcopy(events[0])
        bad["data"]["index"] = 1
        with self.assertRaises(r.CanaryError):
            storage.reduce(state, bad)
        bad = deepcopy(events[1])
        bad["generation"] = 0
        with self.assertRaises(r.CanaryError):
            storage.reduce(state, bad)

    def test_new_failed_input_reuses_failure_bucket_with_a_new_observation(self):
        self.terminal(blocked=True)
        first = self.fresh().report(self.context["digest"], self.outbox(), self.api)
        git = self.fixture.fixture
        git.write("apps/creator-web/src/second.ts", "export const second = 2;\n")
        git.target = git.commit()
        self.context = git.collect()
        self.fixture.context = self.context
        self.terminal(blocked=True)
        second = self.fresh().report(self.context["digest"], self.outbox(), self.api)
        self.assertEqual(first["receipt"]["issue_number"], second["receipt"]["issue_number"])
        self.assertIsNotNone(second["receipt"]["comment_id"])
        self.assertEqual([post[0] for post in self.posts()], ["create_issue", "create_comment"])


if __name__ == "__main__":
    unittest.main()
