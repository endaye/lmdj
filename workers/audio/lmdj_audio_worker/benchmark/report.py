"""benchmark 聚合与 summary 产出（spec Task 6）：跨 run 合并 -> summary.json/csv。

管线：`collect_run` 遍历单个 `run_dir/results/**/combo.json`，逐组合读取
`patch_metrics_for_combo` 与（仅 `status == "completed"` 且能定位到 track/
mix 音频时）`objective_for_combo`，然后把这些原始组合记录聚合成
per-separator×device 统计。`build_summary` 拼接任意多个 `collect_run` 的
原始组合记录（跨机器/跨平台 run 的合并只是"把 raw 列表接起来再重新聚合一
次"——不做加权平均两个已经聚合好的均值那种更容易出错的合并），据此重建
per-separator×device 视图、装配 `scoring.composite_scores`/`scoring.hard_gates`
的输入并产出最终 `summary` dict。`write_summary` 把它落盘成
`summary.json` + `summary.csv`。

## Sub-metric 归约（reduction）选择——都不是 spec 逐字规定，这里记录做法

- `sdr` / `si_sdr`（喂给 `scoring.composite_scores` 的 `separation.sdr`/
  `separation.si_sdr`）：只用 `objective_for_combo` 里 `has_gt=True` 的组合，
  取它们各自的 `sdr["mean"]`/`si_sdr["mean"]`（已经是该组合四个 stem 的均值），
  再对这些组合值取算术平均。**不**逐 stem 展开——每个组合先内部按 stem 求
  均值，再跨组合求均值（两层均值，非加权）。
- `consistency_leakage`：`objective_for_combo` 同时产出 `mixture_consistency`
  （无需 GT，越接近 0/越负越好）与逐 stem `leakage`（需要 GT，越低越好）。
  两者都是 dB 且方向一致（lower-better），但把两个不同物理量简单归一化后
  平均掉细节意义不大，且 leakage 只在有 GT 时才有——为了让这一项在有无 GT
  的组合上都能打分，**只用 `mixture_consistency` 的均值**作为
  `consistency_leakage` 的原始值喂给 scoring；`leakage` 的逐 stem 原始值
  完整保留在 `summary["raw"]`（每条原始组合记录的 `objective.leakage`），
  但不参与任何聚合/打分，只用于人工复核。
- `rtf_wall`：`mean(inference_seconds / duration_seconds)`，`duration_seconds`
  来自该组合 `separation/separation.json` 的 `audio.duration_seconds`
  （`combo.json` 本身的 `performance` 字典不含 duration；见
  `separation/runners/common.py::write_result`）。`duration_seconds` 缺失或
  为 0 的组合直接跳过（不计入均值分母）。
- `peak_memory`（打分用）：该 separator 所有已完成组合里
  `max(peak_rss_bytes, peak_device_memory_bytes)` 的最大值——两个来源的
  "占用峰值"取更大者，再跨组合取最大。
- `size_load`：brief 要求"checkpoint 目录字节数"与"model_load_seconds 均值"
  各自归一化后平均，但 `scoring.composite_scores` 每个子指标只能吃一个
  原始数字。这里选择让 scoring 侧的 `performance.size_load` 只喂
  `model_load_seconds` 的均值（模型加载时间，越低越好，符合 `LOWER_BETTER`）；
  checkpoint 目录的实测字节数改名 `checkpoint_bytes`，只出现在
  per-separator×device 聚合与 `summary["raw"]` 里，不参与打分——docstring
  在此明确记录这个简化，避免下一位读者以为 size_load 应该是字节数。
  `checkpoint_bytes` 通过 `~/.cache/lmdj/separators/<id>/<sha256>/`（尊重
  `LMDJ_MODEL_CACHE` 环境变量，同 `separation/cache.py`）实测目录总字节数；
  读不到（目录不存在/IO 错误）记 `None`。

## linux_rss_limit 的门槛输入（carry-forward，spec Task 5 遗留）

`scoring.hard_gates` 的 `linux_rss_limit` gate 吃 `per_separator[sep]
["peak_rss_bytes_max"]`。这个字段**只能**来自 `device == "cpu"` 且所属 run
`environment.json` 的 `platform` 字段指向 Linux 的组合——Mac 上跑的 cpu
combo（或任何 mps combo）都不计入，因为这个 gate 衡量的是"这个 separator
在生产 Linux CPU 环境里的常驻内存是否超 12GiB"，跟 Mac 上测到的内存数字
无关。若合并进 `build_summary` 的所有 run 里都没有一条满足
"device=='cpu' and 该 run platform 是 Linux" 的组合，这个字段就是
`None`，对应 gate 读到 `"unknown"`（而不是拿 Mac 的数字顶替）。这与
`peak_device_memory_bytes_max`（喂 `mac_memory_limit` gate）不同——那个
字段没有平台限定，跨所有组合取最大值，因为 mac_memory_limit gate 本身
就是用 Mac 物理内存百分比去比较，不需要区分 run 平台。

## GT / manifest 缺失时的降级

`collect_run` 需要 `Track`（尤其 `has_ground_truth`/`ground_truth`）才能
调用 `objective_for_combo`。`manifests` 参数（`{dataset_id: Manifest}`）
优先；缺省时从 `run_dir/manifest.snapshot.json` 反解（不做 schema 校验，
只做宽松字段提取，因为写入快照时已经过 `load_manifest` 校验）。找不到
对应 track、找不到该 track 的归一化混音音频（`run_dir/normalized/<dataset>/
<track>/*.wav`），或 `objective_for_combo` 抛出任何异常（例如 GT 音频文件
缺失、`LMDJ_BENCH_DATA_ROOT` 未设置导致的 `ManifestError`）都会被捕获，
记一条 `warnings` 文案，`objective` 置 `None`——绝不让整个聚合失败。
"""
from __future__ import annotations

