#!/usr/bin/env python3

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from headless_core_proof import validate_mutation_paths


build_root = (REPO_ROOT / "build/core").resolve()
validate_mutation_paths(
    build_root / "release/proof-ctest/run",
    build_root / "release/proof-ctest/beat.wav",
)
validate_mutation_paths(
    build_root / "proof-runs/unique/e2e",
    build_root / "proof-runs/unique/artifacts/beat.wav",
)

for run_root, output_wav in (
    (Path("/"), build_root / "release/proof-ctest/beat.wav"),
    (Path.home(), build_root / "release/proof-ctest/beat.wav"),
    (REPO_ROOT, build_root / "release/proof-ctest/beat.wav"),
    (build_root, build_root / "release/proof-ctest/beat.wav"),
    (
        build_root / "release/not-a-proof-run",
        build_root / "release/proof-ctest/beat.wav",
    ),
    (
        build_root / "release/proof-ctest/run",
        Path.home() / "beat.wav",
    ),
):
    try:
        validate_mutation_paths(run_root, output_wav)
    except ValueError:
        pass
    else:
        raise AssertionError((run_root, output_wav))

print("proof path safety: PASS")
