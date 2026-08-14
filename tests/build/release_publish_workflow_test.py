#!/usr/bin/env python3
"""Contract tests for protected publication of one verified Draft Release."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/publish-release.yml"
ACTION_PINS = {
    "actions/checkout": ("de0fac2e4500dabe0009e67214ff5f5447ce83dd", "v6.0.2"),
    "actions/setup-python": ("a309ff8b426b58ec0e2a45f0f869d46889d02405", "v6.2.0"),
}


class ReleasePublishWorkflowTest(unittest.TestCase):
    def source(self) -> str:
        self.assertTrue(WORKFLOW.is_file(), "publish workflow is missing")
        return WORKFLOW.read_text(encoding="utf-8")

    def mapping_block(self, source: str, key: str, indent: int) -> str:
        lines = source.splitlines()
        header = f"{' ' * indent}{key}:"
        try:
            start = lines.index(header)
        except ValueError:
            self.fail(f"workflow mapping is missing: {key}")
        end = len(lines)
        for index in range(start + 1, len(lines)):
            line = lines[index]
            if not line.strip():
                continue
            line_indent = len(line) - len(line.lstrip(" "))
            if line_indent <= indent:
                end = index
                break
        return "\n".join(lines[start + 1:end])

    def direct_mapping(self, source: str, indent: int) -> dict[str, str]:
        result: dict[str, str] = {}
        pattern = re.compile(
            rf"^ {{{indent}}}([A-Za-z_][A-Za-z0-9_-]*):(?:\s+(.*?))?\s*$"
        )
        for line in source.splitlines():
            match = pattern.fullmatch(line)
            if match is not None:
                self.assertNotIn(match.group(1), result)
                result[match.group(1)] = match.group(2) or ""
        return result

    def job(self, name: str) -> str:
        return self.mapping_block(self.mapping_block(self.source(), "jobs", 0), name, 2)

    def steps(self, source: str) -> list[str]:
        result: list[list[str]] = []
        current: list[str] | None = None
        for line in source.splitlines():
            if line.startswith("      - "):
                if current is not None:
                    result.append(current)
                current = [line]
            elif current is not None:
                current.append(line)
        if current is not None:
            result.append(current)
        return ["\n".join(item) for item in result]

    def test_only_manual_dispatch_accepts_the_three_exact_identifiers(self) -> None:
        source = self.source()
        triggers = self.mapping_block(source, "on", 0)
        self.assertEqual(self.direct_mapping(triggers, 2), {"workflow_dispatch": ""})
        dispatch = self.mapping_block(triggers, "workflow_dispatch", 2)
        inputs = self.mapping_block(dispatch, "inputs", 4)
        self.assertEqual(
            set(self.direct_mapping(inputs, 6)),
            {"tag", "release_id", "plan_sha256"},
        )
        expected = {
            "tag": ("Exact verified tag", "string"),
            "release_id": ("Numeric Draft Release ID", "string"),
            "plan_sha256": ("Exact plan SHA-256", "string"),
        }
        for name, (description, kind) in expected.items():
            with self.subTest(name=name):
                fields = self.direct_mapping(self.mapping_block(inputs, name, 6), 8)
                self.assertEqual(fields, {
                    "description": description,
                    "required": "true",
                    "type": kind,
                })

    def test_approval_separates_read_only_preflight_from_publication(self) -> None:
        source = self.source()
        self.assertEqual(
            self.direct_mapping(self.mapping_block(source, "permissions", 0), 2),
            {"contents": "read"},
        )
        preflight = self.job("preflight")
        publish = self.job("publish")
        self.assertEqual(
            self.direct_mapping(self.mapping_block(preflight, "permissions", 4), 6),
            {"contents": "read", "actions": "read", "deployments": "read"},
        )
        self.assertNotIn("environment", self.direct_mapping(preflight, 4))
        self.assertNotIn("scripts/release.sh publish-draft", preflight)
        publish_mapping = self.direct_mapping(publish, 4)
        self.assertEqual(publish_mapping.get("needs"), "preflight")
        self.assertEqual(publish_mapping.get("environment"), "release")
        self.assertEqual(
            self.direct_mapping(self.mapping_block(publish, "permissions", 4), 6),
            {"contents": "write", "actions": "read", "deployments": "read"},
        )
        self.assertIn("scripts/release.sh verify-draft", preflight)
        self.assertIn("scripts/release.sh audit --remote --tag", preflight)
        verify_index = publish.index("scripts/release.sh verify-draft")
        audit_index = publish.index("scripts/release.sh audit --remote --tag")
        publish_index = publish.index("scripts/release.sh publish-draft")
        self.assertLess(verify_index, publish_index)
        self.assertLess(audit_index, publish_index)

    def test_exact_tag_audit_runs_before_approval_immediately_before_publish_and_afterward(self) -> None:
        preflight = self.job("preflight")
        publish = self.job("publish")
        audit_command = "scripts/release.sh audit --remote --tag"
        self.assertEqual(preflight.count(audit_command), 1)
        self.assertEqual(publish.count(audit_command), 2)
        verify_index = publish.index("scripts/release.sh verify-draft")
        prepublication_audit = publish.index(audit_command)
        publication = publish.index("scripts/release.sh publish-draft")
        postpublication_audit = publish.rindex(audit_command)
        self.assertLess(verify_index, prepublication_audit)
        self.assertLess(prepublication_audit, publication)
        self.assertLess(publication, postpublication_audit)

    def test_both_jobs_use_pinned_protected_main_checkouts_without_credentials(self) -> None:
        source = self.source()
        uses_lines = [line.strip() for line in source.splitlines() if "uses:" in line]
        for line in uses_lines:
            match = re.fullmatch(
                r"-?\s*uses: (actions/[a-z-]+)@([0-9a-f]{40}) # (v[0-9]+(?:\.[0-9]+){1,2})",
                line,
            )
            self.assertIsNotNone(match, f"action is not pinned: {line}")
            assert match is not None
            self.assertEqual((match.group(2), match.group(3)), ACTION_PINS[match.group(1)])
        self.assertEqual(sum("actions/checkout@" in line for line in uses_lines), 2)
        self.assertEqual(sum("actions/setup-python@" in line for line in uses_lines), 2)
        for name in ("preflight", "publish"):
            checkout = next(step for step in self.steps(self.job(name)) if "actions/checkout@" in step)
            self.assertEqual(
                self.direct_mapping(self.mapping_block(checkout, "with", 8), 10),
                {"ref": "main", "fetch-depth": "0", "persist-credentials": "false"},
            )

    def test_publication_is_release_only_and_serialized_by_numeric_id(self) -> None:
        source = self.source()
        concurrency = self.mapping_block(source, "concurrency", 0)
        self.assertEqual(self.direct_mapping(concurrency, 2), {
            "group": "release-publish-${{ inputs.release_id }}",
            "cancel-in-progress": "false",
        })
        lowered = source.lower()
        for forbidden in (
            "netlify", "repository_dispatch", "repository-dispatch",
            "workflow_call", "web-runtime-deploy", "scripts/core.sh package",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_publication_finishes_with_exact_tag_read_only_audit(self) -> None:
        publish = self.job("publish")
        publish_index = publish.index("scripts/release.sh publish-draft")
        audit_index = publish.rindex("scripts/release.sh audit --remote --tag")
        self.assertLess(publish_index, audit_index)
        self.assertIn('"$RELEASE_TAG"', publish[audit_index:])


if __name__ == "__main__":
    unittest.main()
