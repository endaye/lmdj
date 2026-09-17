#!/usr/bin/env python3
"""The shipped entry point must drive the one release driver and its journal."""

import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import tools.release.cli as cli  # noqa: E402
from tools.release.commands import CommandError, CommandResult  # noqa: E402
from tools.release.model import canonical_sha256  # noqa: E402
from tools.release.model import load_policy  # noqa: E402
from tools.release.orchestration import JournalError, RequestJournal, STEPS  # noqa: E402
from tools.release.orchestration_backend import ReleaseBackend  # noqa: E402
from tools.release.orchestration_driver import Observation  # noqa: E402


CONTROL = "b" * 40
ACTOR = 123
SIGNER = "A1B2C3D4E5F60718293A4B5C6D7E8F9012345678"


class Runner:
    """Answer only the Git questions the entry point and backend actually ask."""

    def __init__(self, gitdir):
        self.gitdir, self.calls = Path(gitdir), []

    def run(self, arguments, **kwargs):
        vector = tuple(str(argument) for argument in arguments)
        self.calls.append(vector)
        if "rev-parse" in vector and "--absolute-git-dir" in vector:
            return CommandResult(vector, 0, f"{self.gitdir}\n", "")
        if "merge-base" in vector:
            return CommandResult(vector, 0, "", "")
        raise CommandError(f"unexpected release command: {vector[0]}")


class Git:
    def __init__(self, gitdir):
        self.runner = Runner(gitdir)

    def main_revision(self):
        return CONTROL

    def is_main_ancestor(self, target):
        return target == CONTROL


class GitHub:
    def get_authenticated_actor(self):
        return ACTOR


class Policy:
    """The shipped release policy, so the orchestration policy validates for real."""

    def __init__(self):
        self.selected = load_policy(ROOT / "tools/release/policy.json")

    def __getattr__(self, name):
        return getattr(self.selected, name)


class Carrier:
    """One step's far side: one file per operation, as in the driver fixture."""

    def __init__(self, step, root, *, fail_after_write=False):
        self.step, self.root = step, Path(root)
        self.fail_after_write = fail_after_write
        self.calls = 0

    def observe(self, state, operation):
        target = self.root / operation["operation_id"]
        if not target.exists():
            return Observation("absent")
        payload = json.loads(target.read_text())
        if payload != {"request": state["request_digest"], "step": self.step}:
            return Observation("conflict")
        return Observation("verified", {"sha256": canonical_sha256(payload),
                                        "reference": f"fixture:{operation['operation_id']}"})

    def execute(self, state, operation):
        self.calls += 1
        (self.root / operation["operation_id"]).write_text(
            json.dumps({"request": state["request_digest"], "step": self.step}))
        if self.fail_after_write:
            # The write happened; the result is unknown. Upstream text must not
            # become the request's public status.
            self.fail_after_write = False
            raise RuntimeError("sensitive-upstream-error-not-for-public-status")


class ReleaseEntryPointTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        self.root, self.remote = base / "repo", base / "remote"
        self.root.mkdir()
        self.remote.mkdir()
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        self.gitdir = self.root / ".git"
        # The shipped loader reads the orchestration policy from the tree under
        # release, so the fixture tree carries the real policy document.
        policy_directory = self.root / "tools/release"
        policy_directory.mkdir(parents=True)
        shutil.copy(ROOT / "tools/release/orchestration-policy.json",
                    policy_directory / "orchestration-policy.json")
        self.context = type("Context", (), {
            "git": Git(self.gitdir), "github": GitHub(), "policy": Policy(),
        })()
        self.carriers = {step: Carrier(step, self.remote) for step in STEPS}

    def run_cli(self, arguments, carriers=None, *, capture=None):
        selected = tuple(self.carriers.values()) if carriers is None else tuple(carriers)
        stream = capture if capture is not None else io.StringIO()
        with patch.object(cli, "build_context", return_value=self.context), \
                patch.object(cli, "release_carriers", return_value=selected), \
                patch.object(cli, "compose_candidate", return_value=None), \
                contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            return cli.main(["--repo-root", str(self.root), *arguments])

    def status(self, request_id=None):
        output = io.StringIO()
        arguments = ["--repo-root", str(self.root), "status"]
        if request_id is not None:
            arguments.append(request_id)
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = cli.main(arguments)
        return code, output.getvalue()

    def journal(self):
        # The shipped status path derives this directory from Git, so a real
        # `git init` in setUp is what proves both paths agree on one journal.
        return self.gitdir / "lmdj-release-requests"

    def request_ids(self):
        if not self.journal().is_dir():
            return []
        return sorted(path.name[:-5] for path in self.journal().iterdir()
                      if path.name.endswith(".json"))

    def far_side(self):
        return sorted(path.name for path in self.remote.iterdir())

    def test_one_entry_point_drives_every_step_and_status_reads_the_same_journal(self):
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"]), 0)
        request_ids = self.request_ids()
        self.assertEqual(len(request_ids), 1)
        self.assertEqual(len(self.far_side()), len(STEPS))
        self.assertEqual([carrier.calls for carrier in self.carriers.values()], [1] * len(STEPS))

        code, report = self.status()
        self.assertEqual(code, 0)
        self.assertIn(request_ids[0], report)
        self.assertIn(f"{len(STEPS)}/{len(STEPS)}", report)

        self.assertEqual(self.run_cli(["resume", request_ids[0]]), 0)
        self.assertEqual([carrier.calls for carrier in self.carriers.values()], [1] * len(STEPS))
        self.assertEqual(len(self.far_side()), len(STEPS))

    def test_interrupted_step_resumes_without_repeating_the_external_write(self):
        publication = self.carriers["publication"]
        publication.fail_after_write = True
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"]), 2)
        self.assertEqual(publication.calls, 1)
        self.assertEqual(len(self.far_side()), STEPS.index("publication") + 1)

        code, report = self.status()
        self.assertEqual(code, 0)
        self.assertIn("outstanding intent: publication", report)

        self.assertEqual(self.run_cli(["resume", self.request_ids()[0]]), 0)
        self.assertEqual(publication.calls, 1)
        self.assertEqual(len(self.far_side()), len(STEPS))

    def test_status_before_any_request_reports_none_without_creating_a_journal(self):
        code, report = self.status()
        self.assertEqual(code, 0)
        self.assertIn("no requests", report)
        self.assertFalse(self.journal().exists())

    def test_status_of_one_request_selects_it_and_an_unknown_id_fails_closed(self):
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"]), 0)
        request_id = self.request_ids()[0]
        code, report = self.status(request_id)
        self.assertEqual(code, 0)
        self.assertIn(request_id, report)

        code, report = self.status("release-" + "0" * 16)
        self.assertEqual(code, 2)
        self.assertIn("request is missing", report)

    def test_status_reads_without_creating_state_or_joining_the_writer_lock(self):
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"]), 0)
        (self.journal() / "writer.lock").unlink()
        code, report = self.status()
        self.assertEqual(code, 0)
        self.assertIn(f"{len(STEPS)}/{len(STEPS)}", report)
        self.assertFalse((self.journal() / "writer.lock").exists())

        # A run holding the single-writer lock must stay observable.
        with RequestJournal(self.journal()):
            code, report = self.status()
        self.assertEqual(code, 0)
        self.assertIn(f"{len(STEPS)}/{len(STEPS)}", report)

    def test_one_shot_carriers_are_materialized_once(self):
        backend = ReleaseBackend(Git(self.gitdir), GitHub(),
                                 carriers=(carrier for carrier in self.carriers.values()))
        self.assertEqual(backend.missing(STEPS), ())

    def test_duplicate_carriers_are_rejected(self):
        with self.assertRaisesRegex(JournalError, "duplicate"):
            ReleaseBackend(
                Git(self.gitdir), GitHub(),
                carriers=(carrier for carrier in
                          [self.carriers["candidate"], self.carriers["candidate"]]))

    def test_status_lists_readable_requests_and_names_unreadable_entries(self):
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"]), 0)
        request_id = self.request_ids()[0]
        # A stray entry must not abort the listing with a traceback.
        (self.journal() / ("release-" + "f" * 16 + ".json")).write_text("{}\n")

        code, report = self.status()
        self.assertEqual(code, 0)
        self.assertIn(request_id, report)
        self.assertIn("unreadable journal entry", report)

    def test_unreachable_base_revision_is_refused_before_the_request_exists(self):
        output = io.StringIO()
        unreachable = "d" * 40
        self.assertEqual(
            self.run_cli(["run", "--authority", "issue:1301", "--base-revision", unreachable],
                         capture=output), 2)
        self.assertIn("canonical history", output.getvalue())
        self.assertEqual(self.request_ids(), [])

    def test_step_without_an_enrolled_carrier_refuses_before_the_request_exists(self):
        carriers = [carrier for carrier in self.carriers.values() if carrier.step != "creator"]
        output = io.StringIO()
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"], carriers, capture=output), 2)
        self.assertIn("creator", output.getvalue())
        self.assertEqual(self.request_ids(), [])
        self.assertFalse(self.journal().exists())

    def test_same_scope_run_adopts_the_unfinished_request(self):
        self.carriers["publication"].fail_after_write = True
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"]), 2)
        # A second run with different authority but the same frozen scope
        # adopts the active request and drives it to completion; the incoming
        # authority never replaces the original grant.
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1302"]), 0)
        self.assertEqual(len(self.request_ids()), 1)

    def test_other_scope_is_refused_while_a_request_is_unfinished(self):
        self.carriers["publication"].fail_after_write = True
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"]), 2)
        # A different frozen scope (different control revision) is a different
        # release and is refused while the first request is unfinished.
        main = self.context.git.main_revision
        other = "d" * 40
        self.context.git.is_main_ancestor = lambda target: target in (CONTROL, other)
        try:
            self.context.git.main_revision = lambda: other
            output = io.StringIO()
            self.assertEqual(
                self.run_cli(["run", "--authority", "issue:1302"], capture=output), 2)
            self.assertIn("unfinished", output.getvalue())
        finally:
            self.context.git.main_revision = main
            self.context.git.is_main_ancestor = lambda target: target == CONTROL
        self.assertEqual(len(self.request_ids()), 1)

    def test_resume_of_an_unknown_request_fails_closed(self):
        output = io.StringIO()
        self.assertEqual(self.run_cli(["resume", "release-" + "0" * 16], capture=output), 2)
        self.assertIn("request is missing", output.getvalue())


