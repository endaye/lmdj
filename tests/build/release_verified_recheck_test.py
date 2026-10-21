#!/usr/bin/env python3
"""A journal-verified step is rechecked through its immutable identity only.

Each case fixes one fact about `VerifiedRecheck` (#2422 item 3): a covered
step answers `verified` with the recorded evidence from a handful of cheap
reads, every far-side drift is `conflict`/`absent`, a step whose full
observation is already cheap is answered None, and the backend only consults
an enrolled recheck for a verified transition.
"""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.github_api import GitHubAsset, GitHubRelease  # noqa: E402
from tools.release.model import canonical_json, canonical_sha256  # noqa: E402
from tools.release.orchestration import JournalError  # noqa: E402
from tools.release.orchestration_backend import ReleaseBackend  # noqa: E402
from tools.release.orchestration_driver import Observation  # noqa: E402
from tools.release.verified_recheck import (  # noqa: E402
    RECHECKED_STEPS,
    VerifiedRecheck,
    read_private_document,
)

DIGEST = "a" * 64
BUILD = "2.0.122.0"
TAG = "lmdj-v" + BUILD
CUT_MERGE, WITNESS_MERGE = "c" * 40, "d" * 40
INTENT_MERGE, CHANGELOG_MERGE, RECORD_MERGE, PROMOTION_MERGE = ("1" * 40, "2" * 40,
                                                                "3" * 40, "4" * 40)
BATCH_RUN, RUNTIME_RUN, CREATOR_RUN = 39221726945, 40000000001, 40000000002
BATCH_WORKFLOW, RUNTIME_WORKFLOW, CREATOR_WORKFLOW = 352307416, 502, 503
RELEASE_ID = 418182265
REPOSITORY = "endaye/lmdj"
HEAD = "9" * 40
RUN_HEAD = "8" * 40
PLAN_ASSETS = [{"name": "lmdj-creator-web-6.0.1-product-2.0.122.0.zip", "bytes": 3092602,
                "sha256": "0b" * 32},
               {"name": "lmdj-creator-web-6.0.1-product-2.0.122.0.zip.sha256", "bytes": 111,
                "sha256": "34" * 32}]


def request(**changes):
    document = {"id": "release-" + "0" * 16, "repository": REPOSITORY,
                "actor_id": 34, "authority_ref": "issue:2422",
                "policy_digest": "e" * 64, "control_revision": "f" * 40,
                "base_revision": "f" * 40, "mode": "new", "requested_tag": None}
    document.update(changes)
    return document


def state(**changes):
    document = {"schema": "lmdj.release-request.v1", "request": request(),
                "request_digest": DIGEST, "transitions": []}
    document.update(changes)
    return document


def merge_record(number, merge_sha):
    return {"status": "verified",
            "evidence": {"sha256": "b" * 64, "reference": f"squash:{number}"},
            "merge": {"id": number * 10, "number": number, "head_sha": HEAD,
                      "merge_sha": merge_sha}}


def candidate_state():
    return {"schema": "lmdj.candidate-transition.v1",
            "scope": {"cut_spec": {"operation_id": "5" * 64, "product_build": BUILD,
                                   "request_sha256": DIGEST,
                                   "snapshot_sha256": "6" * 64}},
            "cut_merge": merge_record(2399, CUT_MERGE),
            "witness_started": True, "witness": {"receipt": {}},
            "workspace_base": "7" * 40, "workspace_started": True, "workspace": {},
            "task_started": True, "task": {}, "witness_pr_started": True,
            "witness_merge": merge_record(2400, WITNESS_MERGE)}


def pr_state(number, review_digest, **spec):
    return {"schema": "lmdj.evidence-pr-state.v1",
            "spec": dict({"operation_id": "8" * 64, "head_sha": HEAD}, **spec),
            "create_intent": True, "number": number, "merge_intent": True,
            "merge_sha": None,
            "review_evidence": {"sha256": review_digest,
                                "reference": f"review:kind:pr-{number}"}}


def run_document(run_id, path, workflow_id, **changes):
    document = {"id": run_id, "path": path, "workflow_id": workflow_id, "run_attempt": 1,
                "status": "completed", "conclusion": "success", "head_branch": "main",
                "event": "workflow_dispatch", "head_sha": RUN_HEAD}
    document.update(changes)
    return document


