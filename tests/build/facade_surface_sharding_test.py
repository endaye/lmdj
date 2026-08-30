#!/usr/bin/env python3
"""Require the slow Facade surfaces to stay partitioned into CTest shards."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


EXPECTED = {
    "lmdj_facade_sequence_surface_tests": {
        "facade.sequence_surface": "lifecycle",
        "facade.sequence_surface.recovery": "recovery",
        "facade.sequence_surface.rebase": "rebase",
    },
    "lmdj_facade_sample_surface_tests": {
        "facade.sample_surface": "mutation",
        "facade.sample_surface.quota_replay": "quota-replay",
        "facade.sample_surface.projection": "projection",
    },
    "lmdj_application_c_api_stress_tests": {
        "facade.c_api_stress": "independent-engines",
        "facade.c_api_stress.query_free_race": "query-free-race",
        "facade.c_api_stress.stale_handles": "stale-handles",
        "facade.c_api_stress.lifetime_isolation": "lifetime-isolation",
    },
}


def registered_tests(build_dir: Path) -> dict[str, list[str]]:
    completed = subprocess.run(
        ["ctest", "--test-dir", str(build_dir), "--show-only=json-v1"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"ctest discovery exited {completed.returncode}: {detail}"
        )
    return {
        test["name"]: test["command"]
        for test in json.loads(completed.stdout).get("tests", [])
    }


def declared_shards(executable: Path) -> dict[str, int]:
    completed = subprocess.run(
        [str(executable), "--list-shards"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"--list-shards exited {completed.returncode}: {detail}"
        )
    result: dict[str, int] = {}
    for line in completed.stdout.splitlines():
        name, count = line.split()
        result[name] = int(count)
    return result


def validate_registrations(
    executable: Path,
    expected: dict[str, str],
    registrations: dict[str, list[str]],
) -> list[str]:
    errors: list[str] = []
    owned = {
        name: command
        for name, command in registrations.items()
        if command and Path(command[0]).resolve() == executable.resolve()
    }
    unexpected = sorted(set(owned) - set(expected))
    if unexpected:
        errors.append(
            f"{executable.name}: unexpected CTest registrations {unexpected}"
        )
    for test_name, shard in expected.items():
        command = owned.get(test_name)
        wanted = [str(executable.resolve()), f"--shard={shard}"]
        if command != wanted:
            errors.append(
                f"{test_name}: expected command {wanted}, found {command}"
            )
    return errors


def validate(build_dir: Path) -> list[str]:
    try:
        registrations = registered_tests(build_dir)
    except (OSError, RuntimeError, json.JSONDecodeError, KeyError, TypeError) as error:
        return [f"CTest registration discovery failed: {error}"]
    errors: list[str] = []
    for binary, expected in EXPECTED.items():
        executable = (build_dir / "bin" / binary).resolve()
        try:
            declared = declared_shards(executable)
        except (OSError, RuntimeError, ValueError) as error:
            errors.append(f"{binary}: --list-shards failed: {error}")
            continue

        total = declared.pop("all", None)
        if set(declared) != set(expected.values()):
            errors.append(
                f"{binary}: declared shards {sorted(declared)} do not match "
                f"{sorted(expected.values())}"
            )
        if any(count <= 0 for count in declared.values()):
            errors.append(f"{binary}: every shard must own at least one scenario")
        if total != sum(declared.values()):
            errors.append(
                f"{binary}: bare full-suite count {total} does not equal shard "
                f"total {sum(declared.values())}"
            )

        errors.extend(validate_registrations(executable, expected, registrations))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} <configured-build-dir>", file=sys.stderr)
        return 2
    errors = validate(Path(sys.argv[1]))
    if errors:
        print("Facade surface sharding: FAIL", file=sys.stderr)
        print(
            "why: every registered Facade surface shard must cover one "
            "declared, non-empty subset whose counts reconstruct the bare "
            "full suite",
            file=sys.stderr,
        )
        print("\n".join(errors), file=sys.stderr)
        print(
            "remedy: update the binary --list-shards table and the matching "
            "lmdj_add_test --shard registrations together",
            file=sys.stderr,
        )
        return 1
    print("Facade surface sharding: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
