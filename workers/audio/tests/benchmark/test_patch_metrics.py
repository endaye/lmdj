"""Tests for `patch_metrics_for_combo` (spec Task 4).

Fixtures hand-build four combo-dir shapes (no real pipeline run needed):
完整 passed / 缺 pfs / 降级 lanes（drum_low/drum_high）/ 坏 patch.json.
Every file-missing/corrupt path must degrade to a per-field ``None``
(``patch_loads`` -> False) rather than raising.
"""
from __future__ import annotations

import json
from pathlib import Path

from lmdj_audio_worker.benchmark.patch_metrics import patch_metrics_for_combo

TRACK_ID = "testsong"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _write_combo(combo_dir: Path, status: str = "completed") -> None:
    _write_json(combo_dir / "combo.json", {"status": status})


def _write_report(combo_dir: Path, track_id: str, report: dict) -> None:
    _write_json(combo_dir / "pfs" / track_id / "report.json", report)


def _write_patch(combo_dir: Path, track_id: str, patch: dict | str) -> None:
    path = combo_dir / "pfs" / track_id / "patch.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(patch, str):
        path.write_text(patch)
    else:
        path.write_text(json.dumps(patch))


STANDARD_LANES = [
    {"lane": 0, "name": "kick", "kind": "drum", "pitch": 36, "sample": "samples/kick.wav"},
    {"lane": 1, "name": "snare", "kind": "drum", "pitch": 38, "sample": "samples/snare.wav"},
    {"lane": 2, "name": "hat", "kind": "drum", "pitch": 42, "sample": "samples/hat.wav"},
    {"lane": 3, "name": "bass", "kind": "long", "pitch": 48, "sample": "samples/bass.wav"},
    {"lane": 4, "name": "melody_a", "kind": "long", "pitch": 50, "sample": "samples/melody_a.wav"},
]

DEGRADED_LANES = [
    {"lane": 0, "name": "drum_low", "kind": "drum", "pitch": 36, "sample": "samples/drum_low.wav"},
    {"lane": 1, "name": "drum_high", "kind": "drum", "pitch": 42, "sample": "samples/drum_high.wav"},
    {"lane": 2, "name": "bass", "kind": "long", "pitch": 48, "sample": "samples/bass.wav"},
    {"lane": 3, "name": "melody_a", "kind": "long", "pitch": 50, "sample": "samples/melody_a.wav"},
]


class TestFullPassedCombo:
    def test_all_fields_populated(self, tmp_path: Path):
        combo_dir = tmp_path / "combo"
        _write_combo(combo_dir, status="completed")
        _write_report(combo_dir, TRACK_ID, {
            "song_id": TRACK_ID,
            "status": "passed",
            "score": 0.6556,
            "n_samples": 5,
            "lanes": STANDARD_LANES,
            "attempts": [{"window": 0, "start": 8.01, "score": 0.6556}],
        })
        _write_patch(combo_dir, TRACK_ID, {"patch_id": f"{TRACK_ID}-abcd1234"})

        result = patch_metrics_for_combo(combo_dir, TRACK_ID)

        assert result == {
            "combo_completed": True,
            "pipeline_status": "passed",
            "validation_score": 0.6556,
            "attempts": 1,
            "drum_degraded": False,
            "n_samples": 5,
            "n_lanes": 5,
            "lane_names": ["kick", "snare", "hat", "bass", "melody_a"],
            "patch_loads": True,
        }

    def test_multiple_attempts_counted(self, tmp_path: Path):
        combo_dir = tmp_path / "combo"
        _write_combo(combo_dir, status="completed")
        _write_report(combo_dir, TRACK_ID, {
            "status": "passed",
            "score": 0.51,
            "n_samples": 5,
            "lanes": STANDARD_LANES,
            "attempts": [
                {"window": 0, "start": 0.0, "score": 0.2},
                {"window": 1, "start": 4.0, "score": 0.4},
                {"window": 2, "start": 8.0, "score": 0.51},
            ],
        })
        _write_patch(combo_dir, TRACK_ID, {"patch_id": f"{TRACK_ID}-abcd1234"})

        result = patch_metrics_for_combo(combo_dir, TRACK_ID)

        assert result["attempts"] == 3


