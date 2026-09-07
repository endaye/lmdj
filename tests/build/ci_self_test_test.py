#!/usr/bin/env python3
"""Contract tests for the exact-revision self-test evidence protocol.

The protocol is pure: these tests pass every external fact in (the tip, the
main-history predicate, run identity, timestamps) and assert on documents and
digests. Nothing here fakes GitHub, git or a clock, so the test-double
guidance in `.agents/pitfalls/fake-tool-stub-strictness.md` has nothing to
double; the one external tool the CLI test touches is the script itself.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/build"))
from workflow_inventory import jobs_in  # noqa: E402

POLICY_PATH = ROOT / "scripts/ci/self_test_policy.json"
SCOPE_POLICY_PATH = ROOT / "scripts/ci/scope_policy.json"
SCRIPT_PATH = ROOT / "scripts/ci/self_test.py"

TIP = "a" * 40
OLDER = "b" * 40
FOREIGN = "c" * 40
CONTROL = "d" * 40


def load_module():
    spec = importlib.util.spec_from_file_location("self_test", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load self_test")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


st = load_module()
POLICY_DOCUMENT = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
SCOPE_POLICY = json.loads(SCOPE_POLICY_PATH.read_text(encoding="utf-8"))
POLICY = st.parse_policy(POLICY_DOCUMENT)
MAIN_HISTORY = frozenset({TIP, OLDER})


def identity(kind="schedule", target=TIP, run_id=7, attempt=1, policy=POLICY):
    return st.Identity(st.EVIDENCE_SCHEMA, kind, CONTROL, target, run_id, attempt, policy.revision)


def complete_observations(ident, *, conclusion="success", artifact="uploaded"):
    """One success row per required job, with the Mac primary branch taken."""
    rows = []
    for suite in POLICY.suites:
        for job in suite.jobs:
            rows.append(st.Observation(
                suite.id, job, ident.run_id, ident.run_attempt, ident.target_revision,
                conclusion, artifact, started_at="2026-09-07T16:00:00Z",
                completed_at="2026-09-07T16:10:00Z",
            ))
    return rows


def replace(rows, suite_id, job_id, **changes):
    out = []
    for row in rows:
        if (row.suite, row.job) == (suite_id, job_id):
            fields = {k: getattr(row, k) for k in row.__dataclass_fields__}
            fields.update(changes)
            row = st.Observation(**fields)
        out.append(row)
    return out


def drop(rows, suite, job):
    return [row for row in rows if (row.suite, row.job) != (suite, job)]


def assert_diagnostics_actionable(test, diagnostics):
    for line in diagnostics:
        test.assertRegex(line, r"^why: .+; remedy: .+$",
                         msg=f"why: a diagnostic without a remedy is a colour, not an instruction; got {line!r}")


class PolicyParityTest(unittest.TestCase):
    """The complete-suite list is derived from, and checked against, the sources it mirrors."""

    def test_the_committed_policy_parses(self) -> None:
        self.assertEqual(POLICY.schema, st.POLICY_SCHEMA)
        self.assertEqual(POLICY.evidence_schema, st.EVIDENCE_SCHEMA)
        self.assertEqual(len(POLICY.revision), 64)
        self.assertTrue(all(suite.required for suite in POLICY.suites),
                        "why: a complete run has no optional suite; remedy: mark every suite required")

    def test_every_scope_lane_is_a_suite_with_the_same_jobs(self) -> None:
        self.assertEqual(st.scope_parity(POLICY, SCOPE_POLICY), (),
                         "why: the self-test would call itself complete while missing a lane the "
                         "PR path runs; remedy: follow the diagnostics")
        lanes = {suite.scope_lane for suite in POLICY.suites if suite.scope_lane}
        self.assertEqual(lanes, set(SCOPE_POLICY["lanes"]))

    def test_parity_fails_with_a_remedy_when_scope_policy_gains_a_lane(self) -> None:
        scope = copy.deepcopy(SCOPE_POLICY)
        scope["lanes"].append("new_lane")
        scope["lane_jobs"]["new_lane"] = ["new-job"]
        diagnostics = st.scope_parity(POLICY, scope)
        self.assertEqual(len(diagnostics), 1)
        self.assertIn("scope lane new_lane has no self-test suite", diagnostics[0])
        self.assertIn("remedy: add a scope_lane suite for new_lane with jobs ['new-job']", diagnostics[0])

    def test_parity_fails_when_scope_policy_loses_a_lane_or_changes_its_jobs(self) -> None:
        scope = copy.deepcopy(SCOPE_POLICY)
        scope["lanes"].remove("package")
        scope["lane_jobs"]["creator"] = ["creator-web", "creator-web-visual"]
        diagnostics = st.scope_parity(POLICY, scope)
        self.assertEqual(len(diagnostics), 2)
        joined = "\n".join(diagnostics)
        self.assertIn("suite package mirrors scope lane package, which scope_policy.json no longer declares", joined)
        self.assertIn("suite creator lists jobs ['creator-web'] but scope lane creator runs ['creator-web', 'creator-web-visual']", joined)
        assert_diagnostics_actionable(self, diagnostics)

    def test_nightly_suites_name_jobs_core_nightly_actually_runs(self) -> None:
        nightly_jobs = {job.job_id for job in jobs_in(ROOT / ".github/workflows/core-nightly.yml")}
        nightly_suites = [suite for suite in POLICY.suites if suite.nightly_job]
        self.assertEqual({suite.nightly_job for suite in nightly_suites}, {"core-tsan", "core-stress"},
                         "why: the two stress workloads are what makes this list complete beyond the "
                         "scope lanes; remedy: keep both nightly suites")
        for suite in nightly_suites:
            with self.subTest(suite=suite.id):
                self.assertEqual(suite.origin["workflow"], ".github/workflows/core-nightly.yml")
                self.assertIn(suite.nightly_job, nightly_jobs,
                              f"why: suite {suite.id} names a Nightly job that no longer exists; "
                              "remedy: rename the suite's job or restore the Nightly job")
                self.assertEqual(suite.jobs, (suite.nightly_job,))

    def test_alternatives_are_not_required_jobs_of_any_suite(self) -> None:
        owner = POLICY.job_owner
        for suite in POLICY.suites:
            for job, alts in suite.alternatives.items():
                self.assertIn(job, suite.jobs)
                for alt in alts:
                    self.assertNotIn(alt, owner)
        self.assertEqual(POLICY.suite("core_macos").alternatives, {"macos-primary": ("macos-fallback",)})

    def test_policy_rejects_duplicate_suite_ids_jobs_and_optional_suites(self) -> None:
        cases = {
            "duplicate id": lambda d: d["suites"].append(dict(d["suites"][0])),
            "job in two suites": lambda d: d["suites"][1]["jobs"].append(d["suites"][0]["jobs"][0]),
            "optional suite": lambda d: d["suites"][0].update(required=False),
            "unknown origin": lambda d: d["suites"][0].update(origin={"kind": "manual"}),
            "alternative that is a required job": lambda d: d["suites"][0].update(
                alternatives={d["suites"][0]["jobs"][0]: [d["suites"][1]["jobs"][0]]}),
            "wrong schema": lambda d: d.update(schema="lmdj.ci-self-test-policy.v0"),
        }
        for label, mutate in cases.items():
            with self.subTest(case=label):
                document = copy.deepcopy(POLICY_DOCUMENT)
                mutate(document)
                with self.assertRaises(st.SelfTestPolicyError):
                    st.parse_policy(document)

    def test_policy_revision_changes_with_the_document(self) -> None:
        document = copy.deepcopy(POLICY_DOCUMENT)
        document["suites"][0]["note"] = "changed"
        self.assertNotEqual(st.parse_policy(document).revision, POLICY.revision)


class ResolveTest(unittest.TestCase):
    def resolve(self, request, **overrides):
        kwargs = dict(tip_revision=TIP, is_main_history=MAIN_HISTORY.__contains__,
                      last_conclusion=None, control_revision=CONTROL, run_id=7,
                      run_attempt=1, policy=POLICY)
        kwargs.update(overrides)
        return st.resolve(request, **kwargs)

    def test_a_schedule_request_fixes_the_tip_as_its_target(self) -> None:
        resolution = self.resolve(st.Request("schedule", None, "schedule"))
        self.assertEqual(resolution.action, "run")
        self.assertEqual(resolution.identity.target_revision, TIP)
        self.assertEqual(resolution.identity.policy_revision, POLICY.revision)
        self.assertEqual(resolution.identity.as_document()["run_attempt"], 1)

    def test_explicit_requests_may_choose_an_older_main_revision(self) -> None:
        for kind in ("node", "candidate"):
            with self.subTest(kind=kind):
                resolution = self.resolve(st.Request(kind, OLDER, "owner"))
                self.assertEqual(resolution.action, "run")
                self.assertEqual(resolution.identity.target_revision, OLDER)

    def test_explicit_requests_without_a_target_are_rejected(self) -> None:
        resolution = self.resolve(st.Request("candidate", None, "owner"))
        self.assertEqual(resolution.action, "reject")
        self.assertIsNone(resolution.identity)
        self.assertIn("candidate request names no target", resolution.diagnostics[0])
        assert_diagnostics_actionable(self, resolution.diagnostics)

    def test_wrong_sha_shapes_and_foreign_revisions_are_rejected(self) -> None:
        cases = {
            "short": st.Request("node", "abc123", "owner"),
            "upper-case": st.Request("node", "A" * 40, "owner"),
            "not on main": st.Request("node", FOREIGN, "owner"),
        }
        for label, request in cases.items():
            with self.subTest(case=label):
                resolution = self.resolve(request)
                self.assertEqual(resolution.action, "reject")
                assert_diagnostics_actionable(self, resolution.diagnostics)
        foreign = self.resolve(st.Request("node", FOREIGN, "owner"))
        self.assertIn("is not in main's history", foreign.diagnostics[0])

    def test_bad_control_identity_is_rejected_before_any_target_logic(self) -> None:
        for label, overrides in {
            "control revision": {"control_revision": "main"},
            "tip": {"tip_revision": "HEAD"},
            "run id": {"run_id": 0},
            "unknown kind": {},
        }.items():
            with self.subTest(case=label):
                request = st.Request("nightly" if label == "unknown kind" else "schedule", None, "schedule")
                resolution = self.resolve(request, **overrides)
                self.assertEqual(resolution.action, "reject")

    def test_schedule_skips_when_main_has_not_moved_since_a_complete_conclusion(self) -> None:
        for status in ("passed", "failed"):
            with self.subTest(status=status):
                last = st.Conclusion(TIP, status, "e" * 64, POLICY.revision)
                resolution = self.resolve(st.Request("schedule", None, "schedule"), last_conclusion=last)
                self.assertEqual(resolution.action, "skip")
                self.assertEqual(resolution.identity.target_revision, TIP,
                                 "why: a skip is an observation about a target; remedy: keep the identity")
                self.assertIn("main has not moved", resolution.diagnostics[0])
                self.assertIn(f"complete {status} conclusion", resolution.diagnostics[0])

    def test_schedule_runs_again_when_the_conclusion_was_not_complete_or_policy_changed(self) -> None:
        for label, last in {
            "invalid": st.Conclusion(TIP, "invalid", "e" * 64, POLICY.revision),
            "superseded": st.Conclusion(TIP, "superseded", "e" * 64, POLICY.revision),
            "other target": st.Conclusion(OLDER, "passed", "e" * 64, POLICY.revision),
            "other policy": st.Conclusion(TIP, "passed", "e" * 64, "f" * 64),
        }.items():
            with self.subTest(case=label):
                resolution = self.resolve(st.Request("schedule", None, "schedule"), last_conclusion=last)
                self.assertEqual(resolution.action, "run")

    def test_explicit_requests_never_skip(self) -> None:
        last = st.Conclusion(TIP, "passed", "e" * 64, POLICY.revision)
        for kind in ("node", "candidate"):
            with self.subTest(kind=kind):
                resolution = self.resolve(st.Request(kind, TIP, "owner"), last_conclusion=last)
                self.assertEqual(resolution.action, "run",
                                 "why: an operator asking for evidence gets a fresh batch, not a "
                                 "deduplicated pointer; remedy: exempt explicit kinds from the skip")


class AggregateTest(unittest.TestCase):
    def test_a_complete_successful_batch_passes_with_a_stable_digest(self) -> None:
        ident = identity()
        rows = complete_observations(ident)
        verdict = st.aggregate(ident, POLICY, rows)
        self.assertEqual(verdict.status, "passed")
        self.assertEqual(verdict.diagnostics, ())
        self.assertEqual({r.id for r in verdict.suites}, {s.id for s in POLICY.suites})
        self.assertTrue(all(r.status == "passed" for r in verdict.suites))
        document = verdict.as_document()
        self.assertEqual(document["identity"]["target_revision"], TIP)
        self.assertEqual(document["evidence_schema"], st.EVIDENCE_SCHEMA)
        # Fixed output: same rows in another order give the same digest.
        again = st.aggregate(ident, POLICY, list(reversed(rows)))
        self.assertEqual(again.digest, verdict.digest)
        self.assertEqual(len(verdict.digest), 64)
        conclusion = verdict.conclusion()
        self.assertEqual((conclusion.target_revision, conclusion.status, conclusion.evidence_digest),
                         (TIP, "passed", verdict.digest))

    def test_a_missing_suite_fails_the_batch_and_names_the_job(self) -> None:
        ident = identity()
        rows = drop(complete_observations(ident), "core_release_stress", "core-stress")
        verdict = st.aggregate(ident, POLICY, rows)
        self.assertEqual(verdict.status, "failed")
        stress = next(r for r in verdict.suites if r.id == "core_release_stress")
        self.assertEqual(stress.status, "missing")
        self.assertEqual(stress.jobs, {"core-stress": "missing"})
        self.assertIn("has no observation for job core-stress", stress.diagnostics[0])
        self.assertIn("core_release_stress=missing", verdict.diagnostics[0])
        assert_diagnostics_actionable(self, verdict.diagnostics + stress.diagnostics)

    def test_a_duplicate_identity_makes_the_batch_invalid(self) -> None:
        ident = identity()
        rows = complete_observations(ident)
        rows.append(rows[0])
        verdict = st.aggregate(ident, POLICY, rows)
        self.assertEqual(verdict.status, "invalid")
        self.assertEqual(verdict.suites, ())
        self.assertIn("was observed twice in run 7 attempt 1", verdict.diagnostics[0])

    def test_an_unknown_job_makes_the_batch_invalid(self) -> None:
        ident = identity()
        rows = complete_observations(ident)
        rows.append(st.Observation("core_ubuntu", "core-benchmark", 7, 1, TIP, "success", "uploaded"))
        verdict = st.aggregate(ident, POLICY, rows)
        self.assertEqual(verdict.status, "invalid")
        self.assertIn("job core-benchmark (reported under suite core_ubuntu) is not in the self-test policy",
                      verdict.diagnostics[0])
        self.assertIn("an unknown job cannot count toward a complete run", verdict.diagnostics[0])

    def test_a_job_reported_under_the_wrong_suite_is_invalid(self) -> None:
        ident = identity()
        rows = replace(complete_observations(ident), "package", "package", suite="core_ubuntu")
        verdict = st.aggregate(ident, POLICY, rows)
        self.assertEqual(verdict.status, "invalid")
        self.assertIn("job package was reported under suite core_ubuntu but belongs to package",
                      "\n".join(verdict.diagnostics))

    def test_a_row_for_another_revision_is_invalid_not_ignored(self) -> None:
        ident = identity()
        rows = replace(complete_observations(ident), "docs_static", "docs-static", target_revision=OLDER)
        verdict = st.aggregate(ident, POLICY, rows)
        self.assertEqual(verdict.status, "invalid")
        self.assertIn(f"reports target {OLDER[:12]}, batch target is {TIP[:12]}", verdict.diagnostics[0])

    def test_mixed_run_attempts_are_invalid(self) -> None:
        ident = identity()
        rows = replace(complete_observations(ident), "creator", "creator-web", run_attempt=2)
        verdict = st.aggregate(ident, POLICY, rows)
        self.assertEqual(verdict.status, "invalid")
        self.assertIn("comes from run 7 attempt 2, batch is run 7 attempt 1", verdict.diagnostics[0])
        self.assertIn("a rerun is a new batch", verdict.diagnostics[0])

    def test_a_success_whose_artifact_failed_to_upload_is_an_infrastructure_failure(self) -> None:
        ident = identity()
        rows = replace(complete_observations(ident), "core_coverage", "core-coverage", artifact="failed")
        verdict = st.aggregate(ident, POLICY, rows)
        self.assertEqual(verdict.status, "failed")
        coverage = next(r for r in verdict.suites if r.id == "core_coverage")
        self.assertEqual(coverage.status, "infrastructure_failure")
        self.assertIn("evidence artifact failed to upload", coverage.diagnostics[0])

    def test_an_empty_batch_is_invalid(self) -> None:
        ident = identity()
        verdict = st.aggregate(ident, POLICY, [])
        self.assertEqual(verdict.status, "invalid")
        self.assertIn("batch produced no observations", verdict.diagnostics[0])

    def test_the_mac_fallback_branch_is_a_legitimate_skip(self) -> None:
        ident = identity()
        rows = replace(complete_observations(ident), "core_macos", "macos-primary", conclusion="skipped")
        rows.append(st.Observation("core_macos", "macos-fallback", 7, 1, TIP, "success", "uploaded"))
        verdict = st.aggregate(ident, POLICY, rows)
        self.assertEqual(verdict.status, "passed")
        macos = next(r for r in verdict.suites if r.id == "core_macos")
        self.assertEqual(macos.jobs["macos-primary"], "skipped (alternative macos-fallback succeeded)")

    def test_the_mac_fallback_reported_under_another_suite_is_invalid(self) -> None:
        ident = identity()
        rows = complete_observations(ident)
        rows.append(st.Observation("core_ubuntu", "macos-fallback", 7, 1, TIP, "success", "uploaded"))
        verdict = st.aggregate(ident, POLICY, rows)
        self.assertEqual(verdict.status, "invalid")
        self.assertIn("alternative job macos-fallback was reported under suite core_ubuntu but core_macos declares it",
                      verdict.diagnostics[0])

    def test_a_required_job_skipped_without_its_alternative_does_not_pass(self) -> None:
        ident = identity()
        rows = replace(complete_observations(ident), "core_macos", "macos-primary", conclusion="skipped")
        verdict = st.aggregate(ident, POLICY, rows)
        self.assertEqual(verdict.status, "failed")
        macos = next(r for r in verdict.suites if r.id == "core_macos")
        self.assertEqual(macos.status, "infrastructure_failure")
        self.assertIn("was skipped with no successful alternative", macos.diagnostics[0])
        # A suite with no alternatives at all: a skip is never a pass.
        rows = replace(complete_observations(ident), "package", "package", conclusion="skipped")
        self.assertEqual(st.aggregate(ident, POLICY, rows).status, "failed")

    def test_classification_separates_test_infrastructure_and_blocked(self) -> None:
        ident = identity()
        rows = complete_observations(ident)
        rows = replace(rows, "creator", "creator-web", conclusion="failure")
        rows = replace(rows, "core_asan", "core-asan", conclusion="timed_out")
        rows = replace(rows, "core_coverage", "core-coverage", conclusion="skipped", blocked_by="core-ubuntu")
        rows = replace(rows, "core_ubuntu", "core-ubuntu", conclusion="failure")
        verdict = st.aggregate(ident, POLICY, rows)
        self.assertEqual(verdict.status, "failed")
        by_id = {r.id: r for r in verdict.suites}
        self.assertEqual(by_id["creator"].status, "test_failure")
        self.assertEqual(by_id["core_asan"].status, "infrastructure_failure")
        self.assertEqual(by_id["core_coverage"].status, "blocked")
        self.assertIn("did not run because core-ubuntu failed", by_id["core_coverage"].diagnostics[0])
        self.assertEqual(by_id["core_ubuntu"].status, "test_failure")
        self.assertEqual(by_id["package"].status, "passed")
        self.assertIn("creator=test_failure", verdict.diagnostics[0])
        self.assertIn("core_coverage=blocked", verdict.diagnostics[0])
        for result in verdict.suites:
            assert_diagnostics_actionable(self, result.diagnostics)

    def test_a_policy_revision_mismatch_is_invalid(self) -> None:
        document = copy.deepcopy(POLICY_DOCUMENT)
        document["suites"][0]["note"] = "changed"
        other = st.parse_policy(document)
        ident = identity()
        verdict = st.aggregate(ident, other, complete_observations(ident))
        self.assertEqual(verdict.status, "invalid")
        self.assertIn("was resolved under policy", verdict.diagnostics[0])

    def test_supersession_is_expected_for_schedule_and_refused_for_explicit_requests(self) -> None:
        superseded = st.supersede(identity("schedule"), by_target=OLDER)
        self.assertEqual(superseded.status, "superseded")
        self.assertEqual(superseded.superseded_by, OLDER)
        self.assertIn("expected supersession, not a failure", superseded.diagnostics[0])
        self.assertNotIn(superseded.status, st.COMPLETE_BATCH_STATUSES,
                         "why: a superseded batch proved nothing, so the next schedule request must "
                         "run; remedy: keep superseded out of the deduplicable statuses")
        for kind in ("node", "candidate"):
            with self.subTest(kind=kind):
                refused = st.supersede(identity(kind), by_target=OLDER)
                self.assertEqual(refused.status, "invalid")
                self.assertIn(f"a {kind} request", refused.diagnostics[0])
        self.assertEqual(st.supersede(identity("schedule"), by_target=TIP).status, "invalid")

    def test_observation_documents_round_trip_and_reject_unknown_keys(self) -> None:
        row = st.Observation.from_document({
            "suite": "package", "job": "package", "run_id": "7", "run_attempt": 1,
            "target_revision": TIP, "conclusion": "success", "artifact": "uploaded",
        })
        self.assertEqual((row.run_id, row.blocked_by, row.started_at), (7, None, None))
        with self.assertRaises(ValueError):
            st.Observation.from_document({"suite": "package", "job": "package", "run_id": 7,
                                          "run_attempt": 1, "target_revision": TIP,
                                          "conclusion": "success", "head_sha": TIP})


class ObservationsFromNeedsTest(unittest.TestCase):
    """The verdict job derives observations from `toJSON(needs)`; nothing is invented."""

    def needs(self, **results):
        return {job: {"result": result} for job, result in results.items()}

    def test_every_needed_policy_job_becomes_one_observation(self) -> None:
        ident = identity()
        needs = self.needs(**{job: "success" for suite in POLICY.suites for job in suite.jobs
                              if job not in ("core-tsan", "core-stress")},
                           **{"nightly-tsan": "success", "nightly-stress": "success"})
        rows, diagnostics = st.observations_from_needs(
            ident, POLICY, needs, aliases={"core-tsan": "nightly-tsan", "core-stress": "nightly-stress"})
        self.assertEqual(diagnostics, ())
        self.assertEqual({(r.suite, r.job) for r in rows},
                         {(s.id, j) for s in POLICY.suites for j in s.jobs})
        self.assertTrue(all(r.conclusion == "success" and r.artifact == "none" for r in rows))
        self.assertTrue(all((r.run_id, r.run_attempt, r.target_revision) == (7, 1, TIP) for r in rows))
        self.assertEqual(st.aggregate(ident, POLICY, rows).status, "passed")

    def test_an_absent_job_yields_no_row_so_aggregate_reports_it_missing(self) -> None:
        ident = identity()
        rows, _ = st.observations_from_needs(ident, POLICY, self.needs(package="success"))
        self.assertEqual([(r.suite, r.job) for r in rows], [("package", "package")])
        verdict = st.aggregate(ident, POLICY, rows)
        self.assertEqual(verdict.status, "failed")
        self.assertEqual(next(r for r in verdict.suites if r.id == "core_ubuntu").status, "missing")

    def test_a_skip_behind_a_failed_upstream_is_blocked_by_that_upstream(self) -> None:
        ident = identity()
        needs = self.needs(**{"pre-heavy-gate": "success", "core-ubuntu": "failure",
                              "package": "skipped", "core-coverage": "skipped", "portal": "success"})
        rows, _ = st.observations_from_needs(
            ident, POLICY, needs,
            dependencies={"package": ["pre-heavy-gate", "portal", "core-ubuntu"],
                          "core-coverage": ["pre-heavy-gate", "portal", "core-ubuntu", "package"]})
        by_job = {r.job: r for r in rows}
        self.assertEqual(by_job["package"].blocked_by, "core-ubuntu")
        self.assertEqual(by_job["core-coverage"].blocked_by, "core-ubuntu",
                         "why: the first non-success upstream in declaration order names the cause; "
                         "remedy: keep dependency order upstream-first")
        self.assertIsNone(by_job["core-ubuntu"].blocked_by)

    def test_alternatives_are_observed_under_the_declaring_suite(self) -> None:
        ident = identity()
        rows, _ = st.observations_from_needs(
            ident, POLICY, self.needs(**{"macos-primary": "skipped", "macos-fallback": "success"}))
        by_job = {r.job: r for r in rows}
        self.assertEqual(by_job["macos-fallback"].suite, "core_macos")
        self.assertEqual(by_job["macos-primary"].conclusion, "skipped")

    def test_a_non_result_is_reported_not_repaired(self) -> None:
        ident = identity()
        rows, diagnostics = st.observations_from_needs(ident, POLICY, self.needs(package=""))
        self.assertEqual(rows[0].conclusion, "")
        self.assertIn("needs.package.result is ''", diagnostics[0])
        self.assertEqual(st.aggregate(ident, POLICY, rows).status, "invalid")


class CommandLineTest(unittest.TestCase):
    def run_cli(self, *args, cwd):
        return subprocess.run([sys.executable, str(SCRIPT_PATH), *args], cwd=cwd,
                              capture_output=True, text=True)

    def test_check_resolve_and_aggregate_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            check = self.run_cli("check", "--scope-policy", str(SCOPE_POLICY_PATH), cwd=root)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertIn("parity with scope policy holds", check.stdout)

            (root / "request.json").write_text(json.dumps(
                {"kind": "candidate", "target_revision": OLDER, "requested_by": "owner"}), encoding="utf-8")
            (root / "main.txt").write_text(f"{TIP}\n{OLDER}\n", encoding="utf-8")
            resolve = self.run_cli(
                "resolve", "--request", "request.json", "--tip", TIP, "--main-history", "main.txt",
                "--control-revision", CONTROL, "--run-id", "7", "--run-attempt", "1",
                "--out", "resolution.json", cwd=root)
            self.assertEqual(resolve.returncode, 0, resolve.stderr)
            resolution = json.loads((root / "resolution.json").read_text(encoding="utf-8"))
            self.assertEqual(resolution["action"], "run")
            self.assertEqual(resolution["identity"]["target_revision"], OLDER)
            (root / "identity.json").write_text(json.dumps(resolution["identity"]), encoding="utf-8")

            ident = identity("candidate", OLDER)
            rows = [
                {"suite": r.suite, "job": r.job, "run_id": r.run_id, "run_attempt": r.run_attempt,
                 "target_revision": r.target_revision, "conclusion": r.conclusion, "artifact": r.artifact}
                for r in complete_observations(ident)
            ]
            (root / "observations.json").write_text(json.dumps(rows), encoding="utf-8")
            aggregate = self.run_cli("aggregate", "--identity", "identity.json",
                                     "--observations", "observations.json", "--out", "verdict.json", cwd=root)
            self.assertEqual(aggregate.returncode, 0, aggregate.stderr)
            verdict = json.loads((root / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["status"], "passed")
            self.assertEqual(len(verdict["evidence_digest"]), 64)
            self.assertEqual(verdict["identity"]["policy_revision"], POLICY.revision)

            rows.pop()
            (root / "observations.json").write_text(json.dumps(rows), encoding="utf-8")
            failed = self.run_cli("aggregate", "--identity", "identity.json",
                                  "--observations", "observations.json", cwd=root)
            self.assertEqual(failed.returncode, 1)
            self.assertIn("required suites did not pass", failed.stderr)

    def test_observations_command_reads_needs_aliases_and_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ident = identity()
            (root / "identity.json").write_text(json.dumps(ident.as_document()), encoding="utf-8")
            (root / "needs.json").write_text(json.dumps(
                {"core-ubuntu": {"result": "failure"}, "package": {"result": "skipped"},
                 "nightly-stress": {"result": "success"}, "pre-heavy-gate": {"result": "success"}}),
                encoding="utf-8")
            out = self.run_cli("observations", "--identity", "identity.json", "--needs", "needs.json",
                               "--alias", "core-stress=nightly-stress",
                               "--dependency", "package=pre-heavy-gate,core-ubuntu",
                               "--out", "observations.json", cwd=root)
            self.assertEqual(out.returncode, 0, out.stderr)
            rows = {r["job"]: r for r in json.loads((root / "observations.json").read_text(encoding="utf-8"))}
            self.assertEqual(set(rows), {"core-ubuntu", "package", "core-stress"})
            self.assertEqual(rows["package"]["blocked_by"], "core-ubuntu")
            self.assertEqual(rows["core-stress"]["conclusion"], "success")
            self.assertNotIn("blocked_by", rows["core-ubuntu"])
            bad = self.run_cli("observations", "--identity", "identity.json", "--needs", "needs.json",
                               "--dependency", "package", cwd=root)
            self.assertEqual(bad.returncode, 2)

    def test_resolve_reports_a_skip_with_exit_zero_and_a_reject_with_exit_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "request.json").write_text(json.dumps(
                {"kind": "schedule", "target_revision": None, "requested_by": "schedule"}), encoding="utf-8")
            (root / "main.txt").write_text(f"{TIP}\n", encoding="utf-8")
            (root / "last.json").write_text(json.dumps(
                {"target_revision": TIP, "status": "passed", "evidence_digest": "e" * 64,
                 "policy_revision": POLICY.revision}), encoding="utf-8")
            common = ["--tip", TIP, "--main-history", "main.txt", "--control-revision", CONTROL,
                      "--run-id", "8", "--run-attempt", "1"]
            skip = self.run_cli("resolve", "--request", "request.json", "--last-conclusion", "last.json",
                                *common, cwd=root)
            self.assertEqual(skip.returncode, 0, skip.stderr)
            self.assertEqual(json.loads(skip.stdout)["action"], "skip")

            (root / "request.json").write_text(json.dumps(
                {"kind": "node", "target_revision": FOREIGN, "requested_by": "owner"}), encoding="utf-8")
            reject = self.run_cli("resolve", "--request", "request.json", *common, cwd=root)
            self.assertEqual(reject.returncode, 1)
            self.assertIn("is not in main's history", reject.stderr)


if __name__ == "__main__":
    unittest.main()
