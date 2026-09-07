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
from datetime import datetime, timezone
from typing import NamedTuple
import argparse
import json
import os
import re
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

# The reviewer set, declared once. `ci.yml` builds its matrix from `--select`
# below rather than listing these again, so a backend cannot exist for the
# workflow and not for the check that judges it.
CLAUDE_BACKENDS = (
    {"backend": "glm",
     "base_url": "https://api.z.ai/api/anthropic",
     "secret_name": "ZAI_CODING_KEY"},
    {"backend": "kimi",
     "base_url": "https://api.kimi.com/coding/",
     "secret_name": "KIMI_CODING_KEY"},
)


# The workflows a reviewer can run in. `ci.yml` is where the lanes have lived
# since #659; `pr-review.yml` is the standalone entry the capacity plan (T4)
# prepares, which runs the same jobs under the same names and step names so
# one lane definition describes both. Both are watched until T5a retires the
# `ci.yml` copies; the standalone entry posts nothing on `pull_request` runs
# until its switch is flipped, so its lanes read "too few to judge", not DOWN.
REVIEW_WORKFLOWS = ("ci.yml", "pr-review.yml")
GROK_MARKER = "<!-- lmdj-grok-review -->"


def claude_lane(backend: str, workflow: str = "ci.yml") -> "Lane":
    """The lane one Claude backend occupies inside `workflow`."""
    return Lane(workflow, f"Claude review ({backend})", "Review",
                f"<!-- lmdj-review: {backend} -->", CLAUDE_SIGNS_SINCE)


def claude_lanes(backend: str) -> tuple["Lane", ...]:
    """Every lane one Claude backend occupies, across the review workflows."""
    return tuple(claude_lane(backend, workflow) for workflow in REVIEW_WORKFLOWS)


def grok_lane(workflow: str = "ci.yml") -> "Lane":
    return Lane(workflow, "Grok advisory review", "Run advisory Grok review", GROK_MARKER)


