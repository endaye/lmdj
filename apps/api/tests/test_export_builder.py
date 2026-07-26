from __future__ import annotations

import hashlib
import importlib
import json
import os
import zipfile
from pathlib import Path

import pytest


def _builder():
    return importlib.import_module("lmdj_api.export_builder")


def _write_package(
    root: Path,
    *,
    key: dict[str, object] | None = None,
    stems: tuple[str, ...] = ("stems/drums.wav",),
    samples: tuple[str, ...] = ("samples/kick.wav",),
    midi: tuple[str, ...] = ("chart.mid",),
    patch_id: str = "night-bloom-ab12cd34",
) -> Path:
    package = root / "package"
    package.mkdir(parents=True)
    patch = {
        "schema": "lmdj.patch.v1",
        "patch_id": patch_id,
    }
    (package / "patch.json").write_text(
        json.dumps(patch, ensure_ascii=False, separators=(",", ":")),
    )
    payloads = {
        **{path: f"stem:{path}".encode() for path in stems},
        **{path: f"sample:{path}".encode() for path in samples},
        **{path: f"midi:{path}".encode() for path in midi},
    }
    for relative, payload in payloads.items():
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    source = {
        "schema": "lmdj.creator-export-source.v1",
        "patch": "patch.json",
        "stems": list(stems),
        "samples": list(samples),
        "midi": list(midi),
        "music": {
            "bpm": 89.1,
            "key": key or {"value": "A minor", "confidence": 0.72},
            "time_signature": {
                "numerator": 4,
                "denominator": 4,
                "source": "fixed-v1",
            },
            "loop": {
                "seconds": 10.6696,
                "steps": 64,
                "beats": 16,
                "bars": 4,
            },
        },
        "warnings": [],
    }
    (package / "export-source.json").write_text(
        json.dumps(source, ensure_ascii=False, separators=(",", ":")),
    )
    return package


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_inspection_reports_complete_export_and_only_real_optional_stems(
    tmp_path: Path,
) -> None:
    package = _write_package(
        tmp_path,
        stems=("stems/drums.wav", "stems/vocals.wav"),
    )
    (package / "stems/vocals.wav").unlink()

    status = _builder().inspect_creator_export(package)

    assert status.status == "complete"
    assert status.downloadable is True
    assert status.missing == []
    assert status.items == {
        "stems": {"status": "review", "paths": ["stems/drums.wav"]},
        "samples": {"status": "ready", "paths": ["samples/kick.wav"]},
        "midi": {"status": "ready", "paths": ["midi/chart.mid"]},
        "music": {"status": "ready", "missing": []},
    }
    assert status.music["bpm"] == 89.1
    assert status.music["key"] == {"value": "A minor", "confidence": 0.72}
    assert "optional stem unavailable: stems/vocals.wav" in status.warnings


def test_build_writes_stable_manifest_inventory_and_zip_metadata(
    tmp_path: Path,
) -> None:
    package = _write_package(tmp_path)

    output = _builder().build_creator_export(package, tmp_path / "exports")

    assert output.name == "creator-export-night-bloom-ab12cd34.zip"
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == [
            "manifest.json",
            "patch.json",
            "midi/chart.mid",
            "samples/kick.wav",
            "stems/drums.wav",
        ]
        for info in archive.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.external_attr >> 16 == 0o100644
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["schema"] == "lmdj.creator-export.v1"
        assert manifest["status"] == "complete"
        assert manifest["patch_id"] == "night-bloom-ab12cd34"
        assert manifest["files"]["takes"] == []
        expected = {
            "patch": ["patch.json"],
            "stems": ["stems/drums.wav"],
            "samples": ["samples/kick.wav"],
            "midi": ["midi/chart.mid"],
        }
        for group, archive_paths in expected.items():
            entries = (
                [manifest["files"][group]]
                if group == "patch"
                else manifest["files"][group]
            )
            assert [entry["path"] for entry in entries] == archive_paths
            for entry in entries:
                payload = archive.read(entry["path"])
                assert entry["bytes"] == len(payload)
                assert entry["sha256"] == hashlib.sha256(payload).hexdigest()


def test_material_export_includes_real_timing_artifact(tmp_path: Path) -> None:
    package = _write_package(tmp_path)
    (package / "timing.json").write_text('{"schema":"lmdj.timing.v1"}')
    source_path = package / "export-source.json"
    source = json.loads(source_path.read_text())
    source["timing"] = ["timing.json"]
    source_path.write_text(json.dumps(source))

    status = _builder().inspect_creator_export(package)
    output = _builder().build_creator_export(package, tmp_path / "exports")

    assert status.items["timing"] == {
        "status": "ready",
        "paths": ["timing/timing.json"],
    }
    with zipfile.ZipFile(output) as archive:
        assert "timing/timing.json" in archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["files"]["timing"][0]["path"] == "timing/timing.json"


def test_repeated_builds_have_identical_sha256(tmp_path: Path) -> None:
    package = _write_package(tmp_path)

    first = _builder().build_creator_export(package, tmp_path / "exports-a")
    os.utime(package / "samples/kick.wav", None)
    second = _builder().build_creator_export(package, tmp_path / "exports-b")

    assert _sha256(first) == _sha256(second)


