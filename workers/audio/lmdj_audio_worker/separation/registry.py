"""checkpoint registry（spec §6）：workers/audio/config/separators.json 的加载与门禁校验。"""
from __future__ import annotations

import json
import string
from dataclasses import dataclass
from pathlib import Path

REGISTRY_SCHEMA_VERSION = "lmdj.separators.v1"
ENTRY_STATUSES = ("experimental", "verified", "production")
ALLOWED_DEVICES = ("cpu", "mps")
COMMAND_PLACEHOLDERS = ("input", "output_dir", "device",
                        "checkpoint_dir", "seed", "repeat_id")
_REQUIRED_FIELDS = ("id", "family", "runner", "command", "source",
                    "artifact_sha256", "license", "stems", "sample_rate",
                    "channels", "devices", "inference", "env_lock_sha256",
                    "status")


class RegistryError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class SeparatorEntry:
    id: str
    family: str
    runner: str
    command: tuple[str, ...]
    source_url: str
    source_revision: str
    artifact_sha256: str
    license_code: str
    license_weights: str
    stems: tuple[str, ...]
    sample_rate: int
    channels: int
    devices: tuple[str, ...]
    inference: dict
    env_lock_sha256: str
    status: str


def _is_sha256(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def _command_placeholders(command: list) -> set[str]:
    names: set[str] = set()
    for part in command:
        for _, field_name, _, _ in string.Formatter().parse(part):
            if field_name:
                names.add(field_name)
    return names


def _validate_entry(raw: object, index: int) -> list[str]:
    prefix = f"separators[{index}]"
    if not isinstance(raw, dict):
        return [f"{prefix}: 必须是 object"]
    errors = []
    for f in _REQUIRED_FIELDS:
        if f not in raw:
            errors.append(f"{prefix}: 缺少必填字段 {f}")
    for f in raw:
        if f not in _REQUIRED_FIELDS:
            errors.append(f"{prefix}: 未知字段 {f!r}")
    if errors:
        return errors
    eid = raw["id"]
    if not isinstance(eid, str) or not eid:
        errors.append(f"{prefix}: id 必须是非空字符串")
    if not _is_sha256(raw["artifact_sha256"]):
        errors.append(f"{prefix}({eid}): artifact_sha256 必须是 64 位十六进制")
    if not _is_sha256(raw["env_lock_sha256"]):
        errors.append(f"{prefix}({eid}): env_lock_sha256 必须是 64 位十六进制")
    src = raw["source"]
    if not isinstance(src, dict) or not src.get("url") or not src.get("revision"):
        errors.append(f"{prefix}({eid}): source 必须含 url 与不可变 revision")
    lic = raw["license"]
    if not isinstance(lic, dict) or not lic.get("code") or not lic.get("weights"):
        errors.append(f"{prefix}({eid}): license 必须含 code 与 weights 说明")
    if raw["status"] not in ENTRY_STATUSES:
        errors.append(f"{prefix}({eid}): status 必须属于 {ENTRY_STATUSES}，"
                      f"收到 {raw['status']!r}")
    cmd = raw["command"]
    if (not isinstance(cmd, list) or not cmd
            or not all(isinstance(p, str) for p in cmd)):
        errors.append(f"{prefix}({eid}): command 必须是非空字符串列表")
    else:
        unknown = _command_placeholders(cmd) - set(COMMAND_PLACEHOLDERS)
        if unknown:
            errors.append(f"{prefix}({eid}): command 含未知占位符 {sorted(unknown)}，"
                          f"允许 {COMMAND_PLACEHOLDERS}")
    if (not isinstance(raw["stems"], list) or not raw["stems"]
            or not all(isinstance(s, str) for s in raw["stems"])):
        errors.append(f"{prefix}({eid}): stems 必须是非空字符串列表")
    devices = raw["devices"]
    if not isinstance(devices, list) or not devices:
        errors.append(f"{prefix}({eid}): devices 必须是非空列表")
    else:
        for d in devices:
            if d not in ALLOWED_DEVICES:
                errors.append(f"{prefix}({eid}): 不支持的设备 {d!r}"
                              f"（首轮只有 {ALLOWED_DEVICES}）")
    if not isinstance(raw["inference"], dict):
        errors.append(f"{prefix}({eid}): inference 推理配置必须是 object（spec §6）")
    return errors


def load_registry(path: Path) -> tuple[SeparatorEntry, ...]:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError([f"无法读取 registry {path}: {exc}"]) from exc
    errors: list[str] = []
    if not isinstance(data, dict) or data.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        errors.append(f"registry schema_version 必须是 {REGISTRY_SCHEMA_VERSION!r}")
    raw_entries = data.get("separators") if isinstance(data, dict) else None
    if not isinstance(raw_entries, list):
        errors.append("registry 必须含 separators 列表")
        raise RegistryError(errors)
    for i, raw in enumerate(raw_entries):
        errors.extend(_validate_entry(raw, i))
    ids = [e["id"] for e in raw_entries if isinstance(e, dict) and "id" in e]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"registry: 重复 ID {dup!r}")
    if errors:
        raise RegistryError(errors)
    return tuple(
        SeparatorEntry(
            id=e["id"], family=e["family"], runner=e["runner"],
            command=tuple(e["command"]),
            source_url=e["source"]["url"], source_revision=e["source"]["revision"],
            artifact_sha256=e["artifact_sha256"],
            license_code=e["license"]["code"], license_weights=e["license"]["weights"],
            stems=tuple(e["stems"]), sample_rate=e["sample_rate"],
            channels=e["channels"], devices=tuple(e["devices"]),
            inference=e["inference"], env_lock_sha256=e["env_lock_sha256"],
            status=e["status"],
        )
        for e in raw_entries
    )


def benchmark_entries(entries: tuple[SeparatorEntry, ...]) -> tuple[SeparatorEntry, ...]:
    """internal benchmark 允许全部状态（spec §6 状态语义）。"""
    return tuple(entries)


def production_entries(entries: tuple[SeparatorEntry, ...]) -> tuple[SeparatorEntry, ...]:
    return tuple(e for e in entries if e.status == "production")
