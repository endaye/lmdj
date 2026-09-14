"""Executed exact-source Task receipts for the trusted local release service."""

from copy import deepcopy
from hashlib import sha1, sha256
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import tempfile
import uuid

from .batch_reference import digest, sha
from .evidence_pr import pr_document, validate_spec
from .model import canonical_json, canonical_sha256
from .orchestration import RequestJournal
from .publication_workspace import PublicationWorkspace

# Labels match the evidence PR declaration. The actual Git vector disables
# executable diff extensions; it does not relax the whitespace check.
CHECKS = (
    ("scripts/docs-site.sh check", ("bash", "scripts/docs-site.sh", "check"), 900),
    ("python3 tests/build/ci_change_scope_test.py", ("python3", "tests/build/ci_change_scope_test.py"), 120),
    ("git diff --cached --check", ("git", "-c", "core.hooksPath=" + os.devnull,
        "-c", "core.fsmonitor=false", "-c", "core.attributesFile=" + os.devnull,
        "-c", "core.whitespace=blank-at-eol,blank-at-eof,space-before-tab",
        "diff", "--no-ext-diff", "--no-textconv", "--cached", "--check", "{base_revision}"), 30),
)
MAX_STATE_BYTES = 65536


def _checks(scope):
    # A postcommit check against HEAD would be empty. Compare the verified index
    # to the Task base so whitespace in the introduced commit is actually tested.
    return tuple((label, tuple(scope["base_revision"] if arg == "{base_revision}" else arg for arg in vector), timeout)
                 for label, vector, timeout in CHECKS)


class TaskVerificationError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise TaskVerificationError(f"why: publication Task {reason}; remedy: retain the original verification attempt, inspect the named command and exact source, and repair the cause without inventing a passing receipt")


def task_scope(spec, control_revision):
    validate_spec(spec)
    require(sha(control_revision), "control revision is invalid")
    return {k: v for k, v in spec.items() if k != "task_evidence_sha256"} | {"control_revision": control_revision}


def _spec(scope):
    require(type(scope) is dict and "control_revision" in scope and sha(scope["control_revision"]), "scope is invalid")
    result = {k: v for k, v in scope.items() if k != "control_revision"} | {"task_evidence_sha256": "0" * 64}
    validate_spec(result)
    return result


def verify_tracked_bytes(local, revision, *, mutable_paths=()):
    """Compare filesystem bytes to Git objects without running clean filters."""
    for row in filter(None, local.git("ls-tree", "-r", "-z", revision).split(b"\0")):
        metadata, name = row.split(b"\t", 1)
        mode, kind, oid = metadata.split(b" ")
        relative = Path(os.fsdecode(name))
        require(not relative.is_absolute() and ".." not in relative.parts and kind == b"blob", "tracked path or object is unsafe")
        filename = local.root / relative
        for parent in filename.parents:
            if parent == local.root:
                break
            require(not parent.is_symlink(), "tracked parent is a symlink")
        info = filename.lstat()
        if mode == b"120000":
            require(stat.S_ISLNK(info.st_mode), "tracked symlink type changed")
            raw = os.fsencode(os.readlink(filename))
            actual = sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        else:
            require(mode in (b"100644", b"100755") and stat.S_ISREG(info.st_mode)
                    and bool(info.st_mode & 0o111) == (mode == b"100755"), "tracked file mode changed")
            if relative.as_posix() in mutable_paths:
                continue
            hasher = sha1(b"blob " + str(info.st_size).encode() + b"\0")
            with filename.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(chunk)
            actual = hasher.hexdigest()
        require(actual == oid.decode(), "tracked bytes differ from tested tree")