import json
from pathlib import Path

from .manifest import Manifest, Track
from .metrics import objective_for_combo
from .patch_metrics import patch_metrics_for_combo
from .scoring import composite_scores, hard_gates


# ---------------------------------------------------------------------------
# small IO helpers — all tolerant, never raise
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _platform_is_linux(platform_str: str | None) -> bool:
    return bool(platform_str) and platform_str.strip().lower().startswith("linux")


def _manifests_from_snapshot(run_dir: Path) -> dict[str, Manifest]:
    """`run_dir/manifest.snapshot.json` 反解成 `{dataset_id: Manifest}`。

    宽松解析（不复用 `load_manifest` 的严格校验——快照内容已经校验过一次），
    任何字段形状不对就跳过那条 track/manifest，不抛异常。
    """
    raw = _read_json(Path(run_dir) / "manifest.snapshot.json")
    if raw is None:
        return {}
    out: dict[str, Manifest] = {}
    for value in raw.values():
        if not isinstance(value, dict):
            continue
        dataset_id = value.get("dataset_id")
        tracks_raw = value.get("tracks")
        if not isinstance(dataset_id, str) or not isinstance(tracks_raw, list):
            continue
        tracks: list[Track] = []
        for t in tracks_raw:
            if not isinstance(t, dict) or not isinstance(t.get("id"), str):
                continue
            gt = t.get("ground_truth")
            tracks.append(Track(
                id=t["id"], input=t.get("input", ""), split=t.get("split", ""),
                tags=tuple(t.get("tags") or ()),
                has_ground_truth=bool(t.get("has_ground_truth")),
                ground_truth=dict(gt) if isinstance(gt, dict) else None,
            ))
        out[dataset_id] = Manifest(dataset_id=dataset_id, tracks=tuple(tracks))
    return out


def _load_mix(run_dir: Path, dataset_id: str, track_id: str):
    """`run_dir/normalized/<dataset_id>/<track_id>/*.wav` 里的（唯一）归一化混音。

    该目录在 orchestrator 里对同一个 track 只写一份（幂等复用），文件名取自
    原始输入的 stem，这里不假设具体文件名，只取目录下第一个 `*.wav`。
    缺目录/缺文件返回 `None`（调用方据此跳过 objective 并记 warning）。
    """
    norm_dir = Path(run_dir) / "normalized" / dataset_id / track_id
    if not norm_dir.is_dir():
        return None
    wavs = sorted(norm_dir.glob("*.wav"))
    if not wavs:
        return None
    import soundfile as sf  # 懒加载，跟仓库其余 benchmark 模块同惯例

    data, _sr = sf.read(str(wavs[0]), dtype="float32", always_2d=True)
    return data


def _checkpoint_size_bytes(separator_id: str, checkpoint_sha256: str | None) -> int | None:
    if not checkpoint_sha256:
        return None
    from ..separation.cache import cache_root

    try:
        ckpt_dir = cache_root() / separator_id / checkpoint_sha256
        if not ckpt_dir.is_dir():
            return None
        return sum(f.stat().st_size for f in ckpt_dir.rglob("*") if f.is_file())
    except Exception:  # noqa: BLE001 —— 目录不可读/符号链接环等任何原因都降级为 None，不中断整个聚合
        return None