class TestMissingPfs:
    def test_no_pfs_dir_degrades_to_none(self, tmp_path: Path):
        combo_dir = tmp_path / "combo"
        _write_combo(combo_dir, status="failed")
        # no pfs/, no patch.json at all — pipeline never reached that stage.

        result = patch_metrics_for_combo(combo_dir, TRACK_ID)

        assert result == {
            "combo_completed": False,
            "pipeline_status": None,
            "validation_score": None,
            "attempts": None,
            "drum_degraded": None,
            "n_samples": None,
            "n_lanes": None,
            "lane_names": None,
            "patch_loads": False,
        }

    def test_missing_combo_json_is_not_completed(self, tmp_path: Path):
        combo_dir = tmp_path / "combo"
        combo_dir.mkdir(parents=True)
        # combo.json itself missing (e.g. read mid-write, or wrong path).

        result = patch_metrics_for_combo(combo_dir, TRACK_ID)

        assert result["combo_completed"] is False
        assert result["patch_loads"] is False

    def test_corrupt_combo_json_does_not_raise(self, tmp_path: Path):
        combo_dir = tmp_path / "combo"
        combo_dir.mkdir(parents=True)
        (combo_dir / "combo.json").write_text("{not valid json")

        result = patch_metrics_for_combo(combo_dir, TRACK_ID)

        assert result["combo_completed"] is False

    def test_corrupt_report_json_degrades_to_none(self, tmp_path: Path):
        combo_dir = tmp_path / "combo"
        _write_combo(combo_dir, status="completed")
        report_path = combo_dir / "pfs" / TRACK_ID / "report.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text("{ this is not json")
        _write_patch(combo_dir, TRACK_ID, {"patch_id": f"{TRACK_ID}-abcd1234"})

        result = patch_metrics_for_combo(combo_dir, TRACK_ID)

        assert result["combo_completed"] is True
        assert result["pipeline_status"] is None
        assert result["validation_score"] is None
        assert result["attempts"] is None
        assert result["drum_degraded"] is None
        assert result["n_samples"] is None
        assert result["n_lanes"] is None
        assert result["lane_names"] is None
        assert result["patch_loads"] is True  # patch.json independent of report.json


class TestDegradedLanes:
    def test_drum_low_high_flags_degraded(self, tmp_path: Path):
        combo_dir = tmp_path / "combo"
        _write_combo(combo_dir, status="completed")
        _write_report(combo_dir, TRACK_ID, {
            "status": "passed",
            "score": 0.55,
            "n_samples": 4,
            "lanes": DEGRADED_LANES,
            "attempts": [{"window": 0, "start": 0.0, "score": 0.55}],
        })
        _write_patch(combo_dir, TRACK_ID, {"patch_id": f"{TRACK_ID}-deadbeef"})

        result = patch_metrics_for_combo(combo_dir, TRACK_ID)

        assert result["drum_degraded"] is True
        assert result["n_lanes"] == 4
        assert result["lane_names"] == ["drum_low", "drum_high", "bass", "melody_a"]

    def test_standard_lanes_not_degraded(self, tmp_path: Path):
        combo_dir = tmp_path / "combo"
        _write_combo(combo_dir, status="completed")
        _write_report(combo_dir, TRACK_ID, {
            "status": "passed",
            "score": 0.6,
            "n_samples": 5,
            "lanes": STANDARD_LANES,
            "attempts": [{"window": 0, "start": 0.0, "score": 0.6}],
        })
        _write_patch(combo_dir, TRACK_ID, {"patch_id": f"{TRACK_ID}-abcd1234"})

        result = patch_metrics_for_combo(combo_dir, TRACK_ID)

        assert result["drum_degraded"] is False

    def test_rejected_status_only_one_drum_high_still_degraded(self, tmp_path: Path):
        combo_dir = tmp_path / "combo"
        _write_combo(combo_dir, status="completed")
        _write_report(combo_dir, TRACK_ID, {
            "status": "rejected",
            "score": 0.31,
            "n_samples": 3,
            "lanes": [
                {"lane": 0, "name": "kick", "kind": "drum", "pitch": 36, "sample": "samples/kick.wav"},
                {"lane": 1, "name": "drum_high", "kind": "drum", "pitch": 42, "sample": "samples/drum_high.wav"},
                {"lane": 2, "name": "bass", "kind": "long", "pitch": 48, "sample": "samples/bass.wav"},
            ],
            "attempts": [
                {"window": 0, "start": 0.0, "score": 0.2},
                {"window": 1, "start": 4.0, "score": 0.31},
            ],
        })
        _write_patch(combo_dir, TRACK_ID, {"patch_id": f"{TRACK_ID}-cafef00d"})

        result = patch_metrics_for_combo(combo_dir, TRACK_ID)

        assert result["pipeline_status"] == "rejected"
        assert result["drum_degraded"] is True
        assert result["attempts"] == 2


class TestBadPatchJson:
    def test_missing_patch_json(self, tmp_path: Path):
        combo_dir = tmp_path / "combo"
        _write_combo(combo_dir, status="completed")
        _write_report(combo_dir, TRACK_ID, {
            "status": "passed",
            "score": 0.6556,
            "n_samples": 5,
            "lanes": STANDARD_LANES,
            "attempts": [{"window": 0, "start": 8.01, "score": 0.6556}],
        })
        # no patch.json written at all

        result = patch_metrics_for_combo(combo_dir, TRACK_ID)

        assert result["patch_loads"] is False
        # report-derived fields must still be populated independently.
        assert result["pipeline_status"] == "passed"
        assert result["n_lanes"] == 5

    def test_corrupt_json_patch_loads_false(self, tmp_path: Path):
        combo_dir = tmp_path / "combo"
        _write_combo(combo_dir, status="completed")
        _write_report(combo_dir, TRACK_ID, {
            "status": "passed",
            "score": 0.6556,
            "n_samples": 5,
            "lanes": STANDARD_LANES,
            "attempts": [{"window": 0, "start": 8.01, "score": 0.6556}],
        })
        _write_patch(combo_dir, TRACK_ID, "{ this is not valid json at all")

        result = patch_metrics_for_combo(combo_dir, TRACK_ID)

        assert result["patch_loads"] is False

    def test_valid_json_missing_patch_id_key(self, tmp_path: Path):
        combo_dir = tmp_path / "combo"
        _write_combo(combo_dir, status="completed")
        _write_report(combo_dir, TRACK_ID, {
            "status": "passed",
            "score": 0.6556,
            "n_samples": 5,
            "lanes": STANDARD_LANES,
            "attempts": [{"window": 0, "start": 8.01, "score": 0.6556}],
        })
        _write_patch(combo_dir, TRACK_ID, {"bpm": 89.1})  # valid JSON, no patch_id

        result = patch_metrics_for_combo(combo_dir, TRACK_ID)

        assert result["patch_loads"] is False


class TestMalformedLanes:
    def test_malformed_lanes_degrades_to_none(self, tmp_path: Path):
        """lanes 包含非 dict 条目（如整数）时，整体降级为 None，不抛异常。"""
        combo_dir = tmp_path / "combo"
        _write_combo(combo_dir, status="completed")
        _write_report(combo_dir, TRACK_ID, {
            "status": "passed",
            "score": 0.6,
            "n_samples": 2,
            "lanes": ["drum_low", 123],  # 第二条目是非 dict，应降级
            "attempts": [{"window": 0, "start": 0.0, "score": 0.6}],
        })
        _write_patch(combo_dir, TRACK_ID, {"patch_id": f"{TRACK_ID}-abcd1234"})

        result = patch_metrics_for_combo(combo_dir, TRACK_ID)

        # lanes 相关字段都应为 None，其他字段独立
        assert result["drum_degraded"] is None
        assert result["n_lanes"] is None
        assert result["lane_names"] is None
        # report 的其他字段不受影响
        assert result["validation_score"] == 0.6
        assert result["n_samples"] == 2
        assert result["attempts"] == 1
        assert result["patch_loads"] is True


class TestNonexistentComboDir:
    def test_entirely_missing_combo_dir_does_not_raise(self, tmp_path: Path):
        combo_dir = tmp_path / "does-not-exist"

        result = patch_metrics_for_combo(combo_dir, TRACK_ID)

        assert result["combo_completed"] is False
        assert result["patch_loads"] is False
        assert result["pipeline_status"] is None
