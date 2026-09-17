"""Passive cut/squash object proof; not Task review, main authority or release CI.

The trusted parent authenticates live main and the original frozen request.
This consumer uses the actual private snapshot/cut bindings, not a PR label.
Private indexes may add trees; no checkout, ref update, fetch or remote write.
"""
from hashlib import sha256
from contextlib import nullcontext
from pathlib import Path
import tempfile

from .batch_reference import sha
from .candidate_cut import CandidateCutWorkspace
from .candidate_inputs import CandidateInputs
from .candidate_snapshot import read
from .candidate_workspace import FILES
from .model import canonical_sha256


class CandidateSourceError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise CandidateSourceError(f"why: candidate source {reason}; remedy: retain the original candidate and exact main history; reconcile drift without selecting another target or bypassing review")


class CandidateSourceVerifier:
    def __init__(self, cut):
        require(type(cut) is CandidateCutWorkspace, "requires the concrete cut workspace")
        self.cut, self.local = cut, cut.local
        self.inputs = CandidateInputs(self.local.root)

    def _commit(self, revision):
        require(sha(revision), "revision is invalid")
        require(self.local.git("cat-file", "-t", revision).strip() == b"commit", "object is not a commit")
        require(int(self.local.git("cat-file", "-s", revision)) <= 65536, "commit is oversized")
        headers = self.local.git("cat-file", "commit", revision).split(b"\n\n", 1)[0].split(b"\n")
        trees = [row[5:].decode() for row in headers if row.startswith(b"tree ")]
        parents = [row[7:].decode() for row in headers if row.startswith(b"parent ")]
        require(len(trees) == 1 and sha(trees[0]) and all(sha(p) for p in parents), "commit headers are invalid")
        return trees[0], parents

    def verify(self, *, request, source, cut, frozen, main_revision, merge_revision=None):
        try:
            return self._verify(request, source, cut, frozen, main_revision, merge_revision)
        except CandidateSourceError:
            raise
        except Exception:
            raise CandidateSourceError("why: candidate source binding, objects or input projection are unavailable; remedy: retain the original request and restore exact history; do not fetch or invent a successful proof") from None

    def verify_locked(self, journal, *, request, source, cut, frozen, main_revision, merge_revision):
        """Use only this workspace's active writer, held by its caller."""
        try:
            require(journal is not None and journal is self.local._journal,
                    "supplied journal is not the active source writer")
            journal._active()
            return self._verify(request, source, cut, frozen, main_revision, merge_revision, journal)
        except CandidateSourceError:
            raise
        except Exception:
            raise CandidateSourceError("why: candidate source locked proof is unavailable; remedy: retain the original workspace and restore its writer and exact history") from None

    def _verify(self, request, source, cut, frozen, main, merged, held_journal=None):
        local = self.local
        gitdir = Path(local.git("rev-parse", "--absolute-git-dir").decode().strip())
        with (local._locked(gitdir) if held_journal is None else nullcontext(held_journal)) as journal:
            state = self.cut.snapshot.verified_state(journal, request, source, cut["snapshot_sha256"])
            installed = state["scope"]["source"]
            binding = read(journal, "cut-binding.json")
            require(type(cut) is dict and cut == dict(binding, product_build=installed["product_build"],
                status="cut-committed", files=cut.get("files")), "receipt differs from durable cut binding")
            require(binding["source_sha256"] == canonical_sha256(installed)
                    and binding["snapshot_state_sha256"] == canonical_sha256(state)
                    and binding["source_commit"] == installed["commit"]
                    and binding["base_revision"] == installed["base_revision"]
                    and binding["branch"] == installed["branch"], "source binding changed")
            require(frozen["base_revision"] == binding["base_revision"], "frozen request baseline changed")
            source_tree, source_parents = self._commit(installed["commit"])
            tree, parents = self._commit(binding["commit"])
            require(source_tree == installed["tree"] and source_parents == [binding["base_revision"]]
                    and tree == binding["tree"] and parents == [binding["base_revision"]],
                    "source or cut is not one commit on the original baseline")
            require(local.revision(binding["source_retention_ref"]) == installed["commit"], "source retention is missing")
            # Reconstruct the exact cut using the durable snapshot's raw bytes.
            inventory = state["snapshot"]
            names = [entry["path"] for entry in inventory]
            require(len(names) == len(set(names)) and cut["files"] == sorted(FILES | set(names)),
                    "cut file inventory changed")
            changed = local.git("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", parents[0], binding["commit"])
            require(sorted(name.decode() for name in changed.split(b"\0") if name) == cut["files"],
                    "cut diff changed")
            entries = {}
            for name in cut["files"]:
                row = local.git("ls-tree", "-z", tree, "--", name)
                parts = row.split(b"\t", 1)
                require(len(parts) == 2 and parts[1] == name.encode() + b"\0", "cut path is missing or ambiguous")
                mode, kind, oid = parts[0].decode().split(" ")
                require(mode == "100644" and kind == "blob" and sha(oid), "cut path is not a regular blob")
                entries[name] = oid
            with tempfile.TemporaryDirectory(prefix="lmdj-candidate-source-") as directory:
                index = Path(directory) / "index"
                local.git("read-tree", source_tree, index=index)
                for entry in inventory:
                    name = entry["path"]
                    require(int(local.git("cat-file", "-s", entries[name])) == entry["bytes"], "snapshot length changed")
                    raw = local.git("cat-file", "blob", entries[name])
                    require(sha256(raw).hexdigest() == entry["sha256"], "snapshot bytes changed")
                    local.git("update-index", "--add", "--cacheinfo", "100644," + entries[name] + "," + name, index=index)
                require(local.revision_from_index(index) == tree, "cut differs from installed source plus snapshot")
                self._commit(main)
                if merged is None:
                    self.inputs.verify(frozen, main)
                    merge_tree = merge_parent = None
                else:
                    merge_tree, merge_parents = self._commit(merged)
                    require(len(merge_parents) == 1 and merged != binding["commit"], "result is not a distinct squash")
                    merge_parent = merge_parents[0]
                    self.inputs.verify(frozen, merge_parent)
                    local.git("merge-base", "--is-ancestor", merged, main)
                    local.git("read-tree", merge_parent, index=index)
                    for name, oid in entries.items():
                        local.git("update-index", "--add", "--cacheinfo", "100644," + oid + "," + name, index=index)
                    require(local.revision_from_index(index) == merge_tree, "squash tree differs from the exact candidate on its actual parent")
            self.cut.snapshot._authorize(state["scope"])
            return {"schema":"lmdj.candidate-source-proof.v1", "cut_sha":binding["commit"],
                    "cut_binding_sha256":canonical_sha256(binding), "base_revision":binding["base_revision"],
                    "snapshot_sha256":binding["snapshot_sha256"], "observed_main":main,
                    "merge_sha":merged, "merge_parent":merge_parent, "merge_tree":merge_tree}
