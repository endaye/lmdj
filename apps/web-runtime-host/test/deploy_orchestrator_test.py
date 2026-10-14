#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps/web-runtime-host/tools"))
import deploy_orchestrator


class DeployOrchestratorReleaseTest(unittest.TestCase):
    TAG = "lmdj-v1.0.15.2"
    TARGET = "72ae40074620cc5681c462ba04a31a666449734f"
    ARCHIVE = "lmdj-web-runtime-host-1.2.0-product-1.0.15.2.zip"

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
            host_version="1.2.0",
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

    def test_selects_runtime_assets_from_a_complete_dual_host_release(self) -> None:
        creator = "lmdj-creator-web-2.1.1-product-1.0.15.2.zip"
        assets = [
            creator,
            creator + ".sha256",
            creator + ".sha256.asc",
            self.ARCHIVE,
            self.ARCHIVE + ".sha256",
            self.ARCHIVE + ".sha256.asc",
        ]
        self.assertEqual(
            self.parse(self.metadata(assets=assets)),
            (
                self.ARCHIVE,
                self.ARCHIVE + ".sha256",
                self.ARCHIVE + ".sha256.asc",
                f"https://github.com/endaye/lmdj/releases/tag/{self.TAG}",
            ),
        )

    def test_rejects_invalid_target_metadata_without_using_it_as_attestation(self) -> None:
        for target in (None, "", "main\nother"):
            with self.subTest(target=target):
                with self.assertRaisesRegex(
                    deploy_orchestrator.DeployOrchestratorError, "target metadata"
                ):
                    self.parse(self.metadata(target=target))


class DeployOrchestratorHeadersTest(unittest.TestCase):
    """`cloudflare_headers.py` builds every Host's response rules on this."""

    BASE = "/*\n  Cache-Control: no-store\n"

    def render(self, *, base: str = BASE, missing: str | None = None) -> str:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dist = root / "dist"
            (dist / "assets").mkdir(parents=True)
            paths = [f"assets/asset-{index}.{str(index) * 64}.mjs" for index in range(3)]
            for path in paths:
                if path != missing:
                    (dist / path).write_text("x", encoding="utf-8")
            (dist / "host-manifest.json").write_text(
                json.dumps({"assets": [{"path": path} for path in paths]}),
                encoding="utf-8",
            )
            headers = root / "_headers"
            headers.write_text(base, encoding="utf-8")
            return deploy_orchestrator.render_deploy_headers(dist, headers).decode()

    def test_every_manifest_asset_gets_its_own_immutable_rule(self) -> None:
        rendered = self.render()
        self.assertTrue(rendered.startswith(self.BASE))
        for index in range(3):
            self.assertIn(
                f"/assets/asset-{index}.{str(index) * 64}.mjs\n"
                "  Cache-Control: public, max-age=31536000, immutable",
                rendered,
            )
        self.assertNotRegex(rendered, r"(?m)^/assets/\*$")

    def test_a_blanket_asset_rule_in_the_base_is_refused(self) -> None:
        with self.assertRaisesRegex(
            deploy_orchestrator.DeployOrchestratorError, "response rules are invalid"
        ):
            self.render(base=self.BASE + "\n/assets/*\n  Cache-Control: no-store\n")

    def test_a_manifest_asset_missing_from_the_dist_is_refused(self) -> None:
        missing = f"assets/asset-1.{'1' * 64}.mjs"
        with self.assertRaisesRegex(
            deploy_orchestrator.DeployOrchestratorError, "asset inventory is invalid"
        ):
            self.render(missing=missing)


if __name__ == "__main__":
    unittest.main()
