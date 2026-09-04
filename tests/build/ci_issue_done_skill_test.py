#!/usr/bin/env python3
"""Contract tests for the repository-local issue shipping skill."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / ".agents/skills/issue-done/SKILL.md"
POLICY = REPO_ROOT / "scripts/ci/scope_policy.json"

OWNERSHIP_CONTRACT = (
    "A changed path is safe to push when it matches `rules`, or when it matches\n"
    "`full_rules` and the JSON selects `full` with every lane. A full-only path\n"
    "may retain both an `unclassified path` diagnostic and its named `full rule`\n"
    "reason; that diagnostic alone is not a push blocker. Stop before pushing\n"
    "only when a path matches neither `rules` nor `full_rules`."
)
OPPOSITE_CONTRACT = (
    "A changed path is safe to push only when the JSON has no `unclassified "
    "path` reason."
)
STAGED_OWNERSHIP_CONTRACT = (
    "Whenever `git diff --cached --diff-filter=A --name-only` lists any path, "
    "the ownership suite (or an equivalent gate that reads the staged index) "
    "is mandatory before commit."
)
CONTRACT_FAILURE = (
    "why: the issue-done skill can reject a deliberately full-only path even "
    "though full_rules is canonical ownership and the classifier safely selects "
    "every lane; remedy: state the complete rules-or-full_rules predicate, the "
    "required full result, and the diagnostic-only meaning of unclassified path"
)
STAGED_FAILURE = (
    "why: an unstaged new file is absent from `git ls-files` and the staged index, "
    "so an ownership gate run before staging cannot see it; remedy: keep the "
    "ownership preflight mandatory and preserve the `git add` -> staged diff -> "
    "ownership suite order"
)
SECTION_FAILURE = (
    "why: an issue-done contract section boundary is missing, so the validator "
    "cannot prove the governed instructions; remedy: restore the expected "
    "section heading and rerun this contract test"
)


def section(source: str, start: str, end: str) -> str:
    start_position = source.find(start)
    if start_position < 0:
        raise AssertionError(f"{SECTION_FAILURE}; missing start boundary: {start}")
    content_start = start_position + len(start)
    end_position = source.find(end, content_start)
    if end_position < 0:
        raise AssertionError(f"{SECTION_FAILURE}; missing end boundary: {end}")
    return source[content_start:end_position]


def pre_push_contract_errors(source: str) -> list[str]:
    pre_push = section(
        source,
        "## 4. Push & Create Pull Request",
        "### Split control-plane paths first",
    )
    errors = []
    if OWNERSHIP_CONTRACT not in pre_push:
        errors.append("complete canonical ownership decision is missing")
    if re.search(r"no\s+`unclassified path` reason", pre_push):
        errors.append("opposite unclassified-path requirement is present")
    return errors


def staged_gate_errors(source: str) -> list[str]:
    staged = section(
        source,
        "3. **Mandatory new-file ownership preflight after staging**:",
        "4. **Create Conventional Commit**:",
    )
    markers = (
        "git add <file1> <file2> ...",
        "git diff --cached --diff-filter=A --name-only",
        "python3 tests/build/ci_change_scope_test.py",
        "test_every_tracked_path_has_explicit_ownership_or_full_rule",
    )
    positions = [staged.find(marker) for marker in markers]
    errors = []
    normalized_staged = " ".join(staged.split())
    if STAGED_OWNERSHIP_CONTRACT not in normalized_staged:
        errors.append("complete mandatory staged ownership condition is missing")
    if -1 in positions:
        errors.append("mandatory staged ownership command is missing")
    elif positions != sorted(positions):
        errors.append("mandatory staged ownership commands are out of order")
    return errors


class TemporaryRepository:
    def __init__(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.git("init", "--quiet")
        self.git("config", "user.email", "ci-contract@example.invalid")
        self.git("config", "user.name", "CI Contract")

    def close(self) -> None:
        self.temporary_directory.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit_path(self, path: str, contents: str, message: str) -> str:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")
        self.git("add", "--", path)
        self.git("commit", "--quiet", "-m", message)
        return self.git("rev-parse", "HEAD")


class IssueDoneSkillTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SKILL.read_text(encoding="utf-8")
        cls.local_preflight = cls._load_local_preflight()
        cls.classifier = cls.local_preflight.load_classifier()
        cls.policy = cls.classifier.load_policy(POLICY)

    @staticmethod
    def _load_local_preflight():
        import importlib.util
        import sys

        path = REPO_ROOT / "scripts/ci/local_preflight.py"
        spec = importlib.util.spec_from_file_location(
            "lmdj_issue_done_local_preflight", path
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load local preflight: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def full_only_witness(self) -> tuple[str, frozenset[str]]:
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")
        for encoded_path in sorted(item for item in tracked if item):
            path = encoded_path.decode("utf-8", "strict")
            lanes, reasons = self.classifier.path_classification(self.policy, path)
            full_rule_reasons = frozenset(
                reason for reason in reasons if reason.startswith("full rule: ")
            )
            if not lanes and full_rule_reasons:
                return path, full_rule_reasons
        self.fail(
            "why: the policy has no tracked witness for full_rules-only ownership; "
            "remedy: retain a tracked full-only path or revise this contract and "
            "the issue-done guidance together"
        )

    def assert_full_result(
        self,
        result: dict[str, object],
        path: str,
        full_rule_reasons: frozenset[str],
        selected_key: str,
    ) -> None:
        self.assertEqual("full", result["mode"], CONTRACT_FAILURE)
        selected = result[selected_key]
        if isinstance(selected, dict):
            selected = [lane for lane, enabled in selected.items() if enabled]
        self.assertEqual(set(self.policy["lanes"]), set(selected), CONTRACT_FAILURE)
        reasons = set(result["reasons"])
        self.assertIn(f"unclassified path: {path}", reasons, CONTRACT_FAILURE)
        self.assertTrue(full_rule_reasons & reasons, CONTRACT_FAILURE)

    def test_pre_push_states_complete_canonical_ownership_contract(self) -> None:
        self.assertEqual([], pre_push_contract_errors(self.source), CONTRACT_FAILURE)

    def test_opposite_pre_push_instruction_is_rejected(self) -> None:
        mutated = self.source.replace(OWNERSHIP_CONTRACT, OPPOSITE_CONTRACT)
        self.assertNotEqual(self.source, mutated, CONTRACT_FAILURE)
        self.assertTrue(pre_push_contract_errors(mutated), CONTRACT_FAILURE)

    def test_staged_new_file_gate_remains_mandatory_and_ordered(self) -> None:
        self.assertEqual([], staged_gate_errors(self.source), STAGED_FAILURE)

    def test_staged_failure_names_blind_spot_and_required_order(self) -> None:
        staged_failure = globals().get("STAGED_FAILURE", "")
        for required in (
            "why:",
            "unstaged new file",
            "`git ls-files`",
            "staged index",
            "remedy:",
            "mandatory",
            "`git add` -> staged diff -> ownership suite",
        ):
            with self.subTest(required=required):
                self.assertIn(required, staged_failure)

    def test_staged_gate_never_mutation_is_rejected(self) -> None:
        mutated = self.source.replace(
            "mandatory before commit", "never run before commit", 1
        )
        self.assertNotEqual(self.source, mutated, STAGED_FAILURE)
        self.assertTrue(staged_gate_errors(mutated), STAGED_FAILURE)

    def test_staged_gate_optional_mutation_is_rejected(self) -> None:
        mutated = self.source.replace(
            "mandatory before commit", "optional before commit", 1
        )
        self.assertNotEqual(self.source, mutated, STAGED_FAILURE)
        self.assertTrue(staged_gate_errors(mutated), STAGED_FAILURE)

    def test_reversed_staged_gate_order_is_rejected(self) -> None:
        diff_command = "git diff --cached --diff-filter=A --name-only"
        test_command = "python3 tests/build/ci_change_scope_test.py"
        mutated = self.source.replace(diff_command, "__TEST_COMMAND__", 1)
        mutated = mutated.replace(test_command, diff_command, 1)
        mutated = mutated.replace("__TEST_COMMAND__", test_command, 1)
        self.assertNotEqual(self.source, mutated, STAGED_FAILURE)
        self.assertTrue(staged_gate_errors(mutated), STAGED_FAILURE)

    def test_pre_push_missing_section_boundaries_report_contract_error(self) -> None:
        for boundary in (
            "## 4. Push & Create Pull Request",
            "### Split control-plane paths first",
        ):
            with self.subTest(boundary=boundary):
                mutated = self.source.replace(
                    boundary, "MISSING PRE-PUSH BOUNDARY", 1
                )
                self.assertNotEqual(self.source, mutated, SECTION_FAILURE)
                with self.assertRaisesRegex(
                    AssertionError, r"why: .*; remedy: .*"
                ):
                    pre_push_contract_errors(mutated)

    def test_staged_missing_section_boundaries_report_contract_error(self) -> None:
        for boundary in (
            "3. **Mandatory new-file ownership preflight after staging**:",
            "4. **Create Conventional Commit**:",
        ):
            with self.subTest(boundary=boundary):
                mutated = self.source.replace(
                    boundary, "MISSING STAGED BOUNDARY", 1
                )
                self.assertNotEqual(self.source, mutated, SECTION_FAILURE)
                with self.assertRaisesRegex(
                    AssertionError, r"why: .*; remedy: .*"
                ):
                    staged_gate_errors(mutated)

    def test_real_full_only_path_is_safe_in_classifier_and_local_scope(self) -> None:
        path, full_rule_reasons = self.full_only_witness()
        manifest = self.classifier.classify(
            self.policy,
            [self.classifier.ChangedFile("M", (path,))],
            base_sha="a" * 40,
            head_sha="b" * 40,
            event_name="pull_request",
            draft=False,
            labels=(),
        )
        self.assert_full_result(manifest, path, full_rule_reasons, "lanes")

        repository = TemporaryRepository()
        self.addCleanup(repository.close)
        base_sha = repository.commit_path(path, "base\n", "base")
        repository.commit_path(path, "head\n", "head")
        plan = self.local_preflight.build_plan(repository.root, base_sha)
        self.assert_full_result(plan, path, full_rule_reasons, "selected")


if __name__ == "__main__":
    unittest.main()
