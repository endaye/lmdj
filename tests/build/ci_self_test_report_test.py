#!/usr/bin/env python3
"""Contract tests for the self-test failure reporter.

The GitHub API is a strict fake: every method the reporter invokes explicitly
mirrors the real endpoint's argument shape and refuses what the real endpoint
refuses (unknown run, non-integer ids, an issue state that is not open/closed,
a label that is not a string). Nothing wall-clock is stubbed: the retry sleep
is an injected recorder, so a test that wants back-off sees the delays it was
handed and a test that does not never waits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest import mock
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts/ci/self_test_report.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))


def load_module():
    spec = importlib.util.spec_from_file_location("self_test_report", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load self_test_report")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rep = load_module()

REPO = "endaye/lmdj"
TARGET = "a" * 40
OTHER = "b" * 40
CONTROL = "d" * 40
FIXTURE_JOBS = {"creator": "creator-web", "core_coverage": "core-coverage", "package": "package", "portal": "portal"}
REPORTER_AUTHOR = {"login": "github-actions[bot]", "type": "Bot"}


def run_document(run_id=100, *, attempt=1, event="schedule", path=".github/workflows/ci.yml",
                 name="Core CI / self-test " + TARGET, status="completed", conclusion="failure", repository=REPO, head=CONTROL):
    return {
        "id": run_id, "run_attempt": attempt, "event": event, "path": path, "name": name,
        "display_title": name,
        "status": status, "conclusion": conclusion, "head_sha": head,
        "html_url": f"https://github.com/{REPO}/actions/runs/{run_id}",
        "repository": {"full_name": repository},
        "workflow_id": 42, "head_branch": "main",
    }


def verdict_document(*, status="failed", run_id=100, attempt=1, target=TARGET, suites=None,
                     diagnostics=(), superseded_by=None, kind="schedule"):
    if suites is None:
        suites = [
            {"id": "creator", "status": "test_failure", "jobs": {"creator-web": "failure"},
             "diagnostics": ["why: creator/creator-web failed; remedy: read the job's failure output"]},
            {"id": "core_coverage", "status": "blocked", "jobs": {"core-coverage": "skipped"},
             "diagnostics": ["why: core_coverage/core-coverage did not run because core-ubuntu failed; remedy: fix core-ubuntu"]},
            {"id": "package", "status": "passed", "jobs": {"package": "success"}, "diagnostics": []},
        ]
    if status in ("passed", "failed"):
        present = {suite["id"] for suite in suites}
        suites = list(suites) + [
            {"id": name, "status": "passed", "jobs": {FIXTURE_JOBS[name]: "success"}, "diagnostics": []}
            for name in ("creator", "core_coverage", "package", "portal") if name not in present]
    if status in ("failed", "superseded") and not diagnostics:
        diagnostics = ("why: batch did not pass; remedy: inspect suite diagnostics",)
    suites = [dict(suite, diagnostics=suite["diagnostics"] or
                   (["why: suite did not pass; remedy: inspect job output"] if suite["status"] != "passed" else []))
              for suite in suites]
    document = {
        "evidence_schema": "lmdj.ci-self-test.v1",
        "identity": {"evidence_schema": "lmdj.ci-self-test.v1", "request_kind": kind,
                     "control_revision": CONTROL, "target_revision": target, "run_id": run_id,
                     "run_attempt": attempt, "policy_revision": rep.document_digest(fixture_policy(suites))},
        "status": status, "superseded_by": superseded_by, "suites": suites,
        "diagnostics": list(diagnostics),
    }
    document["evidence_digest"] = rep.document_digest(document)
    return document


def fixture_policy(suites):
    return {"schema": "lmdj.ci-self-test-policy.v1", "evidence_schema": "lmdj.ci-self-test.v1",
            "scope_policy": "scripts/ci/scope_policy.json",
            "suites": [{"id": name, "required": True, "jobs": [job],
                        "origin": {"kind": "scope_lane", "lane": name}}
                       for name, job in FIXTURE_JOBS.items()]}


def zip_bytes(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload if isinstance(payload, (bytes, str)) else json.dumps(payload))
    return buffer.getvalue()


def verdict_zip(document):
    return zip_bytes({"verdict.json": document})


@dataclass
class FakeGitHubApi:
    """Strict stand-in for the eight endpoints the reporter calls."""

    runs: dict[int, dict] = field(default_factory=dict)
    artifacts: dict[int, list[dict]] = field(default_factory=dict)
    blobs: dict[int, bytes] = field(default_factory=dict)
    issues: list[dict] = field(default_factory=list)
    comments: dict[int, list[dict]] = field(default_factory=dict)
    run_lists: dict[tuple[str, str | None], list[dict]] = field(default_factory=dict)
    failures: dict[str, list[int]] = field(default_factory=dict)
    calls: list[tuple] = field(default_factory=list)
    next_number: int = 900
    policies: dict[str, dict] = field(default_factory=dict)
    jobs: dict[int, list[dict]] = field(default_factory=dict)
    ancestry: str = "ahead"

    def get_workflow(self):
        return {"id": 42, "path": ".github/workflows/ci.yml"}

    def get_policy(self, revision):
        return self.policies[revision]

    def compare(self, base, head):
        return {"status": self.ancestry}

    def list_jobs(self, run_id, attempt):
        return self.jobs.get(run_id, [{"name": "Self-test verdict", "conclusion": "cancelled"}])

    def _maybe_fail(self, method):
        queue = self.failures.get(method)
        if queue:
            status = queue.pop(0)
            raise rep.GitHubApiError(status, f"forced {status}")

    @staticmethod
    def _int(value, what):
        if type(value) is not int or value <= 0:
            raise TypeError(f"{what} must be a positive int, got {value!r}")
        return value

    def get_run(self, run_id):
        self.calls.append(("get_run", run_id))
        self._maybe_fail("get_run")
        self._int(run_id, "run_id")
        if run_id not in self.runs:
            raise rep.GitHubApiError(404, "Not Found")
        return self.runs[run_id]

    def list_runs(self, workflow_file, *, event, created, per_page, status="completed"):
        self.calls.append(("list_runs", workflow_file, event, created, per_page, status))
        self._maybe_fail("list_runs")
        if not workflow_file.endswith(".yml") or "/" in workflow_file:
            raise TypeError("workflow_file is a file name like ci.yml")
        if event not in ("schedule", "workflow_dispatch", "push", "pull_request"):
            raise TypeError(f"event {event!r}")
        self._int(per_page, "per_page")
        return [run for run in self.run_lists.get((event, created), [])
                if status is None or run["status"] == status][:per_page]

    def list_artifacts(self, run_id):
        self.calls.append(("list_artifacts", run_id))
        self._maybe_fail("list_artifacts")
        self._int(run_id, "run_id")
        if run_id not in self.runs:
            raise rep.GitHubApiError(404, "Not Found")
        return list(self.artifacts.get(run_id, []))

    def download_artifact(self, artifact_id):
        self.calls.append(("download_artifact", artifact_id))
        self._maybe_fail("download_artifact")
        self._int(artifact_id, "artifact_id")
        if artifact_id not in self.blobs:
            raise rep.GitHubApiError(410, "Gone")
        return self.blobs[artifact_id]

    def list_issues(self, *, label, state):
        self.calls.append(("list_issues", label, state))
        self._maybe_fail("list_issues")
        if not isinstance(label, str) or not label:
            raise TypeError("label must be a non-empty str")
        if state not in ("open", "closed", "all"):
            raise TypeError(f"state {state!r}")
        return [dict(issue) for issue in self.issues
                if label in issue["labels"] and (state == "all" or issue["state"] == state)]

    def list_comments(self, number):
        self.calls.append(("list_comments", number))
        self._maybe_fail("list_comments")
        self._int(number, "number")
        if not any(issue["number"] == number for issue in self.issues):
            raise rep.GitHubApiError(404, "Not Found")
        return list(self.comments.get(number, []))

    def create_issue(self, *, title, body, labels, assignees):
        self.calls.append(("create_issue", title, tuple(labels), tuple(assignees)))
        self._maybe_fail("create_issue")
        if not isinstance(title, str) or not title or not isinstance(body, str):
            raise TypeError("title and body must be str")
        if not all(isinstance(label, str) for label in labels) or not all(isinstance(a, str) for a in assignees):
            raise TypeError("labels and assignees are lists of str")
        self.next_number += 1
        issue = {"number": self.next_number, "title": title, "body": body,
                 "labels": list(labels), "assignees": list(assignees), "state": "open",
                 "user": dict(REPORTER_AUTHOR)}
        self.issues.append(issue)
        return dict(issue)

    def create_comment(self, number, body):
        self.calls.append(("create_comment", number, body[:40]))
        self._maybe_fail("create_comment")
        self._int(number, "number")
        if not isinstance(body, str) or not body:
            raise TypeError("body must be a non-empty str")
        if not any(issue["number"] == number for issue in self.issues):
            raise rep.GitHubApiError(404, "Not Found")
        comment = {"id": len(self.comments.get(number, [])) + 1, "body": body,
                   "user": dict(REPORTER_AUTHOR)}
        self.comments.setdefault(number, []).append(comment)
        return dict(comment)

    def set_issue_state(self, number, state):
        self.calls.append(("set_issue_state", number, state))
        self._maybe_fail("set_issue_state")
        self._int(number, "number")
        if state not in ("open", "closed"):
            raise TypeError(f"state {state!r}")
        for issue in self.issues:
            if issue["number"] == number:
                issue["state"] = state
                return dict(issue)
        raise rep.GitHubApiError(404, "Not Found")

    # helpers ---------------------------------------------------------------
    def with_batch(self, run_id=100, *, document=None, run=None, artifact_id=None):
        document = verdict_document(run_id=run_id) if document is None else document
        self.runs[run_id] = run or run_document(run_id)
        artifact_id = artifact_id or run_id * 10
        self.artifacts[run_id] = [{"id": artifact_id, "name": f"self-test-verdict-{document['identity']['target_revision']}-{run_id}-{document['identity']['run_attempt']}",
                                   "expired": False}]
        self.blobs[artifact_id] = verdict_zip(document)
        self.policies[CONTROL] = fixture_policy(document["suites"])
        return self

    def issue_bodies(self):
        return {issue["number"]: issue for issue in self.issues}


class Sleep:
    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)


def report(api, run_id=100, **kwargs):
    sleep = kwargs.pop("sleep", Sleep())
    return rep.report_run(api, run_id, repository=REPO, assignee="maintainer", sleep=sleep, **kwargs)


class DetectionTest(unittest.TestCase):
    def test_a_failed_batch_without_an_artifact_is_an_incomplete_batch(self) -> None:
        api = FakeGitHubApi(runs={100: run_document(100)}, artifacts={100: [{"id": 1, "name": "ci-scope-" + TARGET}]})
        result = report(api)
        self.assertEqual(result.verdict_status, "incomplete")
        self.assertEqual([o.action for o in result.outcomes], ["created"])

    def test_pull_request_and_foreign_runs_are_refused_before_artifacts_are_read(self) -> None:
        cases = {
            "pull_request": run_document(100, event="pull_request"),
            "other workflow": run_document(100, path=".github/workflows/core-nightly.yml", name="Core Nightly"),
            "other repository": run_document(100, repository="someone/else"),
            "in progress": run_document(100, status="in_progress", conclusion=None),
        }
        for label, run in cases.items():
            with self.subTest(case=label):
                api = FakeGitHubApi(runs={100: run})
                result = report(api)
                self.assertIsNotNone(result.skipped)
                self.assertNotIn(("list_artifacts", 100), api.calls)

    def test_a_cancelled_batch_with_a_verdict_is_still_reported_from_its_verdict(self) -> None:
        document = verdict_document(status="invalid", suites=[],
                                    diagnostics=["why: batch produced no observations; remedy: rerun"])
        api = FakeGitHubApi().with_batch(document=document, run=run_document(100, conclusion="cancelled"))
        result = report(api)
        self.assertEqual(result.verdict_status, "invalid")
        self.assertEqual([o.action for o in result.outcomes], ["created"])
        issue = api.issues[0]
        self.assertIn("self-test-batch-invalid", issue["body"])
        self.assertIn("area:ci-release", issue["labels"])

    def test_zip_entries_with_unsafe_paths_are_refused(self) -> None:
        for name in ("../verdict.json", "/verdict.json", "a/../verdict.json"):
            with self.subTest(name=name):
                with self.assertRaises(rep.ReportingError) as caught:
                    rep.read_verdict_zip(zip_bytes({name: verdict_document()}))
                self.assertIn("unsafe path", str(caught.exception))
        with self.assertRaises(rep.ReportingError):
            rep.read_verdict_zip(zip_bytes({"other.json": {}}))
        with self.assertRaises(rep.ReportingError):
            rep.read_verdict_zip(b"not a zip")

    def test_a_verdict_for_another_run_or_target_is_refused(self) -> None:
        run = rep.parse_run(run_document(100))
        with self.assertRaises(rep.ReportingError) as caught:
            rep.parse_verdict(verdict_document(run_id=99), run=run, target=TARGET, policy=fixture_policy([]))
        self.assertIn("verdict identity", str(caught.exception))
        with self.assertRaises(rep.ReportingError):
            rep.parse_verdict(verdict_document(target=OTHER), run=run, target=TARGET, policy=fixture_policy([]))
        with self.assertRaises(rep.ReportingError):
            document = verdict_document()
            document["evidence_schema"] = "lmdj.ci-self-test.v2"
            rep.parse_verdict(document, run=run, target=TARGET, policy=fixture_policy([]))

    def test_expired_artifacts_do_not_count(self) -> None:
        self.assertIsNone(rep.find_verdict_artifact([
            {"id": 1, "name": f"self-test-verdict-{TARGET}-100-1", "expired": True}],
            run=rep.parse_run(run_document())))
        self.assertEqual(rep.find_verdict_artifact([
            {"id": 2, "name": "ci-scope-" + TARGET}, {"id": 3, "name": f"self-test-verdict-{TARGET}-100-1"}],
            run=rep.parse_run(run_document())),
            (3, TARGET))


class DedupeTest(unittest.TestCase):
    def test_first_observation_creates_one_issue_per_failed_suite(self) -> None:
        api = FakeGitHubApi().with_batch()
        result = report(api)
        self.assertEqual(result.verdict_status, "failed")
        self.assertEqual(sorted(o.action for o in result.outcomes), ["created", "created"])
        titles = sorted(issue["title"] for issue in api.issues)
        self.assertEqual(titles, ["self-test: core_coverage blocked", "self-test: creator test failure"])
        creator = next(issue for issue in api.issues if "creator" in issue["title"])
        self.assertIn("<!-- lmdj-self-test: key=self-test-creator-test-failure -->", creator["body"])
        self.assertIn(f"obs=100/1/creator/", creator["body"])
        self.assertIn(TARGET, creator["body"])
        self.assertIn("Not run in this batch: core_coverage", creator["body"])
        self.assertIn("Severity: high", creator["body"])
        self.assertEqual(creator["assignees"], ["maintainer"])
        self.assertIn("never blocks ordinary Pull Request merges", creator["body"])
        # the passed suite files nothing
        self.assertFalse(any("package" in issue["title"] for issue in api.issues))

    def test_the_same_observation_resent_adds_nothing(self) -> None:
        api = FakeGitHubApi().with_batch()
        report(api)
        writes_before = [call for call in api.calls if call[0] in ("create_issue", "create_comment", "set_issue_state")]
        result = report(api)
        self.assertEqual(sorted(o.action for o in result.outcomes), ["duplicate", "duplicate"])
        writes_after = [call for call in api.calls if call[0] in ("create_issue", "create_comment", "set_issue_state")]
        self.assertEqual(writes_before, writes_after)
        self.assertEqual(sum(len(c) for c in api.comments.values()), 0)

    def test_the_same_suite_class_on_a_later_day_updates_the_open_bucket(self) -> None:
        api = FakeGitHubApi().with_batch(100)
        report(api, 100)
        second = verdict_document(run_id=200, target=OTHER,
                                  suites=[{"id": "creator", "status": "test_failure",
                                           "jobs": {"creator-web": "failure"}, "diagnostics": ["why: again; remedy: fix"]}])
        api.with_batch(200, document=second, run=run_document(200))
        result = report(api, 200)
        self.assertEqual([o.action for o in result.outcomes], ["commented"])
        self.assertEqual(len([i for i in api.issues if "creator" in i["title"]]), 1)
        number = result.outcomes[0].issue_number
        self.assertEqual(len(api.comments[number]), 1)
        self.assertIn("obs=200/1/creator/", api.comments[number][0]["body"])
        self.assertIn(OTHER, api.comments[number][0]["body"])
        self.assertIn("potentially different defects", api.issues[0]["body"])
        self.assertIn("Real test IDs and log-error fingerprints are not yet extracted", api.issues[0]["body"])

    def test_a_rerun_attempt_is_a_new_observation_on_the_same_issue(self) -> None:
        api = FakeGitHubApi().with_batch(100)
        report(api, 100)
        api.with_batch(100, document=verdict_document(run_id=100, attempt=2),
                       run=run_document(100, attempt=2), artifact_id=1001)
        result = report(api, 100)
        self.assertEqual(sorted(o.action for o in result.outcomes), ["commented", "commented"])

    def test_a_closed_issue_that_recurs_is_reopened_with_the_new_observation(self) -> None:
        api = FakeGitHubApi().with_batch(100)
        report(api, 100)
        creator = next(issue for issue in api.issues if "creator" in issue["title"])
        api.set_issue_state(creator["number"], "closed")
        api.calls.clear()
        api.with_batch(200, document=verdict_document(run_id=200, suites=[
            {"id": "creator", "status": "test_failure", "jobs": {"creator-web": "failure"}, "diagnostics": []}]),
            run=run_document(200))
        result = report(api, 200)
        self.assertEqual([o.action for o in result.outcomes], ["reopened"])
        self.assertEqual(creator["state"], "open")
        self.assertIn(("set_issue_state", creator["number"], "open"), api.calls)
        self.assertEqual(len(api.comments[creator["number"]]), 1)

    def test_a_green_batch_closes_nothing(self) -> None:
        api = FakeGitHubApi().with_batch(100)
        report(api, 100)
        api.with_batch(200, document=verdict_document(run_id=200, status="passed", suites=[
            {"id": "creator", "status": "passed", "jobs": {"creator-web": "success"}, "diagnostics": []}]),
            run=run_document(200, conclusion="success"))
        result = report(api, 200)
        self.assertEqual(result.verdict_status, "passed")
        self.assertEqual(result.outcomes, [])
        self.assertTrue(all(issue["state"] == "open" for issue in api.issues))
        self.assertNotIn("set_issue_state", {call[0] for call in api.calls})

    def test_a_different_failure_class_for_the_same_suite_is_a_different_issue(self) -> None:
        api = FakeGitHubApi().with_batch(100)
        report(api, 100)
        api.with_batch(200, document=verdict_document(run_id=200, suites=[
            {"id": "creator", "status": "infrastructure_failure", "jobs": {"creator-web": "timed_out"}, "diagnostics": []}]),
            run=run_document(200))
        result = report(api, 200)
        self.assertEqual([o.action for o in result.outcomes], ["created"])
        self.assertEqual(len([i for i in api.issues if "creator" in i["title"]]), 2)

    def test_two_different_batches_completing_back_to_back_file_independently(self) -> None:
        api = FakeGitHubApi().with_batch(100)
        api.with_batch(200, document=verdict_document(run_id=200, target=OTHER, suites=[
            {"id": "portal", "status": "infrastructure_failure", "jobs": {"portal": "cancelled"}, "diagnostics": []}]),
            run=run_document(200))
        first = report(api, 100)
        second = report(api, 200)
        self.assertEqual(sorted(o.action for o in first.outcomes), ["created", "created"])
        self.assertEqual([o.action for o in second.outcomes], ["created"])
        self.assertEqual(len(api.issues), 3)
        # And a reconcile pass afterwards writes nothing new.
        api.run_lists[("schedule", None)] = [run_document(100), run_document(200)]
        api.run_lists[("workflow_dispatch", None)] = []
        results = rep.reconcile_recent(api, repository=REPO, assignee="maintainer", sleep=Sleep())
        self.assertEqual(sorted(o.action for r in results for o in r.outcomes), ["duplicate"] * 3)

    def test_superseded_batches_file_nothing(self) -> None:
        api = FakeGitHubApi().with_batch(document=verdict_document(status="superseded", suites=[],
                                                                  superseded_by=OTHER))
        result = report(api)
        self.assertEqual(result.verdict_status, "superseded")
        self.assertEqual(result.outcomes, [])
        self.assertEqual(api.issues, [])

    def test_malicious_diagnostic_text_is_escaped_and_truncated(self) -> None:
        evil = "<script>alert(1)</script> ``` \x1b[31m ```" + "x" * 5000
        api = FakeGitHubApi().with_batch(document=verdict_document(suites=[
            {"id": "creator", "status": "test_failure", "jobs": {"creator-web": "failure"}, "diagnostics": [evil]}]))
        report(api)
        body = api.issues[0]["body"]
        self.assertNotIn("<script>", body)
        self.assertIn("&lt;script&gt;", body)
        self.assertNotIn("\x1b", body)
        self.assertNotIn(" ``` ", body.split("```text", 1)[1].split("```", 1)[0])
        self.assertIn("more characters truncated", body)
        self.assertLess(len(body), 4000)


class ReportingErrorTest(unittest.TestCase):
    def test_transient_429_and_5xx_are_retried_with_the_injected_sleep(self) -> None:
        api = FakeGitHubApi().with_batch()
        api.failures["create_issue"] = [429, 503]
        sleep = Sleep()
        result = report(api, sleep=sleep)
        self.assertEqual(sorted(o.action for o in result.outcomes), ["created", "created"])
        self.assertEqual(sleep.delays, list(rep.RETRY_DELAYS))

    def test_a_persistent_5xx_is_a_reporting_error_that_leaves_the_verdict_alone(self) -> None:
        api = FakeGitHubApi().with_batch()
        api.failures["create_issue"] = [500, 500, 500]
        with self.assertRaises(rep.GitHubApiError) as caught:
            report(api)
        self.assertEqual(caught.exception.status, 500)
        self.assertEqual(api.issues, [])
        self.assertEqual(api.blobs[1000], verdict_zip(verdict_document()))

    def test_403_is_not_retried(self) -> None:
        api = FakeGitHubApi().with_batch()
        api.failures["list_issues"] = [403]
        sleep = Sleep()
        with self.assertRaises(rep.GitHubApiError) as caught:
            report(api, sleep=sleep)
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(sleep.delays, [])

    def test_the_cli_exit_code_and_summary_name_the_reporting_error(self) -> None:
        summary = rep.render_summary([], None, error="GitHub API 500: forced 500")
        self.assertIn("**reporting-error**", summary)
        summary = rep.render_summary([rep.RunReport(5, skipped="not a self-test")], None, error=None)
        self.assertIn("skipped — not a self-test", summary)


class MissingCheckTest(unittest.TestCase):
    def test_no_scheduled_run_for_the_date_files_the_missing_issue_once(self) -> None:
        api = FakeGitHubApi()
        api.run_lists[("schedule", "2026-09-08")] = []
        outcome = rep.check_missing(api, date="2026-09-08", assignee="maintainer", sleep=Sleep())
        self.assertEqual(outcome.action, "created")
        body = api.issues[0]["body"]
        self.assertIn("self-test-missing", body)
        self.assertIn("cannot observe a day on which Actions did not run this check", body)
        again = rep.check_missing(api, date="2026-09-08", assignee="maintainer", sleep=Sleep())
        self.assertEqual(again.action, "duplicate")
        later = rep.check_missing(api, date="2026-09-09", assignee="maintainer", sleep=Sleep())
        self.assertEqual(later.action, "commented")
        self.assertEqual(len(api.issues), 1)

    def test_a_scheduled_run_for_the_date_files_nothing(self) -> None:
        api = FakeGitHubApi()
        api.run_lists[("schedule", "2026-09-08")] = [run_document(100)]
        self.assertIsNone(rep.check_missing(api, date="2026-09-08", assignee="maintainer", sleep=Sleep()))
        self.assertEqual(api.issues, [])
        with self.assertRaises(rep.ReportingError):
            rep.check_missing(api, date="yesterday", assignee="maintainer", sleep=Sleep())


class SeverityAndKeyTest(unittest.TestCase):
    def test_keys_never_contain_the_sha_or_a_date(self) -> None:
        run = rep.parse_run(run_document(100))
        for report_ in rep.plan_reports(rep.parse_verdict(verdict_document(), run=run, target=TARGET,
                                                         policy=fixture_policy([])), run):
            self.assertNotIn(TARGET, report_.key)
            self.assertRegex(report_.key, r"^self-test-[a-z0-9-]+$")
            self.assertIn(f"{TARGET}", report_.summary)

    def test_severity_follows_class_then_suite(self) -> None:
        self.assertEqual(rep.severity_of("core_asan", "test_failure"), "high")
        self.assertEqual(rep.severity_of("docs_static", "test_failure"), "medium")
        self.assertEqual(rep.severity_of("core_asan", "infrastructure_failure"), "medium")
        self.assertEqual(rep.severity_of("core_asan", "blocked"), "low")
        self.assertEqual(rep.severity_of("core_asan", "missing"), "low")


class BoundaryRegressionTest(unittest.TestCase):
    def test_display_name_does_not_override_stable_workflow_authority(self):
        for name in ("Core CI / self-test " + TARGET, "Core CI / 757/merge", "Core Nightly", "", "arbitrary display text"):
            with self.subTest(name=name):
                api = FakeGitHubApi().with_batch(run=run_document(name=name))
                result = report(api)
                self.assertIsNone(result.skipped)
                self.assertEqual(result.verdict_status, "failed")
                self.assertEqual(len(result.outcomes), 2)

    def test_display_name_cannot_rescue_wrong_workflow_id_or_path(self):
        for change in ({"workflow_id": 99}, {"path": ".github/workflows/core-nightly.yml"}):
            with self.subTest(change=change):
                api = FakeGitHubApi().with_batch(run=run_document(name="Core CI / self-test " + TARGET))
                api.runs[100].update(change)
                self.assertIsNotNone(report(api).skipped)
                self.assertEqual(api.issues, [])
                self.assertNotIn(("list_artifacts", 100), api.calls)

    def test_user_owned_issue_marker_cannot_redirect_reports_or_reopen_it(self):
        for author in (None, {}, {"login": "maintainer", "type": "User"},
                       {"login": "github-actions[bot]", "type": "User"},
                       {"login": "other[bot]", "type": "Bot"}):
            with self.subTest(author=author):
                api = FakeGitHubApi().with_batch()
                report(api)
                forged = next(issue for issue in api.issues if "creator" in issue["title"])
                forged["user"] = author
                forged["state"] = "closed"
                api.with_batch(200, document=verdict_document(run_id=200), run=run_document(200))
                result = report(api, 200)
                creator = next(outcome for outcome in result.outcomes if "creator" in outcome.key)
                self.assertEqual(creator.action, "created")
                self.assertNotEqual(creator.issue_number, forged["number"])
                self.assertEqual(forged["state"], "closed")
                self.assertNotIn(forged["number"], api.comments)

    def test_user_comment_with_exact_observation_marker_cannot_suppress_report(self):
        for author in (None, {}, {"login": "maintainer", "type": "User"},
                       {"login": "github-actions[bot]", "type": "User"},
                       {"login": "other[bot]", "type": "Bot"}):
            with self.subTest(author=author):
                api = FakeGitHubApi().with_batch()
                report(api)
                bucket = next(issue for issue in api.issues if "creator" in issue["title"])
                document = verdict_document(run_id=200)
                run = rep.parse_run(run_document(200))
                verdict = rep.parse_verdict(document, run=run, target=TARGET, policy=fixture_policy([]))
                observation = next(item for item in rep.plan_reports(verdict, run) if "creator" in item.key)
                api.comments[bucket["number"]] = [{"id": 1, "body": observation.comment_body(), "user": author}]
                api.with_batch(200, document=document, run=run_document(200))
                result = report(api, 200)
                self.assertEqual(next(item.action for item in result.outcomes if "creator" in item.key), "commented")
                comments = api.comments[bucket["number"]]
                self.assertEqual(len(comments), 2)
                self.assertEqual(comments[-1]["user"], REPORTER_AUTHOR)
                self.assertIn(observation.observation_marker, comments[-1]["body"])
                report(api, 200)
                self.assertEqual(len(comments), 2)  # trusted bot observation is now idempotent

    def test_untrusted_issue_body_is_not_an_observation_even_for_direct_lookup(self):
        api = FakeGitHubApi().with_batch()
        report(api)
        issue = next(item for item in api.issues if "creator" in item["title"])
        run = rep.parse_run(run_document())
        verdict = rep.parse_verdict(verdict_document(), run=run, target=TARGET, policy=fixture_policy([]))
        observation = next(item for item in rep.plan_reports(verdict, run) if "creator" in item.key)
        issue["user"] = {"login": "maintainer", "type": "User"}
        self.assertFalse(rep._observation_recorded(api, issue, observation, sleep=Sleep()))

    def test_real_t2_aggregate_document_is_consumed_without_translation(self):
        protocol = rep.self_test
        policy_document = json.loads((Path(protocol.__file__).parent / "self_test_policy.json").read_text())
        policy = protocol.parse_policy(policy_document)
        identity = protocol.Identity(protocol.EVIDENCE_SCHEMA, "schedule", CONTROL, TARGET, 100, 1, policy.revision)
        observations = [protocol.Observation(suite.id, job, 100, 1, TARGET,
                                             "failure" if suite.id == "creator" else "success")
                        for suite in policy.suites for job in suite.jobs]
        verdict = protocol.aggregate(identity, policy, observations)
        document = verdict.as_document()
        document["evidence_digest"] = verdict.digest
        api = FakeGitHubApi().with_batch(document=document)
        api.policies[CONTROL] = policy_document
        result = report(api)
        self.assertEqual(result.verdict_status, "failed")
        self.assertEqual([o.key for o in result.outcomes], ["self-test-creator-test-failure"])

    def test_old_attempt_artifact_is_never_current_evidence(self):
        api = FakeGitHubApi().with_batch(run=run_document(attempt=2))
        result = report(api)
        self.assertEqual(result.verdict_status, "incomplete")
        self.assertNotIn("obs=100/1/creator", api.issues[0]["body"])

    def test_wrong_control_attempt_and_empty_green_are_rejected(self):
        run = rep.parse_run(run_document())
        for mutation in ("control", "attempt", "empty", "digest", "duplicate"):
            document = verdict_document()
            if mutation == "control":
                document["identity"]["control_revision"] = OTHER
            elif mutation == "attempt":
                document["identity"]["run_attempt"] = 2
            elif mutation == "empty":
                document["status"], document["suites"] = "passed", []
            elif mutation == "duplicate":
                document["suites"].append(document["suites"][0])
            document["evidence_digest"] = rep.document_digest({k: v for k, v in document.items() if k != "evidence_digest"})
            if mutation == "digest":
                document["evidence_digest"] = "0" * 64
            with self.subTest(mutation=mutation), self.assertRaises(rep.ReportingError):
                rep.parse_verdict(document, run=run, target=TARGET, policy=fixture_policy([]))

    def test_forged_workflow_or_non_main_control_cannot_write(self):
        for change in ({"workflow_id": 99}, {"head_branch": "feat/untrusted"}, {"repository": {}}):
            api = FakeGitHubApi().with_batch()
            api.runs[100].update(change)
            self.assertIsNotNone(report(api).skipped)
            self.assertEqual(api.issues, [])

    def test_target_outside_main_history_is_rejected(self):
        api = FakeGitHubApi().with_batch()
        api.compare = lambda base, head: {"status": "diverged" if base == TARGET else "ahead"}
        with self.assertRaises(rep.ReportingError):
            report(api)
        self.assertEqual(api.issues, [])

    def test_target_newer_than_control_on_main_is_accepted(self):
        api = FakeGitHubApi().with_batch()
        calls = []
        def compare(base, head):
            calls.append((base, head))
            return {"status": "behind" if (base, head) == (TARGET, CONTROL) else "ahead"}
        api.compare = compare
        result = report(api)
        self.assertEqual(result.verdict_status, "failed")
        self.assertEqual(len(result.outcomes), 2)
        self.assertIn((CONTROL, "main"), calls)
        self.assertIn((TARGET, "main"), calls)
        self.assertNotIn((TARGET, CONTROL), calls)

    def test_invalid_and_infrastructure_guidance_uses_new_dispatch_same_target(self):
        for document in (
            verdict_document(status="invalid", suites=[], diagnostics=["why: bad batch; remedy: repair producer"]),
            verdict_document(suites=[{"id": "creator", "status": "infrastructure_failure",
                                     "jobs": {"creator-web": "failure"}, "diagnostics": ["why: host unavailable"]}]),
        ):
            api = FakeGitHubApi().with_batch(document=document)
            report(api)
            body = api.issues[0]["body"]
            self.assertIn("new dispatch for the same target", body)
            self.assertIn("not a run rerun", body)
            self.assertNotIn("new attempt", body)

    def test_old_compatibility_sweep_does_not_become_missing_self_test(self):
        api = FakeGitHubApi(runs={100: run_document(conclusion="failure")})
        api.jobs[100] = [{"name": "Self-test verdict", "conclusion": "skipped"}]
        self.assertIn("compatibility", report(api).skipped)
        self.assertEqual(api.issues, [])

    def test_resolver_startup_failure_without_request_is_visible_not_a_pass(self):
        api = FakeGitHubApi(runs={100: run_document(event="workflow_dispatch", conclusion="failure")})
        api.jobs[100] = [{"name": "Change Scope", "conclusion": "failure"},
                         {"name": "Self-test verdict", "conclusion": "skipped"}]
        result = report(api)
        self.assertIn("startup failure", result.error)
        self.assertIsNone(result.skipped)
        self.assertEqual(api.issues, [])

    def test_cancelled_request_without_verdict_is_reported(self):
        api = FakeGitHubApi(runs={100: run_document(event="workflow_dispatch", conclusion="cancelled")})
        request = {"evidence_schema": "lmdj.ci-self-test-request.v1", "request_kind": "node",
                   "control_revision": CONTROL, "target_revision": TARGET, "target_verified": False,
                   "run_id": 100, "run_attempt": 1}
        api.artifacts[100] = [{"id": 7, "name": "self-test-request-100-1"}]
        api.blobs[7] = zip_bytes({"request.json": request})
        result = report(api)
        self.assertEqual(result.verdict_status, "incomplete")
        self.assertIn(TARGET, api.issues[0]["body"])
        self.assertIn("Target: unproven", api.issues[0]["body"])

    def test_verified_skip_record_is_not_a_failure(self):
        api = FakeGitHubApi(runs={100: run_document(conclusion="success")})
        identity = verdict_document()["identity"]
        api.artifacts[100] = [{"id": 8, "name": f"self-test-skip-{TARGET}-100-1"}]
        api.blobs[8] = zip_bytes({"skip.json": {"action": "skip", "identity": identity}})
        self.assertIn("verified", report(api).skipped)
        self.assertEqual(api.issues, [])

    def test_in_progress_run_prevents_missing_alert_and_client_omits_status(self):
        api = FakeGitHubApi()
        api.run_lists[("schedule", "2026-09-08")] = [run_document(status="in_progress", conclusion=None)]
        self.assertIsNone(rep.check_missing(api, date="2026-09-08", assignee="maintainer", sleep=Sleep()))
        real = rep.UrllibGitHubApi(REPO, "dummy")
        with mock.patch.object(real, "_request", return_value={"workflow_runs": []}) as request:
            real.list_runs("ci.yml", event="schedule", created="2026-09-08", per_page=5, status=None)
        self.assertNotIn("status=", request.call_args.args[1])

    def test_create_response_loss_rereads_marker_before_retrying(self):
        api = FakeGitHubApi().with_batch()
        original = api.create_issue
        lost = [True]
        def create(**kwargs):
            issue = original(**kwargs)
            if lost:
                lost.pop()
                raise rep.GitHubApiError(0, "response lost after write")
            return issue
        api.create_issue = create
        report(api)
        self.assertEqual(len(api.issues), 2)  # two suite/class buckets, not three writes

    def test_comment_response_loss_rereads_marker_before_retrying(self):
        api = FakeGitHubApi().with_batch()
        report(api)
        api.with_batch(200, document=verdict_document(run_id=200), run=run_document(200))
        original = api.create_comment
        lost = [True]
        def create(number, body):
            comment = original(number, body)
            if lost:
                lost.pop()
                raise rep.GitHubApiError(0, "response lost after write")
            return comment
        api.create_comment = create
        report(api, 200)
        self.assertEqual(sum(len(comments) for comments in api.comments.values()), 2)

    def test_artifact_download_redirect_has_no_authorization(self):
        client = rep.UrllibGitHubApi(REPO, "dummy-token")
        api_opener, download_opener = mock.Mock(), mock.Mock()
        api_opener.open.side_effect = urllib.error.HTTPError(
            "https://api.github.com/artifact", 302, "Found", {"Location": "https://blob.example/signed"}, None)
        download_opener.open.return_value = io.BytesIO(b"zip data")
        with mock.patch("urllib.request.build_opener", side_effect=[api_opener, download_opener]) as build:
            self.assertEqual(client.download_artifact(7), b"zip data")
        self.assertIsInstance(build.call_args_list[0].args[0], rep.NoRedirect)
        api_request = api_opener.open.call_args.args[0]
        download_request = download_opener.open.call_args.args[0]
        self.assertEqual(api_request.get_header("Authorization"), "Bearer dummy-token")
        self.assertIsNone(download_request.get_header("Authorization"))

    def test_redirect_rejects_http_and_strips_even_accidental_credentials(self):
        request = urllib.request.Request("https://blob.example/a", headers={"Authorization": "Bearer dummy"})
        handler = rep.SafeDownloadRedirect()
        redirected = handler.redirect_request(request, None, 302, "Found", {}, "https://other.example/b")
        self.assertIsNone(redirected.get_header("Authorization"))
        with self.assertRaises(rep.ReportingError):
            handler.redirect_request(request, None, 302, "Found", {}, "http://other.example/b")

    def test_bad_batch_does_not_block_reconciliation_of_other_batches(self):
        api = FakeGitHubApi().with_batch(100).with_batch(200)
        api.blobs[1000] = b"broken zip"
        api.run_lists[("schedule", None)] = [run_document(100), run_document(200)]
        results = rep.reconcile_recent(api, repository=REPO, assignee="maintainer", sleep=Sleep())
        self.assertTrue(results[0].error)
        self.assertEqual([o.action for o in results[1].outcomes], ["created", "created"])

    def test_reconciliation_window_overflow_is_visible(self):
        api = FakeGitHubApi().with_batch()
        api.run_lists[("schedule", None)] = [run_document()]
        results = rep.reconcile_recent(api, repository=REPO, assignee="maintainer", sleep=Sleep(), limit=1)
        self.assertIn("window reached", results[-1].error)

    def test_duplicate_zip_entries_and_credentials_are_rejected_or_redacted(self):
        with self.assertRaises(rep.ReportingError):
            rep.read_verdict_zip(zip_bytes({"verdict.json": {}, "other.json": {}}))
        text = rep.sanitize("Authorization: Bearer secret-value github_pat_abcdef ghp_123456")
        self.assertNotIn("secret-value", text)
        self.assertNotIn("github_pat_abcdef", text)


class ProducerMigrationTest(unittest.TestCase):
    # Verified PR #757 squash; scan from committer time before merged_at settles.
    PRODUCER = "22247897e9163a3f34e15f564bec133419d1f177"

    def legacy_api(self, *, run_id, control, conclusion, jobs, attempt=1):
        run = run_document(run_id, head=control, conclusion=conclusion, attempt=attempt,
                           event="workflow_dispatch", name="Core CI / main")
        run["created_at"] = "2026-08-15T18:48:00Z"
        run["updated_at"] = "2026-09-08T12:00:00Z"  # a later rerun is still old control code
        api = FakeGitHubApi(runs={run_id: run}, jobs={run_id: jobs})
        api.compare = lambda base, head: {
            "status": "behind" if (base, head) == (self.PRODUCER, control) else "ahead"}
        return api

    def test_real_legacy_scope_failure_and_cancelled_run_are_not_new_startup_failures(self):
        cases = (
            (31902121850, "0714ba48dbfd5d87b2275375def4a15a6140025f", "failure",
             [{"name": "Change Scope", "conclusion": "failure"}]),
            (33246108574, "c6549c437c918445359ae4051edaa15dc379ba66", "cancelled", []),
        )
        for run_id, control, conclusion, jobs in cases:
            with self.subTest(run_id=run_id):
                api = self.legacy_api(run_id=run_id, control=control, conclusion=conclusion, jobs=jobs)
                result = report(api, run_id)
                self.assertIn("predates self-test producer", result.skipped or "")
                self.assertIsNone(result.error)
                self.assertNotIn(("list_artifacts", run_id), api.calls)
                self.assertEqual(api.issues, [])

    def test_recent_rerun_of_old_control_still_predates_producer(self):
        api = self.legacy_api(run_id=31902121850, control="0714ba48dbfd5d87b2275375def4a15a6140025f",
                              conclusion="failure", jobs=[], attempt=3)
        result = report(api, 31902121850)
        self.assertIn("predates self-test producer", result.skipped or "")
        self.assertIsNone(result.error)

    def test_exact_producer_boundary_is_accepted_and_later_startup_failure_stays_visible(self):
        for control in (self.PRODUCER, CONTROL):
            with self.subTest(control=control):
                api = FakeGitHubApi(runs={100: run_document(head=control, conclusion="failure")})
                api.jobs[100] = [{"name": "Change Scope", "conclusion": "failure"}]
                api.compare = lambda base, head: {"status": "identical" if base == head else "ahead"}
                result = report(api)
                self.assertIsNone(result.skipped)
                self.assertIn("startup failure", result.error or "")

    def test_diverged_or_unknown_control_is_not_silently_classified_as_legacy(self):
        for status in ("diverged", "unknown", None):
            with self.subTest(status=status):
                api = FakeGitHubApi().with_batch()
                api.compare = lambda base, head: {"status": status if base == self.PRODUCER else "ahead"}
                result = report(api)
                self.assertIsNone(result.skipped)
                self.assertIn("producer", result.error or "")
                self.assertIn("why:", result.error or "")
                self.assertIn("remedy:", result.error or "")
                self.assertEqual(api.issues, [])

    def test_recovery_filter_uses_later_of_exact_deployment_and_retention(self):
        self.assertEqual(rep.recovery_created_filter(datetime(2026, 9, 8, tzinfo=timezone.utc)),
                         ">=2026-09-07T12:20:36Z")
        self.assertEqual(rep.recovery_created_filter(datetime(2026, 10, 10, 12, tzinfo=timezone.utc)),
                         ">=2026-09-10T12:00:00Z")

    def test_manual_no_reconcile_retries_only_requested_run_despite_unrelated_overflow(self):
        api = FakeGitHubApi().with_batch()
        api.run_lists[("schedule", None)] = [run_document(run_id=n) for n in range(1, 101)]
        with mock.patch.object(rep, "UrllibGitHubApi", return_value=api), \
                mock.patch.object(rep, "reconcile_recent", side_effect=AssertionError("must not scan unrelated history")), \
                mock.patch.object(rep, "_write_summary"):
            self.assertEqual(rep.main(["--repository", REPO, "report", "--run-id", "100", "--no-reconcile"]), 0)
        self.assertEqual(len(api.issues), 2)

    def test_automatic_reconciliation_gets_exact_deployment_time_filter(self):
        api = FakeGitHubApi().with_batch()
        with mock.patch.object(rep, "UrllibGitHubApi", return_value=api), \
                mock.patch.object(rep, "reconcile_recent", return_value=[]) as reconcile, \
                mock.patch.object(rep, "_write_summary"):
            self.assertEqual(rep.main(["--repository", REPO, "report", "--run-id", "100"]), 0)
        self.assertGreaterEqual(reconcile.call_args.kwargs["created"], ">=2026-09-07T12:20:36Z")



if __name__ == "__main__":
    unittest.main()
