#!/usr/bin/env python3
"""Contract tests for release governance and the repo-local navigation skill."""

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / ".agents/skills/lmdj-release/SKILL.md"
AGENTS = REPO_ROOT / "AGENTS.md"
CLAUDE = REPO_ROOT / "CLAUDE.md"
GIT_WORKFLOW = REPO_ROOT / "docs/governance/git-workflow.md"
VERSION_POLICY = REPO_ROOT / "docs/governance/version-management.md"
PR_TEMPLATE = REPO_ROOT / ".github/pull_request_template.md"
RELEASE_POLICY = REPO_ROOT / "tools/release/policy.json"


class ReleaseSkillTest(unittest.TestCase):
    def read(self, path: Path) -> str:
        self.assertTrue(path.is_file(), f"missing release governance file: {path}")
        return path.read_text(encoding="utf-8")

    def test_skill_starts_from_fresh_exact_tag_remote_audit(self) -> None:
        source = self.read(SKILL)
        first_command = re.search(r"`(scripts/release\.sh [^`]+)`", source)
        self.assertIsNotNone(first_command)
        self.assertEqual(
            first_command.group(1),
            "scripts/release.sh audit --remote --tag TAG",
        )
        self.assertIn("read-only", source)
        self.assertIn("exact tag", source)

    def test_skill_is_navigation_not_policy(self) -> None:
        source = self.read(SKILL)
        for command in ("audit", "prepare", "push-tag", "create-draft", "verify-draft"):
            self.assertIn(f"scripts/release.sh {command}", source)

        policy = json.loads(self.read(RELEASE_POLICY))
        forbidden = (
            policy["fingerprints"]["product"],
            policy["fingerprints"]["checksum"],
            "endaye/lmdj",
            ".sha256.asc",
            "build/release/",
            "private key",
            "~/.gnupg",
            "/Users/",
            "--clobber",
            "git push --tags",
            "gh release create",
            "web-runtime-deploy.sh deploy",
        )
        for value in forbidden:
            with self.subTest(value=value):
                self.assertNotIn(value, source)

    def test_skill_reads_authority_and_stops_after_one_mutation(self) -> None:
        source = self.read(SKILL)
        for authority in (
            "docs/governance/git-workflow.md",
            "docs/governance/version-management.md",
            "docs/release-evidence/release-intents.json",
            "docs/superpowers/specs/2026-08-13-lmdj-standard-release-pipeline-design.md",
        ):
            self.assertIn(authority, source)
        self.assertIn("at most one authorized mutation", source)
        self.assertIn("Stop after that mutation", source)
        self.assertGreaterEqual(
            source.count("scripts/release.sh audit --remote --tag TAG"),
            2,
        )

    def test_skill_rejects_blanket_authority_and_continuous_transition_plans(self) -> None:
        source = self.read(SKILL)
        self.assertIn("## Complete response contract", source)
        contract = source.index("## Complete response contract")
        first_command = source.index("scripts/release.sh audit --remote --tag TAG")
        self.assertLess(contract, first_command)
        for expected in (
            "For any initial, multi-transition, or blanket request, the entire response/action is exactly:",
            "Verified state: Run and describe only `scripts/release.sh audit --remote --tag TAG`; report the exact observed historical/current state; no mutation yet.",
            "Next authorization: After audit, use exactly one of the actionable or no-permitted-transition templates below.",
            "Unperformed states: List only mutation/state-transition actions not executed in this turn; never list an audit or verification already reported under Verified state, and never relabel historically completed tag or Release states as unperformed.",
            "After audit, if the state is actionable releasable, the entire response/action is exactly:",
            "Next authorization: Name exactly one permitted next stable transition and request authorization for that boundary.",
            "For a later boundary-specific authorized turn with actionable releasable state, the entire response/action is exactly:",
            "Verified state: Audit first and report the current state.",
            "Unperformed states: List only mutation/state-transition actions not executed in this turn; never list an audit or verification already reported under Verified state, and never relabel historically completed tag or Release states as unperformed.",
            "Do not output an ordered multi-stage command/action sequence; the template is the complete response.",
        ):
            self.assertIn(expected, source)

    def test_skill_reports_authority_boundaries_without_crossing_them(self) -> None:
        source = self.read(SKILL)
        for expected in (
            "Verified state",
            "Next authorization",
            "Unperformed states",
            "tag",
            "release_id",
            "plan_sha256",
            "`release` Environment",
            "Deployment",
            "Channel promotion",
        ):
            self.assertIn(expected, source)
        self.assertIn("Do not approve", source)

    def test_skill_reports_non_actionable_state_without_rewriting_history(self) -> None:
        source = self.read(SKILL)
        for expected in (
            "After audit, if no transition is permitted, the entire response/action is exactly:",
            "Verified state: Report the observed historical/current state accurately.",
            "Next authorization: none; explain why no permitted mutation exists.",
            "Unperformed states: List only mutation/state-transition actions not executed in this turn; never list an audit or verification already reported under Verified state, and never relabel historically completed tag or Release states as unperformed.",
            "published (audit-only)",
            "abandoned",
            "superseded-unreleased",
            "allocated (not releasable)",
            "unknown",
            "conflict",
            "unverifiable",
            "external-error",
            "Only an actionable releasable state may name exactly one next authorization.",
        ):
            self.assertIn(expected, source)
        self.assertNotIn("all are unperformed", source)
        self.assertNotIn("release verification as unperformed", source.lower())

    def test_skill_states_the_full_exact_main_evidence_precondition(self) -> None:
        source = self.read(SKILL)
        for expected in (
            "## Full exact-main CI evidence",
            "`full`",
            "trusted head",
            "`Change Scope`",
            "`PR Gate`",
            "empty `lanes` input on the exact target SHA",
            "`requested`",
            "14",
            "rerun all of its jobs",
            "A full dispatch is evidence, not authorization",
            "`unverifiable`",
            "`conflict`",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, source)

    def test_governance_binds_release_authority_to_full_exact_main_evidence(self) -> None:
        git_workflow = self.read(GIT_WORKFLOW)
        version_policy = self.read(VERSION_POLICY)
        for expected in (
            "focused",
            "unverifiable base",
            "empty `lanes` input",
            "retained scope manifest is `full`",
            "`PR Gate` both succeeded",
            "14 days",
        ):
            with self.subTest(document="git-workflow", expected=expected):
                self.assertIn(expected, git_workflow)
        for expected in (
            "`mode=full`",
            "`trusted_head=true`",
            "`PR Gate`",
            "14 天",
            "`unverifiable`",
            "`conflict`",
            "`external-error`",
        ):
            with self.subTest(document="version-management", expected=expected):
                self.assertIn(expected, version_policy)

    def test_project_instructions_are_synchronized_and_require_the_skill(self) -> None:
        agents = self.read(AGENTS)
        self.assertEqual(agents.encode(), self.read(CLAUDE).encode())
        for expected in (
            ".agents/skills/lmdj-release/SKILL.md",
            "scripts/release.sh",
            "prepare",
            "push-tag",
            "create-draft",
            "publish",
            "deployment",
            "Channel promotion",
            "incident owner",
        ):
            self.assertIn(expected, agents)

    def test_governance_covers_draft_publication_and_history_rules(self) -> None:
        git_workflow = self.read(GIT_WORKFLOW)
        version_policy = self.read(VERSION_POLICY)
        for expected in ("Draft", "publish-release.yml", "`release` Environment"):
            self.assertIn(expected, git_workflow)
        for expected in (
            "release-intents.json",
            "profile",
            "historical exception",
            "Draft",
            "latest",
            "published Release",
        ):
            self.assertIn(expected, version_policy)

    def test_pull_request_template_declares_release_impact(self) -> None:
        source = self.read(PR_TEMPLATE)
        for line in (
            "## Release Impact",
            "Release impact: none",
            "Candidate tag: none",
            "Profile: none",
            "Channel: none",
            "Intent disposition: none",
            "Release assets: none",
            "Release gates: none",
            "Reason: <!-- Explain why release state changes or remains unchanged. -->",
        ):
            self.assertIn(line, source)


if __name__ == "__main__":
    unittest.main()
