#!/usr/bin/env python3
"""Detect and reconcile orphaned Merge Queue label authorization."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
import argparse
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Protocol

from merge_queue import QUEUE_LABEL, PullRequest, QueueReport


STALL_AGE_SECONDS = 20 * 60


@dataclass(frozen=True)
class LabelEvent:
    event_id: int
    created_at: float


@dataclass(frozen=True)
class StalledItem:
    pr_number: int
    label_event_id: int
    labelled_at: float
    head_sha: str


class WatchdogClient(Protocol):
    def list_labeled_pulls(self, label: str) -> Sequence[PullRequest]: ...
    def latest_label_event(self, number: int, label: str) -> LabelEvent | None: ...
    def has_active_queue_run(self, number: int, since: float) -> bool: ...
    def get_pull(self, number: int) -> PullRequest: ...
    def list_review_comments(self, number: int) -> Sequence[str]: ...
    def remove_label(self, number: int, label: str) -> None: ...
    def create_review_comment(self, number: int, body: str) -> None: ...


def _report(
    code: str,
    pull: PullRequest,
    *,
    ok: bool,
    status: str,
    evidence: tuple[str, ...] = (),
) -> QueueReport:
    return QueueReport(
        ok=ok,
        status=status,
        code=code,
        attempts=0,
        observed_base_sha=pull.base_sha,
        observed_head_sha=pull.head_sha,
        validation_run_ids=(),
        merge_sha=pull.merge_commit_sha,
        message=code,
        evidence=evidence,
    )


def find_stalled_items(
    client: WatchdogClient,
    *,
    now: float,
    minimum_age_seconds: int = STALL_AGE_SECONDS,
) -> tuple[StalledItem, ...]:
    stalled: list[StalledItem] = []
    for pull in client.list_labeled_pulls(QUEUE_LABEL):
        if pull.state != "open" or pull.merged or QUEUE_LABEL not in pull.labels:
            continue
        event = client.latest_label_event(pull.number, QUEUE_LABEL)
        if event is None or now - event.created_at < minimum_age_seconds:
            continue
        if client.has_active_queue_run(pull.number, event.created_at):
            continue
        stalled.append(
            StalledItem(pull.number, event.event_id, event.created_at, pull.head_sha)
        )
    return tuple(sorted(stalled, key=lambda item: (item.labelled_at, item.pr_number)))


def reconcile_stalled_item(
    client: WatchdogClient, item: StalledItem
) -> QueueReport:
    pull = client.get_pull(item.pr_number)
    if pull.merged:
        return _report("already-merged", pull, ok=True, status="already-merged")
    if pull.state != "open":
        return _report("ineligible-pr", pull, ok=False, status="blocked")
    if QUEUE_LABEL not in pull.labels:
        return _report("queue-label-removed", pull, ok=True, status="cancelled")
    if pull.head_sha != item.head_sha:
        return _report(
            "queue-stall-state-changed",
            pull,
            ok=True,
            status="cancelled",
            evidence=(f"expected-head:{item.head_sha}",),
        )
    marker = f"<!-- lmdj-merge-queue:queue-stalled:{item.label_event_id} -->"
    existing = client.list_review_comments(item.pr_number)
    client.remove_label(item.pr_number, QUEUE_LABEL)
    if not any(marker in body for body in existing):
        client.create_review_comment(
            item.pr_number,
            "\n".join((
                marker,
                "## Integration Queue stalled",
                "Stable code: `queue-stalled`",
                "The queue label had no queued or in-progress worker after its latest label event.",
                "Inspect cancellation, timeout, and pending capacity before explicitly re-adding the label.",
            )),
        )
    return _report(
        "queue-stalled",
        pull,
        ok=False,
        status="blocked",
        evidence=(f"label-event:{item.label_event_id}",),
    )


def _default_client_factory(repository: str, token: str):
    from github_queue_api import GitHubQueueClient

    return GitHubQueueClient(repository, token)


def _write_atomic(path: str | Path, contents: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=target.parent, delete=False
    ) as output:
        output.write(contents)
        temporary = Path(output.name)
    os.replace(temporary, target)


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    client_factory: Callable[[str, str], WatchdogClient] = _default_client_factory,
    clock: Callable[[], float] = time.time,
) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args(argv)
    token = environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required")
    client = client_factory(args.repository, token)
    items = find_stalled_items(client, now=clock())
    reports = tuple(reconcile_stalled_item(client, item) for item in items)
    document = {
        "schema": "lmdj.merge-queue-watchdog.v1",
        "reports": [asdict(report) for report in reports],
    }
    _write_atomic(
        args.report,
        json.dumps(document, sort_keys=True, separators=(",", ":")),
    )
    lines = ["## Integration Queue watchdog", ""]
    if not reports:
        lines.append("No stalled queue authorization found.")
    else:
        for report in reports:
            lines.append(
                f"- PR head `{report.observed_head_sha}`: `{report.code}` ({report.status})"
            )
    lines.append("")
    _write_atomic(args.summary, "\n".join(lines))
    return 1 if any(not report.ok for report in reports) else 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
