#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps/web-runtime-host/tools"))
import deploy_orchestrator


class DeployOrchestratorReleaseTest(unittest.TestCase):
    TAG = "lmdj-v1.0.15.2"
    TARGET = "72ae40074620cc5681c462ba04a31a666449734f"
    ARCHIVE = "lmdj-web-runtime-host-1.1.2-product-1.0.15.2.zip"

    def metadata(self, *, target: object = "main", assets: list[str] | None = None) -> str:
        names = assets or [
            self.ARCHIVE,
            self.ARCHIVE + ".sha256",
            self.ARCHIVE + ".sha256.asc",
        ]
        return json.dumps(
            {
                "assets": [{"name": name} for name in names],
                "isDraft": False,
                "isPrerelease": True,
                "tagName": self.TAG,
                "targetCommitish": target,
                "url": f"https://github.com/endaye/lmdj/releases/tag/{self.TAG}",
            }
        )

    def parse(self, source: str):
        return deploy_orchestrator.parse_release_metadata(
            source,
            tag=self.TAG,
            tag_target=self.TARGET,
            product_build="1.0.15.2",
            host_version="1.1.2",
        )

    def test_common_main_target_metadata_is_auxiliary(self) -> None:
        self.assertEqual(
            self.parse(self.metadata(target="main")),
            (
                self.ARCHIVE,
                self.ARCHIVE + ".sha256",
                self.ARCHIVE + ".sha256.asc",
                f"https://github.com/endaye/lmdj/releases/tag/{self.TAG}",
            ),
        )

    def test_requires_exact_three_canonical_release_assets(self) -> None:
        for assets in (
            [self.ARCHIVE, self.ARCHIVE + ".sha256"],
            [self.ARCHIVE, self.ARCHIVE + ".sha256", self.ARCHIVE + ".sha256.asc", "extra"],
            [self.ARCHIVE, self.ARCHIVE + ".sha256", "wrong.asc"],
        ):
            with self.subTest(assets=assets):
                with self.assertRaisesRegex(
                    deploy_orchestrator.DeployOrchestratorError, "asset identity"
                ):
                    self.parse(self.metadata(assets=assets))

    def test_rejects_invalid_target_metadata_without_using_it_as_attestation(self) -> None:
        for target in (None, "", "main\nother"):
            with self.subTest(target=target):
                with self.assertRaisesRegex(
                    deploy_orchestrator.DeployOrchestratorError, "target metadata"
                ):
                    self.parse(self.metadata(target=target))

    def test_legacy_v1_evidence_writer_is_not_exposed(self) -> None:
        self.assertFalse(hasattr(deploy_orchestrator, "write_evidence"))


if __name__ == "__main__":
    unittest.main()
