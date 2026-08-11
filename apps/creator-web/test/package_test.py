#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_TOOL = REPO_ROOT / "apps/creator-web/tools/package.py"


def load_package_module():
    spec = importlib.util.spec_from_file_location("lmdj_creator_package", PACKAGE_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError("Creator package module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CreatorPackageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-creator-package-")
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.ui = self.root / "ui"
        self.runtime = self.root / "runtime"
        self.identity = self.root / "toolchain-identity.json"
        self.repo.mkdir()
        (self.repo / "products/lmdj").mkdir(parents=True)
        (self.repo / "tools/web-runtime").mkdir(parents=True)
        self.ui.joinpath("assets").mkdir(parents=True)
        self.runtime.mkdir()
        version = {
            "contract": "lmdj.product-version.v1",
            "product": "lmdj",
            "milestone": 1,
            "minor": 0,
            "build": 16,
            "patch": 6,
        }
        lock = json.loads(
            (REPO_ROOT / "tools/web-runtime/emscripten.lock.json").read_text(
                encoding="utf-8"
            )
        )
        (self.repo / "products/lmdj/version.json").write_text(
            json.dumps(version), encoding="utf-8"
        )
        (self.repo / "tools/web-runtime/emscripten.lock.json").write_text(
            json.dumps(lock), encoding="utf-8"
        )
        identity = {**lock, "emcc_version": load_package_module().EMCC_VERSION}
        self.identity.write_text(json.dumps(identity), encoding="utf-8")
        (self.ui / "index.html").write_text(
            "<!doctype html>\n<html><head><meta charset=\"UTF-8\" />"
            "<link rel=\"stylesheet\" href=\"/assets/index-source.css\"></head>"
            "<body><div id=\"root\"></div>"
            "<script type=\"module\" src=\"/assets/index-source.js\"></script>"
            "</body></html>\n",
            encoding="utf-8",
            newline="\n",
        )
        (self.ui / "assets/index-source.js").write_text(
            "console.log('creator');\n", encoding="utf-8", newline="\n"
        )
        (self.ui / "assets/index-source.css").write_text(
            "body{margin:0}\n", encoding="utf-8", newline="\n"
        )
        (self.runtime / "lmdj-web-runtime.js").write_text(
            'const wasm="lmdj-web-runtime.wasm";\n', encoding="utf-8", newline="\n"
        )
        (self.runtime / "lmdj-web-runtime.wasm").write_bytes(b"\x00asmcreator")
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "user.email", "test@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "user.name", "Creator Test"],
            check=True,
        )
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "commit", "-qm", "test fixture"], check=True
        )
        self.module = load_package_module()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def build(self, destination: Path) -> None:
        self.module.build_distribution(
            self.repo, self.ui, self.runtime, self.identity, destination
        )

    def test_builds_exact_deterministic_creator_inventory(self) -> None:
        first = self.root / "first-dist"
        second = self.root / "second-dist"
        self.build(first)
        self.build(second)
        self.module.verify_distribution(first, self.repo)
        self.assertEqual(
            sorted(
                (path.relative_to(first).as_posix(), path.read_bytes())
                for path in first.rglob("*") if path.is_file()
            ),
            sorted(
                (path.relative_to(second).as_posix(), path.read_bytes())
                for path in second.rglob("*") if path.is_file()
            ),
        )
        manifest_bytes = (first / "host-manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        self.assertEqual(self.module.canonical_json(manifest), manifest_bytes)
        self.assertEqual(manifest["distribution_contract"], "lmdj.creator-web.distribution.v1")
        self.assertEqual(manifest["product_build"], "1.0.16.6")
        self.assertEqual(manifest["host_id"], "creator-web")
        self.assertEqual(manifest["host_version"], "1.0.3")
        self.assertEqual(manifest["platform_version"], "0.1.3")
        self.assertEqual(
            manifest["compatible_hosts"],
            [{"host_id": "web-runtime-host", "host_version": "1.2.3"}],
        )
        self.assertEqual(
            [entry["role"] for entry in manifest["assets"]],
            ["host_main", "runtime_script", "runtime_wasm", "host_style"],
        )

    def test_dirty_source_fails_before_distribution_mutation(self) -> None:
        destination = self.root / "dist"
        self.build(destination)
        before = {
            path.relative_to(destination).as_posix(): path.read_bytes()
            for path in destination.rglob("*") if path.is_file()
        }
        (self.repo / "dirty.txt").write_text("dirty", encoding="utf-8")
        with self.assertRaisesRegex(self.module.PackageError, "clean Git source"):
            self.build(destination)
        after = {
            path.relative_to(destination).as_posix(): path.read_bytes()
            for path in destination.rglob("*") if path.is_file()
        }
        self.assertEqual(after, before)

    def test_rejects_corrupt_existing_distribution_and_symlink_target(self) -> None:
        destination = self.root / "dist"
        self.build(destination)
        manifest = json.loads((destination / "host-manifest.json").read_bytes())
        asset = destination / manifest["assets"][0]["path"]
        asset.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(self.module.PackageError, "not replaceable"):
            self.build(destination)
        self.assertEqual(asset.read_text(encoding="utf-8"), "tampered")

        alias = self.root / "dist-alias"
        alias.symlink_to(destination, target_is_directory=True)
        with self.assertRaisesRegex(self.module.PackageError, "symlink"):
            self.build(alias)

    def test_verifier_rejects_extra_source_and_local_path_payload(self) -> None:
        destination = self.root / "dist"
        self.build(destination)
        (destination / "source.map").write_text("{}", encoding="utf-8")
        with self.assertRaises(self.module.DistributionError):
            self.module.verify_distribution(destination, self.repo)
        (destination / "source.map").unlink()
        manifest = json.loads((destination / "host-manifest.json").read_bytes())
        main = destination / manifest["assets"][0]["path"]
        main.write_text("/Users/private/source.ts", encoding="utf-8")
        with self.assertRaises(self.module.DistributionError):
            self.module.verify_distribution(destination, self.repo)

    def test_emscripten_virtual_home_is_not_treated_as_a_host_path(self) -> None:
        destination = self.root / "dist"
        (self.runtime / "lmdj-web-runtime.js").write_text(
            'const home="/home/web_user"; const wasm="lmdj-web-runtime.wasm";\n',
            encoding="utf-8",
            newline="\n",
        )

        self.build(destination)

        self.module.verify_distribution(destination, self.repo)

    def test_runtime_file_url_is_rejected_as_a_host_path(self) -> None:
        destination = self.root / "dist"
        (self.runtime / "lmdj-web-runtime.js").write_text(
            'const leaked="file:///home/private/build"; '
            'const wasm="lmdj-web-runtime.wasm";\n',
            encoding="utf-8",
            newline="\n",
        )

        with self.assertRaisesRegex(
            self.module.DistributionError, "absolute local path"
        ):
            self.build(destination)

    def test_cli_has_a_bounded_usage_failure(self) -> None:
        completed = subprocess.run(
            ["python3", str(PACKAGE_TOOL)], check=False, capture_output=True, text=True
        )
        self.assertEqual(completed.returncode, 64)
        self.assertIn("usage:", completed.stderr)


if __name__ == "__main__":
    unittest.main()
