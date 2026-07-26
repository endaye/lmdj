from __future__ import annotations

import json
from pathlib import Path

from lmdj_core_models.materials import (
    MaterialPackage,
    validate_material_package,
)


def write_material_package(root: Path, package: MaterialPackage) -> Path:
    validate_material_package(package)
    output = root / "materials.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            package.to_dict(),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    )
    temporary.replace(output)
    return output
