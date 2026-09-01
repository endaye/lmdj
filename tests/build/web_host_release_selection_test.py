#!/usr/bin/env python3

from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class WebHostReleaseSelectionTest(unittest.TestCase):
    PRODUCT = "1.0.41.0"
    TAG = "lmdj-v1.0.41.0"

    def setUp(self) -> None:
        path = ROOT / "tools/web_deploy/release_selection.py"
        self.assertTrue(path.is_file(), f"missing Host release selector: {path}")
        self.module = importlib.import_module("tools.web_deploy.release_selection")

    def release(self, *, names: list[str] | None = None, **overrides):
        selected = names or self.names()
        document = {
            "assets": [{"name": name} for name in selected],
            "isDraft": False,
            "isPrerelease": True,
            "tagName": self.TAG,
            "targetCommitish": "a" * 40,
            "url": f"https://github.com/endaye/lmdj/releases/tag/{self.TAG}",
        }
        document.update(overrides)
        return document

    def names(self) -> list[str]:
        result = []
        for host in ("creator-web", "web-runtime-host"):
            archive = f"lmdj-{host}-2.1.1-product-{self.PRODUCT}.zip"
            result.extend((archive, archive + ".sha256", archive + ".sha256.asc"))
        return result

    def select(self, release=None, *, host_id="creator-web", host_version="2.1.1"):
        return self.module.select_host_assets(
            self.release() if release is None else release,
            host_id=host_id,
            host_version=host_version,
            product_build=self.PRODUCT,
        )

    def test_selects_one_triplet_only_after_full_inventory_validation(self) -> None:
        selection = self.select()
        archive = f"lmdj-creator-web-2.1.1-product-{self.PRODUCT}.zip"
        self.assertEqual(selection.archive, archive)
        self.assertEqual(selection.checksum, archive + ".sha256")
        self.assertEqual(selection.signature, archive + ".sha256.asc")
        self.assertEqual(selection.asset_names, tuple(self.names()))
        self.assertEqual(
            selection.release_url,
            f"https://github.com/endaye/lmdj/releases/tag/{self.TAG}",
        )

    def test_rejects_incomplete_extra_and_unknown_host_inventories(self) -> None:
        cases = (
            (self.release(names=self.names()[:-1]), "inventory"),
            (self.release(names=[*self.names(), "extra.txt"]), "inventory"),
        )
        for release, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(self.module.ReleaseSelectionError, message):
                    self.select(release)
        with self.assertRaisesRegex(self.module.ReleaseSelectionError, "Host"):
            self.select(host_id="unknown-host")

    def test_rejects_wrong_product_url_draft_and_non_canary(self) -> None:
        cases = (
            (self.release(tagName="lmdj-v1.0.42.0"), "tag"),
            (self.release(url="https://example.invalid/release"), "URL"),
            (self.release(isDraft=True), "published"),
            (self.release(isPrerelease=False), "canary"),
        )
        for release, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(self.module.ReleaseSelectionError, message):
                    self.select(release)

    def test_accepts_historical_three_asset_runtime_release_only(self) -> None:
        archive = f"lmdj-web-runtime-host-2.1.1-product-{self.PRODUCT}.zip"
        selection = self.select(
            self.release(names=[archive, archive + ".sha256", archive + ".sha256.asc"]),
            host_id="web-runtime-host",
        )
        self.assertEqual(selection.archive, archive)
        with self.assertRaisesRegex(self.module.ReleaseSelectionError, "inventory"):
            self.select(
                self.release(names=[archive, archive + ".sha256", archive + ".sha256.asc"]),
                host_id="creator-web",
            )


if __name__ == "__main__":
    unittest.main()
