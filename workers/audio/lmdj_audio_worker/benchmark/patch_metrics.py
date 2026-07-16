"""Patch 质量指标提取（spec Task 4）。

从一个 combo 目录（`combo.json` + `pfs/<track_id>/report.json` + 同目录
`patch.json`）里提取 patch 质量指标供 report 聚合使用。任何文件缺失/损坏
都逐项降级为 `None`（`combo_completed`/`patch_loads` 降级为 `False`），
从不抛异常——combo 目录本身也可能整体不存在（对应 orchestrator 里
normalize/separate 早期失败、pfs 阶段从未跑到的情况）。
"""
from __future__ import annotations

import json
from pathlib import Path

_DEGRADED_DRUM_NAMES = {"drum_low", "drum_high"}


def _read_json(path: Path) -> dict | None:
    """读 JSON 文件；不存在、非法 JSON、或顶层不是 object 均返回 None。"""
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def patch_metrics_for_combo(combo_dir: Path, track_id: str) -> dict:
    combo_dir = Path(combo_dir)

    combo = _read_json(combo_dir / "combo.json")
    combo_completed = combo is not None and combo.get("status") == "completed"

    pfs_dir = combo_dir / "pfs" / track_id
    report = _read_json(pfs_dir / "report.json")

    pipeline_status = None
    validation_score = None
    attempts = None
    drum_degraded = None
    n_samples = None
    n_lanes = None
    lane_names = None

    if report is not None:
        pipeline_status = report.get("status")
        validation_score = report.get("score")
        n_samples = report.get("n_samples")

        attempts_list = report.get("attempts")
        if isinstance(attempts_list, list):
            attempts = len(attempts_list)

        lanes = report.get("lanes")
        if isinstance(lanes, list):
            n_lanes = len(lanes)
            lane_names = [lane.get("name") for lane in lanes]
            drum_degraded = any(name in _DEGRADED_DRUM_NAMES for name in lane_names)

    patch = _read_json(pfs_dir / "patch.json")
    patch_loads = patch is not None and "patch_id" in patch

    return {
        "combo_completed": combo_completed,
        "pipeline_status": pipeline_status,
        "validation_score": validation_score,
        "attempts": attempts,
        "drum_degraded": drum_degraded,
        "n_samples": n_samples,
        "n_lanes": n_lanes,
        "lane_names": lane_names,
        "patch_loads": patch_loads,
    }
