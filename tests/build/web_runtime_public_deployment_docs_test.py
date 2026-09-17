#!/usr/bin/env python3
"""Contract tests for Web Runtime Host public-deployment documentation."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = REPO_ROOT / "docs/deploy/web-runtime-host.md"
WORKFLOW = REPO_ROOT / ".github/workflows/deploy-web-runtime-host.yml"
ACCEPTANCE = REPO_ROOT / "docs/quality/2026-08-08-web-runtime-public-deployment-acceptance.md"
DESIGN = REPO_ROOT / "docs/design/2026-08-08-web-runtime-public-deployment-design.md"
PLAN = REPO_ROOT / "docs/plans/2026-08-08-web-runtime-public-deployment.md"
PORTAL_CURRENT_PAGES = (
    REPO_ROOT / "apps/docs-site/docs/operations/version-and-release.mdx",
    REPO_ROOT / "apps/docs-site/docs/operations/testing-and-proof.mdx",
    REPO_ROOT / "apps/docs-site/docs/hosts/web-runtime.mdx",
)
TAG = "lmdj-v1.0.15.2"
TAG_TARGET = "72ae40074620cc5681c462ba04a31a666449734f"
FINGERPRINT = "2B5EE362F058800036AD4FB5116ECE156F954D29"
CHECKSUM_FINGERPRINT = "CB928A6E89DE498851688EF1AAC3E7019FC1478B"


class WebRuntimePublicDeploymentDocsTest(unittest.TestCase):
    def read(self, path: Path) -> str:
        self.assertTrue(path.is_file(), f"missing documentation: {path}")
        return path.read_text(encoding="utf-8")

    def test_current_truth_binds_publication_to_the_exact_candidate(self) -> None:
        for path in PORTAL_CURRENT_PAGES:
            with self.subTest(path=path):
                source = self.read(path)
                compact = re.sub(r"\s+", "", source)
                self.assertIn("import {BuildIdentity}", source)
                self.assertRegex(source, r"<BuildIdentity(?:\s[^>]*)?\s*/>")
                self.assertIn("evidence", source)
                self.assertIn("不自动", compact)
                self.assertNotIn(TAG_TARGET, source)
                self.assertNotIn(FINGERPRINT, source)
                self.assertNotIn(CHECKSUM_FINGERPRINT, source)
                self.assertNotIn("deployment-tooling branch", source)
                self.assertNotIn("尚未 push", source)
                self.assertNotIn("未做远端验证", source)

    def test_current_routes_explain_the_standard_release_boundaries(self) -> None:
        for path in PORTAL_CURRENT_PAGES:
            with self.subTest(path=path):
                source = self.read(path)
                for expected in (
                    "prepare",
                    "push-tag",
                    "create-draft",
                    "publish-release.yml",
                    "Draft",
                    "`release` Environment",
                    "audit --remote",
                    "historical exception",
                    "manual-only",
                    "released",
                    "deployed",
                    "promoted",
                ):
                    self.assertIn(expected, source)

    def test_current_runtime_docs_use_the_dual_host_release_without_coupling_deployments(self) -> None:
        runbook = self.read(RUNBOOK)
        portal = self.read(PORTAL_CURRENT_PAGES[0])
        for source in (runbook, portal):
            with self.subTest(source=source[:40]):
                self.assertIn("web-hosts", source)
                self.assertRegex(source, r"六(?:项|个|资产)")
                self.assertIn("lmdj-runtime.netlify.app", source)
                self.assertIn("lmdj-creator.netlify.app", source)
                self.assertIn("独立", source)
                self.assertIn("manual-only", source)
                self.assertIn("1.0.40.0", source)
                self.assertIn("不可变", source)

    def test_predeploy_record_is_explicitly_historical(self) -> None:
        source = self.read(ACCEPTANCE)
        for expected in (
            TAG,
            TAG_TARGET,
            FINGERPRINT,
            "pre-deploy 快照",
            "在采集时",
            "不代表当前远端控制面",
        ):
            self.assertIn(expected, source)

        runbook = self.read(RUNBOOK)
        compact_runbook = re.sub(r"\s+", "", runbook)
        for expected in (
            "pre-deploy 证据快照",
            "每次实际操作前",
            "重新验证",
        ):
            self.assertIn(expected, runbook)
        self.assertIn("不是当前远端控制面的动态真相", compact_runbook)

    def test_the_runbook_names_the_deployment_path_it_actually_uses(self) -> None:
        # The retired Netlify facts elsewhere are retained as history. These are
        # the ones an operator acts on today, and the runbook named none of them
        # until the Creator suite's stale assertion exposed the same gap here.
        source = RUNBOOK.read_text(encoding="utf-8")
        for expected in (
            "https://lab.lmdj.workers.dev/",
            "scripts/cloudflare-host-deploy.sh",
            "CLOUDFLARE_API_TOKEN",
            "lmdj.web-runtime-host.deployment-evidence.v3",
        ):
            with self.subTest(current=expected):
                self.assertIn(expected, source)

    def test_the_workflow_deploys_to_the_target_it_was_cut_over_to(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", source)
        self.assertIn("runtime-canary", source)
        self.assertIn("CLOUDFLARE_API_TOKEN", source)
        self.assertIn("scripts/cloudflare-host-deploy.sh", source)
        self.assertIn("--target web-runtime-host", source)
        self.assertNotIn("NETLIFY", source)
        self.assertNotIn("deploy-creator-web", source)
        self.assertNotIn("publish-release", source)

    def test_release_authority_and_header_boundary_are_explicit(self) -> None:
        source = self.read(RUNBOOK)
        self.assertIn("Release ZIP 未修改", source)
        self.assertIn("精确包含三个资产", source)
        self.assertIn("<archive>.sha256.asc", source)
        self.assertIn("才解析 checksum", source)
        self.assertIn("Product tag signer", source)
        self.assertIn("Release checksum signer", source)
        self.assertIn(FINGERPRINT, source)
        self.assertIn(CHECKSUM_FINGERPRINT, source)
        self.assertIn("不得用任一角色密钥替代另一角色", source)
        self.assertIn("revocation certificate", source)
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
        self.assertIn("preflight 发现 official `disabled: true`", source)
        self.assertIn("时间戳中的可选小数秒", source)
        self.assertIn("900 秒 kill budget", source)
        self.assertIn("未知第三 ID 必须 recovery FAIL", source)
        self.assertIn("GET 必须确认 exact prior", source)
        self.assertIn("GET 必须确认 disabled", source)
        self.assertNotIn("NETLIFY_AUTH_TOKEN='authorized-token'", source)

    def test_evidence_schemas_preserve_complete_publication_and_recovery_results(self) -> None:
        source = self.read(RUNBOOK)
        self.assertIn("evidence.json", source)
        self.assertIn("lmdj.web-runtime-host.deployment-evidence.v2", source)
        self.assertIn("{filename, sha256}", source)
        self.assertIn("github_actions", source)
        self.assertIn("prior_good", source)
        self.assertIn("publication", source)
        self.assertIn("release_files", source)
        self.assertIn("validated secret-safe official projection", source)
        self.assertIn("{status_code: 204}", source)
        self.assertIn("post_recovery_site", source)
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
        self.assertNotIn("优先使用 `gh` 自己的 credential store", source)
        for match in re.finditer(r"scripts/web-runtime-deploy\.sh (?:verify|deploy)", source):
            preceding = source[max(0, match.start() - 500):match.start()]
            self.assertIn("read -rsp", preceding)
            self.assertIn("export GITHUB_TOKEN", preceding)

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
