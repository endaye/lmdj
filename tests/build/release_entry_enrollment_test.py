#!/usr/bin/env python3
"""Enrolled step carriers recover their identity lazily and delegate."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.carriers import (  # noqa: E402
    RecoveredStep,
    enroll_changelog_site,
    read_candidate_identity,
    release_identity,
    spec_identity,
)
from tools.release.orchestration import JournalError  # noqa: E402
from tools.release.orchestration_driver import Observation  # noqa: E402

DIGEST = "a" * 64
TARGET = "b" * 40
CUT_MERGE = "c" * 40
SNAPSHOT = "d" * 64
BUILD = "1.0.58.0"


def request(**changes):
    document = {"id": "release-" + "0" * 16, "repository": "endaye/lmdj",
                "actor_id": 34, "authority_ref": "issue:1301",
                "policy_digest": "e" * 64, "control_revision": "f" * 40,
                "base_revision": "f" * 40, "mode": "tag",
                "requested_tag": "lmdj-v" + BUILD}
    document.update(changes)
    return document


def state(**changes):
    document = {"request": request(), "request_digest": DIGEST,
                "schema": "lmdj.release-request.v1", "transitions": []}
    document.update(changes)
    return document


def candidate_document(**changes):
    document = {"schema": "lmdj.candidate-transition.v1",
                "scope": {"cut_spec": {"request_sha256": changes.pop("digest", DIGEST),
                                       "product_build": BUILD,
                                       "snapshot_sha256": SNAPSHOT}},
                "cut_merge": {"merge": {"merge_sha": CUT_MERGE}}}
    document.update(changes)
    return document


class Intent:
    """The ledger row that authorizes a tag."""

    def __init__(self, *, target_revision=TARGET, channel="dev",
                 disposition="published"):
        self.target_revision, self.current_channel = target_revision, channel
        self.disposition = disposition


class Ledger:
    def __init__(self, rows=None):
        self.rows = {"lmdj-v" + BUILD: Intent()} if rows is None else rows

    def intent_for_tag(self, tag):
        return self.rows.get(tag)


class Carrier:
    """A concrete step carrier the wrapper delegates to."""

    def __init__(self, *, drives=False):
        self.seen = []

    def observe(self, state, operation):
        self.seen.append(("observe", state["request_digest"]))
        return Observation("verified", {"sha256": DIGEST, "reference": "fixture"})

    def execute(self, state, operation):
        self.seen.append(("execute", state["request_digest"]))


class Drives(Carrier):
    def advance(self, state, operation, *, before_write):
        before_write()
        self.seen.append(("advance", state["request_digest"]))


class RecoveredStepTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def write_candidate(self, **changes):
        (self.root / "candidate-transition.json").write_text(
            json.dumps(candidate_document(**changes)))

    def step(self, carrier, *, drives=False):
        return RecoveredStep("changelog_site", lambda _s, _o: carrier,
                             drives=drives)

    def operation(self):
        return {"step": "changelog_site", "operation_id": DIGEST,
                "status": "intent", "evidence": None}

    def test_a_step_without_a_derivable_identity_is_pending(self):
        step = RecoveredStep("changelog_site", lambda _s, _o: None)
        observed = step.observe(state(), self.operation())
        self.assertEqual(observed.status, "pending")
        self.assertIsNone(observed.evidence)
        self.assertFalse(hasattr(step, "advance"))
        # Executing a step whose identity is gone would report it done with no
        # write; that is an anomaly, not a wait.
        with self.assertRaises(JournalError):
            step.execute(state(), self.operation())

    def test_a_recoverable_step_delegates_observe_and_execute(self):
        carrier = Carrier()
        step = self.step(carrier)
        self.assertEqual(step.observe(state(), self.operation()).status, "verified")
        step.execute(state(), self.operation())
        self.assertEqual(carrier.seen, [("observe", DIGEST), ("execute", DIGEST)])

    def test_only_a_driving_step_exposes_advance(self):
        # The driver treats any carrier with a callable `advance` as
        # self-driving, so a read-only step must not look like one.
        self.assertFalse(callable(getattr(self.step(Carrier()), "advance", None)))
        driving = self.step(Drives(), drives=True)
        self.assertTrue(callable(getattr(driving, "advance", None)))
        carrier = Drives()
        driving = self.step(carrier, drives=True)
        driving.advance(state(), self.operation(), before_write=lambda: None)
        self.assertEqual(carrier.seen, [("advance", DIGEST)])

    def test_a_driving_step_writes_nothing_while_it_is_pending(self):
        written = []
        step = RecoveredStep("tag", lambda _s, _o: None, drives=True)
        self.assertEqual(step.observe(state(), {"step": "tag", "operation_id": DIGEST}).status,
                         "pending")
        step.advance(state(), {"step": "tag", "operation_id": DIGEST},
                     before_write=lambda: written.append(True))
        self.assertEqual(written, [])
        # Asked to act without that observation, it must not pass silently.
        with self.assertRaises(JournalError):
            step.advance(state(), {"step": "tag", "operation_id": "e" * 64},
                         before_write=lambda: written.append(True))
        self.assertEqual(written, [])

    def test_an_unknown_step_or_recovery_is_refused(self):
        for arguments in (("not-a-step", lambda _s, _o: None),
                          ("changelog_site", None)):
            with self.assertRaises(JournalError):
                RecoveredStep(*arguments)

    def test_a_carrier_cannot_observe_another_step(self):
        step = self.step(Carrier())
        with self.assertRaises(JournalError):
            step.observe(state(), {"step": "final", "operation_id": DIGEST})


class IdentityRecoveryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def write_candidate(self, **changes):
        (self.root / "candidate-transition.json").write_text(
            json.dumps(candidate_document(**changes)))

    def identity(self, document=None, repository_id=12, ledger=None):
        return release_identity(document or state(), candidate_root=self.root,
                                repository_id=repository_id,
                                ledger=Ledger() if ledger is None else ledger)

    def test_a_tag_request_takes_its_frozen_identity_from_the_ledger(self):
        identity = self.identity()
        self.assertEqual(identity["tag"], "lmdj-v" + BUILD)
        self.assertEqual(identity["product_build"], BUILD)
        # Nothing has been cut here, so the intent row is authoritative.
        self.assertEqual(identity["target_revision"], TARGET)
        self.assertEqual(identity["channel"], "dev")

    def test_a_tag_the_ledger_does_not_authorize_fails_closed(self):
        for ledger in (Ledger(rows={}),
                       Ledger(rows={"lmdj-v1.0.59.0": Intent()})):
            with self.assertRaises(JournalError):
                self.identity(ledger=ledger)

    def test_a_new_request_learns_the_allocated_build(self):
        self.write_candidate()
        document = state(request=request(mode="new", requested_tag=None))
        identity = self.identity(document)
        self.assertEqual(identity["tag"], "lmdj-v" + BUILD)
        self.assertEqual(identity["target_revision"], CUT_MERGE)
        self.assertEqual(identity["snapshot_sha256"], SNAPSHOT)

    def test_a_new_request_waits_until_the_cut_is_merged(self):
        self.write_candidate(cut_merge=None)
        document = state(request=request(mode="new", requested_tag=None))
        self.assertIsNone(self.identity(document))

    def test_a_candidate_state_without_a_frozen_snapshot_fails_closed(self):
        for snapshot in (None, "not-a-digest", 0):
            document = candidate_document()
            document["scope"]["cut_spec"]["snapshot_sha256"] = snapshot
            (self.root / "candidate-transition.json").write_text(json.dumps(document))
            with self.assertRaises(JournalError):
                self.identity(state(request=request(mode="new", requested_tag=None)))

    def test_a_candidate_state_from_another_request_fails_closed(self):
        self.write_candidate(digest="9" * 64)
        document = state(request=request(mode="new", requested_tag=None))
        with self.assertRaises(JournalError):
            self.identity(document)

    def test_an_unreadable_candidate_state_fails_closed(self):
        (self.root / "candidate-transition.json").write_text("{not json")
        document = state(request=request(mode="new", requested_tag=None))
        with self.assertRaises(JournalError):
            self.identity(document)

    def test_a_request_without_a_valid_digest_is_refused(self):
        with self.assertRaises(JournalError):
            self.identity(state(request_digest="short"))

    def test_an_unresolved_numeric_repository_identity_is_refused(self):
        for value in (None, 0, "12"):
            with self.assertRaises(JournalError):
                self.identity(repository_id=value)

    def test_the_candidate_and_the_request_must_agree_on_the_build(self):
        self.write_candidate()
        document = state(request=request(requested_tag="lmdj-v1.0.59.0"))
        with self.assertRaises(JournalError):
            self.identity(document)

    def test_spec_identity_carries_the_steps_own_operation_id(self):
        from tools.release.final_steps import site_operation_id

        fields = spec_identity(state(), candidate_root=self.root,
                               repository_id=12, ledger=Ledger(),
                               operation_id=site_operation_id)
        self.assertEqual(fields["operation_id"], site_operation_id(DIGEST))
        self.assertEqual(fields["tag"], "lmdj-v" + BUILD)
        # A step's spec is closed, so the shared fields must be exactly the
        # ones every validator requires and nothing more.
        from tools.release.final_steps import validate_site_spec

        validate_site_spec(dict(fields, site_base_url="https://docs.example.invalid"))

    def test_spec_identity_waits_until_the_target_is_frozen(self):
        ledger = Ledger(rows={"lmdj-v" + BUILD: Intent(target_revision=None)})
        self.assertIsNone(spec_identity(
            state(), candidate_root=self.root, repository_id=12, ledger=ledger,
            operation_id=lambda _digest: DIGEST))

    def test_read_candidate_identity_reports_absence_before_the_step_ran(self):
        self.assertIsNone(read_candidate_identity(self.root, DIGEST))


class ChangelogSiteEnrollmentTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.fetched = []

    def fetch(self, url):
        self.fetched.append(url)
        return 200, f"<html>Product Build {BUILD}</html>"

    def step(self, fetch=None):
        return enroll_changelog_site(
            candidate_root=self.root, repository_id=12, ledger=Ledger(),
            fetch=fetch or self.fetch,
            site_base_url="https://docs.example.invalid")

    def operation(self):
        return {"step": "changelog_site", "operation_id": DIGEST,
                "status": "intent", "evidence": None}

    def test_the_step_is_pending_until_the_build_is_allocated(self):
        # A new-mode request whose candidate step has not run yet: there is no
        # Build to verify, so the step waits rather than claiming absence.
        step = self.step()
        new_mode = state(request=request(mode="new", requested_tag=None))
        self.assertEqual(step.observe(new_mode, self.operation()).status, "pending")
        self.assertEqual(self.fetched, [])

    def test_an_unauthorized_tag_fails_closed_rather_than_waiting(self):
        step = enroll_changelog_site(
            candidate_root=self.root, repository_id=12, ledger=Ledger(rows={}),
            fetch=self.fetch, site_base_url="https://docs.example.invalid")
        with self.assertRaises(JournalError):
            step.observe(state(), self.operation())
        self.assertEqual(self.fetched, [])

    def test_the_step_reads_the_deployed_build_and_binds_its_evidence(self):
        step = self.step()
        observed = step.observe(state(), self.operation())
        self.assertEqual(observed.status, "verified")
        self.assertEqual(set(self.fetched),
                         {"https://docs.example.invalid/versions/" + BUILD + "/",
                          "https://docs.example.invalid/releases/" + BUILD})
        self.assertTrue(observed.evidence["reference"].startswith("site:"))

    def test_a_missing_page_is_absent_and_a_wrong_page_is_a_conflict(self):
        step = self.step(fetch=lambda url: (404, "") if "versions" in url else (200, f"<html>Product Build {BUILD}</html>"))
        self.assertEqual(step.observe(state(), self.operation()).status, "conflict")
        foreign = self.step(fetch=lambda url: (200, "<html>Product Build 1.0.59.0</html>"))
        self.assertEqual(foreign.observe(state(), self.operation()).status, "conflict")


if __name__ == "__main__":
    unittest.main()
