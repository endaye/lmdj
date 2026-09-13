"""Exact, create-only publication branch transport with durable unknowns.

This is an internal adapter, not release authorization or a public run command.
The caller supplies trusted authority/Task/source/protection verification.
"""

from base64 import b64encode
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

from .evidence_pr import pr_document, validate_spec
from .github_api import GitHubClient
from .model import canonical_json, canonical_sha256
from .orchestration import RequestJournal
from .publication_workspace import PublicationWorkspace

REMOTE = "https://github.com/endaye/lmdj.git"
MAX_STATE_BYTES = 65536


class EvidenceBranchError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise EvidenceBranchError(f"why: publication branch {reason}; remedy: reconcile the original operation and exact remote ref; never overwrite drift or blindly repeat a push")


class PublicationBranch:
    def __init__(self, root, repository, *, token, authorize):
        self.root, self.repository = root, Path(repository)
        require(type(token) is str and bool(token) and not any(c in token for c in "\r\n\0"), "credential is unavailable")
        self._token, self.authorize = token, authorize
        self.api = GitHubClient(token=token).release_pr_request

    def _authorize(self, spec):
        # This callback is trusted controller code, never a user/PR-loaded plugin.
        try:
            self.authorize(deepcopy(spec))
        except Exception:
            raise RuntimeError("publication branch authority unavailable") from None
        repo, actor, main = (self.api("GET", route) for route in ("", "/user", "/branches/main"))
        require(type(repo) is dict and type(repo.get("id")) is int and repo["id"] == spec["repository_id"]
                and repo.get("full_name") == "endaye/lmdj", "repository identity changed")
        require(type(actor) is dict and type(actor.get("id")) is int and actor["id"] == spec["actor_id"], "actor changed")
        require(type(main) is dict and main.get("name") == "main" and main.get("protected") is True, "main is not protected")
        local = PublicationWorkspace(self.repository)
        require(local.git("cat-file", "-t", spec["head_sha"]).strip() == b"commit"
                and local.revision(spec["head_sha"] + "^{tree}") == spec["tree_sha"], "local commit identity changed")

    @staticmethod
    def _state(journal, spec):
        journal._active()
        try:
            fd = os.open("branch-state.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=journal.directory)
        except FileNotFoundError:
            try:
                marker = os.open("branch-enrolled", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=journal.directory)
            except FileExistsError:
                raise EvidenceBranchError("why: enrolled branch state is missing; remedy: retain the journal and reconcile the original operation without another push") from None
            try:
                os.fsync(marker)
                os.fsync(journal.directory)
            finally:
                os.close(marker)
            initial = {"schema": "lmdj.evidence-branch-state.v1", "spec": spec, "claimed": False}
            PublicationBranch._save(journal, initial)
            return initial
        try:
            journal._private(fd)
            try:
                marker = os.open("branch-enrolled", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=journal.directory)
            except FileNotFoundError:
                raise EvidenceBranchError("why: branch enrollment marker is missing; remedy: retain the original journal and reconcile its enrollment") from None
            try:
                journal._private(marker)
                require(os.fstat(marker).st_size == 0, "enrollment marker is corrupt")
            finally:
                os.close(marker)
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_STATE_BYTES + 1)
            value = json.loads(raw)
            require(type(value) is dict and set(value) == {"schema", "spec", "claimed"}
                    and value["schema"] == "lmdj.evidence-branch-state.v1"
                    and canonical_json(value["spec"]) == canonical_json(spec)
                    and type(value["claimed"]) is bool and len(raw) <= MAX_STATE_BYTES
                    and canonical_json(value) == raw, "durable state is corrupt or rebound")
            return value
        except EvidenceBranchError:
            raise
        except (ValueError, UnicodeError):
            raise EvidenceBranchError("why: publication branch state is invalid; remedy: retain it and reconcile the original operation") from None
        finally:
            os.close(fd)

    @staticmethod
    def _save(journal, value):
        journal._active()
        encoded = canonical_json(value)
        require(len(encoded) <= MAX_STATE_BYTES, "durable state exceeds its read bound")
        name = ".branch-pending-" + uuid.uuid4().hex
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=journal.directory)
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(fd)
            journal._active()
            os.replace(name, "branch-state.json", src_dir_fd=journal.directory, dst_dir_fd=journal.directory)
            os.fsync(journal.directory)
        finally:
            os.close(fd)

    def _git(self, journal, scratch, *args):
        journal._active()
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_NO_REPLACE_OBJECTS="1", GIT_GRAFT_FILE=os.devnull,
                   GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="https", GIT_TERMINAL_PROMPT="0",
                   GIT_ASKPASS="/usr/bin/false", LC_ALL="C")
        # Never read repository-local remotes, credential helpers, URL rewrites,
        # proxy/SSL overrides, hooks or push options. Only passive objects are reused.
        object_dir = PublicationWorkspace(self.repository).git(
            "rev-parse", "--path-format=absolute", "--git-path", "objects").decode().strip()
        env["GIT_OBJECT_DIRECTORY"] = object_dir
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
                   GIT_CONFIG_VALUE_0="AUTHORIZATION: basic " + b64encode(("x-access-token:" + self._token).encode()).decode())
        command = ["git", "--git-dir=" + str(scratch), "-c", "core.hooksPath=" + os.devnull,
                   "-c", "credential.helper=", "-c", "http.followRedirects=false",
                   "-c", "http.sslVerify=true", "-c", "push.recurseSubmodules=no", *args]
        return subprocess.run(command, env=env, capture_output=True, timeout=30, pass_fds=(journal.lock,))

    def _observe(self, journal, scratch, spec):
        ref = "refs/heads/" + pr_document(spec)["head"]
        result = self._git(journal, scratch, "ls-remote", "--refs", "--exit-code", REMOTE, ref)
        if result.returncode == 2 and result.stdout == b"":
            return "absent"
        require(result.returncode == 0, "remote observation is unavailable")
        require(result.stdout == f"{spec['head_sha']}\t{ref}\n".encode(), "remote ref conflicts")
        return "verified"

    def advance(self, spec):
        validate_spec(spec)
        spec = deepcopy(spec)
        pr_document(spec)  # Reject local document limits before durable enrollment.
        with RequestJournal(self.root) as journal:
            state = self._state(journal, spec)
            try:
                self._authorize(spec)
                self._save(journal, state)
                with tempfile.TemporaryDirectory(prefix="lmdj-evidence-branch-") as directory:
                    scratch = Path(directory) / "git"
                    # init uses the same isolated environment; no global template.
                    result = self._git(journal, scratch, "init", "--bare", "--template=", str(scratch))
                    require(result.returncode == 0, "scratch Git initialization failed")
                    observed = self._observe(journal, scratch, spec)
                    if observed == "absent":
                        if state["claimed"]:
                            return {"status": "unknown", "evidence": None}
                        self._authorize(spec)
                        state["claimed"] = True
                        self._save(journal, state)
                        self._authorize(spec)
                        ref = "refs/heads/" + pr_document(spec)["head"]
                        try:
                            self._git(journal, scratch, "push", "--porcelain", "--atomic",
                                      "--force-with-lease=" + ref + ":", REMOTE, spec["head_sha"] + ":" + ref)
                        except Exception:
                            pass  # Neither ACK nor timeout proves far-side state.
                        observed = self._observe(journal, scratch, spec)
                    if observed != "verified":
                        return {"status": "unknown", "evidence": None}
                    self._authorize(spec)
                    require(self._observe(journal, scratch, spec) == "verified", "remote ref disappeared")
                    state["claimed"] = True  # Never recreate an adopted ref after deletion.
                    self._save(journal, state)
                    return {"status": "verified", "evidence": {
                        "sha256": canonical_sha256({"spec": spec, "ref": pr_document(spec)["head"]}),
                        "reference": "branch:" + pr_document(spec)["head"]}}
            except EvidenceBranchError:
                raise
            except Exception:
                return {"status": "unavailable", "evidence": None}
