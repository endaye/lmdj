#!/usr/bin/env python3
"""Contract tests for the repository-owned, inactive Netcup deployment boundary."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/pr-agent/deploy-runner.sh"
BASE_CONFIG = json.loads((ROOT / "scripts/ci/pr-agent/netcup-review.json").read_text())


def digest(data: bytes) -> dict:
    return {"sha256": hashlib.sha256(data).hexdigest(), "byte_length": len(data)}


def make_bundle(directory: Path, marker: str) -> tuple[Path, Path, dict]:
    files = {
        "IDENTITY": f"schema=lmdj.pr-agent-bundle.v1\nmarker={marker}\n".encode(),
        "pr_agent_review.py": f"# fixture {marker}\n".encode(),
        "config.toml": b"fallback_models=[]\n",
        "requirements.lock": b"fixture==1\n",
        "tokenizer-cache/fb374d419588a4632f3f557e76b4b70aebbca790": b"tokenizer",
        "vendor/litellm/__init__.py": b"# pinned vendor fixture\n",
    }
    archive = directory / f"bundle-{marker}.tar"
    with tarfile.open(archive, "w") as output:
        root = tarfile.TarInfo("pr-agent")
        root.type = tarfile.DIRTYPE
        root.mtime = 0
        output.addfile(root)
        for name, data in files.items():
            info = tarfile.TarInfo(f"pr-agent/{name}")
            info.size = len(data)
            info.mtime = 0
            output.addfile(info, __import__("io").BytesIO(data))
    member_identities = {
        key: {"path": key, **digest(value)}
        for key, value in (
            ("manifest", files["IDENTITY"]),
            ("adapter", files["pr_agent_review.py"]),
            ("default_config", files["config.toml"]),
            ("requirements_lock", files["requirements.lock"]),
            ("stock_tokenizer_asset", files["tokenizer-cache/fb374d419588a4632f3f557e76b4b70aebbca790"]),
        )
    }
    member_identities["manifest"]["path"] = "IDENTITY"
    member_identities["adapter"]["path"] = "pr_agent_review.py"
    member_identities["default_config"]["path"] = "config.toml"
    member_identities["requirements_lock"]["path"] = "requirements.lock"
    member_identities["stock_tokenizer_asset"]["path"] = "tokenizer-cache/fb374d419588a4632f3f557e76b4b70aebbca790"
    identity_document = {
        "schema": "lmdj.pr-agent-deployment.v1",
        "archive": {"sha256": digest(archive.read_bytes())["sha256"], "byte_length": archive.stat().st_size},
        "files": member_identities,
    }
    identity = directory / f"identity-{marker}.json"
    identity.write_text(json.dumps(identity_document, sort_keys=True, separators=(",", ":")) + "\n")
    return archive, identity, member_identities


class RunnerDeploymentTests(unittest.TestCase):
    def setUp(self):
        # Positive fixtures model operator-protected deployment paths, not the
        # checkout runner's ambient umask. Restore the caller after each case;
        # dedicated subprocess tests below exercise permissive caller masks.
        self.addCleanup(os.umask, os.umask(0o022))
        self.tmp = tempfile.TemporaryDirectory(prefix="lmdj-runner-test-")
        self.directory = Path(self.tmp.name)
        self.target = self.directory / "target"
        self.target.mkdir()
        self.archive, self.identity, self.members = make_bundle(self.directory, "one")
        self.runtime_config = self.directory / "runtime.toml"
        self.runtime_config.write_bytes(b"fallback_models=[]\n")
        self.runtime_config.chmod(0o440)

    def tearDown(self):
        self.tmp.cleanup()

    def config(self, archive: Path | None = None, identity: Path | None = None, *, active=True, config_suffix="") -> Path:
        archive = archive or self.archive
        identity = identity or self.identity
        config = copy.deepcopy(BASE_CONFIG)
        config["active"] = active
        if active:
            config["admission"] = {key: True for key in config["admission"]}
        config["bundle"]["archive"].update({"filename": archive.name, **digest(archive.read_bytes())})
        config["bundle"]["identity"].update({"filename": identity.name, **digest(identity.read_bytes())})
        config["bundle"]["files"] = copy.deepcopy(self.members)
        config["runtime_config"].update({"sha256": digest(self.runtime_config.read_bytes())["sha256"], "byte_length": self.runtime_config.stat().st_size})
        if config_suffix:
            config["paths"]["operator_config"] = f"/etc/lmdj/pr-agent/netcup-review-{config_suffix}.json"
        path = self.directory / f"config-{config_suffix or 'one'}.json"
        path.write_text(json.dumps(config, indent=2) + "\n")
        path.chmod(0o600)
        return path

    def fixture_env(self, overrides: dict[str, dict[str, int]] | None = None) -> dict[str, str]:
        identity = {"uid": os.getuid(), "gid": os.getgid()}
        environment = os.environ.copy()
        environment["PR_AGENT_DEPLOY_FIXTURE_IDENTITIES"] = json.dumps(
            {"operator": identity, "service": identity, "overrides": overrides or {}}, sort_keys=True)
        return environment

    def invoke(self, mode: str, config: Path, archive: Path | None = None, identity: Path | None = None,
               *, overrides: dict[str, dict[str, int]] | None = None, child_umask: int = -1):
        command = [str(SCRIPT), mode, "--config", str(config), "--target-root", str(self.target)]
        if archive is not None:
            command += ["--bundle", str(archive)]
        if identity is not None:
            command += ["--identity", str(identity)]
        if mode in {"verify", "install"}:
            command += ["--runtime-config", str(self.runtime_config)]
        return subprocess.run(command, text=True, capture_output=True, check=False,
                              env=self.fixture_env(overrides), umask=child_umask)

    def target_snapshot(self) -> dict[str, tuple]:
        snapshot = {}
        for path in sorted(self.target.rglob("*")):
            relative = str(path.relative_to(self.target))
            stat = path.lstat()
            if path.is_symlink():
                snapshot[relative] = ("symlink", os.readlink(path), stat.st_mode & 0o777, stat.st_uid, stat.st_gid)
            elif path.is_file():
                snapshot[relative] = ("file", path.read_bytes(), stat.st_mode & 0o777, stat.st_uid, stat.st_gid)
            else:
                snapshot[relative] = ("directory", stat.st_mode & 0o777, stat.st_uid, stat.st_gid)
        return snapshot

    def test_committed_defaults_are_inactive_and_use_the_approved_budget(self):
        self.assertFalse(BASE_CONFIG["active"])
        self.assertEqual(BASE_CONFIG["resources"]["concurrency"], 1)
        self.assertEqual(BASE_CONFIG["resources"]["cpu_quota"], "100%")
        self.assertEqual(BASE_CONFIG["resources"]["memory_max"], "2G")
        self.assertTrue(BASE_CONFIG["resources"]["heavy_slice_untouched"])

    def test_permissive_caller_umask_cannot_create_unsafe_install_parents(self):
        config = self.config()
        first = self.invoke("install", config, self.archive, self.identity, child_umask=0o000)
        self.assertEqual(first.returncode, 0, first.stderr)
        for parent in (self.target / "var", self.target / "var/lib", self.target / "var/lib/lmdj",
                       self.target / "etc", self.target / "etc/lmdj", self.target / "etc/lmdj/pr-agent"):
            with self.subTest(parent=parent):
                self.assertEqual(parent.stat().st_mode & 0o777, 0o755)
        before = self.target_snapshot()
        repeat = self.invoke("install", config, self.archive, self.identity, child_umask=0o002)
        self.assertEqual(repeat.returncode, 0, repeat.stderr)
        self.assertEqual(self.target_snapshot(), before)

    def test_permissive_caller_does_not_repair_existing_unsafe_parent(self):
        config = self.config()
        self.target.chmod(0o775)
        before = self.target_snapshot()
        result = self.invoke("install", config, self.archive, self.identity, child_umask=0o000)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("group/world writable", result.stderr)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o775)
        self.assertEqual(self.target_snapshot(), before)

    def test_bash_syntax_and_staged_script_do_not_depend_on_docker_or_systemctl(self):
        syntax = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        source = "\n".join(line for line in SCRIPT.read_text().splitlines() if not line.lstrip().startswith("#"))
        self.assertIsNone(re.search(r"\b(systemctl|docker)\s+(start|stop|restart|daemon|run|exec|build|install)\b", source.lower()))

    def test_dry_run_is_read_only_even_with_inactive_trusted_config(self):
        config = self.config(active=False)
        result = self.invoke("dry-run", config, self.archive, self.identity)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.target.rglob("*")), [])
        self.assertIn('"activation": "not performed"', result.stdout)

    def test_verify_rejects_malformed_detached_identity(self):
        identity = self.directory / "malformed.json"
        identity.write_text('{"schema":"wrong"}\n')
        config = self.config(identity=identity)
        result = self.invoke("verify", config, self.archive, identity)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("schema or keys", result.stderr)

    def test_verify_rejects_archive_digest_mismatch(self):
        tampered = self.directory / "tampered.tar"
        tampered.write_bytes(self.archive.read_bytes() + b"tamper")
        config = self.config()
        result = self.invoke("verify", config, tampered, self.identity)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("archive SHA-256/byte length", result.stderr)

    def test_verify_rejects_archive_link_member(self):
        with tarfile.open(self.archive, "a") as output:
            link = tarfile.TarInfo("pr-agent/unsafe-link")
            link.type = tarfile.SYMTYPE
            link.linkname = "config.toml"
            output.addfile(link)
        identity_document = json.loads(self.identity.read_text())
        identity_document["archive"] = {"sha256": digest(self.archive.read_bytes())["sha256"], "byte_length": self.archive.stat().st_size}
        self.identity.write_text(json.dumps(identity_document, sort_keys=True, separators=(",", ":")) + "\n")
        config = self.config()
        result = self.invoke("verify", config, self.archive, self.identity)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("link member", result.stderr)

    def test_verify_rejects_detached_identity_digest_mismatch(self):
        changed = self.directory / "changed.json"
        changed.write_bytes(self.identity.read_bytes() + b"tamper\n")
        config = self.config(identity=self.identity)
        result = self.invoke("verify", config, self.archive, changed)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("detached deployment identity SHA-256", result.stderr)

    def test_verify_rejects_identity_path_traversal_before_archive_access(self):
        document = json.loads(self.identity.read_text())
        document["files"]["manifest"]["path"] = "../outside"
        identity = self.directory / "traversal.json"
        identity.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")
        config = self.config(identity=identity)
        config_document = json.loads(config.read_text())
        config_document["bundle"]["files"]["manifest"]["path"] = "../outside"
        config.write_text(json.dumps(config_document) + "\n")
        result = self.invoke("verify", config, self.archive, identity)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bundle member path is unsafe", result.stderr)

    def test_install_fails_closed_on_incomplete_admission_without_target_writes(self):
        config = self.config(active=True)
        document = json.loads(config.read_text())
        document["admission"]["capacity_receipts"] = False
        config.write_text(json.dumps(document) + "\n")
        result = self.invoke("install", config, self.archive, self.identity)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("active deployment lacks", result.stderr)
        self.assertEqual(list(self.target.rglob("*")), [])

    def test_install_fails_closed_on_runtime_and_filesystem_isolation_drift(self):
        config = self.config(active=True)
        document = json.loads(config.read_text())
        document["runtime"]["python"] = "/usr/bin/python3.11"
        config.write_text(json.dumps(document) + "\n")
        result = self.invoke("install", config, self.archive, self.identity)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("system Python 3.12", result.stderr)
        self.assertEqual(list(self.target.rglob("*")), [])

    def test_install_stages_exact_release_unit_and_slice_without_activation(self):
        config = self.config(active=True)
        result = self.invoke("install", config, self.archive, self.identity)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout.splitlines()[-1])
        release = Path(output["release"])
        self.assertTrue((release / "bundle.tar").is_file())
        self.assertTrue((release / "DEPLOYMENT_IDENTITY.json").is_file())
        self.assertTrue((self.target / "var/lib/lmdj/pr-agent/current").is_symlink())
        unit = (self.target / "etc/systemd/system/lmdj-pr-agent.service").read_text()
        self.assertIn("User=lmdj-pr-agent", unit)
        self.assertIn("MemoryMax=2G", unit)
        self.assertIn("PrivateTmp=true", unit)
        self.assertIn("UnsetEnvironment=GITHUB_TOKEN GH_TOKEN", unit)
        self.assertIn("/usr/bin/python3.12", unit)
        self.assertIn("--input ", unit)
        self.assertIn("/run/lmdj-pr-agent/attempt/input.json", unit.replace(str(self.target), ""))
        self.assertIn("/runtime.toml", unit.replace(str(self.target), ""))
        self.assertIn("PYTHONPATH=", unit)
        self.assertIn("/vendor:", unit)
        self.assertIn("/usr/bin/flock --nonblock --exclusive", unit)
        self.assertIn("ReadWritePaths=", unit)
        self.assertIn("/var/lib/lmdj/pr-agent/releases/", unit)
        self.assertNotIn("/current/pr_agent_review.py", unit)
        self.assertIn("--deployment-identity", unit)
        self.assertIn("/run/lmdj-pr-agent/output", unit.replace(str(self.target), ""))
        self.assertNotIn("--no-github-write-token", unit)
        self.assertEqual(list(self.target.rglob("*.new-*")), [])

    def test_pristine_first_install_is_the_only_state_less_install_boundary(self):
        config = self.config(active=True)
        self.assertFalse((self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json").exists())
        result = self.invoke("install", config, self.archive, self.identity)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"status": "staged"', result.stdout)

    def test_corrupt_state_with_managed_effects_fails_closed_and_preserves_uncertain_data(self):
        config = self.config(active=True)
        self.assertEqual(self.invoke("install", config, self.archive, self.identity).returncode, 0)
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        corrupt = b'{"bogus":true}\n'
        state_path.write_bytes(corrupt)
        (self.target / "etc/systemd/system/lmdj-pr-agent.service").unlink()
        (self.target / "etc/systemd/system/lmdj-pr-review.slice").unlink()
        result = self.invoke("install", config, self.archive, self.identity)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("incomplete v2 shape", result.stderr)
        self.assertEqual(state_path.read_bytes(), corrupt)
        self.assertFalse((self.target / "etc/systemd/system/lmdj-pr-agent.service").exists())

    def test_missing_state_with_managed_effects_fails_closed_and_preserves_target(self):
        config = self.config(active=True)
        self.assertEqual(self.invoke("install", config, self.archive, self.identity).returncode, 0)
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        state_path.unlink()
        (self.target / "etc/systemd/system/lmdj-pr-agent.service").unlink()
        (self.target / "etc/systemd/system/lmdj-pr-review.slice").unlink()
        result = self.invoke("install", config, self.archive, self.identity)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("state is missing while managed target effects exist", result.stderr)
        self.assertFalse(state_path.exists())
        self.assertFalse((self.target / "etc/systemd/system/lmdj-pr-agent.service").exists())

    def test_fixture_identity_emulation_is_required_and_owner_drift_fails_before_effects(self):
        config = self.config(active=True)
        command = [str(SCRIPT), "install", "--config", str(config), "--bundle", str(self.archive),
                   "--identity", str(self.identity), "--runtime-config", str(self.runtime_config),
                   "--target-root", str(self.target)]
        absent = subprocess.run(command, text=True, capture_output=True, check=False, env={**os.environ, "PR_AGENT_DEPLOY_FIXTURE_IDENTITIES": ""})
        self.assertNotEqual(absent.returncode, 0)
        self.assertIn("fixture identity emulation", absent.stderr)
        operator_state = self.target / "var/lib/lmdj/pr-agent/operator-state"
        operator_state.mkdir(parents=True)
        operator_state.chmod(0o700)
        before = {path: path.read_bytes() for path in self.target.rglob("*") if path.is_file()}
        result = self.invoke("install", config, self.archive, self.identity, overrides={str(operator_state): {"uid": os.getuid() + 1, "gid": os.getgid()}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("operator state owner or mode is not approved", result.stderr)
        self.assertEqual({path: path.read_bytes() for path in self.target.rglob("*") if path.is_file()}, before)

    def test_raw_operator_sources_reject_symlinks_before_any_target_effect(self):
        config = self.config(active=True)
        linked_config = self.directory / "linked-config.json"
        linked_runtime = self.directory / "linked-runtime.toml"
        linked_config.symlink_to(config)
        linked_runtime.symlink_to(self.runtime_config)
        command = [str(SCRIPT), "install", "--config", str(linked_config), "--bundle", str(self.archive),
                   "--identity", str(self.identity), "--runtime-config", str(linked_runtime),
                   "--target-root", str(self.target)]
        for source, expected in ((linked_config, "deployment config must be a regular file"),
                                 (linked_runtime, "operator runtime config source must be a regular file")):
            with self.subTest(source=source.name):
                command[3] = str(source) if source == linked_config else str(config)
                command[9] = str(source) if source == linked_runtime else str(self.runtime_config)
                result = subprocess.run(command, text=True, capture_output=True, check=False, env=self.fixture_env())
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
                self.assertEqual(list(self.target.rglob("*")), [])

    def test_install_release_and_runtime_roots_have_independent_permissions(self):
        config = self.config(active=True)
        result = self.invoke("install", config, self.archive, self.identity)
        self.assertEqual(result.returncode, 0, result.stderr)
        release = (self.target / "var/lib/lmdj/pr-agent/current").resolve()
        self.assertEqual(release.stat().st_mode & 0o777, 0o755)
        self.assertEqual((release / "pr_agent_review.py").stat().st_mode & 0o777, 0o444)
        state_root = self.target / "var/lib/lmdj/pr-agent/engine-state"
        self.assertEqual(state_root.stat().st_mode & 0o777, 0o750)
        attempt = self.target / "run/lmdj-pr-agent/attempt"
        output = self.target / "run/lmdj-pr-agent/output"
        self.assertEqual(attempt.stat().st_mode & 0o777, 0o750)
        self.assertEqual(output.stat().st_mode & 0o777, 0o750)
        unit = (self.target / "etc/systemd/system/lmdj-pr-agent.service").read_text()
        writable = next(line for line in unit.splitlines() if line.startswith("ReadWritePaths="))
        self.assertIn("/var/lib/lmdj/pr-agent/engine-state", writable)
        self.assertIn("/run/lmdj-pr-agent/attempt", writable)
        self.assertIn("/run/lmdj-pr-agent/output", writable)
        self.assertNotIn("/var/lib/lmdj/pr-agent/releases", writable)
        self.assertNotIn("/var/lib/lmdj/pr-agent/operator-state", writable)
        self.assertNotIn("/etc/lmdj/pr-agent", writable)
        self.assertEqual((self.target / "etc/lmdj/pr-agent/runtime.toml").stat().st_mode & 0o777, 0o440)
        runtime_copy = release / "runtime.toml"
        self.assertEqual(runtime_copy.read_bytes(), self.runtime_config.read_bytes())
        with self.assertRaises(PermissionError):
            runtime_copy.write_bytes(b"must refuse\n")
        with self.assertRaises(PermissionError):
            (release / "pr_agent_review.py").write_bytes(b"must refuse\n")
        operator_state = self.target / "var/lib/lmdj/pr-agent/operator-state"
        self.assertEqual(operator_state.stat().st_mode & 0o777, 0o700)
        state_file = state_root / "probe.jsonl"
        state_file.write_text("service-writable\n")
        self.assertEqual(state_file.read_text(), "service-writable\n")

    def test_install_rejects_runtime_config_digest_mismatch_without_code_or_state_write(self):
        config = self.config(active=True)
        changed = self.directory / "changed-runtime.toml"
        changed.write_bytes(b"fallback_models=['tampered']\n")
        changed.chmod(0o440)
        result = subprocess.run([str(SCRIPT), "install", "--config", str(config), "--bundle", str(self.archive),
                                 "--identity", str(self.identity), "--runtime-config", str(changed),
                                 "--target-root", str(self.target)], text=True, capture_output=True, check=False,
                                env=self.fixture_env())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("runtime config SHA-256/byte length", result.stderr)
        self.assertEqual(list(self.target.rglob("*")), [])

    def test_repeated_install_is_idempotent_and_does_not_duplicate_ledger(self):
        config = self.config(active=True)
        first = self.invoke("install", config, self.archive, self.identity)
        second = self.invoke("install", config, self.archive, self.identity)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn('"status": "idempotent"', second.stdout)
        receipts = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        self.assertEqual(len(receipts.read_text().splitlines()), 1)

    def test_repeated_install_rejects_release_root_mode_drift_without_retry_effects(self):
        config = self.config(active=True)
        self.assertEqual(self.invoke("install", config, self.archive, self.identity).returncode, 0)
        current = self.target / "var/lib/lmdj/pr-agent/current"
        release = current.resolve()
        release.chmod(0o777)
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        receipts = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        before = self.target_snapshot()
        state_before = state_path.read_bytes()
        receipts_before = receipts.read_bytes()
        current_before = os.readlink(current)
        retry = self.invoke("install", config, self.archive, self.identity)
        self.assertNotEqual(retry.returncode, 0)
        self.assertIn("release root owner/group or mode", retry.stderr)
        self.assertEqual(self.target_snapshot(), before)
        self.assertEqual(state_path.read_bytes(), state_before)
        self.assertEqual(receipts.read_bytes(), receipts_before)
        self.assertEqual(os.readlink(current), current_before)

    def test_repeated_install_rejects_fixture_emulated_release_member_gid_drift_without_retry_effects(self):
        config = self.config(active=True)
        self.assertEqual(self.invoke("install", config, self.archive, self.identity).returncode, 0)
        current = self.target / "var/lib/lmdj/pr-agent/current"
        member = current.resolve() / "pr_agent_review.py"
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        receipts = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        before = self.target_snapshot()
        state_before = state_path.read_bytes()
        receipts_before = receipts.read_bytes()
        current_before = os.readlink(current)
        wrong_group = {"uid": os.getuid(), "gid": os.getgid() + 1}
        retry = self.invoke("install", config, self.archive, self.identity,
                            overrides={str(member): wrong_group})
        self.assertNotEqual(retry.returncode, 0)
        self.assertIn("release entry owner/group", retry.stderr)
        self.assertEqual(self.target_snapshot(), before)
        self.assertEqual(state_path.read_bytes(), state_before)
        self.assertEqual(receipts.read_bytes(), receipts_before)
        self.assertEqual(os.readlink(current), current_before)

    def test_interrupted_transition_reconciles_one_terminal_receipt(self):
        first_config = self.config(active=True)
        self.assertEqual(self.invoke("install", first_config, self.archive, self.identity).returncode, 0)
        archive_two, identity_two, members_two = make_bundle(self.directory, "receipt-recovery")
        self.members = members_two
        second_config = self.config(archive_two, identity_two, active=True, config_suffix="receipt-recovery")
        self.assertEqual(self.invoke("install", second_config, archive_two, identity_two).returncode, 0)
        receipts = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        receipt_records = [json.loads(line) for line in receipts.read_text().splitlines()]
        second_receipt = receipt_records[-1]
        receipts.write_text(json.dumps(receipt_records[0], sort_keys=True, separators=(",", ":")) + "\n")
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        state = json.loads(state_path.read_text())
        state["transition"] = {"action": "install", "from": state["previous"], "to": state["current"],
                                "previous": state["previous"], "receipt": second_receipt}
        state_path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n")
        retry = self.invoke("install", second_config, archive_two, identity_two)
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertIn('"status": "idempotent"', retry.stdout)
        reconciled = [json.loads(line) for line in receipts.read_text().splitlines()]
        matching = [record for record in reconciled if record.get("transition_id") == second_receipt["transition_id"]]
        self.assertEqual(len(matching), 1)
        self.assertNotIn("transition", json.loads(state_path.read_text()))

    def test_interrupted_transition_before_current_reconciles_one_terminal_receipt(self):
        first_config = self.config(active=True)
        self.assertEqual(self.invoke("install", first_config, self.archive, self.identity).returncode, 0)
        archive_two, identity_two, members_two = make_bundle(self.directory, "receipt-before-current")
        self.members = members_two
        second_config = self.config(archive_two, identity_two, active=True, config_suffix="receipt-before-current")
        self.assertEqual(self.invoke("install", second_config, archive_two, identity_two).returncode, 0)
        receipts = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        receipt_records = [json.loads(line) for line in receipts.read_text().splitlines()]
        second_receipt = receipt_records[-1]
        receipts.write_text(json.dumps(receipt_records[0], sort_keys=True, separators=(",", ":")) + "\n")
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        completed = json.loads(state_path.read_text())
        state = {**completed, "current": completed["previous"], "previous": None}
        state["transition"] = {"action": "install", "from": state["current"], "to": completed["current"],
                               "previous": state["current"], "receipt": second_receipt}
        state_path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n")
        retry = self.invoke("install", second_config, archive_two, identity_two)
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertIn('"status": "idempotent"', retry.stdout)
        reconciled = [json.loads(line) for line in receipts.read_text().splitlines()]
        self.assertEqual(sum(record.get("transition_id") == second_receipt["transition_id"] for record in reconciled), 1)
        final_state = json.loads(state_path.read_text())
        self.assertEqual(final_state["current"], completed["current"])
        self.assertEqual(final_state["previous"], completed["previous"])
        self.assertNotIn("transition", final_state)

    def test_pending_transition_semantic_mismatches_fail_before_reconciliation_effects(self):
        first_config = self.config(active=True)
        self.assertEqual(self.invoke("install", first_config, self.archive, self.identity).returncode, 0)
        archive_two, identity_two, members_two = make_bundle(self.directory, "semantic-recovery")
        self.members = members_two
        second_config = self.config(archive_two, identity_two, active=True, config_suffix="semantic-recovery")
        self.assertEqual(self.invoke("install", second_config, archive_two, identity_two).returncode, 0)
        receipts = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        records = [json.loads(line) for line in receipts.read_text().splitlines()]
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        completed = json.loads(state_path.read_text())
        receipt = records[-1]
        pending = copy.deepcopy(completed)
        pending["transition"] = {"action": "install", "from": completed["previous"], "to": completed["current"],
                                 "previous": completed["previous"], "receipt": copy.deepcopy(receipt)}
        rollback_receipt = {
            "schema": "lmdj.pr-agent-deployment-receipt.v1", "action": "rollback", "status": "staged",
            "transition_id": receipt["transition_id"], "from_release": completed["current"]["release"],
            "to_release": completed["previous"]["release"], "target": copy.deepcopy(receipt["target"]),
        }
        variants = {
            "receipt_action_mismatch": lambda state: state["transition"].update(receipt=copy.deepcopy(rollback_receipt)),
            "receipt_archive_identity_mismatch": lambda state: state["transition"]["receipt"].update(archive_sha256="0" * 64),
            "receipt_boolean_length": lambda state: state["transition"]["receipt"].update(archive_byte_length=True),
            "null_required_digest": lambda state: state["transition"]["to"].update(deployment_identity_sha256=None),
            "null_required_length": lambda state: state["transition"]["to"].update(archive_byte_length=None),
            "missing_required_length": lambda state: state["transition"]["to"].pop("service_unit_byte_length"),
            "boolean_required_length": lambda state: state["transition"]["to"].update(slice_unit_byte_length=True),
            "malformed_required_digest": lambda state: state["transition"]["to"].update(runtime_config_sha256="g" * 64),
            "impossible_current_without_previous": lambda state: state.update(current=None),
            "install_to_relationship_mismatch": lambda state: state["transition"].update(to=completed["previous"]),
            "install_previous_relationship_mismatch": lambda state: state["transition"].update(previous=None),
            "rollback_relationship_mismatch": lambda state: state.update(transition={
                "action": "rollback", "from": completed["current"], "to": completed["previous"],
                "previous": completed["current"], "receipt": copy.deepcopy(rollback_receipt)}),
            "rollback_to_relationship_mismatch": lambda state: state.update(transition={
                "action": "rollback", "from": completed["current"], "to": completed["current"],
                "previous": completed["current"], "receipt": {
                    **copy.deepcopy(rollback_receipt), "to_release": completed["current"]["release"]}}),
        }
        variants["install_from_relationship_mismatch"] = lambda state: state["transition"].update({"from": completed["current"]})
        for name, mutate in variants.items():
            with self.subTest(name=name):
                state = copy.deepcopy(pending)
                mutate(state)
                state_path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n")
                receipts.write_text(json.dumps(records[0], sort_keys=True, separators=(",", ":")) + "\n")
                before = self.target_snapshot()
                retry = self.invoke("install", second_config, archive_two, identity_two)
                self.assertNotEqual(retry.returncode, 0)
                self.assertIn("recover manually", retry.stderr)
                self.assertEqual(self.target_snapshot(), before)
                self.assertIn("transition", json.loads(state_path.read_text()))
                self.assertEqual([json.loads(line) for line in receipts.read_text().splitlines()], [records[0]])

    def test_interrupted_transition_rejects_noncanonical_or_conflicting_same_id_receipt(self):
        first_config = self.config(active=True)
        self.assertEqual(self.invoke("install", first_config, self.archive, self.identity).returncode, 0)
        archive_two, identity_two, members_two = make_bundle(self.directory, "receipt-mismatch")
        self.members = members_two
        second_config = self.config(archive_two, identity_two, active=True, config_suffix="receipt-mismatch")
        self.assertEqual(self.invoke("install", second_config, archive_two, identity_two).returncode, 0)
        receipts = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        records = [json.loads(line) for line in receipts.read_text().splitlines()]
        pending = records[-1]
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        state = json.loads(state_path.read_text())
        state["transition"] = {"action": "install", "from": state["previous"], "to": state["current"],
                               "previous": state["previous"], "receipt": pending}
        state_path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n")
        variants = {
            "id_only": {"transition_id": pending["transition_id"]},
            "wrong_status": {**pending, "status": "uncertain"},
            "wrong_target": {**pending, "target": {**pending["target"], "host": "wrong-host"}},
            "wrong_identity": {**pending, "archive_sha256": "0" * 64},
            "duplicate_conflict": [pending, {**pending, "deployment_identity_sha256": "f" * 64}],
        }
        for name, replacement in variants.items():
            with self.subTest(name=name):
                lines = replacement if isinstance(replacement, list) else [replacement]
                receipts.write_text("\n".join(json.dumps(line, sort_keys=True, separators=(",", ":")) for line in lines) + "\n")
                state_path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n")
                retry = self.invoke("install", second_config, archive_two, identity_two)
                self.assertNotEqual(retry.returncode, 0)
                self.assertIn("transition ID", retry.stderr)
                self.assertIn("transition", json.loads(state_path.read_text()))
                self.assertEqual([json.loads(line) for line in receipts.read_text().splitlines()], lines)

    def test_repeated_install_reverifies_tampered_current_release(self):
        config = self.config(active=True)
        first = self.invoke("install", config, self.archive, self.identity)
        self.assertEqual(first.returncode, 0, first.stderr)
        release = (self.target / "var/lib/lmdj/pr-agent/current").resolve()
        (release / "pr_agent_review.py").chmod(0o644)
        (release / "pr_agent_review.py").write_bytes(b"tampered")
        result = self.invoke("install", config, self.archive, self.identity)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("installed extracted member identity mismatch", result.stderr)

    def test_repeated_install_rejects_tampered_unlisted_vendor_file(self):
        config = self.config(active=True)
        first = self.invoke("install", config, self.archive, self.identity)
        self.assertEqual(first.returncode, 0, first.stderr)
        release = (self.target / "var/lib/lmdj/pr-agent/current").resolve()
        vendor = release / "vendor/litellm/__init__.py"
        vendor.chmod(0o644)
        vendor.write_bytes(b"tampered vendor\n")
        result = self.invoke("install", config, self.archive, self.identity)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("installed archive extracted bytes mismatch", result.stderr)

    def test_same_archive_changed_runtime_is_rejected_before_target_mutation(self):
        config = self.config(active=True)
        first = self.invoke("install", config, self.archive, self.identity)
        self.assertEqual(first.returncode, 0, first.stderr)
        changed = self.directory / "changed-runtime.toml"
        changed.write_bytes(b"fallback_models=['different-runtime']\n")
        changed.chmod(0o440)
        changed_config = json.loads(config.read_text())
        changed_config["runtime_config"].update(digest(changed.read_bytes()))
        changed_config["paths"]["operator_config"] = "/etc/lmdj/pr-agent/netcup-review-changed-runtime.json"
        changed_path = self.directory / "changed-runtime-config.json"
        changed_path.write_text(json.dumps(changed_config) + "\n")
        changed_path.chmod(0o600)
        before = {path: path.read_bytes() for path in self.target.rglob("*") if path.is_file()}
        result = subprocess.run([str(SCRIPT), "install", "--config", str(changed_path), "--bundle", str(self.archive),
                                 "--identity", str(self.identity), "--runtime-config", str(changed),
                                 "--target-root", str(self.target)], text=True, capture_output=True, check=False,
                                env=self.fixture_env())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("operator runtime config differs", result.stderr)
        self.assertEqual({path: path.read_bytes() for path in self.target.rglob("*") if path.is_file()}, before)

    def test_operator_owned_config_mismatch_is_never_overwritten(self):
        config = self.config(active=True)
        self.assertEqual(self.invoke("install", config, self.archive, self.identity).returncode, 0)
        operator_config = self.target / "etc/lmdj/pr-agent/netcup-review.json"
        operator_config.write_text("operator-owned\n")
        result = self.invoke("install", config, self.archive, self.identity)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("operator config differs", result.stderr)

    def test_same_prefix_tampered_unit_fails_before_any_target_change(self):
        first_config = self.config(active=True)
        self.assertEqual(self.invoke("install", first_config, self.archive, self.identity).returncode, 0)
        archive_two, identity_two, members_two = make_bundle(self.directory, "unit-two")
        self.members = members_two
        second_config = self.config(archive_two, identity_two, active=True, config_suffix="unit-two")
        unit = self.target / "etc/systemd/system/lmdj-pr-agent.service"
        unit.write_text("[Unit]\nDescription=LMDJ PR-Agent tampered\n")
        before = {path: path.read_bytes() for path in self.target.rglob("*") if path.is_file()}
        current_before = (self.target / "var/lib/lmdj/pr-agent/current").resolve()
        result = self.invoke("install", second_config, archive_two, identity_two)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("digest does not match", result.stderr)
        self.assertEqual((self.target / "var/lib/lmdj/pr-agent/current").resolve(), current_before)
        self.assertEqual({path: path.read_bytes() for path in self.target.rglob("*") if path.is_file()}, before)

    def test_rollback_switches_exact_release_and_retains_uncertain_ledger_record(self):
        first_config = self.config(active=True)
        self.assertEqual(self.invoke("install", first_config, self.archive, self.identity).returncode, 0)
        unit_path = self.target / "etc/systemd/system/lmdj-pr-agent.service"
        first_unit = unit_path.read_text()
        monetary_ledger = self.target / "var/lib/lmdj/pr-agent/engine-state/ledger.jsonl"
        monetary_ledger.parent.mkdir(parents=True, exist_ok=True)
        monetary_ledger.write_text(json.dumps({"schema": "lmdj.pr-agent-ledger.v1", "status": "reserved"}) + "\n")
        uncertain = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        with uncertain.open("a") as handle:
            handle.write(json.dumps({"status": "uncertain", "request_id": "keep-me"}) + "\n")
        archive_two, identity_two, members_two = make_bundle(self.directory, "two")
        self.members = members_two
        second_config = self.config(archive_two, identity_two, active=True, config_suffix="two")
        self.assertEqual(self.invoke("install", second_config, archive_two, identity_two).returncode, 0)
        second_unit = unit_path.read_text()
        self.assertNotEqual(first_unit, second_unit)
        current = self.target / "var/lib/lmdj/pr-agent/current"
        second_release = current.resolve()
        result = self.invoke("rollback", second_config)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(current.resolve(), second_release)
        first_release = current.resolve()
        rollback_unit = unit_path.read_text()
        self.assertEqual(rollback_unit, first_unit)
        self.assertNotEqual(rollback_unit, second_unit)
        lines = uncertain.read_text().splitlines()
        self.assertTrue(any('"status": "uncertain"' in line for line in lines))
        self.assertTrue(any('"action":"rollback"' in line for line in lines))
        self.assertEqual(json.loads(monetary_ledger.read_text())['status'], "reserved")
        self.assertTrue((self.target / "var/lib/lmdj/pr-agent/releases").is_dir())

        repeated = self.invoke("rollback", second_config)
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertIn('"status": "idempotent"', repeated.stdout)
        self.assertEqual(current.resolve(), first_release)
        self.assertEqual(unit_path.read_text(), first_unit)

        reinstated = self.invoke("install", second_config, archive_two, identity_two)
        self.assertEqual(reinstated.returncode, 0, reinstated.stderr)
        self.assertEqual(current.resolve(), second_release)
        self.assertEqual(unit_path.read_text(), second_unit)
        receipt_records = [json.loads(line) for line in uncertain.read_text().splitlines()]
        transition_ids = [record["transition_id"] for record in receipt_records if "transition_id" in record]
        self.assertEqual(len(transition_ids), 4)
        self.assertEqual(len(transition_ids), len(set(transition_ids)))

    def test_actual_v14_archive_contract_when_explicitly_enabled(self):
        if os.environ.get("PR_AGENT_RUN_V14_DEPLOYMENT_TEST") != "1":
            self.skipTest("set PR_AGENT_RUN_V14_DEPLOYMENT_TEST=1 with the pinned T2 v14 artifact")
        archive = Path(os.environ.get("PR_AGENT_V14_ARCHIVE", "/tmp/lmdj-pr-agent-packaging/artifacts-v14/lmdj-pr-agent-linux-amd64-53072488e4c3b5a6c9ae730fe6fb52fc5f09d06c.tar"))
        identity = archive.with_name("DEPLOYMENT_IDENTITY.json")
        if not archive.is_file() or not identity.is_file():
            self.skipTest("pinned T2 v14 archive and detached identity are unavailable")
        with tarfile.open(archive) as source:
            names = source.getnames()
        self.assertTrue(any(name.startswith("pr-agent/vendor/litellm/") for name in names))
        self.assertIn("pr-agent/pr_agent", names)
        self.assertIn("pr-agent/pr_agent_review.py", names)
        self.members = json.loads(identity.read_text())["files"]
        config = self.config(archive, identity, active=True)
        result = self.invoke("install", config, archive, identity)
        self.assertEqual(result.returncode, 0, result.stderr)
        unit = (self.target / "etc/systemd/system/lmdj-pr-agent.service").read_text()
        self.assertIn("/vendor:", unit)
        self.assertIn("--config /", unit)
        self.assertIn("--engine-cwd /run/lmdj-pr-agent/attempt/engine", unit.replace(str(self.target), "").replace("/private", ""))

    def test_rollback_without_recorded_previous_release_is_read_only_failure(self):
        config = self.config(active=True)
        result = self.invoke("rollback", config)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("previous release", result.stderr)
        self.assertEqual(list(self.target.rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