def _duration_seconds(combo_dir: Path) -> float | None:
    data = _read_json(combo_dir / "separation" / "separation.json")
    if data is None:
        return None
    audio = data.get("audio")
    if not isinstance(audio, dict):
        return None
    value = audio.get("duration_seconds")
    return float(value) if isinstance(value, (int, float)) else None


# ---------------------------------------------------------------------------
# collect_run
# ---------------------------------------------------------------------------

def collect_run(run_dir: Path, manifests: dict | None = None) -> dict:
    """遍历一个 run 目录，返回 `{"run_id", "platform", "is_linux", "warnings",
    "raw_combos", "per_separator_device"}`。

    `raw_combos` 是每个 combo 目录的扁平记录（no absolute paths — 只有
    dataset/track/separator/device/repeat 这些标识符 + combo.json 里的字段 +
    patch_metrics + 可选 objective）；`per_separator_device` 是在这个单一
    run 范围内按 `(separator, device)` 聚合的统计，调用 `_aggregate`。
    """
    run_dir = Path(run_dir)
    env = _read_json(run_dir / "environment.json") or {}
    platform_str = env.get("platform")
    is_linux = _platform_is_linux(platform_str)

    run_json = _read_json(run_dir / "run.json") or {}
    run_id = run_json.get("run_id") or run_dir.name

    manifests = manifests if manifests is not None else _manifests_from_snapshot(run_dir)

    warnings: list[str] = []
    warned: set[str] = set()

    def _warn(msg: str) -> None:
        if msg not in warned:
            warned.add(msg)
            warnings.append(msg)

    mix_cache: dict[tuple[str, str], object] = {}

    def _mix_for(dataset_id: str, track_id: str):
        key = (dataset_id, track_id)
        if key not in mix_cache:
            try:
                mix_cache[key] = _load_mix(run_dir, dataset_id, track_id)
            except Exception as exc:  # noqa: BLE001 —— 损坏的归一化音频等任何原因都降级，不中断整批
                _warn(f"归一化混音音频读取失败 {dataset_id}/{track_id}: {exc}")
                mix_cache[key] = None
        return mix_cache[key]

    raw_combos: list[dict] = []
    results_root = run_dir / "results"
    if results_root.is_dir():
        for combo_json_path in sorted(results_root.glob("*/*/*/*/*/combo.json")):
            combo_dir = combo_json_path.parent
            repeat_str = combo_dir.name
            device = combo_dir.parent.name
            separator_id = combo_dir.parent.parent.name
            track_id = combo_dir.parent.parent.parent.name
            dataset_id = combo_dir.parent.parent.parent.parent.name

            combo = _read_json(combo_json_path)
            if combo is None:
                _warn(f"combo.json 无法读取/损坏: {dataset_id}/{track_id}/{separator_id}/{device}/{repeat_str}")
                continue

            status = combo.get("status")
            performance = combo.get("performance")
            error_category = combo.get("error_category")
            cache_components = combo.get("cache_key_components") or {}
            checkpoint_sha256 = cache_components.get("checkpoint_sha256")

            duration_seconds = _duration_seconds(combo_dir)
            rtf = None
            if (performance and duration_seconds and duration_seconds > 0
                    and performance.get("inference_seconds") is not None):
                rtf = performance["inference_seconds"] / duration_seconds

            patch_metrics = patch_metrics_for_combo(combo_dir, track_id)
            checkpoint_bytes = _checkpoint_size_bytes(separator_id, checkpoint_sha256)

            objective = None
            if status == "completed":
                track = None
                manifest = manifests.get(dataset_id)
                if manifest is not None:
                    track = next((t for t in manifest.tracks if t.id == track_id), None)
                if track is None:
                    _warn(f"manifest 里找不到 track {dataset_id}/{track_id}，跳过 objective")
                else:
                    mix = _mix_for(dataset_id, track_id)
                    if mix is None:
                        _warn(f"缺归一化混音音频 {dataset_id}/{track_id}，跳过 objective")
                    else:
                        try:
                            objective = objective_for_combo(combo_dir, track, mix)
                        except Exception as exc:  # noqa: BLE001 — GT 不可达等任何原因都降级，不失败
                            _warn(f"objective 计算失败 {dataset_id}/{track_id}/{separator_id}/{device}/{repeat_str}: {exc}")

            raw_combos.append({
                "dataset": dataset_id,
                "track": track_id,
                "separator": separator_id,
                "device": device,
                "repeat": int(repeat_str) if repeat_str.isdigit() else repeat_str,
                "status": status,
                "error_category": error_category,
                "performance": performance,
                "duration_seconds": duration_seconds,
                "rtf_wall": rtf,
                "checkpoint_bytes": checkpoint_bytes,
                "patch_metrics": patch_metrics,
                "objective": objective,
                "run_id": run_id,
                "run_is_linux": is_linux,
            })

    per_separator_device = _group_and_aggregate(raw_combos, key=lambda c: (c["separator"], c["device"]))

    return {
        "run_id": run_id,
        "platform": platform_str,
        "is_linux": is_linux,
        "warnings": warnings,
        "raw_combos": raw_combos,
        "per_separator_device": per_separator_device,
    }


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------

