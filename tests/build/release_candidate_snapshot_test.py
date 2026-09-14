#!/usr/bin/env python3
"""Real command/journal lifecycle; Portal content semantics use companion Node tests."""
import json
from copy import deepcopy
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import release_candidate_workspace_test as fixture_module
from tools.release.candidate_snapshot import CandidateSnapshotRun, CandidateSnapshotError
from tools.release.candidate_workspace import CandidateSourceWorkspace
from tools.release.model import canonical_sha256
from tools.release.orchestration import RequestJournal, JournalError

SCRIPT = '''set -eu
case "$1" in
version)
  printf 'version\\n' >> .fixture-calls
  mkdir -p apps/docs-site/versioned_metadata
  printf complete > "apps/docs-site/versioned_metadata/version-$2.json"
  printf '["%s"]\\n' "$2" > apps/docs-site/versions.json
  test ! -f .fixture-fail-generation || exit 23
  ;;
resume-version)
  printf 'resume\\n' >> .fixture-calls
  test "$4" = "$(git rev-parse HEAD)"
  test "$(cat "apps/docs-site/versioned_metadata/version-$2.json")" = complete
  ;;
*) exit 64 ;;
esac
'''


class SnapshotStateTest(unittest.TestCase):
    def test_oversized_state_cannot_replace_a_readable_receipt(self):
        journal = Mock()
        CandidateSnapshotRun._save(journal, {"fixture":"small"})
        self.assertEqual(journal._write.call_count, 1)
        with self.assertRaisesRegex(CandidateSnapshotError, "durable read bound"):
            CandidateSnapshotRun._save(journal, {"fixture":"x" * 65536})
        self.assertEqual(journal._write.call_count, 1)


class SnapshotFixture(fixture_module.WorkspaceFixture):
    def setUp(self):
        # Extend the actual material fixture before creating its source worktree.
        self.fixture = fixture_module.material_fixture.MaterialTest()
        self.addCleanup(self.fixture.doCleanups)
        commit = self.fixture.commit
        def initial_commit():
            # Include fixed fixture inputs before the actual first commit/freeze,
            # instead of repeating both after MaterialTest.setUp has completed.
            canonical = self.fixture.root / "apps/architecture-portal"
            canonical.mkdir(parents=True)
            (canonical / "versions.json").write_text("[]\n")
            (canonical / "versioned_metadata").mkdir()
            (canonical / "versioned_metadata/.gitkeep").touch()
            alias = self.fixture.root / "apps/docs-site"
            alias.mkdir(parents=True)
            (alias / "versions.json").symlink_to("../architecture-portal/versions.json")
            (alias / "versioned_metadata").symlink_to("../architecture-portal/versioned_metadata")
            (self.fixture.root / "scripts").mkdir()
            (self.fixture.root / "scripts/docs-site.sh").write_text(SCRIPT)
            (self.fixture.root / ".gitignore").write_text(".fixture-*\n")
            return commit()
        with patch.object(self.fixture, "commit", side_effect=initial_commit):
            self.fixture.setUp()
        self.request = self.fixture.request
        self.request["base_revision"] = self.fixture.base
        operation = canonical_sha256({"request":canonical_sha256(self.request), "step":"candidate"})
        self.branch = "feat/release-candidate-" + operation
        self.root = self.fixture.container / "worktree"
        self.fixture.git("-c", "core.symlinks=true", "worktree", "add", "-b", self.branch, str(self.root), self.fixture.base)
        self.tool = CandidateSourceWorkspace(self.root, self.fixture.tool)
        self.calls = []
        self.source = self.prepare()
        self.authorities = []
        self.runner = CandidateSnapshotRun(self.tool, authorize=self.authorities.append, path=os.environ["PATH"])
        self.journal = Path(self.tool.git("rev-parse", "--absolute-git-dir").decode().strip()) / self.tool.JOURNAL_NAME

    def run_snapshot(self):
        return self.runner.run(self.request, self.source)

    def commands(self):
        return (self.root / ".fixture-calls").read_text().splitlines()


