#!/usr/bin/env python3
"""Parity contract between the two Web Host deploy workflows.

`deploy-web-runtime-host.yml` and `deploy-creator-web.yml` stay two files
(owner decision, 2026-10-14): release tooling binds each Host to its own
workflow file, its job names (`preflight`, `deploy`), its step names and the
last commit touching that file, so a shared `workflow_call` body would move
the evidence those consumers read. This test keeps the copies from drifting:
each file is normalized by replacing its Host-specific values with
placeholders, and the normalized texts must be identical line for line.

Blind spot: parity cannot see a defect both copies share. The per-Host
contract tests (`web_runtime_deploy_workflow_test.py`,
`creator_web_deploy_workflow_test.py`) are the independent oracle for the
content itself. The identity check below is the oracle for the table: every
Host value must occur in its own file and no value of the other Host may.
"""

from __future__ import annotations

import difflib
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github/workflows"
RUNTIME = "deploy-web-runtime-host.yml"
CREATOR = "deploy-creator-web.yml"

# The complete set of Host-specific values, derived from a diff of the two
# files. Applied in this order: `host_id` is a substring of other values
# (deploy script, concurrency group, workflow file name), so it goes last.
HOST_FIELDS = (
    ("deploy_script", "scripts/web-runtime-deploy.sh", "scripts/creator-web-deploy.sh"),
    ("environment", "runtime-canary", "creator-canary"),
    ("artifact_prefix", "runtime-host-deployment-", "creator-host-deployment-"),
    ("workflow_title", "Deploy Web Runtime Host", "Deploy Creator Web Host"),
    ("release_label", "Runtime Host release", "Creator Web Host release"),
    # Concurrency group, dispatch receipt workflow name, evidence directory
    # and deployment `--target`.
    ("host_id", "web-runtime-host", "creator-web"),
)
RUNTIME_VALUES = {field: runtime for field, runtime, _ in HOST_FIELDS}
CREATOR_VALUES = {field: creator for field, _, creator in HOST_FIELDS}

REMEDY = (
    "why: the two Web Host deploy workflows must differ only in the Host "
    "fields listed in HOST_FIELDS, or one Host deploys under rules the other "
    "lacks; remedy: make the same change in both workflow files, or, if the "
    "difference is a new Host-specific value, add it to HOST_FIELDS in "
    "tests/build/web_host_deploy_workflow_parity_test.py"
)


def normalize(text: str, values: dict[str, str]) -> list[str]:
    lines = text.splitlines()
    for field, _, _ in HOST_FIELDS:
        placeholder = "{{" + field + "}}"
        lines = [line.replace(values[field], placeholder) for line in lines]
    return lines


def parity_differences(runtime_text: str, creator_text: str) -> list[str]:
    runtime = normalize(runtime_text, RUNTIME_VALUES)
    creator = normalize(creator_text, CREATOR_VALUES)
    differences = []
    matcher = difflib.SequenceMatcher(a=runtime, b=creator, autojunk=False)
    for tag, r1, r2, c1, c2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        for offset in range(max(r2 - r1, c2 - c1)):
            r, c = r1 + offset, c1 + offset
            runtime_line = runtime[r] if r < r2 else "<absent>"
            creator_line = creator[c] if c < c2 else "<absent>"
            differences.append(
                f"{RUNTIME}:{r + 1 if r < r2 else '-'} {runtime_line!r} != "
                f"{CREATOR}:{c + 1 if c < c2 else '-'} {creator_line!r}"
            )
    return differences


def identity_violations(text: str, own: dict[str, str], other: dict[str, str],
                        name: str) -> list[str]:
    violations = []
    for field, _, _ in HOST_FIELDS:
        if own[field] not in text:
            violations.append(f"{name} never uses its {field} {own[field]!r}")
        if other[field] in text:
            violations.append(f"{name} uses the other Host's {field} {other[field]!r}")
    return violations


class WebHostDeployWorkflowParityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = (WORKFLOWS / RUNTIME).read_text(encoding="utf-8")
        self.creator = (WORKFLOWS / CREATOR).read_text(encoding="utf-8")

    def test_workflows_differ_only_in_host_fields(self) -> None:
        differences = parity_differences(self.runtime, self.creator)
        self.assertEqual(differences, [], "\n".join(differences + [REMEDY]))

    def test_each_workflow_carries_only_its_own_host_identity(self) -> None:
        violations = identity_violations(
            self.runtime, RUNTIME_VALUES, CREATOR_VALUES, RUNTIME
        ) + identity_violations(self.creator, CREATOR_VALUES, RUNTIME_VALUES, CREATOR)
        self.assertEqual(violations, [], "\n".join(violations + [
            "why: a stale or copied Host value makes parity compare the wrong "
            "identities; remedy: correct the workflow or the HOST_FIELDS table"
        ]))


# The negative tests run on a synthetic pair rendered from the table, so a
# later edit to the real workflows cannot break them for an unrelated reason.
FIXTURE_TEMPLATE = """\
name: {workflow_title}
concurrency:
  group: {host_id}-production
jobs:
  deploy:
    timeout-minutes: 20
    environment: {environment}
    steps:
      - name: Deploy signed {release_label} to Cloudflare
        run: {deploy_script} deploy --target {host_id}
      - with:
          name: {artifact_prefix}evidence
"""


def fixture(values: dict[str, str]) -> str:
    return FIXTURE_TEMPLATE.format(**values)


class ParityFailureReportingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = fixture(RUNTIME_VALUES)
        self.creator = fixture(CREATOR_VALUES)

    def test_fixture_pair_is_in_parity(self) -> None:
        self.assertEqual(parity_differences(self.runtime, self.creator), [])

    def test_non_host_change_in_one_copy_is_reported_with_its_line(self) -> None:
        mutated = self.creator.replace("timeout-minutes: 20", "timeout-minutes: 25")
        self.assertEqual(parity_differences(self.runtime, mutated), [
            f"{RUNTIME}:6 '    timeout-minutes: 20' != "
            f"{CREATOR}:6 '    timeout-minutes: 25'",
        ])

    def test_line_present_in_only_one_copy_is_reported(self) -> None:
        mutated = self.runtime.replace("jobs:\n", "permissions:\n  actions: write\njobs:\n")
        self.assertEqual(parity_differences(mutated, self.creator), [
            f"{RUNTIME}:4 'permissions:' != {CREATOR}:- '<absent>'",
            f"{RUNTIME}:5 '  actions: write' != {CREATOR}:- '<absent>'",
        ])

    def test_copied_identity_of_the_other_host_is_reported(self) -> None:
        mutated = self.runtime.replace("runtime-canary", "creator-canary")
        violations = identity_violations(mutated, RUNTIME_VALUES, CREATOR_VALUES, RUNTIME)
        self.assertEqual(violations, [
            f"{RUNTIME} never uses its environment 'runtime-canary'",
            f"{RUNTIME} uses the other Host's environment 'creator-canary'",
        ])


if __name__ == "__main__":
    unittest.main()
