#!/usr/bin/env python3
"""Actual Git export, durable reservation and canonical Assembly generation."""
from copy import deepcopy
from hashlib import sha1, sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import version
from tools.release.candidate import CATALOG
from tools.release.candidate_inputs import CandidateInputs
from tools.release.candidate_material import CandidateBuildMaterial
from tools.release import candidate_material
from tools.release.model import canonical_json, canonical_sha256
from tools.release.orchestration import JournalError


class MaterialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = tempfile.TemporaryDirectory(prefix="lmdj-material-template-")
        cls.addClassCleanup(cls.template.cleanup)
        cls.source = Path(cls.template.name)
        inputs = CandidateInputs(ROOT)
        revision = inputs.git("rev-parse", "HEAD").decode().strip()
        frozen = inputs.freeze(revision)
        CandidateBuildMaterial(ROOT, cls.source / "unused")._export(frozen, cls.source)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lmdj-material-test-")
        self.addCleanup(self.temp.cleanup)
        self.container = Path(self.temp.name).resolve()
        self.root = self.container / "source"
        shutil.copytree(self.source, self.root)
        self.state = self.container / "state"
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.base = self.commit()
        self.inputs = CandidateInputs(self.root)
        self.frozen = self.inputs.freeze(self.base)
        self.current = version.load_version(self.root / "products/lmdj/version.json")
        self.tool = CandidateBuildMaterial(self.root, self.state)
        self.request = {"id":"release-1", "repository":"example/product", "actor_id":123,
                        "authority_ref":"thread:release-1", "policy_digest":"a" * 64,
                        "control_revision":"b" * 40, "base_revision":self.base,
                        "mode":"new", "requested_tag":None}
        self.tool.reservations.enroll(self.request["repository"])

    def git(self, *args):
        env = {key:value for key,value in os.environ.items() if key in ("PATH", "TMPDIR", "TEMP", "TMP")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        return subprocess.check_output(["git", "-c", "core.hooksPath=" + os.devnull,
                                       "-C", str(self.root), *args], env=env, stderr=subprocess.DEVNULL).decode().strip()

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-m", "fixture")
        return self.git("rev-parse", "HEAD")

    def prepare(self):
        return self.tool.prepare(self.request, self.frozen, self.base)

    def test_real_generators_produce_exact_candidate_files_and_valid_lock(self):
        before = (self.git("status", "--porcelain"), self.git("write-tree"), self.git("show-ref"))
        result = self.prepare()
        expected = version.ProductVersion(self.current.milestone, self.current.minor, self.current.build + 1, 0)
        self.assertEqual(result["binding"]["product_build"], str(expected))
        from tools.release.candidate_workspace import FILES
        self.assertEqual(set(result["files"]), FILES)
        self.assertEqual(before, (self.git("status", "--porcelain"), self.git("write-tree"), self.git("show-ref")))
        self.assertEqual(result["sha256"], canonical_sha256(result["binding"]))
        for item in result["binding"]["files"]:
            raw = result["files"][item["path"]]
            self.assertEqual(item, {"path":item["path"], "size":len(raw), "sha256":sha256(raw).hexdigest()})
        for name, raw in result["files"].items():
            (self.root / name).write_bytes(raw)
        self.assertEqual(version.load_version(self.root / "products/lmdj/version.json"), expected)
        assembly_path = self.root / "products/lmdj/assembly.json"
        assembly = version._verify_assembly(expected, assembly_path)
        version._verify_lock(expected, assembly_path, assembly,
                             self.root / "products/lmdj/assembly.lock.json", repo_root=self.root)
        # Re-rendering through the existing canonical generators yields the
        # same bytes, not merely a self-consistent planner digest.
        compiled = version._render_compiled_assembly(expected, assembly, repo_root=self.root)
        self.assertEqual(compiled, result["files"]["products/lmdj/src/compiled_assembly.cpp"])
        lock = version._lock_document(expected, assembly_path, assembly, compiled, repo_root=self.root)
        self.assertEqual(canonical_json(lock), result["files"]["products/lmdj/assembly.lock.json"])
        # The Runtime identity moves with the reserved build and matches the
        # trusted generator run against the materialized tree (#1531).
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "identity_check", ROOT / "tools/web-runtime/generate_runtime_identity.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.generate(self.root), json.loads(
            result["files"]["products/lmdj/generated/web-runtime-identity.json"]))
        self.assertEqual(module.canonical_json(json.loads(
            result["files"]["products/lmdj/generated/web-runtime-identity.json"])),
            result["files"]["products/lmdj/generated/web-runtime-identity.json"])

    def test_existing_default_root_verification_remains_unchanged(self):
        current = version.load_version(ROOT / "products/lmdj/version.json")
        assembly = version._verify_assembly(current, ROOT / "products/lmdj/assembly.json")
        version._verify_lock(current, ROOT / "products/lmdj/assembly.json", assembly,
                             ROOT / "products/lmdj/assembly.lock.json")

    def test_passive_root_not_controller_root_owns_component_hashes(self):
        manifest = self.root / "packages/foundation/module.json"
        manifest.write_bytes(manifest.read_bytes() + b" \n")
        assembly_path = self.root / "products/lmdj/assembly.json"
        assembly = json.loads(assembly_path.read_bytes())
        compiled = version._render_compiled_assembly(self.current, assembly, repo_root=self.root)
        lock = version._lock_document(self.current, assembly_path, assembly, compiled, repo_root=self.root)
        (self.root / "products/lmdj/assembly.lock.json").write_bytes(canonical_json(lock))
        self.base = self.commit()
        self.frozen = self.inputs.freeze(self.base)
        self.request["base_revision"] = self.base
        result = self.prepare()
        locked = json.loads(result["files"]["products/lmdj/assembly.lock.json"])
        foundation = next(item for item in locked["modules"] if item["id"] == "foundation")
        self.assertEqual(foundation["sha256"], sha256(manifest.read_bytes()).hexdigest())
        self.assertNotEqual(foundation["sha256"], sha256((ROOT / "packages/foundation/module.json").read_bytes()).hexdigest())

    def test_dirty_worktree_and_untracked_manifests_are_not_generator_inputs(self):
        expected = self.prepare()
        (self.root / "products/lmdj/version.json").write_bytes(b"not committed")
        extra = self.root / "apps/injected/module.json"
        extra.parent.mkdir(parents=True)
        extra.write_bytes(b"not committed")
        self.assertEqual(self.prepare(), expected)
        self.assertEqual(extra.read_bytes(), b"not committed")

    def test_resume_reuses_reservation_and_material_bytes(self):
        first = self.prepare()
        raw = (self.state / CATALOG).read_bytes()
        self.tool = CandidateBuildMaterial(self.root, self.state)
        self.assertEqual(self.prepare(), first)
        self.assertEqual((self.state / CATALOG).read_bytes(), raw)

    def test_invalid_canonical_assembly_retains_number_and_writes_no_source(self):
        assembly_path = self.root / "products/lmdj/assembly.json"
        assembly = json.loads(assembly_path.read_bytes())
        assembly["providers"][0]["version"] = "999.0.0"
        assembly_path.write_bytes(canonical_json(assembly))
        self.base = self.commit()
        self.frozen = self.inputs.freeze(self.base)
        self.request["base_revision"] = self.base
        before = self.git("write-tree")
        for _ in range(2):
            with self.assertRaisesRegex(JournalError, "canonical candidate"):
                self.prepare()
        catalogue = json.loads((self.state / CATALOG).read_bytes())["catalogue"]
        self.assertEqual(len(catalogue["reservations"]), 1)
        self.assertEqual(self.git("write-tree"), before)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_stale_compiled_input_is_not_silently_repaired(self):
        filename = self.root / "products/lmdj/src/compiled_assembly.cpp"
        filename.write_bytes(filename.read_bytes() + b"// unexpected\n")
        self.base = self.commit()
        self.frozen = self.inputs.freeze(self.base)
        self.request["base_revision"] = self.base
        with self.assertRaisesRegex(JournalError, "canonical candidate"):
            self.prepare()
        self.assertTrue(filename.read_bytes().endswith(b"// unexpected\n"))

    def test_no_candidate_python_or_shell_is_executed(self):
        script = self.root / "products/lmdj/evil.py"
        script.write_text("raise RuntimeError('candidate code executed')\n")
        self.base = self.commit()
        self.frozen = self.inputs.freeze(self.base)
        self.request["base_revision"] = self.base
        self.prepare()

    def test_reserved_product_line_and_patch_are_not_arbitrary(self):
        for reserved in (self.current, version.ProductVersion(self.current.milestone + 1, self.current.minor, self.current.build + 1, 0),
                         version.ProductVersion(self.current.milestone, self.current.minor, self.current.build + 1, 1)):
            with self.subTest(reserved=reserved), self.assertRaisesRegex(ValueError, "reservation"):
                version.render_build_material(self.root, self.current, reserved)

    def test_export_rejects_wrong_git_blob_bytes(self):
        original = self.tool.inputs.git
        def corrupt(*args, **kwargs):
            raw = original(*args, **kwargs)
            if args == ("cat-file", "--batch"):
                offset = raw.index(b"\n") + 1
                raw = raw[:offset] + bytes([raw[offset] ^ 1]) + raw[offset + 1:]
            return raw
        with patch.object(self.tool.inputs, "git", side_effect=corrupt):
            with self.assertRaisesRegex(JournalError, "Git identity"):
                self.prepare()

    def test_export_bound_counts_repeated_materialized_paths(self):
        raw = b"12345678"
        oid = sha1(b"blob 8\0" + raw).hexdigest()
        entries = [{"path":f"products/lmdj/file-{i}", "mode":"100644", "object":oid} for i in range(3)]
        def source(*args, **kwargs):
            if args == ("cat-file", "--batch"):
                return f"{oid} blob 8\n".encode() + raw + b"\n"
            return f"{oid} blob 8\n".encode()
        with patch.object(candidate_material, "MAX_MATERIAL_BYTES", 16), patch.object(self.tool.inputs, "git", side_effect=source) as reader:
            good = self.container / "good-export"
            self.tool._export({"entries":entries[:2]}, good)
            self.assertEqual((good / entries[0]["path"]).read_bytes(), raw)
            self.assertEqual((good / entries[1]["path"]).read_bytes(), raw)
            reader.reset_mock()
            bad = self.container / "bad-export"
            with self.assertRaisesRegex(JournalError, "inventory exceeds"):
                self.tool._export({"entries":entries}, bad)
            self.assertFalse(bad.exists())
            self.assertFalse(any(call.args == ("cat-file", "--batch") for call in reader.call_args_list))


if __name__ == "__main__":
    unittest.main()
