#!/usr/bin/env python3
"""Behavior tests for Merge Queue stall detection and reconciliation."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))

import merge_queue as mq  # noqa: E402
import merge_queue_watchdog as watchdog  # noqa: E402


SHA_A = "a" * 40
SHA_B = "b" * 40


class FakeClient:
    def __init__(self):
        self.pull = mq.PullRequest(
            number=220,
            state="open",
            merged=False,
            draft=False,
            base_ref="main",
            base_sha=SHA_A,
            head_repository="endaye/lmdj",
            head_sha=SHA_B,
            title="docs: harmless test",
            labels=(mq.QUEUE_LABEL,),
            mergeable=True,
            merge_commit_sha=None,
            head_ref="docs/stall-probe",
        )
        self.label_event = watchdog.LabelEvent(88, 100.0)
        self.active = False
        self.comments = []
        self.removed = []

    def list_labeled_pulls(self, label):
        return (self.pull,) if label in self.pull.labels else ()

    def latest_label_event(self, number, label):
        return self.label_event

    def has_active_queue_run(self, number, since):
        return self.active

    def get_pull(self, number):
        return self.pull

    def list_review_comments(self, number):
        return tuple(self.comments)

    def remove_label(self, number, label):
        self.removed.append((number, label))
        self.pull = replace(self.pull, labels=())

    def create_review_comment(self, number, body):
        self.comments.append(body)


class WatchdogTest(unittest.TestCase):
    def test_young_label_and_active_run_are_not_stalled(self):
        client = FakeClient()
        self.assertEqual(watchdog.find_stalled_items(client, now=1299), ())
        client.active = True
        self.assertEqual(watchdog.find_stalled_items(client, now=1400), ())

    def test_old_label_without_active_run_is_stalled(self):
        client = FakeClient()
        items = watchdog.find_stalled_items(client, now=1400)
        self.assertEqual(items, (watchdog.StalledItem(220, 88, 100.0, SHA_B),))

    def test_reconcile_rereads_live_state_and_removes_authority_once(self):
        client = FakeClient()
        item = watchdog.StalledItem(220, 88, 100.0, SHA_B)
        report = watchdog.reconcile_stalled_item(client, item)
        self.assertEqual(report.code, "queue-stalled")
        self.assertEqual(client.removed, [(220, "merge:queue")])
        self.assertIn("lmdj-merge-queue:queue-stalled:88", client.comments[0])

        second = watchdog.reconcile_stalled_item(client, item)
        self.assertEqual(second.code, "queue-label-removed")
        self.assertEqual(len(client.comments), 1)

    def test_merged_or_changed_head_is_a_benign_noop(self):
        item = watchdog.StalledItem(220, 88, 100.0, SHA_B)
        merged = FakeClient()
        merged.pull = replace(merged.pull, state="closed", merged=True)
        self.assertEqual(
            watchdog.reconcile_stalled_item(merged, item).code,
            "already-merged",
        )
        changed = FakeClient()
        changed.pull = replace(changed.pull, head_sha="c" * 40)
        self.assertEqual(
            watchdog.reconcile_stalled_item(changed, item).code,
            "queue-stall-state-changed",
        )
        self.assertEqual(changed.removed, [])

    def test_existing_marker_prevents_duplicate_review(self):
        client = FakeClient()
        client.comments.append("<!-- lmdj-merge-queue:queue-stalled:88 -->")
        item = watchdog.StalledItem(220, 88, 100.0, SHA_B)
        report = watchdog.reconcile_stalled_item(client, item)
        self.assertEqual(report.code, "queue-stalled")
        self.assertEqual(len(client.comments), 1)

    def test_cli_writes_a_closed_watchdog_report(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "watchdog.json"
            summary_path = Path(directory) / "watchdog.md"
            exit_code = watchdog.run_cli(
                [
                    "--repository", "endaye/lmdj",
                    "--report", str(report_path),
                    "--summary", str(summary_path),
                ],
                environ={"GITHUB_TOKEN": "token"},
                client_factory=lambda _repository, _token: client,
                clock=lambda: 1400.0,
            )
            self.assertEqual(exit_code, 1)
            document = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(document["reports"][0]["code"], "queue-stalled")
            self.assertIn("queue-stalled", summary_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
