"""Cross-process outbox fault journeys over the real Journal protocol."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock

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

    def test_delivery_reuses_each_authenticated_append_result_without_third_history_read(self):
        # Real Journal pre/post reads, transport/API doubles. This count is not
        # a production latency claim or a proof of GitHub permissions/locking.
        with mock.patch.object(self.memory, "page", wraps=self.memory.page) as page, \
                mock.patch.object(self.memory, "page_after", wraps=self.memory.page_after) as delta:
            delivered = self.fresh().deliver(self.api, self.report)
            self.assertLessEqual(page.call_count, 3,
                "why: the four appends re-read the complete history instead of their authenticated delta "
                f"(complete reads: {page.call_count}; the per-append rule performs 10); "
                "remedy: verify the history once per process and authenticate only new events")
            self.assertGreater(delta.call_count, 0,
                "why: appends skipped the authenticated delta read; remedy: verify every new event")
        self.assertEqual(delivered["status"], "delivered")
        state = self.fresh().load()
        row = next(iter(state["deliveries"].values()))
        self.assertEqual(row["status"], "delivered")
        self.assertEqual(row["receipt"], delivered["receipt"])
        self.assertEqual(self.api.issues[0]["body"], row["payload"]["issue_body"])
        self.assertEqual(self.api.issues[0]["number"], delivered["receipt"]["issue_number"])
        self.assertEqual(self.fresh().deliver(self.api, self.report), delivered)
        self.assertEqual(len(self.posts()), 1)

    def test_missing_or_incomplete_append_result_cannot_authorize_business_post(self):
        for invalid in (None, [], {"events": []}):
            with self.subTest(invalid=invalid):
                self.memory, self.api = Memory(), FakeGitHubApi()
                driver = self.fresh()
                append = driver.journal.append
                def lose_result(event):
                    append(event)
                    return deepcopy(invalid)
                with mock.patch.object(driver.journal, "append", side_effect=lose_result):
                    with self.assertRaisesRegex(outbox.OutboxBlocked, "why:.*remedy:"):
                        driver.deliver(self.api, self.report)
                self.assertFalse(self.posts())
                self.assertEqual(driver.state["generation"], 0)
                # The queue really persisted, but the failed caller could not
                # prove it. A fresh reader can recover it, without a lost claim.
                self.assertEqual([e["type"] for e in self.memory.journal().load()], ["queue"])
                self.assertEqual(self.fresh().drain_once(self.api)["status"], "delivered")
                self.assertEqual(len(self.posts()), 1)

    def test_changed_prior_history_in_append_result_cannot_publish_expected_state(self):
        self.fresh().deliver(self.api, self.report)
        driver = self.fresh()
        append = driver.journal.append
        def changed_history(event):
            committed = append(event)
            committed[0]["data"]["payload"]["issue_body"] += "changed"
            return committed
        with mock.patch.object(driver.journal, "append", side_effect=changed_history):
            with self.assertRaisesRegex(outbox.OutboxBlocked, "why:.*remedy:"):
                driver.deliver(self.api, replace(self.report, observation="new"))
        self.assertEqual(driver.state["generation"], 4)
        self.assertEqual(len(self.posts()), 1)

    def test_lock_lost_after_verified_append_cannot_authorize_business_post(self):
        driver = self.fresh()
        append = driver.journal.append
        def release_lock(event):
            committed = append(event)
            self.memory.lock = False
            return committed
        with mock.patch.object(driver.journal, "append", side_effect=release_lock):
            with self.assertRaisesRegex(outbox.OutboxBlocked, "why:.*remedy:"):
                driver.deliver(self.api, self.report)
        self.assertFalse(self.posts())
        self.assertEqual(driver.state["generation"], 0)

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

    def test_unknown_transition_fails_closed_without_mutating_reducer_state(self):
        state = outbox.new_state("report-epoch")
        event = {"id": "outbox:report-epoch:0", "epoch": "report-epoch", "generation": 0,
                 "type": "unknown-transition", "data": {}}
        with self.assertRaisesRegex(outbox.OutboxBlocked, "unknown outbox transition"):
            outbox.reduce(state, event)
        self.assertEqual(state, outbox.new_state("report-epoch"))

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

    def strand(self, *, posted):
        """Persist a claim whose business POST outcome is unknown (gen-879 shape)."""
        original = self.api.create_issue
        def lost(**kwargs):
            if posted:
                original(**kwargs)
            raise Crash()
        self.api.create_issue = lost
        with self.assertRaises(Crash):
            self.fresh().deliver(self.api, self.report)
        self.api.create_issue = original
        state = self.fresh().load()
        key, row = next(iter(state["deliveries"].items()))
        self.assertEqual(row["status"], "claimed")
        self.assertIsNone(row["ack"])
        return key, row["claim"]["digest"]

    def command(self, key, digest, resolution):
        return {"delivery": key, "claim_digest": digest, "resolution": resolution}

    def test_reconcile_claim_requires_closed_command_and_exact_audited_claim(self):
        key, digest = self.strand(posted=False)
        for command in (None, [], "absent",
                        {"delivery": key, "claim_digest": digest},
                        {"delivery": key, "claim_digest": digest, "resolution": {"kind": "absent"}, "extra": 1},
                        {"delivery": "g" * 64, "claim_digest": digest, "resolution": {"kind": "absent"}},
                        {"delivery": key[:-1].upper() + key[-1], "claim_digest": digest, "resolution": {"kind": "absent"}},
                        {"delivery": "0" * 64, "claim_digest": digest, "resolution": {"kind": "absent"}},
                        {"delivery": key, "claim_digest": "0" * 64, "resolution": {"kind": "absent"}},
                        {"delivery": key, "claim_digest": digest, "resolution": {"kind": "unknown"}},
                        {"delivery": key, "claim_digest": digest, "resolution": {"kind": "absent", "issue_number": 9}},
                        {"delivery": key, "claim_digest": digest, "resolution": {"kind": "receipt", "issue_number": 901}},
                        {"delivery": key, "claim_digest": digest, "resolution": {"kind": "receipt", "issue_number": 0, "comment_id": None}},
                        {"delivery": key, "claim_digest": digest, "resolution": {"kind": "receipt", "issue_number": 901, "comment_id": 0}},
                        {"delivery": key, "claim_digest": digest,
                         "resolution": {"kind": "receipt", "issue_number": 901, "comment_id": None, "x": 1}}):
            with self.subTest(command=command):
                with self.assertRaisesRegex(outbox.OutboxBlocked, "why:.*remedy:"):
                    self.fresh().reconcile_claim(self.api, command)
                self.assertEqual(self.fresh().load()["deliveries"][key]["status"], "claimed")
        self.assertFalse(self.posts())

    def test_claim_cleared_reducer_transition_is_exact(self):
        key, digest = self.strand(posted=False)
        before = self.fresh().load()
        event = {"id": "outbox:report-epoch:2", "epoch": "report-epoch", "generation": 2,
                 "type": "claim-cleared", "data": {"delivery": key, "claim_digest": digest, "why": "audited absence"}}
        cleared = outbox.reduce(before, event)
        self.assertEqual(cleared["deliveries"][key]["status"], "queued")
        self.assertIsNone(cleared["deliveries"][key]["claim"])
        self.assertEqual(before["deliveries"][key]["status"], "claimed")
        for data in ({"delivery": key, "claim_digest": "0" * 64, "why": "x"},
                     {"delivery": key, "claim_digest": digest, "why": ""},
                     {"delivery": key, "claim_digest": digest, "why": "x", "extra": 1},
                     {"delivery": "0" * 64, "claim_digest": digest, "why": "x"}):
            with self.subTest(data=data):
                with self.assertRaisesRegex(outbox.OutboxBlocked, "why:.*remedy:"):
                    outbox.reduce(before, {**event, "data": data})
        self.memory, self.api = Memory(), FakeGitHubApi()
        delivered = self.fresh().deliver(self.api, self.report)
        self.assertEqual(delivered["status"], "delivered")
        key = outbox.batch.digest({"key": self.report.key, "observation": self.report.observation})
        with self.assertRaisesRegex(outbox.OutboxBlocked, "why:.*remedy:"):
            outbox.reduce(self.fresh().load(), {"id": "outbox:report-epoch:9", "epoch": "report-epoch",
                "generation": 4, "type": "claim-cleared",
                "data": {"delivery": key, "claim_digest": digest, "why": "x"}})

    def test_absent_reconcile_requeues_and_ordinary_path_rederives_identical_claim(self):
        key, digest = self.strand(posted=False)
        answer = self.fresh().reconcile_claim(self.api, self.command(key, digest, {"kind": "absent"}))
        self.assertEqual(answer, {"status": "claim-cleared", "delivery": key})
        self.assertFalse(self.posts())
        self.assertEqual([e["type"] for e in self.memory.journal().load()], ["queue", "claim", "claim-cleared"])
        with self.assertRaisesRegex(outbox.OutboxBlocked, "why:.*remedy:"):
            self.fresh().reconcile_claim(self.api, self.command(key, digest, {"kind": "absent"}))
        answer = self.fresh().deliver(self.api, self.report)
        self.assertEqual(answer["status"], "delivered")
        self.assertEqual(len(self.posts()), 1)
        events = self.memory.journal().load()
        self.assertEqual([e["type"] for e in events],
                         ["queue", "claim", "claim-cleared", "claim", "ack", "delivered"])
        claims = [e["data"] for e in events if e["type"] == "claim"]
        self.assertEqual(len(claims), 2)
        self.assertEqual(claims[0], claims[1])

    def test_absent_reconcile_refused_while_receipt_visible(self):
        key, digest = self.strand(posted=True)
        with self.assertRaisesRegex(outbox.OutboxBlocked, "why:.*remedy:"):
            self.fresh().reconcile_claim(self.api, self.command(key, digest, {"kind": "absent"}))
        self.assertEqual(self.fresh().load()["deliveries"][key]["status"], "claimed")
        self.assertEqual(len(self.posts()), 1)

    def test_receipt_reconcile_binds_the_exact_live_receipt(self):
        key, digest = self.strand(posted=True)
        number = self.api.issues[0]["number"]
        resolution = {"kind": "receipt", "issue_number": number, "comment_id": None}
        answer = self.fresh().reconcile_claim(self.api, self.command(key, digest, resolution))
        self.assertEqual(answer, {"status": "delivered", "delivery": key,
                                  "receipt": {"issue_number": number, "comment_id": None}})
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual([e["type"] for e in self.memory.journal().load()], ["queue", "claim", "delivered"])
        self.assertEqual(self.fresh().recover(self.api), {"status": "ready"})
        self.assertEqual(self.fresh().deliver(self.api, self.report)["status"], "delivered")
        self.assertEqual(len(self.posts()), 1)

    def test_receipt_reconcile_rejects_a_mismatched_or_forged_receipt(self):
        key, digest = self.strand(posted=True)
        number = self.api.issues[0]["number"]
        with self.assertRaisesRegex(outbox.OutboxBlocked, "why:.*remedy:"):
            self.fresh().reconcile_claim(self.api, self.command(
                key, digest, {"kind": "receipt", "issue_number": number + 100, "comment_id": None}))
        self.api.issues[0]["body"] += "forged"
        with self.assertRaisesRegex(outbox.OutboxBlocked, "why:.*remedy:"):
            self.fresh().reconcile_claim(self.api, self.command(
                key, digest, {"kind": "receipt", "issue_number": number, "comment_id": None}))
        self.api.issues[0]["body"] = self.api.issues[0]["body"][:-6]
        self.api.issues[0]["user"] = {"login": "human", "type": "User"}
        with self.assertRaisesRegex(outbox.OutboxBlocked, "why:.*remedy:"):
            self.fresh().reconcile_claim(self.api, self.command(
                key, digest, {"kind": "receipt", "issue_number": number, "comment_id": None}))
        self.assertEqual(self.fresh().load()["deliveries"][key]["status"], "claimed")
        self.assertEqual(len(self.posts()), 1)

    def test_absent_reconcile_never_clears_an_acknowledged_write(self):
        # The business POST really persisted and its ack is durable; only the
        # delivered confirmation is missing. Build that exact state directly.
        issue = self.api.create_issue(title=self.report.title, body=self.report.issue_body("endaye"),
                                      labels=list(self.report.labels), assignees=["endaye"])
        driver = self.fresh()
        driver.load()
        key = outbox.batch.digest({"key": self.report.key, "observation": self.report.observation})
        payload = outbox.freeze(self.report, "endaye")
        driver._persist("queue", {"delivery": key, "payload": payload})
        operation = {"kind": "create-issue", "issue_number": None,
                     "payload": {"title": self.report.title, "body": payload["issue_body"],
                                 "labels": list(self.report.labels), "assignees": ["endaye"]}}
        operation["digest"] = outbox.batch.digest(operation)
        driver._persist("claim", {"delivery": key, "operation": operation})
        receipt = {"issue_number": issue["number"], "comment_id": None}
        driver._persist("ack", {"delivery": key, "receipt": receipt})
        row = self.fresh().load()["deliveries"][key]
        self.assertEqual(row["status"], "acknowledged")
        digest = row["claim"]["digest"]
        with self.assertRaisesRegex(outbox.OutboxBlocked, "acknowledged"):
            self.fresh().reconcile_claim(self.api, self.command(key, digest, {"kind": "absent"}))
        answer = self.fresh().reconcile_claim(self.api, self.command(
            key, digest, {"kind": "receipt", "issue_number": issue["number"], "comment_id": None}))
        self.assertEqual(answer["status"], "delivered")
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual([e["type"] for e in self.memory.journal().load()], ["queue", "claim", "ack", "delivered"])

    def test_absent_reconcile_of_comment_claim_rederives_one_comment(self):
        self.fresh().deliver(self.api, self.report)
        newer = replace(self.report, observation="52/1/suite/hash")
        original = self.api.create_comment
        self.api.create_comment = lambda number, body: (_ for _ in ()).throw(Crash())
        with self.assertRaises(Crash):
            self.fresh().deliver(self.api, newer)
        self.api.create_comment = original
        state = self.fresh().load()
        key = outbox.batch.digest({"key": newer.key, "observation": newer.observation})
        row = state["deliveries"][key]
        self.assertEqual((row["status"], row["claim"]["kind"]), ("claimed", "create-comment"))
        answer = self.fresh().reconcile_claim(self.api, self.command(key, row["claim"]["digest"], {"kind": "absent"}))
        self.assertEqual(answer["status"], "claim-cleared")
        answer = self.fresh().deliver(self.api, newer)
        self.assertEqual(answer["status"], "delivered")
        self.assertIsNotNone(answer["receipt"]["comment_id"])
        self.assertEqual([p[0] for p in self.posts()], ["create_issue", "create_comment"])

    def test_reconcile_claim_requires_the_writer_lock(self):
        key, digest = self.strand(posted=False)
        self.memory.lock = False
        with self.assertRaisesRegex(outbox.OutboxBlocked, "lock"):
            self.fresh().reconcile_claim(self.api, self.command(key, digest, {"kind": "absent"}))
        self.assertFalse(self.posts())


if __name__ == "__main__":
    unittest.main()