class PublicationTaskVerifier:
    def __init__(self, root, repository, *, authorize, path):
        self.root, self.repository = root, Path(repository).absolute()
        self.authorize, self.path = authorize, path
        require(self.repository.resolve() == self.repository, "repository path contains symlinks")
        require(type(path) is str and path and all(Path(p).is_absolute() for p in path.split(os.pathsep)), "trusted toolchain PATH is invalid")

    def _authorize(self, scope):
        try:
            self.authorize(deepcopy(scope))
        except Exception:
            raise RuntimeError("publication Task authority unavailable") from None

    def _checkout(self, scope):
        local = PublicationWorkspace(self.repository)
        spec = _spec(scope)
        require(local.revision("HEAD") == spec["head_sha"]
                and local.revision("HEAD^{tree}") == spec["tree_sha"]
                and local.revision_from_index() == spec["tree_sha"], "head or index differs from tested identity")
        require(local.git("symbolic-ref", "--short", "HEAD").decode().strip() == pr_document(spec)["head"], "branch is not operation-bound")
        require(not local.git("ls-files", "--others", "--exclude-standard", "-z"), "untracked Task inputs exist")
        verify_tracked_bytes(local, spec["head_sha"])

    @staticmethod
    def _state(journal, scope, *, initialize=False):
        journal._active()
        try:
            fd = os.open("task-state.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=journal.directory)
        except FileNotFoundError:
            require(initialize, "receipt is missing")
            try:
                marker = os.open("task-enrolled", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=journal.directory)
            except FileExistsError:
                raise TaskVerificationError("why: enrolled Task state is missing; remedy: retain the journal and reconcile the original attempt without rerunning commands") from None
            try:
                os.fsync(marker)
                os.fsync(journal.directory)
            finally:
                os.close(marker)
            initial = {"schema": "lmdj.publication-task-tests.v1", "scope": scope, "commands": []}
            PublicationTaskVerifier._save(journal, initial)
            return initial
        try:
            journal._private(fd)
            try:
                marker = os.open("task-enrolled", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=journal.directory)
            except FileNotFoundError:
                raise TaskVerificationError("why: Task enrollment marker is missing; remedy: retain the journal and reconcile the original enrollment") from None
            try:
                journal._private(marker)
                require(os.fstat(marker).st_size == 0, "enrollment marker is corrupt")
            finally:
                os.close(marker)
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_STATE_BYTES + 1)
            value = json.loads(raw)
            require(type(value) is dict and set(value) == {"schema", "scope", "commands"}
                    and value["schema"] == "lmdj.publication-task-tests.v1"
                    and canonical_json(value["scope"]) == canonical_json(scope)
                    and canonical_json(value) == raw and len(raw) <= MAX_STATE_BYTES, "receipt is corrupt or rebound")
            rows = value["commands"]
            require(type(rows) is list and len(rows) <= len(CHECKS), "command inventory is invalid")
            for index, row in enumerate(rows):
                label, vector, _ = _checks(scope)[index]
                require(type(row) is dict and set(row) == {"command", "arguments", "status", "exit_code", "output_sha256", "output_bytes"}
                        and row["command"] == label and row["arguments"] == list(vector), "command identity changed")
                require(row["status"] in ("started", "finished", "verified"), "command state is invalid")
                if row["status"] == "started":
                    require(all(row[k] is None for k in ("exit_code", "output_sha256", "output_bytes")), "unfinished command carries a result")
                else:
                    require(type(row["exit_code"]) is int and -255 <= row["exit_code"] <= 255
                            and digest(row["output_sha256"]) and type(row["output_bytes"]) is int
                            and row["output_bytes"] >= 0, "command result is invalid")
                require(row["status"] != "verified" or row["exit_code"] == 0, "failed command claims verification")
                require(index == len(rows) - 1 or row["status"] == "verified", "command followed an unverified predecessor")
            return value
        except (ValueError, UnicodeError) as error:
            if isinstance(error, TaskVerificationError):
                raise
            raise TaskVerificationError("why: Task receipt is malformed; remedy: preserve it and reconcile the original verification attempt") from None
        finally:
            os.close(fd)

    @staticmethod
    def _save(journal, state):
        journal._active()
        encoded = canonical_json(state)
        require(len(encoded) <= MAX_STATE_BYTES, "receipt exceeds its read bound")
        name = ".task-pending-" + uuid.uuid4().hex
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=journal.directory)
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(fd)
            journal._active()
            os.replace(name, "task-state.json", src_dir_fd=journal.directory, dst_dir_fd=journal.directory)
            os.fsync(journal.directory)
        finally:
            os.close(fd)

    def _execute(self, journal, vector, timeout, *, retained_locks=()):
        result, _ = self._execute_output(journal, vector, timeout, capture_limit=None,
                                        retained_locks=retained_locks)
        return result

    def _execute_capture(self, journal, vector, timeout, *, limit):
        """Return (exit/digest/length, complete bytes or None on overflow).

        This is the original combined stdout/stderr, not a validated receipt.
        Callers must reject nonzero exits, overflow and invalid output before
        using it, and must not persist arbitrary child output in public logs.
        Existing execution callers remain digest-only. The temporary spool's
        disk usage is unchanged; the limit bounds only retained memory bytes.
        """
        require(type(limit) is int and 1 <= limit <= MAX_STATE_BYTES,
                "capture limit must be an integer between 1 and 65536 bytes")
        return self._execute_output(journal, vector, timeout, capture_limit=limit)

    def _execute_output(self, journal, vector, timeout, *, capture_limit, retained_locks=()):
        journal._active()
        require(type(retained_locks) is tuple and all(type(fd) is int and fd >= 0 for fd in retained_locks),
                "retained writer descriptors are invalid")
        writer_fds = tuple(dict.fromkeys((journal.lock, *retained_locks)))
        with tempfile.TemporaryDirectory(prefix="lmdj-task-environment-") as directory:
            # No inherited credentials, injection settings or personal tool config.
            env = dict(PATH=self.path, HOME=directory, TMPDIR=directory, LC_ALL="C",
                GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_NO_LAZY_FETCH="1",
                GIT_ALLOW_PROTOCOL="file", GIT_NO_REPLACE_OBJECTS="1", GIT_GRAFT_FILE=os.devnull,
                GIT_TERMINAL_PROMPT="0", GIT_ATTR_NOSYSTEM="1", PYTHONNOUSERSITE="1", NPM_CONFIG_USERCONFIG=os.devnull)
            if vector[0] == "git":
                env["GIT_ALLOW_PROTOCOL"] = ""
                # The whitespace check must not read .git/config or
                # .git/info/attributes, neither of which is bound by the tree.
                # Committed attributes still come from the verified index.
                scratch = Path(directory) / "git"
                initialized = subprocess.run(["git", "init", "--bare", "--template=", str(scratch)],
                    cwd=directory, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=30, pass_fds=writer_fds)
                require(initialized.returncode == 0, "isolated whitespace repository is unavailable")
                local = PublicationWorkspace(self.repository)
                for setting, name in (("GIT_INDEX_FILE", "index"), ("GIT_OBJECT_DIRECTORY", "objects")):
                    env[setting] = local.git("rev-parse", "--path-format=absolute", "--git-path", name).decode().strip()
                vector = ("git", "--git-dir=" + str(scratch), *vector[1:])
            with tempfile.TemporaryFile() as output:
                with subprocess.Popen(vector, cwd=self.repository, env=env, stdout=output,
                        stderr=subprocess.STDOUT, pass_fds=writer_fds, start_new_session=True) as child:
                    try:
                        code = child.wait(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
                        raise TaskVerificationError("why: Task command exceeded its execution budget; remedy: retain the unfinished attempt and diagnose it; no automatic rerun") from None
                output.seek(0)
                hasher, length = sha256(), 0
                captured = None if capture_limit is None else bytearray()
                for chunk in iter(lambda: output.read(1024 * 1024), b""):
                    hasher.update(chunk)
                    length += len(chunk)
                    if captured is not None:
                        if length <= capture_limit:
                            captured.extend(chunk)
                        else:
                            captured = None
                return ((code, hasher.hexdigest(), length),
                        None if captured is None else bytes(captured))

    @staticmethod
    def _receipt(state):
        require(len(state["commands"]) == len(CHECKS) and all(
            row["status"] == "verified" and row["exit_code"] == 0 for row in state["commands"]), "verification is incomplete or failed")
        return {"sha256": canonical_sha256(state), "reference": "task-tests:" + state["scope"]["operation_id"]}

    def run(self, scope):
        pr_document(_spec(scope))
        scope = deepcopy(scope)
        with RequestJournal(self.root) as journal:
            state = self._state(journal, scope, initialize=True)
            try:
                self._authorize(scope)
                self._checkout(scope)
                self._save(journal, state)
                require(all(row["status"] == "verified" for row in state["commands"]), "prior command is failed or unknown; automatic replay is forbidden")
                for label, vector, timeout in _checks(scope)[len(state["commands"]):]:
                    self._authorize(scope)
                    self._checkout(scope)
                    row = dict(command=label, arguments=list(vector), status="started", exit_code=None,
                               output_sha256=None, output_bytes=None)
                    state["commands"].append(row)
                    self._save(journal, state)
                    code, output_digest, size = self._execute(journal, vector, timeout)
                    row.update(status="finished", exit_code=code, output_sha256=output_digest, output_bytes=size)
                    self._save(journal, state)
                    require(code == 0, f"command {label} exited {code}")
                    self._checkout(scope)
                    row["status"] = "verified"
                    self._save(journal, state)
                return self._receipt(state)
            except TaskVerificationError:
                raise
            except Exception:
                raise TaskVerificationError("why: Task verification is unavailable; remedy: retain the attempt and restore its exact authorized source and toolchain") from None

    def verify(self, spec, control_revision):
        """Read a trusted-service receipt, not a fresh checkout/CI/review verdict.

        Source and authority must be revalidated by the trusted callback; the
        historical checkout need not still be checked out after its PR merges.
        """
        scope = task_scope(spec, control_revision)
        with RequestJournal(self.root) as journal:
            try:
                self._authorize(scope)
                receipt = self._receipt(self._state(journal, scope))
                require(receipt["sha256"] == spec["task_evidence_sha256"], "receipt digest differs from the PR binding")
                return receipt
            except TaskVerificationError:
                raise
            except Exception:
                raise TaskVerificationError("why: Task receipt verification is unavailable; remedy: restore the original authorized scope and private receipt without bypassing validation") from None
