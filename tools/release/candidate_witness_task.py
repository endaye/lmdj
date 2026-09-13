"""Exact official witness bytes -> recoverable independent Task commit.

No generation, push or PR. Trusted verification must execute both Task phases;
the parent still owns live review, protected squash and candidate completion.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re
import tempfile

from .batch_reference import sha
from .candidate_snapshot import read
from .candidate_witness import CandidateWitnessRun, same
from .candidate_workspace import CandidateSourceWorkspace
from .model import canonical_json, canonical_sha256
from .publication_workspace import PublicationWorkspace


class WitnessTaskError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise WitnessTaskError(f"why: witness Task {reason}; remedy: retain the original source, command history and dedicated Task worktree; reconcile without regenerating witness or overwriting drift")


class CandidateWitnessTask(PublicationWorkspace):
    JOURNAL_NAME = "lmdj-candidate-witness-task"
    VERIFY_LABEL = "candidate witness"
    _visible_index = CandidateSourceWorkspace._visible_index

    def __init__(self, root, witness):
        super().__init__(root)
        require(type(witness) is CandidateWitnessRun, "requires the concrete witness runner")
        require(self.root != witness.local.root, "source and destination must be distinct")
        self.witness = witness

    def _file(self, name):
        # The official witness permits 64 MiB; do not silently narrow it to the
        # publication workspace's general evidence-file limit of 8 MiB.
        result = CandidateWitnessRun._read_artifact(self.root, name, optional=True, capture=True)
        return None if result is None else result[1]

    def _check_workspace(self, *args, **kwargs):
        self._visible_index()
        return super()._check_workspace(*args, **kwargs)

    def prepare(self, *, receipt, base_revision, request, source, cut, frozen,
                merge_revision, author_name, author_email, timestamp, verify):
        try:
            return self._prepare(receipt=deepcopy(receipt), base=base_revision,
                inputs=deepcopy(dict(request=request, source=source, cut=cut, frozen=frozen,
                                     merge_revision=merge_revision)),
                author_name=author_name, author_email=author_email, timestamp=timestamp, verify=verify)
        except WitnessTaskError:
            raise
        except Exception:
            raise WitnessTaskError("why: witness Task source, state or verification is unavailable; remedy: inspect retained evidence and restore the same operation without exposing child output or inventing a passing Task") from None

    def _prepare(self, *, receipt, base, inputs, author_name, author_email, timestamp, verify):
        require(sha(base) and callable(verify), "base or trusted Task verifier is invalid")
        require(type(timestamp) is int and 1 <= timestamp <= 253402300799, "timestamp is invalid")
        require(type(author_name) is str and re.fullmatch(r"[A-Za-z0-9 ._-]{1,80}", author_name)
                and type(author_email) is str and re.fullmatch(r"[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+", author_email), "author is invalid")
        request_sha = canonical_sha256(inputs["request"])
        operation = canonical_sha256({"request":request_sha, "step":"candidate-witness"})
        branch = "docs/release-witness-" + operation
        require(self.git("symbolic-ref", "--short", "HEAD").decode().strip() == branch, "branch is not operation-bound")
        gitdir = Path(self.git("rev-parse", "--absolute-git-dir").decode().strip())
        common = Path(self.git("rev-parse", "--path-format=absolute", "--git-common-dir").decode().strip())
        require(gitdir != common and (self.root / ".git").is_file() and not (self.root / ".git").is_symlink(),
                "requires a dedicated linked worktree")
        require(self.git("rev-parse", "--is-shallow-repository").strip() == b"false", "history is shallow")
        # Always source writer first, destination writer second. The payload is
        # captured from an already-confirmed actual command, never reconstructed.
        with self.witness.verified_artifact(receipt, **inputs) as (emitted, raw, source_guard):
            with self._locked(gitdir) as journal:
                enrolled = None
                def check_enrollment():
                    if enrolled is not None:
                        require(same(read(journal, "task-operation.json"), enrolled)
                                and same(read(journal, "binding.json"), enrolled),
                                "binding changed at the write boundary")

                def guard():
                    journal._active()
                    check_enrollment()
                    main = source_guard()
                    check_enrollment()
                    self.witness.local.git("merge-base", "--is-ancestor", base, main)
                    self.git("merge-base", "--is-ancestor", emitted["introducing_revision"], base)
                    journal._active()

                guard()
                name = emitted["witness"]["path"]
                require(not self.git("ls-tree", "-z", base, "--", name),
                        "base already contains a witness; observe its existing Task instead")
                # Every immutable snapshot path must survive main advancement.
                # versions.json may add later versions and is validated by the
                # complete Portal Task check, not frozen to the cut's list.
                snapshot = read(self.witness.local._journal, "snapshot-state.json")["state"]["snapshot"]
                for entry in snapshot:
                    filename = entry["path"]
                    if filename == "apps/architecture-portal/versions.json":
                        continue
                    row = self.git("ls-tree", "-z", base, "--", filename)
                    require(row.startswith(b"100644 blob ") and row.endswith(b"\t" + filename.encode() + b"\0"),
                            "base snapshot path or mode changed")
                    blob = self.git("cat-file", "blob", base + ":" + filename)
                    require(len(blob) == entry["bytes"] and sha256(blob).hexdigest() == entry["sha256"],
                            "base immutable snapshot bytes changed")
                self._file(name)  # Reject unsafe existing files/parents before enrollment.
                with tempfile.TemporaryDirectory(prefix="lmdj-witness-task-index-") as directory:
                    index = Path(directory) / "index"
                    self.git("read-tree", base, index=index)
                    oid = self.git("hash-object", "-w", "--stdin", data=raw).decode().strip()
                    self.git("update-index", "--add", "--cacheinfo", "100644," + oid + "," + name, index=index)
                    require(not self.git("check-attr", "--cached", "--all", "--", name, index=index),
                            "witness path has checkout-transforming attributes")
                    tree = self.revision_from_index(index)
                    require(self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", base, tree) == name.encode() + b"\0",
                            "Task changes more than the canonical witness")
                    identity = f"{author_name} <{author_email}> {timestamp} +0000"
                    message = (f"docs(release): record {emitted['product_build']} squash witness\n\n"
                               f"Release-operation: {operation}\nCandidate-target: {emitted['introducing_revision']}\n"
                               f"Witness-sha256: {emitted['witness']['sha256']}\n")
                    commit = self.git("hash-object", "-t", "commit", "-w", "--stdin",
                        data=f"tree {tree}\nparent {base}\nauthor {identity}\ncommitter {identity}\n\n{message}".encode()).decode().strip()
                    binding = {"schema":"lmdj.candidate-witness-task.v1", "operation_id":operation,
                        "request_sha256":request_sha, "base_revision":base, "target_revision":emitted["introducing_revision"],
                        "receipt_sha256":canonical_sha256(receipt), "witness":emitted["witness"],
                        "tree":tree, "commit":commit, "branch":branch}
                    require(self.revision("HEAD") in (base, commit), "HEAD is outside the bound Task")
                    self._check_workspace(base, tree, {}, {name:raw})
                    marker = read(journal, "task-operation.json", optional=True)
                    previous = read(journal, "binding.json", optional=True)
                    pending = read(journal, "binding.pending", optional=True)
                    guard()
                    if marker is None:
                        require(previous is None and pending is None, "binding exists without enrollment")
                        journal._write("task-operation.json", canonical_json(binding))
                    else:
                        require(same(marker, binding) and (previous is not None or pending is not None),
                                "enrollment changed or binding disappeared")
                    self._binding(journal, binding)
                    enrolled = deepcopy(binding)

                    def verify_phase(root):
                        guard()
                        require(same(read(journal, "task-operation.json"), binding)
                                and same(read(journal, "binding.json"), binding), "binding changed at verification boundary")
                        phase = "staged" if self.revision("HEAD") == base else "committed"
                        verify(root, phase, deepcopy(binding))
                        guard()
                        require(same(read(journal, "task-operation.json"), binding)
                                and same(read(journal, "binding.json"), binding), "binding changed during verification")

                    already_committed = self.revision("HEAD") == commit
                    guard()
                    self._install_commit(journal, base, tree, commit, branch, {}, {name:raw}, index, verify_phase)
                    if not already_committed:
                        verify_phase(self.root)
                    guard()
                    self._check_workspace(base, tree, {}, {name:raw}, complete=True)
                    require(self.revision("HEAD") == commit
                            and self.git("symbolic-ref", "--short", "HEAD").decode().strip() == branch,
                            "HEAD or branch changed after committed verification")
                    return dict(binding, status="witness-committed", files=[name])
