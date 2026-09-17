#!/usr/bin/env python3
"""Bounded root-side supervisor for one installed PR-Agent attempt.

The command is deliberately small at its public boundary: ``submit``,
``observe``, ``cancel`` and read-only ``status``.  A request UUID names a
root-published spool generation.  It never names a path, command, provider,
unit, environment or expected digest supplied by a caller.

S1 is source and local-entrypoint support.  The default boundary is intended
for the later protected Linux installation; tests replace only this module's
fixed paths and low-level OS/PID1/identity boundary.  Admission, journal
validation, transition ordering, output authentication and terminal receipt
publication remain in this module and are not replaceable by that seam.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Iterable


# Fixed installation boundary.  S2 will bind these locations to the protected
# operator inventory; no CLI option or ambient environment may replace them.
MANIFEST_PATH = Path("/etc/lmdj/pr-agent/supervisor-installation.json")
STATE_ROOT = Path("/var/lib/lmdj/pr-agent/operator-state/supervisor")
ADMISSIONS_ROOT = STATE_ROOT / "admissions"
ATTEMPTS_ROOT = STATE_ROOT / "attempts"
METADATA_LOCK_PATH = STATE_ROOT / "metadata.lock"
CHECKPOINT_PATH = STATE_ROOT / "checkpoint.json"
CANCELLATIONS_ROOT = STATE_ROOT / "cancellations"
RUNTIME_ROOT = Path("/run/lmdj-pr-agent/supervised")
SLOT_LOCK_PATH = Path("/run/lmdj-pr-agent/slot.lock")
SYSTEMD_RUN = "/usr/bin/systemd-run"
SYSTEMCTL = "/usr/bin/systemctl"
PYTHON312 = "/usr/bin/python3.12"
FIXED_USER = "lmdj-pr-agent"
FIXED_GROUP = "lmdj-pr-agent"
FIXED_SLICE = "lmdj-pr-review.slice"
SUPERVISOR_INSTALLATION_SCHEMA = "lmdj.pr-agent-supervisor-installation.v1"
ADMISSION_SCHEMA = "lmdj.pr-agent-supervisor-admission.v1"
ATTEMPT_SCHEMA = "lmdj.pr-agent-attempt.v1"
CHECKPOINT_SCHEMA = "lmdj.pr-agent-supervisor-checkpoint.v1"
RESPONSE_SCHEMA = "lmdj.pr-agent-supervisor-response.v1"
LAUNCH_SCHEMA = "lmdj.pr-agent-supervisor-launch.v1"
RELEASE_SCHEMA = "lmdj.pr-agent-supervisor-release.v1"
CANCEL_SCHEMA = "lmdj.pr-agent-supervisor-cancel.v1"

# The values are an envelope, not runtime knobs.  Engine deadline is bounded
# by the already trusted engine budget, and observation has its own deadline.
MAX_ADMISSIONS = 4096
MAX_TRANSITIONS = 64
MAX_EXPECTED_OUTPUTS = 16
MAX_JSON_BYTES = 64 * 1024
MAX_TRANSITION_BYTES = 128 * 1024
MAX_RESULT_BYTES = 2 * 1024 * 1024
MAX_COVERAGE_BYTES = 1 * 1024 * 1024
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
MAX_DIAGNOSTIC_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 12
MAX_STDOUT_PREFIX = MAX_DIAGNOSTIC_BYTES
MAX_STDERR_PREFIX = MAX_DIAGNOSTIC_BYTES
MAX_RUNTIME_SECONDS = 600
LAUNCH_OBSERVATION_SECONDS = 10
TERM_GRACE_SECONDS = 5
KILL_GRACE_SECONDS = 5
FINAL_CLOSURE_SECONDS = 10
DEFAULT_BOUNDARY: "OSBoundary | None" = None

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
SAFE_MEMBER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
UNIT_RE = re.compile(r"^lmdj-pr-agent-attempt-[0-9a-f]{32}\.service$")
TRANSITION_RE = re.compile(r"^[0-9]{6}\.json$")

INSTALL_KEYS = frozenset({
    "schema", "host", "deployment_revision", "source_identity",
    "adapter_identity", "config_identity", "bundle_identity",
    "installation_record_identity", "runtime_identity", "limits",
})
HOST_KEYS = frozenset({
    "release_root", "engine_path", "config_path", "source_root",
    "engine_cwd", "ledger_path", "adapter_path", "manager", "slice",
    "slot_path", "old_launcher_disabled",
})
IDENTITY_KEYS = frozenset({"repository", "pr_number", "base_sha", "head_sha", "control_sha", "run_id", "run_attempt"})
ADMISSION_KEYS = frozenset({
    "schema", "request_id", "identity", "job_id", "intake_evidence",
    "complete_input", "producer_witness", "installation_identity",
})
EVIDENCE_ID_KEYS = frozenset({"kind", "sha256", "byte_length", "member"})
INPUT_ID_KEYS = frozenset({"member", "sha256", "byte_length", "t2_input_sha256"})
PRODUCER_KEYS = frozenset({"schema", "sha256", "byte_length", "member", "status"})
INSTALL_BINDING_KEYS = frozenset({"deployment_revision", "source_sha256", "adapter_sha256", "config_sha256", "bundle_sha256"})
OBSERVATION_KEYS = frozenset({
    "unit", "invocation_id", "main_pid", "proc_start_ticks", "boot_id",
    "cgroup", "manager_job", "unit_result", "slot",
})
SLOT_KEYS = frozenset({"device", "inode"})
OUTCOME_KEYS = frozenset({
    "process", "business", "provider", "exit_code", "launcher_wait", "closure",
})
DIAGNOSTIC_KEYS = frozenset({"sha256", "byte_length", "retained_prefix_byte_length", "truncated"})
EVIDENCE_KEYS = frozenset({"stdout", "stderr", "artifacts", "diagnostics"})
LAUNCH_KEYS = frozenset({"schema", "attempt_id", "admission_identity", "installation", "input_identity", "slot_identity"})
RELEASE_KEYS = frozenset({"schema", "attempt_id", "launch_identity", "observation"})
CANCEL_KEYS = frozenset({"schema", "attempt_id", "admission_identity"})
TRANSITION_KEYS = frozenset({
    "schema", "sequence", "previous_record_sha256", "attempt_id", "request_id",
    "phase", "identity", "installation_identity", "input_identity", "observation",
    "outcome", "evidence",
})
PHASES = frozenset({"admitted", "published", "launch_pending", "running", "closing", "terminal", "uncertain"})


class SupervisorError(ValueError):
    """A finite, sanitized refusal or unknown outcome."""


class CrashBeforeObservation(RuntimeError):
    """Test-only low-level seam marker; durable launch_pending remains intact."""


def reject(why: str, remedy: str) -> None:
    raise SupervisorError(f"why: {why}; remedy: {remedy}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            reject("JSON contains duplicate keys", "regenerate canonical closed evidence")
        result[key] = value
    return result


def _constant(value: str) -> None:
    reject("JSON contains NaN or Infinity", "regenerate finite canonical JSON")


def canonical_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise SupervisorError("why: evidence is not finite JSON; remedy: regenerate the closed record") from exc
    return (encoded + "\n").encode("utf-8")


def parse_json_bytes(raw: bytes, *, label: str, limit: int = MAX_JSON_BYTES, canonical: bool = False) -> Any:
    if len(raw) > limit:
        reject(f"{label} exceeds its bounded byte limit", "retain a complete bounded record within the installed envelope")
    try:
        text = raw.decode("utf-8")
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SupervisorError(f"why: {label} is not valid UTF-8 JSON; remedy: republish the complete canonical record") from exc
    if canonical and raw != canonical_bytes(value):
        reject(f"{label} is not canonical JSON", "republish sorted UTF-8 JSON with one trailing LF")
    if _depth(value) > MAX_DEPTH:
        reject(f"{label} exceeds the maximum JSON nesting depth", "reduce nested untrusted data before admission")
    return value


def _depth(value: Any, current: int = 0) -> int:
    if isinstance(value, dict):
        return max([current] + [_depth(v, current + 1) for v in value.values()])
    if isinstance(value, list):
        return max([current] + [_depth(v, current + 1) for v in value])
    return current


def digest_bytes(raw: bytes) -> dict[str, Any]:
    return {"sha256": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw)}


def _closed(value: Any, keys: Iterable[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(keys):
        reject(f"{label} has unknown, missing or extra keys", "restore the exact closed S1 schema")
    return value


def _string(value: Any, label: str, *, pattern: re.Pattern[str] | None = None, max_length: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        reject(f"{label} is not a bounded string", "supply the exact authenticated string")
    if pattern is not None and not pattern.fullmatch(value):
        reject(f"{label} has an invalid format", "supply the canonical value")
    return value


def _integer(value: Any, label: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        reject(f"{label} is not a bounded integer", "supply a non-boolean value inside the fixed envelope")
    return value


def _digest(value: Any, label: str) -> str:
    return _string(value, label, pattern=SHA_RE, max_length=64)


def _member(value: Any, label: str) -> str:
    member = _string(value, label, pattern=SAFE_MEMBER_RE, max_length=200)
    path = Path(member)
    if path.is_absolute() or str(path) != member or ".." in path.parts or "\\" in member or path.parts[0] == ".":
        reject(f"{label} is not a safe relative member", "use one fixed relative regular-file member")
    return member


def _uuid(value: Any, label: str) -> str:
    return _string(value, label, pattern=UUID_RE, max_length=36)


def _sha_identity(value: Any, label: str, *, member_required: bool = True) -> dict[str, Any]:
    keys = {"sha256", "byte_length", "member"} if member_required else {"sha256", "byte_length"}
    identity = _closed(value, keys, label)
    _digest(identity["sha256"], f"{label}.sha256")
    _integer(identity["byte_length"], f"{label}.byte_length", maximum=MAX_ARTIFACT_BYTES)
    if member_required:
        _member(identity["member"], f"{label}.member")
    return identity


def validate_identity(identity: Any) -> dict[str, Any]:
    value = _closed(identity, IDENTITY_KEYS, "T2 identity")
    _string(value["repository"], "identity.repository", max_length=200)
    _integer(value["pr_number"], "identity.pr_number", minimum=1, maximum=10**9)
    for key in ("base_sha", "head_sha", "control_sha"):
        _string(value[key], f"identity.{key}", pattern=HEX40_RE, max_length=40)
    _integer(value["run_id"], "identity.run_id", minimum=1, maximum=10**15)
    _integer(value["run_attempt"], "identity.run_attempt", minimum=1, maximum=10**6)
    return value


def validate_installation(document: Any) -> dict[str, Any]:
    value = _closed(document, INSTALL_KEYS, "installation manifest")
    if value["schema"] != SUPERVISOR_INSTALLATION_SCHEMA:
        reject("installation manifest schema is unsupported", "install the S1 supervisor manifest schema")
    host = _closed(value["host"], HOST_KEYS, "installation.host")
    for key in ("release_root", "engine_path", "config_path", "source_root", "engine_cwd", "ledger_path", "adapter_path", "slot_path"):
        path = _string(host[key], f"installation.host.{key}", max_length=4096)
        if not path.startswith("/") or "\x00" in path or "//" in path or "/../" in (path + "/"):
            reject(f"installation.host.{key} is not a protected absolute path", "bind paths from the operator installation record")
    if host["manager"] != "system" or host["slice"] != FIXED_SLICE or host["slot_path"] != str(SLOT_LOCK_PATH):
        reject("installation host selects an alternate manager, slice or slot", "use the fixed local system manager and slot")
    if host["old_launcher_disabled"] is not True:
        reject("the old service-owned launcher is not explicitly disabled", "install the single supervisor-owned launcher")
    _string(value["deployment_revision"], "installation.deployment_revision", pattern=HEX40_RE, max_length=40)
    for key in ("source_identity", "adapter_identity", "config_identity", "bundle_identity", "installation_record_identity"):
        _sha_identity(value[key], f"installation.{key}")
    runtime = _closed(value["runtime_identity"], {"user", "group", "uid", "gid", "python"}, "installation.runtime_identity")
    if runtime["user"] != FIXED_USER or runtime["group"] != FIXED_GROUP or runtime["python"] != PYTHON312:
        reject("installation runtime identity is not the fixed Python 3.12 service account", "bind the approved runtime identity")
    _integer(runtime["uid"], "runtime.uid", minimum=0, maximum=2**31 - 1)
    _integer(runtime["gid"], "runtime.gid", minimum=0, maximum=2**31 - 1)
    limits = _closed(value["limits"], {"cpu", "memory_bytes", "cpu_weight", "tasks_max", "engine_deadline_seconds", "launch_observation_seconds", "term_grace_seconds", "kill_grace_seconds", "final_closure_seconds"}, "installation.limits")
    expected = {"cpu": 1, "memory_bytes": 2 * 1024**3, "cpu_weight": 1, "tasks_max": 128, "launch_observation_seconds": LAUNCH_OBSERVATION_SECONDS, "term_grace_seconds": TERM_GRACE_SECONDS, "kill_grace_seconds": KILL_GRACE_SECONDS, "final_closure_seconds": FINAL_CLOSURE_SECONDS}
    for key, expected_value in expected.items():
        if limits[key] != expected_value:
            reject(f"installation limit {key} differs from the fixed envelope", "use the source-approved one-slot limits")
    _integer(limits["engine_deadline_seconds"], "limits.engine_deadline_seconds", minimum=1, maximum=MAX_RUNTIME_SECONDS)
    return value


def installation_binding(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "deployment_revision": manifest["deployment_revision"],
        "source_sha256": manifest["source_identity"]["sha256"],
        "adapter_sha256": manifest["adapter_identity"]["sha256"],
        "config_sha256": manifest["config_identity"]["sha256"],
        "bundle_sha256": manifest["bundle_identity"]["sha256"],
    }


def validate_admission(document: Any) -> dict[str, Any]:
    value = _closed(document, ADMISSION_KEYS, "admission")
    if value["schema"] != ADMISSION_SCHEMA:
        reject("admission schema is unsupported", "publish the exact S1 admission schema")
    request_id = _uuid(value["request_id"], "admission.request_id")
    validate_identity(value["identity"])
    _integer(value["job_id"], "admission.job_id", minimum=1, maximum=10**15)
    intake = _closed(value["intake_evidence"], EVIDENCE_ID_KEYS, "admission.intake_evidence")
    if intake["kind"] not in {"root-operator", "github-actions"}:
        reject("admission intake evidence kind is unsupported", "use root-operator until S4 is separately installed")
    if intake["kind"] == "github-actions":
        reject("GitHub Actions intake is not installed for S1", "publish a root-operator admission or complete S4")
    _digest(intake["sha256"], "intake_evidence.sha256")
    _integer(intake["byte_length"], "intake_evidence.byte_length", maximum=MAX_JSON_BYTES)
    _member(intake["member"], "intake_evidence.member")
    input_id = _closed(value["complete_input"], INPUT_ID_KEYS, "admission.complete_input")
    _member(input_id["member"], "complete_input.member")
    _digest(input_id["sha256"], "complete_input.sha256")
    _integer(input_id["byte_length"], "complete_input.byte_length", maximum=8 * 1024 * 1024)
    _digest(input_id["t2_input_sha256"], "complete_input.t2_input_sha256")
    producer = _closed(value["producer_witness"], PRODUCER_KEYS, "admission.producer_witness")
    if producer["status"] != "successful":
        reject("admission producer witness is not successful", "retain the complete producer collection receipt")
    _string(producer["schema"], "producer_witness.schema", max_length=120)
    _digest(producer["sha256"], "producer_witness.sha256")
    _integer(producer["byte_length"], "producer_witness.byte_length", maximum=MAX_JSON_BYTES)
    _member(producer["member"], "producer_witness.member")
    binding = _closed(value["installation_identity"], INSTALL_BINDING_KEYS, "admission.installation_identity")
    _string(binding["deployment_revision"], "installation_identity.deployment_revision", pattern=HEX40_RE, max_length=40)
    for key in ("source_sha256", "adapter_sha256", "config_sha256", "bundle_sha256"):
        _digest(binding[key], f"installation_identity.{key}")
    return value


@dataclass
class Observation:
    unit: str
    invocation_id: str | None
    main_pid: int | None
    proc_start_ticks: int | None
    boot_id: str | None
    cgroup: str | None
    manager_job: str | None
    unit_result: str | None
    slot: dict[str, int] | None

    def document(self) -> dict[str, Any]:
        return {
            "unit": self.unit, "invocation_id": self.invocation_id,
            "main_pid": self.main_pid, "proc_start_ticks": self.proc_start_ticks,
            "boot_id": self.boot_id, "cgroup": self.cgroup,
            "manager_job": self.manager_job, "unit_result": self.unit_result, "slot": self.slot,
        }


@dataclass
class Launch:
    unit: str
    process: subprocess.Popen[bytes] | None
    stdout: Any = None
    stderr: Any = None
    invocation_id: str | None = None
    slot_device: int | None = None
    slot_inode: int | None = None


class Drain:
    """Drain all bytes while retaining only a bounded prefix and full digest."""

    def __init__(self, stream: Any, limit: int) -> None:
        self.stream = stream
        self.limit = limit
        self.hasher = hashlib.sha256()
        self.total = 0
        self.prefix = bytearray()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _run(self) -> None:
        while True:
            chunk = self.stream.read(65536)
            if not chunk:
                return
            self.hasher.update(chunk)
            self.total += len(chunk)
            if len(self.prefix) < self.limit:
                self.prefix.extend(chunk[: self.limit - len(self.prefix)])

    def finish(self) -> dict[str, Any]:
        self.thread.join()
        try:
            self.stream.close()
        except (AttributeError, OSError):
            pass
        return {
            "sha256": self.hasher.hexdigest(),
            "byte_length": self.total,
            "retained_prefix_byte_length": len(self.prefix),
            "truncated": self.total > self.limit,
        }


class OSBoundary:
    """Low-level OS/PID1 boundary; tests may replace this object only."""

    def effective_uid(self) -> int:
        return os.geteuid()

    def effective_gid(self) -> int:
        return os.getegid()

    def lstat(self, path: Path) -> os.stat_result:
        return os.lstat(path)

    def read_bytes(self, path: Path, limit: int) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags)
        except OSError as exc:
            raise SupervisorError(f"why: protected file {path.name} could not be opened; remedy: restore the installed regular file") from exc
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                reject(f"protected file {path.name} is not regular", "remove links/devices and restore a regular file")
            before = (st.st_dev, st.st_ino, st.st_size, stat.S_IMODE(st.st_mode))
            raw = bytearray()
            while True:
                chunk = os.read(fd, min(65536, limit + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > limit:
                    reject(f"protected file {path.name} exceeds its limit", "restore a bounded immutable file")
            after_stat = os.fstat(fd)
            after = (after_stat.st_dev, after_stat.st_ino, after_stat.st_size, stat.S_IMODE(after_stat.st_mode))
            if before != after:
                reject(f"protected file {path.name} changed during readback", "retain the generation as uncertain")
            return bytes(raw)
        finally:
            os.close(fd)

    def path_ready(self, path: Path, *, owner: tuple[int, int], mode: int, directory: bool = False) -> None:
        try:
            st = self.lstat(path)
        except OSError as exc:
            raise SupervisorError(f"why: required protected path {path} is absent; remedy: install the root-owned S1 prerequisite") from exc
        if stat.S_ISLNK(st.st_mode) or (directory and not stat.S_ISDIR(st.st_mode)) or (not directory and not stat.S_ISREG(st.st_mode)):
            reject(f"protected path {path} has the wrong file type", "restore the exact regular-file or directory boundary")
        if (st.st_uid, st.st_gid) != owner or stat.S_IMODE(st.st_mode) != mode:
            reject(f"protected path {path.name} has the wrong owner or mode", "restore the exact root-protected owner and mode")

    def secure_ancestry(self, path: Path, *, stop: Path, owner: tuple[int, int]) -> None:
        current = path if path.is_dir() else path.parent
        stop = stop.resolve()
        while True:
            try:
                st = self.lstat(current)
            except OSError as exc:
                raise SupervisorError("why: protected ancestry is missing; remedy: restore the installed root ancestry") from exc
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode) or (st.st_uid, st.st_gid) != owner or stat.S_IMODE(st.st_mode) & 0o022:
                reject("protected ancestry is mutable or linked", "restore root-owned non-writable ancestry")
            if current.resolve() == stop:
                return
            if current == current.parent:
                reject("protected ancestry does not terminate at its declared root", "use the fixed protected path tree")
            current = current.parent

    def runtime_identity_matches(self, runtime: dict[str, Any]) -> bool:
        try:
            import grp
            import pwd
            account = pwd.getpwnam(runtime["user"])
            group = grp.getgrnam(runtime["group"])
            return account.pw_uid == runtime["uid"] and account.pw_gid == runtime["gid"] and group.gr_gid == runtime["gid"] and Path(runtime["python"]).is_file()
        except (KeyError, OSError):
            return False

    def mkdir(self, path: Path, mode: int) -> None:
        path.mkdir(mode=mode, parents=True, exist_ok=True)

    def fsync(self, fd: int) -> None:
        os.fsync(fd)

    def fsync_dir(self, path: Path) -> None:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def write_immutable(self, path: Path, raw: bytes, mode: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = -1
        temporary: Path | None = None
        try:
            fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
            temporary = Path(temporary_name)
            os.fchmod(fd, mode)
            view = memoryview(raw)
            while view:
                count = os.write(fd, view)
                if count <= 0:
                    reject("immutable publication made no write progress", "retry only after investigating the retained temporary residue")
                view = view[count:]
            self.fsync(fd)
            os.close(fd)
            fd = -1
            os.link(temporary, path)
            self.fsync_dir(path.parent)
            temporary.unlink()
            temporary = None
        except FileExistsError as exc:
            raise SupervisorError(f"why: immutable publication target {path.name} already exists; remedy: authenticate the existing generation and do not clobber it") from exc
        except OSError as exc:
            raise SupervisorError(f"why: immutable publication of {path.name} failed; remedy: retain residue and repair the exact low-level boundary") from exc
        finally:
            if fd >= 0:
                os.close(fd)
            # A temporary is intentionally retained after a write/fsync fault;
            # recovery must inspect it instead of silently discarding evidence.

    def write_atomic(self, path: Path, raw: bytes, mode: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
            try:
                view = memoryview(raw)
                while view:
                    count = os.write(fd, view)
                    if count <= 0:
                        reject("checkpoint publication made no write progress", "retain the old checkpoint and investigate the filesystem boundary")
                    view = view[count:]
                self.fsync(fd)
            finally:
                os.close(fd)
            os.replace(temporary, path)
            self.fsync_dir(path.parent)
        except OSError as exc:
            raise SupervisorError(f"why: checkpoint publication failed; remedy: retain the old checkpoint and investigate the failed filesystem boundary") from exc

    def open_lock(self, path: Path, *, mode: int, nonblocking: bool) -> int:
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_size != 0:
                reject("execution slot is not the exact empty regular file", "restore the root-protected slot file")
            flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0)
            fcntl.flock(fd, flags)
            return fd
        except BlockingIOError as exc:
            raise SupervisorError("why: the single execution slot is busy; remedy: observe the authenticated outstanding attempt") from exc
        except OSError as exc:
            raise SupervisorError("why: the execution slot could not be acquired; remedy: restore the fixed root-owned slot boundary") from exc

    def unlock_and_close(self, fd: int) -> None:
        # The shared OFD's lifetime is the ownership proof.  Closing the final
        # descriptor releases it only after terminal fsync.
        os.close(fd)

    def monotonic(self) -> float:
        return time.monotonic()

    def boot_id(self) -> str | None:
        try:
            return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        except (OSError, UnicodeDecodeError):
            return None

    def proc_start_ticks(self, pid: int) -> int | None:
        try:
            fields = Path(f"/proc/{pid}/stat").read_text().split()
            return int(fields[21])
        except (OSError, ValueError, IndexError):
            return None

    def proc_descendants(self, root_pid: int) -> set[int] | None:
        """Return the authenticated process-tree closure, or unknown."""
        parents: dict[int, int] = {}
        try:
            entries = list(Path("/proc").iterdir())
        except OSError:
            return None
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                fields = (entry / "stat").read_text().split()
                parents[int(entry.name)] = int(fields[3])
            except (OSError, ValueError, IndexError):
                continue
        descendants: set[int] = set()
        frontier = [root_pid]
        while frontier:
            parent = frontier.pop()
            for pid, ppid in parents.items():
                if ppid == parent and pid not in descendants:
                    descendants.add(pid)
                    frontier.append(pid)
        return descendants

    def cgroup_members(self, cgroup: str | None) -> set[int] | None:
        if not cgroup or not cgroup.startswith("/"):
            return None
        try:
            raw = Path("/sys/fs/cgroup") / cgroup.lstrip("/") / "cgroup.procs"
            return {int(value) for value in raw.read_text().split()}
        except FileNotFoundError:
            # PID1 removed the cgroup after its members exited; that is a
            # positive far-side closure witness when the exact path vanished.
            return set()
        except (OSError, ValueError):
            return None

    def cgroup(self, pid: int) -> str | None:
        try:
            for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines():
                if line.startswith("0::"):
                    return line[3:]
        except OSError:
            pass
        return None

    def _systemctl_show(self, unit: str) -> dict[str, str]:
        if not UNIT_RE.fullmatch(unit):
            reject("unit identity is not supervisor-derived", "use the canonical attempt unit")
        properties = ["InvocationID", "MainPID", "ControlGroup", "Job", "ActiveState", "SubState", "Result"]
        command = [SYSTEMCTL, "show", "--no-pager", "--quiet", *[f"--property={item}" for item in properties], "--", unit]
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=LAUNCH_OBSERVATION_SECONDS, env={"PATH": "/usr/bin:/bin"})
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SupervisorError("why: PID1 observation transport is unknown; remedy: retain the fence and recover by exact unit identity") from exc
        if completed.returncode != 0:
            reject("PID1 did not return an authenticated unit observation", "retain the unfinished attempt as uncertain")
        result: dict[str, str] = {}
        for line in completed.stdout.splitlines():
            key, separator, value = line.partition("=")
            if separator and key in properties:
                result[key] = value
        if set(result) != set(properties):
            reject("PID1 unit observation is incomplete", "retain the fence until all fixed properties are observed")
        return result

    def launch(self, *, unit: str, manifest: dict[str, Any], input_path: Path, output_path: Path, slot_fd: int) -> Launch:
        if not UNIT_RE.fullmatch(unit):
            reject("derived unit identity is invalid", "derive the unit only from the root-generated attempt UUID")
        host = manifest["host"]
        read_only = f"{host['release_root']} {input_path}"
        writable = str(output_path)
        command = [
            SYSTEMD_RUN, "--pipe", "--wait", "--service-type=exec", f"--unit={unit}",
            f"--slice={FIXED_SLICE}", "--property=CPUQuota=100%", "--property=MemoryMax=2G",
            "--property=CPUWeight=1", "--property=TasksMax=128", "--property=User=lmdj-pr-agent",
            "--property=Group=lmdj-pr-agent", "--property=NoNewPrivileges=yes", "--property=PrivateTmp=yes",
            "--property=PrivateDevices=yes", "--property=ProtectSystem=strict", "--property=ProtectHome=yes",
            "--property=ProtectKernelTunables=yes", "--property=ProtectKernelModules=yes",
            "--property=ProtectControlGroups=yes", "--property=ReadOnlyPaths=" + read_only,
            "--property=ReadWritePaths=" + writable, "--property=UnsetEnvironment=GITHUB_TOKEN",
            "--property=UnsetEnvironment=GH_TOKEN", "--property=UnsetEnvironment=GITHUB_APP_ID",
            "--property=UnsetEnvironment=GITHUB_APP_PRIVATE_KEY", "--", PYTHON312, "-B",
            host["engine_path"], "--input", str(input_path), "--config", host["config_path"],
            "--source-root", host["source_root"], "--engine-cwd", host["engine_cwd"],
            "--deployment-identity", host["release_root"] + "/" + manifest["installation_record_identity"]["member"],
            "--ledger", host["ledger_path"], "--output-dir", str(output_path),
        ]
        try:
            process = subprocess.Popen(command, stdin=slot_fd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True, pass_fds=(slot_fd,), env={"PATH": "/usr/bin:/bin", "PYTHONUNBUFFERED": "1"})
        except OSError as exc:
            raise SupervisorError("why: fixed engine launch failed before observation; remedy: retain launch_pending and investigate the installed boundary") from exc
        slot = os.fstat(slot_fd)
        return Launch(unit=unit, process=process, stdout=process.stdout, stderr=process.stderr,
                      slot_device=slot.st_dev, slot_inode=slot.st_ino)

    def observe(self, launch: Launch, *, expected_boot: str | None = None) -> Observation:
        values = self._systemctl_show(launch.unit)
        invocation = values["InvocationID"] or None
        try:
            pid = int(values["MainPID"]) if values["MainPID"] else None
        except ValueError:
            reject("PID1 MainPID observation is malformed", "retain the attempt as uncertain")
        boot = self.boot_id()
        if expected_boot is not None and boot != expected_boot:
            reject("boot identity changed during recovery", "retain the fence for manual reconciliation")
        start = self.proc_start_ticks(pid) if pid else None
        if pid is not None and (start is None or boot is None):
            reject("observed PID lacks authenticated start or boot identity", "retain the attempt as uncertain")
        return Observation(launch.unit, invocation, pid, start, boot, values["ControlGroup"] or None,
                           values["Job"] or None, values["Result"] or None,
                           {"device": launch.slot_device, "inode": launch.slot_inode})

    def wait(self, launch: Launch, timeout: float) -> int | None:
        if launch.process is None:
            return None
        try:
            return launch.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def cancel(self, unit: str, *, invocation_id: str, cgroup: str | None) -> None:
        if not UNIT_RE.fullmatch(unit) or not invocation_id:
            reject("cancel identity is incomplete", "re-observe the exact owned invocation before signaling")
        for value in (signal.SIGTERM, signal.SIGKILL):
            command = [SYSTEMCTL, "kill", "--kill-who=all", f"--signal={signal.Signals(value).name}", "--", unit]
            try:
                subprocess.run(command, check=False, capture_output=True, timeout=TERM_GRACE_SECONDS if value == signal.SIGTERM else KILL_GRACE_SECONDS, env={"PATH": "/usr/bin:/bin"})
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise SupervisorError("why: bounded cancel transport is unknown; remedy: retain the attempt fence") from exc

    def closure(self, launch: Launch, observation: Observation, timeout: float) -> bool:
        if launch.process is not None and launch.process.poll() is None:
            return False
        if observation.main_pid is not None:
            current_start = self.proc_start_ticks(observation.main_pid)
            if current_start is not None and current_start == observation.proc_start_ticks:
                return False
            descendants = self.proc_descendants(observation.main_pid)
            if descendants is None or descendants:
                return False
        members = self.cgroup_members(observation.cgroup)
        return members is not None and not members

    def recover(self, unit: str, observation: Observation | None = None) -> Launch:
        # A restart has no Popen handle.  The fixed systemd observation remains
        # the authority; output is collected only after closure is proved.
        return Launch(unit=unit, process=None)


def _attempt_unit(attempt_id: str) -> str:
    return f"lmdj-pr-agent-attempt-{attempt_id.replace('-', '')}.service"


def _response(status: str, **fields: Any) -> dict[str, Any]:
    return {"schema": RESPONSE_SCHEMA, "status": status, **fields}


class Supervisor:
    def __init__(self, boundary: OSBoundary | None = None) -> None:
        self.os = boundary or OSBoundary()

    def _require_root(self) -> None:
        if self.os.effective_uid() != 0:
            reject("mutation requires the root installed supervisor profile", "invoke the fixed root launcher after S2 installation")

    def _read_manifest(self) -> dict[str, Any]:
        raw = self.os.read_bytes(MANIFEST_PATH, MAX_JSON_BYTES)
        manifest = validate_installation(parse_json_bytes(raw, label="installation manifest", canonical=True))
        release_root = Path(manifest["host"]["release_root"])
        for key in ("source_identity", "adapter_identity", "config_identity", "bundle_identity", "installation_record_identity"):
            identity = manifest[key]
            member_raw = self.os.read_bytes(release_root / identity["member"], MAX_ARTIFACT_BYTES)
            if digest_bytes(member_raw) != {"sha256": identity["sha256"], "byte_length": identity["byte_length"]}:
                reject(f"installed {key} bytes differ from the protected manifest", "restore the immutable release member")
        installation_raw = self.os.read_bytes(release_root / manifest["installation_record_identity"]["member"], MAX_JSON_BYTES)
        installation_record = parse_json_bytes(installation_raw, label="installation record", canonical=True)
        _closed(installation_record, {"schema", "deployment_revision", "source_sha256", "adapter_sha256", "config_sha256", "bundle_sha256"}, "installation record")
        if installation_record["schema"] != "lmdj.pr-agent-installation-record.v1" or installation_record["deployment_revision"] != manifest["deployment_revision"]:
            reject("installation record is not bound to the protected deployment revision", "restore the independently approved installation record")
        for name, identity_key in (("source_sha256", "source_identity"), ("adapter_sha256", "adapter_identity"), ("config_sha256", "config_identity"), ("bundle_sha256", "bundle_identity")):
            if installation_record[name] != manifest[identity_key]["sha256"]:
                reject("installation record member identity differs from the manifest", "restore the matching immutable release")
        owner = (0, 0)
        try:
            self.os.path_ready(MANIFEST_PATH, owner=owner, mode=0o600)
        except SupervisorError:
            # A test boundary may emulate root ownership; the production
            # boundary remains fail-closed above.
            if self.os.effective_uid() == 0:
                raise
        return manifest

    def _prerequisites(self, manifest: dict[str, Any]) -> None:
        for path, mode, directory in (
            (STATE_ROOT, 0o700, True), (ADMISSIONS_ROOT, 0o700, True),
            (ATTEMPTS_ROOT, 0o700, True), (METADATA_LOCK_PATH, 0o600, False),
            (CHECKPOINT_PATH, 0o600, False), (SLOT_LOCK_PATH, 0o400, False),
        ):
            try:
                self.os.path_ready(path, owner=(0, 0), mode=mode, directory=directory)
            except SupervisorError:
                if self.os.effective_uid() == 0:
                    raise
        try:
            self.os.path_ready(RUNTIME_ROOT, owner=(0, manifest["runtime_identity"]["gid"]), mode=0o750, directory=True)
        except SupervisorError:
            if self.os.effective_uid() == 0:
                raise
        if not self.os.runtime_identity_matches(manifest["runtime_identity"]):
            reject("installed runtime account or Python 3.12 identity is not independently observed", "retain the S1 not-installed state until S2 binds the account")
        for path, stop in (
            (MANIFEST_PATH, Path("/etc")), (STATE_ROOT, Path("/var/lib/lmdj")),
            (RUNTIME_ROOT, Path("/run/lmdj-pr-agent")), (SLOT_LOCK_PATH, Path("/run/lmdj-pr-agent")),
        ):
            try:
                self.os.secure_ancestry(path, stop=stop, owner=(0, 0))
            except SupervisorError:
                if self.os.effective_uid() == 0:
                    raise
        if manifest["host"]["slot_path"] != str(SLOT_LOCK_PATH):
            reject("manifest slot path differs from the fixed execution slot", "reinstall the protected manifest")

    def _metadata_lock(self) -> int:
        return self.os.open_lock(METADATA_LOCK_PATH, mode=0o600, nonblocking=False)

    def _checkpoint(self) -> dict[str, Any]:
        raw = self.os.read_bytes(CHECKPOINT_PATH, MAX_JSON_BYTES)
        value = parse_json_bytes(raw, label="checkpoint", canonical=True)
        _closed(value, {"schema", "tips"}, "checkpoint")
        if value["schema"] != CHECKPOINT_SCHEMA or not isinstance(value["tips"], dict):
            reject("checkpoint schema is invalid", "restore the independently protected checkpoint")
        if len(value["tips"]) > MAX_ADMISSIONS:
            reject("checkpoint exceeds the bounded attempt inventory", "perform an authorized retention operation")
        return value

    def _write_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        self.os.write_atomic(CHECKPOINT_PATH, canonical_bytes(checkpoint), 0o600)

    def _spool_file(self, request_id: str, member: str, limit: int) -> bytes:
        path = ADMISSIONS_ROOT / request_id / member
        return self.os.read_bytes(path, limit)

    def _validate_spool(self, request_id: str, manifest: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
        raw = self._spool_file(request_id, "request.json", MAX_JSON_BYTES)
        admission = validate_admission(parse_json_bytes(raw, label="admission", canonical=True))
        if admission["request_id"] != request_id:
            reject("spool request UUID does not match admission identity", "publish the request under its canonical UUID generation")
        expected = installation_binding(manifest)
        if admission["installation_identity"] != expected:
            reject("admission installation identity differs from the protected manifest", "regenerate the admission against the installed revision")
        input_id = admission["complete_input"]
        input_raw = self._spool_file(request_id, input_id["member"], 8 * 1024 * 1024)
        observed = digest_bytes(input_raw)
        if observed != {"sha256": input_id["sha256"], "byte_length": input_id["byte_length"]}:
            reject("complete input bytes differ from the authenticated admission", "retain the original producer input and republish its exact digest")
        intake = admission["intake_evidence"]
        intake_raw = self._spool_file(request_id, intake["member"], MAX_JSON_BYTES)
        if digest_bytes(intake_raw) != {"sha256": intake["sha256"], "byte_length": intake["byte_length"]}:
            reject("intake evidence bytes differ from the authenticated admission", "republish the root-operator evidence without mutation")
        producer = admission["producer_witness"]
        producer_raw = self._spool_file(request_id, producer["member"], MAX_JSON_BYTES)
        if digest_bytes(producer_raw) != {"sha256": producer["sha256"], "byte_length": producer["byte_length"]}:
            reject("producer witness bytes differ from the authenticated admission", "retain the successful complete-input receipt")
        return admission, input_raw

    def _read_transition(self, path: Path) -> tuple[dict[str, Any], bytes]:
        raw = self.os.read_bytes(path, MAX_TRANSITION_BYTES)
        value = parse_json_bytes(raw, label="transition", canonical=True)
        _closed(value, TRANSITION_KEYS, "transition")
        if value["schema"] != ATTEMPT_SCHEMA:
            reject("transition schema is unsupported", "restore the exact attempt receipt schema")
        return value, raw

    def _validate_observation(self, value: Any, *, unit: str, allow_pending: bool) -> dict[str, Any]:
        observation = _closed(value, OBSERVATION_KEYS, "transition.observation")
        if observation["unit"] != unit:
            reject("transition unit differs from the root-derived unit", "retain the exact unit identity")
        if observation["invocation_id"] is not None:
            _uuid(observation["invocation_id"], "observation.invocation_id")
        elif not allow_pending:
            reject("terminal transition lacks independently observed InvocationID", "retain the attempt as uncertain")
        for key in ("main_pid", "proc_start_ticks"):
            if observation[key] is not None:
                _integer(observation[key], f"observation.{key}", minimum=1)
        if observation["boot_id"] is not None:
            _string(observation["boot_id"], "observation.boot_id", max_length=128)
        if observation["cgroup"] is not None:
            _string(observation["cgroup"], "observation.cgroup", max_length=4096)
        if observation["manager_job"] is not None:
            _string(observation["manager_job"], "observation.manager_job", max_length=4096)
        if observation["unit_result"] is not None:
            _string(observation["unit_result"], "observation.unit_result", max_length=128)
        slot = observation["slot"]
        if slot is not None:
            _closed(slot, SLOT_KEYS, "observation.slot")
            _integer(slot["device"], "observation.slot.device", minimum=0)
            _integer(slot["inode"], "observation.slot.inode", minimum=1)
        if observation["invocation_id"] is not None:
            if any(observation[key] is None for key in ("main_pid", "proc_start_ticks", "boot_id", "cgroup", "unit_result", "slot")):
                reject("observed invocation lacks complete PID, boot, cgroup, result or slot identity", "retain the attempt as uncertain")
        return observation

    def _validate_outcome(self, value: Any, *, terminal: bool = False) -> dict[str, Any]:
        outcome = _closed(value, OUTCOME_KEYS, "transition.outcome")
        for key, allowed in {
            "process": {"pending", "running", "closed", "unknown"},
            "business": {"pending", "reviewed", "not-reviewed", "unknown"},
            "provider": {"not-observed", "unknown", "observed"},
            "launcher_wait": {"pending", "exited", "unknown"},
            "closure": {"pending", "closed", "leaked", "unknown"},
        }.items():
            if outcome[key] not in allowed:
                reject(f"transition outcome {key} is invalid", "restore the closed outcome vocabulary")
        if outcome["exit_code"] is not None:
            _integer(outcome["exit_code"], "outcome.exit_code", minimum=-255, maximum=255)
        if terminal and (outcome["process"] != "closed" or outcome["closure"] != "closed" or outcome["launcher_wait"] != "exited"):
            reject("terminal transition does not prove launcher and descendant closure", "retain the attempt as uncertain")
        return outcome

    def _validate_evidence(self, value: Any) -> dict[str, Any]:
        evidence = _closed(value, EVIDENCE_KEYS, "transition.evidence")
        for key, limit in (("stdout", MAX_STDOUT_PREFIX), ("stderr", MAX_STDERR_PREFIX)):
            diag = _closed(evidence[key], DIAGNOSTIC_KEYS, f"evidence.{key}")
            _digest(diag["sha256"], f"evidence.{key}.sha256")
            _integer(diag["byte_length"], f"evidence.{key}.byte_length", maximum=2**63 - 1)
            _integer(diag["retained_prefix_byte_length"], f"evidence.{key}.retained_prefix_byte_length", maximum=limit)
            if type(diag["truncated"]) is not bool or diag["truncated"] != (diag["byte_length"] > limit):
                reject(f"evidence.{key} truncation fact is inconsistent", "retain the complete drained-byte count and digest")
        if not isinstance(evidence["artifacts"], list) or len(evidence["artifacts"]) > MAX_EXPECTED_OUTPUTS:
            reject("output evidence inventory is not bounded", "retain no more than the fixed output inventory")
        for artifact in evidence["artifacts"]:
            item = _closed(artifact, {"member", "sha256", "byte_length"}, "evidence.artifact")
            _member(item["member"], "evidence.artifact.member")
            _digest(item["sha256"], "evidence.artifact.sha256")
            _integer(item["byte_length"], "evidence.artifact.byte_length", maximum=MAX_ARTIFACT_BYTES)
        if not isinstance(evidence["diagnostics"], list) or len(evidence["diagnostics"]) > 32:
            reject("diagnostic inventory is not bounded", "retain only finite sanitized diagnostics")
        for item in evidence["diagnostics"]:
            _string(item, "evidence.diagnostic", max_length=512)
        return evidence

    def _validate_chain(self, attempt_dir: Path, checkpoint: dict[str, Any]) -> tuple[list[dict[str, Any]], list[bytes]]:
        try:
            names = sorted(path.name for path in (attempt_dir / "transitions").iterdir())
        except OSError as exc:
            raise SupervisorError("why: attempt transition directory is unreadable; remedy: retain the attempt as fenced") from exc
        if len(names) > MAX_TRANSITIONS or any(not TRANSITION_RE.fullmatch(name) for name in names):
            reject("attempt transition inventory is invalid or exceeds 64 records", "retain the complete journal for manual recovery")
        records: list[dict[str, Any]] = []
        raws: list[bytes] = []
        previous: str | None = None
        attempt_id = attempt_dir.name
        for index, name in enumerate(names, 1):
            value, raw = self._read_transition(attempt_dir / "transitions" / name)
            if value["sequence"] != index or value["attempt_id"] != attempt_id:
                reject("attempt transition sequence or attempt identity is inconsistent", "retain the unmodified journal")
            if value["previous_record_sha256"] != previous:
                reject("attempt transition predecessor digest is inconsistent", "restore the exact append-only predecessor")
            _uuid(value["attempt_id"], "transition.attempt_id")
            _uuid(value["request_id"], "transition.request_id")
            if value["phase"] not in PHASES:
                reject("attempt transition phase is invalid", "restore the closed phase vocabulary")
            validate_identity(value["identity"])
            binding = _closed(value["installation_identity"], INSTALL_BINDING_KEYS, "transition.installation_identity")
            for key in ("deployment_revision", "source_sha256", "adapter_sha256", "config_sha256", "bundle_sha256"):
                _string(binding[key], f"transition.installation_identity.{key}", pattern=HEX40_RE if key == "deployment_revision" else SHA_RE, max_length=64)
            _sha_identity(value["input_identity"], "transition.input_identity", member_required=False)
            self._validate_observation(value["observation"], unit=_attempt_unit(attempt_id), allow_pending=value["phase"] in {"admitted", "published", "launch_pending", "uncertain"})
            self._validate_outcome(value["outcome"], terminal=value["phase"] == "terminal")
            self._validate_evidence(value["evidence"])
            previous = hashlib.sha256(raw).hexdigest()
            records.append(value)
            raws.append(raw)
        tip = checkpoint["tips"].get(attempt_id)
        if not records:
            reject("attempt has no durable initial record", "retain the complete admission and journal")
        if not isinstance(tip, dict) or set(tip) != {"sequence", "sha256", "byte_length"}:
            reject("protected checkpoint lacks this attempt tip", "restore the independently protected checkpoint")
        if tip["sequence"] != len(records) or tip["sha256"] != hashlib.sha256(raws[-1]).hexdigest() or tip["byte_length"] != len(raws[-1]):
            reject("attempt journal tip differs from the protected checkpoint", "retain the conflicting journal and checkpoint for manual recovery")
        return records, raws

    def _append(self, attempt_dir: Path, checkpoint: dict[str, Any], record: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
        transitions = attempt_dir / "transitions"
        transitions.mkdir(parents=True, exist_ok=True)
        names = sorted(path.name for path in transitions.iterdir())
        if names:
            existing, raws = self._validate_chain(attempt_dir, checkpoint)
        else:
            existing, raws = [], []
        sequence = len(existing) + 1
        record = dict(record)
        record["sequence"] = sequence
        record["previous_record_sha256"] = hashlib.sha256(raws[-1]).hexdigest() if raws else None
        raw = canonical_bytes(record)
        if len(raw) > MAX_TRANSITION_BYTES:
            reject("transition exceeds its bounded byte limit", "retain bounded diagnostics and output identities")
        path = transitions / f"{sequence:06d}.json"
        self.os.write_immutable(path, raw, 0o400)
        new_checkpoint = {"schema": CHECKPOINT_SCHEMA, "tips": dict(checkpoint["tips"])}
        new_checkpoint["tips"][attempt_dir.name] = {"sequence": sequence, "sha256": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw)}
        self._write_checkpoint(new_checkpoint)
        checkpoint["tips"] = new_checkpoint["tips"]
        return record, raw

    def _base_record(self, *, attempt_id: str, request_id: str, admission: dict[str, Any], manifest: dict[str, Any], input_raw: bytes, phase: str, observation: dict[str, Any] | None = None, outcome: dict[str, Any] | None = None, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        unit = _attempt_unit(attempt_id)
        observation = observation or {"unit": unit, "invocation_id": None, "main_pid": None, "proc_start_ticks": None, "boot_id": None, "cgroup": None, "manager_job": None, "unit_result": None, "slot": None}
        outcome = outcome or {"process": "pending", "business": "pending", "provider": "not-observed", "exit_code": None, "launcher_wait": "pending", "closure": "pending"}
        evidence = evidence or {"stdout": digest_bytes(b"") | {"retained_prefix_byte_length": 0, "truncated": False}, "stderr": digest_bytes(b"") | {"retained_prefix_byte_length": 0, "truncated": False}, "artifacts": [], "diagnostics": []}
        return {
            "schema": ATTEMPT_SCHEMA, "sequence": 0, "previous_record_sha256": None,
            "attempt_id": attempt_id, "request_id": request_id, "phase": phase,
            "identity": admission["identity"], "installation_identity": installation_binding(manifest),
            "input_identity": {"sha256": hashlib.sha256(input_raw).hexdigest(), "byte_length": len(input_raw)},
            "observation": observation, "outcome": outcome, "evidence": evidence,
        }

    def _attempt_dirs(self) -> list[Path]:
        try:
            entries = sorted(ATTEMPTS_ROOT.iterdir())
        except OSError as exc:
            raise SupervisorError("why: attempt inventory is unreadable; remedy: retain root state and repair the protected directory") from exc
        if len(entries) > MAX_ADMISSIONS:
            reject("attempt inventory exceeds the fixed 4096-generation bound", "perform an explicitly authorized retention operation")
        for path in entries:
            if not path.is_dir() or path.is_symlink() or not UUID_RE.fullmatch(path.name):
                reject("attempt inventory contains an unsafe generation", "retain the exact root-owned generations and remove no data automatically")
        return entries

    def _load_attempt(self, attempt_id: str, checkpoint: dict[str, Any]) -> tuple[Path, list[dict[str, Any]], list[bytes]]:
        _uuid(attempt_id, "attempt_id")
        attempt_dir = ATTEMPTS_ROOT / attempt_id
        if not attempt_dir.is_dir() or attempt_dir.is_symlink():
            reject("attempt generation is absent or unsafe", "observe only the exact root-published attempt UUID")
        records, raws = self._validate_chain(attempt_dir, checkpoint)
        return attempt_dir, records, raws

    def _publish_runtime(self, attempt_id: str, input_raw: bytes) -> tuple[Path, Path]:
        generation = RUNTIME_ROOT / attempt_id
        engine = generation / "engine"
        output = engine / "output"
        for path in (generation, engine, output):
            self.os.mkdir(path, 0o750)
        input_path = generation / "input.json"
        self.os.write_immutable(input_path, input_raw, 0o440)
        self.os.fsync_dir(generation)
        return input_path, output

    def _validate_output(self, output_dir: Path, admission: dict[str, Any], *, input_hash: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        try:
            names = sorted(path.name for path in output_dir.iterdir())
        except OSError as exc:
            raise SupervisorError("why: engine output directory is unreadable; remedy: retain the attempt as not-reviewed") from exc
        if len(names) > MAX_EXPECTED_OUTPUTS or "result.json" not in names or not any(name == "coverage.json" or name.startswith("coverage-") for name in names):
            reject("engine output inventory is missing result.json or exceeds 16 files", "retain the bounded output as not-reviewed")
        allowed = {"result.json", "coverage.json"}
        for name in names:
            if name not in allowed and not re.fullmatch(r"coverage-[0-9]+-[a-z0-9_-]+\.json", name):
                reject("engine output contains an unexpected file", "retain only the authenticated result and coverage inventory")
        artifacts: list[dict[str, Any]] = []
        result: dict[str, Any] | None = None
        aggregate_bytes = 0
        for name in names:
            path = output_dir / name
            raw = self.os.read_bytes(path, MAX_RESULT_BYTES if name == "result.json" else MAX_COVERAGE_BYTES)
            first = digest_bytes(raw)
            aggregate_bytes += first["byte_length"]
            if aggregate_bytes > MAX_ARTIFACT_BYTES:
                reject("aggregate engine artifacts exceed 8MiB", "retain the bounded output inventory")
            parsed = parse_json_bytes(raw, label=f"output {name}", limit=MAX_RESULT_BYTES if name == "result.json" else MAX_COVERAGE_BYTES)
            if not isinstance(parsed, dict):
                reject(f"output {name} is not a JSON object", "retain the exact T2 output object")
            if parsed.get("input_sha256") != input_hash:
                reject(f"output {name} does not bind the complete input digest", "retain output from the authenticated attempt")
            identity = parsed.get("identity")
            validate_identity(identity)
            if identity != admission["identity"]:
                reject(f"output {name} identity differs from the admitted run", "retain output only after exact identity revalidation")
            if name == "result.json":
                if parsed.get("schema") != "lmdj.pr-agent-result.v1" or parsed.get("status") not in {"reviewed", "not-reviewed"}:
                    reject("engine result schema or status is invalid", "retain the attempt as not-reviewed")
                result = parsed
            else:
                if parsed.get("schema") != "lmdj.pr-agent-coverage.v1":
                    reject(f"output {name} is not a T2 coverage receipt", "retain the attempt as not-reviewed")
            artifacts.append({"member": name, "sha256": first["sha256"], "byte_length": first["byte_length"]})
            reread = self.os.read_bytes(path, MAX_RESULT_BYTES if name == "result.json" else MAX_COVERAGE_BYTES)
            if reread != raw:
                reject(f"output {name} mutated during authentication", "retain the attempt as not-reviewed and fenced")
        assert result is not None
        return artifacts, result

    def _copy_evidence(self, attempt_dir: Path, output_dir: Path, artifacts: list[dict[str, Any]]) -> None:
        evidence_dir = attempt_dir / "evidence"
        self.os.mkdir(evidence_dir, 0o700)
        for artifact in artifacts:
            raw = self.os.read_bytes(output_dir / artifact["member"], MAX_RESULT_BYTES if artifact["member"] == "result.json" else MAX_COVERAGE_BYTES)
            self.os.write_immutable(evidence_dir / artifact["member"], raw, 0o400)
            reread = self.os.read_bytes(evidence_dir / artifact["member"], MAX_RESULT_BYTES if artifact["member"] == "result.json" else MAX_COVERAGE_BYTES)
            if digest_bytes(reread) != {"sha256": artifact["sha256"], "byte_length": artifact["byte_length"]}:
                reject("root-owned evidence readback differs from engine output", "retain the attempt as uncertain")
        self.os.fsync_dir(evidence_dir)

    def _validate_terminal_evidence(self, attempt_dir: Path, record: dict[str, Any]) -> None:
        """Re-authenticate copied evidence before any duplicate readback."""
        for artifact in record["evidence"]["artifacts"]:
            path = attempt_dir / "evidence" / artifact["member"]
            raw = self.os.read_bytes(path, MAX_RESULT_BYTES if artifact["member"] == "result.json" else MAX_COVERAGE_BYTES)
            if digest_bytes(raw) != {"sha256": artifact["sha256"], "byte_length": artifact["byte_length"]}:
                reject("terminal evidence readback differs from its authenticated inventory", "retain the corrupt generation as fenced")

    def _finish(self, *, attempt_dir: Path, checkpoint: dict[str, Any], admission: dict[str, Any], manifest: dict[str, Any], input_raw: bytes, launch: Launch, observation: Observation, boundary_reason: str | None = None, cancel: bool = False, slot_fd: int | None = None) -> dict[str, Any]:
        if cancel:
            self.os.cancel(observation.unit, invocation_id=observation.invocation_id or "", cgroup=observation.cgroup)
        stdout_drain = Drain(launch.stdout, MAX_STDOUT_PREFIX) if launch.stdout is not None else None
        stderr_drain = Drain(launch.stderr, MAX_STDERR_PREFIX) if launch.stderr is not None else None
        if stdout_drain:
            stdout_drain.start()
        if stderr_drain:
            stderr_drain.start()
        deadline = self.os.monotonic() + (manifest["limits"]["engine_deadline_seconds"] if not cancel else TERM_GRACE_SECONDS + KILL_GRACE_SECONDS)
        exit_code: int | None = None
        if launch.process is not None:
            remaining = max(0.0, deadline - self.os.monotonic())
            exit_code = self.os.wait(launch, remaining)
        elif observation.unit_result:
            exit_code = 0 if observation.unit_result == "success" else 1
        if exit_code is None and launch.process is not None and not cancel:
            self.os.cancel(observation.unit, invocation_id=observation.invocation_id or "", cgroup=observation.cgroup)
            exit_code = self.os.wait(launch, TERM_GRACE_SECONDS + KILL_GRACE_SECONDS)
        # Drains started before wait prevent a child filling a pipe and
        # blocking the supervisor before the actual launcher wait is known.
        empty_stdout = {**digest_bytes(b""), "retained_prefix_byte_length": 0, "truncated": False}
        empty_stderr = {**digest_bytes(b""), "retained_prefix_byte_length": 0, "truncated": False}
        stdout_doc = stdout_drain.finish() if stdout_drain else empty_stdout
        stderr_doc = stderr_drain.finish() if stderr_drain else empty_stderr
        if not self.os.closure(launch, observation, FINAL_CLOSURE_SECONDS):
            return self._uncertain(attempt_dir, checkpoint, admission, manifest, input_raw, observation, stdout_doc, stderr_doc, "descendant or launcher closure is unproven")
        artifacts: list[dict[str, Any]] = []
        business = "not-reviewed"
        diagnostics: list[str] = []
        try:
            runtime_output = RUNTIME_ROOT / attempt_dir.name / "engine" / "output"
            artifacts, result = self._validate_output(runtime_output, admission, input_hash=hashlib.sha256(input_raw).hexdigest())
            self._copy_evidence(attempt_dir, runtime_output, artifacts)
            business = "not-reviewed" if cancel else result["status"]
            if cancel:
                diagnostics.append("cancel requested by the fixed supervisor boundary")
        except SupervisorError as exc:
            diagnostics.append(str(exc)[:512])
        evidence = {"stdout": stdout_doc, "stderr": stderr_doc, "artifacts": artifacts, "diagnostics": diagnostics}
        outcome = {"process": "closed", "business": business, "provider": "unknown", "exit_code": exit_code, "launcher_wait": "exited" if exit_code is not None else "unknown", "closure": "closed"}
        if outcome["launcher_wait"] == "unknown":
            return self._uncertain(attempt_dir, checkpoint, admission, manifest, input_raw, observation, stdout_doc, stderr_doc, "launcher wait is unknown")
        acquired_here = False
        if slot_fd is None:
            # Recovery only acquires the slot after the exact child and every
            # descendant are closed.  This avoids a second OFD while a child
            # from the crashed supervisor still owns the original one.
            slot_fd = self.os.open_lock(SLOT_LOCK_PATH, mode=0o400, nonblocking=True)
            acquired_here = True
        try:
            record, raw = self._append(attempt_dir, checkpoint, self._base_record(attempt_id=attempt_dir.name, request_id=admission["request_id"], admission=admission, manifest=manifest, input_raw=input_raw, phase="closing", observation=observation.document(), outcome=outcome, evidence=evidence))
            record, raw = self._append(attempt_dir, checkpoint, self._base_record(attempt_id=attempt_dir.name, request_id=admission["request_id"], admission=admission, manifest=manifest, input_raw=input_raw, phase="terminal", observation=observation.document(), outcome=outcome, evidence=evidence))
        finally:
            if acquired_here:
                self.os.unlock_and_close(slot_fd)
        return _response("completed", attempt_id=attempt_dir.name, phase="terminal", business_outcome=business, process_outcome="closed", terminal_record_sha256=hashlib.sha256(raw).hexdigest())

    def _uncertain(self, attempt_dir: Path, checkpoint: dict[str, Any], admission: dict[str, Any], manifest: dict[str, Any], input_raw: bytes, observation: Observation, stdout: dict[str, Any], stderr: dict[str, Any], reason: str) -> dict[str, Any]:
        evidence = {"stdout": stdout, "stderr": stderr, "artifacts": [], "diagnostics": [reason[:512]]}
        outcome = {"process": "unknown", "business": "unknown", "provider": "unknown", "exit_code": None, "launcher_wait": "unknown", "closure": "unknown"}
        record, raw = self._append(attempt_dir, checkpoint, self._base_record(attempt_id=attempt_dir.name, request_id=admission["request_id"], admission=admission, manifest=manifest, input_raw=input_raw, phase="uncertain", observation=observation.document(), outcome=outcome, evidence=evidence))
        return _response("uncertain", attempt_id=attempt_dir.name, phase="uncertain", reason=reason, terminal_record_sha256=hashlib.sha256(raw).hexdigest())

    def _find_existing(self, admission: dict[str, Any], checkpoint: dict[str, Any]) -> dict[str, Any] | None:
        for attempt_dir in self._attempt_dirs():
            try:
                _, records, _ = self._load_attempt(attempt_dir.name, checkpoint)
            except SupervisorError:
                raise
            first = records[0]
            last = records[-1]
            if last["phase"] != "terminal":
                return {"attempt_id": attempt_dir.name, "records": records, "last": last}
            if first["request_id"] == admission["request_id"] or (first["identity"] == admission["identity"] and first.get("request_id") == admission["request_id"]):
                return {"attempt_id": attempt_dir.name, "records": records, "last": last}
        return None

    def submit(self, request_id: str) -> dict[str, Any]:
        self._require_root()
        request_id = _uuid(request_id, "request_id")
        manifest = self._read_manifest()
        self._prerequisites(manifest)
        metadata_fd = self._metadata_lock()
        slot_fd: int | None = None
        try:
            checkpoint = self._checkpoint()
            admission, input_raw = self._validate_spool(request_id, manifest)
            existing = self._find_existing(admission, checkpoint)
            if existing:
                last = existing["last"]
                if last["phase"] == "terminal":
                    self._validate_terminal_evidence(ATTEMPTS_ROOT / existing["attempt_id"], last)
                    return _response("completed", attempt_id=existing["attempt_id"], phase="terminal", business_outcome=last["outcome"]["business"], process_outcome=last["outcome"]["process"], terminal_record_sha256=hashlib.sha256(canonical_bytes(last)).hexdigest())
                return _response("busy", attempt_id=existing["attempt_id"], phase=last["phase"])
            if len(self._attempt_dirs()) >= MAX_ADMISSIONS:
                reject("root admission inventory has reached 4096 generations", "perform an explicitly authorized retention operation")
            slot_fd = self.os.open_lock(SLOT_LOCK_PATH, mode=0o400, nonblocking=True)
            attempt_id = str(uuid.uuid4())
            attempt_dir = ATTEMPTS_ROOT / attempt_id
            self.os.mkdir(attempt_dir, 0o700)
            self.os.mkdir(attempt_dir / "transitions", 0o700)
            self.os.mkdir(attempt_dir / "evidence", 0o700)
            self.os.write_immutable(attempt_dir / "admission.json", canonical_bytes(admission), 0o400)
            checkpoint["tips"].setdefault(attempt_id, None)
            self._write_checkpoint(checkpoint)
            self._append(attempt_dir, checkpoint, self._base_record(attempt_id=attempt_id, request_id=request_id, admission=admission, manifest=manifest, input_raw=input_raw, phase="admitted"))
            input_path, output_path = self._publish_runtime(attempt_id, input_raw)
            self._append(attempt_dir, checkpoint, self._base_record(attempt_id=attempt_id, request_id=request_id, admission=admission, manifest=manifest, input_raw=input_raw, phase="published"))
            unit = _attempt_unit(attempt_id)
            self._append(attempt_dir, checkpoint, self._base_record(attempt_id=attempt_id, request_id=request_id, admission=admission, manifest=manifest, input_raw=input_raw, phase="launch_pending", observation={"unit": unit, "invocation_id": None, "main_pid": None, "proc_start_ticks": None, "boot_id": None, "cgroup": None, "manager_job": None, "unit_result": None, "slot": None}))
            launch = self.os.launch(unit=unit, manifest=manifest, input_path=input_path, output_path=output_path, slot_fd=slot_fd)
            observed = self.os.observe(launch)
            self._append(attempt_dir, checkpoint, self._base_record(attempt_id=attempt_id, request_id=request_id, admission=admission, manifest=manifest, input_raw=input_raw, phase="running", observation=observed.document(), outcome={"process": "running", "business": "pending", "provider": "not-observed", "exit_code": None, "launcher_wait": "pending", "closure": "pending"}))
            return self._finish(attempt_dir=attempt_dir, checkpoint=checkpoint, admission=admission, manifest=manifest, input_raw=input_raw, launch=launch, observation=observed, slot_fd=slot_fd)
        except CrashBeforeObservation:
            raise
        except SupervisorError:
            raise
        finally:
            if slot_fd is not None:
                self.os.unlock_and_close(slot_fd)
            self.os.unlock_and_close(metadata_fd)

    def _recover(self, attempt_id: str, *, cancel: bool = False) -> dict[str, Any]:
        self._require_root()
        manifest = self._read_manifest()
        self._prerequisites(manifest)
        metadata_fd = self._metadata_lock()
        slot_fd: int | None = None
        try:
            checkpoint = self._checkpoint()
            attempt_dir, records, _ = self._load_attempt(attempt_id, checkpoint)
            last = records[-1]
            admission_raw = self.os.read_bytes(attempt_dir / "admission.json", MAX_JSON_BYTES)
            admission = validate_admission(parse_json_bytes(admission_raw, label="attempt admission", canonical=True))
            binding = installation_binding(manifest)
            if admission["installation_identity"] != binding or last["installation_identity"] != binding:
                reject("attempt installation identity no longer matches the protected revision", "retain the attempt fence for manual recovery")
            input_raw = self._spool_file(admission["request_id"], admission["complete_input"]["member"], 8 * 1024 * 1024)
            if last["phase"] == "terminal":
                self._validate_terminal_evidence(attempt_dir, last)
                return _response("completed", attempt_id=attempt_id, phase="terminal", business_outcome=last["outcome"]["business"], process_outcome=last["outcome"]["process"], terminal_record_sha256=hashlib.sha256(canonical_bytes(last)).hexdigest())
            if last["phase"] == "uncertain":
                return _response("uncertain", attempt_id=attempt_id, phase="uncertain", reason="existing durable uncertainty remains fenced")
            unit = _attempt_unit(attempt_id)
            observation_doc = last["observation"]
            observation = Observation(unit, observation_doc["invocation_id"], observation_doc["main_pid"], observation_doc["proc_start_ticks"], observation_doc["boot_id"], observation_doc["cgroup"], observation_doc["manager_job"], observation_doc["unit_result"], observation_doc["slot"])
            launch = self.os.recover(unit, observation)
            if last["phase"] == "launch_pending":
                observed = self.os.observe(launch, expected_boot=observation.boot_id)
                self._append(attempt_dir, checkpoint, self._base_record(attempt_id=attempt_id, request_id=admission["request_id"], admission=admission, manifest=manifest, input_raw=input_raw, phase="running", observation=observed.document(), outcome={"process": "running", "business": "pending", "provider": "not-observed", "exit_code": None, "launcher_wait": "pending", "closure": "pending"}))
                observation = observed
            elif observation.invocation_id is None:
                return self._uncertain(attempt_dir, checkpoint, admission, manifest, input_raw, observation, last["evidence"]["stdout"], last["evidence"]["stderr"], "unfinished attempt has no authenticated InvocationID")
            else:
                observed = self.os.observe(launch, expected_boot=observation.boot_id)
                if observed.invocation_id != observation.invocation_id:
                    reject("recovery observed a different InvocationID", "retain the attempt fence for manual reconciliation")
                observation = observed
            if cancel:
                # Revalidate exact invocation/cgroup immediately before TERM/KILL.
                observed = self.os.observe(launch, expected_boot=observation.boot_id)
                if observed.invocation_id != observation.invocation_id or observed.unit != unit:
                    reject("cancel target changed during exact revalidation", "retain the attempt as uncertain")
                observation = observed
            return self._finish(attempt_dir=attempt_dir, checkpoint=checkpoint, admission=admission, manifest=manifest, input_raw=input_raw, launch=launch, observation=observation, cancel=cancel, slot_fd=slot_fd)
        finally:
            if slot_fd is not None:
                self.os.unlock_and_close(slot_fd)
            self.os.unlock_and_close(metadata_fd)

    def observe(self, attempt_id: str) -> dict[str, Any]:
        return self._recover(_uuid(attempt_id, "attempt_id"))

    def cancel(self, attempt_id: str) -> dict[str, Any]:
        return self._recover(_uuid(attempt_id, "attempt_id"), cancel=True)

    def status(self) -> dict[str, Any]:
        try:
            manifest = validate_installation(parse_json_bytes(self.os.read_bytes(MANIFEST_PATH, MAX_JSON_BYTES), label="installation manifest", canonical=True))
            installation = "installed-profile"
        except SupervisorError:
            manifest = None
            installation = "not-installed"
        attempts = 0
        try:
            attempts = len(list(ATTEMPTS_ROOT.iterdir()))
        except OSError:
            pass
        return _response("ok", installation=installation, attempts=attempts, slot=str(SLOT_LOCK_PATH), limits=(manifest["limits"] if manifest else {"engine_deadline_seconds": MAX_RUNTIME_SECONDS, "launch_observation_seconds": LAUNCH_OBSERVATION_SECONDS, "term_grace_seconds": TERM_GRACE_SECONDS, "kill_grace_seconds": KILL_GRACE_SECONDS, "final_closure_seconds": FINAL_CLOSURE_SECONDS}))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in {"submit", "observe", "cancel", "status"}:
        print(json.dumps(_response("rejected", error="why: CLI verb is not in the fixed public boundary; remedy: use submit, observe, cancel or status"), sort_keys=True))
        return 2
    supervisor = Supervisor(DEFAULT_BOUNDARY)
    try:
        if args == ["status"]:
            result = supervisor.status()
        elif len(args) == 2 and args[0] in {"submit", "observe", "cancel"}:
            selector = _uuid(args[1], "selector")
            result = getattr(supervisor, args[0])(selector)
        else:
            reject("CLI accepts no path, command, provider, environment, hash or timeout options", "use exactly one fixed UUID selector")
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["status"] in {"ok", "completed"} else 2
    except SupervisorError as exc:
        print(json.dumps(_response("rejected", error=str(exc)), sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
