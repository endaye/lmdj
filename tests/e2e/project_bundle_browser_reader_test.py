#!/usr/bin/env python3
"""Import a Bundle the product packed with the browser reader, not a literal.

#900: `packages/web-runtime-platform/web/project_bundle_reader.mjs` was the
fourth independent copy of the Bundle level enumeration. #784 moved the other
three -- the Contract, the Python packer and the C++ importer -- to `1.2.0`
and `lmdj.project.v4` and left the browser behind, so the Creator refused every
Project this Build creates before a byte crossed the Host bridge. Nothing
caught it because every reader test on both sides of the bridge authored its
own index: `e2e.project_bundle_writer_level` packs a real Project and stops at
the packer, and the browser suite validated a shape it invented.

This test closes that loop. It drives the real CLI Host, packs what that Host
left on disk with the shipped packer, and feeds those exact bytes to the
browser reader module under Node. A level move that misses any one of the four
copies fails here.
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
HARNESS_PATH = Path(__file__).resolve().parent / "project_bundle_browser_reader.mjs"
AUDIO_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "audio" / "kick.wav"
TIMEOUT_SECONDS = 60
PROJECT_ID = "00000000-0000-4000-8000-000000000011"
ASSET_ID = "00000000-0000-4000-8000-000000000111"
PATTERN_ID = "00000000-0000-4000-8000-000000000021"

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


def create_project(executable: Path, assembly: Path, run_root: Path) -> Path:
    workspace = run_root / "workspace"
    workspace.mkdir(parents=True)
    project = run_root / "browser-reader.lmdj"
    cli_command(executable, workspace, assembly, {
        "operation": "project.create",
        "project_path": str(project),
        "project_id": PROJECT_ID,
        "bpm": 120,
    })
    cli_command(executable, workspace, assembly, {
        "operation": "asset.import",
        "project_path": str(project),
        "command_id": "00000000-0000-4000-8000-000000000201",
        "expected_revision": 0,
        "asset_id": ASSET_ID,
        "source_path": str(AUDIO_FIXTURE),
        "media_type": "audio/wav",
    })
    cli_command(executable, workspace, assembly, {
        "operation": "pad.assign",
        "project_path": str(project),
        "command_id": "00000000-0000-4000-8000-000000000202",
        "expected_revision": 1,
        "slot": {"bank": 0, "pad": 0},
        "asset_id": ASSET_ID,
    })
    cli_command(executable, workspace, assembly, {
        "operation": "pattern.create",
        "project_path": str(project),
        "command_id": "00000000-0000-4000-8000-000000000203",
        "expected_revision": 2,
        "pattern_id": PATTERN_ID,
        "bars": 1,
    })
    return project


def main() -> None:
    executable = Path(sys.argv[1])
    assembly = Path(sys.argv[2])
    run_root = Path(sys.argv[3])
    node = shutil.which("node")
    assert node is not None, (
        "why: this case proves the browser Bundle reader accepts what the "
        "product packs, so it needs Node on PATH. Remedy: install Node 26, "
        "the version every Core CI lane provisions."
    )
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True)

    project = create_project(executable, assembly, run_root)
    head = json.loads(
        (project / "manifest.json").read_text(encoding="utf-8")
    )["head_checkpoint"]
    written_contract = json.loads(
        (project / head).read_text(encoding="utf-8")
    )["contract"]

    bundle = run_root / "browser-reader.bundle"
    project_bundle.pack_directory(project, bundle)
    index, _ = project_bundle.read_bundle(bundle)

    request_path = run_root / "request.json"
    request_path.write_text(json.dumps({
        "bundle_path": str(bundle),
        # Read from the packed file by the packer itself, so the browser
        # reader has to reproduce this index rather than be handed it.
        "identity": {
            "project_id": index["project_id"],
            "bundle_digest": index["bundle_digest"],
            "entry_count": len(index["entries"]),
        },
        "summary": {
            "project_id": index["project_id"],
            "pattern_id": PATTERN_ID,
            "revision": 3,
            "bpm": 120,
            "asset_count": 1,
            "assigned_pad_count": 1,
            "bundle_digest": index["bundle_digest"],
        },
    }, sort_keys=True), encoding="utf-8")

    completed = subprocess.run(
        [node, str(HARNESS_PATH), str(request_path)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )
    assert completed.returncode == 0, (
        "why: the browser Project Bundle reader refused a Bundle the shipped "
        f"packer wrote for a Project the shipped CLI created at "
        f"{written_contract} / {index['contract_version']}. Importing a "
        "Bundle is the only way a browser acquires a Project, so this refusal "
        "means no Project this Build creates can be opened in the Creator. "
        "Remedy: the Bundle container version and Project Contract level are "
        "enumerated in contracts/project/lmdj.project-bundle.v1.schema.json, "
        "tools/project-bundle/project_bundle.py, Project I/O's parse_index "
        "and packages/web-runtime-platform/web/project_bundle_reader.mjs -- "
        "move all four in the same cut (#900).\n"
        f"{completed.stderr.strip()}"
    )
    result = json.loads(completed.stdout)

    assert result["operations"][0] == "project.import.begin", result
    assert result["operations"][-1] == "project.import.commit", result
    assert "project.import.abort" not in result["operations"], result
    assert result["project_id"] == index["project_id"], result
    assert result["bundle_digest"] == index["bundle_digest"], result
    assert index["project_contract"] == written_contract, (
        written_contract, index["project_contract"]
    )
    print(
        "project bundle browser reader test: PASS "
        f"({written_contract} at {index['contract_version']}, "
        f"{len(index['entries'])} entries imported)"
    )


if __name__ == "__main__":
    main()
