"""管线编排：分轨 → 截loop → 切片 → MIDI → 验收（不达标自动换窗口重试）。"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np

from . import audio_utils as au
from . import loop_finder, sequencer, slicer, stems, validate
from .config import PipelineConfig

log = logging.getLogger(__name__)


def run_pipeline_abc(input_path: Path, out_root: Path, song_id: str,
                     cfg: PipelineConfig | None = None) -> dict:
    """ABC loop 模式：切 3 个 loop——A(1小节) B(前半小节) C(后半小节)，
    谱面按 A-A-A-BC 走完 4 小节。"""
    cfg = cfg or PipelineConfig()
    t0 = time.time()
    out_dir = out_root / song_id
    out_dir.mkdir(parents=True, exist_ok=True)
    sr = cfg.sample_rate

    stem_paths = stems.separate(Path(input_path), out_dir, cfg)
    stem_audio = {k: au.load_wav(p, sr)[0] for k, p in stem_paths.items()}
    mix = sum(stem_audio.values())                       # 立体声全曲（分轨重和）
    mix_mono = au.to_mono(mix)
    stems_mono = {k: au.to_mono(a) for k, a in stem_audio.items()}

    pre = loop_finder.detect_beats(mix_mono, stems_mono, sr, cfg)
    bpb = cfg.beats_per_bar
    half = bpb // 2

    def pick(n_beats: int, phase: int, taken: list) -> loop_finder.LoopWindow:
        cands = loop_finder.find_loop_windows(
            mix_mono, stems_mono, sr, cfg,
            n_beats=n_beats, start_phase=phase, precomputed=pre)
        for w in cands:
            if all(w.end <= t.start or w.start >= t.end for t in taken):
                return w
        raise RuntimeError(f"{n_beats}拍/相位{phase} 没有不重叠的候选窗口")

    win_a = pick(bpb, 0, [])                  # A：1 小节，小节头起
    win_b = pick(half, 0, [win_a])            # B：前半小节（1-2 拍）
    win_c = pick(half, half, [win_a, win_b])  # C：后半小节（3-4 拍）
    loops = {}
    for name, w in (("loop_a", win_a), ("loop_b", win_b), ("loop_c", win_c)):
        loops[name] = loop_finder.cut_loop(mix, sr, w, cfg)
        au.write_wav(out_dir / "samples" / f"{name}.wav", loops[name], sr)
        log.info("%s @ %.2fs %.3fs score=%.3f", name, w.start,
                 w.end - w.start, w.score)

    # 谱面：A-A-A-BC，时值用名义小节长（loop 落点均匀，演奏端好对齐）
    bar = bpb * 60 / win_a.bpm
    notes = [sequencer.Note(cfg.lane_pitches["loop_a"], i * bar, bar)
             for i in range(3)]
    notes.append(sequencer.Note(cfg.lane_pitches["loop_b"], 3 * bar, bar / 2))
    notes.append(sequencer.Note(cfg.lane_pitches["loop_c"], 3.5 * bar, bar / 2))
    sequencer.write_chart(notes, win_a, out_dir / "chart.mid")

    lanes = {
        "bpm": round(win_a.bpm, 2),
        "pattern": "A-A-A-BC",
        "bars": 4,
        "loop_seconds": round(4 * bar, 4),
        "lanes": [
            {"lane": i, "name": n, "kind": "loop",
             "pitch": cfg.lane_pitches[n], "sample": f"samples/{n}.wav",
             "bars": 1.0 if n == "loop_a" else 0.5}
            for i, n in enumerate(("loop_a", "loop_b", "loop_c"))
        ],
    }
    (out_dir / "lanes.json").write_text(
        json.dumps(lanes, indent=2, ensure_ascii=False))

    # 重渲染：按谱面铺 loop，走完 4 小节
    total = int(4 * bar * sr) + len(loops["loop_c"])
    buf = np.zeros((total, mix.shape[1]), dtype=np.float32)
    for n in notes:
        name = {v: k for k, v in cfg.lane_pitches.items()}[n.pitch]
        s = int(n.time * sr)
        seg = loops[name]
        buf[s:s + len(seg)] += seg
    au.write_wav(out_dir / "render_preview.wav", buf[:int(4 * bar * sr)], sr)

    report = {
        "song_id": song_id, "status": "passed", "mode": "abc",
        "pattern": "A-A-A-BC", "bpm": round(win_a.bpm, 2),
        "windows": {
            n: {"start": round(w.start, 3), "seconds": round(w.end - w.start, 3),
                "score": round(w.score, 4), "detail": w.detail}
            for n, w in (("a", win_a), ("b", win_b), ("c", win_c))},
        "elapsed_sec": round(time.time() - t0, 1),
    }
    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False))
    log.info("song %s abc 完成 (%.1fs)", song_id, report["elapsed_sec"])
    return report


def run_pipeline(input_path: Path, out_root: Path, song_id: str,
                 cfg: PipelineConfig | None = None) -> dict:
    """跑全管线，输出 {out_root}/{song_id}/{samples/*.wav, chart.mid, lanes.json}。

    返回 report dict（同时写入 report.json）。status: passed / rejected。
    """
    cfg = cfg or PipelineConfig()
    t0 = time.time()
    out_dir = out_root / song_id
    out_dir.mkdir(parents=True, exist_ok=True)
    sr = cfg.sample_rate

    # 阶段2 分轨
    stem_paths = stems.separate(Path(input_path), out_dir, cfg)
    stem_audio = {k: au.load_wav(p, sr)[0] for k, p in stem_paths.items()}
    mix_mono = sum(au.to_mono(a) for a in stem_audio.values())

    # 阶段3 候选窗口
    stems_mono = {k: au.to_mono(a) for k, a in stem_audio.items()}
    windows = loop_finder.find_loop_windows(mix_mono, stems_mono, sr, cfg)

    best = None  # (score, artifacts)
    attempts = []
    for wi, window in enumerate(windows[: cfg.n_candidate_windows]):
        try:
            loops = {k: loop_finder.cut_loop(a, sr, window, cfg)
                     for k, a in stem_audio.items()}
            loop_mix = sum(loops.values())

            # 阶段4 切片
            drums, longs = slicer.slice_all(loops, sr, window, cfg)
            samples = drums.samples + longs

            # 阶段5 MIDI
            grid = window.grid_times(cfg.grid_per_beat) - window.start
            notes = sequencer.drum_notes(drums, grid, cfg)
            notes += sequencer.long_notes(longs, loops, sr, grid, cfg)

            # 阶段6 验收
            score, rendered = validate.validate(notes, samples, loop_mix, sr, cfg)
        except RuntimeError as e:
            log.warning("窗口 %d (%.2fs) 失败：%s", wi, window.start, e)
            attempts.append({"window": wi, "start": round(window.start, 2),
                             "error": str(e)})
            continue

        attempts.append({"window": wi, "start": round(window.start, 2),
                         "score": round(score, 4)})
        artifacts = (window, samples, notes, loop_mix, rendered)
        if best is None or score > best[0]:
            best = (score, artifacts)
        if score >= cfg.similarity_threshold:
            break

    if best is None:
        report = {"song_id": song_id, "status": "failed",
                  "error": "所有候选窗口均无法切片", "attempts": attempts}
        (out_dir / "report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False))
        return report

    score, (window, samples, notes, loop_mix, rendered) = best
    passed = score >= cfg.similarity_threshold

    # 落盘
    for s in samples:
        au.write_wav(out_dir / "samples" / f"{s.name}.wav", s.audio, sr)
    sequencer.write_chart(notes, window, out_dir / "chart.mid")
    lanes = sequencer.write_lanes(samples, window, cfg, out_dir / "lanes.json")
    au.write_wav(out_dir / "loop_preview.wav", loop_mix, sr)        # 原 loop（听感对照）
    au.write_wav(out_dir / "render_preview.wav", rendered, sr)      # MIDI 重渲染

    report = {
        "song_id": song_id,
        "status": "passed" if passed else "rejected",
        "score": round(score, 4),
        "threshold": cfg.similarity_threshold,
        "bpm": round(window.bpm, 2),
        "loop_start_sec": round(window.start, 3),
        "loop_seconds": round(window.end - window.start, 3),
        "n_samples": len(samples),
        "n_notes": len(notes),
        "lanes": lanes["lanes"],
        "attempts": attempts,
        "elapsed_sec": round(time.time() - t0, 1),
    }
    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False))
    log.info("song %s %s score=%.3f (%.1fs)", song_id, report["status"],
             score, report["elapsed_sec"])
    return report
