#!/usr/bin/env python3

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PLATFORM_ROOT = REPO_ROOT / "packages/web-runtime-platform"
FORBIDDEN_APP_FILES = {
    "control_runtime.cpp",
    "control_runtime.hpp",
    "bridge.cpp",
    "manifest_gate.cpp",
    "manifest_gate.hpp",
    "web-runtime-pre.js",
}
TEXT_SUFFIXES = {".c", ".cc", ".cpp", ".h", ".hpp", ".js", ".mjs", ".py", ".tsx"}


def fail(message: str) -> None:
    raise AssertionError(message)


def text_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            yield path


def main() -> int:
    app_owned = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "apps").rglob("*")
        if path.is_file() and path.name in FORBIDDEN_APP_FILES
    )
    if app_owned:
        fail("shared Web Runtime sources remain app-owned: " + ", ".join(app_owned))

    for path in PLATFORM_ROOT.rglob("*"):
        if path.is_file() and path.suffix in {".css", ".scss", ".sass", ".less"}:
            fail(f"Platform package owns product presentation: {path}")

    forbidden_native_patterns = {
        r"(?:from|require\s*\()\s*['\"]react": "React dependency",
        r"\b(?:document|HTMLElement|CSSStyleSheet)\b": "DOM or CSS ownership",
        r"lmdj\.web-runtime-host\.distribution": "diagnostic distribution identity",
        r"\b(?:diagnostic-project|creator-web)\b": "product Host identity",
    }
    for production_root in (PLATFORM_ROOT / "include", PLATFORM_ROOT / "src"):
        for path in text_files(production_root):
            source = path.read_text(encoding="utf-8")
            for pattern, label in forbidden_native_patterns.items():
                if re.search(pattern, source, re.IGNORECASE):
                    fail(f"{label} entered Platform package: {path}")

    forbidden_web_patterns = {
        r"(?:from|require\s*\()\s*['\"]react": "React dependency",
        r"\b(?:getElementById|querySelectorAll|CSSStyleSheet)\b": (
            "product DOM presentation"
        ),
        r"\b(?:classList|innerHTML)\b": "product DOM mutation",
        r"lmdj\.web-runtime-host\.distribution": "diagnostic distribution identity",
        r"\b(?:diagnostic-project|creator-web)\b": "product Host identity",
    }
    for path in text_files(PLATFORM_ROOT / "web"):
        source = path.read_text(encoding="utf-8")
        for pattern, label in forbidden_web_patterns.items():
            if re.search(pattern, source, re.IGNORECASE):
                fail(f"{label} entered Platform web module: {path}")

    creator_root = REPO_ROOT / "apps" / "creator-web"
    if creator_root.exists():
        for path in text_files(creator_root):
            source = path.read_text(encoding="utf-8")
            if re.search(r"diagnostic[_-]client\.mjs", source, re.IGNORECASE):
                fail(f"Creator imports diagnostic-only client: {path}")

    direct_project_io = re.compile(
        r"(?:lmdj/project_io/|\blmdj::project_io\b|\blmdj_project_io\b|"
        r"\b(?:ProjectStore|TakeJournal|ProjectStoragePlatform)\b)"
    )
    for host in ("web-runtime-host", "creator-web"):
        root = REPO_ROOT / "apps" / host
        if not root.exists():
            continue
        for production_root in (root / "include", root / "src"):
            if not production_root.exists():
                continue
            for path in text_files(production_root):
                if direct_project_io.search(path.read_text(encoding="utf-8")):
                    fail(f"Host bypasses Application Facade for Project I/O: {path}")
        cmake = root / "CMakeLists.txt"
        if cmake.is_file() and direct_project_io.search(cmake.read_text(encoding="utf-8")):
            fail(f"Host links Project I/O directly: {cmake}")

    print("web runtime platform source boundary: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"web runtime platform source boundary: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
