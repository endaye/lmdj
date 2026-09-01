#!/usr/bin/env python3
"""Contract tests for Creator Web Host public-deployment documentation."""

from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = REPO_ROOT / "docs/deploy/creator-web.md"
WORKFLOW = REPO_ROOT / ".github/workflows/deploy-creator-web.yml"
CURRENT_DOCS = (
    REPO_ROOT / "docs/governance/version-management.md",
    REPO_ROOT / "docs/governance/git-workflow.md",
    REPO_ROOT / "docs/superpowers/specs/2026-08-13-lmdj-standard-release-pipeline-design.md",
    REPO_ROOT / "apps/architecture-portal/docs/hosts/creator-web.mdx",
    REPO_ROOT / "apps/architecture-portal/docs/operations/version-and-release.mdx",
    REPO_ROOT / "apps/architecture-portal/docs/operations/testing-and-proof.mdx",
)


class CreatorWebPublicDeploymentDocsTest(unittest.TestCase):
    def read(self, path: Path) -> str:
        self.assertTrue(path.is_file(), f"missing documentation: {path}")
        return path.read_text(encoding="utf-8")

    def test_runbook_names_exact_site_environment_secret_and_evidence(self) -> None:
        source = self.read(RUNBOOK)
        for expected in (
            "https://lmdj-creator.netlify.app/",
            "creator-canary",
            "NETLIFY_CREATOR_SITE_ID",
            "NETLIFY_AUTH_TOKEN",
            "deploy-creator-web.yml",
            "scripts/creator-web-deploy.sh",
            "lmdj.creator-web.deployment-evidence.v1",
            "lmdj.creator-web.deployment-recovery-evidence.v1",
            "manual-only",
            "workflow_dispatch",
            "exact prior",
        ):
            self.assertIn(expected, source)
        self.assertIn("站点创建完成前", source)
        self.assertIn("不能", source)

    def test_current_docs_define_one_six_asset_release_and_two_deployments(self) -> None:
        for path in CURRENT_DOCS:
            with self.subTest(path=path):
                source = self.read(path)
                self.assertIn("web-hosts", source)
                self.assertIn("Creator", source)
                self.assertIn("Runtime", source)
                self.assertTrue(
                    "六" in source or "six" in source,
                    f"missing six-asset boundary: {path}",
                )
                self.assertTrue(
                    "独立" in source or "independent" in source,
                    f"missing independent deployment boundary: {path}",
                )
                self.assertIn("1.0.40.0", source)
                self.assertTrue(
                    "不可变" in source or "immutable" in source,
                    f"missing historical immutability: {path}",
                )

    def test_workflow_is_manual_only_and_cannot_publish_release_or_runtime(self) -> None:
        source = self.read(WORKFLOW)
        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("release:", source)
        self.assertNotIn("release.published", source)
        self.assertIn("creator-canary", source)
        self.assertIn("NETLIFY_CREATOR_SITE_ID", source)
        self.assertNotIn("deploy-web-runtime-host", source)
        self.assertNotIn("publish-release", source)


if __name__ == "__main__":
    unittest.main()
