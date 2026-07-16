"""benchmark dataset manifest（spec §7）：lmdj.benchmark-manifest.v1。

路径一律相对 LMDJ_BENCH_DATA_ROOT；仓库只提交 schema 与匿名示例，
真实歌曲数据 gitignored；报告不得出现绝对主机路径。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

MANIFEST_SCHEMA_VERSION = "lmdj.benchmark-manifest.v1"
SPLITS = ("full", "perf", "smoke")
_GT_STEMS = ("drums", "bass", "vocals", "other")
_TRACK_FIELDS = ("id", "input", "split", "tags", "has_ground_truth", "ground_truth")


class ManifestError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class Track:
    id: str
    input: str
    split: str
    tags: tuple[str, ...]
    has_ground_truth: bool
    ground_truth: dict | None


@dataclass(frozen=True)
class Manifest:
    dataset_id: str
    tracks: tuple[Track, ...]


def _check_rel_path(value: object, label: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label}: 必须是非空相对路径字符串")
        return
    if value.startswith("/") or value.startswith("~"):
        errors.append(f"{label}: 不得是绝对路径（{value!r}）")
    if ".." in Path(value).parts:
        errors.append(f"{label}: 不得包含 ..（{value!r}）")


def load_manifest(path: Path) -> Manifest:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError([f"无法读取 manifest {path}: {exc}"]) from exc
    errors: list[str] = []
    if not isinstance(data, dict) or data.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append(f"schema_version 必须是 {MANIFEST_SCHEMA_VERSION!r}")
    dataset_id = data.get("dataset_id") if isinstance(data, dict) else None
    if not isinstance(dataset_id, str) or not dataset_id:
        errors.append("dataset_id 必须是非空字符串")
    raw_tracks = data.get("tracks") if isinstance(data, dict) else None
    if not isinstance(raw_tracks, list) or not raw_tracks:
        errors.append("tracks 必须是非空列表")
        raise ManifestError(errors)

    tracks: list[Track] = []
    for i, raw in enumerate(raw_tracks):
        prefix = f"tracks[{i}]"
        if not isinstance(raw, dict):
            errors.append(f"{prefix}: 必须是 object")
            continue
        missing = [f for f in _TRACK_FIELDS if f not in raw]
        if missing:
            errors.append(f"{prefix}: 缺少字段 {missing}")
            continue
        tid = raw["id"]
        if not isinstance(tid, str) or not tid:
            errors.append(f"{prefix}: id 必须是非空字符串")
        _check_rel_path(raw["input"], f"{prefix}({tid}).input", errors)
        if raw["split"] not in SPLITS:
            errors.append(f"{prefix}({tid}): split 必须属于 {SPLITS}")
        if not isinstance(raw["tags"], list):
            errors.append(f"{prefix}({tid}): tags 必须是列表")
        gt = raw["ground_truth"]
        if raw["has_ground_truth"]:
            if not isinstance(gt, dict):
                errors.append(f"{prefix}({tid}): has_ground_truth 时 ground_truth 必须是 object")
            else:
                for stem in _GT_STEMS:
                    if stem not in gt:
                        errors.append(f"{prefix}({tid}): ground_truth 缺少 {stem}")
                    else:
                        _check_rel_path(gt[stem],
                                        f"{prefix}({tid}).ground_truth.{stem}", errors)
        elif gt is not None:
            errors.append(f"{prefix}({tid}): has_ground_truth=False 时 ground_truth 必须为 null")
        tracks.append(Track(
            id=tid, input=raw["input"], split=raw["split"],
            tags=tuple(raw["tags"]) if isinstance(raw["tags"], list) else (),
            has_ground_truth=bool(raw["has_ground_truth"]),
            ground_truth=dict(gt) if isinstance(gt, dict) else None))

    ids = [t.id for t in tracks]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"manifest: 重复 track id {dup!r}")
    if errors:
        raise ManifestError(errors)
    return Manifest(dataset_id=dataset_id, tracks=tuple(tracks))


def data_root() -> Path:
    root = os.environ.get("LMDJ_BENCH_DATA_ROOT")
    if not root:
        raise ManifestError(["环境变量 LMDJ_BENCH_DATA_ROOT 未设置（spec §7.2）"])
    return Path(root)


def resolve_input(track: Track) -> Path:
    path = data_root() / track.input
    if not path.exists():
        raise ManifestError([f"track {track.id}: 输入不存在 {track.input}"
                             "（相对 LMDJ_BENCH_DATA_ROOT）"])
    return path
