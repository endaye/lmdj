#!/usr/bin/env python3

import pathlib
import subprocess
import sys


FORBIDDEN_SYMBOLS = (
    "FaultPoint",
    "set_fault_hook",
    "set_active_directory_sync_hook",
    "set_pattern_claim_hook",
    "invoke_pattern_claim_hook",
    "set_pattern_apply_hook",
    "invoke_pattern_apply_hook",
    "fail_next_pattern_publication",
)

FORBIDDEN_BYTES = (
    b"__testing.fail-next-pattern-publication",
    b"injected runtime Pattern publication failure",
    b"set_pattern_claim_hook",
    b"invoke_pattern_claim_hook",
    b"set_pattern_apply_hook",
    b"invoke_pattern_apply_hook",
)


def validate_symbols(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if any(symbol in line for symbol in FORBIDDEN_SYMBOLS)
    ]


def validate_binary(content: bytes) -> list[str]:
    return [
        marker.decode("ascii")
        for marker in FORBIDDEN_BYTES
        if marker in content
    ]


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(
            "usage: project_io_test_hook_symbols_test.py "
            "<nm-executable> <production-library> [production-library ...]",
            file=sys.stderr,
        )
        return 2

    nm_executable = pathlib.Path(argv[1])
    found = False
    for library_arg in argv[2:]:
        production_library = pathlib.Path(library_arg)
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
        binary_findings = validate_binary(production_library.read_bytes())
        if findings or binary_findings:
            found = True
            print(
                f"production library exposes test-only symbols: "
                f"{production_library}",
                file=sys.stderr,
            )
            for finding in findings:
                print(f"  {finding}", file=sys.stderr)
            for finding in binary_findings:
                print(f"  embedded test marker: {finding}", file=sys.stderr)
    if found:
        return 1

    print("production test-hook symbols: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
