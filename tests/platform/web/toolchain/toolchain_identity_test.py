#!/usr/bin/env python3

import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[4]
LOCK_PATH = REPO_ROOT / "tools/web-runtime/emscripten.lock.json"
VERIFIER_PATH = REPO_ROOT / "tools/web-runtime/verify_emscripten.py"
PACKAGE_PATH = REPO_ROOT / "tests/platform/web/package.json"
PACKAGE_LOCK_PATH = REPO_ROOT / "tests/platform/web/package-lock.json"
CMAKE_PATH = REPO_ROOT / "tests/platform/web/toolchain/CMakeLists.txt"
PROBE_PATH = REPO_ROOT / "tests/platform/web/toolchain/probe.cpp"
IDENTITY_PATH = REPO_ROOT / "build/web/toolchain/toolchain-identity.json"

REQUIRED_LINKER_FLAGS = [
    "-pthread",
    "-sWASMFS",
    "-sAUDIO_WORKLET",
    "-sWASM_WORKERS",
    "-sPROXY_TO_PTHREAD",
    "-sINITIAL_MEMORY=536870912",
    "-sALLOW_MEMORY_GROWTH=0",
    "-sASYNCIFY=1",
    "-sASYNCIFY_IMPORTS=['lmdj_opfs_acquire_writer','lmdj_opfs_replace_complete','lmdj_opfs_list_names']",
]
EXPECTED_LOCK = {
    "emsdk_tag": "6.0.5",
    "emsdk_revision": "dfb9d1a46c3bb8f52e1e6324be23123b9d73c190",
    "emscripten_releases_revision": "dbd755b5da399329c2576f6e3dfa7f419f5d8409",
    "initial_memory": 536870912,
    "allow_memory_growth": False,
    "node": "22",
    "playwright": "1.62.1",
    "linker_flags": REQUIRED_LINKER_FLAGS,
}


def require_files() -> None:
    required = [
        LOCK_PATH,
        VERIFIER_PATH,
        PACKAGE_PATH,
        PACKAGE_LOCK_PATH,
        CMAKE_PATH,
        PROBE_PATH,
    ]
    missing = [path.relative_to(REPO_ROOT).as_posix() for path in required if not path.is_file()]
    assert not missing, f"missing Task 0 files: {', '.join(missing)}"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_emscripten", VERIFIER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_lock_contract(verifier) -> None:
    parsed = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    assert parsed == EXPECTED_LOCK
    assert verifier.validate_lock(parsed) == EXPECTED_LOCK

    rejected = []

    def must_reject(label: str, value: object) -> None:
        try:
            verifier.validate_lock(value)
        except verifier.VerificationError:
            rejected.append(label)
        else:
            raise AssertionError(f"lock mutation was accepted: {label}")

    for key in EXPECTED_LOCK:
        mutated = copy.deepcopy(EXPECTED_LOCK)
        del mutated[key]
        must_reject(f"missing {key}", mutated)

    for key, value in (
        ("emsdk_tag", "6.0.4"),
        ("emsdk_revision", "0" * 40),
        ("emscripten_releases_revision", "f" * 40),
        ("initial_memory", 536_870_911),
        ("allow_memory_growth", True),
        ("node", "23"),
        ("playwright", "1.62.0"),
    ):
        mutated = copy.deepcopy(EXPECTED_LOCK)
        mutated[key] = value
        must_reject(f"wrong {key}", mutated)

    for flag in REQUIRED_LINKER_FLAGS:
        mutated = copy.deepcopy(EXPECTED_LOCK)
        mutated["linker_flags"].remove(flag)
        must_reject(f"missing flag {flag}", mutated)

    mutated = copy.deepcopy(EXPECTED_LOCK)
    mutated["unexpected"] = True
    must_reject("unexpected key", mutated)
    assert len(rejected) == len(EXPECTED_LOCK) + 7 + len(REQUIRED_LINKER_FLAGS) + 1


def assert_browser_package() -> None:
    package = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))
    assert package == {
        "name": "@lmdj/web-toolchain-conformance",
        "version": "0.0.0",
        "private": True,
        "type": "module",
        "engines": {"node": "22.x"},
        "scripts": {"test": "playwright test"},
        "devDependencies": {"@playwright/test": "1.62.1"},
    }

    package_lock = json.loads(PACKAGE_LOCK_PATH.read_text(encoding="utf-8"))
    assert package_lock["lockfileVersion"] == 3
    root = package_lock["packages"][""]
    assert root["engines"] == {"node": "22.x"}
    assert root["devDependencies"] == {"@playwright/test": "1.62.1"}
    playwright = package_lock["packages"]["node_modules/@playwright/test"]
    assert playwright["version"] == "1.62.1"


