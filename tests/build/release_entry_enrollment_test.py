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
    enroll_prepared,
    enroll_promotion,
    enroll_verification,
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


SIGNER = "A1B2C3D4E5F60718293A4B5C6D7E8F9012345678"
TAG_OBJECT = "7" * 40


class LocalTag:
    """The local signed tag state the prepared carrier reads back."""

    def __init__(self, *, object_id=TAG_OBJECT, target_revision=TARGET,
                 signer_fingerprint=SIGNER):
        self.object_id = object_id
        self.target_revision = target_revision
        self.signer_fingerprint = signer_fingerprint


class PreparedEnrollmentTest(unittest.TestCase):
    """`prepared` authorizes before the write and freezes its own outputs."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.prepared_calls = []
        self.tag = None
        self.raises = False

    def body(self):
        return b'{"fixture": "prepared-plan"}'

    def write_plan(self):
        import hashlib

        from tools.release import prepared_step

        output = self.root / prepared_step.output_relative("lmdj-v" + BUILD)
        output.mkdir(parents=True, exist_ok=True)
        (output / prepared_step._PLAN_DOCUMENT).write_bytes(self.body())
        (output / prepared_step._PLAN_DIGEST).write_text(
            hashlib.sha256(self.body()).hexdigest() + "\n")

    def prepare(self, tag):
        self.prepared_calls.append(tag)
        if self.raises:
            raise RuntimeError("sensitive-upstream-error-not-for-public-status")
        # The real prepare signs the local tag first and then writes the plan.
        self.tag = LocalTag()
        self.write_plan()

    def step(self, *, ledger=None, signer=SIGNER):
        return enroll_prepared(
            root=self.root, candidate_root=self.root, repository_id=12,
            ledger=Ledger() if ledger is None else ledger,
            prepare=self.prepare,
            local_tag_state=lambda _tag: self.tag,
            signer_fingerprint=signer)

    def operation(self):
        return {"step": "prepared", "operation_id": DIGEST, "status": "intent",
                "evidence": None}

    def test_the_step_drives_its_own_write(self):
        self.assertTrue(callable(getattr(self.step(), "advance", None)))

    def test_the_step_waits_until_the_reviewed_row_lands(self):
        # The intent row is this run's own intent-step output and it is what
        # authorizes the write; before it lands there is nothing to authorize,
        # so the step waits rather than driving prepare on a guessed identity.
        (self.root / "candidate-transition.json").write_text(json.dumps(
            candidate_document(witness_merge={"merge": {"merge_sha": TARGET}})))
        new_mode = state(request=request(mode="new", requested_tag=None))
        step = self.step(ledger=Ledger(rows={}))
        self.assertEqual(step.observe(new_mode, self.operation()).status, "pending")
        step.advance(new_mode, self.operation(), before_write=lambda: None)
        self.assertEqual(self.prepared_calls, [])

    def test_an_unauthorized_tag_fails_closed_rather_than_waiting(self):
        step = self.step(ledger=Ledger(rows={}))
        with self.assertRaises(JournalError):
            step.observe(state(), self.operation())
        self.assertEqual(self.prepared_calls, [])

    def test_the_step_drives_prepare_once_and_freezes_its_own_output(self):
        import hashlib

        step = self.step()
        # Nothing this step writes exists yet, so the driver is told to act.
        self.assertEqual(step.observe(state(), self.operation()).status, "absent")
        guarded = []
        step.advance(state(), self.operation(),
                     before_write=lambda: guarded.append(True))
        self.assertEqual(guarded, [True])
        self.assertEqual(self.prepared_calls, ["lmdj-v" + BUILD])
        observed = step.observe(state(), self.operation())
        self.assertEqual(observed.status, "verified")
        self.assertEqual(observed.evidence["reference"], "prepared:lmdj-v" + BUILD)
        # The frozen digest is the one prepare recorded, not an invented value.
        from tools.release.carriers import read_prepared_plan

        self.assertEqual(read_prepared_plan(self.root, "lmdj-v" + BUILD),
                         hashlib.sha256(self.body()).hexdigest())

    def test_an_existing_prepared_output_is_verified_without_a_drive(self):
        self.tag = LocalTag()
        self.write_plan()
        step = self.step()
        self.assertEqual(step.observe(state(), self.operation()).status, "verified")
        step.advance(state(), self.operation(), before_write=lambda: None)
        self.assertEqual(self.prepared_calls, [])

    def test_a_local_tag_without_the_output_is_still_absent_work(self):
        # prepare owns the reconcile case and refuses a tag that does not match
        # the reviewed target, so this is absent work rather than a partial one.
        self.tag = LocalTag()
        step = self.step()
        self.assertEqual(step.observe(state(), self.operation()).status, "absent")

    def test_a_leftover_tag_prepare_refuses_surfaces_as_unknown(self):
        # prepare owns the reconcile case and refuses a local tag that does not
        # match the reviewed target, so classifying "tag without output" as
        # absent work never rebuilds over drift: the driver asks the step to
        # act and the refusal surfaces as unknown with the tag untouched.
        self.tag = LocalTag(target_revision="9" * 40)
        self.raises = True
        step = self.step()
        self.assertEqual(step.observe(state(), self.operation()).status, "absent")
        carrier = step.carrier(state(), self.operation())
        observed = carrier.advance(state(), self.operation(),
                                   before_write=lambda: None)
        self.assertEqual(observed.status, "unknown")
        self.assertEqual(self.tag.target_revision, "9" * 40)
        self.assertEqual(self.prepared_calls, ["lmdj-v" + BUILD])

    def test_a_failing_prepare_reports_unknown_and_never_retries(self):
        # prepare owns its own durable recovery, so a raised call is an unknown
        # write result the carrier reports as such: it must not swallow the
        # error, invent evidence, or call prepare a second time.
        self.raises = True
        carrier = self.step().carrier(state(), self.operation())
        observed = carrier.advance(state(), self.operation(),
                                   before_write=lambda: None)
        self.assertEqual(observed.status, "unknown")
        self.assertIsNone(observed.evidence)
        self.assertEqual(self.prepared_calls, ["lmdj-v" + BUILD])

    def test_a_plan_whose_signed_tag_is_gone_stays_pending(self):
        # Present work that cannot be verified is never absent: the driver waits
        # for the restored tag instead of rebuilding over the drift.
        self.write_plan()
        step = self.step()
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")
        step.advance(state(), self.operation(), before_write=lambda: None)
        self.assertEqual(self.prepared_calls, [])

    def test_a_signed_tag_on_another_target_fails_closed(self):
        from tools.release.prepared_step import PreparedStepError

        self.write_plan()
        self.tag = LocalTag(target_revision="9" * 40)
        step = self.step()
        with self.assertRaises(PreparedStepError):
            step.observe(state(), self.operation())

    def test_a_tag_signed_by_another_key_fails_closed(self):
        from tools.release.prepared_step import PreparedStepError

        self.write_plan()
        self.tag = LocalTag()
        step = self.step(signer="B" * 40)
        with self.assertRaises(PreparedStepError):
            step.observe(state(), self.operation())


class PreparedAuthorizationTest(unittest.TestCase):
    """The pre-write half stays a separate, narrower shape than the spec."""

    def authorization(self, **changes):
        from tools.release.prepared_step import prepared_operation_id

        document = {"operation_id": prepared_operation_id(DIGEST),
                    "request_sha256": DIGEST, "repository_id": 12,
                    "actor_id": 34, "tag": "lmdj-v" + BUILD,
                    "target_revision": TARGET}
        document.update(changes)
        return document

    def test_the_reviewed_pre_write_fields_validate(self):
        from tools.release.prepared_step import validate_authorization

        self.assertIsNone(validate_authorization(self.authorization()))

    def test_the_result_fields_are_not_accepted_as_authorization(self):
        # The two shapes must not stand in for one another: `validate_spec`
        # stays the only judge of the complete, result-bound spec.
        from tools.release.prepared_step import (
            PreparedStepError,
            validate_authorization,
        )

        with self.assertRaises(PreparedStepError):
            validate_authorization(self.authorization(plan_sha256=PLAN,
                                                      tag_object_id=TAG_OBJECT))

    def test_a_malformed_derived_field_fails_closed_at_the_freeze(self):
        # `freeze_spec` is the boundary where the derived half joins the
        # authorization, so it is where a corrupted output must be rejected —
        # not one frame later inside `read_back`, which a future caller could
        # skip.
        from tools.release.prepared_step import (
            PreparedStepError,
            freeze_spec,
        )

        class Tag:
            def __init__(self, object_id):
                self.object_id = object_id

        with self.assertRaises(PreparedStepError):
            freeze_spec(self.authorization(), plan_sha256="not-a-digest",
                        tag_state=Tag(TAG_OBJECT))
        with self.assertRaises(PreparedStepError):
            freeze_spec(self.authorization(), plan_sha256=PLAN,
                        tag_state=Tag("not-an-object-id"))
        frozen = freeze_spec(self.authorization(), plan_sha256=PLAN,
                             tag_state=Tag(TAG_OBJECT))
        self.assertEqual(frozen["plan_sha256"], PLAN)
        self.assertEqual(frozen["tag_object_id"], TAG_OBJECT)

    def test_an_operation_from_another_request_fails_closed(self):
        from tools.release.prepared_step import (
            PreparedStepError,
            validate_authorization,
        )

        with self.assertRaises(PreparedStepError):
            validate_authorization(self.authorization(operation_id="9" * 64))

    def test_a_missing_authorization_field_fails_closed(self):
        from tools.release.prepared_step import (
            PreparedStepError,
            validate_authorization,
        )

        for absent in ("tag", "target_revision", "repository_id", "actor_id",
                       "request_sha256", "operation_id"):
            document = self.authorization()
            del document[absent]
            with self.assertRaises(PreparedStepError):
                validate_authorization(document)


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


class RecoveredDispatchTest(unittest.TestCase):
    """The managed dispatch wrapper: pending until derivable, never self-driving."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def operation(self):
        return {"step": "publication", "operation_id": DIGEST,
                "status": "intent", "evidence": None}

    def test_pending_until_derivable_and_no_write_while_waiting(self):
        from tools.release.carriers import RecoveredDispatch

        step = RecoveredDispatch("publication", lambda _s, _o: None)
        observed = step.observe(state(), self.operation())
        self.assertEqual(observed.status, "pending")
        self.assertIsNone(observed.evidence)
        written = []
        # The driver drives a managed pending step through advance; with the
        # inputs still underivable, nothing may be posted or guarded.
        step.advance(state(), self.operation(),
                     before_write=lambda: written.append(True))
        self.assertEqual(written, [])
        with self.assertRaises(JournalError):
            step.advance(state(), {"step": "publication", "operation_id": "e" * 64},
                         before_write=lambda: written.append(True))
        self.assertEqual(written, [])

    def test_delegation_and_refusals(self):
        from tools.release.carriers import RecoveredDispatch

        calls = []

        class Adapter:
            def observe(self, state, operation):
                calls.append("observe")
                return Observation("absent")

            def advance(self, state, operation, *, before_post):
                calls.append("advance")
                before_post()

        step = RecoveredDispatch("publication", lambda _s, _o: Adapter())
        self.assertEqual(step.observe(state(), self.operation()).status, "absent")
        posted = []
        step.advance(state(), self.operation(),
                     before_write=lambda: posted.append(True))
        self.assertEqual(posted, [True])
        self.assertEqual(calls, ["observe", "advance"])
        with self.assertRaises(JournalError):
            step.observe(state(), {"step": "runtime", "operation_id": DIGEST})
        with self.assertRaises(JournalError):
            RecoveredDispatch("draft", lambda _s, _o: None)
        with self.assertRaises(JournalError):
            RecoveredDispatch("publication", None)

    def test_advance_drives_the_adapter_the_observation_produced(self):
        from tools.release.carriers import RecoveredDispatch

        made = []

        class Adapter:
            def __init__(self):
                self.calls = []
                made.append(self)

            def observe(self, state, operation):
                self.calls.append("observe")
                return Observation("absent")

            def advance(self, state, operation, *, before_post):
                self.calls.append("advance")

        step = RecoveredDispatch("publication", lambda _s, _o: Adapter())
        self.assertEqual(step.observe(state(), self.operation()).status, "absent")
        step.advance(state(), self.operation(), before_write=lambda: None)
        # The driver holds one writer lock across observe → advance: the
        # adapter the observation produced is the one the advance drives,
        # not a fresh recovery.
        self.assertEqual(len(made), 1)
        self.assertEqual(made[0].calls, ["observe", "advance"])


