#!/usr/bin/env python3
"""Generate the exact long-material fixtures used by #346 and physical #359."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


FRAMES = 43_200_000
BANK_FRAMES = 16_777_216
SOURCE_REJECT_BYTES = 104_857_601


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ffmpeg(output: Path, *arguments: str) -> None:
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        *arguments, "-map_metadata", "-1", str(output),
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing non-empty output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required")

    song = output / "LM-OK-SONG.mp3"
    ffmpeg(
        song,
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "210", "-c:a", "libmp3lame", "-b:a", "192k",
        "-write_xing", "1",
    )

    boundary = output / "LM-OK-BOUNDARY-INGEST.flac"
    ffmpeg(
        boundary,
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-af", f"atrim=end_sample={FRAMES}",
        "-c:a", "flac", "-compression_level", "5",
    )
    reject_frames = output / "LM-REJ-FRAMES.flac"
    ffmpeg(
        reject_frames,
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-af", f"atrim=end_sample={FRAMES + 1}",
        "-c:a", "flac", "-compression_level", "5",
    )

    reject_source = output / "LM-REJ-SOURCE.mp3"
    ffmpeg(
        reject_source,
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-t", "1", "-c:a", "libmp3lame", "-b:a", "192k",
    )
    with reject_source.open("ab") as destination:
        destination.truncate(SOURCE_REJECT_BYTES)

    reject_channels = output / "LM-REJ-CH.m4a"
    ffmpeg(
        reject_channels,
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=5.1",
        "-t", "1", "-c:a", "aac", "-b:a", "384k", "-movflags", "+faststart",
    )

    commit_boundary = output / "LM-OK-COMMIT-BOUNDARY.wav"
    ffmpeg(
        commit_boundary,
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
        "-af", f"atrim=end_sample={BANK_FRAMES}", "-c:a", "pcm_s16le",
    )
    commit_plus = output / "LM-REJ-COMMIT-PLUS-4B.wav"
    ffmpeg(
        commit_plus,
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
        "-af", f"atrim=end_sample={BANK_FRAMES + 1}", "-c:a", "pcm_s16le",
    )

    dimensions = {
        song.name: {"sample_rate": 44_100, "channels": 2, "decoded_frames_48k": 10_080_000},
        boundary.name: {"sample_rate": 48_000, "channels": 2, "decoded_frames_48k": FRAMES},
        reject_frames.name: {"sample_rate": 48_000, "channels": 2, "decoded_frames_48k": FRAMES + 1},
        reject_source.name: {"sample_rate": 48_000, "channels": 2, "source_bytes": SOURCE_REJECT_BYTES},
        reject_channels.name: {"sample_rate": 48_000, "channels": 6, "decoded_frames_48k": 48_000},
        commit_boundary.name: {"sample_rate": 48_000, "channels": 1, "decoded_frames_48k": BANK_FRAMES},
        commit_plus.name: {"sample_rate": 48_000, "channels": 1, "decoded_frames_48k": BANK_FRAMES + 1},
    }
    fixtures = []
    for path in sorted(output.iterdir()):
        fixtures.append({
            "name": path.stem,
            "file": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            **dimensions[path.name],
        })
    version = subprocess.run(
        ["ffmpeg", "-version"], check=True, text=True, capture_output=True,
    ).stdout.splitlines()[0]
    manifest = {
        "contract": "lmdj.long-material-fixtures.v1",
        "generator": "tests/fixtures/long-material/make_fixtures.py",
        "ffmpeg": version,
        "fixtures": fixtures,
        "lifecycle_sequences": [
            "cancel", "replace", "re-import", "background-recovery",
        ],
    }
    rendered = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.manifest is not None:
        args.manifest.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
