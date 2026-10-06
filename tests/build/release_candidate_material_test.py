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
from tools.release.candidate_material_scope import P1_MATERIAL_SCOPE, HEADER_INPUTS
from tools.release import candidate_material
from tools.release.model import canonical_json, canonical_sha256
from tools.release.orchestration import JournalError


class MaterialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = tempfile.TemporaryDirectory(prefix="lmdj-material-template-")
        cls.addClassCleanup(cls.template.cleanup)
        cls.source = Path(cls.template.name)
        scope = getattr(cls, "material_scope", None)
        inputs = CandidateInputs(ROOT, material_scope=scope)
        revision = inputs.git("rev-parse", "HEAD").decode().strip()
        frozen = inputs.freeze(revision)
        CandidateBuildMaterial(ROOT, cls.source / "unused", material_scope=scope)._export(frozen, cls.source)

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
        scope = getattr(self, "material_scope", None)
        self.inputs = CandidateInputs(self.root, material_scope=scope)
        self.frozen = self.inputs.freeze(self.base)
        self.current = version.load_version(self.root / "products/lmdj/version.json")
        self.tool = CandidateBuildMaterial(self.root, self.state, material_scope=scope)
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
        names = {"products/lmdj/version.json", "products/lmdj/assembly.json",
                 "products/lmdj/assembly.lock.json", "products/lmdj/src/compiled_assembly.cpp",
                 "products/lmdj/generated/web-runtime-identity.json",
                 "products/lmdj/generated/web-runtime-identity.mjs"}
        self.assertEqual(set(result["files"]), names)
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
            "identity_check", self.root / candidate_material.RUNTIME_IDENTITY_GENERATOR)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.generate(self.root), json.loads(
            result["files"]["products/lmdj/generated/web-runtime-identity.json"]))
        self.assertEqual(module.canonical_json(json.loads(
            result["files"]["products/lmdj/generated/web-runtime-identity.json"])),
            result["files"]["products/lmdj/generated/web-runtime-identity.json"])

        # Check both exported identity files, including the MJS projection,
        # after materializing the complete reserved candidate.
        check = subprocess.run([sys.executable, str(self.root / candidate_material.RUNTIME_IDENTITY_GENERATOR),
                                "--repo-root", str(self.root), "--check"],
                               capture_output=True, text=True)
        self.assertEqual(check.returncode, 0,
                         "why: exported Runtime identity pair is stale; "
                         "remedy: regenerate both files from the reserved candidate: " + check.stderr)

    def test_existing_default_root_verification_remains_unchanged(self):
        current = version.load_version(ROOT / "products/lmdj/version.json")
        assembly = version._verify_assembly(current, ROOT / "products/lmdj/assembly.json")
        version._verify_lock(current, ROOT / "products/lmdj/assembly.json", assembly,
                             ROOT / "products/lmdj/assembly.lock.json")

    def test_frozen_future_host_selects_offline_asset_without_extra_material_outputs(self):
        # Only this throwaway Git repository selects a distinct future Host
        # shape, including when the frozen source already contains Host 6.
        # The class template exports HEAD; copy current Source before freezing
        # so precommit verification exercises the new passive policy as well.
        for name in (candidate_material.RUNTIME_IDENTITY_GENERATOR,
                     "tools/web-runtime/runtime-identity.json"):
            shutil.copyfile(ROOT / name, self.root / name)
        manifest_path = self.root / "apps/creator-web/module.json"
        manifest = json.loads(manifest_path.read_bytes())
        future_host_version = f"{max(6, int(manifest['version'].split('.')[0]) + 1)}.0.0"
        self.assertNotEqual(future_host_version, manifest["version"])
        manifest["version"] = future_host_version
        manifest_path.write_bytes(canonical_json(manifest))
        assembly_path = self.root / "products/lmdj/assembly.json"
        assembly = json.loads(assembly_path.read_bytes())
        next(host for host in assembly["hosts"] if host["id"] == "creator-web")["version"] = future_host_version
        assembly_path.write_bytes(canonical_json(assembly))
        compiled = version._render_compiled_assembly(self.current, assembly, repo_root=self.root)
        (self.root / "products/lmdj/src/compiled_assembly.cpp").write_bytes(compiled)
        lock = version._lock_document(self.current, assembly_path, assembly, compiled, repo_root=self.root)
        (self.root / "products/lmdj/assembly.lock.json").write_bytes(canonical_json(lock))
        self.base = self.commit()
        self.frozen = self.inputs.freeze(self.base)
        self.request["base_revision"] = self.base
        before = (self.git("status", "--porcelain"), self.git("write-tree"), self.git("show-ref"))
        result = self.prepare()
        self.assertEqual(before, (self.git("status", "--porcelain"), self.git("write-tree"), self.git("show-ref")))
        identity = json.loads(result["files"]["products/lmdj/generated/web-runtime-identity.json"])
        creator = identity["hosts"]["creator-web"]
        self.assertEqual(creator["version"], future_host_version)
        policy = json.loads((self.root / "tools/web-runtime/runtime-identity.json").read_bytes())
        self.assertEqual(creator["expected_assets"], [
            *policy["hosts"]["creator-web"]["expected_assets"],
            policy["hosts"]["creator-web"]["offline_asset"],
        ])
        self.assertEqual(len(creator["expected_assets"]), 8)
        self.assertEqual(set(result["files"]), {
            "products/lmdj/version.json", "products/lmdj/assembly.json",
            "products/lmdj/assembly.lock.json", "products/lmdj/src/compiled_assembly.cpp",
            "products/lmdj/generated/web-runtime-identity.json",
            "products/lmdj/generated/web-runtime-identity.mjs",
        })
        self.assertEqual(identity["product_build"], result["binding"]["product_build"])
        for name, raw in result["files"].items():
            (self.root / name).write_bytes(raw)
        check = subprocess.run([sys.executable, str(self.root / candidate_material.RUNTIME_IDENTITY_GENERATOR),
                                "--repo-root", str(self.root), "--check"], capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stderr)

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

    def test_identity_generator_failure_retains_reservation_and_writes_no_source(self):
        generator = self.root / candidate_material.RUNTIME_IDENTITY_GENERATOR
        generator.write_text("raise RuntimeError('fixture identity failure')\n")
        self.base = self.commit()
        self.frozen = self.inputs.freeze(self.base)
        self.request["base_revision"] = self.base
        before = (self.git("status", "--porcelain"), self.git("write-tree"), self.git("show-ref"))
        for _ in range(2):
            with self.assertRaisesRegex(JournalError, "Runtime identity generation refused"):
                self.prepare()
        catalogue = json.loads((self.state / CATALOG).read_bytes())["catalogue"]
        self.assertEqual(len(catalogue["reservations"]), 1)
        self.assertEqual(before, (self.git("status", "--porcelain"), self.git("write-tree"), self.git("show-ref")))

    def test_identity_generator_inputs_stay_far_under_the_export_bound(self):
        # Pins the review fact-check on the two newly selected canonical
        # inputs: they count against _export's MAX_MATERIAL_BYTES (64 MiB).
        # If they ever grow to matter, this names it long before a cut
        # fails opaquely with "input inventory exceeds its byte bound".
        total = sum((ROOT / name).stat().st_size for name in (
            "tools/web-runtime/emscripten.lock.json",
            "tools/web-runtime/runtime-identity.json"))
        self.assertLess(total, 1024 * 1024,
                        "why: canonical identity inputs exceed their 1 MiB regression budget; "
                        "remedy: remove unintended input growth before cutting a candidate")

    def test_identity_generator_is_a_pure_data_transformer(self):
        # The cut loads this generator from the frozen export and applies it
        # to materialized candidate data. Its maintained source
        # must stay free of dynamic execution and subprocess escape hatches.
        # Scan non-comment directives, per gate-matches-its-own-prose.
        source = (ROOT / "tools/web-runtime/generate_runtime_identity.py").read_text()
        directives = "\n".join(
            line for line in source.splitlines()
            if not line.lstrip().startswith("#"))
        for banned in ("subprocess", "importlib", "__import__",
                       "exec(", "eval(", "os.system", "popen", "ctypes"):
            self.assertNotIn(banned, directives,
                             "why: Runtime identity generator contains a dynamic execution hook; "
                             "remedy: keep the generator a data transformer")

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


