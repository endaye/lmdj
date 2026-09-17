"""Durable single-writer release requests; records are not external-state proof.

Only a trusted driver may confirm a transition after verifying its far side.
On resume the driver must revalidate receipts against canonical external state.
An outstanding intent forbids another begin: it requires reconciliation first.
"""

from contextlib import AbstractContextManager
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import threading
import uuid

from .model import canonical_json, canonical_sha256


STEPS = ("candidate", "verification", "intent", "changelog", "prepared", "tag",
         "draft", "publication", "published_record", "changelog_site", "runtime",
         "creator", "promotion", "final")
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,79}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_TAG = re.compile(r"lmdj-v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\."
                  r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
_MAX_BYTES = 1024 * 1024


class JournalError(RuntimeError):
    pass


def _fail(reason):
    raise JournalError(f"why: {reason}; remedy: reconcile the original request and its verified evidence")


def _keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        _fail("journal fields are missing or unknown")


def _match(pattern, value):
    return type(value) is str and pattern.fullmatch(value) is not None


def validate_request(request):
    _keys(request, ("id", "repository", "actor_id", "authority_ref", "policy_digest",
                    "control_revision", "base_revision", "mode", "requested_tag"))
    if not _match(_ID, request["id"]):
        _fail("invalid request ID")
    if not _match(re.compile(r"[a-z0-9_.-]+/[a-z0-9_.-]+\Z"), request["repository"]):
        _fail("invalid request repository")
    if type(request["actor_id"]) is not int or request["actor_id"] <= 0:
        _fail("invalid authenticated actor identity")
    # An opaque reference to an independently authenticated authorization record,
    # never the chat body, access token, or owner attestation itself.
    if not _match(re.compile(r"[A-Za-z0-9:/_.#-]{1,256}\Z"), request["authority_ref"]):
        _fail("invalid authorization reference")
    if not _match(_DIGEST, request["policy_digest"]):
        _fail("invalid policy identity")
    for key in ("control_revision", "base_revision"):
        if not _match(_SHA, request[key]):
            _fail("invalid request revision")
    if request["mode"] == "new":
        if request["requested_tag"] is not None:
            _fail("new release request cannot silently select an existing tag")
    elif request["mode"] == "tag":
        if not _match(_TAG, request["requested_tag"]):
            _fail("exact Product tag required")
    else:
        _fail("unknown release request mode")


def _validate_state(state):
    _keys(state, ("schema", "request", "request_digest", "transitions"))
    if state["schema"] != "lmdj.release-request.v1":
        _fail("unknown release journal schema")
    validate_request(state["request"])
    if state["request_digest"] != canonical_sha256(state["request"]):
        _fail("request binding differs")
    records = state["transitions"]
    if type(records) is not list or len(records) > len(STEPS):
        _fail("invalid transition inventory")
    for index, record in enumerate(records):
        _keys(record, ("step", "operation_id", "status", "evidence"))
        if record["step"] != STEPS[index] or not _match(_DIGEST, record["operation_id"]):
            _fail("transition order or operation identity differs")
        expected = canonical_sha256({"request": state["request_digest"], "step": record["step"]})
        if record["operation_id"] != expected:
            _fail("transition operation is not request-bound")
        if record["status"] == "intent":
            if index != len(records) - 1 or record["evidence"] is not None:
                _fail("an unresolved intent cannot have successors or evidence")
        elif record["status"] == "verified":
            _validate_evidence(record["evidence"])
        else:
            _fail("unknown transition status")


def _validate_evidence(evidence):
    _keys(evidence, ("sha256", "reference"))
    if not _match(_DIGEST, evidence["sha256"]):
        _fail("invalid evidence digest")
    if not _match(re.compile(r"[A-Za-z0-9:/_.#-]{1,256}\Z"), evidence["reference"]):
        _fail("invalid evidence reference")


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _fail("duplicate journal key")
        value[key] = item
    return value


class RequestJournal(AbstractContextManager):
    """Use a dedicated private directory on a local POSIX filesystem.

    The lock covers the entire driver's execution, not just JSON writes. Separate
    callers cannot interleave remote effects. This is not protection against a
    malicious process running as the same trusted account.
    """

    def __init__(self, root: Path, *, writable: bool = True):
        self.root = Path(root).absolute()
        self.directory = None
        self.lock = None
        self.owner = None
        self.writable = writable

    def __enter__(self):
        if self.directory is not None:
            _fail("journal context is already open")
        if self.root.resolve() != self.root:
            _fail("journal directory or ancestor is a symlink")
        self.owner = (os.getpid(), threading.get_ident())
        if not self.writable:
            # A reader creates nothing: no directory, no writer lock, no fsync.
            # It also never joins the single-writer lock, so a run in progress
            # stays observable. State updates are atomic renames, so a reader
            # sees a complete earlier or later record, never a partial one.
            try:
                self.directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                self._private(self.directory, directory=True)
            except (OSError, JournalError):
                self.__exit__(None, None, None)
                _fail("journal is missing, unsafe or unavailable for reading")
            return self
        try:
            missing = []
            walk = self.root
            while not walk.exists():
                missing.append(walk)
                if walk.parent == walk:
                    break
                walk = walk.parent
            # Each level is created private: mkdir's mode applies to that
            # directory alone, and parents=True would leave the intermediate
            # levels at the process umask (commonly 0755), which the privacy
            # check below — and every later open — fails closed on. A level
            # that appears meanwhile already existed; keep its mode as-is.
            for level in reversed(missing):
                try:
                    level.mkdir(mode=0o700)
                except FileExistsError:
                    pass
                parent = os.open(level.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(parent)
                finally:
                    os.close(parent)
            self.directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self._private(self.directory, directory=True)
            self.lock = os.open("writer.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                                0o600, dir_fd=self.directory)
            self._private(self.lock)
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.fsync(self.directory)
        except (OSError, JournalError):
            self.__exit__(None, None, None)
            _fail("journal is unsafe, unavailable or owned by another writer")
        return self

    def __exit__(self, *args):
        if (self.owner is not None and self.owner[0] == os.getpid()
                and self.owner[1] != threading.get_ident()):
            _fail("journal context belongs to another thread")
        # A fork child may close its inherited descriptors, but must never
        # LOCK_UN the shared open-file description and unlock its parent's work.
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None
        if self.directory is not None:
            os.close(self.directory)
            self.directory = None
        self.owner = None

    def _private(self, descriptor, directory=False):
        info = os.fstat(descriptor)
        valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        if (not valid or info.st_uid != os.geteuid() or info.st_mode & 0o077
                or (not directory and info.st_nlink != 1)):
            _fail("journal storage must be private and owned by the current account")

    def _active(self):
        if self.owner != (os.getpid(), threading.get_ident()):
            _fail("journal requires its owning process and thread in a live exclusive context")
        if self.directory is None:
            _fail("journal requires a live exclusive context")
        self._private(self.directory, directory=True)
        if not self.writable:
            if self.lock is not None:
                _fail("journal reader context must not hold the writer lock")
            return
        if self.lock is None:
            _fail("journal requires a live exclusive context")
        self._private(self.lock)
        # Detect replacement of the lock/path before every operation. Holding an
        # unlinked old inode must never authorize a second writer's state updates.
        for name, fd in ((None, self.directory), ("writer.lock", self.lock)):
            observed = (os.stat(self.root, follow_symlinks=False) if name is None else
                        os.stat(name, dir_fd=self.directory, follow_symlinks=False))
            actual = os.fstat(fd)
            if (actual.st_dev, actual.st_ino) != (observed.st_dev, observed.st_ino):
                _fail("journal path or writer lock was replaced")

    def read(self, request_id):
        self._active()
        if not _match(_ID, request_id):
            _fail("invalid request ID")
        try:
            fd = os.open(request_id + ".json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=self.directory)
        except FileNotFoundError:
            return None
        except OSError:
            _fail("journal request is unsafe or unavailable")
        try:
            self._private(fd)
            with os.fdopen(fd, "rb", closefd=False) as source:
                raw = source.read(_MAX_BYTES + 1)
            if len(raw) > _MAX_BYTES:
                _fail("journal exceeds size limit")
            envelope = json.loads(raw, object_pairs_hook=_pairs)
            _keys(envelope, ("state", "sha256"))
            if envelope["sha256"] != canonical_sha256(envelope["state"]):
                _fail("journal content digest differs")
            _validate_state(envelope["state"])
            if envelope["state"]["request"]["id"] != request_id:
                _fail("journal filename and request differ")
            if raw != self._encode(envelope["state"]):
                _fail("journal serialization is not canonical")
            return envelope["state"]
        except (ValueError, UnicodeError):
            _fail("journal JSON is malformed")
        finally:
            os.close(fd)

    @staticmethod
    def _encode(state):
        return canonical_json({"state": state, "sha256": canonical_sha256(state)})

    def _save(self, state):
        self._active()
        if not self.writable:
            _fail("journal is open for reading only")
        _validate_state(state)
        encoded = self._encode(state)
        self._write(state["request"]["id"] + ".json", encoded)

    def _write(self, filename, raw):
        self._active()
        if len(raw) > _MAX_BYTES:
            _fail("journal exceeds size limit")
        temporary = ".pending-" + uuid.uuid4().hex
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.directory)
        try:
            with os.fdopen(fd, "wb", closefd=False) as output:
                output.write(raw)
                output.flush()
                os.fsync(fd)
            self._active()
            os.replace(temporary, filename,
                       src_dir_fd=self.directory, dst_dir_fd=self.directory)
            os.fsync(self.directory)
        finally:
            os.close(fd)
            try:
                os.unlink(temporary, dir_fd=self.directory)
            except FileNotFoundError:
                pass

    def read_alias(self, request_id):
        self._active()
        if not _match(_ID, request_id):
            _fail("invalid alias request ID")
        try:
            fd = os.open(request_id + ".alias", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=self.directory)
        except FileNotFoundError:
            return None
        except OSError:
            _fail("request alias is unsafe or unavailable")
        try:
            self._private(fd)
            with os.fdopen(fd, "rb", closefd=False) as source:
                raw = source.read(_MAX_BYTES + 1)
            if len(raw) > _MAX_BYTES:
                _fail("request alias exceeds size limit")
            envelope = json.loads(raw, object_pairs_hook=_pairs)
            _keys(envelope, ("alias", "sha256"))
            alias = envelope["alias"]
            _keys(alias, ("schema", "request", "original_id", "original_digest"))
            validate_request(alias["request"])
            if (alias["schema"] != "lmdj.release-request-alias.v1"
                    or alias["request"]["id"] != request_id
                    or not _match(_ID, alias["original_id"])
                    or alias["original_id"] == request_id
                    or not _match(_DIGEST, alias["original_digest"])
                    or envelope["sha256"] != canonical_sha256(alias)
                    or raw != canonical_json(envelope)):
                _fail("request alias identity or canonical content differs")
            original = self.read(alias["original_id"])
            if original is None or original["request_digest"] != alias["original_digest"]:
                _fail("request alias original is missing or changed")
            if self.read(request_id) is not None:
                _fail("request ID is both an alias and an original")
            fields = ("repository", "actor_id", "policy_digest", "control_revision", "mode", "requested_tag")
            if any(alias["request"][k] != original["request"][k] for k in fields):
                _fail("request alias scope differs from original")
            return alias
        except (ValueError, UnicodeError):
            _fail("request alias JSON is malformed")
        finally:
            os.close(fd)

    def bind_alias(self, request, original):
        self._active()
        validate_request(request)
        _validate_state(original)
        if request["id"] == original["request"]["id"]:
            return
        if self.resolve_active(request) != original:
            _fail("request alias admission changed")
        alias = {"schema":"lmdj.release-request-alias.v1", "request":deepcopy(request),
                 "original_id":original["request"]["id"], "original_digest":original["request_digest"]}
        existing = self.read_alias(request["id"])
        if existing is not None:
            if existing != alias:
                _fail("request alias cannot be rebound")
            return
        self._write(request["id"] + ".alias",
                    canonical_json({"alias":alias, "sha256":canonical_sha256(alias)}))

    def resolve_active(self, request):
        """Read-only admission under the writer lock; never replace authority."""
        self._active()
        validate_request(request)
        alias = self.read_alias(request["id"])
        if alias is not None and alias["request"] != request:
            _fail("alias request ID cannot be rebound to another scope")
        existing = self.read(request["id"])
        if existing is not None:
            if existing["request"] != request:
                _fail("request ID cannot be rebound to another scope")
        active = []
        names = sorted(os.listdir(self.directory))
        for name in names:
            if name.endswith(".alias"):
                if self.read_alias(name[:-6]) is None:
                    _fail("alias inventory changed during admission")
                continue
            if not name.endswith(".json"):
                continue
            state = self.read(name[:-5])
            if state is None:
                _fail("request inventory changed during admission")
            records = state["transitions"]
            complete = len(records) == len(STEPS) and records[-1]["status"] == "verified"
            if state["request"]["repository"] == request["repository"] and not complete:
                active.append(state)
        self._active()
        if sorted(os.listdir(self.directory)) != names:
            _fail("request inventory changed during admission")
        if len(active) > 1:
            _fail("unfinished release inventory is ambiguous")
        if alias is not None:
            if self.read_alias(request["id"]) != alias:
                _fail("request alias changed during admission")
            return self.read(alias["original_id"])
        if existing is not None:
            if self.read(request["id"]) != existing:
                _fail("original release changed during admission")
            return existing
        if not active:
            return None
        original = active[0]
        fields = ("repository", "actor_id", "policy_digest", "control_revision",
                  "mode", "requested_tag")
        if any(original["request"][key] != request[key] for key in fields):
            _fail("unfinished release belongs to another scope")
        if self.read(original["request"]["id"]) != original:
            _fail("original release changed during admission")
        return original

    def create(self, request):
        self._active()
        validate_request(request)
        if self.read_alias(request["id"]) is not None:
            _fail("alias ID must resume its original request, not create a release")
        existing = self.read(request["id"])
        if existing is not None:
            if existing["request"] != request:
                _fail("request ID cannot be rebound to another scope")
            return existing
        for name in os.listdir(self.directory):
            if name.endswith(".json"):
                state = self.read(name[:-5])
                records = state["transitions"]
                complete = len(records) == len(STEPS) and records[-1]["status"] == "verified"
                if state["request"]["repository"] == request["repository"] and not complete:
                    _fail("another release request is unfinished for this repository")
        state = {"schema": "lmdj.release-request.v1", "request": deepcopy(request),
                 "request_digest": canonical_sha256(request), "transitions": []}
        self._save(state)
        return deepcopy(state)

    def begin(self, request_id, step):
        state = self.read(request_id)
        if state is None:
            _fail("release request is missing")
        records = state["transitions"]
        if records and records[-1]["status"] == "intent":
            _fail("outstanding intent needs reconciliation, not another execution")
        if len(records) == len(STEPS) or step != STEPS[len(records)]:
            _fail("transition is not the next release step")
        record = {"step": step,
                  "operation_id": canonical_sha256({"request": state["request_digest"], "step": step}),
                  "status": "intent", "evidence": None}
        records.append(record)
        self._save(state)
        return deepcopy(record)

    def confirm(self, request_id, operation_id, evidence):
        _validate_evidence(evidence)
        state = self.read(request_id)
        if state is None or not state["transitions"]:
            _fail("no transition to reconcile")
        record = state["transitions"][-1]
        if record["operation_id"] != operation_id:
            _fail("confirmation does not match the outstanding operation")
        if record["status"] == "verified":
            if record["evidence"] != evidence:
                _fail("verified transition evidence is immutable")
            return deepcopy(record)
        record.update(status="verified", evidence=deepcopy(evidence))
        self._save(state)
        return deepcopy(record)
