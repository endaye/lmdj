#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("score_slice", ROOT / "tools/provider-benchmark/score_slice.py")
score_slice = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score_slice)
MANIFEST = ROOT / "tests/fixtures/provider-benchmark/sample-slice/manifest.json"

def valid_predictions(frames=None):
    manifest = json.loads(MANIFEST.read_text())
    success = [s for s in manifest["scenarios"] if s["class"] == "success"]
    defaults = {s["id"]: s["expected"]["onset_frames"] for s in success}
    defaults.update(frames or {})
    return {"format": "slice-frame-predictions", "format_version": 1,
            "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
            "cases": [{"fixture_id": s["id"], "source_sha256": s["sha256"], "frames": defaults[s["id"]]} for s in success]}

class ScoreSliceTest(unittest.TestCase):
    def write_predictions(self, value):
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
        json.dump(value, handle)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return Path(handle.name)

    def test_exact_hits_and_micro_scores(self):
        result = score_slice.score(MANIFEST, self.write_predictions(valid_predictions()))
        self.assertEqual(result["micro"], {"tp": 5, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0})

    def test_tolerance_and_closest_match(self):
        changed = valid_predictions({"close_overlapping_tails": [240, 1680]})
        self.assertEqual(score_slice.score(MANIFEST, self.write_predictions(changed))["micro"]["tp"], 5)
        self.assertEqual(score_slice._match([0, 10], [6, 14], 6)[:3], (2, 0, 0))

    def test_silence_and_nullable_ratios(self):
        result = score_slice.score(MANIFEST, self.write_predictions(valid_predictions({"silence": [1]})))
        silence = next(c for c in result["cases"] if c["fixture_id"] == "silence")
        self.assertEqual((silence["tp"], silence["fp"], silence["recall"], silence["f1"]), (0, 1, None, 0.0))
        result = score_slice.score(MANIFEST, self.write_predictions(valid_predictions()))
        silence = next(c for c in result["cases"] if c["fixture_id"] == "silence")
        self.assertTrue(silence["silence_correct"])

    def test_rejects_inventory_hash_order_and_types(self):
        for bad in [
            {**valid_predictions(), "cases": valid_predictions()["cases"][:-1]},
            valid_predictions({"silence": [True]}),
            valid_predictions({"silence": [481, 480]}),
            {**valid_predictions(), "manifest_sha256": "0" * 64},
        ]:
            with self.assertRaises(score_slice.ScoreError):
                score_slice.score(MANIFEST, self.write_predictions(bad))

    def test_rejects_failure_case_and_corrupt_fixture(self):
        bad = valid_predictions()
        bad["cases"][0]["fixture_id"] = "missing_input"
        with self.assertRaises(score_slice.ScoreError):
            score_slice.score(MANIFEST, self.write_predictions(bad))
        bad = valid_predictions()
        bad["cases"][0]["source_sha256"] = "0" * 64
        with self.assertRaises(score_slice.ScoreError):
            score_slice.score(MANIFEST, self.write_predictions(bad))

    def test_result_is_deterministic_and_has_no_host_path(self):
        predictions = self.write_predictions(valid_predictions())
        command = ["python3", str(ROOT / "tools/provider-benchmark/score_slice.py"),
                   "--manifest", str(MANIFEST), "--predictions", str(predictions)]
        first = subprocess.check_output(command, cwd=ROOT)
        second = subprocess.check_output(command, cwd=ROOT)
        self.assertEqual(first, second)
        self.assertNotIn(str(ROOT).encode(), first)

if __name__ == "__main__":
    unittest.main()
