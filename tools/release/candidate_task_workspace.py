"""Owned witness worktree and one durable dependency installation.

The source writer outlives every Git/install child. A cold observer may recover
an exact worktree creation, but never repeat a started dependency installation.
Task checks and actual merged-source verification remain separate consumers.
"""
from copy import deepcopy
import os
from pathlib import Path

from .batch_reference import digest, sha
from .candidate_snapshot import read
from .candidate_witness import same
from .candidate_witness_task import CandidateWitnessTask
from .model import canonical_json, canonical_sha256
from .orchestration import RequestJournal
from .task_verification import PublicationTaskVerifier, verify_tracked_bytes


class CandidateTaskWorkspaceError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise CandidateTaskWorkspaceError(f"why: candidate Task workspace {reason}; remedy: retain the original owned worktree and installation history; restore authority and reconcile without overwriting a path or replaying an unknown or failed install")


class CandidateTaskWorkspace:
    STATE = "candidate-task-workspace.json"
    MARKER = "candidate-task-workspace-operation.json"
    INSTALL = ("bash", "scripts/docs-site.sh", "install")

    def __init__(self, root, task, *, authorize, control_revision, path):
        require(type(task) is CandidateWitnessTask and callable(authorize) and sha(control_revision),
                "requires the concrete Task and trusted control authority")
        self.root, self.task = Path(root).absolute(), task
        require(self.root.resolve() == self.root, "journal path contains a symlink")
        self.authorize, self.control, self.path = authorize, control_revision, path
        self.executor = PublicationTaskVerifier(None, task.root, authorize=authorize, path=path)

    def _scope(self, inputs, receipt, base):
        require(sha(base), "base is not an exact revision")
        operation = canonical_sha256({"request":canonical_sha256(inputs["request"]), "step":"candidate-witness"})
        value = dict(inputs_sha256=canonical_sha256(inputs), receipt_sha256=canonical_sha256(receipt),
            base_revision=base, branch="docs/release-witness-" + operation, worktree=str(self.task.root),
            source_worktree=str(self.task.witness.local.root), control_revision=self.control, path=self.path)
        require(len(canonical_json(value)) <= 8192, "scope exceeds its read bound")
        return value

    def _save(self, journal, state):
        raw = canonical_json(state)
        require(len(raw) <= 16384, "state exceeds its read bound")
        journal._write(self.STATE, raw)

    def _state(self, journal, scope, initialize):
        marker, state = read(journal, self.MARKER, optional=True), read(journal, self.STATE, optional=True)
        if marker is None:
            require(state is None, "state exists without enrollment")
            if not initialize:
                return None
            journal._write(self.MARKER, canonical_json(scope))
            state = dict(schema="lmdj.candidate-task-workspace.v1", scope=deepcopy(scope),
                         create_intent=False, created=False, gitdir=None, install=None)
            self._save(journal, state)
        require(same(read(journal, self.MARKER), scope) and type(state) is dict
                and set(state) == {"schema", "scope", "create_intent", "created", "gitdir", "install"}
                and state["schema"] == "lmdj.candidate-task-workspace.v1" and same(state["scope"], scope)
                and type(state["create_intent"]) is bool and type(state["created"]) is bool,
                "enrolled state is missing, corrupt or rebound")
        require((state["created"] and state["create_intent"] and type(state["gitdir"]) is str
                 and Path(state["gitdir"]).is_absolute())
                or (not state["created"] and state["gitdir"] is None), "creation receipt is invalid")
        install = state["install"]
        if install is not None:
            require(state["created"] and type(install) is dict
                and set(install) == {"arguments", "status", "result"}
                and install["arguments"] == list(self.INSTALL)
                and install["status"] in ("started", "finished", "verified"), "installation identity is invalid")
            result = install["result"]
            require((install["status"] == "started" and result is None)
                or (install["status"] != "started" and type(result) is list and len(result) == 3
                    and type(result[0]) is int and -255 <= result[0] <= 255 and digest(result[1])
                    and type(result[2]) is int and result[2] >= 0), "installation result is invalid")
            require(install["status"] != "verified" or result[0] == 0, "failed installation claims verification")
        return state

    def _identity(self, scope, *, pristine):
        task, source = self.task, self.task.witness.local
        require(task.root.resolve() == task.root and (task.root / ".git").is_file()
                and not (task.root / ".git").is_symlink(), "destination is not a real linked worktree")
        gitdir = Path(task.git("rev-parse", "--absolute-git-dir").decode().strip())
        common = source.git("rev-parse", "--path-format=absolute", "--git-common-dir").strip()
        require(task.git("rev-parse", "--path-format=absolute", "--git-common-dir").strip() == common
                and os.fsencode(gitdir) != common
                and task.git("symbolic-ref", "--short", "HEAD").decode().strip() == scope["branch"],
                "worktree repository or branch differs from the operation")
        require(b"worktree " + os.fsencode(task.root) in source.git("worktree", "list", "--porcelain", "-z").split(b"\0"),
                "destination is not registered in the original repository")
        if pristine:
            task._visible_index()
            tree = task.revision(scope["base_revision"] + "^{tree}")
            require(task.revision("HEAD") == scope["base_revision"] and task.revision_from_index() == tree,
                    "destination is not the original pristine base")
            verify_tracked_bytes(task, tree)
            require(not task.git("ls-files", "--others", "--exclude-standard", "-z"), "untracked inputs exist")
        return str(gitdir)

    def _absent(self, scope):
        source = self.task.witness.local
        require(not os.path.lexists(self.task.root), "destination already exists before owned creation")
        require(not source.git("for-each-ref", "--format=%(refname)", "refs/heads/" + scope["branch"]),
                "operation branch already exists before owned creation")
        require(b"worktree " + os.fsencode(self.task.root) not in source.git("worktree", "list", "--porcelain", "-z").split(b"\0"),
                "destination was already registered before owned creation")

    def observe(self, *, receipt, base_revision, **inputs):
        return self._run(receipt, base_revision, inputs, mutate=False, before_write=None)

    def prepare(self, *, receipt, base_revision, before_write, **inputs):
        require(callable(before_write), "final parent guard is missing")
        return self._run(receipt, base_revision, inputs, mutate=True, before_write=before_write)

    def _run(self, receipt, base, inputs, *, mutate, before_write):
        try:
            receipt, inputs = deepcopy(receipt), deepcopy(inputs)
            scope = self._scope(inputs, receipt, base)
            with RequestJournal(self.root) as journal:
                # Every observation and reconciliation acquires the original
                # source lock before inspecting effects of its old child.
                with self.task.witness.verified_artifact(receipt, **inputs) as (_, _, source_guard):
                    def guard(state=None):
                        journal._active()
                        source_guard()
                        try:
                            self.authorize(deepcopy(scope))
                            if mutate:
                                before_write()
                        except Exception:
                            raise CandidateTaskWorkspaceError("why: candidate Task workspace original parent authority is unavailable; remedy: restore the original grant and writer without exposing callback output or retrying an unknown installation") from None
                        main = source_guard()
                        journal._active()
                        if state is not None:
                            require(same(self._state(journal, scope, False), state), "history changed during authority check")
                        self.task.witness.local.git("merge-base", "--is-ancestor", inputs["merge_revision"], base)
                        self.task.witness.local.git("merge-base", "--is-ancestor", base, main)
                        # No callback follows the final history check. In
                        # particular a late main/source observer must not make
                        # a missing child state look safe to save or accept.
                        journal._active()
                        if state is not None:
                            require(same(self._state(journal, scope, False), state), "history changed after final source check")

                    guard()
                    state = self._state(journal, scope, mutate)
                    if state is None:
                        return dict(status="absent", evidence=None)
                    guard(state)
                    if not state["create_intent"]:
                        self._absent(scope)
                        if not mutate:
                            return dict(status="pending", evidence=None)
                        state["create_intent"] = True
                        self._save(journal, state)
                        guard(state)
                        self._absent(scope)
                        # No hook/filter execution; original source FD is
                        # inherited by the concrete Git child, including if
                        # this controller exits before checkout completes.
                        self.task.witness.local.git("-c", "core.symlinks=true", "worktree", "add",
                            "--no-track", "-b", scope["branch"], str(self.task.root), base)
                    if not state["created"]:
                        if not os.path.lexists(self.task.root):
                            return dict(status="unknown", evidence=None)
                        actual = self._identity(scope, pristine=True)
                        guard(state)
                        require(self._identity(scope, pristine=True) == actual, "creation changed during verification")
                        state.update(created=True, gitdir=actual)
                        self._save(journal, state)
                    require(self._identity(scope, pristine=False) == state["gitdir"], "owned git directory changed")
                    install = state["install"]
                    if install is not None:
                        guard(state)
                        if install["status"] != "verified":
                            return dict(status="unknown" if install["status"] == "started" else "conflict", evidence=None)
                        return dict(status="verified", evidence=dict(sha256=canonical_sha256(state),
                            reference="candidate-task-workspace:" + canonical_sha256(scope)))
                    if not mutate:
                        return dict(status="pending", evidence=None)
                    with self.task._locked(Path(state["gitdir"])) as task_journal:
                        self._identity(scope, pristine=True)
                        guard(state)
                        install = dict(arguments=list(self.INSTALL), status="started", result=None)
                        state["install"] = install
                        self._save(journal, state)
                        guard(state)
                        task_journal._active()
                        self._identity(scope, pristine=True)
                        result = self.executor._execute(task_journal, self.INSTALL, 900,
                            retained_locks=(journal.lock, self.task.witness.local._journal.lock))
                        journal._active()
                        require(same(self._state(journal, scope, False), state), "installation history changed during execution")
                        install.update(status="finished", result=list(result))
                        self._save(journal, state)
                        guard(state)
                        task_journal._active()
                        self._identity(scope, pristine=True)
                        require(result[0] == 0, f"dependency installation exited {result[0]}")
                        install["status"] = "verified"
                        self._save(journal, state)
                        guard(state)
                        task_journal._active()
                        self._identity(scope, pristine=True)
                        return dict(status="verified", evidence=dict(sha256=canonical_sha256(state),
                            reference="candidate-task-workspace:" + canonical_sha256(scope)))
        except CandidateTaskWorkspaceError:
            raise
        except Exception:
            raise CandidateTaskWorkspaceError("why: candidate Task workspace observation or execution is unavailable; remedy: retain the original creation and command history, restore exact evidence, and never expose child output or retry an unknown installation") from None
