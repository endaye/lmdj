#!/usr/bin/env python3
"""Fail-closed state machine for LMDJ's serialized Integration Queue."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Protocol


QUEUE_LABEL = "merge:queue"
MAX_ATTEMPTS = 3
WORKER_TIMEOUT_SECONDS = 360 * 60
MUTATION_WINDOW_SECONDS = 330 * 60
RECONCILIATION_RESERVE_SECONDS = 10 * 60
MINIMUM_ATTEMPT_SECONDS = 10 * 60
MAXIMUM_VALIDATION_SECONDS = 120 * 60
POST_MERGE_RECONCILIATION_ATTEMPTS = 7
POST_MERGE_RECONCILIATION_INTERVAL_SECONDS = 4
POST_MERGE_RECONCILIATION_SECONDS = 30
GITHUB_ACTIONS_APP_ID = 15368
REQUIRED_CHECKS = (
    "core (ubuntu-latest)",
    "core (macos-latest)",
    "PR Gate",
)
CONTROL_PLANE_PATHS = (
    ".github/actionlint.yaml",
    ".github/workflows/ci.yml",
    ".github/workflows/merge-queue.yml",
    "scripts/ci/change_scope.py",
    "scripts/ci/github_queue_api.py",
    "scripts/ci/merge_queue.py",
    "scripts/ci/merge_queue_watchdog.py",
    "scripts/ci/pr_gate.py",
    "scripts/ci/scope_policy.json",
)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class DispatchContractError(RuntimeError):
    """The workflow dispatch response did not carry the promised run identity."""


@dataclass(frozen=True)
class QueueRequest:
    repository: str
    pr_number: int
    actor: str
    event_head_sha: str
    queue_run_id: int
    max_attempts: int = MAX_ATTEMPTS
    started_at: float = 0.0


@dataclass(frozen=True)
class PullRequest:
    number: int
    state: str
    merged: bool
    draft: bool
    base_ref: str
    base_sha: str
    head_repository: str
    head_sha: str
    title: str
    labels: tuple[str, ...]
    mergeable: bool | None
    merge_commit_sha: str | None
    head_ref: str


@dataclass(frozen=True)
class RequiredCheck:
    name: str
    app_id: int
    conclusion: str


@dataclass(frozen=True)
class UpdateResult:
    status: str
    head_sha: str | None


@dataclass(frozen=True)
class ValidationResult:
    classification: str
    run_id: int
    run_status: str
    run_conclusion: str | None
    run_event: str
    workflow_path: str
    head_sha: str
    manifest_mode: str | None
    trusted_head: bool
    ticket: str | None
    base_sha: str | None
    required_checks: tuple[RequiredCheck, ...]
    queue_seconds: float
    execution_seconds: float


@dataclass(frozen=True)
class MergeResult:
    merged: bool
    sha: str | None
    uncertain: bool = False
    message: str = ""


@dataclass(frozen=True)
class QueueAttempt:
    number: int
    base_sha: str
    head_sha: str
    head_tree: str
    ticket: str
    validation_budget_seconds: int


@dataclass(frozen=True)
class QueueReport:
    ok: bool
    status: str
    code: str
    attempts: int
    observed_base_sha: str | None
    observed_head_sha: str | None
    validation_run_ids: tuple[int, ...]
    merge_sha: str | None
    message: str
    evidence: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


class QueueClient(Protocol):
    def get_permission(self, actor: str) -> str: ...
    def get_pull(
        self, number: int, *, timeout_seconds: float | None = None
    ) -> PullRequest: ...
    def get_main_sha(self, *, timeout_seconds: float | None = None) -> str: ...
    def list_changed_paths(self, number: int) -> Sequence[str]: ...
    def is_ancestor(
        self, base: str, head: str, *, timeout_seconds: float | None = None
    ) -> bool: ...
    def update_branch(
        self, number: int, expected_head_sha: str, timeout_seconds: int
    ) -> UpdateResult: ...
    def authorize_sync_validation(
        self, number: int, base_sha: str, head_sha: str, timeout_seconds: int
    ) -> int: ...
    def get_tree(self, sha: str, *, timeout_seconds: float | None = None) -> str: ...
    def dispatch_validation(
        self, number: int, head_ref: str, inputs: Mapping[str, str]
    ) -> int: ...
    def wait_validation(self, run_id: int, timeout_seconds: int) -> ValidationResult: ...
    def merge_pull(self, number: int, payload: Mapping[str, str]) -> MergeResult: ...
    def remove_label(self, number: int, label: str) -> None: ...
    def create_review_comment(self, number: int, body: str) -> None: ...


def _valid_sha(value: str) -> bool:
    return bool(_SHA_RE.fullmatch(value))


def validation_budget_seconds(
    *, now: float, mutation_deadline: float, remaining_attempts: int
) -> int:
    if remaining_attempts <= 0:
        return 0
    available = int(
        (mutation_deadline - now - RECONCILIATION_RESERVE_SECONDS)
        // remaining_attempts
    )
    if available < MINIMUM_ATTEMPT_SECONDS:
        return 0
    return min(MAXIMUM_VALIDATION_SECONDS, available)


def _report(
    *, code: str, status: str = "blocked", attempts: int = 0,
    base: str | None = None, head: str | None = None,
    run_ids: Sequence[int] = (), merge_sha: str | None = None,
    message: str | None = None, evidence: Sequence[str] = (), ok: bool = False,
) -> QueueReport:
    return QueueReport(
        ok=ok,
        status=status,
        code=code,
        attempts=attempts,
        observed_base_sha=base,
        observed_head_sha=head,
        validation_run_ids=tuple(run_ids),
        merge_sha=merge_sha,
        message=message or code,
        evidence=tuple(evidence),
    )


def _cleanup_failure(
    request: QueueRequest, client: QueueClient, report: QueueReport
) -> QueueReport:
    try:
        pull = client.get_pull(request.pr_number)
        if pull.state == "open" and QUEUE_LABEL in pull.labels:
            client.remove_label(request.pr_number, QUEUE_LABEL)
            client.create_review_comment(
                request.pr_number,
                "\n".join((
                    f"<!-- lmdj-merge-queue:{report.code}:{request.queue_run_id} -->",
                    "## Integration Queue stopped",
                    f"Stable code: `{report.code}`",
                    f"Queue run: `{request.queue_run_id}`",
                    f"Observed base/head: `{report.observed_base_sha}` / `{report.observed_head_sha}`",
                    "Fix the named condition, then explicitly add `merge:queue` again.",
                )),
            )
    except Exception as error:  # cleanup evidence must not hide the primary code
        return QueueReport(
            **{
                **asdict(report),
                "evidence": tuple(report.evidence) + (f"cleanup-error:{type(error).__name__}",),
            }
        )
    return report


def _stop(
    request: QueueRequest, client: QueueClient, code: str, *, attempts: int = 0,
    base: str | None = None, head: str | None = None,
    run_ids: Sequence[int] = (), status: str = "blocked",
    evidence: Sequence[str] = (), cleanup: bool = True, ok: bool = False,
) -> QueueReport:
    report = _report(
        code=code,
        status=status,
        attempts=attempts,
        base=base,
        head=head,
        run_ids=run_ids,
        evidence=evidence,
        ok=ok,
    )
    return _cleanup_failure(request, client, report) if cleanup else report


def _labelled(pull: PullRequest) -> bool:
    return QUEUE_LABEL in pull.labels


def _validation_contract_error(
    result: ValidationResult, attempt: QueueAttempt, *, synchronized: bool = False
) -> str | None:
    if result.run_id <= 0:
        return "validation-failed"
    expected_event = "pull_request" if synchronized else "workflow_dispatch"
    expected_ticket = None if synchronized else attempt.ticket
    if (
        result.run_event != expected_event
        or result.workflow_path != ".github/workflows/ci.yml"
        or result.head_sha != attempt.head_sha
        or result.ticket != expected_ticket
        or result.base_sha != attempt.base_sha
        or result.manifest_mode != "full"
        or not result.trusted_head
    ):
        return "validation-failed"
    observed = {
        (check.name, check.app_id, check.conclusion)
        for check in result.required_checks
    }
    expected = {(name, GITHUB_ACTIONS_APP_ID, "success") for name in REQUIRED_CHECKS}
    if observed != expected:
        return "required-check-contract-mismatch"
    if result.run_status != "completed" or result.run_conclusion != "success":
        return "validation-failed"
    return None


def run_queue_item(
    request: QueueRequest, client: QueueClient, *,
    clock: Callable[[], float] = time.time,
    sleeper: Callable[[float], None] = time.sleep,
) -> QueueReport:
    """Run one queue item to a closed terminal report."""
    pull = client.get_pull(request.pr_number)
    if pull.merged:
        return _report(
            code="already-merged",
            status="already-merged",
            head=pull.head_sha,
            merge_sha=pull.merge_commit_sha,
            ok=True,
        )
    if client.get_permission(request.actor) not in {"write", "maintain", "admin"}:
        return _stop(request, client, "unauthorized-actor", head=pull.head_sha)
    if (
        pull.state != "open"
        or pull.draft
        or pull.base_ref != "main"
        or pull.head_repository != request.repository
        or pull.number != request.pr_number
        or pull.head_sha != request.event_head_sha
    ):
        return _stop(request, client, "ineligible-pr", base=pull.base_sha, head=pull.head_sha)
    if not _labelled(pull):
        return _stop(
            request, client, "queue-label-removed", status="cancelled",
            base=pull.base_sha, head=pull.head_sha, cleanup=False, ok=True,
        )
    if pull.mergeable is False:
        return _stop(request, client, "merge-conflict", base=pull.base_sha, head=pull.head_sha)
    if pull.mergeable is None:
        return _stop(request, client, "ineligible-pr", base=pull.base_sha, head=pull.head_sha)
    changed = set(client.list_changed_paths(request.pr_number))
    if changed.intersection(CONTROL_PLANE_PATHS):
        return _stop(
            request, client, "queue-control-plane-change",
            base=pull.base_sha, head=pull.head_sha,
            evidence=tuple(sorted(changed.intersection(CONTROL_PLANE_PATHS))),
        )

    started_at = request.started_at
    mutation_deadline = started_at + MUTATION_WINDOW_SECONDS
    run_ids: list[int] = []
    last_base, last_head = pull.base_sha, pull.head_sha

    for attempt_number in range(1, request.max_attempts + 1):
        remaining_attempts = request.max_attempts - attempt_number + 1
        budget = validation_budget_seconds(
            now=clock(),
            mutation_deadline=mutation_deadline,
            remaining_attempts=remaining_attempts,
        )
        if budget == 0:
            return _stop(
                request, client, "queue-budget-exhausted",
                attempts=attempt_number - 1, base=last_base, head=last_head,
                run_ids=run_ids,
            )

        base = client.get_main_sha()
        pull = client.get_pull(request.pr_number)
        last_base, last_head = base, pull.head_sha
        if pull.merged:
            return _report(
                code="already-merged", status="already-merged",
                attempts=attempt_number - 1, base=base, head=pull.head_sha,
                run_ids=run_ids, merge_sha=pull.merge_commit_sha, ok=True,
            )
        if not _labelled(pull):
            return _stop(
                request, client, "queue-label-removed", status="cancelled",
                attempts=attempt_number - 1, base=base, head=pull.head_sha,
                run_ids=run_ids, cleanup=False, ok=True,
            )
        if not (_valid_sha(base) and _valid_sha(pull.head_sha)):
            return _stop(
                request, client, "ineligible-pr", attempts=attempt_number,
                base=base, head=pull.head_sha, run_ids=run_ids,
            )

        synchronized_run_id: int | None = None
        if not client.is_ancestor(base, pull.head_sha):
            update = client.update_branch(
                request.pr_number, pull.head_sha, min(budget, 10 * 60)
            )
            if update.status == "drift":
                continue
            update_codes = {
                "conflict": "merge-conflict",
                "timeout": "update-branch-timeout",
                "uncertain": "merge-state-uncertain",
            }
            if update.status in update_codes:
                return _stop(
                    request, client, update_codes[update.status],
                    attempts=attempt_number, base=base, head=pull.head_sha,
                    run_ids=run_ids,
                )
            if update.status != "accepted" or not update.head_sha:
                return _stop(
                    request, client, "merge-state-uncertain",
                    attempts=attempt_number, base=base, head=pull.head_sha,
                    run_ids=run_ids,
                )
            pull = client.get_pull(request.pr_number)
            if pull.head_sha != update.head_sha or not client.is_ancestor(base, pull.head_sha):
                continue
            try:
                synchronized_run_id = client.authorize_sync_validation(
                    request.pr_number,
                    base,
                    pull.head_sha,
                    min(budget, 10 * 60),
                )
            except Exception as error:
                return _stop(
                    request, client, "sync-validation-approval-failed",
                    attempts=attempt_number, base=base, head=pull.head_sha,
                    run_ids=run_ids, evidence=(type(error).__name__,),
                )

        head = pull.head_sha
        last_head = head
        budget = validation_budget_seconds(
            now=clock(),
            mutation_deadline=mutation_deadline,
            remaining_attempts=remaining_attempts,
        )
        if budget == 0:
            return _stop(
                request, client, "queue-budget-exhausted",
                attempts=attempt_number, base=base, head=head, run_ids=run_ids,
            )
        attempt = QueueAttempt(
            number=attempt_number,
            base_sha=base,
            head_sha=head,
            head_tree=client.get_tree(head),
            ticket=f"mq:{request.queue_run_id}:{attempt_number}",
            validation_budget_seconds=budget,
        )
        inputs = {
            "lanes": "",
            "queue_ticket": attempt.ticket,
            "queue_pr_number": str(request.pr_number),
            "queue_base_sha": base,
            "queue_head_sha": head,
        }
        if synchronized_run_id is not None:
            run_id = synchronized_run_id
        else:
            try:
                run_id = client.dispatch_validation(request.pr_number, pull.head_ref, inputs)
            except DispatchContractError as error:
                return _stop(
                    request, client, "validation-dispatch-contract-mismatch",
                    attempts=attempt_number, base=base, head=head, run_ids=run_ids,
                    evidence=(str(error),),
                )
            except Exception as error:
                return _stop(
                    request, client, "validation-dispatch-failed",
                    attempts=attempt_number, base=base, head=head, run_ids=run_ids,
                    evidence=(type(error).__name__,),
                )
        if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
            return _stop(
                request, client, "validation-dispatch-contract-mismatch",
                attempts=attempt_number, base=base, head=head, run_ids=run_ids,
            )
        run_ids.append(run_id)
        result = client.wait_validation(run_id, budget)

        if result.classification == "timeout":
            return _stop(
                request, client, "validation-timeout", attempts=attempt_number,
                base=base, head=head, run_ids=run_ids,
            )

        if result.classification in {"queue-base-drift", "queue-head-drift"}:
            live_base = client.get_main_sha()
            live_pull = client.get_pull(request.pr_number)
            confirmed = (
                result.classification == "queue-base-drift" and live_base != base
            ) or (
                result.classification == "queue-head-drift" and live_pull.head_sha != head
            )
            if confirmed:
                last_base, last_head = live_base, live_pull.head_sha
                continue
            return _stop(
                request, client, "validation-failed", attempts=attempt_number,
                base=live_base, head=live_pull.head_sha, run_ids=run_ids,
                evidence=("unconfirmed-drift-artifact",),
            )

        contract_error = _validation_contract_error(
            result, attempt, synchronized=synchronized_run_id is not None
        )
        if contract_error:
            return _stop(
                request, client, contract_error, attempts=attempt_number,
                base=base, head=head, run_ids=run_ids,
            )

        live_base = client.get_main_sha()
        live_pull = client.get_pull(request.pr_number)
        if not _labelled(live_pull):
            return _stop(
                request, client, "queue-label-removed", status="cancelled",
                attempts=attempt_number, base=live_base, head=live_pull.head_sha,
                run_ids=run_ids, cleanup=False, ok=True,
            )
        if live_base != base or live_pull.head_sha != head:
            last_base, last_head = live_base, live_pull.head_sha
            continue

        payload = {
            "merge_method": "squash",
            "sha": head,
            "commit_title": f"{live_pull.title} (#{request.pr_number})",
            "commit_message": "",
        }
        merge = client.merge_pull(request.pr_number, payload)
        if not merge.merged:
            reconciled = client.get_pull(request.pr_number)
            if not reconciled.merged:
                return _stop(
                    request, client,
                    "merge-state-uncertain" if merge.uncertain else "merge-rejected",
                    status="blocked-after-reconciliation" if merge.uncertain else "blocked",
                    attempts=attempt_number, base=base, head=head, run_ids=run_ids,
                    evidence=((merge.message,) if merge.message else ()),
                )
            merge = MergeResult(True, reconciled.merge_commit_sha)

        merge_sha = merge.sha
        merged_main: str | None = None
        merged_pull_state: bool | None = None
        merged_pull_sha: str | None = None
        base_is_ancestor: bool | None = None
        merge_tree: str | None = None
        postcondition_ok = False
        reconciliation_errors: list[str] = []
        reconciliation_deadline = clock() + POST_MERGE_RECONCILIATION_SECONDS

        def reconciliation_timeout() -> float:
            remaining = reconciliation_deadline - clock()
            if remaining <= 0:
                raise TimeoutError("post-merge reconciliation deadline exhausted")
            return remaining

        for reconciliation in range(POST_MERGE_RECONCILIATION_ATTEMPTS):
            try:
                merged_pull = client.get_pull(
                    request.pr_number, timeout_seconds=reconciliation_timeout()
                )
                merged_pull_state = merged_pull.merged
                merged_pull_sha = merged_pull.merge_commit_sha
                merged_main = client.get_main_sha(
                    timeout_seconds=reconciliation_timeout()
                )
                base_is_ancestor = client.is_ancestor(
                    base, merge_sha, timeout_seconds=reconciliation_timeout()
                ) if merge_sha else False
                merge_tree = client.get_tree(
                    merge_sha, timeout_seconds=reconciliation_timeout()
                ) if merge_sha else None
                postcondition_ok = (
                    bool(merge_sha)
                    and merged_pull_state is True
                    and merged_pull_sha == merge_sha
                    and merged_main == merge_sha
                    and base_is_ancestor is True
                    and merge_tree == attempt.head_tree
                )
            except Exception as error:
                reconciliation_errors.append(type(error).__name__)
            if postcondition_ok:
                break
            if reconciliation + 1 < POST_MERGE_RECONCILIATION_ATTEMPTS:
                remaining = reconciliation_deadline - clock()
                if remaining <= 0:
                    break
                sleeper(min(POST_MERGE_RECONCILIATION_INTERVAL_SECONDS, remaining))
        if not postcondition_ok:
            evidence = [
                f"merge-sha:{merge_sha}",
                f"pull-merged:{merged_pull_state}",
                f"pull-merge-sha:{merged_pull_sha}",
                f"main-sha:{merged_main}",
                f"base-ancestor:{base_is_ancestor}",
                f"expected-head-tree:{attempt.head_tree}",
                f"merge-tree:{merge_tree}",
            ]
            if reconciliation_errors:
                evidence.append(
                    f"reconciliation-errors:{','.join(reconciliation_errors)}"
                )
            return _stop(
                request, client, "postcondition-mismatch",
                status="blocked-after-reconciliation", attempts=attempt_number,
                base=base, head=head, run_ids=run_ids,
                evidence=evidence,
                cleanup=False,
            )
        return _report(
            code="merged", status="merged", attempts=attempt_number,
            base=base, head=head, run_ids=run_ids, merge_sha=merge_sha,
            message="exact validated head squash-merged; label revocation is no longer reversible",
            evidence=(
                f"head-tree:{attempt.head_tree}",
                f"queue-seconds:{result.queue_seconds}",
                f"execution-seconds:{result.execution_seconds}",
            ),
            ok=True,
        )

    return _stop(
        request, client, "unstable-after-three-validations",
        attempts=request.max_attempts, base=last_base, head=last_head,
        run_ids=run_ids,
    )


def finalize_aborted(
    request: QueueRequest, client: QueueClient,
    existing_report: QueueReport | None,
) -> QueueReport:
    if existing_report is not None:
        return existing_report
    pull = client.get_pull(request.pr_number)
    if pull.merged:
        return _report(
            code="already-merged", status="already-merged", head=pull.head_sha,
            merge_sha=pull.merge_commit_sha, ok=True,
        )
    return _stop(
        request, client, "queue-worker-aborted",
        base=client.get_main_sha(), head=pull.head_sha,
    )


def render_markdown(report: QueueReport) -> str:
    return "\n".join((
        "## Integration Queue",
        "",
        f"- Status: `{report.status}`",
        f"- Code: `{report.code}`",
        f"- Attempts: `{report.attempts}`",
        f"- Base/head: `{report.observed_base_sha}` / `{report.observed_head_sha}`",
        f"- Validation runs: `{','.join(map(str, report.validation_run_ids))}`",
        f"- Merge SHA: `{report.merge_sha}`",
        f"- Message: {report.message}",
        "",
    ))


def _write(path: str | Path, contents: str) -> None:
    Path(path).write_text(contents, encoding="utf-8")


def _write_atomic(path: str | Path, contents: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=target.parent, delete=False
    ) as output:
        output.write(contents)
        temporary = Path(output.name)
    os.replace(temporary, target)


def _load_report(path: str | Path) -> QueueReport:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("queue report must be an object")
    return QueueReport(
        **{
            **document,
            "validation_run_ids": tuple(document["validation_run_ids"]),
            "evidence": tuple(document["evidence"]),
        }
    )


def _default_client_factory(repository: str, token: str):
    from github_queue_api import GitHubQueueClient

    return GitHubQueueClient(repository, token)


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    client_factory: Callable[[str, str], QueueClient] = _default_client_factory,
    clock: Callable[[], float] = time.time,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("run", "finalize"):
        action = subparsers.add_parser(command)
        action.add_argument("--repository", required=True)
        action.add_argument("--pr-number", type=int, required=True)
        action.add_argument("--actor", required=True)
        action.add_argument("--event-head-sha", required=True)
        action.add_argument("--queue-run-id", type=int, required=True)
        action.add_argument("--report", required=True)
        action.add_argument("--summary")
    render = subparsers.add_parser("render-report")
    render.add_argument("--report", required=True)
    render.add_argument("--summary", required=True)
    args = parser.parse_args(argv)
    if args.command == "render-report":
        report = _load_report(args.report)
        _write(args.summary, render_markdown(report))
        return 0 if report.ok else 1
    token = environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required")
    request = QueueRequest(
        repository=args.repository,
        pr_number=args.pr_number,
        actor=args.actor,
        event_head_sha=args.event_head_sha,
        queue_run_id=args.queue_run_id,
        started_at=clock(),
    )
    client = client_factory(args.repository, token)
    if args.command == "run":
        report = run_queue_item(
            request, client, clock=clock, sleeper=sleeper
        )
    else:
        existing = _load_report(args.report) if Path(args.report).is_file() else None
        report = finalize_aborted(request, client, existing)
    _write_atomic(args.report, report.to_json())
    if args.summary:
        _write(args.summary, render_markdown(report))
    return 0 if report.ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
