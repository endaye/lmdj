#!/usr/bin/env python3
"""Behavior tests for the serialized Integration Queue state machine."""

from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/ci/merge_queue.py"
SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
SHA_D = "d" * 40
SAFE_VALIDATION_EVIDENCE = re.compile(
    r"^(?:check:(?:core \(ubuntu-latest\)|core \(macos-latest\)|PR Gate)="
    r"(?:failure|cancelled|skipped|timed_out|None)|"
    r"missing:(?:core \(ubuntu-latest\)|core \(macos-latest\)|PR Gate)|"
    r"app:(?:core \(ubuntu-latest\)|core \(macos-latest\)|PR Gate)=\d+|"
    r"duplicate:(?:core \(ubuntu-latest\)|core \(macos-latest\)|PR Gate)|"
    r"unexpected:required-check|"
    r"field:(?:run_id=invalid|run_event|workflow_path|head_sha|ticket|base_sha|"
    r"classification=(?:invalid|unexpected)|manifest_mode=(?:focused|None|invalid)|"
    r"trusted_head|run_status|run_conclusion))$"
)


def load_module():
    # merge_queue.py imports its sibling change_scope for the shared
    # merge-evidence predicate, which resolves from `scripts/ci` when the
    # controller runs as a script. Loading it here has to offer the same path
    # rather than depend on another test module having inserted it first.
    scripts_ci = str(MODULE_PATH.parent)
    if scripts_ci not in sys.path:
        sys.path.insert(0, scripts_ci)
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
            head_ref="feat/queue",
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
            sync_run_ids = [9101]
            merge_result = mq.MergeResult(merged=True, sha=SHA_C)
            head_tree = "tree-head"
            merge_tree = "tree-head"
            removed = []
            comments = []
            update_calls = []
            sync_authorization_calls = []
            dispatch_calls = []
            cancel_calls = []
            validation_calls = []
            merge_calls = []

            def get_permission(inner, actor):
                return inner.permission

            def get_pull(inner, number, *, timeout_seconds=None):
                del timeout_seconds
                return inner.pull

            def get_main_sha(inner, *, timeout_seconds=None):
                del timeout_seconds
                return inner.main_sha

            def list_changed_paths(inner, number):
                return inner.changed_paths

            def is_ancestor(inner, base, head, *, timeout_seconds=None):
                del timeout_seconds
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

            def get_tree(inner, sha, *, timeout_seconds=None):
                del timeout_seconds
                return inner.merge_tree if sha == SHA_C else inner.head_tree

            def authorize_sync_validation(
                inner, number, base_sha, head_sha, timeout_seconds
            ):
                inner.sync_authorization_calls.append(
                    (number, base_sha, head_sha, timeout_seconds)
                )
                value = inner.sync_run_ids.pop(0)
                if isinstance(value, Exception):
                    raise value
                return value

            def dispatch_validation(inner, number, head_ref, inputs):
                inner.dispatch_calls.append((number, head_ref, inputs))
                value = inner.dispatch_ids.pop(0)
                if isinstance(value, Exception):
                    raise value
                return value

            def cancel_validation(inner, run_id):
                inner.cancel_calls.append(run_id)

            superseded_pull_runs = ()
            superseded_cancel_calls = []

            def cancel_superseded_pull_runs(inner, head_sha):
                inner.superseded_cancel_calls.append(head_sha)
                if isinstance(inner.superseded_pull_runs, Exception):
                    raise inner.superseded_pull_runs
                return tuple(inner.superseded_pull_runs)

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

    def run_item(self, client, *, request=None, clock=None, sleeper=None):
        clock = clock or FakeClock()
        return self.mq.run_queue_item(
            request or self.request(),
            client,
            clock=clock.now,
            sleeper=sleeper or clock.sleep,
        )

    def test_unauthorized_actor_fails_closed_and_revokes_label(self):
        client = self.client(permission="read")
        report = self.run_item(client)
        self.assertEqual(report.code, "unauthorized-actor")
        self.assertFalse(report.ok)
        self.assertEqual(client.removed, [(220, "merge:queue")])
        self.assertIn("unauthorized-actor", client.comments[0][1])
        self.assertNotIn("Evidence:", client.comments[0][1])

    def test_cleanup_retries_transient_errors_with_backoff(self):
        client = self.client(permission="read")
        original_comment = client.create_review_comment
        comment_attempts = 0
        delays = []

        def create_review_comment(number, body):
            nonlocal comment_attempts
            comment_attempts += 1
            if comment_attempts < 3:
                raise RuntimeError("temporary GitHub error")
            original_comment(number, body)

        client.create_review_comment = create_review_comment
        report = self.run_item(client, sleeper=delays.append)
        self.assertEqual(comment_attempts, 3)
        self.assertEqual(len(client.comments), 1)
        self.assertEqual(report.evidence, ())
        self.assertEqual(delays, [2, 4])

    def test_comment_loss_never_blocks_label_removal_and_is_named(self):
        client = self.client(permission="read")

        class GitHubApiError(RuntimeError):
            pass

        def create_review_comment(number, body):
            del number, body
            raise GitHubApiError("comment unavailable")

        client.create_review_comment = create_review_comment
        report = self.run_item(client, sleeper=lambda _seconds: None)
        self.assertEqual(report.code, "unauthorized-actor")
        self.assertEqual(client.removed, [(220, "merge:queue")])
        self.assertIn("cleanup-error:comment:GitHubApiError", report.evidence)

    def test_label_removal_failure_still_attempts_the_comment(self):
        client = self.client(permission="read")
        label_attempts = 0
        delays = []

        class GitHubApiError(RuntimeError):
            pass

        def remove_label(number, label):
            nonlocal label_attempts
            del number, label
            label_attempts += 1
            raise GitHubApiError("label removal unavailable")

        client.remove_label = remove_label
        report = self.run_item(client, sleeper=delays.append)
        self.assertEqual(report.code, "unauthorized-actor")
        self.assertEqual(label_attempts, 3)
        self.assertEqual(delays, [2, 4])
        self.assertEqual(len(client.comments), 1)
        self.assertEqual(
            report.evidence,
            ("cleanup-error:remove-label:GitHubApiError",),
        )

    def test_cleanup_pull_read_failure_still_attempts_terminal_comment(self):
        client = self.client(permission="read")
        original_get_pull = client.get_pull
        pull_reads = 0
        delays = []

        class GitHubApiError(RuntimeError):
            pass

        def get_pull(number, *, timeout_seconds=None):
            nonlocal pull_reads
            pull_reads += 1
            if pull_reads > 1:
                raise GitHubApiError("pull unavailable")
            return original_get_pull(number, timeout_seconds=timeout_seconds)

        client.get_pull = get_pull
        report = self.run_item(client, sleeper=delays.append)
        self.assertEqual(report.code, "unauthorized-actor")
        self.assertEqual(client.removed, [])
        self.assertEqual(len(client.comments), 1)
        self.assertEqual(
            report.evidence,
            ("cleanup-error:remove-label:GitHubApiError",),
        )
        self.assertEqual(delays, [2, 4])

    def test_cleanup_is_a_noop_when_live_state_proves_label_absent(self):
        client = self.client(permission="read")
        original_get_pull = client.get_pull
        pull_reads = 0

        def get_pull(number, *, timeout_seconds=None):
            nonlocal pull_reads
            pull_reads += 1
            pull = original_get_pull(number, timeout_seconds=timeout_seconds)
            if pull_reads > 1:
                return replace(pull, labels=())
            return pull

        client.get_pull = get_pull
        report = self.run_item(client)
        self.assertEqual(report.code, "unauthorized-actor")
        self.assertEqual(report.evidence, ())
        self.assertEqual(client.removed, [])
        self.assertEqual(client.comments, [])

    def test_both_cleanup_failures_preserve_preexisting_evidence(self):
        client = self.client(permission="read")

        class GitHubApiError(RuntimeError):
            pass

        def remove_label(number, label):
            del number, label
            raise GitHubApiError("label unavailable")

        def create_review_comment(number, body):
            del number, body
            raise TimeoutError("comment unavailable")

        client.remove_label = remove_label
        client.create_review_comment = create_review_comment
        report = self.mq._cleanup_failure(
            self.request(),
            client,
            self.mq._report(
                code="validation-failed",
                evidence=("field:run_status",),
            ),
            sleeper=lambda _seconds: None,
        )
        self.assertEqual(
            report.evidence,
            (
                "field:run_status",
                "cleanup-error:remove-label:GitHubApiError",
                "cleanup-error:comment:TimeoutError",
            ),
        )

    def test_summary_carries_evidence_when_cleanup_degrades(self):
        report = self.mq.QueueReport(
            ok=False,
            status="blocked",
            code="unauthorized-actor",
            attempts=0,
            observed_base_sha=SHA_A,
            observed_head_sha=SHA_B,
            validation_run_ids=(),
            merge_sha=None,
            message="unauthorized-actor",
            evidence=("cleanup-error:comment:GitHubApiError",),
        )
        self.assertIn(
            "- Evidence: cleanup-error:comment:GitHubApiError",
            self.mq.render_markdown(report),
        )

    def test_summary_redacts_hostile_evidence_but_keeps_safe_diagnostics(self):
        report = self.mq.QueueReport(
            ok=False,
            status="blocked",
            code="validation-failed",
            attempts=1,
            observed_base_sha=SHA_A,
            observed_head_sha=SHA_B,
            validation_run_ids=(9001,),
            merge_sha=None,
            message="validation-failed",
            evidence=(
                "missing:PR Gate",
                "check:PR Gate=invalid",
                "cleanup-error:comment:GitHubApiError",
                "/Users/endaye/Projects/lmdj/private.txt",
                "https://api.github.com/repos/endaye/lmdj",
                "token=ghp_super_secret",
                '{"message":"raw merge API response"}',
            ),
        )
        rendered = self.mq.render_markdown(report)
        self.assertIn("missing:PR Gate", rendered)
        self.assertIn("check:PR Gate=invalid", rendered)
        self.assertIn("cleanup-error:comment:GitHubApiError", rendered)
        self.assertIn("evidence-redacted", rendered)
        for hostile in (
            "/Users/endaye",
            "api.github.com",
            "ghp_super_secret",
            "raw merge API response",
        ):
            self.assertNotIn(hostile, rendered)

    def test_terminal_comment_redacts_hostile_evidence_but_keeps_safe_diagnostics(self):
        client = self.client()
        self.mq._cleanup_failure(
            self.request(),
            client,
            self.mq._report(
                code="validation-failed",
                evidence=(
                    "check:PR Gate=failure",
                    "/Users/endaye/Projects/lmdj/private.txt",
                    "https://api.github.com/repos/endaye/lmdj",
                    "token=ghp_super_secret",
                    '{"message":"raw merge API response"}',
                ),
            ),
            sleeper=lambda _seconds: None,
        )
        self.assertEqual(len(client.comments), 1)
        body = client.comments[0][1]
        self.assertIn("Evidence: `check:PR Gate=failure`, `evidence-redacted`", body)
        for hostile in (
            "/Users/endaye",
            "api.github.com",
            "ghp_super_secret",
            "raw merge API response",
        ):
            self.assertNotIn(hostile, body)

    def test_summary_with_empty_evidence_is_exactly_backward_compatible(self):
        report = self.mq.QueueReport(
            ok=False,
            status="blocked",
            code="unauthorized-actor",
            attempts=0,
            observed_base_sha=SHA_A,
            observed_head_sha=SHA_B,
            validation_run_ids=(),
            merge_sha=None,
            message="unauthorized-actor",
            evidence=(),
        )
        self.assertEqual(
            self.mq.render_markdown(report),
            "\n".join((
                "## Integration Queue",
                "",
                "- Status: `blocked`",
                "- Code: `unauthorized-actor`",
                "- Attempts: `0`",
                f"- Base/head: `{SHA_A}` / `{SHA_B}`",
                "- Validation runs: ``",
                "- Merge SHA: `None`",
                "- Message: unauthorized-actor",
                "",
            )),
        )

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
                now=0, mutation_deadline=39 * 60, remaining_attempts=1
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
        clock = FakeClock(300 * 60)
        client = self.client()
        report = self.run_item(client, clock=clock)
        self.assertEqual(report.code, "queue-budget-exhausted")
        self.assertEqual(client.dispatch_calls, [])
        self.assertEqual(client.merge_calls, [])

    def test_attempt_below_measured_validation_floor_never_dispatches(self):
        clock = FakeClock(233 * 60)
        client = self.client()
        report = self.run_item(client, clock=clock)
        self.assertEqual(report.code, "queue-budget-exhausted")
        self.assertEqual(client.dispatch_calls, [])

    def test_update_branch_uses_expected_head_and_revalidates_new_head(self):
        update = self.mq.UpdateResult("accepted", SHA_D)
        validation = replace(
            self.client().validation_results[0],
            run_id=9101,
            run_event="pull_request",
            head_sha=SHA_D,
            ticket=None,
        )
        client = self.client(
            ancestor=False,
            update_results=[update],
            validation_results=[validation],
        )
        report = self.run_item(client)
        self.assertTrue(report.ok)
        self.assertEqual(client.update_calls[0][1], SHA_B)
        self.assertEqual(
            client.sync_authorization_calls,
            [(220, SHA_A, SHA_D, 600)],
        )
        self.assertEqual(client.dispatch_calls, [])
        self.assertEqual(client.validation_calls[0][0], 9101)

    def test_sync_validation_approval_failure_has_a_stable_terminal_code(self):
        client = self.client(
            ancestor=False,
            update_results=[self.mq.UpdateResult("accepted", SHA_D)],
            sync_run_ids=[RuntimeError("approval unavailable")],
        )
        report = self.run_item(client)
        self.assertEqual(report.code, "sync-validation-approval-failed")
        self.assertEqual(client.dispatch_calls, [])

    def test_update_drift_consumes_an_attempt_but_never_repeats_blindly(self):
        update = self.mq.UpdateResult("drift", None)
        client = self.client(ancestor=False, update_results=[update])
        original_get_pull = client.get_pull
        calls = 0

        def get_pull(number, *, timeout_seconds=None):
            del timeout_seconds
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

    def test_failed_required_check_is_validation_failed_and_named(self):
        failed = replace(
            self.client().validation_results[0],
            required_checks=(
                self.mq.RequiredCheck("core (ubuntu-latest)", 15368, "success"),
                self.mq.RequiredCheck("core (macos-latest)", 15368, "success"),
                self.mq.RequiredCheck("PR Gate", 15368, "failure"),
            ),
        )
        client = self.client(validation_results=[failed])
        report = self.run_item(client)
        self.assertEqual(report.code, "validation-failed")
        self.assertNotEqual(report.code, "required-check-contract-mismatch")
        self.assertIn("check:PR Gate=failure", report.evidence)
        self.assert_evidence_is_safe(report)
        self.assertEqual(len(client.comments), 1)
        self.assertIn("Evidence: `check:PR Gate=failure`", client.comments[0][1])

    def test_missing_required_check_is_a_contract_mismatch_with_diff(self):
        missing = replace(
            self.client().validation_results[0],
            required_checks=(
                self.mq.RequiredCheck("core (ubuntu-latest)", 15368, "success"),
                self.mq.RequiredCheck("PR Gate", 15368, "success"),
            ),
        )
        report = self.run_item(self.client(validation_results=[missing]))
        self.assertEqual(report.code, "required-check-contract-mismatch")
        self.assertIn("missing:core (macos-latest)", report.evidence)
        self.assert_evidence_is_safe(report)

    def test_foreign_app_check_is_a_contract_mismatch_with_diff(self):
        foreign = replace(
            self.client().validation_results[0],
            required_checks=(
                self.mq.RequiredCheck("core (ubuntu-latest)", 15368, "success"),
                self.mq.RequiredCheck("core (macos-latest)", 15368, "success"),
                self.mq.RequiredCheck("PR Gate", 12345, "success"),
            ),
        )
        report = self.run_item(self.client(validation_results=[foreign]))
        self.assertEqual(report.code, "required-check-contract-mismatch")
        self.assertIn("app:PR Gate=12345", report.evidence)
        self.assert_evidence_is_safe(report)

    def test_duplicate_required_check_is_a_contract_mismatch_with_diff(self):
        duplicate = replace(
            self.client().validation_results[0],
            required_checks=(
                self.mq.RequiredCheck("core (ubuntu-latest)", 15368, "success"),
                self.mq.RequiredCheck("core (macos-latest)", 15368, "success"),
                self.mq.RequiredCheck("PR Gate", 15368, "success"),
                self.mq.RequiredCheck("PR Gate", 15368, "success"),
            ),
        )
        report = self.run_item(self.client(validation_results=[duplicate]))
        self.assertEqual(report.code, "required-check-contract-mismatch")
        self.assertIn("duplicate:PR Gate", report.evidence)
        self.assert_evidence_is_safe(report)

    def test_focused_validation_is_merge_evidence(self):
        # PR Gate adjudicates the same run against the manifest, failing both
        # when a selected job is not success and when an unselected job ran, so
        # a focused validation already proves every lane the change owed.
        focused = replace(
            self.client().validation_results[0], manifest_mode="focused"
        )
        report = self.run_item(self.client(validation_results=[focused]))
        self.assertEqual(report.code, "merged")

    def test_skippable_checks_stay_a_subset_that_excludes_pr_gate(self):
        # Listing the skippable checks explicitly is what makes a newly added
        # required check fail closed: it is not skippable until someone says
        # so. This pins the other half -- a stale name after a rename, and
        # PR Gate never becoming skippable, since it is what vouches for a
        # skip being owed.
        self.assertTrue(
            set(self.mq.SKIPPABLE_CHECKS)
            < set(self.mq.REQUIRED_CHECKS),
            "skippable checks must be a proper subset of required checks",
        )
        self.assertNotIn("PR Gate", self.mq.SKIPPABLE_CHECKS)

    def test_skipped_core_context_is_owed_only_because_pr_gate_vouches(self):
        # A focused manifest legitimately skips the Core contexts, so a skip
        # there is not a failure. PR Gate is what makes that safe: it fails
        # both when a selected job is not success and when an unselected job
        # ran anyway, so it is never allowed to be skipped itself.
        base = self.client().validation_results[0]
        for name in ("core (ubuntu-latest)", "core (macos-latest)"):
            with self.subTest(skipped=name):
                checks = tuple(
                    replace(check, conclusion="skipped")
                    if check.name == name else check
                    for check in base.required_checks
                )
                result = replace(
                    base, manifest_mode="focused", required_checks=checks
                )
                report = self.run_item(self.client(validation_results=[result]))
                self.assertEqual(report.code, "merged")

        checks = tuple(
            replace(check, conclusion="skipped")
            if check.name == "PR Gate" else check
            for check in base.required_checks
        )
        result = replace(base, manifest_mode="focused", required_checks=checks)
        report = self.run_item(self.client(validation_results=[result]))
        self.assertEqual(report.code, "validation-failed")
        self.assertIn("check:PR Gate=skipped", report.evidence)
        self.assert_evidence_is_safe(report)

    def test_unclassified_validation_mode_names_the_field(self):
        # Breadth must be known. A run that published no mode proves nothing
        # about which lanes were owed, and a `requested` lane selection is an
        # operator's choice rather than a classification of the change.
        for mode in (None, "requested", "draft"):
            with self.subTest(mode=mode):
                unclassified = replace(
                    self.client().validation_results[0], manifest_mode=mode
                )
                report = self.run_item(
                    self.client(validation_results=[unclassified])
                )
                self.assertEqual(report.code, "validation-failed")
                self.assertTrue(
                    any(e.startswith("field:manifest_mode=") for e in report.evidence),
                    report.evidence,
                )
                self.assert_evidence_is_safe(report)

    def assert_evidence_is_safe(self, report):
        for evidence in report.evidence:
            with self.subTest(evidence=evidence):
                self.assertRegex(evidence, SAFE_VALIDATION_EVIDENCE)

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

    def test_non_valid_validation_classification_never_merges(self):
        for classification, expected_evidence in (
            ("invalid", "field:classification=invalid"),
            ("future-classification", "field:classification=unexpected"),
        ):
            with self.subTest(classification=classification):
                result = replace(
                    self.client().validation_results[0],
                    classification=classification,
                )
                client = self.client(validation_results=[result])
                report = self.run_item(client)
                self.assertEqual(report.code, "validation-failed")
                self.assertIn(expected_evidence, report.evidence)
                self.assertEqual(client.merge_calls, [])
                self.assert_evidence_is_safe(report)

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

    def test_validation_timeout_cancels_the_dispatched_orphan(self):
        timed_out = replace(
            self.client().validation_results[0],
            classification="timeout",
            run_status="in_progress",
            run_conclusion=None,
        )
        client = self.client(validation_results=[timed_out])
        report = self.run_item(client)
        self.assertEqual(report.code, "validation-timeout")
        self.assertEqual(client.cancel_calls, [9001])

    def test_validation_timeout_never_cancels_a_synchronize_run(self):
        timed_out = replace(
            self.client().validation_results[0],
            classification="timeout",
            run_id=9101,
            run_status="in_progress",
            run_conclusion=None,
            run_event="pull_request",
            head_sha=SHA_D,
            ticket=None,
        )
        client = self.client(
            ancestor=False,
            update_results=[self.mq.UpdateResult("accepted", SHA_D)],
            validation_results=[timed_out],
        )
        report = self.run_item(client)
        self.assertEqual(report.code, "validation-timeout")
        self.assertEqual(client.dispatch_calls, [])
        self.assertEqual(client.cancel_calls, [])

    def test_cancel_failure_is_evidence_not_a_new_code(self):
        timed_out = replace(
            self.client().validation_results[0],
            classification="timeout",
            run_status="in_progress",
            run_conclusion=None,
        )
        client = self.client(validation_results=[timed_out])

        class GitHubApiError(RuntimeError):
            pass

        def cancel_validation(run_id):
            client.cancel_calls.append(run_id)
            raise GitHubApiError("cancel unavailable")

        client.cancel_validation = cancel_validation
        report = self.run_item(client)
        self.assertEqual(report.code, "validation-timeout")
        self.assertEqual(client.cancel_calls, [9001])
        self.assertIn("cancel-error:GitHubApiError", report.evidence)

    def test_wait_validation_failure_cancels_the_dispatched_run_and_cleans_up(self):
        client = self.client()
        secret_message = "token=ghp_WAIT_FAILURE_MUST_NOT_LEAK"

        class GitHubApiError(RuntimeError):
            pass

        def wait_validation(run_id, timeout_seconds):
            client.validation_calls.append((run_id, timeout_seconds))
            raise GitHubApiError(secret_message)

        client.wait_validation = wait_validation
        try:
            report = self.run_item(client)
        except Exception as error:
            self.fail(
                f"wait_validation escaped the controller: {type(error).__name__}"
            )
        self.assertEqual(report.code, "validation-observation-failed")
        self.assertEqual(report.evidence, ("GitHubApiError",))
        self.assertEqual(report.validation_run_ids, (9001,))
        self.assertEqual(client.cancel_calls, [9001])
        self.assertEqual(client.removed, [(220, "merge:queue")])
        self.assertEqual(len(client.comments), 1)
        for surface in (
            report.to_json(),
            self.mq.render_markdown(report),
            client.comments[0][1],
        ):
            self.assertNotIn(secret_message, surface)

    def test_wait_validation_failure_never_cancels_a_synchronize_run(self):
        client = self.client(
            ancestor=False,
            update_results=[self.mq.UpdateResult("accepted", SHA_D)],
        )

        def wait_validation(run_id, timeout_seconds):
            client.validation_calls.append((run_id, timeout_seconds))
            raise TimeoutError("synchronized observation unavailable")

        client.wait_validation = wait_validation
        try:
            report = self.run_item(client)
        except Exception as error:
            self.fail(
                f"wait_validation escaped the controller: {type(error).__name__}"
            )
        self.assertEqual(report.code, "validation-observation-failed")
        self.assertEqual(report.evidence, ("TimeoutError",))
        self.assertEqual(report.validation_run_ids, (9101,))
        self.assertEqual(client.dispatch_calls, [])
        self.assertEqual(client.cancel_calls, [])
        self.assertEqual(client.removed, [(220, "merge:queue")])
        self.assertEqual(len(client.comments), 1)

    def test_cancel_failure_preserves_wait_observation_failure_and_cleanup(self):
        client = self.client()

        class GitHubApiError(RuntimeError):
            pass

        class CancelError(RuntimeError):
            pass

        def wait_validation(run_id, timeout_seconds):
            client.validation_calls.append((run_id, timeout_seconds))
            raise GitHubApiError("raw observation response")

        def cancel_validation(run_id):
            client.cancel_calls.append(run_id)
            raise CancelError("raw cancellation response")

        client.wait_validation = wait_validation
        client.cancel_validation = cancel_validation
        try:
            report = self.run_item(client)
        except Exception as error:
            self.fail(
                f"wait_validation escaped the controller: {type(error).__name__}"
            )
        self.assertEqual(report.code, "validation-observation-failed")
        self.assertEqual(
            report.evidence,
            ("GitHubApiError", "cancel-error:CancelError"),
        )
        self.assertEqual(client.cancel_calls, [9001])
        self.assertEqual(client.removed, [(220, "merge:queue")])
        self.assertEqual(len(client.comments), 1)
        rendered = report.to_json() + self.mq.render_markdown(report)
        self.assertNotIn("raw observation response", rendered)
        self.assertNotIn("raw cancellation response", rendered)

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
        client = self.client(merge_tree="different-tree")
        clock = FakeClock()
        original_get_tree = client.get_tree
        tree_reads = 0

        def get_tree(sha, *, timeout_seconds=None):
            nonlocal tree_reads
            if sha == SHA_C:
                tree_reads += 1
            return original_get_tree(sha, timeout_seconds=timeout_seconds)

        client.get_tree = get_tree
        report = self.run_item(client, clock=clock)
        self.assertEqual(report.code, "postcondition-mismatch")
        self.assertEqual(report.status, "blocked-after-reconciliation")
        self.assertEqual(clock.value, 24)
        self.assertEqual(len(client.merge_calls), 1)
        self.assertEqual(tree_reads, 7)
        self.assertIn("pull-merged:True", report.evidence)
        self.assertIn(f"pull-merge-sha:{SHA_C}", report.evidence)
        self.assertIn(f"main-sha:{SHA_C}", report.evidence)
        self.assertIn("base-ancestor:True", report.evidence)
        self.assertIn("expected-head-tree:tree-head", report.evidence)
        self.assertIn("merge-tree:different-tree", report.evidence)

    def test_postcondition_deadline_stops_before_the_next_read(self):
        client = self.client(merge_tree="different-tree")
        clock = FakeClock()
        original_get_pull = client.get_pull
        original_get_main_sha = client.get_main_sha
        post_merge_pull_reads = 0
        post_merge_main_reads = 0

        def get_pull(number, *, timeout_seconds=None):
            nonlocal post_merge_pull_reads
            pull = original_get_pull(number, timeout_seconds=timeout_seconds)
            if client.merge_calls:
                post_merge_pull_reads += 1
                clock.sleep(timeout_seconds)
            return pull

        def get_main_sha(*, timeout_seconds=None):
            nonlocal post_merge_main_reads
            if client.merge_calls:
                post_merge_main_reads += 1
            return original_get_main_sha(timeout_seconds=timeout_seconds)

        client.get_pull = get_pull
        client.get_main_sha = get_main_sha
        report = self.run_item(client, clock=clock)
        self.assertEqual(report.code, "postcondition-mismatch")
        self.assertEqual(clock.value, self.mq.POST_MERGE_RECONCILIATION_SECONDS)
        self.assertEqual(post_merge_pull_reads, 1)
        self.assertEqual(post_merge_main_reads, 0)
        self.assertEqual(len(client.merge_calls), 1)

    def test_postcondition_failure_preserves_transient_error_history(self):
        client = self.client(merge_tree="different-tree")
        original_get_main_sha = client.get_main_sha
        failed_reads = 0

        def get_main_sha(*, timeout_seconds=None):
            nonlocal failed_reads
            if client.merge_calls and failed_reads == 0:
                failed_reads += 1
                raise TimeoutError("transient read timeout")
            return original_get_main_sha(timeout_seconds=timeout_seconds)

        client.get_main_sha = get_main_sha
        report = self.run_item(client)
        self.assertEqual(report.code, "postcondition-mismatch")
        self.assertIn("reconciliation-errors:TimeoutError", report.evidence)

    def test_lagging_merge_commit_sha_is_propagation_delay_not_mismatch(self):
        """merged:true with a null merge_commit_sha while every durable fact
        holds is API propagation delay (#304): the run closes as merged."""
        client = self.client()
        original_merge_pull = client.merge_pull

        def merge_pull(number, payload):
            result = original_merge_pull(number, payload)
            client.pull = replace(client.pull, merge_commit_sha=None)
            return result

        client.merge_pull = merge_pull
        clock = FakeClock()
        report = self.run_item(client, clock=clock)
        self.assertEqual(report.code, "merged")
        self.assertEqual(report.status, "merged")
        self.assertTrue(report.ok)
        self.assertEqual(report.merge_sha, SHA_C)
        self.assertIn("pull-merge-sha-lagging", report.evidence)
        # Accepted on the first reconciliation read: no spin, no TimeoutError.
        self.assertEqual(clock.value, 0)
        self.assertEqual(len(client.merge_calls), 1)

    def test_lagging_echo_never_excuses_a_wrong_main_sha(self):
        client = self.client()
        original_merge_pull = client.merge_pull

        def merge_pull(number, payload):
            result = original_merge_pull(number, payload)
            client.pull = replace(client.pull, merge_commit_sha=None)
            client.main_sha = SHA_D
            return result

        client.merge_pull = merge_pull
        report = self.run_item(client)
        self.assertEqual(report.code, "postcondition-mismatch")
        self.assertEqual(report.status, "blocked-after-reconciliation")
        self.assertIn("pull-merge-sha:None", report.evidence)
        self.assertIn(f"main-sha:{SHA_D}", report.evidence)

    def test_lagging_echo_never_excuses_a_wrong_merge_tree(self):
        client = self.client(merge_tree="different-tree")
        original_merge_pull = client.merge_pull

        def merge_pull(number, payload):
            result = original_merge_pull(number, payload)
            client.pull = replace(client.pull, merge_commit_sha=None)
            return result

        client.merge_pull = merge_pull
        report = self.run_item(client)
        self.assertEqual(report.code, "postcondition-mismatch")

    def test_present_but_different_merge_sha_stays_a_hard_mismatch(self):
        client = self.client()
        original_merge_pull = client.merge_pull

        def merge_pull(number, payload):
            result = original_merge_pull(number, payload)
            client.pull = replace(client.pull, merge_commit_sha=SHA_D)
            return result

        client.merge_pull = merge_pull
        report = self.run_item(client)
        self.assertEqual(report.code, "postcondition-mismatch")
        self.assertIn(f"pull-merge-sha:{SHA_D}", report.evidence)

    def test_dispatch_cancels_pull_runs_for_the_exact_head(self):
        client = self.client(superseded_pull_runs=(777, 778))
        report = self.run_item(client)
        self.assertEqual(report.code, "merged")
        self.assertEqual(client.superseded_cancel_calls, [SHA_B])
        self.assertIn("cancelled-pull-run:777", report.evidence)
        self.assertIn("cancelled-pull-run:778", report.evidence)

    def test_pull_run_cancellation_failure_is_non_fatal_evidence(self):
        class CancelSweepError(Exception):
            pass

        client = self.client(superseded_pull_runs=CancelSweepError("boom"))
        report = self.run_item(client)
        self.assertEqual(report.code, "merged")
        self.assertTrue(report.ok)
        self.assertIn("pull-run-cancel-error:CancelSweepError", report.evidence)

    def test_synchronized_validation_never_sweeps_pull_runs(self):
        """After update-branch, the queue consumes the synchronized run, so
        the pull_request run for the new head must not be cancelled."""
        validation = replace(
            self.client().validation_results[0],
            run_id=9101,
            run_event="pull_request",
            head_sha=SHA_D,
            ticket=None,
        )
        client = self.client(
            ancestor=False,
            update_results=[self.mq.UpdateResult("accepted", SHA_D)],
            validation_results=[validation],
        )
        report = self.run_item(client)
        self.assertEqual(report.code, "merged")
        self.assertEqual(client.superseded_cancel_calls, [])

    def test_successful_merge_waits_for_eventually_consistent_pr_metadata(self):
        client = self.client()
        clock = FakeClock()
        original_get_pull = client.get_pull
        stale_reads = 0

        def get_pull(number, *, timeout_seconds=None):
            del timeout_seconds
            nonlocal stale_reads
            pull = original_get_pull(number)
            if client.merge_calls and stale_reads == 0:
                stale_reads += 1
                return replace(
                    pull,
                    state="open",
                    merged=False,
                    merge_commit_sha=None,
                )
            return pull

        client.get_pull = get_pull
        report = self.run_item(client, clock=clock)
        self.assertEqual(report.code, "merged")
        self.assertTrue(report.ok)
        self.assertEqual(stale_reads, 1)
        self.assertEqual(
            clock.value, self.mq.POST_MERGE_RECONCILIATION_INTERVAL_SECONDS
        )
        self.assertEqual(len(client.merge_calls), 1)

    def test_successful_merge_recovers_from_transient_postcondition_read_error(self):
        client = self.client()
        clock = FakeClock()
        original_get_main_sha = client.get_main_sha
        failed_reads = 0

        def get_main_sha(*, timeout_seconds=None):
            nonlocal failed_reads
            if client.merge_calls and failed_reads == 0:
                failed_reads += 1
                raise TimeoutError("transient read timeout")
            return original_get_main_sha(timeout_seconds=timeout_seconds)

        client.get_main_sha = get_main_sha
        report = self.run_item(client, clock=clock)
        self.assertEqual(report.code, "merged")
        self.assertTrue(report.ok)
        self.assertEqual(failed_reads, 1)
        self.assertEqual(
            clock.value, self.mq.POST_MERGE_RECONCILIATION_INTERVAL_SECONDS
        )
        self.assertEqual(len(client.merge_calls), 1)

    def test_finalize_aborted_is_idempotent_and_revokes_live_authority(self):
        client = self.client()
        original_comment = client.create_review_comment
        comment_attempts = 0
        delays = []

        def create_review_comment(number, body):
            nonlocal comment_attempts
            comment_attempts += 1
            if comment_attempts < 3:
                raise RuntimeError("temporary GitHub error")
            original_comment(number, body)

        client.create_review_comment = create_review_comment
        report = self.mq.finalize_aborted(
            self.request(), client, existing_report=None, sleeper=delays.append
        )
        self.assertEqual(report.code, "queue-worker-aborted")
        self.assertEqual(client.removed, [(220, "merge:queue")])
        self.assertEqual(comment_attempts, 3)
        self.assertEqual(delays, [2, 4])
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

    def test_run_cli_always_writes_a_closed_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            summary_path = Path(directory) / "summary.md"
            client = self.client(permission="read")
            exit_code = self.mq.run_cli(
                [
                    "run",
                    "--repository", "endaye/lmdj",
                    "--pr-number", "220",
                    "--actor", "endaye",
                    "--event-head-sha", SHA_B,
                    "--queue-run-id", "123",
                    "--report", str(report_path),
                    "--summary", str(summary_path),
                ],
                environ={"GITHUB_TOKEN": "token"},
                client_factory=lambda _repository, _token: client,
                clock=lambda: 0.0,
                sleeper=lambda _seconds: None,
            )
            self.assertEqual(exit_code, 1)
            document = __import__("json").loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(document["code"], "unauthorized-actor")
            self.assertIn("unauthorized-actor", summary_path.read_text(encoding="utf-8"))

    def test_finalize_cli_preserves_an_existing_closed_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
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
            report_path.write_text(existing.to_json(), encoding="utf-8")
            exit_code = self.mq.run_cli(
                [
                    "finalize",
                    "--repository", "endaye/lmdj",
                    "--pr-number", "220",
                    "--actor", "endaye",
                    "--event-head-sha", SHA_B,
                    "--queue-run-id", "123",
                    "--report", str(report_path),
                ],
                environ={"GITHUB_TOKEN": "token"},
                client_factory=lambda _repository, _token: self.client(),
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(report_path.read_text(encoding="utf-8"), existing.to_json())


if __name__ == "__main__":
    unittest.main(verbosity=2)