class SnapshotRecoveryTest(SnapshotFixture):
    def test_actual_source_to_generation_and_fresh_resume(self):
        first = self.run_snapshot()
        self.assertEqual(first["status"], "snapshot-verified")
        self.assertEqual(first["source_commit"], self.source["commit"])
        self.assertEqual(self.commands(), ["version", "resume"])
        second = self.run_snapshot()
        self.assertEqual(second["sha256"], first["sha256"])
        self.assertNotEqual(second["command_history_sha256"], first["command_history_sha256"])
        self.assertEqual(self.commands(), ["version", "resume", "resume"])
        self.assertEqual(self.tool.revision("HEAD"), self.source["commit"])
        self.assertGreaterEqual(len(self.authorities), 8)
        state = json.loads((self.journal / "snapshot-state.json").read_bytes())["state"]
        self.assertEqual({entry["path"] for entry in state["snapshot"]}, {
            "apps/architecture-portal/versions.json",
            f"apps/architecture-portal/versioned_metadata/version-{self.source['product_build']}.json"})
        self.assertEqual(os.readlink(self.root / "apps/docs-site/versions.json"),
                         "../architecture-portal/versions.json")

    def test_failed_generation_keeps_exit_and_only_resumes_later(self):
        (self.root / ".fixture-fail-generation").touch()
        with self.assertRaisesRegex(CandidateSnapshotError, "version exited 23"):
            self.run_snapshot()
        self.assertEqual(self.commands(), ["version"])
        self.run_snapshot()
        self.assertEqual(self.commands(), ["version", "resume"])
        state = json.loads((self.journal / "snapshot-state.json").read_bytes())["state"]
        self.assertEqual(state["commands"][0]["result"][0], 23)

    def test_process_death_after_generation_does_not_repeat_it(self):
        child = os.fork()
        if child == 0:
            original = self.runner.executor._execute
            def crash(*args, **kwargs):
                original(*args, **kwargs)
                os._exit(24)
            with patch.object(self.runner.executor, "_execute", side_effect=crash):
                self.run_snapshot()
            os._exit(99)
        _, child_status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(child_status), 24)
        self.run_snapshot()
        self.assertEqual(self.commands(), ["version", "resume"])
        state = json.loads((self.journal / "snapshot-state.json").read_bytes())["state"]
        self.assertIsNone(state["commands"][0]["result"])

    def test_process_death_after_enrollment_refuses_fresh_generation(self):
        child = os.fork()
        if child == 0:
            original = RequestJournal._write
            def crash(journal, name, raw):
                original(journal, name, raw)
                if name == "snapshot-operation.json": os._exit(25)
            with patch.object(RequestJournal, "_write", crash):
                self.run_snapshot()
            os._exit(99)
        _, child_status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(child_status), 25)
        with self.assertRaisesRegex(CandidateSnapshotError, "state disappeared"):
            self.run_snapshot()
        self.assertFalse((self.root / ".fixture-calls").exists())


