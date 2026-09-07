#!/usr/bin/env python3
"""Contract tests for the explicit release intent hydration boundary.

The production change these tests fail on is a hydration step that stops being
idempotent, an audit that fetches on miss instead of naming its remedy, or a
workflow that reintroduces its own inline hydrate-by-SHA copy.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.release.commands import CommandError, CommandResult  # noqa: E402
import tools.release.cli as cli  # noqa: E402
from tools.release.hydrate import (  # noqa: E402
    HydrateError,
    LEDGER_PATH,
    format_hydration,
    hydrate_release_intent_targets,
    read_intent_target_revisions,
)

AUDIT_SOURCE = ROOT / "tools/release/audit.py"
HYDRATE_COMMAND = "scripts/release.sh hydrate"
RELEASE_WORKFLOWS = (
    ".github/workflows/ci.yml",
    ".github/workflows/publish-release.yml",
    ".github/workflows/release-audit.yml",
)
PRESENT = "a" * 40
MISSING = "b" * 40
EXCEPTION_TARGET = "c" * 40


def directives(source: str) -> str:
    """Drop YAML comment lines so an absence assertion cannot read its own prose."""
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )


def workflow_jobs(source: str) -> dict[str, str]:
    """Split one workflow into its top-level job bodies."""
    body = source[source.index("\njobs:\n"):]
    names = [
        match for match in re.finditer(r"(?m)^  (?P<name>[a-z0-9][a-z0-9_-]*):$", body)
    ]
    jobs: dict[str, str] = {}
    for index, match in enumerate(names):
        end = names[index + 1].start() if index + 1 < len(names) else len(body)
        jobs[match.group("name")] = body[match.start():end]
    return jobs


class FakeRunner:
    """Answer `cat-file -e` from a mutable object store and record every fetch."""

    def __init__(self, present: set[str], *, fetch_hydrates: bool = True) -> None:
        self.present = set(present)
        self.fetch_hydrates = fetch_hydrates
        self.fetches: list[tuple[str, ...]] = []
        self.probes: list[str] = []
        self.fetch_error: CommandError | None = None

    def run(self, arguments, *, cwd=None, environment=None) -> CommandResult:
        vector = tuple(str(argument) for argument in arguments)
        if vector[:3] == ("git", "cat-file", "-e"):
            revision = vector[3].removesuffix("^{commit}")
            self.probes.append(revision)
            if revision not in self.present:
                raise CommandError("release command failed: git (exit 1)")
            return CommandResult(vector, 0, "", "")
        if vector[:2] == ("git", "fetch"):
            self.fetches.append(vector)
            if self.fetch_error is not None:
                raise self.fetch_error
            if self.fetch_hydrates:
                self.present.update(vector[4:])
            return CommandResult(vector, 0, "", "")
        raise AssertionError(f"unexpected command: {vector}")


class LedgerFixture:
    """A throwaway repository root holding exactly one intent ledger."""

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.addCleanup(self._directory.cleanup)
        self.write(
            entries=[{"target_revision": PRESENT}, {"target_revision": MISSING}],
            exceptions=[{"target_revision": EXCEPTION_TARGET}],
        )

    def write(self, *, entries, exceptions, schema="lmdj.release-intents.v1") -> None:
        path = self.root / LEDGER_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema": schema, "entries": entries, "historical_exceptions": exceptions,
        }), encoding="utf-8")


class ReleaseHydrateLedgerTest(LedgerFixture, unittest.TestCase):
    def test_every_entry_and_historical_exception_target_is_collected_in_order(self) -> None:
        self.assertEqual(
            read_intent_target_revisions(self.root),
            (PRESENT, MISSING, EXCEPTION_TARGET),
        )

    def test_repeated_target_is_collected_once(self) -> None:
        self.write(
            entries=[{"target_revision": PRESENT}, {"target_revision": PRESENT}],
            exceptions=[{"target_revision": PRESENT}],
        )
        self.assertEqual(read_intent_target_revisions(self.root), (PRESENT,))

    def test_absent_unreadable_or_malformed_ledger_fails_closed_naming_the_path(self) -> None:
        cases = {
            "missing file": lambda: (self.root / LEDGER_PATH).unlink(),
            "not json": lambda: (self.root / LEDGER_PATH).write_text("{", encoding="utf-8"),
            "not an object": lambda: (self.root / LEDGER_PATH).write_text("[]", encoding="utf-8"),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                self.setUp()
                mutate()
                with self.assertRaises(HydrateError) as raised:
                    read_intent_target_revisions(self.root)
                self.assertIn(LEDGER_PATH, str(raised.exception))

    def test_missing_section_or_non_sha_target_fails_closed(self) -> None:
        self.write(entries=[{"target_revision": PRESENT}], exceptions="none")
        with self.assertRaises(HydrateError) as raised:
            read_intent_target_revisions(self.root)
        self.assertIn("historical_exceptions", str(raised.exception))
        for target in ("HEAD", PRESENT.upper(), PRESENT[:39], 17, None):
            with self.subTest(target=target):
                self.write(entries=[{"target_revision": target}], exceptions=[])
                with self.assertRaises(HydrateError) as raised:
                    read_intent_target_revisions(self.root)
                self.assertIn("target_revision", str(raised.exception))

    def test_empty_ledger_fails_closed_rather_than_reporting_a_silent_success(self) -> None:
        self.write(entries=[], exceptions=[])
        with self.assertRaises(HydrateError):
            read_intent_target_revisions(self.root)


class ReleaseHydrateOperationTest(LedgerFixture, unittest.TestCase):
    def test_present_targets_are_never_fetched(self) -> None:
        runner = FakeRunner({PRESENT, MISSING, EXCEPTION_TARGET})
        result = hydrate_release_intent_targets(self.root, runner=runner)
        self.assertEqual(result.present, (PRESENT, MISSING, EXCEPTION_TARGET))
        self.assertEqual(result.hydrated, ())
        self.assertEqual(runner.fetches, [])
        self.assertIn("already present", format_hydration(result))

    def test_only_the_missing_targets_are_fetched_by_sha_in_one_command(self) -> None:
        runner = FakeRunner({PRESENT})
        result = hydrate_release_intent_targets(self.root, runner=runner)
        self.assertEqual(result.present, (PRESENT,))
        self.assertEqual(result.hydrated, (MISSING, EXCEPTION_TARGET))
        self.assertEqual(runner.fetches, [
            ("git", "fetch", "--no-tags", "origin", MISSING, EXCEPTION_TARGET),
        ])
        report = format_hydration(result)
        self.assertIn(MISSING, report)
        self.assertIn(EXCEPTION_TARGET, report)

    def test_hydration_is_idempotent_and_the_second_run_fetches_nothing(self) -> None:
        runner = FakeRunner({PRESENT})
        first = hydrate_release_intent_targets(self.root, runner=runner)
        second = hydrate_release_intent_targets(self.root, runner=runner)
        self.assertEqual(first.hydrated, (MISSING, EXCEPTION_TARGET))
        self.assertEqual(second.hydrated, ())
        self.assertEqual(len(runner.fetches), 1)
        self.assertEqual(
            second.present, (PRESENT, MISSING, EXCEPTION_TARGET),
        )

    def test_failed_fetch_names_the_violated_invariant_and_its_remedy(self) -> None:
        runner = FakeRunner({PRESENT})
        runner.fetch_error = CommandError("release command failed", detail="denied")
        with self.assertRaises(HydrateError) as raised:
            hydrate_release_intent_targets(self.root, runner=runner)
        message = str(raised.exception)
        self.assertIn("not reachable from origin", message)
        self.assertIn("no release audit can verify", message)
        self.assertIn("remedy:", message)
        self.assertIn(HYDRATE_COMMAND, message)
        self.assertEqual(raised.exception.detail, "denied")

    def test_a_fetch_that_hydrates_nothing_fails_closed_with_why_and_remedy(self) -> None:
        runner = FakeRunner({PRESENT}, fetch_hydrates=False)
        with self.assertRaises(HydrateError) as raised:
            hydrate_release_intent_targets(self.root, runner=runner)
        message = str(raised.exception)
        self.assertIn("still absent from the local object store", message)
        self.assertIn("unverifiable", message)
        self.assertIn("remedy:", message)
        self.assertIn(HYDRATE_COMMAND, message)


class ReleaseHydrateInterfaceTest(unittest.TestCase):
    def test_the_stable_interface_exposes_hydrate_as_its_own_subcommand(self) -> None:
        options = cli.parse_arguments(["--repo-root", str(ROOT), "hydrate"])
        self.assertEqual(options.command, "hydrate")
        with self.assertRaises(SystemExit):
            cli.parse_arguments(["--repo-root", str(ROOT), "hydrate", "--remote"])

    def test_hydrate_fails_with_the_shared_release_verification_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(cli.main(["--repo-root", directory, "hydrate"]), 2)

    def test_hydrate_is_reachable_through_the_documented_shell_entry_point(self) -> None:
        completed = subprocess.run(
            ["bash", str(ROOT / "scripts/release.sh"), "hydrate", "--help"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("hydrate", completed.stdout)


class ReleaseAuditRemedyTest(unittest.TestCase):
    """The audit reports an absent intent target; only `hydrate` repairs it."""

    def audit_directives(self) -> str:
        source = AUDIT_SOURCE.read_text(encoding="utf-8")
        joined = re.sub(r'"\s*\n\s*"', "", source)
        return "\n".join(
            line for line in joined.splitlines()
            if not line.lstrip().startswith("#")
        )

    def test_absent_target_message_names_the_invariant_and_the_hydrate_remedy(self) -> None:
        message = re.search(
            r"is absent from the local object store, (?P<why>[^\"]*?); "
            r"remedy: run (?P<remedy>scripts/release\.sh [a-z-]+)",
            self.audit_directives(),
        )
        self.assertIsNotNone(
            message,
            "why: a fail-closed check must name the violated invariant and its "
            "remedy (docs/governance/pitfall-ledger.md), and an absent intent "
            "target names neither on its own; remedy: keep the message in "
            f"{AUDIT_SOURCE.relative_to(ROOT)} naming both the binding it cannot "
            f"verify and `{HYDRATE_COMMAND}`",
        )
        assert message is not None
        self.assertIn("cannot bind the intent", message.group("why"))
        self.assertIn("must not fetch it itself", message.group("why"))
        self.assertEqual(message.group("remedy"), HYDRATE_COMMAND)
        self.assertEqual(
            cli.parse_arguments([
                "--repo-root", str(ROOT), message.group("remedy").split()[-1],
            ]).command,
            "hydrate",
            "why: a remedy naming a subcommand the stable interface does not "
            "accept is not actionable; remedy: keep the audit's remedy string and "
            "the release.sh subparser name identical",
        )

    def test_the_audit_reports_an_absent_intent_target_instead_of_fetching_it(self) -> None:
        directives = self.audit_directives()
        for forbidden in ("git fetch", '"fetch"', "hydrate_release_intent_targets"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(
                    forbidden, directives,
                    "why: fetch-on-miss would repair the exact deficiency the audit "
                    "exists to report, so a fresh clone would self-heal silently and "
                    "the finding would never be seen; the audit's only remote read is "
                    "its bounded authority refspec; remedy: leave the fetch in "
                    f"tools/release/hydrate.py and run `{HYDRATE_COMMAND}` before the "
                    "audit",
                )


class ReleaseHydrateWorkflowTest(unittest.TestCase):
    def source(self, relative: str) -> str:
        path = ROOT / relative
        self.assertTrue(path.is_file(), f"workflow is missing: {relative}")
        return path.read_text(encoding="utf-8")

    def test_every_release_consuming_job_hydrates_through_the_subcommand_first(self) -> None:
        checked = 0
        for relative in RELEASE_WORKFLOWS:
            for name, job in workflow_jobs(self.source(relative)).items():
                body = directives(job)
                if "scripts/release.sh" not in body:
                    continue
                checked += 1
                with self.subTest(workflow=relative, job=name):
                    self.assertIn(
                        HYDRATE_COMMAND, body,
                        "why: a fresh clone lacks the pre-squash intent target objects, "
                        "so any release.sh verification in this job reports the intents "
                        f"unverifiable; remedy: add a `{HYDRATE_COMMAND}` step to job "
                        f"{name} of {relative} before its first release.sh step",
                    )
                    self.assertEqual(
                        body.index(HYDRATE_COMMAND),
                        body.index("scripts/release.sh"),
                        "why: hydration must precede every verifying release.sh call in "
                        f"the same job or the audit still fails on a fresh clone; "
                        f"remedy: move the `{HYDRATE_COMMAND}` step to the front of job "
                        f"{name} of {relative}",
                    )
        self.assertEqual(checked, 4, "expected four release-consuming jobs")

    def test_no_workflow_carries_its_own_inline_intent_hydrate_copy(self) -> None:
        for relative in RELEASE_WORKFLOWS:
            body = directives(self.source(relative))
            for forbidden in (LEDGER_PATH, "git fetch --no-tags origin", "cat-file -e"):
                with self.subTest(workflow=relative, forbidden=forbidden):
                    self.assertNotIn(
                        forbidden, body,
                        "why: a per-workflow hydrate copy is the duplication issue #332 "
                        "removed, and each copy drifts from the tool it works around; "
                        f"remedy: call `{HYDRATE_COMMAND}` in {relative} instead of "
                        "reading the intent ledger or fetching by SHA inline",
                    )


if __name__ == "__main__":
    unittest.main()
