"""Durable executed cut Task evidence, separate from source/review acceptance."""
from copy import deepcopy
from pathlib import Path

from .batch_reference import digest, sha
from .candidate_cut import CandidateCutWorkspace
from .candidate_pr import pr_document, validate_spec
from .candidate_snapshot import read
from .model import canonical_json, canonical_sha256
from .task_verification import PublicationTaskVerifier, _checks


class CandidateChecksError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise CandidateChecksError(f"why: candidate Task checks {reason}; remedy: retain the original cut and command history, restore its authority and reconcile without replaying failed or unknown commands")


class CandidateTaskChecks:
    STATE = "cut-checks-state.json"
    MARKER = "cut-checks-operation.json"

    def __init__(self, cut, *, control_revision, authorize, path):
        require(type(cut) is CandidateCutWorkspace and sha(control_revision) and callable(authorize),
                "require the concrete cut, control revision and trusted authority")
        self.cut, self.local = cut, cut.local
        self.control, self.authorize, self.path = control_revision, authorize, path
        self.executor = PublicationTaskVerifier(None, self.local.root, authorize=authorize, path=path)

    def _authorize(self, scope):
        try:
            self.authorize(deepcopy(scope))
        except Exception:
            raise CandidateChecksError("why: candidate Task authority is unavailable; remedy: restore original authorization without exposing callback output or replaying commands") from None

    def _scope(self, journal, binding):
        source = read(journal, "binding.json")
        require(type(source) is dict and set(source) == {"schema", "operation_id", "request_sha256",
            "base_revision", "material_sha256", "product_build", "tree", "commit", "branch"}
            and source["schema"] == "lmdj.candidate-source-workspace.v1"
            and all(sha(source[k]) for k in ("base_revision", "tree", "commit"))
            and all(digest(source[k]) for k in ("operation_id", "request_sha256", "material_sha256"))
            and source["operation_id"] == canonical_sha256({"request":source["request_sha256"], "step":"candidate"})
            and source["branch"] == "feat/release-candidate-" + source["operation_id"], "source identity is invalid")
        require(type(binding) is dict and set(binding) == {"schema", "source_sha256", "snapshot_sha256",
            "snapshot_state_sha256", "base_revision", "source_commit", "tree", "commit", "branch", "source_retention_ref"}
            and binding["schema"] == "lmdj.candidate-cut.v1"
            and all(sha(binding[k]) for k in ("base_revision", "source_commit", "tree", "commit"))
            and all(digest(binding[k]) for k in ("source_sha256", "snapshot_sha256", "snapshot_state_sha256"))
            and binding["source_sha256"] == canonical_sha256(source)
            and binding["source_commit"] == source["commit"] and binding["base_revision"] == source["base_revision"]
            and binding["branch"] == source["branch"]
            and binding["source_retention_ref"] == "refs/lmdj/release-sources/" + source["operation_id"], "cut binding is invalid")
        scope = dict(binding=deepcopy(binding), source=source, control_revision=self.control, path=self.path)
        require(len(canonical_json(scope)) <= 8192, "scope exceeds its read budget")
        return scope

    @staticmethod
    def _commands(scope):
        return [(phase, label, list(vector), timeout) for phase in ("staged", "committed")
                for label, vector, timeout in _checks(scope["binding"])]

    def _save(self, journal, state):
        raw = canonical_json(state)
        require(len(raw) <= 65536, "command history exceeds its read budget")
        journal._write(self.STATE, raw)

    def _state(self, journal, scope, *, initialize=False):
        marker, state = read(journal, self.MARKER, optional=True), read(journal, self.STATE, optional=True)
        if marker is None:
            require(initialize and state is None, "enrollment is missing")
            journal._write(self.MARKER, canonical_json(scope))
            state = dict(schema="lmdj.candidate-task-checks.v1", scope=deepcopy(scope), commands=[])
            self._save(journal, state)
        require(read(journal, self.MARKER) == scope and type(state) is dict
                and set(state) == {"schema", "scope", "commands"}
                and state["schema"] == "lmdj.candidate-task-checks.v1" and state["scope"] == scope,
                "enrolled history is missing, corrupt or rebound")
        rows, commands = state["commands"], self._commands(scope)
        require(type(rows) is list and len(rows) <= len(commands), "command inventory changed")
        for index, row in enumerate(rows):
            phase, label, vector, _ = commands[index]
            require(type(row) is dict and set(row) == {"phase", "command", "arguments", "status", "result"}
                    and (row["phase"], row["command"], row["arguments"]) == (phase, label, vector)
                    and row["status"] in ("started", "finished", "verified"), "command identity changed")
            result = row["result"]
            require((row["status"] == "started" and result is None) or (row["status"] != "started"
                and type(result) is list and len(result) == 3 and type(result[0]) is int
                and -255 <= result[0] <= 255 and digest(result[1]) and type(result[2]) is int
                and result[2] >= 0), "command result is invalid")
            require(row["status"] != "verified" or result[0] == 0, "failed command claims verification")
            require(index == len(rows) - 1 or row["status"] == "verified", "command follows an unconfirmed predecessor")
        return state

    def _binding(self, journal, scope):
        journal._active()
        require(read(journal, "cut-binding.json") == scope["binding"]
                and read(journal, "binding.json") == scope["source"], "retained source or cut binding changed")

    def _receipt(self, state):
        require(len(state["commands"]) == len(self._commands(state["scope"]))
                and all(row["status"] == "verified" and row["result"][0] == 0 for row in state["commands"]),
                "both Task phases are not fully verified")
        return dict(sha256=canonical_sha256(state),
                    reference="candidate-task-tests:" + state["scope"]["source"]["operation_id"])

    def _run_locked(self, root, phase, binding, *, guard):
        require(root == self.local.root and phase in ("staged", "committed") and callable(guard)
                and self.local._journal is not None, "verification requires the original cut writer")
        journal = self.local._journal
        scope = self._scope(journal, binding)

        def checkpoint(state=None):
            self._binding(journal, scope)
            guard()
            self._authorize(scope)
            guard()
            self._binding(journal, scope)
            if state is not None:
                require(self._state(journal, scope) == state, "command history changed under the writer")

        checkpoint()
        require(phase == "staged" or read(journal, self.MARKER, optional=True) is not None,
                "committed cut lacks original staged command history")
        state = self._state(journal, scope, initialize=phase == "staged")
        require(all(row["status"] == "verified" for row in state["commands"]),
                "prior command is failed or unknown; automatic replay is forbidden")
        commands = self._commands(scope)
        boundary = len(commands) // 2
        require((phase == "staged" and len(state["commands"]) <= boundary)
                or (phase == "committed" and len(state["commands"]) >= boundary), "phase order changed")
        end = boundary if phase == "staged" else len(commands)
        while len(state["commands"]) < end:
            checkpoint(state)
            selected_phase, label, vector, timeout = commands[len(state["commands"])]
            row = dict(phase=selected_phase, command=label, arguments=vector, status="started", result=None)
            state["commands"].append(row)
            self._save(journal, state)
            checkpoint(state)
            # The concrete executor passes this original writer FD to its child.
            result = self.executor._execute(journal, tuple(vector), timeout)
            self._binding(journal, scope)
            require(self._state(journal, scope) == state, "command history disappeared during execution")
            row.update(status="finished", result=list(result))
            self._save(journal, state)
            checkpoint(state)
            require(result[0] == 0, f"{phase} command {label} exited {result[0]}")
            row["status"] = "verified"
            self._save(journal, state)
        checkpoint(state)
        return self._receipt(state) if phase == "committed" else None

    def prepare(self, **arguments):
        require("verify" not in arguments and "verify_locked" not in arguments, "caller cannot replace Task commands")
        result = []
        def verify(root, phase, binding, *, guard):
            result.append(self._run_locked(root, phase, binding, guard=guard))
        try:
            cut = self.cut.prepare(**arguments, verify_locked=verify)
            require(result and result[-1] is not None, "committed command proof is missing")
            return dict(cut=cut, checks=result[-1])
        except CandidateChecksError:
            raise
        except Exception:
            raise CandidateChecksError("why: candidate Task execution or authority is unavailable; remedy: preserve the exact attempt and inspect its retained result without replay or exposing child output") from None

    def verify(self, spec):
        """Passive command proof only; source, review and main are other gates."""
        try:
            validate_spec(spec)
            gitdir = Path(self.local.git("rev-parse", "--absolute-git-dir").decode().strip())
            with self.local._locked(gitdir) as journal:
                binding = read(journal, "cut-binding.json")
                scope = self._scope(journal, binding)
                source = scope["source"]
                require(all(spec[k] == source[k] for k in ("operation_id", "request_sha256", "product_build"))
                    and spec["source_sha"] == source["commit"]
                    and spec["base_revision"] == binding["base_revision"] and spec["head_sha"] == binding["commit"]
                    and spec["tree_sha"] == binding["tree"] and pr_document(spec)["head"] == binding["branch"]
                    and spec["snapshot_sha256"] == binding["snapshot_sha256"]
                    and spec["cut_binding_sha256"] == canonical_sha256(binding), "PR cut identity changed")
                self._binding(journal, scope)
                state = self._state(journal, scope)
                self._authorize(scope)
                self._binding(journal, scope)
                require(self._state(journal, scope) == state, "command history changed during authorization")
                result = self._receipt(state)
                require(result["sha256"] == spec["task_evidence_sha256"], "PR command evidence digest changed")
                return result
        except CandidateChecksError:
            raise
        except Exception:
            raise CandidateChecksError("why: candidate Task command evidence or authority is unavailable; remedy: restore original private history without inventing a passing receipt") from None
