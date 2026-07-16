"""Tests for `listening.py` — anonymized blind-listening packaging (Task 7).

Fixtures hand-build a `results/<dataset>/<track>/<separator>/<device>/<repeat>/`
tree with `combo.json` + `pfs/<track>/{render_preview,loop_preview}.wav` +
`separation/stems/{drums,bass,vocals,other}.wav`, mirroring the shapes
documented in `orchestrator.py`/`snapshots.py`. Fake wav "content" uses unique
per-stem markers that never embed the track/separator/device identifiers
themselves — that keeps the leakage-grep assertions meaningful (a grep hit
inside a copied binary blob would be a false positive unrelated to the
anonymization guarantee we're actually testing: no *directory/file name* or
*README/JSON content outside private-key.json* may reveal track/separator/
device identifiers).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from lmdj_audio_worker.benchmark import listening

DATASET = "ds1"
CANONICAL_STEMS = ("drums", "bass", "vocals", "other")


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _write_combo(run_dir: Path, track: str, separator: str, device: str, repeat: int,
                 status: str = "completed", with_stems: bool = True,
                 with_previews: bool = True) -> Path:
    combo_dir = (run_dir / "results" / DATASET / track / separator / device / str(repeat))
    combo_dir.mkdir(parents=True, exist_ok=True)
    (combo_dir / "combo.json").write_text(json.dumps({
        "status": status, "track": track, "separator": separator,
        "device": device, "repeat": repeat,
    }))
    if with_previews:
        _write_bytes(combo_dir / "pfs" / track / "render_preview.wav", b"RENDER-MARKER-0001")
        _write_bytes(combo_dir / "pfs" / track / "loop_preview.wav", b"LOOP-MARKER-0001")
    if with_stems:
        stems_dir = combo_dir / "separation" / "stems"
        for name in CANONICAL_STEMS:
            _write_bytes(stems_dir / f"{name}.wav", f"STEM-{name.upper()}-CONTENT".encode())
    return combo_dir


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    d = tmp_path / "run-test"
    d.mkdir()
    return d


class TestBuildListeningPackage:
    def test_creates_anon_dir_per_completed_combo(self, run_dir: Path) -> None:
        _write_combo(run_dir, "trackA", "sep-alpha", "cpu", 0)
        _write_combo(run_dir, "trackB", "sep-beta", "mps", 1)
        # a failed combo must be skipped entirely
        _write_combo(run_dir, "trackC", "sep-alpha", "cpu", 0, status="failed")

        out = listening.build_listening_package(run_dir)

        assert out == run_dir / "listening-test"
        anon_dirs = sorted(p for p in out.iterdir() if p.is_dir())
        assert len(anon_dirs) == 2
        for d in anon_dirs:
            assert re.fullmatch(r"[0-9a-f]{12}", d.name)
            assert (d / "render.wav").read_bytes() == b"RENDER-MARKER-0001"
            assert (d / "loop.wav").read_bytes() == b"LOOP-MARKER-0001"
            for i in range(1, 5):
                assert (d / f"stem-{i}.wav").exists()

    def test_private_key_has_all_fields_including_stem_order(self, run_dir: Path) -> None:
        _write_combo(run_dir, "trackA", "sep-alpha", "cpu", 2)

        out = listening.build_listening_package(run_dir)
        key = json.loads((out / "private-key.json").read_text())

        assert len(key) == 1
        (anon_id, entry), = key.items()
        assert entry["track"] == "trackA"
        assert entry["separator"] == "sep-alpha"
        assert entry["device"] == "cpu"
        assert entry["repeat"] == 2
        assert sorted(entry["stem_order"]) == sorted(CANONICAL_STEMS)

        # stem-N.wav content must match the *recorded* order, proving the
        # randomized permutation is faithfully recorded, not just plausible.
        anon_dir = out / anon_id
        for i, stem_name in enumerate(entry["stem_order"], start=1):
            expected = f"STEM-{stem_name.upper()}-CONTENT".encode()
            assert (anon_dir / f"stem-{i}.wav").read_bytes() == expected

    def test_include_stems_false_skips_stem_files(self, run_dir: Path) -> None:
        _write_combo(run_dir, "trackA", "sep-alpha", "cpu", 0)

        out = listening.build_listening_package(run_dir, include_stems=False)
        key = json.loads((out / "private-key.json").read_text())
        (anon_id, entry), = key.items()

        assert entry["stem_order"] == []
        anon_dir = out / anon_id
        assert not any(anon_dir.glob("stem-*.wav"))
        assert (anon_dir / "render.wav").exists()
        assert (anon_dir / "loop.wav").exists()

    def test_skips_combo_missing_preview_files(self, run_dir: Path) -> None:
        _write_combo(run_dir, "trackA", "sep-alpha", "cpu", 0, with_previews=False)

        out = listening.build_listening_package(run_dir)
        key = json.loads((out / "private-key.json").read_text())

        assert key == {}
        assert not any(p.is_dir() for p in out.iterdir())

    def test_no_completed_combos_still_writes_key_and_readme(self, run_dir: Path) -> None:
        out = listening.build_listening_package(run_dir)

        assert json.loads((out / "private-key.json").read_text()) == {}
        assert (out / "README.md").exists()

    def test_readme_documents_protocol(self, run_dir: Path) -> None:
        out = listening.build_listening_package(run_dir)
        text = (out / "README.md").read_text()

        assert "3" in text  # >= 3 raters
        for dim in ("crosstalk", "transients", "low_end", "playability"):
            assert dim in text

    def test_no_leakage_of_track_separator_device_strings(self, run_dir: Path) -> None:
        _write_combo(run_dir, "trackA", "sep-alpha", "cpu", 0)
        _write_combo(run_dir, "trackB", "sep-beta", "mps", 3)

        out = listening.build_listening_package(run_dir)

        for needle in ("trackA", "trackB", "sep-alpha", "sep-beta", "cpu", "mps"):
            result = subprocess.run(
                ["grep", "-r", "-l", "--exclude=private-key.json", needle, str(out)],
                capture_output=True, text=True,
            )
            assert result.returncode == 1, (
                f"leak of {needle!r} found in: {result.stdout!r} {result.stderr!r}"
            )

    def test_anon_dir_names_do_not_encode_identity(self, run_dir: Path) -> None:
        _write_combo(run_dir, "trackA", "sep-alpha", "cpu", 0)
        out = listening.build_listening_package(run_dir)
        anon_dirs = [p.name for p in out.iterdir() if p.is_dir()]
        assert len(anon_dirs) == 1
        assert "trackA" not in anon_dirs[0]
        assert "sep-alpha" not in anon_dirs[0]

    def test_returns_listening_test_dir_path(self, run_dir: Path) -> None:
        out = listening.build_listening_package(run_dir)
        assert out == run_dir / "listening-test"
        assert out.is_dir()

    def test_no_results_dir_at_all(self, run_dir: Path) -> None:
        # run_dir exists but never had any combos written (e.g. every track
        # failed at normalize before any combo_dir was created).
        out = listening.build_listening_package(run_dir)
        assert out.is_dir()
        assert json.loads((out / "private-key.json").read_text()) == {}


class TestLoadListeningScores:
    def test_score_math_matches_hand_computed_mean(self, tmp_path: Path) -> None:
        key = {
            "anon1": {"track": "t1", "separator": "sep-solo", "device": "cpu",
                     "repeat": 0, "stem_order": ["drums", "bass", "vocals", "other"]},
        }
        scores = {
            "anon1": {
                "rater1": {"crosstalk": 2, "transients": 4, "low_end": 3, "playability": 5},
                "rater2": {"crosstalk": 4, "transients": 2, "low_end": 5, "playability": 3},
            },
        }
        key_path = tmp_path / "private-key.json"
        scores_path = tmp_path / "scores.json"
        key_path.write_text(json.dumps(key))
        scores_path.write_text(json.dumps(scores))

        result = listening.load_listening_scores(scores_path, key_path)

        # values = [2,4,3,5,4,2,5,3] -> sum 28, mean 3.5 -> (3.5-1)/4*10 = 6.25
        assert result["sep-solo"]["score"] == pytest.approx(6.25)
        assert result["sep-solo"]["veto"] is False
        assert result["sep-solo"]["n_raters"] == 2
        assert result["sep-solo"]["n_combos"] == 1

    def test_veto_true_when_two_raters_score_one_on_same_dim(self, tmp_path: Path) -> None:
        key = {
            "anonV": {"track": "t1", "separator": "sep-veto", "device": "cpu",
                     "repeat": 0, "stem_order": []},
        }
        scores = {
            "anonV": {
                "rater1": {"crosstalk": 1, "transients": 3, "low_end": 3, "playability": 3},
                "rater2": {"crosstalk": 1, "transients": 3, "low_end": 3, "playability": 3},
                "rater3": {"crosstalk": 4, "transients": 3, "low_end": 3, "playability": 3},
            },
        }
        key_path = tmp_path / "private-key.json"
        scores_path = tmp_path / "scores.json"
        key_path.write_text(json.dumps(key))
        scores_path.write_text(json.dumps(scores))

        result = listening.load_listening_scores(scores_path, key_path)

        assert result["sep-veto"]["veto"] is True

    def test_veto_false_when_only_one_rater_scores_one(self, tmp_path: Path) -> None:
        key = {
            "anonN": {"track": "t1", "separator": "sep-noveto", "device": "cpu",
                     "repeat": 0, "stem_order": []},
        }
        scores = {
            "anonN": {
                "rater1": {"crosstalk": 1, "transients": 3, "low_end": 3, "playability": 3},
                "rater2": {"crosstalk": 3, "transients": 3, "low_end": 3, "playability": 3},
                "rater3": {"crosstalk": 4, "transients": 3, "low_end": 3, "playability": 3},
            },
        }
        key_path = tmp_path / "private-key.json"
        scores_path = tmp_path / "scores.json"
        key_path.write_text(json.dumps(key))
        scores_path.write_text(json.dumps(scores))

        result = listening.load_listening_scores(scores_path, key_path)

        assert result["sep-noveto"]["veto"] is False

    def test_aggregates_multiple_combos_for_same_separator(self, tmp_path: Path) -> None:
        key = {
            "anon1": {"track": "t1", "separator": "sep-a", "device": "cpu",
                     "repeat": 0, "stem_order": []},
            "anon2": {"track": "t2", "separator": "sep-a", "device": "cpu",
                     "repeat": 0, "stem_order": []},
        }
        scores = {
            "anon1": {"rater1": {"crosstalk": 5, "transients": 5, "low_end": 5, "playability": 5}},
            "anon2": {"rater1": {"crosstalk": 1, "transients": 1, "low_end": 1, "playability": 1}},
        }
        key_path = tmp_path / "private-key.json"
        scores_path = tmp_path / "scores.json"
        key_path.write_text(json.dumps(key))
        scores_path.write_text(json.dumps(scores))

        result = listening.load_listening_scores(scores_path, key_path)

        # mean of [5,5,5,5,1,1,1,1] = 3.0 -> (3-1)/4*10 = 5.0
        assert result["sep-a"]["score"] == pytest.approx(5.0)
        assert result["sep-a"]["n_combos"] == 2
        # only one rater scored 1 per (combo, dim) -> no veto
        assert result["sep-a"]["veto"] is False

    def test_separates_by_separator_independently(self, tmp_path: Path) -> None:
        key = {
            "anon1": {"track": "t1", "separator": "sep-x", "device": "cpu",
                     "repeat": 0, "stem_order": []},
            "anon2": {"track": "t2", "separator": "sep-y", "device": "cpu",
                     "repeat": 0, "stem_order": []},
        }
        scores = {
            "anon1": {"rater1": {"crosstalk": 5, "transients": 5, "low_end": 5, "playability": 5}},
            "anon2": {"rater1": {"crosstalk": 1, "transients": 1, "low_end": 1, "playability": 1}},
        }
        key_path = tmp_path / "private-key.json"
        scores_path = tmp_path / "scores.json"
        key_path.write_text(json.dumps(key))
        scores_path.write_text(json.dumps(scores))

        result = listening.load_listening_scores(scores_path, key_path)

        assert result["sep-x"]["score"] == pytest.approx(10.0)
        assert result["sep-y"]["score"] == pytest.approx(0.0)

    def test_unknown_anon_id_in_scores_is_ignored(self, tmp_path: Path) -> None:
        key = {
            "anon1": {"track": "t1", "separator": "sep-a", "device": "cpu",
                     "repeat": 0, "stem_order": []},
        }
        scores = {
            "anon1": {"rater1": {"crosstalk": 3, "transients": 3, "low_end": 3, "playability": 3}},
            "anon-not-in-key": {"rater1": {"crosstalk": 5, "transients": 5, "low_end": 5, "playability": 5}},
        }
        key_path = tmp_path / "private-key.json"
        scores_path = tmp_path / "scores.json"
        key_path.write_text(json.dumps(key))
        scores_path.write_text(json.dumps(scores))

        result = listening.load_listening_scores(scores_path, key_path)

        assert list(result.keys()) == ["sep-a"]
