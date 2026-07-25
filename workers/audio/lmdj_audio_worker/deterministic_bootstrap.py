"""Seed a demo-vendored interpreter before running its console entrypoint."""
from __future__ import annotations

import random
import runpy
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) < 2:
        raise SystemExit("usage: deterministic_bootstrap.py SEED ENTRYPOINT [ARGS...]")
    seed, entrypoint, *entrypoint_args = arguments
    random.seed(int(seed))
    sys.argv = [entrypoint, *entrypoint_args]
    runpy.run_path(str(Path(entrypoint)), run_name="__main__")


if __name__ == "__main__":
    main()
