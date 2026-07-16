"""单个 separator 的 smoke 执行：registry -> cache -> runner -> canonical 校验。

dev.sh `separate` 的实现；也是 Phase 1C orchestrator 之前的手动验收工具。
主 venv 运行（需要 pfs extra 的 soundfile 做 canonical 校验）。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .cache import ensure_checkpoint
from .contract import validate_canonical_stems
from .protocol import SeparationRequest, run_separator
from .registry import load_registry

_WORKER_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = _WORKER_ROOT / "config" / "separators.json"


def _input_frames(path: Path) -> int | None:
    import soundfile as sf
    try:
        info = sf.info(str(path))
    except Exception:
        return None
    return info.frames if info.samplerate == 44100 else None


def _stem_frames(out_dir: Path, result) -> int:
    import soundfile as sf
    return sf.info(str(out_dir / result.stems["drums"])).frames


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser("separation-smoke", description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--device", required=True, choices=("cpu", "mps"))
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args(argv)

    entries = {e.id: e for e in load_registry(args.registry)}
    entry = entries.get(args.id)
    if entry is None:
        print(f"未知 separator id {args.id!r}，registry 有 {sorted(entries)}",
              file=sys.stderr)
        return 1
    if args.device not in entry.devices:
        print(f"{args.id} 不支持设备 {args.device}（registry devices={entry.devices}）",
              file=sys.stderr)
        return 1

    out_dir = args.out or Path(f"separation-smoke-{args.id}-{int(time.time())}")
    checkpoint_dir = ensure_checkpoint(entry)
    request = SeparationRequest(input_path=args.input, output_dir=out_dir,
                                device=args.device)
    result = run_separator(entry, request, checkpoint_dir,
                           timeout_sec=args.timeout)
    if result.status != "completed":
        print(f"FAILED [{result.error.category}] source={result.source} "
              f"exit={result.error.exit_code}\n{result.error.stderr_tail}",
              file=sys.stderr)
        return 1

    expected_frames = _input_frames(args.input)
    if expected_frames is None:
        print("warning: 输入无法用 soundfile 读取或非 44.1k，时长核对退化为 stems 自身帧数")
        expected_frames = _stem_frames(out_dir, result)
    errors = validate_canonical_stems(out_dir, result, expected_frames)
    if errors:
        print("canonical 校验失败：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    perf = result.performance or {}
    print(f"actual_device: {result.actual_device}")
    print(f"canonical OK: 4 stems @ {out_dir}")
    print("performance: " + ", ".join(f"{k}={v}" for k, v in sorted(perf.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
