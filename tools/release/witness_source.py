"""Passive witness Task/squash proof from actual retained producer evidence.

Not original request authorization, Task-command proof, review or release CI.
No command generation, fetch, checkout, ref or staged-entry mutation is performed.
Existing source guards may refresh Git's index cache via write-tree.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile

from .candidate_snapshot import read
from .candidate_source import CandidateSourceVerifier
from .candidate_witness import same
from .candidate_witness_task import CandidateWitnessTask
from .model import canonical_sha256
from .task_verification import verify_tracked_bytes
from .witness_pr import pr_document, validate_spec


class WitnessSourceError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise WitnessSourceError(f"why: witness source {reason}; remedy: retain the original candidate, Task and command history; reconcile exact objects and bindings without regenerating witness or accepting an API merge alone")


class CandidateWitnessSourceVerifier:
    _commit = CandidateSourceVerifier._commit

    def __init__(self, task):
        require(type(task) is CandidateWitnessTask, "requires the concrete witness Task")
        self.task = self.local = task
        self.git = task.git

    def _ancestor(self, before, after):
        self.git("merge-base", "--is-ancestor", before, after)

    def _blob(self, revision, fact):
        name = fact["path"]
        row = self.git("ls-tree", "-z", revision, "--", name)
        require(row.startswith(b"100644 blob ") and row.endswith(b"\t" + name.encode() + b"\0"),
                "artifact is missing or its committed mode changed")
        oid = row.split(b"\t", 1)[0].split(b" ")[2].decode()
        require(int(self.git("cat-file", "-s", oid)) == fact["bytes"], "artifact byte length changed")
        raw = self.git("cat-file", "blob", oid)
        require(len(raw) == fact["bytes"] and sha256(raw).hexdigest() == fact["sha256"],
                "artifact bytes changed")
        return oid

    def _expected_tree(self, parent, witness, raw):
        require(not self.git("ls-tree", "-z", parent, "--", witness["path"]),
                "parent already contains a witness; this is not its introducing Task")
        with tempfile.TemporaryDirectory(prefix="lmdj-witness-source-") as directory:
            index = Path(directory) / "index"
            self.git("read-tree", parent, index=index)
            oid = self.git("hash-object", "-w", "--stdin", data=raw).decode().strip()
            self.git("update-index", "--add", "--cacheinfo", "100644," + oid + "," + witness["path"], index=index)
            return self.task.revision_from_index(index)

    def _unchanged_history(self, introducing, main, names):
        # Same all-history/parent comparison as the official Portal verifier:
        # a merge matching a parent is not itself a new immutable edit, while
        # an edit followed by a revert must still be rejected.
        rows = self.git("log", "--full-history", "--format=%H", introducing + ".." + main, "--", *names)
        for revision in rows.decode().splitlines():
            _, parents = self._commit(revision)
            require(any(not self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "-z",
                                     parent, revision, "--", *names) for parent in parents),
                    "immutable artifact history changed after introduction")

    def _snapshot(self, revision, entries, build):
        for entry in entries:
            if entry["path"] != "apps/architecture-portal/versions.json":
                self._blob(revision, entry)
        name = "apps/architecture-portal/versions.json"
        row = self.git("ls-tree", "-z", revision, "--", name)
        require(row.startswith(b"100644 blob ") and row.endswith(b"\t" + name.encode() + b"\0"),
                "version index is missing or not regular")
        require(int(self.git("cat-file", "-s", revision + ":" + name)) <= 64 * 1024 * 1024,
                "version index exceeds its bound")
        versions = json.loads(self.git("cat-file", "blob", revision + ":" + name))
        require(type(versions) is list and all(type(v) is str for v in versions)
                and len(versions) == len(set(versions)) and versions.count(build) == 1,
                "candidate is missing or duplicated in version index")

    def verify(self, spec, *, receipt, request, source, cut, frozen, main_revision, merge_revision=None):
        try:
            validate_spec(spec)
            return self._verify(deepcopy(spec), deepcopy(receipt), deepcopy(dict(request=request,
                source=source, cut=cut, frozen=frozen, merge_revision=spec["target_revision"])),
                main_revision, merge_revision)
        except WitnessSourceError:
            raise
        except Exception:
            raise WitnessSourceError("why: witness source objects, private bindings or original authority are unavailable; remedy: restore the original evidence and retry observation of the same candidate; never fetch on miss or invent a passing proof") from None

    def _verify(self, spec, receipt, inputs, main, merged):
        task = self.task
        self._commit(main)
        require(self.git("rev-parse", "--is-shallow-repository").strip() == b"false", "history is shallow")
        require(spec["request_sha256"] == canonical_sha256(inputs["request"])
                and spec["source_sha"] == inputs["source"]["commit"]
                and spec["product_build"] == inputs["source"]["product_build"]
                and spec["witness_receipt_sha256"] == canonical_sha256(receipt), "request or receipt identity changed")
        gitdir = Path(self.git("rev-parse", "--absolute-git-dir").decode().strip())
        common = Path(self.git("rev-parse", "--path-format=absolute", "--git-common-dir").decode().strip())
        require(gitdir != common and (task.root / ".git").is_file() and not (task.root / ".git").is_symlink(),
                "Task is not a dedicated linked worktree")
        with task.witness.verified_artifact(receipt, **inputs) as (emitted, raw, source_guard):
            with task._locked(gitdir) as journal:
                witness = emitted["witness"]
                require(same(witness, spec["witness"]), "spec artifact differs from the official receipt")
                expected = {"schema":"lmdj.candidate-witness-task.v1", "operation_id":spec["operation_id"],
                    "request_sha256":spec["request_sha256"], "base_revision":spec["base_revision"],
                    "target_revision":spec["target_revision"], "receipt_sha256":spec["witness_receipt_sha256"],
                    "witness":witness, "tree":spec["tree_sha"], "commit":spec["head_sha"],
                    "branch":pr_document(spec)["head"]}

                def task_guard():
                    journal._active()
                    require(same(read(journal, "task-operation.json"), expected)
                            and same(read(journal, "binding.json"), expected)
                            and canonical_sha256(expected) == spec["task_binding_sha256"], "Task binding changed")
                    require(task.revision("HEAD") == spec["head_sha"]
                            and self.git("symbolic-ref", "--short", "HEAD").decode().strip() == expected["branch"],
                            "retained Task HEAD or branch changed")
                    task._visible_index()
                    require(not self.git("diff-index", "--cached", "--no-ext-diff", "--no-textconv", "--no-renames",
                                         "--raw", "-z", spec["head_sha"]), "retained Task index changed")
                    verify_tracked_bytes(task, spec["head_sha"])
                    require(task._file(witness["path"]) == raw, "retained witness bytes changed")
                    require(not self.git("ls-files", "--others", "--exclude-standard", "-z"), "untracked Task inputs exist")

                def guard():
                    task_guard()
                    observed = source_guard()
                    task_guard()  # A trusted callback may still lose local state.
                    require(observed == main, "main observation changed; re-observe the same candidate")

                guard()
                self._ancestor(spec["target_revision"], spec["base_revision"])
                self._ancestor(spec["base_revision"], main)
                tree, parents = self._commit(spec["head_sha"])
                require(parents == [spec["base_revision"]] and tree == spec["tree_sha"], "Task commit identity changed")
                require(tree == self._expected_tree(spec["base_revision"], witness, raw), "Task is not base plus only the exact witness")
                self._blob(spec["head_sha"], witness)
                snapshot = read(task.witness.local._journal, "snapshot-state.json")["state"]["snapshot"]
                self._snapshot(spec["base_revision"], snapshot, spec["product_build"])
                self._snapshot(main, snapshot, spec["product_build"])
                immutable = [entry["path"] for entry in snapshot if entry["path"] != "apps/architecture-portal/versions.json"]
                self._unchanged_history(spec["target_revision"], main, immutable)
                merge_parent = merge_tree = None
                if merged is not None:
                    merge_tree, merge_parents = self._commit(merged)
                    require(len(merge_parents) == 1 and merged not in
                            (spec["head_sha"], spec["target_revision"], spec["source_sha"]), "result is not a distinct witness squash")
                    merge_parent = merge_parents[0]
                    self._ancestor(spec["base_revision"], merge_parent)
                    self._ancestor(merged, main)
                    require(merge_tree == self._expected_tree(merge_parent, witness, raw),
                            "squash differs from its actual parent plus the exact witness")
                    self._blob(merged, witness)
                    self._blob(main, witness)
                    self._unchanged_history(merged, main, [witness["path"]])
                guard()
                return {"schema":"lmdj.witness-pr-source.v1", "operation_id":spec["operation_id"],
                    "request_sha256":spec["request_sha256"], "target_revision":spec["target_revision"],
                    "head_sha":spec["head_sha"], "tree_sha":tree, "base_revision":spec["base_revision"],
                    "task_binding_sha256":spec["task_binding_sha256"], "witness":witness,
                    "witness_receipt_sha256":spec["witness_receipt_sha256"], "observed_main":main,
                    "merge_sha":merged, "merge_parent":merge_parent, "merge_tree":merge_tree}