def dispatch_record(workflow, workflow_id, **inputs):
    return {"schema": "lmdj.durable-dispatch.v1", "baseline": [1], "post_intent": True,
            "spec": {"workflow": workflow, "workflow_id": workflow_id,
                     "inputs": dict({"tag": TAG, "request_id": "8" * 64}, **inputs)}}


def release(plan, **changes):
    fields = dict(
        id=RELEASE_ID, tag_name=TAG, name=TAG,
        body=f'<!-- lmdj.release-plan-marker.v3 {{"plan_sha256": "{plan}"}} -->',
        draft=True, prerelease=True, make_latest=None,
        html_url="https://example.invalid/release",
        upload_url="https://example.invalid/upload",
        assets=tuple(GitHubAsset(id=index + 1, name=item["name"], size=item["bytes"],
                                 api_url="https://api.example.invalid/a", browser_download_url="",
                                 release_id=RELEASE_ID, label=None, content_type="application/zip",
                                 state="uploaded")
                     for index, item in enumerate(PLAN_ASSETS)),
        target_commitish="f" * 40)
    fields.update(changes)
    return GitHubRelease(**fields)


class Git:
    def __init__(self):
        self.ancestors = {CUT_MERGE, WITNESS_MERGE, INTENT_MERGE, CHANGELOG_MERGE,
                          RECORD_MERGE, PROMOTION_MERGE, RUN_HEAD}
        self.asked = []

    def is_main_ancestor(self, target):
        self.asked.append(target)
        return target in self.ancestors


class GitHub:
    """Far-side identities only: no asset, artifact or review inventory reads."""

    def __init__(self, plan):
        self.pull_requests = {
            2399: CUT_MERGE, 2400: WITNESS_MERGE, 2407: INTENT_MERGE,
            2417: CHANGELOG_MERGE, 2424: RECORD_MERGE, 2425: PROMOTION_MERGE}
        self.heads = {}
        self.runs = {
            BATCH_RUN: run_document(BATCH_RUN, ".github/workflows/self-test-report.yml",
                                    BATCH_WORKFLOW, event="workflow_run"),
            RUNTIME_RUN: run_document(RUNTIME_RUN, ".github/workflows/deploy-web-runtime-host.yml",
                                      RUNTIME_WORKFLOW),
            CREATOR_RUN: run_document(CREATOR_RUN, ".github/workflows/deploy-creator-web.yml",
                                      CREATOR_WORKFLOW)}
        self.release = release(plan)
        self.reads = []

    def get_pull_request(self, repository, number):
        self.reads.append(("pull", number))
        assert repository == REPOSITORY
        merge_sha = self.pull_requests.get(number)
        if merge_sha is None:
            return None
        return {"number": number, "state": "closed", "merged": True,
                "merge_commit_sha": merge_sha, "head_sha": self.heads.get(number, HEAD),
                "title": "t"}

    def get_release_by_tag(self, repository, tag):
        self.reads.append(("release", tag))
        assert repository == REPOSITORY
        return self.release if self.release is not None and self.release.tag_name == tag else None

    def get_batch_evidence(self, path, *, raw=False):
        self.reads.append(("batch", path))
        return self._run(path)

    def get_dispatch_evidence(self, path, *, raw=False):
        self.reads.append(("dispatch", path))
        return self._run(path)

    def _run(self, path):
        prefix = f"/repos/{REPOSITORY}/actions/runs/"
        assert path.startswith(prefix), path
        run = self.runs.get(int(path[len(prefix):]))
        if run is None:
            raise RuntimeError("404")
        return deepcopy(run)


def write_private(directory, name, document):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for level in (directory, *directory.parents):
        if level.name.startswith("ops-") or level == directory:
            os.chmod(level, 0o700)
    path = directory / name
    path.write_bytes(canonical_json(document))
    os.chmod(path, 0o600)
    return path


class VerifiedRecheckTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        self.root = base / "repo"
        self.operations = base / "ops-journal" / "operations" / request()["id"]
        self.operations.mkdir(parents=True, mode=0o700)
        os.chmod(self.operations.parent, 0o700)
        os.chmod(self.operations.parent.parent, 0o700)
        plan_document = canonical_json({"schema": "lmdj.release-plan.v1", "tag": TAG,
                                        "assets": PLAN_ASSETS})
        self.plan = hashlib.sha256(plan_document).hexdigest()
        output = self.root / "build/release" / TAG
        output.mkdir(parents=True)
        (output / "release-plan.json").write_bytes(plan_document)
        (output / "release-plan.sha256").write_text(self.plan + "\n")
        self.candidate = candidate_state()
        write_private(self.operations / "candidate-transition",
                      "candidate-transition.json", self.candidate)
        self.reviews = {"intent": "11" * 32, "changelog": "22" * 32,
                        "published_record": "33" * 32, "promotion": "44" * 32}
        self.batch_reference = {"schema": "lmdj.ci-batch-release-reference.v1",
                                "request": {"target": WITNESS_MERGE}, "run_attempt": 1}
        write_private(self.operations / "intent-sequence/pr", "pr-state.json",
                      pr_state(2407, self.reviews["intent"], batch_reference=self.batch_reference,
                               batch_run_id=BATCH_RUN, target_revision=WITNESS_MERGE))
        write_private(self.operations / "changelog-sequence/pr", "pr-state.json",
                      pr_state(2417, self.reviews["changelog"]))
        write_private(self.operations / "published-record-pr", "pr-state.json",
                      pr_state(2424, self.reviews["published_record"]))
        write_private(self.operations / "promotion-sequence/pr", "pr-state.json",
                      pr_state(2425, self.reviews["promotion"]))
        write_private(self.operations / "dispatch-publication", "dispatch.json",
                      dispatch_record("publish-release.yml", 501, release_id=str(RELEASE_ID),
                                      plan_sha256=self.plan))
        write_private(self.operations / "dispatch-runtime", "dispatch.json",
                      dispatch_record("deploy-web-runtime-host.yml", RUNTIME_WORKFLOW,
                                      prior_site_sha256="7" * 64))
        write_private(self.operations / "dispatch-creator", "dispatch.json",
                      dispatch_record("deploy-creator-web.yml", CREATOR_WORKFLOW,
                                      prior_site_sha256="7" * 64))
        self.git, self.github = Git(), GitHub(self.plan)
        self.recheck = VerifiedRecheck(root=self.root, operations=self.operations,
                                       repository=REPOSITORY, git=self.git,
                                       github=self.github, batch_workflow_id=BATCH_WORKFLOW)

    # -- the evidence each step's full observation recorded ---------------

    def evidence(self, step):
        if step == "candidate":
            return {"sha256": canonical_sha256(self.candidate),
                    "reference": "candidate:" + "5" * 64}
        if step == "verification":
            return {"sha256": canonical_sha256(self.batch_reference),
                    "reference": f"batch-result:{BATCH_RUN}:{WITNESS_MERGE}"}
        if step in ("intent", "changelog", "promotion"):
            number, merge = {"intent": (2407, INTENT_MERGE), "changelog": (2417, CHANGELOG_MERGE),
                             "promotion": (2425, PROMOTION_MERGE)}[step]
            return {"sha256": canonical_sha256({"kind": step, "merge": merge,
                                                "review": self.reviews[step]}),
                    "reference": f"{step}-pr:{number}"}
        if step == "published_record":
            return {"sha256": canonical_sha256({"kind": step, "merge": RECORD_MERGE,
                                                "review": self.reviews[step]}),
                    "reference": "merged:published_record:" + RECORD_MERGE}
        if step == "draft":
            return {"sha256": canonical_sha256({"tag": TAG, "plan_sha256": self.plan,
                                                "release_id": RELEASE_ID}),
                    "reference": f"draft:{RELEASE_ID}"}
        if step == "publication":
            return {"sha256": "9b" * 32,
                    "reference": f"https://github.com/{REPOSITORY}/releases/tag/{TAG}"}
        run = RUNTIME_RUN if step == "runtime" else CREATOR_RUN
        return {"sha256": "9c" * 32,
                "reference": f"https://github.com/{REPOSITORY}/actions/runs/{run}"}

    def operation(self, step, evidence=None, status="verified"):
        return {"step": step, "operation_id": canonical_sha256({"request": DIGEST, "step": step}),
                "status": status, "evidence": self.evidence(step) if evidence is None else evidence}

    def publish(self, **changes):
        self.github.release = release(self.plan, draft=False, **changes)

    def check(self, step, **state_changes):
        return self.recheck.recheck(state(**state_changes), self.operation(step))

    # -- coverage ---------------------------------------------------------

    def test_every_covered_step_reverifies_from_its_immutable_identity(self):
        self.publish()
        for step in RECHECKED_STEPS:
            with self.subTest(step=step):
                observed = self.check(step)
                self.assertEqual(observed.status, "verified", observed.diagnostic)
                self.assertEqual(observed.evidence, self.evidence(step))
        # Only identities were read: no asset, artifact, review or journal page.
        kinds = {kind for kind, _ in self.github.reads}
        self.assertEqual(kinds, {"pull", "release", "batch", "dispatch"})

    def test_steps_whose_observation_is_already_cheap_keep_it(self):
        for step in ("prepared", "tag", "changelog_site", "final"):
            with self.subTest(step=step):
                self.assertIsNone(self.recheck.recheck(state(), self.operation(
                    step, {"sha256": DIGEST, "reference": "x"})))
        self.assertEqual(self.github.reads, [])

    def test_only_a_verified_record_may_be_rechecked(self):
        with self.assertRaisesRegex(JournalError, "journal verified"):
            self.recheck.recheck(state(), self.operation("draft", status="intent"))
        for broken in (None, {"sha256": "x", "reference": "draft:1"}, {"sha256": DIGEST}):
            with self.subTest(broken=broken), self.assertRaisesRegex(JournalError, "no evidence"):
                self.recheck.recheck(state(), dict(self.operation("draft"), evidence=broken))

    def test_a_draft_still_verifies_once_the_release_is_published(self):
        self.assertEqual(self.check("draft").status, "verified")
        self.publish()
        self.assertEqual(self.check("draft").status, "verified")

    def test_a_tag_mode_request_rechecks_its_requested_tag(self):
        changed = dict(request(mode="tag", requested_tag=TAG))
        observed = self.recheck.recheck(state(request=changed), self.operation("draft"))
        self.assertEqual(observed.status, "verified")

    # -- drift fails closed -------------------------------------------------

    def test_a_moved_pull_request_merge_is_a_conflict(self):
        for step, number in (("candidate", 2399), ("candidate", 2400), ("intent", 2407),
                             ("changelog", 2417), ("published_record", 2424),
                             ("promotion", 2425)):
            with self.subTest(step=step, number=number):
                saved = self.github.pull_requests[number]
                self.github.pull_requests[number] = "e" * 40
                self.git.ancestors.add("e" * 40)
                observed = self.check(step)
                self.github.pull_requests[number] = saved
                self.assertEqual(observed.status, "conflict")
                self.assertIn(f"#{number}" if step == "candidate" else "differs", observed.diagnostic)

    def test_a_merge_commit_outside_canonical_history_is_a_conflict(self):
        for step, merge in (("candidate", WITNESS_MERGE), ("intent", INTENT_MERGE),
                            ("verification", WITNESS_MERGE)):
            with self.subTest(step=step):
                self.git.ancestors.discard(merge)
                observed = self.check(step)
                self.git.ancestors.add(merge)
                self.assertEqual(observed.status, "conflict")
                self.assertIn("canonical history", observed.diagnostic)

    def test_a_missing_pull_request_or_release_is_absent_not_a_pass(self):
        del self.github.pull_requests[2407]
        self.assertEqual(self.check("intent").status, "absent")
        self.github.release = None
        for step in ("draft", "publication"):
            with self.subTest(step=step):
                self.assertEqual(self.check(step).status, "absent")

    def test_a_retained_record_that_drifted_from_the_evidence_is_a_conflict(self):
        changed = dict(self.candidate, witness_started=False, witness=None,
                       workspace_base=None, workspace_started=False, workspace=None,
                       task_started=False, task=None, witness_pr_started=False,
                       witness_merge=None)
        write_private(self.operations / "candidate-transition",
                      "candidate-transition.json", changed)
        observed = self.check("candidate")
        self.assertEqual(observed.status, "conflict")
        self.assertIn("witness_merge", observed.diagnostic)
        write_private(self.operations / "candidate-transition",
                      "candidate-transition.json", dict(changed, witness_started=True,
                                                        witness={"receipt": {}},
                                                        witness_merge=merge_record(2400, WITNESS_MERGE)))
        observed = self.check("candidate")
        self.assertEqual(observed.status, "conflict")
        self.assertIn("differs from the recorded evidence", observed.diagnostic)

    def test_a_release_that_dropped_the_prepared_plan_is_a_conflict(self):
        self.github.release = release(self.plan, body="no marker")
        self.assertEqual(self.check("draft").status, "conflict")
        self.publish(body="no marker")
        self.assertEqual(self.check("publication").status, "conflict")

    def test_publication_requires_the_dispatched_release_to_be_published(self):
        observed = self.check("publication")
        self.assertEqual(observed.status, "conflict")
        self.assertIn("still a draft", observed.diagnostic)
        self.publish(id=RELEASE_ID + 1)
        observed = self.check("publication")
        self.assertEqual(observed.status, "conflict")
        self.assertIn("not the one dispatched", observed.diagnostic)

    def test_an_asset_inventory_that_drifted_from_the_plan_is_a_conflict(self):
        assets = self.github.release.assets
        cases = {"missing": assets[:1],
                 "foreign": assets + (GitHubAsset(**dict(assets[0].__dict__, id=9, name="extra.zip")),),
                 "size": (GitHubAsset(**dict(assets[0].__dict__, size=assets[0].size + 1)), assets[1]),
                 "state": (GitHubAsset(**dict(assets[0].__dict__, state="starter")), assets[1])}
        for name, drifted in cases.items():
            for step in ("draft", "publication"):
                with self.subTest(case=name, step=step):
                    self.github.release = release(self.plan, draft=step == "draft", assets=drifted)
                    observed = self.check(step)
                    self.assertEqual(observed.status, "conflict", (name, step))
                    self.assertIn(step + ":", observed.diagnostic)
        # The plan itself is the inventory: a plan without one fails closed.
        output = self.root / "build/release" / TAG
        (output / "release-plan.json").write_bytes(b'{"plan": "fixture"}\n')
        replaced = hashlib.sha256(b'{"plan": "fixture"}\n').hexdigest()
        (output / "release-plan.sha256").write_text(replaced + "\n")
        self.github.release = release(replaced)
        with self.assertRaisesRegex(JournalError, "asset inventory"):
            self.check("draft")

    def test_a_pull_request_merged_from_another_head_is_a_conflict(self):
        for step, number in (("candidate", 2399), ("candidate", 2400), ("intent", 2407),
                             ("changelog", 2417), ("published_record", 2424),
                             ("promotion", 2425)):
            with self.subTest(step=step, number=number):
                self.github.heads[number] = "a" * 40
                observed = self.check(step)
                del self.github.heads[number]
                self.assertEqual(observed.status, "conflict")
                self.assertIn("reviewed head", observed.diagnostic)

    def test_a_run_of_another_workflow_identity_or_off_main_is_a_conflict(self):
        for step, run_id in (("verification", BATCH_RUN), ("runtime", RUNTIME_RUN),
                             ("creator", CREATOR_RUN)):
            for key, value in (("workflow_id", 999), ("head_sha", "e" * 40)):
                with self.subTest(step=step, key=key):
                    saved = self.github.runs[run_id][key]
                    self.github.runs[run_id][key] = value
                    observed = self.check(step)
                    self.github.runs[run_id][key] = saved
                    self.assertEqual(observed.status, "conflict", (step, key))
        # A deployment with no retained dispatch is absent, never a pass.
        (self.operations / "dispatch-runtime/dispatch.json").unlink()
        self.assertEqual(self.check("runtime").status, "absent")

    def test_a_reviewed_intent_that_binds_another_batch_is_a_conflict(self):
        for change in ({"batch_run_id": BATCH_RUN + 1},
                       {"batch_reference": {"schema": "other"}},
                       {"target_revision": CUT_MERGE}):
            with self.subTest(change=change):
                spec = {**dict(batch_reference=self.batch_reference, batch_run_id=BATCH_RUN,
                               target_revision=WITNESS_MERGE), **change}
                write_private(self.operations / "intent-sequence/pr", "pr-state.json",
                              pr_state(2407, self.reviews["intent"], **spec))
                observed = self.check("verification")
                self.assertEqual(observed.status, "conflict")
                self.assertIn("another batch reference", observed.diagnostic)
        # Before the intent step records anything, the run and witness carry the check.
        (self.operations / "intent-sequence/pr/pr-state.json").unlink()
        self.assertEqual(self.check("verification").status, "verified")

    def test_a_rerun_failed_or_foreign_run_is_a_conflict(self):
        cases = {"run_attempt": 2, "conclusion": "failure", "status": "in_progress",
                 "head_branch": "feat/x", "path": ".github/workflows/ci.yml"}
        for step, run_id in (("verification", BATCH_RUN), ("runtime", RUNTIME_RUN),
                             ("creator", CREATOR_RUN)):
            for key, value in cases.items():
                with self.subTest(step=step, key=key):
                    saved = self.github.runs[run_id][key]
                    self.github.runs[run_id][key] = value
                    observed = self.check(step)
                    self.github.runs[run_id][key] = saved
                    self.assertEqual(observed.status, "conflict", (step, key))
        self.github.runs[RUNTIME_RUN]["event"] = "push"
        self.assertEqual(self.check("runtime").status, "conflict")

    def test_a_verification_target_that_differs_from_the_candidate_witness_is_a_conflict(self):
        foreign = {"sha256": canonical_sha256(self.batch_reference),
                   "reference": f"batch-result:{BATCH_RUN}:{CUT_MERGE}"}
        observed = self.recheck.recheck(state(), self.operation("verification", foreign))
        self.assertEqual(observed.status, "conflict")
        self.assertIn("witness merge differs", observed.diagnostic)

    def test_a_recorded_reference_of_another_shape_is_a_conflict(self):
        for step in ("verification", "runtime", "publication"):
            with self.subTest(step=step):
                observed = self.recheck.recheck(state(), self.operation(
                    step, {"sha256": "9a" * 32, "reference": "fixture:other"}))
                self.assertEqual(observed.status, "conflict")

    def test_a_missing_local_record_is_absent_and_a_corrupt_one_fails_closed(self):
        path = self.operations / "intent-sequence/pr/pr-state.json"
        path.unlink()
        self.assertEqual(self.check("intent").status, "absent")
        path.write_bytes(b'{"schema": "lmdj.evidence-pr-state.v1"}\n')
        os.chmod(path, 0o600)
        with self.assertRaisesRegex(JournalError, "canonical"):
            self.check("intent")
        path.write_bytes(canonical_json({"schema": "other"}))
        with self.assertRaisesRegex(JournalError, "expected record"):
            self.check("intent")
        os.chmod(self.operations / "candidate-transition/candidate-transition.json", 0o644)
        with self.assertRaises(JournalError):
            self.check("candidate")

    def test_read_private_document_reads_only_private_canonical_json(self):
        directory = self.operations / "fixture"
        self.assertIsNone(read_private_document(directory, "x.json"))
        write_private(directory, "x.json", {"a": 1})
        self.assertEqual(read_private_document(directory, "x.json"), {"a": 1})
        self.assertIsNone(read_private_document(directory, "missing.json"))
        (directory / "x.json").write_text(json.dumps({"a": 1}, indent=2))
        with self.assertRaisesRegex(JournalError, "canonical"):
            read_private_document(directory, "x.json")