def _mean(values: list[float]) -> float | None:
    return float(sum(values) / len(values)) if values else None


def _max_or_none(values: list[float]) -> float | None:
    return max(values) if values else None


def _aggregate(combos: list[dict]) -> dict:
    """给定一组 raw combo 记录（任意粒度：per (sep,device)、per sep 全设备
    池化、或按其它 filter 抽取的子集），算出一份聚合统计。所有跨 run 合并
    都通过"先拼接 raw_combos 再调这个函数"完成，从不合并两份已经聚合好的
    均值。"""
    total = len(combos)
    completed = [c for c in combos if c["status"] == "completed"]
    n_completed = len(completed)
    n_failed = total - n_completed

    failure_categories: dict[str, int] = {}
    for c in combos:
        if c["status"] != "completed" and c.get("error_category"):
            failure_categories[c["error_category"]] = failure_categories.get(c["error_category"], 0) + 1
    invalid_stems_failures = failure_categories.get("invalid_stems", 0)

    completion_rate = (n_completed / total) if total else None
    contract_compliance_rate = ((total - invalid_stems_failures) / total) if total else None

    # performance — only combos that actually have a `performance` dict (completed ones)
    perf_combos = [c for c in combos if c.get("performance")]
    wall_seconds = [c["performance"]["wall_seconds"] for c in perf_combos
                    if c["performance"].get("wall_seconds") is not None]
    inference_seconds = [c["performance"]["inference_seconds"] for c in perf_combos
                          if c["performance"].get("inference_seconds") is not None]
    rtf_values = [c["rtf_wall"] for c in combos if c.get("rtf_wall") is not None]
    peak_rss = [c["performance"]["peak_rss_bytes"] for c in perf_combos
                if c["performance"].get("peak_rss_bytes") is not None]
    peak_device_mem = [c["performance"]["peak_device_memory_bytes"] for c in perf_combos
                        if c["performance"].get("peak_device_memory_bytes") is not None]
    model_load = [c["performance"]["model_load_seconds"] for c in perf_combos
                  if c["performance"].get("model_load_seconds") is not None]
    checkpoint_bytes = next((c["checkpoint_bytes"] for c in combos if c.get("checkpoint_bytes") is not None), None)

    peak_rss_max = _max_or_none(peak_rss)
    peak_device_mem_max = _max_or_none(peak_device_mem)
    peak_memory_candidates = [v for v in (peak_rss_max, peak_device_mem_max) if v is not None]
    peak_memory_max = max(peak_memory_candidates) if peak_memory_candidates else None

    performance = {
        "wall_seconds_mean": _mean(wall_seconds),
        "inference_seconds_mean": _mean(inference_seconds),
        "rtf_wall_mean": _mean(rtf_values),
        "peak_rss_bytes_max": peak_rss_max,
        "peak_device_memory_bytes_max": peak_device_mem_max,
        "peak_memory_max": peak_memory_max,
        "model_load_seconds_mean": _mean(model_load),
        "checkpoint_bytes": checkpoint_bytes,
    }

    # separation (objective) — sdr/si_sdr only from has_gt combos' per-combo "mean";
    # consistency_leakage from mixture_consistency (present with or without GT).
    gt_objectives = [c["objective"] for c in combos if c.get("objective") and c["objective"].get("has_gt")]
    all_objectives = [c["objective"] for c in combos if c.get("objective")]

    sdr_means = [o["sdr"]["mean"] for o in gt_objectives if o.get("sdr", {}).get("mean") is not None]
    si_sdr_means = [o["si_sdr"]["mean"] for o in gt_objectives if o.get("si_sdr", {}).get("mean") is not None]
    mc_values = [o["mixture_consistency"] for o in all_objectives if o.get("mixture_consistency") is not None]

    # leak_worst_db: per-combo max leakage (最坏泄漏), then mean over combos with GT.
    # 只用于报告可见性；已通过 consistency_leakage 简化参与打分。
    leak_worst_db_values = []
    for o in gt_objectives:
        leakage = o.get("leakage")
        if isinstance(leakage, dict):
            stem_values = [v for v in leakage.values() if v is not None]
            if stem_values:
                leak_worst_db_values.append(max(stem_values))

    separation = {
        "sdr_mean": _mean(sdr_means),
        "si_sdr_mean": _mean(si_sdr_means),
        "consistency_leakage_mean": _mean(mc_values),
        "leak_worst_db_mean": _mean(leak_worst_db_values),
        "gt_combo_count": len(gt_objectives),
    }

    # patch quality
    pm = [c["patch_metrics"] for c in combos]
    n_passed = sum(1 for m in pm if m.get("combo_completed") and m.get("patch_loads")
                   and m.get("pipeline_status") == "passed")
    completed_passed_rate = (n_passed / total) if total else None
    validation_scores = [m["validation_score"] for m in pm if m.get("validation_score") is not None]
    reached_report = [m for m in pm if m.get("attempts") is not None]
    n_clean = sum(1 for m in reached_report if m.get("attempts", 0) <= 1 and not m.get("drum_degraded"))
    retry_degrade_clean_rate = (n_clean / len(reached_report)) if reached_report else None

    patch = {
        "completed_passed_rate": completed_passed_rate,
        "validation_score_mean": _mean(validation_scores),
        "retry_degrade_clean_rate": retry_degrade_clean_rate,
    }

    structural_stability = _structural_stability(combos)

    return {
        "total_combos": total,
        "completed_combos": n_completed,
        "failed_combos": n_failed,
        "completion_rate": completion_rate,
        "contract_compliance_rate": contract_compliance_rate,
        "failure_categories": failure_categories,
        "invalid_stems_failures": invalid_stems_failures,
        "structural_stability": structural_stability,
        "performance": performance,
        "separation": separation,
        "patch": patch,
    }


