#!/usr/bin/env python3
"""Contract tests: every Web proof owns the server its browsers drive.

Two runner services share the `ci-web-heavy` host. A Playwright-managed
`webServer` must know its URL before the server exists, so it can only bind a
fixed port: concurrent lanes contend for it, and a server leaked by a crashed
lane keeps holding it and fails every later lane at startup (issue #297). The
proofs therefore start their own server on a kernel-assigned ephemeral port
and pass its base URL in, and the Playwright config has no managed server and
no default base URL to fall back to.
"""

from __future__ import annotations

from pathlib import Path
import os
import json
import sys
from types import SimpleNamespace
from unittest import mock
import re
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYWRIGHT_CONFIG = REPO_ROOT / "tests/platform/web/playwright.config.mjs"
PLAYWRIGHT_INVOCATION = re.compile(
    r'npm --prefix "\$(?:web_test_root|repo_root/tests/platform/web)" test'
)
EXTERNAL_SERVER = re.compile(r"LMDJ_(?:WEB_HOST|CREATOR_WEB)_EXTERNAL_SERVER=1")
# Every script that drives the shared Playwright project, mapped to the
# environment variable naming the server it owns and, where the invocation is
# not a direct command, the shell function that owns both.
PROOF_SCRIPTS = {
    "scripts/web-toolchain-conformance.sh": ("LMDJ_WEB_HOST_BASE_URL", None),
    "scripts/web-runtime-host.sh": ("LMDJ_WEB_HOST_BASE_URL", None),
    "scripts/creator-web.sh": ("LMDJ_CREATOR_WEB_BASE_URL", None),
}


def playwright_commands(text: str) -> list[str]:
    """Return each direct Playwright invocation with its leading environment."""
    commands: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not PLAYWRIGHT_INVOCATION.search(line):
            continue
        start = index
        while start > 0 and lines[start - 1].rstrip().endswith("\\"):
            start -= 1
        commands.append("\n".join(lines[start : index + 1]))
    return commands


def shell_function(text: str, name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{\n(.*?)^\}}$", text, re.DOTALL | re.MULTILINE)
    if match is None:
        raise AssertionError(f"shell function {name}() is missing")
    return match.group(1)


