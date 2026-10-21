"""Cheap immutability rechecks for transitions the journal already verified.

A resume used to re-drive every verified step through its complete far-side
observation: the candidate source proof, the batch verdict bundle, every Draft
asset download, each reviewed PR's full review inventory. That cost 25–30
minutes per round, almost all of it re-proving facts that cannot change
(#2422). A verified journal record is the trusted local proof that the step's
far side was once fully verified; what a resume must still establish is that
the immutable identity the proof named is still the same object. These
rechecks read exactly that and nothing more:

- `candidate`: the retained transition state still hashes to the recorded
  evidence, and both squash merges (cut and witness) are still their Pull
  Request's merge of the reviewed head and reachable canonical history;
- `verification`: the executor run is still a completed, passed first attempt
  of the pinned batch workflow on canonical main, for the witness the
  candidate recorded, and the reviewed intent (once its record exists) still
  binds the same batch reference digest and run;
- `intent` / `changelog` / `promotion` / `published_record`: the Pull Request
  is still merged from the reviewed head at the merge commit the gate digest
  binds, and that commit is reachable canonical history;
- `draft`: the Release under the tag still carries the prepared plan digest,
  the recorded numeric identity (draft or published) and exactly the plan's
  asset inventory, every asset uploaded;
- `publication`: the Release the dispatch named is published, not a draft,
  with the dispatched plan and the plan's asset inventory;
- `runtime` / `creator`: the recorded deployment run is still a completed,
  passed first attempt of the retained dispatch's pinned workflow, dispatched
  for this release on canonical main.

Every check fails closed: a changed merge commit, a moved Release, a re-run or
deleted run, a missing local record are `conflict`/`absent`, never a pass.
A step whose full observation is already a handful of local reads
(`prepared`, `tag`, `changelog_site`, `final`) is answered None and keeps it.
Nothing here runs a proof, drives a write or replaces the first verification:
a transition reaches `verified` only through its carrier's full observation.
"""

from copy import deepcopy
import json
import os
from pathlib import Path
import re

from .model import canonical_json, canonical_sha256
from .orchestration import JournalError, RequestJournal, STEPS
from .orchestration_driver import Observation


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_BUILD = re.compile(r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}\.0\Z")
_BATCH_REFERENCE = re.compile(r"batch-result:([1-9][0-9]*):([0-9a-f]{40})\Z")
_RUN_URL = re.compile(r"https://github\.com/endaye/lmdj/actions/runs/([1-9][0-9]*)\Z")
_MAX_BYTES = 1024 * 1024
_BATCH_WORKFLOW = ".github/workflows/self-test-report.yml"
_DEPLOY_WORKFLOWS = {"runtime": ".github/workflows/deploy-web-runtime-host.yml",
                     "creator": ".github/workflows/deploy-creator-web.yml"}
# step -> (PR journal relative to the operations root, gate kind, reference)
_PR_STEPS = {
    "intent": ("intent-sequence/pr", "intent", "intent-pr:{number}"),
    "changelog": ("changelog-sequence/pr", "changelog", "changelog-pr:{number}"),
    "promotion": ("promotion-sequence/pr", "promotion", "promotion-pr:{number}"),
    "published_record": ("published-record-pr", "published_record",
                         "merged:published_record:{merge}"),
}
RECHECKED_STEPS = ("candidate", "verification", "intent", "changelog", "draft",
                   "publication", "published_record", "runtime", "creator",
                   "promotion")


def _fail(reason):
    raise JournalError(f"why: verified recheck {reason}; remedy: reconcile the "
                       "retained request records with the far side; never "
                       "re-verify by hand or edit a journal")


def _conflict(reason):
    return Observation("conflict", diagnostic=f"JournalError: why: verified recheck {reason}; "
                       "remedy: reconcile the far-side drift against the retained record")


