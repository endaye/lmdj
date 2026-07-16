"""MUSDB18HQ 目录 -> lmdj.benchmark-manifest.v1 生成器（1D 前置物料工具）。

MUSDB18HQ 布局：<root>/{train,test}/<Track Name>/{mixture,drums,bass,other,vocals}.wav。
生成的 manifest 以 <root> 为 LMDJ_BENCH_DATA_ROOT，公开 track 名作 id（spec §7.1：
仓库只提交 manifest schema 与公开 track ID，不提交数据集内容）。

用法：
    python -m lmdj_audio_worker.benchmark.musdb --root ~/datasets/musdb18hq \
        --out musdb18hq-test.manifest.json [--subset test] [--perf 8]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .manifest import MANIFEST_SCHEMA_VERSION

_GT_STEMS = ("drums", "bass", "vocals", "other")


class MusdbLayoutError(ValueError):
    pass


def build_musdb_manifest(root: Path, subset: str = "test",
                         perf: int = 0) -> dict:
    root = Path(root)
    subset_dir = root / subset
    if not subset_dir.is_dir():
        raise MusdbLayoutError(f"MUSDB subset 目录不存在: {subset_dir}")
    track_dirs = sorted(p for p in subset_dir.iterdir() if p.is_dir())
    if not track_dirs:
        raise MusdbLayoutError(f"MUSDB subset 目录为空: {subset_dir}")

    errors: list[str] = []
    tracks: list[dict] = []
    for i, track_dir in enumerate(track_dirs):
        name = track_dir.name
        missing = [s for s in ("mixture", *_GT_STEMS)
                   if not (track_dir / f"{s}.wav").exists()]
        if missing:
            errors.append(f"{name}: 缺少 {missing}")
            continue
        rel = f"{subset}/{name}"
        tracks.append({
            "id": name,
            "input": f"{rel}/mixture.wav",
            "split": "perf" if i < perf else "full",
            "tags": [],
            "has_ground_truth": True,
            "ground_truth": {s: f"{rel}/{s}.wav" for s in _GT_STEMS},
        })
    if errors:
        raise MusdbLayoutError("；".join(errors))
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "dataset_id": f"musdb18hq-{subset}",
        "tracks": tracks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser("musdb-manifest", description=__doc__)
    parser.add_argument("--root", type=Path, required=True,
                        help="MUSDB18HQ 根目录（含 train/ test/）")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--subset", default="test", choices=("train", "test"))
    parser.add_argument("--perf", type=int, default=0,
                        help="按字母序把前 N 首标为 perf split（Linux 性能采样子集）")
    args = parser.parse_args(argv)
    try:
        data = build_musdb_manifest(args.root, subset=args.subset,
                                    perf=args.perf)
    except MusdbLayoutError as exc:
        print(f"MUSDB 布局错误：{exc}", file=sys.stderr)
        return 1
    args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"manifest 写入 {args.out}（{len(data['tracks'])} tracks，"
          f"data root 应设为 {args.root}）")
    for t in data["tracks"]:
        print(f"  [{t['split']:<4}] {t['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
