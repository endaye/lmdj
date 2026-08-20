#!/usr/bin/env python3
"""Behavior tests for the serialized Integration Queue state machine."""

from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/ci/merge_queue.py"
SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
SHA_D = "d" * 40


def load_module():
    spec = importlib.util.spec_from_file_location("merge_queue", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load merge queue controller")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeClock:
    def __init__(self, value: float = 0.0):
        self.value = value

    def now(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class MergeQueueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mq = load_module()

    def request(self, **changes):
        request = self.mq.QueueRequest(
            repository="endaye/lmdj",
            pr_number=220,
            actor="endaye",
            event_head_sha=SHA_B,
            queue_run_id=123,
        )
        return replace(request, **changes)

    def pull(self, **changes):
        pull = self.mq.PullRequest(
            number=220,
            state="open",
            merged=False,
            draft=False,
            base_ref="main",
            base_sha=SHA_A,
            head_repository="endaye/lmdj",
            head_sha=SHA_B,
            title="feat(ci): serialize integration",
            labels=("merge:queue",),
            mergeable=True,
            merge_commit_sha=None,
        )
        return replace(pull, **changes)

    def client(self, **changes):
        mq = self.mq

        class FakeClient:
            permission = "write"
            pull = self.pull()
            main_sha = SHA_A
            changed_paths = ("packages/foundation/src/value.cpp",)
            ancestor = True
            ancestor_overrides = {}
            update_results = []
            validation_results = [
                mq.ValidationResult(
                    classification="valid",
                    run_id=9001,
                    run_status="completed",
                    run_conclusion="success",
                    run_event="workflow_dispatch",
                    workflow_path=".github/workflows/ci.yml",
                    head_sha=SHA_B,
                    manifest_mode="full",
                    trusted_head=True,
                    ticket="mq:123:1",
                    base_sha=SHA_A,
                    required_checks=(
                        mq.RequiredCheck("core (ubuntu-latest)", 15368, "success"),
                        mq.RequiredCheck("core (macos-latest)", 15368, "success"),
                        mq.RequiredCheck("PR Gate", 15368, "success"),
                    ),
                    queue_seconds=10,
                    execution_seconds=20,
                )
            ]
            dispatch_ids = [9001]
            merge_result = mq.MergeResult(merged=True, sha=SHA_C)
            head_tree = "tree-head"
            merge_tree = "tree-head"
            removed = []
            comments = []
            update_calls = []
            dispatch_calls = []
            validation_calls = []
            merge_calls = []

            def get_permission(inner, actor):
                return inner.permission

            def get_pull(inner, number):
                return inner.pull

            def get_main_sha(inner):
                return inner.main_sha

            def list_changed_paths(inner, number):
                return inner.changed_paths

            def is_ancestor(inner, base, head):
                return inner.ancestor_overrides.get((base, head), inner.ancestor)

            def update_branch(inner, number, expected_head_sha, timeout_seconds):
                inner.update_calls.append((number, expected_head_sha, timeout_seconds))
                if inner.update_results:
                    result = inner.update_results.pop(0)
                    if result.status == "accepted" and result.head_sha:
                        inner.pull = replace(inner.pull, head_sha=result.head_sha, base_sha=inner.main_sha)
                        inner.ancestor = True
                    return result
                raise AssertionError("unexpected update_branch call")

            def get_tree(inner, sha):
                return inner.merge_tree if sha == SHA_C else inner.head_tree

            def dispatch_validation(inner, number, head_ref, inputs):
                inner.dispatch_calls.append((number, head_ref, inputs))
                value = inner.dispatch_ids.pop(0)
                if isinstance(value, Exception):
                    raise value
                return value

            def wait_validation(inner, run_id, timeout_seconds):
                inner.validation_calls.append((run_id, timeout_seconds))
                return inner.validation_results.pop(0)

            def merge_pull(inner, number, payload):
                inner.merge_calls.append((number, payload))
                if inner.merge_result.merged:
                    inner.pull = replace(
                        inner.pull,
                        state="closed",
                        merged=True,
                        merge_commit_sha=inner.merge_result.sha,
                    )
                    inner.main_sha = inner.merge_result.sha
                return inner.merge_result

            def remove_label(inner, number, label):
                inner.removed.append((number, label))
                inner.pull = replace(
                    inner.pull,
                    labels=tuple(value for value in inner.pull.labels if value != label),
                )

            def create_review_comment(inner, number, body):
                inner.comments.append((number, body))

        client = FakeClient()
        for name, value in changes.items():
            setattr(client, name, value)
        return client

    def run_item(self, client, *, request=None, clock=None):
        clock = clock or FakeClock()
        return self.mq.run_queue_item(
            request or self.request(), client, clock=clock.now, sleeper=clock.sleep
        )

    def test_unauthorized_actor_fails_closed_and_revokes_label(self):
        client = self.client(permission="read")
        report = self.run_item(client)
        self.assertEqual(report.code, "unauthorized-actor")
        self.assertFalse(report.ok)
        self.assertEqual(client.removed, [(220, "merge:queue")])
        self.assertIn("unauthorized-actor", client.comments[0][1])

    def test_already_merged_duplicate_is_a_quiet_success(self):
        client = self.client(pull=self.pull(state="closed", merged=True, merge_commit_sha=SHA_C))
        report = self.run_item(client)
        self.assertEqual(report.code, "already-merged")
        self.assertTrue(report.ok)
        self.assertEqual(client.removed, [])
        self.assertEqual(client.comments, [])

    def test_closed_unmerged_pull_is_ineligible(self):
        report = self.run_item(self.client(pull=self.pull(state="closed")))
        self.assertEqual(report.code, "ineligible-pr")

    def test_every_eligibility_boundary_fails_closed(self):
        cases = (
            self.pull(draft=True),
            self.pull(base_ref="develop"),
            self.pull(head_repository="someone/fork"),
            self.pull(labels=()),
            self.pull(mergeable=False),
        )
        expected = (
            "ineligible-pr", "ineligible-pr", "ineligible-pr",
            "queue-label-removed", "merge-conflict",
        )
        self.assertEqual(
            [self.run_item(self.client(pull=pull)).code for pull in cases],
            list(expected),
        )

    def test_event_head_must_match_the_first_live_pull(self):
        report = self.run_item(self.client(pull=self.pull(head_sha=SHA_C)))
        self.assertEqual(report.code, "ineligible-pr")

    def test_control_plane_change_cannot_self_merge(self):
        for path in self.mq.CONTROL_PLANE_PATHS:
            with self.subTest(path=path):
                report = self.run_item(self.client(changed_paths=(path,)))
                self.assertEqual(report.code, "queue-control-plane-change")

    def test_dynamic_budget_reserves_reconciliation_time(self):
        self.assertEqual(
            self.mq.validation_budget_seconds(
                now=0, mutation_deadline=9 * 60, remaining_attempts=1
            ),
            0,
        )
        self.assertEqual(
            self.mq.validation_budget_seconds(
                now=0, mutation_deadline=330 * 60, remaining_attempts=3
            ),
            6400,
        )

    def test_budget_exhaustion_starts_no_mutation(self):
        clock = FakeClock(321 * 60)
        client = self.client()
        report = self.run_item(client, clock=clock)
        self.assertEqual(report.code, "queue-budget-exhausted")
        self.assertEqual(client.dispatch_calls, [])
        self.assertEqual(client.merge_calls, [])

    def test_update_branch_uses_expected_head_and_revalidates_new_head(self):
        update = self.mq.UpdateResult("accepted", SHA_D)
        validation = replace(
            self.client().validation_results[0], head_sha=SHA_D, ticket="mq:123:1"
        )
        client = self.client(
            ancestor=False,
            update_results=[update],
            validation_results=[validation],
        )
        report = self.run_item(client)
        self.assertTrue(report.ok)
        self.assertEqual(client.update_calls[0][1], SHA_B)
        self.assertEqual(client.dispatch_calls[0][1], SHA_D)
        self.assertEqual(client.dispatch_calls[0][2]["queue_base_sha"], SHA_A)

    def test_update_drift_consumes_an_attempt_but_never_repeats_blindly(self):
        update = self.mq.UpdateResult("drift", None)
        client = self.client(ancestor=False, update_results=[update])
        original_get_pull = client.get_pull
        calls = 0

        def get_pull(number):
            nonlocal calls
            calls += 1
            if calls >= 3:
                client.pull = replace(client.pull, head_sha=SHA_D)
                client.ancestor = True
            return original_get_pull(number)

        client.get_pull = get_pull
        client.validation_results[0] = replace(
            client.validation_results[0], head_sha=SHA_D, ticket="mq:123:2"
        )
        report = self.run_item(client)
        self.assertTrue(report.ok)
        self.assertEqual(report.attempts, 2)
        self.assertEqual(len(client.update_calls), 1)

    def test_update_conflict_timeout_and_uncertainty_have_stable_codes(self):
        cases = (
            ("conflict", "merge-conflict"),
            ("timeout", "update-branch-timeout"),
            ("uncertain", "merge-state-uncertain"),
        )
        for status, code in cases:
            with self.subTest(status=status):
                client = self.client(
                    ancestor=False,
                    update_results=[self.mq.UpdateResult(status, None)],
                )
                self.assertEqual(self.run_item(client).code, code)

    def test_dispatch_schema_mismatch_has_no_polling_fallback(self):
        client = self.client(
            dispatch_ids=[self.mq.DispatchContractError("missing workflow_run_id")]
        )
        report = self.run_item(client)
        self.assertEqual(report.code, "validation-dispatch-contract-mismatch")
        self.assertEqual(client.validation_calls, [])

    def test_validation_is_bound_to_exact_run_and_required_checks(self):
        invalid = replace(
            self.client().validation_results[0],
            required_checks=(
                self.mq.RequiredCheck("PR Gate", 999, "success"),
            ),
        )
        report = self.run_item(self.client(validation_results=[invalid]))
        self.assertEqual(report.code, "required-check-contract-mismatch")

    def test_live_confirmed_base_drift_retries_full_validation(self):
        drift = replace(
            self.client().validation_results[0],
            classification="queue-base-drift",
            run_status="completed",
            run_conclusion="failure",
        )
        valid = replace(
            self.client().validation_results[0],
            run_id=9002,
            base_sha=SHA_C,
            ticket="mq:123:2",
        )
        client = self.client(
            validation_results=[drift, valid],
            dispatch_ids=[9001, 9002],
        )
        original_wait = client.wait_validation

        def wait(run_id, timeout):
            result = original_wait(run_id, timeout)
            if result.classification == "queue-base-drift":
                client.main_sha = SHA_C
                client.pull = replace(client.pull, base_sha=SHA_C)
            return result

        client.wait_validation = wait
        report = self.run_item(client)
        self.assertTrue(report.ok)
        self.assertEqual(report.attempts, 2)
        self.assertEqual(report.validation_run_ids, (9001, 9002))

    def test_unconfirmed_drift_artifact_is_terminal_validation_failure(self):
        drift = replace(
            self.client().validation_results[0],
            classification="queue-base-drift",
            run_conclusion="failure",
        )
        report = self.run_item(self.client(validation_results=[drift]))
        self.assertEqual(report.code, "validation-failed")

    def test_ordinary_ci_failure_never_consumes_drift_retry(self):
        failed = replace(
            self.client().validation_results[0],
            classification="invalid",
            run_conclusion="failure",
        )
        report = self.run_item(self.client(validation_results=[failed]))
        self.assertEqual(report.code, "validation-failed")
        self.assertEqual(report.attempts, 1)

    def test_label_removed_after_validation_never_merges(self):
        client = self.client()
        original_wait = client.wait_validation

        def wait(run_id, timeout):
            result = original_wait(run_id, timeout)
            client.pull = replace(client.pull, labels=())
            return result

        client.wait_validation = wait
        report = self.run_item(client)
        self.assertEqual(report.code, "queue-label-removed")
        self.assertTrue(report.ok)
        self.assertEqual(client.merge_calls, [])

    def test_validation_timeout_has_its_own_terminal_code(self):
        timed_out = replace(
            self.client().validation_results[0],
            classification="timeout",
            run_status="in_progress",
            run_conclusion=None,
        )
        report = self.run_item(self.client(validation_results=[timed_out]))
        self.assertEqual(report.code, "validation-timeout")

    def test_merge_commit_must_descend_from_the_validated_base(self):
        client = self.client(ancestor_overrides={(SHA_A, SHA_C): False})
        report = self.run_item(client)
        self.assertEqual(report.code, "postcondition-mismatch")

    def test_squash_payload_and_postconditions_are_exact(self):
        client = self.client()
        report = self.run_item(client)
        self.assertEqual(report.code, "merged")
        self.assertEqual(report.merge_sha, SHA_C)
        self.assertEqual(
            client.merge_calls[0][1],
            {
                "merge_method": "squash",
                "sha": SHA_B,
                "commit_title": "feat(ci): serialize integration (#220)",
                "commit_message": "",
            },
        )

    def test_tree_mismatch_is_blocked_after_reconciliation(self):
        report = self.run_item(self.client(merge_tree="different-tree"))
        self.assertEqual(report.code, "postcondition-mismatch")
        self.assertEqual(report.status, "blocked-after-reconciliation")

    def test_finalize_aborted_is_idempotent_and_revokes_live_authority(self):
        client = self.client()
        report = self.mq.finalize_aborted(self.request(), client, existing_report=None)
        self.assertEqual(report.code, "queue-worker-aborted")
        self.assertEqual(client.removed, [(220, "merge:queue")])
        existing = self.mq.QueueReport(
            ok=True,
            status="merged",
            code="merged",
            attempts=1,
            observed_base_sha=SHA_A,
            observed_head_sha=SHA_B,
            validation_run_ids=(9001,),
            merge_sha=SHA_C,
            message="merged",
            evidence=(),
        )
        self.assertIs(self.mq.finalize_aborted(self.request(), client, existing), existing)


if __name__ == "__main__":
    unittest.main(verbosity=2)
