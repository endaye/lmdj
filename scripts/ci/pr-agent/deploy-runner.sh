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
usage: deploy-runner.sh {dry-run|verify|stage|install|rollback}
  [--config PATH] [--bundle PATH] [--identity PATH] [--target-root PATH]

verify and install require --bundle and --identity.  target-root is intended
for isolated fixtures; production uses the absolute paths in the trusted
configuration.  stage and active verify/install also require
--runtime-config.  stage requires inactive disabled-provider config; install
requires active config and complete admission. Neither invokes systemctl.
EOF
}

[[ $# -ge 1 ]] || { usage; exit 64; }
mode=$1
shift
case "$mode" in dry-run|verify|stage|install|rollback) ;; *) usage; exit 64 ;; esac

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

exec "$python_bin" - "$mode" "$config_path" "$bundle_path" "$identity_path" "$runtime_config_path" "$target_root" "${BASH_SOURCE[0]}" <<'PY'
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
import tomllib
import uuid


MODE, CONFIG_ARG, BUNDLE_ARG, IDENTITY_ARG, RUNTIME_CONFIG_ARG, TARGET_ROOT_ARG, RUNNER_ARG = sys.argv[1:]
ROOT = Path(TARGET_ROOT_ARG).resolve()
if not ROOT.is_absolute():
    raise SystemExit("deploy-runner: target root must be absolute")
RUNNER_PATH = Path(RUNNER_ARG).resolve()


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
    def parent_identity(candidate: Path) -> tuple[int, int]:
        resolved = str(candidate.resolve())
        if resolved in overrides:
            return overrides[resolved]
        # Fixture identity maps enumerate the pre-existing trusted roots. A
        # directory created below such a root inherits that emulated identity;
        # real-host checks still use the actual stat identity at every parent.
        ancestor = candidate.parent
        while ancestor != ROOT and ancestor != ancestor.parent:
            ancestor_resolved = str(ancestor.resolve())
            if ancestor_resolved in overrides:
                return overrides[ancestor_resolved]
            ancestor = ancestor.parent
        return observed_identity(candidate, overrides)
    parent = path.parent
    while True:
        if parent.is_symlink():
            fail(f"{label} parent is a symlink: {parent}")
        if parent.exists():
            if not parent.is_dir():
                fail(f"{label} parent is not a directory: {parent}")
            if parent_identity(parent) != operator:
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
    state_path = path_from_config(paths["state"])
    receipt_path = path_from_config(paths["deployment_receipts"])
    # Validate the named roots before walking child paths so diagnostics and
    # the admission boundary remain tied to the actual root that drifted.
    validate_owned_directory(install_root, operator, 0o755, overrides, "install root")
    validate_owned_directory(operator_state, operator, 0o700, overrides, "operator state")
    for path, label in ((install_root, "install root"), (operator_state, "operator state"),
                        (operator_config, "operator inventory"), (target_runtime, "operator runtime target"),
                        (service_unit, "service unit"), (slice_unit, "slice unit"),
                        (state_path, "operator state"), (receipt_path, "deployment receipts")):
        require_secure_parent_chain(path, operator, overrides, label)
    if ROOT == Path("/"):
        require_secure_parent_chain(config_source, operator, overrides, "operator inventory source")
    if runtime_source is not None and ROOT == Path("/"):
        require_secure_parent_chain(runtime_source, operator, overrides, "operator runtime source")
    validate_owned_file(operator_config, operator, 0o600, overrides, "operator inventory")
    validate_owned_file(config_source, operator, 0o600, overrides, "operator inventory source", required=True)
    validate_owned_file(target_runtime, (operator[0], service[1]), 0o440, overrides, "operator runtime target")
    if runtime_source is not None:
        validate_owned_file(runtime_source, (operator[0], service[1]), 0o440, overrides, "operator runtime source", required=True)
    validate_owned_file(service_unit, operator, 0o644, overrides, "service unit")
    validate_owned_file(slice_unit, operator, 0o644, overrides, "slice unit")
    # State and receipt files are authority, not repairable output.  Missing
    # files remain valid for the pristine creation boundary; existing files
    # must already have the exact operator identity and private mode.
    validate_owned_file(state_path, operator, 0o600, overrides, "deployment state")
    validate_owned_file(receipt_path, operator, 0o600, overrides, "deployment receipts")


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
    if runtime_config["sha256"] is not None and not valid_sha256(runtime_config["sha256"]):
        fail("operator runtime config SHA-256 is invalid")
    if runtime_config["byte_length"] is not None and (type(runtime_config["byte_length"]) is not int or runtime_config["byte_length"] < 0):
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
    if any(type(value) is not bool for value in admission.values()):
        fail("admission fields must be strict booleans; why: ambiguous admission cannot authorize a transition; remedy: use true or false JSON values")
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


def validate_runtime_config(config: dict, source: Path | None, required: bool, require_binding: bool = False) -> tuple[str, int] | None:
    if source is None:
        if required:
            fail("active verify/install requires --runtime-config")
        return None
    if source.is_symlink() or not source.is_file():
        fail("operator runtime config source must be a regular file, not a symlink or missing")
    actual_sha, actual_length = sha256(source)
    expected = config["runtime_config"]
    if require_binding and (expected["sha256"] is None or expected["byte_length"] is None):
        fail("operator runtime config binding must contain a non-null SHA-256 and byte length before stage effects")
    if expected["sha256"] is not None and (actual_sha, actual_length) != (expected["sha256"], expected["byte_length"]):
        fail("operator runtime config SHA-256/byte length does not match the trusted binding")
    return actual_sha, actual_length


def validate_staged_runtime_config(source: Path, runtime_identity: tuple[str, int]) -> None:
    """Parse only the trusted TOML shape; stage must never admit an enabled provider."""
    try:
        document = tomllib.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        fail(f"staged runtime TOML is invalid: {exc}; why: stage must validate supplied bytes before effects; remedy: provide valid TOML")
    providers = document.get("providers")
    if not isinstance(providers, dict) or not providers:
        fail("staged runtime TOML has no provider inventory; why: stage must prove every provider is disabled; remedy: provide providers.<name>.enabled=false entries")
    for name, provider in providers.items():
        if not isinstance(name, str) or not isinstance(provider, dict):
            fail(f"staged runtime provider entry is not a safe table: {name}; why: stage must not execute or import input; remedy: provide provider tables with enabled=false")
        if type(provider.get("enabled")) is not bool or provider["enabled"]:
            fail(f"staged runtime provider is enabled: {name}; why: inactive stage cannot authorize a paid provider; remedy: set providers.{name}.enabled=false")
    if runtime_identity[0] is None or runtime_identity[1] is None:
        fail("staged runtime config identity is incomplete; why: revision identity must be complete before effects; remedy: bind SHA-256 and byte length")


