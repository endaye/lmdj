"""Owned original source checkout and one durable official dependency install.

The request/authority and shared catalogue are provisioned by the trusted caller.
This does not generate source, snapshots, a cut, a PR or a released identity.
"""
from copy import deepcopy
import os
from pathlib import Path

from .batch_reference import digest, sha
from .candidate_snapshot import read
from .candidate_workspace import CandidateSourceWorkspace
from .model import canonical_json, canonical_sha256
from .orchestration import RequestJournal, validate_request
from .publication_workspace import PublicationWorkspace
from .task_verification import PublicationTaskVerifier, verify_tracked_bytes


class CandidateSourceSetupError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise CandidateSourceSetupError(f"why: candidate source setup {reason}; remedy: restore the original request, catalogue and owned checkout; reconcile retained effects without recreating enrollment, replacing user files or replaying an unknown installation")


def same(left, right):
    return canonical_json(left) == canonical_json(right)


class CandidateSourceSetup:
    STATE = "source-setup.json"
    MARKER = "source-setup-operation.json"
    INSTALL = ("bash", "scripts/docs-site.sh", "install")

    def __init__(self, root, workspace, *, repository_root, request, authorize, observe_main, path):
        require(type(workspace) is CandidateSourceWorkspace and callable(authorize)
                and callable(observe_main), "concrete source and trusted authority are required")
        validate_request(request)
        require(request["mode"] == "new", "requires the original new-version request")
        self.root, self.workspace = Path(root).absolute(), workspace
        require(self.root.resolve() == self.root, "private state path contains symlinks")
        self.repository = PublicationWorkspace(repository_root)
        self.material = workspace.material
        require(self.material.inputs.git.__self__.root == self.repository.root
                and self.material.reservations.inputs.git.__self__.root == self.repository.root,
                "material and reservation repositories differ")
        self.request, self.authorize = deepcopy(request), authorize
        self.observe_main, self.path = observe_main, path
        self.executor = PublicationTaskVerifier(None, workspace.root, authorize=authorize, path=path)

    def _scope(self, frozen):
        operation = canonical_sha256({"request":canonical_sha256(self.request), "step":"candidate"})
        scope = dict(request=self.request, frozen_sha256=canonical_sha256(frozen),
            repository_root=str(self.repository.root), worktree=str(self.workspace.root),
            reservation_root=str(self.material.reservations.state_root.absolute()),
            common_gitdir=self.repository.git("rev-parse", "--path-format=absolute", "--git-common-dir").decode().strip(),
            branch="feat/release-candidate-" + operation, path=self.path)
        require(len(canonical_json(scope)) <= 8192, "scope exceeds its read bound")
        return scope

    def _save(self, journal, state):
        raw = canonical_json(state)
        require(len(raw) <= 32768, "state exceeds its read bound")
        journal._write(self.STATE, raw)

    def _state(self, journal, scope):
        marker, state = read(journal, self.MARKER, optional=True), read(journal, self.STATE, optional=True)
        if marker is None:
            require(state is None, "state exists without original enrollment")
            return None
        require(same(marker, scope) and type(state) is dict and set(state) ==
            {"schema", "scope", "reservation_started", "reservation", "create_intent", "gitdir", "install"}
            and state["schema"] == "lmdj.candidate-source-setup.v1" and same(state["scope"], scope)
            and type(state["reservation_started"]) is bool and type(state["create_intent"]) is bool,
            "enrolled history is missing, corrupt or rebound")
        require((state["reservation"] is None or (state["reservation_started"] and type(state["reservation"]) is dict))
            and (not state["create_intent"] or state["reservation"] is not None)
            and (state["gitdir"] is None or (state["create_intent"] and type(state["gitdir"]) is str
                and Path(state["gitdir"]).is_absolute())), "effect ordering or creation receipt is invalid")
        install = state["install"]
        if install is not None:
            require(state["gitdir"] is not None and type(install) is dict
                and set(install) == {"arguments", "status", "result"}
                and install["arguments"] == list(self.INSTALL)
                and install["status"] in ("started", "finished", "verified"), "installation identity changed")
            result = install["result"]
            require((install["status"] == "started" and result is None)
                or (install["status"] != "started" and type(result) is list and len(result) == 3
                    and type(result[0]) is int and -255 <= result[0] <= 255 and digest(result[1])
                    and type(result[2]) is int and result[2] >= 0), "command result is invalid")
            require(install["status"] != "verified" or result[0] == 0, "failed install claims success")
        return state

    def _absent(self, scope):
        require(not os.path.lexists(self.workspace.root), "destination already exists before owned creation")
        require(not self.repository.git("for-each-ref", "--format=%(refname)", "refs/heads/" + scope["branch"]),
                "operation branch already exists before owned creation")
        require(b"worktree " + os.fsencode(self.workspace.root) not in
                self.repository.git("worktree", "list", "--porcelain", "-z").split(b"\0"),
                "destination is already registered")

    def _identity(self, scope, *, pristine):
        local = self.workspace
        require(local.root.resolve() == local.root and (local.root / ".git").is_file()
                and not (local.root / ".git").is_symlink(), "destination is not a real linked worktree")
        gitdir = local.git("rev-parse", "--absolute-git-dir").decode().strip()
        require(local.git("rev-parse", "--path-format=absolute", "--git-common-dir").decode().strip() == scope["common_gitdir"]
            and gitdir != scope["common_gitdir"]
            and local.git("symbolic-ref", "--short", "HEAD").decode().strip() == scope["branch"]
            and b"worktree " + os.fsencode(local.root) in
                self.repository.git("worktree", "list", "--porcelain", "-z").split(b"\0"),
            "owned repository, branch or registration changed")
        if pristine:
            local._visible_index()
            base = self.request["base_revision"]
            require(local.revision("HEAD") == base and local.revision_from_index() == local.revision(base + "^{tree}"),
                    "checkout is not the original pristine base")
            verify_tracked_bytes(local, base)
            require(not local.git("ls-files", "--others", "--exclude-standard", "-z"), "untracked inputs exist")
        return gitdir

    def observe(self, *, initialize=False):
        require(type(initialize) is bool, "initialization mode is invalid")
        return self._run(mutate=False, initialize=initialize, before_write=None)

    def prepare(self, *, before_write):
        require(callable(before_write), "final parent guard is required")
        return self._run(mutate=True, initialize=False, before_write=before_write)

    def _run(self, *, mutate, initialize, before_write):
        try:
            # Recreate only a passive projection of immutable original Git
            # objects; never select a new baseline or reset its reservation.
            frozen = self.material.inputs.freeze(self.request["base_revision"])
            scope = self._scope(frozen)
            result = lambda status: dict(status=status, evidence=None)
            with RequestJournal(self.root) as journal:
                require(self.repository._journal is None, "repository writer is already active")
                # Git creation retains the parent's original writer descriptor.
                self.repository._journal = journal
                try:
                    def guard(expected, *, live_inputs=False):
                        journal._active()
                        require(same(self._state(journal, scope), expected), "history changed before authority check")
                        try:
                            self.authorize(deepcopy(self.request))
                            if before_write is not None:
                                before_write()
                            main = self.observe_main()
                        except Exception:
                            raise CandidateSourceSetupError("why: candidate source setup authority or main is unavailable; remedy: restore the original trusted grant and observer without exposing callback output or replaying effects") from None
                        require(sha(main), "main observation is not an exact commit")
                        self.repository.git("merge-base", "--is-ancestor", self.request["base_revision"], main)
                        if live_inputs:
                            self.material.inputs.verify(frozen, main)
                        if expected is not None and expected["reservation"] is not None:
                            # The last trusted callback may have removed or
                            # rebound catalogue storage. Re-read actual original
                            # reservation evidence before effects or success,
                            # not the dict cached before that callback.
                            actual = self.material.reservations.observe(self.request, frozen,
                                main if live_inputs else self.request["base_revision"])
                            require(same(actual, expected["reservation"]), "original reservation changed during authority check")
                        journal._active()
                        require(same(self._state(journal, scope), expected), "history changed during authority check")
                        return main

                    state = self._state(journal, scope)
                    guard(state)
                    if state is None:
                        if not initialize:
                            require(not mutate, "setup must be enrolled before parent intent")
                            return result("absent")
                        self._absent(scope)
                        guard(None, live_inputs=True)
                        self._absent(scope)
                        journal._write(self.MARKER, canonical_json(scope))
                        state = dict(schema="lmdj.candidate-source-setup.v1", scope=deepcopy(scope),
                            reservation_started=False, reservation=None, create_intent=False, gitdir=None, install=None)
                        self._save(journal, state)
                    guard(state)
                    # A verified setup is a historical installation receipt;
                    # later source/cut consumers separately verify their bytes.
                    # New effects must additionally recheck live input parity.
                    main = guard(state, live_inputs=state["install"] is None)
                    observation_base = self.request["base_revision"] if state["install"] is not None else main
                    reservation = self.material.reservations.observe(self.request, frozen, observation_base)
                    guard(state)
                    if state["reservation"] is not None:
                        require(same(reservation, state["reservation"]), "original reservation disappeared or changed")
                    elif reservation is None:
                        if state["reservation_started"]:
                            return result("unknown")
                        if not mutate:
                            return result("pending")
                        state["reservation_started"] = True
                        self._save(journal, state)
                        main = guard(state, live_inputs=True)
                        reservation = self.material.reservations.reserve(self.request, frozen, main)
                        guard(state)
                        require(same(self.material.reservations.observe(self.request, frozen, main), reservation),
                                "reservation far side differs")
                    if state["reservation"] is None:
                        require(state["reservation_started"], "unowned reservation cannot be adopted")
                        state["reservation"] = reservation
                        self._save(journal, state)
                    if not state["create_intent"]:
                        self._absent(scope)
                        if not mutate:
                            return result("pending")
                        guard(state, live_inputs=True)
                        state["create_intent"] = True
                        self._save(journal, state)
                        guard(state, live_inputs=True)
                        self._absent(scope)
                        self.repository.git("-c", "core.symlinks=true", "worktree", "add", "--no-track", "-b",
                            scope["branch"], str(self.workspace.root), self.request["base_revision"])
                    if not os.path.lexists(self.workspace.root):
                        return result("unknown")
                    gitdir = self._identity(scope, pristine=False)
                    with self.workspace._locked(Path(gitdir)) as source_journal:
                        if state["gitdir"] is None:
                            self._identity(scope, pristine=True)
                            guard(state, live_inputs=True)
                            require(self._identity(scope, pristine=True) == gitdir, "creation changed during verification")
                            state["gitdir"] = gitdir
                            self._save(journal, state)
                        require(gitdir == state["gitdir"], "owned Git directory changed")
                        install = state["install"]
                        if install is None:
                            if not mutate:
                                return result("pending")
                            guard(state, live_inputs=True)
                            self._identity(scope, pristine=True)
                            install = dict(arguments=list(self.INSTALL), status="started", result=None)
                            state["install"] = install
                            self._save(journal, state)
                            guard(state, live_inputs=True)
                            source_journal._active()
                            self._identity(scope, pristine=True)
                            executed = self.executor._execute(source_journal, self.INSTALL, 900,
                                retained_locks=(journal.lock,))
                            require(same(self._state(journal, scope), state), "history changed during installation")
                            install.update(status="finished", result=list(executed))
                            self._save(journal, state)
                            guard(state, live_inputs=True)
                            self._identity(scope, pristine=True)
                            require(executed[0] == 0, f"installation exited {executed[0]}")
                            install["status"] = "verified"
                            self._save(journal, state)
                        guard(state)
                        source_journal._active()
                        require(self._identity(scope, pristine=False) == gitdir, "final owned identity changed")
                        if install["status"] != "verified":
                            return result("unknown" if install["status"] == "started" else "conflict")
                        return dict(status="verified", frozen=deepcopy(frozen), reservation=deepcopy(reservation),
                            evidence=dict(sha256=canonical_sha256(state), reference="candidate-source-setup:" + canonical_sha256(scope)))
                finally:
                    self.repository._journal = None
        except CandidateSourceSetupError:
            raise
        except Exception:
            raise CandidateSourceSetupError("why: candidate source setup state or execution is unavailable; remedy: restore the original catalogue, writer and checkout without repeating an unknown effect or exposing child output") from None
