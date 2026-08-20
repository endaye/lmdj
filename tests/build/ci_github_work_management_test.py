#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = ROOT / ".github" / "ISSUE_TEMPLATE"
GOVERNANCE = ROOT / "docs" / "governance" / "github-work-management.md"
PR_TEMPLATE = ROOT / ".github" / "pull_request_template.md"

FORM_CONTRACTS = {
    "feature.yml": ("type:feature", ("summary", "outcome", "scope", "acceptance", "dependencies", "stage", "area", "version_impact", "documentation_impact", "source")),
    "bug.yml": ("type:bug", ("summary", "observed", "expected", "reproduction", "evidence", "acceptance", "stage", "area", "version_impact", "documentation_impact")),
    "question.yml": ("type:question", ("question", "importance", "evidence", "decision_criteria", "stage", "area", "source")),
    "task.yml": ("type:task", ("outcome", "scope", "acceptance", "dependencies", "stage", "area", "version_impact", "documentation_impact", "source")),
    "documentation.yml": ("type:docs", ("authority", "change", "audience", "acceptance", "links", "version_impact", "documentation_impact")),
}


class GitHubWorkManagementContractTest(unittest.TestCase):
    def read(self, name: str) -> str:
        return (TEMPLATE_ROOT / name).read_text(encoding="utf-8")

    def test_blank_issues_are_disabled(self) -> None:
        source = self.read("config.yml")
        self.assertIn("blank_issues_enabled: false", source)
        self.assertIn("contact_links: []", source)

    def test_all_five_forms_have_closed_fields_and_one_type(self) -> None:
        self.assertEqual(
            {path.name for path in TEMPLATE_ROOT.glob("*.yml")},
            {"config.yml", *FORM_CONTRACTS},
        )
        for filename, (label, field_ids) in FORM_CONTRACTS.items():
            with self.subTest(filename=filename):
                source = self.read(filename)
                for header in ("name:", "description:", "title:", "labels:", "body:"):
                    self.assertRegex(source, rf"(?m)^{re.escape(header)}")
                self.assertRegex(source, rf'(?m)^labels: \["{re.escape(label)}"\]$')
                ids = tuple(re.findall(r"(?m)^    id: ([a-z_]+)$", source))
                self.assertEqual(ids, field_ids)

    def test_every_form_captures_acceptance_or_decision_criteria(self) -> None:
        for filename in FORM_CONTRACTS:
            source = self.read(filename)
            self.assertTrue(
                "    id: acceptance" in source or "    id: decision_criteria" in source,
                filename,
            )

    def test_governance_preserves_durable_authority(self) -> None:
        source = GOVERNANCE.read_text(encoding="utf-8")
        for required in (
            "Issues own active lifecycle state",
            "GitHub Project owns portfolio state",
            "Repository documents own durable truth",
            "An Issue comment is not a product decision",
            "Closes #",
            "Relates to #",
            "release, deployment, publication, or Channel promotion",
        ):
            self.assertIn(required, source)

    def test_governance_makes_the_canonical_transition_explicit(self) -> None:
        source = " ".join(GOVERNANCE.read_text(encoding="utf-8").split())
        for required in (
            "An Issue becomes the lifecycle authority only after a replacement Issue exists and its source link is verified.",
            "GitHub Project becomes the portfolio authority only after `LMDJ Work` exists and the item is added.",
            "Before migration, repository question/TODO sources retain their current live state.",
            "Migrate active work only after the replacement Issue is created and the source link is verified.",
            "`docs/prd/questions/*.md` must not be migrated before this repository contract is merged.",
        ):
            self.assertIn(required, source)

    def test_pull_request_template_requires_issue_relation(self) -> None:
        source = PR_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("## Related Issue", source)
        self.assertIn("Closes #", source)
        self.assertIn("Relates to #", source)
        self.assertIn("None — reason:", source)


if __name__ == "__main__":
    unittest.main()
