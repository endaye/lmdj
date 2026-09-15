#!/usr/bin/env python3
"""The carrier maps sequence progress to driver observations without inventing passes."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.intent import IntentCommit, intent_operation_id  # noqa: E402
from tools.release.intent_carrier import (  # noqa: E402
    IntentBranch,
    IntentCarrier,
    IntentPrSequence,
    IntentPullRequest,
)
from tools.release.orchestration_driver import Observation  # noqa: E402

HEAD = "1" * 40
TREE = "2" * 40
TARGET = "3" * 40
REQUEST = "4" * 64


def spec_for_test(**changes):
    document = {"operation_id": intent_operation_id(REQUEST), "request_sha256": REQUEST,
                "repository_id": 12, "actor_id": 34, "target_revision": TARGET,
                "product_build": "1.0.57.0", "tag": "lmdj-v1.0.57.0",
                "snapshot_sha256": "5" * 64, "batch_reference": "batch-verdict-v1:zlib-base64:AAA",
                "batch_run_id": 4242}
    document.update(changes)
    return document


class CarrierFixture(unittest.TestCase):
    def setUp(self):
        self.container = tempfile.TemporaryDirectory()
        self.addCleanup(self.container.cleanup)
        self.root = Path(self.container.name).resolve()
        self.spec = spec_for_test()

    def new_commit(self, **changes):
        arguments = dict(root=self.root / "worktree", repository_root=self.root / "repo",
                         spec=self.spec, freeze=lambda root: None, author_name="Fixture",
                         author_email="fixture@example.invalid")
        arguments.update(changes)
        return IntentCommit(**arguments)

    def new_sequence(self):
        root = Path(self.container.name).resolve() / "sequence"
        branch = IntentBranch(root / "branch", root / "repo", token="FIXTURE-NOT-A-SECRET",
                              authorize=lambda spec: None)
        pr = IntentPullRequest(root / "pr", api=lambda *a, **k: None,
                               authorize=lambda spec: None, review=lambda *a: None,
                               verify_merged=lambda *a: None)
        return IntentPrSequence(root, branch=branch, pr=pr)

    def new_carrier(self, commit, sequence):
        return IntentCarrier(commit=commit, sequence=sequence)


class CarrierProtocolTest(CarrierFixture):
    def test_sequence_states_map_to_honest_observations(self):
        cases = [(("merged",), "verified"), (("absent",), "pending"), (("pending",), "pending"),
                 (("unknown",), "unknown"), (("conflict",), "conflict")]
        for (status,), expected in cases:
            sequence = self.new_sequence()
            sequence.observe = lambda spec, initialize=False, status=status: {
                "status": status, "phase": "pr", "evidence": None}
            sequence.pr.observe_merge = lambda spec: {
                "status": "verified", "merge": {"number": 7},
                "evidence": {"sha256": "5" * 64, "reference": "fixture"}}
            carrier = self.new_carrier(self.new_commit(), sequence)
            carrier._spec = self.spec
            observed = carrier.observe({}, {"step": "intent"})
            self.assertIsInstance(observed, Observation)
            self.assertEqual(observed.status, expected, status)

    def test_merged_sequence_without_verified_merge_is_unknown(self):
        sequence = self.new_sequence()
        sequence.observe = lambda spec, initialize=False: {"status": "merged", "phase": "pr",
                                                          "evidence": None}
        sequence.pr.observe_merge = lambda spec: {"status": "pending", "merge": None}
        carrier = self.new_carrier(self.new_commit(), sequence)
        carrier._spec = self.spec
        self.assertEqual(carrier.observe({}, {"step": "intent"}).status, "unknown")

    def test_observation_before_any_commit_is_pending_and_calls_nothing(self):
        sequence = self.new_sequence()
        sequence.observe = lambda *a, **k: self.fail("must not drive the sequence yet")
        carrier = self.new_carrier(self.new_commit(), sequence)
        self.assertEqual(carrier.observe({}, {"step": "intent"}).status, "pending")

    def test_restarted_carrier_recovers_the_spec_from_the_durable_commit(self):
        commit = self.new_commit()
        commit.root.mkdir(parents=True)
        commit.completed_head = lambda: HEAD
        commit._git = lambda *args: (HEAD + "\n").encode() if "^{tree}" not in args[-1] \
            else (TREE + "\n").encode()
        sequence = self.new_sequence()
        seen = {}

        def observe(spec, initialize=False):
            seen["spec"] = spec
            return {"status": "merged", "phase": "pr", "evidence": None}

        sequence.observe = observe
        sequence.pr.observe_merge = lambda spec: {
            "status": "verified", "merge": {"number": 11},
            "evidence": {"sha256": "6" * 64, "reference": "fixture"}}
        carrier = self.new_carrier(commit, sequence)
        observed = carrier.observe({}, {"step": "intent"})
        self.assertEqual(observed.status, "verified")
        self.assertEqual(seen["spec"]["head_sha"], HEAD)
        self.assertEqual(seen["spec"]["tree_sha"], TREE)

    def test_verified_merge_without_an_evidence_digest_is_refused(self):
        sequence = self.new_sequence()
        sequence.observe = lambda spec, initialize=False: {"status": "merged", "phase": "pr",
                                                          "evidence": None}
        sequence.pr.observe_merge = lambda spec: {"status": "verified", "merge": {"number": 7}}
        carrier = self.new_carrier(self.new_commit(), sequence)
        carrier._spec = self.spec
        with self.assertRaises(Exception) as caught:
            carrier.observe({}, {"step": "intent"})
        self.assertNotIn("0" * 64, str(caught.exception))

    def test_a_moved_commit_refreshes_the_cached_spec(self):
        commit = self.new_commit()
        commit.root.mkdir(parents=True)
        heads = [("1" * 40, "2" * 40), ("3" * 40, "4" * 40)]
        commit.completed_head = lambda: heads[0][0]
        commit._git = lambda *args: (heads[0][1] + "\n").encode()

        def git_tree(*args):
            return (heads.pop(0)[1] + "\n").encode()

        sequence = self.new_sequence()
        seen = []
        sequence.observe = lambda spec, initialize=False: (seen.append(spec["head_sha"]),
                                                          {"status": "pending", "phase": "pr"})[1]
        carrier = self.new_carrier(commit, sequence)
        carrier.observe({}, {"step": "intent"})
        commit._git = git_tree
        commit.completed_head = lambda: "3" * 40
        carrier.observe({}, {"step": "intent"})
        self.assertEqual(seen, ["1" * 40, "3" * 40])

    def test_advance_requires_the_durable_write_guard(self):
        carrier = self.new_carrier(self.new_commit(), self.new_sequence())
        with self.assertRaises(Exception):
            carrier.advance({}, {"step": "intent"}, before_write=None)


if __name__ == "__main__":
    unittest.main()
