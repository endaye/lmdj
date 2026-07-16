"""Tests for museval SDR wrapper, GT loading, and per-combo objective metrics.

Covers `sdr_framewise_median`, `load_stems_dir`, `load_gt`, and
`objective_for_combo` per docs/superpowers/plans/2026-07-16-separation-phase1c-metrics.md
Task 3. Synthetic four-stem signals (sines at different frequencies + a pulse
train for drums) stand in for real separated stems; museval is called for real
(no mocking) except in the dedicated all-NaN guard test for `sdr_framewise_median`,
where `bss_eval` is monkeypatched to force a deterministic all-NaN row.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from lmdj_audio_worker.benchmark import metrics
from lmdj_audio_worker.benchmark.manifest import Track

SR = 44100
STEMS = metrics.STEMS


def _sine(freq: float, n: int, sr: int = SR) -> np.ndarray:
    t = np.arange(n) / sr
    x = np.sin(2 * np.pi * freq * t).astype(np.float32)
    return np.column_stack([x, x])


def _pulses(n: int, sr: int = SR, interval_s: float = 0.5) -> np.ndarray:
    x = np.zeros(n, dtype=np.float32)
    step = int(interval_s * sr)
    x[::step] = 1.0
    return np.column_stack([x, x])


def make_gt_stems(n: int = SR * 2) -> dict:
    """合成四轨：drums=脉冲串，bass/vocals=不同频率正弦，other=双频和声。"""
    return {
        "drums": _pulses(n),
        "bass": _sine(80.0, n),
        "vocals": _sine(300.0, n),
        "other": _sine(440.0, n) + _sine(660.0, n),
    }


def write_stems(dir_path: Path, stems: dict, sr: int = SR) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    for name, data in stems.items():
        sf.write(str(dir_path / f"{name}.wav"), data, sr, subtype="FLOAT")


def make_track(track_id: str = "gt-song", has_gt: bool = True, gt_rel: dict | None = None) -> Track:
    gt = None
    if has_gt:
        gt = gt_rel or {stem: f"{track_id}/{stem}.wav" for stem in STEMS}
    return Track(id=track_id, input=f"{track_id}/mix.wav", split="full",
                 tags=(), has_ground_truth=has_gt, ground_truth=gt)


class TestLoadStemsDir:
    def test_loads_four_canonical_wavs(self, tmp_path):
        stems = make_gt_stems(n=1000)
        write_stems(tmp_path / "stems", stems)

        loaded = metrics.load_stems_dir(tmp_path / "stems")

        assert set(loaded) == set(STEMS)
        for stem in STEMS:
            assert loaded[stem].shape == (1000, 2)
            assert loaded[stem].dtype == np.float32

    def test_missing_stem_raises_value_error(self, tmp_path):
        stems = make_gt_stems(n=1000)
        del stems["bass"]
        write_stems(tmp_path / "stems", stems)

        with pytest.raises(ValueError, match="bass"):
            metrics.load_stems_dir(tmp_path / "stems")


class TestLoadGt:
    def test_loads_and_validates_sample_rate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(tmp_path))
        stems = make_gt_stems(n=1000)
        write_stems(tmp_path / "gt-song", stems)

        loaded = metrics.load_gt(make_track())

        assert set(loaded) == set(STEMS)
        for stem in STEMS:
            assert loaded[stem].shape == (1000, 2)

    def test_bad_sample_rate_raises_value_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(tmp_path))
        stems = make_gt_stems(n=1000)
        write_stems(tmp_path / "gt-song", stems)
        sf.write(str(tmp_path / "gt-song" / "bass.wav"), stems["bass"], 22050, subtype="FLOAT")

        with pytest.raises(ValueError, match="44100"):
            metrics.load_gt(make_track())


class TestSdrFramewiseMedian:
    def test_near_perfect_reconstruction_is_very_high(self):
        gt = make_gt_stems()
        rng = np.random.default_rng(7)
        est = {stem: (data + rng.normal(scale=1e-6, size=data.shape).astype(np.float32))
               for stem, data in gt.items()}

        result = metrics.sdr_framewise_median(gt, est)

        for stem in STEMS:
            assert result[stem] is not None
            assert result[stem] > 40.0, f"{stem}: {result[stem]}"

    def test_noisy_estimate_gives_finite_value(self):
        gt = make_gt_stems()
        rng = np.random.default_rng(8)
        est = {stem: (data + rng.normal(scale=0.05, size=data.shape).astype(np.float32))
               for stem, data in gt.items()}

        result = metrics.sdr_framewise_median(gt, est)

        for stem in STEMS:
            assert result[stem] is not None
            assert math.isfinite(result[stem])

    def test_all_nan_stem_becomes_none(self, monkeypatch):
        gt = make_gt_stems(n=SR)
        est = {stem: data.copy() for stem, data in gt.items()}

        def fake_bss_eval(ref, est_stack, window=44100, hop=44100):
            n_frames = 2
            sdr = np.zeros((4, n_frames))
            sdr[1, :] = np.nan  # bass row fully NaN
            dummy = np.zeros((4, n_frames))
            return sdr, dummy, dummy, dummy, dummy

        monkeypatch.setattr("museval.metrics.bss_eval", fake_bss_eval)

        result = metrics.sdr_framewise_median(gt, est)

        assert result["bass"] is None
        for stem in ("drums", "vocals", "other"):
            assert result[stem] == pytest.approx(0.0)


class TestObjectiveForCombo:
    def _combo_dir(self, tmp_path: Path, estimates: dict) -> Path:
        combo_dir = tmp_path / "combo"
        write_stems(combo_dir / "separation" / "stems", estimates)
        return combo_dir

    def test_no_gt_track_only_has_mixture_consistency(self, tmp_path):
        gt = make_gt_stems(n=2000)
        mix = sum(gt[s] for s in STEMS)
        combo_dir = self._combo_dir(tmp_path, gt)
        track = make_track(has_gt=False)

        result = metrics.objective_for_combo(combo_dir, track, mix)

        assert result["has_gt"] is False
        assert set(result) <= {"has_gt", "mixture_consistency", "warnings"}
        assert result["mixture_consistency"] == pytest.approx(-120.0, abs=1e-3)

    def test_gt_track_reports_sdr_si_sdr_leakage(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(tmp_path))
        gt = make_gt_stems(n=SR)
        rng = np.random.default_rng(9)
        est = {stem: (data + rng.normal(scale=0.05, size=data.shape).astype(np.float32))
               for stem, data in gt.items()}
        write_stems(tmp_path / "gt-song", gt)
        combo_dir = self._combo_dir(tmp_path, est)
        mix = sum(est[s] for s in STEMS)

        result = metrics.objective_for_combo(combo_dir, make_track(), mix)

        assert result["has_gt"] is True
        assert "mean" in result["sdr"]
        assert "mean" in result["si_sdr"]
        for stem in STEMS:
            assert result["sdr"][stem] is not None
            assert result["si_sdr"][stem] is not None
            assert result["leakage"][stem] is not None
        assert result["sdr"]["mean"] > 0
        assert result["si_sdr"]["mean"] > 0
        assert "warnings" not in result

    def test_length_diff_within_tolerance_is_truncated(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(tmp_path))
        gt = make_gt_stems(n=SR)
        write_stems(tmp_path / "gt-song", gt)
        # One sample shorter + tiny noise: a bit-exact truncated copy would give an
        # exact (inf) museval SDR, which the NaN/inf guard would then fold to None —
        # the tiny perturbation keeps this a realistic "very good but not exact" case.
        rng = np.random.default_rng(11)
        est = {stem: (data[:-1] + rng.normal(scale=1e-6, size=data[:-1].shape).astype(np.float32))
               for stem, data in gt.items()}
        combo_dir = self._combo_dir(tmp_path, est)
        mix = sum(est[s] for s in STEMS)

        result = metrics.objective_for_combo(combo_dir, make_track(), mix)

        assert result["has_gt"] is True
        assert result["sdr"]["mean"] is not None

    def test_length_diff_beyond_tolerance_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(tmp_path))
        gt = make_gt_stems(n=SR)
        write_stems(tmp_path / "gt-song", gt)
        est = {stem: data[:-5] for stem, data in gt.items()}
        combo_dir = self._combo_dir(tmp_path, est)
        mix = sum(est[s] for s in STEMS)

        with pytest.raises(ValueError):
            metrics.objective_for_combo(combo_dir, make_track(), mix)

    def test_nan_in_estimate_guards_to_none_with_warning(self, tmp_path, monkeypatch):
        """NaN guard (2026-07-16 review addendum): a corrupted estimate stem must
        degrade to None + a warnings entry for every metric it touches, never raise.
        """
        monkeypatch.setenv("LMDJ_BENCH_DATA_ROOT", str(tmp_path))
        gt = make_gt_stems(n=SR)
        write_stems(tmp_path / "gt-song", gt)
        # Tiny noise on every stem keeps the unaffected stems' museval SDR away
        # from the exact-match (inf) edge case; only bass gets an explicit NaN.
        rng = np.random.default_rng(12)
        est = {stem: (data + rng.normal(scale=1e-6, size=data.shape).astype(np.float32))
               for stem, data in gt.items()}
        est["bass"][100, 0] = np.nan
        combo_dir = self._combo_dir(tmp_path, est)
        mix = sum(gt[s] for s in STEMS)

        result = metrics.objective_for_combo(combo_dir, make_track(), mix)

        assert result["mixture_consistency"] is None
        assert result["si_sdr"]["bass"] is None
        assert result["sdr"]["bass"] is None
        assert result["leakage"]["bass"] is None
        assert "warnings" in result
        assert any("bass" in w for w in result["warnings"])
        for stem in ("drums", "vocals", "other"):
            assert result["si_sdr"][stem] is not None
            assert result["sdr"][stem] is not None
            assert result["leakage"][stem] is not None
