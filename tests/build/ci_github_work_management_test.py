#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = ROOT / ".github" / "ISSUE_TEMPLATE"

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


if __name__ == "__main__":
    unittest.main()
