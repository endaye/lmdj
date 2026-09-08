"""合成一首 90 BPM 测试曲并预置 stems 缓存，用于跳过 demucs 快速测试阶段 3-6。

用法: python scripts/make_test_song.py output/testsong
"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100
BPM = 90
BEAT = 60 / BPM
BARS = 12


def env(n, attack=0.001, decay=0.15):
    t = np.arange(n) / SR
    return np.minimum(t / attack, 1.0) * np.exp(-t / decay)


def kick():
    n = int(0.25 * SR)
    t = np.arange(n) / SR
    f = 110 * np.exp(-t * 18) + 45
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, decay=0.12)


def snare():
    n = int(0.18 * SR)
    rng = np.random.default_rng(1)
    return (rng.standard_normal(n) * 0.5 +
            np.sin(2 * np.pi * 190 * np.arange(n) / SR)) * env(n, decay=0.07) * 0.7


def hat():
    n = int(0.07 * SR)
    rng = np.random.default_rng(2)
    noise = rng.standard_normal(n)
    hp = np.diff(noise, prepend=0)  # 简易高通
    return hp * env(n, decay=0.025) * 0.5


def tone(freq, dur, harmonic=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * freq * t) + harmonic * 0.3 * np.sin(2 * np.pi * freq * 2 * t)
    e = np.minimum(t / 0.01, 1.0) * np.minimum((dur - t) / 0.05, 1.0).clip(0, 1)
    return y * e


def place(buf, snd, beat_pos):
    s = int(beat_pos * BEAT * SR)
    e = min(s + len(snd), len(buf))
    if e > s:
        buf[s:e] += snd[:e - s]


def main(out_dir: Path):
    n = int(BARS * 4 * BEAT * SR)
    drums, bass, melody = np.zeros(n), np.zeros(n), np.zeros(n)

    k, sn, h = kick(), snare(), hat()
    for bar in range(BARS):
        b = bar * 4
        for pos in (0, 2.5):
            place(drums, k, b + pos)
        for pos in (1, 3):
            place(drums, sn, b + pos)
        for pos in np.arange(0, 4, 0.5):
            place(drums, h, b + pos)

    bass_line = [55.0, 55.0, 41.2, 49.0]  # A1 A1 E1 G1，每小节一个音
    for bar in range(BARS):
        place(bass, tone(bass_line[bar % 4], BEAT * 3.5) * 0.6, bar * 4)

    mel = [220, 261.6, 329.6, 261.6, 196, 220, 246.9, 220]  # 两小节一句
    for bar in range(0, BARS, 2):
        for i, f in enumerate(mel):
            place(melody, tone(f, BEAT * 0.9, harmonic=1.0) * 0.35, bar * 4 + i)

    stems_dir = out_dir / "stems"
    stems_dir.mkdir(parents=True, exist_ok=True)
    for name, mono in [("drums", drums), ("bass", bass), ("melody", melody)]:
        stereo = np.stack([mono, mono], axis=1).astype(np.float32)
        peak = np.abs(stereo).max()
        if peak > 1:
            stereo /= peak
        sf.write(stems_dir / f"{name}.wav", stereo, SR)

    mix = (drums + bass + melody)
    mix /= np.abs(mix).max() * 1.1
    sf.write(out_dir / "input.wav", mix.astype(np.float32), SR)
    print(f"test song ({BPM} bpm, {BARS} bars) -> {out_dir}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "output/testsong"))
