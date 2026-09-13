"""Durable branch -> PR subjourney. A merged PR is not candidate completion.

Trusted release parent initializes via observe before its own intent, then uses
advance only under that intent. Production authority/source/review/reservation
gates are mandatory on the concrete children; witness is a subsequent leg.
"""
from copy import deepcopy
import json
import os
from pathlib import Path

from .candidate_branch import CandidateBranch
from .candidate_pr import CandidatePullRequest, pr_document, validate_spec
from .model import canonical_json
from .orchestration import RequestJournal

MAX_STATE_BYTES = 65536


class CandidateSequenceError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise CandidateSequenceError(f"why: candidate PR sequence {reason}; remedy: restore the original parent and child journals; do not recreate missing operation state or repeat unknown writes")


class CandidatePrSequence:
    _validate_spec = staticmethod(validate_spec)
    _document = staticmethod(pr_document)
    _branch_type, _pr_type = CandidateBranch, CandidatePullRequest
    _state_file = "candidate-pr-sequence.json"
    _schema = "lmdj.candidate-pr-sequence.v1"

    def __init__(self, root, *, branch, pr):
        require(type(branch) is self._branch_type and type(pr) is self._pr_type,
                "requires the concrete candidate children")
        self.root, self.branch, self.pr = Path(root).absolute(), branch, pr
        self._children()

    def _children(self):
        require(self.root.resolve() == self.root
                and Path(self.branch.root).absolute() == self.root / "branch"
                and Path(self.pr.root).absolute() == self.root / "pr", "child paths are not bound to this parent")

    @staticmethod
    def _enrollment(journal, *, create=False):
        journal._active()
        if create:
            try:
                fd = os.open("sequence-enrolled", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=journal.directory)
            except FileExistsError:
                raise CandidateSequenceError("why: enrolled sequence state is missing; remedy: restore the original state; never re-enroll an existing operation") from None
            try:
                os.fsync(fd)
                os.fsync(journal.directory)
            finally:
                os.close(fd)
        else:
            try:
                fd = os.open("sequence-enrolled", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=journal.directory)
            except FileNotFoundError:
                raise CandidateSequenceError("why: sequence enrollment marker is missing; remedy: reconcile the original private enrollment without replacing state") from None
            try:
                journal._private(fd)
                require(os.fstat(fd).st_size == 0, "enrollment marker is corrupt")
            finally:
                os.close(fd)

    @classmethod
    def _read(cls, journal, spec):
        journal._active()
        try:
            fd = os.open(cls._state_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=journal.directory)
        except FileNotFoundError:
            return None
        try:
            journal._private(fd)
            cls._enrollment(journal)
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_STATE_BYTES + 1)
            state = json.loads(raw)
            require(len(raw) <= MAX_STATE_BYTES and canonical_json(state) == raw and type(state) is dict
                    and set(state) == {"schema", "spec", "phase"}
                    and state["schema"] == cls._schema
                    and canonical_json(state["spec"]) == canonical_json(spec)
                    and state["phase"] in ("initializing", "branch", "pr-initializing", "pr"), "state is invalid or rebound")
            return state
        finally:
            os.close(fd)

    @classmethod
    def _save(cls, journal, state, phase):
        updated = dict(state, phase=phase)
        encoded = canonical_json(updated)
        require(len(encoded) <= MAX_STATE_BYTES, "state exceeds its read bound")
        journal._write(cls._state_file, encoded)
        state["phase"] = phase

    def observe(self, spec, *, initialize=False):
        require(type(initialize) is bool, "initialization mode is invalid")
        return self._run(spec, initialize=initialize, mutate=False)

    def advance(self, spec, *, before_write):
        require(callable(before_write), "final parent guard is unavailable")
        return self._run(spec, initialize=False, mutate=True, before_write=before_write)

    def _run(self, spec, *, initialize, mutate, before_write=None):
        self._validate_spec(spec)
        spec = deepcopy(spec)
        self._document(spec)  # Validate before enrolling any parent or child state.
        self._children()
        with RequestJournal(self.root) as journal:
            try:
                state = self._read(journal, spec)
                if state is None:
                    if not initialize:
                        return {"status":"unknown", "phase":None, "evidence":None}
                    self._enrollment(journal, create=True)
                    state = {"schema":self._schema, "spec":spec, "phase":"initializing"}
                    self._save(journal, state, "initializing")

                def guard():
                    journal._active()
                    self._children()
                    require(self._read(journal, spec) == state, "parent state changed at write boundary")
                    before_write()
                    journal._active()
                    self._children()
                    require(self._read(journal, spec) == state, "parent state changed during authority check")

                def child(controller, method, **kwargs):
                    journal._active()
                    self._children()
                    result = getattr(controller, method)(spec, **kwargs)
                    journal._active()
                    self._children()
                    return result

                def pending(result):
                    return {"status":result["status"], "phase":state["phase"], "evidence":None}

                if state["phase"] == "initializing":
                    result = child(self.branch, "observe", initialize=True)
                    if result["status"] not in ("absent", "verified"):
                        return pending(result)
                    self._save(journal, state, "branch")
                if state["phase"] == "branch":
                    result = child(self.branch, "observe")
                    if mutate and result["status"] == "absent":
                        child(self.branch, "advance", require_initialized=True, before_write=guard)
                        result = child(self.branch, "observe")
                    if result["status"] != "verified":
                        return pending(result)
                    self._save(journal, state, "pr-initializing")
                if state["phase"] == "pr-initializing":
                    result = child(self.pr, "observe", initialize=True)
                    if result["status"] not in ("absent", "pending", "verified"):
                        return pending(result)
                    self._save(journal, state, "pr")
                result = child(self.pr, "observe")
                if mutate and result["status"] in ("absent", "pending"):
                    child(self.pr, "advance", require_initialized=True, before_write=guard)
                    result = child(self.pr, "observe")
                if result["status"] == "verified":
                    return {"status":"merged", "phase":"pr", "evidence":result["evidence"]}
                return pending(result)
            except CandidateSequenceError:
                raise
            except Exception:
                # Preserve raw private state; never serialize provider/auth errors.
                return {"status":"unknown", "phase":None, "evidence":None}
