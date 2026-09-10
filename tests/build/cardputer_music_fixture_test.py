#!/usr/bin/env python3
"""Fix the approved music workload; this is not a hardware acceptance test."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "tests/fixtures/cardputer/music_fixture.py"
SPEC = importlib.util.spec_from_file_location("cardputer_music_fixture", GENERATOR)
assert SPEC and SPEC.loader
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)


class MusicFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(GENERATOR.with_suffix(".json").read_text())
        cls.pcm = {(variant, slot): FIXTURE.pcm(variant, slot)
                   for variant in ("A", "B") for slot in range(4)}

    def test_format(self):
        self.assertEqual((self.manifest["sample_rate"], self.manifest["channels"],
                          self.manifest["format"]), (48000, 1, "pcm16le"))

    def test_exact_music_lengths(self):
        for variant in ("A", "B"):
            self.assertEqual([len(self.pcm[variant, slot]) for slot in range(4)],
                             [24000, 24000, 9600, 38400])

    def test_committed_pcm_identity(self):
        for variant in ("A", "B"):
            for slot, sample in enumerate(self.manifest["variants"][variant]["samples"]):
                data = self.pcm[variant, slot]
                self.assertEqual((len(data), hashlib.sha256(data).hexdigest()),
                                 (sample["byte_length"], sample["sha256"]))

    def test_all_sounds_are_distinct(self):
        self.assertEqual(len(set(self.pcm.values())), 8)

    def test_each_sound_has_a_decaying_nonempty_tail(self):
        for data in self.pcm.values():
            values = struct.unpack("<" + "h" * (len(data) // 2), data)
            quarter = len(values) // 4
            early = sum(abs(value) for value in values[:quarter])
            late = sum(abs(value) for value in values[-quarter:])
            self.assertGreater(late, 0)
            self.assertLess(late, early)

    def test_sample_edges_are_zero(self):
        for data in self.pcm.values():
            self.assertEqual(data[:2] + data[-2:], b"\0" * 4)

    def test_pattern_geometry(self):
        self.assertEqual((self.manifest["tempo_bpm"], self.manifest["ppq"],
                          self.manifest["length_ticks"]), (120, 960, 7680))

    def test_exact_pattern_steps(self):
        expected = {0: [0, 8, 16, 24], 1: [4, 12, 20, 28],
                    2: list(range(0, 32, 2)), 3: [3, 7, 11, 15, 19, 23, 27, 31]}
        for variant in ("A", "B"):
            events = FIXTURE.events(variant)
            self.assertEqual(len(events), 32)
            for slot, steps in expected.items():
                self.assertEqual([event["tick"] for event in events if event["pad"] == slot],
                                 [step * 240 for step in steps])

    def test_manifest_matches_complete_generator(self):
        self.assertEqual(self.manifest, FIXTURE.manifest())

    def test_generation_is_repeatable(self):
        for key, data in self.pcm.items():
            self.assertEqual(data, FIXTURE.pcm(*key))

    def test_unknown_variant_or_slot_is_rejected(self):
        for variant, slot in (("C", 0), ("A", -1), ("A", 4)):
            with self.assertRaisesRegex(ValueError, "why:.*remedy:"):
                FIXTURE.pcm(variant, slot)
        with self.assertRaises(ValueError):
            FIXTURE.events("C")

    def test_export_matches_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "fixture"
            result = subprocess.run([sys.executable, str(GENERATOR), "--output", str(destination)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((destination / "music_fixture.json").read_text()),
                             self.manifest)
            for variant in ("A", "B"):
                for slot, sample in enumerate(self.manifest["variants"][variant]["samples"]):
                    self.assertEqual((destination / f"{variant}-{sample['name']}.pcm").read_bytes(),
                                     self.pcm[variant, slot])


if __name__ == "__main__":
    unittest.main(verbosity=2)
