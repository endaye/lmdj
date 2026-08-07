#!/usr/bin/env python3
"""Validate that every configured Core CTest registration has one test tier."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


TIERS = {"unit", "component", "contract", "host", "e2e", "stress"}
MAX_TIMEOUT = {
    "unit": 10.0,
    "component": 30.0,
    "contract": 30.0,
    "host": 120.0,
    "e2e": 180.0,
    "stress": 300.0,
}


def properties_by_name(test: dict[str, object]) -> dict[str, object]:
    return {
        property_["name"]: property_["value"]
        for property_ in test.get("properties", [])
    }


def validate(build_dir: Path) -> tuple[list[str], int]:
    cache = (build_dir / "CMakeCache.txt").read_text(encoding="utf-8")
    is_asan = "LMDJ_SANITIZER:STRING=address" in cache.splitlines()
    is_tsan = "LMDJ_SANITIZER:STRING=thread" in cache.splitlines()
    sanitizer_name = "ASan" if is_asan else "TSan" if is_tsan else None
    sanitizer_timeout_factor = 3.0 if is_asan else 4.0 if is_tsan else 1.0
    result = subprocess.run(
        ["ctest", "--test-dir", str(build_dir), "--show-only=json-v1"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return [f"ctest registration query failed:\n{result.stderr.strip()}"], 0

    test_info = json.loads(result.stdout)
    tests = test_info.get("tests", [])
    errors: list[str] = []
    names: set[str] = set()
    resolved_build_dir = build_dir.resolve()

    if not tests:
        errors.append("no registered tests")

    for test in tests:
        name = test["name"]
        if name in names:
            errors.append(f"duplicate test name: {name}")
        names.add(name)

        properties = properties_by_name(test)
        labels = properties.get("LABELS", [])
        if isinstance(labels, str):
            labels = [labels]
        tiers = TIERS.intersection(labels)
        if len(tiers) != 1:
            errors.append(
                f"{name}: expected exactly one tier label, found {sorted(tiers)}"
            )
            continue

        command = test.get("command", [])
        executable = Path(command[0]) if command else None
        is_native = bool(
            executable
            and executable.is_absolute()
            and executable.resolve().is_relative_to(resolved_build_dir)
        )
        if is_native != ("native" in labels):
            errors.append(
                f"{name}: native label does not match executable ownership"
            )

        tier = next(iter(tiers))
        timeout = properties.get("TIMEOUT")
        if timeout is None:
            errors.append(f"{name}: missing timeout")
            continue
        timeout_limit = MAX_TIMEOUT[tier] * sanitizer_timeout_factor
        if sanitizer_name and is_native and tier != "stress":
            expected_timeout = MAX_TIMEOUT[tier] * sanitizer_timeout_factor
            if float(timeout) != expected_timeout:
                errors.append(
                    f"{name}: {sanitizer_name} timeout {timeout} must be "
                    f"{expected_timeout}"
                )
        if float(timeout) > timeout_limit:
            errors.append(
                f"{name}: timeout {timeout} exceeds {tier} limit "
                f"{timeout_limit}"
            )

    return errors, len(tests)


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} <configured-build-dir>", file=sys.stderr)
        return 2

    errors, count = validate(Path(sys.argv[1]))
    if errors:
        print("Core test taxonomy: FAIL", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(f"Core test taxonomy: PASS ({count} registered tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
