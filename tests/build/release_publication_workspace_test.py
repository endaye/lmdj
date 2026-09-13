#!/usr/bin/env python3
"""Real linked-worktree publication installation and crash/recovery boundaries."""

from copy import deepcopy
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_publication_evidence_test as fixtures
from tools.release.model import canonical_json
from tools.release.orchestration import JournalError, RequestJournal
from tools.release.publication import collect_publication_state
from tools.release.publication_evidence import LEDGER, PIN, INDEX, plan_publication_patch
from tools.release.publication_workspace import PublicationWorkspace, PublicationWorkspaceError


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PublicationEvidenceTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.operation = "7" * 64
        self.branch = "docs/release-evidence-" + self.operation
        self.base = self.fixture.git("rev-parse", "HEAD").stdout.strip()
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-publication-workspace-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "task"
        self.fixture.git("-c", "core.symlinks=true", "worktree", "add", "-b", self.branch, str(self.root), self.base)
        self.workspace = PublicationWorkspace(self.root)
        self.record, self.intent = collect_publication_state(self.fixture.f.tag,
            self.fixture.journey.created.release_id, self.fixture.journey.created.plan_sha256,
            self.fixture.f.context())
        self.arguments = dict(base_revision=self.base, operation_id=self.operation,
            policy=self.fixture.f.policy, intent=self.intent, record=self.record,
            author_name="Release Fixture", author_email="fixture@example.invalid",
            timestamp=1789250000, verify=self.verify)
        self.verifications = 0

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], text=True,
                              capture_output=True, check=True).stdout.strip()

    def verify(self, root):
        self.verifications += 1
        self.assertEqual(plan_publication_patch(root, self.fixture.f.policy, self.intent, self.record), "")
        self.workspace.git("diff", "--cached", "--check")

    def run_task(self, **changes):
        return self.workspace.prepare(**dict(self.arguments, **changes))

    def test_success_reopen_returns_same_commit_and_preserves_base_and_history(self):
        before = self.fixture.git("rev-parse", "HEAD").stdout
        frozen = (self.root / "apps/docs-site/versioned_docs/version-1.0.0.0/frozen.mdx").read_bytes()
        result = self.run_task()
        self.workspace = PublicationWorkspace(self.root)
        self.assertEqual(self.run_task(), result)
        self.assertEqual(self.verifications, 2)
        self.assertEqual(self.git("rev-parse", "HEAD^"), self.base)
        self.assertEqual(self.git("rev-list", "--count", self.base + "..HEAD"), "1")
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.fixture.git("rev-parse", "HEAD").stdout, before)
        self.assertEqual((self.root / "apps/docs-site/versioned_docs/version-1.0.0.0/frozen.mdx").read_bytes(), frozen)
        self.assertEqual(set(self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()), set(result["files"]))
        self.assertIn("Release-operation: " + self.operation, self.git("log", "-1", "--format=%B"))

    def test_failed_verification_keeps_base_then_recovers_without_duplicate_commit(self):
        def fail(_):
            raise RuntimeError("SECRET-RAW-VERIFIER-DETAIL")
        with self.assertRaisesRegex(PublicationWorkspaceError, "Task verification failed") as error:
            self.run_task(verify=fail)
        self.assertNotIn("SECRET", str(error.exception))
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)
        result = self.run_task()
        self.assertEqual(self.git("rev-parse", "HEAD"), result["commit"])

    def test_partial_installation_recovers_exact_old_new_mix(self):
        original = self.workspace._install
        installed = []
        def interrupt(*args, **kwargs):
            value = original(*args, **kwargs)
            installed.append(args[0])
            if len(installed) == 2:
                raise InterruptedError("fixture interruption after durable files")
            return value
        with patch.object(self.workspace, "_install", side_effect=interrupt), self.assertRaises(InterruptedError):
            self.run_task()
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)
        self.workspace = PublicationWorkspace(self.root)
        self.assertEqual(self.run_task()["commit"], self.git("rev-parse", "HEAD"))

    def test_crash_after_ref_update_reconciles_existing_commit(self):
        original = self.workspace.git
        def interrupt(*args, **kwargs):
            value = original(*args, **kwargs)
            if args[0] == "update-ref":
                raise InterruptedError("fixture interruption after ref effect")
            return value
        with patch.object(self.workspace, "git", side_effect=interrupt), self.assertRaises(InterruptedError):
            self.run_task()
        committed = self.git("rev-parse", "HEAD")
        self.assertNotEqual(committed, self.base)
        self.assertEqual(self.run_task()["commit"], committed)
        self.assertEqual(self.git("rev-list", "--count", self.base + "..HEAD"), "1")

    def test_process_death_after_ref_update_reopens_and_revalidates(self):
        child = os.fork()
        if child == 0:
            original = self.workspace.git
            def terminate(*args, **kwargs):
                value = original(*args, **kwargs)
                if args[0] == "update-ref":
                    os._exit(73)
                return value
            try:
                self.workspace.git = terminate
                self.run_task()
            except BaseException:
                os._exit(74)
            os._exit(75)
        _, wait_status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(wait_status), 73)
        committed = self.git("rev-parse", "HEAD")
        self.assertNotEqual(committed, self.base)
        self.workspace = PublicationWorkspace(self.root)
        self.assertEqual(self.run_task()["commit"], committed)
        self.assertEqual(self.verifications, 1)

    def test_binding_rename_crash_windows_recover_without_checkout_before_binding(self):
        original = os.replace
        for after in (False, True):
            with self.subTest(after=after):
                def interrupt(*args, **kwargs):
                    if args[0] == "binding.pending":
                        if after:
                            original(*args, **kwargs)
                        raise InterruptedError("binding rename interruption")
                    return original(*args, **kwargs)
                with patch("tools.release.publication_workspace.os.replace", side_effect=interrupt), self.assertRaises(InterruptedError):
                    self.run_task()
                self.assertEqual(self.git("rev-parse", "HEAD"), self.base)
                self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.run_task()["commit"], self.git("rev-parse", "HEAD"))

    def test_git_child_keeps_writer_lock_after_controller_death(self):
        input_read, input_write = os.pipe()
        ready_read, ready_write = os.pipe()
        child = os.fork()
        if child == 0:
            os.close(ready_read)
            os.close(input_write)
            original = subprocess.run
            def launch_orphan(*args, **kwargs):
                if kwargs.get("pass_fds"):
                    orphan = subprocess.Popen(["git", "hash-object", "--stdin"], stdin=input_read,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        pass_fds=kwargs["pass_fds"], env=kwargs["env"], cwd=self.root)
                    self.assertGreater(orphan.pid, 0)
                    os.write(ready_write, b"ready")
                    os._exit(73)
                return original(*args, **kwargs)
            try:
                with patch("tools.release.publication_workspace.subprocess.run", side_effect=launch_orphan):
                    self.run_task()
            except BaseException:
                os._exit(74)
            os._exit(75)
        os.close(ready_write)
        os.close(input_read)
        try:
            self.assertEqual(os.read(ready_read, 5), b"ready")
            _, wait_status = os.waitpid(child, 0)
            self.assertEqual(os.waitstatus_to_exitcode(wait_status), 73)
            gitdir = Path(self.git("rev-parse", "--absolute-git-dir"))
            with self.assertRaises(JournalError):
                with RequestJournal(gitdir / "lmdj-publication-workspace"):
                    pass
        finally:
            os.close(ready_read)
            os.close(input_write)
        deadline = time.monotonic() + 5
        while True:
            try:
                with RequestJournal(gitdir / "lmdj-publication-workspace"):
                    break
            except JournalError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)
        self.assertEqual(self.run_task()["commit"], self.git("rev-parse", "HEAD"))

    def test_rebound_operation_rejected_before_overwriting_partial_files(self):
        with self.assertRaises(PublicationWorkspaceError):
            self.run_task(verify=lambda _: (_ for _ in ()).throw(RuntimeError()))
        before = (self.root / LEDGER).read_bytes()
        with self.assertRaisesRegex(PublicationWorkspaceError, "binding changed"):
            self.run_task(timestamp=self.arguments["timestamp"] + 1)
        self.assertEqual((self.root / LEDGER).read_bytes(), before)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)

    def test_unknown_edit_preserved_and_no_commit(self):
        (self.root / INDEX).write_text("user edit\n")
        with self.assertRaisesRegex(PublicationWorkspaceError, "bytes drifted"):
            self.run_task()
        self.assertEqual((self.root / INDEX).read_text(), "user edit\n")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)

    def test_clean_filter_cannot_hide_unrelated_raw_edit_or_execute(self):
        relative = "apps/docs-site/versioned_docs/version-1.0.0.0/frozen.mdx"
        target = self.root / relative
        original = target.read_bytes()
        common = Path(self.git("rev-parse", "--path-format=absolute", "--git-common-dir"))
        marker = Path(self.temporary.name) / "filter-executed"
        (common / "info/attributes").write_text(relative + " filter=fixture\n")
        self.git("config", "filter.fixture.clean", f"touch '{marker}'; printf 'frozen\\n'")
        self.assertEqual(original, b"frozen\n")
        target.write_bytes(b"hidden unrelated edit\n")
        with self.assertRaises(PublicationWorkspaceError):
            self.run_task()
        self.assertFalse(marker.exists(), "workspace verification must not execute local clean filters")
        self.assertEqual(target.read_bytes(), b"hidden unrelated edit\n")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)

    def test_interrupted_real_file_write_recovers_without_torn_target(self):
        child = os.fork()
        if child == 0:
            original = self.workspace._install
            def limited(*args):
                resource.setrlimit(resource.RLIMIT_FSIZE, (10, 10))
                return original(*args)
            try:
                self.workspace._install = limited
                self.run_task()
            except OSError:
                os._exit(73)
            except BaseException:
                os._exit(74)
            os._exit(75)
        _, child_status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(child_status), 73)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)
        self.workspace = PublicationWorkspace(self.root)
        self.assertEqual(self.run_task()["commit"], self.git("rev-parse", "HEAD"))

    def test_missing_partial_clone_blob_is_not_hydrated(self):
        self.fixture.git("config", "uploadpack.allowFilter", "true")
        self.fixture.git("config", "uploadpack.allowAnySHA1InWant", "true")
        clone = Path(self.temporary.name).resolve() / "partial"
        self.fixture.git("clone", "--filter=blob:none", "--no-checkout", self.fixture.root.as_uri(), str(clone))
        blob = self.git("rev-parse", self.base + ":" + LEDGER)
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="")
        absent = subprocess.run(["git", "-C", str(clone), "cat-file", "-e", blob], capture_output=True, env=env)
        self.assertNotEqual(absent.returncode, 0)
        objects = clone / ".git/objects"
        inventory = lambda: {str(p.relative_to(objects)): p.read_bytes() for p in objects.rglob("*") if p.is_file()}
        before = inventory()
        with self.assertRaises(PublicationWorkspaceError):
            PublicationWorkspace(clone).git("cat-file", "blob", blob)
        self.assertEqual(inventory(), before)

    def test_process_death_around_atomic_install_preserves_recoverable_bytes(self):
        for after in (False, True):
            with self.subTest(after=after):
                child = os.fork()
                if child == 0:
                    original = os.replace
                    def interrupted(source, *args, **kwargs):
                        if str(source).startswith("install-"):
                            if after:
                                original(source, *args, **kwargs)
                            os._exit(73)
                        return original(source, *args, **kwargs)
                    try:
                        with patch("tools.release.publication_workspace.os.replace", side_effect=interrupted):
                            self.run_task()
                    except BaseException:
                        os._exit(74)
                    os._exit(75)
                _, child_status = os.waitpid(child, 0)
                self.assertEqual(os.waitstatus_to_exitcode(child_status), 73)
                self.assertEqual(self.git("rev-parse", "HEAD"), self.base)
        self.workspace = PublicationWorkspace(self.root)
        committed = self.run_task()["commit"]
        self.assertEqual(self.run_task()["commit"], committed)
        self.assertEqual(self.git("rev-list", "--count", self.base + "..HEAD"), "1")

    def test_unchanged_raw_file_does_not_execute_configured_clean_filter(self):
        relative = "apps/docs-site/versioned_docs/version-1.0.0.0/frozen.mdx"
        common = Path(self.git("rev-parse", "--path-format=absolute", "--git-common-dir"))
        marker = Path(self.temporary.name) / "filter-executed"
        (common / "info/attributes").write_text(relative + " filter=fixture\n")
        self.git("config", "filter.fixture.clean", f"touch '{marker}'; printf 'changed\\n'")
        self.assertEqual(self.run_task()["commit"], self.git("rev-parse", "HEAD"))
        self.assertFalse(marker.exists())

    def test_index_skip_flags_do_not_hide_unrelated_raw_drift(self):
        relative = "apps/docs-site/versioned_docs/version-1.0.0.0/frozen.mdx"
        for flag in ("--assume-unchanged", "--skip-worktree"):
            with self.subTest(flag=flag):
                self.git("update-index", flag, relative)
                (self.root / relative).write_bytes(b"hidden edit\n")
                with self.assertRaisesRegex(PublicationWorkspaceError, "unrelated tracked raw bytes"):
                    self.run_task()
                self.assertEqual(self.git("rev-parse", "HEAD"), self.base)

    def test_unrelated_untracked_file_is_not_added_or_removed(self):
        (self.root / "user.txt").write_text("retain\n")
        with self.assertRaisesRegex(PublicationWorkspaceError, "unrelated or untracked"):
            self.run_task()
        self.assertEqual((self.root / "user.txt").read_text(), "retain\n")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)

    def test_unknown_staged_edit_is_not_overwritten(self):
        (self.root / PIN).write_text("staged user edit\n")
        self.git("add", PIN)
        before = self.git("write-tree")
        with self.assertRaisesRegex(PublicationWorkspaceError, "index contains"):
            self.run_task()
        self.assertEqual(self.git("write-tree"), before)

    def test_verifier_modifying_files_cannot_commit(self):
        def tamper(_):
            (self.root / INDEX).write_text("wrong after verification\n")
        with self.assertRaisesRegex(PublicationWorkspaceError, "bytes drifted"):
            self.run_task(verify=tamper)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)

    def test_symlink_and_hardlink_target_preserved(self):
        target = self.root / LEDGER
        original = target.read_bytes()
        outside = Path(self.temporary.name) / "outside"
        outside.write_bytes(original)
        for mode in ("symlink", "hardlink"):
            target.unlink()
            if mode == "symlink":
                target.symlink_to(outside)
            else:
                os.link(outside, target)
            with self.assertRaisesRegex(PublicationWorkspaceError, "single-link regular"):
                self.run_task()
            self.assertEqual(outside.read_bytes(), original)

    def test_wrong_branch_and_primary_worktree_are_refused(self):
        self.git("switch", "-c", "docs/wrong-task")
        with self.assertRaisesRegex(PublicationWorkspaceError, "branch is not operation-bound"):
            self.run_task()
        self.fixture.git("switch", self.branch)
        with self.assertRaisesRegex(PublicationWorkspaceError, "dedicated linked worktree"):
            PublicationWorkspace(self.fixture.root).prepare(**self.arguments)

    def test_exclusive_lock_refuses_second_writer(self):
        gitdir = Path(self.git("rev-parse", "--absolute-git-dir"))
        with RequestJournal(gitdir / "lmdj-publication-workspace"):
            with self.assertRaises(JournalError):
                self.run_task()
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)

    def test_injected_git_environment_does_not_redirect_index_or_repository(self):
        outside = Path(self.temporary.name) / "foreign-index"
        with patch.dict(os.environ, {"GIT_INDEX_FILE": str(outside), "GIT_DIR": "/nonexistent",
            "GIT_WORK_TREE": "/nonexistent", "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.bare", "GIT_CONFIG_VALUE_0": "true"}):
            result = self.run_task()
        self.assertEqual(self.git("rev-parse", "HEAD"), result["commit"])
        self.assertFalse(outside.exists())

    def test_tampered_binding_is_not_recreated(self):
        self.run_task()
        gitdir = Path(self.git("rev-parse", "--absolute-git-dir"))
        binding = gitdir / "lmdj-publication-workspace/binding.json"
        binding.write_bytes(b"corrupt retained bytes")
        with self.assertRaisesRegex(PublicationWorkspaceError, "binding changed"):
            self.run_task()
        self.assertEqual(binding.read_bytes(), b"corrupt retained bytes")

    def test_checkout_filter_is_refused_before_installation(self):
        common = Path(self.git("rev-parse", "--path-format=absolute", "--git-common-dir"))
        (common / "info/attributes").write_text(LEDGER + " filter=fixture\n")
        self.git("config", "filter.fixture.smudge", "false")
        with self.assertRaisesRegex(PublicationWorkspaceError, "checkout-transforming attributes"):
            self.run_task()
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_incomplete_pending_binding_is_preserved_not_guessed(self):
        gitdir = Path(self.git("rev-parse", "--absolute-git-dir"))
        with RequestJournal(gitdir / "lmdj-publication-workspace") as journal:
            pending = journal.root / "binding.pending"
            pending.write_bytes(b"partial")
            pending.chmod(0o600)
        with self.assertRaisesRegex(PublicationWorkspaceError, "pending operation binding is incomplete or changed"):
            self.run_task()
        self.assertEqual(pending.read_bytes(), b"partial")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)


if __name__ == "__main__":
    unittest.main()
