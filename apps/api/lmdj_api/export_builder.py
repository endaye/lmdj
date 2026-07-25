from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SOURCE_SCHEMA = "lmdj.creator-export-source.v1"
EXPORT_SCHEMA = "lmdj.creator-export.v1"
SOURCE_FILENAME = "export-source.json"
_SAFE_PATCH_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_CANONICAL_STEM_NAMES = frozenset({
    "bass.wav",
    "drums.wav",
    "other.wav",
    "vocals.wav",
})
_STREAM_CHUNK_BYTES = 1024 * 1024


class ExportIncomplete(Exception):
    def __init__(self, missing: list[str]) -> None:
        self.missing = list(missing)
        super().__init__(f"Creator export incomplete: {', '.join(self.missing)}")


@dataclass(frozen=True)
class _ExportFile:
    source_path: str
    archive_path: str
    path: Path


@dataclass(frozen=True)
class CreatorExportStatus:
    status: str
    downloadable: bool
    items: dict[str, dict[str, Any]]
    missing: list[str]
    warnings: list[str]
    music: dict[str, Any]
    _patch_id: str | None = field(default=None, repr=False)
    _files: dict[str, tuple[_ExportFile, ...]] = field(
        default_factory=dict,
        repr=False,
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "downloadable": self.downloadable,
            "items": self.items,
            "missing": self.missing,
            "warnings": self.warnings,
            "music": self.music,
        }


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _partial_without_source() -> CreatorExportStatus:
    missing = [SOURCE_FILENAME]
    return CreatorExportStatus(
        status="partial",
        downloadable=False,
        items={
            "stems": {"status": "missing", "paths": []},
            "samples": {"status": "missing", "paths": []},
            "midi": {"status": "missing", "paths": []},
            "music": {"status": "missing", "missing": missing},
        },
        missing=missing,
        warnings=[],
        music={},
    )


