"""复用已有一组 loop（如 jkl），把鼓换成最基本的 boom bap 写法，
存成一个新 render（不重新切 loop）。

basic boom bap（每完整小节，16 分网格）：
  kick  落 1、3 拍            slot 0, 8
  snare 落 2、4 拍（backbeat）slot 4, 12
  hat   八分音符              slot 0,2,4,6,8,10,12,14（拍点上略响）
半小节取前 8 格的对应部分。

用法: python scripts/rerender_boombap.py output/al-johnson-peaceful jkl bb
"""
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pretty_midi

sys.path.insert(0, str(Path(__file__).parent.parent))

from song_pipeline import audio_utils as au
from song_pipeline.config import PipelineConfig
from song_pipeline.slicer import classify_hits, cut_oneshots_by_label

logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
log = logging.getLogger("boombap")


def boombap_bar(n_slots, step, swing=0.0, ghost_kick=False):
    """返回 [(t_秒, label, gain)]，t 是小节内偏移。n_slots=16 整小节，8 半小节。

    swing: 反拍八分 hat 往后挪 swing×16分（0=直，0.5=明显摇摆）
    ghost_kick: 整小节时在 3 拍后半（beat 3.5）加一发切分 kick
    """
    beat = n_slots // 4               # 一拍 = 4 个 16 分
    kicks = [(0, 1.0), (2 * beat, 1.0)]                       # 1、3 拍
    if ghost_kick and n_slots >= 16:
        kicks.append((2 * beat + 2, 0.8))                    # beat 3.5 切分
    snares = [(beat, 1.0), (3 * beat, 1.0)]                  # 2、4 拍
    out = [(s * step, "kick", g) for s, g in kicks if s < n_slots]
    out += [(s * step, "snare", g) for s, g in snares if s < n_slots]
    for s in range(0, n_slots, 2):                           # 八分 hat
        on_beat = s % beat == 0
        t = s * step + (0.0 if on_beat else swing * step)    # 反拍加 swing
        out.append((t, "hat", 0.65 if on_beat else 0.5))
    return out


def recut_drums(song_dir: Path, loop_names: list[str], cfg) -> None:
    """从 src 这组 loop 对应的鼓轨窗口重切 kick/snare/hat，覆盖 samples。"""
    sr = cfg.sample_rate
    side = json.loads((song_dir / "loop_windows.json").read_text())
    wins = {w["name"]: w for w in side}
    drums = au.load_wav(song_dir / "stems" / "drums.wav", sr)[0]
    all_hits = []
    for n in loop_names:
        w = wins[n]
        s, e = int(w["start"] * sr), int(w["end"] * sr)
        all_hits += [(w["start"] + t, l)
                     for t, l in classify_hits(drums[s:e], sr)]
    shots = cut_oneshots_by_label(drums, sr, all_hits, cfg)
    for label, shot in shots.items():
        au.write_wav(song_dir / "samples" / f"{label}.wav", shot, sr)
    log.info("重切鼓 one-shot: %s",
             {k: round(len(shots[k]) / sr, 3) for k in shots})


def fill_half_bar(n_slots, step, swing):
    """第四小节后半的 fill（半小节）：下拍 kick + 点缀 hat + 后半拍 snare 16 分
    roll 渐强收尾，把段落推向下一轮。比单纯重复 kick-snare 有起伏。"""
    beat = n_slots // 4                                   # =2（半小节 2 拍）
    out = [(0.0, "kick", 1.0)]                            # 下拍 kick
    out.append((0.0, "hat", 0.55))                        # 拍头 hat
    out.append((beat * step + swing * step, "hat", 0.4))  # off-beat hat（swing）
    roll = [2 * beat, 2 * beat + 1, 2 * beat + 2, 2 * beat + 3]  # 末拍 4 个 16 分
    gains = [0.45, 0.6, 0.8, 1.0]                          # 渐强
    out += [(s * step, "snare", g) for s, g in zip(roll, gains) if s < n_slots]
    return out


def main(song_dir: Path, src_tag: str, out_tag: str, recut: bool = True,
         swing: float = 0.0, ghost_kick: bool = False):
    cfg = PipelineConfig()
    sr = cfg.sample_rate
    lanes = json.loads((song_dir / f"lanes{src_tag}.json").read_text())
    bpm = lanes["bpm"]
    bar = 4 * 60 / bpm
    step = bar / 16

    names = [l["name"] for l in lanes["lanes"]]
    loop_names = [n for n in names if n.startswith("loop_")]  # [大, 前半, 后半]
    if recut:
        recut_drums(song_dir, loop_names, cfg)
    samples = {l["name"]: au.load_wav(song_dir / l["sample"], sr)[0]
               for l in lanes["lanes"]}
    pitch = {n: cfg.lane_pitches[n] for n in samples}
    ch = max(s.shape[1] for s in samples.values())

    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    inst = pretty_midi.Instrument(program=0, name="lmdj-boombap")

    def note(name, t, dur, gain=1.0):
        inst.notes.append(pretty_midi.Note(
            velocity=max(1, int(round(gain * 100))), pitch=pitch[name],
            start=t, end=t + dur))

    big, half_a, half_b = loop_names           # 1小节 / 前半 / 后半
    for i in range(3):                         # 前三小节：大 loop + boom bap
        note(big, i * bar, bar)
        for t, label, g in boombap_bar(16, step, swing, ghost_kick):
            note(label, i * bar + t, 0.1, g)
    # 第四小节：前半正常 groove，后半做 fill 收尾
    note(half_a, 3 * bar, bar / 2)
    note(half_b, 3.5 * bar, bar / 2)
    for t, label, g in boombap_bar(8, step, swing, ghost_kick):  # 前半
        note(label, 3 * bar + t, 0.1, g)
    for t, label, g in fill_half_bar(8, step, swing):            # 后半 fill
        note(label, 3.5 * bar + t, 0.1, g)

    pm.instruments.append(inst)
    chart_path = song_dir / f"chart{out_tag}.mid"
    pm.write(str(chart_path))
    drums = sum(1 for n in inst.notes if n.pitch in
                (pitch["kick"], pitch["snare"], pitch["hat"]))
    log.info("%s: %d notes（loop 5 + boom bap 鼓 %d）",
             chart_path.name, len(inst.notes), drums)

    # render：从 chart 回放
    p2n = {p: n for n, p in pitch.items()}
    total = int(4 * bar * sr) + sr
    buf = np.zeros((total, ch), dtype=np.float32)
    for n in pretty_midi.PrettyMIDI(str(chart_path)).instruments[0].notes:
        seg = samples[p2n[n.pitch]] * (n.velocity / 100)
        p = int(n.start * sr)
        q = min(p + len(seg), total)
        buf[p:q] += seg[:q - p]
    render_path = song_dir / f"render{out_tag}.wav"
    au.write_wav(render_path, buf[:int(4 * bar * sr)], sr)
    log.info("-> %s（复用 %s 的 loop，boom bap 鼓）", render_path.name, src_tag)


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2],
         sys.argv[3] if len(sys.argv) > 3 else "bb")
