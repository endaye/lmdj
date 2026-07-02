"""鼓变奏渲染：bass+melody 按 A-A-A-BC 走带不动，鼓用原唱片自己的
kick/snare/hat one-shot 重新演奏——以原 pattern 为底，每次重复做轻量变异：

  rep1(A) 原样 | rep2(A) 加 offbeat hat + ghost snare | rep3(A) 减一发 hat 加一发 hat
  B 原样 | C 结尾 snare 双击 fill

不变的：kick 的小节头、snare 的反拍（2/4 拍）位置永不动。

用法: python scripts/render_drumvar.py output/al-johnson-peaceful [seed]
"""
import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from song_pipeline import audio_utils as au
from song_pipeline.config import PipelineConfig
from song_pipeline.slicer import classify_hits, cut_oneshots_by_label

logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
log = logging.getLogger("drumvar")


def _quantize(hits, step, n_slots):
    """onset 时间 → 16 分 slot（去重，同 slot 同标签只留一发）。"""
    slots = {}
    for t, l in hits:
        s = min(round(t / step), n_slots - 1)
        slots[(s, l)] = 1.0
    return slots


def build_a_bar(hits, dur, step, rng, n_extra_kicks):
    """前三小节（A）的 groove 模板 + kick 变奏。所有鼓击严格落在 16 分网格。

    - kick 开第一拍（原 pattern 没有就补上）
    - snare 锁死 2、4 拍
    - hat 保持原样（量化到 16 分）
    - 变奏只发生在 kick：可以增多（n_extra_kicks 发，落在空 16 分上）
    """
    n_slots = int(round(dur / step))
    backbeats = (round(n_slots / 4), round(3 * n_slots / 4))  # 2、4 拍
    q = _quantize(hits, step, n_slots)

    slots = {(s, l): g for (s, l), g in q.items() if l == "hat"}
    kicks = {s for (s, l) in q if l == "kick"} | {0}     # kick 开第一拍
    slots.update({(s, "kick"): 1.0 for s in kicks})
    slots.update({(b, "snare"): 1.0 for b in backbeats})

    occupied = {s for (s, _) in slots}
    for _ in range(n_extra_kicks):
        # 离已有 kick 至少 2 个 16 分，避免连续 kick 卡壳感
        free = [s for s in range(1, n_slots) if s not in occupied
                and all(abs(s - k) >= 2 for k in kicks)]
        if not free:
            break
        s = int(rng.choice(free))
        kicks.add(s)
        occupied.add(s)
        slots[(s, "kick")] = 0.85
    return sorted((s * step, l, g) for (s, l), g in slots.items())


def build_bar4_half(hits, dur, step, rng, is_c):
    """第四小节（B/C 半小节）：snare 位置可变，C 结尾加 fill。全部落网格。"""
    n_slots = int(round(dur / step))
    q = _quantize(hits, step, n_slots)
    occupied = {s for (s, _) in q}
    hat_slots = {s for (s, l) in q if l == "hat"}

    slots = {}
    dropped: set = set()
    for (s, l), g in sorted(q.items()):
        if (s, l) in dropped:
            continue
        if l == "snare" and rng.random() < 0.6:      # snare 挪位，可顶掉 hat
            cand = [c for c in (s - 1, s + 1, s + 2)
                    if 0 < c < n_slots and (c not in occupied or c in hat_slots)]
            if cand:
                c = int(rng.choice(cand))
                occupied.add(c)
                dropped.add((c, "hat"))
                slots.pop((c, "hat"), None)
                slots[(c, "snare")] = 1.0
                continue
        slots[(s, l)] = g
    if is_c:                                          # 结尾 snare fill
        tail = [s for s in (n_slots - 2, n_slots - 1) if s not in occupied]
        if tail:
            slots[(int(rng.choice(tail)), "snare")] = 0.8
    return sorted((s * step, l, g) for (s, l), g in slots.items())


def main(song_dir: Path, seed: int = 7):
    cfg = PipelineConfig()
    sr = cfg.sample_rate
    rng = np.random.default_rng(seed)
    report = json.loads((song_dir / "report.json").read_text())
    assert report.get("mode") == "abc"
    bar = 4 * 60 / report["bpm"]
    step = bar / 16  # 16 分音符

    stems = {k: au.load_wav(song_dir / "stems" / f"{k}.wav", sr)[0]
             for k in ("drums", "bass", "melody")}
    bassmel = stems["bass"] + stems["melody"]

    fade = int(cfg.crossfade_ms / 1000 * sr)
    loops, all_hits = {}, []
    for name in ("a", "b", "c"):
        w = report["windows"][name]
        s, e = int(w["start"] * sr), int((w["start"] + w["seconds"]) * sr)
        seg = bassmel[s:min(e + fade, len(bassmel))].copy()
        loops[name] = au.crossfade_loop(seg, fade) if len(seg) > e - s else seg
        hits = classify_hits(stems["drums"][s:e], sr)
        loops[name + "_hits"] = hits
        all_hits += [(w["start"] + t, l) for t, l in hits]

    # one-shot 从整段鼓轨里按标签选最干净一发（音色 = 原唱片）
    shots = cut_oneshots_by_label(stems["drums"], sr, all_hits, cfg)
    log.info("原鼓 one-shot: %s", {k: round(len(v) / sr, 3) for k, v in shots.items()})

    # 前三小节 A：kick 开第一拍 + snare 锁 2/4，kick 逐次增多 0/1/2 发
    # 第四小节 B/C：snare 可挪位，C 收 fill
    placements = [("a", 0.0, ("a", 0)), ("a", bar, ("a", 1)), ("a", 2 * bar, ("a", 2)),
                  ("b", 3 * bar, ("b4", False)), ("c", 3.5 * bar, ("b4", True))]
    total = int(4 * bar * sr) + sr
    buf = np.zeros((total, bassmel.shape[1]), dtype=np.float32)

    for name, t0, (kind, arg) in placements:
        s = int(t0 * sr)
        seg = loops[name]
        buf[s:s + len(seg)] += seg
        dur = report["windows"][name]["seconds"]
        if kind == "a":
            varied = build_a_bar(loops[name + "_hits"], dur, step, rng, arg)
        else:
            varied = build_bar4_half(loops[name + "_hits"], dur, step, rng, arg)
        log.info("%-2s @%4.1fs: %s", name, t0,
                 " ".join(f"{l}@{round(t / step)}{'·' if g < 1 else ''}"
                          for t, l, g in varied))
        for t, label, gain in varied:
            if label not in shots:
                continue
            shot = shots[label] * gain
            p = s + int(t * sr)
            q = min(p + len(shot), total)
            buf[p:q] += shot[:q - p]

    n_out = int(4 * bar * sr)
    au.write_wav(song_dir / "render_preview.wav", buf[:n_out], sr)
    log.info("-> %s (%.1fs)", song_dir / "render_preview.wav", n_out / sr)


if __name__ == "__main__":
    main(Path(sys.argv[1]),
         int(sys.argv[2]) if len(sys.argv) > 2 else 7)
