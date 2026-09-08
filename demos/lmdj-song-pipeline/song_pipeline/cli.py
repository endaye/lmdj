"""CLI：song-pipeline run / batch / serve"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .config import PipelineConfig
from .pipeline import run_pipeline

AUDIO_EXTS = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aiff"}


def _cfg(args) -> PipelineConfig:
    cfg = PipelineConfig()
    if args.fast:
        cfg.demucs_model = "htdemucs"  # 单模型，比 _ft（4 模型 bag）快 4 倍
    if getattr(args, "max_loop_seconds", None):
        cfg.max_loop_seconds = args.max_loop_seconds
    if getattr(args, "bars", None):
        cfg.bars = args.bars
    return cfg


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
    ap = argparse.ArgumentParser(prog="song-pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="单曲跑全管线")
    run.add_argument("input", type=Path)
    run.add_argument("--out", type=Path, default=Path("output"))
    run.add_argument("--song-id", default=None)
    run.add_argument("--fast", action="store_true", help="用 htdemucs 加速分轨")
    run.add_argument("--max-loop-seconds", type=float, default=None,
                     help="loop 时长上限，自动折半小节数塞进去")
    run.add_argument("--bars", type=int, default=None, help="固定 loop 小节数（如 1）")
    run.add_argument("--abc", action="store_true",
                     help="ABC loop 模式：A(1小节)+B/C(半小节)，谱面 A-A-A-BC")

    batch = sub.add_parser("batch", help="批量模式：跑目录下所有音频并出合格率报告")
    batch.add_argument("input_dir", type=Path)
    batch.add_argument("--out", type=Path, default=Path("output"))
    batch.add_argument("--fast", action="store_true")

    serve = sub.add_parser("serve", help="启动 FastAPI 服务")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    gen = sub.add_parser("gen", help="阶段1：MusicGen 生成一首固定 BPM 的曲子")
    gen.add_argument("--bpm", type=int, default=85)
    gen.add_argument("--style", default="lofi hiphop beat")
    gen.add_argument("--seconds", type=float, default=30.0)
    gen.add_argument("--seed", type=int, default=None)
    gen.add_argument("--out", type=Path, default=Path("output"))
    gen.add_argument("--song-id", default=None)
    gen.add_argument("--fast", action="store_true")
    gen.add_argument("--run", action="store_true", help="生成后直接串全管线")

    args = ap.parse_args()

    if args.cmd == "run":
        song_id = args.song_id or args.input.stem.replace(" ", "_")
        if args.abc:
            from .pipeline import run_pipeline_abc
            report = run_pipeline_abc(args.input, args.out, song_id, _cfg(args))
        else:
            report = run_pipeline(args.input, args.out, song_id, _cfg(args))
        print(json.dumps(report, indent=2, ensure_ascii=False))

    elif args.cmd == "batch":
        files = sorted(p for p in args.input_dir.iterdir()
                       if p.suffix.lower() in AUDIO_EXTS)
        results = []
        for p in files:
            try:
                r = run_pipeline(p, args.out, p.stem.replace(" ", "_"), _cfg(args))
            except Exception as e:  # noqa: BLE001 批量模式单曲失败不中断
                r = {"song_id": p.stem, "status": "failed", "error": str(e)}
            results.append(r)
            print(f"[{r['status']:>8}] {r['song_id']} score={r.get('score', '-')}")
        passed = sum(r["status"] == "passed" for r in results)
        summary = {"total": len(results), "passed": passed,
                   "pass_rate": round(passed / max(1, len(results)), 3),
                   "results": results}
        (args.out / "batch_report.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False))
        print(f"\n合格率 {passed}/{len(results)} = {summary['pass_rate']:.0%}"
              f" → {args.out / 'batch_report.json'}")

    elif args.cmd == "gen":
        from .generate import generate
        song_id = args.song_id or f"gen_{args.bpm}bpm_{args.seed or 'rnd'}"
        wav, bpm = generate(args.out / song_id / "input.wav", bpm=args.bpm,
                            style=args.style, seconds=args.seconds, seed=args.seed)
        if args.run:
            cfg = _cfg(args)
            cfg.bpm_hint = float(bpm)  # 生成端固定的 BPM 直接喂给拍子检测
            report = run_pipeline(wav, args.out, song_id, cfg)
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(wav)

    elif args.cmd == "serve":
        import uvicorn
        uvicorn.run("song_pipeline.api:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