class SnapshotSafetyTest(SnapshotFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Safety cases consume independent copies of one REAL installed source;
        # recovery cases above still perform the full producer journey per case.
        # Restore the same temporary absolute paths, so Git worktree pointers and
        # durable identities are never rewritten. This class must run serially.
        seed = SnapshotFixture()
        cls.addClassCleanup(seed.doCleanups)
        seed.setUp()
        assert seed.tool._journal is None
        with RequestJournal(seed.journal):
            pass
        cls.seed_fields = {key:deepcopy(getattr(seed.fixture, key))
                           for key in ("container", "root", "state", "base", "frozen", "current")}
        cls.seed_request, cls.seed_source = deepcopy(seed.request), deepcopy(seed.source)
        cls.seed_branch, cls.seed_root = seed.branch, seed.root
        backup = tempfile.TemporaryDirectory(prefix="lmdj-snapshot-safety-seed-")
        cls.addClassCleanup(backup.cleanup)
        cls.seed_backup = Path(backup.name) / "container"
        shutil.copytree(seed.fixture.container, cls.seed_backup, symlinks=True)

    def setUp(self):
        container = self.seed_fields["container"]
        # This exact directory was created by the seed's TemporaryDirectory;
        # never derive cleanup targets from tested journal bytes or environment.
        shutil.rmtree(container)
        shutil.copytree(self.seed_backup, container, symlinks=True)
        self.fixture = fixture_module.material_fixture.MaterialTest()
        for key, value in self.seed_fields.items():
            setattr(self.fixture, key, deepcopy(value))
        self.fixture.tool = fixture_module.material_fixture.CandidateBuildMaterial(
            self.fixture.root, self.fixture.state)
        self.request, self.source = deepcopy(self.seed_request), deepcopy(self.seed_source)
        self.branch, self.root = self.seed_branch, self.seed_root
        self.tool = CandidateSourceWorkspace(self.root, self.fixture.tool)
        self.calls, self.authorities = [], []
        self.runner = CandidateSnapshotRun(self.tool, authorize=self.authorities.append, path=os.environ["PATH"])
        self.journal = Path(self.tool.git("rev-parse", "--absolute-git-dir").decode().strip()) / self.tool.JOURNAL_NAME
        self.addCleanup(self.assert_writer_closed)

    def assert_writer_closed(self):
        self.assertIsNone(self.tool._journal)
        with RequestJournal(self.journal):
            pass

    def test_missing_output_refuses_resume_without_regeneration(self):
        (self.root / ".fixture-fail-generation").touch()
        with self.assertRaisesRegex(CandidateSnapshotError, "version exited 23"):
            self.run_snapshot()
        artifact = self.root / f"apps/architecture-portal/versioned_metadata/version-{self.source['product_build']}.json"
        artifact.unlink()
        with self.assertRaisesRegex(CandidateSnapshotError, "resume-version exited"):
            self.run_snapshot()
        self.assertEqual(self.commands(), ["version", "resume"])
        self.assertFalse(artifact.exists())

    def test_verified_snapshot_byte_drift_refuses_before_another_command(self):
        self.run_snapshot()
        artifact = self.root / f"apps/architecture-portal/versioned_metadata/version-{self.source['product_build']}.json"
        artifact.write_bytes(artifact.read_bytes() + b"\n")
        with self.assertRaisesRegex(CandidateSnapshotError, "previously verified snapshot bytes changed"):
            self.run_snapshot()
        self.assertEqual(self.commands(), ["version", "resume"])
        self.assertEqual(artifact.read_bytes(), b"complete\n")

    def test_lost_state_after_enrollment_cannot_generate_again(self):
        self.run_snapshot()
        (self.journal / "snapshot-state.json").unlink()
        with self.assertRaisesRegex(CandidateSnapshotError, "state disappeared"):
            self.run_snapshot()
        self.assertEqual(self.commands(), ["version", "resume"])

    def test_tracked_command_drift_is_not_executed(self):
        (self.root / "scripts/docs-site.sh").write_text("exit 0\n")
        with self.assertRaisesRegex(CandidateSnapshotError, "tracked source files changed"):
            self.run_snapshot()
        self.assertFalse((self.root / ".fixture-calls").exists())

    def test_budget_exhaustion_never_repeats_generation(self):
        self.runner = CandidateSnapshotRun(self.tool, authorize=self.authorities.append,
                                          path=os.environ["PATH"], verification_limit=1)
        self.run_snapshot()
        with self.assertRaisesRegex(CandidateSnapshotError, "budget exhausted"):
            self.run_snapshot()
        self.assertEqual(self.commands(), ["version", "resume"])

    def test_failed_authority_cannot_start_generation(self):
        def refuse(scope):
            raise PermissionError("fixture-secret-must-not-leak")
        self.runner.authorize = refuse
        with self.assertRaisesRegex(CandidateSnapshotError, "authority is unavailable") as caught:
            self.run_snapshot()
        self.assertNotIn("fixture-secret", str(caught.exception))
        self.assertFalse((self.root / ".fixture-calls").exists())

    def test_authority_exception_type_does_not_imply_sanitized_text(self):
        def refuse(scope):
            raise JournalError("fixture-secret-must-not-leak")
        self.runner.authorize = refuse
        with self.assertRaisesRegex(CandidateSnapshotError, "authority is unavailable") as caught:
            self.run_snapshot()
        self.assertNotIn("fixture-secret", str(caught.exception))
        self.assertFalse((self.root / ".fixture-calls").exists())

    def test_source_workspace_writer_blocks_snapshot_writer(self):
        with RequestJournal(self.journal):
            with self.assertRaisesRegex(JournalError, "another writer"):
                self.run_snapshot()
        self.assertFalse((self.root / ".fixture-calls").exists())

    def test_clean_filter_cannot_hide_replaced_command_source(self):
        self.run_snapshot()
        (self.fixture.root / ".git/info/attributes").write_text("scripts/docs-site.sh filter=hide\n")
        self.fixture.git("config", "filter.hide.clean", "git show HEAD:scripts/docs-site.sh")
        (self.root / "scripts/docs-site.sh").write_text("echo UNTRUSTED > .fixture-evil\n")
        # Ordinary Git applies the actual disguise; the trusted helper already
        # disables filters. Neither path replaces the runner's raw-byte check.
        self.assertEqual(self.fixture.git("-C", str(self.root), "diff", "--name-only", "--", "scripts/docs-site.sh"), "")
        self.assertNotEqual(self.tool.git("diff", "--name-only", "--", "scripts/docs-site.sh"), b"")
        with self.assertRaisesRegex(CandidateSnapshotError, "tracked source files changed"):
            self.run_snapshot()
        self.assertFalse((self.root / ".fixture-evil").exists())
        self.assertEqual(self.commands(), ["version", "resume"])


if __name__ == "__main__":
    unittest.main()
