#!/usr/bin/env python3
"""The sharded release-suite runner keeps whole modules together and fails closed."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_suite_runner as runner

PASSING = """import unittest
class T(unittest.TestCase):
{cases}
"""


def module(cases: int, failing: int = 0) -> str:
    lines = [f"    def test_{i}(self): pass" for i in range(cases)]
    lines += [f"    def test_fail_{i}(self): self.fail('fixture failure')" for i in range(failing)]
    return PASSING.format(cases="\n".join(lines))


class RunnerFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-release-suite-runner-")
        self.start = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        (self.start / "release_alpha_test.py").write_text(module(3))
        (self.start / "release_beta_test.py").write_text(module(2))
        (self.start / "release_gamma_test.py").write_text(module(1))
        (self.start / "unrelated_test.py").write_text(module(1))
        # In-process discovery imports the fixture modules; drop them so the
        # next case's start directory is discovered afresh.
        self.addCleanup(self.forget_fixture_modules)

    def forget_fixture_modules(self) -> None:
        for name in [name for name in sys.modules if name.startswith(("release_alpha", "release_beta", "release_gamma", "release_delta", "unrelated_test"))]:
            del sys.modules[name]
        while str(self.start) in sys.path:
            sys.path.remove(str(self.start))

    def run_runner(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(runner.__file__), "--start", str(self.start), *arguments],
            cwd=runner.ROOT, capture_output=True, text=True, timeout=90, check=False)


class DiscoveryAndPartitionTest(RunnerFixture):
    def test_discovery_groups_ids_by_module_and_ignores_other_patterns(self) -> None:
        modules = runner.discover(self.start)
        self.assertEqual(list(modules), ["release_alpha_test", "release_beta_test", "release_gamma_test"])
        self.assertEqual([len(ids) for ids in modules.values()], [3, 2, 1])

    def test_partition_keeps_modules_whole_covers_each_once_and_is_deterministic(self) -> None:
        modules = runner.discover(self.start)
        first = runner.partition(modules, 2)
        self.assertEqual(first, runner.partition(modules, 2))
        self.assertEqual(sorted(name for bucket in first for name in bucket), sorted(modules))
        self.assertEqual(first, [["release_alpha_test"], ["release_beta_test", "release_gamma_test"]])
        self.assertEqual(len(runner.partition(modules, 8)), 3, "empty buckets are dropped")

    def test_default_shard_count_is_bounded_by_four(self) -> None:
        with patch.object(runner.os, "cpu_count", return_value=16):
            self.assertEqual(runner.resolve_shard_count(None), 4)
        with patch.object(runner.os, "cpu_count", return_value=2):
            self.assertEqual(runner.resolve_shard_count(None), 2)
        with self.assertRaises(SystemExit):
            runner.resolve_shard_count(0)


class ExecutionTest(RunnerFixture):
    def test_every_discovered_test_runs_exactly_once_across_shards(self) -> None:
        completed = self.run_runner("--shards", "2")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Ran 6 of 6 discovered tests from 3 modules across 2 shards", completed.stderr)
        self.assertIn("slowest 6 tests:", completed.stderr)
        self.assertRegex(completed.stderr, r"\n +\d+\.\ds  release_alpha_test\.T\.test_0\n")
        self.assertTrue(completed.stderr.rstrip().endswith("OK"), completed.stderr)

    def test_a_failing_module_fails_the_run_and_surfaces_its_output(self) -> None:
        (self.start / "release_delta_test.py").write_text(module(1, failing=1))
        completed = self.run_runner("--shards", "2")
        self.assertEqual(completed.returncode, 1)
        self.assertIn("FAILED", completed.stderr)
        self.assertIn("release_delta_test", completed.stderr)
        self.assertIn("fixture failure", completed.stderr)
        self.assertIn("Ran 8 of 8 discovered tests", completed.stderr)

    def test_a_worker_that_skips_a_test_is_an_accounting_failure(self) -> None:
        original = runner.subprocess.Popen

        class SkippingChild:
            """A worker that reports success but never executed one discovered id."""

            def __init__(self, command, **keywords):
                report = Path(command[command.index("--worker") + 1])
                modules = command[command.index("--start") + 2:]
                ids = [test_id for name in modules
                       for test_id in runner.discover(Path(command[command.index("--start") + 1]))[name]]
                report.write_text(json.dumps({"executed": ids[1:], "errors": [], "successful": True}))
                self.pid = 1

            def poll(self):
                return 0

            def wait(self):
                return 0

        stderr = io.StringIO()
        with patch.object(runner.subprocess, "Popen", SkippingChild), patch.object(sys, "stderr", stderr):
            status = runner.run_sharded(1, self.start)
        self.assertEqual(status, 1)
        self.assertIn("shard accounting failed: discovered 6 tests, executed 5", stderr.getvalue())
        self.assertIn("never executed: release_alpha_test.T.test_0", stderr.getvalue())
        del original

    def test_a_repeated_id_cannot_stand_in_for_a_missing_one(self) -> None:
        class RepeatingChild:
            """Same count as discovered: one id twice, another never."""

            def __init__(self, command, **keywords):
                ids = [test_id for name in command[command.index("--start") + 2:]
                       for test_id in runner.discover(Path(command[command.index("--start") + 1]))[name]]
                ids = [ids[0], *ids[:-1]]
                Path(command[command.index("--worker") + 1]).write_text(
                    json.dumps({"executed": ids, "errors": [], "successful": True}))
                self.pid = 1

            def poll(self):
                return 0

            def wait(self):
                return 0

        stderr = io.StringIO()
        with patch.object(runner.subprocess, "Popen", RepeatingChild), patch.object(sys, "stderr", stderr):
            status = runner.run_sharded(1, self.start)
        self.assertEqual(status, 1)
        self.assertIn("shard accounting failed: discovered 6 tests, executed 6", stderr.getvalue())
        self.assertIn("never executed: release_gamma_test.T.test_0", stderr.getvalue())
        self.assertIn("unexpected or repeated: release_alpha_test.T.test_0", stderr.getvalue())

    def test_a_truncated_worker_report_fails_the_shard_without_a_parent_crash(self) -> None:
        class TruncatingChild:
            """A worker killed mid-write: the report is half a JSON document."""

            def __init__(self, command, **keywords):
                Path(command[command.index("--worker") + 1]).write_text('{"executed": ["release_al')
                self.pid = 1

            def poll(self):
                return 0

            def wait(self):
                return 0

        stderr = io.StringIO()
        with patch.object(runner.subprocess, "Popen", TruncatingChild), patch.object(sys, "stderr", stderr):
            status = runner.run_sharded(1, self.start)
        self.assertEqual(status, 1)
        self.assertIn("worker report unreadable", stderr.getvalue())
        self.assertIn("shard accounting failed: discovered 6 tests, executed 0", stderr.getvalue())

    def test_a_hung_worker_is_killed_and_reported_with_the_other_shards(self) -> None:
        (self.start / "release_omega_test.py").write_text(
            "import time, unittest\nclass T(unittest.TestCase):\n    def test_hang(self): time.sleep(60)\n")
        completed = self.run_runner("--shards", "2", "--worker-timeout", "3")
        self.assertEqual(completed.returncode, 1)
        self.assertIn("hung past 3s and was killed", completed.stderr)
        self.assertIn("release_omega_test", completed.stderr)
        # The healthy shard still reports its complete run.
        self.assertRegex(completed.stderr, r"shard \d of 2: Ran \d+ tests")
        never = [line for line in completed.stderr.splitlines() if line.startswith("never executed:")]
        self.assertEqual(len(never), 1, completed.stderr)
        self.assertIn("release_omega_test.T.test_hang", never[0])

    def test_worker_mode_records_the_exact_executed_ids(self) -> None:
        report = self.start / "report.json"
        completed = self.run_runner("--worker", str(report), "release_beta_test", "release_gamma_test")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(report.read_text())
        self.assertEqual(payload["executed"],
                         ["release_beta_test.T.test_0", "release_beta_test.T.test_1", "release_gamma_test.T.test_0"])
        self.assertTrue(payload["successful"])
        self.assertEqual(set(payload["durations"]), set(payload["executed"]))

    def test_worker_refuses_a_module_resolved_outside_the_start_directory(self) -> None:
        # `start` is sys.path[0] in a real worker, so only a name already
        # bound elsewhere in this process can shadow it; bind one and check
        # that the worker refuses to run it instead of trusting the binding.
        shadow = self.start / "shadow"
        shadow.mkdir()
        (shadow / "release_beta_test.py").write_text(module(1))
        spec = importlib.util.spec_from_file_location("release_beta_test", shadow / "release_beta_test.py")
        bound = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bound)
        report = self.start / "report.json"
        stderr = io.StringIO()
        with patch.dict(sys.modules, {"release_beta_test": bound}), patch.object(sys, "stderr", stderr):
            status = runner.run_worker(report, ["release_beta_test"], self.start)
        self.assertEqual(status, 1)
        payload = json.loads(report.read_text())
        self.assertEqual(payload["executed"], [])
        self.assertIn("resolved to", payload["errors"][0])
        self.assertNotIn("Ran ", stderr.getvalue())

    def test_modules_outside_worker_mode_are_a_usage_error(self) -> None:
        completed = self.run_runner("release_alpha_test")
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
