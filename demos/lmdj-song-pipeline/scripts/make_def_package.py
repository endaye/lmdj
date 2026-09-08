"""DEF 出包：同一首歌切 3 个无鼓 loop（D=1小节 E/F=半小节，bass+melody），
鼓单独切 kick/snare/hat one-shot，chart.mid 同时触发 loop 和鼓
（鼓 pattern 按既定变奏规则、全部落 16 分网格），
render_preview 由 chart.mid 真实回放生成。

共 6 个 samples：loop_d/e/f + kick/snare/hat。

用法: python scripts/make_def_package.py output/al-johnson-peaceful [seed]
"""
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pretty_midi

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from render_drumvar import build_a_bar, build_bar4_half

from song_pipeline import audio_utils as au
from song_pipeline import loop_finder
from song_pipeline.config import PipelineConfig
from song_pipeline.slicer import classify_hits, cut_oneshots_by_label

logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
log = logging.getLogger("def")


def overlaps(w, taken):
    return any(w.start < t_end and w.end > t_start for t_start, t_end in taken)


def main(song_dir: Path, seed: int = 2, letters=("d", "e", "f"), tag: str = ""):
    cfg = PipelineConfig()
    sr = cfg.sample_rate
    rng = np.random.default_rng(seed)
    report = json.loads((song_dir / "report.json").read_text())
    bar = 4 * 60 / report["bpm"]
    step = bar / 16
    lname = [f"loop_{c}" for c in letters]
    pat = "-".join(c.upper() for c in letters[:1] * 3) + "-" + \
          "".join(c.upper() for c in letters[1:])

    stems = {k: au.load_wav(song_dir / "stems" / f"{k}.wav", sr)[0]
             for k in ("drums", "bass", "melody")}
    bassmel = stems["bass"] + stems["melody"]
    bassmel_mono = au.to_mono(bassmel)
    mix_mono = bassmel_mono + au.to_mono(stems["drums"])
    stems_mono = {k: au.to_mono(v) for k, v in stems.items()}

    # 拍点用全曲 mix 检测（鼓参与 downbeat 投票），窗口打分用无鼓信号
    pre = loop_finder.detect_beats(mix_mono, stems_mono, sr, cfg)
    # 避让：report 里 A/B/C + sidecar 里之前切过的所有 loop 窗口
    taken = [(w["start"], w["start"] + w["seconds"])
             for w in report.get("windows", {}).values()]
    side = song_dir / "loop_windows.json"
    prev = json.loads(side.read_text()) if side.exists() else []
    taken += [(w["start"], w["end"]) for w in prev]

    def pick(n_beats, phase):
        for w in loop_finder.find_loop_windows(
                bassmel_mono, stems_mono, sr, cfg,
                n_beats=n_beats, start_phase=phase, precomputed=pre):
            if not overlaps(w, taken):
                taken.append((w.start, w.end))
                return w
        raise RuntimeError("没有可用窗口（候选都与已切 loop 重叠）")

    bpb = cfg.beats_per_bar
    win = {lname[0]: pick(bpb, 0),          # 1 小节
           lname[1]: pick(bpb // 2, 0),     # 前半小节
           lname[2]: pick(bpb // 2, bpb // 2)}  # 后半小节
    prev += [{"name": n, "start": w.start, "end": w.end} for n, w in win.items()]
    side.write_text(json.dumps(prev, indent=2))

    samples = {}
    for name, w in win.items():
        samples[name] = loop_finder.cut_loop(bassmel, sr, w, cfg)  # 无鼓
        au.write_wav(song_dir / "samples" / f"{name}.wav", samples[name], sr)
        log.info("%s @ %.2fs %.3fs score=%.3f（bass+melody）",
                 name, w.start, w.end - w.start, w.score)

    # 鼓 one-shot：从 D/E/F 窗口的鼓轨里选最干净一发
    all_hits = []
    for w in win.values():
        s, e = int(w.start * sr), int(w.end * sr)
        all_hits += [(w.start + t, l)
                     for t, l in classify_hits(stems["drums"][s:e], sr)]
    shots = cut_oneshots_by_label(stems["drums"], sr, all_hits, cfg)
    for label, shot in shots.items():
        samples[label] = shot
        au.write_wav(song_dir / "samples" / f"{label}.wav", shot, sr)
    log.info("鼓 one-shot: %s", {k: round(len(shots[k]) / sr, 3) for k in shots})

    # 鼓 pattern：D 窗口的原 pattern 为底，按既定变奏规则（全落 16 分网格）
    def hits_at(w):
        s, e = int(w.start * sr), int(w.end * sr)
        return classify_hits(stems["drums"][s:e], sr)

    d_dur = win[lname[0]].end - win[lname[0]].start
    h_dur = win[lname[1]].end - win[lname[1]].start
    drum_bars = [build_a_bar(hits_at(win[lname[0]]), d_dur, step, rng, n)
                 for n in (0, 1, 2)]
    drum_b4 = [build_bar4_half(hits_at(win[lname[1]]), h_dur, step, rng, False),
               build_bar4_half(hits_at(win[lname[2]]), h_dur, step, rng, True)]

    # chart.mid：loop 触发 + 鼓触发，velocity 携带力度
    pm = pretty_midi.PrettyMIDI(initial_tempo=report["bpm"])
    inst = pretty_midi.Instrument(program=0, name="lmdj-def")

    def note(pitch, t, dur, gain=1.0):
        inst.notes.append(pretty_midi.Note(
            velocity=max(1, int(round(gain * 100))), pitch=pitch,
            start=t, end=t + dur))

    for i in range(3):                                   # 前三小节
        note(cfg.lane_pitches[lname[0]], i * bar, bar)
        for t, label, g in drum_bars[i]:
            note(cfg.lane_pitches[label], i * bar + t, 0.1, g)
    note(cfg.lane_pitches[lname[1]], 3 * bar, bar / 2)   # 第 4 小节前/后半
    note(cfg.lane_pitches[lname[2]], 3.5 * bar, bar / 2)
    for half, t0 in zip(drum_b4, (3 * bar, 3.5 * bar)):
        for t, label, g in half:
            note(cfg.lane_pitches[label], t0 + t, 0.1, g)

    pm.instruments.append(inst)
    chart_path = song_dir / f"chart{tag}.mid"
    pm.write(str(chart_path))
    log.info("%s: %d notes（loop 5 + 鼓 %d）", chart_path.name, len(inst.notes),
             len(inst.notes) - 5)

    lanes = {
        "bpm": report["bpm"], "pattern": pat, "bars": 4,
        "loop_seconds": round(4 * bar, 4),
        "lanes": [{"lane": i, "name": n, "kind": k,
                   "pitch": cfg.lane_pitches[n], "sample": f"samples/{n}.wav"}
                  for i, (n, k) in enumerate(
                      [(lname[0], "loop"), (lname[1], "loop"),
                       (lname[2], "loop"), ("kick", "drum"),
                       ("snare", "drum"), ("hat", "drum")])],
    }
    (song_dir / f"lanes{tag}.json").write_text(
        json.dumps(lanes, indent=2, ensure_ascii=False))

    # render：从 chart.mid 真实回放（pitch → sample，velocity → 增益）
    pitch_to_name = {cfg.lane_pitches[n]: n for n in samples}
    chart = pretty_midi.PrettyMIDI(str(chart_path))
    total = int(4 * bar * sr) + sr
    buf = np.zeros((total, bassmel.shape[1]), dtype=np.float32)
    for n in chart.instruments[0].notes:
        seg = samples[pitch_to_name[n.pitch]] * (n.velocity / 100)
        p = int(n.start * sr)
        q = min(p + len(seg), total)
        buf[p:q] += seg[:q - p]
    render_path = song_dir / f"render{tag}.wav"
    au.write_wav(render_path, buf[:int(4 * bar * sr)], sr)
    log.info("-> %s（由 %s 回放生成）", render_path.name, chart_path.name)


if __name__ == "__main__":
    # 用法: make_def_package.py <song_dir> [seed] [letters如ghi] [tag]
    args = sys.argv[1:]
    song = Path(args[0])
    seed = int(args[1]) if len(args) > 1 else 2
    letters = tuple(args[2]) if len(args) > 2 else ("d", "e", "f")
    tag = args[3] if len(args) > 3 else ""
    main(song, seed, letters, tag)
