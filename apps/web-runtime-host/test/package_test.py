#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_TOOL = REPO_ROOT / "apps/web-runtime-host/tools/package.py"
OPERATOR_SCRIPT = REPO_ROOT / "scripts/web-runtime-host.sh"
LOCK_PATH = REPO_ROOT / "tools/web-runtime/emscripten.lock.json"
PRODUCT_VERSION_PATH = REPO_ROOT / "products/lmdj/version.json"


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def current_product_build() -> str:
    version = json.loads(PRODUCT_VERSION_PATH.read_text(encoding="utf-8"))
    return ".".join(
        str(version[name]) for name in ("milestone", "minor", "build", "patch")
    )


class PackageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-web-package-")
        self.root = Path(self.temporary.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.runtime_js = self.runtime / "lmdj-web-runtime-host.js"
        self.runtime_wasm = self.runtime / "lmdj-web-runtime-host.wasm"
        self.runtime_js.write_text(
            'function findWasmBinary(){return locateFile("lmdj-web-runtime-host.wasm")}\n',
            encoding="utf-8",
            newline="\n",
        )
        self.runtime_wasm.write_bytes(b"\x00asm\x01\x00\x00\x00")
        self.identity = self.root / "toolchain-identity.json"
        identity = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        identity["emcc_version"] = (
            "emcc (Emscripten gcc/clang-like replacement + linker emulating GNU ld) 6.0.5"
        )
        self.identity.write_bytes(canonical_json(identity) + b"\n")
        self.dist = self.root / "dist"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_package(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(PACKAGE_TOOL),
                "--repo-root",
                str(REPO_ROOT),
                "--runtime-root",
                str(self.runtime),
                "--identity",
                str(self.identity),
                "--dist-root",
                str(self.dist),
                *extra,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_wrong_arity_is_rejected(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(PACKAGE_TOOL)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 64)
        self.assertIn("usage:", completed.stderr)

        completed = subprocess.run(
            [str(OPERATOR_SCRIPT), "clean", "unexpected"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 64)
        self.assertIn("usage:", completed.stderr)

    def test_clean_rejects_an_overridden_path_outside_the_exact_host_build(self) -> None:
        unsafe = self.root / "outside"
        unsafe.mkdir()
        marker = unsafe / "must-survive"
        marker.write_text("safe", encoding="utf-8")
        completed = subprocess.run(
            [str(OPERATOR_SCRIPT), "clean"],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "LMDJ_WEB_HOST_BUILD_ROOT": str(unsafe),
            },
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("unsafe build root", completed.stderr)
        self.assertTrue(marker.is_file())

    def test_toolchain_mismatch_fails_closed(self) -> None:
        identity = json.loads(self.identity.read_text(encoding="utf-8"))
        identity["emsdk_tag"] = "latest"
        self.identity.write_bytes(canonical_json(identity) + b"\n")
        completed = self.run_package()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("toolchain identity mismatch", completed.stderr)
        self.assertFalse(self.dist.exists())

    def test_missing_runtime_asset_fails_closed(self) -> None:
        self.runtime_wasm.unlink()
        completed = self.run_package()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("runtime asset is missing", completed.stderr)
        self.assertFalse(self.dist.exists())

    def test_existing_unowned_distribution_is_never_replaced(self) -> None:
        self.dist.mkdir()
        marker = self.dist / "must-survive"
        marker.write_text("unowned", encoding="utf-8")
        completed = self.run_package()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("existing distribution is not replaceable", completed.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "unowned")

    def test_package_is_deterministic_and_binds_every_required_identity(self) -> None:
        first = self.run_package()
        self.assertEqual(first.returncode, 0, first.stderr)
        first_inventory = {
            path.relative_to(self.dist).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(self.dist.rglob("*"))
            if path.is_file()
        }
        second = self.run_package()
        self.assertEqual(second.returncode, 0, second.stderr)
        second_inventory = {
            path.relative_to(self.dist).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(self.dist.rglob("*"))
            if path.is_file()
        }
        self.assertEqual(second_inventory, first_inventory)

        manifest_bytes = (self.dist / "host-manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        self.assertEqual(manifest_bytes, canonical_json(manifest))
        self.assertEqual(
            set(manifest),
            {
                "assets",
                "emscripten",
                "heap_bytes",
                "host_version",
                "manifest_version",
                "product_build",
                "protocol_version",
                "resource_limits",
            },
        )
        self.assertEqual(manifest["manifest_version"], 1)
        self.assertEqual(manifest["product_build"], current_product_build())
        self.assertEqual(manifest["host_version"], "1.0.0")
        self.assertEqual(manifest["protocol_version"], 1)
        self.assertEqual(manifest["heap_bytes"], 536_870_912)
        self.assertEqual(
            manifest["resource_limits"],
            {
                "decoded_float_pcm_bytes_per_bank": 67_108_864,
                "decoded_float_pcm_bytes_total": 134_217_728,
                "decoded_frames_per_pad": 240_000,
                "imported_wav_bytes": 1_048_576,
            },
        )
        identity = json.loads(self.identity.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["emscripten"],
            {
                "emcc_version": identity["emcc_version"],
                "emscripten_releases_revision": identity[
                    "emscripten_releases_revision"
                ],
                "emsdk_revision": identity["emsdk_revision"],
                "emsdk_tag": identity["emsdk_tag"],
            },
        )

        roles = {asset["role"] for asset in manifest["assets"]}
        self.assertEqual(
            roles,
            {
                "host_main",
                "host_module",
                "host_style",
                "runtime_script",
                "runtime_wasm",
            },
        )
        for asset in manifest["assets"]:
            self.assertEqual(set(asset), {"bytes", "path", "role", "sha256"})
            self.assertRegex(
                asset["path"],
                r"^assets/[a-z0-9-]+\.[0-9a-f]{64}\.(?:css|js|mjs|wasm)$",
            )
            path = self.dist / asset["path"]
            payload = path.read_bytes()
            self.assertEqual(asset["bytes"], len(payload))
            self.assertEqual(asset["sha256"], hashlib.sha256(payload).hexdigest())

        index = (self.dist / "index.html").read_text(encoding="utf-8")
        digest = hashlib.sha256(manifest_bytes).hexdigest()
        self.assertIn(
            f'<meta name="lmdj-host-manifest-sha256" content="{digest}">',
            index,
        )
        self.assertIn(
            '<meta name="lmdj-host-manifest-path" content="./host-manifest.json">',
            index,
        )
        self.assertIn(
            f'<meta name="lmdj-product-build" content="{current_product_build()}">',
            index,
        )
        self.assertIn(
            '<meta name="lmdj-host-version" content="1.0.0">', index
        )
        self.assertIn(
            '<meta name="lmdj-host-protocol-version" content="1">', index
        )
        self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)[^>]*>", index, re.I))


if __name__ == "__main__":
    unittest.main()
