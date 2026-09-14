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
NETCUP = REPO_ROOT / "scripts/ci/elastic-runner/netcup.json"
PROBE = REPO_ROOT / "scripts/ci/host_inventory_probe.py"


class HostInventoryWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = WORKFLOW.read_text(encoding="utf-8")
        self.probe = PROBE.read_text(encoding="utf-8")
        self.directives = "\n".join(
            line for line in self.source.splitlines()
            if not line.lstrip().startswith("#")
        )

    def test_it_is_dispatch_only_and_read_only(self) -> None:
        self.assertIn("workflow_dispatch:", self.source)
        self.assertNotRegex(self.directives, r"(?m)^  (?:pull_request|push|schedule):")
        self.assertIn("permissions:\n  contents: read", self.source)

    def test_it_runs_self_hosted_on_the_explicit_host(self) -> None:
        self.assertIn("- self-hosted", self.source)
        self.assertIn("${{ inputs.host }}", self.source)
        self.assertIn("inputs.host == 'netcup' && inputs.role", self.source)
        self.assertNotIn("runs-on: ubuntu-24.04", self.directives)

    def test_every_named_host_is_selectable_and_not_a_generic_pool(self) -> None:
        for host in ("netcup", "contabo"):
            with self.subTest(host=host):
                self.assertIn(f"- {host}\n", self.source)
        self.assertIn("explicit host label", self.source)
        self.assertNotIn("shared-with-staging", self.directives)

    def test_unsupported_host_role_pairs_are_rejected_after_targeting(self) -> None:
        self.assertIn(
            'if [ "$SELECTED_HOST" = contabo ] && [ "$SELECTED_ROLE" != ci-general ]',
            self.source,
        )
        self.assertIn("exit 78", self.source)
        self.assertIn("falsely standing in for both", self.source)

    def test_parity_checks_fail_only_on_readable_mismatch(self) -> None:
        self.assertIn("/etc/lmdj/elastic-runner.json", self.source)
        self.assertIn("scripts/ci/elastic-runner/${SELECTED_HOST}.json", self.source)
        self.assertIn("mismatch", self.probe)
        self.assertIn("blocked/unavailable", self.probe)
        self.assertIn("return 1 if config_status == \"mismatch\"", self.probe)

    def test_missing_capability_and_kernel_sources_remain_explicit_findings(self) -> None:
        self.assertIn("shutil.which", self.probe)
        self.assertIn("/boot/config-{platform.release()}", self.probe)
        self.assertIn("/proc/config.gz", self.probe)
        self.assertIn("readiness is not claimed", self.probe)

    def test_provenance_includes_host_runner_service_and_utc_source(self) -> None:
        for marker in (
            "host",
            "service_unit",
            "observed_at_utc",
            "revision",
            "git_head",
            "workflow_sha",
            "hostname",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.probe)
        self.assertIn("/proc/self/cgroup", self.probe)
        self.assertNotIn("list-units", self.probe)

    def test_checkout_is_pinned_and_does_not_persist_credentials(self) -> None:
        self.assertIn("de0fac2e4500dabe0009e67214ff5f5447ce83dd", self.source)
        self.assertIn("persist-credentials: false", self.source)
        self.assertIn("GITHUB_RUN_ATTEMPT", self.source)
        self.assertIn("GITHUB_WORKFLOW_SHA", self.source)
        self.assertIn("GITHUB_SHA", self.source)
        self.assertIn("GITHUB_STEP_SUMMARY", self.probe)

    def test_capacity_commands_are_read_once_and_short_output_is_guarded(self) -> None:
        self.assertEqual(self.probe.count('run("free", "-h")'), 1)
        self.assertEqual(self.probe.count('run("df", "-h", ".")'), 1)
        self.assertIn("len(free_lines[1].split()) > 1", self.probe)
        self.assertIn("len(df_lines[1].split()) > 3", self.probe)
        self.assertIn("run URL", self.source)

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
        for tool in ("clang-22", "clang++-22", "llvm-cov-22"):
            with self.subTest(tool=tool):
                self.assertIn(f"command -v {tool}", coverage_gate)
                self.assertIn("shutil.which", self.probe)
                self.assertIn(tool, self.probe)

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
        self.assertIn("A missing capability or unreadable source", self.probe)

    def test_its_ci_core_dispatch_is_registered_with_the_elastic_controller(self) -> None:
        """The role-scan gate cannot see this job; this test stands in for it.

        `runs-on` takes the role from a dispatch input, so the generic scan
        over workflows for literal `ci-core` never finds this one. Dispatched
        with `ci-core` it lands on a netcup service under the name
        `Host inventory (ci-core)`, and `_current_job_is_core` prefix-matches
        that against `core_job_names`. Unregistered, the controller classifies
        it as non-core and keeps admitting elastic load beside it.
        """
        import json as _json
        name = next(l.split("name:", 1)[1].strip()
                    for l in self.source.splitlines() if l.strip().startswith("name: Host inventory"))
        prefix = name.split(" (")[0]
        registered = _json.loads(NETCUP.read_text(encoding="utf-8"))["core_job_names"]
        self.assertIn(
            prefix, registered,
            msg=(f"why: the elastic controller prefix-matches the running job name "
                 f"against core_job_names and cannot see this job's role from the "
                 f"workflow text; remedy: keep {prefix!r} in "
                 f"scripts/ci/elastic-runner/netcup.json core_job_names"),
        )

    def test_it_cannot_change_the_host(self) -> None:
        for forbidden in (
            "apt-get",
            "sudo",
            "npm install",
            "pip install",
            "systemctl start",
            "systemctl stop",
            "systemctl enable",
            "systemctl set-property",
            "systemctl daemon-reload",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(
                    forbidden,
                    self.source + self.probe,
                    msg=(
                        "why: this workflow exists to observe a host, and a probe "
                        "that can alter one is no longer a measurement of what was "
                        "there; remedy: keep it to command -v and version output"
                    ),
                )


if __name__ == "__main__":
    unittest.main()
