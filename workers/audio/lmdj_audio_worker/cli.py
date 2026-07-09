from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lmdj_audio_worker.job import process_job
from lmdj_audio_worker.runner import DemoPipelineRunner
from lmdj_audio_worker.status import read_status

_WORKER_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JOBS_ROOT = _WORKER_ROOT / "jobs"
DEFAULT_DEMO_DIR = (
    _WORKER_ROOT.parent.parent / "references" / "demos" / "lmdj-song-pipeline"
)


def main() -> None:
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

    args = parser.parse_args()

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
    else:
        job_dir = args.jobs_root / args.job_id
        if not (job_dir / "status.json").exists():
            print(f"unknown job_id: {args.job_id}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(read_status(job_dir).to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
