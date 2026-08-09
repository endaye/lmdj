#!/usr/bin/env python3
"""Protect the full Project I/O fault-matrix browser time budget."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SPEC = REPO_ROOT / "tests/platform/web/project_io/project_io_web_conformance.spec.mjs"


def main() -> int:
    source = SPEC.read_text(encoding="utf-8")
    fault_observation_timeout = re.search(
        r"const FAULT_REACHED_OBSERVATION_TIMEOUT_MS = ([0-9_]+);",
        source,
    )
    assert fault_observation_timeout is not None, (
        "named Project I/O fault observation timeout is missing"
    )
    assert int(fault_observation_timeout.group(1).replace("_", "")) >= 60_000, (
        "Project I/O fault observation timeout must cover slow OPFS progress "
        "on the Linux runner"
    )
    timeout = re.search(
        r"const PROJECT_IO_CONFORMANCE_TIMEOUT_MS = ([0-9_]+);",
        source,
    )
    assert timeout is not None, "named Project I/O conformance timeout is missing"
    assert int(timeout.group(1).replace("_", "")) >= 1_200_000, (
        "Project I/O conformance timeout must cover both full fault matrices "
        "on the slowest trusted Linux runner"
    )
    assert "test.setTimeout(PROJECT_IO_CONFORMANCE_TIMEOUT_MS);" in source
    assert 'page.on("pageerror", onPageError);' in source, (
        "Project I/O conformance must observe runtime failures before navigation"
    )
    assert "await Promise.race([" in source, (
        "Project I/O result waits must race completion against runtime failure"
    )
    assert "result?.error" in source, (
        "Project I/O conformance must fail on a reported native runtime error"
    )
    assert "trackedPage(context)" in source, (
        "Project I/O conformance must observe runtime failures on child pages"
    )
    print("Web Project I/O timeout policy: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
