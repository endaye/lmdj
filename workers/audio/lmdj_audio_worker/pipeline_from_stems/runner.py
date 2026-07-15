"""从已有 legacy stems（drums/bass/melody）运行 pipeline 阶段 3–6。

阶段 3–6 的编排逐行来自 demo pipeline.py::run_pipeline（stage 2 分轨替换为
直接读 stems 目录）。行为改动必须先过 scripts/dev.sh parity。
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np

from . import audio_utils as au
from . import loop_finder, sequencer, slicer, validate
from .config import PipelineConfig

log = logging.getLogger(__name__)

LEGACY_STEMS = ("drums", "bass", "melody")


def load_legacy_stems(stems_dir: Path, sr: int) -> dict[str, np.ndarray]:
    stems_dir = Path(stems_dir)
    expected = {k: stems_dir / f"{k}.wav" for k in LEGACY_STEMS}
    missing = [k for k, p in expected.items() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"stems 目录缺少 {missing}（需要 {list(LEGACY_STEMS)}）: {stems_dir}")
    return {k: au.load_wav(p, sr)[0] for k, p in expected.items()}


def run_from_stems(stems_dir: Path, out_root: Path, song_id: str,
                   cfg: PipelineConfig | None = None) -> dict:
    cfg = cfg or PipelineConfig()
    t0 = time.time()
    out_dir = Path(out_root) / song_id
    out_dir.mkdir(parents=True, exist_ok=True)
    sr = cfg.sample_rate

    # 阶段2 替换：直接读 stems 目录（demo: stems.separate）
    stem_audio = load_legacy_stems(stems_dir, sr)
    mix_mono = sum(au.to_mono(a) for a in stem_audio.values())

    # 阶段3 候选窗口 —— 以下与 demo run_pipeline 逐行一致
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
    au.write_wav(out_dir / "loop_preview.wav", loop_mix, sr)
    au.write_wav(out_dir / "render_preview.wav", rendered, sr)

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