def test_build_streams_assets_without_path_read_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _write_package(
        tmp_path,
        stems=("stems/drums.wav", "stems/vocals.wav"),
        samples=("samples/kick.wav", "samples/snare.wav"),
    )
    original_read_bytes = Path.read_bytes

    def reject_asset_read_bytes(path: Path) -> bytes:
        if path.resolve().is_relative_to(package.resolve()):
            pytest.fail(f"asset loaded wholesale: {path}")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_asset_read_bytes)

    output = _builder().build_creator_export(package, tmp_path / "exports")

    with zipfile.ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        for group in ("patch", "stems", "samples", "midi"):
            entries = (
                [manifest["files"][group]]
                if group == "patch"
                else manifest["files"][group]
            )
            for entry in entries:
                payload = archive.read(entry["path"])
                assert entry["bytes"] == len(payload)
                assert entry["sha256"] == hashlib.sha256(payload).hexdigest()


def test_build_uses_one_shared_inspection_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _write_package(tmp_path)
    builder = _builder()
    original = builder.inspect_creator_export
    calls: list[Path] = []

    def inspect_once(package_dir: Path):
        calls.append(package_dir)
        return original(package_dir)

    monkeypatch.setattr(builder, "inspect_creator_export", inspect_once)

    builder.build_creator_export(package, tmp_path / "exports")

    assert calls == [package]


def test_build_replaces_output_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _write_package(tmp_path)
    builder = _builder()
    real_replace = builder.os.replace
    replacements: list[tuple[Path, Path]] = []

    def replace(source: str | Path, destination: str | Path) -> None:
        replacements.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(builder.os, "replace", replace)

    output = builder.build_creator_export(package, tmp_path / "exports")

    assert replacements == [(replacements[0][0], output)]
    temporary, destination = replacements[0]
    assert temporary.parent == destination.parent
    assert temporary != destination
    assert not temporary.exists()


@pytest.mark.parametrize(
    ("field", "unsafe"),
    [
        ("patch", "../outside.json"),
        ("samples", "/tmp/outside.wav"),
        ("midi", "midi/../../outside.mid"),
    ],
)
def test_inspection_rejects_path_traversal(
    tmp_path: Path,
    field: str,
    unsafe: str,
) -> None:
    package = _write_package(tmp_path)
    source_path = package / "export-source.json"
    source = json.loads(source_path.read_text())
    source[field] = unsafe if field == "patch" else [unsafe]
    source_path.write_text(json.dumps(source))

    with pytest.raises(ValueError, match="unsafe export source path"):
        _builder().inspect_creator_export(package)


def test_inspection_rejects_symlink_outside_package(tmp_path: Path) -> None:
    package = _write_package(tmp_path)
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"private")
    sample = package / "samples/kick.wav"
    sample.unlink()
    sample.symlink_to(outside)

    with pytest.raises(ValueError, match="unsafe export source path"):
        _builder().inspect_creator_export(package)


def test_inspection_rejects_export_source_symlink_outside_package(
    tmp_path: Path,
) -> None:
    package = _write_package(tmp_path)
    source_path = package / "export-source.json"
    outside = tmp_path / "outside-source.json"
    source_path.replace(outside)
    source_path.symlink_to(outside)

    with pytest.raises(ValueError, match="unsafe export source path"):
        _builder().inspect_creator_export(package)

    with pytest.raises(ValueError, match="unsafe export source path"):
        _builder().build_creator_export(package, tmp_path / "exports")
    assert not (tmp_path / "exports").exists()


def test_inspection_rejects_archive_basename_collisions(tmp_path: Path) -> None:
    package = _write_package(
        tmp_path,
        samples=("samples/kick.wav", "alternate/kick.wav"),
    )

    with pytest.raises(ValueError, match="archive path collision"):
        _builder().inspect_creator_export(package)


def test_inspection_rejects_unsafe_patch_id(tmp_path: Path) -> None:
    package = _write_package(tmp_path, patch_id="../stolen")

    with pytest.raises(ValueError, match="unsafe patch_id"):
        _builder().inspect_creator_export(package)


@pytest.mark.parametrize(
    ("mutation", "missing"),
    [
        ("patch", "patch.json"),
        ("key", "music.key"),
        ("midi", "chart.mid"),
        ("samples", "samples"),
    ],
)
def test_incomplete_required_inputs_do_not_build(
    tmp_path: Path,
    mutation: str,
    missing: str,
) -> None:
    package = _write_package(tmp_path)
    if mutation == "patch":
        (package / "patch.json").unlink()
    elif mutation == "key":
        source_path = package / "export-source.json"
        source = json.loads(source_path.read_text())
        source["music"]["key"] = None
        source_path.write_text(json.dumps(source))
    elif mutation == "midi":
        (package / "chart.mid").unlink()
    else:
        (package / "samples/kick.wav").unlink()

    with pytest.raises(_builder().ExportIncomplete) as caught:
        _builder().build_creator_export(package, tmp_path / "exports")

    assert missing in caught.value.missing
    assert not (tmp_path / "exports").exists()


def test_any_missing_inventoried_sample_blocks_export(tmp_path: Path) -> None:
    package = _write_package(
        tmp_path,
        samples=("samples/kick.wav", "samples/snare.wav"),
    )
    (package / "samples/snare.wav").unlink()

    status = _builder().inspect_creator_export(package)

    assert status.status == "partial"
    assert status.downloadable is False
    assert status.items["samples"] == {
        "status": "missing",
        "paths": ["samples/kick.wav"],
    }
    assert "samples/snare.wav" in status.missing
    with pytest.raises(_builder().ExportIncomplete) as caught:
        _builder().build_creator_export(package, tmp_path / "exports")
    assert "samples/snare.wav" in caught.value.missing
    assert not (tmp_path / "exports").exists()
