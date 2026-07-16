from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lmdj_audio_worker.benchmark.listening import build_listening_package, load_listening_scores
from lmdj_audio_worker.benchmark.orchestrator import RunConfig, run_benchmark
from lmdj_audio_worker.benchmark.report import build_summary, collect_run, write_summary
from lmdj_audio_worker.job import process_job
from lmdj_audio_worker.runner import DemoPipelineRunner
from lmdj_audio_worker.status import read_status

_WORKER_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JOBS_ROOT = _WORKER_ROOT / "jobs"
DEFAULT_DEMO_DIR = (
    _WORKER_ROOT.parent.parent / "references" / "demos" / "lmdj-song-pipeline"
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="LMDJ Audio Worker: audio -> pipeline -> patchify -> patch.json")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="同步处理一个音频文件")
    run.add_argument("audio", type=Path)
    run.add_argument("--job-id", default=None)
    run.add_argument("--jobs-root", type=Path, default=DEFAULT_JOBS_ROOT)
    run.add_argument("--demo-dir", type=Path, default=DEFAULT_DEMO_DIR)
    run.add_argument("--no-fast", action="store_true", help="用 htdemucs_ft（更慢更准）")

    status = sub.add_parser("status", help="打印 job 的 status.json")
    status.add_argument("job_id")
    status.add_argument("--jobs-root", type=Path, default=DEFAULT_JOBS_ROOT)

    benchmark = sub.add_parser(
        "benchmark", help="批量跑 dataset x separator x device 基准（spec §8）")
    benchmark.add_argument(
        "--dataset", action="append", required=True, dest="datasets",
        help="benchmark manifest 路径，可重复传入以聚合多个 dataset")
    benchmark.add_argument(
        "--separators", required=True,
        help="逗号分隔的 separator id 列表，如 a,b")
    benchmark.add_argument("--device", required=True, choices=("cpu", "mps"))
    benchmark.add_argument("--repeats", type=int, default=1)
    benchmark.add_argument("--seed", type=int, default=0)
    benchmark.add_argument("--fresh", action="store_true", help="忽略缓存，强制重跑")
    benchmark.add_argument("--timeout", type=int, default=1800, dest="timeout_sec")
    benchmark.add_argument("--out", type=Path, default=Path("benchmarks"), dest="out_root")
    benchmark.add_argument("--run-id", default=None)
    benchmark.add_argument("--registry", type=Path, default=None, dest="registry_path")

    report = sub.add_parser(
        "report", help="聚合多个 benchmark run，产出 summary.json/csv + 对齐文本表（spec §9）")
    report.add_argument(
        "--run", action="append", required=True, dest="runs", type=Path,
        help="benchmark run 目录，可重复传入以聚合多个 run")
    report.add_argument(
        "--listening-scores", type=Path, default=None, dest="listening_scores",
        help="盲听评分 JSON 路径；给出时才回读盲听分数")
    report.add_argument(
        "--listening-key", type=Path, default=None, dest="listening_key",
        help="private-key.json 路径，默认 <第一个 --run>/listening-test/private-key.json")
    report.add_argument(
        "--attestations", type=Path, default=None,
        help="attestations JSON 路径（macos_mps_smoke/linux_cpu_smoke/... spec §9.5）")
    report.add_argument(
        "--out", type=Path, default=None,
        help="summary.json/csv 输出目录，默认第一个 --run 目录")

    listening_package = sub.add_parser(
        "listening-package", help="把一个 run 的 completed 组合打包成匿名盲听样本（spec §8/§9.3）")
    listening_package.add_argument("--run", required=True, dest="run", type=Path)
    listening_package.add_argument(
        "--no-stems", action="store_true", help="不打包分离出的 stem，只打包 render/loop")

    args = parser.parse_args(argv)

    if args.command == "run":
        runner = DemoPipelineRunner(args.demo_dir, fast=not args.no_fast)
        try:
            final = process_job(
                args.audio,
                jobs_root=args.jobs_root,
                runner=runner,
                job_id=args.job_id,
                on_state=lambda s: print(f"[{s.updated_at}] {s.job_id} -> {s.state}"),
            )
        except FileNotFoundError as error:
            print(f"error: {error}", file=sys.stderr)
            sys.exit(1)
        if final.state == "failed":
            print(f"error: {final.error}", file=sys.stderr)
            sys.exit(1)
        patch_path = args.jobs_root / final.job_id / (final.package_dir or "") / "patch.json"
        print(f"patch: {patch_path}")
    elif args.command == "benchmark":
        cfg = RunConfig(
            manifests=list(args.datasets),
            separator_ids=[s.strip() for s in args.separators.split(",") if s.strip()],
            device=args.device,
            repeats=args.repeats,
            seed=args.seed,
            fresh=args.fresh,
            timeout_sec=args.timeout_sec,
            out_root=args.out_root,
            run_id=args.run_id,
            registry_path=args.registry_path,
        )
        summary = run_benchmark(cfg)
        print(f"run_dir: {summary.run_dir}")
        print(f"total: {summary.total}")
        print(f"completed: {summary.completed}")
        print(f"failed: {summary.failed}")
        print(f"cache_hits: {summary.cache_hits}")
        if summary.failed > 0:
            sys.exit(1)
    elif args.command == "report":
        runs = [collect_run(run_dir) for run_dir in args.runs]
        listening = None
        if args.listening_scores is not None:
            key_path = args.listening_key
            if key_path is None:
                key_path = args.runs[0] / "listening-test" / "private-key.json"
            listening = load_listening_scores(args.listening_scores, key_path)
        attestations = None
        if args.attestations is not None:
            attestations = json.loads(Path(args.attestations).read_text())
        summary = build_summary(runs, listening=listening, attestations=attestations)
        out_dir = args.out if args.out is not None else args.runs[0]
        write_summary(out_dir, summary)
        _print_report(summary)
    elif args.command == "listening-package":
        out_dir = build_listening_package(args.run, include_stems=not args.no_stems)
        print(f"listening_package: {out_dir}")
    else:
        job_dir = args.jobs_root / args.job_id
        if not (job_dir / "status.json").exists():
            print(f"unknown job_id: {args.job_id}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(read_status(job_dir).to_dict(), ensure_ascii=False, indent=2))


def _print_report(summary: dict) -> None:
    """打印按 separator 对齐的文本表：separator / total_score / scored_out_of

    / gate 状态汇总，任一 gate 为 "fail" 的行末尾追加 `GATE FAILED`（报告工具
    本身不是门禁执行者——这个标注不影响 CLI 的退出码）。
    """
    scores = summary.get("scores") or {}
    gates = summary.get("gates") or {}
    separators = sorted(scores)

    header = f"{'separator':<24}{'total_score':>12}{'scored_out_of':>15}  gate_status"
    print(header)
    print("-" * len(header))
    for sep in separators:
        sep_score = scores.get(sep) or {}
        sep_gate = gates.get(sep) or {}
        total = sep_score.get("total") or 0.0
        scored_out_of = sep_score.get("scored_out_of") or 0.0
        gate_pairs = ", ".join(
            f"{name}={status}" for name, status in sep_gate.items() if name != "gate_blocked")
        line = f"{sep:<24}{total:>12.2f}{scored_out_of:>15.2f}  {gate_pairs}"
        if sep_gate.get("gate_blocked"):
            line += "  GATE FAILED"
        print(line)


if __name__ == "__main__":
    main()
