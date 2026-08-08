#!/usr/bin/env python3
"""Contract tests for Web Runtime Host public-deployment documentation."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = REPO_ROOT / "docs/deploy/web-runtime-host.md"
ACCEPTANCE = REPO_ROOT / "docs/quality/2026-08-08-web-runtime-public-deployment-acceptance.md"
DESIGN = REPO_ROOT / "docs/superpowers/specs/2026-08-08-web-runtime-public-deployment-design.md"
PLAN = REPO_ROOT / "docs/superpowers/plans/2026-08-08-web-runtime-public-deployment.md"
PORTAL_CURRENT_PAGES = (
    REPO_ROOT / "apps/architecture-portal/docs/operations/version-and-release.mdx",
    REPO_ROOT / "apps/architecture-portal/docs/hosts/web-runtime.mdx",
    REPO_ROOT / "apps/architecture-portal/docs/platform/web-runtime.mdx",
)
TAG = "lmdj-v1.0.15.2"
TAG_TARGET = "72ae40074620cc5681c462ba04a31a666449734f"
FINGERPRINT = "2B5EE362F058800036AD4FB5116ECE156F954D29"


class WebRuntimePublicDeploymentDocsTest(unittest.TestCase):
    def read(self, path: Path) -> str:
        self.assertTrue(path.is_file(), f"missing documentation: {path}")
        return path.read_text(encoding="utf-8")

    def test_current_truth_separates_merged_target_from_unmerged_tooling(self) -> None:
        for path in (*PORTAL_CURRENT_PAGES, ACCEPTANCE):
            with self.subTest(path=path):
                source = self.read(path)
                self.assertIn(TAG, source)
                self.assertIn(TAG_TARGET, source)
                self.assertIn(FINGERPRINT, source)
                self.assertIn("本地已存在", source)
                self.assertIn("尚未 push", source)
                self.assertIn("未做远端验证", source)
                self.assertIn("origin/main", source)
                self.assertIn("PR #98", source)
                self.assertIn("deployment-tooling", source)

    def test_current_truth_never_denies_the_local_signed_tag(self) -> None:
        deprecated_local_tag_absence = re.compile(
            r"也没有(?:本候选的)?\s*(?:signed\s+tag|已签名(?:的)?\s*tag)"
        )
        for path in (*PORTAL_CURRENT_PAGES, ACCEPTANCE):
            with self.subTest(path=path):
                self.assertNotRegex(
                    self.read(path),
                    deprecated_local_tag_absence,
                    "current truth must distinguish absent remote verification from a local signed tag",
                )

    def test_release_authority_and_header_boundary_are_explicit(self) -> None:
        source = self.read(RUNBOOK)
        self.assertIn("Release ZIP 未修改", source)
        self.assertIn("精确包含三个资产", source)
        self.assertIn("<archive>.sha256.asc", source)
        self.assertIn("才解析 checksum", source)
        self.assertIn("独立授权", source)
        self.assertIn("不记录私钥或 token", source)
        self.assertIn("九条", source)
        self.assertIn("禁止 `/assets/*` blanket", source)
        self.assertIn("unknown/source map `no-store`", source)

    def test_site_id_is_nonsecret_evidence_identity(self) -> None:
        source = self.read(RUNBOOK)
        self.assertIn("site ID 本质上不是 secret", source)
        self.assertIn("已批准的 scoped configuration contract", source)
        self.assertIn("Environment secret `NETLIFY_RUNTIME_SITE_ID`", source)
        self.assertIn("evidence artifact", source)
        self.assertIn("验收记录", source)
        self.assertIn("不得与 token 混淆", source)
        self.assertIn("不在 tracked runbook、Portal 或日志中写入真实值", source)

    def test_recovery_contract_covers_prior_and_first_publication(self) -> None:
        source = self.read(RUNBOOK)
        self.assertIn("先 smoke prior immutable URL", source)
        self.assertIn("production alias", source)
        self.assertIn("publish 后失败即使 API 返回 error", source)
        self.assertIn("恢复 exact prior", source)
        self.assertIn("reversible `PUT /sites/{site_id}/disable`", source)
        self.assertIn("preflight 发现站点已 disabled", source)
        self.assertIn("480 秒 kill budget", source)
        self.assertNotIn("NETLIFY_AUTH_TOKEN='authorized-token'", source)

    def test_evidence_schemas_preserve_complete_publication_and_recovery_results(self) -> None:
        source = self.read(RUNBOOK)
        self.assertIn("evidence.json", source)
        self.assertIn("lmdj.web-runtime-host.deployment-evidence.v2", source)
        self.assertIn("{filename, sha256}", source)
        self.assertIn("github_actions", source)
        self.assertIn("prior_good", source)
        self.assertIn("publication", source)
        self.assertIn("recovery-evidence.json", source)
        self.assertIn("lmdj.web-runtime-host.deployment-recovery-evidence.v1", source)
        self.assertIn("reconcile", source)
        self.assertIn("recovery_response", source)
        self.assertIn("不得丢弃 HTTP JSON 或 restore response", source)

    def test_short_lived_github_token_flow_avoids_history_and_cleans_up(self) -> None:
        source = self.read(RUNBOOK)
        self.assertIn("read -rsp", source)
        self.assertIn("trap 'unset GITHUB_TOKEN' EXIT INT TERM", source)
        self.assertIn("unset GITHUB_TOKEN", source)
        self.assertIn("不得在 shell 命令行写", source)

    def test_approved_design_and_plan_record_no_version_change_and_three_routes(self) -> None:
        for path in (DESIGN, PLAN):
            with self.subTest(path=path):
                source = self.read(path)
                self.assertIn("Version impact: none", source)
                self.assertIn("Documentation impact: required", source)
                self.assertIn("/operations/version-and-release/", source)
                self.assertIn("/hosts/web-runtime/", source)
                self.assertIn("/platform/web-runtime/", source)
                self.assertIn("<archive>.sha256.asc", source)
                self.assertIn("lmdj.web-runtime-host.deployment-evidence.v2", source)
                self.assertIn("lmdj.web-runtime-host.deployment-recovery-evidence.v1", source)


if __name__ == "__main__":
    unittest.main()