class WebVerificationModes(unittest.TestCase):
    def invoke(self, host, mode, *, browser_status=0, diff_status=0):
        name = "proof_creator" if host == "creator" else "proof_host"
        filename = "creator-web.sh" if host == "creator" else "web-runtime-host.sh"
        body = shell_function((REPO_ROOT / "scripts" / filename).read_text(), name)
        helpers = ("activate_toolchain require_dependencies require_playwright "
                   "verify_browser_fixture_generator run_audio_worklet_conformance "
                   "generate_project_fixture generate_sample_editor_fixture "
                   "clean_creator configure_creator build_creator package_creator test_creator test_creator_ui "
                   "clean_host configure_host build_host run_nonbrowser_tests "
                   "generate_browser_fixtures verify_proof_fixture_inventory python3 cmake").split()
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace"
            program = "set -eu\n" + "\n".join(
                f'{helper}() {{ printf "%s\\n" "{helper} $*" >> "$TRACE"; }}'
                for helper in helpers)
            program += '''
git() { :; }
mktemp() { printf '%s\\n' /proof; }
diff() { printf '%s\\n' "diff $*" >> "$TRACE"; return "$DIFF_STATUS"; }
run_browser_gate() { printf '%s\\n' "run_browser_gate $*" >> "$TRACE"; return "$BROWSER_STATUS"; }
repo_root=/repo
web_test_root=/repo/tests/platform/web
dist_root=/dist
fixture_source_root=/fixtures
'''
            program += name + "() {\n" + body + "\n}\n" + name + ' "$MODE"\n'
            result = subprocess.run(["bash", "-c", program], capture_output=True, text=True,
                                    env={**os.environ, "TRACE": str(trace), "MODE": mode,
                                         "DIFF_STATUS": str(diff_status),
                                         "BROWSER_STATUS": str(browser_status)})
            return result, trace.read_text().splitlines()

    def test_quick_builds_once_without_cleaning_or_reproducibility_claim(self):
        for host, suffix in (("creator", "creator"), ("runtime", "host")):
            with self.subTest(host=host):
                result, calls = self.invoke(host, "quick")
                self.assertEqual(result.returncode, 0, result.stderr)
                names = [call.split()[0] for call in calls]
                self.assertEqual(names.count("build_" + suffix), 1)
                self.assertNotIn("clean_" + suffix, names)
                self.assertNotIn("diff", names)
                self.assertIn("Quick: PASS", result.stdout)
                self.assertNotIn("reproducibility: PASS", result.stdout)
                self.assertNotIn("Proof: PASS", result.stdout)

    def test_smoke_builds_once_runs_all_ui_tests_and_durable_journey(self):
        result, calls = self.invoke("creator", "smoke")
        self.assertEqual(result.returncode, 0, result.stderr)
        names = [call.split()[0] for call in calls]
        self.assertEqual(names, ["activate_toolchain", "require_dependencies",
                                "configure_creator", "build_creator", "package_creator",
                                "test_creator_ui", "run_browser_gate"])
        self.assertEqual(calls[-1], "run_browser_gate    smoke")
        self.assertIn("Smoke: PASS", result.stdout)
        self.assertNotIn("Proof: PASS", result.stdout)
        self.assertNotIn("Quick: PASS", result.stdout)

    def test_smoke_browser_failure_is_not_a_passing_result(self):
        result, _ = self.invoke("creator", "smoke", browser_status=9)
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertNotIn("Smoke: PASS", result.stdout)

    def test_full_keeps_two_clean_builds_and_byte_comparison(self):
        for host, suffix in (("creator", "creator"), ("runtime", "host")):
            with self.subTest(host=host):
                result, calls = self.invoke(host, "proof")
                self.assertEqual(result.returncode, 0, result.stderr)
                build_calls = [call.split()[0] for call in calls
                               if call.split()[0] in {"clean_" + suffix, "configure_" + suffix,
                                                      "build_" + suffix, "diff"}]
                self.assertEqual(build_calls, ["clean_" + suffix, "configure_" + suffix,
                                              "build_" + suffix] * 2 + ["diff"])
                self.assertIn("reproducibility: PASS", result.stdout)
                self.assertIn("Proof: PASS", result.stdout)

    def test_each_mode_reaches_complete_journey_with_all_fixture_arguments(self):
        # Independent absolute inventories: comparing the two modes alone
        # would miss a fixture/journey removed from both.
        for mode in ("quick", "proof"):
            result, calls = self.invoke("creator", mode)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("generate_project_fixture /proof/creator-proof-bundle.lmdj", calls)
            self.assertIn("generate_project_fixture /proof/overview/creator-overview-bundle.lmdj overview", calls)
            self.assertIn("generate_sample_editor_fixture /proof/creator-sample-proof-bundle.lmdj", calls)
            self.assertIn("run_browser_gate /proof/creator-proof-bundle.lmdj /proof/creator-sample-proof-bundle.lmdj /proof/creator-candidate-proof-bundle.lmdj", calls)
            result, calls = self.invoke("runtime", mode)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("run_audio_worklet_conformance ", calls)
            self.assertIn("run_nonbrowser_tests ", calls)
            self.assertIn("verify_proof_fixture_inventory /proof/fixtures", calls)
            self.assertIn("run_browser_gate /proof/dist /proof/fixtures 1", calls)

    def test_browser_failure_is_not_reported_as_quick_or_full_pass(self):
        for host in ("creator", "runtime"):
            for mode in ("quick", "proof"):
                result, _ = self.invoke(host, mode, browser_status=9)
                self.assertEqual(result.returncode, 9, result.stderr)
                self.assertNotIn("Quick: PASS", result.stdout)
                self.assertNotIn("Proof: PASS", result.stdout)

    def test_full_reproducibility_failure_stops_before_browser_journeys(self):
        for host in ("creator", "runtime"):
            result, calls = self.invoke(host, "proof", diff_status=1)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertFalse(any(call.startswith("run_browser_gate ") for call in calls))


