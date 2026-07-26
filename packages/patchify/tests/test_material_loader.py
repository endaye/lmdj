import json
import shutil
from pathlib import Path

import pytest

from lmdj_patchify.material_loader import load_material_package

FIXTURE = Path(__file__).parent / "fixtures" / "material-package"


def test_loads_valid_material_package():
    loaded = load_material_package(FIXTURE)
    assert loaded.package.schema == "lmdj.materials.v1"
    assert len(loaded.package.materials) == 4


def test_rejects_missing_or_escaping_asset(tmp_path):
    package = tmp_path / "package"
    shutil.copytree(FIXTURE, package)
    (package / "samples" / "kick-a.wav").unlink()
    with pytest.raises(ValueError, match="missing material audio"):
        load_material_package(package)

    shutil.rmtree(package)
    shutil.copytree(FIXTURE, package)
    data = json.loads((package / "materials.json").read_text())
    data["materials"][0]["audio_path"] = "../outside.wav"
    (package / "materials.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="invalid materials"):
        load_material_package(package)


def test_runtime_loader_rejects_unknown_contract_fields(tmp_path):
    package = tmp_path / "package"
    shutil.copytree(FIXTURE, package)
    data = json.loads((package / "materials.json").read_text())
    data["materials"][0]["unreviewed_field"] = True
    (package / "materials.json").write_text(json.dumps(data))

    with pytest.raises(ValueError, match="Additional properties"):
        load_material_package(package)
