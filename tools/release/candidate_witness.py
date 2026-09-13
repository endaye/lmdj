"""Durable local witness production; not witness PR or release acceptance."""
from base64 import b64decode, b64encode
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import stat

from .batch_reference import digest, sha
from .candidate_source import CandidateSourceVerifier
from .candidate_snapshot import read
from .dispatch_receipt import unique
from .model import canonical_json, canonical_sha256
from .orchestration import validate_request
from .task_verification import PublicationTaskVerifier, verify_tracked_bytes


class CandidateWitnessError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise CandidateWitnessError(f"why: candidate witness {reason}; remedy: retain the original source, witness and command history; reconcile without replaying generation or inventing verification")


def same(left, right):
    return canonical_json(left) == canonical_json(right)


class CandidateWitnessRun:
    def __init__(self, verifier, *, authorize, observe_main, path, verification_limit=3):
        require(type(verifier) is CandidateSourceVerifier, "requires the concrete source verifier")
        require(callable(authorize) and callable(observe_main), "trusted authority and main observers are required")
        require(type(verification_limit) is int and 1 <= verification_limit <= 3, "verification budget is invalid")
        self.verifier, self.local = verifier, verifier.local
        self.authorize, self.observe_main = authorize, observe_main
        self.path, self.limit = path, verification_limit
        self.executor = PublicationTaskVerifier(None, self.local.root, authorize=authorize, path=path)

    def _scope(self, inputs):
        validate_request(inputs["request"])
        require(sha(inputs["merge_revision"]), "introducing revision is invalid")
        return {"request":inputs["request"], "source_sha256":canonical_sha256(inputs["source"]),
                "cut_sha256":canonical_sha256(inputs["cut"]), "frozen_sha256":canonical_sha256(inputs["frozen"]),
                "merge_revision":inputs["merge_revision"], "product_build":inputs["source"]["product_build"],
                "path":self.path, "verification_limit":self.limit}

    @staticmethod
    def _names(scope):
        build = scope["product_build"]
        return (f"apps/architecture-portal/versioned_metadata/version-{build}.json",
                f"apps/architecture-portal/versioned_provenance/version-{build}-squash-witness.json")

    def _check_scope_budget(self, scope):
        # Include repeated argument vectors and maximum base64 output, not
        # just scope size. The fixed envelope/result fields fit within 2 KiB.
        required = (len(canonical_json(scope)) + len(canonical_json(self._vector(scope, True)))
                    + self.limit * (len(canonical_json(self._vector(scope, False))) + 4 * ((8192 + 2) // 3))
                    + 2048)
        require(required <= 65536, "scope exceeds its durable command-history budget")

    def _artifact(self, name, *, optional=False):
        filename = self.local.root / name
        for parent in filename.parents:
            if parent == self.local.root:
                break
            require(parent.is_dir() and not parent.is_symlink(), "artifact parent is unsafe")
        try:
            fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            require(optional, "artifact is missing")
            return None
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and not before.st_mode & 0o111
                    and before.st_nlink == 1 and before.st_size <= 64 * 1024 * 1024,
                    "artifact is not a bounded single-link regular file")
            hasher, length = sha256(), 0
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                length += len(chunk)
                require(length <= 64 * 1024 * 1024, "artifact exceeded its byte bound")
                hasher.update(chunk)
            after, current = os.fstat(fd), filename.lstat()
            identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            require(identity(before) == identity(after) == identity(current) and length == before.st_size,
                    "artifact changed during reading")
            return {"path":name, "bytes":length, "sha256":hasher.hexdigest()}
        finally:
            os.close(fd)

    @staticmethod
    def _bindings(journal):
        return {name:read(journal, name) for name in ("binding.json", "cut-binding.json",
                "snapshot-operation.json", "snapshot-state.json")}

    def _guard(self, journal, scope, inputs, proof=None):
        # Callbacks are trusted control code, but their errors are never logs.
        try:
            self.authorize(deepcopy(scope))
            main = self.observe_main()
        except Exception:
            require(False, "original authority or main observation is unavailable")
        journal._active()
        bindings = self._bindings(journal)
        if proof is None:
            # Reconstruct the complete immutable Git proof once per acquired
            # writer, never from a persisted cache. No command has run yet.
            verified = self.verifier.verify_locked(journal, **inputs, main_revision=main)
            proof = {"verified":verified, "bindings":bindings}
        else:
            require(same(bindings, proof["bindings"]), "source evidence changed under the writer")
            self.verifier.cut.snapshot._authorize(bindings["snapshot-state.json"]["state"]["scope"])
            # The pinned source/cut/squash objects and original bindings cannot
            # change within this writer. Check their live identity/presence,
            # fresh main ancestry and ALL mutable checkout facts each time;
            # do not repeatedly rebuild their identical private-index trees.
            source, cut, verified = inputs["source"], inputs["cut"], proof["verified"]
            for revision, tree, parent in ((source["commit"], source["tree"], source["base_revision"]),
                    (cut["commit"], cut["tree"], cut["base_revision"]),
                    (inputs["merge_revision"], verified["merge_tree"], verified["merge_parent"])):
                require(self.verifier._commit(revision) == (tree, [parent]), "pinned source object changed")
            self.verifier._commit(main)
            self.local.git("merge-base", "--is-ancestor", inputs["merge_revision"], main)
        require(same(self._bindings(journal), proof["bindings"]), "source evidence changed under the writer")
        local, cut = self.local, inputs["cut"]
        local._visible_index()
        require(local.git("symbolic-ref", "--short", "HEAD").decode().strip() == cut["branch"]
                and local.revision("HEAD") == cut["commit"]
                and local.revision_from_index() == cut["tree"], "cut HEAD, branch or index changed")
        verify_tracked_bytes(local, cut["commit"])
        other = {os.fsdecode(p) for p in local.git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0") if p}
        require(other <= {self._names(scope)[1]}, "unrelated untracked files exist")
        require(local.revision(cut["source_retention_ref"]) == inputs["source"]["commit"], "source retention changed")
        journal._active()
        return proof

    @staticmethod
    def _save(journal, state):
        raw = canonical_json({"state":state, "sha256":canonical_sha256(state)})
        require(len(raw) <= 65536, "state exceeds its read bound")
        journal._write("witness-state.json", raw)

    @staticmethod
    def _vector(scope, generation):
        return ["bash", "scripts/docs-site.sh", "witness" if generation else "verify-witness",
                scope["product_build"], scope["merge_revision"]]

    def _state(self, journal, scope):
        marker = read(journal, "witness-operation.json", optional=True)
        envelope = read(journal, "witness-state.json", optional=True)
        if marker is None:
            require(envelope is None, "state exists without enrollment")
            return None
        require(same(marker, scope) and type(envelope) is dict and set(envelope) == {"state", "sha256"},
                "enrollment changed or state disappeared")
        state = envelope["state"]
        require(type(state) is dict and set(state) == {"schema", "scope", "generate", "commands", "confirmed"}
                and state["schema"] == "lmdj.candidate-witness-run.v1" and same(state["scope"], scope)
                and canonical_sha256(state) == envelope["sha256"] and type(state["generate"]) is bool,
                "state schema, scope or digest changed")
        rows = state["commands"]
        require(type(rows) is list and 1 <= len(rows) <= self.limit + int(state["generate"]), "command inventory is invalid")
        for index, row in enumerate(rows):
            generation = state["generate"] and index == 0
            require(type(row) is dict and set(row) == {"arguments", "result", "output"}
                    and row["arguments"] == self._vector(scope, generation), "command identity changed")
            result = row["result"]
            require(result is None or (type(result) is list and len(result) == 3
                    and type(result[0]) is int and -255 <= result[0] <= 255 and digest(result[1])
                    and type(result[2]) is int and result[2] >= 0), "command result is invalid")
            output = row["output"]
            require(output is None or (not generation and result is not None and result[0] == 0
                    and type(output) is str), "output is not a successful verifier result")
            if output is not None:
                self._decode(row)
        confirmed = state["confirmed"]
        require(type(confirmed) is int and 0 <= confirmed <= len(rows)
                and (confirmed == 0 or (confirmed > int(state["generate"])
                    and rows[confirmed - 1]["output"] is not None)), "confirmation boundary is invalid")
        return state

    @staticmethod
    def _decode(row):
        raw = b64decode(row["output"], validate=True)
        require(len(raw) <= 8192 and b64encode(raw).decode() == row["output"]
                and row["result"] == [0, sha256(raw).hexdigest(), len(raw)], "emitted output binding changed")
        value = json.loads(raw, object_pairs_hook=unique)
        require(type(value) is dict and set(value) == {"schema", "status", "product_build",
                "source_revision", "introducing_revision", "source_tree", "metadata", "witness"}
                and value["schema"] == "lmdj.snapshot-witness-check.v1"
                and value["status"] == "verified-by-retained-source"
                and type(value["product_build"]) is str
                and all(sha(value[key]) for key in ("source_revision", "introducing_revision", "source_tree")),
                "emitted receipt schema is invalid")
        for key in ("metadata", "witness"):
            entry = value[key]
            require(type(entry) is dict and set(entry) == {"path", "bytes", "sha256"}
                    and type(entry["path"]) is str and type(entry["bytes"]) is int
                    and 0 <= entry["bytes"] <= 64 * 1024 * 1024 and digest(entry["sha256"]),
                    "emitted artifact identity is invalid")
        return value

    def _expected(self, scope, inputs):
        metadata, witness = self._names(scope)
        return {"schema":"lmdj.snapshot-witness-check.v1", "status":"verified-by-retained-source",
                "product_build":scope["product_build"], "source_revision":inputs["source"]["commit"],
                "introducing_revision":scope["merge_revision"], "source_tree":inputs["source"]["tree"],
                "metadata":self._artifact(metadata), "witness":self._artifact(witness)}

    def _command(self, journal, state, inputs, proof, *, generation):
        scope = state["scope"]
        self._guard(journal, scope, inputs, proof)
        if not state["commands"]:
            require(same(read(journal, "witness-operation.json"), scope)
                    and read(journal, "witness-state.json", optional=True) is None,
                    "first command enrollment changed")
        else:
            require(same(self._state(journal, scope), state), "state changed before command intent")
        row = {"arguments":self._vector(scope, generation), "result":None, "output":None}
        state["commands"].append(row)
        self._save(journal, state)
        self._guard(journal, scope, inputs, proof)
        require(same(self._state(journal, scope), state), "state changed before child execution")
        if generation:
            result, raw = self.executor._execute(journal, tuple(row["arguments"]), 900), None
        else:
            result, raw = self.executor._execute_capture(journal, tuple(row["arguments"]), 900, limit=8192)
        row["result"] = list(result)
        # Keep actual command evidence before any post-command gate. Arbitrary
        # failure text is hashed only; success bytes are admitted below.
        self._save(journal, state)
        self._guard(journal, scope, inputs, proof)
        require(same(self._state(journal, scope), state), "state changed after child execution")
        require(result[0] == 0, f"{row['arguments'][2]} exited {result[0]}")
        if not generation:
            require(raw is not None, "verifier output exceeded its bound")
            candidate = dict(row, output=b64encode(raw).decode())
            require(same(self._decode(candidate), self._expected(scope, inputs)), "emitted receipt differs from actual candidate artifacts")
            if state["confirmed"]:
                require(same(self._decode(state["commands"][state["confirmed"] - 1]), self._decode(candidate)),
                        "previously confirmed artifact identity changed")
            row["output"] = candidate["output"]
            state["confirmed"] = len(state["commands"])
            self._save(journal, state)

    def run(self, *, request, source, cut, frozen, merge_revision):
        try:
            inputs = deepcopy(dict(request=request, source=source, cut=cut, frozen=frozen, merge_revision=merge_revision))
            scope = self._scope(inputs)
            self._check_scope_budget(scope)
            gitdir = Path(self.local.git("rev-parse", "--absolute-git-dir").decode().strip())
            with self.local._locked(gitdir) as journal:
                proof = self._guard(journal, scope, inputs)
                state = self._state(journal, scope)
                if state is None:
                    generate = self._artifact(self._names(scope)[1], optional=True) is None
                    journal._write("witness-operation.json", canonical_json(scope))
                    state = {"schema":"lmdj.candidate-witness-run.v1", "scope":scope,
                             "generate":generate, "commands":[], "confirmed":0}
                    # Marker precedes the first state/intent. A crash in this
                    # gap is unknown; it may never enroll a fresh generation.
                    if generate:
                        self._command(journal, state, inputs, proof, generation=True)
                elif state["confirmed"]:
                    require(same(self._decode(state["commands"][state["confirmed"] - 1]), self._expected(scope, inputs)),
                            "previously confirmed artifact identity changed")
                require(len(state["commands"]) - int(state["generate"]) < self.limit, "verification budget exhausted")
                self._command(journal, state, inputs, proof, generation=False)
                return {"status":"witness-verified", "receipt":self._decode(state["commands"][-1]),
                        "command_history_sha256":canonical_sha256(state)}
        except CandidateWitnessError:
            raise
        except Exception:
            raise CandidateWitnessError("why: candidate witness state, source proof or execution is unavailable; remedy: retain the original attempt and reconcile without replaying generation or exposing child output") from None