def _structural_stability(combos: list[dict]) -> float | None:
    """同 track 多 repeat 的 `(n_samples, lane_names)` 一致比例；无重复 -> None。"""
    by_track: dict[str, list[dict]] = {}
    for c in combos:
        by_track.setdefault(c["track"], []).append(c["patch_metrics"])

    repeated_tracks = {track: metrics_list for track, metrics_list in by_track.items()
                       if len(metrics_list) > 1}
    if not repeated_tracks:
        return None

    consistent = 0
    for metrics_list in repeated_tracks.values():
        signatures = {
            (m.get("n_samples"), tuple(m.get("lane_names") or ()))
            for m in metrics_list
        }
        if len(signatures) == 1:
            consistent += 1
    return consistent / len(repeated_tracks)


def _group_and_aggregate(combos: list[dict], key) -> dict:
    groups: dict = {}
    for c in combos:
        groups.setdefault(key(c), []).append(c)
    out: dict = {}
    for k, group_combos in groups.items():
        if isinstance(k, tuple):
            d = out
            for part in k[:-1]:
                d = d.setdefault(part, {})
            d[k[-1]] = _aggregate(group_combos)
        else:
            out[k] = _aggregate(group_combos)
    return out


# ---------------------------------------------------------------------------
# build_summary
# ---------------------------------------------------------------------------