class CoordinatedFixture(unittest.TestCase):
    material_scope = P1_MATERIAL_SCOPE
    @classmethod
    def setUpClass(cls):
        MaterialTest.setUpClass.__func__(cls)
        inputs = CandidateInputs(ROOT)
        revision = inputs.git("rev-parse", "HEAD").decode().strip()
        for host in ("creator-web", "web-runtime-host"):
            name = f"apps/{host}/CHANGELOG.md"
            if inputs.git("ls-tree", revision, "--", name):
                (cls.source / name).write_bytes(inputs.git("show", revision + ":" + name))
        for name in ("apps/core-mcp/pyproject.toml", "apps/core-mcp/lmdj_core_mcp/__init__.py"):
            target = cls.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(inputs.git("show", revision + ":" + name))
    setUp = MaterialTest.setUp
    git = MaterialTest.git
    commit = MaterialTest.commit
    prepare = MaterialTest.prepare


class CoordinatedMaterialTest(CoordinatedFixture):
    def test_mcp_package_identities_follow_the_allocated_host(self):
        import ast
        import tomllib
        names = ("apps/core-mcp/pyproject.toml", "apps/core-mcp/lmdj_core_mcp/__init__.py")
        before = {name:(self.root / name).read_bytes() for name in names}
        result = self.prepare()
        host = json.loads(result["files"]["apps/core-mcp/module.json"])["version"]
        project = tomllib.loads(result["files"][names[0]].decode())
        self.assertEqual(project["project"]["version"], host)
        tree = ast.parse(result["files"][names[1]])
        assignment, = [node for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == "__version__"
                               for target in node.targets)]
        self.assertEqual(ast.literal_eval(assignment.value), host)
        old_host = json.loads((self.root / "apps/core-mcp/module.json").read_bytes())["version"]
        for name in names:
            self.assertEqual(result["files"][name].replace(json.dumps(host).encode(),
                             json.dumps(old_host).encode(), 1), before[name])

    def test_mcp_project_version_rewrite_targets_the_field_instead_of_a_comment(self):
        import tomllib
        name = "apps/core-mcp/pyproject.toml"
        old_host = json.loads((self.root / "apps/core-mcp/module.json").read_bytes())["version"]
        before = (self.root / name).read_bytes().replace(
            json.dumps(old_host).encode(), repr(old_host).encode(), 1)
        before += ("\n# version = " + json.dumps(old_host) + "\n").encode()
        (self.root / name).write_bytes(before)
        self.base = self.commit()
        self.request["base_revision"] = self.base
        self.frozen = self.inputs.freeze(self.base)
        result = self.prepare()
        host = json.loads(result["files"]["apps/core-mcp/module.json"])["version"]
        self.assertEqual(tomllib.loads(result["files"][name].decode())["project"]["version"], host)
        self.assertEqual(result["files"][name], before.replace(
            repr(old_host).encode(), repr(host).encode(), 1))

    def test_mcp_runtime_version_utf8_bom_is_refused(self):
        name = "apps/core-mcp/lmdj_core_mcp/__init__.py"
        old_host = json.loads((self.root / "apps/core-mcp/module.json").read_bytes())["version"]
        (self.root / name).write_bytes(b"\xef\xbb\xbf" +
                                     ("__version__ = " + json.dumps(old_host) + "\n").encode())
        self.base = self.commit()
        self.request["base_revision"] = self.base
        self.frozen = self.inputs.freeze(self.base)
        with self.assertRaisesRegex(JournalError, "canonical candidate material generation refused"):
            self.prepare()

    def test_mcp_runtime_version_annotation_override_is_refused(self):
        name = "apps/core-mcp/lmdj_core_mcp/__init__.py"
        old_host = json.loads((self.root / "apps/core-mcp/module.json").read_bytes())["version"]
        with (self.root / name).open("a") as stream:
            stream.write("\n__version__: str = " + json.dumps(old_host) + "\n")
        self.base = self.commit()
        self.request["base_revision"] = self.base
        self.frozen = self.inputs.freeze(self.base)
        with self.assertRaisesRegex(JournalError, "canonical candidate material generation refused"):
            self.prepare()

    def test_mcp_runtime_version_nested_override_is_refused(self):
        name = "apps/core-mcp/lmdj_core_mcp/__init__.py"
        old_host = json.loads((self.root / "apps/core-mcp/module.json").read_bytes())["version"]
        with (self.root / name).open("a") as stream:
            stream.write("\nif True:\n    __version__ = " + json.dumps(old_host) + "\n")
        self.base = self.commit()
        self.request["base_revision"] = self.base
        self.frozen = self.inputs.freeze(self.base)
        with self.assertRaisesRegex(JournalError, "canonical candidate material generation refused"):
            self.prepare()

    def test_mcp_project_version_mismatch_is_refused(self):
        name = "apps/core-mcp/pyproject.toml"
        raw = (self.root / name).read_bytes()
        old_host = json.loads((self.root / "apps/core-mcp/module.json").read_bytes())["version"]
        (self.root / name).write_bytes(raw.replace(json.dumps(old_host).encode(), b'"0.0.0"', 1))
        self.base = self.commit()
        self.request["base_revision"] = self.base
        self.frozen = self.inputs.freeze(self.base)
        with self.assertRaisesRegex(JournalError, "canonical candidate material generation refused"):
            self.prepare()

    def test_mcp_runtime_version_expression_is_not_executed(self):
        name = "apps/core-mcp/lmdj_core_mcp/__init__.py"
        marker = self.container / "must-not-execute"
        (self.root / name).write_text('__version__ = __import__("pathlib").Path(' +
                                     repr(str(marker)) + ').touch()\n')
        self.base = self.commit()
        self.request["base_revision"] = self.base
        self.frozen = self.inputs.freeze(self.base)
        with self.assertRaisesRegex(JournalError, "canonical candidate material generation refused"):
            self.prepare()
        self.assertFalse(marker.exists())

    def test_actual_graph_material_has_exact_24_paths_and_far_side_identities(self):
        import ast
        from tools.release.candidate_workspace import FILES
        before = self.git("write-tree"), self.git("show-ref"), self.git("status", "--porcelain")
        result = self.prepare()
        self.assertEqual(len(result["files"]), 24)
        self.assertEqual(set(result["files"]), FILES | version.P1_BUILD_MATERIAL_FILES)
        self.assertEqual(result["binding"]["material_scope"], P1_MATERIAL_SCOPE)
        old_test = (self.root / "tests/build/version_test.py").read_bytes()
        npm_before = {name:json.loads((self.root / name).read_bytes()) for name in
                      ("apps/creator-web/package.json", "apps/creator-web/package-lock.json")}
        profiles = {name:(self.root / name).read_bytes() for name in
                    ("products/lmdj/src/cardputer_assembly.cpp", "apps/cardputer-host/CMakeLists.txt")}
        headers = {name:(self.root / name).read_bytes() for name in HEADER_INPUTS}
        self.assertEqual(before, (self.git("write-tree"), self.git("show-ref"), self.git("status", "--porcelain")))
        for name, raw in result["files"].items():
            self.assertNotEqual(raw, (self.root / name).read_bytes(), name)
            (self.root / name).write_bytes(raw)
        current = version.load_version(self.root / "products/lmdj/version.json")
        assembly_path = self.root / "products/lmdj/assembly.json"
        assembly = version._verify_assembly(current, assembly_path)
        version._verify_lock(current, assembly_path, assembly,
                             self.root / "products/lmdj/assembly.lock.json", repo_root=self.root)
        identity = json.loads(result["files"]["products/lmdj/generated/web-runtime-identity.json"])
        self.assertEqual(identity["product_build"], str(current))
        creator = identity["hosts"]["creator-web"]
        self.assertEqual(len(creator["expected_assets"]), 8)
        self.assertEqual(sum(item["role"] == "offline_worker" for item in creator["expected_assets"]), 1)
        old_tree, new_tree = ast.parse(old_test), ast.parse(result["files"]["tests/build/version_test.py"])
        def baseline(tree):
            node = next(node for node in tree.body if isinstance(node, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "expected_modules" for t in node.targets))
            value = ast.literal_eval(node.value)
            tree.body.remove(node)
            return value, ast.dump(tree, include_attributes=False)
        old_rows, old_logic = baseline(old_tree)
        new_rows, new_logic = baseline(new_tree)
        self.assertEqual(old_logic, new_logic)
        self.assertEqual(old_rows.keys(), new_rows.keys())
        for path, row in new_rows.items():
            manifest = json.loads((self.root / path).read_bytes())
            self.assertEqual(row, (manifest["module"], manifest["version"], manifest["api_version"], manifest["dependencies"]))
            self.assertEqual((row[0], row[2], row[3].keys()),
                             (old_rows[path][0], old_rows[path][2], old_rows[path][3].keys()))
        for name, old in npm_before.items():
            after = json.loads((self.root / name).read_bytes())
            after["version"] = old["version"]
            if name.endswith("package-lock.json"):
                after["packages"][""]["version"] = old["packages"][""]["version"]
            self.assertEqual(after, old)
        cardputer_version = json.loads((self.root / "apps/cardputer-host/module.json").read_bytes())["version"]
        old_cardputer_version = json.loads(self.git("show", self.base + ":apps/cardputer-host/module.json"))["version"]
        new_sha = sha256(result["files"]["products/lmdj/assembly.json"]).hexdigest()
        old_sha = sha256(self.git("show", self.base + ":products/lmdj/assembly.json").encode() + b"\n").hexdigest()
        for name, old in profiles.items():
            expected = old.replace(str(self.current).encode(), str(current).encode())
            if name.endswith(".cpp"):
                expected = expected.replace(old_cardputer_version.encode(), cardputer_version.encode()).replace(old_sha.encode(), new_sha.encode())
            self.assertEqual((self.root / name).read_bytes(), expected)
        for name, old in headers.items():
            old_header = next(line for line in old.splitlines() if line.startswith(b"Host: "))
            after = (self.root / name).read_bytes()
            new_header = next(line for line in after.splitlines() if line.startswith(b"Host: "))
            self.assertEqual(after.replace(new_header, old_header, 1), old)
        owning = ROOT / "apps/docs-site/scripts/lib/host-changelogs.mjs"
        code = "import {projectChangelogs} from " + json.dumps(owning.as_uri()) + "; await projectChangelogs(process.argv[1]);"
        subprocess.run(["node", "--input-type=module", "-e", code, str(self.root)],
                       check=True, capture_output=True)

    def test_scope_projection_freezes_headers_without_changing_legacy_projection(self):
        from tools.release.candidate_inputs import CandidateInputError
        legacy = CandidateInputs(self.root)
        legacy_frozen = legacy.freeze(self.base)
        self.assertNotIn("material_scope", legacy_frozen)
        self.assertFalse(HEADER_INPUTS.intersection(e["path"] for e in legacy_frozen["entries"]))
        self.assertTrue(HEADER_INPUTS <= {e["path"] for e in self.frozen["entries"]})
        page = self.root / sorted(HEADER_INPUTS)[0]
        page.write_bytes(page.read_bytes() + b"\nChanged source projection.\n")
        current = self.commit()
        legacy.verify(legacy_frozen, current)
        with self.assertRaisesRegex(CandidateInputError, "changed since"):
            self.inputs.verify(self.frozen, current)
        self.assertEqual(legacy.freeze(self.base), legacy_frozen)
        self.assertEqual(self.inputs.freeze(self.base), self.frozen)

    def test_old_lock_is_verified_before_any_prospective_pin_and_failed_number_remains(self):
        path = self.root / "products/lmdj/assembly.lock.json"
        broken = json.loads(path.read_bytes())
        broken["assembly_sha256"] = "0" * 64
        path.write_bytes(canonical_json(broken))
        base = self.commit()
        frozen = self.inputs.freeze(base)
        request = dict(self.request, base_revision=base)
        before = self.git("write-tree"), self.git("status", "--porcelain")
        with self.assertRaisesRegex(JournalError, "canonical candidate material generation refused"):
            self.tool.prepare(request, frozen, base)
        self.assertEqual(before, (self.git("write-tree"), self.git("status", "--porcelain")))
        self.assertEqual(str(self.tool.reservations.recorded(request)),
                         f"{self.current.milestone}.{self.current.minor}.{self.current.build + 1}.0")

    def test_new_consumer_refuses_closed_closure_without_writing_source(self):
        path = self.root / "apps/unexpected-host/module.json"
        path.parent.mkdir(parents=True)
        document = json.loads((self.root / "apps/creator-web/module.json").read_bytes())
        document["module"] = "unexpected-host"
        path.write_bytes(canonical_json(document))
        base = self.commit()
        before = self.git("write-tree")
        with self.assertRaisesRegex(JournalError, "canonical candidate material generation refused"):
            self.tool.prepare(dict(self.request, base_revision=base), self.inputs.freeze(base), base)
        self.assertEqual(self.git("write-tree"), before)

    def test_unknown_scope_and_original_reservation_rebind_are_refused(self):
        with self.assertRaisesRegex(ValueError, "scope is unknown"):
            CandidateBuildMaterial(self.root, self.state, material_scope=dict(P1_MATERIAL_SCOPE, files=[]))
        self.prepare()
        legacy = CandidateBuildMaterial(self.root, self.state)
        before = (self.state / CATALOG).read_bytes()
        with self.assertRaises(JournalError):
            legacy.prepare(self.request, legacy.inputs.freeze(self.base), self.base)
        self.assertEqual((self.state / CATALOG).read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
