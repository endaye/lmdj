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

    def test_second_scope_is_refused_while_the_first_request_is_unfinished(self):
        self.carriers["publication"].fail_after_write = True
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"]), 2)
        output = io.StringIO()
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1302"], capture=output), 2)
        self.assertIn("unfinished", output.getvalue())
        self.assertEqual(len(self.request_ids()), 1)

    def test_resume_of_an_unknown_request_fails_closed(self):
        output = io.StringIO()
        self.assertEqual(self.run_cli(["resume", "release-" + "0" * 16], capture=output), 2)
        self.assertIn("request is missing", output.getvalue())


if __name__ == "__main__":
    unittest.main()
