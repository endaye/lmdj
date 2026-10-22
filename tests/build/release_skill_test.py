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


ISSUE_LIST_SKILL = REPO_ROOT / ".agents/skills/issue-list/SKILL.md"
CLEANUP_PITFALL = REPO_ROOT / ".agents/pitfalls/cleanup-removes-live-release-state.md"
# The release-owned paths a branch/worktree cleanup must never remove or prune
# (#2351, extended by #2422 item 6 after a cleanup deleted the pinned emsdk).
RELEASE_OWNED_PATHS = (
    ".local/release-worktrees/",
    ".git/worktrees/candidate-*",
    ".git/lmdj-release-requests/",
    "build/toolchains/",
    "build/release/",
)


class ReleaseSkillTest(unittest.TestCase):
    def read(self, path: Path) -> str:
        self.assertTrue(path.is_file(), f"missing release governance file: {path}")
        return path.read_text(encoding="utf-8")

    def test_operator_host_checklist_names_each_step_with_its_command(self) -> None:
        """The M1 checklist (#2422 item 7) is a section, not folklore.

        Each host condition that cost 2.0.122.0 time has its own line with the
        exact command the operator runs, and the section says which of them
        `doctor` detects. A checklist without the commands sends the operator
        back to a chat transcript at the worst moment.
        """
        source = self.read(SKILL)
        self.assertIn("## Operator host during a release", source)
        section = source.split("## Operator host during a release", 1)[1].split("\n## ", 1)[0]
        for item, command in (
                ("Spotlight", "Spotlight Privacy"),
                ("fseventsd", "sudo killall fseventsd"),
                ("heavy work", "uptime"),
                ("runner", "launchctl bootout gui/$(id -u)/actions.runner."),
                ("runner", "launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/actions.runner."),
                ("doctor", "scripts/release.sh doctor")):
            with self.subTest(item=item):
                self.assertIn(command, section, f"the checklist lacks the {item} command")

    def test_cleanup_rules_name_every_release_owned_path(self) -> None:
        """A cleanup that does not know a path is release-owned deletes it.

        Four places tell an agent what never to remove: the standing rule in
        AGENTS.md / CLAUDE.md (byte-identical), issue-list Mode 2 (the
        protect-before-classify text and its response table row) and the
        pitfall whose recurrences are the deletions that already happened.
        Every release-owned path in RELEASE_OWNED_PATHS, the single source of
        the protected set, must appear verbatim in each of them.
        """
        agents, claude = self.read(AGENTS), self.read(CLAUDE)
        self.assertEqual(agents, claude, "AGENTS.md and CLAUDE.md must stay byte-identical")
        rule = next((line for line in agents.splitlines()
                     if "cleanup never removes or prunes release-owned state" in line), "")
        self.assertTrue(rule, "AGENTS.md lacks the release-owned cleanup rule")
        issue_list = self.read(ISSUE_LIST_SKILL)
        protect = issue_list.split("### 2. Protect before classifying", 1)[1]
        protect = protect.split("### 3.", 1)[0]
        table_row = next((line for line in protect.splitlines()
                          if line.startswith("| Release-owned path")), "")
        self.assertTrue(table_row, "issue-list Mode 2 lacks the release-owned table row")
        pitfall = self.read(CLEANUP_PITFALL)
        how_to_apply = pitfall.split("## How to apply", 1)[1]
        for path in RELEASE_OWNED_PATHS:
            with self.subTest(path=path):
                self.assertIn(path, rule, f"AGENTS.md cleanup rule does not name {path}")
                self.assertIn(path, protect, f"issue-list Mode 2 does not name {path}")
                self.assertIn(path, table_row, f"the Mode 2 response table does not name {path}")
                self.assertIn(path, how_to_apply, f"the cleanup pitfall does not name {path}")

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
        for command in ("audit", "prepare", "push-tag", "create-draft", "verify-draft", "verify-published", "promote"):
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

    def test_skill_reads_authority_and_verifies_each_transition(self) -> None:
        source = self.read(SKILL)
        for authority in (
            "docs/governance/git-workflow.md",
            "docs/governance/version-management.md",
            "docs/release-evidence/release-intents.json",
            "docs/design/2026-08-13-lmdj-standard-release-pipeline-design.md",
        ):
            self.assertIn(authority, source)
        self.assertIn("current `AGENTS.md`", source)
        self.assertIn("verify each result, and continue without renewed approval", source)
        self.assertGreaterEqual(
            source.count("scripts/release.sh audit --remote --tag TAG"),
            2,
        )

    def test_skill_preserves_overall_authority_and_explicit_restrictions(self) -> None:
        source = self.read(SKILL)
        for expected in (
            "One overall release authorization covers its scoped transitions",
            "Explicit narrower user restrictions win",
            "For an audit-only, design or development request, keep release mutations out of",
            "A boundary-specific restriction still stops at that boundary",
            "does not imply an unattended controller exists",
        ):
            self.assertIn(expected, source)
        for obsolete in (
            "at most one authorized mutation",
            "Stop after that mutation",
            "request authorization for that boundary",
            "Do not output an ordered multi-stage",
        ):
            self.assertNotIn(obsolete, source)

    def test_skill_reports_authority_boundaries_without_crossing_them(self) -> None:
        source = self.read(SKILL)
        for expected in (
            "last verified state",
            "scope expansion",
            "remaining work",
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
            "without republishing or",
            "Do not relabel historically completed states as unperformed",
            "abandoned",
            "superseded-unreleased",
            "allocated identity needs candidate evidence",
            "unknown",
            "conflict",
            "unverifiable",
            "external-error",
            "Only a verified releasable intent admits new preparation/tag/Draft/publication",
        ):
            self.assertIn(expected, source)
        self.assertNotIn("all are unperformed", source)
        self.assertNotIn("release verification as unperformed", source.lower())

    def test_publication_records_ledger_before_promotion(self) -> None:
        source = self.read(SKILL)
        self.assertIn("evidence-only reviewed PR", source)
        self.assertIn("promote requires a published intent", source)
        self.assertLess(source.index("changing its intent to published"),
                        source.index("continue to covered Channel promotion"))

    def test_skill_states_the_full_exact_main_evidence_precondition(self) -> None:
        source = self.read(SKILL)
        for expected in (
            "## Full exact-main CI evidence",
            "`complete-test-v2`",
            "`self-test-v1`",
            "15-suite",
            "`self_test_evidence`",
            "`batch_test_evidence`",
            "`lmdj.release-plan-marker.v3`",
            "`executor_event`",
            "durable-claim attestation",
            "exactly one",
            "control/target",
            "30 days",
            "not Re-run jobs",
            "`lmdj.ci-batch-release-reference.v2`",
            "lane-scoped retry",
            "digest",
            "A full dispatch is evidence, not authorization",
            "`unverifiable`",
            "`conflict`",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, source)

    def test_skill_routes_fresh_full_candidates_through_the_durable_main_controller(self) -> None:
        source = self.read(SKILL)
        remedy = "remedy: document the current main controller and closed exact-target candidate request"
        for expected in (
            "`self-test-report.yml` on ref `main`",
            "`batch_operation=reconcile`",
            "Leave `journal_config` empty",
            "Both kinds request all 15 suites",
            "neither moves automatic processing progress or authorizes a release",
            "Redelivering the same ID and target reconciles the original request",
            '"kind":"retry"',
            '"retry_of":"<the candidate\'s request id>"',
            "never list suites",
            "retried at most once",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, source, f"why: missing candidate boundary {expected!r}; {remedy}")
        requests = re.findall(r"`batch_request=(\{[^`]+\})`", source)
        self.assertEqual(len(requests), 1, f"why: candidate request example is missing or ambiguous; {remedy}")
        self.assertEqual(
            json.loads(requests[0]),
            {"id": "<stable-request-id>", "kind": "candidate", "target": "<exact-main-SHA>"},
            f"why: candidate request fields or exact target differ; {remedy}",
        )

    def test_governance_binds_release_authority_to_full_exact_main_evidence(self) -> None:
        git_workflow = self.read(GIT_WORKFLOW)
        version_policy = self.read(VERSION_POLICY)
        for expected in (
            "verified exact main-history",
            "canonical\nrelease verifier accepts",
            "complete, current, exact-candidate evidence",
            "Expired or missing evidence",
            "new authorized test request",
            "separate verification boundaries",
        ):
            with self.subTest(document="git-workflow", expected=expected):
                self.assertIn(expected, git_workflow)
        for expected in (
            "`complete-test-v2`",
            "`self-test-v1`",
            "15-suite",
            "`self_test_evidence`",
            "30 天",
            "`unverifiable`",
            "`conflict`",
            "`external-error`",
            "`batch_test_evidence`",
            "`lmdj.release-plan-marker.v3`",
            "`Disposition.PUBLISHED`",
            "`lmdj.ci-batch-release-reference.v2`",
            '"kind":"retry"',
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