class RealCompositionTest(unittest.TestCase):
    """The shipped release_carriers assembles the twelve enrolled carriers.

    Only the review-reader seam is patched (the production one speaks HTTPS);
    every other composition input is answered by the fixture repository or
    the fixture GitHub stub, so this exercises the real assembly path.
    """

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        self.root = base / "repo"
        self.root.mkdir()
        subprocess.run(["git", "init", "--quiet", "-b", "main", str(self.root)],
                       check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name",
                        "Release Fixture"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email",
                        "fixture@example.invalid"], check=True)
        workflows = self.root / ".github/workflows"
        workflows.mkdir(parents=True)
        for name in ("publish-release.yml", "deploy-web-runtime-host.yml",
                     "deploy-creator-web.yml"):
            (workflows / name).write_text("name: fixture\n")
        policy_dir = self.root / "tools/release"
        policy_dir.mkdir(parents=True)
        shutil.copy(ROOT / "tools/release/orchestration-policy.json",
                    policy_dir / "orchestration-policy.json")
        storage_dir = self.root / "scripts/ci"
        storage_dir.mkdir(parents=True)
        shutil.copy(ROOT / "scripts/ci/incremental_storage.json",
                    storage_dir / "incremental_storage.json")
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "--quiet", "-m",
                        "fixture main"], check=True)
        self.control = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"],
            check=True, capture_output=True).stdout.decode().strip()
        self.gitdir = self.root / ".git"
        self.context = type("Context", (), {
            "git": CompositionGit(self.root), "github": CompositionGitHub(),
            "policy": Policy(), "repo_root": self.root,
            "tag_signer_fingerprint": SIGNER,
        })()
        self.policy = cli.build_orchestration_policy(self.root, self.context)

    def request(self):
        return cli.build_request(self.context, self.policy,
                                 authority_ref="issue:1301")

    def carriers(self, request):
        def reader(repository):
            return type("Reader", (), {
                "get": lambda self, path, fresh=False: {"id": 12}})()

        with patch("tools.release.entry_composition.release_token",
                   return_value="fixture-only-no-credential"), \
                patch("tools.release.entry_composition.production_review_reader",
                      return_value=reader):
            return cli.release_carriers(self.context, self.policy, request)

    def test_the_entry_exposes_the_fourteen_enrolled_carriers_in_order(self):
        from tools.release.carriers import (
            DeferredCandidate,
            RecoveredDispatch,
            RecoveredStep,
        )
        from tools.release.entry_composition import ENROLLED_STEPS

        carriers = self.carriers(self.request())
        self.assertEqual(tuple(carrier.step for carrier in carriers),
                         ENROLLED_STEPS)
        self.assertEqual(len(carriers), 14)
        self.assertIs(type(carriers[0]), DeferredCandidate)
        for carrier in carriers[1:]:
            self.assertIn(type(carrier), (RecoveredStep, RecoveredDispatch))
        for step in ("publication", "runtime", "creator"):
            selected = carriers[ENROLLED_STEPS.index(step)]
            self.assertIs(type(selected), RecoveredDispatch)
        for step in ("verification", "intent", "changelog", "prepared", "tag",
                     "draft", "published_record", "changelog_site", "promotion",
                     "final"):
            self.assertIs(type(carriers[ENROLLED_STEPS.index(step)]),
                          RecoveredStep)
        backend = ReleaseBackend(self.context.git, self.context.github,
                                 carriers=carriers)
        # Every driver step is owned now, so the scope refusal no longer fires.
        self.assertEqual(backend.missing(STEPS), ())
        # The refusal itself is intact; it simply has nothing to report. Drop
        # one carrier and the same check names exactly the step that is gone.
        dropped = ReleaseBackend(self.context.git, self.context.github,
                                 carriers=carriers[:-1])
        self.assertEqual(dropped.missing(STEPS), ("final",))

    def test_run_no_longer_refuses_the_scope_and_opens_one_request(self):
        request_ids = []
        journal = self.gitdir / "lmdj-release-requests"
        output = io.StringIO()
        with patch.object(cli, "build_context", return_value=self.context), \
                patch.object(cli, "compose_candidate", return_value=None), \
                patch("tools.release.entry_composition.release_token",
                      return_value="fixture-only-no-credential"), \
                patch("tools.release.entry_composition.production_review_reader",
                      return_value=lambda repository: type("Reader", (), {
                          "get": lambda self, path, fresh=False: {"id": 12}})()), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = cli.main(["--repo-root", str(self.root), "run",
                             "--authority", "issue:1301"])
        # The scope check no longer refuses: the run reaches the driver, opens
        # exactly one request and stops at the first step with no work yet.
        report = output.getvalue()
        self.assertEqual(code, 2)
        self.assertNotIn("release scope has steps without an enrolled carrier",
                         report)
        self.assertIn("verified steps: 0/14", report)
        self.assertIn("step: candidate", report)
        self.assertTrue(journal.is_dir())
        opened = sorted(path.name[:-5] for path in journal.iterdir()
                        if path.name.endswith(".json"))
        self.assertEqual(len(opened), 1)
        self.assertEqual(request_ids, [])


