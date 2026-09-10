#!/usr/bin/env bash
set -euo pipefail

# Newly created parent directories must be traversable, but never group/world
# writable. Existing unsafe paths still fail the ownership boundary unchanged.
umask 022

# Repository-owned deployment boundary for the PR-Agent Netcup review slot.
# This command stages and verifies an immutable release; it never invokes
# systemctl.  Activation, host admission, and supplier/API checks remain
# separate lead-authorized operations.

usage() {
  cat >&2 <<'EOF'
usage: deploy-runner.sh {dry-run|verify|install|rollback}
  [--config PATH] [--bundle PATH] [--identity PATH] [--target-root PATH]

verify and install require --bundle and --identity.  target-root is intended
for isolated fixtures; production uses the absolute paths in the trusted
configuration.  install and active verify also require --runtime-config.
install stages files and units but does not activate them.
EOF
}

[[ $# -ge 1 ]] || { usage; exit 64; }
mode=$1
shift
case "$mode" in dry-run|verify|install|rollback) ;; *) usage; exit 64 ;; esac

config_path="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/netcup-review.json"
bundle_path=""
identity_path=""
runtime_config_path=""
target_root="/"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) [[ $# -ge 2 ]] || { usage; exit 64; }; config_path=$2; shift 2 ;;
    --bundle) [[ $# -ge 2 ]] || { usage; exit 64; }; bundle_path=$2; shift 2 ;;
    --identity) [[ $# -ge 2 ]] || { usage; exit 64; }; identity_path=$2; shift 2 ;;
    --runtime-config) [[ $# -ge 2 ]] || { usage; exit 64; }; runtime_config_path=$2; shift 2 ;;
    --target-root) [[ $# -ge 2 ]] || { usage; exit 64; }; target_root=$2; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "deploy-runner: unknown option: $1" >&2; usage; exit 64 ;;
  esac
done

python_bin=${PR_AGENT_DEPLOY_PYTHON:-python3}
command -v "$python_bin" >/dev/null 2>&1 || {
  echo "deploy-runner: Python helper is unavailable: $python_bin" >&2
  exit 127
}

exec "$python_bin" - "$mode" "$config_path" "$bundle_path" "$identity_path" "$runtime_config_path" "$target_root" <<'PY'
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import grp
import pwd
import shutil
import sys
import tarfile
import tempfile
import time
import uuid


MODE, CONFIG_ARG, BUNDLE_ARG, IDENTITY_ARG, RUNTIME_CONFIG_ARG, TARGET_ROOT_ARG = sys.argv[1:]
ROOT = Path(TARGET_ROOT_ARG).resolve()
if not ROOT.is_absolute():
    raise SystemExit("deploy-runner: target root must be absolute")


def _identity(value: object, label: str) -> tuple[int, int]:
    if not isinstance(value, dict) or set(value) != {"uid", "gid"}:
        fail(f"{label} identity must contain exactly uid and gid")
    if not isinstance(value["uid"], int) or not isinstance(value["gid"], int) or value["uid"] < 0 or value["gid"] < 0:
        fail(f"{label} identity is invalid")
    return value["uid"], value["gid"]


def deployment_identities(config: dict) -> tuple[tuple[int, int], tuple[int, int], dict[str, tuple[int, int]]]:
    """Return operator/service identities; non-/ targets require explicit test emulation."""
    if ROOT == Path("/"):
        if os.geteuid() != 0:
            fail("real-host install must run as root after the service identity is provisioned")
        try:
            user = pwd.getpwnam(config["runtime"]["user"])
            group = grp.getgrnam(config["runtime"]["group"])
        except KeyError as exc:
            fail(f"runtime service identity is not provisioned: {exc}")
        return (0, 0), (user.pw_uid, group.gr_gid), {}
    raw = os.environ.get("PR_AGENT_DEPLOY_FIXTURE_IDENTITIES")
    if raw is None:
        fail("non-root target fixtures require explicit PR_AGENT_DEPLOY_FIXTURE_IDENTITIES emulation")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"fixture identity emulation is not JSON: {exc}")
    if not isinstance(document, dict) or set(document) != {"operator", "service", "overrides"} or not isinstance(document["overrides"], dict):
        fail("fixture identity emulation must contain operator, service and overrides")
    overrides = {str(Path(path).resolve()): _identity(identity, f"fixture override {path}") for path, identity in document["overrides"].items()
                 if isinstance(path, str)}
    if len(overrides) != len(document["overrides"]):
        fail("fixture identity override paths must be strings")
    return _identity(document["operator"], "fixture operator"), _identity(document["service"], "fixture service"), overrides


def observed_identity(path: Path, overrides: dict[str, tuple[int, int]]) -> tuple[int, int]:
    resolved = str(path.resolve())
    if resolved in overrides:
        return overrides[resolved]
    stat = path.stat()
    return stat.st_uid, stat.st_gid


def require_secure_parent_chain(path: Path, operator: tuple[int, int], overrides: dict[str, tuple[int, int]], label: str) -> None:
    """All existing parents through the trusted root are operator controlled and non-writable."""
    parent = path.parent
    while True:
        if parent.is_symlink():
            fail(f"{label} parent is a symlink: {parent}")
        if parent.exists():
            if not parent.is_dir():
                fail(f"{label} parent is not a directory: {parent}")
            if observed_identity(parent, overrides) != operator:
                fail(f"{label} parent is not owned by the approved operator identity: {parent}")
            if parent.stat().st_mode & 0o022:
                fail(f"{label} parent is group/world writable: {parent}")
        if parent == ROOT or parent == parent.parent:
            return
        parent = parent.parent


def validate_owned_directory(path: Path, identity: tuple[int, int], mode: int, overrides: dict[str, tuple[int, int]], label: str) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or not path.is_dir():
        fail(f"{label} must be a directory, not a symlink or other type: {path}")
    if observed_identity(path, overrides) != identity or path.stat().st_mode & 0o777 != mode:
        fail(f"{label} owner or mode is not approved: {path}")


def validate_owned_file(path: Path, identity: tuple[int, int], mode: int, overrides: dict[str, tuple[int, int]], label: str, required: bool = False) -> None:
    if not path.exists() and not path.is_symlink():
        if required:
            fail(f"{label} is missing")
        return
    if path.is_symlink() or not path.is_file():
        fail(f"{label} must be a regular file, not a symlink or other type: {path}")
    if observed_identity(path, overrides) != identity or path.stat().st_mode & 0o777 != mode:
        fail(f"{label} owner or mode is not approved: {path}")


def validate_operator_boundary(config: dict, config_source: Path, runtime_source: Path | None,
                               operator: tuple[int, int], service: tuple[int, int], overrides: dict[str, tuple[int, int]]) -> None:
    """Reject owner, mode, parent, or symlink drift before a managed target write."""
    paths = config["paths"]
    install_root = path_from_config(paths["install_root"])
    operator_state = path_from_config(paths["operator_state_root"])
    operator_config = path_from_config(paths["operator_config"])
    target_runtime = path_from_config(paths["runtime_config"])
    service_unit = path_from_config(paths["unit"])
    slice_unit = path_from_config(paths["slice_unit"])
    for path, label in ((install_root, "install root"), (operator_state, "operator state"),
                        (operator_config, "operator inventory"), (target_runtime, "operator runtime target"),
                        (service_unit, "service unit"), (slice_unit, "slice unit")):
        require_secure_parent_chain(path, operator, overrides, label)
    if ROOT == Path("/"):
        require_secure_parent_chain(config_source, operator, overrides, "operator inventory source")
    if runtime_source is not None and ROOT == Path("/"):
        require_secure_parent_chain(runtime_source, operator, overrides, "operator runtime source")
    validate_owned_directory(install_root, operator, 0o755, overrides, "install root")
    validate_owned_directory(operator_state, operator, 0o700, overrides, "operator state")
    validate_owned_file(operator_config, operator, 0o600, overrides, "operator inventory")
    validate_owned_file(config_source, operator, 0o600, overrides, "operator inventory source", required=True)
    validate_owned_file(target_runtime, (operator[0], service[1]), 0o440, overrides, "operator runtime target")
    if runtime_source is not None:
        validate_owned_file(runtime_source, (operator[0], service[1]), 0o440, overrides, "operator runtime source", required=True)
    validate_owned_file(service_unit, operator, 0o644, overrides, "service unit")
    validate_owned_file(slice_unit, operator, 0o644, overrides, "slice unit")


def fail(message: str) -> "NoReturn":
    raise RuntimeError(message)


def read_json(path: Path, label: str) -> dict:
    if path.is_symlink() or not path.is_file():
        fail(f"{label} must be a regular file, not a symlink or missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{label} is not valid UTF-8 JSON: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must be a JSON object")
    return value


def sha256(path: Path) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        fail(f"identity input is not a regular file: {path}")
    digest = hashlib.sha256()
    length = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            length += len(chunk)
    return digest.hexdigest(), length


def path_from_config(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        fail(f"trusted path must be absolute: {value}")
    if ROOT == Path("/"):
        return path
    return ROOT / path.relative_to("/")


def validate_config(config: dict) -> None:
    required = {"schema", "active", "target", "bundle", "runtime", "runtime_config", "resources", "paths", "admission"}
    if set(config) != required:
        fail(f"trusted deployment config keys must be exactly {sorted(required)}")
    if config["schema"] != "lmdj.pr-agent-runner.v1":
        fail("unsupported deployment config schema")
    if not isinstance(config["active"], bool):
        fail("deployment active flag must be boolean")
    target = config["target"]
    if set(target) != {"host", "service", "slice", "labels"}:
        fail("target inventory must contain host, service, slice and labels")
    if not target["host"] or "." in target["host"] or "/" in target["host"]:
        fail("target host is not an exact host identifier")
    if target["service"] != "lmdj-pr-agent.service" or target["slice"] != "lmdj-pr-review.slice":
        fail("deployment target unit or sibling slice is not the approved target")
    if target["labels"] != ["self-hosted", "Linux", "X64", "netcup", "ci-pr-agent"]:
        fail("deployment route must remain self-hosted Netcup ci-pr-agent")
    bundle = config["bundle"]
    if set(bundle) != {"archive", "identity", "files"}:
        fail("bundle inventory must contain archive, identity and files")
    for name in ("archive", "identity"):
        item = bundle[name]
        if set(item) != {"filename", "sha256", "byte_length"}:
            fail(f"bundle {name} identity is incomplete")
        if not item["filename"] or Path(item["filename"]).name != item["filename"]:
            fail(f"bundle {name} filename must be a basename")
        if not isinstance(item["byte_length"], int) or item["byte_length"] <= 0:
            fail(f"bundle {name} byte length is invalid")
        if not isinstance(item["sha256"], str) or len(item["sha256"]) != 64:
            fail(f"bundle {name} SHA-256 is invalid")
    expected_files = {"manifest", "adapter", "default_config", "requirements_lock", "stock_tokenizer_asset"}
    if set(bundle["files"]) != expected_files:
        fail("bundle member inventory must name exactly the five detached members")
    for member in bundle["files"].values():
        if set(member) != {"path", "sha256", "byte_length"}:
            fail("bundle member identity is incomplete")
        relative = PurePosixPath(member["path"])
        if relative.is_absolute() or ".." in relative.parts or str(relative) != member["path"]:
            fail("bundle member path is unsafe")
        if not isinstance(member["byte_length"], int) or member["byte_length"] < 0:
            fail("bundle member byte length is invalid")
        if not isinstance(member["sha256"], str) or len(member["sha256"]) != 64:
            fail("bundle member SHA-256 is invalid")
    runtime = config["runtime"]
    if set(runtime) != {"python", "user", "group", "blocked_environment"} or runtime["python"] != "/usr/bin/python3.12":
        fail("runtime must use the pinned system Python 3.12")
    if runtime["user"] != "lmdj-pr-agent" or runtime["group"] != "lmdj-pr-agent":
        fail("runtime user/group isolation is not the approved account")
    if runtime["blocked_environment"] != ["GITHUB_TOKEN", "GH_TOKEN", "GITHUB_APP_ID", "GITHUB_APP_PRIVATE_KEY"]:
        fail("engine must explicitly block GitHub write credentials")
    runtime_config = config["runtime_config"]
    if set(runtime_config) != {"path", "sha256", "byte_length"} or not isinstance(runtime_config["path"], str) or not runtime_config["path"].startswith("/"):
        fail("operator runtime config binding is incomplete")
    if runtime_config["sha256"] is not None and (not isinstance(runtime_config["sha256"], str) or len(runtime_config["sha256"]) != 64):
        fail("operator runtime config SHA-256 is invalid")
    if runtime_config["byte_length"] is not None and (not isinstance(runtime_config["byte_length"], int) or runtime_config["byte_length"] < 0):
        fail("operator runtime config byte length is invalid")
    if config["active"] and (runtime_config["sha256"] is None or runtime_config["byte_length"] is None):
        fail("active deployment must bind an operator runtime config identity")
    resources = config["resources"]
    if resources != {"concurrency": 1, "cpu_quota": "100%", "memory_max": "2G", "cpu_weight": 1,
                     "review_slice": "lmdj-pr-review.slice", "heavy_slice_untouched": True,
                     "heavy_cpu_quota": "14 CPUs", "heavy_memory_max": "48G"}:
        fail("review resource envelope or heavy-service preservation is invalid")
    paths = config["paths"]
    expected_paths = {"install_root", "operator_config", "runtime_config", "state_root", "operator_state_root", "ledger", "deployment_receipts", "state", "unit", "slice_unit", "temporary_root", "slot_lock", "attempt_root", "output_root"}
    if set(paths) != expected_paths:
        fail("deployment paths are incomplete")
    for value in paths.values():
        if not isinstance(value, str) or not value.startswith("/"):
            fail("deployment paths must be absolute")
        pure = PurePosixPath(value)
        if ".." in pure.parts or str(pure) != value:
            fail("deployment paths must be canonical absolute paths")
    if paths["runtime_config"] != runtime_config["path"] or paths["state"] != paths["operator_state_root"] + "/runtime.json":
        fail("runtime config and state paths are not bound to their exact roots")
    if not paths["ledger"].startswith(paths["state_root"] + "/") or not paths["deployment_receipts"].startswith(paths["operator_state_root"] + "/"):
        fail("monetary ledger and operator receipts must use separate roots")
    admission = config["admission"]
    if set(admission) != {"operator_access", "runner04_classification", "capacity_receipts", "filesystem_isolation", "activation_receipt", "runtime_config_receipt"}:
        fail("activation prerequisites are incomplete")
    if config["active"] and not all(admission.values()):
        fail("active deployment lacks an approved admission receipt")


def file_bytes_from_tar(archive: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    stream = archive.extractfile(member)
    if stream is None:
        fail(f"archive member is not readable: {member.name}")
    return stream.read()


def validate_bundle(config: dict, bundle_path: Path, identity_path: Path, extract: bool) -> tuple[str, int, Path | None, dict]:
    expected_archive = config["bundle"]["archive"]
    actual_sha, actual_length = sha256(bundle_path)
    if actual_sha != expected_archive["sha256"] or actual_length != expected_archive["byte_length"]:
        fail("archive SHA-256/byte length does not match the trusted inventory")
    actual_identity_sha, actual_identity_length = sha256(identity_path)
    expected_identity = config["bundle"]["identity"]
    if actual_identity_sha != expected_identity["sha256"] or actual_identity_length != expected_identity["byte_length"]:
        fail("detached deployment identity SHA-256/byte length does not match the trusted inventory")
    identity = read_json(identity_path, "detached deployment identity")
    if set(identity) != {"schema", "archive", "files"} or identity["schema"] != "lmdj.pr-agent-deployment.v1":
        fail("detached deployment identity schema or keys are invalid")
    if identity["archive"] != {"sha256": actual_sha, "byte_length": actual_length}:
        fail("detached identity archive does not match the actual archive")
    expected_files = config["bundle"]["files"]
    if set(identity["files"]) != set(expected_files):
        fail("detached identity member set differs from trusted inventory")
    for name, member in identity["files"].items():
        if set(member) != {"path", "sha256", "byte_length"} or member != expected_files[name]:
            fail(f"detached member identity differs from trusted inventory: {name}")
    extracted_dir: Path | None = None
    with tarfile.open(bundle_path, mode="r:*") as archive:
        members = archive.getmembers()
        names: set[str] = set()
        for member in members:
            if member.name in names:
                fail(f"archive contains duplicate member: {member.name}")
            names.add(member.name)
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts or (member.name != "pr-agent" and not member.name.startswith("pr-agent/")):
                fail(f"archive contains an unsafe member path: {member.name}")
            if member.issym() or member.islnk():
                fail(f"archive contains a link member: {member.name}")
        for name, expected in identity["files"].items():
            archive_name = "pr-agent/" + expected["path"]
            member = next((candidate for candidate in members if candidate.name == archive_name), None)
            if member is None or not member.isfile():
                fail(f"archive is missing detached member: {expected['path']}")
            data = file_bytes_from_tar(archive, member)
            digest = hashlib.sha256(data).hexdigest()
            if digest != expected["sha256"] or len(data) != expected["byte_length"]:
                fail(f"archive member identity mismatch: {expected['path']}")
        if extract:
            extracted_dir = Path(tempfile.mkdtemp(prefix="lmdj-pr-agent-verify-"))
            root = extracted_dir / "pr-agent"
            root.mkdir()
            for member in members:
                relative = PurePosixPath(member.name).relative_to("pr-agent")
                destination = root / Path(*relative.parts)
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(file_bytes_from_tar(archive, member))
                    destination.chmod(0o444)
            for expected in identity["files"].values():
                actual_path = root / Path(*PurePosixPath(expected["path"]).parts)
                digest, length = sha256(actual_path)
                if digest != expected["sha256"] or length != expected["byte_length"]:
                    fail(f"extracted member identity mismatch: {expected['path']}")
    return actual_sha, actual_length, extracted_dir, identity


def validate_runtime_config(config: dict, source: Path | None, required: bool) -> tuple[str, int] | None:
    if source is None:
        if required:
            fail("active verify/install requires --runtime-config")
        return None
    if source.is_symlink() or not source.is_file():
        fail("operator runtime config source must be a regular file, not a symlink or missing")
    actual_sha, actual_length = sha256(source)
    expected = config["runtime_config"]
    if expected["sha256"] is not None and (actual_sha, actual_length) != (expected["sha256"], expected["byte_length"]):
        fail("operator runtime config SHA-256/byte length does not match the trusted binding")
    return actual_sha, actual_length


def render_unit(config: dict, engine_root: Path) -> tuple[str, str]:
    target = config["target"]
    runtime = config["runtime"]
    paths = config["paths"]
    blocked_environment = " ".join(runtime["blocked_environment"])
    current = engine_root
    runtime_config = engine_root / "runtime.toml"
    attempt = path_from_config(paths["attempt_root"])
    output = path_from_config(paths["output_root"])
    service = f"""[Unit]
Description=LMDJ PR-Agent isolated one-slot review attempt (staged, not auto-activated)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User={runtime['user']}
Group={runtime['group']}
WorkingDirectory={current}
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=LITELLM_LOCAL_MODEL_COST_MAP=true
Environment=PYTHONPATH={current / 'vendor'}:{current}
Environment=TIKTOKEN_CACHE_DIR={current / 'tokenizer-cache'}
ExecStartPre=/usr/bin/test -r {attempt / 'input.json'}
ExecStartPre=/usr/bin/test -d {attempt / 'engine'}
ExecStartPre=/usr/bin/test -d {output}
ExecStart=/usr/bin/flock --nonblock --exclusive {path_from_config(paths['slot_lock'])} {runtime['python']} {current / 'pr_agent_review.py'} --input {attempt / 'input.json'} --config {runtime_config} --source-root {current} --engine-cwd {attempt / 'engine'} --deployment-identity {current / 'DEPLOYMENT_IDENTITY.json'} --ledger {path_from_config(paths['ledger'])} --output-dir {output}
Slice={target['slice']}
CPUQuota={config['resources']['cpu_quota']}
CPUWeight={config['resources']['cpu_weight']}
MemoryMax={config['resources']['memory_max']}
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictNamespaces=true
LockPersonality=true
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
UnsetEnvironment={blocked_environment}
ReadOnlyPaths={current} {runtime_config}
ReadWritePaths={path_from_config(paths['state_root'])} {attempt} {output} {path_from_config(paths['slot_lock'])}

[Install]
WantedBy=multi-user.target
"""
    slice_unit = f"""[Unit]
Description=LMDJ PR-Agent one-slot review sibling slice

[Slice]
CPUQuota={config['resources']['cpu_quota']}
CPUWeight={config['resources']['cpu_weight']}
MemoryMax={config['resources']['memory_max']}
TasksMax=128
"""
    return service, slice_unit


def ensure_protected(path: Path, data: bytes, mode: int, identity: tuple[int, int] | None = None) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
            fail(f"operator-owned path differs and will not be overwritten: {path}")
        path.chmod(mode)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
    if temporary.exists() or temporary.is_symlink():
        fail(f"refusing to reuse temporary operator path: {temporary}")
    temporary.write_bytes(data)
    temporary.chmod(mode)
    if identity is not None:
        os.chown(temporary, identity[0], identity[1])
    os.replace(temporary, path)


def validate_protected(path: Path, data: bytes, label: str) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
            fail(f"{label} differs and will not be overwritten")


def validate_generated_unit(path: Path, expected_sha: str | None, expected_length: int | None, label: str) -> None:
    if not path.exists() and not path.is_symlink():
        if expected_sha is not None:
            fail(f"{label} is missing during an authenticated transition")
        return
    if path.is_symlink() or not path.is_file():
        fail(f"{label} is not a regular file")
    actual_sha, actual_length = sha256(path)
    if expected_sha is None or (actual_sha, actual_length) != (expected_sha, expected_length):
        fail(f"{label} digest does not match the authenticated deployment state")


def ensure_generated_unit(path: Path, data: bytes, expected_sha: str | None, expected_length: int | None, label: str) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            fail(f"{label} is not a regular file: {path}")
        validate_generated_unit(path, expected_sha, expected_length, label)
        temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
        temporary.write_bytes(data)
        temporary.chmod(0o644)
        os.replace(temporary, path)
        return
    if expected_sha is not None:
        fail(f"{label} is missing during an authenticated transition")
    ensure_protected(path, data, 0o644)


def ensure_directory(path: Path, mode: int) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        fail(f"trusted directory is not a directory: {path}")
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(mode)


def chown_tree(path: Path, identity: tuple[int, int]) -> None:
    uid, gid = identity
    for child in (path, *path.rglob("*")):
        if child.is_symlink():
            fail(f"refusing to change ownership through a symlink: {child}")
        os.chown(child, uid, gid)


def append_ledger(path: Path, record: dict) -> None:
    if path.is_symlink():
        fail("durable ledger must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    path.chmod(0o600)


def verify_release(release: Path, record: dict, owner_identity: tuple[int, int] | None = None,
                   identity_overrides: dict[str, tuple[int, int]] | None = None) -> None:
    if not release.is_dir() or release.is_symlink():
        fail(f"release is not a regular immutable directory: {release}")
    overrides = identity_overrides or {}
    if release.stat().st_mode & 0o777 != 0o755:
        fail(f"installed release root owner/group or mode is not approved: {release}; remedy: restore the service identity and mode 0755 before retry")
    if owner_identity is not None and observed_identity(release, overrides) != owner_identity:
        fail(f"installed release root owner/group or mode is not approved: {release}; remedy: restore the service identity and mode 0755 before retry")
    bundle = release / "bundle.tar"
    identity_path = release / "DEPLOYMENT_IDENTITY.json"
    actual_sha, actual_length = sha256(bundle)
    if (actual_sha, actual_length) != (record.get("archive_sha256"), record.get("archive_byte_length")):
        fail(f"installed archive identity mismatch: {release}")
    actual_identity_sha, actual_identity_length = sha256(identity_path)
    if (actual_identity_sha, actual_identity_length) != (record.get("deployment_identity_sha256"), record.get("deployment_identity_byte_length")):
        fail(f"installed deployment identity mismatch: {release}")
    deployment_identity = read_json(identity_path, "installed deployment identity")
    if deployment_identity.get("archive") != {"sha256": actual_sha, "byte_length": actual_length}:
        fail(f"installed detached archive identity mismatch: {release}")
    expected_files = record.get("member_identities")
    if deployment_identity.get("files") != expected_files:
        fail(f"installed detached member inventory mismatch: {release}")
    runtime_config = release / "runtime.toml"
    runtime_sha, runtime_length = sha256(runtime_config)
    if (runtime_sha, runtime_length) != (record.get("runtime_config_sha256"), record.get("runtime_config_byte_length")):
        fail(f"installed runtime config identity mismatch: {release}")
    for member in deployment_identity.get("files", {}).values():
        actual = release / Path(*PurePosixPath(member["path"]).parts)
        actual_member_sha, actual_member_length = sha256(actual)
        if (actual_member_sha, actual_member_length) != (member["sha256"], member["byte_length"]):
            fail(f"installed extracted member identity mismatch: {member['path']}")
    archive_members: set[str] = set()
    with tarfile.open(bundle, mode="r:*") as archive:
        for member in archive.getmembers():
            if member.name == "pr-agent":
                continue
            relative = PurePosixPath(member.name).relative_to("pr-agent")
            if member.isdir():
                continue
            if not member.isfile():
                fail(f"installed archive contains a non-file extracted member: {member.name}")
            archive_members.add(str(relative))
            stream = archive.extractfile(member)
            if stream is None:
                fail(f"installed archive member is not readable: {member.name}")
            digest = hashlib.sha256()
            length = 0
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                length += len(chunk)
            actual = release / Path(*relative.parts)
            actual_sha, actual_length = sha256(actual)
            if (actual_sha, actual_length) != (digest.hexdigest(), length):
                fail(f"installed archive extracted bytes mismatch: {relative}")
    allowed_extra = {"bundle.tar", "DEPLOYMENT_IDENTITY.json", "runtime.toml"}
    for child in release.rglob("*"):
        if child.is_file():
            relative = str(child.relative_to(release))
            if relative not in archive_members and relative not in allowed_extra:
                fail(f"installed release has an unverified extracted file: {relative}")
    for child in release.rglob("*"):
        if child.is_symlink():
            fail(f"installed release contains a symlink: {child}")
        if child.is_dir() and child.stat().st_mode & 0o777 != 0o755:
            fail(f"installed release directory is not service-traversable: {child}")
        if child.is_file() and child.stat().st_mode & 0o777 != 0o444:
            fail(f"installed release file is writable: {child}")
        if owner_identity is not None and observed_identity(child, overrides) != owner_identity:
            fail(f"installed release entry owner/group is not the approved service identity: {child}; remedy: restore the service UID/GID before retry")


def valid_release_record(record: object, install_root: Path) -> bool:
    required = {"release", "archive_sha256", "archive_byte_length", "deployment_identity_sha256",
                "deployment_identity_byte_length", "member_identities", "runtime_config_sha256",
                "runtime_config_byte_length", "service_unit_sha256", "service_unit_byte_length",
                "slice_unit_sha256", "slice_unit_byte_length"}
    if not isinstance(record, dict) or set(record) != required:
        return False
    release = record.get("release")
    archive_sha = record.get("archive_sha256")
    if not isinstance(release, str) or not valid_sha256(archive_sha):
        return False
    pure = PurePosixPath(release)
    if not pure.is_absolute() or ".." in pure.parts:
        return False
    candidate = Path(release)
    if candidate != install_root / "releases" / archive_sha:
        return False
    for name in ("archive_sha256", "deployment_identity_sha256", "runtime_config_sha256", "service_unit_sha256", "slice_unit_sha256"):
        if not valid_sha256(record.get(name)):
            return False
    for name in ("archive_byte_length", "deployment_identity_byte_length", "runtime_config_byte_length", "service_unit_byte_length", "slice_unit_byte_length"):
        value = record.get(name)
        if type(value) is not int or value < 0:
            return False
    if record["archive_byte_length"] <= 0 or record["deployment_identity_byte_length"] <= 0:
        return False
    if record["service_unit_byte_length"] <= 0 or record["slice_unit_byte_length"] <= 0:
        return False
    return isinstance(record.get("member_identities"), dict) and bool(record["member_identities"])


def valid_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def valid_receipt(record: object, inventory_record: dict) -> bool:
    if not isinstance(record, dict):
        return False
    action = record.get("action")
    common = {"schema", "action", "status", "transition_id", "target"}
    if action == "install":
        required = common | {"archive_sha256", "archive_byte_length", "deployment_identity_sha256"}
    elif action == "rollback":
        required = common | {"from_release", "to_release"}
    else:
        return False
    if not (set(record) == required and record.get("schema") == "lmdj.pr-agent-deployment-receipt.v1"
            and record.get("status") == "staged" and isinstance(record.get("transition_id"), str)
            and bool(record["transition_id"]) and record.get("target") == inventory_record):
        return False
    if action == "install":
        return (valid_sha256(record.get("archive_sha256"))
                and type(record.get("archive_byte_length")) is int
                and record["archive_byte_length"] > 0
                and valid_sha256(record.get("deployment_identity_sha256")))
    return isinstance(record.get("from_release"), str) and bool(record["from_release"]) and isinstance(record.get("to_release"), str) and bool(record["to_release"])


def valid_transition_semantics(state: dict, transition: dict, inventory_record: dict) -> bool:
    """Bind an interrupted intent and its receipt to one real transition shape."""
    action = transition["action"]
    before = transition["from"]
    target = transition["to"]
    prior = transition["previous"]
    receipt = transition["receipt"]
    current = state["current"]
    previous = state["previous"]
    if not valid_receipt(receipt, inventory_record) or receipt["action"] != action:
        return False
    if action == "install":
        # A generated install intent names its old current release as both
        # `from` and `previous`.  During recovery, state may still describe the
        # far side (current == target), but it must retain that same old release.
        if prior != before or target == before:
            return False
        if before is None:
            if previous is not None or current not in (None, target):
                return False
        elif current == before:
            if previous == target:
                return False
        elif current == target:
            if previous != before:
                return False
        else:
            return False
        return (receipt["archive_sha256"] == target["archive_sha256"]
                and receipt["archive_byte_length"] == target["archive_byte_length"]
                and receipt["deployment_identity_sha256"] == target["deployment_identity_sha256"])
    # A rollback intent is only meaningful from the recorded current release
    # to its recorded previous release.  Its far side has current/previous set
    # to the rollback target, as the terminal rollback state does.
    if prior != target or before == target:
        return False
    if current == before:
        if previous != target:
            return False
    elif current == target:
        if previous != target:
            return False
    else:
        return False
    return receipt["from_release"] == before["release"] and receipt["to_release"] == target["release"]


def valid_inventory_record(record: object, expected: dict) -> bool:
    if not isinstance(record, dict) or set(record) != set(expected):
        return False
    for key, value in record.items():
        if key == "operator_config":
            if not isinstance(value, str) or not value.startswith("/") or ".." in PurePosixPath(value).parts:
                return False
        elif value != expected[key]:
            return False
    return True


def validate_state(state: object, install_root: Path, inventory_record: dict) -> dict:
    if not isinstance(state, dict):
        fail("deployment state must be a JSON object")
    allowed = {"schema", "current", "previous", "inventory", "activation", "transition"}
    required = allowed - {"transition"}
    if not required.issubset(state) or not set(state).issubset(allowed):
        fail("deployment state has an unrecognized or incomplete v2 shape; recover manually")
    if state.get("schema") != "lmdj-pr-agent-runtime-state.v2" or not valid_inventory_record(state.get("inventory"), inventory_record) or state.get("activation") != "pending":
        fail("deployment state does not match the trusted v2 operator semantics; recover manually")
    for name in ("current", "previous"):
        if state[name] is not None and not valid_release_record(state[name], install_root):
            fail(f"deployment state {name} record is not a closed authenticated release identity; recover manually")
    if state["current"] is None and state["previous"] is not None:
        fail("deployment state has a previous release without an authenticated current release; recover manually")
    if "transition" in state:
        transition = state["transition"]
        if not isinstance(transition, dict) or set(transition) != {"action", "from", "to", "previous", "receipt"}:
            fail("deployment state transition is not a closed v2 transition; recover manually")
        if transition["action"] not in {"install", "rollback"} or transition["from"] is not None and not valid_release_record(transition["from"], install_root) or not valid_release_record(transition["to"], install_root) or transition["previous"] is not None and not valid_release_record(transition["previous"], install_root) or not valid_transition_semantics(state, transition, inventory_record):
            fail("deployment state transition is not semantically authenticated; recover manually")
    return state


def managed_effects_exist(paths: dict, install_root: Path) -> bool:
    markers = (install_root / "current", install_root / "releases", path_from_config(paths["state"]),
               path_from_config(paths["deployment_receipts"]), path_from_config(paths["operator_config"]),
               path_from_config(paths["runtime_config"]), path_from_config(paths["unit"]),
               path_from_config(paths["slice_unit"]), path_from_config(paths["slot_lock"]))
    return any(marker.exists() or marker.is_symlink() for marker in markers)


def read_state(path: Path, paths: dict, install_root: Path, inventory_record: dict) -> dict:
    if not path.exists() and not path.is_symlink():
        if managed_effects_exist(paths, install_root):
            fail("deployment state is missing while managed target effects exist; preserve the target and recover manually")
        return {}
    return validate_state(read_json(path, "deployment state"), install_root, inventory_record)


def write_state(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)


def symlink_target(path: Path) -> Path | None:
    if not path.exists() and not path.is_symlink():
        return None
    if not path.is_symlink():
        fail(f"current release path is not a symlink: {path}")
    return path.resolve()


def inventory(config: dict) -> dict:
    paths = config["paths"]
    return {
        "host": config["target"]["host"],
        "service": config["target"]["service"],
        "slice": config["target"]["slice"],
        "labels": config["target"]["labels"],
        "install_root": str(path_from_config(paths["install_root"])),
        "operator_config": str(path_from_config(paths["operator_config"])),
        "runtime_config": str(path_from_config(paths["runtime_config"])),
        "state_root": str(path_from_config(paths["state_root"])),
        "operator_state_root": str(path_from_config(paths["operator_state_root"])),
        "ledger": str(path_from_config(paths["ledger"])),
        "deployment_receipts": str(path_from_config(paths["deployment_receipts"])),
        "state": str(path_from_config(paths["state"])),
        "unit": str(path_from_config(paths["unit"])),
        "slice_unit": str(path_from_config(paths["slice_unit"])),
        "slot_lock": str(path_from_config(paths["slot_lock"])),
        "attempt_root": str(path_from_config(paths["attempt_root"])),
        "output_root": str(path_from_config(paths["output_root"])),
    }


def release_record(release: Path, archive_sha: str, archive_length: int, identity_path: Path, identity: dict, runtime_identity: tuple[str, int] | None, service_unit: bytes, slice_unit: bytes) -> dict:
    identity_sha, identity_length = sha256(identity_path)
    return {"release": str(release), "archive_sha256": archive_sha, "archive_byte_length": archive_length,
            "deployment_identity_sha256": identity_sha, "deployment_identity_byte_length": identity_length,
            "member_identities": identity["files"],
            "runtime_config_sha256": runtime_identity[0] if runtime_identity else None,
            "runtime_config_byte_length": runtime_identity[1] if runtime_identity else None,
            "service_unit_sha256": hashlib.sha256(service_unit).hexdigest(),
            "service_unit_byte_length": len(service_unit),
            "slice_unit_sha256": hashlib.sha256(slice_unit).hexdigest(),
            "slice_unit_byte_length": len(slice_unit)}


def validate_state_units(config: dict, state: dict, service_unit_path: Path, slice_unit_path: Path) -> None:
    current = state.get("current")
    if not isinstance(current, dict):
        validate_generated_unit(service_unit_path, None, None, "service unit")
        validate_generated_unit(slice_unit_path, None, None, "slice unit")
        return
    validate_generated_unit(service_unit_path, current.get("service_unit_sha256"), current.get("service_unit_byte_length"), "service unit")
    validate_generated_unit(slice_unit_path, current.get("slice_unit_sha256"), current.get("slice_unit_byte_length"), "slice unit")


def append_receipt_once(path: Path, record: dict) -> None:
    if path.is_symlink():
        fail("deployment receipts must not be a symlink")
    transition = record.get("transition_id")
    if not isinstance(transition, str) or not transition:
        fail("deployment receipt lacks a stable transition ID")
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    matches = 0
    if path.exists():
        if not path.is_file():
            fail("deployment receipts must be a regular file")
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                existing = json.loads(line)
            except json.JSONDecodeError as exc:
                fail(f"deployment receipts contain malformed JSON: {exc}")
            if not isinstance(existing, dict):
                fail("deployment receipts contain a non-object record")
            if existing.get("transition_id") == transition:
                matches += 1
                if line != canonical or existing != record:
                    fail("deployment receipt with this transition ID is not the complete canonical pending record; recover manually")
    if matches > 1:
        fail("deployment receipts contain duplicate terminal records for this transition; recover manually")
    if matches == 1:
        return
    append_ledger(path, record)


def reconcile_transition(state_path: Path, state: dict, current: Path, service_unit_path: Path, slice_unit_path: Path, receipt_path: Path, install_root: Path, inventory_record: dict, owner_identity: tuple[int, int] | None, identity_overrides: dict[str, tuple[int, int]]) -> dict:
    transition = state.get("transition")
    if not isinstance(transition, dict):
        return state
    # Re-validate even for transitions created in this process: no receipt,
    # state clear, or other reconciliation write may precede this admission.
    validate_state(state, install_root, inventory_record)
    target = transition.get("to")
    if not isinstance(target, dict) or not isinstance(target.get("release"), str):
        fail("interrupted deployment transition has no authenticated target; reconcile state manually")
    target_path = Path(target["release"])
    if symlink_target(current) == target_path:
        verify_release(target_path, target, owner_identity, identity_overrides)
        validate_generated_unit(service_unit_path, target.get("service_unit_sha256"), target.get("service_unit_byte_length"), "service unit")
        validate_generated_unit(slice_unit_path, target.get("slice_unit_sha256"), target.get("slice_unit_byte_length"), "slice unit")
        receipt = transition.get("receipt")
        if not isinstance(receipt, dict):
            fail("interrupted deployment transition lacks a durable receipt")
        append_receipt_once(receipt_path, receipt)
        state["current"] = target
        state["previous"] = transition.get("previous")
        state.pop("transition", None)
        write_state(state_path, state)
        return state
    fail("interrupted deployment transition is durable but incomplete; reconcile unit files and current symlink before retry")


def run() -> int:
    config_source = Path(os.path.abspath(CONFIG_ARG))
    config = read_json(config_source, "deployment config")
    validate_config(config)
    paths = config["paths"]
    install_root = path_from_config(paths["install_root"])
    current = install_root / "current"
    state_path = path_from_config(paths["state"])
    bundle_path = Path(BUNDLE_ARG).resolve() if BUNDLE_ARG else None
    identity_path = Path(IDENTITY_ARG).resolve() if IDENTITY_ARG else None
    runtime_source = Path(os.path.abspath(RUNTIME_CONFIG_ARG)) if RUNTIME_CONFIG_ARG else None
    if MODE in {"dry-run", "verify", "install"}:
        if bundle_path is None or identity_path is None:
            fail(f"{MODE} requires --bundle and --identity")
        if not bundle_path.is_file() or not identity_path.is_file():
            fail("bundle and detached identity must be present regular files")
        runtime_identity = validate_runtime_config(config, runtime_source, config["active"] and MODE in {"verify", "install"})
        archive_sha, archive_length, extracted, identity = validate_bundle(config, bundle_path, identity_path, MODE == "install")
        if extracted is not None:
            shutil.rmtree(extracted)
        print(json.dumps({"mode": MODE, "active": config["active"], "inventory": inventory(config),
                          "archive": {"sha256": archive_sha, "byte_length": archive_length},
                          "detached_identity": identity_path.name,
                          "activation": "not performed"}, sort_keys=True))
        if MODE in {"dry-run", "verify"}:
            return 0
        if not config["active"]:
            fail("trusted deployment config is inactive; no installation was performed")
        if runtime_source is None or runtime_identity is None:
            fail("install requires a separately supplied operator runtime config")
        operator_identity, owner_identity, fixture_overrides = deployment_identities(config)
        release = install_root / "releases" / archive_sha
        service_unit, slice_unit = render_unit(config, release)
        operator_config = path_from_config(paths["operator_config"])
        target_runtime = path_from_config(paths["runtime_config"])
        slot_lock = path_from_config(paths["slot_lock"])
        if slot_lock.exists() or slot_lock.is_symlink():
            if slot_lock.is_symlink() or not slot_lock.is_file():
                fail(f"slot lock must be a regular file: {slot_lock}")
        if release.exists() and not release.is_dir():
            fail(f"release path is not a directory: {release}")
        validate_operator_boundary(config, config_source, runtime_source, operator_identity, owner_identity, fixture_overrides)
        state = read_state(state_path, paths, install_root, inventory(config))
        # A pristine operator-state root is the minimal durable-intent substrate;
        # it is created only after the state-less/closed-state admission above.
        ensure_directory(path_from_config(paths["operator_state_root"]), 0o700)
        if ROOT == Path("/"):
            os.chown(path_from_config(paths["operator_state_root"]), operator_identity[0], operator_identity[1])
        state = reconcile_transition(state_path, state, current, path_from_config(paths["unit"]), path_from_config(paths["slice_unit"]), path_from_config(paths["deployment_receipts"]), install_root, inventory(config), owner_identity, fixture_overrides)
        release_identity = release_record(release, archive_sha, archive_length, identity_path, identity, runtime_identity, service_unit.encode(), slice_unit.encode())
        current_target = symlink_target(current)
        validate_protected(operator_config, config_source.read_bytes(), "operator config")
        validate_protected(target_runtime, runtime_source.read_bytes(), "operator runtime config")
        validate_state_units(config, state, path_from_config(paths["unit"]), path_from_config(paths["slice_unit"]))
        if release.exists():
            verify_release(release, release_identity, owner_identity, fixture_overrides)
        if current_target == release and release.is_dir():
            if state.get("current") == release_identity:
                print(json.dumps({"mode": "install", "status": "idempotent", "release": str(release)}, sort_keys=True))
                return 0
        previous_record = state.get("current") if isinstance(state.get("current"), dict) and current_target != release else state.get("previous")
        receipt = {"schema": "lmdj.pr-agent-deployment-receipt.v1", "action": "install",
                   "status": "staged", "transition_id": uuid.uuid4().hex,
                   "archive_sha256": archive_sha, "archive_byte_length": archive_length,
                   "deployment_identity_sha256": release_identity["deployment_identity_sha256"],
                   "target": inventory(config)}
        transition_state = {"schema": "lmdj-pr-agent-runtime-state.v2", "current": state.get("current"),
                            "previous": state.get("previous"), "inventory": inventory(config), "activation": "pending"}
        transition_state["transition"] = {"action": "install", "from": state.get("current"), "to": release_identity,
                                            "previous": previous_record, "receipt": receipt}
        write_state(state_path, transition_state)
        release.parent.mkdir(parents=True, exist_ok=True)
        release.parent.chmod(0o755)
        if not release.exists():
            stage = Path(tempfile.mkdtemp(prefix=f".{archive_sha}.", dir=release.parent))
            stage.chmod(0o755)
            try:
                with tarfile.open(bundle_path, mode="r:*") as archive:
                    for member in archive.getmembers():
                        relative = PurePosixPath(member.name).relative_to("pr-agent")
                        destination = stage / Path(*relative.parts)
                        if member.isdir():
                            destination.mkdir(parents=True, exist_ok=True)
                            destination.chmod(0o755)
                        elif member.isfile():
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            destination.parent.chmod(0o755)
                            destination.write_bytes(file_bytes_from_tar(archive, member))
                            destination.chmod(0o444)
                shutil.copy2(bundle_path, stage / "bundle.tar")
                shutil.copy2(identity_path, stage / "DEPLOYMENT_IDENTITY.json")
                shutil.copy2(runtime_source, stage / "runtime.toml")
                (stage / "bundle.tar").chmod(0o444)
                (stage / "DEPLOYMENT_IDENTITY.json").chmod(0o444)
                (stage / "runtime.toml").chmod(0o444)
                chown_tree(stage, owner_identity)
                os.replace(stage, release)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
        ensure_directory(install_root, 0o755)
        ensure_directory(path_from_config(paths["state_root"]), 0o750)
        ensure_directory(path_from_config(paths["operator_state_root"]), 0o700)
        ensure_directory(path_from_config(paths["temporary_root"]), 0o700)
        ensure_directory(path_from_config(paths["attempt_root"]), 0o750)
        ensure_directory(path_from_config(paths["attempt_root"]) / "engine", 0o750)
        ensure_directory(path_from_config(paths["output_root"]), 0o750)
        for writable_root in (path_from_config(paths["state_root"]), path_from_config(paths["attempt_root"]), path_from_config(paths["output_root"])):
            chown_tree(writable_root, owner_identity)
        if slot_lock.exists() or slot_lock.is_symlink():
            if slot_lock.is_symlink() or not slot_lock.is_file():
                fail(f"slot lock must be a regular file: {slot_lock}")
        else:
            slot_lock.parent.mkdir(parents=True, exist_ok=True)
            slot_lock.touch()
        slot_lock.chmod(0o660)
        if owner_identity is not None:
            os.chown(slot_lock, owner_identity[0], owner_identity[1])
        verify_release(release, release_identity, owner_identity, fixture_overrides)
        ensure_protected(operator_config, config_source.read_bytes(), 0o600, operator_identity)
        ensure_protected(target_runtime, runtime_source.read_bytes(), 0o440, (operator_identity[0], owner_identity[1]))
        prior = state.get("current") if isinstance(state.get("current"), dict) else None
        ensure_generated_unit(path_from_config(paths["unit"]), service_unit.encode(), prior.get("service_unit_sha256") if prior else None, prior.get("service_unit_byte_length") if prior else None, "service unit")
        ensure_generated_unit(path_from_config(paths["slice_unit"]), slice_unit.encode(), prior.get("slice_unit_sha256") if prior else None, prior.get("slice_unit_byte_length") if prior else None, "slice unit")
        next_link = current.with_name(f".current-new-{os.getpid()}")
        if next_link.exists() or next_link.is_symlink():
            fail(f"refusing to reuse temporary current link: {next_link}")
        next_link.symlink_to(release)
        os.replace(next_link, current)
        state = {"schema": "lmdj-pr-agent-runtime-state.v2", "current": state.get("current"),
                 "previous": state.get("previous"), "inventory": inventory(config), "activation": "pending",
                 "transition": transition_state["transition"]}
        write_state(state_path, state)
        state = reconcile_transition(state_path, state, current, path_from_config(paths["unit"]), path_from_config(paths["slice_unit"]), path_from_config(paths["deployment_receipts"]), install_root, inventory(config), owner_identity, fixture_overrides)
        print(json.dumps({"mode": "install", "status": "staged", "release": str(release),
                          "activation": "pending; systemctl was not invoked"}, sort_keys=True))
        return 0
    if MODE == "rollback":
        operator_identity, owner_identity, fixture_overrides = deployment_identities(config)
        state = read_state(state_path, paths, install_root, inventory(config))
        # Rollback has no runtime source, but still refuses root/operator boundary drift before effects.
        validate_operator_boundary(config, config_source, None, operator_identity, owner_identity, fixture_overrides)
        state = reconcile_transition(state_path, state, current, path_from_config(paths["unit"]), path_from_config(paths["slice_unit"]), path_from_config(paths["deployment_receipts"]), install_root, inventory(config), owner_identity, fixture_overrides)
        if not state:
            fail("rollback requires a recorded previous release")
        if state.get("schema") != "lmdj-pr-agent-runtime-state.v2":
            fail("rollback requires v2 deployment state with current and previous identities")
        current_record = state.get("current")
        previous = state.get("previous")
        if not isinstance(current_record, dict) or not isinstance(current_record.get("release"), str):
            fail("rollback requires an authenticated current release record")
        if not isinstance(previous, dict) or not isinstance(previous.get("release"), str):
            fail("rollback requires a recorded previous release")
        current_path = Path(current_record["release"])
        previous_path = Path(previous["release"])
        for candidate, label, record in ((current_path, "current", current_record), (previous_path, "previous", previous)):
            if install_root not in candidate.parents or not candidate.is_dir():
                fail(f"recorded {label} release is outside the trusted install root or missing")
            verify_release(candidate, record, owner_identity, fixture_overrides)
        if symlink_target(current) != current_path:
            fail("current symlink does not match authenticated current release; reconcile before rollback")
        service_unit, slice_unit = render_unit(config, previous_path)
        desired_service_sha = hashlib.sha256(service_unit.encode()).hexdigest()
        desired_slice_sha = hashlib.sha256(slice_unit.encode()).hexdigest()
        if (desired_service_sha, len(service_unit.encode())) != (previous.get("service_unit_sha256"), previous.get("service_unit_byte_length")) or (desired_slice_sha, len(slice_unit.encode())) != (previous.get("slice_unit_sha256"), previous.get("slice_unit_byte_length")):
            fail("rollback target unit identity does not match recorded release state")
        validate_state_units(config, state, path_from_config(paths["unit"]), path_from_config(paths["slice_unit"]))
        old = symlink_target(current)
        if old == previous_path and state.get("current") == previous:
            print(json.dumps({"mode": "rollback", "status": "idempotent", "release": str(previous_path)}, sort_keys=True))
            return 0
        transition_state = dict(state)
        receipt = {"schema": "lmdj.pr-agent-deployment-receipt.v1", "action": "rollback", "status": "staged",
                   "transition_id": uuid.uuid4().hex,
                   "from_release": current_record["release"], "to_release": previous["release"], "target": inventory(config)}
        transition_state["transition"] = {"action": "rollback", "from": current_record, "to": previous,
                                            "previous": previous, "receipt": receipt}
        write_state(state_path, transition_state)
        ensure_generated_unit(path_from_config(paths["unit"]), service_unit.encode(), current_record.get("service_unit_sha256"), current_record.get("service_unit_byte_length"), "service unit")
        ensure_generated_unit(path_from_config(paths["slice_unit"]), slice_unit.encode(), current_record.get("slice_unit_sha256"), current_record.get("slice_unit_byte_length"), "slice unit")
        next_link = current.with_name(f".current-new-{os.getpid()}")
        if next_link.exists() or next_link.is_symlink():
            fail(f"refusing to reuse temporary current link: {next_link}")
        next_link.symlink_to(previous_path)
        os.replace(next_link, current)
        next_state = {"schema": "lmdj-pr-agent-runtime-state.v2", "current": current_record, "previous": previous,
                      "inventory": inventory(config), "activation": "pending", "transition": transition_state["transition"]}
        write_state(state_path, next_state)
        state = reconcile_transition(state_path, next_state, current, path_from_config(paths["unit"]), path_from_config(paths["slice_unit"]), path_from_config(paths["deployment_receipts"]), install_root, inventory(config), owner_identity, fixture_overrides)
        print(json.dumps({"mode": "rollback", "status": "staged", "release": str(previous_path),
                          "activation": "pending; systemctl was not invoked"}, sort_keys=True))
        return 0
    fail(f"unsupported mode: {MODE}")


try:
    raise SystemExit(run())
except RuntimeError as exc:
    print(f"deploy-runner: {exc}", file=sys.stderr)
    raise SystemExit(2)
PY
