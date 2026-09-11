#!/usr/bin/env python3
"""Contract tests for the repository-owned, inactive Netcup deployment boundary."""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import stat
import shutil
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/pr-agent/deploy-runner.sh"
BASE_CONFIG = json.loads((ROOT / "scripts/ci/pr-agent/netcup-review.json").read_text())
PROVIDER_ENV_FILE = "EnvironmentFile=-/etc/lmdj/pr-agent/provider.env"
PROVIDER_ENV_NAMES = (
    "PR_AGENT_DEEPSEEK_API_KEY",
    "PR_AGENT_ZAI_API_KEY",
    "PR_AGENT_XAI_API_KEY",
    "PR_AGENT_KIMI_API_KEY",
)


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

    def fixture_env(self, overrides: dict[str, dict[str, int]] | None = None,
                    *, operator: dict[str, int] | None = None,
                    service: dict[str, int] | None = None) -> dict[str, str]:
        identity = {"uid": os.getuid(), "gid": os.getgid()}
        environment = os.environ.copy()
        environment["PR_AGENT_DEPLOY_FIXTURE_IDENTITIES"] = json.dumps(
            {"operator": operator or identity, "service": service or identity, "overrides": overrides or {}}, sort_keys=True)
        return environment

    def runtime(self, marker: str, enabled: bool) -> Path:
        source = self.directory / f"runtime-{marker}.toml"
        source.write_text(f"[providers.deepseek]\nenabled={'true' if enabled else 'false'}\n")
        source.chmod(0o440)
        return source

    def config_for_runtime(self, source: Path, *, active: bool, operator_access: bool = True,
                           runner_classification: bool = True, suffix: str = "") -> Path:
        document = json.loads(self.config(active=active, config_suffix=suffix).read_text())
        document["admission"]["operator_access"] = operator_access
        document["admission"]["runner04_classification"] = runner_classification
        document["runtime_config"].update(digest(source.read_bytes()))
        path = self.directory / f"runtime-config-{source.stem}.json"
        path.write_text(json.dumps(document, sort_keys=True) + "\n")
        path.chmod(0o600)
        return path

    def invoke(self, mode: str, config: Path, archive: Path | None = None, identity: Path | None = None,
               *, runtime: Path | None = None, overrides: dict[str, dict[str, int]] | None = None,
               child_umask: int = -1, python_bin: Path | None = None,
               trace_path: Path | None = None, operator: dict[str, int] | None = None,
               service: dict[str, int] | None = None, extra_environment: dict[str, str] | None = None,
               without_provider_environment: bool = False):
        command = [str(SCRIPT), mode, "--config", str(config), "--target-root", str(self.target)]
        if archive is not None:
            command += ["--bundle", str(archive)]
        if identity is not None:
            command += ["--identity", str(identity)]
        if mode in {"verify", "stage", "install"}:
            command += ["--runtime-config", str(runtime or self.runtime_config)]
        environment = self.fixture_env(overrides, operator=operator, service=service)
        if without_provider_environment:
            for name in PROVIDER_ENV_NAMES:
                environment.pop(name, None)
        if extra_environment:
            environment.update(extra_environment)
        if python_bin is not None:
            environment["PR_AGENT_DEPLOY_PYTHON"] = str(python_bin)
        if trace_path is not None:
            environment["PR_AGENT_TRACE_PATH"] = str(trace_path)
        return subprocess.run(command, text=True, capture_output=True, check=False,
                              env=environment, umask=child_umask)

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

    def external_snapshot(self, root: Path) -> dict[str, tuple]:
        snapshot = {}
        for path in sorted(root.rglob("*")):
            relative = str(path.relative_to(root))
            metadata = path.lstat()
            if path.is_symlink():
                snapshot[relative] = ("symlink", os.readlink(path), metadata.st_mode & 0o777,
                                      metadata.st_uid, metadata.st_gid)
            elif path.is_file():
                snapshot[relative] = ("file", path.read_bytes(), metadata.st_mode & 0o777,
                                      metadata.st_uid, metadata.st_gid)
            else:
                snapshot[relative] = ("directory", metadata.st_mode & 0o777,
                                      metadata.st_uid, metadata.st_gid)
        return snapshot

    def target_path(self, absolute: str) -> Path:
        return (self.target / Path(absolute).relative_to("/")).resolve()

    def assert_release_record_complete(self, record: dict, *, expected_release: Path,
                                       expected_service_unit: bytes | None = None,
                                       expected_slice_unit: bytes | None = None) -> None:
        self.assertEqual(record["release"], str(expected_release))
        self.assertEqual(
            (expected_release / "REVISION_RECORD.json").read_bytes(),
            (json.dumps(record, sort_keys=True, indent=2) + "\n").encode(),
        )
        for path in expected_release.rglob("*"):
            if path.is_symlink():
                self.fail(f"immutable release contains a symlink: {path}")
            metadata = path.stat()
            expected_mode = 0o755 if path.is_dir() else 0o444
            self.assertEqual(metadata.st_mode & 0o777, expected_mode, path)
            self.assertEqual((metadata.st_uid, metadata.st_gid), (os.getuid(), os.getgid()), path)
        digest_fields = (
            ("bundle.tar", "archive_sha256", "archive_byte_length"),
            ("DEPLOYMENT_IDENTITY.json", "deployment_identity_sha256", "deployment_identity_byte_length"),
            ("runtime.toml", "runtime_config_sha256", "runtime_config_byte_length"),
            ("operator-config.json", "operator_config_sha256", "operator_config_byte_length"),
            ("service.unit", "service_unit_sha256", "service_unit_byte_length"),
            ("slice.unit", "slice_unit_sha256", "slice_unit_byte_length"),
        )
        for relative, digest_key, length_key in digest_fields:
            actual = digest((expected_release / relative).read_bytes())
            self.assertEqual(actual["sha256"], record[digest_key])
            self.assertEqual(actual["byte_length"], record[length_key])
        if expected_service_unit is not None:
            self.assertEqual((expected_release / "service.unit").read_bytes(), expected_service_unit)
        if expected_slice_unit is not None:
            self.assertEqual((expected_release / "slice.unit").read_bytes(), expected_slice_unit)
        for digest_key in ("archive_sha256", "deployment_identity_sha256", "runtime_config_sha256",
                           "operator_config_sha256", "deployment_tool_sha256", "service_unit_sha256",
                           "slice_unit_sha256"):
            self.assertRegex(record[digest_key], r"^[0-9a-f]{64}$")
        for length_key in ("archive_byte_length", "deployment_identity_byte_length",
                           "runtime_config_byte_length", "operator_config_byte_length",
                           "deployment_tool_byte_length", "service_unit_byte_length",
                           "slice_unit_byte_length"):
            self.assertIsInstance(record[length_key], int)
            self.assertGreater(record[length_key], 0)
        member_identities = record["member_identities"]
        self.assertTrue(member_identities)
        for member in member_identities.values():
            actual = digest((expected_release / member["path"]).read_bytes())
            self.assertEqual(actual["sha256"], member["sha256"])
            self.assertEqual(actual["byte_length"], member["byte_length"])

    def assert_revision_far_side(self, config: Path, runtime: Path, revision: Path,
                                 operator_bytes: bytes, service_unit: bytes, slice_unit: bytes,
                                 ledger_bytes: bytes) -> dict:
        config_document = json.loads(config.read_text())
        operator_path = self.target_path(config_document["paths"]["operator_config"])
        runtime_path = self.target_path(config_document["paths"]["runtime_config"])
        service_path = self.target_path(config_document["paths"]["unit"])
        slice_path = self.target_path(config_document["paths"]["slice_unit"])
        ledger_path = self.target_path(config_document["paths"]["ledger"])
        self.assertEqual(operator_path.read_bytes(), operator_bytes)
        self.assertEqual(runtime_path.read_bytes(), runtime.read_bytes())
        self.assertEqual(service_path.read_bytes(), service_unit)
        self.assertEqual(slice_path.read_bytes(), slice_unit)
        self.assertEqual(ledger_path.read_bytes(), ledger_bytes)
        current_path = self.target_path(config_document["paths"]["install_root"]) / "current"
        self.assertTrue(current_path.is_symlink())
        self.assertEqual(current_path.resolve(), revision)
        state_path = self.target_path(config_document["paths"]["state"])
        state = json.loads(state_path.read_text())
        self.assertEqual(state["schema"], "lmdj-pr-agent-runtime-state.v3")
        self.assertEqual(state["current"]["release"], str(revision))
        self.assertEqual(state["inventory"]["runtime_config"], str(runtime_path))
        self.assertEqual(state["inventory"]["operator_config"], str(operator_path))
        self.assert_release_record_complete(state["current"], expected_release=revision)
        if state["previous"] is not None:
            self.assert_release_record_complete(state["previous"], expected_release=Path(state["previous"]["release"]))
        service_identity = digest(service_unit)
        self.assertEqual(state["current"]["service_unit_sha256"], service_identity["sha256"])
        self.assertEqual(state["current"]["service_unit_byte_length"], service_identity["byte_length"])
        slice_identity = digest(slice_unit)
        self.assertEqual(state["current"]["slice_unit_sha256"], slice_identity["sha256"])
        self.assertEqual(state["current"]["slice_unit_byte_length"], slice_identity["byte_length"])
        receipt_path = Path(state["inventory"]["deployment_receipts"])
        self.assertEqual(state["latest_transition"], json.loads(receipt_path.read_text().splitlines()[-1]))
        self.assertEqual(operator_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(runtime_path.stat().st_mode & 0o777, 0o440)
        self.assertEqual(service_path.stat().st_mode & 0o777, 0o644)
        self.assertEqual(slice_path.stat().st_mode & 0o777, 0o644)
        self.assertEqual(state_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(receipt_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(os.readlink(current_path), str(revision))
        return state

    def assert_terminal_far_side(self, state_path: Path, expected_release: Path,
                                 expected_previous_release: Path | None,
                                 expected_config: Path, expected_runtime: Path,
                                 expected_action: str, ledger_bytes: bytes,
                                 expected_previous_config: Path | None = None,
                                 expected_previous_runtime: Path | None = None,
                                 expected_receipt_target_config: Path | None = None,
                                 expected_service_unit: bytes | None = None,
                                 expected_slice_unit: bytes | None = None,
                                 expected_previous_service_unit: bytes | None = None,
                                 expected_previous_slice_unit: bytes | None = None) -> dict:
        """Assert the complete external terminal state, including metadata."""
        state = json.loads(state_path.read_text())
        self.assertNotIn("transition", state)
        self.assertEqual(state["activation"], "pending")
        record = state["current"]
        self.assertEqual(record["release"], str(expected_release))
        expected_document = json.loads(expected_config.read_text())
        expected_inventory = self.expected_inventory(expected_config)
        expected_receipt_target_inventory = self.expected_inventory(
            expected_receipt_target_config or expected_config)
        if expected_service_unit is None or expected_slice_unit is None:
            expected_service_unit, expected_slice_unit = self.expected_unit_bytes(expected_config, expected_release)
        self.assertEqual(state["inventory"], expected_inventory)
        self.assertEqual(record["target_inventory"], expected_inventory)
        self.assertEqual(record["active"], expected_document["active"])
        self.assertEqual(record["admission"], expected_document["admission"])
        self.assertEqual(record["operator_config_path"], expected_inventory["operator_config"])
        self.assertEqual(record["runtime_config_path"], expected_inventory["runtime_config"])
        self.assertEqual(record["operator_config_sha256"], digest(expected_config.read_bytes())["sha256"])
        self.assertEqual(record["operator_config_byte_length"], expected_config.stat().st_size)
        if expected_runtime is None:
            self.assertIsNone(record["runtime_config_sha256"])
            self.assertIsNone(record["runtime_config_byte_length"])
        else:
            self.assertEqual(record["runtime_config_sha256"], digest(expected_runtime.read_bytes())["sha256"])
            self.assertEqual(record["runtime_config_byte_length"], expected_runtime.stat().st_size)
        self.assertEqual(record, json.loads((expected_release / "REVISION_RECORD.json").read_text()))
        self.assert_release_record_complete(
            record, expected_release=expected_release,
            expected_service_unit=expected_service_unit,
            expected_slice_unit=expected_slice_unit)
        if expected_previous_release is None:
            self.assertIsNone(state["previous"])
        else:
            self.assertEqual(state["previous"]["release"], str(expected_previous_release))
            self.assertEqual(state["previous"], json.loads((expected_previous_release / "REVISION_RECORD.json").read_text()))
            if expected_previous_service_unit is None or expected_previous_slice_unit is None:
                expected_previous_service_unit, expected_previous_slice_unit = self.expected_unit_bytes(
                    expected_previous_config, expected_previous_release)
            self.assert_release_record_complete(
                state["previous"], expected_release=expected_previous_release,
                expected_service_unit=expected_previous_service_unit,
                expected_slice_unit=expected_previous_slice_unit)
            self.assertIsNotNone(expected_previous_config)
            previous_document = json.loads(expected_previous_config.read_text())
            previous_inventory = self.expected_inventory(expected_previous_config)
            previous_record = state["previous"]
            self.assertEqual(previous_record["target_inventory"], previous_inventory)
            self.assertEqual(previous_record["active"], previous_document["active"])
            self.assertEqual(previous_record["admission"], previous_document["admission"])
            self.assertEqual(previous_record["operator_config_path"], previous_inventory["operator_config"])
            self.assertEqual(previous_record["runtime_config_path"], previous_inventory["runtime_config"])
            self.assertEqual(previous_record["operator_config_sha256"], digest(expected_previous_config.read_bytes())["sha256"])
            self.assertEqual(previous_record["operator_config_byte_length"], expected_previous_config.stat().st_size)
            if expected_previous_runtime is None:
                self.assertIsNone(previous_record["runtime_config_sha256"])
                self.assertIsNone(previous_record["runtime_config_byte_length"])
            else:
                self.assertEqual(previous_record["runtime_config_sha256"], digest(expected_previous_runtime.read_bytes())["sha256"])
                self.assertEqual(previous_record["runtime_config_byte_length"], expected_previous_runtime.stat().st_size)
        release = expected_release
        inventory = state["inventory"]
        paths = {name: Path(inventory[name]) for name in
                 ("operator_config", "runtime_config", "unit", "slice_unit", "state", "deployment_receipts", "ledger")}
        self.assertEqual(paths["operator_config"].read_bytes(), expected_config.read_bytes())
        self.assertEqual(paths["runtime_config"].read_bytes(), expected_runtime.read_bytes())
        actual_service_unit = paths["unit"].read_bytes()
        actual_slice_unit = paths["slice_unit"].read_bytes()
        self.assertEqual(actual_service_unit, expected_service_unit)
        self.assertEqual(actual_slice_unit, expected_slice_unit)
        self.assertEqual(digest(actual_service_unit),
                         {"sha256": record["service_unit_sha256"],
                          "byte_length": record["service_unit_byte_length"]})
        self.assertEqual(digest(actual_slice_unit),
                         {"sha256": record["slice_unit_sha256"],
                          "byte_length": record["slice_unit_byte_length"]})
        if ledger_bytes is None:
            self.assertFalse(paths["ledger"].exists())
        else:
            self.assertEqual(paths["ledger"].read_bytes(), ledger_bytes)
        expected_modes = {"operator_config": 0o600, "runtime_config": 0o440,
                          "unit": 0o644, "slice_unit": 0o644,
                          "state": 0o600, "deployment_receipts": 0o600}
        for name, mode in expected_modes.items():
            self.assertEqual(paths[name].stat().st_mode & 0o777, mode, name)
            self.assertEqual((paths[name].stat().st_uid, paths[name].stat().st_gid),
                             (os.getuid(), os.getgid()), name)
        pointer = Path(inventory["install_root"]) / "current"
        self.assertTrue(pointer.is_symlink())
        self.assertEqual(os.readlink(pointer), str(release))
        latest = json.loads(paths["deployment_receipts"].read_text().splitlines()[-1])
        self.assertEqual(latest, state["latest_transition"])
        self.assertEqual(latest["action"], expected_action)
        self.assertEqual(latest["target"], expected_receipt_target_inventory)
        self.assertEqual(latest["from_release"],
                         expected_previous_release and str(Path(inventory["install_root"]) / "releases" / expected_previous_release.name))
        self.assertEqual(latest["to_release"], str(expected_release))
        for endpoint, expected_record in (("from", state["previous"]), ("to", record)):
            if expected_record is None:
                self.assertIsNone(latest[f"{endpoint}_record_sha256"])
                self.assertIsNone(latest[f"{endpoint}_record_byte_length"])
            else:
                record_bytes = (Path(expected_record["release"]) / "REVISION_RECORD.json").read_bytes()
                self.assertEqual(latest[f"{endpoint}_record_sha256"], hashlib.sha256(record_bytes).hexdigest())
                self.assertEqual(latest[f"{endpoint}_record_byte_length"], len(record_bytes))
        return state

    def _novel_setup(self, *, distinct_paths: bool = False, nested_receipts: bool = False):
        """Create the admitted A-stage/B-install fixture used by N1-N3 ports."""
        suffix_a = "novel-old" if distinct_paths else ""
        suffix_b = "novel-new" if distinct_paths else ""
        runtime_a = self.runtime("novel-a", enabled=False)
        config_a = self.config_for_runtime(runtime_a, active=False, suffix=suffix_a)
        if nested_receipts:
            document = json.loads(config_a.read_text())
            document["paths"]["deployment_receipts"] = document["paths"]["operator_state_root"] + "/receipts/history.jsonl"
            config_a.write_text(json.dumps(document, sort_keys=True) + "\n")
        staged = self.invoke("stage", config_a, self.archive, self.identity, runtime=runtime_a)
        self.assertEqual(staged.returncode, 0, staged.stderr)
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        receipt_path = self.target_path(json.loads(config_a.read_text())["paths"]["deployment_receipts"])
        state_a = json.loads(state_path.read_text())
        runtime_b = self.runtime("novel-b", enabled=True)
        config_b = self.config_for_runtime(runtime_b, active=True, suffix=suffix_b)
        if nested_receipts:
            document = json.loads(config_b.read_text())
            document["paths"]["deployment_receipts"] = document["paths"]["operator_state_root"] + "/receipts/history.jsonl"
            config_b.write_text(json.dumps(document, sort_keys=True) + "\n")
        installed = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        receipts = [json.loads(line) for line in receipt_path.read_text().splitlines()]
        state_b = json.loads(state_path.read_text())
        ledger = self.target_path(json.loads(config_b.read_text())["paths"]["ledger"])
        uncertain = b'{"status":"uncertain","request_id":"n1-n3-port"}\n'
        ledger.write_bytes(uncertain)
        return runtime_a, config_a, runtime_b, config_b, state_path, receipt_path, state_a, state_b, uncertain

    def expected_inventory(self, config: Path) -> dict:
        document = json.loads(config.read_text())
        paths = document["paths"]
        inventory = {}
        for key in ("install_root", "operator_config", "runtime_config", "state_root",
                    "operator_state_root", "ledger", "deployment_receipts", "state",
                    "unit", "slice_unit", "slot_lock", "attempt_root", "output_root"):
            inventory[key] = str(self.target.resolve() / Path(paths[key]).relative_to("/"))
        inventory.update({key: document["target"][key] for key in ("host", "service", "slice", "labels")})
        return inventory

    def expected_revision_path(self, config: Path, runtime: Path | None) -> Path:
        """Independently bind the fixture's revision identity before invoke."""
        document = json.loads(config.read_text())
        inventory = self.expected_inventory(config)
        archive_bytes = self.archive.read_bytes()
        identity_bytes = self.identity.read_bytes()
        runtime_identity = digest(runtime.read_bytes()) if runtime is not None else {"sha256": None, "byte_length": None}
        payload = {
            "schema": "lmdj.pr-agent-deployment-revision.v1",
            "archive": digest(archive_bytes),
            "detached_identity": digest(identity_bytes),
            "runtime_config": runtime_identity,
            "operator_config": digest(config.read_bytes()),
            "inventory": inventory,
            "active": document["active"],
            "admission": document["admission"],
            "deployment_tool": digest(SCRIPT.read_bytes()),
        }
        revision = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return Path(inventory["install_root"]) / "releases" / revision

    def expected_unit_bytes(self, config: Path, release: Path, *, include_provider_environment: bool = True) -> tuple[bytes, bytes]:
        """Build the fixed fixture oracle without invoking the production renderer."""
        document = json.loads(config.read_text())
        target = document["target"]
        runtime = document["runtime"]
        inventory = self.expected_inventory(config)
        blocked_environment = " ".join(runtime["blocked_environment"])
        current = release
        runtime_config = release / "runtime.toml"
        attempt = Path(inventory["attempt_root"])
        output = Path(inventory["output_root"])
        slot_lock = Path(inventory["slot_lock"])
        ledger = Path(inventory["ledger"])
        provider_environment = PROVIDER_ENV_FILE + "\n" if include_provider_environment else ""
        command = (
            "/usr/bin/flock --nonblock --exclusive " + str(slot_lock) + " " + runtime["python"] + " "
            + str(current / "pr_agent_review.py") + " --input " + str(attempt / "input.json")
            + " --config " + str(runtime_config) + " --source-root " + str(current)
            + " --engine-cwd " + str(attempt / "engine")
            + " --deployment-identity " + str(current / "DEPLOYMENT_IDENTITY.json")
            + " --ledger " + str(ledger) + " --output-dir " + str(output)
        ) if document["active"] else "/usr/bin/false"
        service = f"""[Unit]
Description=LMDJ PR-Agent isolated one-slot review attempt (staged, not auto-activated)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User={runtime['user']}
Group={runtime['group']}
WorkingDirectory={current}
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=LITELLM_LOCAL_MODEL_COST_MAP=true
Environment=PYTHONPATH={current / 'vendor'}:{current}
Environment=TIKTOKEN_CACHE_DIR={current / 'tokenizer-cache'}
{provider_environment}ExecStartPre=/usr/bin/test -r {attempt / 'input.json'}
ExecStartPre=/usr/bin/test -d {attempt / 'engine'}
ExecStartPre=/usr/bin/test -d {output}
ExecStart={command}
Slice={target['slice']}
CPUQuota={document['resources']['cpu_quota']}
CPUWeight={document['resources']['cpu_weight']}
MemoryMax={document['resources']['memory_max']}
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictNamespaces=true
LockPersonality=true
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
UnsetEnvironment={blocked_environment}
ReadOnlyPaths={current} {runtime_config}
ReadWritePaths={Path(inventory['state_root'])} {attempt} {output} {slot_lock}

[Install]
WantedBy=multi-user.target
"""
        slice_unit = f"""[Unit]
Description=LMDJ PR-Agent one-slot review sibling slice

[Slice]
CPUQuota={document['resources']['cpu_quota']}
CPUWeight={document['resources']['cpu_weight']}
MemoryMax={document['resources']['memory_max']}
TasksMax=128
"""
        return service.encode(), slice_unit.encode()

    def _assert_unchanged_failure(self, result, before, message):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(message, result.stderr)
        self.assertEqual(self.target_snapshot(), before)

    def test_service_environment_directive_is_fixed_and_provider_value_is_not_copied(self):
        source = SCRIPT.read_text()
        directives = "\n".join(line for line in source.splitlines() if line.startswith("Environment"))
        self.assertEqual(directives.count(PROVIDER_ENV_FILE), 1)
        self.assertNotIn("Environment=PR_AGENT_", directives)
        self.assertNotIn("PassEnvironment=", source)
        for blocked_name in ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_APP_ID", "GITHUB_APP_PRIVATE_KEY"):
            self.assertIn(blocked_name, source)

        inactive_runtime = self.runtime("service-environment-inactive", enabled=False)
        inactive_config = self.config_for_runtime(inactive_runtime, active=False)
        inactive = self.invoke("stage", inactive_config, self.archive, self.identity,
                               runtime=inactive_runtime, without_provider_environment=True)
        self.assertEqual(inactive.returncode, 0, inactive.stderr)
        inactive_unit = (self.target / "etc/systemd/system/lmdj-pr-agent.service").read_bytes()
        self.assertIn((PROVIDER_ENV_FILE + "\n").encode(), inactive_unit)
        self.assertIn(b"ExecStart=/usr/bin/false\n", inactive_unit)
        self.assertIn(b"UnsetEnvironment=GITHUB_TOKEN GH_TOKEN GITHUB_APP_ID GITHUB_APP_PRIVATE_KEY\n", inactive_unit)

        shutil.rmtree(self.target)
        self.target.mkdir()
        active_runtime = self.runtime("service-environment-active", enabled=True)
        active_config = self.config_for_runtime(active_runtime, active=True)
        synthetic = "synthetic-provider-value-never-copy"
        active = self.invoke("install", active_config, self.archive, self.identity,
                             runtime=active_runtime,
                             extra_environment={"PR_AGENT_DEEPSEEK_API_KEY": synthetic})
        self.assertEqual(active.returncode, 0, active.stderr)
        self.assertNotIn(synthetic, active.stdout)
        self.assertNotIn(synthetic, active.stderr)
        self.assertFalse(self.target_path("/etc/lmdj/pr-agent/provider.env").exists())
        self.assertNotIn(synthetic.encode(), self.archive.read_bytes())
        self.assertNotIn(synthetic.encode(), self.identity.read_bytes())
        for path in self.target.rglob("*"):
            if path.is_file() and not path.is_symlink():
                self.assertNotIn(synthetic.encode(), path.read_bytes(), path)

    def test_new_renderer_install_and_rollback_restore_historical_unit_bytes(self):
        global SCRIPT
        old_script = self.directory / "old-deploy-runner.sh"
        old_script.write_bytes(subprocess.check_output([
            "git", "show",
            "a22dae478fba4e53ba9a5467dc1b9afe775c51e1:scripts/ci/pr-agent/deploy-runner.sh",
        ]))
        old_script.chmod(0o755)
        current_script = SCRIPT
        config_a = self.config(active=True)
        archive_bytes = self.archive.read_bytes()
        identity_bytes = self.identity.read_bytes()
        config_bytes = config_a.read_bytes()
        runtime_bytes = self.runtime_config.read_bytes()
        try:
            SCRIPT = old_script
            release_a = self.expected_revision_path(config_a, self.runtime_config)
            expected_old_service, expected_old_slice = self.expected_unit_bytes(
                config_a, release_a, include_provider_environment=False)
            self.assertNotIn(PROVIDER_ENV_FILE.encode(), expected_old_service)
            self.assertNotIn(PROVIDER_ENV_FILE.encode(), expected_old_slice)
            SCRIPT = current_script
            release_b = self.expected_revision_path(config_a, self.runtime_config)
            self.assertNotEqual(release_a, release_b)
            expected_new_service, expected_new_slice = self.expected_unit_bytes(config_a, release_b)
            self.assertIn(PROVIDER_ENV_FILE.encode(), expected_new_service)
            SCRIPT = old_script
            installed_a = self.invoke("install", config_a, self.archive, self.identity)
            self.assertEqual(installed_a.returncode, 0, installed_a.stderr)
            state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
            receipt_path = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
            state = self.assert_terminal_far_side(
                state_path, release_a, None, config_a, self.runtime_config, "install", None,
                expected_service_unit=expected_old_service,
                expected_slice_unit=expected_old_slice)
            self.assertEqual(state["current"]["deployment_tool_sha256"], digest(old_script.read_bytes())["sha256"])
            old_receipt_bytes = receipt_path.read_bytes()
            self.assertEqual(len(old_receipt_bytes.splitlines()), 1)
            old_release_snapshot = self.external_snapshot(release_a)

            SCRIPT = current_script
            installed_b = self.invoke("install", config_a, self.archive, self.identity)
            self.assertEqual(installed_b.returncode, 0, installed_b.stderr)
            state = self.assert_terminal_far_side(
                state_path, release_b, release_a, config_a, self.runtime_config, "install", None,
                expected_previous_config=config_a,
                expected_previous_runtime=self.runtime_config,
                expected_service_unit=expected_new_service,
                expected_slice_unit=expected_new_slice,
                expected_previous_service_unit=expected_old_service,
                expected_previous_slice_unit=expected_old_slice)
            self.assertEqual(state["current"]["deployment_tool_sha256"], digest(current_script.read_bytes())["sha256"])
            new_receipt_bytes = receipt_path.read_bytes()
            self.assertEqual(len(new_receipt_bytes.splitlines()), 2)
            self.assertTrue(new_receipt_bytes.startswith(old_receipt_bytes))
            self.assertEqual(self.external_snapshot(release_a), old_release_snapshot)

            rolled_back = self.invoke("rollback", config_a)
            self.assertEqual(rolled_back.returncode, 0, rolled_back.stderr)
            state = self.assert_terminal_far_side(
                state_path, release_a, release_b, config_a, self.runtime_config, "rollback", None,
                expected_previous_config=config_a,
                expected_previous_runtime=self.runtime_config,
                expected_service_unit=expected_old_service,
                expected_slice_unit=expected_old_slice,
                expected_previous_service_unit=expected_new_service,
                expected_previous_slice_unit=expected_new_slice)
            self.assertEqual(self.external_snapshot(release_a), old_release_snapshot)
            rollback_receipt_bytes = receipt_path.read_bytes()
            self.assertEqual(len(rollback_receipt_bytes.splitlines()), 3)
            self.assertTrue(rollback_receipt_bytes.startswith(new_receipt_bytes))
            self.assertEqual(self.archive.read_bytes(), archive_bytes)
            self.assertEqual(self.identity.read_bytes(), identity_bytes)
            self.assertEqual(config_a.read_bytes(), config_bytes)
            self.assertEqual(self.runtime_config.read_bytes(), runtime_bytes)
        finally:
            SCRIPT = current_script

    def test_stage_creates_disabled_revision_with_fail_closed_unit(self):
        runtime = self.runtime("a", enabled=False)
        config = self.config_for_runtime(runtime, active=False)
        result = self.invoke("stage", config, self.archive, self.identity, runtime=runtime)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout.splitlines()[-1])
        release = Path(output["release"])
        self.assertNotEqual(release.name, digest(self.archive.read_bytes())["sha256"])
        self.assertEqual((release / "runtime.toml").read_bytes(), runtime.read_bytes())
        self.assertEqual((release / "operator-config.json").read_bytes(), config.read_bytes())
        unit = (self.target / "etc/systemd/system/lmdj-pr-agent.service").read_text()
        self.assertIn("ExecStart=/usr/bin/false", unit)
        self.assertNotIn("ExecStart=/usr/bin/flock", unit)

    def test_stage_rejects_any_enabled_provider_without_target_effects(self):
        runtime = self.runtime("enabled", enabled=True)
        config = self.config_for_runtime(runtime, active=False)
        result = self.invoke("stage", config, self.archive, self.identity, runtime=runtime)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("provider is enabled", result.stderr)
        self.assertEqual(list(self.target.rglob("*")), [])

    def test_stage_requires_strict_boolean_admission_fields(self):
        runtime = self.runtime("typed", enabled=False)
        config = self.config_for_runtime(runtime, active=False)
        document = json.loads(config.read_text())
        document["admission"]["operator_access"] = "true"
        config.write_text(json.dumps(document) + "\n")
        result = self.invoke("stage", config, self.archive, self.identity, runtime=runtime)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("strict booleans", result.stderr)
        self.assertEqual(list(self.target.rglob("*")), [])

    def test_stage_requires_complete_runtime_binding_before_effects(self):
        runtime = self.runtime("binding", enabled=False)
        for sha256_value, byte_length in ((None, None), (digest(runtime.read_bytes())["sha256"], None), (None, runtime.stat().st_size)):
            with self.subTest(sha256=sha256_value, byte_length=byte_length):
                config = self.config_for_runtime(runtime, active=False)
                document = json.loads(config.read_text())
                document["runtime_config"].update(sha256=sha256_value, byte_length=byte_length)
                config.write_text(json.dumps(document) + "\n")
                result = self.invoke("stage", config, self.archive, self.identity, runtime=runtime)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("non-null SHA-256 and byte length", result.stderr)
                self.assertEqual(list(self.target.rglob("*")), [])

    def test_changed_path_install_authenticates_old_owner_and_parent(self):
        runtime_a = self.runtime("owner-a", enabled=False)
        config_a = self.config_for_runtime(runtime_a, active=False, suffix="old-owner")
        self.assertEqual(self.invoke("stage", config_a, self.archive, self.identity, runtime=runtime_a).returncode, 0)
        old_path = self.target_path(json.loads(config_a.read_text())["paths"]["operator_config"])
        runtime_b = self.runtime("owner-b", enabled=True)
        config_b = self.config_for_runtime(runtime_b, active=True, suffix="new-owner")
        before = self.target_snapshot()
        result = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b,
                             overrides={str(old_path): {"uid": os.getuid() + 1, "gid": os.getgid()}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("recorded operator config owner or mode", result.stderr)
        self.assertEqual(self.target_snapshot(), before)

    def test_changed_path_install_rejects_unsafe_retained_parent(self):
        runtime_a = self.runtime("parent-a", enabled=False)
        config_a = self.config_for_runtime(runtime_a, active=False, suffix="parent-old")
        self.assertEqual(self.invoke("stage", config_a, self.archive, self.identity, runtime=runtime_a).returncode, 0)
        runtime_b = self.runtime("parent-b", enabled=True)
        config_b = self.config_for_runtime(runtime_b, active=True, suffix="parent-new")
        self.assertEqual(self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b).returncode, 0)
        old_path = self.target_path(json.loads(config_a.read_text())["paths"]["operator_config"])
        old_path.parent.chmod(0o777)
        runtime_c = self.runtime("parent-c", enabled=True)
        config_c = self.config_for_runtime(runtime_c, active=True, suffix="parent-new")
        before = self.target_snapshot()
        result = self.invoke("install", config_c, self.archive, self.identity, runtime=runtime_c)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("operator inventory parent is group/world writable", result.stderr)
        self.assertEqual(self.target_snapshot(), before)

    def test_distinct_operator_and_service_identities_survive_all_transitions(self):
        actual = {"uid": os.getuid(), "gid": os.getgid()}
        operator = {"uid": actual["uid"] + 1, "gid": actual["gid"] + 1}
        config_a = self.config(active=True)
        document = json.loads(config_a.read_text())
        overrides: dict[str, dict[str, int]] = {}
        for value in document["paths"].values():
            path = self.target_path(value)
            while True:
                overrides[str(path)] = operator
                if path == self.target.resolve():
                    break
                path = path.parent
        runtime_a = self.runtime("distinct-a", enabled=True)
        config_a = self.config_for_runtime(runtime_a, active=True)
        overrides[str(config_a)] = operator
        overrides[str(runtime_a)] = {"uid": operator["uid"], "gid": actual["gid"]}
        overrides[str(self.target_path(json.loads(config_a.read_text())["paths"]["runtime_config"]))] = {
            "uid": operator["uid"], "gid": actual["gid"]}
        operator_state_root = self.target_path(json.loads(config_a.read_text())["paths"]["operator_state_root"])
        overrides[str(operator_state_root / "control.lock")] = operator
        result = self.invoke("install", config_a, self.archive, self.identity, runtime=runtime_a,
                             overrides=overrides, operator=operator, service=actual)
        self.assertEqual(result.returncode, 0, result.stderr)
        archive_b, identity_b, members_b = make_bundle(self.directory, "distinct-b")
        self.archive, self.identity = archive_b, identity_b
        self.members = members_b
        runtime_b = self.runtime("distinct-b", enabled=True)
        config_b = self.config_for_runtime(runtime_b, active=True, suffix="distinct-b")
        overrides[str(config_b)] = operator
        overrides[str(runtime_b)] = {"uid": operator["uid"], "gid": actual["gid"]}
        overrides[str(self.target_path(json.loads(config_b.read_text())["paths"]["operator_config"]))] = operator
        result = self.invoke("install", config_b, archive_b, identity_b, runtime=runtime_b,
                             overrides=overrides, operator=operator, service=actual)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.invoke("rollback", config_b, overrides=overrides, operator=operator, service=actual)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_install_rejects_foreign_current_pointer_before_repair(self):
        config_a = self.config(active=True)
        self.assertEqual(self.invoke("install", config_a, self.archive, self.identity).returncode, 0)
        current = self.target / "var/lib/lmdj/pr-agent/current"
        current.unlink()
        current.symlink_to(self.directory / "foreign-release")
        runtime_b = self.runtime("pointer-b", enabled=True)
        config_b = self.config_for_runtime(runtime_b, active=True, suffix="pointer-b")
        before = self.target_snapshot()
        result = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pointer does not equal authenticated state", result.stderr)
        self.assertEqual(self.target_snapshot(), before)

    def test_state_rejects_extra_previous_member_identity_before_repeat(self):
        config_a = self.config(active=True)
        self.assertEqual(self.invoke("install", config_a, self.archive, self.identity).returncode, 0)
        archive_b, identity_b, members_b = make_bundle(self.directory, "previous-extra")
        self.members = members_b
        config_b = self.config(archive_b, identity_b, active=True, config_suffix="previous-extra")
        self.assertEqual(self.invoke("install", config_b, archive_b, identity_b).returncode, 0)
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        state = json.loads(state_path.read_text())
        state["previous"]["member_identities"]["unexpected"] = {"path": "invented", "sha256": "0" * 64, "byte_length": 1}
        state_path.write_text(json.dumps(state) + "\n")
        before = self.target_snapshot()
        result = self.invoke("install", config_b, archive_b, identity_b)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("previous record is not a closed", result.stderr)
        self.assertEqual(self.target_snapshot(), before)

    def test_same_bundle_revision_journey_stage_install_rollback_reinstall(self):
        runtime_a = self.runtime("a", enabled=False)
        config_a = self.config_for_runtime(runtime_a, active=False)
        staged = self.invoke("stage", config_a, self.archive, self.identity, runtime=runtime_a)
        self.assertEqual(staged.returncode, 0, staged.stderr)
        revision_a = Path(json.loads(staged.stdout.splitlines()[-1])["release"])
        operator_a = config_a.read_bytes()
        unit_path = self.target / "etc/systemd/system/lmdj-pr-agent.service"
        slice_path = self.target / "etc/systemd/system/lmdj-pr-review.slice"
        unit_a = unit_path.read_bytes()
        slice_a = slice_path.read_bytes()
        ledger = self.target / "var/lib/lmdj/pr-agent/engine-state/ledger.jsonl"
        uncertain_ledger = b'{"schema":"lmdj.pr-agent-ledger.v1","status":"uncertain","request_id":"same-bundle-journey"}\n'
        ledger.write_bytes(uncertain_ledger)
        self.assertIn(b"ExecStart=/usr/bin/false\n", unit_a)
        self.assert_revision_far_side(config_a, runtime_a, revision_a, operator_a, unit_a, slice_a, uncertain_ledger)
        runtime_b = self.runtime("b", enabled=True)
        config_b = self.config_for_runtime(runtime_b, active=True)
        installed = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        revision_b = Path(json.loads(installed.stdout.splitlines()[-1])["release"])
        self.assertNotEqual(revision_a, revision_b)
        operator_b = config_b.read_bytes()
        unit_b = unit_path.read_bytes()
        slice_b = slice_path.read_bytes()
        self.assert_revision_far_side(config_b, runtime_b, revision_b, operator_b, unit_b, slice_b, uncertain_ledger)
        self.assertEqual((revision_a / "runtime.toml").read_bytes(), runtime_a.read_bytes())
        self.assertEqual((revision_b / "runtime.toml").read_bytes(), runtime_b.read_bytes())
        rollback = self.invoke("rollback", config_b)
        self.assertEqual(rollback.returncode, 0, rollback.stderr)
        self.assert_revision_far_side(config_a, runtime_a, revision_a, operator_a, unit_a, slice_a, uncertain_ledger)
        state = json.loads((self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json").read_text())
        self.assertEqual(state["current"]["release"], str(revision_a))
        self.assertEqual(state["previous"]["release"], str(revision_b))
        repeat = self.invoke("rollback", config_b)
        self.assertEqual(repeat.returncode, 0, repeat.stderr)
        self.assertIn('"status": "idempotent"', repeat.stdout)
        self.assert_revision_far_side(config_a, runtime_a, revision_a, operator_a, unit_a, slice_a, uncertain_ledger)
        reinstated = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b)
        self.assertEqual(reinstated.returncode, 0, reinstated.stderr)
        self.assert_revision_far_side(config_b, runtime_b, revision_b, operator_b, unit_b, slice_b, uncertain_ledger)
        self.assertEqual((revision_a / "runtime.toml").read_bytes(), runtime_a.read_bytes())
        receipts = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        self.assertEqual(len(receipts.read_text().splitlines()), 4)

    def test_concurrent_control_mutation_is_rejected_by_operator_lock(self):
        runtime_a = self.runtime("lock-a", enabled=False)
        config_a = self.config_for_runtime(runtime_a, active=False)
        staged = self.invoke("stage", config_a, self.archive, self.identity, runtime=runtime_a)
        self.assertEqual(staged.returncode, 0, staged.stderr)
        lock_path = self.target / "var/lib/lmdj/pr-agent/operator-state/control.lock"
        with lock_path.open("r+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            runtime_b = self.runtime("lock-b", enabled=True)
            config_b = self.config_for_runtime(runtime_b, active=True)
            before = self.target_snapshot()
            result = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("another deployment control transition", result.stderr)
            self.assertEqual(self.target_snapshot(), before)
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

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
        self.assertEqual((release / "service.unit").read_bytes(), unit.encode())
        self.assertEqual((release / "slice.unit").read_bytes(), (self.target / "etc/systemd/system/lmdj-pr-review.slice").read_bytes())
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
        self.assertIn("incomplete v3 shape", result.stderr)
        self.assertEqual(state_path.read_bytes(), corrupt)
        self.assertFalse((self.target / "etc/systemd/system/lmdj-pr-agent.service").exists())

    def test_legacy_v2_state_is_refused_without_target_effects(self):
        runtime = self.runtime("legacy", enabled=False)
        config = self.config_for_runtime(runtime, active=False)
        staged = self.invoke("stage", config, self.archive, self.identity, runtime=runtime)
        self.assertEqual(staged.returncode, 0, staged.stderr)
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        original = state_path.read_bytes()
        legacy = json.loads(original)
        legacy["schema"] = "lmdj-pr-agent-runtime-state.v2"
        state_path.write_text(json.dumps(legacy, sort_keys=True, indent=2) + "\n")
        before = self.target_snapshot()
        result = self.invoke("stage", config, self.archive, self.identity, runtime=runtime)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("legacy v2 deployment state is unsupported", result.stderr)
        self.assertEqual(self.target_snapshot(), before)

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
        completed_current = copy.deepcopy(state["current"])
        state["current"] = copy.deepcopy(state["previous"])
        state["previous"] = None
        state["latest_transition"] = receipt_records[0]
        state["transition"] = {"action": "install", "from": copy.deepcopy(state["current"]),
                                "to": completed_current, "previous": copy.deepcopy(state["current"]),
                                "receipt": second_receipt}
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
        state["latest_transition"] = receipt_records[0]
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

    def test_interrupted_transition_accepts_duplicate_identical_receipt_once(self):
        first_config = self.config(active=True)
        self.assertEqual(self.invoke("install", first_config, self.archive, self.identity).returncode, 0)
        archive_two, identity_two, members_two = make_bundle(self.directory, "duplicate-identical")
        self.members = members_two
        second_config = self.config(archive_two, identity_two, active=True, config_suffix="duplicate-identical")
        self.assertEqual(self.invoke("install", second_config, archive_two, identity_two).returncode, 0)
        receipts = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        records = [json.loads(line) for line in receipts.read_text().splitlines()]
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        completed = json.loads(state_path.read_text())
        pending = {**completed, "current": completed["previous"], "previous": None,
                   "latest_transition": records[0],
                   "transition": {"action": "install", "from": completed["previous"],
                                  "to": completed["current"], "previous": completed["previous"],
                                  "receipt": records[-1]}}
        receipts.write_text("\n".join(json.dumps(record, sort_keys=True, separators=(",", ":"))
                            for record in (*records, records[-1])) + "\n")
        state_path.write_text(json.dumps(pending, sort_keys=True, indent=2) + "\n")
        retry = self.invoke("install", second_config, archive_two, identity_two)
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertEqual(len(receipts.read_text().splitlines()), 3)
        self.assertNotIn("transition", json.loads(state_path.read_text()))

    def test_interrupted_mixed_external_effects_refuse_read_only(self):
        runtime_a = self.runtime("mixed-a", enabled=True)
        config_a = self.config_for_runtime(runtime_a, active=True)
        self.assertEqual(self.invoke("install", config_a, self.archive, self.identity, runtime=runtime_a).returncode, 0)
        unit_path = self.target / "etc/systemd/system/lmdj-pr-agent.service"
        slice_path = self.target / "etc/systemd/system/lmdj-pr-review.slice"
        unit_a = unit_path.read_bytes()
        slice_a = slice_path.read_bytes()
        runtime_b = self.runtime("mixed-b", enabled=True)
        runtime_b.chmod(0o640)
        runtime_b.write_bytes(b"[providers.deepseek]\nenabled=true\nmodel='mixed-b'\n")
        runtime_b.chmod(0o440)
        config_b = self.config_for_runtime(runtime_b, active=True)
        self.assertEqual(self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b).returncode, 0)
        unit_b = unit_path.read_bytes()
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        completed = json.loads(state_path.read_text())
        record_a = completed["previous"]
        record_b = completed["current"]
        receipts = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        records = [json.loads(line) for line in receipts.read_text().splitlines()]
        receipt_b = json.loads(receipts.read_text().splitlines()[-1])
        pending = {**completed, "current": record_a, "previous": None}
        pending["latest_transition"] = records[0]
        pending["transition"] = {"action": "install", "from": record_a, "to": record_b,
                                  "previous": record_a, "receipt": receipt_b}
        state_path.write_text(json.dumps(pending, sort_keys=True, indent=2) + "\n")
        current = self.target / "var/lib/lmdj/pr-agent/current"
        current.unlink()
        current.symlink_to(record_a["release"])
        operator_path = self.target / "etc/lmdj/pr-agent/netcup-review.json"
        runtime_path = self.target / "etc/lmdj/pr-agent/runtime.toml"
        operator_path.write_bytes(config_b.read_bytes())
        runtime_path.chmod(0o640)
        runtime_path.write_bytes(runtime_a.read_bytes())
        runtime_path.chmod(0o440)
        unit_path.write_bytes(unit_b)
        slice_path.write_bytes(slice_a)
        before = self.target_snapshot()
        retry = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b)
        self.assertNotEqual(retry.returncode, 0)
        self.assertIn("durable but incomplete", retry.stderr)
        self.assertEqual(self.target_snapshot(), before)

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
            "schema": "lmdj.pr-agent-deployment-receipt.v3", "action": "rollback", "status": "staged",
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
                self.assertTrue(any(fragment in retry.stderr for fragment in (
                    "transition ID", "trusted inventory", "retained release", "initial install")))
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

    def test_same_archive_changed_runtime_creates_distinct_revision(self):
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
        before_release = (self.target / "var/lib/lmdj/pr-agent/current").resolve()
        result = subprocess.run([str(SCRIPT), "install", "--config", str(changed_path), "--bundle", str(self.archive),
                                 "--identity", str(self.identity), "--runtime-config", str(changed),
                                 "--target-root", str(self.target)], text=True, capture_output=True, check=False,
                                env=self.fixture_env())
        self.assertEqual(result.returncode, 0, result.stderr)
        after_release = (self.target / "var/lib/lmdj/pr-agent/current").resolve()
        self.assertNotEqual(after_release, before_release)
        self.assertEqual((after_release / "runtime.toml").read_bytes(), changed.read_bytes())
        self.assertTrue(before_release.is_dir())

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
        receipt_path = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        with monetary_ledger.open("a") as handle:
            handle.write(json.dumps({"status": "uncertain", "request_id": "keep-me"}) + "\n")
        monetary_ledger_before = monetary_ledger.read_bytes()
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
        self.assertEqual(monetary_ledger.read_bytes(), monetary_ledger_before)
        lines = monetary_ledger.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["status"], "reserved")
        self.assertEqual(json.loads(lines[1])["status"], "uncertain")
        receipt_lines = receipt_path.read_text().splitlines()
        self.assertTrue(any('"action":"rollback"' in line for line in receipt_lines))
        self.assertTrue((self.target / "var/lib/lmdj/pr-agent/releases").is_dir())

        repeated = self.invoke("rollback", second_config)
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertIn('"status": "idempotent"', repeated.stdout)
        self.assertEqual(current.resolve(), first_release)
        self.assertEqual(unit_path.read_text(), first_unit)
        self.assertEqual(monetary_ledger.read_bytes(), monetary_ledger_before)

        reinstated = self.invoke("install", second_config, archive_two, identity_two)
        self.assertEqual(reinstated.returncode, 0, reinstated.stderr)
        self.assertEqual(current.resolve(), second_release)
        self.assertEqual(unit_path.read_text(), second_unit)
        self.assertEqual(monetary_ledger.read_bytes(), monetary_ledger_before)
        receipt_records = [json.loads(line) for line in receipt_path.read_text().splitlines()]
        transition_ids = [record["transition_id"] for record in receipt_records if "transition_id" in record]
        self.assertEqual(len(transition_ids), 4)
        self.assertEqual(len(transition_ids), len(set(transition_ids)))

    def test_rollback_rejects_forged_latest_transition_witness_read_only(self):
        config = self.config(active=True)
        self.assertEqual(self.invoke("install", config, self.archive, self.identity).returncode, 0)
        archive_two, identity_two, members_two = make_bundle(self.directory, "witness-two")
        self.members = members_two
        config_two = self.config(archive_two, identity_two, active=True, config_suffix="witness-two")
        self.assertEqual(self.invoke("install", config_two, archive_two, identity_two).returncode, 0)
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        state = json.loads(state_path.read_text())
        state["latest_transition"]["transition_id"] = "forged"
        state_path.write_text(json.dumps(state) + "\n")
        before = self.target_snapshot()
        result = self.invoke("rollback", config_two)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("latest transition witness", result.stderr)
        self.assertEqual(self.target_snapshot(), before)

    def test_established_state_rejects_missing_latest_transition_witness(self):
        config = self.config(active=True)
        self.assertEqual(self.invoke("install", config, self.archive, self.identity).returncode, 0)
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        state = json.loads(state_path.read_text())
        state["latest_transition"] = None
        state_path.write_text(json.dumps(state) + "\n")
        before = self.target_snapshot()
        result = self.invoke("install", config, self.archive, self.identity)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing the latest transition witness", result.stderr)
        self.assertEqual(self.target_snapshot(), before)

    def test_established_state_rejects_stale_historical_latest_witness_read_only(self):
        config_a = self.config(active=True)
        self.assertEqual(self.invoke("install", config_a, self.archive, self.identity).returncode, 0)
        runtime_b = self.runtime("stale-witness-b", enabled=True)
        config_b = self.config_for_runtime(runtime_b, active=True)
        self.assertEqual(self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b).returncode, 0)
        self.assertEqual(self.invoke("rollback", config_b).returncode, 0)
        self.assertEqual(self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b).returncode, 0)
        self.assertEqual(self.invoke("rollback", config_b).returncode, 0)
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        receipts = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        state = json.loads(state_path.read_text())
        records = [json.loads(line) for line in receipts.read_text().splitlines()]
        rollbacks = [record for record in records if record["action"] == "rollback"]
        self.assertEqual(len(rollbacks), 2)
        state["latest_transition"] = rollbacks[0]
        state_path.write_text(json.dumps(state) + "\n")
        before = self.target_snapshot()
        result = self.invoke("rollback", config_b)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("actual latest durable receipt", result.stderr)
        self.assertEqual(self.target_snapshot(), before)

    def test_install_rejects_forged_latest_witness_read_only(self):
        config = self.config(active=True)
        self.assertEqual(self.invoke("install", config, self.archive, self.identity).returncode, 0)
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        state = json.loads(state_path.read_text())
        state["latest_transition"]["transition_id"] = "not-in-receipts"
        state_path.write_text(json.dumps(state) + "\n")
        before = self.target_snapshot()
        result = self.invoke("install", config, self.archive, self.identity)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("actual latest durable receipt", result.stderr)
        self.assertEqual(self.target_snapshot(), before)

    def test_pending_state_rejects_latest_witness_absent_from_receipts(self):
        config_a = self.config(active=True)
        self.assertEqual(self.invoke("install", config_a, self.archive, self.identity).returncode, 0)
        archive_b, identity_b, members_b = make_bundle(self.directory, "pending-witness")
        self.members = members_b
        config_b = self.config(archive_b, identity_b, active=True, config_suffix="pending-witness")
        self.assertEqual(self.invoke("install", config_b, archive_b, identity_b).returncode, 0)
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        receipts = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        state = json.loads(state_path.read_text())
        records = [json.loads(line) for line in receipts.read_text().splitlines()]
        state["transition"] = {"action": "install", "from": state["previous"], "to": state["current"],
                                "previous": state["previous"], "receipt": records[-1]}
        state["latest_transition"] = {**records[-1], "transition_id": "not-in-receipts"}
        state_path.write_text(json.dumps(state) + "\n")
        before = self.target_snapshot()
        result = self.invoke("install", config_b, archive_b, identity_b)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("latest transition", result.stderr)
        self.assertEqual(self.target_snapshot(), before)

    def test_pending_recovery_authenticates_previous_before_receipt_mutation(self):
        config_a = self.config(active=True)
        self.assertEqual(self.invoke("install", config_a, self.archive, self.identity).returncode, 0)
        archive_b, identity_b, members_b = make_bundle(self.directory, "pending-previous")
        self.members = members_b
        config_b = self.config(archive_b, identity_b, active=True, config_suffix="pending-previous")
        self.assertEqual(self.invoke("install", config_b, archive_b, identity_b).returncode, 0)
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        receipts = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        state = json.loads(state_path.read_text())
        records = [json.loads(line) for line in receipts.read_text().splitlines()]
        state["transition"] = {"action": "install", "from": copy.deepcopy(state["previous"]),
                                "to": copy.deepcopy(state["current"]), "previous": copy.deepcopy(state["previous"]),
                                "receipt": copy.deepcopy(records[-1])}
        state["latest_transition"] = records[0]
        receipts.write_text(json.dumps(records[0], sort_keys=True, separators=(",", ":")) + "\n")
        state["previous"]["member_identities"]["adapter"]["byte_length"] += 1
        state["transition"]["from"] = copy.deepcopy(state["previous"])
        state["transition"]["previous"] = copy.deepcopy(state["previous"])
        state_path.write_text(json.dumps(state) + "\n")
        state_before, receipts_before = state_path.read_bytes(), receipts.read_bytes()
        before = self.target_snapshot()
        result = self.invoke("install", config_b, archive_b, identity_b)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(state_path.read_bytes(), state_before)
        self.assertEqual(receipts.read_bytes(), receipts_before)
        self.assertEqual(self.target_snapshot(), before)

    def test_pending_recovery_requires_exact_final_base_witness_read_only(self):
        _, _, _, config_b, state_path, receipt_path, pending, _ = self._prepare_pending_rollback_far_side()
        records = [json.loads(line) for line in receipt_path.read_text().splitlines()]
        pending["latest_transition"] = records[0]
        state_path.write_text(json.dumps(pending) + "\n")
        before = self.target_snapshot()
        receipt_before = receipt_path.read_bytes()
        result = self.invoke("rollback", config_b)
        self._assert_unchanged_failure(result, before, "exact final base-history receipt")
        self.assertEqual(receipt_path.read_bytes(), receipt_before)

    def test_initial_stage_and_install_receipt_crashes_recover_once(self):
        wrapper = self.directory / "initial-crash-python"
        wrapper.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "real_replace = os.replace\n"
            "def replace(source, destination):\n"
            "    if str(destination).endswith('/runtime.json') and 'transition' not in json.load(open(source)):\n"
            "        os._exit(73)\n"
            "    return real_replace(source, destination)\n"
            "os.replace = replace\n"
            "sys.argv = sys.argv[1:]\n"
            "exec(compile(sys.stdin.read(), '<deploy-runner>', 'exec'), {'__name__':'__main__'})\n")
        wrapper.chmod(0o755)
        for mode, active in (("stage", False), ("install", True)):
            with self.subTest(mode=mode):
                shutil.rmtree(self.target)
                self.target.mkdir()
                runtime = self.runtime("initial-" + mode, enabled=active)
                config = self.config_for_runtime(runtime, active=active)
                crashed = self.invoke(mode, config, self.archive, self.identity, runtime=runtime, python_bin=wrapper)
                self.assertEqual(crashed.returncode, 73, crashed.stderr)
                state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
                receipt_path = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
                pending = json.loads(state_path.read_text())
                self.assertIsNone(pending["latest_transition"])
                self.assertIsNone(pending["transition"]["from"])
                self.assertEqual(json.loads(receipt_path.read_text().splitlines()[-1]), pending["transition"]["receipt"])
                receipts_before = receipt_path.read_bytes()
                retried = self.invoke(mode, config, self.archive, self.identity, runtime=runtime)
                self.assertEqual(retried.returncode, 0, retried.stderr)
                self.assertEqual(receipt_path.read_bytes(), receipts_before)
                final = json.loads(state_path.read_text())
                self.assertNotIn("transition", final)
                self.assertEqual(final["current"], pending["transition"]["to"])
                self.assertIsNone(final["previous"])

    def test_pending_rollback_authenticates_far_side_operator_mode_read_only(self):
        runtime_a = self.runtime("pending-rollback-a", enabled=False)
        config_a = self.config_for_runtime(runtime_a, active=False, suffix="pending-rollback-old")
        self.assertEqual(self.invoke("stage", config_a, self.archive, self.identity, runtime=runtime_a).returncode, 0)
        runtime_b = self.runtime("pending-rollback-b", enabled=True)
        config_b = self.config_for_runtime(runtime_b, active=True, suffix="pending-rollback-new")
        self.assertEqual(self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b).returncode, 0)
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        receipts = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        state_before_rollback = json.loads(state_path.read_text())
        records = [json.loads(line) for line in receipts.read_text().splitlines()]
        state = json.loads(state_path.read_text())
        rollback_receipt = {"schema": "lmdj.pr-agent-deployment-receipt.v3", "action": "rollback",
                            "status": "staged", "transition_id": "pending-rollback-mode",
                            "from_release": state["current"]["release"],
                            "to_release": state["previous"]["release"],
                            "from_record_sha256": hashlib.sha256((Path(state["current"]["release"]) / "REVISION_RECORD.json").read_bytes()).hexdigest(),
                            "from_record_byte_length": (Path(state["current"]["release"]) / "REVISION_RECORD.json").stat().st_size,
                            "to_record_sha256": hashlib.sha256((Path(state["previous"]["release"]) / "REVISION_RECORD.json").read_bytes()).hexdigest(),
                            "to_record_byte_length": (Path(state["previous"]["release"]) / "REVISION_RECORD.json").stat().st_size,
                            "target": copy.deepcopy(records[-1]["target"])}
        state["transition"] = {"action": "rollback", "from": copy.deepcopy(state["current"]),
                                "to": copy.deepcopy(state["previous"]), "previous": copy.deepcopy(state["current"]),
                                "receipt": rollback_receipt}
        state["latest_transition"] = state_before_rollback["latest_transition"]
        state_path.write_text(json.dumps(state) + "\n")
        old_operator = Path(state["previous"]["operator_config_path"])
        old_operator.chmod(0o666)
        state_before, receipts_before = state_path.read_bytes(), receipts.read_bytes()
        before = self.target_snapshot()
        result = self.invoke("rollback", config_b)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("recorded operator config owner or mode", result.stderr)
        self.assertEqual(state_path.read_bytes(), state_before)
        self.assertEqual(receipts.read_bytes(), receipts_before)
        self.assertEqual(self.target_snapshot(), before)

    def test_pending_install_receipt_endpoints_are_bound_read_only(self):
        config_a = self.config(active=True)
        self.assertEqual(self.invoke("install", config_a, self.archive, self.identity).returncode, 0)
        archive_b, identity_b, members_b = make_bundle(self.directory, "pending-endpoint")
        self.members = members_b
        config_b = self.config(archive_b, identity_b, active=True, config_suffix="pending-endpoint")
        self.assertEqual(self.invoke("install", config_b, archive_b, identity_b).returncode, 0)
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        receipts = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        completed = json.loads(state_path.read_text())
        records = [json.loads(line) for line in receipts.read_text().splitlines()]
        pending = {**completed, "transition": {"action": "install", "from": completed["previous"],
                    "to": completed["current"], "previous": completed["previous"], "receipt": records[-1]},
                   "latest_transition": records[0]}
        receipts_before = json.dumps(records[0], sort_keys=True, separators=(",", ":")) + "\n"
        for endpoint in ("from_release", "to_release"):
            with self.subTest(endpoint=endpoint):
                state = copy.deepcopy(pending)
                state["transition"]["receipt"][endpoint] = "/forged-release"
                state_path.write_text(json.dumps(state) + "\n")
                receipts.write_text(receipts_before)
                state_before, receipt_before = state_path.read_bytes(), receipts.read_bytes()
                before = self.target_snapshot()
                result = self.invoke("install", config_b, archive_b, identity_b)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(state_path.read_bytes(), state_before)
                self.assertEqual(receipts.read_bytes(), receipt_before)
                self.assertEqual(self.target_snapshot(), before)

    def test_install_rejects_current_intermediate_alias_read_only(self):
        config = self.config(active=True)
        self.assertEqual(self.invoke("install", config, self.archive, self.identity).returncode, 0)
        current = self.target / "var/lib/lmdj/pr-agent/current"
        release = current.resolve()
        alias = self.directory / "unrecorded-alias"
        alias.symlink_to(release)
        current.unlink()
        current.symlink_to(alias)
        before = self.target_snapshot()
        result = self.invoke("install", config, self.archive, self.identity)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pointer does not equal authenticated state", result.stderr)
        self.assertEqual(self.target_snapshot(), before)

    def test_persistent_helper_flushes_file_before_rename_and_directory_after(self):
        wrapper = self.directory / "trace-python"
        wrapper.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, stat, sys\n"
            "trace = os.environ['PR_AGENT_TRACE_PATH']\n"
            "real_fsync, real_replace = os.fsync, os.replace\n"
            "def identity(value):\n"
            "    return [value.st_dev, value.st_ino, value.st_mode & 0o777, value.st_uid, value.st_gid]\n"
            "def record(value):\n"
            "    with open(trace, 'a', encoding='utf-8') as handle: handle.write(json.dumps(value) + '\\n')\n"
            "def fsync(fd):\n"
            "    value = os.fstat(fd); record({'event': 'fsync', 'dir': stat.S_ISDIR(value.st_mode), 'identity': identity(value)}); return real_fsync(fd)\n"
            "def replace(source, destination):\n"
            "    record({'event': 'replace', 'source': identity(os.stat(source)), 'parent': identity(os.stat(os.path.dirname(destination))), 'destination': str(destination)}); return real_replace(source, destination)\n"
            "os.fsync, os.replace = fsync, replace\n"
            "sys.argv = sys.argv[1:]\n"
            "code = sys.stdin.read()\n"
            "exec(compile(code, '<deploy-runner>', 'exec'), {'__name__': '__main__'})\n")
        wrapper.chmod(0o755)
        trace = self.directory / "fsync-trace.log"
        runtime_a = self.runtime("trace-a", enabled=False)
        config_a = self.config_for_runtime(runtime_a, active=False, suffix="trace-old")
        staged = self.invoke("stage", config_a, self.archive, self.identity, runtime=runtime_a,
                             python_bin=wrapper, trace_path=trace)
        self.assertEqual(staged.returncode, 0, staged.stderr)
        runtime_b = self.runtime("trace-b", enabled=True)
        config_b = self.config_for_runtime(runtime_b, active=True, suffix="trace-new")
        trace.write_text("")
        installed = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b,
                                python_bin=wrapper, trace_path=trace)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        events = [json.loads(line) for line in trace.read_text().splitlines()]
        old_index = next(index for index, event in enumerate(events)
                         if event.get("event") == "replace" and event["destination"].endswith("netcup-review-trace-new.json"))
        self.assertEqual(events[old_index - 1]["event"], "fsync")
        self.assertFalse(events[old_index - 1]["dir"])
        self.assertEqual(events[old_index - 1]["identity"], events[old_index]["source"])
        self.assertEqual(events[old_index]["source"][2], 0o600)
        self.assertEqual(events[old_index + 1]["event"], "fsync")
        self.assertTrue(events[old_index + 1]["dir"])
        self.assertEqual(events[old_index + 1]["identity"], events[old_index]["parent"])
        old_path = self.target_path(json.loads(config_a.read_text())["paths"]["operator_config"])
        old_path.unlink()
        trace.write_text("")
        rolled = self.invoke("rollback", config_b, python_bin=wrapper, trace_path=trace)
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        events = [json.loads(line) for line in trace.read_text().splitlines()]
        new_index = next(index for index, event in enumerate(events)
                         if event.get("event") == "replace" and event["destination"].endswith("netcup-review-trace-old.json"))
        self.assertEqual(events[new_index - 1]["event"], "fsync")
        self.assertFalse(events[new_index - 1]["dir"])
        self.assertEqual(events[new_index - 1]["identity"], events[new_index]["source"])
        self.assertEqual(events[new_index]["source"][2], 0o600)
        self.assertEqual(events[new_index + 1]["event"], "fsync")
        self.assertTrue(events[new_index + 1]["dir"])
        self.assertEqual(events[new_index + 1]["identity"], events[new_index]["parent"])

    def test_n1_port_actual_writer_crash_after_receipt_before_state_publish(self):
        _, _, _, config_b, state_path, receipt_path, _, state_b, _ = self._novel_setup()
        wrapper = self.directory / "crash-after-receipt-python"
        wrapper.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "real_replace = os.replace\n"
            "def replace(source, destination):\n"
            "    if str(destination).endswith('/runtime.json'):\n"
            "        if 'transition' not in json.load(open(source)):\n"
            "            os._exit(73)\n"
            "    return real_replace(source, destination)\n"
            "os.replace = replace\n"
            "sys.argv = sys.argv[1:]\n"
            "exec(compile(sys.stdin.read(), '<deploy-runner>', 'exec'), {'__name__': '__main__'})\n")
        wrapper.chmod(0o755)
        crashed = self.invoke("rollback", config_b, python_bin=wrapper)
        self.assertEqual(crashed.returncode, 73, crashed.stderr)
        pending = json.loads(state_path.read_text())
        self.assertEqual(pending["latest_transition"], state_b["latest_transition"])
        self.assertIn("transition", pending)
        receipts_before = receipt_path.read_bytes()
        self.assertEqual(json.loads(receipts_before.splitlines()[-1]), pending["transition"]["receipt"])
        retried = self.invoke("rollback", config_b)
        self.assertEqual(retried.returncode, 0, retried.stderr)
        self.assertEqual(receipt_path.read_bytes(), receipts_before)
        self.assertNotIn("transition", json.loads(state_path.read_text()))

    def test_n1_port_prospective_self_witness_is_rejected_read_only(self):
        _, _, runtime_b, config_b, state_path, receipt_path, _, state_b, _ = self._novel_setup()
        records = [json.loads(line) for line in receipt_path.read_text().splitlines()]
        prospective = copy.deepcopy(state_b)
        prospective["latest_transition"] = state_b["latest_transition"]
        prospective["transition"] = {"action": "install", "from": copy.deepcopy(state_b["previous"]),
                                      "to": copy.deepcopy(state_b["current"]), "previous": copy.deepcopy(state_b["previous"]),
                                      "receipt": copy.deepcopy(state_b["latest_transition"])}
        state_path.write_text(json.dumps(prospective) + "\n")
        receipt_path.write_text("".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                                    for record in (records[0], records[-1])))
        before = self.target_snapshot()
        result = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b)
        self._assert_unchanged_failure(result, before, "own historical witness")

    def test_n1_port_conflicting_historical_id_is_rejected_read_only(self):
        _, _, runtime_b, config_b, _, receipt_path, _, state_b, _ = self._novel_setup()
        records = [json.loads(line) for line in receipt_path.read_text().splitlines()]
        forged = {**records[0], "to_release": "/forged-release"}
        receipt_path.write_text("".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                                for record in (records[0], forged, records[-1])))
        before = self.target_snapshot()
        result = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b)
        self._assert_unchanged_failure(result, before, "conflicting transition ID")

    def test_closed_receipt_objects_without_transition_ids_are_read_only(self):
        mutations = [{"malformed": {}}, {"remove": True}, {"null": True}]
        for mutation in mutations:
            with self.subTest(malformed=mutation):
                shutil.rmtree(self.target)
                self.target.mkdir()
                for source in (self.directory / "runtime-novel-a.toml", self.directory / "runtime-novel-b.toml"):
                    if source.exists():
                        source.chmod(0o600)
                _, _, _, config_b, _, receipt_path, _, _, _ = self._novel_setup()
                if "malformed" in mutation:
                    malformed = mutation["malformed"]
                else:
                    valid = json.loads(receipt_path.read_text().splitlines()[-1])
                    malformed = copy.deepcopy(valid)
                    if "remove" in mutation:
                        malformed.pop("transition_id")
                    else:
                        malformed["transition_id"] = None
                receipt_path.write_text(receipt_path.read_text() +
                                        json.dumps(malformed, sort_keys=True, separators=(",", ":")) + "\n")
                before = self.target_snapshot()
                result = self.invoke("rollback", config_b)
                reason = ("canonical record commitments"
                          if malformed.get("schema") == "lmdj.pr-agent-deployment-receipt.v3"
                          and any(key not in malformed for key in ("from_record_sha256", "from_record_byte_length",
                                                                   "to_record_sha256", "to_record_byte_length"))
                          else "legacy, malformed, or forged transition ID")
                self._assert_unchanged_failure(result, before, reason)

    def test_n2_port_symlinked_releases_parent_is_rejected_read_only(self):
        _, _, runtime_b, config_b, _, _, _, state_b, _ = self._novel_setup()
        releases = Path(state_b["current"]["release"]).parent
        relocated = self.directory / "relocated-releases"
        releases.rename(relocated)
        releases.symlink_to(relocated)
        before = self.target_snapshot()
        result = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b)
        self._assert_unchanged_failure(result, before, "release parent is a symlink")

    def test_n2_port_retained_previous_external_mode_is_rejected_read_only(self):
        _, _, runtime_b, config_b, _, _, state_a, _, _ = self._novel_setup(distinct_paths=True)
        Path(state_a["current"]["operator_config_path"]).chmod(0o666)
        runtime_c = self.runtime("novel-c", enabled=True)
        config_c = self.config_for_runtime(runtime_c, active=True, suffix="novel-new")
        before = self.target_snapshot()
        result = self.invoke("install", config_c, self.archive, self.identity, runtime=runtime_c)
        self._assert_unchanged_failure(result, before, "recorded operator config owner or mode")

    def test_n1_port_duplicate_identical_pending_receipts_recover_without_append(self):
        _, _, runtime_b, config_b, state_path, receipt_path, _, state_b, _ = self._novel_setup()
        records = [json.loads(line) for line in receipt_path.read_text().splitlines()]
        pending = copy.deepcopy(state_b)
        pending["current"] = copy.deepcopy(state_b["previous"])
        pending["previous"] = None
        pending["latest_transition"] = records[0]
        pending["transition"] = {"action": "install", "from": copy.deepcopy(state_b["previous"]),
                                  "to": copy.deepcopy(state_b["current"]), "previous": copy.deepcopy(state_b["previous"]),
                                  "receipt": copy.deepcopy(records[-1])}
        state_path.write_text(json.dumps(pending) + "\n")
        receipt_path.write_text("".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                                    for record in (records[0], records[-1], records[-1])))
        receipts_before = receipt_path.read_bytes()
        before = self.target_snapshot()
        result = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(receipt_path.read_bytes(), receipts_before)
        self.assertNotIn("transition", json.loads(state_path.read_text()))
        self.assertNotEqual(before, self.target_snapshot())

    def test_n1_port_conflicting_retained_record_is_rejected_read_only(self):
        _, _, runtime_b, config_b, state_path, receipt_path, state_a, state_b, _ = self._novel_setup()
        pending = copy.deepcopy(state_b)
        pending["current"] = copy.deepcopy(state_a["current"])
        pending["previous"] = copy.deepcopy(state_a["current"])
        pending["previous"]["member_identities"]["adapter"]["byte_length"] += 1
        pending["latest_transition"] = copy.deepcopy(state_a["latest_transition"])
        pending["transition"] = {"action": "install", "from": copy.deepcopy(state_a["current"]),
                                  "to": copy.deepcopy(state_b["current"]), "previous": copy.deepcopy(state_a["current"]),
                                  "receipt": copy.deepcopy(state_b["latest_transition"])}
        state_path.write_text(json.dumps(pending) + "\n")
        receipt_path.write_text(json.dumps(state_a["latest_transition"], sort_keys=True, separators=(",", ":")) + "\n")
        before = self.target_snapshot()
        result = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b)
        self._assert_unchanged_failure(result, before, "retained release records conflict")

    def _prepare_pending_rollback_far_side(self):
        runtime_a, config_a, runtime_b, config_b, state_path, receipt_path, state_a, state_b, uncertain = self._novel_setup(distinct_paths=True)
        rolled = self.invoke("rollback", config_b)
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        after = json.loads(state_path.read_text())
        records = [json.loads(line) for line in receipt_path.read_text().splitlines()]
        pending = copy.deepcopy(state_b)
        pending["latest_transition"] = state_b["latest_transition"]
        pending["transition"] = {"action": "rollback", "from": copy.deepcopy(state_b["current"]),
                                  "to": copy.deepcopy(state_a["current"]), "previous": copy.deepcopy(state_b["current"]),
                                  "receipt": copy.deepcopy(after["latest_transition"])}
        state_path.write_text(json.dumps(pending) + "\n")
        receipt_path.write_text("".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                                    for record in records[:2]))
        return runtime_a, config_a, runtime_b, config_b, state_path, receipt_path, pending, uncertain

    def test_n2_port_pending_rollback_missing_far_side_file_is_read_only(self):
        _, _, _, config_b, state_path, receipt_path, pending, _ = self._prepare_pending_rollback_far_side()
        Path(pending["transition"]["to"]["operator_config_path"]).unlink()
        before = self.target_snapshot()
        result = self.invoke("rollback", config_b)
        self._assert_unchanged_failure(result, before, "target operator config")
        self.assertIn("transition", json.loads(state_path.read_text()))
        self.assertTrue(receipt_path.read_bytes())

    def test_n2_port_pending_rollback_wrong_owner_far_side_is_read_only(self):
        _, _, _, config_b, _, _, pending, _ = self._prepare_pending_rollback_far_side()
        path = Path(pending["transition"]["to"]["operator_config_path"])
        before = self.target_snapshot()
        result = self.invoke("rollback", config_b, overrides={str(path): {"uid": os.getuid() + 1, "gid": os.getgid()}})
        self._assert_unchanged_failure(result, before, "recorded operator config owner or mode")

    def test_n2_port_pending_rollback_unsafe_parent_is_read_only(self):
        _, _, _, config_b, _, _, pending, _ = self._prepare_pending_rollback_far_side()
        path = Path(pending["transition"]["to"]["operator_config_path"])
        path.parent.chmod(0o777)
        before = self.target_snapshot()
        result = self.invoke("rollback", config_b)
        self._assert_unchanged_failure(result, before, "operator inventory parent")

    def test_n1_port_six_leg_same_archive_arrival_sequence(self):
        runtime_a = self.runtime("novel-a", enabled=False)
        config_a = self.config_for_runtime(runtime_a, active=False)
        runtime_b = self.runtime("novel-b", enabled=True)
        config_b = self.config_for_runtime(runtime_b, active=True)
        release_a = self.expected_revision_path(config_a, runtime_a)
        release_b = self.expected_revision_path(config_b, runtime_b)
        service_a, slice_a = self.expected_unit_bytes(config_a, release_a)
        service_b, slice_b = self.expected_unit_bytes(config_b, release_b)
        self.assertNotEqual(service_a, service_b)
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        receipt_path = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        result = self.invoke("stage", config_a, self.archive, self.identity, runtime=runtime_a)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_terminal_far_side(state_path, release_a, None, config_a, runtime_a, "install", None,
                                      expected_receipt_target_config=config_a,
                                      expected_service_unit=service_a, expected_slice_unit=slice_a)
        result = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_terminal_far_side(state_path, release_b, release_a, config_b, runtime_b, "install", None,
                                      expected_previous_config=config_a, expected_previous_runtime=runtime_a,
                                      expected_receipt_target_config=config_b,
                                      expected_service_unit=service_b, expected_slice_unit=slice_b,
                                      expected_previous_service_unit=service_a,
                                      expected_previous_slice_unit=slice_a)

        uncertain = b'{"status":"uncertain","request_id":"n1-n3-port"}\n'
        ledger_path = self.target_path(json.loads(config_a.read_text())["paths"]["ledger"])
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_bytes(uncertain)
        expected = [("rollback", config_b, None, release_a, release_b, "rollback", config_a, runtime_a),
                    ("install", config_b, runtime_b, release_b, release_a, "install", config_b, runtime_b),
                    ("stage", config_a, runtime_a, release_a, release_b, "install", config_a, runtime_a),
                    ("rollback", config_a, None, release_b, release_a, "rollback", config_b, runtime_b)]
        for mode, config, runtime, expected_release, expected_previous, action, expected_config, expected_runtime in expected:
            result = self.invoke(mode, config, self.archive, self.identity, runtime=runtime)
            self.assertEqual(result.returncode, 0, result.stderr)
            expected_service, expected_slice = ((service_a, slice_a) if expected_release == release_a
                                                else (service_b, slice_b))
            previous_service, previous_slice = ((service_a, slice_a) if expected_previous == release_a
                                                else (service_b, slice_b)) if expected_previous is not None else (None, None)
            self.assert_terminal_far_side(state_path, expected_release, expected_previous,
                                          expected_config, expected_runtime, action, uncertain,
                                          expected_previous_config=(config_a if expected_previous == release_a else config_b)
                                          if expected_previous is not None else None,
                                          expected_previous_runtime=(runtime_a if expected_previous == release_a else runtime_b)
                                          if expected_previous is not None else None,
                                          expected_receipt_target_config=config,
                                          expected_service_unit=expected_service,
                                          expected_slice_unit=expected_slice,
                                          expected_previous_service_unit=previous_service,
                                          expected_previous_slice_unit=previous_slice)
        self.assertEqual(len(receipt_path.read_text().splitlines()), 6)
        runtime_path = Path(json.loads(state_path.read_text())["inventory"]["runtime_config"])
        runtime_path.chmod(0o640)
        with self.assertRaises(AssertionError):
            self.assert_terminal_far_side(state_path, release_b, release_a, config_b, runtime_b, "rollback", uncertain,
                                                  expected_previous_config=config_a, expected_previous_runtime=runtime_a)

    def test_n1_port_distinct_path_rollback_binds_invoking_inventory(self):
        runtime_a, config_a, runtime_b, config_b, state_path, _, _, _, uncertain = self._novel_setup(
            distinct_paths=True)
        release_a = self.expected_revision_path(config_a, runtime_a)
        release_b = self.expected_revision_path(config_b, runtime_b)
        service_a, slice_a = self.expected_unit_bytes(config_a, release_a)
        service_b, slice_b = self.expected_unit_bytes(config_b, release_b)
        self.assertNotEqual(self.expected_inventory(config_a)["operator_config"],
                            self.expected_inventory(config_b)["operator_config"])
        result = self.invoke("rollback", config_b)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_terminal_far_side(
            state_path, release_a, release_b, config_a, runtime_a, "rollback", uncertain,
            expected_previous_config=config_b, expected_previous_runtime=runtime_b,
            expected_receipt_target_config=config_b,
            expected_service_unit=service_a, expected_slice_unit=slice_a,
            expected_previous_service_unit=service_b, expected_previous_slice_unit=slice_b)

    def test_n1_port_rejects_unique_self_install_arrival_read_only(self):
        runtime = self.runtime("self-arrival", enabled=False)
        config = self.config_for_runtime(runtime, active=False)
        first = self.invoke("stage", config, self.archive, self.identity, runtime=runtime)
        self.assertEqual(first.returncode, 0, first.stderr)
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        receipts_path = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        original_receipts = receipts_path.read_bytes()
        repeat = self.invoke("stage", config, self.archive, self.identity, runtime=runtime)
        self.assertEqual(repeat.returncode, 0, repeat.stderr)
        self.assertEqual(receipts_path.read_bytes(), original_receipts)
        unavailable = self.invoke("rollback", config)
        self.assertEqual(unavailable.returncode, 2, unavailable.stderr)
        self.assertIn("recorded previous release", unavailable.stderr)

        state = json.loads(state_path.read_text())
        first_receipt = state["latest_transition"]
        self_install = copy.deepcopy(first_receipt)
        self_install["transition_id"] = "invented-self-install-arrival"
        self_install["from_release"] = self_install["to_release"]
        self_install["from_record_sha256"] = self_install["to_record_sha256"]
        self_install["from_record_byte_length"] = self_install["to_record_byte_length"]
        state["previous"] = copy.deepcopy(state["current"])
        state["latest_transition"] = self_install
        state_path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n")
        receipts_path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                                          for row in (first_receipt, self_install)))

        before_stage = self.target_snapshot()
        rejected_stage = self.invoke("stage", config, self.archive, self.identity, runtime=runtime)
        self._assert_unchanged_failure(rejected_stage, before_stage, "same immutable release")
        before_rollback = self.target_snapshot()
        rejected_rollback = self.invoke("rollback", config)
        self._assert_unchanged_failure(rejected_rollback, before_rollback, "same immutable release")

    def test_n1_port_coherent_unit_corruption_is_rejected_by_actual_method(self):
        original_invoke = self.invoke
        for unit_kind in ("service", "slice"):
            with self.subTest(unit=unit_kind):
                shutil.rmtree(self.target)
                self.target.mkdir()
                for source in self.directory.glob("runtime-*.toml"):
                    source.unlink()
                calls = [0]
                injected = [False]

                def replace_bytes(path, data):
                    mode = path.stat().st_mode & 0o777
                    path.chmod(0o600)
                    path.write_bytes(data)
                    path.chmod(mode)

                def invoke(*args, **kwargs):
                    result = original_invoke(*args, **kwargs)
                    calls[0] += 1
                    if calls[0] == 6 and result.returncode == 0:
                        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
                        state = json.loads(state_path.read_text())
                        record = state["current"]
                        release = Path(record["release"])
                        stored_unit = release / f"{unit_kind}.unit"
                        changed = stored_unit.read_bytes() + b"\n# injected coherent wrong final unit\n"
                        replace_bytes(stored_unit, changed)
                        external_key = "unit" if unit_kind == "service" else "slice_unit"
                        replace_bytes(Path(state["inventory"][external_key]), changed)
                        record[f"{unit_kind}_unit_sha256"] = hashlib.sha256(changed).hexdigest()
                        record[f"{unit_kind}_unit_byte_length"] = len(changed)
                        record_bytes = (json.dumps(record, sort_keys=True, indent=2) + "\n").encode()
                        replace_bytes(release / "REVISION_RECORD.json", record_bytes)
                        receipt = state["latest_transition"]
                        receipt["to_record_sha256"] = hashlib.sha256(record_bytes).hexdigest()
                        receipt["to_record_byte_length"] = len(record_bytes)
                        receipt_path = Path(state["inventory"]["deployment_receipts"])
                        rows = [json.loads(line) for line in receipt_path.read_text().splitlines()]
                        rows[-1] = receipt
                        replace_bytes(receipt_path, "".join(
                            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows).encode())
                        replace_bytes(state_path, (json.dumps(state, sort_keys=True, indent=2) + "\n").encode())
                        injected[0] = True
                    return result

                self.invoke = invoke
                try:
                    with self.assertRaises(AssertionError) as caught:
                        self.test_n1_port_six_leg_same_archive_arrival_sequence()
                finally:
                    self.invoke = original_invoke
                self.assertTrue(injected[0])
                self.assertEqual(calls[0], 6)
                self.assertIn("injected coherent wrong final unit", str(caught.exception))

    def test_n1_port_first_a_and_b_far_side_corruption_fails_immediately(self):
        for corrupt in ("first-a", "first-b"):
            with self.subTest(corrupt=corrupt):
                shutil.rmtree(self.target)
                self.target.mkdir()
                runtime_a = self.runtime("corrupt-a-" + corrupt, enabled=False)
                config_a = self.config_for_runtime(runtime_a, active=False)
                runtime_b = self.runtime("corrupt-b-" + corrupt, enabled=True)
                config_b = self.config_for_runtime(runtime_b, active=True)
                release_a = self.expected_revision_path(config_a, runtime_a)
                release_b = self.expected_revision_path(config_b, runtime_b)
                state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
                result = self.invoke("stage", config_a, self.archive, self.identity, runtime=runtime_a)
                self.assertEqual(result.returncode, 0, result.stderr)
                expected_release, expected_config, expected_runtime = release_a, config_a, runtime_a
                if corrupt == "first-a":
                    runtime_path = Path(json.loads(state_path.read_text())["inventory"]["runtime_config"])
                    runtime_path.chmod(0o640)
                    runtime_path.write_bytes(b"corrupt-a\n")
                    runtime_path.chmod(0o440)
                else:
                    self.assert_terminal_far_side(state_path, release_a, None, config_a, runtime_a, "install", None)
                    result = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    expected_release, expected_config, expected_runtime = release_b, config_b, runtime_b
                    operator_path = Path(json.loads(state_path.read_text())["inventory"]["operator_config"])
                    operator_path.chmod(0o640)
                    operator_path.write_bytes(b"corrupt-b\n")
                    operator_path.chmod(0o600)
                with self.assertRaises(AssertionError):
                    self.assert_terminal_far_side(state_path, expected_release,
                                                  None if corrupt == "first-a" else release_a,
                                                  expected_config, expected_runtime, "install", None,
                                                  expected_previous_config=None if corrupt == "first-a" else config_a,
                                                  expected_previous_runtime=None if corrupt == "first-a" else runtime_a)

    def test_n1_port_stale_historical_latest_witness_is_rejected_at_arrival_guard(self):
        runtime_a, config_a, runtime_b, config_b, state_path, _, _, _, _ = self._novel_setup()
        for mode, config, runtime in (("rollback", config_b, None), ("install", config_b, runtime_b),
                                      ("rollback", config_b, None), ("install", config_b, runtime_b),
                                      ("rollback", config_b, None)):
            result = self.invoke(mode, config, self.archive, self.identity, runtime=runtime)
            self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(state_path.read_text())
        receipts = self.target / "var/lib/lmdj/pr-agent/operator-state/deployment-receipts.jsonl"
        records = [json.loads(line) for line in receipts.read_text().splitlines()]
        state["latest_transition"] = records[2]
        state_path.write_text(json.dumps(state) + "\n")
        before = self.target_snapshot()
        result = self.invoke("rollback", config_b)
        self._assert_unchanged_failure(result, before, "actual latest durable receipt")

    def test_n2_port_pending_rollback_far_side_mode_reason_is_asserted(self):
        _, _, _, config_b, state_path, _, pending, _ = self._prepare_pending_rollback_far_side()
        path = Path(pending["transition"]["to"]["operator_config_path"])
        path.chmod(0o666)
        before = self.target_snapshot()
        result = self.invoke("rollback", config_b)
        self._assert_unchanged_failure(result, before, "recorded operator config owner or mode")
        self.assertIn("transition", json.loads(state_path.read_text()))

    def test_n1_port_terminal_archive_and_target_forgery_is_read_only(self):
        _, _, runtime_b, config_b, state_path, receipt_path, _, state_b, _ = self._novel_setup()
        forged = copy.deepcopy(state_b["latest_transition"])
        forged["archive_sha256"] = "0" * 64
        forged["target"]["host"] = "forged-host"
        state = copy.deepcopy(state_b)
        records = [json.loads(line) for line in receipt_path.read_text().splitlines()]
        state["latest_transition"] = records[-1]
        state_path.write_text(json.dumps(state) + "\n")
        receipt_path.write_text("".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                                    for record in (records[0], forged)))
        before = self.target_snapshot()
        result = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b)
        self._assert_unchanged_failure(result, before, "deployment receipt target does not match trusted inventory")

    def test_history_reducer_rejects_impossible_relabelled_rollback(self):
        _, _, runtime_b, config_b, state_path, receipt_path, _, state_b, _ = self._novel_setup()
        runtime_c = self.runtime("relabel-c", enabled=True)
        config_c = self.config_for_runtime(runtime_c, active=True, suffix="relabel-c")
        self.assertEqual(self.invoke("install", config_c, self.archive, self.identity, runtime=runtime_c).returncode, 0)
        state_c = json.loads(state_path.read_text())
        records = [json.loads(line) for line in receipt_path.read_text().splitlines()]
        forged = copy.deepcopy(records[-1])
        forged["action"] = "rollback"
        forged["transition_id"] = "impossible-relabelled-rollback"
        forged.pop("archive_sha256")
        forged.pop("archive_byte_length")
        forged.pop("deployment_identity_sha256")
        forged["from_release"] = state_c["current"]["release"]
        forged["to_release"] = state_b["previous"]["release"]
        def commitment(record):
            data = (json.dumps(record, sort_keys=True, indent=2) + "\n").encode()
            return hashlib.sha256(data).hexdigest(), len(data)
        forged["from_record_sha256"], forged["from_record_byte_length"] = commitment(state_c["current"])
        forged["to_record_sha256"], forged["to_record_byte_length"] = commitment(state_b["previous"])
        state = copy.deepcopy(state_c)
        state["latest_transition"] = records[-1]
        state["transition"] = {"action": "rollback", "from": copy.deepcopy(state_c["current"]),
                                "to": copy.deepcopy(state_b["previous"]), "previous": copy.deepcopy(state_c["current"]),
                                "receipt": forged}
        state_path.write_text(json.dumps(state) + "\n")
        receipt_path.write_text("".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                                    for record in records[:3]))
        before = self.target_snapshot()
        result = self.invoke("install", config_c, self.archive, self.identity, runtime=runtime_c)
        self._assert_unchanged_failure(result, before, "replay-derived previous revision")

    def test_historical_record_requires_operator_receipt_commitment(self):
        _, _, runtime_b, config_b, state_path, receipt_path, _, state_b, _ = self._novel_setup()
        prior = copy.deepcopy(state_b["previous"])
        metadata = Path(prior["release"]) / "REVISION_RECORD.json"
        unit = Path(prior["release"]) / "service.unit"
        changed = unit.read_bytes().replace(b"Description=LMDJ", b"Description=forged")
        unit.chmod(0o644)
        unit.write_bytes(changed)
        unit.chmod(0o444)
        prior["service_unit_sha256"] = hashlib.sha256(changed).hexdigest()
        prior["service_unit_byte_length"] = len(changed)
        metadata.chmod(0o644)
        metadata.write_text(json.dumps(prior, sort_keys=True, indent=2) + "\n")
        metadata.chmod(0o444)
        state = copy.deepcopy(state_b)
        state["previous"] = prior
        state_path.write_text(json.dumps(state) + "\n")
        before = self.target_snapshot()
        result = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b)
        self._assert_unchanged_failure(result, before, "record commitment")

    def test_unretained_historical_record_length_guard_reaches_commitment_check(self):
        _, _, runtime_b, config_b, state_path, receipt_path, _, _, _ = self._novel_setup()
        runtime_c = self.runtime("historical-length-c", enabled=True)
        config_c = self.config_for_runtime(runtime_c, active=True, suffix="historical-length-c")
        self.assertEqual(self.invoke("install", config_c, self.archive, self.identity,
                                     runtime=runtime_c).returncode, 0)
        state_c = json.loads(state_path.read_text())
        records = [json.loads(line) for line in receipt_path.read_text().splitlines()]
        record_path = Path(records[0]["to_release"]) / "REVISION_RECORD.json"
        self.assertNotIn(str(record_path.parent), {state_c["current"]["release"], state_c["previous"]["release"]})
        record = json.loads(record_path.read_text())
        record["runtime_config_byte_length"] += 1
        record_path.chmod(0o644)
        record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
        record_path.chmod(0o444)
        before = self.target_snapshot()
        result = self.invoke("install", config_c, self.archive, self.identity, runtime=runtime_c)
        self._assert_unchanged_failure(result, before, "historical immutable revision record is not a closed")

    def test_unretained_historical_unit_and_record_forgery_reaches_commitment_check(self):
        _, _, runtime_b, config_b, state_path, receipt_path, _, _, _ = self._novel_setup()
        runtime_c = self.runtime("historical-unit-c", enabled=True)
        config_c = self.config_for_runtime(runtime_c, active=True, suffix="historical-unit-c")
        self.assertEqual(self.invoke("install", config_c, self.archive, self.identity,
                                     runtime=runtime_c).returncode, 0)
        state_c = json.loads(state_path.read_text())
        records = [json.loads(line) for line in receipt_path.read_text().splitlines()]
        release = Path(records[0]["to_release"])
        self.assertNotIn(str(release), {state_c["current"]["release"], state_c["previous"]["release"]})
        unit_path = release / "service.unit"
        record_path = release / "REVISION_RECORD.json"
        changed = unit_path.read_bytes().replace(b"ExecStart=/usr/bin/false", b"ExecStart=/usr/bin/true")
        self.assertNotEqual(changed, unit_path.read_bytes())
        unit_path.chmod(0o644)
        unit_path.write_bytes(changed)
        unit_path.chmod(0o444)
        record = json.loads(record_path.read_text())
        record["service_unit_sha256"] = hashlib.sha256(changed).hexdigest()
        record["service_unit_byte_length"] = len(changed)
        record_path.chmod(0o644)
        record_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
        record_path.chmod(0o444)
        before = self.target_snapshot()
        result = self.invoke("install", config_c, self.archive, self.identity, runtime=runtime_c)
        self._assert_unchanged_failure(result, before, "record commitment")

    def test_v3_receipt_without_record_commitments_is_read_only(self):
        config = self.config(active=True)
        self.assertEqual(self.invoke("install", config, self.archive, self.identity).returncode, 0)
        state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
        state = json.loads(state_path.read_text())
        state["latest_transition"].pop("to_record_sha256")
        state_path.write_text(json.dumps(state) + "\n")
        before = self.target_snapshot()
        result = self.invoke("install", config, self.archive, self.identity)
        self._assert_unchanged_failure(result, before, "canonical record commitments")

    def test_historical_endpoint_path_must_match_immutable_record(self):
        _, _, runtime_b, config_b, state_path, receipt_path, _, state_b, _ = self._novel_setup()
        runtime_c = self.runtime("clone-c", enabled=True)
        config_c = self.config_for_runtime(runtime_c, active=True, suffix="clone-c")
        self.assertEqual(self.invoke("install", config_c, self.archive, self.identity, runtime=runtime_c).returncode, 0)
        state_c = json.loads(state_path.read_text())
        original = Path(state_b["previous"]["release"])
        clone = original.parent / ("f" * 64)
        shutil.copytree(original, clone)
        records = [json.loads(line) for line in receipt_path.read_text().splitlines()]
        records[0]["to_release"] = str(clone)
        records[1]["from_release"] = str(clone)
        state = copy.deepcopy(state_c)
        state["latest_transition"] = records[2]
        receipt_path.write_text("".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                                    for record in records))
        state_path.write_text(json.dumps(state) + "\n")
        before = self.target_snapshot()
        result = self.invoke("install", config_c, self.archive, self.identity, runtime=runtime_c)
        self._assert_unchanged_failure(result, before, "endpoint record does not bind the canonical release path")

    def test_stored_historical_record_bytes_must_match_canonical_commitment(self):
        _, _, runtime_b, config_b, state_path, _, _, state_b, _ = self._novel_setup()
        record_path = Path(state_b["current"]["release"]) / "REVISION_RECORD.json"
        original = record_path.read_bytes()
        record_path.chmod(0o644)
        record_path.write_bytes(original + b" \n")
        record_path.chmod(0o444)
        before = self.target_snapshot()
        result = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b)
        self._assert_unchanged_failure(result, before, "immutable revision record bytes are not canonical")

    def test_pending_receipt_target_forgery_is_rejected_before_append(self):
        _, _, _, config_b, state_path, receipt_path, pending, _ = self._prepare_pending_rollback_far_side()
        pending["transition"]["receipt"]["target"]["operator_config"] = "/etc/lmdj/pr-agent/forged.json"
        state_path.write_text(json.dumps(pending) + "\n")
        before = self.target_snapshot()
        result = self.invoke("rollback", config_b)
        self._assert_unchanged_failure(result, before, "transition is not semantically authenticated")

    def test_rollback_rejects_changed_invoking_operator_inventory(self):
        _, _, _, config_b, _, _, _, state_b, _ = self._novel_setup()
        document = json.loads(config_b.read_text())
        document["paths"]["operator_config"] = "/etc/lmdj/pr-agent/never-invoked.json"
        forged = self.directory / "changed-invoking-config.json"
        forged.write_text(json.dumps(document) + "\n")
        forged.chmod(0o600)
        before = self.target_snapshot()
        result = self.invoke("rollback", forged)
        self._assert_unchanged_failure(result, before, "invocation inventory")

    def test_n3_port_each_of_six_transitions_has_source_and_parent_fsync(self):
        wrapper = self.directory / "trace-six-python"
        trace = self.directory / "trace-six.jsonl"
        wrapper.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys, stat\n"
            "real_fsync, real_replace = os.fsync, os.replace\n"
            "def ident(value): return [value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid]\n"
            "def emit(value):\n"
            "    with open(os.environ['PR_AGENT_TRACE_PATH'], 'a') as handle: handle.write(json.dumps(value) + '\\n')\n"
            "def fsync(fd):\n"
            "    value = os.fstat(fd)\n"
            "    path = None\n"
            "    for base, dirs, files in os.walk(sys.argv[-2]):\n"
            "        for name in files:\n"
            "            candidate = os.path.join(base, name)\n"
            "            try:\n"
            "                if os.stat(candidate).st_ino == value.st_ino and os.stat(candidate).st_dev == value.st_dev:\n"
            "                    path = candidate\n"
            "                    raise StopIteration\n"
            "            except FileNotFoundError:\n"
            "                continue\n"
            "            except StopIteration:\n"
            "                break\n"
            "        if path is not None:\n"
            "            break\n"
            "    emit({'event':'fsync','identity':ident(value),'path':path}); return real_fsync(fd)\n"
            "def replace(source, destination):\n"
            "    event = {'event':'replace','source':ident(os.lstat(source)),'parent':ident(os.stat(os.path.dirname(destination))),'destination':str(destination)}\n"
            "    result = real_replace(source, destination)\n"
            "    event['destination_identity'] = ident(os.lstat(destination))\n"
            "    emit(event)\n"
            "    return result\n"
            "os.fsync, os.replace = fsync, replace\n"
            "sys.argv = sys.argv[1:]\n"
            "exec(compile(sys.stdin.read(), '<deploy-runner>', 'exec'), {'__name__':'__main__'})\n")
        wrapper.chmod(0o755)
        runtime_a = self.runtime("durability-a", enabled=False)
        config_a = self.config_for_runtime(runtime_a, active=False)
        runtime_b = self.runtime("durability-b", enabled=True)
        config_b = self.config_for_runtime(runtime_b, active=True)
        transitions = (("stage", config_a, runtime_a), ("install", config_b, runtime_b),
                       ("rollback", config_b, None), ("install", config_b, runtime_b),
                       ("stage", config_a, runtime_a), ("rollback", config_a, None))
        expected = ((config_a, runtime_a, None, "install"),
                    (config_b, runtime_b, "A", "install"),
                    (config_a, runtime_a, "B", "rollback"),
                    (config_b, runtime_b, "A", "install"),
                    (config_a, runtime_a, "B", "install"),
                    (config_b, runtime_b, "A", "rollback"))
        ledger_bytes = b'{"status":"uncertain","request_id":"n1-n3-port"}\n'
        ledger_path = self.target_path(json.loads(config_a.read_text())["paths"]["ledger"])
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_bytes(ledger_bytes)
        ledger_path.chmod(0o644)
        release_a = self.expected_revision_path(config_a, runtime_a)
        release_b = self.expected_revision_path(config_b, runtime_b)
        service_a, slice_a = self.expected_unit_bytes(config_a, release_a)
        service_b, slice_b = self.expected_unit_bytes(config_b, release_b)
        counts = []
        for leg, ((mode, config, runtime), (expected_config, expected_runtime,
                                            expected_previous, expected_action)) in enumerate(
                                                zip(transitions, expected), start=1):
            trace.write_text("")
            result = self.invoke(mode, config, self.archive, self.identity, runtime=runtime,
                                 python_bin=wrapper, trace_path=trace)
            self.assertEqual(result.returncode, 0, result.stderr)
            events = [json.loads(line) for line in trace.read_text().splitlines()]
            replacements = [index for index, event in enumerate(events) if event["event"] == "replace"]
            self.assertTrue(replacements)
            final_destinations = {}
            for index in replacements:
                final_destinations[events[index]["destination"]] = events[index]["destination_identity"]
                self.assertEqual(events[index + 1]["event"], "fsync")
                self.assertEqual(events[index + 1]["identity"], events[index]["parent"])
                if not stat.S_ISLNK(events[index]["source"][2]):
                    self.assertEqual(events[index - 1]["event"], "fsync")
                    self.assertEqual(events[index - 1]["identity"], events[index]["source"])
                    self.assertEqual(events[index]["destination_identity"], events[index]["source"],
                                     f"leg {leg} replaced destination metadata")
            for destination, expected_identity in final_destinations.items():
                final_path = Path(destination)
                self.assertTrue(final_path.exists() or final_path.is_symlink(),
                                f"leg {leg} removed published destination {destination}")
                final_metadata = final_path.lstat()
                self.assertEqual(
                    [final_metadata.st_dev, final_metadata.st_ino,
                     final_metadata.st_mode, final_metadata.st_uid,
                     final_metadata.st_gid],
                    expected_identity,
                    f"leg {leg} final destination metadata changed: {destination}",
                )
            if leg <= 2:
                expected_release = release_a if leg == 1 else release_b
                publication_indexes = [index for index, event in enumerate(events)
                                       if event["event"] == "replace"
                                       and event["destination"] == str(expected_release)]
                self.assertEqual(len(publication_indexes), 1,
                                 f"leg {leg} did not publish the expected immutable release")
                publication_index = publication_indexes[0]
                expected_record = expected_release / "REVISION_RECORD.json"
                expected_identity = [expected_record.stat().st_dev, expected_record.stat().st_ino,
                                     expected_record.stat().st_mode, expected_record.stat().st_uid,
                                     expected_record.stat().st_gid]
                record_fsync_indexes = [index for index, event in enumerate(events)
                                        if event["event"] == "fsync" and event["identity"] == expected_identity]
                self.assertTrue(record_fsync_indexes,
                                f"leg {leg} did not fsync the published revision record")
                self.assertTrue(any(index < publication_index for index in record_fsync_indexes),
                                f"leg {leg} fsynced the revision record after release publication")
            counts.append(len(replacements))
            state = json.loads((self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json").read_text())
            expected_release = release_a if expected_previous in (None, "B") else release_b
            if expected_previous == "A":
                expected_previous_release = release_a
            elif expected_previous == "B":
                expected_previous_release = release_b
            else:
                expected_previous_release = None
            if expected_release is not None and (expected_previous != "B" or release_b is not None):
                expected_service, expected_slice = ((service_a, slice_a) if expected_release == release_a
                                                    else (service_b, slice_b))
                previous_service, previous_slice = ((service_a, slice_a) if expected_previous == "A"
                                                    else (service_b, slice_b)) if expected_previous is not None else (None, None)
                self.assert_terminal_far_side(
                    self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json",
                    expected_release, expected_previous_release, expected_config,
                    expected_runtime, expected_action, ledger_bytes,
                    expected_previous_config=(config_a if expected_previous == "A" else config_b)
                    if expected_previous is not None else None,
                    expected_previous_runtime=(runtime_a if expected_previous == "A" else runtime_b)
                    if expected_previous is not None else None,
                    expected_receipt_target_config=config,
                    expected_service_unit=expected_service,
                    expected_slice_unit=expected_slice,
                    expected_previous_service_unit=previous_service,
                    expected_previous_slice_unit=previous_slice)
        self.assertEqual(len(counts), 6)
        self.assertTrue(all(count > 0 for count in counts))

    def test_n3_port_late_record_fsync_is_rejected_by_actual_method(self):
        original_invoke = self.invoke
        calls = [0]
        injected = [False]
        shim = '''
original_traced_fsync, original_traced_replace = fsync, replace
late_record_fds = []
release_published = False
def fsync(fd):
    identity = os.fstat(fd)
    for base, dirs, files in os.walk(sys.argv[-2]):
        if 'REVISION_RECORD.json' in files:
            candidate = os.path.join(base, 'REVISION_RECORD.json')
            metadata = os.stat(candidate)
            if (metadata.st_dev, metadata.st_ino) == (identity.st_dev, identity.st_ino):
                late_record_fds.append(os.dup(fd))
                return None
    result = original_traced_fsync(fd)
    if release_published and stat.S_ISDIR(identity.st_mode):
        while late_record_fds:
            deferred = late_record_fds.pop(0)
            original_traced_fsync(deferred)
            with open(os.environ['PR_AGENT_TRACE_PATH'] + '.late-records', 'a') as out:
                out.write(json.dumps({'record': ident(os.fstat(deferred)), 'after_release_and_parent': True}) + '\\n')
            os.close(deferred)
    return result
def replace(source, destination):
    global release_published
    result = original_traced_replace(source, destination)
    if os.path.isdir(destination) and os.path.isfile(os.path.join(destination, 'REVISION_RECORD.json')):
        release_published = True
    return result
'''

        def invoke(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                wrapper = kwargs["python_bin"]
                text = wrapper.read_text()
                marker = "os.fsync, os.replace = fsync, replace\n"
                self.assertEqual(text.count(marker), 1)
                wrapper.write_text(text.replace(marker, shim + "\n" + marker))
                injected[0] = True
            return original_invoke(*args, **kwargs)

        self.invoke = invoke
        try:
            with self.assertRaises(AssertionError) as caught:
                self.test_n3_port_each_of_six_transitions_has_source_and_parent_fsync()
        finally:
            self.invoke = original_invoke
        trace = self.directory / "trace-six.jsonl"
        events = [json.loads(line) for line in trace.read_text().splitlines()]
        release_event = next(event for event in events
                             if event["event"] == "replace" and "/releases/" in event["destination"])
        release_path = Path(release_event["destination"])
        record_identity = [release_path.joinpath("REVISION_RECORD.json").stat().st_dev,
                           release_path.joinpath("REVISION_RECORD.json").stat().st_ino,
                           release_path.joinpath("REVISION_RECORD.json").stat().st_mode,
                           release_path.joinpath("REVISION_RECORD.json").stat().st_uid,
                           release_path.joinpath("REVISION_RECORD.json").stat().st_gid]
        release_index = events.index(release_event)
        self.assertTrue(any(index > release_index and event["event"] == "fsync"
                            and event["identity"] == record_identity
                            for index, event in enumerate(events)))
        self.assertTrue(injected[0])
        self.assertEqual(calls[0], 1)
        self.assertIn("after release publication", str(caught.exception))

    def test_n3_port_final_state_metadata_corruption_fails_actual_method(self):
        real_invoke = self.invoke
        calls = 0

        def corrupt_final_state(*args, **kwargs):
            nonlocal calls
            result = real_invoke(*args, **kwargs)
            calls += 1
            if calls == 6:
                state_path = self.target / "var/lib/lmdj/pr-agent/operator-state/runtime.json"
                state_path.chmod(0o666)
            return result

        self.invoke = corrupt_final_state
        with self.assertRaises(AssertionError):
            self.test_n3_port_each_of_six_transitions_has_source_and_parent_fsync()
        self.assertEqual(calls, 6)

    def test_n2_port_state_receipt_leaf_owner_mode_and_nested_parent_matrix(self):
        cases = (("state-mode", "state", "mode"), ("state-owner", "state", "owner"),
                 ("receipt-mode", "receipt", "mode"), ("receipt-owner", "receipt", "owner"))
        for name, which, variant in cases:
            with self.subTest(name=name):
                shutil.rmtree(self.target)
                self.target.mkdir()
                for source in (self.directory / "runtime-novel-a.toml", self.directory / "runtime-novel-b.toml"):
                    if source.exists():
                        source.chmod(0o600)
                _, _, runtime_b, config_b, state_path, receipt_path, _, _, _ = self._novel_setup()
                path = state_path if which == "state" else receipt_path
                overrides = None
                if variant == "mode":
                    path.chmod(0o666)
                else:
                    overrides = {str(path): {"uid": os.getuid() + 1, "gid": os.getgid()}}
                before = self.target_snapshot()
                runtime_c = self.runtime("trust-" + name, enabled=True)
                config_c = self.config_for_runtime(runtime_c, active=True, suffix="trust-" + name)
                result = self.invoke("install", config_c, self.archive, self.identity, runtime=runtime_c,
                                     overrides=overrides)
                self._assert_unchanged_failure(result, before, "deployment " + ("state" if which == "state" else "receipts"))
        shutil.rmtree(self.target)
        self.target.mkdir()
        for source in (self.directory / "runtime-novel-a.toml", self.directory / "runtime-novel-b.toml"):
            if source.exists():
                source.chmod(0o600)
        _, _, runtime_b, config_b, _, receipt_path, _, _, _ = self._novel_setup(nested_receipts=True)
        relocated = self.directory / "relocated-history"
        receipt_parent = receipt_path.parent
        receipt_parent.rename(relocated)
        receipt_parent.symlink_to(relocated)
        before = self.target_snapshot()
        external_before = self.external_snapshot(relocated)
        result = self.invoke("install", config_b, self.archive, self.identity, runtime=runtime_b)
        self._assert_unchanged_failure(result, before, "deployment receipts parent is a symlink")
        self.assertEqual(self.external_snapshot(relocated), external_before)

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
