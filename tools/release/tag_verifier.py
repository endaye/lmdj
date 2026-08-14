#!/usr/bin/env python3
"""Agentless verification entry point for a fetched annotated Product tag."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.release.openpgp import OpenPgpError, OpenPgpVerifier


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tag_verifier.py")
    parser.add_argument("--homedir", required=True, type=Path)
    parser.add_argument("--tag-file", required=True, type=Path)
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--gpg-program", default="gpg")
    options = parser.parse_args(argv)
    try:
        OpenPgpVerifier(gpg_program=options.gpg_program).verify_inline_tag(
            options.homedir, options.tag_file, options.fingerprint,
        )
    except OpenPgpError as error:
        print(f"release tag verification error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