CHANGELOG_DOCUMENT = {"schema": "lmdj.release-changelog.v1",
                      "repository": "endaye/lmdj", "tag": "lmdj-v" + BUILD,
                      "product_build": BUILD, "profile": "web-hosts",
                      "target_revision": TARGET, "baseline": None,
                      "commits": [TARGET],
                      "changes": [{"category": "fix", "area": "core",
                                   "text": "Fixture repair", "commits": [TARGET]}],
                      "exclusions": []}


class PublicationEnrollmentTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.release = None
        self.built = []
        self.binds = []
        self.effect_calls = []
        self.api_reads = []

    def write_plan(self):
        import hashlib

        from tools.release import prepared_step

        output = self.root / prepared_step.output_relative("lmdj-v" + BUILD)
        output.mkdir(parents=True, exist_ok=True)
        body = b'{"fixture": "plan"}'
        (output / prepared_step._PLAN_DOCUMENT).write_bytes(body)
        (output / prepared_step._PLAN_DIGEST).write_text(
            hashlib.sha256(body).hexdigest() + "\n")
        return hashlib.sha256(body).hexdigest()

    def ledger(self, with_changelog=False):
        self.intent = Intent()
        if with_changelog:
            self.intent.changelog = deepcopy(CHANGELOG_DOCUMENT)
        return Ledger(rows={"lmdj-v" + BUILD: self.intent})

    def verify_effect(self, state, operation, binding):
        self.effect_calls.append(binding)
        return Observation("pending")

    def transition_for(self, spec, expected, bind):
        self.binds.append(bind)
        from tools.release.dispatch_evidence import DispatchEvidenceConsumer
        from tools.release.dispatch_transition import DispatchTransition
        from tools.release.durable_dispatch import DurableDispatch
        from tools.release.github_api import GitHubClient

        def transport(method, url, headers, body):
            self.api_reads.append((method, url))
            raise AssertionError("the absent path must not touch the API")

        consumer = DispatchEvidenceConsumer(
            api_get=lambda *a, **k: None, git_root=self.root, repository_id=12,
            workflow="publish-release.yml", workflow_id=50,
            producer_revision=spec["producer_revision"])
        controller = DurableDispatch(
            self.root / "dispatch",
            client=GitHubClient(token="FIXTURE-NOT-A-SECRET",
                                http_transport=transport),
            consumer=consumer, authorize=lambda _spec: None,
            ready=lambda _spec: None)
        self.built.append((deepcopy(spec), deepcopy(expected)))
        return DispatchTransition(controller, spec, bind=bind,
                                  verify_effect=self.verify_effect)

    def step(self, **overrides):
        from tools.release.carriers import enroll_publication

        arguments = dict(root=self.root, candidate_root=self.root,
                         repository_id=12,
                         workflow_id=50, producer_revision="0" * 40,
                         release_by_tag=lambda _tag: self.release,
                         transition_for=self.transition_for)
        arguments.update(overrides)
        if "ledger" not in arguments:
            arguments["ledger"] = self.ledger()
        return enroll_publication(**arguments)

    def publication_state(self):
        # The real DispatchTransition validates the journal state's request
        # binding, so the fixture digest must be the true canonical one.
        from tools.release.model import canonical_sha256

        document = request()
        return state(request=document,
                     request_digest=canonical_sha256(document))

    def operation(self):
        from tools.release.model import canonical_sha256

        digest = canonical_sha256(request())
        return {"step": "publication",
                "operation_id": canonical_sha256({"request": digest,
                                                  "step": "publication"}),
                "status": "intent", "evidence": None}

    def test_pending_at_each_underivable_stage(self):
        step = self.step()
        # New mode before any allocation: no Build to publish.
        new_mode = state(request=request(mode="new", requested_tag=None))
        self.assertEqual(step.observe(new_mode, self.operation()).status, "pending")
        # Tag mode with the row but no prepared plan.
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")
        # Plan prepared but the draft step has not created the Release.
        self.write_plan()
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")
        # Draft exists but the changelog step has not bound its record.
        self.release = {"draft": True, "id": 4096}
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")
        self.assertEqual(self.built, [])

    def test_an_unreadable_or_idless_release_fails_closed(self):
        self.write_plan()
        step = self.step()
        for release in ("not-a-projection", {"draft": True},
                        {"draft": True, "id": "4096"}):
            self.release = release
            with self.assertRaises(JournalError):
                step.observe(state(), self.operation())
        self.assertEqual(self.built, [])

    def test_non_callable_readers_are_refused_at_enrollment(self):
        from tools.release.carriers import enroll_publication

        with self.assertRaises(JournalError):
            self.step(release_by_tag=None)
        with self.assertRaises(JournalError):
            self.step(transition_for=None)

    def test_delegation_builds_the_real_managed_adapter(self):
        from tools.release.model import canonical_sha256

        plan = self.write_plan()
        self.release = {"draft": True, "id": 4096}
        step = self.step(ledger=self.ledger(with_changelog=True))
        # The real DispatchTransition + DurableDispatch: the durable child is
        # enrolled, nothing is posted, and the honest not-yet-dispatched state
        # is absent (not pending — the inputs exist, the effect does not).
        observed = step.observe(self.publication_state(), self.operation())
        self.assertEqual(observed.status, "absent")
        self.assertEqual(self.api_reads, [])
        self.assertEqual(self.effect_calls, [])
        self.assertEqual(len(self.built), 1)
        spec, expected = self.built[0]
        digest = canonical_sha256(request())
        operation_id = canonical_sha256({"request": digest,
                                         "step": "publication"})
        self.assertEqual(spec["operation_id"], operation_id)
        self.assertEqual(spec["workflow"], "publish-release.yml")
        self.assertEqual(spec["workflow_id"], 50)
        self.assertEqual(spec["inputs"], {"tag": "lmdj-v" + BUILD,
                                          "release_id": "4096",
                                          "plan_sha256": plan,
                                          "request_id": operation_id})
        from tools.release.changelog import binding

        digests = binding(deepcopy(CHANGELOG_DOCUMENT))
        self.assertEqual(expected, {"target_revision": TARGET,
                                    "changelog_sha256": digests["sha256"],
                                    "notes_sha256": digests["notes_sha256"]})
        # The durable dispatch child enrolled its own state, read-only.
        enrolled = json.loads((self.root / "dispatch" / "dispatch.json").read_text())
        self.assertEqual(enrolled["post_intent"], False)
        self.assertEqual(enrolled["spec"]["operation_id"], operation_id)

    def test_a_drifting_record_fails_closed_at_the_dispatch_boundary(self):
        self.write_plan()
        self.release = {"draft": True, "id": 4096}
        step = self.step(ledger=self.ledger(with_changelog=True))
        self.assertEqual(step.observe(self.publication_state(), self.operation()).status,
                         "absent")
        # The bind cross-check itself: the records must still agree with the
        # enrolled spec at the dispatch boundary.
        self.release = {"draft": True, "id": 8192}
        with self.assertRaises(JournalError):
            self.binds[0](self.publication_state(), self.operation(),
                          self.built[0][0])
        # And one layer down, the durable child refuses the rebound spec that
        # a fresh recovery derives from the drifted record.
        from tools.release.durable_dispatch import DurableDispatchError

        with self.assertRaises(DurableDispatchError):
            step.observe(self.publication_state(), self.operation())

    def test_bind_also_guards_the_frozen_effect_expectation(self):
        self.write_plan()
        self.release = {"draft": True, "id": 4096}
        step = self.step(ledger=self.ledger(with_changelog=True))
        self.assertEqual(step.observe(self.publication_state(), self.operation()).status,
                         "absent")
        # The spec inputs still match, but the frozen expectation drifted: the
        # row's changelog binding changed under the enrolled adapter.
        self.intent.changelog = deepcopy(CHANGELOG_DOCUMENT)
        self.intent.changelog["changes"][0]["text"] = "Rewritten after review"
        with self.assertRaises(JournalError):
            self.binds[0](self.publication_state(), self.operation(),
                          self.built[0][0])


