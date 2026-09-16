#!/usr/bin/env python3
"""Enrolled step carriers recover their identity lazily and delegate."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.carriers import (  # noqa: E402
    RecoveredStep,
    enroll_changelog,
    enroll_changelog_site,
    enroll_draft,
    enroll_final,
    enroll_intent,
    enroll_promotion,
    enrolled_candidate_timestamp,
    read_candidate_identity,
    read_prepared_plan,
    read_verified_batch,
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

    def test_a_malformed_ledger_target_revision_fails_closed(self):
        for revision in (None, "not-a-revision", 1234):
            ledger = Ledger(rows={"lmdj-v" + BUILD: Intent(target_revision=revision)})
            with self.assertRaises(JournalError):
                self.identity(ledger=ledger)

    def test_a_tag_the_ledger_does_not_authorize_fails_closed(self):
        for ledger in (Ledger(rows={}),
                       Ledger(rows={"lmdj-v1.0.59.0": Intent()})):
            with self.assertRaises(JournalError):
                self.identity(ledger=ledger)

    def test_a_new_request_learns_the_allocated_build(self):
        # The allocation proves the Build and the frozen snapshot; the target
        # revision is the batch-certified witness merge the intent row binds
        # (TARGET here), never the cut squash (CUT_MERGE) the transition names
        # separately.
        self.write_candidate(witness_merge={"merge": {"merge_sha": TARGET}})
        document = state(request=request(mode="new", requested_tag=None))
        identity = self.identity(document)
        self.assertEqual(identity["tag"], "lmdj-v" + BUILD)
        self.assertEqual(identity["target_revision"], TARGET)
        self.assertEqual(identity["snapshot_sha256"], SNAPSHOT)

    def test_a_new_request_waits_for_the_intent_row(self):
        # The intent row is this run's own intent-step output; before it lands
        # there is no authoritative target revision to bind.
        self.write_candidate(witness_merge={"merge": {"merge_sha": TARGET}})
        document = state(request=request(mode="new", requested_tag=None))
        self.assertIsNone(self.identity(document, ledger=Ledger(rows={})))

    def test_a_row_disagreeing_with_the_witness_merge_fails_closed(self):
        self.write_candidate(witness_merge={"merge": {"merge_sha": "9" * 40}})
        document = state(request=request(mode="new", requested_tag=None))
        with self.assertRaises(JournalError):
            self.identity(document)
        # The row exists, so the intent step completed; a candidate state that
        # never recorded the witness merge is drift, not an early state.
        self.write_candidate()
        with self.assertRaises(JournalError):
            self.identity(document)

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
                               operation_id=site_operation_id,
                               fields=("tag", "product_build", "target_revision",
                                       "repository_id", "actor_id",
                                       "request_sha256"))
        self.assertEqual(fields["operation_id"], site_operation_id(DIGEST))
        self.assertEqual(fields["tag"], "lmdj-v" + BUILD)
        # A step's spec is closed, so the shared fields must be exactly the
        # ones every validator requires and nothing more.
        from tools.release.final_steps import validate_site_spec

        validate_site_spec(dict(fields, site_base_url="https://docs.example.invalid"))

    def test_spec_identity_reports_a_missing_base_field_instead_of_crashing(self):
        document = state()
        del document["request"]["actor_id"]
        with self.assertRaises(JournalError):
            spec_identity(document, candidate_root=self.root, repository_id=12,
                          ledger=Ledger(),
                          operation_id=lambda _digest: DIGEST,
                          fields=("tag", "target_revision", "repository_id",
                                  "actor_id", "request_sha256"))

    def test_spec_identity_waits_until_the_allocation_is_frozen(self):
        # The candidate step has allocated the Build but its cut is not merged,
        # so no step spec can bind a target revision yet.
        (self.root / "candidate-transition.json").write_text(
            json.dumps(candidate_document(cut_merge=None)))
        self.assertIsNone(spec_identity(
            state(request=request(mode="new", requested_tag=None)),
            candidate_root=self.root, repository_id=12, ledger=Ledger(),
            operation_id=lambda _digest: DIGEST,
            fields=("tag", "target_revision", "repository_id", "actor_id",
                    "request_sha256")))

    def test_read_candidate_identity_reports_absence_before_the_step_ran(self):
        self.assertIsNone(read_candidate_identity(self.root, DIGEST))

    def test_the_witness_revision_waits_for_the_witness_merge(self):
        # The witness merge is the batch-certified revision the intent step
        # binds; it exists only after the witness PR is verified merged.
        self.write_candidate()
        self.assertIsNone(read_candidate_identity(self.root, DIGEST)["witness_revision"])
        self.write_candidate(witness_merge={"merge": {"merge_sha": "9" * 40}})
        self.assertEqual(read_candidate_identity(self.root, DIGEST)["witness_revision"],
                         "9" * 40)
        self.write_candidate(witness_merge={"merge": {"merge_sha": "short"}})
        with self.assertRaises(JournalError):
            read_candidate_identity(self.root, DIGEST)


WITNESS = "7" * 40
ORIGIN_RUN = 3401234567


def verified_state(reference=f"batch-result:{ORIGIN_RUN}:{WITNESS}",
                   status="verified"):
    return state(transitions=[{
        "step": "verification", "operation_id": DIGEST, "status": status,
        "evidence": {"sha256": DIGEST, "reference": reference}}])


def batch_document(origin_run=ORIGIN_RUN):
    return {"request": {"origin_run": {"run_id": origin_run, "attempt": 1}},
            "schema": "lmdj.batch-reference.v1"}


class VerifiedBatchRecoveryTest(unittest.TestCase):
    def read(self, document=None, state_document=None, reader=None):
        return read_verified_batch(
            state_document or verified_state(),
            batch_reference_for=reader or (
                lambda _witness: document if document is not None else batch_document()))

    def test_no_verified_verification_step_means_not_yet(self):
        self.assertIsNone(read_verified_batch(state(), batch_reference_for=lambda _w: None))
        self.assertIsNone(read_verified_batch(
            verified_state(status="intent"), batch_reference_for=lambda _w: None))

    def test_the_reference_and_its_origin_run_are_recovered(self):
        recovered = self.read()
        self.assertEqual(recovered["batch_run_id"], ORIGIN_RUN)
        self.assertEqual(recovered["witness_revision"], WITNESS)
        self.assertEqual(recovered["batch_reference"]["request"]["origin_run"]["run_id"],
                         ORIGIN_RUN)

    def test_an_encoded_journal_reference_is_decoded(self):
        import scripts.ci.batch_runtime as runtime

        encoded = runtime.encode_reference(batch_document())
        recovered = read_verified_batch(
            verified_state(),
            batch_reference_for=lambda _witness: (encoded.decode()
                                                  if isinstance(encoded, bytes) else encoded))
        self.assertEqual(recovered["batch_run_id"], ORIGIN_RUN)

    def test_a_reference_that_does_not_bind_the_verified_run_fails_closed(self):
        with self.assertRaises(JournalError):
            self.read(document=batch_document(origin_run=ORIGIN_RUN + 1))

    def test_a_malformed_or_missing_reference_fails_closed(self):
        for reference in ("batch-result:0:" + WITNESS,
                          "batch-result:" + str(ORIGIN_RUN) + ":short",
                          "not-a-batch-result"):
            with self.assertRaises(JournalError):
                self.read(state_document=verified_state(reference=reference))
        with self.assertRaises(JournalError):
            read_verified_batch(
                state(transitions=[{"step": "verification", "status": "verified",
                                    "operation_id": DIGEST, "evidence": None}]),
                batch_reference_for=lambda _w: batch_document())

    def test_an_unreadable_document_fails_closed(self):
        with self.assertRaises(JournalError):
            self.read(document="not-a-document")
        with self.assertRaises(JournalError):
            read_verified_batch(verified_state(), batch_reference_for="no")


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

    def test_a_new_mode_step_waits_for_the_intent_row(self):
        # The allocation and witness merge exist, but the intent row is this
        # run's own intent-step output: until it lands there is no
        # authoritative target revision, and the step must not bind the cut
        # squash the candidate transition names separately.
        (self.root / "candidate-transition.json").write_text(json.dumps(
            candidate_document(witness_merge={"merge": {"merge_sha": TARGET}})))
        step = enroll_changelog_site(
            candidate_root=self.root, repository_id=12, ledger=Ledger(rows={}),
            fetch=self.fetch, site_base_url="https://docs.example.invalid")
        new_mode = state(request=request(mode="new", requested_tag=None))
        self.assertEqual(step.observe(new_mode, self.operation()).status, "pending")
        self.assertEqual(self.fetched, [])
        # Once the row has landed and agrees with the witness merge, the same
        # step verifies against the row's target.
        observed = self.step().observe(new_mode, self.operation())
        self.assertEqual(observed.status, "verified")

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


PLAN = "a" * 64


class PreparedPlanRecoveryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        from tools.release import prepared_step

        self.prepared = prepared_step
        self.output = (self.root / prepared_step.output_relative("lmdj-v" + BUILD))

    def write_plan(self, digest=PLAN, body=b"{}"):
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / self.prepared._PLAN_DOCUMENT).write_bytes(body)
        recorded = digest if digest is not None else __import__("hashlib").sha256(body).hexdigest()
        (self.output / self.prepared._PLAN_DIGEST).write_text(recorded + "\n")

    def test_the_enrollment_reads_the_plan_where_the_step_does(self):
        self.assertIsNone(read_prepared_plan(self.root, "lmdj-v" + BUILD))
        self.write_plan(digest=None)
        self.assertEqual(read_prepared_plan(self.root, "lmdj-v" + BUILD),
                         __import__("hashlib").sha256(b"{}").hexdigest())

    def test_a_swapped_digest_that_names_other_bytes_fails_closed(self):
        # A digest file alone must not redefine the plan a later step binds.
        self.write_plan(digest=PLAN, body=b"{}")
        with self.assertRaises(JournalError):
            read_prepared_plan(self.root, "lmdj-v" + BUILD)

    def test_a_document_without_its_digest_fails_closed(self):
        # prepare writes both together, so half the pair is drift, not absence.
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / self.prepared._PLAN_DOCUMENT).write_bytes(b"{}")
        with self.assertRaises(JournalError):
            read_prepared_plan(self.root, "lmdj-v" + BUILD)

    def test_a_digest_without_its_document_fails_closed(self):
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / self.prepared._PLAN_DIGEST).write_text(PLAN + "\n")
        with self.assertRaises(JournalError):
            read_prepared_plan(self.root, "lmdj-v" + BUILD)

    def test_a_malformed_or_unreadable_digest_fails_closed(self):
        self.write_plan("not-a-digest")
        with self.assertRaises(JournalError):
            read_prepared_plan(self.root, "lmdj-v" + BUILD)


class Projection:
    """The far-side Release projection draft_step reads."""

    def __init__(self, *, plan_sha256, draft=True, release_id=4096):
        self.id, self.draft = release_id, draft
        self.tag, self.plan_sha256 = "lmdj-v" + BUILD, plan_sha256


class DraftEnrollmentTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.created = []
        self.release = None

    def write_plan(self):
        import hashlib

        from tools.release import prepared_step

        output = self.root / prepared_step.output_relative("lmdj-v" + BUILD)
        output.mkdir(parents=True, exist_ok=True)
        # prepare writes the document and its digest together; the enrollment
        # now checks they agree.
        body = b'{"fixture": "plan"}'
        (output / prepared_step._PLAN_DOCUMENT).write_bytes(body)
        (output / prepared_step._PLAN_DIGEST).write_text(
            hashlib.sha256(body).hexdigest() + "\n")

    def create_draft(self, tag):
        import hashlib

        self.created.append(tag)
        self.release = Projection(
            plan_sha256=hashlib.sha256(b'{"fixture": "plan"}').hexdigest())

    def step(self):
        return enroll_draft(
            root=self.root, candidate_root=self.root, repository_id=12,
            ledger=Ledger(),
            create_draft=self.create_draft,
            release_by_tag=lambda _tag: self.release)

    def operation(self):
        return {"step": "draft", "operation_id": DIGEST, "status": "intent",
                "evidence": None}

    def test_the_step_drives_its_own_write(self):
        step = self.step()
        self.assertTrue(callable(getattr(step, "advance", None)))

    def test_the_step_waits_until_a_plan_is_prepared(self):
        step = self.step()
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")
        step.advance(state(), self.operation(), before_write=lambda: None)
        self.assertEqual(self.created, [])

    def test_the_step_creates_the_draft_and_verifies_it(self):
        self.write_plan()
        step = self.step()
        # No Release yet: the carrier reports pending so the driver drives it.
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")
        step.advance(state(), self.operation(), before_write=lambda: None)
        self.assertEqual(self.created, ["lmdj-v" + BUILD])
        self.assertEqual(step.observe(state(), self.operation()).status, "verified")

    def test_a_draft_bound_to_another_plan_fails_closed(self):
        self.write_plan()
        self.release = Projection(plan_sha256="9" * 64)
        from tools.release.draft_step import DraftStepError

        step = self.step()
        with self.assertRaises(DraftStepError):
            step.observe(state(), self.operation())


class FinalEnrollmentTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.fetched = []
        self.read = []
        self.release = None
        self.recorded = None
        self.row = None

    def fetch(self, url):
        self.fetched.append(url)
        return 200, f"<html>Product Build {BUILD}</html>"

    def release_by_tag(self, tag):
        self.read.append(("release", tag))
        return self.release

    def ledger_row(self, tag):
        self.read.append(("row", tag))
        return self.row

    def release_id_for(self, tag):
        self.read.append(("record", tag))
        return self.recorded

    def step(self, ledger=None):
        return enroll_final(
            candidate_root=self.root, repository_id=12,
            ledger=Ledger() if ledger is None else ledger, fetch=self.fetch,
            release_by_tag=self.release_by_tag, ledger_row=self.ledger_row,
            release_id_for=self.release_id_for,
            site_base_url="https://docs.example.invalid")

    def operation(self):
        return {"step": "final", "operation_id": DIGEST, "status": "intent",
                "evidence": None}

    def publish(self, release_id=4096):
        self.release = {"draft": False, "id": release_id}
        self.recorded = release_id
        self.row = {"tag": "lmdj-v" + BUILD, "target_revision": TARGET,
                    "channel": "dev", "disposition": "published"}

    def test_the_step_exposes_no_advance(self):
        # The final step only verifies; the driver must never take the
        # self-driving path for it.
        self.assertFalse(callable(getattr(self.step(), "advance", None)))

    def test_non_callable_readers_are_refused_at_enrollment(self):
        with self.assertRaises(JournalError):
            enroll_final(candidate_root=self.root, repository_id=12,
                         ledger=Ledger(), fetch=self.fetch,
                         release_by_tag=self.release_by_tag,
                         ledger_row=self.ledger_row, release_id_for=None,
                         site_base_url="https://docs.example.invalid")

    def test_the_step_is_pending_until_the_build_is_allocated(self):
        step = self.step()
        new_mode = state(request=request(mode="new", requested_tag=None))
        self.assertEqual(step.observe(new_mode, self.operation()).status, "pending")
        self.assertEqual(self.read, [])
        self.assertEqual(self.fetched, [])

    def test_the_step_is_pending_until_the_record_names_the_release(self):
        step = self.step()
        # Neither the record nor the far side names a Release yet.
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")
        # A Draft still being assembled is not a confirmed identity.
        self.release = {"draft": True, "id": 4096}
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")
        # Even a published Release cannot be bound before the record names it.
        self.release = {"draft": False, "id": 4096}
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")
        self.assertEqual(self.fetched, [])

    def test_an_unauthorized_tag_fails_closed_rather_than_waiting(self):
        step = self.step(ledger=Ledger(rows={}))
        with self.assertRaises(JournalError):
            step.observe(state(), self.operation())
        self.assertEqual(self.read, [])
        self.assertEqual(self.fetched, [])

    def test_a_one_sided_or_disagreeing_release_identity_fails_closed(self):
        step = self.step()
        # The record names a Release the far side does not have.
        self.recorded = 4096
        with self.assertRaises(JournalError):
            step.observe(state(), self.operation())
        # The record names a Release that is still a draft.
        self.release = {"draft": True, "id": 4096}
        with self.assertRaises(JournalError):
            step.observe(state(), self.operation())
        # The two sides disagree on the numeric identity.
        self.release = {"draft": False, "id": 8192}
        with self.assertRaises(JournalError):
            step.observe(state(), self.operation())
        # A record without a valid numeric identity is drift.
        self.release = {"draft": False, "id": 4096}
        for recorded in ("4096", 0, -1):
            self.recorded = recorded
            with self.assertRaises(JournalError):
                step.observe(state(), self.operation())
        # An unreadable far-side projection cannot be cross-confirmed.
        self.recorded = 4096
        self.release = "not-a-projection"
        with self.assertRaises(JournalError):
            step.observe(state(), self.operation())
        self.assertEqual(self.fetched, [])

    def test_the_step_delegates_to_the_final_carrier(self):
        self.publish()
        step = self.step()
        observed = step.observe(state(), self.operation())
        self.assertEqual(observed.status, "verified")
        self.assertEqual(observed.evidence["reference"], "final:lmdj-v" + BUILD)
        # Recovery cross-confirms both sides, then the carrier re-reads them
        # under the tag its spec froze.
        tag = "lmdj-v" + BUILD
        self.assertEqual(self.read, [("release", tag), ("record", tag),
                                     ("release", tag), ("row", tag)])
        self.assertEqual(set(self.fetched),
                         {"https://docs.example.invalid/versions/" + BUILD + "/",
                          "https://docs.example.invalid/releases/" + BUILD})

    def test_a_ledger_row_that_disagrees_fails_closed(self):
        self.publish()
        self.row = dict(self.row, disposition="releasable")
        from tools.release.final_steps import SiteStepError

        with self.assertRaises(SiteStepError):
            self.step().observe(state(), self.operation())


WITNESS_MERGE = "2" * 40
INTENT_RUN = 3401234568


def closed_batch_document(target=WITNESS_MERGE, run_id=INTENT_RUN):
    """A closed verified batch reference document, as the verification step binds."""
    return {"schema": "lmdj.ci-batch-release-reference.v1",
            "executor_control_revision": "3" * 40, "executor_event": "push",
            "run_attempt": 1, "origin_record_digest": "5" * 64,
            "admission_record_digest": "6" * 64, "evidence_digest": "7" * 64,
            "request": {"id": "batch-intent", "kind": "auto", "base": "8" * 40,
                        "target": target, "control": "3" * 40,
                        "policy": "9" * 64,
                        "selection": {"kind": "full", "suites": ["unit"],
                                      "reasons": ["candidate"]},
                        "origin_run": {"run_id": run_id, "attempt": 1}}}


class IntentEnrollmentTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.commit_specs = []
        self.sequence_specs = []

    def write_candidate(self, **changes):
        (self.root / "candidate-transition.json").write_text(
            json.dumps(candidate_document(**changes)))

    def write_witness(self):
        self.write_candidate(witness_merge={"merge": {"merge_sha": WITNESS_MERGE}})

    def commit_for(self, spec):
        from tools.release.intent import IntentCommit

        self.commit_specs.append(deepcopy(spec))
        return IntentCommit(root=self.root / "intent-worktree",
                            repository_root=self.root / "repo", spec=spec,
                            freeze=lambda root: None, author_name="Fixture",
                            author_email="fixture@example.invalid")

    def sequence_for(self, spec):
        from tools.release.intent_carrier import (
            IntentBranch,
            IntentPrSequence,
            IntentPullRequest,
        )

        self.sequence_specs.append(deepcopy(spec))
        root = self.root / "intent-sequence"
        branch = IntentBranch(root / "branch", root / "repo",
                              token="FIXTURE-NOT-A-SECRET",
                              authorize=lambda _spec: None)
        pr = IntentPullRequest(root / "pr", api=lambda *a, **k: None,
                               authorize=lambda _spec: None,
                               review=lambda *a: None, verify_merged=lambda *a: None)
        return IntentPrSequence(root, branch=branch, pr=pr)

    def step(self, **overrides):
        arguments = dict(candidate_root=self.root, repository_id=12,
                         batch_reference_for=lambda _witness: closed_batch_document(),
                         commit_for=self.commit_for, sequence_for=self.sequence_for)
        arguments.update(overrides)
        return enroll_intent(**arguments)

    def operation(self):
        return {"step": "intent", "operation_id": DIGEST, "status": "intent",
                "evidence": None}

    def new_mode(self, **changes):
        document = state(request=request(mode="new", requested_tag=None), **changes)
        return document

    def verified(self):
        return self.new_mode(transitions=[{
            "step": "verification", "operation_id": DIGEST, "status": "verified",
            "evidence": {"sha256": DIGEST,
                         "reference": f"batch-result:{INTENT_RUN}:{WITNESS_MERGE}"}}])

    def test_the_step_drives_its_own_write(self):
        # The intent step records the reviewed intent: it commits the docs
        # change and drives the PR sequence under the driver's guard.
        self.assertTrue(callable(getattr(self.step(), "advance", None)))

    def test_non_callable_factories_are_refused_at_enrollment(self):
        with self.assertRaises(JournalError):
            self.step(commit_for=None)

    def test_the_step_is_pending_until_the_candidate_is_allocated(self):
        step = self.step()
        self.assertEqual(step.observe(self.new_mode(), self.operation()).status,
                         "pending")
        # A tag-mode request has no candidate state to derive from; its intent
        # row already exists on main, so the step waits rather than rewriting it.
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")
        self.assertEqual(self.commit_specs, [])

    def test_the_step_is_pending_until_the_witness_merge_and_batch_are_frozen(self):
        step = self.step()
        # The cut is merged but the witness merge is not verified yet.
        self.write_candidate()
        self.assertEqual(step.observe(self.verified(), self.operation()).status,
                         "pending")
        # The witness merge exists but the verification step is not verified.
        self.write_witness()
        self.assertEqual(step.observe(self.new_mode(), self.operation()).status,
                         "pending")
        self.assertEqual(self.commit_specs, [])

    def test_a_pending_step_writes_nothing_when_asked_to_advance(self):
        written = []
        step = self.step()
        self.assertEqual(step.observe(self.new_mode(), self.operation()).status,
                         "pending")
        step.advance(self.new_mode(), self.operation(),
                     before_write=lambda: written.append(True))
        self.assertEqual(written, [])
        self.assertEqual(self.commit_specs, [])

    def test_a_witness_disagreement_fails_closed(self):
        self.write_witness()
        # The journal's verified reference names a witness the candidate state
        # never recorded: two durable records disagree, so the step refuses.
        document = self.new_mode(transitions=[{
            "step": "verification", "operation_id": DIGEST, "status": "verified",
            "evidence": {"sha256": DIGEST,
                         "reference": f"batch-result:{INTENT_RUN}:{'4' * 40}"}}])
        with self.assertRaises(JournalError):
            self.step().observe(document, self.operation())

    def test_a_reference_document_binding_another_target_fails_closed(self):
        self.write_witness()
        # The document decodes and binds the recorded run, but certifies a
        # different revision than the witness merge both records name.
        step = self.step(batch_reference_for=lambda _w: closed_batch_document(
            target="4" * 40))
        from tools.release.intent import IntentError

        with self.assertRaises(IntentError):
            step.observe(self.verified(), self.operation())

    def test_a_batch_reference_binding_another_run_fails_closed(self):
        self.write_witness()
        step = self.step(batch_reference_for=lambda _w: closed_batch_document(
            run_id=INTENT_RUN + 1))
        with self.assertRaises(JournalError):
            step.observe(self.verified(), self.operation())

    def test_the_step_delegates_to_the_real_intent_carrier(self):
        self.write_witness()
        step = self.step()
        # The real carrier observes pending before its durable commit exists
        # and must not touch the PR sequence yet.
        observed = step.observe(self.verified(), self.operation())
        self.assertEqual(observed.status, "pending")
        self.assertEqual(len(self.commit_specs), 1)
        self.assertEqual(len(self.sequence_specs), 1)
        spec = self.commit_specs[0]
        self.assertEqual(set(spec), {"operation_id", "request_sha256",
                                     "repository_id", "actor_id", "target_revision",
                                     "product_build", "tag", "snapshot_sha256",
                                     "batch_reference", "batch_run_id"})
        from tools.release.intent import intent_operation_id

        self.assertEqual(spec["operation_id"], intent_operation_id(DIGEST))
        # The intent target is the batch-certified witness merge, never the
        # cut squash the allocation names separately.
        self.assertEqual(spec["target_revision"], WITNESS_MERGE)
        self.assertEqual(spec["tag"], "lmdj-v" + BUILD)
        self.assertEqual(spec["snapshot_sha256"], SNAPSHOT)
        self.assertEqual(spec["batch_reference"], closed_batch_document())
        self.assertEqual(spec["batch_run_id"], INTENT_RUN)
        self.assertEqual(spec, self.sequence_specs[0])

    def test_a_request_without_a_valid_digest_is_refused(self):
        self.write_witness()
        step = self.step()
        with self.assertRaises(JournalError):
            step.observe(self.new_mode(request_digest="short"), self.operation())
        self.assertEqual(self.commit_specs, [])


MAIN_TIP = "1" * 40
CHANGELOG_DIGEST = "5" * 64
NOTES_DIGEST = "6" * 64


class ChangelogEnrollmentTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.commit_specs = []
        self.sequence_specs = []

    def commit_for(self, spec):
        from tools.release.changelog_step import ChangelogCommit

        self.commit_specs.append(deepcopy(spec))
        return ChangelogCommit(root=self.root / "changelog-worktree",
                               repository_root=self.root / "repo", spec=spec,
                               editorial=lambda: ([], []), author_name="Fixture",
                               author_email="fixture@example.invalid")

    def sequence_for(self, spec):
        from tools.release.changelog_step import (
            ChangelogBranch,
            ChangelogPrSequence,
            ChangelogPullRequest,
        )

        self.sequence_specs.append(deepcopy(spec))
        root = self.root / "changelog-sequence"
        branch = ChangelogBranch(root / "branch", root / "repo",
                                 token="FIXTURE-NOT-A-SECRET",
                                 authorize=lambda _spec: None)
        pr = ChangelogPullRequest(root / "pr", api=lambda *a, **k: None,
                                  authorize=lambda _spec: None,
                                  review=lambda *a: None, verify_merged=lambda *a: None)
        return ChangelogPrSequence(root, branch=branch, pr=pr)

    def step(self, **overrides):
        arguments = dict(
            candidate_root=self.root, repository_id=12, ledger=Ledger(),
            main_revision=lambda: MAIN_TIP,
            changelog_binding=lambda: {"schema": "lmdj.release-changelog.v1",
                                       "sha256": CHANGELOG_DIGEST,
                                       "notes_sha256": NOTES_DIGEST},
            commit_for=self.commit_for, sequence_for=self.sequence_for)
        arguments.update(overrides)
        return enroll_changelog(**arguments)

    def operation(self):
        return {"step": "changelog", "operation_id": DIGEST, "status": "intent",
                "evidence": None}

    def test_the_step_drives_its_own_write(self):
        # The changelog step lands the frozen document: it commits the ledger
        # row edit and drives the reviewed PR sequence under the driver's guard.
        self.assertTrue(callable(getattr(self.step(), "advance", None)))

    def test_non_callable_factories_are_refused_at_enrollment(self):
        with self.assertRaises(JournalError):
            self.step(changelog_binding=None)

    def test_the_step_is_pending_until_the_intent_row_exists(self):
        step = self.step()
        # New mode without any candidate state: no Build to bind.
        new_mode = state(request=request(mode="new", requested_tag=None))
        self.assertEqual(step.observe(new_mode, self.operation()).status, "pending")
        # Allocated and witness-merged, but the row is this run's own intent
        # output: until it lands there is no authoritative target revision.
        (self.root / "candidate-transition.json").write_text(json.dumps(
            candidate_document(witness_merge={"merge": {"merge_sha": TARGET}})))
        waiting = self.step(ledger=Ledger(rows={}))
        self.assertEqual(waiting.observe(new_mode, self.operation()).status, "pending")
        self.assertEqual(self.commit_specs, [])

    def test_an_unauthorized_tag_fails_closed_rather_than_waiting(self):
        step = self.step(ledger=Ledger(rows={}))
        with self.assertRaises(JournalError):
            step.observe(state(), self.operation())
        self.assertEqual(self.commit_specs, [])

    def test_an_unavailable_base_or_binding_fails_closed(self):
        with self.assertRaises(JournalError):
            self.step(main_revision=lambda: "not-a-sha").observe(state(), self.operation())
        for bound in (None, {"sha256": CHANGELOG_DIGEST},
                      {"sha256": "short", "notes_sha256": NOTES_DIGEST}):
            with self.assertRaises(JournalError):
                self.step(changelog_binding=lambda: bound).observe(state(),
                                                                   self.operation())
        self.assertEqual(self.commit_specs, [])

    def test_a_pending_step_writes_nothing_when_asked_to_advance(self):
        written = []
        step = self.step()
        new_mode = state(request=request(mode="new", requested_tag=None))
        self.assertEqual(step.observe(new_mode, self.operation()).status, "pending")
        step.advance(new_mode, self.operation(),
                     before_write=lambda: written.append(True))
        self.assertEqual(written, [])
        self.assertEqual(self.commit_specs, [])

    def test_the_step_delegates_to_the_real_changelog_carrier(self):
        step = self.step()
        # The real carrier observes pending before its durable commit exists
        # and must not touch the PR sequence yet.
        observed = step.observe(state(), self.operation())
        self.assertEqual(observed.status, "pending")
        self.assertEqual(len(self.commit_specs), 1)
        self.assertEqual(len(self.sequence_specs), 1)
        spec = self.commit_specs[0]
        self.assertEqual(set(spec), {"operation_id", "request_sha256",
                                     "repository_id", "actor_id", "base_revision",
                                     "head_sha", "tree_sha", "target_revision",
                                     "product_build", "tag", "changelog_sha256",
                                     "notes_sha256"})
        from tools.release.changelog_step import changelog_operation_id

        self.assertEqual(spec["operation_id"], changelog_operation_id(DIGEST))
        # The target revision is the intent row's (the batch-certified witness
        # merge), the base is the resolved canonical main tip, and the digests
        # are the reviewed document's binding.
        self.assertEqual(spec["target_revision"], TARGET)
        self.assertEqual(spec["base_revision"], MAIN_TIP)
        self.assertEqual(spec["changelog_sha256"], CHANGELOG_DIGEST)
        self.assertEqual(spec["notes_sha256"], NOTES_DIGEST)
        self.assertEqual(spec["tag"], "lmdj-v" + BUILD)
        # The commit's own head/tree do not exist yet; the placeholders are
        # deterministic, distinct from base and target, and replaced by the
        # durable commit's identities before the transport reads them.
        self.assertNotIn(spec["head_sha"], (MAIN_TIP, TARGET))
        self.assertNotEqual(spec["head_sha"], spec["tree_sha"])
        self.assertEqual(spec, self.sequence_specs[0])


def _deployment_binding(from_channel="canary", to_channel="dev"):
    from tools.release.model import canonical_sha256

    return {"from_channel": from_channel, "to_channel": to_channel,
            "deployment_runs_sha256": canonical_sha256({"runs": [
                {"host": "runtime", "run_id": 111, "evidence_sha256": "a" * 64},
                {"host": "creator", "run_id": 222, "evidence_sha256": "b" * 64}]}),
            "attestation_sha256": canonical_sha256({"attestation": "verified"})}


class PromotionEnrollmentTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.commit_specs = []
        self.sequence_specs = []
        self.bound = None

    def canary_ledger(self):
        # The promotion starts from the publication channel: the row exists
        # (published) but has no promotions yet.
        return Ledger(rows={"lmdj-v" + BUILD: Intent(channel="canary")})

    def commit_for(self, spec):
        from tools.release.promotion_step import PromotionCommit

        self.commit_specs.append(deepcopy(spec))
        return PromotionCommit(root=self.root / "promotion-worktree",
                               repository_root=self.root / "repo", spec=spec,
                               plan=None, main_tip=lambda: MAIN_TIP,
                               author_name="Fixture",
                               author_email="fixture@example.invalid")

    def sequence_for(self, spec):
        from tools.release.promotion_step import (
            PromotionBranch,
            PromotionPrSequence,
            PromotionPullRequest,
        )

        self.sequence_specs.append(deepcopy(spec))
        root = self.root / "promotion-sequence"
        branch = PromotionBranch(root / "branch", root / "repo",
                                 token="FIXTURE-NOT-A-SECRET",
                                 authorize=lambda _spec: None)
        pr = PromotionPullRequest(root / "pr", api=lambda *a, **k: None,
                                  authorize=lambda _spec: None,
                                  review=lambda *a: None,
                                  verify_merged=lambda *a: None)
        return PromotionPrSequence(root, branch=branch, pr=pr)

    def step(self, **overrides):
        arguments = dict(
            candidate_root=self.root, repository_id=12, ledger=self.canary_ledger(),
            main_revision=lambda: MAIN_TIP,
            promotion_binding=lambda: self.bound,
            commit_for=self.commit_for, sequence_for=self.sequence_for)
        arguments.update(overrides)
        return enroll_promotion(**arguments)

    def operation(self):
        return {"step": "promotion", "operation_id": DIGEST, "status": "intent",
                "evidence": None}

    def test_the_step_drives_its_own_write(self):
        # The promotion step lands the reviewed ledger record and evidence
        # document, then drives the reviewed PR sequence under the guard.
        self.assertTrue(callable(getattr(self.step(), "advance", None)))

    def test_non_callable_factories_are_refused_at_enrollment(self):
        with self.assertRaises(JournalError):
            self.step(promotion_binding=None)

    def test_the_step_is_pending_until_the_identity_and_binding_exist(self):
        step = self.step()
        # New mode without any candidate state: no Build to bind.
        new_mode = state(request=request(mode="new", requested_tag=None))
        self.assertEqual(step.observe(new_mode, self.operation()).status, "pending")
        # Identity derivable (tag-mode row) but the deployment evidence the
        # promotion attests does not exist yet: the step waits.
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")
        self.assertEqual(self.commit_specs, [])

    def test_an_unauthorized_tag_fails_closed_rather_than_waiting(self):
        step = self.step(ledger=Ledger(rows={}))
        with self.assertRaises(JournalError):
            step.observe(state(), self.operation())
        self.assertEqual(self.commit_specs, [])

    def test_a_binding_disagreeing_with_the_row_fails_closed(self):
        step = self.step()
        # The reviewed promotion must start from the channel the row is on.
        with self.assertRaises(JournalError):
            self.step(promotion_binding=lambda: _deployment_binding(
                from_channel="dev", to_channel="beta")).observe(state(), self.operation())
        # Backwards, same-channel, stable and unknown targets are all refused.
        for to_channel in ("canary", "stable", "nowhere"):
            with self.assertRaises(JournalError):
                self.step(promotion_binding=lambda: _deployment_binding(
                    to_channel=to_channel)).observe(state(), self.operation())
        self.assertEqual(self.commit_specs, [])

    def test_a_malformed_binding_fails_closed(self):
        for bound in ("not-a-binding", {"from_channel": "canary"},
                      _deployment_binding()):
            broken = bound
            if isinstance(bound, dict) and "deployment_runs_sha256" in bound:
                broken = dict(bound, deployment_runs_sha256="short")
            with self.assertRaises(JournalError):
                self.step(promotion_binding=lambda: broken).observe(state(),
                                                                    self.operation())
        self.assertEqual(self.commit_specs, [])

    def test_a_pending_step_writes_nothing_when_asked_to_advance(self):
        written = []
        step = self.step()
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")
        step.advance(state(), self.operation(),
                     before_write=lambda: written.append(True))
        self.assertEqual(written, [])
        self.assertEqual(self.commit_specs, [])

    def test_the_step_delegates_to_the_real_promotion_carrier(self):
        self.bound = _deployment_binding()
        step = self.step()
        # The real carrier observes pending before its durable commit exists
        # and must not touch the PR sequence yet.
        observed = step.observe(state(), self.operation())
        self.assertEqual(observed.status, "pending")
        self.assertEqual(len(self.commit_specs), 1)
        self.assertEqual(len(self.sequence_specs), 1)
        spec = self.commit_specs[0]
        self.assertEqual(set(spec), {"operation_id", "request_sha256",
                                     "repository_id", "actor_id", "base_revision",
                                     "head_sha", "tree_sha", "tag",
                                     "target_revision", "to_channel",
                                     "from_channel", "deployment_runs_sha256",
                                     "attestation_sha256"})
        from tools.release.promotion_step import promotion_operation_id

        self.assertEqual(spec["operation_id"], promotion_operation_id(DIGEST))
        # The target revision is the intent row's, the base is the resolved
        # canonical main tip, and the promotion binds the row's channel.
        self.assertEqual(spec["target_revision"], TARGET)
        self.assertEqual(spec["base_revision"], MAIN_TIP)
        self.assertEqual(spec["tag"], "lmdj-v" + BUILD)
        self.assertEqual((spec["from_channel"], spec["to_channel"]),
                         ("canary", "dev"))
        self.assertEqual(spec["deployment_runs_sha256"],
                         self.bound["deployment_runs_sha256"])
        self.assertEqual(spec["attestation_sha256"],
                         self.bound["attestation_sha256"])
        # Inert placeholders: distinct from base, replaced from the durable
        # commit before the transport reads them.
        self.assertNotEqual(spec["head_sha"], MAIN_TIP)
        self.assertNotEqual(spec["head_sha"], spec["tree_sha"])
        self.assertEqual(spec, self.sequence_specs[0])


class CandidateEnrollmentTest(unittest.TestCase):
    """The managed candidate adapter's assembly contract.

    The full new-mode assembly drives the real preparation layer (owned
    install, official snapshot, six cut checks); that journey is covered by
    tests/build/release_candidate_portal_journey.py, which composes the
    transition through the same production assembly. Here: the refusal and
    recovery boundaries that need no preparation run.
    """

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def test_a_tag_mode_request_is_refused_before_any_preparation(self):
        # A checked-cut allocation exists only for `new` mode; the preparation
        # layer itself refuses an existing-tag request.
        from tools.release.carriers import enroll_candidate
        from tools.release.candidate_preparation import CandidatePreparationError

        with self.assertRaises(CandidatePreparationError):
            enroll_candidate(
                request=request(), preparation_root=self.root / "preparation",
                repository_root=self.root / "repo", source_root=self.root / "src",
                reservation_root=self.root / "reservations",
                transition_root=self.root / "transition",
                witness_root=self.root / "witness", repository_id=12,
                client=None, token="FIXTURE-NOT-A-SECRET",
                authorize=lambda _request: None, observe_main=lambda: TARGET,
                review=lambda *a: None, verify_merged=lambda *a: None,
                clock=lambda: 1789550000, path="/usr/bin:/bin",
                author_name="Fixture", author_email="fixture@example.invalid",
                source_timestamp=1789550000)
        self.assertFalse((self.root / "preparation").exists())

    def test_non_callable_gates_are_refused_at_enrollment(self):
        from tools.release.carriers import enroll_candidate

        with self.assertRaises(JournalError):
            enroll_candidate(
                request=request(mode="new", requested_tag=None),
                preparation_root=self.root / "preparation",
                repository_root=self.root / "repo", source_root=self.root / "src",
                reservation_root=self.root / "reservations",
                transition_root=self.root / "transition",
                witness_root=self.root / "witness", repository_id=12,
                client=None, token="FIXTURE-NOT-A-SECRET",
                authorize=None, observe_main=lambda: TARGET,
                review=lambda *a: None, verify_merged=lambda *a: None,
                clock=lambda: 1789550000, path="/usr/bin:/bin",
                author_name="Fixture", author_email="fixture@example.invalid",
                source_timestamp=1789550000)

    def test_the_author_timestamp_is_recovered_from_the_enrolled_scope(self):
        from tools.release.candidate_transition import CandidateTransition
        from tools.release.model import canonical_json
        from tools.release.orchestration import RequestJournal

        root = self.root / "transition"
        self.assertIsNone(enrolled_candidate_timestamp(root))
        root.mkdir(mode=0o700)
        self.assertIsNone(enrolled_candidate_timestamp(root))
        scope = {"author": {"author_name": "Fixture",
                            "author_email": "fixture@example.invalid",
                            "timestamp": 1789550000}}
        with RequestJournal(root) as journal:
            journal._write(CandidateTransition.MARKER, canonical_json(scope))
        self.assertEqual(enrolled_candidate_timestamp(root), 1789550000)

    def test_a_corrupt_enrolled_scope_fails_closed(self):
        from tools.release.candidate_transition import CandidateTransition
        from tools.release.model import canonical_json
        from tools.release.orchestration import RequestJournal

        root = self.root / "transition"
        root.mkdir(mode=0o700)
        with RequestJournal(root) as journal:
            journal._write(CandidateTransition.MARKER,
                           canonical_json({"author": {"timestamp": "soon"}}))
        with self.assertRaises(JournalError):
            enrolled_candidate_timestamp(root)


if __name__ == "__main__":
    unittest.main()
