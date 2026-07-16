"""Tests for `report.py` — collect_run / build_summary / write_summary (Task 6).

Fixtures hand-build `results/<dataset>/<track>/<separator>/<device>/<repeat>/
combo.json` trees directly (no real pipeline/orchestrator run needed), mirroring
the shapes documented in `orchestrator.py`/`patch_metrics.py`/`metrics.py`.
`objective_for_combo` and `_load_mix` are monkeypatched per the brief's guidance
("objective 部分直接注入 metrics dict") so tests never need real GT/mix audio
or `LMDJ_BENCH_DATA_ROOT`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from lmdj_audio_worker.benchmark import report
from lmdj_audio_worker.benchmark.manifest import Manifest, Track

DS = "ds1"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _write_env(run_dir: Path, platform_str: str, run_id: str = "run-test") -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "environment.json", {"platform": platform_str})
    _write_json(run_dir / "run.json", {"run_id": run_id})


def _combo_dir(run_dir: Path, track: str, separator: str, device: str, repeat: int) -> Path:
    return run_dir / "results" / DS / track / separator / device / str(repeat)


def _write_combo(run_dir: Path, track: str, separator: str, device: str, repeat: int,
                 status: str = "completed", error_category: str | None = None,
                 performance: dict | None = None,
                 checkpoint_sha256: str | None = None) -> Path:
    combo_dir = _combo_dir(run_dir, track, separator, device, repeat)
    _write_json(combo_dir / "combo.json", {
        "status": status,
        "error_category": error_category,
        "performance": performance,
        "cache_key_components": {"checkpoint_sha256": checkpoint_sha256} if checkpoint_sha256 else {},
        "track": track, "separator": separator, "device": device, "repeat": repeat,
    })
    return combo_dir


def _write_separation_json(combo_dir: Path, duration_seconds: float) -> None:
    _write_json(combo_dir / "separation" / "separation.json", {
        "audio": {"sample_rate": 44100, "channels": 2, "duration_seconds": duration_seconds},
    })


def _write_report(combo_dir: Path, track_id: str, report_data: dict) -> None:
    _write_json(combo_dir / "pfs" / track_id / "report.json", report_data)


def _write_patch(combo_dir: Path, track_id: str, patch: dict) -> None:
    _write_json(combo_dir / "pfs" / track_id / "patch.json", patch)


_PERF = {
    "model_load_seconds": 1.0, "inference_seconds": 2.0, "wall_seconds": 3.5,
    "peak_rss_bytes": 1_000_000, "peak_device_memory_bytes": 2_000_000,
}

STANDARD_LANES = [{"lane": 0, "name": "kick"}, {"lane": 1, "name": "bass"}]


def _passing_report(n_samples: int = 2, lanes=None) -> dict:
    return {
        "status": "passed", "score": 0.7, "n_samples": n_samples,
        "lanes": lanes if lanes is not None else STANDARD_LANES,
        "attempts": [{"window": 0, "start": 0.0, "score": 0.7}],
    }


class TestCollectRunAggregation:
    def test_counts_and_completion_rate(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        _write_env(run_dir, "macOS-14.5-arm64")
        _write_combo(run_dir, "song1", "sepA", "cpu", 0, status="completed", performance=_PERF)
        _write_combo(run_dir, "song2", "sepA", "cpu", 0, status="failed",
                    error_category="invalid_stems")

        result = report.collect_run(run_dir, manifests={})

        agg = result["per_separator_device"]["sepA"]["cpu"]
        assert agg["total_combos"] == 2
        assert agg["completed_combos"] == 1
        assert agg["failed_combos"] == 1
        assert agg["completion_rate"] == pytest.approx(0.5)
        assert agg["failure_categories"] == {"invalid_stems": 1}
        assert agg["invalid_stems_failures"] == 1
        assert agg["contract_compliance_rate"] == pytest.approx(0.5)

    def test_performance_means_from_completed_combos_only(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        _write_env(run_dir, "macOS-14.5-arm64")
        _write_combo(run_dir, "song1", "sepA", "cpu", 0, status="completed", performance=_PERF)
        _write_combo(run_dir, "song2", "sepA", "cpu", 0, status="failed", error_category="inference")
        # Defensive edge case: orchestrator never actually emits `status="completed"`
        # with `performance=None`, but the aggregator filters on dict-presence, not
        # on `status` — this asserts that decoupling doesn't crash or skew the mean.
        _write_combo(run_dir, "song3", "sepA", "cpu", 0, status="completed", performance=None)

        result = report.collect_run(run_dir, manifests={})

        perf = result["per_separator_device"]["sepA"]["cpu"]["performance"]
        assert perf["wall_seconds_mean"] == pytest.approx(3.5)
        assert perf["peak_rss_bytes_max"] == 1_000_000
        assert perf["peak_device_memory_bytes_max"] == 2_000_000
        assert perf["peak_memory_max"] == 2_000_000
        assert perf["model_load_seconds_mean"] == pytest.approx(1.0)

    def test_rtf_wall_from_separation_json_duration(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        _write_env(run_dir, "macOS-14.5-arm64")
        combo_dir = _write_combo(run_dir, "song1", "sepA", "cpu", 0, status="completed",
                                 performance=_PERF)
        _write_separation_json(combo_dir, duration_seconds=4.0)

        result = report.collect_run(run_dir, manifests={})

        raw = result["raw_combos"][0]
        assert raw["rtf_wall"] == pytest.approx(2.0 / 4.0)
        assert result["per_separator_device"]["sepA"]["cpu"]["performance"]["rtf_wall_mean"] == pytest.approx(0.5)

    def test_missing_duration_skips_rtf(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        _write_env(run_dir, "macOS-14.5-arm64")
        _write_combo(run_dir, "song1", "sepA", "cpu", 0, status="completed", performance=_PERF)
        # no separation.json written -> duration unknown

        result = report.collect_run(run_dir, manifests={})

        assert result["raw_combos"][0]["rtf_wall"] is None
        assert result["per_separator_device"]["sepA"]["cpu"]["performance"]["rtf_wall_mean"] is None

    def test_patch_metrics_merged_per_combo(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        _write_env(run_dir, "macOS-14.5-arm64")
        combo_dir = _write_combo(run_dir, "song1", "sepA", "cpu", 0, status="completed",
                                 performance=_PERF)
        _write_report(combo_dir, "song1", _passing_report())
        _write_patch(combo_dir, "song1", {"patch_id": "song1-abcd1234"})

        result = report.collect_run(run_dir, manifests={})

        agg = result["per_separator_device"]["sepA"]["cpu"]
        assert agg["patch"]["completed_passed_rate"] == pytest.approx(1.0)
        assert agg["patch"]["validation_score_mean"] == pytest.approx(0.7)
        assert agg["patch"]["retry_degrade_clean_rate"] == pytest.approx(1.0)

    def test_checkpoint_bytes_measured_from_cache_dir(self, tmp_path: Path, monkeypatch):
        cache_dir = tmp_path / "cache"
        monkeypatch.setenv("LMDJ_MODEL_CACHE", str(cache_dir))
        ckpt_dir = cache_dir / "sepA" / "deadbeef"
        ckpt_dir.mkdir(parents=True)
        (ckpt_dir / "model.bin").write_bytes(b"x" * 1234)

        run_dir = tmp_path / "run1"
        _write_env(run_dir, "macOS-14.5-arm64")
        _write_combo(run_dir, "song1", "sepA", "cpu", 0, status="completed",
                    performance=_PERF, checkpoint_sha256="deadbeef")

        result = report.collect_run(run_dir, manifests={})

        assert result["raw_combos"][0]["checkpoint_bytes"] == 1234
        assert result["per_separator_device"]["sepA"]["cpu"]["performance"]["checkpoint_bytes"] == 1234

    def test_checkpoint_bytes_none_when_unreadable(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("LMDJ_MODEL_CACHE", str(tmp_path / "no-such-cache"))
        run_dir = tmp_path / "run1"
        _write_env(run_dir, "macOS-14.5-arm64")
        _write_combo(run_dir, "song1", "sepA", "cpu", 0, status="completed",
                    performance=_PERF, checkpoint_sha256="deadbeef")

        result = report.collect_run(run_dir, manifests={})

        assert result["raw_combos"][0]["checkpoint_bytes"] is None

    def test_structural_stability_none_without_repeats(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        _write_env(run_dir, "macOS-14.5-arm64")
        combo_dir = _write_combo(run_dir, "song1", "sepA", "cpu", 0, status="completed",
                                 performance=_PERF)
        _write_report(combo_dir, "song1", _passing_report())

        result = report.collect_run(run_dir, manifests={})

        assert result["per_separator_device"]["sepA"]["cpu"]["structural_stability"] is None

    def test_structural_stability_consistent_repeats(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        _write_env(run_dir, "macOS-14.5-arm64")
        for repeat in (0, 1):
            combo_dir = _write_combo(run_dir, "song1", "sepA", "cpu", repeat,
                                     status="completed", performance=_PERF)
            _write_report(combo_dir, "song1", _passing_report(n_samples=2))

        result = report.collect_run(run_dir, manifests={})

        assert result["per_separator_device"]["sepA"]["cpu"]["structural_stability"] == pytest.approx(1.0)

    def test_structural_stability_inconsistent_repeats(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        _write_env(run_dir, "macOS-14.5-arm64")
        combo_dir0 = _write_combo(run_dir, "song1", "sepA", "cpu", 0,
                                  status="completed", performance=_PERF)
        _write_report(combo_dir0, "song1", _passing_report(n_samples=2))
        combo_dir1 = _write_combo(run_dir, "song1", "sepA", "cpu", 1,
                                  status="completed", performance=_PERF)
        _write_report(combo_dir1, "song1",
                     _passing_report(n_samples=3, lanes=STANDARD_LANES + [{"lane": 2, "name": "hat"}]))

        result = report.collect_run(run_dir, manifests={})

        assert result["per_separator_device"]["sepA"]["cpu"]["structural_stability"] == pytest.approx(0.0)


class TestCollectRunObjective:
    def _manifest(self, has_gt: bool = True) -> dict:
        track = Track(id="song1", input="song1.wav", split="full", tags=(),
                     has_ground_truth=has_gt,
                     ground_truth={s: f"song1/{s}.wav" for s in
                                   ("drums", "bass", "vocals", "other")} if has_gt else None)
        return {DS: Manifest(dataset_id=DS, tracks=(track,))}

    def test_objective_computed_for_completed_combo(self, tmp_path: Path, monkeypatch):
        run_dir = tmp_path / "run1"
        _write_env(run_dir, "macOS-14.5-arm64")
        _write_combo(run_dir, "song1", "sepA", "cpu", 0, status="completed", performance=_PERF)

        fake_objective = {"has_gt": True, "mixture_consistency": -40.0,
                          "sdr": {"mean": 8.0}, "si_sdr": {"mean": 7.5},
                          "leakage": {"drums": -10.0, "bass": -12.0, "vocals": -9.0, "other": -11.0}}
        monkeypatch.setattr(report, "objective_for_combo",
                            lambda combo_dir, track, mix: fake_objective)
        monkeypatch.setattr(report, "_load_mix", lambda run_dir, dataset_id, track_id: object())

        result = report.collect_run(run_dir, manifests=self._manifest())

        assert result["raw_combos"][0]["objective"] == fake_objective
        sep = result["per_separator_device"]["sepA"]["cpu"]["separation"]
        assert sep["sdr_mean"] == pytest.approx(8.0)
        assert sep["si_sdr_mean"] == pytest.approx(7.5)
        assert sep["consistency_leakage_mean"] == pytest.approx(-40.0)

    def test_objective_skipped_for_failed_combo(self, tmp_path: Path, monkeypatch):
        run_dir = tmp_path / "run1"
        _write_env(run_dir, "macOS-14.5-arm64")
        _write_combo(run_dir, "song1", "sepA", "cpu", 0, status="failed",
                    error_category="inference")

        called = []
        monkeypatch.setattr(report, "objective_for_combo",
                            lambda combo_dir, track, mix: called.append(1) or {})

        result = report.collect_run(run_dir, manifests=self._manifest())

        assert called == []
        assert result["raw_combos"][0]["objective"] is None

    def test_missing_manifest_track_skips_objective_with_warning(self, tmp_path: Path, monkeypatch):
        run_dir = tmp_path / "run1"
        _write_env(run_dir, "macOS-14.5-arm64")
        _write_combo(run_dir, "song1", "sepA", "cpu", 0, status="completed", performance=_PERF)

        called = []
        monkeypatch.setattr(report, "objective_for_combo",
                            lambda combo_dir, track, mix: called.append(1) or {})

        result = report.collect_run(run_dir, manifests={})  # no manifest at all

        assert called == []
        assert result["raw_combos"][0]["objective"] is None
        assert any("manifest" in w for w in result["warnings"])

    def test_missing_mix_audio_skips_objective_with_warning(self, tmp_path: Path, monkeypatch):
        run_dir = tmp_path / "run1"
        _write_env(run_dir, "macOS-14.5-arm64")
        _write_combo(run_dir, "song1", "sepA", "cpu", 0, status="completed", performance=_PERF)

        called = []
        monkeypatch.setattr(report, "objective_for_combo",
                            lambda combo_dir, track, mix: called.append(1) or {})
        # no run_dir/normalized/... written -> _load_mix returns None (real impl, not mocked)

        result = report.collect_run(run_dir, manifests=self._manifest())

        assert called == []
        assert result["raw_combos"][0]["objective"] is None
        assert any("归一化混音" in w for w in result["warnings"])

    def test_corrupt_normalized_mix_audio_skips_objective_with_warning(self, tmp_path: Path, monkeypatch):
        run_dir = tmp_path / "run1"
        _write_env(run_dir, "macOS-14.5-arm64")
        _write_combo(run_dir, "song1", "sepA", "cpu", 0, status="completed", performance=_PERF)
        norm_dir = run_dir / "normalized" / DS / "song1"
        norm_dir.mkdir(parents=True)
        (norm_dir / "song1.wav").write_bytes(b"not a real wav file")

        called = []
        monkeypatch.setattr(report, "objective_for_combo",
                            lambda combo_dir, track, mix: called.append(1) or {})

        result = report.collect_run(run_dir, manifests=self._manifest())

        assert called == []
        assert result["raw_combos"][0]["objective"] is None
        assert any("读取失败" in w for w in result["warnings"])

    def test_objective_exception_caught_as_warning(self, tmp_path: Path, monkeypatch):
        run_dir = tmp_path / "run1"
        _write_env(run_dir, "macOS-14.5-arm64")
        _write_combo(run_dir, "song1", "sepA", "cpu", 0, status="completed", performance=_PERF)

        def _boom(combo_dir, track, mix):
            raise ValueError("GT 不可达")

        monkeypatch.setattr(report, "objective_for_combo", _boom)
        monkeypatch.setattr(report, "_load_mix", lambda run_dir, dataset_id, track_id: object())

        result = report.collect_run(run_dir, manifests=self._manifest())

        assert result["raw_combos"][0]["objective"] is None
        assert any("objective 计算失败" in w for w in result["warnings"])


class TestBuildSummary:
    def _one_run(self, tmp_path, name, platform_str, device, peak_rss, run_id):
        run_dir = tmp_path / name
        _write_env(run_dir, platform_str, run_id=run_id)
        _write_combo(run_dir, "song1", "sepA", device, 0, status="completed",
                    performance={**_PERF, "peak_rss_bytes": peak_rss})
        return report.collect_run(run_dir, manifests={})

    def test_merges_raw_combos_across_runs(self, tmp_path: Path):
        run1 = self._one_run(tmp_path, "run1", "macOS-14.5-arm64", "mps", 1_000_000, "run-mac")
        run2 = self._one_run(tmp_path, "run2", "Linux-5.15.0-x86_64", "cpu", 2_000_000, "run-linux")

        summary = report.build_summary([run1, run2])

        assert len(summary["raw"]["combos"]) == 2
        assert set(summary["run_ids"]) == {"run-mac", "run-linux"}
        assert "mps" in summary["per_separator_device"]["sepA"]
        assert "cpu" in summary["per_separator_device"]["sepA"]
        # pooled per-separator view combines both devices' combos
        assert summary["per_separator"]["sepA"]["total_combos"] == 2

    def test_csv_rows_columns_and_roundtrip(self, tmp_path: Path):
        run1 = self._one_run(tmp_path, "run1", "macOS-14.5-arm64", "mps", 1_000_000, "run-mac")

        summary = report.build_summary([run1])
        out_dir = tmp_path / "out"
        report.write_summary(out_dir, summary)

        assert (out_dir / "summary.json").exists()
        assert (out_dir / "summary.csv").exists()

        df = pd.read_csv(out_dir / "summary.csv")
        expected_cols = {
            "separator", "device", "total_combos", "completed_combos",
            "completion_rate", "sdr_mean", "si_sdr_mean", "mixture_consistency_mean",
            "passed_rate", "rtf_wall_mean", "peak_memory_bytes", "total_score",
            "scored_out_of", "gate_blocked",
        }
        assert expected_cols.issubset(set(df.columns))
        assert len(df) == 1
        assert df.iloc[0]["separator"] == "sepA"
        assert df.iloc[0]["device"] == "mps"

    def test_summary_json_has_no_absolute_paths(self, tmp_path: Path):
        run1 = self._one_run(tmp_path, "run1", "macOS-14.5-arm64", "mps", 1_000_000, "run-mac")

        summary = report.build_summary([run1])

        serialized = json.dumps(summary, default=str)
        assert str(tmp_path) not in serialized
        assert str(tmp_path.resolve()) not in serialized

    def test_linux_rss_carry_forward_mac_only_is_unknown(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        _write_env(run_dir, "macOS-14.5-arm64")
        # Mac run: cpu device present too, but the *run itself* is not linux —
        # must not be picked up by the linux_rss_limit gate input.
        _write_combo(run_dir, "song1", "sepA", "cpu", 0, status="completed",
                    performance={**_PERF, "peak_rss_bytes": 50 * 1024 ** 3})  # huge, would fail if used
        run1 = report.collect_run(run_dir, manifests={})

        summary = report.build_summary([run1])

        assert summary["hard_gate_input"]["sepA"]["peak_rss_bytes_max"] is None
        assert summary["gates"]["sepA"]["linux_rss_limit"] == "unknown"

    def test_linux_rss_carry_forward_uses_only_linux_rows(self, tmp_path: Path):
        mac_run_dir = tmp_path / "mac_run"
        _write_env(mac_run_dir, "macOS-14.5-arm64")
        _write_combo(mac_run_dir, "song1", "sepA", "cpu", 0, status="completed",
                    performance={**_PERF, "peak_rss_bytes": 50 * 1024 ** 3})  # over 12GiB — must be ignored
        mac_run = report.collect_run(mac_run_dir, manifests={})

        linux_run_dir = tmp_path / "linux_run"
        _write_env(linux_run_dir, "Linux-5.15.0-x86_64-with-glibc2.31")
        _write_combo(linux_run_dir, "song1", "sepA", "cpu", 0, status="completed",
                    performance={**_PERF, "peak_rss_bytes": 4 * 1024 ** 3})  # under 12GiB
        linux_run = report.collect_run(linux_run_dir, manifests={})

        summary = report.build_summary([mac_run, linux_run])

        assert summary["hard_gate_input"]["sepA"]["peak_rss_bytes_max"] == 4 * 1024 ** 3
        assert summary["gates"]["sepA"]["linux_rss_limit"] == "pass"
