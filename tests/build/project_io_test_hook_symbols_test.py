#!/usr/bin/env python3

import pathlib
import subprocess
import sys


FORBIDDEN_SYMBOLS = (
    "FaultPoint",
    "set_fault_hook",
    "set_active_directory_sync_hook",
)


def validate_symbols(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if any(symbol in line for symbol in FORBIDDEN_SYMBOLS)
    ]


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            "usage: project_io_test_hook_symbols_test.py "
            "<nm-executable> <production-library>",
            file=sys.stderr,
        )
        return 2

    nm_executable = pathlib.Path(argv[1])
    production_library = pathlib.Path(argv[2])
    completed = subprocess.run(
        [str(nm_executable), "-g", str(production_library)],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        print(completed.stderr, file=sys.stderr, end="")
        return completed.returncode

    findings = validate_symbols(completed.stdout)
    if findings:
        print(
            "production Project I/O library exposes test-only symbols:",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1

    print("project io production test-hook symbols: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
