#!/usr/bin/env python3
"""The prepared step's read-back verifier and carrier mapping are exact."""
from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.orchestration_driver import Observation  # noqa: E402
from tools.release.prepared_step import (  # noqa: E402
    PreparedCarrier,
    PreparedStepError,
    output_relative,
    prepared_operation_id,
    read_back,
    validate_spec,
)

REQUEST = "4" * 64
TARGET = "6" * 40
TAG_OBJECT = "7" * 40
PLAN_BODY = b'{"plan":true}\n'
import hashlib
PLAN = hashlib.sha256(PLAN_BODY).hexdigest()
SIGNER = "2B5EE362F058800036AD4FB5116ECE156F954D29"


def spec(**changes):
    document = {"operation_id": prepared_operation_id(REQUEST), "request_sha256": REQUEST,
                "repository_id": 12, "actor_id": 34, "tag": "lmdj-v1.0.57.0",
                "target_revision": TARGET, "plan_sha256": PLAN, "tag_object_id": TAG_OBJECT}
    document.update(changes)
    return document


@dataclass(frozen=True)
class FakeTag:
    object_id: str
    target_revision: str
    signer_fingerprint: str


class ReadBackTest(unittest.TestCase):
    def setUp(self):
        self.container = tempfile.TemporaryDirectory()
        self.addCleanup(self.container.cleanup)
        self.root = Path(self.container.name).resolve()
        self.output = self.root / output_relative("lmdj-v1.0.57.0")
        self.output.mkdir(parents=True)

    def write_plan(self, digest=PLAN):
        (self.output / "release-plan.json").write_bytes(PLAN_BODY)
        (self.output / "release-plan.sha256").write_text(digest + "\n", encoding="ascii")

    def test_absent_without_output_and_pending_without_tag(self):
        fresh = self.root / "elsewhere"
        self.assertEqual(read_back(fresh, spec(), tag_state=None,
                                   signer_fingerprint=SIGNER), "absent")
        self.write_plan()
        self.assertEqual(read_back(self.root, spec(), tag_state=None,
                                   signer_fingerprint=SIGNER), "pending")

    def test_verified_binds_document_digest_and_tag_identity(self):
        self.write_plan()
        evidence = read_back(self.root, spec(), tag_state=FakeTag(
            TAG_OBJECT, TARGET, SIGNER), signer_fingerprint=SIGNER)
        self.assertEqual(evidence["status"], "verified")
        self.assertEqual(evidence["evidence"]["reference"], "prepared:lmdj-v1.0.57.0")
        again = read_back(self.root, spec(), tag_state=FakeTag(
            TAG_OBJECT, TARGET, SIGNER), signer_fingerprint=SIGNER)
        self.assertEqual(again, evidence)

    def test_drift_fails_closed(self):
        self.write_plan(digest="8" * 64)
        with self.assertRaises(PreparedStepError):
            read_back(self.root, spec(), tag_state=None, signer_fingerprint=SIGNER)
        self.write_plan()
        drifted_tag = FakeTag("f" * 40, TARGET, SIGNER)
        with self.assertRaises(PreparedStepError):
            read_back(self.root, spec(), tag_state=drifted_tag, signer_fingerprint=SIGNER)
        wrong_signer = FakeTag(TAG_OBJECT, TARGET, "0" * 40)
        with self.assertRaises(PreparedStepError):
            read_back(self.root, spec(), tag_state=wrong_signer, signer_fingerprint=SIGNER)

    def test_spec_is_closed(self):
        validate_spec(spec())
        with self.assertRaises(PreparedStepError):
            validate_spec(spec(operation_id="0" * 64))
        with self.assertRaises(PreparedStepError):
            validate_spec(dict(spec(), extra=1))
        with self.assertRaises(PreparedStepError):
            validate_spec(spec(tag="lmdj-v1.0.58"))


class CarrierTest(unittest.TestCase):
    def setUp(self):
        self.container = tempfile.TemporaryDirectory()
        self.addCleanup(self.container.cleanup)
        self.root = Path(self.container.name).resolve()
        self.output = self.root / output_relative("lmdj-v1.0.57.0")
        self.prepared = 0
        self.tag = None
        self.guards = 0

    def prepare(self, tag):
        self.prepared += 1
        self.output.mkdir(parents=True)
        (self.output / "release-plan.json").write_bytes(PLAN_BODY)
        (self.output / "release-plan.sha256").write_text(PLAN + "\n", encoding="ascii")
        self.tag = FakeTag(TAG_OBJECT, TARGET, SIGNER)

    def tag_state(self):
        return self.tag

    def carrier(self):
        return PreparedCarrier(root=self.root, spec=spec(), prepare=self.prepare,
                               tag_state=self.tag_state, signer_fingerprint=SIGNER)

    def test_advance_runs_prepare_once_under_the_guard_and_recovers(self):
        carrier = self.carrier()
        self.assertEqual(carrier.observe({}, {"step": "prepared"}).status, "absent")

        def guard():
            self.guards += 1
        advanced = carrier.advance({}, {"step": "prepared"}, before_write=guard)
        self.assertEqual(advanced.status, "verified")
        self.assertEqual(advanced.evidence["reference"], "prepared:lmdj-v1.0.57.0")
        self.assertEqual(self.prepared, 1)
        again = carrier.advance({}, {"step": "prepared"}, before_write=guard)
        self.assertEqual(again.status, "verified")
        self.assertEqual(self.prepared, 1, "verified state never re-runs prepare")
        self.assertEqual(self.guards, 1, "the write guard fired exactly once")

    def test_unreadable_present_output_fails_closed_without_rerunning_prepare(self):
        self.output.mkdir(parents=True)
        (self.output / "release-plan.json").mkdir()  # a directory at the document path
        carrier = self.carrier()
        with self.assertRaises(PreparedStepError):
            carrier.observe({}, {"step": "prepared"})
        self.assertEqual(self.prepared, 0, "unreadable state must not trigger prepare")

    def test_prepare_failure_is_unknown_not_absent(self):
        def failing(tag):
            raise RuntimeError("toolchain unavailable")
        carrier = PreparedCarrier(root=self.root, spec=spec(), prepare=failing,
                                  tag_state=lambda: None, signer_fingerprint=SIGNER)
        self.assertEqual(carrier.advance({}, {"step": "prepared"},
                                         before_write=lambda: None).status, "unknown")

    def test_carrier_refuses_an_untrusted_composition(self):
        with self.assertRaises(PreparedStepError):
            PreparedCarrier(root=self.root, spec=spec(), prepare=None,
                            tag_state=lambda: None, signer_fingerprint=SIGNER)
        with self.assertRaises(PreparedStepError):
            PreparedCarrier(root=self.root, spec=spec(), prepare=self.prepare,
                            tag_state=lambda: None, signer_fingerprint="")
        with self.assertRaises(PreparedStepError):
            PreparedCarrier(root=self.root, spec=spec(**{"plan_sha256": "short"}),
                            prepare=self.prepare, tag_state=lambda: None,
                            signer_fingerprint=SIGNER)


if __name__ == "__main__":
    unittest.main()
