#!/usr/bin/env python3
"""Detect an advisory review lane that has been failing quietly.

Both advisory review lanes carry `continue-on-error`, so a failed review no
longer reddens a Pull Request. That was deliberate: a lane which cannot block a
merge should not be able to redden every Pull Request, because it devalues every
other red check. It also creates a blind spot, and this closes it.

The signal is the **effect**, not the step conclusion. `continue-on-error` does
more than keep the job green: the Actions API reports the guarded step's
`conclusion` as `success` even when it exited 1. The first real outage proved
it -- the Grok credential expired at 10:11 on 2026-09-05, every run that day
died with `Not signed in`, and every one of them reads `success` at both job
and step level. A check built on step conclusions would have reported that
lane healthy all day. So this asks a question the API cannot rewrite: after the
run began, did this lane leave its signature on the Pull Request?

Each lane signs what it posts. Grok's sticky summary opens with
`<!-- lmdj-grok-review -->` and is posted on every completed review; the two
Claude backends are told to open every comment with
`<!-- lmdj-review: glm -->` or `<!-- lmdj-review: kimi -->`. The signature is
what makes each backend its own lane -- they run as matrix legs of one job and
post under one identity, so without it a dead backend hides behind a live one.

Silence is not evidence. A cancelled run, a job skipped by its `if:`, or a
review step skipped for want of a secret reached no verdict and is dropped. A
step the run never reached is not skipped -- it is an attempt the lane failed
to make -- and is judged like any other attempt: by whether anything was posted.

A single failure is not a signal -- a model call times out, a runner restarts.
A lane is declared down only when every one of the last `--window` attempts
left nothing behind, which is a lane that has stopped working rather than a
lane having a bad day.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import argparse
import json
import os
import sys
import urllib.error
import urllib.request


@dataclass(frozen=True)
class Lane:
    """One reviewer, identified by the job that runs it and the mark it leaves.

    `signs_since` is the ISO date from which this lane was instructed to sign.
    Runs older than it posted unsigned comments and cannot be judged by a
    marker that did not exist yet -- counting them as failures would declare a
    healthy lane DOWN on the first scheduled run, a false red on the very
    alert channel this workflow uses. Empty means the marker predates any run
    the window can reach.
    """

    workflow: str
    job: str
    step: str
    marker: str
    signs_since: str = ""

    @property
    def name(self) -> str:
        return f"{self.workflow} / {self.job}"


# The Claude backends began signing when the prompt instruction shipped; Grok's
# sticky-comment marker predates this check, so it needs no cutoff.
CLAUDE_SIGNS_SINCE = "2026-09-06"

REVIEW_LANES = (
    # The Claude backends run inside ci.yml since #659, so Pre-heavy Gate can
    # order itself after them. Job and step names are unchanged.
    Lane("ci.yml", "Claude review (glm)", "Review",
         "<!-- lmdj-review: glm -->", CLAUDE_SIGNS_SINCE),
    Lane("ci.yml", "Claude review (kimi)", "Review",
         "<!-- lmdj-review: kimi -->", CLAUDE_SIGNS_SINCE),
    Lane("grok-review.yml", "Grok advisory review", "Run advisory Grok review",
         "<!-- lmdj-grok-review -->"),
)

# Outcomes that carry no evidence either way and are dropped rather than
# counted. `cancelled` applies to the run; `skipped` to the job or the step.
SILENT = {"skipped", "cancelled"}

# Run listing is paged until the window is filled rather than taken from one
# fixed page. Bounded so an all-cancelled history cannot loop forever.
RUNS_PER_PAGE = 50
MAX_RUN_PAGES = 6


class LivenessUnavailable(RuntimeError):
    """The API could not be read, so nothing was observed.

    Distinct from observing a healthy lane and from observing too little. A
    check that reports health when it could not look is wrong in the
    reassuring direction, which is worse than not running at all.
    """


@dataclass(frozen=True)
class LaneVerdict:
    lane: str
    observed: int
    failed: int
    down: bool
    detail: str


def evaluate(lane: str, observations: Sequence[str], *, window: int) -> LaneVerdict:
    """Decide whether a lane is down from its recent observations.

    `observations` is newest first and holds exactly one `success` or
    `failure` per run in which this lane attempted a review. Runs that made
    no attempt have already been dropped by the collector.
    """
    considered = list(observations)[:window]
    failed = sum(1 for outcome in considered if outcome == "failure")
    if len(considered) < window:
        return LaneVerdict(
            lane, len(considered), failed, False,
            f"only {len(considered)} of {window} attempts observed; too few to judge",
        )
    if failed == window:
        return LaneVerdict(
            lane, len(considered), failed, True,
            f"every one of the last {window} attempts posted nothing",
        )
    return LaneVerdict(
        lane, len(considered), failed, False,
        f"{window - failed} of the last {window} attempts posted a review",
    )


Request = Callable[[str, str], object]

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"


def _api(path: str, context: str) -> object:
    """GET `path` from the REST API, raising rather than reporting silence.

    `urllib`, not `gh`. No `run:` step in this repository invokes `gh` on a
    self-hosted runner and nothing installs it there -- `claude-review.yml`'s
    `gh pr comment` calls run inside `claude-code-action`, on its own tooling,
    not on the host. A missing binary would also have escaped the failure
    handling below, because `FileNotFoundError` is not a nonzero exit. Both
    `scripts/ci/github_queue_api.py` and `.github/scripts/grok_review.py`
    already reach the API this way.
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise LivenessUnavailable(
            "why: GITHUB_TOKEN is unset, so this check cannot read the "
            "surfaces it judges by and would report health without looking; "
            "remedy: pass secrets.GITHUB_TOKEN to the step"
        )
    request = urllib.request.Request(
        f"{API_ROOT}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "lmdj-advisory-review-liveness",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError) as error:
        detail = getattr(error, "code", None) or str(error)
        raise LivenessUnavailable(
            f"why: {context} failed ({detail}), so this check observed nothing "
            f"and cannot distinguish a healthy lane from an unreadable one; "
            f"remedy: restore API access for the runner (token scope, rate "
            f"limit, network) and rerun"
        ) from error


def evidence_posted(
    repository: str, pr_number: int, since: str, marker: str,
    *, api: Request = _api,
) -> bool:
    """Whether `marker` appears in anything posted on the Pull Request since `since`.

    Three surfaces, because the lanes use all of them: issue comments (Grok's
    sticky summary, and the Claude summary when a review is clean), review
    comments (Claude's inline findings), and review bodies (Grok's thread
    review). `since` on the comment endpoints filters by update time, so an
    upserted sticky comment counts; review bodies carry no `since` filter and
    are compared here.
    """
    for path, context in (
        (f"/repos/{repository}/issues/{pr_number}/comments?since={since}&per_page=100",
         f"reading issue comments on PR {pr_number}"),
        (f"/repos/{repository}/pulls/{pr_number}/comments?since={since}&per_page=100",
         f"reading review comments on PR {pr_number}"),
    ):
        for item in api(path, context) or []:
            if marker in (item.get("body") or ""):
                return True
    reviews = api(
        f"/repos/{repository}/pulls/{pr_number}/reviews?per_page=100",
        f"reading reviews on PR {pr_number}",
    ) or []
    return any(
        marker in (review.get("body") or "")
        and (review.get("submitted_at") or "") >= since
        for review in reviews
    )


def collect_observations(
    repository: str, lane: Lane, *, limit: int, api: Request = _api,
) -> list[str]:
    """One `success` or `failure` per attempted run for `lane`, newest first."""
    # Paged until `limit` *observations* exist, not until `limit` runs have
    # been seen. The Claude lanes live in ci.yml, which also runs on push,
    # dispatch and draft events -- completed, non-cancelled runs that skip the
    # review job entirely. Budgeting on run count let those pad the pages,
    # stop the pager early, and hand `evaluate` too few observations to judge:
    # exit 0, green while blind, the case this loop exists to prevent. Only a
    # judged attempt spends the budget now. The event filter removes the
    # push and dispatch runs before they are fetched; drafts still arrive as
    # pull_request runs and are dropped below when their job is skipped.
    observations: list[str] = []
    for page in range(1, MAX_RUN_PAGES + 1):
        payload = api(
            f"/repos/{repository}/actions/workflows/{lane.workflow}/runs"
            f"?status=completed&event=pull_request"
            f"&per_page={RUNS_PER_PAGE}&page={page}",
            f"listing runs of {lane.workflow}",
        ) or {}
        batch = payload.get("workflow_runs") or []
        for run in batch:
            if run.get("conclusion") in SILENT:
                continue
            # A run that predates the signing instruction posted unsigned
            # comments. It is not evidence of failure; it is evidence of nothing.
            if lane.signs_since and (run.get("created_at") or "") < lane.signs_since:
                continue
            payload = api(
                f"/repos/{repository}/actions/runs/{run['id']}/jobs",
                f"reading jobs of run {run['id']}",
            ) or {}
            jobs = [j for j in (payload.get("jobs") or []) if j.get("name") == lane.job]
            if not jobs:
                continue
            job = jobs[0]
            step = next(
                (s.get("conclusion") for s in (job.get("steps") or [])
                 if s.get("name") == lane.step),
                None,
            )
            # A skipped job or step made no attempt. Every other conclusion --
            # including `timed_out`, the way a hung vendor endpoint dies, and a
            # null step the run never reached -- is an attempt, and is judged by
            # its effect rather than by a conclusion `continue-on-error` rewrites.
            if job.get("conclusion") in SILENT or step in SILENT:
                continue
            pulls = run.get("pull_requests") or []
            if not pulls:
                continue
            posted = evidence_posted(
                repository, int(pulls[0]["number"]), run["created_at"], lane.marker,
                api=api,
            )
            observations.append("success" if posted else "failure")
            if len(observations) >= limit:
                return observations
        if len(batch) < RUNS_PER_PAGE:
            break
    return observations


def render(verdicts: Sequence[LaneVerdict]) -> str:
    lines = ["## Advisory review liveness", ""]
    for verdict in verdicts:
        mark = "DOWN" if verdict.down else "ok"
        lines.append(
            f"- **{verdict.lane}**: {mark} — {verdict.detail} "
            f"({verdict.failed}/{verdict.observed} posted nothing)"
        )
    if any(v.down for v in verdicts):
        lines += [
            "",
            "A lane reported DOWN attempted a review on every run in the window "
            "and left no signed comment on any of them. Because both lanes carry "
            "`continue-on-error`, the API records those runs as `success` and "
            "nothing on any Pull Request shows it; the step log of the newest "
            "run is the place to look.",
        ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--window", type=int, default=5)
    parser.add_argument("--summary", default="")
    args = parser.parse_args(argv)

    try:
        verdicts = [
            evaluate(
                lane.name,
                collect_observations(args.repository, lane, limit=args.window * 3),
                window=args.window,
            )
            for lane in REVIEW_LANES
        ]
    except LivenessUnavailable as error:
        print(str(error), file=sys.stderr)
        return 1

    report = render(verdicts)
    print(report, end="")
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as handle:
            handle.write(report)
    return 1 if any(v.down for v in verdicts) else 0


if __name__ == "__main__":
    sys.exit(main())
