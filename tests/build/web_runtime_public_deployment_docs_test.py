#!/usr/bin/env python3
"""Contract tests for Web Runtime Host public-deployment documentation."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = REPO_ROOT / "docs/deploy/web-runtime-host.md"
ACCEPTANCE = REPO_ROOT / "docs/quality/2026-08-08-web-runtime-public-deployment-acceptance.md"
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

    def test_current_truth_records_the_local_signed_tag_without_remote_claim(self) -> None:
        for path in (*PORTAL_CURRENT_PAGES, ACCEPTANCE):
            with self.subTest(path=path):
                source = self.read(path)
                self.assertIn(TAG, source)
                self.assertIn(TAG_TARGET, source)
                self.assertIn(FINGERPRINT, source)
                self.assertIn("本地已存在", source)
                self.assertIn("尚未 push", source)
                self.assertIn("未做远端验证", source)

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

    def test_runbook_keeps_release_bytes_and_headers_boundary_explicit(self) -> None:
        source = self.read(RUNBOOK)
        self.assertIn("Release ZIP 未修改", source)
        self.assertIn("apps/web-runtime-host/deploy/_headers", source)
        self.assertIn("repository-tracked deploy-control artifact", source)
        self.assertIn("不在 Release bundle 内", source)
        self.assertIn("独立加入", source)

    def test_site_id_is_nonsecret_evidence_identity(self) -> None:
        source = self.read(RUNBOOK)
        self.assertIn("site ID 本质上不是 secret", source)
        self.assertIn("已批准的 scoped configuration contract", source)
        self.assertIn("Environment secret `NETLIFY_RUNTIME_SITE_ID`", source)
        self.assertIn("evidence artifact", source)
        self.assertIn("验收记录", source)
        self.assertIn("不得与 token 混淆", source)
        self.assertIn("不在 tracked runbook、Portal 或日志中写入真实值", source)

    def test_rollback_requires_controlled_authorized_operation(self) -> None:
        source = self.read(RUNBOOK)
        self.assertIn("没有 rollback dispatch", source)
        self.assertIn("单独授权", source)
        self.assertIn("先 smoke prior immutable URL", source)
        self.assertIn("exact prior Deploy ID", source)
        self.assertIn("再 smoke production alias", source)
        self.assertIn("prior evidence", source)
        self.assertIn("初次发布没有 prior good Deploy", source)
        self.assertNotIn("NETLIFY_AUTH_TOKEN='authorized-token'", source)

    def test_evidence_inspection_separates_artifact_run_metadata_and_logs(self) -> None:
        source = self.read(RUNBOOK)
        self.assertIn("evidence.json", source)
        self.assertIn("GitHub run metadata", source)
        self.assertIn("workflow log", source)
        self.assertIn("artifact identity", source)
        self.assertIn("不单独提供", source)
        self.assertIn("run URL", source)
        self.assertIn("timestamp", source)
        self.assertIn("smoke detail", source)


if __name__ == "__main__":
    unittest.main()
