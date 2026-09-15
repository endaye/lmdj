#!/usr/bin/env python3
"""The tag step's remote/local identity comparison and carrier mapping."""
from dataclasses import dataclass
import unittest

ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
__import__("sys").path.insert(0, str(ROOT))
from tools.release.orchestration_driver import Observation  # noqa: E402
from tools.release.tag_step import (  # noqa: E402
    TagCarrier,
    TagStepError,
    read_back,
    tag_operation_id,
    validate_spec,
)

REQUEST = "4" * 64
TARGET = "6" * 40
TAG_OBJECT = "7" * 40
PLAN = "9" * 64
SIGNER = "2B5EE362F058800036AD4FB5116ECE156F954D29"


def spec(**changes):
    document = {"operation_id": tag_operation_id(REQUEST), "request_sha256": REQUEST,
                "repository_id": 12, "actor_id": 34, "tag": "lmdj-v1.0.57.0",
                "target_revision": TARGET, "plan_sha256": PLAN, "tag_object_id": TAG_OBJECT}
    document.update(changes)
    return document


@dataclass(frozen=True)
class FakeTag:
    object_id: str
    target_revision: str
    signer_fingerprint: str


LOCAL = FakeTag(TAG_OBJECT, TARGET, SIGNER)


class ReadBackTest(unittest.TestCase):
    def test_pending_until_the_remote_tag_exists(self):
        self.assertEqual(read_back(LOCAL, None, spec()), "pending")

    def test_verified_binds_local_and_remote_identity(self):
        evidence = read_back(LOCAL, FakeTag(TAG_OBJECT, TARGET, SIGNER), spec())
        self.assertEqual(evidence["status"], "verified")
        self.assertEqual(evidence["evidence"]["reference"], "tag:lmdj-v1.0.57.0")

    def test_drift_fails_closed(self):
        with self.assertRaises(TagStepError):
            read_back(None, None, spec())
        with self.assertRaises(TagStepError):
            read_back(FakeTag("f" * 40, TARGET, SIGNER), None, spec())
        with self.assertRaises(TagStepError):
            read_back(LOCAL, FakeTag("f" * 40, TARGET, SIGNER), spec())
        with self.assertRaises(TagStepError):
            read_back(LOCAL, FakeTag(TAG_OBJECT, "f" * 40, SIGNER), spec())

    def test_spec_is_closed(self):
        validate_spec(spec())
        with self.assertRaises(TagStepError):
            validate_spec(spec(operation_id="0" * 64))
        with self.assertRaises(TagStepError):
            validate_spec(dict(spec(), extra=1))
        with self.assertRaises(TagStepError):
            validate_spec(spec(tag="not-a-tag"))


class CarrierTest(unittest.TestCase):
    def setUp(self):
        self.local = LOCAL
        self.remote = None
        self.pushes = 0
        self.guards = 0

    def push_tag(self, tag):
        self.pushes += 1
        self.remote = FakeTag(TAG_OBJECT, TARGET, SIGNER)

    def carrier(self):
        return TagCarrier(spec=spec(), push_tag=self.push_tag,
                          local_tag_state=lambda: self.local,
                          remote_tag_state=lambda: self.remote)

    def test_advance_pushes_once_under_the_guard_and_never_repeats(self):
        carrier = self.carrier()
        self.assertEqual(carrier.observe({}, {"step": "tag"}).status, "pending")

        def guard():
            self.guards += 1
        advanced = carrier.advance({}, {"step": "tag"}, before_write=guard)
        self.assertEqual(advanced.status, "verified")
        self.assertEqual(advanced.evidence["reference"], "tag:lmdj-v1.0.57.0")
        self.assertEqual(self.pushes, 1)
        again = carrier.advance({}, {"step": "tag"}, before_write=guard)
        self.assertEqual(again.status, "verified")
        self.assertEqual(self.pushes, 1, "verified state never re-pushes")
        self.assertEqual(self.guards, 1, "the write guard fired exactly once")

    def test_push_failure_is_unknown_and_recoverable(self):
        def failing(tag):
            raise RuntimeError("transport down")
        carrier = TagCarrier(spec=spec(), push_tag=failing,
                             local_tag_state=lambda: self.local,
                             remote_tag_state=lambda: self.remote)
        self.assertEqual(carrier.advance({}, {"step": "tag"},
                                         before_write=lambda: None).status, "unknown")
        # The transport reconciles; the next advance verifies without a push.
        self.remote = FakeTag(TAG_OBJECT, TARGET, SIGNER)
        self.assertEqual(carrier.advance({}, {"step": "tag"},
                                         before_write=lambda: None).status, "verified")

    def test_carrier_refuses_an_untrusted_composition(self):
        with self.assertRaises(TagStepError):
            TagCarrier(spec=spec(), push_tag=None,
                       local_tag_state=lambda: LOCAL, remote_tag_state=lambda: None)
        with self.assertRaises(TagStepError):
            TagCarrier(spec=spec(**{"plan_sha256": "short"}), push_tag=lambda t: None,
                       local_tag_state=lambda: LOCAL, remote_tag_state=lambda: None)


if __name__ == "__main__":
    unittest.main()
