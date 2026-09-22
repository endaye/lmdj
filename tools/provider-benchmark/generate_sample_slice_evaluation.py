#!/usr/bin/env python3
"""Reproduce S3 integer PCM fixtures; truth is the authored pulse schedule."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
PREFIX = 'tests/fixtures/provider-benchmark/sample-slice-evaluation'


def specifications():
    rows = []

    def add(name, onsets, peak=24000, tail=120, rate=48000, channels=1):
        rows.append(dict(id=name, sample_rate=rate, channels=channels,
                         frame_count=4800, onset_frames=onsets, peak=peak,
                         tail_frames=tail, channel=channels - 1))

    for label, peak in [('below', 4095), ('at', 4096), ('high', 24000)]:
        add('velocity-' + label, [480, 1440, 2400], peak=peak)
    add('tail-separated', [480, 1440], tail=720)
    add('tail-overlap', [480, 1440], tail=1920)
    add('dense-below', [480, 719, 958], tail=48)
    add('dense-at', [480, 720, 960], tail=48)
    add('mono-44100', [441, 1323, 2205], rate=44100)
    add('stereo-right-44100', [441, 1323, 2205], rate=44100, channels=2)
    add('stereo-right-48000', [480, 1440, 2400], channels=2)
    add('silence-stereo', [], channels=2)
    return rows


def render(spec):
    samples = [0] * (spec['frame_count'] * spec['channels'])
    for onset in spec['onset_frames']:
        for offset in range(min(spec['tail_frames'], spec['frame_count'] - onset)):
            amplitude = spec['peak'] * (spec['tail_frames'] - offset) // spec['tail_frames']
            # Integer square carrier; no platform libm or RNG dependency.
            amplitude *= 1 if (offset // 16) % 2 == 0 else -1
            index = (onset + offset) * spec['channels'] + spec['channel']
            samples[index] += amplitude
    pcm = struct.pack('<' + 'h' * len(samples), *(max(-32768, min(32767, n)) for n in samples))
    block = spec['channels'] * 2
    fmt = struct.pack('<HHIIHH', 1, spec['channels'], spec['sample_rate'],
                      spec['sample_rate'] * block, block, 16)
    body = b'WAVEfmt ' + struct.pack('<I', len(fmt)) + fmt + b'data' + struct.pack('<I', len(pcm)) + pcm
    return b'RIFF' + struct.pack('<I', len(body)) + body


def corpus():
    files, scenarios = {}, []
    for spec in specifications():
        name = spec['id'] + '.wav'
        raw = render(spec)
        files[name] = raw
        scenarios.append(dict(id=spec['id'], **{'class': 'success'}, path=f'{PREFIX}/{name}',
                              sha256=hashlib.sha256(raw).hexdigest(), byte_length=len(raw),
                              origin='synthetic', spdx_license='CC0-1.0',
                              sample_rate=spec['sample_rate'], channels=spec['channels'],
                              expected=dict(onset_frames=spec['onset_frames'], tolerance_frames=0),
                              generation={k: v for k, v in spec.items() if k != 'id'}))
    manifest = dict(schema='lmdj.provider-benchmark-fixtures.v1', capability='sample.slice',
                    generator='tools/provider-benchmark/generate_sample_slice_evaluation.py',
                    license=dict(spdx='CC0-1.0', affirmer='Zhang Yuancheng',
                                 canonical_url='https://creativecommons.org/publicdomain/zero/1.0/',
                                 scope='generated WAV files and manifest.json in this directory only'),
                    scenarios=scenarios)
    files['manifest.json'] = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
    return files


def generate(directory, check=False):
    files = corpus()
    if check:
        actual = {p.name for p in directory.iterdir()}
        if actual - (set(files) | {'LICENSE.md'}):
            raise ValueError('undeclared fixture files')
        for name, data in files.items():
            if (directory / name).read_bytes() != data:
                raise ValueError(f'{name}: regeneration differs')
    else:
        directory.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            (directory / name).write_bytes(data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / PREFIX)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    generate(args.output_dir, args.check)
