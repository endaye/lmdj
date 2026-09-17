#!/usr/bin/env python3
"""Real local-OS journeys for the bounded S1 supervisor entrypoint.

The helper child is an installed temporary executable, never request input or
Python source sent through fd 0.  The test boundary replaces only root/PID1
identity and launch/observation calls; admission, closed schemas, journal
chains, lock lifetime, filesystem publication, output readback and duplicate
handling all run through the public ``main`` entrypoint.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("pr_agent_attempt_supervisor", ROOT / "scripts/ci/pr_agent_attempt_supervisor.py")
subject = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = subject
SPEC.loader.exec_module(subject)


def canonical(value):
    return subject.canonical_bytes(value)


def identity():
    return {
        "repository": "endaye/lmdj", "pr_number": 1229,
        "base_sha": "a" * 40, "head_sha": "b" * 40,
        "control_sha": "c" * 40, "run_id": 123456, "run_attempt": 1,
    }


class LocalBoundary(subject.OSBoundary):
    """Root/PID1 seam with real open/fstat/flock/Popen/filesystem effects."""

    def __init__(self, *, helper: Path, crash_before_observation=False, mutate_output=False):
        self.helper = helper
        self.launches = {}
        self.launch_count = 0
        self.crash_before_observation = crash_before_observation
        self.mutate_output = mutate_output
        self.observations = 0
        self.slot_busy_during_observation = False
        self.cancel_count = 0

    def effective_uid(self):
        return 0

    def effective_gid(self):
        return 0

    def path_ready(self, path, *, owner, mode, directory=False):
        # Ownership is a low-level Linux seam.  File type, bytes and modes are
        # still exercised by the inherited no-follow reads and real fds.
        return None

    def secure_ancestry(self, path, *, stop, owner):
        return None

    def runtime_identity_matches(self, runtime):
        return True

    def launch(self, *, unit, manifest, input_path, output_path, slot_fd):
        self.launch_count += 1
        process = subprocess.Popen(
            [sys.executable, str(self.helper), str(input_path), str(output_path)],
            stdin=slot_fd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            close_fds=True, pass_fds=(slot_fd,),
        )
        launch = subject.Launch(unit=unit, process=process, stdout=process.stdout, stderr=process.stderr)
        launch.slot = os.fstat(slot_fd)
        launch.output_dir = output_path
        self.launches[unit] = launch
        return launch

    def observe(self, launch, *, expected_boot=None):
        self.observations += 1
        if self.crash_before_observation:
            self.crash_before_observation = False
            raise subject.CrashBeforeObservation("simulated supervisor crash before PID1 observation")
        if expected_boot is not None and expected_boot != "test-boot":
            subject.reject("boot identity changed during recovery", "retain the attempt fence for manual reconciliation")
        try:
            process_start = 1 if launch.process is None else max(1, launch.process.pid)
            pid = None if launch.process is None else launch.process.pid
        except AttributeError:
            pid, process_start = None, None
        if launch.process is not None and launch.process.poll() is None:
            try:
                held = subject.OSBoundary.open_lock(self, subject.SLOT_LOCK_PATH, mode=0o400, nonblocking=True)
            except subject.SupervisorError:
                self.slot_busy_during_observation = True
            else:
                os.close(held)
        slot = {"device": launch.slot.st_dev, "inode": launch.slot.st_ino}
        return subject.Observation(launch.unit, str(uuid.uuid5(uuid.NAMESPACE_URL, launch.unit)), pid,
                                   process_start, "test-boot", "/test/lmdj", "test-job", "success", slot)

    def recover(self, unit, observation=None):
        if unit not in self.launches:
            subject.reject("the exact unfinished unit is not observable", "retain the attempt as uncertain")
        return self.launches[unit]

    def wait(self, launch, timeout):
        if launch.process is None:
            return 0
        try:
            return launch.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def cancel(self, unit, *, invocation_id, cgroup):
        self.cancel_count += 1
        launch = self.launches[unit]
        if launch.process is not None and launch.process.poll() is None:
            launch.process.terminate()

    def closure(self, launch, observation, timeout):
        return launch.process is None or launch.process.poll() is not None


class FailingCheckpointBoundary(LocalBoundary):
    def write_atomic(self, path, raw, mode):
        raise subject.SupervisorError("why: injected checkpoint fsync failure; remedy: retain the fence")


class MutatingOutputBoundary(LocalBoundary):
    def wait(self, launch, timeout):
        result = super().wait(launch, timeout)
        output = Path(launch.output_dir)
        target = output / "result.json"
        if target.exists():
            target.unlink()
            target.symlink_to(self.helper)
        return result


class LeakingBoundary(LocalBoundary):
    def closure(self, launch, observation, timeout):
        return False


class SupervisorJourneyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="lmdj-supervisor-")
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.admissions = self.state / "admissions"
        self.attempts = self.state / "attempts"
        self.runtime = self.root / "run"
        self.release = self.root / "release"
        self.admissions.mkdir(parents=True)
        self.attempts.mkdir(parents=True)
        self.release.mkdir()
        self.runtime.mkdir()
        self.metadata = self.state / "metadata.lock"
        self.metadata.touch()
        self.slot = self.root / "slot.lock"
        self.slot.touch()
        self.checkpoint = self.state / "checkpoint.json"
        self.checkpoint.write_bytes(canonical({"schema": subject.CHECKPOINT_SCHEMA, "tips": {}}))
        self.helper = self.release / "engine-helper.py"
        self.helper.write_text(
            "import hashlib, json, pathlib, sys, time\n"
            "input_path, output_dir = map(pathlib.Path, sys.argv[1:])\n"
            "raw = input_path.read_bytes()\n"
            "document = json.loads(raw)\n"
            "output_dir.mkdir(parents=True, exist_ok=True)\n"
            "digest = hashlib.sha256(raw).hexdigest()\n"
            "identity = document['identity']\n"
            "result = {'schema':'lmdj.pr-agent-result.v1','status':'reviewed','error_class':None,'identity':identity,'input_sha256':digest}\n"
            "coverage = {'schema':'lmdj.pr-agent-coverage.v1','identity':identity,'input_sha256':digest}\n"
            "(output_dir/'result.json').write_text(json.dumps(result)+'\\n')\n"
            "(output_dir/'coverage.json').write_text(json.dumps(coverage)+'\\n')\n"
            "print('local-supervisor-child')\n"
            "time.sleep(0.15)\n",
            encoding="utf-8",
        )
        self.helper.chmod(0o755)
        for name, contents in {
            "supervisor.py": b"immutable supervisor source\n",
            "adapter.py": b"immutable adapter validator\n",
            "config.toml": b"[providers]\n",
            "bundle.tar": b"immutable bundle bytes\n",
        }.items():
            (self.release / name).write_bytes(contents)
        self._old_paths = {name: getattr(subject, name) for name in (
            "MANIFEST_PATH", "STATE_ROOT", "ADMISSIONS_ROOT", "ATTEMPTS_ROOT",
            "METADATA_LOCK_PATH", "CHECKPOINT_PATH", "RUNTIME_ROOT", "SLOT_LOCK_PATH",
        )}
        self._old_boundary = subject.DEFAULT_BOUNDARY
        subject.MANIFEST_PATH = self.root / "supervisor-installation.json"
        subject.STATE_ROOT = self.state
        subject.ADMISSIONS_ROOT = self.admissions
        subject.ATTEMPTS_ROOT = self.attempts
        subject.METADATA_LOCK_PATH = self.metadata
        subject.CHECKPOINT_PATH = self.checkpoint
        subject.RUNTIME_ROOT = self.runtime
        subject.SLOT_LOCK_PATH = self.slot
        self.manifest = self._write_manifest()
        self.request_id = str(uuid.uuid4())
        self._write_request()
        self.addCleanup(self._restore)

    def _restore(self):
        for name, value in self._old_paths.items():
            setattr(subject, name, value)
        subject.DEFAULT_BOUNDARY = self._old_boundary
        self.tmp.cleanup()

    def _write_manifest(self):
        def digest_member(member):
            raw = (self.release / member).read_bytes()
            return {"sha256": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw), "member": member}

        def sha(member):
            return hashlib.sha256((self.release / member).read_bytes()).hexdigest()

        record = {
            "schema": "lmdj.pr-agent-installation-record.v1", "deployment_revision": "d" * 40,
            "source_sha256": sha("supervisor.py"), "adapter_sha256": sha("adapter.py"),
            "config_sha256": sha("config.toml"), "bundle_sha256": sha("bundle.tar"),
        }
        (self.release / "INSTALLATION_RECORD.json").write_bytes(canonical(record))

        manifest = {
            "schema": subject.SUPERVISOR_INSTALLATION_SCHEMA,
            "host": {
                "release_root": str(self.release), "engine_path": str(self.helper),
                "config_path": str(self.release / "config.toml"), "source_root": str(self.release),
                "engine_cwd": str(self.root), "ledger_path": str(self.root / "ledger.jsonl"),
                "adapter_path": str(self.release / "adapter.py"), "manager": "system",
                "slice": subject.FIXED_SLICE, "slot_path": str(self.slot), "old_launcher_disabled": True,
            },
            "deployment_revision": "d" * 40,
            "source_identity": digest_member("supervisor.py"),
            "adapter_identity": digest_member("adapter.py"),
            "config_identity": digest_member("config.toml"),
            "bundle_identity": digest_member("bundle.tar"),
            "installation_record_identity": digest_member("INSTALLATION_RECORD.json"),
            "runtime_identity": {"user": subject.FIXED_USER, "group": subject.FIXED_GROUP, "uid": 0, "gid": 0, "python": subject.PYTHON312},
            "limits": {"cpu": 1, "memory_bytes": 2 * 1024**3, "cpu_weight": 1, "tasks_max": 128,
                       "engine_deadline_seconds": 20, "launch_observation_seconds": 10,
                       "term_grace_seconds": 5, "kill_grace_seconds": 5, "final_closure_seconds": 10},
        }
        subject.MANIFEST_PATH.write_bytes(canonical(manifest))
        return manifest

    def _write_request(self, *, request_id=None, kind="root-operator"):
        request_id = request_id or self.request_id
        generation = self.admissions / request_id
        generation.mkdir(parents=True, exist_ok=True)
        input_document = {"schema": "lmdj.pr-agent-input.v1", "identity": identity(), "files": []}
        input_raw = canonical(input_document)
        intake_raw = b"root operator spool authorization\n"
        producer_raw = b"complete producer collection receipt\n"
        def digest(raw):
            return {"sha256": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw)}
        admission = {
            "schema": subject.ADMISSION_SCHEMA, "request_id": request_id, "identity": identity(), "job_id": 99,
            "intake_evidence": {"kind": kind, **digest(intake_raw), "member": "intake-evidence.json"},
            "complete_input": {**digest(input_raw), "member": "input.json", "t2_input_sha256": hashlib.sha256(input_raw).hexdigest()},
            "producer_witness": {"schema": "lmdj.pr-agent-producer-receipt.v1", "status": "successful", **digest(producer_raw), "member": "producer-witness.json"},
            "installation_identity": subject.installation_binding(self.manifest),
        }
        (generation / "request.json").write_bytes(canonical(admission))
        (generation / "input.json").write_bytes(input_raw)
        (generation / "intake-evidence.json").write_bytes(intake_raw)
        (generation / "producer-witness.json").write_bytes(producer_raw)
        return admission

    def invoke(self, boundary, argv):
        output = io.StringIO()
        subject.DEFAULT_BOUNDARY = boundary
        with contextlib.redirect_stdout(output):
            result_code = subject.main(argv)
        if result_code not in {0, 2}:
            self.fail(f"unexpected supervisor exit {result_code}: {output.getvalue()}")
        payload = json.loads(output.getvalue())
        if payload.get("status") == "rejected":
            raise subject.SupervisorError(payload["error"])
        return payload, output.getvalue()

    def test_complete_public_lifecycle_and_competing_flock(self):
        boundary = LocalBoundary(helper=self.helper)
        result, _ = self.invoke(boundary, ["submit", self.request_id])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["business_outcome"], "reviewed")
        self.assertEqual(boundary.launch_count, 1)
        self.assertTrue(boundary.slot_busy_during_observation)
        attempt = self.attempts / result["attempt_id"]
        self.assertEqual(sorted(p.name for p in (attempt / "transitions").iterdir()), [f"{i:06d}.json" for i in range(1, 7)])
        self.assertEqual((attempt / "evidence" / "result.json").read_bytes(), (self.runtime / result["attempt_id"] / "engine" / "output" / "result.json").read_bytes())
        duplicate, _ = self.invoke(boundary, ["submit", self.request_id])
        self.assertEqual(duplicate["status"], "completed")
        self.assertEqual(duplicate["attempt_id"], result["attempt_id"])
        self.assertEqual(boundary.launch_count, 1)

    def test_root_spool_mutation_is_refused_before_launch(self):
        generation = self.admissions / self.request_id
        raw = (generation / "input.json").read_bytes()
        (generation / "input.json").write_bytes(raw + b"mutation")
        boundary = LocalBoundary(helper=self.helper)
        with self.assertRaises(subject.SupervisorError) as caught:
            self.invoke(boundary, ["submit", self.request_id])
        self.assertIn("complete input bytes differ", str(caught.exception))
        self.assertEqual(boundary.launch_count, 0)
        self.assertEqual(list(self.attempts.iterdir()), [])

    def test_bool_job_id_and_old_launcher_profile_are_refused_before_launch(self):
        request = self.admissions / self.request_id / "request.json"
        admission = json.loads(request.read_text())
        admission["job_id"] = True
        request.write_bytes(canonical(admission))
        boundary = LocalBoundary(helper=self.helper)
        with self.assertRaises(subject.SupervisorError) as caught:
            self.invoke(boundary, ["submit", self.request_id])
        self.assertIn("job_id is not a bounded integer", str(caught.exception))
        self.assertEqual(boundary.launch_count, 0)
        admission["job_id"] = 99
        request.write_bytes(canonical(admission))
        manifest = json.loads(subject.MANIFEST_PATH.read_text())
        manifest["host"]["old_launcher_disabled"] = False
        subject.MANIFEST_PATH.write_bytes(canonical(manifest))
        with self.assertRaises(subject.SupervisorError) as caught:
            self.invoke(boundary, ["submit", self.request_id])
        self.assertIn("old service-owned launcher", str(caught.exception))
        self.assertEqual(boundary.launch_count, 0)

    def test_duplicate_keys_and_actions_intake_are_rejected_before_effect(self):
        request = self.admissions / self.request_id / "request.json"
        request.write_bytes(b'{"schema":"x","schema":"y"}\n')
        boundary = LocalBoundary(helper=self.helper)
        with self.assertRaises(subject.SupervisorError):
            self.invoke(boundary, ["submit", self.request_id])
        self.assertEqual(boundary.launch_count, 0)
        self._write_request(kind="github-actions")
        with self.assertRaises(subject.SupervisorError) as caught:
            self.invoke(boundary, ["submit", self.request_id])
        self.assertIn("GitHub Actions intake is not installed", str(caught.exception))
        self.assertEqual(boundary.launch_count, 0)

    def test_crash_before_observation_recovers_same_child_without_relaunch(self):
        boundary = LocalBoundary(helper=self.helper, crash_before_observation=True)
        with self.assertRaises(subject.CrashBeforeObservation):
            self.invoke(boundary, ["submit", self.request_id])
        attempts = list(self.attempts.iterdir())
        self.assertEqual(len(attempts), 1)
        attempt_id = attempts[0].name
        self.assertEqual(boundary.launch_count, 1)
        recovered, _ = self.invoke(boundary, ["observe", attempt_id])
        self.assertEqual(recovered["status"], "completed")
        self.assertEqual(boundary.launch_count, 1)
        self.assertEqual(recovered["attempt_id"], attempt_id)

    def test_cancel_revalidates_exact_invocation_and_keeps_one_launch(self):
        boundary = LocalBoundary(helper=self.helper, crash_before_observation=True)
        with self.assertRaises(subject.CrashBeforeObservation):
            self.invoke(boundary, ["submit", self.request_id])
        attempt_id = next(self.attempts.iterdir()).name
        cancelled, _ = self.invoke(boundary, ["cancel", attempt_id])
        self.assertEqual(cancelled["status"], "completed")
        self.assertEqual(cancelled["business_outcome"], "not-reviewed")
        self.assertEqual(boundary.cancel_count, 1)
        self.assertEqual(boundary.launch_count, 1)

    def test_unfinished_generation_fences_a_competing_request(self):
        boundary = LocalBoundary(helper=self.helper, crash_before_observation=True)
        with self.assertRaises(subject.CrashBeforeObservation):
            self.invoke(boundary, ["submit", self.request_id])
        other_id = str(uuid.uuid4())
        self._write_request(request_id=other_id)
        competing, _ = self.invoke(boundary, ["submit", other_id])
        self.assertEqual(competing["status"], "busy")
        self.assertEqual(boundary.launch_count, 1)
        recovered, _ = self.invoke(boundary, ["observe", next(self.attempts.iterdir()).name])
        self.assertEqual(recovered["status"], "completed")

    def test_surviving_descendant_or_unknown_closure_stays_fenced(self):
        boundary = LeakingBoundary(helper=self.helper)
        result, _ = self.invoke(boundary, ["submit", self.request_id])
        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["phase"], "uncertain")
        duplicate, _ = self.invoke(boundary, ["submit", self.request_id])
        self.assertEqual(duplicate["status"], "busy")
        self.assertEqual(boundary.launch_count, 1)

    def test_output_symlink_is_not_a_reviewed_result(self):
        boundary = MutatingOutputBoundary(helper=self.helper)
        result, _ = self.invoke(boundary, ["submit", self.request_id])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["business_outcome"], "not-reviewed")
        evidence = self.attempts / result["attempt_id"] / "evidence"
        self.assertEqual(list(evidence.iterdir()), [])

    def test_terminal_duplicate_does_not_clobber_or_relaunch(self):
        boundary = LocalBoundary(helper=self.helper)
        result, _ = self.invoke(boundary, ["submit", self.request_id])
        input_path = self.admissions / self.request_id / "input.json"
        input_path.chmod(0o600)
        input_path.write_bytes(input_path.read_bytes() + b"changed")
        input_path.chmod(0o440)
        with self.assertRaises(subject.SupervisorError) as caught:
            self.invoke(boundary, ["submit", self.request_id])
        self.assertIn("complete input bytes differ", str(caught.exception))
        self.assertEqual(boundary.launch_count, 1)
        self.assertTrue((self.attempts / result["attempt_id"] / "evidence" / "result.json").exists())

    def test_checkpoint_failure_retains_prelaunch_fence_and_no_launch(self):
        boundary = FailingCheckpointBoundary(helper=self.helper)
        with self.assertRaises(subject.SupervisorError) as caught:
            self.invoke(boundary, ["submit", self.request_id])
        self.assertIn("checkpoint fsync failure", str(caught.exception))
        self.assertEqual(boundary.launch_count, 0)
        self.assertEqual(len(list(self.attempts.iterdir())), 1)

    def test_terminal_evidence_corruption_stays_fenced_after_restart(self):
        boundary = LocalBoundary(helper=self.helper)
        result, _ = self.invoke(boundary, ["submit", self.request_id])
        evidence = self.attempts / result["attempt_id"] / "evidence" / "result.json"
        evidence.chmod(0o600)
        evidence.write_bytes(b"corrupt\n")
        evidence.chmod(0o400)
        with self.assertRaises(subject.SupervisorError) as caught:
            self.invoke(boundary, ["observe", result["attempt_id"]])
        self.assertIn("terminal evidence readback differs", str(caught.exception))
        self.assertEqual(boundary.launch_count, 1)

    def test_cli_has_no_ambient_override_or_arbitrary_selector(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(subject.main(["submit", self.request_id, "--timeout", "1"]), 2)
        self.assertIn("no path, command, provider", output.getvalue())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(subject.main(["status"]), 0)
        self.assertIn('"schema":"lmdj.pr-agent-supervisor-response.v1"', output.getvalue())


if __name__ == "__main__":
    unittest.main()
