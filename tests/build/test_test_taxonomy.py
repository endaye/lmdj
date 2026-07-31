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

        tier = next(iter(tiers))
        timeout = properties.get("TIMEOUT")
        if timeout is None:
            errors.append(f"{name}: missing timeout")
            continue
        if float(timeout) > MAX_TIMEOUT[tier]:
            errors.append(
                f"{name}: timeout {timeout} exceeds {tier} limit "
                f"{MAX_TIMEOUT[tier]}"
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
