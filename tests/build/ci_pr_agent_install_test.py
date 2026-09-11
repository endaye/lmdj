#!/usr/bin/env python3
"""Real Linux filesystem/ACL transitions with a no-network witness fixture.

Run as root on the deployment platform. This proves installer transitions, not
PRReviewer import, provider health or systemd resource isolation.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = Path(os.environ.get("PR_AGENT_INSTALLER_TEST_SCRIPT", ROOT / "scripts/ci/pr-agent/install.sh"))
WORKFLOW = Path(os.environ.get("PR_AGENT_WORKFLOW_TEST_FILE", ROOT / ".github/workflows/pr-review.yml"))
WITNESS = '''import json, pathlib, sys
if (pathlib.Path(__file__).parent / "runtime.toml").read_text() == "invalid":
    sys.exit(2)
print(json.dumps({"schema":"lmdj.pr-agent-config-witness.v1",
"provider_order":["deepseek"],"providers":{"deepseek":{"enabled":False}},
"engine":{"name":"fixture","version":"0.0.0","source_commit":"000000000000"}}))
'''


@unittest.skipUnless(sys.platform == "linux" and os.getuid() == 0,
                     "installer filesystem/ACL tests require an explicit root Linux run")
class InstallTransitions(unittest.TestCase):
    def setUp(self):
        for executable in ("sudo", "flock", "setfacl", "/usr/bin/python3.12"):
            self.assertIsNotNone(shutil.which(executable), f"why: {executable} missing; remedy: prepare the deployment platform")
        self.tmp = tempfile.TemporaryDirectory(prefix="lmdj-install-test.")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.chmod(0o755)
        self.install = self.root / "installation"
        self.source = self.install / "releases" / "seed"
        self.source.mkdir(parents=True)
        self.staging = self.root / "staging"
        self.staging.mkdir()
        for directory in ("pr_agent", "vendor", "tokenizer-cache"):
            (self.source / directory).mkdir()
        for name, data in {
            "pr_agent_review.py": WITNESS, "config.toml": "seed config",
            "requirements.lock": "fixture", "LICENSE": "fixture",
            "tokenizer-cache/fb374d419588a4632f3f557e76b4b70aebbca790": "fixture",
            "runtime.toml": "old runtime",
            "IDENTITY": "adapter_sha256=old\ndefault_config_sha256=old\n",
            "DEPLOYMENT_IDENTITY.json": '{"archive":{"sha256":"seed"},"files":{}}',
        }.items():
            (self.source / name).write_text(data)
        (self.install / "current").symlink_to(self.source)
        (self.install / "slot.lock").touch()
        (self.install / "engine-state").mkdir()
        self.ledger = self.install / "engine-state" / "ledger.jsonl"
        self.ledger.write_bytes(b"retained historical ledger\n")
        for name, data in {"pr_agent_review.py": WITNESS, "runtime.toml": "new runtime", "run-engine.sh": "fixture"}.items():
            (self.staging / name).write_text(data)
        self.original = self.snapshot(self.source)

    @staticmethod
    def snapshot(root):
        return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def run_install(self):
        return subprocess.run(["bash", str(INSTALLER), str(self.staging)], text=True, capture_output=True,
                              env={**os.environ, "PR_AGENT_INSTALL_ROOT": str(self.install),
                                   "PR_AGENT_RUNNER_ACCOUNTS": "nobody"}, timeout=30)

    def test_success_keeps_seed_and_ledger_and_binds_new_member_bytes(self):
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        candidate = (self.install / "current").resolve()
        self.assertNotEqual(candidate, self.source)
        self.assertEqual((self.install / "previous").resolve(), self.source)
        self.assertEqual(self.snapshot(self.source), self.original)
        self.assertEqual(self.ledger.read_bytes(), b"retained historical ledger\n")
        document = json.loads((candidate / "DEPLOYMENT_IDENTITY.json").read_text())
        self.assertEqual(document["archive"], {"sha256": "seed"})
        for member in document["files"].values():
            data = (candidate / member["path"]).read_bytes()
            self.assertEqual(member["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(member["byte_length"], len(data))
        self.assertEqual((candidate / "runtime.toml").read_text(), "new runtime")
        for entry in candidate.rglob("*"):
            self.assertEqual(entry.stat().st_uid, 0)
            self.assertFalse(entry.stat().st_mode & 0o022)
        # The actual non-owner account can read the new tree and shared ledger.
        access = subprocess.run(["sudo", "-u", "nobody", "test", "-w", str(self.ledger)])
        self.assertEqual(access.returncode, 0)

    def test_failed_witness_does_not_switch_current_or_rewrite_seed(self):
        (self.staging / "runtime.toml").write_text("invalid")
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.install / "current").resolve(), self.source)
        self.assertFalse((self.install / "previous").exists())
        self.assertEqual(self.snapshot(self.source), self.original)
        self.assertEqual(self.ledger.read_bytes(), b"retained historical ledger\n")

    def test_busy_slot_refuses_before_creating_a_candidate(self):
        with (self.install / "slot.lock").open() as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("owns the slot", result.stderr)
        self.assertEqual(list((self.install / "releases").iterdir()), [self.source])
        self.assertEqual(self.snapshot(self.source), self.original)

    def test_current_outside_releases_is_refused_before_copy(self):
        (self.install / "current").unlink()
        (self.install / "current").symlink_to(self.root)
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside the releases directory", result.stderr)
        self.assertEqual(list((self.install / "releases").iterdir()), [self.source])

    def run_workflow_engine_step(self, *, failed_witness=False):
        # Execute the real workflow shell with only its fixed lock path relocated
        # into this fixture. The wrapper observes locking, never calls a model.
        source = WORKFLOW.read_text()
        step = source.split("      - name: deepseek review\n", 1)[1].split("      - name: Validate PR-Agent result", 1)[0]
        body = step.split("        run: |\n", 1)[1]
        script = "\n".join(line[10:] for line in body.splitlines())
        script = script.replace("/var/lib/lmdj/pr-agent/slot.lock", str(self.install / "slot.lock"))
        wrapper = self.root / "scripts/ci/pr-agent/run-engine.sh"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text('''set -eu
if flock -n "$TEST_SLOT" true; then
  echo "wrapper ran outside slot lock" >&2
  exit 80
fi
printf '%s\\n' "$1" >> "$REVIEW_DIR/trace"
if [ "$1" = --witness ] && [ "$FAIL_WITNESS" = 1 ]; then exit 2; fi
printf '{"release":"fixture-A"}\\n'
''')
        return subprocess.run(["bash", "-euo", "pipefail", "-c", script], cwd=self.root,
                              env={**os.environ, "REVIEW_DIR": str(self.staging),
                                   "TEST_SLOT": str(self.install / "slot.lock"),
                                   "FAIL_WITNESS": "1" if failed_witness else "0"},
                              text=True, capture_output=True, timeout=10)

    def test_workflow_witness_and_input_both_hold_the_installation_lock(self):
        result = self.run_workflow_engine_step()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.staging / "trace").read_text().splitlines(), ["--witness", "--input"])
        self.assertEqual(json.loads((self.staging / "t2-config-witness.json").read_text()),
                         {"release": "fixture-A"})
        self.assertEqual(json.loads((self.staging / "t2-result.json").read_text()),
                         {"release": "fixture-A"})

    def test_workflow_failed_witness_never_invokes_the_model_entrypoint(self):
        result = self.run_workflow_engine_step(failed_witness=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual((self.staging / "trace").read_text().splitlines(), ["--witness"])
        self.assertFalse((self.staging / "t2-result.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
