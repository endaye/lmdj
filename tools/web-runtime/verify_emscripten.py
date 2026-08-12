#!/usr/bin/env python3

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = REPO_ROOT / "tools/web-runtime/emscripten.lock.json"
OUTPUT_PATH = REPO_ROOT / "build/web/toolchain/toolchain-identity.json"
LOCK_KEYS = {
    "allow_memory_growth",
    "emcc_version",
    "emscripten_releases_revision",
    "emsdk_revision",
    "emsdk_tag",
    "initial_memory",
    "linker_flags",
    "node",
    "playwright",
}


class VerificationError(RuntimeError):
    pass


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_lock(value: object) -> dict:
    if not isinstance(value, dict):
        raise VerificationError("lock root must be an object")
    actual_keys = set(value)
    expected_keys = LOCK_KEYS
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        unexpected = sorted(actual_keys - expected_keys)
        raise VerificationError(
            f"lock keys mismatch: missing={missing}, unexpected={unexpected}"
        )
    for key in (
        "emcc_version",
        "emscripten_releases_revision",
        "emsdk_revision",
        "emsdk_tag",
        "node",
        "playwright",
    ):
        if not isinstance(value[key], str) or not value[key]:
            raise VerificationError(f"lock value is invalid for {key}")
    if type(value["initial_memory"]) is not int or value["initial_memory"] < 1:
        raise VerificationError("lock initial_memory is invalid")
    if type(value["allow_memory_growth"]) is not bool:
        raise VerificationError("lock allow_memory_growth is invalid")
    if not isinstance(value["linker_flags"], list) or not value["linker_flags"] or not all(
        isinstance(flag, str) and flag for flag in value["linker_flags"]
    ):
        raise VerificationError("lock linker_flags are invalid")
    return dict(value)


def run_checked(command: list[str], label: str) -> str:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise VerificationError(f"{label} failed: {detail}")
    return completed.stdout.strip()


def require_below(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    expected_root = root.resolve(strict=True)
    try:
        resolved.relative_to(expected_root)
    except ValueError as error:
        raise VerificationError(
            f"{label} must resolve below {expected_root}, got {resolved}"
        ) from error
    return resolved


def verify_active_sdk(lock: dict) -> dict:
    emsdk_value = os.environ.get("EMSDK", "")
    if not emsdk_value:
        raise VerificationError("EMSDK is not set")
    emsdk = Path(emsdk_value).expanduser().resolve(strict=True)
    if not emsdk.is_dir():
        raise VerificationError(f"EMSDK is not a directory: {emsdk}")

    head = run_checked(
        ["git", "-C", str(emsdk), "rev-parse", "HEAD"],
        "emsdk Git identity",
    )
    if head != lock["emsdk_revision"]:
        raise VerificationError(
            f"emsdk revision mismatch: expected {lock['emsdk_revision']}, got {head}"
        )

    releases_path = emsdk / "emscripten-releases-tags.json"
    try:
        releases = json.loads(releases_path.read_text(encoding="utf-8"))
        release_revision = releases["releases"][lock["emsdk_tag"]]
    except (OSError, KeyError, json.JSONDecodeError, TypeError) as error:
        raise VerificationError(
            f"invalid emscripten release mapping: {releases_path}"
        ) from error
    if release_revision != lock["emscripten_releases_revision"]:
        raise VerificationError(
            "emscripten-releases revision mismatch: "
            f"expected {lock['emscripten_releases_revision']}, got {release_revision}"
        )

    emcc_command = shutil.which("emcc")
    if emcc_command is None:
        raise VerificationError("emcc is not on PATH")
    emcc = require_below(
        Path(emcc_command),
        emsdk / "upstream/emscripten",
        "active emcc",
    )
    version_output = run_checked([str(emcc), "--version"], "emcc version")
    version_line = version_output.splitlines()[0] if version_output else ""
    if version_line != lock["emcc_version"]:
        raise VerificationError(
            "emcc version mismatch: "
            f"expected {lock['emcc_version']!r}, got {version_line!r}"
        )

    return dict(lock)


def main() -> int:
    try:
        parsed = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        lock = validate_lock(parsed)
        identity = verify_active_sdk(lock)
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(
            canonical_json(identity) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except (
        OSError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
        VerificationError,
    ) as error:
        print(f"emscripten verification error: {error}", file=sys.stderr)
        return 2
    print(f"emscripten identity: PASS ({OUTPUT_PATH.relative_to(REPO_ROOT)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
