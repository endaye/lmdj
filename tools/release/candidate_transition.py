"""Managed checked-cut -> reviewed squash -> witness -> reviewed squash.

This is not request freezing/materialization, a live service, complete CI or a
release. Gates authenticate original authority and independent current/historical
review; concrete source and command verifiers additionally prove every local leg.
"""
from copy import deepcopy
from pathlib import Path
import re

from .batch_reference import positive, sha
from .candidate_branch import CandidateBranch
from .candidate_checks import CandidateTaskChecks
from .candidate_pr import CandidatePullRequest, validate_spec as validate_cut
from .candidate_pr_sequence import CandidatePrSequence
from .candidate_snapshot import read
from .candidate_source import CandidateSourceVerifier
from .candidate_task_workspace import CandidateTaskWorkspace
from .candidate_witness import CandidateWitnessRun, same
from .candidate_witness_task import CandidateWitnessTask
from .github_api import GitHubClient
from .model import canonical_json, canonical_sha256
from .orchestration import RequestJournal, _validate_state, validate_request
from .orchestration_driver import Observation
from .witness_checks import WitnessTaskChecks
from .witness_pr import WitnessBranch, WitnessPullRequest, WitnessPrSequence, validate_spec as validate_witness
from .witness_source import CandidateWitnessSourceVerifier


class CandidateTransitionError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise CandidateTransitionError(f"why: managed candidate {reason}; remedy: restore the original request, checked cut and child journals; reconcile the same target without replaying unknown writes or bypassing witness and review")