def assert_verifier_fails_closed() -> None:
    environment = os.environ.copy()
    environment.pop("EMSDK", None)
    completed = subprocess.run(
        [sys.executable, str(VERIFIER_PATH)],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "emscripten verification error: EMSDK is not set\n"
    if IDENTITY_PATH.is_file():
        serialized = IDENTITY_PATH.read_text(encoding="utf-8")
        parsed = json.loads(serialized)
        assert serialized == json.dumps(
            parsed,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"


def function_body(source: str, name: str) -> str:
    match = re.search(rf"\b{name}\s*\([^)]*\)\s*\{{", source, flags=re.DOTALL)
    assert match is not None, f"missing function body: {name}"
    start = match.end()
    depth = 1
    index = start
    while index < len(source) and depth:
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
        index += 1
    assert depth == 0, f"unterminated function body: {name}"
    return source[start : index - 1]


def assert_audio_callback_is_not_asyncify_reachable() -> None:
    cmake = CMAKE_PATH.read_text(encoding="utf-8")
    source = PROBE_PATH.read_text(encoding="utf-8")
    link_options = cmake.split("target_link_options(", 1)[1].split("\n)", 1)[0]
    for flag in REQUIRED_LINKER_FLAGS:
        assert link_options.count(flag) == 1, (
            f"CMake must apply required linker flag exactly once: {flag}"
        )
    assert "ASYNCIFY_REMOVE" not in cmake
    assert "add_library(probe_audio_callback OBJECT probe.cpp)" in cmake
    assert "LMDJ_PROBE_AUDIO_CALLBACK=1" in cmake
    assert "LMDJ_PROBE_CONTROL=1" in cmake
    assert "#if defined(LMDJ_PROBE_AUDIO_CALLBACK)" in source
    shared_atomics = re.findall(
        r"^extern std::atomic<[^>]+>\s+([a-zA-Z_][a-zA-Z0-9_]*);$",
        source,
        flags=re.MULTILINE,
    )
    assert shared_atomics == ["shared_probe_word"], shared_atomics
    body = function_body(source, "process_probe")
    for bridge in (
        "lmdj_opfs_acquire_writer",
        "lmdj_opfs_replace_complete",
        "lmdj_opfs_list_names",
        "emscripten_sleep",
        "emscripten_wget",
        "emscripten_fetch",
    ):
        assert bridge not in body, f"audio callback reaches Asyncify path: {bridge}"
    assert "samplesPerChannel" in body
    assert "shared_probe_word" in body
    assert "kQuantumMismatchMask" in source
    assert "std::atomic<std::uint32_t>::is_always_lock_free" in source
    assert "compare_exchange_strong" in source
    for retired_word in ("observed_frames", "shared_marker"):
        assert re.search(
            rf"\bstd::atomic<[^>]+>\s+{retired_word}\b",
            source,
        ) is None
    assert "return true;" in body

    object_path = (
        REPO_ROOT
        / "build/web/toolchain/cmake/CMakeFiles/probe_audio_callback.dir/probe.cpp.o"
    )
    link_path = REPO_ROOT / "build/web/toolchain/cmake/CMakeFiles/probe.dir/link.txt"
    if object_path.is_file():
        emsdk = Path(os.environ.get("EMSDK", ""))
        llvm_nm = emsdk / "upstream/bin/llvm-nm"
        assert llvm_nm.is_file(), "EMSDK llvm-nm is required to inspect the callback object"
        completed = subprocess.run(
            [str(llvm_nm), "--undefined-only", str(object_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        undefined = {
            line.split()[-1]
            for line in completed.stdout.splitlines()
            if line.strip()
        }
        assert undefined == {"shared_probe_word"}, undefined
    if link_path.is_file():
        emitted_link = link_path.read_text(encoding="utf-8")
        for flag in REQUIRED_LINKER_FLAGS:
            assert emitted_link.count(flag) == 1, (
                f"emitted link must contain required flag exactly once: {flag}"
            )


def main() -> int:
    try:
        require_files()
        verifier = load_verifier()
        assert_lock_contract(verifier)
        assert_browser_package()
        assert_verifier_fails_closed()
        assert_audio_callback_is_not_asyncify_reachable()
    except (AssertionError, json.JSONDecodeError, OSError) as error:
        print(f"web toolchain identity: FAIL: {error}", file=sys.stderr)
        return 1
    print("web toolchain identity: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
