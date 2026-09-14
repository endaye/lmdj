"""Recoverable one-commit candidate cut from installed source and verified snapshot.

No generation, push, PR, squash or release. Trusted Task verification runs before
and after the guarded ref update; the parent still owns the remote transitions.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import tempfile

from .candidate_snapshot import CandidateSnapshotRun, read
from .candidate_workspace import FILES
from .model import canonical_json, canonical_sha256
from .task_verification import verify_tracked_bytes


class CandidateCutError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise CandidateCutError(f"why: candidate cut {reason}; remedy: retain the source object, snapshot and dedicated worktree; reconcile the original cut without overwriting drift or bypassing Task verification")


class CandidateCutWorkspace:
    def __init__(self, snapshot):
        require(type(snapshot) is CandidateSnapshotRun, "requires the concrete snapshot executor")
        self.snapshot, self.local = snapshot, snapshot.workspace

    @staticmethod
    def commit_bytes(source, tree, snapshot_sha256, author_name, author_email, timestamp):
        identity = f"{author_name} <{author_email}> {timestamp} +0000"
        message = (f"chore(release): allocate {source['product_build']} candidate\n\nRelease-operation: {source['operation_id']}\n"
                   f"Candidate-source: {source['commit']}\nSnapshot-sha256: {snapshot_sha256}\n")
        return f"tree {tree}\nparent {source['base_revision']}\nauthor {identity}\ncommitter {identity}\n\n{message}".encode()

    def _check(self, source, tree, commit, *, staged):
        local = self.local
        local._visible_index()
        require(local.git("symbolic-ref", "--short", "HEAD").decode().strip() == source["branch"], "branch changed")
        require(local.revision("HEAD") in (source["commit"], commit), "HEAD advanced outside this cut")
        allowed = (tree,) if staged else (source["tree"], tree)
        require(local.revision_from_index() in allowed, "index contains unrelated edits")
        # All output files already exist from the snapshot step. Do not use Git
        # clean-filter output as a substitute for the raw final-tree bytes.
        verify_tracked_bytes(local, tree)
        tree_paths = {row.decode() for row in local.git("ls-tree", "--name-only", "-r", "-z", tree).split(b"\0") if row}
        untracked = {row.decode() for row in local.git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0") if row}
        require(untracked <= tree_paths, "unrelated untracked files are present")

    @staticmethod
    def _verify(verify, verify_locked, root, phase, binding, guard):
        guard()
        try:
            if verify_locked is None:
                verify(root, phase, deepcopy(binding))
            else:
                verify_locked(root, phase, deepcopy(binding), guard=guard)
        except Exception:
            raise CandidateCutError("why: candidate cut Task verification failed; remedy: inspect the retained staged or committed candidate and resume the same cut without bypassing checks") from None
        guard()

    def prepare(self, *, request, source, snapshot_sha256, author_name, author_email, timestamp,
                verify=None, verify_locked=None):
        try:
            return self._prepare(request=request, source=source, snapshot_sha256=snapshot_sha256,
                author_name=author_name, author_email=author_email, timestamp=timestamp,
                verify=verify, verify_locked=verify_locked)
        except CandidateCutError:
            raise
        except Exception:
            raise CandidateCutError("why: candidate cut source, state or verification is unavailable; remedy: restore its original private evidence and worktree; do not regenerate the snapshot or rewrite the candidate") from None

    def _prepare(self, *, request, source, snapshot_sha256, author_name, author_email, timestamp, verify, verify_locked):
        require((callable(verify) and verify_locked is None) or (verify is None and callable(verify_locked)),
                "requires exactly one trusted Task verifier")
        require(type(timestamp) is int and 1 <= timestamp <= 253402300799, "timestamp is invalid")
        require(type(author_name) is str and re.fullmatch(r"[A-Za-z0-9 ._-]{1,80}", author_name)
                and type(author_email) is str and re.fullmatch(r"[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+", author_email), "author is invalid")
        local = self.local
        gitdir = Path(local.git("rev-parse", "--absolute-git-dir").decode().strip())
        with local._locked(gitdir) as journal:
            state = self.snapshot.verified_state(journal, request, source, snapshot_sha256)
            source = state["scope"]["source"]
            build = source["product_build"]
            require(re.fullmatch(r"\d+\.\d+\.\d+\.\d+", build), "Build is invalid")
            metadata_name = f"apps/architecture-portal/versioned_metadata/version-{build}.json"
            expected = {}
            inventory = state["snapshot"]
            require(type(inventory) is list and 0 < len(inventory) <= 512, "snapshot inventory is invalid")
            total = 0
            for entry in inventory:
                require(type(entry) is dict and set(entry) == {"path", "bytes", "sha256"}, "snapshot entry is invalid")
                name = entry["path"]
                require(type(name) is str and name == PurePosixPath(name).as_posix()
                        and not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts,
                        "snapshot path is unsafe")
                require(name in ("apps/architecture-portal/versions.json", metadata_name,
                    f"apps/architecture-portal/versioned_sidebars/version-{build}-sidebars.json")
                    or name.startswith((f"apps/architecture-portal/versioned_docs/version-{build}/",
                        f"apps/architecture-portal/static/versions/{build}/diagrams/")), "snapshot path is outside this Build")
                require(name not in expected, "snapshot inventory repeats a path")
                raw = local._file(name)
                require(raw is not None and type(entry["bytes"]) is int and len(raw) == entry["bytes"]
                        and sha256(raw).hexdigest() == entry["sha256"], "snapshot bytes changed")
                total += len(raw)
                require(total <= 64 * 1024 * 1024, "snapshot exceeds its byte bound")
                expected[name] = raw
            require(metadata_name in expected and "apps/architecture-portal/versions.json" in expected, "snapshot metadata or versions is absent")
            metadata = json.loads(expected[metadata_name])
            require(metadata.get("revision") == source["commit"] and metadata.get("product_build") == build
                    and metadata.get("channel") == "canary", "snapshot source identity differs")
            frozen = datetime.fromisoformat(metadata["frozen_at_utc"].replace("Z", "+00:00"))
            require(frozen.tzinfo is not None and datetime.fromtimestamp(timestamp, timezone.utc) >= frozen,
                    "commit time precedes snapshot freeze")
            with tempfile.TemporaryDirectory(prefix="lmdj-candidate-cut-index-") as directory:
                index = Path(directory) / "index"
                local.git("read-tree", source["tree"], index=index)
                for name, raw in sorted(expected.items()):
                    oid = local.git("hash-object", "-w", "--stdin", data=raw).decode().strip()
                    local.git("update-index", "--add", "--cacheinfo", "100644," + oid + "," + name, index=index)
                tree = local.revision_from_index(index)
                changed = {name.decode() for name in local.git("diff-tree", "--no-ext-diff", "--no-commit-id", "--name-only", "-r", "-z", source["base_revision"], tree).split(b"\0") if name}
                require(changed == FILES | set(expected), "final diff is not exact source plus snapshot")
                raw = self.commit_bytes(source, tree, snapshot_sha256, author_name, author_email, timestamp)
                commit = local.git("hash-object", "-t", "commit", "-w", "--stdin", data=raw).decode().strip()
                retention = "refs/lmdj/release-sources/" + source["operation_id"]
                binding = {"schema":"lmdj.candidate-cut.v1", "source_sha256":canonical_sha256(source),
                    "snapshot_sha256":snapshot_sha256, "snapshot_state_sha256":canonical_sha256(state),
                    "base_revision":source["base_revision"], "source_commit":source["commit"],
                    "tree":tree, "commit":commit, "branch":source["branch"], "source_retention_ref":retention}
                previous = read(journal, "cut-binding.json", optional=True)
                self._check(source, tree, commit, staged=False)
                if previous is None:
                    require(local.revision("HEAD") == source["commit"] and local.revision_from_index() == source["tree"],
                            "cut binding is missing after staging or commit")
                    journal._write("cut-binding.json", canonical_json(binding))
                else:
                    require(previous == binding, "durable cut binding changed")

                def guard(phase):
                    journal._active()
                    self.snapshot._authorize(state["scope"])
                    require(read(journal, "binding.json") == source
                            and read(journal, "cut-binding.json") == binding
                            and canonical_sha256(self.snapshot._state(journal, state["scope"]))
                                == binding["snapshot_state_sha256"],
                            "source, snapshot or cut history changed during verification")
                    self._check(source, tree, commit, staged=True)
                    require(local.revision("HEAD") == (source["commit"] if phase == "staged" else commit),
                            "verification phase HEAD changed")
                    retained = local.git("for-each-ref", "--format=%(refname) %(objectname)", retention).decode().strip()
                    allowed = ("", retention + " " + source["commit"]) if phase == "staged" else (retention + " " + source["commit"],)
                    require(retained in allowed, "source retention ref changed during verification")

                if local.revision("HEAD") == source["commit"]:
                    if local.revision_from_index() != tree:
                        local.git("read-tree", tree)
                    self._check(source, tree, commit, staged=True)
                    self._verify(verify, verify_locked, local.root, "staged", binding, lambda: guard("staged"))
                    retained = local.git("for-each-ref", "--format=%(refname) %(objectname)", retention).decode().strip()
                    require(retained in ("", retention + " " + source["commit"]), "source retention ref changed")
                    if not retained:
                        local.git("update-ref", retention, source["commit"], "0" * 40)
                    local.git("update-ref", "refs/heads/" + source["branch"], commit, source["commit"])
                self._check(source, tree, commit, staged=True)
                require(local.revision(retention) == source["commit"], "source retention proof is missing")
                self._verify(verify, verify_locked, local.root, "committed", binding, lambda: guard("committed"))
                require(local.revision("HEAD") == commit, "final commit identity changed")
                require(local.revision(retention) == source["commit"], "source retention ref changed during verification")
                return dict(binding, product_build=build, status="cut-committed", files=sorted(changed))
