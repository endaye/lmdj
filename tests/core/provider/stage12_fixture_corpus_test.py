#!/usr/bin/env python3
"""Contract tests for the deterministic Stage 12 sample.slice smoke corpus.

The production change that makes these tests pass is the fixture generator and
the exact committed corpus it owns. The assertions use plan-owned literal
truth rather than values derived from the generator under test.
"""

from __future__ import annotations

import hashlib
import io
import importlib.util
import json
from pathlib import Path, PurePosixPath
import subprocess
import struct
import sys
import tempfile
import unittest
import wave


ROOT = Path(__file__).resolve().parents[3]
GENERATOR_PATH = (
    ROOT / "tools/provider-benchmark/generate_sample_slice_smoke.py"
)
FIXTURE_DIR = ROOT / "tests/fixtures/provider-benchmark/sample-slice"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"

WAV_NAMES = {
    "slice-basic.wav",
    "slice-close-overlap.wav",
    "slice-silence.wav",
    "slice-truncated.wav",
    "slice-bad-header.wav",
}
SCENARIO_IDS = [
    "basic_three_onsets",
    "close_overlapping_tails",
    "silence",
    "missing_input",
    "truncated_data",
    "bad_riff_header",
]


class Stage12FixtureCorpusTest(unittest.TestCase):
    def load_generator(self):
        self.assertTrue(
            GENERATOR_PATH.is_file(),
            f"Stage 12 fixture generator is missing: {GENERATOR_PATH}",
        )
        spec = importlib.util.spec_from_file_location(
            "stage12_sample_slice_fixture_generator", GENERATOR_PATH
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def build_corpus(self):
        module = self.load_generator()
        generated, manifest = module.build_corpus()
        self.assertEqual(set(generated), WAV_NAMES)
        self.assertIsInstance(manifest, dict)
        return generated, manifest

    def committed_manifest(self):
        self.load_generator()
        self.assertTrue(
            MANIFEST_PATH.is_file(),
            f"Stage 12 fixture manifest is missing: {MANIFEST_PATH}",
        )
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def scenario_map(self, manifest):
        return {item["id"]: item for item in manifest["scenarios"]}

    def pcm16_samples(self, contents):
        with wave.open(io.BytesIO(contents), "rb") as reader:
            frame_count = reader.getnframes()
            pcm = reader.readframes(frame_count)
        return struct.unpack(f"<{frame_count}h", pcm)

    def run_cli(self, output_dir, *, check=False):
        self.load_generator()
        command = [
            sys.executable,
            str(GENERATOR_PATH),
            "--output-dir",
            str(output_dir),
        ]
        if check:
            command.append("--check")
        return subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def assert_check_fails_without_writing(self, fixture_dir):
        before = {
            path.name: path.read_bytes()
            for path in fixture_dir.iterdir()
            if path.is_file()
        }
        result = self.run_cli(fixture_dir, check=True)
        after = {
            path.name: path.read_bytes()
            for path in fixture_dir.iterdir()
            if path.is_file()
        }
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("why:", result.stderr)
        self.assertIn("remedy:", result.stderr)
        self.assertEqual(after, before)

    def test_scenario_inventory_is_closed(self):
        _, manifest = self.build_corpus()
        self.assertEqual(
            manifest["schema"], "lmdj.provider-benchmark-fixtures.v1"
        )
        self.assertEqual(manifest["capability"], "sample.slice")
        self.assertEqual(
            [item["id"] for item in manifest["scenarios"]], SCENARIO_IDS
        )
        self.assertEqual(
            [item["class"] for item in manifest["scenarios"]],
            [
                "success",
                "success",
                "success",
                "input_failure",
                "input_failure",
                "input_failure",
            ],
        )

    def test_success_ground_truth_uses_exact_frames_and_tolerance(self):
        _, manifest = self.build_corpus()
        observed = {
            item["id"]: (
                item["expected"]["onset_frames"],
                item["expected"]["tolerance_frames"],
            )
            for item in manifest["scenarios"]
            if item["class"] == "success"
        }
        self.assertEqual(
            observed,
            {
                "basic_three_onsets": ([2400, 7200, 12000], 480),
                "close_overlapping_tails": ([480, 1440], 240),
                "silence": ([], 480),
            },
        )

    def test_tolerances_are_positive_and_cannot_match_adjacent_onsets(self):
        _, manifest = self.build_corpus()
        for item in manifest["scenarios"]:
            if item["class"] != "success":
                continue
            onsets = item["expected"]["onset_frames"]
            tolerance = item["expected"]["tolerance_frames"]
            self.assertIs(type(tolerance), int)
            self.assertGreater(tolerance, 0)
            if len(onsets) >= 2:
                minimum_spacing = min(
                    right - left for left, right in zip(onsets, onsets[1:])
                )
                self.assertLess(tolerance, minimum_spacing)

    def test_failure_reasons_are_assigned_to_the_detecting_layer(self):
        _, manifest = self.build_corpus()
        scenarios = self.scenario_map(manifest)
        self.assertEqual(
            scenarios["missing_input"]["expected"],
            {"reason": "input_artifact_unavailable"},
        )
        self.assertEqual(
            scenarios["truncated_data"]["expected"],
            {"reason": "source_audio_unsupported"},
        )
        self.assertEqual(
            scenarios["bad_riff_header"]["expected"],
            {"reason": "source_audio_unsupported"},
        )
        self.assertNotIn("input_artifact_too_large", json.dumps(manifest))

    def test_generated_bytes_match_committed_bytes_and_hashes(self):
        generated, manifest = self.build_corpus()
        canonical_manifest = (
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        self.assertEqual(MANIFEST_PATH.read_bytes(), canonical_manifest)

        for scenario in manifest["scenarios"]:
            path = scenario.get("path")
            if path is None:
                self.assertNotIn("sha256", scenario)
                self.assertNotIn("byte_length", scenario)
                continue
            contents = generated[PurePosixPath(path).name]
            self.assertEqual(
                hashlib.sha256(contents).hexdigest(), scenario["sha256"]
            )
            self.assertEqual(len(contents), scenario["byte_length"])
            self.assertEqual((ROOT / path).read_bytes(), contents)

    def test_success_wavs_are_mono_pcm16_at_48khz(self):
        generated, manifest = self.build_corpus()
        for scenario in manifest["scenarios"]:
            if scenario["class"] != "success":
                continue
            wav_path = PurePosixPath(scenario["path"])
            with tempfile.TemporaryDirectory() as directory:
                temporary_wav = Path(directory) / wav_path.name
                temporary_wav.write_bytes(generated[wav_path.name])
                with wave.open(str(temporary_wav), "rb") as reader:
                    self.assertEqual(reader.getnchannels(), 1)
                    self.assertEqual(reader.getsampwidth(), 2)
                    self.assertEqual(reader.getframerate(), 48_000)
                    self.assertEqual(reader.getcomptype(), "NONE")

    def test_audio_signal_matches_the_declared_onset_ground_truth(self):
        generated, _ = self.build_corpus()
        basic = self.pcm16_samples(generated["slice-basic.wav"])
        self.assertTrue(all(sample == 0 for sample in basic[:2_400]))
        self.assertEqual(
            [basic[2_400], basic[7_200], basic[12_000]],
            [24_000, 24_000, 24_000],
        )

        close = self.pcm16_samples(generated["slice-close-overlap.wav"])
        self.assertTrue(all(sample == 0 for sample in close[:480]))
        self.assertEqual([close[480], close[1_440]], [16_000, 24_000])

        silence = self.pcm16_samples(generated["slice-silence.wav"])
        self.assertEqual(len(silence), 4_800)
        self.assertTrue(all(sample == 0 for sample in silence))

    def test_failure_wavs_are_structurally_invalid_in_the_declared_way(self):
        generated, _ = self.build_corpus()
        truncated = generated["slice-truncated.wav"]
        self.assertEqual(truncated[:4], b"RIFF")
        self.assertEqual(truncated[8:12], b"WAVE")
        self.assertEqual(truncated[36:40], b"data")
        declared_data_bytes = struct.unpack("<I", truncated[40:44])[0]
        self.assertGreater(declared_data_bytes, len(truncated) - 44)

        bad_header = generated["slice-bad-header.wav"]
        self.assertEqual(bad_header[:4], b"NOPE")
        self.assertEqual(bad_header[8:12], b"WAVE")
        with self.assertRaises(wave.Error):
            wave.open(io.BytesIO(bad_header), "rb")

    def test_manifest_paths_are_normalized_repository_relative_posix_paths(self):
        _, manifest = self.build_corpus()
        expected_prefix = PurePosixPath(
            "tests/fixtures/provider-benchmark/sample-slice"
        )
        observed_names = set()
        for scenario in manifest["scenarios"]:
            path = scenario.get("path")
            if path is None:
                continue
            self.assertNotIn("\\", path)
            pure_path = PurePosixPath(path)
            self.assertFalse(pure_path.is_absolute())
            self.assertNotIn("..", pure_path.parts)
            self.assertEqual(pure_path.parent, expected_prefix)
            observed_names.add(pure_path.name)
        self.assertEqual(observed_names, WAV_NAMES)

    def test_generated_material_is_synthetic_and_cc0_only(self):
        _, manifest = self.build_corpus()
        self.assertEqual(manifest["license"]["spdx"], "CC0-1.0")
        self.assertEqual(
            manifest["license"]["canonical_url"],
            "https://creativecommons.org/publicdomain/zero/1.0/",
        )
        self.assertEqual(manifest["license"]["affirmer"], "Zhang Yuancheng")
        self.assertEqual(
            manifest["generator"],
            "tools/provider-benchmark/generate_sample_slice_smoke.py",
        )
        for scenario in manifest["scenarios"]:
            self.assertIsInstance(scenario["generation"], dict)
            if scenario.get("path") is not None:
                self.assertEqual(scenario["origin"], "synthetic")
                self.assertEqual(scenario["spdx_license"], "CC0-1.0")

    def test_cli_check_accepts_exact_corpus_and_license(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory)
            result = self.run_cli(fixture_dir)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            (fixture_dir / "LICENSE.md").write_text(
                "CC0 scope marker for test\n", encoding="utf-8"
            )
            checked = self.run_cli(fixture_dir, check=True)
            self.assertEqual(
                checked.returncode, 0, checked.stdout + checked.stderr
            )

    def test_cli_check_rejects_missing_file_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory)
            self.assertEqual(self.run_cli(fixture_dir).returncode, 0)
            (fixture_dir / "slice-silence.wav").unlink()
            self.assert_check_fails_without_writing(fixture_dir)

    def test_cli_check_rejects_changed_file_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory)
            self.assertEqual(self.run_cli(fixture_dir).returncode, 0)
            changed = fixture_dir / "slice-basic.wav"
            changed.write_bytes(b"changed fixture")
            self.assert_check_fails_without_writing(fixture_dir)

    def test_cli_check_rejects_undeclared_file_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory)
            self.assertEqual(self.run_cli(fixture_dir).returncode, 0)
            (fixture_dir / "undeclared.wav").write_bytes(b"not declared")
            self.assert_check_fails_without_writing(fixture_dir)

    def test_committed_manifest_matches_build_corpus(self):
        _, generated_manifest = self.build_corpus()
        self.assertEqual(self.committed_manifest(), generated_manifest)


if __name__ == "__main__":
    unittest.main()