class CompositionGit:
    """Answer the composition's Git reads from the real fixture repository."""

    def __init__(self, root):
        self.root = Path(root)
        from tools.release.commands import CommandRunner

        self.runner = CommandRunner()

    def main_revision(self):
        return self.runner.run(
            ("git", "-C", str(self.root), "rev-parse", "main")).stdout.strip()

    def is_main_ancestor(self, target):
        try:
            self.runner.run(("git", "-C", str(self.root), "merge-base",
                             "--is-ancestor", target, "main"))
            return True
        except CommandError:
            return False

    def local_tag_state(self, tag):
        raise AssertionError("assembly never reads local tags")


class CompositionGitHub:
    def get_authenticated_actor(self):
        return ACTOR

    def get_dispatch_evidence(self, path, *, raw=False):
        workflow = path.rsplit("/", 1)[-1]
        return {"id": {"publish-release.yml": 501,
                       "deploy-web-runtime-host.yml": 502,
                       "deploy-creator-web.yml": 503}[workflow],
                "path": ".github/workflows/" + workflow}

    def get_batch_evidence(self, path, *, raw=False):
        raise AssertionError("assembly never reads batch evidence")

    def get_release_by_tag(self, repository, tag):
        raise AssertionError("assembly never reads releases")


if __name__ == "__main__":
    unittest.main()