def read_private_document(root, name):
    """One canonical JSON document from a private journal directory, or None.

    The same read discipline the step journals apply: a private directory,
    a private regular file opened without following links, bounded size and
    byte-exact canonical JSON. A missing file is None; anything else that is
    not the document fails closed.
    """
    root = Path(root).absolute()
    if not root.is_dir():
        return None
    with RequestJournal(root, writable=False) as journal:
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=journal.directory)
        except FileNotFoundError:
            return None
        try:
            journal._private(fd)
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(_MAX_BYTES + 1)
        finally:
            os.close(fd)
    if len(raw) > _MAX_BYTES:
        _fail(f"{name} exceeds its read bound")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        _fail(f"{name} is not a JSON document")
    if type(value) is not dict or canonical_json(value) != raw:
        _fail(f"{name} is not canonical JSON")
    return value


class VerifiedRecheck:
    """The enrolled verified-transition recheck for one request's records."""

    def __init__(self, *, root, operations, repository, git, github,
                 batch_workflow_id):
        """git: `is_main_ancestor(sha)`. github: the release GitHub client's
        `get_pull_request`, `get_release_by_tag`, `get_batch_evidence` and
        `get_dispatch_evidence` readers. `operations` is this request's own
        journal operations directory; `root` is the repository root the
        prepared output lives under. `batch_workflow_id` is the policy's
        pinned batch executor workflow identity.
        """
        for name, reader in (("is_main_ancestor", git),):
            if not callable(getattr(reader, name, None)):
                _fail(f"requires a Git reader with {name}")
        for name in ("get_pull_request", "get_release_by_tag", "get_batch_evidence",
                     "get_dispatch_evidence"):
            if not callable(getattr(github, name, None)):
                _fail(f"requires a GitHub reader with {name}")
        if type(repository) is not str or not re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", repository):
            _fail("requires the canonical repository name")
        if type(batch_workflow_id) is not int or batch_workflow_id <= 0:
            _fail("requires the pinned batch workflow identity")
        self.root = Path(root).absolute()
        self.operations = Path(operations).absolute()
        self.repository = repository
        self.git, self.github = git, github
        self.batch_workflow_id = batch_workflow_id

    # -- driver protocol -------------------------------------------------

    def recheck(self, state, operation):
        """The cheap immutability recheck of one verified transition, or None.

        None keeps the step's full observation. Any covered step answers an
        Observation: `verified` only with evidence equal to the record.
        """
        if type(operation) is not dict or operation.get("status") != "verified":
            _fail("applies only to a transition the journal verified")
        step = operation.get("step")
        if step not in STEPS:
            _fail("names an unknown step")
        if step not in RECHECKED_STEPS:
            return None
        if type(state) is not dict or type(state.get("request")) is not dict:
            _fail("requires the running request state")
        evidence = operation.get("evidence")
        if (type(evidence) is not dict or set(evidence) != {"sha256", "reference"}
                or not isinstance(evidence["reference"], str)
                or not isinstance(evidence["sha256"], str)
                or _DIGEST.fullmatch(evidence["sha256"]) is None):
            _fail("the verified record carries no evidence")
        if step == "candidate":
            return self._candidate(evidence)
        if step == "verification":
            return self._verification(evidence)
        if step in _PR_STEPS:
            return self._pull_request(step, evidence)
        if step == "draft":
            return self._draft(state, evidence)
        if step == "publication":
            return self._publication(state, evidence)
        return self._deployment(step, state, evidence)

    # -- shared readers --------------------------------------------------

    @staticmethod
    def _settle(step, recorded, live):
        if live != recorded:
            return _conflict(f"{step}: the live immutable identity differs from the recorded evidence")
        return Observation("verified", deepcopy(recorded))

    def _candidate_state(self):
        document = read_private_document(self.operations / "candidate-transition",
                                         "candidate-transition.json")
        if document is None:
            return None
        if document.get("schema") != "lmdj.candidate-transition.v1":
            _fail("the candidate transition state is not the expected record")
        return document

    def _tag(self, state):
        request = state["request"]
        tag = request.get("requested_tag")
        if tag is None:
            document = self._candidate_state()
            scope = document.get("scope") if document is not None else None
            cut = scope.get("cut_spec") if type(scope) is dict else None
            build = cut.get("product_build") if type(cut) is dict else None
            if type(build) is not str or _BUILD.fullmatch(build) is None:
                _fail("the candidate transition records no valid product build")
            tag = "lmdj-v" + build
        return tag

    @staticmethod
    def _merge(record):
        """(number, merge_sha, head_sha) from a retained merge record, or None."""
        merge = record.get("merge") if type(record) is dict else None
        if type(merge) is not dict:
            return None
        number, merge_sha, head = merge.get("number"), merge.get("merge_sha"), merge.get("head_sha")
        if type(number) is not int or isinstance(number, bool) or number <= 0 \
                or type(merge_sha) is not str or _SHA.fullmatch(merge_sha) is None \
                or type(head) is not str or _SHA.fullmatch(head) is None:
            _fail("a retained merge record carries no valid Pull Request identity")
        return number, merge_sha, head

    def _merged_pull_request(self, number, head_sha):
        """The live Pull Request row still merged from the reviewed head, or an
        Observation refusing it."""
        row = self.github.get_pull_request(self.repository, number)
        if row is None:
            return Observation("absent")
        merge_sha = row.get("merge_commit_sha")
        if row.get("merged") is not True or type(merge_sha) is not str \
                or _SHA.fullmatch(merge_sha) is None:
            return _conflict(f"pull request #{number} is no longer a merged squash")
        if row.get("head_sha") != head_sha:
            return _conflict(f"pull request #{number} no longer merges the reviewed head")
        if not self.git.is_main_ancestor(merge_sha):
            return _conflict(f"pull request #{number}'s merge commit is not reachable canonical history")
        return row

    def _run(self, reader, run_id):
        document = reader(f"/repos/{self.repository}/actions/runs/{run_id}")
        if type(document) is not dict:
            _fail(f"run {run_id} is not readable")
        return document

    def _completed_first_attempt(self, run, run_id, *, path, workflow_id):
        if run.get("id") != run_id:
            return f"run {run_id} answers for another run"
        if run.get("path") != path or run.get("workflow_id") != workflow_id:
            return f"run {run_id} is not a run of the pinned {path}"
        if run.get("run_attempt") != 1:
            return f"run {run_id} was re-run; attempt 1 is the verified evidence"
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            return f"run {run_id} is no longer a completed, passed run"
        head = run.get("head_sha")
        if run.get("head_branch") != "main" or type(head) is not str \
                or _SHA.fullmatch(head) is None or not self.git.is_main_ancestor(head):
            return f"run {run_id} did not run on canonical main"
        return None

    def _dispatch_spec(self, step, tag):
        """The retained durable dispatch spec for this step and tag, or None."""
        record = read_private_document(self.operations / f"dispatch-{step}", "dispatch.json")
        if record is None:
            return None
        spec = record.get("spec") if record.get("schema") == "lmdj.durable-dispatch.v1" else None
        inputs = spec.get("inputs") if type(spec) is dict else None
        if type(inputs) is not dict or inputs.get("tag") != tag \
                or type(spec.get("workflow_id")) is not int or spec["workflow_id"] <= 0:
            _fail(f"{step}: the retained dispatch does not name this release")
        return spec

    def _plan_assets(self, tag):
        """The prepared plan's closed asset inventory as {name: bytes}."""
        from .prepared_step import _PLAN_DOCUMENT, output_relative

        try:
            document = json.loads((self.root / output_relative(tag) / _PLAN_DOCUMENT).read_bytes())
        except (OSError, ValueError, UnicodeError):
            _fail("the prepared plan document is unreadable")
        assets = document.get("assets") if type(document) is dict else None
        if type(assets) is not list or not assets or any(
                type(item) is not dict or type(item.get("name")) is not str
                or type(item.get("bytes")) is not int for item in assets):
            _fail("the prepared plan carries no closed asset inventory")
        inventory = {item["name"]: item["bytes"] for item in assets}
        if len(inventory) != len(assets):
            _fail("the prepared plan names an asset twice")
        return inventory

    def _assets_drift(self, step, tag, release):
        """Why the live asset inventory differs from the prepared plan, or None.

        Names and sizes only: the bytes were verified when the step first
        verified (and again by the publish workflow); what a resume must see
        is an asset removed, replaced by another size, or no longer uploaded.
        """
        inventory = self._plan_assets(tag)
        live = {}
        for asset in release.assets:
            if asset.name in live:
                return f"{step}: the Release carries asset {asset.name} twice"
            live[asset.name] = asset
        if set(live) != set(inventory):
            return f"{step}: the Release asset inventory differs from the prepared plan"
        for name, size in inventory.items():
            if live[name].size != size:
                return f"{step}: asset {name} no longer has the prepared size"
            if live[name].state != "uploaded":
                return f"{step}: asset {name} is no longer uploaded"
        return None

    # -- steps -------------------------------------------------------------

    def _candidate(self, evidence):
        document = self._candidate_state()
        if document is None:
            return Observation("absent")
        scope = document.get("scope")
        cut = scope.get("cut_spec") if type(scope) is dict else None
        operation_id = cut.get("operation_id") if type(cut) is dict else None
        if type(operation_id) is not str or _DIGEST.fullmatch(operation_id) is None:
            _fail("the candidate transition state records no operation")
        for name in ("cut_merge", "witness_merge"):
            identity = self._merge(document.get(name))
            if identity is None:
                return _conflict(f"candidate: the retained state records no verified {name}")
            number, merge_sha, head = identity
            row = self._merged_pull_request(number, head)
            if type(row) is Observation:
                return row
            if row["merge_commit_sha"] != merge_sha:
                return _conflict(f"candidate: pull request #{number} now merges at another commit")
        live = {"sha256": canonical_sha256(document),
                "reference": "candidate:" + operation_id}
        return self._settle("candidate", evidence, live)

    def _verification(self, evidence):
        matched = _BATCH_REFERENCE.fullmatch(evidence["reference"])
        if matched is None:
            return _conflict("verification: the recorded reference is not a batch result")
        run_id, witness = int(matched.group(1)), matched.group(2)
        document = self._candidate_state()
        identity = self._merge(document.get("witness_merge")) if document is not None else None
        if identity is None:
            return _conflict("verification: the candidate records no verified witness merge")
        if identity[1] != witness:
            return _conflict("verification: the candidate witness merge differs from the verified target")
        if not self.git.is_main_ancestor(witness):
            return _conflict("verification: the verified target is not reachable canonical history")
        run = self._run(self.github.get_batch_evidence, run_id)
        drift = self._completed_first_attempt(run, run_id, path=_BATCH_WORKFLOW,
                                              workflow_id=self.batch_workflow_id)
        if drift is not None:
            return _conflict("verification: " + drift)
        # The reviewed intent freezes the same batch reference the verification
        # step verified; once its record exists, the two must still agree.
        intent = read_private_document(self.operations / "intent-sequence/pr", "pr-state.json")
        if intent is not None:
            spec = intent.get("spec") if intent.get("schema") == "lmdj.evidence-pr-state.v1" else None
            if type(spec) is not dict:
                _fail("verification: the retained intent record is not the expected record")
            if (canonical_sha256(spec.get("batch_reference")) != evidence["sha256"]
                    or spec.get("batch_run_id") != run_id
                    or spec.get("target_revision") != witness):
                return _conflict("verification: the reviewed intent binds another batch reference")
        # The reference document hashes retained controller attestations; the
        # recorded digest is the proof already made, bound here to a run that
        # is still the same completed first attempt for the same witness.
        return Observation("verified", deepcopy(evidence))

    def _pull_request(self, step, evidence):
        relative, kind, reference = _PR_STEPS[step]
        record = read_private_document(self.operations / relative, "pr-state.json")
        if record is None:
            return Observation("absent")
        if record.get("schema") != "lmdj.evidence-pr-state.v1":
            _fail(f"{step}: the retained Pull Request state is not the expected record")
        number, review = record.get("number"), record.get("review_evidence")
        if type(number) is not int or isinstance(number, bool) or number <= 0 \
                or type(review) is not dict \
                or type(review.get("sha256")) is not str \
                or _DIGEST.fullmatch(review["sha256"]) is None:
            return _conflict(f"{step}: the retained state records no reviewed merge")
        spec = record.get("spec")
        head = spec.get("head_sha") if type(spec) is dict else None
        if type(head) is not str or _SHA.fullmatch(head) is None:
            _fail(f"{step}: the retained Pull Request state names no reviewed head")
        row = self._merged_pull_request(number, head)
        if type(row) is Observation:
            return row
        merge_sha = row["merge_commit_sha"]
        live = {"sha256": canonical_sha256({"kind": kind, "merge": merge_sha,
                                            "review": review["sha256"]}),
                "reference": reference.format(number=number, merge=merge_sha)}
        return self._settle(step, evidence, live)

    def _release(self, tag):
        """(projection, release) for the Release under the tag, or None."""
        from .draft_step import release_projection

        release = self.github.get_release_by_tag(self.repository, tag)
        if release is None:
            return None
        projection = release_projection(release)
        if type(projection.id) is not int or projection.id <= 0:
            _fail("the far-side Release carries no valid numeric identity")
        return projection, release

    def _plan(self, tag):
        from .carriers import read_prepared_plan

        return read_prepared_plan(self.root, tag)

    def _draft(self, state, evidence):
        tag = self._tag(state)
        plan = self._plan(tag)
        if plan is None:
            return _conflict("draft: the prepared plan this Draft was verified against is missing")
        found = self._release(tag)
        if found is None:
            return Observation("absent")
        projection, release = found
        if projection.tag != tag or projection.plan_sha256 != plan:
            return _conflict("draft: the far-side Release no longer carries the prepared plan")
        drift = self._assets_drift("draft", tag, release)
        if drift is not None:
            return _conflict(drift)
        live = {"sha256": canonical_sha256({"tag": tag, "plan_sha256": plan,
                                            "release_id": projection.id}),
                "reference": "draft:" + str(projection.id)}
        return self._settle("draft", evidence, live)

    def _publication(self, state, evidence):
        tag = self._tag(state)
        if evidence["reference"] != f"https://github.com/{self.repository}/releases/tag/{tag}":
            return _conflict("publication: the recorded reference is not this release's publication")
        spec = self._dispatch_spec("publication", tag)
        if spec is None:
            return Observation("absent")
        inputs = spec["inputs"]
        try:
            release_id = int(inputs.get("release_id"))
        except (TypeError, ValueError):
            _fail("publication: the retained dispatch names no numeric Release")
        plan = self._plan(tag)
        if plan is None or inputs.get("plan_sha256") != plan:
            return _conflict("publication: the prepared plan differs from the dispatched one")
        found = self._release(tag)
        if found is None:
            return Observation("absent")
        projection, release = found
        if projection.id != release_id:
            return _conflict("publication: the Release under this tag is not the one dispatched")
        if projection.draft:
            return _conflict("publication: the dispatched Release is still a draft")
        if projection.plan_sha256 != plan:
            return _conflict("publication: the published Release no longer carries the prepared plan")
        drift = self._assets_drift("publication", tag, release)
        if drift is not None:
            return _conflict(drift)
        return Observation("verified", deepcopy(evidence))

    def _deployment(self, step, state, evidence):
        matched = _RUN_URL.fullmatch(evidence["reference"])
        if matched is None:
            return _conflict(f"{step}: the recorded reference is not a deployment run")
        run_id = int(matched.group(1))
        spec = self._dispatch_spec(step, self._tag(state))
        if spec is None:
            return Observation("absent")
        run = self._run(self.github.get_dispatch_evidence, run_id)
        drift = self._completed_first_attempt(run, run_id, path=_DEPLOY_WORKFLOWS[step],
                                              workflow_id=spec["workflow_id"])
        if drift is None and run.get("event") != "workflow_dispatch":
            drift = f"run {run_id} was not dispatched"
        if drift is not None:
            return _conflict(f"{step}: " + drift)
        return Observation("verified", deepcopy(evidence))
