from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import PipelineConfig
from .runner import run_from_stems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        "pipeline-from-stems",
        description="legacy stems (drums/bass/melody) -> pipeline 阶段 3-6 -> 包目录")
    parser.add_argument("--stems", type=Path, required=True,
                        help="含 drums.wav/bass.wav/melody.wav 的目录")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--song-id", required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = run_from_stems(args.stems, args.out, args.song_id, PipelineConfig())
    return 0 if report.get("status") in ("passed", "rejected") else 1


if __name__ == "__main__":
    sys.exit(main())
