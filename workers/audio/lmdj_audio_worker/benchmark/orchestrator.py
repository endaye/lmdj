"""benchmark orchestrator（spec §4/§8/§10）：组合遍历 + 全链执行 + 缓存/resume。

组合 = dataset×track×separator×device×repeat。一个组合失败不得中止整批；
设备不支持记 unsupported_device 失败（不跳过不降级）；缓存命中不重跑、
不计入性能指标。orchestrator 不 import 任何模型框架（runner 是子进程）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..separation.protocol import SeparationRequest
from ..separation.registry import load_registry
from . import cache_key as ck
from . import snapshots
from .manifest import load_manifest, resolve_input

_WORKER_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = _WORKER_ROOT / "config" / "separators.json"

# combo.json 阶段顺序（spec §4/§8/记录规范），_run_combo 与 _finalize 沿用同一顺序
_STAGE_ORDER = ("normalize", "separate", "validate", "compat", "pfs", "patchify")


@dataclass
class OrchestratorDeps:
    normalize: Callable
    ensure_checkpoint: Callable
    separate: Callable
    validate_stems: Callable
    compat: Callable
    pfs_run: Callable
    patchify: Callable


def default_deps() -> OrchestratorDeps:
    from lmdj_patchify.patchify import patchify_package

    from ..pipeline_from_stems.compat import map_canonical_to_legacy
    from ..runner import PipelineFromStemsRunner
    from ..separation.cache import ensure_checkpoint
    from ..separation.contract import validate_canonical_stems
    from ..separation.protocol import run_separator
    from .normalize import normalize_input

    pfs = PipelineFromStemsRunner()
    return OrchestratorDeps(
        normalize=normalize_input,
        ensure_checkpoint=ensure_checkpoint,
        separate=run_separator,
        validate_stems=validate_canonical_stems,
        compat=map_canonical_to_legacy,
        pfs_run=pfs.run,
        patchify=patchify_package,
    )


@dataclass
class RunConfig:
    manifests: list
    separator_ids: list
    device: str
    repeats: int = 1
    seed: int = 0
    fresh: bool = False
    timeout_sec: int = 1800
    out_root: Path = Path("benchmarks")
    run_id: str | None = None
    registry_path: Path | None = None


@dataclass
class RunSummary:
    run_dir: Path
    total: int = 0
    completed: int = 0
    failed: int = 0
    cache_hits: int = 0
    failures: list = field(default_factory=list)


def run_benchmark(cfg: RunConfig, *, deps: OrchestratorDeps | None = None) -> RunSummary:
    deps = deps or default_deps()
    registry_path = Path(cfg.registry_path or DEFAULT_REGISTRY)
    entries = {e.id: e for e in load_registry(registry_path)}
    unknown = [s for s in cfg.separator_ids if s not in entries]
    if unknown:
        raise ValueError(f"未知 separator id: {unknown}（registry 有 {sorted(entries)}）")

    run_id = cfg.run_id or time.strftime("run-%Y%m%d-%H%M%S")
    run_dir = snapshots.init_run(
        Path(cfg.out_root), run_id, [Path(m) for m in cfg.manifests],
        registry_path,
        {"separators": list(cfg.separator_ids), "device": cfg.device,
         "repeats": cfg.repeats, "seed": cfg.seed, "fresh": cfg.fresh,
         "timeout_sec": cfg.timeout_sec})
    summary = RunSummary(run_dir=run_dir)

    for manifest_path in cfg.manifests:
        m = load_manifest(Path(manifest_path))
        for track in m.tracks:
            normalized = None
            norm_error = None
            try:
                # 按 track.id 分目录：不同 track 同名源文件（如都叫 vocal.mp3）
                # 若共用一个目录会因幂等复用静默拿到第一首的音频
                normalized = deps.normalize(
                    resolve_input(track),
                    run_dir / "normalized" / m.dataset_id / track.id)
            except Exception as exc:  # noqa: BLE001 —— 记录后继续其他 track
                norm_error = str(exc)[-2000:]
            for sep_id in cfg.separator_ids:
                entry = entries[sep_id]
                for repeat in range(cfg.repeats):
                    summary.total += 1
                    _run_combo(cfg, deps, summary, run_dir, m.dataset_id,
                               track, entry, repeat, normalized, norm_error)
    _finalize(run_dir, summary)
    return summary


def _run_combo(cfg: RunConfig, deps: OrchestratorDeps, summary: RunSummary,
              run_dir: Path, dataset_id: str, track, entry, repeat: int,
              normalized, norm_error: str | None) -> None:
    combo_path = snapshots.combo_dir(
        run_dir, dataset_id, track.id, entry.id, cfg.device, repeat)
    stages: dict[str, dict] = {}

    def _skip_downstream_of(stage: str) -> None:
        for later in _STAGE_ORDER[_STAGE_ORDER.index(stage) + 1:]:
            stages[later] = {"status": "skipped", "seconds": 0.0}

    def _fail(stage: str, category: str, error_text: str, elapsed: float,
              cache_key: str | None, cache_key_components: dict) -> None:
        stages[stage] = {"status": "failed", "seconds": round(elapsed, 3),
                         "error": (error_text or "")[-2000:]}
        _skip_downstream_of(stage)
        record = {
            "status": "failed",
            "cache_key": cache_key,
            "cache_key_components": cache_key_components,
            "track": track.id,
            "separator": entry.id,
            "device": cfg.device,
            "repeat": repeat,
            "stages": dict(stages),
            "failed_stage": stage,
            "error_category": category,
            "performance": None,
            "cached": False,
        }
        snapshots.write_combo(combo_path, record)
        summary.failed += 1
        summary.failures.append({
            "track": track.id,
            "separator": entry.id,
            "device": cfg.device,
            "repeat": repeat,
            "stage": stage,
            "category": category,
            "error": (error_text or "")[-2000:],
            "elapsed_seconds": round(elapsed, 3),
        })

    # normalize 失败：该 track 所有组合都记 inference 失败，stage=normalize，
    # 且 normalize 之后的所有阶段都是 skipped（从未真正执行）。
    if norm_error is not None:
        _fail("normalize", "inference", norm_error, 0.0, None, {})
        return
    stages["normalize"] = {"status": "ok", "seconds": 0.0}

    cache_key = ck.combo_cache_key(normalized.sha256, entry, cfg.device, cfg.seed, repeat)
    cache_key_components = ck.describe(normalized.sha256, entry, cfg.device, cfg.seed, repeat)

    # 设备不支持：不得静默降级，也不得调用 separate；记在 separate 阶段。
    if cfg.device not in entry.devices:
        _fail("separate", "unsupported_device",
              f"{entry.id} 不支持设备 {cfg.device}（registry devices={entry.devices}）",
              0.0, cache_key, cache_key_components)
        return

    # 缓存命中：不执行任何阶段，只更新 cached 标记与 run 汇总计数。
    if not cfg.fresh:
        prev = snapshots.read_combo(combo_path)
        if (prev is not None and prev.get("cache_key") == cache_key
                and prev.get("status") == "completed"):
            updated = dict(prev)
            updated["cached"] = True
            snapshots.write_combo(combo_path, updated)
            summary.cache_hits += 1
            summary.completed += 1
            return

    # separate
    t0 = time.monotonic()
    try:
        checkpoint_dir = deps.ensure_checkpoint(entry)
        request = SeparationRequest(
            input_path=normalized.path, output_dir=combo_path / "separation",
            device=cfg.device, seed=cfg.seed, repeat_id=repeat)
        result = deps.separate(entry, request, checkpoint_dir,
                               timeout_sec=cfg.timeout_sec)
    except Exception as exc:  # noqa: BLE001 —— 未预期异常按 downstream 归类
        _fail("separate", "downstream", str(exc), time.monotonic() - t0,
              cache_key, cache_key_components)
        return
    elapsed = time.monotonic() - t0
    if result.status != "completed":
        category = result.error.category if result.error else "inference"
        error_text = result.error.stderr_tail if result.error else ""
        _fail("separate", category, error_text, elapsed, cache_key, cache_key_components)
        return
    stages["separate"] = {"status": "ok", "seconds": round(elapsed, 3)}

    # validate
    separation_dir = combo_path / "separation"
    t0 = time.monotonic()
    try:
        errors = deps.validate_stems(separation_dir, result, normalized.frames)
    except Exception as exc:  # noqa: BLE001
        _fail("validate", "downstream", str(exc), time.monotonic() - t0,
              cache_key, cache_key_components)
        return
    elapsed = time.monotonic() - t0
    if errors:
        _fail("validate", "invalid_stems", "; ".join(errors), elapsed,
              cache_key, cache_key_components)
        return
    stages["validate"] = {"status": "ok", "seconds": round(elapsed, 3)}

    # compat：canonical stems 固定写在 <separation_dir>/stems/<name>.wav
    # （runner 共享 scaffold `write_canonical_stems` 的约定，spec §5）。
    legacy_dir = combo_path / "legacy"
    t0 = time.monotonic()
    try:
        deps.compat(separation_dir / "stems", legacy_dir)
    except Exception as exc:  # noqa: BLE001
        _fail("compat", "downstream", str(exc), time.monotonic() - t0,
              cache_key, cache_key_components)
        return
    stages["compat"] = {"status": "ok", "seconds": round(time.monotonic() - t0, 3)}

    # pfs
    pfs_root = combo_path / "pfs"
    t0 = time.monotonic()
    try:
        package_dir = deps.pfs_run(legacy_dir, pfs_root, track.id)
    except Exception as exc:  # noqa: BLE001
        _fail("pfs", "downstream", str(exc), time.monotonic() - t0,
              cache_key, cache_key_components)
        return
    stages["pfs"] = {"status": "ok", "seconds": round(time.monotonic() - t0, 3)}

    # patchify
    t0 = time.monotonic()
    try:
        deps.patchify(package_dir)
    except Exception as exc:  # noqa: BLE001
        _fail("patchify", "downstream", str(exc), time.monotonic() - t0,
              cache_key, cache_key_components)
        return
    stages["patchify"] = {"status": "ok", "seconds": round(time.monotonic() - t0, 3)}

    record = {
        "status": "completed",
        "cache_key": cache_key,
        "cache_key_components": cache_key_components,
        "track": track.id,
        "separator": entry.id,
        "device": cfg.device,
        "repeat": repeat,
        "stages": dict(stages),
        "failed_stage": None,
        "error_category": None,
        "performance": result.performance,
        "cached": False,
    }
    snapshots.write_combo(combo_path, record)
    summary.completed += 1


def _finalize(run_dir: Path, summary: RunSummary) -> None:
    snapshots.finalize_run(run_dir, {
        "total": summary.total,
        "completed": summary.completed,
        "failed": summary.failed,
        "cache_hits": summary.cache_hits,
        "failures": summary.failures,
    })
