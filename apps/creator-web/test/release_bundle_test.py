#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))


class CreatorReleaseBundleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-creator-release-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def load_module(self, name: str, path: Path):
        self.assertTrue(path.is_file(), f"missing release module: {path}")
        spec = importlib.util.spec_from_file_location(name, path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)  # type: ignore[union-attr]
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        sys.modules[name] = module
        self.addCleanup(sys.modules.pop, name, None)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module

    def shared_module(self):
        return importlib.import_module("tools.release.web_host_bundle")

    def creator_module(self):
        return self.load_module(
            "lmdj_test_creator_release_bundle",
            REPO_ROOT / "apps/creator-web/tools/release_bundle.py",
        )

    def test_archive_bytes_are_deterministic(self) -> None:
        dist = self.root / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
        (dist / "assets/main.js").write_bytes(b"main")
        first = self.root / "first.zip"
        second = self.root / "second.zip"

        shared = self.shared_module()
        shared.create_dist_zip(dist, first)
        shared.create_dist_zip(dist, second)

        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_default_verifier_is_loaded_from_creator_host(self) -> None:
        tagged_repo = self.root / "tagged-repository"
        package_path = tagged_repo / "apps/creator-web/tools/package.py"
        package_path.parent.mkdir(parents=True)
        package_path.write_text(
            "from pathlib import Path\n"
            "def verify_distribution(dist_root, repo_root):\n"
            "    Path(repo_root, 'used-creator-verifier').write_text(dist_root.name)\n",
            encoding="utf-8",
        )
        dist = self.root / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
        (dist / "host-manifest.json").write_text(
            json.dumps({"host_version": "2.1.1", "product_build": "1.0.41.0"}),
            encoding="utf-8",
        )
        archive = self.root / "creator.zip"
        shared = self.shared_module()
        shared.create_dist_zip(dist, archive)
        checksum = self.root / "creator.zip.sha256"
        checksum.write_text(
            f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n",
            encoding="ascii",
        )
        signature = self.root / "creator.zip.sha256.asc"
        signature.write_text(
            "-----BEGIN PGP SIGNATURE-----\nfixture\n-----END PGP SIGNATURE-----\n",
            encoding="ascii",
        )
        key = self.root / "checksum.asc"
        key.write_text("fixture", encoding="ascii")

        creator = self.creator_module()
        bundle = creator.stage_release_bundle(
            repo_root=tagged_repo,
            archive_path=archive,
            checksum_path=checksum,
            signature_path=signature,
            checksum_public_key_path=key,
            trusted_checksum_fingerprint="CB928A6E89DE498851688EF1AAC3E7019FC1478B",
            output_root=self.root / "staged",
            expected_product_build="1.0.41.0",
            expected_host_version="2.1.1",
            checksum_authorizer=lambda checksum, signature, key, fingerprint: None,
        )

        self.assertEqual(bundle.product_build, "1.0.41.0")
        self.assertEqual(bundle.host_version, "2.1.1")
        self.assertEqual(
            (tagged_repo / "used-creator-verifier").read_text(encoding="utf-8"),
            "dist",
        )


if __name__ == "__main__":
    unittest.main()
