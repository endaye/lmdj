#!/usr/bin/env python3
"""Validate original bytes locally, or authenticate the complete deployed corpus."""
import argparse
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
from urllib.request import Request, urlopen
import wave
import kit
sys.path.insert(0, str(kit.ROOT / "tests/conformance"))
import json_schema

def validate(files):
    index = json.loads(files["catalog/index.json"])
    json_schema.check(index, json.loads((kit.ROOT / "contracts/soundset-catalog/lmdj.soundset-catalog.v1.schema.json").read_text()), "default catalog")
    assert len(index["entries"]) == 1
    entry = index["entries"][0]
    raw = files[f'manifest/{entry["manifest_sha256"]}']
    assert kit.digest(raw) == entry["manifest_sha256"]
    manifest = json.loads(raw)
    json_schema.check(manifest, json.loads((kit.ROOT / "contracts/soundset/lmdj.soundset.v1.schema.json").read_text()), "default manifest")
    assert kit.canonical(manifest) == raw
    assert manifest["set_id"] == entry["set_id"] == kit.SET_ID
    assert manifest["version"] == entry["version"]
    assert manifest["license"]["spdx_id"] == "CC0-1.0"
    assert entry["license_summary"] == {key: manifest["license"][key] for key in ("spdx_id", "rights_holder")}
    assert [slot["slot"] for slot in manifest["slots"]] == list(range(16))
    unique = {}
    for slot in manifest["slots"]:
        artifact = slot["artifact"]
        data = files[f'blob/{artifact["sha256"]}']
        assert len(data) == artifact["byte_length"] and kit.digest(data) == artifact["sha256"]
        with wave.open(io.BytesIO(data), "rb") as wav:
            assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 48000)
            frames = wav.getnframes(); pcm = wav.readframes(frames)
            assert 0 < frames <= 48000 * 2
            values = struct.unpack("<" + "h" * frames, pcm)
            assert max(abs(value) for value in values) > 1000
            assert values[0] == values[-1] == 0
        unique[artifact["sha256"]] = len(data)
    assert len(unique) == 16, "each Pad needs a distinct original sound"
    assert len(raw) + sum(unique.values()) == entry["total_bytes"], "Catalog total includes the authenticated manifest and unique blobs"
    return entry

def live(origin):
    from urllib.parse import urlsplit
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.username:
        raise ValueError("live verification needs an absolute HTTPS origin")
    origin = origin.rstrip("/")
    expected = kit.check()
    for name, data in expected.items():
        route = "/catalog/index.json" if name == "catalog/index.json" else "/object/" + name
        with urlopen(Request(origin + route, headers={"Cache-Control": "no-cache"}), timeout=30) as response:
            observed = response.read(len(data) + 1)
            if observed != data: raise ValueError(f"deployed bytes mismatch at {route}")
            assert response.headers.get("Access-Control-Allow-Origin") == "*"
            if name != "catalog/index.json": assert "immutable" in response.headers.get("Cache-Control", "")
    with urlopen(origin + "/health", timeout=30) as response:
        assert json.load(response) == {"service": "lmdj-default-assets", "ok": True}
    print(f"live default assets: {len(expected)} objects authenticated at {origin}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--live")
    args = parser.parse_args()
    validate(kit.check())
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for name, data in kit.build().items():
            target = root / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        assert kit.check(root) == kit.check()
        first = next((root / "blob").iterdir())
        first.write_bytes(first.read_bytes()[:-1] + b"X")
        try: kit.check(root)
        except ValueError: pass
        else: raise AssertionError("mutated corpus was admitted")
    print("default kit: schema, rights, 16 distinct WAVs, hashes, totals and regeneration verified")
    if args.live: live(args.live)
