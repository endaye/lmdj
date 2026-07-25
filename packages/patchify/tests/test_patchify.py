import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from lmdj_core_models.model import load_patch_schema
from lmdj_patchify.patchify import patchify_package


def test_patchify_package_writes_valid_patch_json(golden_package: Path):
    patch = patchify_package(golden_package)
    data = json.loads((golden_package / "patch.json").read_text())

    jsonschema.validate(data, load_patch_schema())          # 输出必须过 schema
    assert data["schema"] == "lmdj.patch.v1"
    assert data["patch_id"].startswith("testsong-")
    assert len(data["patch_id"].split("-")[-1]) == 8        # 内容 hash 短前缀
    assert data["patterns"][0]["length_steps"] == patch.patterns[0].length_steps
    assert data["patterns"][0]["notes"], "patterns must carry normalized notes"
    assert data["scenes"][0]["pattern_ids"] == ["pattern_original"]
    assert len(data["pads"]) == 16
    assert [pad["index"] for pad in data["pads"]] == list(range(16))
    assert all(pad["action"] == "empty" for pad in data["pads"][8:16])
    assert data["scenes"][0]["pad_indexes"] == list(range(16))

    element_ids = {e["element_id"] for e in data["elements"]}
    mapped = {eid for pad in data["pads"] for eid in pad["behavior"].get("element_ids", [])}
    assert set(data["metadata"]["unmapped_element_ids"]) == element_ids - mapped


def test_patchify_is_deterministic(golden_package: Path, tmp_path: Path):
    out_a, out_b = tmp_path / "a.json", tmp_path / "b.json"
    patchify_package(golden_package, out_a)
    patchify_package(golden_package, out_b)
    assert out_a.read_bytes() == out_b.read_bytes()


def test_patchify_rejects_loops_profile(golden_package: Path):
    raw = json.loads((golden_package / "lanes.json").read_text())
    # 从 golden 派生：把所有 lane 改名为 loop_*（ABC/DEF 包形态），pitch/sample 不变
    for i, row in enumerate(raw["lanes"]):
        new_name = f"loop_{chr(ord('a') + i)}"
        sample_path = golden_package / row["sample"]
        new_rel = f"samples/{new_name}.wav"
        sample_path.rename(golden_package / new_rel)
        row.update(name=new_name, kind="long", sample=new_rel)
    (golden_package / "lanes.json").write_text(json.dumps(raw))

    with pytest.raises(ValueError, match="unsupported package profile"):
        patchify_package(golden_package)


def test_cli_writes_custom_output_path(golden_package: Path):
    out_path = golden_package / "custom-patch.json"

    result = subprocess.run(
        [sys.executable, "-m", "lmdj_patchify.cli", str(golden_package), "--out", str(out_path)],
        check=True,
        text=True,
        capture_output=True,
    )

    data = json.loads(out_path.read_text())
    assert data["patch_id"].startswith("testsong-")
    assert str(out_path) in result.stdout
