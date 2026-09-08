#!/usr/bin/env python3
"""Contract tests for Creator Web Host public-deployment documentation."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = REPO_ROOT / "docs/deploy/creator-web.md"
WORKFLOW = REPO_ROOT / ".github/workflows/deploy-creator-web.yml"
GIT_WORKFLOW = REPO_ROOT / "docs/governance/git-workflow.md"
VERSION_POLICY = REPO_ROOT / "docs/governance/version-management.md"
CURRENT_DOCS = (
    VERSION_POLICY,
    REPO_ROOT / "docs/design/2026-08-13-lmdj-standard-release-pipeline-design.md",
    REPO_ROOT / "apps/docs-site/docs/hosts/creator-web.mdx",
    REPO_ROOT / "apps/docs-site/docs/operations/version-and-release.mdx",
    REPO_ROOT / "apps/docs-site/docs/operations/testing-and-proof.mdx",
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

    def test_git_workflow_resolves_the_authoritative_web_host_policy(self) -> None:
        # Git workflow owns navigation/authorization, not a second copy of
        # changing release identities. Follow its actual link and verify the
        # far-side policy section, not just that some Markdown link exists.
        source = self.read(GIT_WORKFLOW)
        release_heading = "## 6. Releases and urgent fixes\n"
        self.assertEqual(source.count(release_heading), 1,
            "why: Git release guidance section is missing or ambiguous; remedy: retain one release authorization section")
        release = source.split(release_heading, 1)[1].split("\n## ", 1)[0]
        links = re.findall(r"\[Web Host release and deployment policy\]\(([^)]+)\)", release)
        self.assertEqual(len(links), 1,
            "why: Git release guidance lacks one authoritative Web Host policy link; remedy: link version-management.md in the release section")
        target = (GIT_WORKFLOW.parent / links[0]).resolve()
        self.assertEqual(target, VERSION_POLICY.resolve(),
            "why: Git workflow delegates release facts to the wrong document; remedy: link the canonical version-management.md")
        policy = self.read(target)
        heading = "### Web Host Product Release 与部署身份\n"
        self.assertEqual(policy.count(heading), 1,
            "why: canonical Web Host policy section is missing or ambiguous; remedy: retain one authoritative release/deployment section")
        section = policy.split(heading, 1)[1].split("\n## ", 1)[0]
        for fact, alternatives in (
            ("release profile", ("web-hosts",)),
            ("Creator Host", ("Creator",)),
            ("Runtime Host", ("Runtime",)),
            ("six-asset inventory", ("六", "six")),
            ("independent deployment", ("独立", "independent")),
            ("historical release exception", ("1.0.40.0",)),
            ("historical immutability", ("不可变", "immutable")),
        ):
            with self.subTest(fact=fact):
                self.assertTrue(any(value in section for value in alternatives),
                    f"why: linked canonical policy lacks {fact}; remedy: restore the authorized fact in its Web Host section, not a duplicate in Git workflow")

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
