"""Actual staged/committed witness Task checks, not review or release evidence."""
from copy import deepcopy
from pathlib import Path

from .batch_reference import digest, sha
from .candidate_snapshot import read
from .candidate_witness import same
from .candidate_witness_task import CandidateWitnessTask
from .model import canonical_json, canonical_sha256
from .task_verification import PublicationTaskVerifier, _checks, verify_tracked_bytes
from .witness_pr import pr_document, validate_spec


class WitnessChecksError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise WitnessChecksError(f"why: witness Task checks {reason}; remedy: retain the original command history and exact Task, restore its authority and source, and reconcile without replaying failed or unknown commands")


class WitnessTaskChecks:
    STATE = "witness-checks-state.json"
    MARKER = "witness-checks-operation.json"

    def __init__(self, task, *, control_revision, authorize, path):
        require(type(task) is CandidateWitnessTask and sha(control_revision) and callable(authorize),
                "require the concrete Task, control revision and trusted authority")
        self.task, self.control, self.authorize, self.path = task, control_revision, authorize, path
        self.executor = PublicationTaskVerifier(None, task.root, authorize=authorize, path=path)

    def _authorize(self, scope):
        try:
            self.authorize(deepcopy(scope))
        except Exception:
            raise WitnessChecksError("why: witness Task authority is unavailable; remedy: restore the original authorization without exposing callback output or replaying commands") from None

    def _scope(self, binding):
        require(type(binding) is dict and set(binding) == {"schema", "operation_id", "request_sha256",
            "base_revision", "target_revision", "receipt_sha256", "witness", "tree", "commit", "branch"}
            and binding["schema"] == "lmdj.candidate-witness-task.v1"
            and all(sha(binding[k]) for k in ("base_revision", "target_revision", "tree", "commit"))
            and all(digest(binding[k]) for k in ("operation_id", "request_sha256", "receipt_sha256"))
            and binding["operation_id"] == canonical_sha256({"request":binding["request_sha256"], "step":"candidate-witness"})
            and binding["branch"] == "docs/release-witness-" + binding["operation_id"], "Task binding is invalid")
        scope = {"binding":deepcopy(binding), "control_revision":self.control, "path":self.path}
        require(len(canonical_json(scope)) <= 8192, "scope exceeds its read budget")
        return scope

    @staticmethod
    def _commands(scope):
        return [(phase, label, list(vector), timeout) for phase in ("staged", "committed")
                for label, vector, timeout in _checks(scope["binding"])]

    def _save(self, journal, state):
        raw = canonical_json(state)
        require(len(raw) <= 65536, "command history exceeds its read bound")
        journal._write(self.STATE, raw)

    def _state(self, journal, scope, *, initialize=False):
        marker, state = read(journal, self.MARKER, optional=True), read(journal, self.STATE, optional=True)
        if marker is None:
            require(initialize and state is None, "enrollment is missing")
            journal._write(self.MARKER, canonical_json(scope))
            state = {"schema":"lmdj.witness-task-checks.v1", "scope":deepcopy(scope), "commands":[]}
            self._save(journal, state)
        require(same(read(journal, self.MARKER), scope) and type(state) is dict
                and set(state) == {"schema", "scope", "commands"}
                and state["schema"] == "lmdj.witness-task-checks.v1" and same(state["scope"], scope),
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

    def _binding(self, journal, binding):
        journal._active()
        require(same(read(journal, "binding.json"), binding)
                and same(read(journal, "task-operation.json"), binding), "retained Task binding changed")

    def _checkout(self, phase, binding):
        task = self.task
        task._visible_index()
        head = binding["base_revision"] if phase == "staged" else binding["commit"]
        require(task.revision("HEAD") == head
            and task.git("symbolic-ref", "--short", "HEAD").decode().strip() == binding["branch"]
            and task.revision_from_index() == binding["tree"], "Task HEAD, branch or index changed")
        verify_tracked_bytes(task, binding["tree"])
        require(not task.git("ls-files", "--others", "--exclude-standard", "-z"), "untracked Task inputs exist")

    def _receipt(self, state):
        require(len(state["commands"]) == len(self._commands(state["scope"]))
                and all(row["status"] == "verified" and row["result"][0] == 0 for row in state["commands"]),
                "both Task phases are not fully verified")
        return {"sha256":canonical_sha256(state),
                "reference":"witness-task-tests:" + state["scope"]["binding"]["operation_id"]}

    def _run_locked(self, root, phase, binding, *, guard):
        require(root == self.task.root and phase in ("staged", "committed") and callable(guard),
                "verification boundary is invalid")
        journal, source = self.task._journal, self.task.witness.local._journal
        require(journal is not None and source is not None, "both original writers must be held")
        scope = self._scope(binding)

        def checkpoint(state=None):
            source._active()
            self._binding(journal, binding)
            guard()
            self._authorize(scope)
            guard()
            source._active()
            self._binding(journal, binding)
            self._checkout(phase, binding)
            if state is not None:
                require(same(self._state(journal, scope), state), "command history changed under the writer")

        checkpoint()
        require(phase == "staged" or read(journal, self.MARKER, optional=True) is not None,
                "committed Task lacks original staged command history")
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
            # Keep both flock descriptions alive in the real child, including
            # the scratch-Git initializer, if this controller dies first.
            result = self.executor._execute(journal, tuple(vector), timeout, retained_locks=(source.lock,))
            source._active()
            self._binding(journal, binding)
            require(same(self._state(journal, scope), state), "command history disappeared during execution")
            row.update(status="finished", result=list(result))
            self._save(journal, state)
            checkpoint(state)
            require(result[0] == 0, f"{phase} command {label} exited {result[0]}")
            row["status"] = "verified"
            self._save(journal, state)
        checkpoint(state)
        return self._receipt(state) if phase == "committed" else None

    def prepare(self, **arguments):
        """Run the actual Task and both command phases; no push or PR."""
        require("verify" not in arguments and "verify_locked" not in arguments, "caller cannot replace Task commands")
        result = []
        def verify(root, phase, binding, *, guard):
            result.append(self._run_locked(root, phase, binding, guard=guard))
        try:
            task = self.task.prepare(**arguments, verify_locked=verify)
            require(result and result[-1] is not None, "committed command proof is missing")
            return {"task":task, "checks":result[-1]}
        except WitnessChecksError:
            raise
        except Exception:
            raise WitnessChecksError("why: witness Task execution or authority is unavailable; remedy: preserve its exact attempt and inspect the retained result without replaying commands or exposing child output") from None

    def verify(self, spec):
        """Passive command evidence only; original source/review are other gates."""
        try:
            validate_spec(spec)
            binding = {"schema":"lmdj.candidate-witness-task.v1", "operation_id":spec["operation_id"],
                "request_sha256":spec["request_sha256"], "base_revision":spec["base_revision"],
                "target_revision":spec["target_revision"], "receipt_sha256":spec["witness_receipt_sha256"],
                "witness":spec["witness"], "tree":spec["tree_sha"], "commit":spec["head_sha"],
                "branch":pr_document(spec)["head"]}
            require(canonical_sha256(binding) == spec["task_binding_sha256"], "PR Task binding digest changed")
            scope = self._scope(binding)
            gitdir = Path(self.task.git("rev-parse", "--absolute-git-dir").decode().strip())
            with self.task._locked(gitdir) as journal:
                self._binding(journal, binding)
                state = self._state(journal, scope)
                self._authorize(scope)
                self._binding(journal, binding)
                require(same(self._state(journal, scope), state), "command history changed during authorization")
                result = self._receipt(state)
                require(result["sha256"] == spec["task_evidence_sha256"], "PR command evidence digest changed")
                return result
        except WitnessChecksError:
            raise
        except Exception:
            raise WitnessChecksError("why: witness Task command evidence or authority is unavailable; remedy: retain and restore the original private history without inventing a passing receipt") from None
