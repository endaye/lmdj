#!/usr/bin/env python3
"""Real-Git tests for the complete PR-Agent input producer."""

from __future__ import annotations

import copy
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import change_scope
import pr_agent_input as producer
import pr_agent_review as adapter


class RealGit:
    def __init__(self, path: Path):
        self.path = path

    def run(self, *args: str, check: bool = True) -> bytes:
        result = subprocess.run(["git", *args], cwd=self.path, capture_output=True)
        if check and result.returncode:
            raise AssertionError(result.stderr.decode(errors="replace"))
        return result.stdout

    def text(self, *args: str) -> str:
        return self.run(*args).decode().strip()

    def commit(self, message: str) -> str:
        self.run("-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-qm", message)
        return self.text("rev-parse", "HEAD")


class ProducerTests(unittest.TestCase):
    GENERATED_CHANGES = {
        "apps/architecture-portal/versioned_docs/version-1.0.57.0/intro.md": b"snapshot page\n",
        "apps/architecture-portal/versioned_metadata/version-1.0.57.0.json": b"{}\n",
        "apps/architecture-portal/versioned_sidebars/version-1.0.57.0-sidebars.json": b"{}\n",
        "apps/architecture-portal/versioned_provenance/version-1.0.57.0.json": b"{}\n",
        "apps/architecture-portal/static/versions/1.0.57.0/manifest.json": b"{}\n",
        "products/lmdj/generated/web-runtime-identity.mjs": b"export {};\n",
        "products/lmdj/src/compiled_assembly.cpp": b"// rendered assembly\n",
        "products/lmdj/src/cardputer_assembly.cpp": b"// rendered assembly\n",
        "products/lmdj/assembly.lock.json": b"{}\n",
    }

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lmdj-pr-agent-input-test-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.git = RealGit(self.repo)
        self.git.run("init", "-q", "-b", "main")

    def identity(self, base: str, head: str, control: str | None = None) -> dict[str, object]:
        return {
            "repository": "endaye/lmdj",
            "pull_request": 1151,
            "base_sha": base,
            "head_sha": head,
            "control_sha": control or head,
            "run_id": "real-git-test",
            "run_attempt": 1,
        }

    def commit_files(self, files: dict[str, bytes], message: str) -> str:
        for name, content in files.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.git.run("add", "--", *files)
        return self.git.commit(message)

    def commit_raw_files(self, files: dict[bytes, bytes], parent: str | None = None) -> str:
        entries = []
        for name, content in sorted(files.items()):
            blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=self.repo,
                                  input=content, capture_output=True, check=True).stdout.strip()
            entries.append(b"100644 blob " + blob + b"\t" + name + b"\0")
        tree = subprocess.run(["git", "mktree", "-z"], cwd=self.repo, input=b"".join(entries),
                              capture_output=True, check=True).stdout.strip()
        command = ["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                   "commit-tree", tree.decode()]
        if parent is not None:
            command.extend(["-p", parent])
        revision = subprocess.run(command, cwd=self.repo, input=b"raw\n", capture_output=True,
                                  check=True).stdout.decode().strip()
        self.git.run("update-ref", "HEAD", revision)
        return revision

    def base_and_head(self, base_files: dict[str, bytes], head_files: dict[str, bytes]) -> tuple[str, str]:
        base = self.commit_files(base_files, "base")
        head = self.commit_files(head_files, "head")
        return base, head

    def build(self, base: str, head: str, control: str | None = None) -> dict:
        return producer.build_input(self.repo, self.identity(base, head, control))

    def test_real_git_inventory_uses_fixed_commits_and_ignores_worktree_config_and_hooks(self):
        root = self.commit_files({"tracked.txt": b"base\n"}, "root")
        self.git.run("checkout", "-qb", "feature")
        head = self.commit_files({"tracked.txt": b"head\n", "added.txt": b"added\n"}, "feature")
        self.git.run("checkout", "-q", "main")
        self.git.run("reset", "-q", "--hard", root)
        base_tip = self.commit_files({"base-only.txt": b"main advanced\n"}, "main advanced")
        self.git.run("checkout", "-q", "feature")
        self.git.run("config", "diff.external", str(self.repo / "must-not-run"))
        self.git.run("config", "diff.textconv", str(self.repo / "must-not-run"))
        hostile = self.repo / "must-not-run"
        hostile_sentinel = Path(self.temp.name) / "hostile-executed"
        hostile.write_text(f"#!/bin/sh\nprintf HOSTILE_EXECUTED > {hostile_sentinel}\n", encoding="utf-8")
        hostile.chmod(0o755)
        (self.repo / "working-tree-only.txt").write_text("not in either commit", encoding="utf-8")
        hook = self.repo / ".git/hooks/post-checkout"
        hook.write_text("#!/bin/sh\nprintf HOOK_EXECUTED > hook-result\n", encoding="utf-8")
        hook.chmod(0o755)
        commands: list[list[str]] = []
        original = producer._bounded_process

        def record(command, **kwargs):
            commands.append(list(command))
            return original(command, **kwargs)

        with mock.patch.dict(os.environ, {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "diff.external",
                                          "GIT_CONFIG_VALUE_0": str(hostile)}, clear=False), \
             mock.patch.object(producer, "_bounded_process", side_effect=record):
            document = self.build(root, head)
        self.assertEqual(document["identity"]["base_sha"], root)
        self.assertEqual(document["identity"]["head_sha"], head)
        self.assertEqual(document["identity"]["control_sha"], head)
        self.assertEqual([item["path"] for item in document["files"]], ["added.txt", "tracked.txt"])
        self.assertFalse((self.repo / "hook-result").exists())
        self.assertFalse(hostile_sentinel.exists())
        self.assertTrue(commands)
        self.assertTrue(all("checkout" not in command and "reset" not in command for command in commands))
        self.assertTrue(all("--no-replace-objects" in command and "--no-pager" in command for command in commands))
        diff_commands = [command for command in commands if "diff" in command]
        self.assertGreaterEqual(len(diff_commands), 3)
        self.assertTrue(any("--name-status" in command for command in diff_commands))
        self.assertTrue(any("--raw" in command for command in diff_commands))
        self.assertTrue(any("--full-index" in command for command in diff_commands))
        for command in diff_commands:
            self.assertIn("--find-renames=50%", command)
            self.assertIn("--no-ext-diff", command)
            self.assertIn("--no-textconv", command)
            self.assertIn("--no-color", command)
            self.assertIn("--no-indent-heuristic", command)
            self.assertIn("--diff-algorithm=myers", command)
            self.assertIn("--src-prefix=a/", command)
            self.assertIn("--dst-prefix=b/", command)
            if "--name-status" in command or "--raw" in command:
                self.assertEqual(command[-1], "--")
            else:
                # The complete diff excludes tool-generated artifacts by
                # pathspec so their bytes never enter the review input.
                separator = command.index("--")
                self.assertEqual(command[separator + 1], ".")
                self.assertEqual(
                    command[separator + 2:],
                    [f":(exclude){path}" for path in
                     producer.GENERATED_DIRECTORY_PREFIXES + producer.GENERATED_FILES],
                )

        expected = self.git.run(
            "--no-pager", "-c", "core.quotePath=false", "diff", "--find-renames=50%", "--no-ext-diff",
            "--no-textconv", "--no-color", "--full-index", "--no-indent-heuristic", "--diff-algorithm=myers",
            "--src-prefix=a/", "--dst-prefix=b/", root, head, "--",
        )
        self.assertEqual(document["diff"]["text"].encode(), expected)
        self.assertEqual(self.git.text("rev-parse", "HEAD"), head)
        self.assertEqual(base_tip, self.git.text("rev-parse", "main"))

    def test_bounded_process_streams_stdin_and_caps_stdout_and_stderr(self):
        payload = b"x" * (1024 * 1024)
        echo = [sys.executable, "-c", "import sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(str(len(data)).encode())"]
        self.assertEqual(
            producer._bounded_process(echo, cwd=self.repo, input_data=payload, max_output=64,
                                      env=producer._git_environment()),
            str(len(payload)).encode(),
        )
        with self.assertRaises(producer.InputCollectionError):
            producer._bounded_process(
                [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x' * 65)"],
                cwd=self.repo, max_output=64, env=producer._git_environment(),
            )
        with self.assertRaises(producer.InputCollectionError):
            producer._bounded_process(
                [sys.executable, "-c", "import sys; sys.stderr.buffer.write(b'x' * 65537)"],
                cwd=self.repo, max_output=64, env=producer._git_environment(),
            )

    def test_bounded_process_child_closes_stdin_after_ready_and_times_out(self):
        command = [
            sys.executable, "-c",
            "import sys,time; sys.stdin.close(); print('READY', flush=True); time.sleep(1)",
        ]
        with mock.patch.object(producer, "GIT_TIMEOUT_SECONDS", 0.05):
            with self.assertRaisesRegex(producer.InputCollectionError, "bounded time limit"):
                producer._bounded_process(
                    command, cwd=self.repo, input_data=b"x" * (128 * 1024),
                    max_output=64, env=producer._git_environment(),
                )

    def test_diff_attributes_are_bound_to_the_base_tree_not_worktree_index_or_ambient_env(self):
        base, head = self.base_and_head({"a.txt": b"old\n"}, {"a.txt": b"new\n"})
        (self.repo / ".gitattributes").write_bytes(b"*.txt -diff\n")
        self.git.run("add", ".gitattributes")
        info_attributes = self.repo / ".git/info/attributes"
        info_attributes.write_bytes(b"*.txt -diff\n")
        global_attributes = self.repo / "global.attributes"
        global_attributes.write_bytes(b"*.txt -diff\n")
        with mock.patch.dict(os.environ, {
            "GIT_ATTR_SOURCE": "worktree",
            "GIT_ATTR_NOSYSTEM": "0",
            "GIT_CONFIG_GLOBAL": str(global_attributes),
            "GIT_CONFIG_SYSTEM": str(global_attributes),
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "diff.external",
            "GIT_CONFIG_VALUE_0": str(self.repo / "must-not-run"),
        }, clear=False):
            document = self.build(base, head)
        self.assertEqual(document["files"][0]["change_kind"], "modified")
        self.assertEqual(document["files"][0]["hunks"][0]["right_lines"][0]["text"], "new")
        self.assertIn("@@ -1 +1 @@", document["diff"]["text"])

    def test_every_file_and_hunk_is_compared_to_independent_git_objects_and_diff(self):
        base = self.commit_files({
            "modify.txt": "\n".join(f"line-{index}" for index in range(1, 61)).encode() + b"\n",
            "delete.txt": b"remove me\n",
            "old.txt": "\n".join(f"rename-{index}" for index in range(1, 21)).encode() + b"\n",
            "binary.bin": b"\x00old\xff",
        }, "base")
        modify = self.repo / "modify.txt"
        modify_lines = modify.read_text(encoding="utf-8").splitlines()
        modify_lines[1] = "changed-2"
        modify_lines[24] = "changed-25"
        modify.write_text("\n".join(modify_lines) + "\n", encoding="utf-8")
        (self.repo / "delete.txt").unlink()
        (self.repo / "old.txt").rename(self.repo / "new.txt")
        rename_lines = (self.repo / "new.txt").read_text(encoding="utf-8").splitlines()
        rename_lines[9] = "renamed-10"
        (self.repo / "new.txt").write_text("\n".join(rename_lines) + "\n", encoding="utf-8")
        (self.repo / "binary.bin").write_bytes(b"\x00new\xfe")
        (self.repo / "added.txt").write_bytes(b"new content\n")
        self.git.run("add", "-A")
        head = self.git.commit("head")
        document = self.build(base, head)
        fixed_diff = self.git.run(
            "--no-pager", "-c", "core.quotePath=false", "diff", "--find-renames=50%", "--no-ext-diff",
            "--no-textconv", "--no-color", "--full-index", "--no-indent-heuristic", "--diff-algorithm=myers",
            "--src-prefix=a/", "--dst-prefix=b/", base, head, "--",
        )
        self.assertEqual(document["diff"]["text"].encode(), fixed_diff)
        self.assertEqual(document["diff"]["byte_length"], len(fixed_diff))
        self.assertEqual(document["diff"]["sha256"], hashlib.sha256(fixed_diff).hexdigest())
        expected_inventory = change_scope.parse_name_status_z(self.git.run(
            "--no-pager", "-c", "core.quotePath=false", "diff", "--name-status", "-z", "--find-renames=50%",
            "--no-ext-diff", "--no-textconv", "--no-color", "--full-index", "--no-indent-heuristic",
            "--diff-algorithm=myers", "--src-prefix=a/", "--dst-prefix=b/", base, head, "--",
        ))
        self.assertEqual([(f["change_kind"], f["path"]) for f in document["files"]],
                         [("binary" if item.status == "M" and item.paths[0] == "binary.bin" else
                           {"A": "added", "D": "deleted", "M": "modified", "R": "renamed"}[item.status[0]], item.paths[-1])
                          for item in expected_inventory])
        by_path = {file["path"]: file for file in document["files"]}
        self.assertEqual(by_path["delete.txt"]["change_kind"], "deleted")
        self.assertEqual(by_path["new.txt"]["old_path"], "old.txt")
        self.assertEqual(len(by_path["modify.txt"]["hunks"]), 2)
        self.assertEqual(
            [right for hunk in by_path["modify.txt"]["hunks"] for right in hunk["right_lines"]],
            [
                {"line": 2, "text": "changed-2", "sha256": hashlib.sha256(b"changed-2").hexdigest()},
                {"line": 25, "text": "changed-25", "sha256": hashlib.sha256(b"changed-25").hexdigest()},
            ],
        )
        self.assertEqual(
            by_path["modify.txt"]["patch"],
            "@@ -1,5 +1,5 @@\n"
            " line-1\n-line-2\n+changed-2\n line-3\n line-4\n line-5\n"
            "@@ -22,7 +22,7 @@ line-21\n"
            " line-22\n line-23\n line-24\n-line-25\n+changed-25\n line-26\n line-27\n line-28\n",
        )
        for file in document["files"]:
            old_path = file["old_path"] or file["path"]
            if file["base"] is not None:
                old_oid = self.git.text("rev-parse", f"{base}:{old_path}")
                old_bytes = self.git.run("cat-file", "blob", old_oid)
                self.assertEqual(file["base"]["object_id"], old_oid)
                self.assertEqual(file["base"]["byte_length"], len(old_bytes))
                self.assertEqual(base64_decode(file["base"]["data_b64"]), old_bytes)
            if file["head"] is not None:
                new_oid = self.git.text("rev-parse", f"{head}:{file['path']}")
                new_bytes = self.git.run("cat-file", "blob", new_oid)
                self.assertEqual(file["head"]["object_id"], new_oid)
                self.assertEqual(file["head"]["byte_length"], len(new_bytes))
                self.assertEqual(base64_decode(file["head"]["data_b64"]), new_bytes)
            for hunk in file["hunks"]:
                self.assertEqual(hunk["patch_sha256"], hashlib.sha256(hunk["patch"].encode()).hexdigest())
                for right in hunk["right_lines"]:
                    self.assertEqual(right["sha256"], hashlib.sha256(right["text"].encode()).hexdigest())
        adapter.authenticate_input(document)

    def test_crlf_and_missing_final_newline_bytes_are_not_normalized(self):
        base = self.commit_files({"ordinary.txt": b"old\n"}, "base")
        (self.repo / "ordinary.txt").write_bytes(b"new\r\nline\r\n")
        (self.repo / "without-final-newline.txt").write_bytes(b"no-final-newline")
        self.git.run("add", ".")
        head = self.git.commit("head")
        document = self.build(base, head)
        by_path = {item["path"]: item for item in document["files"]}
        self.assertEqual(base64_decode(by_path["ordinary.txt"]["head"]["data_b64"]), b"new\r\nline\r\n")
        self.assertEqual(base64_decode(by_path["without-final-newline.txt"]["head"]["data_b64"]), b"no-final-newline")
        self.assertIn(b"\\ No newline at end of file", document["diff"]["text"].encode())
        self.assertIn("+new", by_path["ordinary.txt"]["patch"])
        adapter.authenticate_input(document)

    def test_rename_with_edits_and_pure_rename_retain_old_path_and_exact_bytes(self):
        base = self.commit_files({"old.txt": b"line 0\nline 1\nline 2\nline 3\nline 4\nline 5\n"}, "base")
        (self.repo / "old.txt").rename(self.repo / "new.txt")
        (self.repo / "new.txt").write_bytes(b"line 0\nline 1\nchanged\nline 3\nline 4\nline 5\n")
        self.git.run("add", ".")
        edited = self.git.commit("rename edited")
        document = self.build(base, edited)
        self.assertEqual(document["files"][0]["change_kind"], "renamed")
        self.assertEqual(document["files"][0]["old_path"], "old.txt")
        self.assertEqual(document["files"][0]["path"], "new.txt")
        adapter.authenticate_input(document)

        base2 = self.git.text("rev-parse", "HEAD")
        (self.repo / "new.txt").rename(self.repo / "pure-new.txt")
        self.git.run("add", ".")
        pure = self.git.commit("pure rename")
        pure_doc = self.build(base2, pure)
        self.assertEqual(pure_doc["files"][0]["change_kind"], "renamed")
        self.assertEqual(pure_doc["files"][0]["old_path"], "new.txt")
        self.assertEqual(pure_doc["files"][0]["path"], "pure-new.txt")
        self.assertEqual(len(pure_doc["files"][0]["hunks"]), 1)
        adapter.authenticate_input(pure_doc)

    def test_binary_modification_is_represented_with_both_blob_sides(self):
        base = self.commit_files({"binary.bin": b"\x00old\xff"}, "base")
        (self.repo / "binary.bin").write_bytes(b"\x00new\xfe")
        self.git.run("add", ".")
        head = self.git.commit("binary")
        document = self.build(base, head)
        file = document["files"][0]
        self.assertEqual(file["change_kind"], "binary")
        self.assertIsNotNone(file["base"])
        self.assertIsNotNone(file["head"])
        self.assertIn("Binary files", file["patch"])
        self.assertEqual(file["hunks"][0]["right_lines"], [])
        adapter.authenticate_input(document)

    def test_unsupported_binary_deletion_retains_real_inventory(self):
        base = self.commit_files({"binary.bin": b"\x00old\xff"}, "base")
        (self.repo / "binary.bin").unlink()
        self.git.run("add", "-A")
        head = self.git.commit("binary deletion")
        failure = self.assert_failure(base, head, "binary deletion")
        self.assertEqual(failure["inventory"], [{"status": "D", "paths": ["binary.bin"]}])

    def test_unsupported_binary_rename_retains_both_real_paths(self):
        base = self.commit_files({"old.bin": b"\x00" * 4096 + b"old"}, "base")
        (self.repo / "old.bin").rename(self.repo / "new.bin")
        (self.repo / "new.bin").write_bytes(b"\x00" * 4096 + b"new")
        self.git.run("add", "-A")
        head = self.git.commit("binary rename")
        failure = self.assert_failure(base, head, "binary rename")
        self.assertEqual(failure["inventory"][0]["status"][0], "R")
        self.assertEqual(failure["inventory"][0]["paths"], ["old.bin", "new.bin"])

    def test_real_gitlink_is_refused_before_blob_admission(self):
        base = self.commit_files({"base.txt": b"base\n"}, "base")
        nested = Path(self.temp.name) / "nested"
        nested.mkdir()
        nested_git = RealGit(nested)
        nested_git.run("init", "-q")
        (nested / "nested.txt").write_bytes(b"nested\n")
        nested_git.run("add", ".")
        nested_commit = nested_git.commit("nested")
        self.git.run("update-index", "--add", "--cacheinfo", f"160000,{nested_commit},vendor.git")
        head = self.git.commit("gitlink")
        failure = self.assert_failure(base, head, "Git blob object")
        self.assertEqual(failure["inventory"], [{"status": "A", "paths": ["vendor.git"]}])

    def test_missing_required_commit_is_refused_before_inventory_admission(self):
        base = self.commit_files({"base.txt": b"base\n"}, "base")
        missing = "b" * 40
        with self.assertRaises(producer.InputCollectionError) as raised:
            self.build(missing, base)
        self.assertIn("required Git commit object is unavailable", str(raised.exception))
        self.assertEqual(raised.exception.result["inventory"], [])
        self.assertEqual(raised.exception.result["reasons"], [])

    def test_real_blob_object_type_is_refused_before_blob_read(self):
        base = self.commit_files({"blob.txt": b"blob\n"}, "base")
        tree_oid = self.git.text("rev-parse", f"{base}^{{tree}}")
        metadata = producer._object_metadata(self.repo, [tree_oid])
        with self.assertRaisesRegex(producer.InputCollectionError, "not a blob"):
            producer._blob(self.repo, tree_oid, metadata, "blob.txt")

    def test_real_oversized_blob_is_refused_with_inventory(self):
        base = self.commit_files({"base.txt": b"base\n"}, "base")
        oversized = b"x" * (adapter.MAX_BLOB_BYTES + 1)
        head = self.commit_files({"oversized.bin": oversized}, "oversized blob")
        failure = self.assert_failure(base, head, "oversized")
        self.assertEqual(failure["inventory"], [{"status": "A", "paths": ["oversized.bin"]}])

    def test_real_oversized_patch_is_refused_at_hunk_boundary(self):
        base = self.commit_files({"patch.txt": b"old\n"}, "base")
        head = self.commit_files({"patch.txt": b"new\n"}, "head")
        with mock.patch.object(adapter, "MAX_PATCH_BYTES", 16):
            failure = self.assert_failure(base, head, "patch for patch.txt is empty or oversized")
        self.assertEqual(failure["inventory"], [{"status": "M", "paths": ["patch.txt"]}])

    def test_real_oversized_complete_diff_is_refused_before_file_admission(self):
        base = self.commit_files({"diff.txt": b"old\n"}, "base")
        head = self.commit_files({"diff.txt": b"new\n"}, "head")
        with mock.patch.object(adapter, "MAX_INPUT_BYTES", 180):
            failure = self.assert_failure(base, head, "complete Git diff")
        self.assertEqual(failure["inventory"], [{"status": "M", "paths": ["diff.txt"]}])

    def test_real_oversized_total_input_is_refused_after_hunk_representation(self):
        lines = [f"line-{index:04d}-0123456789\n" for index in range(400)]
        base = self.commit_files({"total.txt": "".join(lines).encode()}, "base")
        changed = list(lines)
        changed[200] = "changed-0200-0123456789\n"
        head = self.commit_files({"total.txt": "".join(changed).encode()}, "head")
        with mock.patch.object(adapter, "MAX_INPUT_BYTES", 1024):
            failure = self.assert_failure(base, head, "represented input")
        self.assertEqual(failure["inventory"], [{"status": "M", "paths": ["total.txt"]}])

    def test_malformed_closed_identity_is_refused_without_git_admission(self):
        base, head = self.base_and_head({"identity.txt": b"old\n"}, {"identity.txt": b"new\n"})
        identity = self.identity(base, head)
        identity["unexpected"] = "forged"
        with self.assertRaises(producer.InputCollectionError) as raised:
            producer.build_input(self.repo, identity)
        self.assertIn("T2 identity is invalid", str(raised.exception))
        self.assertEqual(raised.exception.result["inventory"], [])
        self.assertEqual(raised.exception.result["reasons"], [])

    def test_quoted_and_unsafe_real_paths_fail_closed_with_complete_inventory(self):
        base = self.commit_files({"base.txt": b"base\n"}, "base")
        quoted = self.repo / 'quoted"name.txt'
        unsafe = self.repo / "unsafe\\name.txt"
        quoted.write_bytes(b"quoted\n")
        unsafe.write_bytes(b"unsafe\n")
        self.git.run("add", "-A")
        head = self.git.commit("hostile paths")
        failure = self.assert_failure(base, head, "noncanonical")
        self.assertEqual(failure["inventory"], [
            {"status": "A", "paths": ['quoted"name.txt']},
            {"status": "A", "paths": ["unsafe\\name.txt"]},
        ])

    def test_non_utf8_path_retains_lossless_bytes_and_later_valid_inventory_in_json(self):
        base = self.commit_raw_files({b"source.txt": b"old\n"})
        invalid = b"a-\xff.txt"
        head = self.commit_raw_files({b"source.txt": b"old\n", invalid: b"new\n",
                                      b"z-later.txt": b"later\n"}, parent=base)
        with self.assertRaises(producer.InputCollectionError) as raised:
            self.build(base, head)
        failure = raised.exception.result
        expected_invalid_b64 = base64_decode(base64.b64encode(invalid).decode())
        self.assertEqual(expected_invalid_b64, invalid)
        self.assertEqual(failure["inventory"], [
            {"status": "A", "paths": [None],
             "paths_raw_hex": [invalid.hex()],
             "paths_raw_base64": [base64.b64encode(invalid).decode("ascii")]},
            {"status": "A", "paths": ["z-later.txt"]},
        ])
        self.assertEqual(failure["reasons"], [
            {"path_raw_hex": invalid.hex(),
             "path_raw_base64": base64.b64encode(invalid).decode("ascii"),
             "reason": "raw Git inventory path is not UTF-8"},
            {"path": "z-later.txt", "reason": "raw Git inventory path is not UTF-8"},
        ])
        raw = self.git.run(
            "--no-pager", "-c", "core.quotePath=false", "diff", "--raw", "-z", "--abbrev=40",
            "--find-renames=50%", "--no-ext-diff", "--no-textconv", "--no-color", "--full-index",
            "--no-indent-heuristic", "--diff-algorithm=myers", "--src-prefix=a/", "--dst-prefix=b/",
            base, head, "--",
        )
        self.assertEqual(failure["raw_inventory"], {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "byte_length": len(raw), "complete": True, "truncated": False,
        })
        encoded = json.dumps(failure, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(json.loads(encoded), failure)
        output = Path(self.temp.name) / "non-utf8-failure-output"
        producer.publish_failure(output, failure)
        self.assertEqual(json.loads((output / "collection-failure.json").read_text(encoding="utf-8")), failure)
        self.assertFalse((output / "t2-input.json").exists())

    def assert_failure(self, base: str, head: str, text: str) -> dict:
        with self.assertRaises(producer.InputCollectionError) as raised:
            self.build(base, head)
        failure = raised.exception.result
        self.assertEqual(failure["status"], "failed")
        self.assertTrue(failure["inventory"])
        self.assertTrue(all(text in reason["reason"] for reason in failure["reasons"]))
        return failure

    def test_unsupported_metadata_only_change_is_explicit_and_complete(self):
        base = self.commit_files({"mode.txt": b"same\n"}, "base")
        (self.repo / "mode.txt").chmod(0o755)
        self.git.run("add", ".")
        head = self.git.commit("mode only")
        failure = self.assert_failure(base, head, "zero-hunk")
        self.assertEqual(failure["inventory"], [{"status": "M", "paths": ["mode.txt"]}])

    def test_unsupported_binary_addition_is_explicit_and_has_no_input(self):
        base = self.commit_files({"base.txt": b"base\n"}, "base")
        (self.repo / "binary.bin").write_bytes(b"\x00new\xff")
        self.git.run("add", ".")
        head = self.git.commit("binary addition")
        failure = self.assert_failure(base, head, "binary addition")
        self.assertEqual(failure["inventory"], [{"status": "A", "paths": ["binary.bin"]}])

    def test_unsupported_type_change_is_explicit_and_has_no_input(self):
        base = self.commit_files({"type.txt": b"regular\n"}, "base")
        (self.repo / "type.txt").unlink()
        os.symlink("other-target", self.repo / "type.txt")
        self.git.run("add", "-A")
        head = self.git.commit("type change")
        failure = self.assert_failure(base, head, "type change")
        self.assertEqual(failure["inventory"], [{"status": "T", "paths": ["type.txt"]}])

    def test_path_space_round_trips_real_git_bytes_and_adapter_right_lines(self):
        base = self.commit_files({"base.txt": b"base\n"}, "base")
        (self.repo / "path with spaces.txt").write_bytes(b"space\n")
        self.git.run("add", ".")
        head = self.git.commit("space")
        document = self.build(base, head)
        file = document["files"][0]
        self.assertEqual(file["change_kind"], "added")
        self.assertEqual(file["path"], "path with spaces.txt")
        self.assertIsNone(file["old_path"])
        raw_diff = self.git.run(
            "--no-pager", "-c", "core.quotePath=false", "diff", "--find-renames=50%", "--no-ext-diff",
            "--no-textconv", "--no-color", "--full-index", "--no-indent-heuristic", "--diff-algorithm=myers",
            "--src-prefix=a/", "--dst-prefix=b/", base, head, "--",
        )
        self.assertEqual(document["diff"]["text"].encode(), raw_diff)
        self.assertEqual(document["diff"]["byte_length"], len(raw_diff))
        self.assertEqual(document["diff"]["sha256"], hashlib.sha256(raw_diff).hexdigest())
        oid = self.git.text("rev-parse", f"{head}:path with spaces.txt")
        head_bytes = self.git.run("cat-file", "blob", oid)
        self.assertEqual(file["head"]["object_id"], oid)
        self.assertEqual(file["head"]["byte_length"], len(head_bytes))
        self.assertEqual(base64_decode(file["head"]["data_b64"]), head_bytes)
        hunk = file["hunks"][0]
        self.assertEqual(hunk["patch_sha256"], hashlib.sha256(hunk["patch"].encode()).hexdigest())
        self.assertEqual(hunk["right_lines"], [{
            "line": 1, "text": "space", "sha256": hashlib.sha256(b"space").hexdigest(),
        }])
        authenticated = adapter.authenticate_input(document)
        self.assertEqual(authenticated["files"][0]["head_bytes"], b"space\n")
        self.assertEqual(authenticated["files"][0]["hunks"][0]["right_lines"], [1])

    def test_file_limit_refusal_retains_entire_nul_inventory(self):
        base = self.commit_files({"base.txt": b"base\n"}, "base")
        files = {f"file-{index:02d}.txt": f"{index}\n".encode() for index in range(adapter.MAX_FILES + 1)}
        self.commit_files(files, "many")
        head = self.git.text("rev-parse", "HEAD")
        failure = self.assert_failure(base, head, "MAX_FILES")
        self.assertEqual(len(failure["inventory"]), adapter.MAX_FILES + 1)
        self.assertEqual({path for item in failure["inventory"] for path in item["paths"]}, set(files))
        self.assertTrue(all("generated" in reason["reason"] for reason in failure["reasons"]))

    def test_generated_artifacts_are_excluded_from_limits_but_recorded(self):
        base = self.commit_files({"base.txt": b"base\n"}, "base")
        reviewable = {
            f"file-{index:02d}.txt": f"{index}\n".encode() for index in range(adapter.MAX_FILES - 1)
        }
        # A one-line append to versions.json stays reviewable; only the frozen
        # snapshot directories under it are generated artifacts.  Together the
        # reviewable set sits exactly at MAX_FILES.
        reviewable["apps/architecture-portal/versions.json"] = b'["1.0.57.0"]\n'
        self.commit_files({**reviewable, **self.GENERATED_CHANGES}, "build allocation")
        head = self.git.text("rev-parse", "HEAD")
        document = self.build(base, head)
        self.assertEqual(len(document["files"]), adapter.MAX_FILES)
        self.assertEqual(
            {file["path"] for file in document["files"]},
            set(reviewable),
        )
        excluded = document["excluded_generated"]
        self.assertEqual(excluded["count"], len(self.GENERATED_CHANGES))
        self.assertEqual(excluded["paths"], sorted(self.GENERATED_CHANGES))
        for path in self.GENERATED_CHANGES:
            self.assertNotIn(path, document["diff"]["text"])
        self.assertNotIn("rendered assembly", document["diff"]["text"])
        authenticated = adapter.authenticate_input(document)
        self.assertEqual(len(authenticated["files"]), adapter.MAX_FILES)

    def test_all_generated_inventory_is_refused_with_explicit_reason(self):
        base = self.commit_files({"base.txt": b"base\n"}, "base")
        self.commit_files(self.GENERATED_CHANGES, "snapshot only")
        head = self.git.text("rev-parse", "HEAD")
        failure = self.assert_failure(base, head, "only excluded generated artifacts")
        self.assertEqual(
            {path for item in failure["inventory"] for path in item["paths"]},
            set(self.GENERATED_CHANGES),
        )

    def test_object_type_and_size_are_checked_before_blob_read(self):
        base = self.commit_files({"blob.txt": b"blob\n"}, "base")
        (self.repo / "blob.txt").write_bytes(b"changed\n")
        self.git.run("add", ".")
        head = self.git.commit("head")
        original = producer._object_metadata
        with mock.patch.object(producer, "_object_metadata", return_value={}):
            failure = self.assert_failure(base, head, "object for blob.txt is missing")
        self.assertIs(producer._object_metadata, original)
        self.assertEqual(failure["inventory"], [{"status": "M", "paths": ["blob.txt"]}])

    def test_missing_batch_object_is_classified_before_blob_read(self):
        missing = "a" * 40
        metadata = producer._object_metadata(self.repo, [missing])
        self.assertEqual(metadata, {missing: ("missing", -1)})
        with self.assertRaisesRegex(producer.InputCollectionError, "object for missing.txt is missing"):
            producer._blob(self.repo, missing, metadata, "missing.txt")

    def test_tampering_any_authenticated_field_fails_the_real_adapter(self):
        base, head = self.base_and_head({"a.txt": b"old\n"}, {"a.txt": b"new\n"})
        original = self.build(base, head)
        mutations = []
        changed = copy.deepcopy(original)
        changed["input_sha256"] = "0" * 64
        mutations.append(changed)
        changed = copy.deepcopy(original)
        changed["files"][0]["head"]["data_b64"] = "bm90LWJ5dGVz"
        changed["input_sha256"] = hashlib.sha256(
            json.dumps({key: value for key, value in changed.items() if key != "input_sha256"},
                       ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        mutations.append(changed)
        changed = copy.deepcopy(original)
        changed["files"][0]["hunks"][0]["right_lines"][0]["text"] = "forged"
        changed["input_sha256"] = hashlib.sha256(
            json.dumps({key: value for key, value in changed.items() if key != "input_sha256"},
                       ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        mutations.append(changed)
        for value in mutations:
            with self.subTest(value=value):
                with self.assertRaises(adapter.EngineError):
                    adapter.authenticate_input(value)

    def test_publish_collection_is_no_clobber_and_receipt_is_last_success_marker(self):
        output = Path(self.temp.name) / "output"
        artifacts = {
            "context.json": b"context",
            "pr.diff": b"diff",
            "pr-body.md": b"body",
            "history.json": b"[]",
            "t2-input.json": b"input",
            "collection-receipt.json": b"receipt",
        }
        producer.publish_collection(output, artifacts)
        self.assertEqual(sorted(path.name for path in output.iterdir()), sorted(artifacts))
        self.assertEqual((output / "collection-receipt.json").read_bytes(), b"receipt")
        original = {path.name: path.read_bytes() for path in output.iterdir()}
        with self.assertRaises(producer.PublicationError):
            producer.publish_collection(output, {"collection-receipt.json": b"forged"})
        self.assertEqual({path.name: path.read_bytes() for path in output.iterdir()}, original)

    def test_publish_collection_fsync_failure_leaves_no_success_marker(self):
        output = Path(self.temp.name) / "fsync-output"
        artifacts = {"t2-input.json": b"input", "collection-receipt.json": b"receipt"}
        with mock.patch.object(producer.os, "fsync", side_effect=OSError("injected fsync")):
            with self.assertRaises(producer.PublicationError):
                producer.publish_collection(output, artifacts)
        self.assertFalse((output / "collection-receipt.json").exists())
        self.assertTrue(any(path.name.endswith(".partial") for path in output.iterdir()))

    def test_publish_collection_second_directory_fsync_failure_removes_complete_marker(self):
        output = Path(self.temp.name) / "second-fsync-output"
        artifacts = {"t2-input.json": b"input", "collection-receipt.json": b"receipt"}
        original_fsync = producer._fsync_directory
        calls = 0

        def fail_second(directory):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected final directory fsync")
            return original_fsync(directory)

        with mock.patch.object(producer, "_fsync_directory", side_effect=fail_second):
            with self.assertRaises(producer.PublicationError):
                producer.publish_collection(output, artifacts)
        self.assertFalse((output / "collection-receipt.json").exists())
        self.assertEqual((output / "t2-input.json").read_bytes(), b"input")

    def test_strict_consumer_refuses_real_fifo_after_child_ready_without_hanging(self):
        output = Path(self.temp.name) / "fifo-output"
        output.mkdir()
        for name in producer.COLLECTION_ARTIFACTS:
            (output / name).write_bytes(b"")
        os.unlink(output / "context.json")
        os.mkfifo(output / "context.json")
        empty_digest = hashlib.sha256(b"").hexdigest()
        witness = {
            "schema": producer.PUBLICATION_WITNESS_SCHEMA,
            "status": "committed",
            "artifacts": {
                name: {"sha256": empty_digest, "byte_length": 0}
                for name in producer.COLLECTION_ARTIFACTS
            },
            "receipt_sha256": empty_digest,
        }
        child_code = """
import json
import sys
import pr_agent_input as p

print("READY", flush=True)
try:
    p.verify_publication(sys.argv[1], json.loads(sys.argv[2]))
except p.PublicationError as error:
    print(type(error).__name__ + ":" + str(error), flush=True)
else:
    raise SystemExit("FIFO was admitted")
"""
        child = subprocess.Popen(
            [sys.executable, "-c", child_code, str(output), json.dumps(witness)],
            cwd=ROOT,
            env={**producer._git_environment(), "PYTHONPATH": str(ROOT / "scripts/ci")},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            stdout, stderr = child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
            self.fail("strict consumer hung while opening a retained FIFO")
        self.assertEqual(child.returncode, 0, stderr)
        self.assertIn("READY", stdout)
        self.assertIn("PublicationError", stdout)

    def test_strict_consumer_rejects_actual_symlink_at_open_boundary(self):
        output = Path(self.temp.name) / "symlink-output"
        output.mkdir()
        for name in producer.COLLECTION_ARTIFACTS:
            (output / name).write_bytes(b"")
        outside = Path(self.temp.name) / "outside"
        outside.write_bytes(b"")
        retained = output / "context.json"
        retained.unlink()
        os.symlink(outside, retained)
        empty_digest = hashlib.sha256(b"").hexdigest()
        witness = {
            "schema": producer.PUBLICATION_WITNESS_SCHEMA,
            "status": "committed",
            "artifacts": {
                name: {"sha256": empty_digest, "byte_length": 0}
                for name in producer.COLLECTION_ARTIFACTS
            },
            "receipt_sha256": empty_digest,
        }
        with self.assertRaisesRegex(producer.PublicationError, "context.json"):
            producer.verify_publication(output, witness)

    def test_strict_consumer_bounds_an_oversized_retained_artifact(self):
        output = Path(self.temp.name) / "oversized-output"
        output.mkdir()
        for name in producer.COLLECTION_ARTIFACTS:
            (output / name).write_bytes(b"")
        bound = adapter.MAX_INPUT_BYTES * 4
        (output / "context.json").write_bytes(b"x" * (bound + 1))
        empty_digest = hashlib.sha256(b"").hexdigest()
        witness = {
            "schema": producer.PUBLICATION_WITNESS_SCHEMA,
            "status": "committed",
            "artifacts": {
                name: {"sha256": empty_digest, "byte_length": 0}
                for name in producer.COLLECTION_ARTIFACTS
            },
            "receipt_sha256": empty_digest,
        }
        with self.assertRaisesRegex(producer.PublicationError, "context.json"):
            producer.verify_publication(output, witness)


def base64_decode(value: str) -> bytes:
    import base64
    return base64.b64decode(value, validate=True)


if __name__ == "__main__":
    unittest.main()
