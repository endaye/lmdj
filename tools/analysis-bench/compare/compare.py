"""Ground-truth comparison for the analysis-bench prototype.

Runs the lmdj_analysis_bench CLI on every fixture x capability, computes
reference values with numpy/scipy using the identical algorithms documented
in docs/superpowers/plans/2026-08-15-lmdj-audio-analysis-bench-prototype.md,
and emits a Markdown comparison table.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import wavfile

ONSET_TOLERANCE_SECONDS = 0.03
CLICK_TRAIN_TIMES = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5)
# Explicit fixture list: the fixtures directory also holds WAV files owned by
# other suites (e.g. web-runtime-host-short.wav), which this comparison must
# not pick up.
FIXTURE_NAMES = ("kick.wav", "snare.wav", "stereo.wav")


def read_mono(path: Path) -> tuple[int, np.ndarray]:
    sample_rate, data = wavfile.read(path)
    assert data.dtype == np.int16, f"{path} must be PCM16"
    mono = data.astype(np.float64) / 32768.0
    if mono.ndim == 2:
        mono = mono.mean(axis=1)
    return sample_rate, mono


def reference_peaks(mono: np.ndarray, samples_per_bucket: int = 256):
    bucket_count = (mono.size + samples_per_bucket - 1) // samples_per_bucket
    padded = np.zeros(bucket_count * samples_per_bucket)
    padded[: mono.size] = mono
    buckets = padded.reshape(bucket_count, samples_per_bucket)
    if mono.size % samples_per_bucket:
        # Ignore padding in the final partial bucket.
        buckets[-1, mono.size % samples_per_bucket :] = buckets[
            -1, mono.size % samples_per_bucket - 1
        ]
    scale = lambda v: np.clip(np.rint(v * 32767.0), -32767, 32767).astype(int)
    return scale(buckets.min(axis=1)), scale(buckets.max(axis=1))


def reference_loudness(mono: np.ndarray):
    if mono.size == 0:
        return -300.0, -300.0
    peak = float(np.abs(mono).max())
    rms = float(np.sqrt(np.mean(mono * mono)))
    to_dbfs = lambda a: -300.0 if a <= 0.0 else 20.0 * np.log10(a)
    return to_dbfs(peak), to_dbfs(rms)


def reference_onsets(
    mono: np.ndarray,
    sample_rate: int,
    fft_size: int = 1024,
    hop_size: int = 512,
):
    if mono.size < fft_size:
        return []
    window = np.hanning(fft_size)
    frames = [
        mono[start : start + fft_size] * window
        for start in range(0, mono.size - fft_size + 1, hop_size)
    ]
    magnitudes = np.abs(np.fft.rfft(np.array(frames), axis=1))
    flux = np.maximum(0.0, np.diff(magnitudes, axis=0, prepend=0)).sum(axis=1)
    threshold = flux.mean() + 1.5 * flux.std()
    times = np.arange(flux.size) * hop_size / sample_rate
    onsets = []
    for i in range(1, flux.size - 1):
        if (
            flux[i] > threshold
            and flux[i] > flux[i - 1]
            and flux[i] >= flux[i + 1]
        ):
            if onsets and times[i] - onsets[-1] < 0.05:
                continue
            onsets.append(float(times[i]))
    return onsets


def match_onsets(expected, actual, tolerance=ONSET_TOLERANCE_SECONDS):
    matched = sum(
        any(abs(found - want) <= tolerance for found in actual)
        for want in expected
    )
    return matched


def make_click_train(path: Path, sample_rate: int = 48000) -> None:
    samples = np.zeros(sample_rate * 2, dtype=np.int16)
    for at in CLICK_TRAIN_TIMES:
        start = int(at * sample_rate)
        burst = np.where(
            np.arange(64) % 2 == 0, 24000, -24000
        ).astype(np.int16)
        samples[start : start + 64] = burst
    wavfile.write(path, sample_rate, samples)


def run_bench(bench, workspace, fixture, capability, parameters=None):
    command = [
        str(bench),
        "--workspace", str(workspace),
        "--fixture", str(fixture),
        "--capability", capability,
        "--iterations", "5",
    ]
    if parameters:
        command += ["--parameters", json.dumps(parameters)]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"bench failed for {fixture}: {completed.stderr}")
    report = json.loads(completed.stdout)
    assert len(report["runs"]) == 1
    return report["runs"][0]


def compare_fixture(bench, workspace_root, fixture, rows, failures):
    sample_rate, mono = read_mono(fixture)
    is_click_train = fixture.name == "click_train.wav"
    # Reference clipping uses the raw int16 samples (any channel), matching
    # the provider's definition, which checks interleaved samples before the
    # mono mixdown.
    raw = wavfile.read(fixture)[1]
    assert raw.dtype == np.int16, f"{fixture} must be PCM16"
    ref_clipping = bool((raw == 32767).any() or (raw == -32768).any())

    run = run_bench(
        bench,
        workspace_root / "peaks" / fixture.stem,
        fixture,
        "analysis.waveform-peaks.v1",
    )
    result = run["result"]
    ref_min, ref_max = reference_peaks(mono)
    peaks_ok = (
        np.array_equal(np.array(result["min"]), ref_min)
        and np.array_equal(np.array(result["max"]), ref_max)
    ) or (
        np.abs(np.array(result["min"]) - ref_min).max() <= 1
        and np.abs(np.array(result["max"]) - ref_max).max() <= 1
    )
    rows.append(
        f"| {fixture.name} | peaks | {run['provider_id']} | "
        f"{run['ms_median']:.2f} ms | buckets={result['bucket_count']} | "
        f"{'PASS' if peaks_ok else 'FAIL'} |"
    )
    if not peaks_ok:
        failures.append(f"{fixture.name} peaks mismatch")

    run = run_bench(
        bench,
        workspace_root / "loudness" / fixture.stem,
        fixture,
        "analysis.loudness.v1",
    )
    result = run["result"]
    ref_peak, ref_rms = reference_loudness(mono)
    loudness_ok = (
        abs(result["peak_dbfs"] - ref_peak) <= 0.01
        and abs(result["rms_dbfs"] - ref_rms) <= 0.01
        and result["clipping"] == ref_clipping
    )
    rows.append(
        f"| {fixture.name} | loudness | {run['provider_id']} | "
        f"{run['ms_median']:.2f} ms | peak={result['peak_dbfs']:.2f} dBFS "
        f"rms={result['rms_dbfs']:.2f} dBFS clip={result['clipping']} | "
        f"{'PASS' if loudness_ok else 'FAIL'} |"
    )
    if not loudness_ok:
        failures.append(f"{fixture.name} loudness mismatch")

    run = run_bench(
        bench,
        workspace_root / "onsets" / fixture.stem,
        fixture,
        "analysis.onsets.v1",
    )
    result = run["result"]
    actual = result["onsets_seconds"]
    if is_click_train:
        matched = match_onsets(CLICK_TRAIN_TIMES, actual)
        onsets_ok = matched == len(CLICK_TRAIN_TIMES) and len(actual) == len(
            CLICK_TRAIN_TIMES
        )
        detail = f"{matched}/{len(CLICK_TRAIN_TIMES)} clicks matched"
    else:
        expected = reference_onsets(mono, sample_rate)
        if not expected:
            # Short fixtures (fewer samples than fft_size) legitimately have
            # no reference onsets; agreement means the provider found none.
            onsets_ok = not actual
            detail = (
                "no reference onsets; provider agrees"
                if onsets_ok
                else f"no reference onsets but provider found {len(actual)}"
            )
        else:
            matched = match_onsets(expected, actual)
            fraction = matched / len(expected)
            onsets_ok = fraction >= 0.5
            detail = (
                f"{matched}/{len(expected)} reference onsets matched "
                f"({fraction:.0%})"
            )
    rows.append(
        f"| {fixture.name} | onsets | {run['provider_id']} | "
        f"{run['ms_median']:.2f} ms | {detail} | "
        f"{'PASS' if onsets_ok else 'FAIL'} |"
    )
    if not onsets_ok:
        failures.append(f"{fixture.name} onsets mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", required=True)
    parser.add_argument("--fixtures-dir", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    fixtures = [Path(args.fixtures_dir) / name for name in FIXTURE_NAMES]
    missing = [fixture.name for fixture in fixtures if not fixture.is_file()]
    assert not missing, f"missing fixtures: {missing}"
    rows = [
        "| fixture | capability | provider | median time | result | verdict |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as temp:
        workspace_root = Path(temp)
        click_train = workspace_root / "click_train.wav"
        make_click_train(click_train)
        for fixture in [*fixtures, click_train]:
            compare_fixture(
                Path(args.bench), workspace_root, fixture, rows, failures
            )

    table = "# analysis-bench comparison\n\n" + "\n".join(rows) + "\n"
    print(table)
    Path(args.report).write_text(table)
    if failures:
        print("FAILURES:", *failures, sep="\n  - ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