class CreatorFixtureWorkloads(unittest.TestCase):
    def assignments(self, layout):
        source = shell_function((REPO_ROOT / "scripts/creator-web.sh").read_text(), "generate_project_fixture")
        program = source.split("<<'PY'\n", 1)[1].split("\nPY", 1)[0]
        calls = []
        def invoke(command, **kwargs):
            request = json.loads(command[-1])
            calls.append(request)
            revision = 0 if request["operation"] == "project.create" else request.get("expected_revision", 0) + 1
            return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({"ok": True, "project_revision": revision}))
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(sys, "argv", ["-", "/core", "/assembly", "/kick.wav", directory, layout]), \
                mock.patch.object(subprocess, "run", side_effect=invoke):
            exec(compile(program, "<real-fixture-generator>", "exec"), {})
        return calls

    def test_general_fixture_retains_all_64_assignments_and_pattern(self):
        calls = self.assignments("all")
        self.assertEqual(len(calls), 67)
        self.assertEqual([r["slot"] for r in calls if r["operation"] == "pad.assign"],
                         [{"bank": n // 16, "pad": n % 16} for n in range(64)])
        self.assertEqual(calls[-1]["operation"], "pattern.create")
        self.assertEqual(calls[-1]["expected_revision"], 65)

    def test_overview_fixture_keeps_b03_and_only_its_required_history(self):
        calls = self.assignments("overview")
        self.assertEqual([r["operation"] for r in calls],
                         ["project.create", "asset.import", "pad.assign", "pattern.create"])
        self.assertEqual(calls[2]["slot"], {"bank": 1, "pad": 2})
        self.assertEqual(calls[-1]["expected_revision"], 2)


class CreatorBrowserWorkloads(unittest.TestCase):
    SERIAL_SLOTS = ["catalog-chromium", "sample-chromium", "webkit",
                    "capture-chromium", "capture-denied-chromium", "sample-webkit"]

    def invoke(self, mode, fail_slot=""):
        text = (REPO_ROOT / "scripts/creator-web.sh").read_text()
        functions = "".join(
            f"{name}() {{\n{shell_function(text, name)}\n}}\n"
            for name in ("start_proof_server", "run_serial_browser_groups", "run_browser_gate"))
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace"
            program = r"""
set -euo pipefail
repo_root="$ROOT"
creator_root="$ROOT/apps/creator-web"
web_test_root="$ROOT/tests/platform/web"
build_root="$WORK"
dist_root="$WORK"
required_sample_editor_spec="$web_test_root/creator/creator_web_sample_editor.spec.mjs"
required_capture_spec="$web_test_root/creator/creator_web_capture.spec.mjs"
proof_server_pid=''
proof_server_ready_root=''
serial_server_pid=''
serial_server_ready_root=''
serial_groups_pid=''
started_server_port=''
cleanup_server() {
  local pid
  for pid in "$serial_groups_pid" "$serial_server_pid" "$proof_server_pid"; do
    [[ -z "$pid" ]] || { kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; }
  done
  serial_groups_pid=''
  serial_server_pid=''
  proof_server_pid=''
}
trap cleanup_server EXIT
mktemp() { command mktemp -d "$WORK/server.XXXXXX"; }
python3() {
  case "$1" in
    */serve_distribution.py)
      while [[ $# -gt 0 && "$1" != --ready-file ]]; do shift; done
      echo server >> "$WORK/servers"
      touch "$2"; exec sleep 30 ;;
    -c) printf '%s\n' fixture-nonce ;;
    -)
      cat >/dev/null
      if [[ "$2" == */host-manifest.json ]]; then
        printf '%s\n' '1.0.0.0 1.0.0'
      else
        printf '%s\n' "$((12344 + $(wc -l < "$WORK/servers")))"
      fi
      ;;
    *) return 64 ;;
  esac
}
npm() {
  # The pool and the first serial group each wait, bounded, to observe the
  # other in flight. Either order of a one-after-the-other run is recorded
  # as running alone instead of overlapped.
  local overlap=''
  case "$LMDJ_WEB_RESULTS_SLOT" in
    catalog-chromium)
      overlap=serial-alone
      for _ in $(seq 1 100); do
        [[ -f "$WORK/pool-running" ]] && { overlap=overlapped; break; }
        sleep 0.05
      done
      touch "$WORK/serial-started"
      ;;
    chromium)
      touch "$WORK/pool-running"
      overlap=pool-alone
      for _ in $(seq 1 100); do
        [[ -f "$WORK/serial-started" ]] && { overlap=overlapped; break; }
        sleep 0.05
      done
      rm -f "$WORK/pool-running"
      ;;
  esac
  local sigint
  sigint="$(command python3 -c 'import signal; print(signal.getsignal(signal.SIGINT) is signal.SIG_IGN and "ignored" or "default")')"
  printf '%s|%s|%s|%s|%s|%s\n' "$LMDJ_CREATOR_WEB_BASE_URL" "$LMDJ_WEB_RESULTS_SLOT" \
    "${LMDJ_SOUNDSET_CATALOG_UPSTREAM_FILE:-}" "$overlap" "$sigint" "$*" >> "$TRACE"
  [[ "$LMDJ_WEB_RESULTS_SLOT" != "$FAIL_SLOT" ]] || return 17
}
"""
            program += functions + 'run_browser_gate /main /sample /candidate "$MODE"\n'
            result = subprocess.run(["bash", "-c", program], capture_output=True, text=True,
                                    timeout=30, env={**os.environ, "ROOT": str(REPO_ROOT),
                                        "WORK": directory, "TRACE": str(trace), "MODE": mode,
                                        "FAIL_SLOT": fail_slot})
            calls = [dict(zip(("url", "slot", "upstream", "overlap", "sigint", "args"),
                              line.split("|", 5)))
                     for line in trace.read_text().splitlines()]
            return result, calls

    def test_smoke_executes_only_the_complete_deployment_journey(self):
        result, calls = self.invoke("smoke")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["url"], "http://127.0.0.1:12345")
        self.assertEqual(calls[0]["slot"], "deployment-chromium")
        self.assertIn("--project=creator-deployment deployment/creator_web_deployment.spec.mjs",
                      calls[0]["args"])

    def test_complete_browser_inventory_is_retained_independently(self):
        result, calls = self.invoke("journey")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(call["slot"] for call in calls), sorted(
            ["chromium", "deployment-chromium"] + self.SERIAL_SLOTS))
        self.assertEqual(calls[-1]["slot"], "deployment-chromium")

    def test_serial_groups_keep_their_order(self):
        result, calls = self.invoke("journey")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call["slot"] for call in calls if call["slot"] in self.SERIAL_SLOTS],
                         self.SERIAL_SLOTS)

    def test_serial_groups_overlap_the_independent_pool(self):
        # #2286: run one after the other, the groups exceed the 35-minute job.
        result, calls = self.invoke("journey")
        self.assertEqual(result.returncode, 0, result.stderr)
        first = [call for call in calls if call["slot"] in ("chromium", "catalog-chromium")]
        self.assertEqual(sorted(call["overlap"] for call in first), ["overlapped", "overlapped"])

    def test_serial_groups_keep_a_default_sigint_disposition(self):
        # An asynchronous command started without job control ignores SIGINT
        # (.agents/pitfalls/background-proof-inherits-ignored-signals.md).
        result, calls = self.invoke("journey")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({call["sigint"] for call in calls if call["slot"] in self.SERIAL_SLOTS},
                         {"default"})

    def test_independent_pool_runs_three_workers(self):
        result, calls = self.invoke("journey")
        self.assertEqual(result.returncode, 0, result.stderr)
        pool = [call for call in calls if call["slot"] == "chromium"]
        self.assertEqual(len(pool), 1)
        self.assertIn("--project=chromium --workers=3 ", pool[0]["args"])

    def test_serial_groups_drive_their_own_server_and_catalog_file(self):
        result, calls = self.invoke("journey")
        self.assertEqual(result.returncode, 0, result.stderr)
        by_slot = {call["slot"]: call for call in calls}
        pool_url = by_slot["chromium"]["url"]
        self.assertEqual(by_slot["deployment-chromium"]["url"], pool_url)
        serial_urls = {by_slot[slot]["url"] for slot in self.SERIAL_SLOTS}
        self.assertEqual(len(serial_urls), 1)
        self.assertNotIn(pool_url, serial_urls)
        pool_upstream = Path(by_slot["chromium"]["upstream"])
        serial_upstreams = {by_slot[slot]["upstream"] for slot in self.SERIAL_SLOTS}
        self.assertEqual(len(serial_upstreams), 1)
        serial_upstream = Path(serial_upstreams.pop())
        self.assertEqual(pool_upstream.name, "catalog-upstream")
        self.assertEqual(serial_upstream.name, "catalog-upstream")
        self.assertNotEqual(serial_upstream.parent, pool_upstream.parent)

    def test_failure_of_the_independent_pool_propagates(self):
        result, _ = self.invoke("journey", fail_slot="chromium")
        self.assertEqual(result.returncode, 17, result.stderr)

    def test_failure_of_a_serial_group_propagates_and_later_groups_still_run(self):
        result, calls = self.invoke("journey", fail_slot="capture-chromium")
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual([call["slot"] for call in calls if call["slot"] in self.SERIAL_SLOTS],
                         self.SERIAL_SLOTS)

    def test_failure_of_the_durable_smoke_propagates(self):
        result, calls = self.invoke("smoke", fail_slot="deployment-chromium")
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(len(calls), 1)


