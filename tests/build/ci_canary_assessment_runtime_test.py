"""Real local processes, not proof of provider or deployment isolation."""
from functools import lru_cache
import json
import os
from pathlib import Path
import signal
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.canary import assessment_runtime as runtime, records as r
import ci_canary_assessment_test as fixture


@lru_cache(maxsize=16)
def standalone_python(candidates):
    """The parent setup-python binary may require stripped loader variables."""
    for index, candidate in enumerate(candidates):
        try:
            result = subprocess.run([candidate, "-I", "-c",
                "import argparse,json,pathlib,subprocess; print('lmdj-fixture-python-ready')"],
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                capture_output=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout == b"lmdj-fixture-python-ready\n":
            if index:
                print(f"Process fixture uses independently verified interpreter: {candidate}", file=sys.stderr)
            return candidate
    raise RuntimeError("why: no fixture Python starts with the sanitized environment; "
                       "remedy: provide a standalone system Python; do not forward loader variables or skip process tests")


@unittest.skipUnless(os.name == "posix", "assessment process adapter requires POSIX")
class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.child_python = standalone_python(tuple(dict.fromkeys(
            (sys.executable, "/usr/bin/python3", "/usr/local/bin/python3"))))
        self.fixture = fixture.AssessmentTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.context = self.fixture.context
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {backend: {"executable": str(self.root / backend), "model": "fixture-model"}
                       for backend in runtime.a.BACKENDS}
        self.credentials = {"ZAI_CODING_KEY": "zai-secret", "KIMI_CODING_KEY": "kimi-secret",
                            "GROK_AUTH_JSON": '{"token":"grok-secret"}'}

    def executable(self, backend, body):
        path = Path(self.config[backend]["executable"])
        # Reject unknown flags/arity rather than certifying any invocation. The
        # shapes are taken from the inspected CLI help; real authentication,
        # tools and managed-config side effects remain explicit live gaps.
        flags = (["--cwd", "--prompt-file", "--output-format", "--model", "--max-turns", "--tools",
                  "--permission-mode", "--system-prompt-override"] if backend == "grok" else
                 ["--tools", "--disallowedTools", "--mcp-config", "--setting-sources", "--settings",
                  "--max-turns", "--output-format", "--model", "--system-prompt"])
        switches = (["--verbatim", "--no-subagents", "--disable-web-search"] if backend == "grok" else
                    ["--bare", "--restricted", "--print", "--strict-mcp-config", "--no-session-persistence"])
        preflight = ("import argparse,os\np=argparse.ArgumentParser(allow_abbrev=False)\n"
                     + "for flag in " + repr(flags) + ": p.add_argument(flag,required=True)\n"
                     + "for flag in " + repr(switches) + ": p.add_argument(flag,required=True,action='store_true')\n")
        if backend == "grok":
            preflight += "p.add_argument('--deny',action='append',required=True)\n"
        else:
            preflight += "assert os.environ.get('ANTHROPIC_API_KEY'), 'bare requires an explicit API key'\n"
        preflight += "args=p.parse_args()\nassert args.output_format=='json'\n"
        path.write_text("#!" + self.child_python + "\n" + preflight + body)
        path.chmod(0o700)

    def answer(self, backend="glm", advice=None):
        advice = self.fixture.advice() if advice is None else advice
        envelope = {"type": "result", "text" if backend == "grok" else "result": json.dumps(advice)}
        self.executable(backend, "import json\nprint(" + repr(json.dumps(envelope)) + ")\n")

    def execute(self):
        return runtime.execute(self.context, config=self.config, credentials=self.credentials)

    def test_real_process_advice_stops_fallback(self):
        self.answer()
        result = self.execute()
        self.assertEqual(result["selected_backend"], "glm")
        self.assertEqual(len(result["attempts"]), 1)
        self.assertFalse(result["admission_evidence"])

    def test_nonzero_and_invalid_output_reach_grok(self):
        self.executable("glm", "raise SystemExit(2)\n")
        self.executable("kimi", "print('not JSON')\n")
        self.answer("grok")
        result = self.execute()
        self.assertEqual(result["selected_backend"], "grok")
        self.assertEqual([item["error_class"] for item in result["attempts"]],
                         ["runtime_failure", "invalid_output", None])

    def test_missing_credentials_never_launch_and_do_not_leak(self):
        self.answer()
        self.credentials = {}
        result = self.execute()
        self.assertEqual(result["state"], "blocked")
        self.assertEqual([item["error_class"] for item in result["attempts"]], ["missing_credential"] * 3)
        self.assertEqual(result["report_intent"]["reason"], "backends_unavailable")
        self.assertNotIn("secret", json.dumps(result))

    def test_major_stops_without_trying_more_convenient_backend(self):
        advice = self.fixture.advice()
        advice["components"][0]["impact"] = "major"
        self.answer(advice=advice)
        result = self.execute()
        self.assertEqual(result["report_intent"]["reason"], "compatibility_review")
        self.assertEqual(len(result["attempts"]), 1)

    def test_child_gets_complete_stdin_and_only_selected_credentials(self):
        observed = self.root / "observed.json"
        envelope = {"type": "result", "result": json.dumps(self.fixture.advice())}
        self.executable("glm", "import os,json,sys\nfrom pathlib import Path\n"
                        + "Path(" + repr(str(observed)) + ").write_text(json.dumps({"
                        + "'env':dict(os.environ),'cwd':os.getcwd(),'input':sys.stdin.read(),'args':sys.argv}))\n"
                        + "print(" + repr(json.dumps(envelope)) + ")\n")
        with patch.dict(os.environ, {"GH_TOKEN": "github-secret", "CF_API_TOKEN": "deploy-secret",
                                     "ANTHROPIC_API_KEY": "ambient-secret", "LD_PRELOAD": "bad"}):
            self.execute()
        actual = json.loads(observed.read_text())
        env = actual["env"]
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "zai-secret")
        self.assertEqual(env["ANTHROPIC_API_KEY"], "zai-secret")
        self.assertNotIn("ambient-secret", json.dumps(actual))
        for key in ("GH_TOKEN", "CF_API_TOKEN", "LD_PRELOAD", "KIMI_CODING_KEY",
                    "GROK_AUTH_JSON", "HOME", "CODEX_HOME"):
            self.assertNotIn(key, env)
        self.assertEqual(json.loads(actual["input"])["context"], self.context)
        self.assertIn("--restricted", actual["args"])
        self.assertIn("--bare", actual["args"])
        self.assertFalse(Path(actual["cwd"]).exists())
        self.assertFalse(Path(env["CLAUDE_CONFIG_DIR"]).exists())

    def test_grok_auth_is_private_temporary_and_not_in_environment(self):
        observed = self.root / "observed.json"
        self.credentials.pop("ZAI_CODING_KEY")
        self.credentials.pop("KIMI_CODING_KEY")
        envelope = {"type": "result", "text": json.dumps(self.fixture.advice())}
        self.executable("grok", "import os,json,sys,stat\nfrom pathlib import Path\n"
                        + "auth=Path(os.environ['GROK_HOME'])/'auth.json'\n"
                        + "Path(" + repr(str(observed)) + ").write_text(json.dumps({"
                        + "'path':str(auth),'mode':stat.S_IMODE(auth.stat().st_mode),'env':dict(os.environ),"
                        + "'input':Path(sys.argv[sys.argv.index('--prompt-file')+1]).read_text(),'args':sys.argv}))\n"
                        + "print(" + repr(json.dumps(envelope)) + ")\n")
        self.assertEqual(self.execute()["selected_backend"], "grok")
        actual = json.loads(observed.read_text())
        self.assertEqual(actual["mode"], 0o600)
        self.assertNotIn("GROK_AUTH_JSON", actual["env"])
        self.assertNotIn("XAI_API_KEY", actual["env"])
        self.assertFalse(Path(actual["path"]).exists())
        self.assertEqual(json.loads(actual["input"])["context"], self.context)
        self.assertIn("Read", actual["args"])
        self.assertIn("MCPTool", actual["args"])
        self.assertNotIn("--always-approve", actual["args"])

    def test_kimi_bare_uses_its_explicit_api_key_not_a_zai_or_ambient_token(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, env = runtime._invocation("kimi", self.config["kimi"], "kimi-secret", Path(directory))
        self.assertEqual(env["ANTHROPIC_API_KEY"], "kimi-secret")
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://api.kimi.com/coding/")
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", env)

    def test_missing_binary_is_finite_failure(self):
        result = self.execute()
        self.assertEqual([item["error_class"] for item in result["attempts"]], ["runtime_failure"] * 3)

    def test_invalid_context_launches_nothing(self):
        self.context["digest"] = "a" * 64
        with self.assertRaises(r.CanaryError):
            self.execute()

    def test_untrusted_command_shape_rejected_before_launch(self):
        for key, value in (("executable", "claude"), ("model", "x; touch /tmp/bad")):
            with self.subTest(key=key):
                config = {backend: dict(item) for backend, item in self.config.items()}
                config["glm"][key] = value
                with self.assertRaises(r.CanaryError):
                    runtime.execute(self.context, config=config, credentials=self.credentials)

    def process(self, body, **kwargs):
        return runtime.run_process([self.child_python, "-c", body], cwd=self.root,
                                   env={"PATH": "/usr/bin:/bin"}, prompt=b"input", **kwargs)

    def test_real_timeout_is_bounded(self):
        start = time.monotonic()
        result = self.process("import time; time.sleep(30)", timeout=0.15)
        self.assertEqual(result["error_class"], "timeout")
        self.assertEqual(result["returncode"], -signal.SIGKILL)
        self.assertLess(time.monotonic() - start, 3)
        self.assertEqual(result["output"], b"")

    def test_combined_output_limit_includes_stderr(self):
        for descriptor in (1, 2):
            with self.subTest(descriptor=descriptor):
                result = self.process(f"import os; os.write({descriptor}, b'x'*1000000)", output_limit=100)
                self.assertEqual(result["error_class"], "invalid_output")
                self.assertEqual(result["output"], b"")

    @unittest.skipUnless(sys.platform == "linux", "descendant liveness assertion uses Linux /proc")
    def test_successful_parent_cannot_leave_sleeping_descendant(self):
        pidfile = self.root / "pid"
        result = self.process("import subprocess,sys\nfrom pathlib import Path\n"
                              "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],"
                              "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
                              + "Path(" + repr(str(pidfile)) + ").write_text(str(p.pid))\nprint('ok')", timeout=1)
        self.assertIsNone(result["error_class"])
        pid = int(pidfile.read_text())
        for _ in range(100):
            if self.departed(pid):
                break
            time.sleep(0.01)
        else:
            self.fail("why: assessment descendant survived; remedy: kill the attempt process group")

    @staticmethod
    def departed(pid):
        """Whether the descendant is gone or a zombie, without racing its exit.

        Checking `/proc/<pid>/stat` for existence and then reading it are two
        operations, and the exit this waits for lands between them: Linux
        answers the read with `ProcessLookupError`, which is this test's
        success condition arriving by another route rather than a failure.
        """
        try:
            return Path(f"/proc/{pid}/stat").read_text().split()[2] == "Z"
        except (ProcessLookupError, FileNotFoundError):
            return True

    def test_a_descendant_that_exits_mid_read_counts_as_departed(self):
        # Not Linux-only: the race this fixes is in the reader, and the reader
        # is what the poll loop above depends on. On a runner the exit lands
        # between `exists()` and `read_text()`, and Linux answers the read with
        # `ProcessLookupError` — the awaited outcome arriving by another route.
        for error in (ProcessLookupError(3, "No such process"),
                      FileNotFoundError(2, "No such file or directory")):
            with self.subTest(error=type(error).__name__):
                with patch.object(Path, "read_text", side_effect=error):
                    self.assertTrue(
                        self.departed(1),
                        "why: a descendant that vanished while being read was "
                        "reported as still running, so the poll loop errors "
                        "instead of succeeding; "
                        "remedy: treat a vanished process as departed")

    def test_a_running_descendant_is_not_departed(self):
        # The other direction: a live process must not be mistaken for gone,
        # or the loop would pass without the descendant ever being killed.
        with patch.object(Path, "read_text", return_value="1 (sleep) S 0 1 1"):
            self.assertFalse(self.departed(1))
        with patch.object(Path, "read_text", return_value="1 (sleep) Z 0 1 1"):
            self.assertTrue(self.departed(1))

    def test_error_envelope_is_not_valid_advice(self):
        self.executable("glm", "print(" + repr(json.dumps({"type": "result", "is_error": True,
                         "result": json.dumps(self.fixture.advice())})) + ")\n")
        result = self.execute()
        self.assertEqual(result["attempts"][0]["error_class"], "invalid_output")

    def test_grok_text_envelope_matches_existing_adapter_contract(self):
        self.credentials.pop("ZAI_CODING_KEY")
        self.credentials.pop("KIMI_CODING_KEY")
        self.executable("grok", "print(" + repr(json.dumps({"text": json.dumps(self.fixture.advice())})) + ")\n")
        self.assertEqual(self.execute()["selected_backend"], "grok")

    def test_grok_error_with_apparently_valid_text_is_rejected(self):
        output = json.dumps({"type": "error", "text": json.dumps(self.fixture.advice())}).encode()
        with self.assertRaises(r.CanaryError):
            runtime._advice_output("grok", output)

    def test_unknown_stops_chain(self):
        advice = self.fixture.advice()
        advice["components"][0]["unknowns"] = ["Cannot establish shared dependency compatibility"]
        self.answer(advice=advice)
        result = self.execute()
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(len(result["attempts"]), 1)

    def test_closed_pipes_do_not_bypass_process_deadline(self):
        result = self.process("import os,time; os.close(1); os.close(2); time.sleep(30)", timeout=0.15)
        self.assertEqual(result["error_class"], "timeout")

    def test_inherited_pipe_descendant_cannot_hold_attempt_open(self):
        result = self.process("import subprocess,sys; "
                              "subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])",
                              timeout=0.15)
        self.assertEqual(result["error_class"], "timeout")

    def test_interruption_reaps_process_before_propagating(self):
        started = []
        original = runtime.subprocess.Popen

        def launch(*args, **kwargs):
            process = original(*args, **kwargs)
            started.append(process)
            return process

        with patch.object(runtime.subprocess, "Popen", side_effect=launch), \
                patch.object(runtime.selectors.DefaultSelector, "select", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.process("import time;time.sleep(30)")
        self.assertIsNotNone(started[0].poll())

    def test_failed_process_never_returns_raw_secret_output(self):
        result = self.process("import sys;print('provider-secret');print('private-key',file=sys.stderr);sys.exit(1)")
        self.assertEqual(result["error_class"], "runtime_failure")
        self.assertNotIn("secret", str(result))
        self.assertNotIn("private-key", str(result))

    def test_tampered_model_input_binding_is_rejected(self):
        advice = self.fixture.advice()
        advice["input_digest"] = "f" * 64
        self.answer(advice=advice)
        self.assertEqual(self.execute()["attempts"][0]["error_class"], "invalid_output")

    def test_process_budgets_cannot_be_increased(self):
        for kwargs in ({"timeout": 301}, {"output_limit": runtime.MAX_PROCESS_BYTES + 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(r.CanaryError):
                self.process("print('ok')", **kwargs)

    def test_fixture_refuses_an_option_the_real_cli_does_not_declare(self):
        self.answer()
        original = runtime._invocation

        def invalid(*args):
            command, cwd, env = original(*args)
            return command + ["--invented-unsafe-option"], cwd, env

        with patch.object(runtime, "_invocation", side_effect=invalid):
            self.assertEqual(self.execute()["attempts"][0]["error_class"], "runtime_failure")

    def test_interpreter_selection_refuses_parent_environment_dependency(self):
        wrapper = self.root / "dependent-python"
        wrapper.write_text('#!/bin/sh\n[ "$LMDJ_FIXTURE_DEPENDENCY" = available ] || exit 127\n'
                           + 'exec ' + shlex.quote(self.child_python) + ' "$@"\n')
        wrapper.chmod(0o700)
        available = subprocess.run([str(wrapper), "-c", "print('with-dependency')"],
            env={"PATH": "/usr/bin:/bin", "LMDJ_FIXTURE_DEPENDENCY": "available"},
            capture_output=True, timeout=5, check=True)
        self.assertEqual(available.stdout, b"with-dependency\n")
        with patch.dict(os.environ, {"LMDJ_FIXTURE_DEPENDENCY": "available"}):
            self.assertEqual(standalone_python((str(wrapper), self.child_python)), self.child_python)
        self.assertEqual(standalone_python((self.child_python, str(self.root / "missing-python"))),
                         self.child_python)

    def test_missing_standalone_interpreter_is_a_failure_not_a_skip(self):
        with self.assertRaisesRegex(RuntimeError, "why:.*remedy:"):
            standalone_python((str(self.root / "missing-python"),))

    def test_interpreter_probe_requires_exact_stdlib_identity_response(self):
        fake = self.root / "not-python"
        fake.write_text('#!/bin/sh\nprintf "lmdj-fixture-python-ready extra-output\\n"\n')
        fake.chmod(0o700)
        with self.assertRaisesRegex(RuntimeError, "why:.*remedy:"):
            standalone_python((str(fake),))


if __name__ == "__main__":
    unittest.main()
