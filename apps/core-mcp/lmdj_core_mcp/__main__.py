"""Command-line entry point for the LMDJ MCP stdio Host."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from .c_api import CApiError, Engine
from .server import serve


def lexical_absolute(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or os.path.normpath(value) != value:
        raise argparse.ArgumentTypeError(
            "path must be absolute and lexically normalized"
        )
    return path


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="lmdj-core-mcp")
    parser.add_argument("--library", required=True, type=lexical_absolute)
    parser.add_argument("--workspace", required=True, type=lexical_absolute)
    return parser.parse_args()


def main() -> int:
    options = arguments()
    try:
        engine = Engine(options.library, options.workspace)
    except CApiError:
        print("lmdj-core-mcp: startup failed", file=sys.stderr)
        return 2
    try:
        return serve(engine, sys.stdin.buffer.fileno(), sys.stdout.buffer)
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
