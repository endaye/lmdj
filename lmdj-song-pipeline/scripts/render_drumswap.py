"""鼓替换渲染：ABC render 的 bass+melody 不动，鼓换成指定歌的鼓 one-shot。

原鼓轨只用来提取 onset 落点和 kick/snare/hat 标签（不量化，保留原律动），
替换鼓的整体响度对齐原鼓轨 RMS。

用法: python scripts/render_drumswap.py output/al-johnson-peaceful output/gen_85bpm_42
"""
import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from song_pipeline import audio_utils as au
from song_pipeline.config import PipelineConfig

logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
log = logging.getLogger("drumswap")


def classify_hits(drum_loop: np.ndarray, sr: int) -> list[tuple[float, str]]:
    """规则式鼓击分类：按低/高频段能量占比判 kick/hat/snare（不依赖聚类，
    半小节只有 3 个击点也能用）。"""
    import librosa
    mono = au.to_mono(drum_loop)
    onsets = librosa.onset.onset_detect(y=mono, sr=sr, hop_length=512,
                                        backtrack=True, units="samples")
    hits = []
    win = int(0.08 * sr)
    for s in onsets:
        seg = mono[s:s + win]
        if len(seg) < 256 or np.abs(seg).max() < 1e-3:
            continue
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        freqs = np.fft.rfftfreq(len(seg), 1 / sr)
        total = spec.sum() + 1e-9
        low = spec[freqs < 150].sum() / total
        high = spec[freqs >= 4000].sum() / total
        if low > 0.25:
            label = "kick"
        elif high > 0.35:
            label = "hat"
        else:
            label = "snare"
        hits.append((s / sr, label))
    return hits


def main(song_dir: Path, drum_src_dir: Path):
    cfg = PipelineConfig()
    sr = cfg.sample_rate
    report = json.loads((song_dir / "report.json").read_text())
    assert report.get("mode") == "abc", "需要 ABC 模式的输出"
    bar = 4 * 60 / report["bpm"]

    stems = {k: au.load_wav(song_dir / "stems" / f"{k}.wav", sr)[0]
             for k in ("drums", "bass", "melody")}
    bassmel = stems["bass"] + stems["melody"]

    shots = {k: au.load_wav(drum_src_dir / "samples" / f"{k}.wav", sr)[0]
             for k in ("kick", "snare", "hat")}
    log.info("替换鼓源: %s (kick/snare/hat)", drum_src_dir)

    fade = int(cfg.crossfade_ms / 1000 * sr)
    loops = {}
    for name in ("a", "b", "c"):
        w = report["windows"][name]
        s, e = int(w["start"] * sr), int((w["start"] + w["seconds"]) * sr)
        seg = bassmel[s:min(e + fade, len(bassmel))].copy()
        loops[name] = au.crossfade_loop(seg, fade) if len(seg) > e - s else seg
        drum_loop = stems["drums"][s:e].copy()
        hits = classify_hits(drum_loop, sr)
        loops[name + "_hits"] = hits
        log.info("loop_%s: %d 个鼓击点 %s", name, len(hits),
                 [h[1] for h in hits])

    # A-A-A-BC 时间线
    placements = [("a", 0.0), ("a", bar), ("a", 2 * bar),
                  ("b", 3 * bar), ("c", 3.5 * bar)]
    total = int(4 * bar * sr) + sr
    ch = bassmel.shape[1]
    music = np.zeros((total, ch), dtype=np.float32)
    drums_new = np.zeros((total, ch), dtype=np.float32)
    drums_ref = np.zeros((total, ch), dtype=np.float32)

    for name, t0 in placements:
        s = int(t0 * sr)
        seg = loops[name]
        music[s:s + len(seg)] += seg
        w = report["windows"][name]
        src = int(w["start"] * sr)
        n = int(w["seconds"] * sr)
        drums_ref[s:s + n] += stems["drums"][src:src + n]
        for t, label in loops[name + "_hits"]:
            shot = shots[label]
            p = s + int(t * sr)
            q = min(p + len(shot), total)
            drums_new[p:q] += shot[:q - p]

    # 替换鼓响度对齐原鼓轨
    gain = float(np.sqrt((drums_ref ** 2).mean() / ((drums_new ** 2).mean() + 1e-12)))
    gain = min(gain, 4.0)
    log.info("鼓增益 %.2fx", gain)

    out = music + drums_new * gain
    n_out = int(4 * bar * sr)
    au.write_wav(song_dir / "render_drumswap.wav", out[:n_out], sr)
    log.info("-> %s (%.1fs)", song_dir / "render_drumswap.wav", n_out / sr)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
