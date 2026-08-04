#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_TOOL = REPO_ROOT / "apps/web-runtime-host/tools/package.py"
DEFAULT_DIST = Path(
    os.environ.get("LMDJ_WEB_HOST_DIST_ROOT", REPO_ROOT / "build/web/host/dist")
)


def load_package_module():
    spec = importlib.util.spec_from_file_location("lmdj_web_package", PACKAGE_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError("package module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


class DistributionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_package_module()
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-web-dist-")
        self.root = Path(self.temporary.name) / "dist"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_valid_distribution(self, content: bytes = b"export {};\n") -> None:
        assets = self.root / "assets"
        assets.mkdir(exist_ok=True)
        digest = hashlib.sha256(content).hexdigest()
        asset_path = assets / f"runtime.{digest}.js"
        asset_path.write_bytes(content)
        manifest = {
            "manifest_version": 1,
            "product_build": "1.0.13.0",
            "host_version": "1.0.0",
            "protocol_version": 1,
            "heap_bytes": 536_870_912,
            "resource_limits": {
                "imported_wav_bytes": 1_048_576,
                "decoded_frames_per_pad": 240_000,
                "decoded_float_pcm_bytes_per_bank": 67_108_864,
                "decoded_float_pcm_bytes_total": 134_217_728,
            },
            "emscripten": {
                "emsdk_tag": "6.0.5",
                "emsdk_revision": "dfb9d1a46c3bb8f52e1e6324be23123b9d73c190",
                "emscripten_releases_revision": "dbd755b5da399329c2576f6e3dfa7f419f5d8409",
                "emcc_version": "emcc 6.0.5",
            },
            "assets": [
                {
                    "path": asset_path.relative_to(self.root).as_posix(),
                    "bytes": len(content),
                    "sha256": digest,
                    "role": "runtime_script",
                }
            ],
        }
        manifest_bytes = canonical_json(manifest)
        (self.root / "host-manifest.json").write_bytes(manifest_bytes)
        manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
        (self.root / "index.html").write_text(
            "<!doctype html><html><head>"
            f'<meta name="lmdj-host-manifest-sha256" content="{manifest_digest}">'
            f'<script src="./{asset_path.relative_to(self.root).as_posix()}"></script>'
            "</head></html>",
            encoding="utf-8",
            newline="\n",
        )

    def test_built_distribution_is_clean(self) -> None:
        self.module.verify_distribution(DEFAULT_DIST, REPO_ROOT)

    def test_missing_hashed_asset_and_manifest_mismatch_are_rejected(self) -> None:
        self.write_valid_distribution()
        asset = next((self.root / "assets").iterdir())
        asset.unlink()
        with self.assertRaisesRegex(self.module.DistributionError, "missing asset"):
            self.module.verify_distribution(self.root, REPO_ROOT)

        shutil.rmtree(self.root)
        self.root.mkdir()
        self.write_valid_distribution()
        asset = next((self.root / "assets").iterdir())
        original = asset.read_bytes()
        asset.write_bytes(bytes([original[0] ^ 1]) + original[1:])
        with self.assertRaisesRegex(self.module.DistributionError, "asset hash mismatch"):
            self.module.verify_distribution(self.root, REPO_ROOT)

    def test_source_maps_sources_fixtures_server_and_dependencies_are_rejected(self) -> None:
        forbidden = {
            "assets/runtime.js.map": "source map",
            "assets/source.cpp": "source file",
            "tests/fixture.wav": "test fixture",
            "server.py": "proof server",
            "node_modules/dev-package/index.js": "development dependency",
            "package.json": "development dependency",
        }
        for relative, label in forbidden.items():
            with self.subTest(label=label):
                shutil.rmtree(self.root)
                self.root.mkdir()
                self.write_valid_distribution()
                path = self.root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"forbidden")
                with self.assertRaises(self.module.DistributionError):
                    self.module.verify_distribution(self.root, REPO_ROOT)

    def test_absolute_local_paths_are_rejected_even_when_asset_hash_matches(self) -> None:
        content = b'const leaked = "/Users/example/private/build";\n'
        self.write_valid_distribution(content)
        with self.assertRaisesRegex(self.module.DistributionError, "absolute local path"):
            self.module.verify_distribution(self.root, REPO_ROOT)


if __name__ == "__main__":
    unittest.main()