def build_summary(runs: list[dict], listening: dict | None = None,
                  attestations: dict | None = None) -> dict:
    """合并多个 `collect_run` 输出（跨设备/跨平台），装配 scoring 输入，产出
    最终 summary dict（`write_summary` 直接落盘这个返回值）。"""
    all_combos: list[dict] = []
    all_warnings: list[str] = []
    run_ids: list[str] = []
    for run in runs:
        all_combos.extend(run.get("raw_combos", []))
        all_warnings.extend(run.get("warnings", []))
        run_ids.append(run.get("run_id"))

    per_separator_device = _group_and_aggregate(all_combos, key=lambda c: (c["separator"], c["device"]))
    separator_ids = sorted({c["separator"] for c in all_combos})
    per_separator_pooled = {
        sep: _aggregate([c for c in all_combos if c["separator"] == sep])
        for sep in separator_ids
    }

    # linux_rss_limit carry-forward: only device=="cpu" combos from linux-platform runs.
    linux_cpu_rss_by_sep: dict[str, float | None] = {}
    for sep in separator_ids:
        values = [
            c["performance"]["peak_rss_bytes"]
            for c in all_combos
            if c["separator"] == sep and c["device"] == "cpu" and c.get("run_is_linux")
            and c.get("performance") and c["performance"].get("peak_rss_bytes") is not None
        ]
        linux_cpu_rss_by_sep[sep] = max(values) if values else None

    composite_input = {
        sep: {
            "reliability": {
                "batch_success": agg["completion_rate"],
                "contract_compliance": agg["contract_compliance_rate"],
                "structural_stability": agg["structural_stability"],
            },
            "separation": {
                "sdr": agg["separation"]["sdr_mean"],
                "si_sdr": agg["separation"]["si_sdr_mean"],
                "consistency_leakage": agg["separation"]["consistency_leakage_mean"],
            },
            "patch": {
                "completed_passed": agg["patch"]["completed_passed_rate"],
                "validation_score": agg["patch"]["validation_score_mean"],
                "retry_degrade_structure": agg["patch"]["retry_degrade_clean_rate"],
            },
            "performance": {
                "rtf_wall": agg["performance"]["rtf_wall_mean"],
                "peak_memory": agg["performance"]["peak_memory_max"],
                "size_load": agg["performance"]["model_load_seconds_mean"],
            },
        }
        for sep, agg in per_separator_pooled.items()
    }

    hard_gate_input = {
        sep: {
            "invalid_stems_failures": (agg["invalid_stems_failures"] if agg["total_combos"] else None),
            "total_combos": agg["total_combos"] or None,
            "completed_combos": (agg["completed_combos"] if agg["total_combos"] else None),
            "patch_passed_rate": agg["patch"]["completed_passed_rate"],
            "peak_rss_bytes_max": linux_cpu_rss_by_sep.get(sep),
            "peak_device_memory_bytes_max": agg["performance"]["peak_device_memory_bytes_max"],
        }
        for sep, agg in per_separator_pooled.items()
    }

    scores = composite_scores(composite_input, listening)
    gates = hard_gates(hard_gate_input, attestations, listening)

    csv_rows = _build_csv_rows(per_separator_device, scores, gates)

    return {
        "run_ids": run_ids,
        "warnings": all_warnings,
        "per_separator_device": per_separator_device,
        "per_separator": per_separator_pooled,
        "scoring_input": composite_input,
        "hard_gate_input": hard_gate_input,
        "scores": scores,
        "gates": gates,
        "csv_rows": csv_rows,
        "raw": {"combos": all_combos},
    }


def _build_csv_rows(per_separator_device: dict, scores: dict, gates: dict) -> list[dict]:
    rows: list[dict] = []
    for sep in sorted(per_separator_device):
        sep_score = scores.get(sep, {})
        sep_gate = gates.get(sep, {})
        for device in sorted(per_separator_device[sep]):
            agg = per_separator_device[sep][device]
            rows.append({
                "separator": sep,
                "device": device,
                "total_combos": agg["total_combos"],
                "completed_combos": agg["completed_combos"],
                "completion_rate": agg["completion_rate"],
                "sdr_mean": agg["separation"]["sdr_mean"],
                "si_sdr_mean": agg["separation"]["si_sdr_mean"],
                "mixture_consistency_mean": agg["separation"]["consistency_leakage_mean"],
                "leak_worst_db": agg["separation"]["leak_worst_db_mean"],
                "passed_rate": agg["patch"]["completed_passed_rate"],
                "rtf_wall_mean": agg["performance"]["rtf_wall_mean"],
                "peak_memory_bytes": agg["performance"]["peak_memory_max"],
                "total_score": sep_score.get("total"),
                "scored_out_of": sep_score.get("scored_out_of"),
                "gate_blocked": sep_gate.get("gate_blocked"),
            })
    return rows


def write_summary(out_dir: Path, summary: dict) -> None:
    """`out_dir/summary.json`（完整 summary dict）+ `out_dir/summary.csv`
    （`summary["csv_rows"]`，pandas to_csv，index 不写入）。"""
    import pandas as pd  # 懒加载：pandas 只在落盘 CSV 时需要，跟 metrics.py 的重依赖懒加载惯例一致

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str))

    rows = summary.get("csv_rows") or []
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "summary.csv", index=False)
