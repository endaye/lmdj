#!/usr/bin/env python3
"""Contract and deterministic-container tests for lmdj.project-bundle.v1."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "tools" / "project-bundle" / "project_bundle.py"
SCHEMA_PATH = (
    REPO_ROOT / "contracts" / "project" / "lmdj.project-bundle.v1.schema.json"
)
PROJECT_V3_SCHEMA_PATH = (
    REPO_ROOT / "contracts" / "project" / "lmdj.project.v3.schema.json"
)
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "contracts"
PROJECT_ID = "12345678-1234-4123-8123-123456789abc"

assert TOOL_PATH.is_file(), f"missing Project Bundle tool: {TOOL_PATH}"
assert SCHEMA_PATH.is_file(), f"missing Project Bundle Contract: {SCHEMA_PATH}"

spec = importlib.util.spec_from_file_location("project_bundle", TOOL_PATH)
assert spec is not None and spec.loader is not None
project_bundle = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = project_bundle
spec.loader.exec_module(project_bundle)

sys.path.insert(0, str(REPO_ROOT / "tests" / "conformance"))
import json_schema  # noqa: E402


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def write_project(source: Path) -> None:
    (source / "assets").mkdir(parents=True)
    (source / "history" / "checkpoints").mkdir(parents=True)
    (source / "history" / "transactions").mkdir(parents=True)
    (source / "recovery" / "active").mkdir(parents=True)
    (source / "recovery" / "sealed").mkdir(parents=True)
    manifest = {
        "contract": "lmdj.project.manifest.v1",
        "head_checkpoint": "history/checkpoints/0.json",
        "head_revision": 0,
        "transactions": [],
    }
    checkpoint = {
        "contract": "lmdj.project.v3",
        "project_id": PROJECT_ID,
    }
    (source / "manifest.json").write_bytes(
        project_bundle.canonical_json(manifest) + b"\n"
    )
    (source / "history" / "checkpoints" / "0.json").write_bytes(
        project_bundle.canonical_json(checkpoint) + b"\n"
    )
    (source / "assets" / "kick.wav").write_bytes(b"RIFF-test-kick")


def make_index(entries: list[dict], total: int) -> dict:
    index = {
        "bundle_digest": "0" * 64,
        "compression": "none",
        "contract": "lmdj.project-bundle.v1",
        "contract_version": "1.1.0",
        "entries": entries,
        "project_contract": "lmdj.project.v3",
        "project_id": PROJECT_ID,
        "uncompressed_bytes": total,
    }
    index["bundle_digest"] = project_bundle.bundle_digest(index)
    return index


def entry(path: str, payload: bytes, offset: int) -> dict:
    return {
        "bytes": len(payload),
        "offset": offset,
        "path": path,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def write_bundle(path: Path, index: dict, payload: bytes = b"") -> None:
    index_bytes = project_bundle.canonical_json(index)
    path.write_bytes(
        project_bundle.MAGIC
        + len(index_bytes).to_bytes(4, "big")
        + index_bytes
        + payload
    )


def expect_invalid(path: Path, fragment: str) -> None:
    try:
        project_bundle.read_bundle(path)
    except project_bundle.BundleError as error:
        assert fragment in str(error), (fragment, str(error))
    else:
        raise AssertionError(f"expected invalid bundle mentioning {fragment!r}")


def test_schema_and_fixtures() -> None:
    schema = load_json(SCHEMA_PATH)
    valid = load_json(FIXTURE_ROOT / "project-bundle-valid.json")
    invalid = load_json(
        FIXTURE_ROOT / "project-bundle-invalid-traversal.json"
    )
    json_schema.check(valid, schema, "project-bundle-valid")
    errors = json_schema.validate(invalid, schema)
    assert any("does not match pattern" in error for error in errors), errors


def test_v3_project_truth_fixture_is_canonical_and_tick_native() -> None:
    schema = load_json(PROJECT_V3_SCHEMA_PATH)
    project = load_json(FIXTURE_ROOT / "project-v3-valid.json")
    json_schema.check(project, schema, "project-v3-valid")
    assert project["contract"] == "lmdj.project.v3"
    assert "takes" not in project
    assert isinstance(project["assets"], list)
    assert isinstance(project["patterns"], list)
    for pattern in project["patterns"]:
        loop_length = pattern["bars"] * 3840
        for event in pattern["events"]:
            assert "step" not in event
            assert 0 <= event["onset_tick"] < loop_length
            assert 1 <= event["duration_tick"] <= (
                loop_length - event["onset_tick"]
            )
    encoded = project_bundle.canonical_json(project)
    assert encoded == project_bundle.canonical_json(json.loads(encoded))


def test_pack_header_digest_payload_and_determinism(root: Path) -> None:
    source = root / "project.lmdj"
    source.mkdir()
    write_project(source)
    first = root / "first.lmdj"
    second = root / "second.lmdj"
    first_digest = project_bundle.pack_directory(source, first)
    second_digest = project_bundle.pack_directory(source, second)
    assert first.read_bytes() == second.read_bytes()
    assert first_digest == second_digest

    raw = first.read_bytes()
    assert raw[:8] == b"LMDJBND1"
    index_size = int.from_bytes(raw[8:12], "big")
    index_bytes = raw[12 : 12 + index_size]
    index = json.loads(index_bytes)
    digest_source = dict(index)
    del digest_source["bundle_digest"]
    assert index_bytes == project_bundle.canonical_json(index)
    assert index["bundle_digest"] == hashlib.sha256(
        project_bundle.canonical_json(digest_source)
    ).hexdigest()
    assert index["bundle_digest"] == first_digest
    assert index["project_id"] == PROJECT_ID
    assert index["project_contract"] == "lmdj.project.v3"
    assert [item["path"] for item in index["entries"]] == sorted(
        item["path"] for item in index["entries"]
    )

    verified, payload_offset = project_bundle.read_bundle(first)
    assert verified == index
    assert payload_offset == 12 + index_size
    for item in verified["entries"]:
        begin = payload_offset + item["offset"]
        payload = raw[begin : begin + item["bytes"]]
        assert hashlib.sha256(payload).hexdigest() == item["sha256"]


def test_cli(root: Path) -> None:
    source = root / "cli-project.lmdj"
    source.mkdir()
    write_project(source)
    output = root / "cli-output.lmdj"
    packed = subprocess.run(
        [
            sys.executable,
            str(TOOL_PATH),
            "pack",
            "--source",
            str(source),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert packed.returncode == 0, packed.stderr
    assert packed.stdout.strip() == project_bundle.read_bundle(output)[0][
        "bundle_digest"
    ]
    verified = subprocess.run(
        [sys.executable, str(TOOL_PATH), "verify", str(output)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert verified.returncode == 0, verified.stderr
    assert verified.stdout.strip() == packed.stdout.strip()


def test_index_and_payload_rejections(root: Path) -> None:
    payload = b"ab"
    valid_entries = [entry("a", b"a", 0), entry("b", b"b", 1)]
    valid_index = make_index(valid_entries, len(payload))

    for contract in ("lmdj.project.v1", "lmdj.project.v2"):
        legacy = copy.deepcopy(valid_index)
        legacy["project_contract"] = contract
        legacy["bundle_digest"] = project_bundle.bundle_digest(legacy)
        path = root / f"valid-{contract}.lmdj"
        write_bundle(path, legacy, payload)
        assert project_bundle.read_bundle(path)[0]["project_contract"] == contract

    cases: list[tuple[str, dict, bytes, str]] = []
    unsupported = copy.deepcopy(valid_index)
    unsupported["project_contract"] = "lmdj.project.v4"
    unsupported["bundle_digest"] = project_bundle.bundle_digest(unsupported)
    cases.append(("project-contract", unsupported, payload, "unsupported"))
    invalid_paths = {
        "absolute": "/manifest.json",
        "dotdot": "history/../manifest.json",
        "dot": "history/./manifest.json",
        "empty-segment": "history//manifest.json",
        "backslash": "history\\manifest.json",
        "nul": "history/manifest\0.json",
        "non-ascii": "history/café.json",
    }
    for name, invalid_path in invalid_paths.items():
        mutated = copy.deepcopy(valid_index)
        mutated["entries"][0]["path"] = invalid_path
        mutated["bundle_digest"] = project_bundle.bundle_digest(mutated)
        cases.append((name, mutated, payload, "path"))

    duplicate = copy.deepcopy(valid_index)
    duplicate["entries"][1]["path"] = duplicate["entries"][0]["path"]
    duplicate["bundle_digest"] = project_bundle.bundle_digest(duplicate)
    cases.append(("duplicate", duplicate, payload, "duplicate"))

    casefold = copy.deepcopy(valid_index)
    casefold["entries"][0]["path"] = "A"
    casefold["entries"][1]["path"] = "a"
    casefold["bundle_digest"] = project_bundle.bundle_digest(casefold)
    cases.append(("casefold", casefold, payload, "case-fold"))

    gap = copy.deepcopy(valid_index)
    gap["entries"][1]["offset"] = 2
    gap["bundle_digest"] = project_bundle.bundle_digest(gap)
    cases.append(("gap", gap, payload, "contiguous"))

    overlap = copy.deepcopy(valid_index)
    overlap["entries"][1]["offset"] = 0
    overlap["bundle_digest"] = project_bundle.bundle_digest(overlap)
    cases.append(("overlap", overlap, payload, "contiguous"))

    wrong_hash = copy.deepcopy(valid_index)
    wrong_hash["entries"][0]["sha256"] = "0" * 64
    wrong_hash["bundle_digest"] = project_bundle.bundle_digest(wrong_hash)
    cases.append(("hash", wrong_hash, payload, "payload hash"))

    for name, index, case_payload, fragment in cases:
        path = root / f"invalid-{name}.lmdj"
        write_bundle(path, index, case_payload)
        expect_invalid(path, fragment)

    trailing = root / "invalid-trailing.lmdj"
    write_bundle(trailing, valid_index, payload + b"x")
    expect_invalid(trailing, "trailing")

    noncanonical = root / "invalid-noncanonical.lmdj"
    encoded = json.dumps(valid_index, sort_keys=True).encode("utf-8")
    noncanonical.write_bytes(
        project_bundle.MAGIC
        + len(encoded).to_bytes(4, "big")
        + encoded
        + payload
    )
    expect_invalid(noncanonical, "canonical")


def test_limit_rejections(root: Path) -> None:
    too_many_entries = [
        {
            "bytes": 0,
            "offset": 0,
            "path": f"entry-{number:04d}",
            "sha256": hashlib.sha256(b"").hexdigest(),
        }
        for number in range(project_bundle.MAX_ENTRIES + 1)
    ]
    too_many = root / "invalid-entry-count.lmdj"
    write_bundle(too_many, make_index(too_many_entries, 0))
    expect_invalid(too_many, "entry count")

    oversized_index = root / "invalid-index-size.lmdj"
    oversized_index.write_bytes(
        project_bundle.MAGIC
        + (project_bundle.MAX_INDEX_BYTES + 1).to_bytes(4, "big")
        + b"x" * (project_bundle.MAX_INDEX_BYTES + 1)
    )
    expect_invalid(oversized_index, "index exceeds")

    oversized_entry = root / "invalid-entry-size.lmdj"
    large_entry = {
        "bytes": project_bundle.MAX_ENTRY_BYTES + 1,
        "offset": 0,
        "path": "large",
        "sha256": "0" * 64,
    }
    write_bundle(
        oversized_entry,
        make_index([large_entry], project_bundle.MAX_ENTRY_BYTES + 1),
    )
    expect_invalid(oversized_entry, "entry exceeds")

    total_entries = []
    offset = 0
    for number in range(8):
        total_entries.append(
            {
                "bytes": project_bundle.MAX_ENTRY_BYTES,
                "offset": offset,
                "path": f"large-{number}",
                "sha256": "0" * 64,
            }
        )
        offset += project_bundle.MAX_ENTRY_BYTES
    total_entries.append(
        {
            "bytes": 1,
            "offset": offset,
            "path": "overflow",
            "sha256": "0" * 64,
        }
    )
    oversized_total = root / "invalid-total-size.lmdj"
    write_bundle(oversized_total, make_index(total_entries, offset + 1))
    expect_invalid(oversized_total, "payload exceeds")


def test_pack_rejects_unsafe_tree(root: Path) -> None:
    source = root / "unsafe.lmdj"
    source.mkdir()
    write_project(source)

    outside = root / "outside"
    outside.write_bytes(b"outside")
    symlink = source / "assets" / "escape.wav"
    symlink.symlink_to(outside)
    try:
        project_bundle.pack_directory(source, root / "symlink.lmdj")
    except project_bundle.BundleError as error:
        assert "symlink" in str(error)
    else:
        raise AssertionError("expected symlink rejection")
    symlink.unlink()

    hardlink = source / "assets" / "hardlink.wav"
    os.link(source / "assets" / "kick.wav", hardlink)
    try:
        project_bundle.pack_directory(source, root / "hardlink.lmdj")
    except project_bundle.BundleError as error:
        assert "hardlink" in str(error)
    else:
        raise AssertionError("expected hardlink rejection")
    hardlink.unlink()

    fifo = source / "assets" / "pipe"
    os.mkfifo(fifo)
    try:
        project_bundle.pack_directory(source, root / "fifo.lmdj")
    except project_bundle.BundleError as error:
        assert "regular file" in str(error)
    else:
        raise AssertionError("expected special-file rejection")
    fifo.unlink()

    redirected_parent = root / "redirected-output"
    redirected_parent.symlink_to(source / "assets", target_is_directory=True)
    try:
        project_bundle.pack_directory(
            source, redirected_parent / "inside-source.lmdj"
        )
    except project_bundle.BundleError as error:
        assert "inside the source Project" in str(error)
    else:
        raise AssertionError("expected resolved output-parent rejection")


def main() -> None:
    test_schema_and_fixtures()
    test_v3_project_truth_fixture_is_canonical_and_tick_native()
    with tempfile.TemporaryDirectory(prefix="lmdj-project-bundle-test-") as raw:
        root = Path(raw)
        test_pack_header_digest_payload_and_determinism(root)
        test_cli(root)
        test_index_and_payload_rejections(root)
        test_limit_rejections(root)
        test_pack_rejects_unsafe_tree(root)
    print("project bundle contract tests: PASS")


if __name__ == "__main__":
    main()
