#!/usr/bin/env python3
"""The fixture interpreter helper hands sanitized children a Python that starts."""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_fixture_interpreter as interpreter

SANITIZED = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LC_ALL": "C"}


class FixtureInterpreterTest(unittest.TestCase):
    def test_fixture_path_resolves_python3_to_the_verified_interpreter_without_loader_variables(self):
        path = interpreter.fixture_path()
        env = {**SANITIZED, "PATH": path}
        which = subprocess.run(["sh", "-c", "command -v python3"], env=env, capture_output=True, text=True, check=True)
        self.assertEqual(Path(which.stdout.strip()).parent, Path(path.split(os.pathsep)[0]))
        result = subprocess.run(["python3", "-c", "import sys; print(sys.executable)"], env=env,
                                capture_output=True, text=True, check=True, timeout=10)
        self.assertEqual(os.path.realpath(result.stdout.strip()), os.path.realpath(interpreter.fixture_python()))

    def test_probe_rejects_an_interpreter_older_than_3_11(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "old-python"
            fake.write_text("#!/bin/sh\n" + "exec " + shlex.quote(interpreter.fixture_python())
                            + " -c 'import sys; sys.version_info = (3, 9, 0); exec(sys.argv[1])' \"$3\"\n")
            fake.chmod(0o700)
            with self.assertRaisesRegex(RuntimeError, "why:.*remedy:"):
                interpreter.standalone_python((str(fake),))

    def test_reexec_is_a_no_op_when_the_parent_already_starts_sanitized(self):
        with patch.object(interpreter, "fixture_python", return_value=sys.executable), \
                patch.object(interpreter.os, "execv") as execv:
            interpreter.reexec_when_parent_cannot_start_sanitized()
        execv.assert_not_called()

    def test_fixture_path_survives_an_unset_PATH(self):
        interpreter.fixture_path.cache_clear()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PATH", None)
            path = interpreter.fixture_path()
        interpreter.fixture_path.cache_clear()
        self.assertTrue(path.split(os.pathsep)[0].startswith(tempfile.gettempdir().rstrip("/").split("/")[0] + "/"))
        self.assertIn(os.defpath.strip(os.pathsep), path)

    def test_reexec_hands_argv_to_the_verified_interpreter_once(self):
        with patch.object(interpreter, "fixture_python", return_value="/verified/python3"), \
                patch.object(interpreter.os, "execv") as execv, \
                patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LMDJ_FIXTURE_REEXEC", None)
            interpreter.reexec_when_parent_cannot_start_sanitized()
            execv.assert_called_once_with("/verified/python3", ["/verified/python3", *sys.argv])
            with self.assertRaisesRegex(RuntimeError, "still differs"):
                interpreter.reexec_when_parent_cannot_start_sanitized()


if __name__ == "__main__":
    unittest.main()