def deployment_projection(**changes):
    """A frozen deployment projection with the shape DeploymentEffect binds."""
    document = {"target_revision": TARGET, "product_build": BUILD,
                "host_version": "4.2.0", "site_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "archive": {"filename": "lmdj-web-runtime-host-4.2.0.tar.gz",
                            "sha256": "5" * 64},
                "release_files": {"index_sha256": "6" * 64,
                                  "manifest_sha256": "7" * 64},
                "prior": None, "prior_site_sha256": "8" * 64}
    document.update(changes)
    return document


class DeploymentEnrollmentTest(unittest.TestCase):
    """Both Host deploy steps share the enrollment; each case runs twice."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.projection = None
        self.built = []
        self.binds = []
        self.effect_calls = []
        self.api_reads = []

    def transition_for(self, spec, expected, bind):
        from tools.release.deployment_effect import DeploymentEffect
        from tools.release.dispatch_evidence import DispatchEvidenceConsumer
        from tools.release.dispatch_transition import DispatchTransition
        from tools.release.durable_dispatch import DurableDispatch
        from tools.release.github_api import GitHubClient

        def transport(method, url, headers, body):
            self.api_reads.append((method, url))
            raise AssertionError("the absent path must not touch the API")

        consumer = DispatchEvidenceConsumer(
            api_get=lambda *a, **k: None, git_root=self.root, repository_id=12,
            workflow=spec["workflow"], workflow_id=50,
            producer_revision=spec["producer_revision"])
        controller = DurableDispatch(
            self.root / ("dispatch-" + spec["workflow"]),
            client=GitHubClient(token="FIXTURE-NOT-A-SECRET",
                                http_transport=transport),
            consumer=consumer, authorize=lambda _spec: None,
            ready=lambda _spec: None)
        # The real effect verifier validates the frozen projection's full
        # shape at construction.
        effect = DeploymentEffect(consumer=consumer, spec=spec,
                                  expected=expected)
        self.built.append((deepcopy(spec), deepcopy(expected)))
        self.binds.append(bind)
        return DispatchTransition(controller, spec, bind=bind,
                                  verify_effect=effect)

    def step(self, step, **overrides):
        from tools.release.carriers import enroll_deployment

        arguments = dict(candidate_root=self.root, repository_id=12,
                         ledger=Ledger(), workflow_id=50,
                         producer_revision="0" * 40,
                         projection_for=lambda _tag: self.projection,
                         transition_for=self.transition_for)
        arguments.update(overrides)
        return enroll_deployment(step, **arguments)

    def operation(self, step):
        from tools.release.model import canonical_sha256

        digest = canonical_sha256(request())
        return {"step": step,
                "operation_id": canonical_sha256({"request": digest,
                                                  "step": step}),
                "status": "intent", "evidence": None}

    def deploy_state(self):
        from tools.release.model import canonical_sha256

        document = request()
        return state(request=document,
                     request_digest=canonical_sha256(document))

    def test_pending_until_the_identity_and_projection_exist(self):
        for step_name in ("runtime", "creator"):
            with self.subTest(step=step_name):
                step = self.step(step_name)
                new_mode = state(request=request(mode="new",
                                                 requested_tag=None))
                self.assertEqual(step.observe(new_mode, self.operation(step_name)).status,
                                 "pending")
                # Identity derivable (tag-mode row) but the composition has
                # not assembled the frozen projection yet.
                self.assertEqual(step.observe(self.deploy_state(),
                                              self.operation(step_name)).status,
                                 "pending")
        self.assertEqual(self.built, [])

    def test_a_projection_that_does_not_bind_this_release_fails_closed(self):
        for bad in ("not-a-projection",
                    deployment_projection(target_revision="9" * 40),
                    deployment_projection(product_build="1.0.59.0"),
                    deployment_projection(prior_site_sha256="short"),
                    {"target_revision": TARGET}):
            for step_name in ("runtime", "creator"):
                with self.subTest(step=step_name):
                    self.projection = bad
                    with self.assertRaises(JournalError):
                        self.step(step_name).observe(self.deploy_state(),
                                                     self.operation(step_name))
        self.assertEqual(self.built, [])

    def test_non_callable_readers_and_unknown_steps_are_refused(self):
        from tools.release.carriers import enroll_deployment

        with self.assertRaises(JournalError):
            self.step("runtime", projection_for=None)
        with self.assertRaises(JournalError):
            enroll_deployment("publication", candidate_root=self.root,
                              repository_id=12, ledger=Ledger(),
                              workflow_id=50, producer_revision="0" * 40,
                              projection_for=lambda _tag: None,
                              transition_for=self.transition_for)

    def test_delegation_builds_the_real_managed_adapter_per_step(self):
        from tools.release.model import canonical_sha256

        self.projection = deployment_projection()
        for step_name, workflow in (("runtime", "deploy-web-runtime-host.yml"),
                                    ("creator", "deploy-creator-web.yml")):
            with self.subTest(step=step_name):
                step = self.step(step_name)
                observed = step.observe(self.deploy_state(),
                                        self.operation(step_name))
                # Real DispatchTransition + DurableDispatch + DeploymentEffect:
                # durable child enrolled read-only, nothing posted, honest
                # absent (inputs exist, the effect does not).
                self.assertEqual(observed.status, "absent")
        self.assertEqual(self.api_reads, [])
        self.assertEqual(self.effect_calls, [])
        self.assertEqual(len(self.built), 2)
        digest = canonical_sha256(request())
        for (spec, expected), (step_name, workflow) in zip(
                self.built, (("runtime", "deploy-web-runtime-host.yml"),
                             ("creator", "deploy-creator-web.yml"))):
            operation_id = canonical_sha256({"request": digest, "step": step_name})
            self.assertEqual(spec["operation_id"], operation_id)
            self.assertEqual(spec["workflow"], workflow)
            self.assertEqual(spec["inputs"],
                             {"tag": "lmdj-v" + BUILD, "request_id": operation_id,
                              "prior_site_sha256": "8" * 64})
            self.assertEqual(expected, deployment_projection())
        for step_name, workflow in (("runtime", "deploy-web-runtime-host.yml"),
                                    ("creator", "deploy-creator-web.yml")):
            enrolled = json.loads(
                (self.root / ("dispatch-" + workflow) / "dispatch.json").read_text())
            self.assertEqual(enrolled["post_intent"], False)

    def test_bind_rejects_projection_drift(self):
        self.projection = deployment_projection()
        step = self.step("runtime")
        self.assertEqual(step.observe(self.deploy_state(),
                                      self.operation("runtime")).status, "absent")
        self.projection = deployment_projection(prior_site_sha256="9" * 64)
        with self.assertRaises(JournalError):
            self.binds[0](self.deploy_state(), self.operation("runtime"),
                          self.built[0][0])
        # And one layer down, the durable child refuses the rebound spec.
        from tools.release.durable_dispatch import DurableDispatchError

        with self.assertRaises(DurableDispatchError):
            step.observe(self.deploy_state(), self.operation("runtime"))


class PublishedRecordEnrollmentTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.release = None
        self.factory_inputs = []
        self.api_reads = []

    def write_plan(self):
        import hashlib

        from tools.release import prepared_step

        output = self.root / prepared_step.output_relative("lmdj-v" + BUILD)
        output.mkdir(parents=True, exist_ok=True)
        body = b'{"fixture": "plan"}'
        (output / prepared_step._PLAN_DOCUMENT).write_bytes(body)
        (output / prepared_step._PLAN_DIGEST).write_text(
            hashlib.sha256(body).hexdigest() + "\n")
        return hashlib.sha256(body).hexdigest()

    def api(self, method, path, document=None):
        # The absent path is GET-only: repo/actor/branch authority reads plus
        # the PR inventory lookup.
        self.assertEqual(method, "GET")
        self.api_reads.append(path)
        if path == "":
            return {"id": 12, "full_name": "endaye/lmdj"}
        if path == "/user":
            return {"id": 34}
        if path == "/branches/main":
            return {"name": "main", "protected": True, "commit": {"sha": TARGET}}
        if path.startswith("/pulls?"):
            return []
        raise AssertionError(path)

    def transition_for(self, **inputs):
        from tools.release.evidence_pr import EvidencePullRequest
        from tools.release.evidence_pr_transition import EvidencePrTransition

        self.factory_inputs.append(deepcopy(inputs))
        spec = {"operation_id": inputs["operation_id"],
                "request_sha256": inputs["request_sha256"],
                "repository_id": 12, "actor_id": 34, "base_revision": TARGET,
                "head_sha": "7" * 40, "tree_sha": "8" * 40,
                "tag": inputs["tag"],
                "target_revision": inputs["target_revision"],
                "task_evidence_sha256": "9" * 64}
        controller = EvidencePullRequest(self.root / "evidence-pr", api=self.api,
                                         authorize=lambda _spec: None,
                                         review=lambda *a: None,
                                         verify_merged=lambda *a: None)
        return EvidencePrTransition(controller, spec)

    def step(self, **overrides):
        from tools.release.carriers import enroll_published_record

        arguments = dict(root=self.root, candidate_root=self.root,
                         repository_id=12, ledger=Ledger(),
                         release_by_tag=lambda _tag: self.release,
                         transition_for=self.transition_for)
        arguments.update(overrides)
        return enroll_published_record(**arguments)

    def operation(self):
        from tools.release.model import canonical_sha256

        digest = canonical_sha256(request())
        return {"step": "published_record",
                "operation_id": canonical_sha256({"request": digest,
                                                  "step": "published_record"}),
                "status": "intent", "evidence": None}

    def record_state(self):
        from tools.release.model import canonical_sha256

        document = request()
        return state(request=document,
                     request_digest=canonical_sha256(document))

    def test_the_step_drives_its_own_write(self):
        # The evidence commit and the reviewed PR leg are this step's write;
        # the wrapper exposes the driver-guarded advance for it.
        self.assertTrue(callable(getattr(self.step(), "advance", None)))

    def test_pending_at_each_underivable_stage(self):
        step = self.step()
        # New mode before any allocation: no Build to record.
        new_mode = state(request=request(mode="new", requested_tag=None))
        self.assertEqual(step.observe(new_mode, self.operation()).status, "pending")
        # Tag mode with the row but no prepared plan.
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")
        # Plan prepared but nothing is published under the tag.
        self.write_plan()
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")
        # Published run not complete: the Release is still a draft.
        self.release = {"draft": True, "id": 4096}
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")
        self.assertEqual(self.factory_inputs, [])

    def test_an_unreadable_or_idless_release_fails_closed(self):
        self.write_plan()
        step = self.step()
        for release in ("not-a-projection", {"draft": False},
                        {"draft": False, "id": "4096"}):
            self.release = release
            with self.assertRaises(JournalError):
                step.observe(state(), self.operation())
        self.assertEqual(self.factory_inputs, [])

    def test_a_pending_step_writes_nothing_when_asked_to_advance(self):
        written = []
        step = self.step()
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")
        step.advance(state(), self.operation(),
                     before_write=lambda: written.append(True))
        self.assertEqual(written, [])
        self.assertEqual(self.factory_inputs, [])

    def test_non_callable_readers_are_refused_at_enrollment(self):
        with self.assertRaises(JournalError):
            self.step(release_by_tag=None)
        with self.assertRaises(JournalError):
            self.step(transition_for=None)

    def test_a_wrong_adapter_type_is_refused(self):
        self.write_plan()
        self.release = {"draft": False, "id": 4096}
        step = self.step(transition_for=lambda **inputs: object())
        with self.assertRaises(JournalError):
            step.observe(state(), self.operation())

    def test_delegation_builds_the_real_evidence_transition(self):
        from tools.release.model import canonical_sha256

        plan = self.write_plan()
        self.release = {"draft": False, "id": 4096}
        step = self.step()
        # The real EvidencePrTransition over the real EvidencePullRequest:
        # the durable child enrolls read-only and the far side shows no PR.
        observed = step.observe(self.record_state(), self.operation())
        self.assertEqual(observed.status, "absent")
        self.assertEqual(len(self.factory_inputs), 1)
        inputs = self.factory_inputs[0]
        digest = canonical_sha256(request())
        self.assertEqual(inputs, {
            "tag": "lmdj-v" + BUILD, "target_revision": TARGET,
            "repository_id": 12, "actor_id": 34, "request_sha256": digest,
            "operation_id": canonical_sha256({"request": digest,
                                              "step": "published_record"}),
            "release_id": 4096, "plan_sha256": plan})
        enrolled = json.loads(
            (self.root / "evidence-pr" / "pr-state.json").read_text())
        self.assertEqual(enrolled["spec"]["tag"], "lmdj-v" + BUILD)


class VerificationEnrollmentTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        # The verification carrier's own fixture environment: real batch
        # journal module, recording consumer of the production type.
        import release_verification_carrier_test as verification_fixture

        self.fixture = verification_fixture.BatchVerificationTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.witness = verification_fixture.WITNESS

    def write_witness(self):
        (self.root / "candidate-transition.json").write_text(json.dumps(
            candidate_document(
                witness_merge={"merge": {"merge_sha": self.witness}})))

    def step(self, **overrides):
        arguments = dict(candidate_root=self.root,
                         journal_load=self.fixture.journal.load,
                         consumer=self.fixture.consumer,
                         fresh_receipts=lambda _state: dict(
                             witness_revision=self.witness))
        arguments.update(overrides)
        return enroll_verification(**arguments)

    def operation(self):
        return {"step": "verification", "operation_id": DIGEST,
                "status": "intent", "evidence": None}

    def test_the_step_is_observe_only(self):
        # The batch is produced by main's own CI when the witness merge lands,
        # never by this step; nothing here may look self-driving.
        self.assertFalse(callable(getattr(self.step(), "advance", None)))

    def test_pending_until_the_witness_merge_is_verified(self):
        step = self.step()
        new_mode = state(request=request(mode="new", requested_tag=None))
        self.assertEqual(step.observe(new_mode, self.operation()).status, "pending")
        # The cut is merged but its witness merge is not verified yet.
        (self.root / "candidate-transition.json").write_text(
            json.dumps(candidate_document()))
        self.assertEqual(step.observe(new_mode, self.operation()).status, "pending")
        # A tag-mode request has no candidate state; the step waits, matching
        # the managed candidate transition's own tag-mode refusal.
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")

    def test_an_invalid_request_digest_fails_closed(self):
        self.write_witness()
        with self.assertRaises(JournalError):
            self.step().observe(state(request_digest="short"), self.operation())

    def test_non_callable_or_wrong_type_dependencies_are_refused(self):
        from tools.release.verification import VerificationError

        with self.assertRaises(JournalError):
            self.step(journal_load=None)
        with self.assertRaises(JournalError):
            self.step(fresh_receipts=None)
        self.write_witness()
        with self.assertRaises(VerificationError):
            self.step(consumer=object()).observe(state(), self.operation())

    def test_delegation_to_the_real_batch_verification(self):
        self.write_witness()
        step = self.step()
        # No batch result yet: the real carrier's honest pending.
        self.assertEqual(step.observe(state(), self.operation()).status, "pending")
        self.assertIsNone(self.fixture.consumer.verified)
        # The terminal full-batch result for the exact witness verifies, and
        # the evidence is the reference the intent step later recovers.
        self.fixture.journal.append(self.fixture.result_event())
        observed = step.observe(state(), self.operation())
        self.assertEqual(observed.status, "verified")
        self.assertEqual(observed.evidence["reference"],
                         f"batch-result:4242:{self.witness}")
        self.assertEqual(self.fixture.consumer.verified, (4242, self.witness))
        # The candidate state read is request-bound: another request's
        # allocation cannot stand in for this one.
        (self.root / "candidate-transition.json").write_text(json.dumps(
            candidate_document(digest="9" * 64,
                               witness_merge={"merge": {"merge_sha": self.witness}})))
        with self.assertRaises(JournalError):
            step.observe(state(), self.operation())


if __name__ == "__main__":
    unittest.main()
