#!/usr/bin/env python3
"""Exact-revision self-test evidence: what a complete run is, and what one proved.

Two pure functions carry the protocol. ``resolve`` turns a request (the daily
schedule, an operator's node dispatch, a release candidate) into the identity
one self-test batch will run under, or into a recorded skip when the target is
the one the last complete conclusion already covered. ``aggregate`` turns the
per-job observations of a finished batch into one verdict over the policy's
complete suite list, refusing anything that is not evidence for exactly that
identity: another target, another run or attempt, a suite the policy does not
know, a duplicate identity, a missing suite, an empty batch.

Nothing here touches GitHub, a clock, or storage. Callers pass the tip, the
main-history predicate, the run identity and the timestamps in; the tests pass
values. The schema strings are CI-internal evidence versions, not product or
cross-language Contracts, so ``contracts/`` does not learn about them.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import sys


POLICY_SCHEMA = "lmdj.ci-self-test-policy.v1"
EVIDENCE_SCHEMA = "lmdj.ci-self-test.v1"

REQUEST_KINDS = ("schedule", "node", "candidate")
#: Request kinds an unchanged target may deduplicate into a skip. Explicit
#: node and candidate requests always run: the operator asked for evidence.
DEDUPLICATED_KINDS = frozenset({"schedule"})

JOB_CONCLUSIONS = frozenset({"success", "failure", "cancelled", "skipped", "timed_out"})
ARTIFACT_STATES = frozenset({"uploaded", "failed", "none"})

#: Suite statuses. ``passed`` is the only one that counts toward a passed
#: batch; the others say why not, so a red batch is actionable rather than a
#: colour. ``superseded`` is the expected outcome of a schedule request that a
#: newer target replaced before it ran -- not a failure, not a pass.
SUITE_PASSED = "passed"
SUITE_TEST_FAILURE = "test_failure"
SUITE_INFRASTRUCTURE_FAILURE = "infrastructure_failure"
SUITE_BLOCKED = "blocked"
SUITE_MISSING = "missing"

BATCH_PASSED = "passed"
BATCH_FAILED = "failed"
BATCH_INVALID = "invalid"
BATCH_SUPERSEDED = "superseded"
#: Conclusions a later schedule request may deduplicate against. A batch that
#: was invalid or superseded proved nothing about its target, so the next
#: request for that target runs.
COMPLETE_BATCH_STATUSES = frozenset({BATCH_PASSED, BATCH_FAILED})

_SHA = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]*$")


class SelfTestPolicyError(ValueError):
    """The policy file itself is not a valid complete-suite list."""


def _diagnostic(why: str, remedy: str) -> str:
    return f"why: {why}; remedy: {remedy}"


def canonical_json(document: object) -> str:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest_of(document: object) -> str:
    return hashlib.sha256(canonical_json(document).encode("ascii")).hexdigest()


# --------------------------------------------------------------------------
# Policy
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Suite:
    id: str
    origin: Mapping[str, str]
    jobs: tuple[str, ...]
    required: bool
    #: job -> alternatives whose success makes a skip of that job legitimate.
    alternatives: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def scope_lane(self) -> str | None:
        return self.origin["lane"] if self.origin.get("kind") == "scope_lane" else None

    @property
    def nightly_job(self) -> str | None:
        return self.origin["job"] if self.origin.get("kind") == "nightly_job" else None


@dataclass(frozen=True)
class Policy:
    schema: str
    evidence_schema: str
    scope_policy: str
    suites: tuple[Suite, ...]
    #: sha256 of the canonical policy document; identifies which complete-suite
    #: definition a batch was judged against.
    revision: str

    def suite(self, suite_id: str) -> Suite | None:
        for suite in self.suites:
            if suite.id == suite_id:
                return suite
        return None

    @property
    def job_owner(self) -> dict[str, str]:
        return {job: suite.id for suite in self.suites for job in suite.jobs}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SelfTestPolicyError(message)


def parse_policy(document: object) -> Policy:
    _require(isinstance(document, dict), "policy document must be a JSON object")
    assert isinstance(document, dict)
    _require(document.get("schema") == POLICY_SCHEMA,
             f"policy schema must be {POLICY_SCHEMA}")
    _require(document.get("evidence_schema") == EVIDENCE_SCHEMA,
             f"policy evidence_schema must be {EVIDENCE_SCHEMA}")
    scope_policy = document.get("scope_policy")
    _require(isinstance(scope_policy, str) and bool(scope_policy),
             "policy scope_policy must name the scope policy path")
    raw_suites = document.get("suites")
    _require(isinstance(raw_suites, list) and bool(raw_suites),
             "policy suites must be a non-empty list")
    assert isinstance(raw_suites, list)

    suites: list[Suite] = []
    seen_ids: set[str] = set()
    seen_jobs: dict[str, str] = {}
    for raw in raw_suites:
        _require(isinstance(raw, dict), "each suite must be an object")
        allowed = {"id", "origin", "jobs", "required", "alternatives", "note"}
        extra = set(raw) - allowed
        _require(not extra, f"suite carries unknown keys {sorted(extra)}")
        suite_id = raw.get("id")
        _require(isinstance(suite_id, str) and _IDENTIFIER.match(suite_id) is not None,
                 f"suite id {suite_id!r} is not a lower-case identifier")
        _require(suite_id not in seen_ids, f"suite {suite_id} is declared twice")
        seen_ids.add(suite_id)

        origin = raw.get("origin")
        _require(isinstance(origin, dict), f"suite {suite_id} origin must be an object")
        kind = origin.get("kind")
        if kind == "scope_lane":
            _require(set(origin) == {"kind", "lane"} and isinstance(origin["lane"], str),
                     f"suite {suite_id} scope_lane origin needs exactly a lane")
        elif kind == "nightly_job":
            _require(set(origin) == {"kind", "workflow", "job"}
                     and isinstance(origin["workflow"], str) and isinstance(origin["job"], str),
                     f"suite {suite_id} nightly_job origin needs a workflow and a job")
        else:
            raise SelfTestPolicyError(
                f"suite {suite_id} origin kind {kind!r} is not scope_lane or nightly_job")

        jobs = raw.get("jobs")
        _require(isinstance(jobs, list) and bool(jobs)
                 and all(isinstance(job, str) and _IDENTIFIER.match(job) for job in jobs),
                 f"suite {suite_id} jobs must be a non-empty list of job ids")
        _require(len(set(jobs)) == len(jobs), f"suite {suite_id} lists a job twice")
        for job in jobs:
            _require(job not in seen_jobs,
                     f"job {job} belongs to both {seen_jobs.get(job)} and {suite_id}")
            seen_jobs[job] = suite_id
        _require(raw.get("required") is True,
                 f"suite {suite_id} must be required: a complete run has no optional suite")

        alternatives_raw = raw.get("alternatives", {})
        _require(isinstance(alternatives_raw, dict),
                 f"suite {suite_id} alternatives must map a job to alternative jobs")
        alternatives: dict[str, tuple[str, ...]] = {}
        for job, alts in alternatives_raw.items():
            _require(job in jobs, f"suite {suite_id} alternative for {job} names a job it does not list")
            _require(isinstance(alts, list) and bool(alts)
                     and all(isinstance(alt, str) and _IDENTIFIER.match(alt) for alt in alts),
                     f"suite {suite_id} alternatives for {job} must be a non-empty list of job ids")
            _require(all(alt not in jobs for alt in alts),
                     f"suite {suite_id} alternative for {job} must not be one of its own required jobs")
            alternatives[job] = tuple(alts)
        suites.append(Suite(suite_id, dict(origin), tuple(jobs), True, alternatives))

    for suite in suites:
        for alts in suite.alternatives.values():
            for alt in alts:
                _require(alt not in seen_jobs,
                         f"alternative job {alt} is a required job of suite {seen_jobs.get(alt)}")

    return Policy(POLICY_SCHEMA, EVIDENCE_SCHEMA, scope_policy, tuple(suites), digest_of(document))


def load_policy(path: Path) -> Policy:
    with path.open("r", encoding="utf-8") as handle:
        return parse_policy(json.load(handle))


def scope_parity(policy: Policy, scope_policy: Mapping[str, object]) -> tuple[str, ...]:
    """Diagnostics when the scope-lane suites drift from scope_policy.json.

    Empty means the two definitions of "every lane" agree. Each diagnostic
    names the lane or job and the edit that restores parity, so a change to
    either file fails a contract test with the remedy in the message.
    """
    diagnostics: list[str] = []
    lanes = scope_policy.get("lanes")
    lane_jobs = scope_policy.get("lane_jobs")
    if not isinstance(lanes, list) or not isinstance(lane_jobs, dict):
        return (_diagnostic("scope policy has no lanes / lane_jobs to compare against",
                            "point self_test_policy.json at a valid scope_policy.json"),)
    lane_suites = {suite.scope_lane: suite for suite in policy.suites if suite.scope_lane}
    for lane in lanes:
        suite = lane_suites.get(lane)
        if suite is None:
            diagnostics.append(_diagnostic(
                f"scope lane {lane} has no self-test suite",
                f"add a scope_lane suite for {lane} with jobs {lane_jobs.get(lane)} to self_test_policy.json"))
            continue
        expected = tuple(lane_jobs.get(lane, ()))
        if suite.jobs != expected:
            diagnostics.append(_diagnostic(
                f"suite {suite.id} lists jobs {list(suite.jobs)} but scope lane {lane} runs {list(expected)}",
                f"make suite {suite.id} jobs equal scope_policy.json lane_jobs[{lane}]"))
    for lane, suite in lane_suites.items():
        if lane not in lanes:
            diagnostics.append(_diagnostic(
                f"suite {suite.id} mirrors scope lane {lane}, which scope_policy.json no longer declares",
                f"remove suite {suite.id} or restore lane {lane} in scope_policy.json"))
    return tuple(diagnostics)


# --------------------------------------------------------------------------
# Resolve
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Request:
    kind: str
    #: Exact main SHA, or None for a schedule request that takes the tip.
    target_revision: str | None
    requested_by: str


@dataclass(frozen=True)
class Identity:
    evidence_schema: str
    request_kind: str
    control_revision: str
    target_revision: str
    run_id: int
    run_attempt: int
    policy_revision: str

    def as_document(self) -> dict[str, object]:
        return {
            "evidence_schema": self.evidence_schema,
            "request_kind": self.request_kind,
            "control_revision": self.control_revision,
            "target_revision": self.target_revision,
            "run_id": self.run_id,
            "run_attempt": self.run_attempt,
            "policy_revision": self.policy_revision,
        }


@dataclass(frozen=True)
class Conclusion:
    """What an earlier batch concluded about a target, as the store retains it."""

    target_revision: str
    status: str
    evidence_digest: str
    policy_revision: str


@dataclass(frozen=True)
class Resolution:
    action: str  # run | skip | reject
    identity: Identity | None
    diagnostics: tuple[str, ...]

    def as_document(self) -> dict[str, object]:
        return {
            "evidence_schema": EVIDENCE_SCHEMA,
            "action": self.action,
            "identity": self.identity.as_document() if self.identity else None,
            "diagnostics": list(self.diagnostics),
        }


def _reject(*diagnostics: str) -> Resolution:
    return Resolution("reject", None, tuple(diagnostics))


def resolve(
    request: Request,
    *,
    tip_revision: str,
    is_main_history: Callable[[str], bool],
    last_conclusion: Conclusion | None,
    control_revision: str,
    run_id: int,
    run_attempt: int,
    policy: Policy,
) -> Resolution:
    """Fix the target one batch will test, or record why none runs.

    ``is_main_history`` answers whether a SHA is reachable from main; the
    caller supplies it (``git merge-base --is-ancestor`` in CI, a set in tests)
    so this function never runs git. A schedule request whose target is the
    one the last *complete* conclusion already judged under the same policy
    revision skips; explicit requests never do.
    """
    if request.kind not in REQUEST_KINDS:
        return _reject(_diagnostic(
            f"request kind {request.kind!r} is not one of {list(REQUEST_KINDS)}",
            "dispatch as schedule, node or candidate"))
    if not request.requested_by:
        return _reject(_diagnostic("request records no requester",
                                   "record the event or operator that asked for this batch"))
    for label, value in (("control revision", control_revision), ("tip revision", tip_revision)):
        if not _SHA.match(value or ""):
            return _reject(_diagnostic(f"{label} {value!r} is not a full 40-hex SHA",
                                       "pass the exact commit SHA, not a ref or short form"))
    if run_id <= 0 or run_attempt <= 0:
        return _reject(_diagnostic(
            f"run id {run_id} / attempt {run_attempt} do not identify a GitHub run",
            "pass github.run_id and github.run_attempt of the batch"))

    if request.target_revision is None:
        if request.kind != "schedule":
            return _reject(_diagnostic(
                f"{request.kind} request names no target",
                "explicit requests pass the exact main SHA they want tested"))
        target = tip_revision
    else:
        target = request.target_revision
    if not _SHA.match(target):
        return _reject(_diagnostic(f"target {target!r} is not a full 40-hex SHA",
                                   "pass the exact 40-hex commit SHA"))
    if not is_main_history(target):
        return _reject(_diagnostic(
            f"target {target[:12]} is not in main's history",
            "self-tests judge main revisions only; pick a SHA reachable from main"))

    identity = Identity(EVIDENCE_SCHEMA, request.kind, control_revision, target,
                        run_id, run_attempt, policy.revision)
    if (request.kind in DEDUPLICATED_KINDS and last_conclusion is not None
            and last_conclusion.target_revision == target
            and last_conclusion.status in COMPLETE_BATCH_STATUSES
            and last_conclusion.policy_revision == policy.revision):
        return Resolution("skip", identity, (
            f"target {target[:12]} already has a complete {last_conclusion.status} conclusion "
            f"({last_conclusion.evidence_digest[:12]}) under this policy; main has not moved, "
            "so the schedule batch is skipped and that conclusion stands with its own date",
        ))
    return Resolution("run", identity, ())


# --------------------------------------------------------------------------
# Aggregate
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Observation:
    suite: str
    job: str
    run_id: int
    run_attempt: int
    target_revision: str
    conclusion: str
    artifact: str = "none"
    blocked_by: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "Observation":
        allowed = {"suite", "job", "run_id", "run_attempt", "target_revision", "conclusion",
                   "artifact", "blocked_by", "started_at", "completed_at"}
        extra = set(document) - allowed
        if extra:
            raise ValueError(f"observation carries unknown keys {sorted(extra)}")
        return cls(
            suite=str(document["suite"]),
            job=str(document["job"]),
            run_id=int(document["run_id"]),  # type: ignore[arg-type]
            run_attempt=int(document["run_attempt"]),  # type: ignore[arg-type]
            target_revision=str(document["target_revision"]),
            conclusion=str(document["conclusion"]),
            artifact=str(document.get("artifact", "none")),
            blocked_by=(str(document["blocked_by"]) if document.get("blocked_by") else None),
            started_at=(str(document["started_at"]) if document.get("started_at") else None),
            completed_at=(str(document["completed_at"]) if document.get("completed_at") else None),
        )


@dataclass(frozen=True)
class SuiteResult:
    id: str
    status: str
    diagnostics: tuple[str, ...]
    jobs: Mapping[str, str]


@dataclass(frozen=True)
class Verdict:
    identity: Identity
    status: str
    suites: tuple[SuiteResult, ...]
    diagnostics: tuple[str, ...]
    superseded_by: str | None = None

    def as_document(self) -> dict[str, object]:
        return {
            "evidence_schema": self.identity.evidence_schema,
            "identity": self.identity.as_document(),
            "status": self.status,
            "superseded_by": self.superseded_by,
            "suites": [
                {"id": result.id, "status": result.status,
                 "jobs": dict(sorted(result.jobs.items())),
                 "diagnostics": list(result.diagnostics)}
                for result in sorted(self.suites, key=lambda result: result.id)
            ],
            "diagnostics": list(self.diagnostics),
        }

    @property
    def digest(self) -> str:
        return digest_of(self.as_document())

    def conclusion(self) -> Conclusion:
        return Conclusion(self.identity.target_revision, self.status, self.digest,
                          self.identity.policy_revision)


def _invalid(identity: Identity, diagnostics: Sequence[str]) -> Verdict:
    return Verdict(identity, BATCH_INVALID, (), tuple(diagnostics))


def supersede(identity: Identity, *, by_target: str) -> Verdict:
    """The expected end of a schedule batch a newer target replaced before it ran."""
    if identity.request_kind not in DEDUPLICATED_KINDS:
        return _invalid(identity, (_diagnostic(
            f"a {identity.request_kind} request for {identity.target_revision[:12]} cannot be superseded",
            "explicit requests run to a conclusion or are cancelled by the operator; only schedule "
            "pending may be replaced by a newer target"),))
    if not _SHA.match(by_target) or by_target == identity.target_revision:
        return _invalid(identity, (_diagnostic(
            f"superseding target {by_target!r} is not a different full SHA",
            "record the newer main SHA that replaced this pending batch"),))
    return Verdict(identity, BATCH_SUPERSEDED, (), (
        f"schedule batch for {identity.target_revision[:12]} was replaced by {by_target[:12]} "
        "before it ran; this is expected supersession, not a failure, and proves nothing about either target",
    ), superseded_by=by_target)


def aggregate(identity: Identity, policy: Policy, observations: Iterable[Observation]) -> Verdict:
    """Judge one finished batch against the complete suite list.

    Anything that is not evidence for exactly ``identity`` makes the batch
    ``invalid`` with a diagnostic per defect: another target or run/attempt,
    a job the policy does not know, the same job observed twice. A batch with
    no observations is not a pass either. Otherwise every suite is classified
    and the batch passes only when all of them did.
    """
    if identity.policy_revision != policy.revision:
        return _invalid(identity, (_diagnostic(
            f"identity was resolved under policy {identity.policy_revision[:12]} but is judged under {policy.revision[:12]}",
            "aggregate with the policy revision the batch was resolved under, or resolve again"),))

    rows = list(observations)
    if not rows:
        return _invalid(identity, (_diagnostic(
            "batch produced no observations",
            "a batch with no job results proved nothing; treat as infrastructure failure and rerun"),))

    owner = policy.job_owner
    known_alternatives = {alt for suite in policy.suites for alts in suite.alternatives.values() for alt in alts}
    defects: list[str] = []
    seen: dict[tuple[str, str], Observation] = {}
    for row in rows:
        if row.target_revision != identity.target_revision:
            defects.append(_diagnostic(
                f"{row.suite}/{row.job} reports target {row.target_revision[:12]}, batch target is {identity.target_revision[:12]}",
                "every job checks out and reports the resolved target; drop results from other revisions"))
        if (row.run_id, row.run_attempt) != (identity.run_id, identity.run_attempt):
            defects.append(_diagnostic(
                f"{row.suite}/{row.job} comes from run {row.run_id} attempt {row.run_attempt}, batch is run {identity.run_id} attempt {identity.run_attempt}",
                "one batch is one run attempt; a rerun is a new batch, not extra rows in this one"))
        if row.conclusion not in JOB_CONCLUSIONS:
            defects.append(_diagnostic(
                f"{row.suite}/{row.job} conclusion {row.conclusion!r} is not a GitHub job conclusion",
                f"report one of {sorted(JOB_CONCLUSIONS)}"))
        if row.artifact not in ARTIFACT_STATES:
            defects.append(_diagnostic(
                f"{row.suite}/{row.job} artifact state {row.artifact!r} is unknown",
                f"report one of {sorted(ARTIFACT_STATES)}"))
        if row.job in known_alternatives:
            declaring_suite = owner[_alternative_owner(policy, row.job)]
            if row.suite != declaring_suite:
                defects.append(_diagnostic(
                    f"alternative job {row.job} was reported under suite {row.suite} but {declaring_suite} declares it",
                    "report an alternative under the suite whose job it may stand in for"))
        elif owner.get(row.job) is None:
            defects.append(_diagnostic(
                f"job {row.job} (reported under suite {row.suite}) is not in the self-test policy",
                "add it to a suite in self_test_policy.json or stop reporting it; an unknown job cannot count toward a complete run"))
        elif owner[row.job] != row.suite:
            defects.append(_diagnostic(
                f"job {row.job} was reported under suite {row.suite} but belongs to {owner[row.job]}",
                "report each job under the suite the policy assigns it"))
        key = (row.suite, row.job)
        if key in seen:
            defects.append(_diagnostic(
                f"{row.suite}/{row.job} was observed twice in run {identity.run_id} attempt {identity.run_attempt}",
                "one observation per job per attempt; a repeated upload must be deduplicated before aggregation"))
        seen[key] = row
    if defects:
        return _invalid(identity, defects)

    by_job = {row.job: row for row in rows}
    results: list[SuiteResult] = []
    for suite in policy.suites:
        results.append(_judge_suite(suite, by_job))

    batch_diagnostics: list[str] = []
    failed = [result for result in results if result.status != SUITE_PASSED]
    if failed:
        batch_diagnostics.append(_diagnostic(
            "required suites did not pass: " + ", ".join(f"{r.id}={r.status}" for r in failed),
            "a complete run passes only when every suite passed; see each suite's diagnostics"))
    status = BATCH_FAILED if failed else BATCH_PASSED
    return Verdict(identity, status, tuple(results), tuple(batch_diagnostics))


def _alternative_owner(policy: Policy, alternative: str) -> str:
    for suite in policy.suites:
        for job, alts in suite.alternatives.items():
            if alternative in alts:
                return job
    return alternative


def _judge_suite(suite: Suite, by_job: Mapping[str, Observation]) -> SuiteResult:
    jobs: dict[str, str] = {}
    diagnostics: list[str] = []
    statuses: list[str] = []
    for job in suite.jobs:
        row = by_job.get(job)
        if row is None:
            jobs[job] = "missing"
            statuses.append(SUITE_MISSING)
            diagnostics.append(_diagnostic(
                f"suite {suite.id} has no observation for job {job}",
                "a required job that never reported is not a pass; find out whether it ran and rerun the batch"))
            continue
        jobs[job] = row.conclusion
        if row.conclusion == "success":
            if row.artifact == "failed":
                statuses.append(SUITE_INFRASTRUCTURE_FAILURE)
                diagnostics.append(_diagnostic(
                    f"{suite.id}/{job} succeeded but its evidence artifact failed to upload",
                    "a result without retained evidence cannot be reused; rerun the job or repair artifact upload"))
            continue
        if row.conclusion == "skipped":
            alternatives = suite.alternatives.get(job, ())
            witnesses = [alt for alt in alternatives
                         if by_job.get(alt) is not None and by_job[alt].conclusion == "success"]
            if witnesses:
                jobs[job] = f"skipped (alternative {witnesses[0]} succeeded)"
                continue
            if row.blocked_by:
                statuses.append(SUITE_BLOCKED)
                diagnostics.append(_diagnostic(
                    f"{suite.id}/{job} did not run because {row.blocked_by} failed",
                    f"fix {row.blocked_by}; this job is blocked, not passed"))
                continue
            statuses.append(SUITE_INFRASTRUCTURE_FAILURE)
            diagnostics.append(_diagnostic(
                f"{suite.id}/{job} was skipped with no successful alternative",
                "a required job may only be skipped when its declared alternative succeeded in the same run"))
            continue
        if row.conclusion == "failure":
            statuses.append(SUITE_TEST_FAILURE)
            diagnostics.append(_diagnostic(
                f"{suite.id}/{job} failed",
                "read the job's failure output; file or update the failure Issue for this suite"))
            continue
        statuses.append(SUITE_INFRASTRUCTURE_FAILURE)
        diagnostics.append(_diagnostic(
            f"{suite.id}/{job} ended {row.conclusion}",
            "a cancelled or timed-out job proved nothing; rerun the batch once the cause is known"))
    if not statuses:
        return SuiteResult(suite.id, SUITE_PASSED, (), jobs)
    for candidate in (SUITE_TEST_FAILURE, SUITE_INFRASTRUCTURE_FAILURE, SUITE_MISSING, SUITE_BLOCKED):
        if candidate in statuses:
            return SuiteResult(suite.id, candidate, tuple(diagnostics), jobs)
    return SuiteResult(suite.id, statuses[0], tuple(diagnostics), jobs)


# --------------------------------------------------------------------------
# Observations from a workflow's `needs` context
# --------------------------------------------------------------------------


NEEDS_RESULTS = frozenset({"success", "failure", "cancelled", "skipped"})


def observations_from_needs(
    identity: Identity,
    policy: Policy,
    needs: Mapping[str, Mapping[str, object]],
    *,
    aliases: Mapping[str, str] | None = None,
    dependencies: Mapping[str, Sequence[str]] | None = None,
) -> tuple[list[Observation], tuple[str, ...]]:
    """Turn the caller's ``needs`` context into one observation per known job.

    ``needs`` is ``toJSON(needs)`` from the verdict job: job id to
    ``{"result": ...}``. ``aliases`` maps a policy job to the caller job that
    ran it (a reusable-workflow caller reports one result for the workflow
    it called). ``dependencies`` maps a job to the upstream jobs whose
    non-success explains a skip; the first such upstream becomes
    ``blocked_by``. A job absent from ``needs`` yields no observation, so
    ``aggregate`` reports the suite as missing rather than this function
    inventing a result. Diagnostics name every job whose result is not a
    GitHub job result; those rows are still emitted so aggregate rejects them.
    """
    aliases = dict(aliases or {})
    dependencies = {job: tuple(ups) for job, ups in (dependencies or {}).items()}
    rows: list[Observation] = []
    diagnostics: list[str] = []

    def result_of(job: str) -> str | None:
        entry = needs.get(aliases.get(job, job))
        if not isinstance(entry, Mapping):
            return None
        return str(entry.get("result", ""))

    watched = [(suite.id, job) for suite in policy.suites for job in suite.jobs]
    watched += [(suite.id, alt) for suite in policy.suites
                for alts in suite.alternatives.values() for alt in alts]
    for suite_id, job in watched:
        result = result_of(job)
        if result is None:
            continue
        if result not in NEEDS_RESULTS:
            diagnostics.append(_diagnostic(
                f"needs.{aliases.get(job, job)}.result is {result!r}",
                "the verdict job must run with always() so every needed job has a result"))
        blocked_by = None
        if result == "skipped":
            for upstream in dependencies.get(job, ()):
                upstream_result = result_of(upstream)
                if upstream_result is not None and upstream_result != "success":
                    blocked_by = upstream
                    break
        rows.append(Observation(
            suite_id, job, identity.run_id, identity.run_attempt, identity.target_revision,
            result, "none", blocked_by,
        ))
    return rows, tuple(diagnostics)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path | None, document: object) -> None:
    text = json.dumps(document, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    if path is None:
        sys.stdout.write(text)
    else:
        path.write_text(text, encoding="utf-8")


def _cmd_check(args: argparse.Namespace) -> int:
    try:
        policy = load_policy(args.policy)
    except (SelfTestPolicyError, OSError, ValueError, KeyError) as error:
        print(_diagnostic(f"self-test policy is invalid ({error})",
                          "repair scripts/ci/self_test_policy.json"), file=sys.stderr)
        return 2
    scope = _read_json(args.scope_policy if args.scope_policy else Path(policy.scope_policy))
    diagnostics = scope_parity(policy, scope if isinstance(scope, dict) else {})
    for line in diagnostics:
        print(line, file=sys.stderr)
    if diagnostics:
        return 1
    print(f"self-test policy {policy.revision[:12]}: {len(policy.suites)} suites, parity with scope policy holds")
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    policy = load_policy(args.policy)
    request_document = _read_json(args.request)
    if not isinstance(request_document, dict):
        print(_diagnostic("request file is not a JSON object", "write kind, target_revision, requested_by"),
              file=sys.stderr)
        return 2
    request = Request(str(request_document.get("kind", "")),
                      request_document.get("target_revision"),  # type: ignore[arg-type]
                      str(request_document.get("requested_by", "")))
    history = {line.strip() for line in args.main_history.read_text(encoding="utf-8").splitlines()
               if line.strip()}
    last: Conclusion | None = None
    if args.last_conclusion is not None and args.last_conclusion.exists():
        document = _read_json(args.last_conclusion)
        if isinstance(document, dict):
            last = Conclusion(str(document.get("target_revision", "")), str(document.get("status", "")),
                              str(document.get("evidence_digest", "")), str(document.get("policy_revision", "")))
    resolution = resolve(
        request, tip_revision=args.tip, is_main_history=history.__contains__,
        last_conclusion=last, control_revision=args.control_revision,
        run_id=args.run_id, run_attempt=args.run_attempt, policy=policy,
    )
    _write_json(args.out, resolution.as_document())
    for line in resolution.diagnostics:
        print(line, file=sys.stderr)
    return 0 if resolution.action in ("run", "skip") else 1


def _identity_from(path: Path) -> Identity | None:
    document = _read_json(path)
    if not isinstance(document, dict):
        return None
    return Identity(
        str(document["evidence_schema"]), str(document["request_kind"]),
        str(document["control_revision"]), str(document["target_revision"]),
        int(document["run_id"]), int(document["run_attempt"]),  # type: ignore[arg-type]
        str(document["policy_revision"]),
    )


def _parse_pairs(items: Sequence[str], *, many: bool) -> dict[str, object]:
    parsed: dict[str, object] = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or not key or not value:
            raise ValueError(f"expected key=value, got {item!r}")
        parsed[key] = tuple(v for v in value.split(",") if v) if many else value
    return parsed


def _cmd_observations(args: argparse.Namespace) -> int:
    policy = load_policy(args.policy)
    identity = _identity_from(args.identity)
    if identity is None:
        print(_diagnostic("identity file is not a JSON object", "pass the identity resolve wrote"),
              file=sys.stderr)
        return 2
    needs = _read_json(args.needs)
    if not isinstance(needs, dict):
        print(_diagnostic("needs file is not a JSON object", "write toJSON(needs) to it"), file=sys.stderr)
        return 2
    try:
        aliases = _parse_pairs(args.alias, many=False)
        dependencies = _parse_pairs(args.dependency, many=True)
    except ValueError as error:
        print(_diagnostic(str(error), "pass --alias policy-job=caller-job and --dependency job=up1,up2"),
              file=sys.stderr)
        return 2
    rows, diagnostics = observations_from_needs(
        identity, policy, needs, aliases=aliases,  # type: ignore[arg-type]
        dependencies=dependencies,  # type: ignore[arg-type]
    )
    _write_json(args.out, [
        {"suite": r.suite, "job": r.job, "run_id": r.run_id, "run_attempt": r.run_attempt,
         "target_revision": r.target_revision, "conclusion": r.conclusion, "artifact": r.artifact,
         **({"blocked_by": r.blocked_by} if r.blocked_by else {})}
        for r in rows
    ])
    for line in diagnostics:
        print(line, file=sys.stderr)
    return 0


def _cmd_aggregate(args: argparse.Namespace) -> int:
    policy = load_policy(args.policy)
    identity = _identity_from(args.identity)
    if identity is None:
        print(_diagnostic("identity file is not a JSON object", "pass the identity resolve wrote"),
              file=sys.stderr)
        return 2
    rows_document = _read_json(args.observations)
    if not isinstance(rows_document, list):
        print(_diagnostic("observations file is not a JSON list", "write one object per job"),
              file=sys.stderr)
        return 2
    try:
        rows = [Observation.from_document(row) for row in rows_document]
    except (KeyError, ValueError, TypeError) as error:
        print(_diagnostic(f"observation is malformed ({error})",
                          "each row needs suite, job, run_id, run_attempt, target_revision, conclusion"),
              file=sys.stderr)
        return 2
    if args.superseded_by:
        verdict = supersede(identity, by_target=args.superseded_by)
    else:
        verdict = aggregate(identity, policy, rows)
    document = verdict.as_document()
    document["evidence_digest"] = verdict.digest
    _write_json(args.out, document)
    for line in verdict.diagnostics:
        print(line, file=sys.stderr)
    return 0 if verdict.status in (BATCH_PASSED, BATCH_SUPERSEDED) else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", type=Path, default=Path(__file__).with_name("self_test_policy.json"))
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="validate the policy and its parity with scope_policy.json")
    check.add_argument("--scope-policy", type=Path, default=None)
    check.set_defaults(func=_cmd_check)

    res = sub.add_parser("resolve", help="fix the target of one batch or record a skip")
    res.add_argument("--request", type=Path, required=True)
    res.add_argument("--tip", required=True)
    res.add_argument("--main-history", type=Path, required=True,
                     help="file with one main SHA per line (git rev-list main)")
    res.add_argument("--last-conclusion", type=Path, default=None)
    res.add_argument("--control-revision", required=True)
    res.add_argument("--run-id", type=int, required=True)
    res.add_argument("--run-attempt", type=int, required=True)
    res.add_argument("--out", type=Path, default=None)
    res.set_defaults(func=_cmd_resolve)

    obs = sub.add_parser("observations", help="derive per-job observations from a workflow's needs context")
    obs.add_argument("--identity", type=Path, required=True)
    obs.add_argument("--needs", type=Path, required=True, help="file holding toJSON(needs)")
    obs.add_argument("--alias", action="append", default=[], help="policy-job=caller-job")
    obs.add_argument("--dependency", action="append", default=[], help="job=upstream1,upstream2")
    obs.add_argument("--out", type=Path, default=None)
    obs.set_defaults(func=_cmd_observations)

    agg = sub.add_parser("aggregate", help="judge one finished batch")
    agg.add_argument("--identity", type=Path, required=True)
    agg.add_argument("--observations", type=Path, required=True)
    agg.add_argument("--superseded-by", default=None)
    agg.add_argument("--out", type=Path, default=None)
    agg.set_defaults(func=_cmd_aggregate)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