def _read_source(package_root: Path) -> dict[str, Any] | None:
    source_path = package_root / SOURCE_FILENAME
    resolved_source = source_path.resolve()
    if (
        resolved_source == package_root
        or not resolved_source.is_relative_to(package_root)
    ):
        raise ValueError(f"unsafe export source path: {SOURCE_FILENAME}")
    if not resolved_source.is_file():
        return None
    try:
        source = json.loads(resolved_source.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {SOURCE_FILENAME}") from error
    if not isinstance(source, dict) or source.get("schema") != SOURCE_SCHEMA:
        raise ValueError(f"invalid {SOURCE_FILENAME} schema")
    return source


def _source_paths(source: dict[str, Any], field_name: str) -> list[str]:
    values = source.get(field_name)
    if not isinstance(values, list) or any(
        not isinstance(value, str) or not value
        for value in values
    ):
        raise ValueError(f"invalid export source {field_name}")
    return values


def _safe_source_file(
    package_root: Path,
    source_path: str,
    archive_path: str,
) -> _ExportFile:
    relative = Path(source_path)
    if (
        not source_path
        or "\x00" in source_path
        or "\\" in source_path
        or relative.is_absolute()
        or ".." in relative.parts
        or relative == Path(".")
    ):
        raise ValueError(f"unsafe export source path: {source_path}")
    resolved = (package_root / relative).resolve()
    if resolved == package_root or not resolved.is_relative_to(package_root):
        raise ValueError(f"unsafe export source path: {source_path}")
    return _ExportFile(
        source_path=relative.as_posix(),
        archive_path=archive_path,
        path=resolved,
    )


def _inventory_files(
    package_root: Path,
    values: list[str],
    group: str,
) -> tuple[_ExportFile, ...]:
    files: list[_ExportFile] = []
    archive_sources: dict[str, str] = {}
    seen_sources: set[str] = set()
    for value in values:
        relative = Path(value)
        archive_path = f"{group}/{relative.name}"
        candidate = _safe_source_file(package_root, value, archive_path)
        previous = archive_sources.get(archive_path)
        if previous is not None and previous != candidate.source_path:
            raise ValueError(
                "archive path collision: "
                f"{previous} and {candidate.source_path} -> {archive_path}",
            )
        archive_sources[archive_path] = candidate.source_path
        if candidate.source_path not in seen_sources:
            seen_sources.add(candidate.source_path)
            files.append(candidate)
    return tuple(files)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _music_missing(music: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    bpm = music.get("bpm")
    if not _is_number(bpm) or bpm <= 0:
        missing.append("music.bpm")

    key = music.get("key")
    if (
        not isinstance(key, dict)
        or not isinstance(key.get("value"), str)
        or not key["value"].strip()
        or not _is_number(key.get("confidence"))
    ):
        missing.append("music.key")

    time_signature = music.get("time_signature")
    if (
        not isinstance(time_signature, dict)
        or not isinstance(time_signature.get("numerator"), int)
        or isinstance(time_signature.get("numerator"), bool)
        or time_signature["numerator"] <= 0
        or not isinstance(time_signature.get("denominator"), int)
        or isinstance(time_signature.get("denominator"), bool)
        or time_signature["denominator"] <= 0
        or not isinstance(time_signature.get("source"), str)
        or not time_signature["source"]
    ):
        missing.append("music.time_signature")

    loop = music.get("loop")
    if not isinstance(loop, dict):
        missing.append("music.loop")
    else:
        required_loop_fields = ("seconds", "steps", "beats", "bars")
        if any(
            not _is_number(loop.get(name)) or loop[name] <= 0
            for name in required_loop_fields
        ):
            missing.append("music.loop")
    return missing


def _load_patch_id(patch_file: _ExportFile) -> str:
    try:
        patch = json.loads(patch_file.path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("invalid patch.json") from error
    patch_id = patch.get("patch_id") if isinstance(patch, dict) else None
    if (
        not isinstance(patch_id, str)
        or not _SAFE_PATCH_ID.fullmatch(patch_id)
        or Path(patch_id).name != patch_id
    ):
        raise ValueError("unsafe patch_id")
    return patch_id


def inspect_creator_export(package_dir: Path) -> CreatorExportStatus:
    package_root = package_dir.resolve()
    if not package_root.is_dir():
        raise ValueError(f"Creator package does not exist: {package_dir}")
    source = _read_source(package_root)
    if source is None:
        return _partial_without_source()

    patch_source = source.get("patch")
    if not isinstance(patch_source, str) or not patch_source:
        raise ValueError("invalid export source patch")
    patch_file = _safe_source_file(
        package_root,
        patch_source,
        "patch.json",
    )
    stems = _inventory_files(
        package_root,
        _source_paths(source, "stems"),
        "stems",
    )
    samples = _inventory_files(
        package_root,
        _source_paths(source, "samples"),
        "samples",
    )
    midi = _inventory_files(
        package_root,
        _source_paths(source, "midi"),
        "midi",
    )

    source_warnings = source.get("warnings")
    if not isinstance(source_warnings, list) or any(
        not isinstance(warning, str)
        for warning in source_warnings
    ):
        raise ValueError("invalid export source warnings")
    warnings = list(source_warnings)
    missing: list[str] = []

    patch_id: str | None = None
    real_patch: tuple[_ExportFile, ...] = ()
    if patch_file.path.is_file():
        patch_id = _load_patch_id(patch_file)
        real_patch = (patch_file,)
    else:
        missing.append(patch_file.source_path)

    real_stems = tuple(file for file in stems if file.path.is_file())
    missing_stems = [file for file in stems if not file.path.is_file()]
    for file in missing_stems:
        warnings.append(f"optional stem unavailable: {file.source_path}")
    available_stem_names = {Path(file.archive_path).name for file in real_stems}
    absent_canonical_stems = sorted(_CANONICAL_STEM_NAMES - available_stem_names)
    if not stems:
        warnings.append("optional stems unavailable")
    elif absent_canonical_stems:
        names = ", ".join(name.removesuffix(".wav") for name in absent_canonical_stems)
        warnings.append(f"optional stems unavailable: {names}")
    if not real_stems:
        stem_status = "missing"
    elif missing_stems or absent_canonical_stems:
        stem_status = "review"
    else:
        stem_status = "ready"

    real_samples = tuple(file for file in samples if file.path.is_file())
    missing_samples = [file for file in samples if not file.path.is_file()]
    for file in missing_samples:
        warnings.append(f"sample unavailable: {file.source_path}")
    missing.extend(file.source_path for file in missing_samples)
    if not real_samples:
        missing.append("samples")
        sample_status = "missing"
    elif missing_samples:
        sample_status = "missing"
    else:
        sample_status = "ready"

    real_midi = tuple(file for file in midi if file.path.is_file())
    missing_midi = [file for file in midi if not file.path.is_file()]
    if not midi:
        missing.append("midi")
    else:
        missing.extend(file.source_path for file in missing_midi)
    midi_status = "ready" if real_midi and not missing_midi else "missing"

    music = source.get("music")
    if not isinstance(music, dict):
        music = {}
    missing_music = _music_missing(music)
    missing.extend(missing_music)
    music_status = "missing" if missing_music else "ready"

    missing = _unique(missing)
    warnings = _unique(warnings)
    status = "partial" if missing else "complete"
    return CreatorExportStatus(
        status=status,
        downloadable=not missing,
        items={
            "stems": {
                "status": stem_status,
                "paths": sorted(file.archive_path for file in real_stems),
            },
            "samples": {
                "status": sample_status,
                "paths": sorted(file.archive_path for file in real_samples),
            },
            "midi": {
                "status": midi_status,
                "paths": sorted(file.archive_path for file in real_midi),
            },
            "music": {
                "status": music_status,
                "missing": missing_music,
            },
        },
        missing=missing,
        warnings=warnings,
        music=music,
        _patch_id=patch_id,
        _files={
            "patch": real_patch,
            "stems": real_stems,
            "samples": real_samples,
            "midi": real_midi,
        },
    )


def _manifest_entry(file: _ExportFile) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    try:
        with file.path.open("rb") as source:
            while chunk := source.read(_STREAM_CHUNK_BYTES):
                size += len(chunk)
                digest.update(chunk)
    except OSError as error:
        raise ExportIncomplete([file.source_path]) from error
    return {
        "path": file.archive_path,
        "bytes": size,
        "sha256": digest.hexdigest(),
    }


def _zip_info(archive_path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(
        archive_path,
        date_time=(1980, 1, 1, 0, 0, 0),
    )
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _write_asset(archive: zipfile.ZipFile, file: _ExportFile) -> None:
    try:
        with (
            file.path.open("rb") as source,
            archive.open(_zip_info(file.archive_path), "w", force_zip64=True) as target,
        ):
            shutil.copyfileobj(source, target, length=_STREAM_CHUNK_BYTES)
    except OSError as error:
        raise ExportIncomplete([file.source_path]) from error


def build_creator_export(package_dir: Path, output_dir: Path) -> Path:
    inspection = inspect_creator_export(package_dir)
    if not inspection.downloadable:
        raise ExportIncomplete(inspection.missing)
    if inspection._patch_id is None:
        raise ExportIncomplete(["patch.json"])

    patch_file = inspection._files["patch"][0]
    stems = sorted(inspection._files["stems"], key=lambda file: file.archive_path)
    samples = sorted(inspection._files["samples"], key=lambda file: file.archive_path)
    midi = sorted(inspection._files["midi"], key=lambda file: file.archive_path)
    file_manifest = {
        "patch": _manifest_entry(patch_file),
        "stems": [_manifest_entry(file) for file in stems],
        "samples": [_manifest_entry(file) for file in samples],
        "midi": [_manifest_entry(file) for file in midi],
        "takes": [],
    }
    manifest = {
        "schema": EXPORT_SCHEMA,
        "status": "complete",
        "patch_id": inspection._patch_id,
        "music": inspection.music,
        "files": file_manifest,
        "warnings": inspection.warnings,
    }
    manifest_payload = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()

    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"creator-export-{inspection._patch_id}.zip"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output_dir,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w") as archive:
            archive.writestr(_zip_info("manifest.json"), manifest_payload)
            _write_asset(archive, patch_file)
            for file in sorted(
                (*stems, *samples, *midi),
                key=lambda candidate: candidate.archive_path,
            ):
                _write_asset(archive, file)
        os.replace(temporary, output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return output
