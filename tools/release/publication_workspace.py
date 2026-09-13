"""Recoverable local publication-evidence Task; never push, publish or deploy.

The caller supplies a dedicated linked worktree and freshly verified frozen
publication state. The branch and durable binding belong to one operation.
Git object construction uses a private index; only declared evidence files may
be installed. Verification must succeed before the branch advances atomically.
"""

from hashlib import sha1, sha256
from contextlib import contextmanager
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

from .batch_reference import digest, sha
from .model import canonical_json
from .orchestration import RequestJournal
from .publication_evidence import INDEX, LEDGER, PAGES, PIN, PUBLICATIONS, plan_publication_patch


class PublicationWorkspaceError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise PublicationWorkspaceError(
            f"why: publication workspace {reason}; remedy: retain the original operation and reconcile its dedicated worktree; do not overwrite drift or bypass verification")


class PublicationWorkspace:
    JOURNAL_NAME = "lmdj-publication-workspace"
    VERIFY_LABEL = "publication"

    def __init__(self, root):
        self.root = Path(root).absolute()
        self._journal = None
        require(self.root.resolve() == self.root, "path contains a symlink")

    def git(self, *args, data=None, index=None):
        lease = ()
        if self._journal is not None:
            self._journal._active()
            # The Git child retains this open lock description if its controller
            # dies. A replacement writer cannot overlap an orphaned Git write.
            lease = (self._journal.lock,)
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_NO_REPLACE_OBJECTS="1", GIT_GRAFT_FILE=os.devnull,
                   GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="", LC_ALL="C")
        if index is not None:
            env["GIT_INDEX_FILE"] = str(index)
        try:
            # Even write-tree may refresh entries through clean filters. Disable
            # every configured driver for each invocation, including after the
            # trusted verifier returns; never execute target-selected commands.
            filters = subprocess.run(["git", "-C", str(self.root), "config", "--includes",
                "--null", "--name-only", "--get-regexp", r"^filter\..*\.(clean|smudge|process|required)$"],
                capture_output=True, env=env, timeout=30, pass_fds=lease)
            require(filters.returncode in (0, 1), "filter configuration cannot be inspected")
            overrides = []
            for key in filter(None, filters.stdout.split(b"\0")):
                name = key.decode("utf-8")
                require(name.startswith("filter.") and "\n" not in name, "filter configuration key is unsafe")
                overrides.extend(("-c", name + ("=false" if name.endswith(".required") else "=")))
            result = subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull,
                "-c", "core.fsmonitor=false", "-c", "core.autocrlf=false", "-c", "core.fsync=all",
                "-c", "core.attributesFile=" + os.devnull, *overrides, "-C", str(self.root), *args], input=data,
                capture_output=True, env=env, timeout=30, pass_fds=lease)
        except (OSError, subprocess.TimeoutExpired):
            raise PublicationWorkspaceError("why: publication workspace Git is unavailable; remedy: restore the same worktree and retry observation") from None
        require(result.returncode == 0, "Git operation refused")
        return result.stdout

    @contextmanager
    def _locked(self, gitdir):
        require(self._journal is None, "writer context is already active")
        with RequestJournal(gitdir / self.JOURNAL_NAME) as journal:
            self._journal = journal
            try:
                yield journal
            finally:
                self._journal = None

    def revision(self, name):
        value = self.git("rev-parse", "--verify", name).decode().strip()
        require(sha(value), "Git identity is not SHA-1")
        return value

    def _file(self, relative):
        path = self.root / relative
        for parent in path.parents:
            if parent == self.root:
                break
            require(parent.is_dir() and not parent.is_symlink(), "file parent is unsafe")
        try:
            info = path.lstat()
        except FileNotFoundError:
            return None
        require(stat.S_ISREG(info.st_mode) and not info.st_mode & 0o111 and info.st_nlink == 1 and info.st_size <= 8 * 1024 * 1024,
                "file is not a bounded single-link regular file")
        return path.read_bytes()

    def _binding(self, journal, value):
        """Install canonical binding before any checkout; never replace one."""
        journal._active()
        payload = canonical_json(value)
        try:
            fd = os.open("binding.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=journal.directory)
        except FileNotFoundError:
            try:
                fd = os.open("binding.pending", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=journal.directory)
                created = True
            except FileExistsError:
                fd = os.open("binding.pending", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=journal.directory)
                created = False
            try:
                journal._private(fd)
                if created:
                    with os.fdopen(fd, "wb", closefd=False) as stream:
                        stream.write(payload)
                        stream.flush()
                else:
                    with os.fdopen(fd, "rb", closefd=False) as stream:
                        require(stream.read(65537) == payload, "pending operation binding is incomplete or changed")
                os.fsync(fd)
                journal._active()
                # One writer owns this directory. Atomic rename avoids the
                # two-link crash window; an exact complete pending file can be
                # adopted after a pre-rename crash without rewriting its bytes.
                os.replace("binding.pending", "binding.json", src_dir_fd=journal.directory,
                           dst_dir_fd=journal.directory)
                os.fsync(journal.directory)
            finally:
                os.close(fd)
            return
        try:
            journal._private(fd)
            with os.fdopen(fd, "rb", closefd=False) as stream:
                require(stream.read(65537) == payload, "operation binding changed")
        finally:
            os.close(fd)

    def prepare(self, *, base_revision, operation_id, policy, intent, record,
                author_name, author_email, timestamp, verify):
        """Apply/recover and commit after trusted Task verification.

        `verify(root)` is trusted controller code (never loaded from the target)
        and must run the Task's Portal/ownership checks, raising on failure.
        This internal API does not authenticate release authorization, main
        ancestry, published state, review or PR merge; its caller must do so.
        """
        require(sha(base_revision) and digest(operation_id), "base or operation identity is invalid")
        require(type(timestamp) is int and 1 <= timestamp <= 253402300799, "timestamp is invalid")
        require(type(author_name) is str and re.fullmatch(r"[A-Za-z0-9 ._-]{1,80}", author_name)
                and type(author_email) is str and re.fullmatch(r"[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+", author_email), "commit author is invalid")
        branch = "docs/release-evidence-" + operation_id
        require(self.git("symbolic-ref", "--short", "HEAD").decode().strip() == branch, "branch is not operation-bound")
        require(self.git("rev-parse", "--is-shallow-repository").strip() == b"false", "history is shallow")
        gitdir = Path(self.git("rev-parse", "--absolute-git-dir").decode().strip())
        common = Path(self.git("rev-parse", "--path-format=absolute", "--git-common-dir").decode().strip())
        require(gitdir != common and (self.root / ".git").is_file() and not (self.root / ".git").is_symlink(), "a dedicated linked worktree is required")
        with self._locked(gitdir) as journal:
            # Reconstruct from immutable base blobs, not potentially half-written
            # workspace files. Only passive planner inputs are materialized.
            with tempfile.TemporaryDirectory(prefix="lmdj-publication-input-") as directory:
                source = Path(directory)
                inventory = self.git("ls-tree", "-r", "-z", base_revision).split(b"\0")
                selected = {}
                for row in filter(None, inventory):
                    metadata, filename = row.split(b"\t", 1)
                    name = filename.decode("utf-8")
                    if name in (LEDGER, PUBLICATIONS, PIN) or name.startswith(PAGES + "/"):
                        mode, kind, oid = metadata.split(b" ")
                        require(mode == b"100644" and kind == b"blob" and ".." not in Path(name).parts,
                                "base evidence file mode is unsafe")
                        raw = self.git("cat-file", "blob", oid.decode())
                        require(len(raw) <= 8 * 1024 * 1024, "base evidence exceeds its bound")
                        selected[name] = raw
                        target = source / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(raw)
                patch = plan_publication_patch(source, policy, intent, record).encode()
                require(patch, "base already contains the publication; observe its existing PR instead")
                index = source / "private-index"
                self.git("read-tree", base_revision, index=index)
                self.git("apply", "--cached", "--whitespace=error", "-", data=patch, index=index)
                tree = self.revision_from_index(index)
                files = self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", base_revision, tree).split(b"\0")
                files = [name.decode() for name in files if name]
                expected_files = {LEDGER, PUBLICATIONS, PIN, INDEX, PAGES + "/" + intent.identity + ".mdx"}
                require(set(files) == expected_files, "patch changes paths beyond this publication")
                require(not self.git("check-attr", "--cached", "--all", "--", *files, index=index),
                        "evidence paths have checkout-transforming attributes")
                expected = {name: self.git("cat-file", "blob", tree + ":" + name) for name in files}
                message = (f"docs(release): record {intent.tag} publication\n\n"
                           f"Release-operation: {operation_id}\nPublication-record-sha256: {sha256(canonical_json(record)).hexdigest()}\n")
                identity = f"{author_name} <{author_email}> {timestamp} +0000"
                commit_bytes = f"tree {tree}\nparent {base_revision}\nauthor {identity}\ncommitter {identity}\n\n{message}".encode()
                commit = self.git("hash-object", "-t", "commit", "-w", "--stdin", data=commit_bytes).decode().strip()
                binding = {"schema": "lmdj.publication-workspace.v1", "operation_id": operation_id,
                           "base_revision": base_revision, "patch_sha256": sha256(patch).hexdigest(),
                           "tree": tree, "commit": commit, "branch": branch}
                self._binding(journal, binding)
                self._install_commit(journal, base_revision, tree, commit, branch,
                                     selected, expected, index, verify)
                return dict(binding, tag=intent.tag, target_revision=intent.target_revision,
                            files=sorted(files), status="committed")

    def _install_commit(self, journal, base_revision, tree, commit, branch,
                        selected, expected, index, verify):
        """Shared atomic OLD/NEW recovery after the planner freezes binding."""
        head = self.revision("HEAD")
        require(head in (base_revision, commit), "branch advanced to an unrelated commit")
        self._check_workspace(base_revision, tree, selected, expected)
        if head == base_revision:
            for name in sorted(expected):
                journal._active()
                require(self._file(name) in (selected.get(name), expected[name]), "file changed before installation")
                self._install(name, expected[name], selected.get(name))
            self.git("read-tree", tree)
        self._check_workspace(base_revision, tree, selected, expected, complete=True)
        try:
            verify(self.root)
        except Exception:
            raise PublicationWorkspaceError(f"why: {self.VERIFY_LABEL} Task verification failed; remedy: inspect retained verification output and resume the same operation without bypassing checks") from None
        journal._active()
        self._check_workspace(base_revision, tree, selected, expected, complete=True)
        require(self.git("symbolic-ref", "--short", "HEAD").decode().strip() == branch, "branch changed during verification")
        if head == base_revision:
            self.git("update-ref", "refs/heads/" + branch, commit, base_revision)
        require(self.revision("HEAD") == commit and self.revision_from_index() == tree, "commit identity drifted")
        self._check_workspace(base_revision, tree, selected, expected, complete=True)

    def revision_from_index(self, index=None):
        value = self.git("write-tree", index=index).decode().strip()
        require(sha(value), "index tree identity is invalid")
        return value

    def _install(self, name, payload, old):
        journal = self._journal
        journal._active()
        parent = os.open((self.root / name).parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            require(os.fstat(parent).st_dev == os.fstat(journal.directory).st_dev,
                    "staging and destination are on different devices")
            descriptor, staging = tempfile.mkstemp(prefix="install-", dir=journal.root)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fchmod(stream.fileno(), 0o644)
                os.fsync(stream.fileno())
            os.fsync(journal.directory)
            journal._active()
            require(self._file(name) in (old, payload), "file changed before atomic installation")
            os.replace(Path(staging).name, Path(name).name,
                       src_dir_fd=journal.directory, dst_dir_fd=parent)
            os.fsync(parent)
            os.fsync(journal.directory)
        finally:
            os.close(parent)

    def _raw_identity(self, name):
        target = self.root / name
        for parent in target.parents:
            if parent == self.root:
                break
            require(parent.is_dir() and not parent.is_symlink(), "tracked file parent is unsafe")
        try:
            info = target.lstat()
            if stat.S_ISLNK(info.st_mode):
                raw = os.fsencode(os.readlink(target))
                return b"120000", sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest().encode()
            require(stat.S_ISREG(info.st_mode), "tracked file is not regular")
            descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                before = os.fstat(stream.fileno())
                require(stat.S_ISREG(before.st_mode), "tracked file changed type")
                digest = sha1(b"blob " + str(before.st_size).encode() + b"\0")
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                after = os.fstat(stream.fileno())
                require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                        (after.st_size, after.st_mtime_ns, after.st_ctime_ns), "tracked file changed during read")
            return (b"100755" if before.st_mode & 0o111 else b"100644"), digest.hexdigest().encode()
        except OSError:
            raise PublicationWorkspaceError("why: tracked raw bytes are unavailable; remedy: restore the original worktree without running content filters") from None

    def _check_workspace(self, base, tree, old, expected, complete=False):
        # The real index may be OLD or NEW, never a mixture or someone else's
        # staged edits. Ignored tool outputs (node_modules/build) are not Task
        # files and remain untouched; exact evidence paths are always byte-checked.
        require(self.revision_from_index() in ((tree,) if complete else (self.revision(base + "^{tree}"), tree)), "index contains unexpected edits")
        # Git diff/status can run local clean filters and hide raw edits, including
        # assume-unchanged/skip-worktree entries. Read every base path directly.
        for row in filter(None, self.git("ls-tree", "-r", "-z", base).split(b"\0")):
            metadata, filename = row.split(b"\t", 1)
            mode, kind, oid = metadata.split(b" ")
            name = filename.decode()
            if name in expected:
                continue
            require(kind == b"blob" and mode in (b"100644", b"100755", b"120000"), "tracked mode is unsupported")
            require(self._raw_identity(name) == (mode, oid), "unrelated tracked raw bytes or mode drifted")
        untracked = self.git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
        observed = {name.decode() for name in untracked if name}
        require(observed <= set(expected), "unrelated or untracked files are present")
        for name, new in expected.items():
            require(self._file(name) in ((new,) if complete else (old.get(name), new)), "file bytes drifted")
