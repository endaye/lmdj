#!/usr/bin/env python3
"""Protocol faults only; real GitHub visibility/editor semantics remain O1."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
from incremental_batch import digest
from incremental_batch_journal import IssueBodyAnchor, Journal, JournalBlocked


class MemoryTransport:
    """Test-only service. Not a production backend or claim of API atomicity."""
    def __init__(self):
        self.comments = []
        self.body = {"checkpoint": {"head": None, "pending": None}, "provenance": "trusted-run"}
        self.posts = 0
        self.body_writes = 0
        self.page_reads = 0
        self.delta_reads = 0
        self.fail_read = False
        self.lose_post_response = False
        self.reject_post = False
        self.hide_comments = False
        self.lose_commit_response = False

    def read_body(self, issue_id):
        if self.fail_read:
            raise OSError("state API unavailable")
        return deepcopy(self.body)

    def write_body(self, issue_id, checkpoint):
        self.body_writes += 1
        self.body = {"checkpoint": deepcopy(checkpoint), "provenance": "trusted-run"}
        if self.lose_commit_response and checkpoint["pending"] is None:
            raise OSError("checkpoint persisted but response lost")

    def append(self, issue_id, envelope):
        self.posts += 1
        if self.reject_post:
            raise OSError("POST outcome unknown")
        self.comments.append({"id": len(self.comments) + 1, "edited": False,
                              "envelope": deepcopy(envelope), "provenance": "trusted-run"})
        if self.lose_post_response:
            raise OSError("POST persisted but response lost")

    def page(self, issue_id, cursor):
        self.page_reads += 1
        if self.fail_read:
            raise OSError("state API unavailable")
        if self.hide_comments:
            return {"comments": [], "next": None, "cursor": None}
        start = int(cursor or 0)
        end = start + 1  # intentionally exercise every page
        rows = deepcopy(self.comments[start:end])
        return {"comments": rows,
                "next": str(end) if end < len(self.comments) else None,
                "cursor": str(end) if rows else None}

    def page_after(self, issue_id, cursor):
        self.delta_reads += 1
        if self.fail_read:
            raise OSError("state API unavailable")
        if self.hide_comments:
            return {"comments": [], "next": None, "cursor": None, "total": len(self.comments)}
        start = int(cursor)
        end = start + 1
        rows = deepcopy(self.comments[start:end])
        return {"comments": rows,
                "next": str(end) if end < len(self.comments) else None,
                "cursor": str(end) if rows else None,
                "total": len(self.comments)}

    def last(self, issue_id):
        if self.fail_read:
            raise OSError("state API unavailable")
        if self.hide_comments or not self.comments:
            return None
        return deepcopy(self.comments[-1])


class JournalTest(unittest.TestCase):
    def setUp(self):
        self.transport = MemoryTransport()
        self.lock = True
        self.authenticate = lambda record, issue: issue == 7 and record["provenance"] == "trusted-run"
        self.anchor = IssueBodyAnchor(7, self.transport, self.authenticate, lambda: self.lock)
        self.journal = Journal(7, self.transport, self.anchor, self.authenticate, lambda: self.lock)

    def append(self, number):
        return self.journal.append({"id": str(number), "epoch": "one", "generation": number,
                                    "type": "observe", "data": {"target": "a" * 40}})

    def test_complete_pagination_and_reopen(self):
        for number in range(4):
            self.append(number)
        reopened = Journal(7, self.transport, self.anchor, self.authenticate, lambda: self.lock)
        self.assertEqual(len(reopened.load()), 4,
                         "why: restart omitted journal pages; remedy: read every cursor before replay")

    def test_same_event_append_is_idempotent(self):
        self.append(0)
        self.append(0)
        self.assertEqual(self.transport.posts, 1, "why: duplicate event made another POST; remedy: compare recorded identity")

    def test_conflicting_event_id_is_rejected(self):
        self.append(0)
        with self.assertRaisesRegex(JournalBlocked, "reused"):
            self.journal.append({"id": "0", "different": True})

    def test_comment_tail_deletion_is_detected_by_checkpoint(self):
        self.append(0)
        self.append(1)
        self.transport.comments.pop()
        # In-process the verified prefix is not replayed, but a changed
        # inventory can never be absorbed into it.
        with self.assertRaisesRegex(JournalBlocked, "inventory changed"):
            self.journal.load()
        # Any later process replays the complete history and reports the
        # unanchored suffix itself.
        fresh = Journal(7, self.transport, self.anchor, self.authenticate, lambda: self.lock)
        with self.assertRaisesRegex(JournalBlocked, "suffix is missing"):
            fresh.load()

    def test_whole_comment_history_deletion_is_not_empty_state(self):
        self.append(0)
        self.transport.comments.clear()
        with self.assertRaisesRegex(JournalBlocked, "inventory changed"):
            self.journal.load()
        fresh = Journal(7, self.transport, self.anchor, self.authenticate, lambda: self.lock)
        with self.assertRaisesRegex(JournalBlocked, "suffix is missing"):
            fresh.load()

    def test_manually_edited_comment_is_rejected(self):
        self.append(0)
        self.transport.comments[0]["edited"] = True
        # The edit lands in the prefix this process already authenticated, so
        # it must be refused by the next complete replay, not silently adopted.
        fresh = Journal(7, self.transport, self.anchor, self.authenticate, lambda: self.lock)
        with self.assertRaisesRegex(JournalBlocked, "comment was edited"):
            fresh.load()

    def test_manual_checkpoint_edit_is_rejected(self):
        self.append(0)
        self.transport.body["provenance"] = "human-editor"
        with self.assertRaisesRegex(JournalBlocked, "last editor"):
            self.journal.load()

    def test_untrusted_comment_cannot_advance_checkpoint(self):
        self.transport.lose_post_response = True
        with self.assertRaises(JournalBlocked):
            self.append(0)
        self.transport.comments[0]["provenance"] = "other-workflow"
        with self.assertRaisesRegex(JournalBlocked, "untrusted journal"):
            self.journal.load()
        self.assertIsNone(self.anchor.read()["head"],
                          "why: untrusted tail became checkpoint; remedy: authenticate before adoption")

    def test_post_persisted_response_lost_is_adopted_without_second_post(self):
        self.transport.lose_post_response = True
        with self.assertRaises(JournalBlocked):
            self.append(0)
        self.assertIsNotNone(self.anchor.read()["pending"],
                             "why: lost response erased intent; remedy: retain prepared identity")
        events = self.journal.load()
        self.assertEqual(len(events), 1, "why: recovery lost persisted event; remedy: adopt exact pending identity")
        self.assertEqual(self.transport.posts, 1, "why: recovery duplicated POST; remedy: reconcile first")
        self.assertIsNone(self.anchor.read()["pending"],
                          "why: recovered event left pending transaction; remedy: advance checkpoint")

    def test_comment_visibility_delay_blocks_without_reposting(self):
        self.transport.hide_comments = True
        with self.assertRaisesRegex(JournalBlocked, "not yet visible"):
            self.append(0)
        with self.assertRaises(JournalBlocked):
            self.append(0)
        self.assertEqual(self.transport.posts, 1, "why: invisible POST retried; remedy: preserve launch uncertainty")
        self.transport.hide_comments = False
        self.assertEqual(len(self.journal.load()), 1, "why: later visible append not recovered; remedy: inspect pending")

    def test_post_unknown_and_absent_blocks_not_fake_success(self):
        self.transport.reject_post = True
        with self.assertRaises(JournalBlocked):
            self.append(0)
        with self.assertRaisesRegex(JournalBlocked, "uncertain"):
            self.journal.load()

    def test_checkpoint_response_loss_reopens_committed_event(self):
        self.transport.lose_commit_response = True
        with self.assertRaises(JournalBlocked):
            self.append(0)
        self.assertEqual(len(self.journal.load()), 1,
                         "why: durable checkpoint response loss lost progress; remedy: reread instead of repeat")
        self.assertEqual(self.transport.posts, 1, "why: checkpoint uncertainty duplicated event; remedy: replay read")

    def test_missing_anchor_never_infers_empty_cursor(self):
        journal = Journal(7, self.transport, None, self.authenticate, lambda: self.lock)
        with self.assertRaisesRegex(JournalBlocked, "checkpoint is unavailable"):
            journal.load()

    def test_deleted_checkpoint_never_rebuilds_from_comments_without_audit(self):
        self.append(0)
        self.transport.body = None
        with self.assertRaisesRegex(JournalBlocked, "checkpoint object is absent"):
            self.journal.load()

    def test_state_service_outage_performs_no_write(self):
        self.transport.fail_read = True
        with self.assertRaisesRegex(JournalBlocked, "state API unavailable"):
            self.append(0)
        self.assertEqual(self.transport.posts, 0, "why: unavailable state still admitted; remedy: fail closed")

    def test_missing_writer_lock_blocks_all_mutation(self):
        self.lock = False
        with self.assertRaisesRegex(JournalBlocked, "writer lock"):
            self.append(0)
        self.assertEqual(self.transport.body_writes, 0, "why: unlocked writer mutated checkpoint; remedy: shared lock")

    def test_corrupt_payload_digest_is_rejected(self):
        self.append(0)
        self.transport.comments[0]["envelope"]["event"]["generation"] = 999
        fresh = Journal(7, self.transport, self.anchor, self.authenticate, lambda: self.lock)
        with self.assertRaisesRegex(JournalBlocked, "digest mismatch"):
            fresh.load()

    def test_unanchored_tail_is_not_guessed(self):
        self.append(0)
        self.transport.body["checkpoint"] = {"head": None, "pending": None}
        with self.assertRaisesRegex(JournalBlocked, "unanchored"):
            self.journal.load()

    def test_stranded_pending_blocks_on_tail_peek_without_full_replay(self):
        self.append(0)
        self.transport.reject_post = True
        with self.assertRaises(JournalBlocked):
            self.append(1)
        self.transport.page_reads = 0
        with self.assertRaisesRegex(JournalBlocked, "uncertain"):
            self.journal.load()
        self.assertEqual(self.transport.page_reads, 0,
                         "why: blocked journal full-replays every health tick; remedy: fail fast on the tail peek")

    def test_reconcile_pending_clears_proven_absent_intent_and_recovers(self):
        self.append(0)
        self.transport.reject_post = True
        with self.assertRaises(JournalBlocked):
            self.append(1)
        digest = self.anchor.read()["pending"]["digest"]
        self.transport.delta_reads = 0
        events = self.journal.reconcile_pending(digest)
        self.assertEqual(len(events), 1, "why: drain lost committed history; remedy: clear only the stranded intent")
        self.assertGreater(self.transport.delta_reads, 0,
                           "why: absence claimed without authenticating the tail; remedy: prove against every comment")
        self.assertIsNone(self.anchor.read()["pending"],
                          "why: stranded intent survived the drain; remedy: restore the anchor after the absence proof")
        self.transport.reject_post = False
        self.append(1)
        self.assertEqual(len(self.journal.load()), 2,
                         "why: drained journal cannot accept new events; remedy: continue from the retained head")

    def test_reconcile_pending_requires_the_exact_audited_digest(self):
        self.transport.reject_post = True
        with self.assertRaises(JournalBlocked):
            self.append(0)
        with self.assertRaisesRegex(JournalBlocked, "different intent"):
            self.journal.reconcile_pending("0" * 64)
        self.assertIsNotNone(self.anchor.read()["pending"],
                             "why: wrong digest cleared the intent; remedy: bind the exact audited digest")

    def test_reconcile_pending_refuses_when_nothing_is_stranded(self):
        self.append(0)
        with self.assertRaisesRegex(JournalBlocked, "no stranded pending"):
            self.journal.reconcile_pending("0" * 64)

    def test_reconcile_pending_never_clears_a_persisted_event(self):
        self.transport.lose_post_response = True
        with self.assertRaises(JournalBlocked):
            self.append(0)
        digest = self.anchor.read()["pending"]["digest"]
        with self.assertRaisesRegex(JournalBlocked, "persisted"):
            self.journal.reconcile_pending(digest)
        self.assertIsNotNone(self.anchor.read()["pending"],
                             "why: committed event cleared by hand; remedy: ordinary load recovery adopts it")
        self.assertEqual(len(self.journal.load()), 1,
                         "why: ordinary recovery did not adopt the persisted event; remedy: inspect pending")

    def test_reconcile_pending_refuses_a_forked_intent(self):
        self.append(0)
        self.transport.reject_post = True
        with self.assertRaises(JournalBlocked):
            self.append(1)
        pending = self.anchor.read()["pending"]
        self.transport.body["checkpoint"]["pending"] = {**pending, "previous": "f" * 64}
        with self.assertRaisesRegex(JournalBlocked, "not the chain successor"):
            self.journal.reconcile_pending(pending["digest"])

    def test_in_process_appends_verify_the_history_once(self):
        for number in range(4):
            self.append(number)
        # One complete walk (the empty start plus its adoption), then deltas:
        # the old per-append rule re-read the whole history twice per append.
        self.assertEqual(self.transport.page_reads, 2,
                         "why: each append re-verified the complete history; remedy: verify it once per process")
        self.assertGreater(self.transport.delta_reads, 0,
                           "why: later appends skipped the authenticated tail; remedy: verify the delta")
        self.assertEqual([event["id"] for event in self.journal.load()], ["0", "1", "2", "3"],
                         "why: reuse dropped authenticated history; remedy: return cached prefix plus delta")

    def tail(self, previous, event, *, provenance="trusted-run", edited=False, digest_override=None):
        envelope = {"previous": previous, "event": dict(event)}
        envelope["digest"] = digest_override or digest({"previous": previous, "event": envelope["event"]})
        return {"id": len(self.transport.comments) + 1, "edited": edited,
                "envelope": envelope, "provenance": provenance}

    def test_incremental_read_rejects_every_tail_forgery(self):
        self.append(0)
        head = self.anchor.read()["head"]
        event = {"id": "1", "epoch": "one", "generation": 1, "type": "observe", "data": {"target": "a" * 40}}
        cases = {
            "edited": (self.tail(head, event, edited=True), "comment was edited"),
            "untrusted writer": (self.tail(head, event, provenance="human"), "untrusted journal writer"),
            "chain break": (self.tail("f" * 64, event), "missing or forked"),
            "digest tamper": (self.tail(head, event, digest_override="0" * 64), "digest mismatch"),
            "duplicate id": ({**self.tail(head, event), "id": self.transport.comments[0]["id"]},
                             "duplicate or invalid journal comment ID"),
        }
        for name, (tampered, message) in cases.items():
            with self.subTest(name=name):
                before = deepcopy(self.transport.comments)
                self.transport.comments.append(tampered)
                with self.assertRaisesRegex(JournalBlocked, message):
                    self.journal.load()
                self.transport.comments = before

    def test_incremental_read_rejects_a_changed_inventory(self):
        self.append(0)
        self.append(1)
        self.transport.comments = self.transport.comments[:1]
        with self.assertRaisesRegex(JournalBlocked, "inventory changed"):
            self.journal.load()

    def test_foreign_write_invalidates_the_cache(self):
        self.append(0)
        first = self.transport.page_reads
        other = Journal(7, self.transport, self.anchor, self.authenticate, lambda: self.lock)
        other.append({"id": "1", "epoch": "one", "generation": 1, "type": "observe", "data": {"target": "a" * 40}})
        events = self.journal.load()
        self.assertEqual([event["id"] for event in events], ["0", "1"],
                         "why: a foreign write was not seen; remedy: replay completely when the head moved")
        self.assertGreater(self.transport.page_reads, first,
                           "why: a foreign head was trusted as a delta base; remedy: re-verify the complete history")

    def test_reuse_matches_a_fresh_process(self):
        for number in range(3):
            self.append(number)
        reused = self.journal.load()
        fresh = Journal(7, self.transport, self.anchor, self.authenticate, lambda: self.lock)
        self.assertEqual(reused, fresh.load(),
                         "why: in-process reuse produced a different history; remedy: keep verification equivalent")


if __name__ == "__main__":
    unittest.main()
