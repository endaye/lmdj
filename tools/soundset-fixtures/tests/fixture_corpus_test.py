#!/usr/bin/env python3
"""The committed Sound Set fixture corpus is reproducible and self-consistent.

Two obligations:

1. every committed byte comes back out of `generate.py` unchanged, so the
   corpus can be regenerated instead of hand-patched;
2. the corpus really carries the cases Stage 11 Tasks 4, 5 and 7 need — the
   canonical-byte identity of S11-D1, the unique-byte accounting of S11-D7,
   one S8-D6 violation, one content mismatch, and one catalog
   `license_summary` that disagrees with its manifest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile

tool_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(tool_root))

import generate  # noqa: E402
from soundset_fixtures import (  # noqa: E402
    BLOBS,
    LICENSE_SUMMARY_OVERRIDES,
    SET_SPECS,
    TAMPERED_DECLARED_BLOB,
    TAMPERED_SERVED_BLOB,
    canonical_json_bytes,
    sha256_hex,
)

repository_root = tool_root.parents[1]
corpus_root = repository_root / "tests" / "fixtures" / "soundset"

SPDX_ALLOWLIST = {"CC0-1.0", "CC-BY-4.0"}
ROLES = {
    "kick",
    "snare",
    "clap",
    "hat_closed",
    "hat_open",
    "perc",
    "cymbal",
    "bass",
    "melody",
    "chord",
    "vocal",
    "fx",
    "other",
}
SUPPORTED_SAMPLE_RATES = {44_100, 48_000}

expected = generate.build_corpus()

# --------------------------------------------------------------------------
# 1. Reproducibility
# --------------------------------------------------------------------------

committed = generate.committed_files(corpus_root)
problems = generate.differences(expected, committed)
assert not problems, "corpus is not reproducible:\n" + "\n".join(problems)
assert committed, "no committed corpus files were found"

# Regenerating into an empty tree must produce the same bytes again, so the
# generator is independent of whatever already sits on disk.
with tempfile.TemporaryDirectory(prefix="lmdj-soundset-regen-") as staging:
    staging_root = Path(staging)
    generate.write(staging_root, generate.build_corpus())
    assert not generate.differences(
        committed, generate.committed_files(staging_root)
    ), "a fresh generation does not match the committed corpus"

# --------------------------------------------------------------------------
# 2. Content addressing
# --------------------------------------------------------------------------

declared_tampered_sha256 = sha256_hex(BLOBS[TAMPERED_DECLARED_BLOB].build())
declared_tampered_length = len(BLOBS[TAMPERED_DECLARED_BLOB].build())
served_tampered_bytes = BLOBS[TAMPERED_SERVED_BLOB].build()

manifest_names = sorted(
    name.split("/", 1)[1] for name in committed if name.startswith("manifest/")
)
blob_names = sorted(
    name.split("/", 1)[1] for name in committed if name.startswith("blob/")
)
assert len(manifest_names) == len(SET_SPECS), manifest_names
assert blob_names, blob_names

for digest in manifest_names:
    payload = committed[f"manifest/{digest}"]
    assert len(digest) == 64 and digest == digest.lower(), digest
    # S11-D1: the stored object is its own canonical form, hashed over exactly
    # those bytes, with no trailing newline.
    assert sha256_hex(payload) == digest, digest
    assert not payload.endswith(b"\n"), digest
    assert payload == canonical_json_bytes(json.loads(payload)), digest

for digest in blob_names:
    payload = committed[f"blob/{digest}"]
    assert len(digest) == 64 and digest == digest.lower(), digest
    if digest == declared_tampered_sha256:
        continue
    assert sha256_hex(payload) == digest, digest

# The tampered blob is the one deliberate exception, and it must fail both
# the hash check and the length check.
tampered_path = f"blob/{declared_tampered_sha256}"
assert tampered_path in committed, "the tampered blob case is missing"
tampered_bytes = committed[tampered_path]
assert tampered_bytes == served_tampered_bytes
assert sha256_hex(tampered_bytes) != declared_tampered_sha256
assert len(tampered_bytes) != declared_tampered_length

# --------------------------------------------------------------------------
# 3. Manifest shape and the audio cases
# --------------------------------------------------------------------------


def wav_format(payload: bytes) -> tuple[int, int, int, int]:
    """Return (audio_format, channels, sample_rate, bits) from a RIFF/WAVE."""
    assert payload[:4] == b"RIFF" and payload[8:12] == b"WAVE"
    offset = 12
    while offset + 8 <= len(payload):
        identifier = payload[offset : offset + 4]
        size = struct.unpack_from("<I", payload, offset + 4)[0]
        body = payload[offset + 8 : offset + 8 + size]
        if identifier == b"fmt ":
            audio_format, channels, sample_rate = struct.unpack_from(
                "<HHI", body, 0
            )
            bits = struct.unpack_from("<H", body, 14)[0]
            return audio_format, channels, sample_rate, bits
        offset += 8 + size + (size % 2)
    raise AssertionError("WAV fixture has no fmt chunk")


manifests = {
    json.loads(committed[f"manifest/{digest}"])["set_id"]: json.loads(
        committed[f"manifest/{digest}"]
    )
    for digest in manifest_names
}
assert len(manifests) == len(SET_SPECS), "set_id values must be unique"

observed_rates: set[int] = set()
observed_channels: set[int] = set()
s8_d6_violations = 0
duplicate_artifact_sets = 0
demo_sets = 0
demo_reusing_a_slot_artifact = 0

for manifest in manifests.values():
    assert manifest["contract"] == "lmdj.soundset.v1"
    slots = manifest["slots"]
    assert len(slots) == 16, manifest["set_id"]
    assert sorted(slot["slot"] for slot in slots) == list(range(16))
    license_block = manifest["license"]
    assert set(license_block) == {
        "spdx_id",
        "rights_holder",
        "copyright",
        "attribution",
    }, manifest["set_id"]
    assert license_block["rights_holder"] and license_block["copyright"]

    occupied = [slot for slot in slots if "artifact" in slot]
    assert occupied, manifest["set_id"]
    assert any("artifact" not in slot for slot in slots), (
        f"{manifest['set_id']} has no empty slot; S11-D12 needs one"
    )

    references = [slot["artifact"]["sha256"] for slot in occupied]
    if len(references) != len(set(references)):
        duplicate_artifact_sets += 1

    # S11-D5: the optional set-level demo Artifact. It is a plain Artifact ref
    # under the same S8-D6 constraints, so it is stored and checked like any
    # slot's Artifact.
    demo = manifest.get("demo")
    if demo is not None:
        demo_sets += 1
        assert set(demo) == {"sha256", "media_type", "byte_length"}, demo
        assert demo["media_type"] == "audio/wav"
        demo_stored = committed.get(f"blob/{demo['sha256']}")
        assert demo_stored is not None, f"missing demo blob {demo['sha256']}"
        assert demo["byte_length"] == len(demo_stored), demo
        audio_format, channels, sample_rate, bits = wav_format(demo_stored)
        assert audio_format == 1, demo
        assert sample_rate in SUPPORTED_SAMPLE_RATES, demo
        assert bits == 16 and channels in (1, 2), demo
        if demo["sha256"] in set(references):
            demo_reusing_a_slot_artifact += 1

    for slot in occupied:
        assert slot["role"] in ROLES, slot
        assert slot["name"]
        artifact = slot["artifact"]
        assert set(artifact) == {"sha256", "media_type", "byte_length"}
        assert artifact["media_type"] == "audio/wav"
        stored = committed.get(f"blob/{artifact['sha256']}")
        assert stored is not None, f"missing blob {artifact['sha256']}"
        if artifact["sha256"] == declared_tampered_sha256:
            continue
        assert artifact["byte_length"] == len(stored), artifact
        audio_format, channels, sample_rate, bits = wav_format(stored)
        assert audio_format == 1, artifact
        if (
            sample_rate not in SUPPORTED_SAMPLE_RATES
            or bits != 16
            or channels not in (1, 2)
        ):
            s8_d6_violations += 1
            continue
        observed_rates.add(sample_rate)
        observed_channels.add(channels)

assert observed_rates == SUPPORTED_SAMPLE_RATES, observed_rates
assert observed_channels == {1, 2}, observed_channels
assert s8_d6_violations >= 1, "no S8-D6-invalid blob case"
assert duplicate_artifact_sets >= 1, (
    "no Set reuses one Artifact across two slots; S11-D7 unique-byte "
    "accounting has nothing to bite on"
)
assert demo_sets >= 1, (
    "no Set carries a set-level demo Artifact; S11-D5 preview has nothing "
    "to play"
)
assert demo_reusing_a_slot_artifact >= 1, (
    "no Set's demo reuses a slot Artifact hash, so S11-D7's "
    "'downloaded once, counted once' rule across the demo and the slots has "
    "no witness in the corpus"
)

# --------------------------------------------------------------------------
# 4. Catalog index
# --------------------------------------------------------------------------

index_bytes = committed["catalog/index.json"]
assert not index_bytes.endswith(b"\n")
index = json.loads(index_bytes)
assert index_bytes == canonical_json_bytes(index)
assert index["contract"] == "lmdj.soundset-catalog.v1"
entries = index["entries"]
assert len(entries) == len(SET_SPECS), entries

mismatched_summaries = 0
matched_summaries = 0
allowlisted = set()

for entry in entries:
    manifest_bytes = committed[f"manifest/{entry['manifest_sha256']}"]
    manifest = json.loads(manifest_bytes)
    assert manifest["set_id"] == entry["set_id"]
    assert manifest["version"] == entry["version"]
    assert entry["name"] == manifest["name"]
    assert entry["publisher"] == manifest["publisher"]
    assert set(entry["license_summary"]) == {"spdx_id", "rights_holder"}

    roles = sorted(
        {slot["role"] for slot in manifest["slots"] if "artifact" in slot}
    )
    assert entry["roles_summary"] == roles, entry["set_id"]

    # S11-D7: canonical manifest bytes plus each unique blob's declared
    # byte_length, counted exactly once. The set-level demo joins the same
    # unique set, so a demo that reuses a slot Artifact adds nothing.
    unique = {
        slot["artifact"]["sha256"]: slot["artifact"]["byte_length"]
        for slot in manifest["slots"]
        if "artifact" in slot
    }
    if "demo" in manifest:
        unique[manifest["demo"]["sha256"]] = manifest["demo"]["byte_length"]
    assert entry["total_bytes"] == len(manifest_bytes) + sum(unique.values()), (
        entry["set_id"]
    )

    summary = entry["license_summary"]
    if (
        summary["spdx_id"] == manifest["license"]["spdx_id"]
        and summary["rights_holder"] == manifest["license"]["rights_holder"]
    ):
        matched_summaries += 1
    else:
        mismatched_summaries += 1

    if manifest["license"]["spdx_id"] in SPDX_ALLOWLIST:
        allowlisted.add(manifest["license"]["spdx_id"])

assert matched_summaries >= 1, "no catalog entry agrees with its manifest"
assert mismatched_summaries == len(LICENSE_SUMMARY_OVERRIDES), (
    "the deliberate license_summary mismatch case is missing"
)
assert allowlisted == SPDX_ALLOWLIST, (
    f"both v1 allowlisted licenses must appear: {allowlisted}"
)

# One CC-BY-4.0 Set must carry a non-empty attribution, and one must not.
by_attributions = {
    bool(manifest["license"]["attribution"])
    for manifest in manifests.values()
    if manifest["license"]["spdx_id"] == "CC-BY-4.0"
}
assert by_attributions == {True, False}, by_attributions

# --------------------------------------------------------------------------
# 5. Contract Schema, once Stage 11 Task 1 has landed the Schemas
# --------------------------------------------------------------------------

soundset_schema = (
    repository_root / "contracts" / "soundset" / "lmdj.soundset.v1.schema.json"
)
catalog_schema = (
    repository_root
    / "contracts"
    / "soundset-catalog"
    / "lmdj.soundset-catalog.v1.schema.json"
)
if soundset_schema.is_file() and catalog_schema.is_file():
    sys.path.insert(0, str(repository_root / "tests" / "conformance"))
    import json_schema  # noqa: E402

    schema = json.loads(soundset_schema.read_text(encoding="utf-8"))
    for digest in manifest_names:
        json_schema.check(
            json.loads(committed[f"manifest/{digest}"]),
            schema,
            f"soundset manifest {digest}",
        )
    json_schema.check(
        index,
        json.loads(catalog_schema.read_text(encoding="utf-8")),
        "soundset catalog index",
    )
    print("soundset fixture corpus tests: PASS (schemas validated)")
else:
    print("soundset fixture corpus tests: PASS (schemas not yet in tree)")