class CandidateTransition:
    STATE = "candidate-transition.json"
    MARKER = "candidate-transition-operation.json"

    def __init__(self, root, *, checks, request, source, checked_cut, frozen,
                 repository_id, client, token, authorize, observe_main, review, verify_merged,
                 witness_root, author_name, author_email, timestamp):
        require(type(checks) is CandidateTaskChecks and type(client) is GitHubClient,
                "requires the concrete cut checks and authenticated GitHub transport")
        require(all(callable(v) for v in (authorize, observe_main, review, verify_merged))
                and positive(repository_id), "trusted authority, main and review gates are required")
        validate_request(request)
        require(request["mode"] == "new" and request["repository"] == "endaye/lmdj",
                "checked-cut allocation requires a new-version request, not an existing tag")
        require(type(timestamp) is int and 1 <= timestamp <= 253402300799
                and type(author_name) is str and re.fullmatch(r"[A-Za-z0-9 ._-]{1,80}", author_name)
                and type(author_email) is str and re.fullmatch(r"[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+", author_email),
                "fixed Task author identity or timestamp is invalid")
        self.root = Path(root).absolute()
        require(self.root.resolve() == self.root, "private root contains symlinks")
        self.request, self.source, self.checked, self.frozen = deepcopy((request, source, checked_cut, frozen))
        self.checks, self.source_verifier = checks, CandidateSourceVerifier(checks.cut)
        self.authorize, self.observe_main = authorize, observe_main
        self.review, self.verify_merged = review, verify_merged
        self.author = dict(author_name=author_name, author_email=author_email, timestamp=timestamp)
        self._active = None
        self._persisted = None
        cut = self.checked["cut"]
        binding = {k:v for k,v in cut.items() if k not in ("status", "files", "product_build")}
        self.cut_spec = dict(operation_id=source["operation_id"], request_sha256=canonical_sha256(request),
            repository_id=repository_id, actor_id=request["actor_id"], base_revision=cut["base_revision"],
            head_sha=cut["commit"], tree_sha=cut["tree"], product_build=cut["product_build"],
            source_sha=source["commit"], cut_binding_sha256=canonical_sha256(binding),
            snapshot_sha256=cut["snapshot_sha256"], task_evidence_sha256=checked_cut["checks"]["sha256"])
        validate_cut(self.cut_spec)
        self.cut_pr = CandidatePrSequence(self.root / "cut-pr",
            branch=CandidateBranch(self.root / "cut-pr/branch", checks.local.root, token=token, authorize=self._cut_authorize),
            pr=CandidatePullRequest(self.root / "cut-pr/pr", api=client.candidate_pr_request,
                authorize=self._cut_authorize, review=self._cut_review, verify_merged=self._cut_merged))
        self.cut_pr.branch.api = client.candidate_pr_request
        self.witness = CandidateWitnessRun(self.source_verifier, authorize=self._local_authorize,
            observe_main=self._main, path=checks.path)
        self.task = CandidateWitnessTask(witness_root, self.witness)
        self.workspace = CandidateTaskWorkspace(self.root / "workspace", self.task,
            authorize=self._local_authorize, control_revision=checks.control, path=checks.path)
        self.witness_checks = WitnessTaskChecks(self.task, control_revision=checks.control,
            authorize=self._local_authorize, path=checks.path)
        self.witness_source = CandidateWitnessSourceVerifier(self.task)
        self.witness_pr = WitnessPrSequence(self.root / "witness-pr",
            branch=WitnessBranch(self.root / "witness-pr/branch", self.task.root, token=token, authorize=self._witness_authorize),
            pr=WitnessPullRequest(self.root / "witness-pr/pr", api=client.witness_pr_request,
                authorize=self._witness_authorize, review=self._witness_review, verify_merged=self._witness_merged))
        self.witness_pr.branch.api = client.witness_pr_request
        self.scope = dict(request_sha256=canonical_sha256(request), source_sha256=canonical_sha256(source),
            checked_cut_sha256=canonical_sha256(checked_cut), frozen_sha256=canonical_sha256(frozen),
            cut_spec=self.cut_spec, witness_root=str(self.task.root), author=self.author,
            control_revision=checks.control, path=checks.path)
        require(len(canonical_json(self.scope)) <= 8192, "scope exceeds its read budget")

    def _save(self, journal, state):
        journal._active()
        if self._active is not None:
            require(journal is self._active[0] and state is self._active[1]
                and same(self._state(journal), self._persisted), "parent history changed before checkpoint")
        raw = canonical_json(state)
        require(len(raw) <= 65536, "state exceeds its read budget")
        journal._write(self.STATE, raw)
        if self._active is not None:
            self._persisted = deepcopy(state)

    def _state(self, journal, *, initialize=False):
        marker, state = read(journal, self.MARKER, optional=True), read(journal, self.STATE, optional=True)
        if marker is None:
            require(state is None, "state exists without enrollment")
            if not initialize:
                return None
            journal._write(self.MARKER, canonical_json(self.scope))
            state = dict(schema="lmdj.candidate-transition.v1", scope=deepcopy(self.scope), cut_merge=None,
                witness_started=False, witness=None, workspace_base=None, workspace_started=False,
                workspace=None, task_started=False, task=None, witness_pr_started=False, witness_merge=None)
            self._save(journal, state)
        require(same(read(journal, self.MARKER), self.scope) and type(state) is dict
            and set(state) == {"schema", "scope", "cut_merge", "witness_started", "witness", "workspace_base",
                "workspace_started", "workspace", "task_started", "task", "witness_pr_started", "witness_merge"}
            and state["schema"] == "lmdj.candidate-transition.v1" and same(state["scope"], self.scope),
            "enrolled history is missing, corrupt or rebound")
        require(all(type(state[k]) is bool for k in ("witness_started", "workspace_started", "task_started", "witness_pr_started"))
            and all(state[k] is None or type(state[k]) is dict for k in ("cut_merge", "witness", "workspace", "task", "witness_merge"))
            and (state["workspace_base"] is None or sha(state["workspace_base"])), "child receipt schema is invalid")
        require((not state["witness_started"] or state["cut_merge"] is not None)
            and (state["witness"] is None or state["witness_started"])
            and (state["workspace_base"] is None or state["witness"] is not None)
            and (not state["workspace_started"] or state["workspace_base"] is not None)
            and (state["workspace"] is None or state["workspace_started"])
            and (not state["task_started"] or state["workspace"] is not None)
            and (state["task"] is None or state["task_started"])
            and (not state["witness_pr_started"] or state["task"] is not None)
            and (state["witness_merge"] is None or state["witness_pr_started"]), "child ordering changed")
        return state

    def _guard(self):
        require(self._active is not None, "original parent writer is not held")
        journal, state, before_write = self._active
        journal._active()
        require(same(state, self._persisted) and same(self._state(journal), self._persisted), "parent history changed")
        try:
            self.authorize(deepcopy(self.request))
            if before_write is not None:
                before_write()
        except Exception:
            raise CandidateTransitionError("why: managed candidate original authority is unavailable; remedy: restore the original grant and writer without exposing callback output or replaying effects") from None
        journal._active()
        require(same(state, self._persisted) and same(self._state(journal), self._persisted), "parent history changed during authorization")

    def _local_authorize(self, scope):
        self._guard()  # Called inside child source/task writers; do not nest them.

    def _main(self):
        try:
            revision = self.observe_main()
        except Exception:
            raise CandidateTransitionError("why: managed candidate main observation is unavailable; remedy: restore the authenticated main observer without exposing callback output or selecting another target") from None
        require(sha(revision), "observed main is not an exact revision")
        return revision

    def _inputs(self):
        return dict(request=self.request, source=self.source, cut=self.checked["cut"], frozen=self.frozen)

    def _witness_inputs(self):
        return dict(self._inputs(), merge_revision=self._active[1]["cut_merge"]["merge"]["merge_sha"])

    def _cut_authorize(self, spec):
        self._guard()
        require(same(spec, self.cut_spec), "cut PR scope changed")
        require(same(self.checks.verify(spec), self.checked["checks"]), "cut command receipt changed")
        self._guard()

    def _cut_write_guard(self):
        self._cut_authorize(self.cut_spec)
        self.source_verifier.verify(**self._inputs(), main_revision=self._main())
        self._guard()

    def _cut_review(self, spec, row):
        return self.review("candidate", deepcopy(spec), deepcopy(row))

    def _cut_merged(self, spec, row, review):
        gate = self.verify_merged("candidate", deepcopy(spec), deepcopy(row), deepcopy(review))
        require(type(gate) is Observation, "historical candidate review is invalid")
        gate.validate()
        if gate.status != "verified":
            return gate
        proof = self.source_verifier.verify(**self._inputs(), main_revision=self._main(),
            merge_revision=row["merge_commit_sha"])
        self._guard()
        return Observation("verified", dict(sha256=canonical_sha256(dict(review=gate.evidence,
            source={k:v for k,v in proof.items() if k != "observed_main"})), reference="candidate-squash:" + str(row["id"])))

    def _witness_spec(self):
        state = self._active[1]
        task = state["task"]["task"]
        binding = {k:v for k,v in task.items() if k not in ("status", "files")}
        spec = dict(operation_id=task["operation_id"], request_sha256=canonical_sha256(self.request),
            repository_id=self.cut_spec["repository_id"], actor_id=self.request["actor_id"],
            base_revision=task["base_revision"], head_sha=task["commit"], tree_sha=task["tree"],
            product_build=self.cut_spec["product_build"], target_revision=self._witness_inputs()["merge_revision"],
            source_sha=self.source["commit"], witness_receipt_sha256=canonical_sha256(state["witness"]),
            task_binding_sha256=canonical_sha256(binding), task_evidence_sha256=state["task"]["checks"]["sha256"],
            witness=state["witness"]["receipt"]["witness"])
        validate_witness(spec)
        return spec

    def _witness_authorize(self, spec):
        self._guard()
        require(same(spec, self._witness_spec()), "witness PR scope changed")
        require(same(self.witness_checks.verify(spec), self._active[1]["task"]["checks"]), "witness command receipt changed")
        self.witness_source.verify(spec, receipt=self._active[1]["witness"], **self._inputs(),
            main_revision=self._main())
        self._guard()

    def _witness_review(self, spec, row):
        return self.review("witness", deepcopy(spec), deepcopy(row))

    def _witness_merged(self, spec, row, review):
        gate = self.verify_merged("witness", deepcopy(spec), deepcopy(row), deepcopy(review))
        require(type(gate) is Observation, "historical witness review is invalid")
        gate.validate()
        if gate.status != "verified":
            return gate
        proof = self.witness_source.verify(spec, receipt=self._active[1]["witness"], **self._inputs(),
            main_revision=self._main(), merge_revision=row["merge_commit_sha"])
        self._guard()
        return Observation("verified", dict(sha256=canonical_sha256(dict(review=gate.evidence,
            source={k:v for k,v in proof.items() if k != "observed_main"})), reference="witness-squash:" + str(row["id"])))

    def _bound(self, state, operation):
        _validate_state(state)
        require(same(state["request"], self.request) and state["request_digest"] == self.scope["request_sha256"]
            and operation.get("step") == "candidate" and operation.get("operation_id") == self.cut_spec["operation_id"],
            "driver operation is not the original allocation request")
        return any(row["operation_id"] == operation["operation_id"] for row in state["transitions"])

    def observe(self, state, operation):
        result = self._run(state, operation, mutate=False, before_write=None)
        return Observation(result["status"], result["evidence"])

    def verified_candidate(self, state, operation):
        """Fresh exact identities for later candidate-test/intent consumers."""
        result = self._run(state, operation, mutate=False, before_write=None)
        require(result["status"] == "verified", "candidate is not fully verified")
        return result["candidate"]

    def advance(self, state, operation, *, before_write):
        require(callable(before_write) and self._bound(state, operation) and state["transitions"]
            and state["transitions"][-1] == operation and operation["status"] == "intent",
            "advance lacks its durable driver frontier and final guard")
        return self._run(state, operation, mutate=True, before_write=before_write)

    def _run(self, parent, operation, *, mutate, before_write):
        try:
            return self._drive(parent, operation, mutate=mutate, before_write=before_write)
        except CandidateTransitionError:
            raise
        except Exception:
            raise CandidateTransitionError("why: managed candidate evidence or child execution is unavailable; remedy: retain the original parent and child attempts and restore their authority without exposing callback output or retrying unknown effects") from None

    def _drive(self, parent, operation, *, mutate, before_write):
        started = self._bound(parent, operation)
        require(self._active is None, "controller is already running")
        result = lambda status: dict(status=status, evidence=None)
        with RequestJournal(self.root) as journal:
            state = self._state(journal, initialize=not started)
            if state is None:
                return result("unknown")
            self._active = (journal, state, before_write)
            self._persisted = deepcopy(state)
            try:
                self._guard()
                # The cut child is enrolled before the driver records candidate
                # intent. Thereafter its own sequence cannot be re-enrolled.
                observed = self.cut_pr.observe(self.cut_spec, initialize=not started)
                if mutate and observed["status"] in ("absent", "pending"):
                    self.cut_pr.advance(self.cut_spec, before_write=self._cut_write_guard)
                    observed = self.cut_pr.observe(self.cut_spec)
                if observed["status"] != "merged":
                    return result(observed["status"])
                cut_merge = self.cut_pr.pr.observe_merge(self.cut_spec)
                if cut_merge["status"] != "verified":
                    return result(cut_merge["status"])
                self._guard()
                require(state["cut_merge"] is None or same(state["cut_merge"], cut_merge), "verified candidate squash changed")
                state["cut_merge"] = cut_merge
                self._save(journal, state)
                inputs = self._witness_inputs()
                observed = self.witness.observe(**inputs)
                if observed["status"] == "absent" and state["witness_started"]:
                    return result("unknown")
                if observed["status"] != "verified":
                    if not mutate:
                        return result("pending")
                    state["witness_started"] = True
                    self._save(journal, state)
                    self._guard()
                    self.witness.run(**inputs)
                    observed = self.witness.observe(**inputs)
                require(observed["status"] == "verified", "witness command did not yield confirmed evidence")
                require(state["witness"] is None or same(state["witness"], observed["receipt"]), "confirmed witness receipt changed")
                state.update(witness_started=True, witness=observed["receipt"])
                self._save(journal, state)
                if state["workspace_base"] is None:
                    base = self._main()
                    self._guard()
                    state["workspace_base"] = base
                    self._save(journal, state)
                workspace_args = dict(receipt=state["witness"], base_revision=state["workspace_base"], **inputs)
                observed = self.workspace.observe(**workspace_args)
                if observed["status"] == "absent" and state["workspace_started"]:
                    return result("unknown")
                if observed["status"] in ("absent", "pending"):
                    if not mutate:
                        return result("pending")
                    state["workspace_started"] = True
                    self._save(journal, state)
                    self.workspace.prepare(**workspace_args, before_write=self._guard)
                    observed = self.workspace.observe(**workspace_args)
                if observed["status"] != "verified":
                    return result(observed["status"])
                require(state["workspace"] is None or same(state["workspace"], observed["evidence"]), "workspace receipt changed")
                state.update(workspace_started=True, workspace=observed["evidence"])
                self._save(journal, state)
                if state["task"] is None:
                    if not mutate:
                        return result("pending")
                    if state["task_started"]:
                        gitdir = Path(self.task.git("rev-parse", "--absolute-git-dir").decode().strip())
                        with self.task._locked(gitdir) as task_journal:
                            if read(task_journal, "task-operation.json", optional=True) is None:
                                return result("unknown")
                    state["task_started"] = True
                    self._save(journal, state)
                    self._guard()
                    checked = self.witness_checks.prepare(**workspace_args, **self.author)
                    self._guard()
                    state["task"] = checked
                    self._save(journal, state)
                spec = self._witness_spec()
                self._witness_authorize(spec)
                # As with the cut, enroll before persisting the parent's child
                # start. Child markers prevent reenrollment after a gap/crash.
                observed = self.witness_pr.observe(spec, initialize=not state["witness_pr_started"])
                state["witness_pr_started"] = True
                self._save(journal, state)
                if mutate and observed["status"] in ("absent", "pending"):
                    self.witness_pr.advance(spec, before_write=lambda: self._witness_authorize(spec))
                    observed = self.witness_pr.observe(spec)
                if observed["status"] != "merged":
                    return result(observed["status"])
                merged = self.witness_pr.pr.observe_merge(spec)
                if merged["status"] != "verified":
                    return result(merged["status"])
                self._guard()
                require(state["witness_merge"] is None or same(state["witness_merge"], merged), "verified witness squash changed")
                state["witness_merge"] = merged
                self._save(journal, state)
                self._guard()
                candidate = dict(operation_id=self.cut_spec["operation_id"], product_build=self.cut_spec["product_build"],
                    target_revision=cut_merge["merge"]["merge_sha"], witness_revision=merged["merge"]["merge_sha"],
                    candidate_pr=cut_merge["merge"], witness_pr=merged["merge"],
                    snapshot_sha256=self.cut_spec["snapshot_sha256"], witness=spec["witness"])
                return dict(status="verified", candidate=candidate, evidence=dict(sha256=canonical_sha256(state),
                    reference="candidate:" + self.cut_spec["operation_id"]))
            finally:
                self._active = None
                self._persisted = None
