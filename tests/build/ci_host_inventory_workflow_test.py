#!/usr/bin/env python3
"""Contract for the host inventory probe.

It exists to answer one question with measurement instead of assumption: what
does a self-hosted role already provide? #591 step 6 was blocked for days on
"provision clang-18/llvm-18 and a ccache on netcup" without anyone checking
which of those was actually missing.

Two properties keep it useful. It must report rather than assert, because a
missing tool is the finding and a red job would be indistinguishable from a
broken workflow. And it must stay incapable of doing anything but look.
"""

from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/ci-host-inventory.yml"
CONTABO = REPO_ROOT / "scripts/ci/elastic-runner/contabo.json"


class HostInventoryWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = WORKFLOW.read_text(encoding="utf-8")
        self.directives = "\n".join(
            line for line in self.source.splitlines()
            if not line.lstrip().startswith("#")
        )

    def test_it_is_dispatch_only_and_read_only(self) -> None:
        self.assertIn("workflow_dispatch:", self.source)
        self.assertNotRegex(self.directives, r"(?m)^  (?:pull_request|push|schedule):")
        self.assertIn("permissions:\n  contents: read", self.source)

    def test_it_runs_self_hosted_on_the_dispatched_role(self) -> None:
        self.assertIn("- self-hosted", self.source)
        self.assertIn("${{ inputs.role }}", self.source)
        self.assertNotIn("runs-on: ubuntu-24.04", self.directives)

    def test_every_role_is_selectable(self) -> None:
        """Inventorying one host is only useful against a baseline from another."""
        for role in ("ci-web-heavy", "ci-general", "ci-core"):
            with self.subTest(role=role):
                self.assertIn(f"- {role}\n", self.source)

    def test_it_probes_exactly_what_the_coverage_lane_requires(self) -> None:
        """A probe that checks different tools than the gate answers nothing."""
        coverage_gate = (REPO_ROOT / ".github/workflows/ci.yml").read_text(
            encoding="utf-8"
        )
        for tool in ("clang-18", "clang++-18", "llvm-cov-18"):
            with self.subTest(tool=tool):
                self.assertIn(f"command -v {tool}", coverage_gate)
                self.assertIn(tool, self.source)

    def test_a_missing_tool_is_a_finding_rather_than_a_failure(self) -> None:
        """`set -e` would abort on the first absent tool and report nothing else.

        The whole output is the answer, so the step must survive every probe
        that comes back negative.
        """
        self.assertIn(
            "set -uo pipefail",
            self.source,
            msg=(
                "why: with -e, the first missing tool ends the step and the "
                "remaining rows never print, turning a complete inventory into "
                "one line; remedy: keep set -uo pipefail without -e, and let "
                "each probe record its own yes or no"
            ),
        )
        self.assertNotIn("set -euo pipefail", self.source)

    def test_its_ci_core_dispatch_is_registered_with_the_elastic_controller(self) -> None:
        """The role-scan gate cannot see this job; this test stands in for it.

        `runs-on` takes the role from a dispatch input, so the generic scan
        over workflows for literal `ci-core` never finds this one. Dispatched
        with `ci-core` it lands on a Contabo service under the name
        `Host inventory (ci-core)`, and `_current_job_is_core` prefix-matches
        that against `core_job_names`. Unregistered, the controller classifies
        it as non-core and keeps admitting elastic load beside it.
        """
        import json as _json
        name = next(l.split("name:", 1)[1].strip()
                    for l in self.source.splitlines() if l.strip().startswith("name: Host inventory"))
        prefix = name.split(" (")[0]
        registered = _json.loads(CONTABO.read_text(encoding="utf-8"))["core_job_names"]
        self.assertIn(
            prefix, registered,
            msg=(f"why: the elastic controller prefix-matches the running job name "
                 f"against core_job_names and cannot see this job's role from the "
                 f"workflow text; remedy: keep {prefix!r} in "
                 f"scripts/ci/elastic-runner/contabo.json core_job_names"),
        )

    def test_it_cannot_change_the_host(self) -> None:
        for forbidden in ("apt-get", "sudo", "npm install", "pip install", "systemctl"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(
                    forbidden,
                    self.source,
                    msg=(
                        "why: this workflow exists to observe a host, and a probe "
                        "that can alter one is no longer a measurement of what was "
                        "there; remedy: keep it to command -v and version output"
                    ),
                )


if __name__ == "__main__":
    unittest.main()
