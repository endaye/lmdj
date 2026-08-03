#!/usr/bin/env python3

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = REPO_ROOT / "tools/web-runtime/emscripten.lock.json"
OUTPUT_PATH = REPO_ROOT / "build/web/toolchain/toolchain-identity.json"
EXPECTED_LOCK = {
    "emsdk_tag": "6.0.5",
    "emsdk_revision": "dfb9d1a46c3bb8f52e1e6324be23123b9d73c190",
    "emscripten_releases_revision": "dbd755b5da399329c2576f6e3dfa7f419f5d8409",
    "initial_memory": 536_870_912,
    "allow_memory_growth": False,
    "node": "22",
    "playwright": "1.62.1",
    "linker_flags": [
        "-pthread",
        "-sWASMFS",
        "-sAUDIO_WORKLET",
        "-sWASM_WORKERS",
        "-sPROXY_TO_PTHREAD",
        "-sINITIAL_MEMORY=536870912",
        "-sALLOW_MEMORY_GROWTH=0",
        "-sASYNCIFY=1",
        "-sASYNCIFY_IMPORTS=['lmdj_opfs_acquire_writer','lmdj_opfs_replace_complete','lmdj_opfs_list_names']",
    ],
}


class VerificationError(RuntimeError):
    pass


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_lock(value: object) -> dict:
    if not isinstance(value, dict):
        raise VerificationError("lock root must be an object")
    actual_keys = set(value)
    expected_keys = set(EXPECTED_LOCK)
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        unexpected = sorted(actual_keys - expected_keys)
        raise VerificationError(
            f"lock keys mismatch: missing={missing}, unexpected={unexpected}"
        )
    for key, expected in EXPECTED_LOCK.items():
        actual = value[key]
        if type(actual) is not type(expected) or actual != expected:
            raise VerificationError(
                f"lock value mismatch for {key}: expected {expected!r}, got {actual!r}"
            )
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
    if re.search(r"(?<![0-9.])6\.0\.5(?![0-9.])", version_line) is None:
        raise VerificationError(
            f"emcc version mismatch: expected 6.0.5, got {version_line!r}"
        )

    return {
        **lock,
        "emcc_version": version_line,
    }


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
