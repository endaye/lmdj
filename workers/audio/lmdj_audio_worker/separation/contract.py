"""lmdj.separation.v1 —— separator runner 输出契约。

字段与硬约束的规范文本：
docs/superpowers/specs/2026-07-15-multi-separator-benchmark-design.md §5。
只用 stdlib；canonical stems 的音频级校验（需 numpy/soundfile）见
validate_canonical_stems，调用方须安装 `pfs` extra。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = "lmdj.separation.v1"
CANONICAL_STEMS = ("drums", "bass", "vocals", "other")
CANONICAL_SAMPLE_RATE = 44100
CANONICAL_CHANNELS = 2
MAX_ABS_PEAK = 8.0
STATUSES = ("completed", "failed")
SOURCES = ("runner", "orchestrator")
# spec §10 统一错误类别，顺序固定
ERROR_CATEGORIES = (
    "download", "checksum", "license", "unsupported_device",
    "timeout", "oom", "inference", "invalid_stems", "downstream", "metric",
)
_SEPARATOR_KEYS = ("id", "family", "checkpoint_sha256", "runner_version")
_AUDIO_KEYS = ("sample_rate", "channels", "duration_seconds")
_PERFORMANCE_KEYS = ("model_load_seconds", "inference_seconds", "wall_seconds",
                     "peak_rss_bytes", "peak_device_memory_bytes")
_ERROR_KEYS = ("category", "stage", "stderr_tail", "elapsed_seconds")


class ContractError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class SeparatorInfo:
    id: str
    family: str
    checkpoint_sha256: str
    runner_version: str


@dataclass(frozen=True)
class SeparationError:
    category: str
    exit_code: int | None
    stage: str
    stderr_tail: str
    elapsed_seconds: float


@dataclass(frozen=True)
class SeparationResult:
    status: str
    source: str
    input_sha256: str
    separator: SeparatorInfo
    requested_device: str
    actual_device: str | None = None
    stems: dict[str, str] | None = None
    audio: dict | None = None
    performance: dict | None = None
    error: SeparationError | None = None

    def to_dict(self) -> dict:
        data: dict = {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "source": self.source,
            "input_sha256": self.input_sha256,
            "separator": {
                "id": self.separator.id,
                "family": self.separator.family,
                "checkpoint_sha256": self.separator.checkpoint_sha256,
                "runner_version": self.separator.runner_version,
            },
            "requested_device": self.requested_device,
        }
        if self.actual_device is not None:
            data["actual_device"] = self.actual_device
        if self.stems is not None:
            data["stems"] = dict(self.stems)
        if self.audio is not None:
            data["audio"] = dict(self.audio)
        if self.performance is not None:
            data["performance"] = dict(self.performance)
        if self.error is not None:
            data["error"] = {
                "category": self.error.category,
                "exit_code": self.error.exit_code,
                "stage": self.error.stage,
                "stderr_tail": self.error.stderr_tail,
                "elapsed_seconds": self.error.elapsed_seconds,
            }
        return data

    @classmethod
    def from_dict(cls, data: object) -> "SeparationResult":
        errors = validate_result_dict(data)
        if errors:
            raise ContractError(errors)
        assert isinstance(data, dict)
        sep = data["separator"]
        error = None
        if "error" in data:
            e = data["error"]
            error = SeparationError(
                category=e["category"], exit_code=e.get("exit_code"),
                stage=e["stage"], stderr_tail=e["stderr_tail"],
                elapsed_seconds=e["elapsed_seconds"])
        return cls(
            status=data["status"], source=data["source"],
            input_sha256=data["input_sha256"],
            separator=SeparatorInfo(
                id=sep["id"], family=sep["family"],
                checkpoint_sha256=sep["checkpoint_sha256"],
                runner_version=sep["runner_version"]),
            requested_device=data["requested_device"],
            actual_device=data.get("actual_device"),
            stems=data.get("stems"),
            audio=data.get("audio"),
            performance=data.get("performance"),
            error=error,
        )


def _is_sha256(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def validate_result_dict(data: object) -> list[str]:
    """dict 级校验；返回错误列表，空列表即合法。"""
    if not isinstance(data, dict):
        return ["separation.json 顶层必须是 JSON object"]
    errors: list[str] = []
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version 必须是 {SCHEMA_VERSION!r}，"
                      f"收到 {data.get('schema_version')!r}")
    status = data.get("status")
    if status not in STATUSES:
        errors.append(f"status 必须属于 {STATUSES}，收到 {status!r}")
    if data.get("source") not in SOURCES:
        errors.append(f"source 必须属于 {SOURCES}，收到 {data.get('source')!r}")
    if not _is_sha256(data.get("input_sha256")):
        errors.append("input_sha256 必须是 64 位十六进制字符串")
    sep = data.get("separator")
    if not isinstance(sep, dict):
        errors.append("separator 必须是 object")
    else:
        for key in _SEPARATOR_KEYS:
            if not isinstance(sep.get(key), str) or not sep.get(key):
                errors.append(f"separator.{key} 必须是非空字符串")
    if not isinstance(data.get("requested_device"), str):
        errors.append("requested_device 必须是字符串")

    if status == "completed":
        if not isinstance(data.get("actual_device"), str):
            errors.append("completed 记录必须带 actual_device")
        stems = data.get("stems")
        if not isinstance(stems, dict):
            errors.append("completed 记录必须带 stems object")
        else:
            for name in CANONICAL_STEMS:
                if not isinstance(stems.get(name), str):
                    errors.append(f"stems 缺少 canonical 轨 {name!r}")
            for name in stems:
                if name not in CANONICAL_STEMS:
                    errors.append(f"stems 含非 canonical 轨 {name!r}")
        audio = data.get("audio")
        if not isinstance(audio, dict):
            errors.append("completed 记录必须带 audio object")
        else:
            for key in _AUDIO_KEYS:
                if key not in audio:
                    errors.append(f"audio 缺少 {key}")
        perf = data.get("performance")
        if not isinstance(perf, dict):
            errors.append("completed 记录必须带 performance object")
        else:
            for key in _PERFORMANCE_KEYS:
                if key not in perf:
                    errors.append(f"performance 缺少 {key}")
    elif status == "failed":
        if "stems" in data:
            errors.append("失败记录不得包含 stems 字段（spec §5）")
        err = data.get("error")
        if not isinstance(err, dict):
            errors.append("failed 记录必须带 error object")
        else:
            for key in _ERROR_KEYS:
                if key not in err:
                    errors.append(f"error 缺少 {key}")
            if err.get("category") not in ERROR_CATEGORIES:
                errors.append(
                    f"error.category 必须属于 {ERROR_CATEGORIES}，"
                    f"收到 {err.get('category')!r}")
    return errors


def write_result(path: Path, result: SeparationResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


def load_result_file(path: Path) -> SeparationResult:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError([f"无法读取 {path}: {exc}"]) from exc
    return SeparationResult.from_dict(data)


def validate_canonical_stems(package_dir: Path, result: SeparationResult,
                             expected_frames: int) -> list[str]:
    """canonical package 音频级硬约束（spec §5）。需要 `pfs` extra。

    expected_frames：输入音频的帧数（44.1 kHz 下），由调用方解码输入后提供。
    """
    import numpy as np
    import soundfile as sf

    errors: list[str] = []
    stems = result.stems or {}
    for name in CANONICAL_STEMS:
        rel = stems.get(name)
        if rel is None:
            errors.append(f"{name}: result.stems 缺少该轨")
            continue
        path = package_dir / rel
        if not path.exists():
            errors.append(f"{name}: 文件不存在 {rel}")
            continue
        try:
            info = sf.info(str(path))
            data, sr = sf.read(str(path), dtype="float32", always_2d=True)
        except Exception as exc:  # noqa: BLE001 —— 损坏文件统一转错误条目
            errors.append(f"{name}: 无法读取（{exc}）")
            continue
        if info.subtype != "FLOAT":
            errors.append(f"{name}: subtype={info.subtype}，要求 32-bit float (FLOAT)")
        if sr != CANONICAL_SAMPLE_RATE:
            errors.append(f"{name}: sample_rate={sr}，要求 {CANONICAL_SAMPLE_RATE}")
        if data.shape[1] != CANONICAL_CHANNELS:
            errors.append(f"{name}: channels={data.shape[1]}，要求 {CANONICAL_CHANNELS}")
        if len(data) == 0:
            errors.append(f"{name}: 空音频")
            continue
        if abs(len(data) - expected_frames) > 1:
            errors.append(f"{name}: 长度 {len(data)} frames，"
                          f"与输入 {expected_frames} 误差超过 1 sample")
        if not np.isfinite(data).all():
            errors.append(f"{name}: 含 NaN/Inf")
        else:
            peak = float(np.abs(data).max())
            if peak > MAX_ABS_PEAK:
                errors.append(f"{name}: 峰值 {peak:.3f} 超过 {MAX_ABS_PEAK}")
    return errors
