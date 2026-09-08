#!/usr/bin/env python3
"""Contract tests for trusted Core Nightly runner routing."""

from __future__ import annotations

from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/core-nightly.yml"
CORE_ROLE = (
    "runs-on: [self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool, ci-core]"
)
TSAN_COMMANDS = (
    "python3 tests/fixtures/audio/make_fixtures.py",
    "python3 tests/fixtures/golden/reference_render.py",
    "bash scripts/verify-core-dependencies.sh",
    "scripts/core.sh configure tsan",
    "scripts/core.sh build tsan",
    "scripts/core.sh test tsan stress",
)


class CoreNightlyWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def job(self, job_name: str) -> str:
        match = re.search(
            rf"^  {re.escape(job_name)}:\n(?P<body>.*?)(?=^  [a-z0-9-]+:|\Z)",
            self.source,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(
            match,
            "why: the Nightly routing contract cannot inspect the missing "
            f"{job_name} job; remedy: define {job_name} in core-nightly.yml",
        )
        assert match is not None
        return match.group("body")

    def test_release_stress_uses_the_native_core_role(self) -> None:
        stress = self.job("core-stress")
        message = (
            "why: trusted Release stress must queue on the native Core role "
            "instead of consuming Hosted Ubuntu; remedy: route core-stress "
            f"with {CORE_ROLE} and retain the bounded repeat command"
        )
        self.assertIn(CORE_ROLE, stress, message)
        self.assertNotIn("runs-on: ubuntu-24.04", stress, message)
        self.assertIn("--repeat until-fail:20", stress, message)

    def test_scheduled_tsan_runs_on_the_core_role(self) -> None:
        """Routing was accepted on same-revision evidence, and stays pinned.

        #693: the host caps `vm.mmap_rnd_bits` at 28, and the probe on
        netcup passed at that state. Without the cap no TSan runtime starts
        there, so the routing and the prerequisite check travel together.
        """
        tsan = self.job("core-tsan")
        message = (
            "why: scheduled TSan is trusted native Core workload since #693 "
            "and Hosted Ubuntu would bill 25-35 minutes a day for it; remedy: "
            f"route core-tsan with {CORE_ROLE} and keep the stress command"
        )
        self.assertIn(CORE_ROLE, tsan, message)
        self.assertNotIn("runs-on: ubuntu-24.04", tsan, message)
        for command in TSAN_COMMANDS:
            self.assertIn(command, tsan, message)

    def test_scheduled_tsan_verifies_the_host_prerequisite_first(self) -> None:
        """Probe actual runtime startup without root-only sysctl access."""
        tsan = self.job("core-tsan")
        self.assertIn("name: Verify the TSan host prerequisite", tsan)
        self.assertIn("clang++-22 -fsanitize=thread -shared-libsan", tsan)
        self.assertIn('"-Wl,-rpath,$runtime_dir"', tsan)
        self.assertIn("for attempt in {1..10}", tsan)
        self.assertNotIn("sysctl -n", tsan)
        self.assertIn("configure-sanitizer-aslr.sh", tsan)
        self.assertIn("why:", tsan)
        self.assertIn("remedy:", tsan)
        prerequisite = tsan.index("Verify the TSan host prerequisite")
        configure = tsan.index("scripts/core.sh configure tsan")
        self.assertLess(
            prerequisite,
            configure,
            msg=(
                "why: a prerequisite checked after the TSan build would let a "
                "runtime FATAL or a silent death report first; remedy: keep the "
                "runtime check before the configure step"
            ),
        )

    def test_no_hosted_tsan_lane_or_probe_remains(self) -> None:
        """The probe answered its question; a second TSan lane would only drift."""
        self.assertNotIn("core-tsan-self-hosted-probe", self.source)
        self.assertNotIn("probe_self_hosted_tsan", self.source)
        self.assertNotIn(
            "runs-on: ubuntu-24.04",
            self.job("core-tsan"),
            msg=(
                "why: a Hosted TSan lane beside the ci-core one would measure "
                "a different kernel and bill Hosted minutes for a question the "
                "role already answers; remedy: keep core-tsan on ci-core only"
            ),
        )

    def test_tsan_compiles_with_the_pinned_clang(self) -> None:
        """TSan is the reason the Core pin exists, so the lane must use it.

        GCC 13.3's libtsan gives a less useful failure than LLVM 22's when
        the host regresses, and the pin is what the coverage lane and the
        host inventory verify. The pin is set at configure time; build and
        test inherit the cached compiler.
        """
        body = self.job("core-tsan")
        self.assertIn(
            "env CC=clang-22 CXX=clang++-22 scripts/core.sh configure tsan",
            body,
            msg=(
                "why: core-tsan would otherwise configure TSan with the "
                "platform default GCC rather than the pinned toolchain; "
                "remedy: keep the CC/CXX pin on the configure step"
            ),
        )
        self.assertIn("command -v clang-22", body)
        self.assertIn("command -v clang++-22", body)
        self.assertNotIn(
            "apt-get",
            body,
            msg=(
                "why: the ci-core host is provisioned once by the operator and "
                "shared by several runner services, so a per-job install would "
                "mutate shared machine state; remedy: verify with command -v "
                "and install nothing"
            ),
        )

    def test_both_native_jobs_share_the_repository_capacity_queue(self) -> None:
        """Naming the `ci-core` role is not enough to make them run one at a time.

        The role spans two runner services on one physical host, so without the
        capacity queue a dispatched probe and the release stress suite start in
        the same second and run beside each other. Both are timing-sensitive,
        and twenty consecutive stress repetitions are the least tolerant
        workload in the repository.

        Observed: run 33838737018 started the TSan probe (then
        `core-tsan-self-hosted-probe`) and
        `core-stress` at 04:58:05Z on `contabo-lmdj-linux` and
        `contabo-lmdj-linux-02`, and both failed. The probe's failure said
        nothing about whether the host can execute the TSan runtime, which is
        the only question it exists to answer.
        """
        for job_name in ("core-tsan", "core-stress"):
            with self.subTest(job=job_name):
                self.assertRegex(
                    self.job(job_name),
                    r"(?m)^    concurrency:\n"
                    r"      group: lmdj-native-heavy\n"
                    r"      queue: max\n"
                    r"      cancel-in-progress: false$",
                    msg=(
                        f"why: {job_name} names the ci-core role, which spans two "
                        "runner services on one host, so a sibling native job "
                        "runs beside it rather than after it and consumes the "
                        "CPU its timing-sensitive tests were budgeted for; "
                        "remedy: keep the lmdj-native-heavy block with queue: "
                        "max before cancel-in-progress: false, the same one "
                        "ci.yml puts on every admitted shared-host lane"
                    ),
                )

    def test_nightly_keeps_read_only_repository_permission(self) -> None:
        prefix = self.source.split("jobs:", 1)[0]
        message = (
            "why: Nightly build and compatibility jobs require no repository "
            "mutation; remedy: retain top-level contents: read and remove any "
            "contents: write permission"
        )
        self.assertIn("permissions:\n  contents: read", prefix, message)
        self.assertNotIn("contents: write", self.source, message)

    def prerequisite(self, *, compile_code=0, startup_code=0, fail_at=1, directory_code=0, source_code=0):
        step = self.job("core-tsan").split("      - name: Verify the TSan host prerequisite\n", 1)[1]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1].split("      - name:", 1)[0])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "outputs"
            compiler = Path(directory) / "clang++-22"
            compiler.write_text("""#!/bin/bash
if [[ "$*" == '-print-runtime-dir' ]]; then
  printf '%s\n' "$TEST_DIRECTORY"
  exit "$TEST_DIRECTORY_CODE"
fi
[[ "$#" == 7 && "$1" == -fsanitize=thread && "$2" == -shared-libsan && "$3" == "-Wl,-rpath,$TEST_DIRECTORY" && "$4" == -pthread && "$6" == -o ]] || exit 97

if [[ "$TEST_COMPILE_CODE" != 0 ]]; then exit "$TEST_COMPILE_CODE"; fi
cat >"$7" <<'PROBE'
#!/bin/bash
count=0
if test -f "$TEST_DIRECTORY/count"; then read -r count <"$TEST_DIRECTORY/count"; fi
count=$((count+1))
echo "$count" >"$TEST_DIRECTORY/count"
if [[ "$count" == "$TEST_FAIL_AT" ]]; then exit "$TEST_STARTUP_CODE"; fi
PROBE
chmod +x "$7"
""")
            compiler.chmod(0o755)
            result = subprocess.run(["/bin/bash", "-e", "-c", 'cat() { if [[ "$TEST_SOURCE_CODE" != 0 ]]; then return "$TEST_SOURCE_CODE"; fi; command cat "$@"; }\n' + script + '\nprintf "BUILD_REACHED\\n"'],
                env={**os.environ, "PATH": directory + os.pathsep + os.environ["PATH"],
                     "GITHUB_OUTPUT": str(output), "TEST_DIRECTORY": directory,
                     "TEST_SOURCE_CODE": str(source_code), "TEST_DIRECTORY_CODE": str(directory_code), "TEST_COMPILE_CODE": str(compile_code),
                     "TEST_STARTUP_CODE": str(startup_code), "TEST_FAIL_AT": str(fail_at)},
                capture_output=True, text=True)
            flags = dict(line.split("=", 1) for line in output.read_text().splitlines()) if output.exists() else {}
            self.starts = int((Path(directory) / "count").read_text()) if (Path(directory) / "count").exists() else 0
        return result, flags

    def assert_infrastructure(self, result, flags):
        self.assertNotEqual(result.returncode, 0, "why: unknown TSan prerequisite became success; remedy: fail before build")
        self.assertEqual(flags, {"infrastructure_failure": "true"},
                         "why: TSan preflight failure lost its infrastructure flag; remedy: emit before exiting")
        self.assertNotIn("BUILD_REACHED", result.stdout)
        self.assertIn("why:", result.stderr)
        self.assertIn("remedy:", result.stderr)

    def test_probe_source_write_failure_records_infrastructure(self):
        self.assert_infrastructure(*self.prerequisite(source_code=1))
        self.assertEqual(self.starts, 0)

    def test_runtime_directory_failure_records_infrastructure(self):
        self.assert_infrastructure(*self.prerequisite(directory_code=1))
        self.assertEqual(self.starts, 0)

    def test_compiler_failure_records_infrastructure_before_execution(self):
        self.assert_infrastructure(*self.prerequisite(compile_code=1))
        self.assertEqual(self.starts, 0)

    def test_silent_runtime_failure_stops_without_retry(self):
        self.assert_infrastructure(*self.prerequisite(startup_code=139))
        self.assertEqual(self.starts, 1)

    def test_late_startup_failure_is_not_hidden_by_earlier_success(self):
        self.assert_infrastructure(*self.prerequisite(startup_code=66, fail_at=10))
        self.assertEqual(self.starts, 10)

    def test_runtime_timeout_records_infrastructure(self):
        self.assert_infrastructure(*self.prerequisite(startup_code=124))

    def test_ten_successful_starts_retain_build_and_test_path(self):
        result, flags = self.prerequisite()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(flags, {})
        self.assertEqual(self.starts, 10)
        self.assertIn("BUILD_REACHED", result.stdout)

    def test_real_preflight_flag_flows_through_reusable_output_to_scoped_debt(self):
        # Output links are the platform leg; execute their source here, then
        # consume the actual bytes via the production scoped verdict adapter.
        self.assertIn('infrastructure_failure: ${{ steps.prerequisite.outputs.infrastructure_failure }}', self.source)
        self.assertIn('value: ${{ jobs.core-tsan.outputs.infrastructure_failure }}', self.source)
        failed, flags = self.prerequisite(startup_code=66)
        self.assert_infrastructure(failed, flags)
        sys.path.insert(0, str(REPO_ROOT / "scripts/ci"))
        import batch_verdict
        import self_test
        import test_scope
        policy = test_scope.load_policy(REPO_ROOT)
        sha = "a" * 40
        identity = dict(request_id="tsan-prerequisite", request_kind="auto", base_sha="b" * 40,
            target_sha=sha, control_sha=sha, policy_digest=policy.digest, run_id=51, run_attempt=1)
        selection = test_scope.select(policy, [], ["test:core_tsan_stress"])
        legacy_identity = self_test.Identity(batch_verdict.SCHEMA, "auto", sha, sha, 51, 1, policy.inventory.revision)
        rows, _ = self_test.observations_from_needs(legacy_identity, policy.inventory,
            {"nightly-tsan": {"result": "failure", "outputs": flags}}, aliases={"core-tsan": "nightly-tsan"})
        from dataclasses import asdict
        selected_rows = [asdict(row) for row in rows if row.suite in selection["suites"]]
        verdict = batch_verdict.build(policy, identity, selection, selected_rows)
        suite = next(s for s in verdict["suites"] if s["id"] == "core_tsan_stress")
        self.assertEqual(suite["status"], "infrastructure_failure")
        self.assertTrue(suite["verification_debt"])
        self.assertEqual(suite["failures"], [])
        self.assertEqual(batch_verdict.scheduler_outcomes(verdict, policy, identity, selection),
                         {"core_tsan_stress": "infrastructure"})
        self.assertEqual(verdict["status"], "failed")


if __name__ == "__main__":
    unittest.main()