class PlaywrightConfigOwnsNoServer(unittest.TestCase):
    def setUp(self) -> None:
        self.source = "\n".join(
            line
            for line in PLAYWRIGHT_CONFIG.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("//")
        )

    def test_declares_no_managed_web_server(self) -> None:
        for forbidden in ("webServer", "reuseExistingServer"):
            self.assertNotIn(
                forbidden,
                self.source,
                f"{forbidden} reintroduces a fixed-port server shared by both "
                "runner services on the Web host",
            )

    def test_declares_no_fixed_loopback_port(self) -> None:
        self.assertNotRegex(
            self.source,
            r"127\.0\.0\.1:\d|\b41\d{2}\b",
            "the Playwright config must not name a port; the lane's own "
            "server publishes the ephemeral port it was given",
        )

    def test_fails_closed_without_an_owned_base_url(self) -> None:
        self.assertRegex(
            self.source,
            r"if \(!browserProofBaseURL\) \{\s*throw new Error\(",
            "a run with no owned base URL must fail closed instead of "
            "proving itself against whatever already listens",
        )


class ProofScriptsOwnTheirServer(unittest.TestCase):
    def test_toolchain_proof_binds_an_ephemeral_port(self) -> None:
        text = (REPO_ROOT / "scripts/web-toolchain-conformance.sh").read_text(
            encoding="utf-8"
        )
        self.assertRegex(
            text,
            r'server\.py" \\\n\s+--root "\$toolchain_root" \\\n'
            r"\s+--port 0 \\\n\s+--write-port",
            "the Proof server must take a kernel-assigned port and publish it",
        )
        self.assertIn(
            'service": "web-toolchain-conformance"',
            text,
            "the Proof must confirm the port it read serves this service",
        )

    def test_every_playwright_invocation_receives_an_owned_base_url(self) -> None:
        for relative, (base_url, function) in PROOF_SCRIPTS.items():
            text = (REPO_ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(script=relative):
                self.assertRegex(
                    text,
                    PLAYWRIGHT_INVOCATION,
                    "the script no longer drives Playwright; drop it from "
                    "PROOF_SCRIPTS instead of leaving it unchecked",
                )
                scopes = (
                    playwright_commands(text)
                    if function is None
                    else [shell_function(text, function)]
                )
                self.assertTrue(scopes, "no Playwright invocation was located")
                for scope in scopes:
                    self.assertIn(
                        f"{base_url}=",
                        scope,
                        f"{relative} runs Playwright without naming the "
                        "server it owns",
                    )
                    self.assertRegex(
                        scope,
                        EXTERNAL_SERVER,
                        f"{relative} runs Playwright without declaring the "
                        "server external, so Playwright would manage one",
                    )


if __name__ == "__main__":
    unittest.main()
