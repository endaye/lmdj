#!/usr/bin/env python3
"""Write or verify the Sound Set Catalog fixture corpus.

    python3 tools/soundset-fixtures/generate.py            # rewrite in place
    python3 tools/soundset-fixtures/generate.py --check     # verify only

`--check` is what `tools.soundset_fixture_corpus` asserts in CI: every
committed byte must be reproducible from this generator alone.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from soundset_fixtures import (  # noqa: E402
    GENERATED_DIRECTORIES,
    build_corpus,
    sha256_hex,
)


DEFAULT_ROOT = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "soundset"
)


def committed_files(root: Path) -> dict[str, bytes]:
    """Return every generated file under `root`, keyed by relative path."""
    found: dict[str, bytes] = {}
    for directory in GENERATED_DIRECTORIES:
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_dir():
                continue
            found[path.relative_to(root).as_posix()] = path.read_bytes()
    return found


REMEDY = (
    "remedy: never hand-edit the corpus. Change "
    "tools/soundset-fixtures/soundset_fixtures.py, then run "
    "`python3 tools/soundset-fixtures/generate.py` and commit the result."
)


def differences(expected: dict[str, bytes], found: dict[str, bytes]) -> list[str]:
    """Return one why/remedy line per file that is not reproducible."""
    problems: list[str] = []
    for name in sorted(set(expected) - set(found)):
        problems.append(
            f"why: {name} is produced by the generator but is not committed, "
            f"so the corpus on disk is incomplete. {REMEDY}"
        )
    for name in sorted(set(found) - set(expected)):
        problems.append(
            f"why: {name} is committed but no generator case produces it, so "
            f"nothing describes what it is for. {REMEDY} If the case is "
            f"wanted, add it to SET_SPECS or BLOBS and give it a row in "
            f"tests/fixtures/soundset/README.md."
        )
    for name in sorted(set(expected) & set(found)):
        if expected[name] != found[name]:
            problems.append(
                f"why: {name} is not reproducible — committed "
                f"{len(found[name])} bytes sha256 "
                f"{sha256_hex(found[name])}, generated "
                f"{len(expected[name])} bytes sha256 "
                f"{sha256_hex(expected[name])}. A content-addressed object "
                f"whose bytes the generator cannot reproduce has no "
                f"recoverable identity. {REMEDY}"
            )
    return problems


def write(root: Path, expected: dict[str, bytes]) -> None:
    for directory in GENERATED_DIRECTORIES:
        shutil.rmtree(root / directory, ignore_errors=True)
    for name, payload in expected.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed corpus instead of rewriting it",
    )
    arguments = parser.parse_args(argv)

    expected = build_corpus()
    if not arguments.check:
        write(arguments.root, expected)
        print(
            f"wrote {len(expected)} files "
            f"({sum(len(payload) for payload in expected.values())} bytes) "
            f"to {arguments.root}"
        )
        return 0

    problems = differences(expected, committed_files(arguments.root))
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print(f"corpus reproducible: {len(expected)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