REVIEW_LANES = (
    *(claude_lane(entry["backend"], workflow)
      for workflow in REVIEW_WORKFLOWS for entry in CLAUDE_BACKENDS),
    *(grok_lane(workflow) for workflow in REVIEW_WORKFLOWS),
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


class Observation(NamedTuple):
    """One judged attempt: what it produced, and when the run started."""

    outcome: str
    at: str


# A lane that stopped being scheduled stops producing observations, and its
# last ones stay in the window forever. Without an age limit the first backend
# demoted by `--select` could never be promoted back: its final failures would
# read as DOWN for the life of the repository, and a vendor outage would become
# permanent. Past this many days the window is treated as no longer describing
# the lane -- unknown, not down -- so the selector tries it again and gathers
# fresh evidence. Three days is short enough that a recovery is picked up
# quickly and long enough that a quiet weekend does not churn the choice.
STALE_AFTER_DAYS = 3


def _age_days(when: str, now: datetime) -> float:
    """Days between an ISO-8601 API timestamp and `now`, or 0.0 if unparseable.

    Unparseable means "do not claim it is old": the risk of a bad parse is
    silently promoting a dead backend, and treating the reading as fresh keeps
    the existing verdict rather than inventing a new one.
    """
    try:
        moment = datetime.fromisoformat(when.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return 0.0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (now - moment).total_seconds() / 86400.0


def evaluate(
    lane: str,
    observations: Sequence[Observation],
    *,
    window: int,
    now: datetime | None = None,
) -> LaneVerdict:
    """Decide whether a lane is down from its recent observations.

    `observations` is newest first and holds exactly one `success` or
    `failure` per run in which this lane attempted a review. Runs that made
    no attempt have already been dropped by the collector.

    `now` enables the staleness rule; without it the window is judged on
    content alone, which is what the scheduled report did before backends
    could be taken out of rotation.
    """
    considered = list(observations)[:window]
    failed = sum(1 for observation in considered if observation.outcome == "failure")
    if considered and now is not None:
        age = _age_days(considered[0].at, now)
        if age > STALE_AFTER_DAYS:
            return LaneVerdict(
                lane, len(considered), failed, False,
                f"newest attempt is {age:.1f} days old; the lane is not being "
                f"exercised, so the window no longer describes it",
            )
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
) -> list[Observation]:
    """One `success` or `failure` per attempted run for `lane`, newest first."""
    if lane.workflow == "pr-review.yml":
        return collect_standalone_observations(repository, lane, limit=limit, api=api)
    # Paged until `limit` *observations* exist, not until `limit` runs have
    # been seen. The Claude lanes live in ci.yml, which also runs on push,
    # dispatch and draft events -- completed, non-cancelled runs that skip the
    # review job entirely. Budgeting on run count let those pad the pages,
    # stop the pager early, and hand `evaluate` too few observations to judge:
    # exit 0, green while blind, the case this loop exists to prevent. Only a
    # judged attempt spends the budget now. The event filter removes the
    # push and dispatch runs before they are fetched; drafts still arrive as
    # pull_request runs and are dropped below when their job is skipped.
    observations: list[Observation] = []
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
            observations.append(
                Observation("success" if posted else "failure", run["created_at"])
            )
            if len(observations) >= limit:
                return observations
        if len(batch) < RUNS_PER_PAGE:
            break
    return observations


def exact_review_posted(repository: str, number: int, run: str, attempt: str,
                        backend: str, *, api: Request = _api) -> bool:
    """A trusted bot COMMENT review from this run/attempt, attached to its head.

    Legacy marker/time heuristics remain only for the unchanged ci.yml entry.
    User comments, a later head, another backend or an updated sticky comment
    cannot stand in for this immutable publisher observation.
    """
    identity = re.compile(
        r"^<!-- lmdj-review-v1 " + re.escape(repository) + " " + str(number)
        + r" ([0-9a-f]{40}) " + re.escape(run) + " " + re.escape(attempt)
        + " " + re.escape(backend) + r" -->$"
    )
    for page in range(1, 11):
        reviews = api(f"/repos/{repository}/pulls/{number}/reviews?per_page=100&page={page}",
                      f"reading exact review evidence on PR {number}") or []
        for review in reviews:
            lines = (review.get("body") or "").splitlines()
            match = identity.fullmatch(lines[1]) if len(lines) > 1 else None
            if (match and review.get("commit_id") == match.group(1)
                    and review.get("state") == "COMMENTED"
                    and (review.get("user") or {}).get("login") == "github-actions[bot]"):
                return True
        if len(reviews) < 100:
            return False
    raise LivenessUnavailable("why: review evidence exceeded the bounded page budget; remedy: inspect this run manually")


def collect_standalone_observations(repository: str, lane: Lane, *, limit: int,
                                   api: Request = _api) -> list[Observation]:
    backend = "grok" if lane.marker == GROK_MARKER else lane.job.rsplit("(", 1)[1].rstrip(")")
    publisher = "Publish Grok advisory review" if backend == "grok" else f"Publish Claude review ({backend})"
    observations = []
    for page in range(1, MAX_RUN_PAGES + 1):
        payload = api(f"/repos/{repository}/actions/workflows/pr-review.yml/runs"
                      f"?status=completed&per_page={RUNS_PER_PAGE}&page={page}",
                      "listing standalone PR review runs") or {}
        batch = payload.get("workflow_runs") or []
        for run in batch:
            if run.get("conclusion") in SILENT or run.get("event") not in {"pull_request", "workflow_dispatch"}:
                continue
            if run.get("event") == "workflow_dispatch" and run.get("head_branch") != "main":
                continue
            # dispatch has no run.pull_requests and head_sha is the control
            # revision, not the PR head. The trusted run-name supplies its PR.
            named = re.match(r"^PR Review / #([1-9][0-9]*) @ ", run.get("display_title") or "")
            if not named:
                continue
            jobs = (api(f"/repos/{repository}/actions/runs/{run['id']}/jobs?per_page=100",
                        "reading standalone review and publisher outcomes") or {}).get("jobs") or []
            job = next((j for j in jobs if j.get("name") == lane.job), None)
            if not job or job.get("conclusion") in SILENT:
                continue
            publication = next((j for j in jobs if j.get("name") == publisher), {})
            step = next((s.get("conclusion") for s in job.get("steps", []) if s.get("name") == lane.step), None)
            posted = (job.get("conclusion") == "success" and step == "success"
                      and publication.get("conclusion") == "success"
                      and exact_review_posted(repository, int(named.group(1)), str(run["id"]),
                                              str(run.get("run_attempt", 1)), backend, api=api))
            observations.append(Observation("success" if posted else "failure", run["created_at"]))
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


def select_backends(
    repository: str,
    candidates: Sequence[str],
    *,
    window: int,
    now: datetime,
    api: Request = _api,
) -> tuple[list[str], str]:
    """The Claude backends to run on one Pull Request, and why (#659 item 3).

    Exactly one runs. `candidates` is the preference order: the first entry is
    the primary, and a later one is used only when everything before it is
    DOWN. The choice is made from the same evidence the scheduled report uses
    -- what each backend actually posted -- never from a step conclusion,
    which `continue-on-error` rewrites to `success`.

    Fail open in both directions that matter. A backend whose window is too
    short, or too old to describe it, is *not* DOWN and is used: running it is
    how evidence accrues, and withholding review because the evidence is thin
    would make silence self-perpetuating. If every candidate is DOWN the
    primary runs anyway -- the scheduled check is already alerting, and a
    Pull Request should not lose its reviewer because the alert is correct.
    """
    if len(candidates) == 1:
        # Nothing to choose between, so nothing to read the API for. `ci.yml`
        # takes this path on push and dispatch runs, where there is no Pull
        # Request to review and the job will be skipped anyway.
        return list(candidates), f"{candidates[0]} is the only candidate"
    reasons = []
    for backend in candidates:
        # A backend's evidence is what it posted from any review workflow. The
        # two entries are the same lane on a different trigger, and after T5a
        # only the standalone one keeps posting -- judging `ci.yml` alone would
        # then see every backend age into "stale" and never DOWN.
        observations = sorted(
            (observation
             for lane in claude_lanes(backend)
             for observation in collect_observations(repository, lane, limit=window, api=api)),
            key=lambda observation: observation.at, reverse=True,
        )
        verdict = evaluate(backend, observations, window=window, now=now)
        reasons.append(f"{backend}: {verdict.detail}")
        if not verdict.down:
            note = "primary" if backend == candidates[0] else "fallback for a DOWN primary"
            return [backend], f"{backend} ({note}) — " + "; ".join(reasons)
    return (
        [candidates[0]],
        f"every candidate is DOWN, running {candidates[0]} anyway — " + "; ".join(reasons),
    )


def _selection_matrix(backends: Sequence[str]) -> dict:
    """The `strategy.matrix` value for the chosen backends."""
    chosen = set(backends)
    return {"include": [dict(e) for e in CLAUDE_BACKENDS if e["backend"] in chosen]}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--window", type=int, default=5)
    parser.add_argument("--summary", default="")
    parser.add_argument(
        "--select",
        default="",
        help=(
            "comma-separated backend preference order; prints the matrix for the "
            "one to run instead of the liveness report"
        ),
    )
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)

    if args.select:
        named = [name.strip() for name in args.select.split(",") if name.strip()]
        known = {entry["backend"] for entry in CLAUDE_BACKENDS}
        unknown = [name for name in named if name not in known]
        candidates = [name for name in named if name in known]
        if unknown or not candidates:
            # Say so loudly, then continue anyway. `CLAUDE_REVIEW_ORDER` is an
            # operator knob, `ci.yml` runs this under `set -euo pipefail`, and
            # a nonzero exit here would leave `strategy.matrix` empty -- so a
            # typo in the knob would cost the Pull Request its review entirely.
            # Whatever is left of the order stands; if nothing is, the first
            # declared backend does.
            print(
                f"why: --select names {unknown or 'nothing'}, which is not a declared "
                f"backend; remedy: use a comma-separated subset of {sorted(known)}",
                file=sys.stderr,
            )
            if not candidates:
                candidates = [CLAUDE_BACKENDS[0]["backend"]]
        try:
            chosen, reason = select_backends(
                args.repository, candidates, window=args.window, now=now
            )
        except Exception as error:  # noqa: BLE001
            # Deliberately total. `ci.yml` builds `strategy.matrix` from this
            # output, so anything that leaves it empty costs the Pull Request
            # its review -- and a broken selector is a worse reason to lose a
            # reviewer than a broken backend. Unreadable evidence, an API
            # shape change, a bug here: all mean "run the primary and say so".
            chosen = [candidates[0]]
            reason = f"selection failed ({type(error).__name__}: {error}); using {chosen[0]}"
        print(f"::notice::advisory review backend — {reason}")
        print(json.dumps(_selection_matrix(chosen)))
        return 0

    try:
        verdicts = [
            evaluate(
                lane.name,
                collect_observations(args.repository, lane, limit=args.window * 3),
                window=args.window,
                now=now,
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
