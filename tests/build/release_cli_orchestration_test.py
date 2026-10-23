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


class VariableStore:
    """An in-memory repository Actions variable store for the freeze."""

    def __init__(self):
        self.variables = {}

    def get_repository_variable(self, repository, name):
        return self.variables.get(name)

    def create_repository_variable(self, repository, name, value):
        self.variables[name] = value

    def update_repository_variable(self, repository, name, value):
        self.variables[name] = value

    def delete_repository_variable(self, repository, name):
        self.variables.pop(name, None)


class GitHub(VariableStore):
    def get_authenticated_actor(self):
        return ACTOR


class Freeze:
    """Records the hold/release the entry point performs for its request."""

    def __init__(self, *, holder=None, refuse=False):
        self.holder, self.refuse, self.held, self.released = holder, refuse, [], []

    def read(self):
        return self.holder

    def hold(self, request_id):
        if self.refuse or (self.holder is not None and self.holder != request_id):
            raise JournalError("why: another release request holds the freeze; remedy: finish or retire it")
        self.held.append(request_id)
        self.holder = request_id

    def release(self, request_id):
        self.released.append(request_id)
        self.holder = None


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
        self.freeze = Freeze()

    def run_cli(self, arguments, carriers=None, *, capture=None):
        selected = tuple(self.carriers.values()) if carriers is None else tuple(carriers)
        stream = capture if capture is not None else io.StringIO()
        with patch.object(cli, "build_context", return_value=self.context), \
                patch.object(cli, "release_carriers", return_value=selected), \
                patch.object(cli, "release_freeze", return_value=self.freeze), \
                patch.object(cli, "release_recheck", return_value=None), \
                patch.object(cli, "release_doctor", return_value=[]), \
                patch.object(cli, "confirm_canonical_signing_keys", return_value=[]), \
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

    def test_run_holds_the_release_freeze_and_a_complete_request_releases_it(self):
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"]), 0)
        (request_id,) = self.request_ids()
        self.assertEqual(self.freeze.held, [request_id])
        self.assertEqual(self.freeze.released, [request_id])
        self.assertIsNone(self.freeze.holder)

    def test_a_blocked_request_keeps_the_freeze_and_resume_holds_it_again(self):
        carriers = dict(self.carriers)
        carriers["verification"] = Carrier("verification", self.remote, fail_after_write=True)
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"], carriers.values()), 2)
        (request_id,) = self.request_ids()
        self.assertEqual((self.freeze.held, self.freeze.released, self.freeze.holder),
                         ([request_id], [], request_id))
        self.assertEqual(self.run_cli(["resume", request_id]), 0)
        self.assertEqual(self.freeze.released, [request_id])

    def test_run_refuses_before_creating_a_request_while_another_holds_the_freeze(self):
        self.freeze = Freeze(holder="release-" + "9" * 16)
        output = io.StringIO()
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"], capture=output), 2)
        self.assertEqual(self.request_ids(), [])
        self.assertIn("another release request holds the freeze", output.getvalue())
        self.assertEqual(self.far_side(), [])

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

    def test_resume_and_status_name_the_last_swallowed_failure_until_it_clears(self):
        # The cause of an unknown step reaches the operator console through the
        # private failure note; the request state never carries it.
        self.carriers["publication"].fail_after_write = True
        output = io.StringIO()
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"], capture=output), 2)
        self.assertIn("last failure: publication unknown at ", output.getvalue())
        # A foreign exception names its type only; its text stays private.
        self.assertIn("unknown at ", output.getvalue())
        self.assertIn(": RuntimeError\n", output.getvalue())
        self.assertNotIn("sensitive", output.getvalue())
        request_id = self.request_ids()[0]
        self.assertNotIn("sensitive", (self.journal() / f"{request_id}.json").read_text())

        code, report = self.status()
        self.assertEqual(code, 0)
        self.assertIn("last failure: publication unknown", report)

        self.assertEqual(self.run_cli(["resume", request_id]), 0)
        code, report = self.status()
        self.assertNotIn("last failure", report)

    def test_a_malformed_failure_note_does_not_hide_the_listing(self):
        self.carriers["publication"].fail_after_write = True
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"]), 2)
        request_id = self.request_ids()[0]
        (self.journal() / f"{request_id}.failure").write_text("{}")
        code, report = self.status()
        self.assertEqual(code, 0)
        self.assertIn(request_id, report)
        self.assertIn("last failure: unreadable", report)

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

    def unfinished_request(self):
        # Like a request whose later steps were completed outside the entry:
        # unfinished in the journal, with no outstanding intent.
        request = {"id": "release-" + "1" * 16, "repository": "endaye/lmdj", "actor_id": 4829591,
                   "authority_ref": "issue:1301", "policy_digest": "a" * 64,
                   "control_revision": CONTROL, "base_revision": CONTROL,
                   "mode": "new", "requested_tag": None}
        with RequestJournal(self.journal()) as journal:
            journal.create(request)
        return request["id"]

    def candidate_intent_request(self, *, head_sha=None, ordinal=1):
        # Like a request whose candidate cut began and was left outstanding,
        # with its managed cut Pull Request record in the operations journal.
        from tools.release.orchestration import STEPS
        unfinished = self.unfinished_request
        if ordinal != 1:
            def unfinished():
                request = {"id": "release-" + str(ordinal) * 16, "repository": "endaye/lmdj",
                           "actor_id": 4829591, "authority_ref": "issue:1301",
                           "policy_digest": "a" * 64, "control_revision": CONTROL,
                           "base_revision": CONTROL, "mode": "new", "requested_tag": None}
                with RequestJournal(self.journal()) as journal:
                    journal.create(request)
                return request["id"]
        request_id = unfinished()
        head = head_sha or "a" * 40
        with RequestJournal(self.journal()) as journal:
            state = journal.read(request_id)
            begun = journal.begin(request_id, STEPS[0])
        pr_state = {"number": 2073, "spec": {"operation_id": begun["operation_id"],
                                             "head_sha": head}}
        pr_path = (self.journal() / "operations" / request_id / "candidate-transition"
                   / "cut-pr" / "pr" / "pr-state.json")
        pr_path.parent.mkdir(parents=True, exist_ok=True)
        pr_path.write_text(json.dumps(pr_state))
        return request_id

    def retire(self, request_id, tag, *, reserved="1.0.61.0", audit_code="ok",
               disposition="published"):
        from tools.release.audit import AuditFinding, AuditReport
        from tools.release.candidate import CandidateReservations
        from tools.release.model import Disposition
        from scripts.version import ProductVersion
        calls = []
        entry = type("Entry", (), {"tag": tag, "disposition": Disposition(disposition)})()
        context = type("AuditContext", (), {"ledger": type("Ledger", (), {"entries": (entry,)})()})()

        def audit(selected, *, remote, tag):
            calls.append(tag)
            return AuditReport("2026-09-28T00:00:00Z", "endaye/lmdj", "remote",
                               (AuditFinding(audit_code, tag, "remote tag matches canonical intent"),))

        version = ProductVersion(*map(int, reserved.split(".")))
        output = io.StringIO()
        self.retire_freeze = Freeze(holder=request_id)
        with patch.object(CandidateReservations, "recorded", return_value=version), \
                patch.object(cli, "build_audit_context", return_value=context), \
                patch.object(cli, "retire_freeze", return_value=self.retire_freeze), \
                patch.object(cli, "audit", side_effect=audit), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = cli.main(["--repo-root", str(self.root), "retire", request_id,
                             "--superseded-by", tag])
        return code, output.getvalue(), calls

    def retire_unreleased(self, request_id, build, *, reserved="1.0.64.0", on_main="1.0.65.0",
                          remote_tag=None, disposition=None, pull_request=None):
        from tools.release.candidate import CandidateReservations
        from tools.release.model import Disposition
        from scripts.version import ProductVersion
        calls = []
        version = lambda text: ProductVersion(*map(int, text.split(".")))
        entries = () if disposition is None else (
            type("Entry", (), {"tag": f"lmdj-v{reserved}", "disposition": Disposition(disposition)})(),)
        git = type("Git", (), {"main_revision": lambda self: "f" * 40,
                                "remote_tag_object": lambda self, tag: calls.append(tag) or remote_tag})()

        class GitHub:
            def get_pull_request(self, repository, number):
                calls.append(("pulls", number))
                return pull_request(number) if pull_request is not None else None

        context = type("Context", (), {
            "git": git, "ledger": type("Ledger", (), {"entries": entries})(),
            "github": GitHub(),
            "policy": type("Policy", (), {"repository": "endaye/lmdj"}),
        })()
        output = io.StringIO()
        self.retire_freeze = Freeze(holder=request_id)
        with patch.object(CandidateReservations, "recorded", return_value=version(reserved)), \
                patch.object(CandidateReservations, "version_at", return_value=version(on_main)), \
                patch.object(cli, "retire_freeze", return_value=self.retire_freeze), \
                patch.object(cli, "build_context", side_effect=lambda root: calls.append("context") or context), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = cli.main(["--repo-root", str(self.root), "retire", request_id,
                             "--superseded-by-build", build])
        return code, output.getvalue(), calls

    def editorial(self, request_id, pair, *, disposition="releasable", freeze_error=None):
        import tools.release.changelog as changelog_module
        from tools.release.candidate import CandidateReservations
        from tools.release.model import Disposition
        from scripts.version import ProductVersion
        intent = type("Intent", (), {"tag": "lmdj-v1.0.66.0",
                                     "disposition": Disposition(disposition)})()
        ledger = type("Ledger", (), {"intent_for_tag": lambda self, tag: intent
                                     if tag == intent.tag else None})()
        context = type("Context", (), {"ledger": ledger})()
        frozen = {"commits": ["a" * 40, "b" * 40],
                  "baseline": {"tag": "lmdj-v1.0.61.0", "target_revision": "c" * 40}}

        def freeze(root, selected, selected_ledger, changes, exclusions):
            if freeze_error is not None:
                raise changelog_module.ChangelogError(freeze_error)
            return dict(frozen, changes=changes, exclusions=exclusions)

        source = self.root / "editorial.json"
        source.write_text(json.dumps(pair))
        output = io.StringIO()
        with patch.object(CandidateReservations, "recorded",
                          return_value=ProductVersion(1, 0, 66, 0)), \
                patch.object(cli, "build_context", return_value=context), \
                patch.object(changelog_module, "freeze", side_effect=freeze), \
                patch.object(changelog_module, "binding", return_value={
                    "schema": "lmdj.release-changelog.v1", "sha256": "1" * 64,
                    "notes_sha256": "2" * 64}), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = cli.main(["--repo-root", str(self.root), "editorial", request_id, str(source)])
        return code, output.getvalue()

    def recorded_editorial(self, request_id):
        from tools.release.changelog_editorial import read
        return read(self.journal() / "operations" / request_id, request_id=request_id)

    def test_editorial_is_frozen_then_recorded_once_for_the_request(self):
        request_id = self.unfinished_request()
        pair = {"changes": [], "exclusions": [{"commit": "a" * 40, "reason": "documentation only"}]}
        code, report = self.editorial(request_id, pair)
        self.assertEqual(code, 0, report)
        self.assertIn("covers all 2 source commits since lmdj-v1.0.61.0", report)
        recorded = self.recorded_editorial(request_id)
        self.assertEqual((recorded["tag"], recorded["exclusions"]), ("lmdj-v1.0.66.0", pair["exclusions"]))
        self.assertEqual(recorded["binding"]["sha256"], "1" * 64)
        # Re-recording the identical editorial is a no-op; a different one is refused.
        self.assertEqual(self.editorial(request_id, pair)[0], 0)
        code, report = self.editorial(request_id, dict(pair, changes=[{"category": "fix"}]))
        self.assertEqual(code, 2, report)
        self.assertIn("differs from the editorial already recorded", report)
        self.assertEqual(self.recorded_editorial(request_id)["changes"], [])

    def test_editorial_without_complete_coverage_or_releasable_intent_is_not_recorded(self):
        request_id = self.unfinished_request()
        pair = {"changes": [], "exclusions": []}
        code, report = self.editorial(request_id, pair, freeze_error="source commit is not covered")
        self.assertEqual(code, 2, report)
        self.assertIn("source commit is not covered", report)
        code, report = self.editorial(request_id, pair, disposition="published")
        self.assertEqual(code, 2, report)
        self.assertIn("no releasable intent", report)
        self.assertIsNone(self.recorded_editorial(request_id))

    def test_retire_unreleased_candidate_superseded_by_a_later_build(self):
        request_id = self.unfinished_request()
        code, report, calls = self.retire_unreleased(request_id, "1.0.65.0")
        self.assertEqual(code, 0, report)
        self.assertIn("(1.0.64.0, never published) superseded by Build 1.0.65.0", report)
        self.assertEqual(calls, ["context", "lmdj-v1.0.64.0"])
        self.assertEqual(self.request_ids(), [])
        with RequestJournal(self.journal()) as journal:
            retirement = journal.read_retirement(request_id)["retirement"]
        self.assertEqual((retirement["identity"], retirement["superseded_by_build"],
                          retirement["main_revision"]), ("1.0.64.0", "1.0.65.0", "f" * 40))

    def test_retire_unreleased_refuses_a_build_that_is_not_later_before_any_network(self):
        request_id = self.unfinished_request()
        for build in ("1.0.64.0", "1.0.63.0", "1.1.65.0"):
            code, report, calls = self.retire_unreleased(request_id, build)
            self.assertEqual((code, calls), (2, []))
            self.assertIn("not a later BUILD", report)
        self.assertEqual(self.request_ids(), [request_id])

    def test_retire_unreleased_requires_main_to_carry_the_build(self):
        request_id = self.unfinished_request()
        code, report, _ = self.retire_unreleased(request_id, "1.0.65.0", on_main="1.0.64.0")
        self.assertEqual(code, 2)
        self.assertIn("canonical main does not carry the superseding Build", report)
        self.assertEqual(self.request_ids(), [request_id])

    def test_retire_unreleased_refuses_a_tagged_or_releasable_build(self):
        request_id = self.unfinished_request()
        code, report, _ = self.retire_unreleased(request_id, "1.0.65.0", remote_tag="a" * 40)
        self.assertEqual(code, 2)
        self.assertIn("the reserved Build was tagged", report)
        for disposition in ("releasable", "published"):
            code, report, _ = self.retire_unreleased(request_id, "1.0.65.0", disposition=disposition)
            self.assertEqual(code, 2)
            self.assertIn("releasable or published intent", report)
        self.assertEqual(self.request_ids(), [request_id])

    def test_retire_unreleased_settles_an_outstanding_candidate_intent_by_a_closed_cut(self):
        request_id = self.candidate_intent_request()
        head = "a" * 40
        # GitHub fills merge_commit_sha even for a closed Pull Request that
        # never merged; the merged boolean and state are the settle facts.
        closed = lambda number: {"number": number, "state": "closed", "merged": False,
                                 "merge_commit_sha": "b" * 40, "head_sha": head,
                                 "title": "chore(release): allocate 1.0.64.0 candidate"}
        code, report, calls = self.retire_unreleased(request_id, "1.0.65.0", pull_request=closed)
        self.assertEqual(code, 0, report)
        self.assertIn("pull request #2073: closed unmerged", report)
        self.assertIn(("pulls", 2073), calls)
        with RequestJournal(self.journal()) as journal:
            retirement = journal.read_retirement(request_id)["retirement"]
        self.assertEqual(retirement["settled_intent"]["pull_request"], 2073)
        self.assertEqual(retirement["settled_intent"]["head_sha"], head)
        self.assertFalse(retirement["settled_intent"]["merged"])
        self.assertEqual(self.request_ids(), [])

        # A merged cut is equally terminal and settles with its merge commit.
        request_id = self.candidate_intent_request(ordinal=2)
        merged = lambda number: {"number": number, "state": "closed", "merged": True,
                                 "merge_commit_sha": "c" * 40, "head_sha": head,
                                 "title": "chore(release): allocate 1.0.64.0 candidate"}
        code, report, _ = self.retire_unreleased(request_id, "1.0.65.0", pull_request=merged)
        self.assertEqual(code, 0, report)
        self.assertIn("pull request #2073: merged at head", report)
        self.assertIn("c" * 40, report)
        with RequestJournal(self.journal()) as journal:
            retirement = journal.read_retirement(request_id)["retirement"]
        self.assertTrue(retirement["settled_intent"]["merged"])
        self.assertEqual(retirement["settled_intent"]["merge_commit_sha"], "c" * 40)

    def test_retire_unreleased_refuses_an_unsettleable_candidate_intent(self):
        request_id = self.candidate_intent_request()
        head = "a" * 40
        for row in ({"number": 2073, "state": "open", "merged": False,
                     "merge_commit_sha": None, "head_sha": head,
                     "title": "chore(release): allocate 1.0.64.0 candidate"},
                    {"number": 2073, "state": "open", "merged": False,
                     "merge_commit_sha": None, "head_sha": head,
                     "title": "chore(release): allocate 1.0.64.0 candidate"},
                    {"number": 2073, "state": "closed", "merged": True,
                     "merge_commit_sha": "b" * 40, "head_sha": "d" * 40,
                     "title": "chore(release): allocate 1.0.64.0 candidate"},
                    {"number": 2073, "state": "closed", "merged": False,
                     "merge_commit_sha": None, "head_sha": "c" * 40,
                     "title": "chore(release): allocate 1.0.64.0 candidate"},
                    {"number": 2073, "state": "closed", "merged": False,
                     "merge_commit_sha": None, "head_sha": head,
                     "title": "chore(release): allocate 9.9.99.0 candidate"}):
            code, report, _ = self.retire_unreleased(request_id, "1.0.65.0",
                                                     pull_request=lambda number: row)
            self.assertEqual(code, 2)
            self.assertIn("not terminal", report)
            self.assertEqual(self.request_ids(), [request_id])
        # A missing Pull Request far side settles nothing either.
        code, report, _ = self.retire_unreleased(request_id, "1.0.65.0", pull_request=None)
        self.assertEqual(code, 2)
        self.assertIn("cut Pull Request is missing", report)
        self.assertEqual(self.request_ids(), [request_id])

    def test_retire_refuses_a_tag_that_is_not_the_reserved_build_before_auditing(self):
        request_id = self.unfinished_request()
        code, report, calls = self.retire(request_id, "lmdj-v1.0.62.0")
        self.assertEqual(code, 2)
        self.assertIn("not the Build this request reserved", report)
        self.assertEqual(calls, [])
        self.assertEqual(self.request_ids(), [request_id])

    def test_retire_requires_a_passing_audit_of_a_published_release(self):
        request_id = self.unfinished_request()
        code, report, calls = self.retire(request_id, "lmdj-v1.0.61.0", audit_code="conflict")
        self.assertEqual((code, calls), (2, ["lmdj-v1.0.61.0"]))
        self.assertIn("remote audit must pass", report)
        code, report, _ = self.retire(request_id, "lmdj-v1.0.61.0", disposition="releasable")
        self.assertEqual(code, 2)
        self.assertIn("only a published release", report)
        self.assertEqual(self.request_ids(), [request_id])

    def test_a_published_supersession_retires_over_an_outstanding_intent(self):
        # 1.0.66.0: the driver's publication intent stayed outstanding while the
        # Build was published through the per-command path. The published,
        # audited Build settles it; the intent stays in the retained record.
        self.carriers["publication"].fail_after_write = True
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"]), 2)
        (request_id,) = self.request_ids()
        code, report, _ = self.retire(request_id, "lmdj-v1.0.61.0")
        self.assertEqual(code, 0, report)
        self.assertEqual(self.request_ids(), [])
        with RequestJournal(self.journal(), writable=False) as journal:
            retained = journal.read_retirement(request_id)
        self.assertEqual(retained["original"]["transitions"][-1]["status"], "intent")

    def test_an_unreleased_supersession_refuses_an_outstanding_intent(self):
        self.carriers["publication"].fail_after_write = True
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"]), 2)
        (request_id,) = self.request_ids()
        code, report, _ = self.retire_unreleased(request_id, "1.0.62.0", reserved="1.0.61.0",
                                                 on_main="1.0.62.0")
        self.assertEqual(code, 2)
        self.assertIn("outstanding intent", report)
        self.assertEqual(self.request_ids(), [request_id])

    def test_retired_request_no_longer_blocks_a_new_scope(self):
        request_id = self.unfinished_request()
        code, report, _ = self.retire(request_id, "lmdj-v1.0.61.0")
        self.assertEqual(code, 0, report)
        self.assertIn(f"release request retired: {request_id} superseded by lmdj-v1.0.61.0", report)
        self.assertEqual(self.request_ids(), [])
        self.assertTrue((self.journal() / f"{request_id}.retired").is_file())
        other = "d" * 40
        main = self.context.git.main_revision
        self.context.git.is_main_ancestor = lambda target: target in (CONTROL, other)
        try:
            self.context.git.main_revision = lambda: other
            self.assertEqual(self.run_cli(["run", "--authority", "issue:1302"]), 0)
        finally:
            self.context.git.main_revision = main
            self.context.git.is_main_ancestor = lambda target: target == CONTROL
        self.assertEqual(len(self.request_ids()), 1)
        self.assertNotEqual(self.request_ids(), [request_id])

    def test_run_and_resume_enroll_the_composed_recheck_on_the_backend(self):
        # The driver receives the composed verified-transition recheck, so a
        # resume rechecks verified steps cheaply instead of re-observing them.
        seen = []
        real_driver = cli.ReleaseDriver

        class Driver:
            def __init__(self, root, policy, backend, **kwargs):
                seen.append(backend)
                self.inner = real_driver(root, policy, backend, **kwargs)

            def run(self, request):
                return self.inner.run(request)

            def resume(self, request_id):
                return self.inner.resume(request_id)

        recheck = type("Recheck", (), {"recheck": lambda self, state, operation: None})()
        with patch.object(cli, "build_context", return_value=self.context), \
                patch.object(cli, "release_carriers", return_value=tuple(self.carriers.values())), \
                patch.object(cli, "release_doctor", return_value=[]), \
                patch.object(cli, "confirm_canonical_signing_keys", return_value=[]), \
                patch.object(cli, "release_recheck", return_value=recheck) as composed, \
                patch.object(cli, "compose_candidate", return_value=None), \
                patch.object(cli, "ReleaseDriver", Driver), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["--repo-root", str(self.root), "run",
                                       "--authority", "issue:1301"]), 0)
            (request_id,) = self.request_ids()
            self.assertEqual(cli.main(["--repo-root", str(self.root), "resume", request_id]), 0)
        self.assertEqual(len(seen), 2)
        self.assertEqual(composed.call_count, 2)
        for backend in seen:
            self.assertIs(backend._recheck, recheck)

    def test_reprove_reaches_the_prepare_context_and_defaults_off(self):
        # `prepare --reprove`, `run --reprove` and `resume --reprove` select the
        # complete local Web Host proof; without the flag prepare relies on the
        # candidate batch evidence and builds reproducibly only (#2422 item 4).
        from tools.release.profiles import ProfileRuntime

        seen = []
        real_runtime = ProfileRuntime

        def recording_runtime(**fields):
            seen.append(fields.get("reprove", "absent"))
            return real_runtime(**fields)

        git, github = self.context.git, self.context.github
        fake_git = type("FetchingGit", (), {
            "runner": git.runner, "main_revision": git.main_revision,
            "is_main_ancestor": git.is_main_ancestor,
            "fetch_authority": lambda self, repository, branch: None,
            "detached_worktree": lambda self, revision: contextlib.nullcontext(self_root),
        })()
        self_root = self.root
        reader = lambda tree: (self.context.policy.selected, type("Ledger", (), {})())
        # A resume reaches the context only for a request the journal holds.
        self.carriers["publication"].fail_after_write = True
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"]), 2)
        (known,) = self.request_ids()
        for arguments, expected in ((["prepare", "lmdj-v1.0.61.0"], False),
                                    (["prepare", "lmdj-v1.0.61.0", "--reprove"], True),
                                    (["run", "--authority", "issue:1301", "--reprove"], True),
                                    (["resume", known], False),
                                    (["resume", known, "--reprove"], True)):
            with self.subTest(arguments=arguments):
                seen.clear()
                with patch.object(cli, "ProfileRuntime", recording_runtime), \
                        patch.object(cli, "GitRepository", return_value=fake_git), \
                        patch.object(cli, "_authenticated_github_client", return_value=github), \
                        patch.object(cli, "load_authority_documents", reader), \
                        patch.object(cli, "release_doctor", return_value=[]), \
                        patch.object(cli, "confirm_canonical_signing_keys", return_value=[]), \
                        patch.object(cli, "prepare", side_effect=CommandError("stop after context")), \
                        patch.object(cli, "build_orchestration_policy", side_effect=CommandError("stop after context")), \
                        contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    cli.main(["--repo-root", str(self.root), *arguments])
                self.assertEqual(seen, [expected])

    def test_reprove_is_recorded_with_the_request_and_kept_on_resume(self):
        # `run --reprove` records the request's wish beside its operation
        # journals; a later `resume` without the flag keeps the complete local
        # proof instead of silently building reproducibly only (#2453 review).
        from tools.release.profiles import ProfileRuntime

        seen = []
        real_runtime = ProfileRuntime

        def recording_runtime(**fields):
            seen.append(fields.get("reprove", "absent"))
            return real_runtime(**fields)

        git, github = self.context.git, self.context.github
        self_root = self.root
        fake_git = type("FetchingGit", (), {
            "runner": git.runner, "main_revision": git.main_revision,
            "is_main_ancestor": git.is_main_ancestor,
            "fetch_authority": lambda self, repository, branch: None,
            "detached_worktree": lambda self, revision: contextlib.nullcontext(self_root),
        })()
        reader = lambda tree: (self.context.policy.selected, type("Ledger", (), {})())
        carriers = tuple(self.carriers.values())

        def main(*arguments):
            seen.clear()
            with patch.object(cli, "ProfileRuntime", recording_runtime), \
                    patch.object(cli, "GitRepository", return_value=fake_git), \
                    patch.object(cli, "_authenticated_github_client", return_value=github), \
                    patch.object(cli, "load_authority_documents", reader), \
                    patch.object(cli, "release_doctor", return_value=[]), \
                    patch.object(cli, "confirm_canonical_signing_keys", return_value=[]), \
                    patch.object(cli, "release_carriers", return_value=carriers), \
                    patch.object(cli, "release_recheck", return_value=None), \
                    patch.object(cli, "compose_candidate", return_value=None), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return cli.main(["--repo-root", str(self.root), *arguments])

        self.carriers["publication"].fail_after_write = True
        self.assertEqual(main("run", "--authority", "issue:1301", "--reprove"), 2)
        self.assertEqual(seen, [True])
        (request_id,) = self.request_ids()
        marker = self.journal() / "operations" / request_id / "reprove-requested"
        self.assertTrue(marker.is_file())
        self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
        code, report = self.status()
        self.assertEqual(code, 0)
        self.assertIn("complete local Web Host proof requested (--reprove)", report)
        # The flag is kept on a resume that does not repeat it.
        self.assertEqual(main("resume", request_id), 0)
        self.assertEqual(seen, [True])
        # Another request that never asked for it still builds reproducibly.
        marker.unlink()
        self.assertEqual(main("resume", request_id), 0)
        self.assertEqual(seen, [False])
        code, report = self.status()
        self.assertNotIn("--reprove", report)

    def test_reprove_marker_follows_the_request_lifecycle(self):
        # Unknown request: nothing is recorded. Retired request: the marker is
        # cleared so a re-created identical scope starts without it.
        output = io.StringIO()
        self.assertEqual(self.run_cli(["resume", "release-" + "0" * 16, "--reprove"], capture=output), 2)
        self.assertFalse((self.journal() / "operations" / ("release-" + "0" * 16)).exists())
        request_id = self.unfinished_request()
        cli.record_reprove(self.root, self.context.git, request_id)
        cli.record_reprove(self.root, self.context.git, request_id)  # idempotent
        marker = self.journal() / "operations" / request_id / "reprove-requested"
        self.assertTrue(marker.is_file())
        code, report, _ = self.retire_unreleased(request_id, "1.0.65.0")
        self.assertEqual(code, 0, report)
        self.assertFalse(marker.exists())
        # The published-supersession retirement clears it too.
        self.carriers["publication"].fail_after_write = True
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"]), 2)
        (request_id,) = self.request_ids()
        cli.record_reprove(self.root, self.context.git, request_id)
        marker = self.journal() / "operations" / request_id / "reprove-requested"
        self.assertTrue(marker.is_file())
        code, report, _ = self.retire(request_id, "lmdj-v1.0.61.0")
        self.assertEqual(code, 0, report)
        self.assertFalse(marker.exists())

    def test_run_resume_and_prepare_refuse_while_the_doctor_fails(self):
        # The host preflight runs first and a failed check stops the long
        # local path before any context, request or build exists (#2422 item 5).
        from tools.release.doctor import Check

        failed = [Check("emsdk", "fail", "no emsdk at /x", "install emsdk 6.0.5 under /x"),
                  Check("gh auth", "ok", "GITHUB_TOKEN is set")]
        # The resume case names a request the journal holds; an unknown one is
        # the journal's finding and is reported before the doctor.
        self.carriers["publication"].fail_after_write = True
        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"]), 2)
        (known,) = self.request_ids()
        for arguments in (["run", "--authority", "issue:1301"],
                          ["resume", known],
                          ["prepare", "lmdj-v1.0.61.0"]):
            with self.subTest(arguments=arguments):
                output, errors = io.StringIO(), io.StringIO()
                with patch.object(cli, "release_doctor", return_value=failed), \
                        patch.object(cli, "build_context", side_effect=AssertionError("context built")), \
                        contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    code = cli.main(["--repo-root", str(self.root), *arguments])
                self.assertEqual(code, 2)
                self.assertIn("[fail] emsdk: no emsdk at /x", output.getvalue())
                self.assertIn("remedy: install emsdk 6.0.5 under /x", output.getvalue())
                self.assertIn(f"release doctor: refusing {arguments[0]}", errors.getvalue())
        self.assertEqual(self.request_ids(), [known])
        # Read-only commands never wait on the doctor.
        with patch.object(cli, "release_doctor", side_effect=AssertionError("doctor ran")):
            code, report = self.status()
        self.assertEqual(code, 0)

    def test_the_signing_keys_are_rechecked_against_the_canonical_policy(self):
        # The doctor reads the checkout's policy before any fetch; after the
        # canonical fetch the key roles are checked again with the canonical
        # fingerprints, which are what the release signs with.
        from tools.release.doctor import Check

        seen = []

        def canonical(probes, *, product_fingerprint, checksum_fingerprint):
            seen.append((product_fingerprint, checksum_fingerprint))
            return [Check("signing key (checksum)", "fail", f"secret key {checksum_fingerprint} is not in x",
                          "import the checksum private key into x")]
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(cli, "release_doctor", return_value=[]), \
                patch.object(cli, "build_context", return_value=self.context), \
                patch.object(cli, "check_signing_keys", canonical), \
                patch.object(cli, "build_orchestration_policy", side_effect=AssertionError("ran past the gate")), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = cli.main(["--repo-root", str(self.root), "run", "--authority", "issue:1301"])
        self.assertEqual(code, 2)
        policy = self.context.policy
        self.assertEqual(seen, [(policy.product_fingerprint, policy.checksum_fingerprint)])
        self.assertIn("[fail] signing key (checksum)", output.getvalue())
        self.assertIn("canonical policy names a signing key", errors.getvalue())
        self.assertEqual(self.request_ids(), [])

    def test_doctor_subcommand_prints_every_check_and_its_exit_names_the_outcome(self):
        from tools.release.doctor import Check

        passing = [Check("emsdk", "ok", "fine"), Check("m1 runner", "skip", "macOS only")]
        failing = passing + [Check("host load", "fail", "load 9.0 exceeds 8 cpus", "stop heavy work")]
        for checks, expected in ((passing, 0), (failing, 2)):
            with self.subTest(expected=expected):
                output = io.StringIO()
                with patch.object(cli, "release_doctor", return_value=checks), \
                        contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    self.assertEqual(cli.main(["--repo-root", str(self.root), "doctor"]), expected)
                self.assertIn("[ok] emsdk: fine", output.getvalue())
                self.assertIn("[skip] m1 runner: macOS only", output.getvalue())
                if expected:
                    self.assertIn("remedy: stop heavy work", output.getvalue())

    def test_release_doctor_reports_its_own_unreadable_inputs_as_checks(self):
        # No policy in this checkout: a failed check with a remedy, not a traceback.
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(cli.main(["--repo-root", str(self.root), "doctor"]), 2)
        self.assertIn("[fail] release policy: tools/release/policy.json is unreadable here", output.getvalue())
        self.assertIn("remedy: run from the main checkout", output.getvalue())
        self.assertNotIn("release verification error", output.getvalue())

    def test_release_doctor_binds_the_policy_keys_and_the_journal_root(self):
        policy_dir = self.root / "tools/release"
        shutil.copy(ROOT / "tools/release/policy.json", policy_dir / "policy.json")
        seen = {}

        def fake_run_doctor(root, **fields):
            seen.update(fields, root=root)
            return []
        with patch.object(cli, "run_doctor", fake_run_doctor), \
                patch.object(cli, "GitRepository", return_value=self.context.git):
            self.assertEqual(cli.release_doctor(self.root), [])
        policy = self.context.policy
        self.assertEqual(seen["product_fingerprint"], policy.product_fingerprint)
        self.assertEqual(seen["checksum_fingerprint"], policy.checksum_fingerprint)
        self.assertEqual(seen["journal_root"], self.journal())
        self.assertEqual(seen["root"], self.root)

    def test_resume_of_an_unknown_request_fails_closed(self):
        output = io.StringIO()
        self.assertEqual(self.run_cli(["resume", "release-" + "0" * 16], capture=output), 2)
        self.assertIn("request is missing", output.getvalue())

    def test_prepare_and_a_resume_at_the_prepared_step_require_the_runner_paused(self):
        from tools.release.orchestration import STEPS
        seen = []

        def doctor(root, *, require_paused_runner=False):
            seen.append(require_paused_runner)
            return []

        def main(arguments):
            with patch.object(cli, "build_context", return_value=self.context), \
                    patch.object(cli, "release_carriers", return_value=tuple(self.carriers.values())), \
                    patch.object(cli, "release_recheck", return_value=None), \
                    patch.object(cli, "release_doctor", doctor), \
                    patch.object(cli, "confirm_canonical_signing_keys", return_value=[]), \
                    patch.object(cli, "compose_candidate", return_value=None), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return cli.main(["--repo-root", str(self.root), *arguments])
        # A run, and a resume whose next step is before `prepared`, need the runner up.
        self.carriers["publication"].fail_after_write = True
        self.assertEqual(main(["run", "--authority", "issue:1301"]), 2)
        (request_id,) = self.request_ids()
        self.assertEqual(main(["resume", request_id]), 0)   # next step: publication
        with patch.object(cli, "_next_step", return_value="prepared"):
            self.assertEqual(main(["resume", request_id]), 0)
        with patch.object(cli, "_next_step", return_value="verification"):
            self.assertEqual(main(["resume", request_id]), 0)
        with patch.object(cli, "release_doctor", doctor), \
                patch.object(cli, "build_context", side_effect=CommandError("stop")), \
                contextlib.redirect_stderr(io.StringIO()):
            cli.main(["--repo-root", str(self.root), "prepare", "lmdj-v1.0.61.0"])
        self.assertEqual(seen, [False, False, True, False, True])
        # `_next_step` reads the journal read-only: the first unverified step.
        self.assertEqual(cli._next_step(self.root, self.context.git, request_id), None)
        self.assertEqual(cli._next_step(self.root, self.context.git, "release-" + "0" * 16), None)

    def test_an_unknown_resume_is_reported_before_the_host_doctor(self):
        # The journal's finding is not hidden behind a failing host check.
        from tools.release.doctor import Check

        self.assertEqual(self.run_cli(["run", "--authority", "issue:1301"]), 0)
        policy_dir = self.root / "tools/release"
        shutil.copy(ROOT / "tools/release/policy.json", policy_dir / "policy.json")
        failed = [Check("host load", "fail", "load 9.0 exceeds 8 cpus", "stop heavy work")]
        output = io.StringIO()
        with patch.object(cli, "release_doctor", return_value=failed), \
                patch.object(cli, "GitRepository", return_value=self.context.git), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = cli.main(["--repo-root", str(self.root), "resume", "release-" + "0" * 16])
        self.assertEqual(code, 2)
        self.assertIn("request is missing", output.getvalue())
        self.assertNotIn("host load", output.getvalue())
        # The finding is the request even while another driver holds the lock.
        output = io.StringIO()
        with RequestJournal(self.journal()), \
                patch.object(cli, "release_doctor", return_value=failed), \
                patch.object(cli, "GitRepository", return_value=self.context.git), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = cli.main(["--repo-root", str(self.root), "resume", "release-" + "0" * 16])
        self.assertEqual(code, 2)
        self.assertIn("request is missing", output.getvalue())
        self.assertNotIn("another writer", output.getvalue())


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

    def test_the_entry_composes_the_verified_recheck_for_the_request(self):
        from tools.release.verified_recheck import VerifiedRecheck

        request = self.request()
        recheck = cli.release_recheck(self.context, self.policy, request)
        self.assertIs(type(recheck), VerifiedRecheck)
        self.assertEqual(recheck.operations,
                         self.gitdir / "lmdj-release-requests" / "operations" / request["id"])
        self.assertEqual((recheck.root, recheck.repository), (self.root, "endaye/lmdj"))
        self.assertIs(recheck.github, self.context.github)

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
                patch.object(cli, "release_doctor", return_value=[]), \
                patch.object(cli, "confirm_canonical_signing_keys", return_value=[]), \
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


class CompositionGitHub(VariableStore):
    def get_authenticated_actor(self):
        return ACTOR

    def get_dispatch_evidence(self, path, *, raw=False):
        assert path.startswith("/repos/endaye/lmdj/"), path
        workflow = path.rsplit("/", 1)[-1]
        return {"id": {"publish-release.yml": 501,
                       "deploy-web-runtime-host.yml": 502,
                       "deploy-creator-web.yml": 503}[workflow],
                "path": ".github/workflows/" + workflow}

    def get_batch_evidence(self, path, *, raw=False):
        raise AssertionError("assembly never reads batch evidence")

    def get_release_by_tag(self, repository, tag):
        raise AssertionError("assembly never reads releases")

    def get_pull_request(self, repository, number):
        raise AssertionError("assembly never reads pull requests")


if __name__ == "__main__":
    unittest.main()
