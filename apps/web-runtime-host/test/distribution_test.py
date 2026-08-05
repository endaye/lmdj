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
        shutil.copytree(DEFAULT_DIST, self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def reset_distribution(self) -> None:
        shutil.rmtree(self.root)
        shutil.copytree(DEFAULT_DIST, self.root)

    def rewrite_manifest(self, mutate) -> dict:
        manifest_path = self.root / "host-manifest.json"
        old_bytes = manifest_path.read_bytes()
        manifest = json.loads(old_bytes)
        mutate(manifest)
        manifest_bytes = canonical_json(manifest)
        manifest_path.write_bytes(manifest_bytes)
        old_digest = hashlib.sha256(old_bytes).hexdigest()
        manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
        index_path = self.root / "index.html"
        index = index_path.read_text(encoding="utf-8").replace(
            old_digest, manifest_digest
        )
        index_path.write_text(index, encoding="utf-8", newline="\n")
        return manifest

    def test_built_distribution_is_clean(self) -> None:
        self.module.verify_distribution(DEFAULT_DIST, REPO_ROOT)
        manifest = json.loads((DEFAULT_DIST / "host-manifest.json").read_bytes())
        self.assertEqual(len(manifest["assets"]), 9)
        self.assertEqual(
            len([
                asset for asset in manifest["assets"]
                if asset["path"].startswith("assets/diagnostic-project.")
                and asset["path"].endswith(".mjs")
            ]),
            1,
        )
        self.assertFalse(any(DEFAULT_DIST.rglob("*.wav")))
        self.assertEqual(
            manifest["distribution_contract"],
            "lmdj.web-runtime-host.distribution.v1",
        )
        self.assertEqual(
            set(manifest),
            {
                "assets",
                "distribution_contract",
                "emscripten",
                "heap_bytes",
                "host_version",
                "manifest_version",
                "product_build",
                "protocol_version",
                "resource_limits",
            },
        )

    def test_every_schema_identity_role_and_metadata_tamper_is_rejected(self) -> None:
        mutations = {
            "extra root field": lambda value: value.__setitem__("unexpected", True),
            "ownership": lambda value: value.__setitem__("distribution_contract", "other"),
            "manifest version": lambda value: value.__setitem__("manifest_version", 2),
            "product": lambda value: value.__setitem__("product_build", "999.0.0.0"),
            "host": lambda value: value.__setitem__("host_version", "999.0.0"),
            "protocol": lambda value: value.__setitem__("protocol_version", 999),
            "heap": lambda value: value.__setitem__("heap_bytes", 1),
            "limit": lambda value: value["resource_limits"].__setitem__("imported_wav_bytes", 1),
            "emsdk tag": lambda value: value["emscripten"].__setitem__("emsdk_tag", "latest"),
            "emsdk revision": lambda value: value["emscripten"].__setitem__("emsdk_revision", "a" * 40),
            "releases revision": lambda value: value["emscripten"].__setitem__("emscripten_releases_revision", "b" * 40),
            "emcc output": lambda value: value["emscripten"].__setitem__("emcc_version", "emcc 6.0.5"),
            "empty inventory": lambda value: value.__setitem__("assets", []),
            "duplicate role": lambda value: value["assets"][0].__setitem__("role", "host_main"),
            "unknown role": lambda value: value["assets"][0].__setitem__("role", "unknown"),
            "zero bytes": lambda value: value["assets"][0].__setitem__("bytes", 0),
            "unsafe path": lambda value: value["assets"][0].__setitem__("path", "assets/../escape.js"),
            "filename digest": lambda value: value["assets"][0].__setitem__("sha256", "f" * 64),
            "asset extra field": lambda value: value["assets"][0].__setitem__("unexpected", True),
            "asset order": lambda value: value["assets"].__setitem__(slice(0, 2), list(reversed(value["assets"][:2]))),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                self.reset_distribution()
                self.rewrite_manifest(mutate)
                with self.assertRaises(self.module.DistributionError):
                    self.module.verify_distribution(self.root, REPO_ROOT)

    def test_missing_hashed_asset_and_manifest_mismatch_are_rejected(self) -> None:
        asset = next((self.root / "assets").iterdir())
        asset.unlink()
        with self.assertRaisesRegex(self.module.DistributionError, "missing asset"):
            self.module.verify_distribution(self.root, REPO_ROOT)

        self.reset_distribution()
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
                shutil.copytree(DEFAULT_DIST, self.root)
                path = self.root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"forbidden")
                with self.assertRaises(self.module.DistributionError):
                    self.module.verify_distribution(self.root, REPO_ROOT)

    def test_absolute_local_paths_are_rejected_even_when_asset_hash_matches(self) -> None:
        manifest_path = self.root / "host-manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        entry = next(asset for asset in manifest["assets"] if asset["role"] == "runtime_script")
        old_relative = entry["path"]
        old_path = self.root / old_relative
        content = old_path.read_bytes() + b'\nconst leaked = "/Users/example/private/build";\n'
        digest = hashlib.sha256(content).hexdigest()
        new_relative = f"assets/runtime.{digest}.js"
        new_path = self.root / new_relative
        old_path.rename(new_path)
        new_path.write_bytes(content)
        entry.update(path=new_relative, bytes=len(content), sha256=digest)
        old_manifest_bytes = manifest_path.read_bytes()
        new_manifest_bytes = canonical_json(manifest)
        manifest_path.write_bytes(new_manifest_bytes)
        index_path = self.root / "index.html"
        index = index_path.read_text(encoding="utf-8")
        index = index.replace(old_relative, new_relative)
        index = index.replace(
            hashlib.sha256(old_manifest_bytes).hexdigest(),
            hashlib.sha256(new_manifest_bytes).hexdigest(),
        )
        index_path.write_text(index, encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(self.module.DistributionError, "absolute local path"):
            self.module.verify_distribution(self.root, REPO_ROOT)

    def test_index_identity_metadata_is_exactly_bound_to_manifest(self) -> None:
        index_path = self.root / "index.html"
        index = index_path.read_text(encoding="utf-8").replace(
            'content="1.1.0"', 'content="999.0.0"', 1
        )
        index_path.write_text(index, encoding="utf-8", newline="\n")
        with self.assertRaises(self.module.DistributionError):
            self.module.verify_distribution(self.root, REPO_ROOT)


if __name__ == "__main__":
    unittest.main()
