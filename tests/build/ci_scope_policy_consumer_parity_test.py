#!/usr/bin/env python3
"""Keep every repository-backed scope-policy proof consumer in parity."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
sys.path.insert(0, str(ROOT / "tests/build"))

import change_scope  # noqa: E402
import local_preflight  # noqa: E402
import pr_gate  # noqa: E402
from ci_scope_policy_test_support import policy_transition  # noqa: E402


PARITY_MESSAGE = (
    "why: a focused scope-policy proof must be independently revalidated by "
    "the summary and PR Gate consumers; remedy: pass the complete "
    "repository checkout to the shared manifest validator at every consumer"
)
LOCAL_PARITY_MESSAGE = (
    "why: the advisory local pre-flight must evaluate uncommitted policy edits "
    "against the merge-base without weakening revision-bound consumers; remedy: "
    "use the pure classification differential for the working tree and keep the "
    "repository proof for committed manifest consumers"
)


def git(root, *args):
    return subprocess.run(
        ("git", *args), cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


class ScopePolicyConsumerParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(
            (ROOT / "scripts/ci/scope_policy.json").read_text(encoding="utf-8")
        )

    def manifest(self, transition):
        inventory = change_scope.read_git_inventory(
            transition.root, transition.base_sha, transition.head_sha
        )
        return change_scope.classify(
            transition.head_policy,
            inventory,
            base_sha=transition.base_sha,
            head_sha=transition.head_sha,
            event_name="push",
            draft=False,
            labels=(),
            policy_edit_preserving=True,
        )

    @staticmethod
    def formal_results(policy, manifest):
        selected = set(manifest["required_jobs"])
        jobs = {
            job for lane_jobs in policy["lane_jobs"].values()
            for job in lane_jobs
        }
        return {
            job: "success" if job in selected else "skipped"
            for job in jobs
        }

    def assert_consumers(self, transition, *, accepted):
        manifest = self.manifest(transition)
        if accepted:
            summary = change_scope._summary(
                manifest, transition.head_policy, repository=transition.root
            )
            self.assertIn("<code>focused</code>", summary, PARITY_MESSAGE)
        else:
            with self.assertRaisesRegex(ValueError, "why:.*remedy:"):
                change_scope._summary(
                    manifest, transition.head_policy,
                    repository=transition.root,
                )

        gate = pr_gate.validate_gate(
            transition.head_policy,
            manifest,
            self.formal_results(transition.head_policy, manifest),
            transition.head_sha,
            expected_base_sha=transition.base_sha,
            repository=transition.root,
        )
        self.assertIs(gate.ok, accepted, PARITY_MESSAGE)

    def test_all_repository_consumers_accept_the_same_preserving_proof(self):
        with policy_transition(self.policy, preserving=True) as transition:
            self.assert_consumers(transition, accepted=True)

    def test_all_repository_consumers_reject_a_forged_preserving_proof(self):
        with policy_transition(self.policy, preserving=False) as transition:
            self.assert_consumers(transition, accepted=False)

    def test_git_head_policy_cannot_be_replaced_by_the_caller(self):
        with policy_transition(self.policy, preserving=False) as transition:
            manifest = self.manifest(transition)
            caller_policy = transition.base_policy
            accepted = {}
            try:
                change_scope.validate_manifest(
                    manifest, caller_policy, repository=transition.root
                )
                accepted["manifest"] = True
            except ValueError:
                accepted["manifest"] = False
            try:
                change_scope._summary(
                    manifest, caller_policy, repository=transition.root
                )
                accepted["summary"] = True
            except ValueError:
                accepted["summary"] = False
            accepted["pr"] = pr_gate.validate_gate(
                caller_policy,
                manifest,
                self.formal_results(caller_policy, manifest),
                transition.head_sha,
                expected_base_sha=transition.base_sha,
                repository=transition.root,
            ).ok

        self.assertEqual(
            accepted,
            {"manifest": False, "summary": False, "pr": False},
            PARITY_MESSAGE,
        )

    def test_missing_or_invalid_git_head_policy_fails_closed(self):
        for name, document in (("missing", None), ("invalid", "{}\n")):
            with self.subTest(name=name):
                with policy_transition(self.policy, preserving=True) as transition:
                    manifest = self.manifest(transition)
                    policy_path = transition.root / change_scope.SCOPE_POLICY_PATH
                    if document is None:
                        policy_path.unlink()
                    else:
                        policy_path.write_text(document, encoding="utf-8")
                    git(
                        transition.root,
                        "add", "--all", "--", change_scope.SCOPE_POLICY_PATH,
                    )
                    git(transition.root, "commit", "--quiet", "-m", name)
                    manifest["head_sha"] = git(
                        transition.root, "rev-parse", "HEAD"
                    )

                    with self.assertRaisesRegex(
                        ValueError, "head scope policy is unavailable"
                    ):
                        change_scope.validate_manifest(
                            manifest,
                            transition.head_policy,
                            repository=transition.root,
                        )

    def test_local_preflight_separates_working_tree_and_revision_authority(self):
        for preserving in (True, False):
            with self.subTest(preserving=preserving):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    git(root, "init", "--quiet")
                    git(root, "config", "user.email", "ci@example.invalid")
                    git(root, "config", "user.name", "CI Test")

                    existing = root / "docs/existing.md"
                    existing.parent.mkdir(parents=True)
                    existing.write_text("existing\n", encoding="utf-8")
                    policy_path = root / change_scope.SCOPE_POLICY_PATH
                    policy_path.parent.mkdir(parents=True)
                    policy_path.write_text(
                        json.dumps(self.policy, indent=2) + "\n", encoding="utf-8"
                    )
                    git(root, "add", "--all")
                    git(root, "commit", "--quiet", "-m", "base policy")
                    base_sha = git(root, "rev-parse", "HEAD")

                    working_policy = copy.deepcopy(self.policy)
                    if preserving:
                        probe = "tests/build/scope_policy_probe.py"
                        working_policy["rules"].append({
                            "match": {"kind": "exact", "value": probe},
                            "lanes": ["ci_contract"],
                        })
                        probe_path = root / probe
                        probe_path.parent.mkdir(parents=True)
                        probe_path.write_text("# uncommitted probe\n", encoding="utf-8")
                    else:
                        markdown_rule = next(
                            rule for rule in working_policy["rules"]
                            if rule["match"] == {"kind": "suffix", "value": ".md"}
                        )
                        markdown_rule["lanes"].append("portal")
                    policy_path.write_text(
                        json.dumps(working_policy, indent=2) + "\n",
                        encoding="utf-8",
                    )

                    original_policy_path = local_preflight.POLICY_PATH
                    try:
                        local_preflight.POLICY_PATH = policy_path
                        plan = local_preflight.build_plan(root, base_sha)
                    finally:
                        local_preflight.POLICY_PATH = original_policy_path

                    expected_mode = "focused" if preserving else "full"
                    self.assertEqual(
                        plan["mode"], expected_mode, LOCAL_PARITY_MESSAGE
                    )
                    if preserving:
                        self.assertEqual(
                            plan["selected"], ["ci_contract"], LOCAL_PARITY_MESSAGE
                        )


if __name__ == "__main__":
    unittest.main()
