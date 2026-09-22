#!/usr/bin/env python3
"""S3 fixture truth/reproduction and emitted-byte collector boundaries."""
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generate_sample_slice_evaluation as g
import run_sample_slice_evaluation as r


class CorpusTests(unittest.TestCase):
    def test_retained_bytes_regenerate(self):
        g.generate(g.ROOT / g.PREFIX, check=True)

    def test_reproduction_is_directory_independent(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            g.generate(p / 'a'); g.generate(p / 'b')
            self.assertEqual({f.name: f.read_bytes() for f in (p / 'a').iterdir()},
                             {f.name: f.read_bytes() for f in (p / 'b').iterdir()})

    def test_changed_wav_refused_without_repair(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder); g.generate(p)
            target = p / 'velocity-high.wav'
            changed = target.read_bytes()[:-1] + b'x'; target.write_bytes(changed)
            with self.assertRaisesRegex(ValueError, 'regeneration differs'):
                g.generate(p, check=True)
            self.assertEqual(target.read_bytes(), changed)

    def test_undeclared_file_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder); g.generate(p); (p / 'extra.wav').write_bytes(b'')
            with self.assertRaisesRegex(ValueError, 'undeclared'):
                g.generate(p, check=True)

    def test_velocity_truth_and_threshold_bracket(self):
        files = g.corpus()
        for name, peak in [('below', 4095), ('at', 4096), ('high', 24000)]:
            with self.subTest(name=name), wave.open(io.BytesIO(files[f'velocity-{name}.wav'])) as wav:
                samples = struct.unpack('<4800h', wav.readframes(4800))
                self.assertEqual([samples[i] for i in (480, 1440, 2400)], [peak] * 3)
                self.assertEqual([samples[i - 1] for i in (480, 1440, 2400)], [0] * 3)
        manifest = json.loads(files['manifest.json'])
        self.assertTrue(all(s['expected'] == dict(onset_frames=[480, 1440, 2400], tolerance_frames=0)
                            for s in manifest['scenarios'] if s['id'].startswith('velocity-')))

    def test_dense_truth_straddles_refractory(self):
        specs = {s['id']: s for s in g.specifications()}
        self.assertEqual(specs['dense-below']['onset_frames'], [480, 719, 958])
        self.assertEqual(specs['dense-at']['onset_frames'], [480, 720, 960])

    def test_overlap_changes_tail_not_truth(self):
        specs = {s['id']: s for s in g.specifications()}
        self.assertEqual(specs['tail-separated']['onset_frames'], [480, 1440])
        self.assertEqual(specs['tail-overlap']['onset_frames'], [480, 1440])
        for name, previous_nonzero in [('tail-separated', False), ('tail-overlap', True)]:
            with wave.open(io.BytesIO(g.render(specs[name]))) as wav:
                samples = struct.unpack('<4800h', wav.readframes(4800))
                self.assertEqual(samples[1439] != 0, previous_nonzero)

    def test_stereo_right_and_supported_rates(self):
        for rate in (44100, 48000):
            raw = g.corpus()[f'stereo-right-{rate}.wav']
            with wave.open(io.BytesIO(raw)) as wav:
                self.assertEqual((wav.getframerate(), wav.getnchannels()), (rate, 2))
                samples = struct.unpack('<9600h', wav.readframes(4800))
                self.assertEqual(set(samples[::2]), {0})
                self.assertEqual(samples[(441 if rate == 44100 else 480) * 2 + 1], 24000)

    def test_silence_has_no_truth_or_signal(self):
        with wave.open(io.BytesIO(g.corpus()['silence-stereo.wav'])) as wav:
            self.assertEqual(set(wav.readframes(4800)), {0})
        scenario = next(s for s in json.loads(g.corpus()['manifest.json'])['scenarios'] if s['id'] == 'silence-stereo')
        self.assertEqual(scenario['expected']['onset_frames'], [])


class CollectorTests(unittest.TestCase):
    def setUp(self):
        # Deliberately synthetic collector unit input, never a measured report.
        self.manifest = json.loads(g.corpus()['manifest.json'])
        self.manifest['scenarios'] = self.manifest['scenarios'][:1]
        case = self.manifest['scenarios'][0]
        emitted = json.dumps(dict(contract='lmdj.slice-points.v1', source_sha256=case['sha256'], frame_rate=48000, points=[]))
        run = dict(elapsed_seconds=.2, output_bytes=emitted, output_sha256=hashlib.sha256(emitted.encode()).hexdigest(),
                   output_byte_length=len(emitted), frame_count=4800, sample_rate=48000, persisted_status='succeeded')
        self.raw = dict(manifest_sha256='a' * 64, parameters={}, cases=[dict(fixture_id=case['id'], runs=[run, copy.deepcopy(run)])])

    def test_predictions_use_output_not_truth(self):
        result = r.predictions(self.manifest, 'a' * 64, self.raw)
        self.assertEqual(result['cases'][0]['frames'], [])
        self.assertEqual(self.raw['cases'][0]['runs'][0]['real_time_factor'], 2)

    def test_changed_output_bytes_refused(self):
        self.raw['cases'][0]['runs'][0]['output_bytes'] += ' '
        with self.assertRaisesRegex(ValueError, 'output byte identity'):
            r.predictions(self.manifest, 'a' * 64, self.raw)

    def test_missing_repeat_refused(self):
        self.raw['cases'][0]['runs'].pop()
        with self.assertRaisesRegex(ValueError, 'two real executions'):
            r.predictions(self.manifest, 'a' * 64, self.raw)

    def test_source_duration_mismatch_refused(self):
        self.raw['cases'][0]['runs'][0]['frame_count'] = 1
        with self.assertRaisesRegex(ValueError, 'duration differs'):
            r.predictions(self.manifest, 'a' * 64, self.raw)

    def test_repeat_byte_difference_is_rejected(self):
        self.raw['cases'][0]['runs'][1].update(output_bytes='different', output_sha256='b' * 64)
        scores = dict(cases=[dict(fixture_id='velocity-below', tp=0, fp=0, fn=3,
                                 precision=None, recall=0, f1=0)])
        case = r.make_cases(self.manifest, 'a' * 64, self.raw, scores)[0]
        self.assertEqual(case['status'], 'rejected')
        self.assertEqual(case['rejection_reasons'], ['determinism_violation'])

    def test_quality_misses_are_preserved_without_production_qualification(self):
        scores = dict(cases=[dict(fixture_id='velocity-below', tp=0, fp=0, fn=3,
                                 precision=None, recall=0, f1=0)])
        case = r.make_cases(self.manifest, 'a' * 64, self.raw, scores)[0]
        self.assertEqual(case['status'], 'observation_only')
        metrics = {m['metric']: m for m in case['measurements']}
        self.assertEqual(metrics['fn']['value'], 3)
        self.assertEqual(metrics['precision']['status'], 'not_applicable')
        self.assertEqual(metrics['peak_process_tree_rss']['status'], 'not_enforceable')


if __name__ == '__main__':
    unittest.main()