def render_unit(config: dict, engine_root: Path, *, active: bool | None = None,
                target_inventory: dict | None = None) -> tuple[str, str]:
    target = config["target"]
    runtime = config["runtime"]
    paths = config["paths"]
    blocked_environment = " ".join(runtime["blocked_environment"])
    current = engine_root
    active = config["active"] if active is None else active
    runtime_config = engine_root / "runtime.toml"
    def inventory_path(name: str) -> Path:
        return Path(target_inventory[name]) if target_inventory is not None else path_from_config(paths[name])

    attempt = inventory_path("attempt_root")
    output = inventory_path("output_root")
    slot_lock = inventory_path("slot_lock")
    ledger = inventory_path("ledger")
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
ExecStart={('/usr/bin/flock --nonblock --exclusive ' + str(slot_lock) + ' ' + runtime['python'] + ' ' + str(current / 'pr_agent_review.py') + ' --input ' + str(attempt / 'input.json') + ' --config ' + str(runtime_config) + ' --source-root ' + str(current) + ' --engine-cwd ' + str(attempt / 'engine') + ' --deployment-identity ' + str(current / 'DEPLOYMENT_IDENTITY.json') + ' --ledger ' + str(ledger) + ' --output-dir ' + str(output)) if active else '/usr/bin/false'}
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
        fsync_file(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
    if temporary.exists() or temporary.is_symlink():
        fail(f"refusing to reuse temporary operator path: {temporary}")
    temporary.write_bytes(data)
    temporary.chmod(mode)
    if identity is not None and (ROOT == Path("/") or identity == (os.getuid(), os.getgid())):
        os.chown(temporary, identity[0], identity[1])
    fsync_file(temporary)
    os.replace(temporary, path)
    fsync_directory(path.parent)


def fsync_file(path: Path) -> None:
    """Flush file bytes and final mode/ownership metadata before publication."""
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def fsync_directory(path: Path) -> None:
    """Make an atomic replacement durable before reporting a transition."""
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def fsync_tree(path: Path) -> None:
    """Flush copied release bytes and every enclosing directory before publish."""
    for child in path.rglob("*"):
        if child.is_file() and not child.is_symlink():
            with child.open("rb") as handle:
                os.fsync(handle.fileno())
    directories = [child for child in path.rglob("*") if child.is_dir() and not child.is_symlink()]
    for directory in sorted(directories, key=lambda value: len(value.parts), reverse=True):
        fsync_directory(directory)
    fsync_directory(path)


def replace_authenticated(path: Path, data: bytes, mode: int, old_sha: str | None,
                           old_length: int | None, label: str,
                           identity: tuple[int, int] | None = None) -> None:
    """Replace a managed file only after authenticating its current bytes."""
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            fail(f"{label} is not a regular file")
        actual = sha256(path)
        if old_sha is None or actual != (old_sha, old_length):
            fail(f"current {label} identity does not match authenticated state; why: replacing unknown bytes could hide a concurrent or forged mutation; remedy: retain files and recover manually")
        if path.read_bytes() == data:
            path.chmod(mode)
            fsync_file(path)
            return
    elif old_sha is not None:
        fail(f"current {label} is missing during an authenticated replacement; remedy: recover the retained transition manually")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
    if temporary.exists() or temporary.is_symlink():
        fail(f"refusing to reuse temporary operator path: {temporary}")
    temporary.write_bytes(data)
    temporary.chmod(mode)
    if identity is not None and (ROOT == Path("/") or identity == (os.getuid(), os.getgid())):
        os.chown(temporary, identity[0], identity[1])
    fsync_file(temporary)
    os.replace(temporary, path)
    fsync_directory(path.parent)


def validate_protected(path: Path, data: bytes, label: str) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
            fail(f"{label} differs and will not be overwritten")


def validate_generated_unit(path: Path, expected_sha: str | None, expected_length: int | None, label: str,
                           operator_identity: tuple[int, int] | None = None,
                           identity_overrides: dict[str, tuple[int, int]] | None = None) -> None:
    if not path.exists() and not path.is_symlink():
        if expected_sha is not None:
            fail(f"{label} is missing during an authenticated transition")
        return
    if path.is_symlink() or not path.is_file():
        fail(f"{label} is not a regular file")
    if path.stat().st_mode & 0o777 != 0o644:
        fail(f"{label} owner or mode is not approved: {path}")
    if operator_identity is not None and observed_identity(path, identity_overrides or {}) != operator_identity:
        fail(f"{label} owner or mode is not approved: {path}")
    actual_sha, actual_length = sha256(path)
    if expected_sha is None or (actual_sha, actual_length) != (expected_sha, expected_length):
        fail(f"{label} digest does not match the authenticated deployment state")


def ensure_generated_unit(path: Path, data: bytes, expected_sha: str | None, expected_length: int | None, label: str,
                          operator_identity: tuple[int, int] | None = None,
                          identity_overrides: dict[str, tuple[int, int]] | None = None) -> None:
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file():
            fail(f"{label} is not a regular file: {path}")
        validate_generated_unit(path, expected_sha, expected_length, label, operator_identity, identity_overrides)
        temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
        temporary.write_bytes(data)
        temporary.chmod(0o644)
        if operator_identity is not None and ROOT == Path("/"):
            os.chown(temporary, operator_identity[0], operator_identity[1])
        fsync_file(temporary)
        os.replace(temporary, path)
        fsync_directory(path.parent)
        return
    if expected_sha is not None:
        fail(f"{label} is missing during an authenticated transition")
    ensure_protected(path, data, 0o644, operator_identity)


def ensure_directory(path: Path, mode: int) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        fail(f"trusted directory is not a directory: {path}")
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(mode)
    fsync_directory(path)


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
    fsync_file(path)
    fsync_directory(path.parent)


def verify_release(release: Path, record: dict, owner_identity: tuple[int, int] | None = None,
                   identity_overrides: dict[str, tuple[int, int]] | None = None,
                   parent_identity: tuple[int, int] | None = None) -> None:
    if not release.is_dir() or release.is_symlink():
        fail(f"release is not a regular immutable directory: {release}")
    overrides = identity_overrides or {}
    if parent_identity is not None:
        require_secure_parent_chain(release, parent_identity, overrides, "release")
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
    if not valid_member_identities(expected_files) or deployment_identity.get("files") != expected_files:
        fail(f"installed detached member inventory mismatch: {release}")
    runtime_config = release / "runtime.toml"
    if not runtime_config.is_file() or runtime_config.is_symlink():
        fail(f"installed runtime config is not a regular file: {release}")
    runtime_sha, runtime_length = sha256(runtime_config)
    if (runtime_sha, runtime_length) != (record.get("runtime_config_sha256"), record.get("runtime_config_byte_length")):
        fail(f"installed runtime config identity mismatch: {release}")
    operator_config = release / "operator-config.json"
    if not operator_config.is_file() or operator_config.is_symlink():
        fail(f"installed operator config is not a regular file: {release}")
    operator_sha, operator_length = sha256(operator_config)
    if (operator_sha, operator_length) != (record.get("operator_config_sha256"), record.get("operator_config_byte_length")):
        fail(f"installed operator config identity mismatch: {release}")
    for unit_name, sha_key, length_key, label in (
            ("service.unit", "service_unit_sha256", "service_unit_byte_length", "stored service unit"),
            ("slice.unit", "slice_unit_sha256", "slice_unit_byte_length", "stored slice unit")):
        stored = release / unit_name
        if not stored.is_file() or stored.is_symlink():
            fail(f"{label} is not a regular file: {release}")
        stored_sha, stored_length = sha256(stored)
        if (stored_sha, stored_length) != (record.get(sha_key), record.get(length_key)):
            fail(f"{label} identity mismatch: {release}")
    for member in deployment_identity.get("files", {}).values():
        actual = release / Path(*PurePosixPath(member["path"]).parts)
        if not actual.is_file() or actual.is_symlink():
            fail(f"installed extracted member is not a regular file: {member['path']}")
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
            if not actual.is_file() or actual.is_symlink():
                fail(f"installed archive member is not a regular file: {relative}")
            actual_sha, actual_length = sha256(actual)
            if (actual_sha, actual_length) != (digest.hexdigest(), length):
                fail(f"installed archive extracted bytes mismatch: {relative}")
    revision_record_path = release / "REVISION_RECORD.json"
    if not revision_record_path.is_file() or revision_record_path.is_symlink():
        fail(f"installed release lacks its immutable revision record: {release}")
    revision_record_bytes = revision_record_path.read_bytes()
    revision_record = read_json(revision_record_path, "installed immutable revision record")
    if revision_record_bytes != canonical_record_bytes(revision_record):
        fail(f"installed immutable revision record bytes are not canonical: {release}; remedy: retain the immutable record and recover manually")
    if revision_record != record:
        fail(f"installed immutable revision record mismatch: {release}")
    allowed_extra = {"bundle.tar", "DEPLOYMENT_IDENTITY.json", "runtime.toml", "operator-config.json", "service.unit", "slice.unit", "REVISION_RECORD.json"}
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


def valid_release_record(record: object, install_root: Path, trusted_inventory: dict | None = None) -> bool:
    required = {"release", "archive_sha256", "archive_byte_length", "deployment_identity_sha256",
                "deployment_identity_byte_length", "member_identities", "runtime_config_sha256",
                "runtime_config_byte_length", "operator_config_path", "operator_config_sha256",
                "operator_config_byte_length", "runtime_config_path", "target_inventory", "active", "admission",
                "deployment_tool_sha256", "deployment_tool_byte_length",
                "service_unit_sha256", "service_unit_byte_length", "slice_unit_sha256",
                "slice_unit_byte_length"}
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
    revision = candidate.name
    if not valid_sha256(revision) or candidate != install_root / "releases" / revision:
        return False
    for name in ("archive_sha256", "deployment_identity_sha256", "runtime_config_sha256", "deployment_tool_sha256", "service_unit_sha256", "slice_unit_sha256"):
        if not valid_sha256(record.get(name)):
            return False
    for name in ("archive_byte_length", "deployment_identity_byte_length", "runtime_config_byte_length", "operator_config_byte_length", "deployment_tool_byte_length", "service_unit_byte_length", "slice_unit_byte_length"):
        value = record.get(name)
        if type(value) is not int or value < 0:
            return False
    if (record["archive_byte_length"] <= 0 or record["deployment_identity_byte_length"] <= 0
            or record["runtime_config_byte_length"] <= 0 or record["operator_config_byte_length"] <= 0):
        return False
    if record["deployment_tool_byte_length"] <= 0 or record["service_unit_byte_length"] <= 0 or record["slice_unit_byte_length"] <= 0:
        return False
    if not valid_member_identities(record.get("member_identities")):
        return False
    if not valid_inventory_shape(record.get("target_inventory")) or not isinstance(record.get("active"), bool):
        return False
    target_inventory = record["target_inventory"]
    if target_inventory["install_root"] != str(install_root):
        return False
    if trusted_inventory is not None:
        for key in INVENTORY_KEYS - {"operator_config"}:
            if target_inventory[key] != trusted_inventory[key]:
                return False
        if Path(target_inventory["operator_config"]).parent != Path(trusted_inventory["operator_config"]).parent:
            return False
    if set(record.get("admission", {})) != {"operator_access", "runner04_classification", "capacity_receipts", "filesystem_isolation", "activation_receipt", "runtime_config_receipt"} or any(type(value) is not bool for value in record["admission"].values()):
        return False
    expected_revision = revision_id_from_material(
        record["archive_sha256"], record["archive_byte_length"], record["deployment_identity_sha256"],
        record["deployment_identity_byte_length"],
        (record["runtime_config_sha256"], record["runtime_config_byte_length"]),
        (record["operator_config_sha256"], record["operator_config_byte_length"]),
        record["target_inventory"], record["active"], record["admission"],
        (record["deployment_tool_sha256"], record["deployment_tool_byte_length"]))
    return (isinstance(record.get("operator_config_path"), str)
            and valid_sha256(record.get("operator_config_sha256"))
            and isinstance(record.get("runtime_config_path"), str)
            and record["runtime_config_path"] == record["target_inventory"]["runtime_config"]
            and record["operator_config_path"] == record["target_inventory"]["operator_config"]
            and revision == expected_revision)


def valid_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


MEMBER_KEYS = {"manifest", "adapter", "default_config", "requirements_lock", "stock_tokenizer_asset"}


def valid_member_identities(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != MEMBER_KEYS:
        return False
    for member in value.values():
        if not isinstance(member, dict) or set(member) != {"path", "sha256", "byte_length"}:
            return False
        relative = PurePosixPath(member["path"]) if isinstance(member.get("path"), str) else None
        if relative is None or relative.is_absolute() or ".." in relative.parts or str(relative) != member["path"]:
            return False
        if not valid_sha256(member.get("sha256")) or type(member.get("byte_length")) is not int or member["byte_length"] < 0:
            return False
    return True


def valid_receipt(record: object, inventory_record: dict) -> bool:
    if not isinstance(record, dict):
        return False
    action = record.get("action")
    common = {"schema", "action", "status", "transition_id", "from_release", "to_release", "target",
              "from_record_sha256", "from_record_byte_length", "to_record_sha256", "to_record_byte_length"}
    if action == "install":
        required = common | {"archive_sha256", "archive_byte_length", "deployment_identity_sha256"}
    elif action == "rollback":
        required = common
    else:
        return False
    if not (set(record) == required and record.get("schema") == "lmdj.pr-agent-deployment-receipt.v3"
            and record.get("status") == "staged" and isinstance(record.get("transition_id"), str)
            and bool(record["transition_id"]) and valid_inventory_shape(record.get("target"))
            and (record.get("from_release") is None or isinstance(record.get("from_release"), str))
            and isinstance(record.get("to_release"), str) and bool(record.get("to_release"))):
        return False
    for name in ("from_record_sha256", "to_record_sha256"):
        if record.get(name) is not None and not valid_sha256(record.get(name)):
            return False
    for name in ("from_record_byte_length", "to_record_byte_length"):
        value = record.get(name)
        if value is not None and (type(value) is not int or value <= 0):
            return False
    if (record.get("from_release") is None
            and (record.get("from_record_sha256") is not None or record.get("from_record_byte_length") is not None)):
        return False
    if record.get("to_release") is None or record.get("to_record_sha256") is None or record.get("to_record_byte_length") is None:
        return False
    if action == "install":
        return (valid_sha256(record.get("archive_sha256"))
                and type(record.get("archive_byte_length")) is int
                and record["archive_byte_length"] > 0
                and valid_sha256(record.get("deployment_identity_sha256")))
    return bool(record.get("from_release"))


def valid_transition_semantics(state: dict, transition: dict, inventory_record: dict) -> bool:
    """Bind an interrupted intent and its receipt to one real transition shape."""
    action = transition["action"]
    before = transition["from"]
    target = transition["to"]
    prior = transition["previous"]
    receipt = transition["receipt"]
    current = state["current"]
    previous = state["previous"]
    if not valid_receipt(receipt, inventory_record) or receipt["target"] != inventory_record or receipt["action"] != action:
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
            # The pending state retains the exact replayed base pair.  Its
            # previous may equal the prospective target; the future previous
            # is carried only in transition metadata until publication.
            pass
        elif current == target:
            if previous != before:
                return False
        else:
            return False
        return (receipt["from_release"] == (before["release"] if before is not None else None)
                and receipt["to_release"] == target["release"]
                and receipt["archive_sha256"] == target["archive_sha256"]
                and receipt["archive_byte_length"] == target["archive_byte_length"]
                and receipt["deployment_identity_sha256"] == target["deployment_identity_sha256"])
    # A rollback intent is meaningful from current to previous.  Its far side
    # records the former current as the new previous so a later install can
    # move forward again without losing the exact prior identity.
    if prior != before or before == target:
        return False
    if current == before:
        # The pending state retains the replayed base pair; the future
        # previous record is carried only by transition metadata.
        pass
    elif current == target:
        if previous != before:
            return False
    else:
        return False
    return receipt["from_release"] == before["release"] and receipt["to_release"] == target["release"]


def valid_inventory_record(record: object, expected: dict) -> bool:
    if not valid_inventory_shape(record) or not valid_inventory_shape(expected) or set(record) != set(expected):
        return False
    for key, value in record.items():
        if key == "operator_config":
            if (not isinstance(value, str) or not value.startswith("/") or ".." in PurePosixPath(value).parts
                    or Path(value).parent != Path(expected[key]).parent):
                return False
        elif value != expected[key]:
            return False
    return True


def validate_state(state: object, install_root: Path, inventory_record: dict) -> dict:
    if not isinstance(state, dict):
        fail("deployment state must be a JSON object")
    allowed = {"schema", "current", "previous", "inventory", "activation", "latest_transition", "transition"}
    required = allowed - {"transition"}
    if not required.issubset(state) or not set(state).issubset(allowed):
        fail("deployment state has an unrecognized or incomplete v3 shape; recover manually")
    if state.get("schema") == "lmdj-pr-agent-runtime-state.v2":
        fail("legacy v2 deployment state is unsupported; no effects were changed; remedy: have the operator perform the reviewed v2-to-v3 recovery before retry")
    if state.get("schema") != "lmdj-pr-agent-runtime-state.v3" or not valid_inventory_record(state.get("inventory"), inventory_record) or state.get("activation") != "pending":
        fail("deployment state does not match the trusted v3 operator semantics; recover manually")
    for name in ("current", "previous"):
        if state[name] is not None and not valid_release_record(state[name], install_root, state["inventory"]):
            fail(f"deployment state {name} record is not a closed authenticated release identity; recover manually")
    if state["current"] is None and state["previous"] is not None:
        fail("deployment state has a previous release without an authenticated current release; recover manually")
    latest = state.get("latest_transition")
    if isinstance(latest, dict) and latest.get("schema") == "lmdj.pr-agent-deployment-receipt.v3" and any(
            key not in latest for key in ("from_record_sha256", "from_record_byte_length",
                                          "to_record_sha256", "to_record_byte_length")):
        fail("deployment receipt lacks canonical record commitments; remedy: perform the reviewed v3 recovery without inferring historical authority")
    if latest is not None and not valid_receipt(latest, inventory_record):
        fail("deployment state latest transition is not a closed authenticated receipt; recover manually")
    if "transition" in state:
        transition = state["transition"]
        if not isinstance(transition, dict) or set(transition) != {"action", "from", "to", "previous", "receipt"}:
            fail("deployment state transition is not a closed v2 transition; recover manually")
        if transition["action"] not in {"install", "rollback"} or transition["from"] is not None and not valid_release_record(transition["from"], install_root, state["inventory"]) or not valid_release_record(transition["to"], install_root, state["inventory"]) or transition["previous"] is not None and not valid_release_record(transition["previous"], install_root, state["inventory"]) or not valid_transition_semantics(state, transition, inventory_record):
            fail("deployment state transition is not semantically authenticated; recover manually")
        if latest is not None and latest.get("to_release") not in {
                record.get("release") for record in (state.get("current"), transition.get("from"), transition.get("to"))
                if isinstance(record, dict)}:
            fail("deployment state latest transition is not bound to the retained transition; recover manually")
        if latest is None and transition.get("from") is not None:
            fail("deployment state is missing the prior latest transition witness; recover manually")
    elif latest is not None:
        expected_current = state["current"]["release"] if isinstance(state.get("current"), dict) else None
        expected_previous = state["previous"]["release"] if isinstance(state.get("previous"), dict) else None
        if latest.get("to_release") != expected_current or latest.get("from_release") != expected_previous:
            fail("deployment state latest transition is not bound to current and previous; recover manually")
    elif state.get("current") is not None:
        fail("deployment state is missing the latest transition witness; recover manually")
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
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    fsync_directory(path.parent)


def symlink_target(path: Path) -> Path | None:
    if not path.exists() and not path.is_symlink():
        return None
    if not path.is_symlink():
        fail(f"current release path is not a symlink: {path}")
    return path.resolve()


def direct_pointer_matches(path: Path, expected: Path) -> bool:
    """Require the recorded release as the literal, direct symlink target."""
    if not path.is_symlink():
        return False
    return os.readlink(path) == str(expected)


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


INVENTORY_KEYS = {"host", "service", "slice", "labels", "install_root", "operator_config",
                  "runtime_config", "state_root", "operator_state_root", "ledger",
                  "deployment_receipts", "state", "unit", "slice_unit", "slot_lock",
                  "attempt_root", "output_root"}


def valid_inventory_shape(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != INVENTORY_KEYS:
        return False
    if any(not isinstance(value[key], str) or not value[key].startswith("/")
           or ".." in PurePosixPath(value[key]).parts or str(PurePosixPath(value[key])) != value[key]
           for key in INVENTORY_KEYS - {"labels", "host", "service", "slice"}):
        return False
    return (isinstance(value["labels"], list) and all(isinstance(label, str) for label in value["labels"])
            and value["service"] == "lmdj-pr-agent.service"
            and value["slice"] == "lmdj-pr-review.slice")


def release_record(release: Path, archive_sha: str, archive_length: int, identity_path: Path, identity: dict,
                   runtime_identity: tuple[str, int] | None, service_unit: bytes, slice_unit: bytes,
                   operator_bytes: bytes, target_inventory: dict, active: bool, admission: dict) -> dict:
    identity_sha, identity_length = sha256(identity_path)
    operator_sha = hashlib.sha256(operator_bytes).hexdigest()
    runner_sha, runner_length = sha256(RUNNER_PATH)
    return {"release": str(release), "archive_sha256": archive_sha, "archive_byte_length": archive_length,
            "deployment_identity_sha256": identity_sha, "deployment_identity_byte_length": identity_length,
            "member_identities": identity["files"],
            "runtime_config_sha256": runtime_identity[0] if runtime_identity else None,
            "runtime_config_byte_length": runtime_identity[1] if runtime_identity else None,
            "operator_config_path": target_inventory["operator_config"],
            "operator_config_sha256": operator_sha,
            "operator_config_byte_length": len(operator_bytes),
            "runtime_config_path": target_inventory["runtime_config"],
            "target_inventory": target_inventory,
            "active": active,
            "admission": admission,
            "deployment_tool_sha256": runner_sha,
            "deployment_tool_byte_length": runner_length,
            "service_unit_sha256": hashlib.sha256(service_unit).hexdigest(),
            "service_unit_byte_length": len(service_unit),
            "slice_unit_sha256": hashlib.sha256(slice_unit).hexdigest(),
            "slice_unit_byte_length": len(slice_unit)}


def canonical_record_bytes(record: dict) -> bytes:
    """Exact immutable record bytes committed by the operator receipt."""
    return (json.dumps(record, sort_keys=True, indent=2) + "\n").encode()


def record_commitment(record: dict) -> tuple[str, int]:
    data = canonical_record_bytes(record)
    return hashlib.sha256(data).hexdigest(), len(data)


def revision_id_from_material(archive_sha: str, archive_length: int, identity_sha: str,
                              identity_length: int, runtime_identity: tuple[str, int],
                              operator_identity: tuple[str, int], target_inventory: dict,
                              active: bool, admission: dict,
                              deployment_tool_identity: tuple[str, int]) -> str:
    """Derive an immutable revision without hashing a unit containing its own path."""
    payload = {
        "schema": "lmdj.pr-agent-deployment-revision.v1",
        "archive": {"sha256": archive_sha, "byte_length": archive_length},
        "detached_identity": {"sha256": identity_sha, "byte_length": identity_length},
        "runtime_config": {"sha256": runtime_identity[0], "byte_length": runtime_identity[1]},
        "operator_config": {"sha256": operator_identity[0], "byte_length": operator_identity[1]},
        "inventory": target_inventory,
        "active": active,
        "admission": admission,
        "deployment_tool": {"sha256": deployment_tool_identity[0], "byte_length": deployment_tool_identity[1]},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def revision_id(config: dict, archive_sha: str, archive_length: int, identity_sha: str,
                identity_length: int, runtime_identity: tuple[str, int], operator_bytes: bytes) -> str:
    return revision_id_from_material(
        archive_sha, archive_length, identity_sha, identity_length, runtime_identity,
        (hashlib.sha256(operator_bytes).hexdigest(), len(operator_bytes)), inventory(config),
        config["active"], config["admission"], sha256(RUNNER_PATH))


def validate_state_units(config: dict, state: dict, service_unit_path: Path, slice_unit_path: Path,
                         operator_identity: tuple[int, int] | None = None,
                         identity_overrides: dict[str, tuple[int, int]] | None = None) -> None:
    current = state.get("current")
    if not isinstance(current, dict):
        validate_generated_unit(service_unit_path, None, None, "service unit", operator_identity, identity_overrides)
        validate_generated_unit(slice_unit_path, None, None, "slice unit", operator_identity, identity_overrides)
        return
    validate_generated_unit(service_unit_path, current.get("service_unit_sha256"), current.get("service_unit_byte_length"), "service unit", operator_identity, identity_overrides)
    validate_generated_unit(slice_unit_path, current.get("slice_unit_sha256"), current.get("slice_unit_byte_length"), "slice unit", operator_identity, identity_overrides)


def append_receipt_once(path: Path, record: dict) -> None:
    if path.is_symlink():
        fail("deployment receipts must not be a symlink")
    inventory_record = record.get("target")
    if not valid_receipt(record, inventory_record):
        fail("deployment receipt is not the closed v3 transition shape; recover manually")
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
            if not valid_receipt(existing, inventory_record):
                if existing.get("schema") == "lmdj.pr-agent-deployment-receipt.v3" and any(
                        key not in existing for key in ("from_record_sha256", "from_record_byte_length",
                                                        "to_record_sha256", "to_record_byte_length")):
                    fail("deployment receipt lacks canonical record commitments; remedy: perform the reviewed v3 recovery without inferring historical authority")
                fail("deployment receipts contain a legacy, malformed, or forged transition ID; recover manually")
            existing_canonical = json.dumps(existing, sort_keys=True, separators=(",", ":"))
            if line != existing_canonical:
                fail("deployment receipts contain a noncanonical transition record; recover manually")
            if existing.get("transition_id") == transition:
                matches += 1
                if line != canonical or existing != record:
                    fail("deployment receipt with this transition ID is not the complete canonical pending record; recover manually")
    if matches >= 1:
        return
    append_ledger(path, record)


def read_terminal_receipts(path: Path, inventory_record: dict) -> list[dict]:
    if not path.exists() and not path.is_symlink():
        return []
    if path.is_symlink() or not path.is_file():
        fail("deployment receipts must be a regular file")
    terminal: list[dict] = []
    by_transition: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            fail(f"deployment receipts contain malformed JSON: {exc}")
        if not isinstance(record, dict):
            fail("deployment receipts contain a non-object record")
        if not valid_receipt(record, inventory_record):
            if record.get("schema") == "lmdj.pr-agent-deployment-receipt.v3" and any(
                    key not in record for key in ("from_record_sha256", "from_record_byte_length",
                                                  "to_record_sha256", "to_record_byte_length")):
                fail("deployment receipt lacks canonical record commitments; remedy: perform the reviewed v3 recovery without inferring historical authority")
            fail("deployment receipts contain a legacy, malformed, or forged transition ID; recover manually")
        if line != json.dumps(record, sort_keys=True, separators=(",", ":")):
            fail("deployment receipts contain a noncanonical transition record; recover manually")
        transition_id = record["transition_id"]
        prior = by_transition.get(transition_id)
        if prior is not None:
            if prior != record:
                fail("deployment receipts contain a conflicting transition ID; recover manually")
            # Repeated byte-identical lines are one arrival, not another
            # append-order event.  Preserve the first position.
            continue
        by_transition[transition_id] = record
        terminal.append(record)
    return terminal


def release_path_for_receipt(value: object, install_root: Path) -> Path:
    if not isinstance(value, str):
        fail("deployment receipt endpoint is not a release path; recover manually")
    candidate = Path(value)
    if (not candidate.is_absolute() or ".." in PurePosixPath(value).parts
            or not valid_sha256(candidate.name)
            or candidate != install_root / "releases" / candidate.name):
        fail("deployment receipt endpoint is not the canonical immutable release path; recover manually")
    return candidate


def validate_receipt_release_identity(receipt: dict, endpoint: str, install_root: Path,
                                      retained: dict[str, dict], owner_identity: tuple[int, int] | None,
                                      operator_identity: tuple[int, int] | None,
                                      identity_overrides: dict[str, tuple[int, int]]) -> dict:
    """Authenticate a receipt endpoint from retained or immutable release evidence."""
    path = release_path_for_receipt(endpoint, install_root)
    record = retained.get(endpoint)
    if record is None:
        if not path.is_dir() or path.is_symlink():
            fail("deployment receipt endpoint release is missing or not immutable; recover manually")
        metadata = path / "REVISION_RECORD.json"
        if metadata.is_symlink() or not metadata.is_file():
            fail("deployment receipt endpoint lacks a complete immutable revision record; recover manually")
        metadata_bytes = metadata.read_bytes()
        record = read_json(metadata, "historical immutable revision record")
        if metadata_bytes != canonical_record_bytes(record):
            fail("historical immutable revision record bytes are not canonical; recover manually")
        if not valid_release_record(record, install_root):
            fail("historical immutable revision record is not a closed authenticated release identity; recover manually")
    if record.get("release") != endpoint:
        fail("deployment receipt endpoint record does not bind the canonical release path; recover manually")
    verify_release(path, record, owner_identity, identity_overrides, operator_identity)
    committed_sha, committed_length = record_commitment(record)
    prefix = "from" if endpoint == receipt.get("from_release") else "to"
    if (receipt.get(f"{prefix}_record_sha256"), receipt.get(f"{prefix}_record_byte_length")) != (committed_sha, committed_length):
        fail("deployment receipt endpoint record commitment does not match the immutable record; recover manually")
    if receipt["action"] == "install" and endpoint == receipt["to_release"]:
        if (receipt["archive_sha256"] != record["archive_sha256"]
                or receipt["archive_byte_length"] != record["archive_byte_length"]
                or receipt["deployment_identity_sha256"] != record["deployment_identity_sha256"]):
            fail("deployment receipt archive or detached identity does not match its retained release; recover manually")
    return record


def validate_receipt_history(terminal: list[dict], state: dict, inventory_record: dict,
                             install_root: Path, owner_identity: tuple[int, int] | None = None,
                             operator_identity: tuple[int, int] | None = None,
                             identity_overrides: dict[str, tuple[int, int]] | None = None) -> tuple[dict | None, dict | None]:
    retained: dict[str, dict] = {}
    for record in (state.get("current"), state.get("previous")):
        if isinstance(record, dict) and isinstance(record.get("release"), str):
            prior = retained.get(record["release"])
            if prior is not None and prior != record:
                fail("retained release records conflict for one immutable release; recover manually")
            retained[record["release"]] = record
    transition = state.get("transition")
    if isinstance(transition, dict):
        for key in ("from", "to", "previous"):
            record = transition.get(key)
            if isinstance(record, dict) and isinstance(record.get("release"), str):
                prior = retained.get(record["release"])
                if prior is not None and prior != record:
                    fail("retained release records conflict for one immutable release; recover manually")
                retained[record["release"]] = record
    overrides = identity_overrides or {}
    derived_current: dict | None = None
    derived_previous: dict | None = None
    for index, receipt in enumerate(terminal):
        if not valid_inventory_record(receipt["target"], inventory_record):
            fail("deployment receipt target does not match trusted inventory; recover manually")
        from_release = receipt["from_release"]
        if index == 0:
            if receipt["action"] != "install" or from_release is not None:
                fail("deployment receipt history must begin with an initial install from null; recover manually")
        elif from_release != (derived_current["release"] if derived_current is not None else None):
            fail("deployment receipt history is not a unique first-arrival sequence; recover manually")
        from_record = None
        if from_release is not None:
            from_record = validate_receipt_release_identity(receipt, from_release, install_root, retained,
                                                            owner_identity, operator_identity, overrides)
        to_record = validate_receipt_release_identity(receipt, receipt["to_release"], install_root, retained,
                                                       owner_identity, operator_identity, overrides)
        if receipt["action"] == "install" and from_release == receipt["to_release"]:
            fail("deployment receipt install cannot arrive at the same immutable release; why: a distinct install ID cannot create an A-to-A terminal arrival; remedy: retain the history and recover manually")
        # Install receipts describe the exact inventory used to create their
        # destination. Rollback receipts intentionally describe the invoking
        # (from) inventory; the destination is the prior revision's identity.
        expected_target = (to_record["target_inventory"] if receipt["action"] == "install" else
                           from_record["target_inventory"] if from_record is not None else None)
        if expected_target is None or receipt["target"] != expected_target:
            fail("deployment receipt target is not bound to its immutable transition inventory; recover manually")
        if index == 0:
            if receipt["from_record_sha256"] is not None or receipt["from_record_byte_length"] is not None:
                fail("initial deployment receipt must have a null source commitment; recover manually")
            derived_previous = None
        elif receipt["action"] == "rollback":
            if derived_previous is None or receipt["to_release"] != derived_previous["release"]:
                fail("deployment receipt rollback target is not the replay-derived previous revision; recover manually")
        else:
            if derived_current is None:
                fail("deployment receipt history has no authenticated current arrival; recover manually")
        derived_previous = derived_current
        derived_current = to_record
    return derived_current, derived_previous


def validate_latest_transition_witness(state: dict, receipt_path: Path, inventory_record: dict,
                                       install_root: Path, owner_identity: tuple[int, int] | None = None,
                                       operator_identity: tuple[int, int] | None = None,
                                       identity_overrides: dict[str, tuple[int, int]] | None = None) -> None:
    """Bind state.latest_transition to the last authenticated terminal arrival.

    A receipt can be appended immediately before the state publication during
    an interrupted transition.  In that one window the pending receipt is the
    only permitted terminal record after the state's prior witness.
    """
    terminal = read_terminal_receipts(receipt_path, inventory_record)
    derived_current, derived_previous = validate_receipt_history(
        terminal, state, inventory_record, install_root,
        owner_identity, operator_identity, identity_overrides)
    latest = state.get("latest_transition")
    transition = state.get("transition")
    if transition is None:
        expected = terminal[-1] if terminal else None
        if latest != expected:
            fail("deployment state latest transition witness is not the actual latest durable receipt; recover manually")
        if ((state.get("current") != derived_current)
                or (state.get("previous") != derived_previous)):
            fail("deployment state current and previous do not match replayed terminal history; recover manually")
        return
    pending = transition.get("receipt") if isinstance(transition, dict) else None
    if pending is not None and any(record.get("transition_id") == pending.get("transition_id") and record != pending
                                  for record in terminal):
        fail("deployment receipts contain a conflicting transition ID; recover manually")
    if latest is not None and pending is not None and latest == pending:
        fail("pending transition receipt cannot be its own historical witness; recover manually")
    pending_index = None
    if pending is not None:
        matching = [index for index, record in enumerate(terminal) if record == pending]
        if len(matching) > 1:
            fail("deployment transition has duplicate pending arrivals; recover manually")
        if matching:
            pending_index = matching[0]
            if pending_index != len(terminal) - 1:
                fail("pending transition receipt is not the last unique durable arrival; recover manually")
    base_latest = terminal[-1] if terminal else None
    if pending_index is not None:
        base_latest = terminal[-2] if len(terminal) > 1 else None
    if latest != base_latest:
        fail("deployment state latest transition witness is not the exact final base-history receipt; recover manually")
    base_terminal = list(terminal)
    if pending_index is not None:
        base_terminal.pop()
    base_current, base_previous = validate_receipt_history(
        base_terminal, state, inventory_record, install_root,
        owner_identity, operator_identity, identity_overrides)
    if state.get("current") != base_current or state.get("previous") != base_previous:
        fail("pending transition state does not retain the exact base current and previous history; recover manually")
    prospective_terminal = list(base_terminal)
    if pending is not None:
        prospective_terminal.append(pending)
    prospective_current, prospective_previous = validate_receipt_history(
        prospective_terminal, state, inventory_record, install_root,
        owner_identity, operator_identity, identity_overrides)
    if (prospective_current != transition.get("to")
            or prospective_previous != transition.get("previous")):
        fail("pending transition state is not an authenticated replay boundary; recover manually")


def validate_current_files(state: dict, config: dict, operator_config: Path, runtime_config: Path,
                           service_unit_path: Path, slice_unit_path: Path,
                           operator_identity: tuple[int, int] | None = None,
                           owner_identity: tuple[int, int] | None = None,
                           identity_overrides: dict[str, tuple[int, int]] | None = None) -> None:
    """Authenticate every current managed byte before accepting a new revision."""
    current = state.get("current")
    if not isinstance(current, dict):
        for path, label in ((operator_config, "operator config"), (runtime_config, "operator runtime config")):
            if path.exists() or path.is_symlink():
                fail(f"current {label} exists without an authenticated release state; remedy: recover manually")
        return
    target_inventory = current.get("target_inventory")
    if not isinstance(target_inventory, dict):
        fail("current release lacks a complete deployment inventory; remedy: recover manually")
    for expected_path, expected_sha, expected_length, label, identity, mode in (
            (current.get("operator_config_path"), current.get("operator_config_sha256"),
             current.get("operator_config_byte_length"), "operator config", operator_identity, 0o600),
            (current.get("runtime_config_path"), current.get("runtime_config_sha256"),
             current.get("runtime_config_byte_length"), "operator runtime config",
             (operator_identity[0], owner_identity[1]) if operator_identity and owner_identity else None, 0o440)):
        if not isinstance(expected_path, str):
            fail(f"current {label} lacks an authenticated path; remedy: recover manually")
        authenticated_path = Path(expected_path)
        require_secure_parent_chain(authenticated_path, operator_identity, identity_overrides or {}, label)
        validate_owned_file(authenticated_path, identity, mode, identity_overrides or {}, f"current {label}", required=True)
        if sha256(authenticated_path) != (expected_sha, expected_length):
            fail(f"operator config differs: current {label} identity does not match authenticated state; remedy: recover manually")
    validate_generated_unit(service_unit_path, current.get("service_unit_sha256"), current.get("service_unit_byte_length"), "service unit", operator_identity, identity_overrides)
    validate_generated_unit(slice_unit_path, current.get("slice_unit_sha256"), current.get("slice_unit_byte_length"), "slice unit", operator_identity, identity_overrides)


def validate_recorded_operator_path(record: dict, current_record: dict | None,
                                    operator_identity: tuple[int, int],
                                    identity_overrides: dict[str, tuple[int, int]]) -> None:
    """Authenticate a retained revision's operator path without requiring
    old bytes from a path currently occupied by the far side."""
    path = Path(record["operator_config_path"])
    require_secure_parent_chain(path, operator_identity, identity_overrides, "recorded operator config")
    if not path.exists() and not path.is_symlink():
        return
    validate_owned_file(path, operator_identity, 0o600, identity_overrides, "recorded operator config", required=True)
    if current_record is None or path != Path(current_record["operator_config_path"]):
        if sha256(path) != (record["operator_config_sha256"], record["operator_config_byte_length"]):
            fail("recorded operator config is forged or has the wrong identity; remedy: recover manually")


def validate_recorded_external_files(record: dict, operator_identity: tuple[int, int],
                                     owner_identity: tuple[int, int],
                                     identity_overrides: dict[str, tuple[int, int]]) -> None:
    """Validate the complete far-side external terminal state before effects."""
    inventory_record = record["target_inventory"]
    entries = (
        (Path(record["operator_config_path"]), operator_identity, 0o600,
         record["operator_config_sha256"], record["operator_config_byte_length"], "target operator config"),
        (Path(record["runtime_config_path"]), (operator_identity[0], owner_identity[1]), 0o440,
         record["runtime_config_sha256"], record["runtime_config_byte_length"], "target runtime config"),
        (Path(inventory_record["unit"]), operator_identity, 0o644,
         record["service_unit_sha256"], record["service_unit_byte_length"], "target service unit"),
        (Path(inventory_record["slice_unit"]), operator_identity, 0o644,
         record["slice_unit_sha256"], record["slice_unit_byte_length"], "target slice unit"),
    )
    for path, identity, mode, expected_sha, expected_length, label in entries:
        require_secure_parent_chain(path, operator_identity, identity_overrides, label)
        validate_owned_file(path, identity, mode, identity_overrides, label, required=True)
        if sha256(path) != (expected_sha, expected_length):
            fail(f"{label} does not match its authenticated terminal state; remedy: retain transition and recover manually")


def verify_recorded_releases(state: dict, current: Path, install_root: Path,
                             owner_identity: tuple[int, int] | None,
                             operator_identity: tuple[int, int] | None,
                             identity_overrides: dict[str, tuple[int, int]]) -> None:
    current_record = state.get("current")
    current_target = symlink_target(current)
    if current_record is None:
        if current_target is not None:
            fail("current release pointer exists without an authenticated current state; recover manually")
    else:
        current_path = Path(current_record["release"])
        if not direct_pointer_matches(current, current_path):
            fail("current release pointer does not equal authenticated state; retain target and recover manually")
        verify_release(current_path, current_record, owner_identity, identity_overrides, operator_identity)
    previous = state.get("previous")
    if previous is not None:
        previous_path = Path(previous["release"])
        verify_release(previous_path, previous, owner_identity, identity_overrides, operator_identity)


def acquire_control_lock(operator_state: Path, operator_identity: tuple[int, int],
                         identity_overrides: dict[str, tuple[int, int]]):
    """Serialize complete control transitions under an operator-owned lock."""
    lock_path = operator_state / "control.lock"
    if lock_path.exists() or lock_path.is_symlink():
        validate_owned_file(lock_path, operator_identity, 0o600, identity_overrides, "operator control lock")
    else:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except OSError as exc:
        fail(f"operator control lock cannot be opened without symlink following: {exc}; remedy: retain the target and recover manually")
    handle = os.fdopen(descriptor, "r+")
    if operator_identity != (os.getuid(), os.getgid()) and ROOT == Path("/"):
        os.chown(lock_path, operator_identity[0], operator_identity[1])
    os.fchmod(handle.fileno(), 0o600)
    fsync_directory(lock_path.parent)
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        fail("another deployment control transition is in progress; why: concurrent mutation cannot be authenticated; remedy: wait for the owner-held transition to finish")
    return handle


def reconcile_transition(state_path: Path, state: dict, current: Path, service_unit_path: Path,
                         slice_unit_path: Path, receipt_path: Path, install_root: Path,
                         inventory_record: dict, owner_identity: tuple[int, int] | None,
                         operator_identity: tuple[int, int] | None,
                         identity_overrides: dict[str, tuple[int, int]],
                         operator_config: Path | None = None, runtime_config: Path | None = None) -> dict:
    transition = state.get("transition")
    if not state:
        return state
    validate_state(state, install_root, inventory_record)
    validate_latest_transition_witness(state, receipt_path, inventory_record, install_root,
                                       owner_identity, operator_identity, identity_overrides)
    if not isinstance(transition, dict):
        return state
    # Re-validate even for transitions created in this process: no receipt,
    # state clear, or other reconciliation write may precede this admission.
    target = transition.get("to")
    if not isinstance(target, dict) or not isinstance(target.get("release"), str):
        fail("interrupted deployment transition has no authenticated target; reconcile state manually")
    retained = (state.get("current"), state.get("previous"), transition.get("from"),
                transition.get("to"), transition.get("previous"))
    seen: dict[str, dict] = {}
    for record in retained:
        if not isinstance(record, dict) or not isinstance(record.get("release"), str):
            continue
        if record["release"] not in seen:
            verify_release(Path(record["release"]), record, owner_identity, identity_overrides, operator_identity)
            seen[record["release"]] = record
        elif seen[record["release"]] != record:
            fail("retained release records conflict for one immutable release; recover manually")
        if operator_identity is not None:
            validate_recorded_operator_path(record, state.get("current"), operator_identity, identity_overrides)
    target_path = Path(target["release"])
    if direct_pointer_matches(current, target_path):
        verify_release(target_path, target, owner_identity, identity_overrides, operator_identity)
        if operator_identity is None or owner_identity is None:
            fail("deployment transition lacks authenticated operator and service identities")
        validate_recorded_external_files(target, operator_identity, owner_identity, identity_overrides)
        receipt = transition.get("receipt")
        if not isinstance(receipt, dict):
            fail("interrupted deployment transition lacks a durable receipt")
        prospective = dict(state)
        prospective["current"] = target
        prospective["previous"] = transition.get("previous")
        prospective["inventory"] = target.get("target_inventory", inventory_record)
        prospective["latest_transition"] = receipt
        prospective.pop("transition", None)
        validate_state(prospective, install_root, prospective["inventory"])
        append_receipt_once(receipt_path, receipt)
        state = prospective
        state.pop("transition", None)
        write_state(state_path, state)
        return state
    fail("interrupted deployment transition is durable but incomplete; why: the exact authenticated far side is not present; remedy: recover manually by reconciling unit files and current symlink before retry")


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
    if MODE in {"dry-run", "verify", "stage", "install"}:
        if bundle_path is None or identity_path is None:
            fail(f"{MODE} requires --bundle and --identity")
        if not bundle_path.is_file() or not identity_path.is_file():
            fail("bundle and detached identity must be present regular files")
        runtime_identity = validate_runtime_config(config, runtime_source, MODE == "stage" or (config["active"] and MODE in {"verify", "install"}), MODE == "stage")
        archive_sha, archive_length, extracted, identity = validate_bundle(config, bundle_path, identity_path, MODE in {"stage", "install"})
        if extracted is not None:
            shutil.rmtree(extracted)
        print(json.dumps({"mode": MODE, "active": config["active"], "inventory": inventory(config),
                          "archive": {"sha256": archive_sha, "byte_length": archive_length},
                          "detached_identity": identity_path.name,
                          "activation": "not performed"}, sort_keys=True))
        if MODE in {"dry-run", "verify"}:
            return 0
        if MODE == "stage":
            if config["active"]:
                fail("stage requires an inactive trusted deployment config; why: stage must not authorize activation; remedy: set active=false")
            if runtime_source is None or runtime_identity is None:
                fail("stage requires a separately supplied operator runtime config identity")
            validate_staged_runtime_config(runtime_source, runtime_identity)
        elif not config["active"]:
            fail("trusted deployment config is inactive; no installation was performed")
        if runtime_source is None or runtime_identity is None:
            fail("install requires a separately supplied operator runtime config")
        operator_identity, owner_identity, fixture_overrides = deployment_identities(config)
        if MODE == "stage" and not (config["admission"]["operator_access"] and config["admission"]["runner04_classification"]):
            fail("stage lacks operator-access or runner classification prerequisite; why: pending prerequisites must not be fabricated; remedy: provide explicit true evidence before stage")
        operator_config = path_from_config(paths["operator_config"])
        target_runtime = path_from_config(paths["runtime_config"])
        slot_lock = path_from_config(paths["slot_lock"])
        operator_bytes = config_source.read_bytes()
        identity_sha, identity_length = sha256(identity_path)
        revision = revision_id(config, archive_sha, archive_length, identity_sha, identity_length, runtime_identity, operator_bytes)
        release = install_root / "releases" / revision
        target_inventory = inventory(config)
        service_unit, slice_unit = render_unit(config, release, active=config["active"], target_inventory=target_inventory)
        if slot_lock.exists() or slot_lock.is_symlink():
            if slot_lock.is_symlink() or not slot_lock.is_file():
                fail(f"slot lock must be a regular file: {slot_lock}")
        if release.exists() and not release.is_dir():
            fail(f"release path is not a directory: {release}")
        validate_operator_boundary(config, config_source, runtime_source, operator_identity, owner_identity, fixture_overrides)
        state = read_state(state_path, paths, install_root, inventory(config))
        validate_latest_transition_witness(state, path_from_config(paths["deployment_receipts"]), inventory(config), install_root,
                                           owner_identity, operator_identity, fixture_overrides)
        if (MODE == "install" and isinstance(state.get("current"), dict)
                and "transition" not in state
                and state["current"].get("operator_config_path") != str(operator_config)
                and (operator_config.exists() or operator_config.is_symlink())):
            fail("operator config differs at the new authenticated inventory path; remedy: recover manually")
        # A pristine operator-state root is the minimal durable-intent substrate;
        # it is created only after the state-less/closed-state admission above.
        ensure_directory(path_from_config(paths["operator_state_root"]), 0o700)
        if ROOT == Path("/"):
            os.chown(path_from_config(paths["operator_state_root"]), operator_identity[0], operator_identity[1])
        control_lock = acquire_control_lock(path_from_config(paths["operator_state_root"]), operator_identity, fixture_overrides)
        try:
            state = read_state(state_path, paths, install_root, inventory(config))
            state = reconcile_transition(state_path, state, current, path_from_config(paths["unit"]), path_from_config(paths["slice_unit"]), path_from_config(paths["deployment_receipts"]), install_root, inventory(config), owner_identity, operator_identity, fixture_overrides, operator_config, target_runtime)
        except Exception:
            control_lock.close()
            raise
        release_identity = release_record(release, archive_sha, archive_length, identity_path, identity, runtime_identity, service_unit.encode(), slice_unit.encode(), operator_bytes, target_inventory, config["active"], config["admission"])
        current_target = symlink_target(current)
        verify_recorded_releases(state, current, install_root, owner_identity, operator_identity, fixture_overrides)
        for retained_record in (state.get("current"), state.get("previous")):
            if isinstance(retained_record, dict):
                validate_recorded_operator_path(retained_record, state.get("current"), operator_identity, fixture_overrides)
        validate_current_files(state, config, operator_config, target_runtime, path_from_config(paths["unit"]), path_from_config(paths["slice_unit"]), operator_identity, owner_identity, fixture_overrides)
        validate_state_units(config, state, path_from_config(paths["unit"]), path_from_config(paths["slice_unit"]), operator_identity, fixture_overrides)
        if release.exists():
            verify_release(release, release_identity, owner_identity, fixture_overrides, operator_identity)
        if direct_pointer_matches(current, release) and release.is_dir():
            if state.get("current") == release_identity:
                print(json.dumps({"mode": "install", "status": "idempotent", "release": str(release)}, sort_keys=True))
                return 0
        previous_record = state.get("current") if isinstance(state.get("current"), dict) and not direct_pointer_matches(current, release) else state.get("previous")
        from_commitment = record_commitment(state["current"]) if isinstance(state.get("current"), dict) else (None, None)
        to_commitment = record_commitment(release_identity)
        receipt = {"schema": "lmdj.pr-agent-deployment-receipt.v3", "action": "install",
                   "status": "staged", "transition_id": uuid.uuid4().hex,
                   "from_release": state.get("current", {}).get("release") if isinstance(state.get("current"), dict) else None,
                   "to_release": release_identity["release"],
                   "archive_sha256": archive_sha, "archive_byte_length": archive_length,
                   "deployment_identity_sha256": release_identity["deployment_identity_sha256"],
                   "from_record_sha256": from_commitment[0], "from_record_byte_length": from_commitment[1],
                   "to_record_sha256": to_commitment[0], "to_record_byte_length": to_commitment[1],
                   "target": inventory(config)}
        transition_state = {"schema": "lmdj-pr-agent-runtime-state.v3", "current": state.get("current"),
                            "previous": state.get("previous"), "inventory": inventory(config), "activation": "pending",
                            "latest_transition": state.get("latest_transition")}
        transition_state["transition"] = {"action": "install", "from": state.get("current"), "to": release_identity,
                                            "previous": previous_record, "receipt": receipt}
        write_state(state_path, transition_state)
        release.parent.mkdir(parents=True, exist_ok=True)
        release.parent.chmod(0o755)
        if not release.exists():
            stage = Path(tempfile.mkdtemp(prefix=f".{revision}.", dir=release.parent))
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
                operator_copy = stage / "operator-config.json"
                operator_copy.write_bytes(operator_bytes)
                (stage / "service.unit").write_bytes(service_unit.encode())
                (stage / "slice.unit").write_bytes(slice_unit.encode())
                (stage / "REVISION_RECORD.json").write_text(
                    json.dumps(release_identity, sort_keys=True, indent=2) + "\n", encoding="utf-8")
                (stage / "bundle.tar").chmod(0o444)
                (stage / "DEPLOYMENT_IDENTITY.json").chmod(0o444)
                (stage / "runtime.toml").chmod(0o444)
                (stage / "operator-config.json").chmod(0o444)
                (stage / "service.unit").chmod(0o444)
                (stage / "slice.unit").chmod(0o444)
                (stage / "REVISION_RECORD.json").chmod(0o444)
                chown_tree(stage, owner_identity)
                fsync_tree(stage)
                os.replace(stage, release)
                fsync_directory(release.parent)
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
            fsync_file(slot_lock)
            fsync_directory(slot_lock.parent)
        slot_lock.chmod(0o660)
        if owner_identity is not None:
            os.chown(slot_lock, owner_identity[0], owner_identity[1])
        verify_release(release, release_identity, owner_identity, fixture_overrides, operator_identity)
        prior = state.get("current") if isinstance(state.get("current"), dict) else None
        if prior and prior.get("operator_config_path") != str(operator_config):
            if operator_config.exists() or operator_config.is_symlink():
                fail("operator config differs at the new authenticated inventory path; remedy: recover manually")
            ensure_protected(operator_config, operator_bytes, 0o600, operator_identity)
        else:
            replace_authenticated(operator_config, operator_bytes, 0o600,
                                   prior.get("operator_config_sha256") if prior else None,
                                   prior.get("operator_config_byte_length") if prior else None,
                                   "operator config", operator_identity)
        replace_authenticated(target_runtime, runtime_source.read_bytes(), 0o440,
                               prior.get("runtime_config_sha256") if prior else None,
                               prior.get("runtime_config_byte_length") if prior else None,
                               "operator runtime config", (operator_identity[0], owner_identity[1]))
        ensure_generated_unit(path_from_config(paths["unit"]), service_unit.encode(), prior.get("service_unit_sha256") if prior else None, prior.get("service_unit_byte_length") if prior else None, "service unit", operator_identity, fixture_overrides)
        ensure_generated_unit(path_from_config(paths["slice_unit"]), slice_unit.encode(), prior.get("slice_unit_sha256") if prior else None, prior.get("slice_unit_byte_length") if prior else None, "slice unit", operator_identity, fixture_overrides)
        next_link = current.with_name(f".current-new-{os.getpid()}")
        if next_link.exists() or next_link.is_symlink():
            fail(f"refusing to reuse temporary current link: {next_link}")
        next_link.symlink_to(release)
        os.replace(next_link, current)
        fsync_directory(current.parent)
        state = {"schema": "lmdj-pr-agent-runtime-state.v3", "current": state.get("current"),
                 "previous": state.get("previous"), "inventory": inventory(config), "activation": "pending",
                 "latest_transition": transition_state.get("latest_transition"),
                 "transition": transition_state["transition"]}
        write_state(state_path, state)
        state = reconcile_transition(state_path, state, current, path_from_config(paths["unit"]), path_from_config(paths["slice_unit"]), path_from_config(paths["deployment_receipts"]), install_root, inventory(config), owner_identity, operator_identity, fixture_overrides, operator_config, target_runtime)
        print(json.dumps({"mode": MODE, "status": "staged", "release": str(release),
                          "activation": "pending; systemctl was not invoked"}, sort_keys=True))
        control_lock.close()
        return 0
    if MODE == "rollback":
        operator_identity, owner_identity, fixture_overrides = deployment_identities(config)
        # Rollback has no runtime source, but still refuses root/operator boundary drift before effects.
        validate_operator_boundary(config, config_source, None, operator_identity, owner_identity, fixture_overrides)
        state = read_state(state_path, paths, install_root, inventory(config))
        if not state:
            fail("rollback requires a recorded previous release")
        operator_config = path_from_config(paths["operator_config"])
        target_runtime = path_from_config(paths["runtime_config"])
        control_lock = acquire_control_lock(path_from_config(paths["operator_state_root"]), operator_identity, fixture_overrides)
        state = read_state(state_path, paths, install_root, inventory(config))
        state = reconcile_transition(state_path, state, current, path_from_config(paths["unit"]), path_from_config(paths["slice_unit"]), path_from_config(paths["deployment_receipts"]), install_root, inventory(config), owner_identity, operator_identity, fixture_overrides, operator_config, target_runtime)
        if state.get("schema") != "lmdj-pr-agent-runtime-state.v3":
            fail("rollback requires v3 deployment state with current and previous identities")
        current_record = state.get("current")
        previous = state.get("previous")
        if not isinstance(current_record, dict) or not isinstance(current_record.get("release"), str):
            fail("rollback requires an authenticated current release record")
        if not isinstance(previous, dict) or not isinstance(previous.get("release"), str):
            fail("rollback requires a recorded previous release")
        invocation_inventory = inventory(config)
        if current_record.get("target_inventory") != invocation_inventory:
            latest_invocation = state.get("latest_transition")
            repeat_of_latest_rollback = (isinstance(latest_invocation, dict)
                and latest_invocation.get("action") == "rollback"
                and latest_invocation.get("to_release") == current_record.get("release")
                and latest_invocation.get("target") == invocation_inventory)
            if not repeat_of_latest_rollback:
                fail("rollback invocation inventory does not exactly match the authenticated current release; remedy: use the recorded operator configuration basename and paths")
        current_path = Path(current_record["release"])
        previous_path = Path(previous["release"])
        for candidate, label, record in ((current_path, "current", current_record), (previous_path, "previous", previous)):
            if install_root not in candidate.parents or not candidate.is_dir():
                fail(f"recorded {label} release is outside the trusted install root or missing")
            verify_release(candidate, record, owner_identity, fixture_overrides, operator_identity)
        if not direct_pointer_matches(current, current_path):
            fail("current symlink does not match authenticated current release; reconcile before rollback")
        validate_current_files(state, config, operator_config, target_runtime, path_from_config(paths["unit"]), path_from_config(paths["slice_unit"]), operator_identity, owner_identity, fixture_overrides)
        validate_recorded_operator_path(previous, current_record, operator_identity, fixture_overrides)
        service_unit = (previous_path / "service.unit").read_bytes()
        slice_unit = (previous_path / "slice.unit").read_bytes()
        validate_state_units(config, state, path_from_config(paths["unit"]), path_from_config(paths["slice_unit"]), operator_identity, fixture_overrides)
        previous_operator_config = Path(previous["operator_config_path"])
        current_operator_config = Path(current_record["operator_config_path"])
        if previous_operator_config != current_operator_config:
            require_secure_parent_chain(previous_operator_config, operator_identity, fixture_overrides, "previous operator config")
            if previous_operator_config.exists() or previous_operator_config.is_symlink():
                validate_owned_file(previous_operator_config, operator_identity, 0o600, fixture_overrides, "previous operator config", required=True)
                if sha256(previous_operator_config) != (previous.get("operator_config_sha256"), previous.get("operator_config_byte_length")):
                    fail("previous operator config is forged or has the wrong identity; remedy: recover manually")
        old = symlink_target(current)
        receipt_path = path_from_config(paths["deployment_receipts"])
        terminal_receipts = read_terminal_receipts(receipt_path, inventory(config))
        latest = state.get("latest_transition")
        if latest is not None and sum(record == latest for record in terminal_receipts) != 1:
            fail("latest transition witness is not exactly one durable canonical receipt; recover manually")
        if (direct_pointer_matches(current, current_path) and state.get("current") == current_record
                and isinstance(latest, dict) and latest.get("action") == "rollback"
                and latest.get("from_release") == previous["release"]
                and latest.get("to_release") == current_record["release"]
                and sum(record == latest for record in terminal_receipts) == 1):
                print(json.dumps({"mode": "rollback", "status": "idempotent", "release": str(current_path)}, sort_keys=True))
                return 0
        if direct_pointer_matches(current, previous_path) and state.get("current") == previous:
            print(json.dumps({"mode": "rollback", "status": "idempotent", "release": str(previous_path)}, sort_keys=True))
            return 0
        transition_state = dict(state)
        from_commitment = record_commitment(current_record)
        to_commitment = record_commitment(previous)
        receipt = {"schema": "lmdj.pr-agent-deployment-receipt.v3", "action": "rollback", "status": "staged",
                   "transition_id": uuid.uuid4().hex,
                   "from_release": current_record["release"], "to_release": previous["release"],
                   "from_record_sha256": from_commitment[0], "from_record_byte_length": from_commitment[1],
                   "to_record_sha256": to_commitment[0], "to_record_byte_length": to_commitment[1],
                   "target": inventory(config)}
        transition_state["transition"] = {"action": "rollback", "from": current_record, "to": previous,
                                            "previous": current_record, "receipt": receipt}
        write_state(state_path, transition_state)
        ensure_generated_unit(path_from_config(paths["unit"]), service_unit, current_record.get("service_unit_sha256"), current_record.get("service_unit_byte_length"), "service unit", operator_identity, fixture_overrides)
        ensure_generated_unit(path_from_config(paths["slice_unit"]), slice_unit, current_record.get("slice_unit_sha256"), current_record.get("slice_unit_byte_length"), "slice unit", operator_identity, fixture_overrides)
        if previous_operator_config == current_operator_config:
            replace_authenticated(previous_operator_config, (previous_path / "operator-config.json").read_bytes(), 0o600,
                                  current_record.get("operator_config_sha256"), current_record.get("operator_config_byte_length"),
                                  "operator config", operator_identity)
        else:
            if not current_operator_config.is_file() or current_operator_config.is_symlink() or sha256(current_operator_config) != (current_record.get("operator_config_sha256"), current_record.get("operator_config_byte_length")):
                fail("current operator config identity does not match authenticated state; remedy: recover manually")
            if previous_operator_config.exists() or previous_operator_config.is_symlink():
                validate_owned_file(previous_operator_config, operator_identity, 0o600, fixture_overrides, "previous operator config", required=True)
                if sha256(previous_operator_config) != (previous.get("operator_config_sha256"), previous.get("operator_config_byte_length")):
                    fail("previous operator config is forged or has the wrong identity; remedy: recover manually")
            else:
                ensure_protected(previous_operator_config, (previous_path / "operator-config.json").read_bytes(), 0o600, operator_identity)
            current_operator_config.unlink()
            fsync_directory(current_operator_config.parent)
        replace_authenticated(target_runtime, (previous_path / "runtime.toml").read_bytes(), 0o440,
                              current_record.get("runtime_config_sha256"), current_record.get("runtime_config_byte_length"),
                              "operator runtime config", (operator_identity[0], owner_identity[1]))
        next_link = current.with_name(f".current-new-{os.getpid()}")
        if next_link.exists() or next_link.is_symlink():
            fail(f"refusing to reuse temporary current link: {next_link}")
        next_link.symlink_to(previous_path)
        os.replace(next_link, current)
        fsync_directory(current.parent)
        next_state = {"schema": "lmdj-pr-agent-runtime-state.v3", "current": current_record, "previous": state.get("previous"),
                      "inventory": previous.get("target_inventory", inventory(config)), "activation": "pending",
                      "latest_transition": transition_state.get("latest_transition"), "transition": transition_state["transition"]}
        write_state(state_path, next_state)
        state = reconcile_transition(state_path, next_state, current, path_from_config(paths["unit"]), path_from_config(paths["slice_unit"]), path_from_config(paths["deployment_receipts"]), install_root, inventory(config), owner_identity, operator_identity, fixture_overrides, operator_config, target_runtime)
        print(json.dumps({"mode": "rollback", "status": "staged", "release": str(previous_path),
                          "activation": "pending; systemctl was not invoked"}, sort_keys=True))
        control_lock.close()
        return 0
    fail(f"unsupported mode: {MODE}")


try:
    raise SystemExit(run())
except RuntimeError as exc:
    print(f"deploy-runner: {exc}", file=sys.stderr)
    raise SystemExit(2)
PY
