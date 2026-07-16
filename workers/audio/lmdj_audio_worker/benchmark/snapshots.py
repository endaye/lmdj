"""Benchmark run 目录与快照（spec §8）。

一个 run 目录（`benchmarks/<run-id>/`）在开始时冻结四份快照——`run.json`
（run_id/created_at/args/data_root 环境变量名，**不记环境变量值**）、
`manifest.snapshot.json`、`registry.snapshot.json`、`environment.json`——
使得发布的 report 能从这些 snapshot 重建实验身份，且不含绝对主机路径。

`combo_dir`/`write_combo`/`read_combo` 管理 `results/<dataset>/<track>/
<separator>/<device>/<repeat>/combo.json`，逐组合落盘、可断点续跑。
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import time
from pathlib import Path

RUN_ID_RE = re.compile(r"[A-Za-z0-9_-]+")

_DATA_ROOT_ENV_VAR = "LMDJ_BENCH_DATA_ROOT"
_CONFIG_FILES = ("parity-constraints.txt", "runner-scnet-constraints.txt", "msst.lock", "metrics-constraints.txt")
_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def _write_json_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _environment_snapshot() -> dict:
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "config_sha256": {
            name: _sha256_file(_CONFIG_DIR / name) for name in _CONFIG_FILES
        },
    }


def init_run(out_root: Path, run_id: str, manifest_paths: list[Path],
             registry_path: Path, args: dict) -> Path:
    """建 `out_root/<run_id>/`，冻结 run/manifest/registry/environment 四份快照。"""
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError(f"非法 run_id {run_id!r}，只允许 {RUN_ID_RE.pattern}")

    run_dir = Path(out_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    run_json = {
        "run_id": run_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "args": args,
        "data_root": _DATA_ROOT_ENV_VAR,
    }
    _write_json_atomic(run_dir / "run.json", run_json)

    manifest_snapshot = {
        Path(p).name: json.loads(Path(p).read_text()) for p in manifest_paths
    }
    _write_json_atomic(run_dir / "manifest.snapshot.json", manifest_snapshot)

    registry_snapshot = json.loads(Path(registry_path).read_text())
    _write_json_atomic(run_dir / "registry.snapshot.json", registry_snapshot)

    _write_json_atomic(run_dir / "environment.json", _environment_snapshot())

    return run_dir


def combo_dir(run_dir: Path, dataset_id: str, track_id: str, separator_id: str,
              device: str, repeat: int) -> Path:
    """`run_dir/results/<dataset>/<track>/<separator>/<device>/<repeat>`（不自动创建）。"""
    return (Path(run_dir) / "results" / dataset_id / track_id / separator_id
             / device / str(repeat))


def write_combo(path: Path, record: dict) -> None:
    """原子写 `path/combo.json`；`path` 不存在时自动创建。"""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(path / "combo.json", record)


def read_combo(path: Path) -> dict | None:
    """读 `path/combo.json`；不存在或 JSON 损坏 -> None。"""
    combo_path = Path(path) / "combo.json"
    try:
        return json.loads(combo_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def finalize_run(run_dir: Path, summary: dict) -> None:
    """把 counts/failures 等 summary 字段合并写回 `run.json`（原字段保留）。"""
    run_json_path = Path(run_dir) / "run.json"
    run_json = json.loads(run_json_path.read_text())
    run_json.update(summary)
    _write_json_atomic(run_json_path, run_json)
