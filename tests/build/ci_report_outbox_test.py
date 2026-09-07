"""Cross-process outbox fault journeys over the real Journal protocol."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/ci"), str(ROOT / "tests/build")]
import report_outbox as outbox
import self_test_report as reporting
from ci_batch_controller_test import Memory
from ci_self_test_report_test import FakeGitHubApi


class Crash(BaseException):
    pass


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.memory = Memory()
        self.api = FakeGitHubApi()
        self.report = reporting.Report(key="suite/failure", title="Failure", observation="51/1/suite/hash", severity="medium",
                                       labels=("self-test", "type:bug"), summary="Verified failure", detail="Exact evidence")

    def fresh(self):
        # Fresh object is a fresh reporter process: no old _WriteState survives.
        return outbox.Outbox(self.memory.journal(), lambda: self.memory.lock, "report-epoch")

    def posts(self):
        return [c for c in self.api.calls if c[0] in {"create_issue", "create_comment"}]

    def test_create_ack_visible_receipt_then_duplicate_delivery(self):
        first = self.fresh().deliver(self.api, self.report)
        second = self.fresh().deliver(self.api, self.report)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "delivered")
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual([e["type"] for e in self.memory.journal().load()], ["queue", "claim", "ack", "delivered"])

    def test_new_observation_uses_existing_bucket(self):
        first = self.fresh().deliver(self.api, self.report)
        second = self.fresh().deliver(self.api, replace(self.report, observation="52/1/suite/hash"))
        self.assertEqual(first["receipt"]["issue_number"], second["receipt"]["issue_number"])
        self.assertIsNotNone(second["receipt"]["comment_id"])
        self.assertEqual([p[0] for p in self.posts()], ["create_issue", "create_comment"])

    def test_queue_response_loss_before_claim_can_resume_safely(self):
        self.memory.fail = ("queue", "after")
        with self.assertRaises(outbox.OutboxBlocked):
            self.fresh().deliver(self.api, self.report)
        self.assertFalse(self.posts())
        self.assertEqual(self.fresh().drain_once(self.api)["status"], "delivered")
        self.assertEqual(len(self.posts()), 1)

    def test_comment_post_process_death_recovers_without_second_comment(self):
        self.fresh().deliver(self.api, self.report)
        newer = replace(self.report, observation="new")
        original = self.api.create_comment
        def die(number, body):
            original(number, body)
            raise Crash()
        self.api.create_comment = die
        with self.assertRaises(Crash):
            self.fresh().deliver(self.api, newer)
        self.api.create_comment = original
        self.assertEqual(self.fresh().deliver(self.api, newer)["status"], "delivered")
        self.assertEqual([p[0] for p in self.posts()], ["create_issue", "create_comment"])

    def test_pending_claim_blocks_new_report_but_keeps_its_durable_queue(self):
        self.memory.fail = ("claim", "after")
        with self.assertRaises(outbox.OutboxBlocked):
            self.fresh().deliver(self.api, self.report)
        newer = replace(self.report, key="other", observation="new")
        self.assertEqual(self.fresh().deliver(self.api, newer)["status"], "needs-reconciliation")
        self.assertEqual(len(self.fresh().load()["deliveries"]), 2)
        self.assertFalse(self.posts())

    def test_idle_drain_does_not_write_journal_or_business_objects(self):
        self.assertEqual(self.fresh().drain_once(self.api), {"status": "idle"})
        self.assertFalse(self.memory.comments)
        self.assertFalse(self.api.calls)

    def test_claim_response_loss_never_sends_business_post_on_restart(self):
        self.memory.fail = ("claim", "after")
        with self.assertRaises(outbox.OutboxBlocked):
            self.fresh().deliver(self.api, self.report)
        self.assertFalse(self.posts())
        answer = self.fresh().deliver(self.api, self.report)
        self.assertEqual(answer["status"], "needs-reconciliation")
        self.assertIn("before sending", answer["why"])
        self.assertFalse(self.posts())

    def test_claim_before_post_process_death_is_honestly_ambiguous(self):
        original = self.api.create_issue
        self.api.create_issue = lambda **kwargs: (_ for _ in ()).throw(Crash())
        with self.assertRaises(Crash):
            self.fresh().deliver(self.api, self.report)
        self.api.create_issue = original
        for _ in range(3):
            answer = self.fresh().deliver(self.api, self.report)
            self.assertEqual(answer["status"], "needs-reconciliation")
        self.assertFalse(self.posts())

    def test_post_response_loss_reads_exact_receipt_without_repost(self):
        original = self.api.create_issue
        def lose(**kwargs):
            original(**kwargs)
            raise reporting.GitHubApiError(0, "response lost")
        self.api.create_issue = lose
        result = self.fresh().deliver(self.api, self.report)
        self.assertEqual(result["status"], "delivered")
        self.assertEqual(len(self.posts()), 1)

    def test_post_then_process_death_recovers_in_new_process(self):
        original = self.api.create_issue
        def die(**kwargs):
            original(**kwargs)
            raise Crash()
        self.api.create_issue = die
        with self.assertRaises(Crash):
            self.fresh().deliver(self.api, self.report)
        self.api.create_issue = original
        answer = self.fresh().deliver(self.api, self.report)
        self.assertEqual(answer["status"], "delivered")
        self.assertEqual(len(self.posts()), 1)

    def test_ack_response_loss_does_not_repeat_acknowledged_post(self):
        self.memory.fail = ("ack", "after")
        with self.assertRaises(outbox.OutboxBlocked):
            self.fresh().deliver(self.api, self.report)
        self.assertEqual(self.fresh().deliver(self.api, self.report)["status"], "delivered")
        self.assertEqual(len(self.posts()), 1)

    def test_delivered_response_loss_replays_exact_delivery(self):
        self.memory.fail = ("delivered", "after")
        with self.assertRaises(outbox.OutboxBlocked):
            self.fresh().deliver(self.api, self.report)
        self.assertEqual(self.fresh().deliver(self.api, self.report)["status"], "delivered")
        self.assertEqual(len(self.posts()), 1)

    def test_invisible_post_remains_pending_until_exact_receipt_visible(self):
        original_write, original_list = self.api.create_issue, self.api.list_issues
        def invisible(**kwargs):
            response = original_write(**kwargs)
            self.api.list_issues = lambda **kwargs: []
            return response
        self.api.create_issue = invisible
        with self.assertRaises(reporting.WriteVisibilityError):
            self.fresh().deliver(self.api, self.report)
        self.assertEqual(self.fresh().deliver(self.api, self.report)["status"], "needs-reconciliation")
        self.api.list_issues = original_list
        self.assertEqual(self.fresh().deliver(self.api, self.report)["status"], "delivered")
        self.assertEqual(len(self.posts()), 1)

    def test_read_404_after_unknown_post_does_not_authorize_retry(self):
        original_write = self.api.create_issue
        def die(**kwargs):
            original_write(**kwargs)
            raise Crash()
        self.api.create_issue = die
        with self.assertRaises(Crash):
            self.fresh().deliver(self.api, self.report)
        self.api.list_issues = lambda **kwargs: (_ for _ in ()).throw(reporting.GitHubApiError(404, "hidden"))
        self.assertEqual(self.fresh().deliver(self.api, self.report)["status"], "needs-reconciliation")
        self.assertEqual(len(self.posts()), 1)

    def test_known_bucket_disappearing_cannot_create_a_second_issue(self):
        self.fresh().deliver(self.api, self.report)
        self.api.list_issues = lambda **kwargs: []
        with self.assertRaises(reporting.WriteVisibilityError):
            self.fresh().deliver(self.api, replace(self.report, observation="new"))
        self.assertEqual(len(self.posts()), 1)

    def test_changed_frozen_body_is_rejected(self):
        self.fresh().deliver(self.api, self.report)
        with self.assertRaisesRegex(outbox.OutboxBlocked, "body changed"):
            self.fresh().deliver(self.api, replace(self.report, detail="different"))
        self.assertEqual(len(self.posts()), 1)

    def test_mutated_visible_body_does_not_forge_receipt(self):
        original = self.api.create_issue
        def die(**kwargs):
            original(**kwargs)
            raise Crash()
        self.api.create_issue = die
        with self.assertRaises(Crash):
            self.fresh().deliver(self.api, self.report)
        self.api.issues[0]["body"] += "changed"
        self.assertEqual(self.fresh().recover(self.api)["status"], "needs-reconciliation")
        self.assertEqual(len(self.posts()), 1)

    def test_claim_digest_tampering_is_rejected_by_reducer(self):
        driver = self.fresh()
        driver.load()
        payload = outbox.freeze(self.report, "endaye")
        key = outbox.batch.digest({"key": self.report.key, "observation": self.report.observation})
        driver._persist("queue", {"delivery": key, "payload": payload})
        operation = {"kind": "create-comment", "issue_number": 123, "payload": {"body": self.report.comment_body()}, "digest": "f" * 64}
        with self.assertRaisesRegex(outbox.OutboxBlocked, "digest"):
            driver._persist("claim", {"delivery": key, "operation": operation})
        self.assertFalse(self.posts())

    def test_new_comment_claim_cannot_redirect_known_bucket(self):
        self.fresh().deliver(self.api, self.report)
        driver = self.fresh()
        driver.load()
        newer = replace(self.report, observation="new")
        key = outbox.batch.digest({"key": newer.key, "observation": newer.observation})
        driver._persist("queue", {"delivery": key, "payload": outbox.freeze(newer, "endaye")})
        operation = {"kind": "create-comment", "issue_number": 123, "payload": {"body": newer.comment_body()}}
        operation["digest"] = outbox.batch.digest(operation)
        with self.assertRaisesRegex(outbox.OutboxBlocked, "known bucket target"):
            driver._persist("claim", {"delivery": key, "operation": operation})
        self.assertEqual(len(self.posts()), 1)

    def test_changed_receipt_target_is_rejected(self):
        self.fresh().deliver(self.api, self.report)
        state = self.fresh().load()
        key, delivery = next(iter(state["deliveries"].items()))
        state["deliveries"][key]["status"] = "acknowledged"
        driver = self.fresh()
        driver.state = state
        with self.assertRaisesRegex(outbox.OutboxBlocked, "acknowledged|bucket"):
            driver._persist("delivered", {"delivery": key, "receipt": {"issue_number": 999, "comment_id": None}})

    def test_deleted_journal_tail_blocks_all_report_posts(self):
        self.fresh().deliver(self.api, self.report)
        self.memory.comments.pop()
        with self.assertRaises(outbox.OutboxBlocked):
            self.fresh().deliver(self.api, replace(self.report, observation="new"))
        self.assertEqual(len(self.posts()), 1)

    def test_missing_writer_lock_blocks_before_business_api(self):
        self.memory.lock = False
        with self.assertRaises(outbox.OutboxBlocked):
            self.fresh().deliver(self.api, self.report)
        self.assertFalse(self.api.calls)

    def test_explicit_refusal_does_not_automatically_retry(self):
        def refused(**kwargs):
            self.api.calls.append(("create_issue",))
            raise reporting.GitHubApiError(403, "explicit refusal")
        self.api.create_issue = refused
        with self.assertRaises(reporting.GitHubApiError):
            self.fresh().deliver(self.api, self.report)
        self.assertEqual(self.fresh().deliver(self.api, self.report)["status"], "needs-reconciliation")
        self.assertEqual(len(self.posts()), 1)


if __name__ == "__main__":
    unittest.main()
