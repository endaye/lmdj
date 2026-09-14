"""Recoverable internal source commit for the official clean-HEAD snapshot seam.

Not a finished cut Task: snapshot/final commit, reviewed PR, squash and witness
must follow. Never push this intermediate source commit as a completed cut.
"""
from pathlib import Path
import re
import tempfile

from .candidate_material import CandidateBuildMaterial
from .model import canonical_json, canonical_sha256
from .orchestration import validate_request
from .publication_workspace import PublicationWorkspace, PublicationWorkspaceError

FILES = {"products/lmdj/version.json", "products/lmdj/assembly.json",
         "products/lmdj/assembly.lock.json", "products/lmdj/src/compiled_assembly.cpp"}


def require(value, reason):
    if not value:
        raise PublicationWorkspaceError(f"why: candidate source workspace {reason}; remedy: retain the original reservation and dedicated worktree; do not push an incomplete cut or overwrite drift")


class CandidateSourceWorkspace(PublicationWorkspace):
    JOURNAL_NAME = "lmdj-candidate-source-workspace"
    VERIFY_LABEL = "candidate source"

    def __init__(self, root, material):
        super().__init__(root)
        require(type(material) is CandidateBuildMaterial, "requires the concrete material generator")
        self.material = material

    def _visible_index(self):
        effective_root = self.git("rev-parse", "--path-format=absolute", "--show-toplevel").decode().strip()
        require(Path(effective_root).resolve() == self.root,
                "effective Git worktree root differs from the owned directory")
        require(all(row.startswith(b"H ") for row in self.git("ls-files", "-v", "-z").split(b"\0") if row),
                "index hides tracked changes with skip-worktree or assume-unchanged")

    def _check_workspace(self, *args, **kwargs):
        # Index flags are not part of write-tree. Recheck after verification,
        # not only before generation, so a tool cannot conceal its own drift.
        self._visible_index()
        super()._check_workspace(*args, **kwargs)

    def prepare_source(self, **arguments):
        """Commit exact generated source after trusted source-only verification.

        Caller authenticates original authority/control/main/baseline CI before
        every call. verify(root) must validate the material Task, not report
        snapshot/release checks as passed before those artifacts exist.
        """
        return self._source(**arguments, observe=False)

    def observe_source(self, **arguments):
        """Original binding and actual OLD/NEW bytes, without installation.

        Reconstructs immutable Git objects in private indexes, but never enrolls,
        allocates, changes the real index/ref/checkout or invokes a Task command.
        """
        return self._source(**arguments, observe=True)

    def _source(self, *, request, frozen, main_revision, author_name,
                author_email, timestamp, verify, observe, before_write=None):
        from .candidate_snapshot import read
        validate_request(request)
        require(before_write is None or callable(before_write), "write guard is invalid")
        require(request["mode"] == "new", "requires a new-build request")
        require(type(timestamp) is int and 1 <= timestamp <= 253402300799, "timestamp is invalid")
        require(type(author_name) is str and re.fullmatch(r"[A-Za-z0-9 ._-]{1,80}", author_name)
                and type(author_email) is str and re.fullmatch(r"[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+", author_email), "author identity is invalid")
        operation = canonical_sha256({"request":canonical_sha256(request), "step":"candidate"})
        branch = "feat/release-candidate-" + operation
        base = request["base_revision"]
        require(self.git("symbolic-ref", "--short", "HEAD").decode().strip() == branch,
                "branch is not operation-bound")
        gitdir = Path(self.git("rev-parse", "--absolute-git-dir").decode().strip())
        common = Path(self.git("rev-parse", "--path-format=absolute", "--git-common-dir").decode().strip())
        require(gitdir != common and (self.root / ".git").is_file() and not (self.root / ".git").is_symlink(),
                "requires a dedicated linked worktree")
        with self._locked(gitdir) as journal:
            require(self.git("rev-parse", "--is-shallow-repository").strip() == b"false", "history is shallow")
            self._visible_index()
            previous = read(journal, "binding.json", optional=True) if observe else None
            if observe and previous is None:
                return dict(status="absent", source=None)
            generated = (self.material.observe if observe else self.material.prepare)(request, frozen, main_revision)
            require(set(generated["files"]) == FILES, "material inventory is not the four source files")
            # The generator may use another worktree; authenticate this object's
            # base too before constructing any checkout state.
            selected = {}
            entries = {entry["path"]:entry for entry in frozen["entries"]}
            for name in sorted(FILES):
                require(name in entries and entries[name]["mode"] == "100644", "base material mode is invalid")
                oid = self.git("rev-parse", base + ":" + name).decode().strip()
                require(oid == entries[name]["object"], "base object differs from frozen input")
                selected[name] = self.git("cat-file", "blob", oid)
            expected = generated["files"]
            with tempfile.TemporaryDirectory(prefix="lmdj-candidate-source-index-") as directory:
                index = Path(directory) / "index"
                self.git("read-tree", base, index=index)
                for name, raw in sorted(expected.items()):
                    oid = self.git("hash-object", "-w", "--stdin", data=raw).decode().strip()
                    self.git("update-index", "--add", "--cacheinfo", "100644," + oid + "," + name, index=index)
                require(not self.git("check-attr", "--cached", "--all", "--", *sorted(FILES), index=index),
                        "source paths have checkout-transforming attributes")
                tree = self.revision_from_index(index)
                files = {name.decode() for name in self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", base, tree).split(b"\0") if name}
                require(files == FILES, "generated tree changes unexpected paths")
                product_build = generated["binding"]["product_build"]
                message = (f"chore(release): stage {product_build} snapshot source\n\n"
                           f"Release-operation: {operation}\nCandidate-material-sha256: {generated['sha256']}\n")
                identity = f"{author_name} <{author_email}> {timestamp} +0000"
                raw_commit = f"tree {tree}\nparent {base}\nauthor {identity}\ncommitter {identity}\n\n{message}".encode()
                commit = self.git("hash-object", "-t", "commit", "-w", "--stdin", data=raw_commit).decode().strip()
                binding = {"schema":"lmdj.candidate-source-workspace.v1", "operation_id":operation,
                           "request_sha256":canonical_sha256(request), "base_revision":base,
                           "material_sha256":generated["sha256"], "product_build":product_build,
                           "tree":tree, "commit":commit, "branch":branch}
                receipt = dict(binding, files=sorted(files), status="source-committed")
                if observe:
                    require(canonical_json(previous) == canonical_json(binding), "observed source binding changed")
                    require(self.revision("HEAD") in (base, commit), "observed source HEAD changed")
                    self._check_workspace(base, tree, selected, expected)
                    if self.revision("HEAD") == base:
                        return dict(status="pending", source=None)
                    self._check_workspace(base, tree, selected, expected, complete=True)
                    verify(self.root)
                    journal._active()
                    require(canonical_json(read(journal, "binding.json")) == canonical_json(binding), "source history changed during observation")
                    require(self.revision("HEAD") == commit, "source HEAD changed during observation")
                    self._check_workspace(base, tree, selected, expected, complete=True)
                    return dict(status="verified", source=receipt)
                self._binding(journal, binding)
                def guard():
                    before_write()
                    journal._active()
                    require(canonical_json(read(journal, "binding.json")) == canonical_json(binding),
                            "source binding changed during write authorization")
                self._install_commit(journal, base, tree, commit, branch, selected, expected, index, verify,
                                     before_write=guard if before_write is not None else None)
                return receipt