class BackendRecheckTest(unittest.TestCase):
    class Carrier:
        def __init__(self, step):
            self.step, self.observed = step, 0

        def observe(self, state, operation):
            self.observed += 1
            return Observation("verified", {"sha256": DIGEST, "reference": "fixture"})

    class Recheck:
        def __init__(self, answer):
            self.answer, self.seen = answer, []

        def recheck(self, state, operation):
            self.seen.append(operation["step"])
            return self.answer

    def backend(self, recheck):
        git = type("Git", (), {"is_main_ancestor": lambda self, t: True})()
        github = type("GitHub", (), {"get_authenticated_actor": lambda self: 34})()
        return ReleaseBackend(git, github, carriers=(self.Carrier("draft"),), recheck=recheck)

    def test_the_recheck_requires_the_pinned_batch_workflow(self):
        git = type("Git", (), {"is_main_ancestor": lambda self, t: True})()
        with self.assertRaisesRegex(JournalError, "batch workflow"):
            VerifiedRecheck(root=".", operations=".", repository=REPOSITORY, git=git,
                            github=GitHub("a" * 64), batch_workflow_id=None)

    def test_the_backend_consults_the_enrolled_recheck_and_declines_without_one(self):
        operation = {"step": "draft", "operation_id": DIGEST, "status": "verified",
                     "evidence": {"sha256": DIGEST, "reference": "draft:1"}}
        self.assertIsNone(self.backend(None).recheck(state(), operation))
        agreed = Observation("verified", operation["evidence"])
        enrolled = self.Recheck(agreed)
        self.assertEqual(self.backend(enrolled).recheck(state(), operation), agreed)
        self.assertEqual(enrolled.seen, ["draft"])
        with self.assertRaisesRegex(JournalError, "no enrolled carrier"):
            self.backend(enrolled).recheck(state(), dict(operation, step="final"))

    def test_an_object_without_recheck_is_refused_at_enrollment(self):
        with self.assertRaisesRegex(JournalError, "not a verified-transition recheck"):
            self.backend(object())


if __name__ == "__main__":
    unittest.main()
