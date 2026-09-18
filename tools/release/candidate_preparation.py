"""Owned request -> source -> snapshot -> checked cut, without remote effects."""
from copy import deepcopy
from pathlib import Path
import re

from scripts import version
from .batch_reference import sha
from .candidate_material import CandidateBuildMaterial
from .candidate_workspace import CandidateSourceWorkspace
from .candidate_source_setup import CandidateSourceSetup
from .candidate_snapshot import CandidateSnapshotRun, read
from .candidate_cut import CandidateCutWorkspace
from .candidate_checks import CandidateTaskChecks
from .model import canonical_json, canonical_sha256
from .orchestration import RequestJournal, validate_request


class CandidatePreparationError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise CandidatePreparationError(f"why: candidate preparation {reason}; remedy: restore the original request and child histories, reconcile the same owned candidate without reallocating, replaying unknown commands or bypassing Task verification")


def same(left, right):
    return canonical_json(left) == canonical_json(right)


class CandidatePreparation:
    STATE = "candidate-preparation.json"
    MARKER = "candidate-preparation-operation.json"

    def __init__(self, root, *, repository_root, source_root, reservation_root,
                 request, authorize, observe_main, path, author_name, author_email,
                 source_timestamp, clock):
        validate_request(request)
        require(request["mode"] == "new" and all(callable(v) for v in (authorize, observe_main, clock)),
                "requires original new request and trusted authority, main and clock")
        require(type(source_timestamp) is int and 1 <= source_timestamp <= 253402300799
                and type(author_name) is str and re.fullmatch(r"[A-Za-z0-9 ._-]{1,80}", author_name)
                and type(author_email) is str and re.fullmatch(r"[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+", author_email),
                "fixed source timestamp or Task author is invalid")
        self.root = Path(root).absolute()
        require(self.root.resolve() == self.root, "parent root contains symlinks")
        self.request, self.authorize = deepcopy(request), authorize
        self.observe_main, self.clock, self.path = observe_main, clock, path
        self.author = dict(author_name=author_name, author_email=author_email)
        self.timestamp = source_timestamp
        self.material = CandidateBuildMaterial(repository_root, reservation_root)
        self.local = CandidateSourceWorkspace(source_root, self.material)
        self.setup = CandidateSourceSetup(self.root / "source-setup", self.local,
            repository_root=repository_root, request=request, authorize=self._child_authorize,
            observe_main=self._main, path=path)
        self.snapshot = CandidateSnapshotRun(self.local, authorize=self._child_authorize, path=path)
        self.checks = CandidateTaskChecks(CandidateCutWorkspace(self.snapshot),
            control_revision=request["control_revision"], authorize=self._child_authorize, path=path)
        self.scope = dict(request=self.request, repository_root=str(self.setup.repository.root),
            source_root=str(self.local.root), reservation_root=str(Path(reservation_root).absolute()),
            path=path, author=self.author, source_timestamp=source_timestamp)
        require(len(canonical_json(self.scope)) <= 8192, "scope exceeds its bound")
        self._active = None

    def _state(self, journal):
        marker, state = read(journal, self.MARKER, optional=True), read(journal, self.STATE, optional=True)
        if marker is None:
            require(state is None, "state exists without enrollment")
            return None
        require(same(marker, self.scope) and type(state) is dict and set(state) ==
            {"schema", "scope", "setup_started", "setup", "source_started", "source",
             "snapshot_started", "snapshot", "cut_started", "cut_timestamp", "checked_cut"}
            and state["schema"] == "lmdj.candidate-preparation.v1" and same(state["scope"], self.scope),
            "original enrollment is missing, corrupt or rebound")
        require(all(type(state[k]) is bool for k in ("setup_started", "source_started", "snapshot_started", "cut_started"))
            and all(state[k] is None or type(state[k]) is dict for k in ("setup", "source", "snapshot", "checked_cut"))
            and (state["cut_timestamp"] is None or (type(state["cut_timestamp"]) is int
                and self.timestamp <= state["cut_timestamp"] <= 253402300799)), "child schema is invalid")
        require((state["setup"] is None or state["setup_started"])
            and (not state["source_started"] or state["setup"] is not None)
            and (state["source"] is None or state["source_started"])
            and (not state["snapshot_started"] or state["source"] is not None)
            and (state["snapshot"] is None or state["snapshot_started"])
            and (not state["cut_started"] or (state["snapshot"] is not None and state["cut_timestamp"] is not None))
            and (state["cut_timestamp"] is None or state["cut_started"])
            and (state["checked_cut"] is None or state["cut_started"]), "child order changed")
        return state

    def _save(self):
        journal, state, _, _ = self._active
        require(same(self._state(journal), self._persisted), "parent history changed before checkpoint")
        raw = canonical_json(state)
        require(len(raw) <= 65536, "history exceeds its read bound")
        journal._write(self.STATE, raw)
        self._persisted = deepcopy(state)

    def _main(self):
        main = self.observe_main()
        require(sha(main), "main is not an exact revision")
        return main

    def _guard(self, *, live=False):
        require(self._active is not None, "parent writer is not held")
        journal, state, before_write, _ = self._active
        journal._active()
        require(same(self._state(journal), self._persisted) and same(state, self._persisted), "parent history changed")
        try:
            self.authorize(deepcopy(self.request))
            if before_write is not None:
                before_write()
            main = self._main()
        except Exception:
            raise CandidatePreparationError("why: candidate preparation authority or main is unavailable; remedy: restore the original trusted grant without exposing callback output or replaying effects") from None
        self.setup.repository.git("merge-base", "--is-ancestor", self.request["base_revision"], main)
        if state["setup"] is not None:
            reservation = self.material.reservations.observe(self.request, self._frozen,
                main if live else self.request["base_revision"])
            require(reservation is not None and canonical_sha256(reservation) == state["setup"]["reservation_sha256"],
                    "original reservation changed")
        elif live:
            self.material.inputs.verify(self._frozen, main)
        journal._active()
        require(same(self._state(journal), self._persisted) and same(state, self._persisted), "parent history changed during authority check")
        return main

    def _child_authorize(self, unused):
        if self._active is not None:
            self._guard(live=self._active[3] and self._active[1]["checked_cut"] is None)
            return
        # Post-drive verification (the transition's reviewed-squash proof)
        # re-proves the same authority without a drive session: this context
        # performs no writes and the durable receipts it authenticates were
        # checkpointed under the drive's own writer.
        frozen = self.material.inputs.freeze(self.request["base_revision"])
        main = self._main()
        self.setup.repository.git("merge-base", "--is-ancestor", self.request["base_revision"], main)
        self.material.inputs.verify(frozen, main)

    def _write_guard(self):
        return self._guard(live=True)

    def _verify_source(self, root):
        self._write_guard()
        require(root == self.local.root, "source verifier root changed")
        current = version.load_version(root / "products/lmdj/version.json")
        assembly_path = root / "products/lmdj/assembly.json"
        assembly = version._verify_assembly(current, assembly_path)
        version._verify_lock(current, assembly_path, assembly,
            root / "products/lmdj/assembly.lock.json", repo_root=root)
        self._write_guard()

    def _source_arguments(self):
        return dict(request=self.request, frozen=self._frozen, main_revision=self._guard(live=True),
            **self.author, timestamp=self.timestamp, verify=self._verify_source)

    def observe(self, *, initialize=False):
        require(type(initialize) is bool, "initialization flag is invalid")
        return self._run(mutate=False, initialize=initialize, before_write=None)

    def prepare(self, *, before_write):
        require(callable(before_write), "final caller guard is required")
        return self._run(mutate=True, initialize=False, before_write=before_write)

    def _run(self, *, mutate, initialize, before_write):
        require(self._active is None, "controller is already running")
        try:
            self._frozen = self.material.inputs.freeze(self.request["base_revision"])
            with RequestJournal(self.root) as journal:
                state = self._state(journal)
                created = state is None
                if state is None:
                    require(not mutate, "must enroll before caller intent")
                    if not initialize:
                        return dict(status="absent", evidence=None)
                    try:
                        self.authorize(deepcopy(self.request))
                    except Exception:
                        # Same-type upstream refusals are private at enrollment
                        # too; the public channel never echoes callback output.
                        raise CandidatePreparationError("why: candidate preparation authority is unavailable; remedy: restore the original trusted grant without exposing callback output or replaying effects") from None
                    journal._active()
                    require(self._state(journal) is None, "enrollment changed during authorization")
                    journal._write(self.MARKER, canonical_json(self.scope))
                    state = dict(schema="lmdj.candidate-preparation.v1", scope=deepcopy(self.scope),
                        setup_started=False, setup=None, source_started=False, source=None,
                        snapshot_started=False, snapshot=None, cut_started=False, cut_timestamp=None, checked_cut=None)
                    journal._write(self.STATE, canonical_json(state))
                self._persisted = deepcopy(state)
                self._active = (journal, state, before_write, mutate)
                try:
                    return self._drive(mutate, initialize_setup=created)
                finally:
                    self._active = None
        except CandidatePreparationError:
            raise
        except Exception:
            raise CandidatePreparationError("why: candidate preparation child evidence or execution is unavailable; remedy: retain the original attempt and inspect its private history without replaying unknown effects or exposing child output") from None

    def _drive(self, mutate, *, initialize_setup):
        state = self._active[1]
        result = lambda status: dict(status=status, evidence=None)
        self._guard()
        setup = self.setup.observe(initialize=initialize_setup)
        if mutate and setup["status"] == "pending":
            state["setup_started"] = True
            self._save()
            setup = self.setup.prepare(before_write=self._write_guard)
        if setup["status"] != "verified":
            return result("unknown" if setup["status"] == "absent" else setup["status"])
        require(state["setup_started"] and same(setup["frozen"], self._frozen), "unowned or changed setup")
        setup_receipt = dict(evidence=setup["evidence"], reservation_sha256=canonical_sha256(setup["reservation"]))
        require(state["setup"] is None or same(state["setup"], setup_receipt), "setup receipt changed")
        if state["setup"] is None:
            state["setup"] = setup_receipt
            self._save()

        if not state["snapshot_started"]:
            observed = self.local.observe_source(**self._source_arguments())
            first = not state["source_started"]
            if first:
                require(observed["status"] == "absent", "source existed before its parent intent")
                if not mutate:
                    return result("pending")
                state["source_started"] = True
                self._save()
            elif observed["status"] == "absent":
                return result("unknown")
            if observed["status"] != "verified":
                if not mutate:
                    return result(observed["status"])
                self.local.prepare_source(**self._source_arguments(), before_write=self._write_guard)
                observed = self.local.observe_source(**self._source_arguments())
            require(observed["status"] == "verified", "source did not verify")
            require(state["source"] is None or same(state["source"], observed["source"]), "source receipt changed")
            if state["source"] is None:
                state["source"] = observed["source"]
                self._save()

        if not state["cut_started"]:
            observed = self.snapshot.observe(self.request, state["source"])
            first = not state["snapshot_started"]
            if first:
                require(observed["status"] == "absent", "snapshot existed before its parent intent")
                if not mutate:
                    return result("pending")
                state["snapshot_started"] = True
                self._save()
            elif observed["status"] == "absent":
                return result("unknown")
            if observed["status"] != "verified":
                if not mutate:
                    return result(observed["status"])
                self.snapshot.run(self.request, state["source"])
                observed = self.snapshot.observe(self.request, state["source"])
            require(observed["status"] == "verified", "snapshot did not verify")
            require(state["snapshot"] is None or same(state["snapshot"], observed["snapshot"]), "snapshot receipt changed")
            if state["snapshot"] is None:
                state["snapshot"] = observed["snapshot"]
                self._save()

        first = not state["cut_started"]
        if first:
            if not mutate:
                return result("pending")
            self._write_guard()
            timestamp = self.clock()
            require(type(timestamp) is int and self.timestamp <= timestamp <= 253402300799, "cut clock is invalid")
            self._write_guard()
            state.update(cut_started=True, cut_timestamp=timestamp)
            self._save()
        arguments = dict(request=self.request, source=state["source"], snapshot_sha256=state["snapshot"]["sha256"],
                         **self.author, timestamp=state["cut_timestamp"])
        observed = self.checks.observe(**arguments, frozen=self._frozen, main_revision=self.request["base_revision"])
        if first:
            require(observed["status"] == "absent", "cut existed before its parent intent")
        if not first and observed["status"] == "absent":
            return result("unknown")
        if observed["status"] != "verified":
            if not mutate or observed["status"] not in ("absent", "pending"):
                return result(observed["status"])
            self._write_guard()
            self.checks.prepare(**arguments)
            observed = self.checks.observe(**arguments, frozen=self._frozen, main_revision=self.request["base_revision"])
        require(observed["status"] == "verified", "cut did not verify")
        require(state["checked_cut"] is None or same(state["checked_cut"], observed["checked_cut"]), "checked cut changed")
        if state["checked_cut"] is None:
            state["checked_cut"] = observed["checked_cut"]
            self._save()
        self._guard()
        return dict(status="verified", source=deepcopy(state["source"]), frozen=deepcopy(self._frozen),
            checked_cut=deepcopy(state["checked_cut"]), evidence=dict(sha256=canonical_sha256(state),
                reference="candidate-preparation:" + canonical_sha256(self.scope)))
