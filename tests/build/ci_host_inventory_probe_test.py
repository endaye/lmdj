#!/usr/bin/env python3
"""Executable fixtures for host inventory evidence and parity outcomes."""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/ci/host_inventory_probe.py"
SANITIZER = ROOT / "scripts/ci/host/configure-sanitizer-aslr.sh"
SPEC = importlib.util.spec_from_file_location("host_inventory_probe", PROBE)
assert SPEC and SPEC.loader
PROBE_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE_MODULE)


class HostInventoryProbeTest(unittest.TestCase):
    def run_probe(self, expected: dict, actual: str | dict | None, *, mmap: str = "28", mmap_missing: bool = False, cgroup: str = "0::/system.slice/actions.runner.example.service\n", sanitizer: Path = SANITIZER, proc_stat: str | None = None, proc_stat_missing: bool = False, tool_root: Path | None = None, output_format: str = "json", summary_path: Path | None = None, free_text: str | None = None, df_text: str | None = None, host: str = "netcup", role: str = "ci-core"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected_path = root / "expected.json"
            actual_path = root / "actual.json"
            mmap_path = root / "mmap"
            cgroup_path = root / "cgroup"
            proc_stat_path = root / "proc-stat"
            free_path = root / "free"
            df_path = root / "df"
            expected_path.write_text(json.dumps(expected), encoding="utf-8")
            if actual is None:
                pass
            elif isinstance(actual, dict):
                actual_path.write_text(json.dumps(actual), encoding="utf-8")
            else:
                actual_path.write_text(actual, encoding="utf-8")
            if not mmap_missing:
                mmap_path.write_text(mmap, encoding="utf-8")
            cgroup_path.write_text(cgroup, encoding="utf-8")
            if not proc_stat_missing:
                proc_stat_path.write_text(proc_stat or "cpu 1 2 3 4 5 6 11 13 17 19\n", encoding="utf-8")
            if free_text is not None:
                free_path.write_text(free_text, encoding="utf-8")
            if df_text is not None:
                df_path.write_text(df_text, encoding="utf-8")
            if tool_root:
                tool_root.mkdir(parents=True, exist_ok=True)
            environment = {
                **os.environ,
                "RUNNER_NAME": "netcup-lmdj-linux-01",
                "GITHUB_SERVER_URL": "https://github.example",
                "GITHUB_REPOSITORY": "endaye/lmdj",
                "GITHUB_RUN_ID": "1234",
                "GITHUB_RUN_ATTEMPT": "2",
                "GITHUB_SHA": "a" * 40,
                "GITHUB_WORKFLOW_SHA": "b" * 40,
            }
            if summary_path:
                environment["GITHUB_STEP_SUMMARY"] = str(summary_path)
            command = [
                    "python3", str(PROBE), "--host", host, "--role", role,
                    "--expected-config", str(expected_path), "--actual-config", str(actual_path),
                    "--sanitizer-script", str(sanitizer), "--mmap-file", str(mmap_path),
                    "--cgroup-file", str(cgroup_path), "--proc-stat-file", str(proc_stat_path),
                    "--format", output_format,
                ]
            if tool_root:
                command += ["--tool-root", str(tool_root)]
            if free_text is not None:
                command += ["--free-file", str(free_path)]
            if df_text is not None:
                command += ["--df-file", str(df_path)]
            result = subprocess.run(
                command,
                cwd=ROOT, env=environment, text=True, capture_output=True, check=False,
            )
            return result, (json.loads(result.stdout) if output_format == "json" else result.stdout)

    def test_matching_config_and_sanitizer_are_measured_with_exact_provenance(self):
        config = {"host": "netcup", "baseline": [], "elastic": [], "pin": 1}
        result, evidence = self.run_probe(config, config)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(evidence["controller_config"]["status"], "match")
        self.assertEqual(evidence["sanitizer"]["status"], "match")
        self.assertEqual(evidence["provenance"]["service_unit"], "actions.runner.example.service")
        self.assertEqual(evidence["provenance"]["run_url"], "https://github.example/endaye/lmdj/actions/runs/1234")
        self.assertEqual(evidence["provenance"]["run_attempt"], "2")
        self.assertEqual(evidence["provenance"]["revision"], "a" * 40)
        self.assertEqual(evidence["provenance"]["workflow_sha"], "b" * 40)
        expected_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        self.assertEqual(evidence["provenance"]["git_head"], expected_head)

    def test_readable_config_mismatch_fails_closed_without_masking_sanitizer(self):
        config = {"host": "netcup", "baseline": [], "elastic": [], "pin": 1}
        result, evidence = self.run_probe(config, {**config, "pin": 2}, mmap="28")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(evidence["controller_config"]["status"], "mismatch")
        self.assertEqual(evidence["sanitizer"]["status"], "match")

    def test_readable_sanitizer_mismatch_fails_closed_without_masking_config(self):
        config = {"host": "netcup", "baseline": [], "elastic": [], "pin": 1}
        result, evidence = self.run_probe(config, config, mmap="32")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(evidence["controller_config"]["status"], "match")
        self.assertEqual(evidence["sanitizer"]["status"], "mismatch")

    def test_malformed_or_missing_config_is_blocked_without_claiming_parity(self):
        config = {"host": "netcup", "baseline": [], "elastic": []}
        malformed, malformed_evidence = self.run_probe(config, "{not-json")
        self.assertEqual(malformed.returncode, 0)
        self.assertEqual(malformed_evidence["controller_config"]["status"], "malformed")
        missing, missing_evidence = self.run_probe(config, None)
        self.assertEqual(missing.returncode, 0)
        self.assertEqual(missing_evidence["controller_config"]["status"], "missing")

    def test_unavailable_cgroup_and_sanitizer_source_are_explicit(self):
        config = {"host": "netcup", "baseline": [], "elastic": []}
        with tempfile.TemporaryDirectory() as directory:
            missing_script = Path(directory) / "missing-sanitizer.sh"
            result, evidence = self.run_probe(config, config, cgroup="not-a-cgroup\n", sanitizer=missing_script)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(evidence["provenance"]["service_unit"], "unavailable")
        self.assertEqual(evidence["sanitizer"]["status"], "unavailable")

    def test_missing_mmap_fixture_does_not_crash_or_claim_readiness(self):
        config = {"host": "netcup", "baseline": [], "elastic": []}
        result, evidence = self.run_probe(config, config, mmap_missing=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(evidence["sanitizer"]["status"], "unavailable")

    def test_proc_stat_distinct_counters_and_short_or_missing_inputs(self):
        config = {"host": "netcup", "baseline": [], "elastic": []}
        before = "cpu 1 2 3 4 5 11 13 17 19\n"
        after = "cpu 9 9 9 9 9 14 18 20 22\n"
        self.assertEqual(PROBE_MODULE.parse_cpu_fields(before), (11, 13, 17))
        self.assertEqual(PROBE_MODULE.parse_cpu_fields(after), (14, 18, 20))
        self.assertEqual(PROBE_MODULE.cpu_delta(PROBE_MODULE.parse_cpu_fields(before), PROBE_MODULE.parse_cpu_fields(after)), {"irq": "3", "softirq": "5", "steal": "3"})
        for count in range(0, 8):
            with self.subTest(truncated_fields=count):
                self.assertIsNone(PROBE_MODULE.parse_cpu_fields("cpu " + " ".join(str(i) for i in range(count)) + "\n"))
        self.assertIsNone(PROBE_MODULE.parse_cpu_fields(before + after))
        short, short_evidence = self.run_probe(config, config, proc_stat="cpu 1 2\n")
        self.assertEqual(short.returncode, 0)
        self.assertEqual(short_evidence["accounting"], {"status": "unavailable"})
        missing, missing_evidence = self.run_probe(config, config, proc_stat_missing=True)
        self.assertEqual(missing.returncode, 0)
        self.assertEqual(missing_evidence["accounting"], {"status": "unavailable"})

    def test_markdown_summary_is_complete_and_reaches_step_summary(self):
        config = {"host": "netcup", "baseline": [], "elastic": []}
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.md"
            result, output = self.run_probe(config, config, output_format="markdown", summary_path=summary)
            self.assertEqual(result.returncode, 0)
            saved = summary.read_text(encoding="utf-8")
        self.assertEqual(saved, output)
        for marker in ("### Elastic controller parity", "### Sanitizer host parity", "### Native Core toolchain", "### Kernel accounting", "### Idle-host accounting"):
            self.assertIn(marker, saved)

    def test_missing_tools_are_reported_and_unsupported_contabo_core_is_blocked(self):
        config = {"host": "netcup", "baseline": [], "elastic": []}
        with tempfile.TemporaryDirectory() as directory:
            result, evidence = self.run_probe(config, config, tool_root=Path(directory))
        self.assertEqual(result.returncode, 0)
        self.assertTrue(all(row["present"] == "**no**" for row in evidence["tools"]))
        blocked, blocked_evidence = self.run_probe(config, config, host="contabo", role="ci-core")
        self.assertEqual(blocked.returncode, 78)
        self.assertEqual(blocked_evidence["status"], "blocked")

    def test_tool_root_executes_the_discovered_path(self):
        config = {"host": "netcup", "baseline": [], "elastic": []}
        with tempfile.TemporaryDirectory() as directory:
            tool_root = Path(directory)
            tool = tool_root / "clang-22"
            tool.write_text("#!/bin/sh\nprintf 'fixture-clang\\n'\n", encoding="utf-8")
            tool.chmod(0o755)
            result, evidence = self.run_probe(config, config, tool_root=tool_root)
        self.assertEqual(result.returncode, 0)
        clang = next(row for row in evidence["tools"] if row["tool"] == "clang-22")
        self.assertEqual(clang["version"], "fixture-clang")

    def test_short_or_missing_free_and_df_outputs_are_unavailable_not_crashes(self):
        config = {"host": "netcup", "baseline": [], "elastic": []}
        result, evidence = self.run_probe(config, config, free_text="Mem:\n", df_text="Filesystem\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(evidence["capacity"]["memory"], "unavailable")
        self.assertEqual(evidence["capacity"]["workspace_free"], "unavailable")


if __name__ == "__main__":
    unittest.main()
