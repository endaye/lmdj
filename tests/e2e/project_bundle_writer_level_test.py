#!/usr/bin/env python3
"""Pack a Project the product actually created, not one this test invented.

#784: `lmdj.project-bundle.v1` enumerated `project_contract` up to
`lmdj.project.v3` while Project I/O had moved its writer to
`lmdj.project.v4`, so no Project the product created could be packed. The
Contract suite stayed green because it packed a synthetic v3 checkpoint it
wrote itself. This test drives the real CLI Host, then packs and verifies what
that Host left on disk, so the same class of gap fails here first.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "tools" / "project-bundle" / "project_bundle.py"
TIMEOUT_SECONDS = 60

spec = importlib.util.spec_from_file_location("project_bundle", TOOL_PATH)
assert spec is not None and spec.loader is not None
project_bundle = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = project_bundle
spec.loader.exec_module(project_bundle)


def cli_command(
    executable: Path, workspace: Path, assembly: Path, request: dict
) -> dict:
    completed = subprocess.run(
        [
            str(executable),
            "--workspace",
            str(workspace),
            "--assembly",
            str(assembly),
            "command",
            "--request",
            json.dumps(request, sort_keys=True, separators=(",", ":")),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )
    assert completed.returncode == 0, (completed.returncode, completed.stderr)
    response = json.loads(completed.stdout)
    assert response["ok"] is True, response
    return response


def main() -> None:
    executable = Path(sys.argv[1])
    assembly = Path(sys.argv[2])
    run_root = Path(sys.argv[3])
    if run_root.exists():
        shutil.rmtree(run_root)
    (run_root / "workspace").mkdir(parents=True)
    workspace = run_root / "workspace"
    project = run_root / "bundle-writer-level.lmdj"

    cli_command(
        executable,
        workspace,
        assembly,
        {
            "operation": "project.create",
            "project_path": str(project),
            "project_id": "00000000-0000-4000-8000-000000000001",
            "bpm": 120,
        },
    )

    head = json.loads(
        (project / "manifest.json").read_text(encoding="utf-8")
    )["head_checkpoint"]
    written_contract = json.loads(
        (project / head).read_text(encoding="utf-8")
    )["contract"]

    output = run_root / "bundle-writer-level.bundle"
    digest = project_bundle.pack_directory(project, output)
    index, _ = project_bundle.read_bundle(output)

    assert index["project_contract"] == written_contract, (
        "why: the CLI Host persisted "
        f"{written_contract!r} but the packed Bundle names "
        f"{index['project_contract']!r}. Remedy: widen "
        "contracts/project/lmdj.project-bundle.v1.schema.json, "
        "project_bundle.PROJECT_CONTRACTS and Project I/O's parse_index "
        "allowlist in the same cut that moves the writer."
    )
    assert index["bundle_digest"] == digest
    assert index["contract_version"] == project_bundle.CONTRACT_VERSION
    print(
        "project bundle writer-level test: PASS "
        f"({written_contract} packed at {index['contract_version']})"
    )


if __name__ == "__main__":
    main()
