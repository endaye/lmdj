#!/usr/bin/env python3
"""Linux job interpreters must survive the release executor's environment."""
from pathlib import Path
import json
import os
import re
import shlex
import subprocess
import tempfile
import textwrap
import unittest

from release_fixture_interpreter import fixture_python

ROOT = Path(__file__).resolve().parents[2]
SELECT = "name: Select standalone system Python"


def selector_script(source):
    match = re.search(
        r"name: Select standalone system Python\n        shell: bash\n        run: \|\n"
        r"((?:          [^\n]*\n|\n)+)", source,
    )
    if match is None:
        raise AssertionError("why: system Python prerequisite is missing; remedy: restore the workflow-owned shell step")
    return textwrap.dedent(match[1]).rstrip() + "\n"


class SystemPythonTest(unittest.TestCase):
    def run_selector(self, interpreter, env):
        source = (ROOT / ".github/workflows/ci.yml").read_text()
        script = selector_script(source)
        # Replace only the host-specific executable, leaving the actual startup
        # probe and PATH publication intact. No candidate checkout is present.
        self.assertEqual(script.count('python_executable="/usr/bin/python3"'), 1)
        script = script.replace('python_executable="/usr/bin/python3"',
                                "python_executable=" + shlex.quote(interpreter))
        return subprocess.run(["bash", "-s"], input=script, env=env,
                              cwd=env["RUNNER_TEMP"], capture_output=True, text=True)

    def test_selected_names_and_sys_executable_start_without_parent_environment(self):
        with tempfile.TemporaryDirectory(prefix="system python ") as directory:
            root = Path(directory)
            github_path = root / "github-path"
            env = {**os.environ, "RUNNER_TEMP": directory,
                   "GITHUB_PATH": str(github_path),
                   "PYTHONHOME": str(root / "invalid-python-home"),
                   "LD_LIBRARY_PATH": str(root / "irrelevant-loader-path")}
            result = self.run_selector(fixture_python(), env)
            self.assertEqual(result.returncode, 0, result.stderr)
            observation = json.loads(result.stdout)
            self.assertEqual(observation["python"], os.path.realpath(fixture_python()))
            self.assertEqual(observation["version"], observation["sanitized_child"])
            selected = github_path.read_text().strip()
            for name in ("python", "python3"):
                with self.subTest(name=name):
                    child = subprocess.run(
                        [name, "-c", "import os,sys; print(os.path.realpath(sys.executable))"],
                        env={"PATH": selected + os.pathsep + os.defpath},
                        capture_output=True, text=True, check=True,
                    )
                    self.assertEqual(child.stdout.strip(), observation["python"])

    def test_loader_dependent_interpreter_is_refused_before_path_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dependent = root / "dependent-python"
            dependent.write_text(
                '#!/bin/sh\n'
                'if [ -z "${LD_LIBRARY_PATH:-}" ]; then\n'
                '  echo "libpython fixture: loader variable missing" >&2; exit 127\n'
                'fi\n'
                'echo "fixture parent starts with its loader environment"\n'
            )
            dependent.chmod(0o755)
            github_path = root / "github-path"
            env = {**os.environ, "RUNNER_TEMP": directory,
                   "GITHUB_PATH": str(github_path), "LD_LIBRARY_PATH": directory}
            control = subprocess.run([str(dependent)], env=env, capture_output=True)
            self.assertEqual(control.returncode, 0)
            result = self.run_selector(str(dependent), env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("libpython fixture: loader variable missing", result.stderr)
            self.assertIn("why: system Python cannot run", result.stderr)
            self.assertIn("remedy: repair the host Python installation", result.stderr)
            self.assertFalse(github_path.exists())
            self.assertEqual(list(root.glob("lmdj-system-python.*")), [])

    def test_all_workflows_use_the_same_verified_shell_probe(self):
        expected = selector_script((ROOT / ".github/workflows/ci.yml").read_text())
        for name in ("core-nightly.yml", "ci-self-hosted-core-benchmark.yml", "release-audit.yml"):
            with self.subTest(workflow=name):
                actual = selector_script((ROOT / ".github/workflows" / name).read_text())
                self.assertEqual(actual, expected,
                                 "why: system Python prerequisites differ; remedy: retain the same sanitized startup probe in every workflow")

    def test_core_and_release_consumers_select_system_python_before_execution(self):
        consumers = {
            ".github/workflows/ci.yml": {
                "deploy-contract": "scripts/release.sh hydrate",
                "package": "scripts/core.sh package",
                "core-ubuntu": "python3 tests/fixtures/audio/make_fixtures.py",
                "core-asan": "python3 tests/fixtures/audio/make_fixtures.py",
                "core-coverage": "python3 tests/fixtures/audio/make_fixtures.py",
            },
            ".github/workflows/core-nightly.yml": {
                "core-tsan": "python3 tests/fixtures/audio/make_fixtures.py",
            },
            ".github/workflows/ci-self-hosted-core-benchmark.yml": {
                "benchmark": "scripts/core.sh",
            },
            ".github/workflows/release-audit.yml": {
                "audit": "scripts/release.sh hydrate",
            },
        }
        for workflow, jobs in consumers.items():
            source = (ROOT / workflow).read_text()
            for job, consumer in jobs.items():
                with self.subTest(workflow=workflow, job=job):
                    match = re.search(rf"^  {job}:\n.*?(?=^  [a-z0-9-]+:|\Z)",
                                      source, re.M | re.S)
                    self.assertIsNotNone(match, f"missing job {job}")
                    directives = "\n".join(line for line in match[0].splitlines()
                                           if not line.lstrip().startswith("#"))
                    if "- *standalone-python" in directives:
                        self.assertIn("- &standalone-python\n        " + SELECT, source)
                        directives = directives.replace("- *standalone-python", SELECT)
                    message = ("why: Linux Core/release checks require a loader-independent interpreter; "
                               "remedy: select system Python before running the job's Python consumers")
                    self.assertIn(SELECT, directives, message)
                    self.assertNotIn("actions/setup-python@", directives, message)
                    self.assertLess(directives.index(SELECT), directives.index(consumer), message)


if __name__ == "__main__":
    unittest.main()
