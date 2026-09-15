#!/usr/bin/env python3
"""The draft step's far-side read-back and carrier mapping."""
from dataclasses import dataclass
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.orchestration_driver import Observation  # noqa: E402
from tools.release.draft_step import (  # noqa: E402
    DraftCarrier,
    DraftStepError,
    draft_operation_id,
    read_back,
    validate_spec,
)

REQUEST = "4" * 64
TARGET = "6" * 40
PLAN = "9" * 64
RELEASE_ID = 4096


def spec(**changes):
    document = {"operation_id": draft_operation_id(REQUEST), "request_sha256": REQUEST,
                "repository_id": 12, "actor_id": 34, "tag": "lmdj-v1.0.57.0",
                "target_revision": TARGET, "plan_sha256": PLAN}
    document.update(changes)
    return document


@dataclass(frozen=True)
class FakeRelease:
    id: int
    draft: bool
    tag: str
    plan_sha256: str


DRAFT = FakeRelease(RELEASE_ID, True, "lmdj-v1.0.57.0", PLAN)


class ReadBackTest(unittest.TestCase):
    def test_pending_while_no_release_exists(self):
        self.assertEqual(read_back(None, spec()), "pending")

    def test_verified_binds_draft_to_the_prepared_plan(self):
        evidence = read_back(DRAFT, spec())
        self.assertEqual(evidence["status"], "verified")
        self.assertEqual(evidence["evidence"]["reference"], f"draft:{RELEASE_ID}")

    def test_published_is_its_own_status_not_verified(self):
        published = FakeRelease(RELEASE_ID, False, "lmdj-v1.0.57.0", PLAN)
        result = read_back(published, spec())
        self.assertEqual(result["status"], "published")
        self.assertEqual(result["evidence"]["reference"], f"draft:{RELEASE_ID}")

    def test_drift_fails_closed(self):
        with self.assertRaises(DraftStepError):
            read_back(FakeRelease(RELEASE_ID, True, "lmdj-v1.0.58.0", PLAN), spec())
        with self.assertRaises(DraftStepError):
            read_back(FakeRelease(RELEASE_ID, True, "lmdj-v1.0.57.0", "8" * 64), spec())

    def test_spec_is_closed(self):
        validate_spec(spec())
        with self.assertRaises(DraftStepError):
            validate_spec(spec(operation_id="0" * 64))
        with self.assertRaises(DraftStepError):
            validate_spec(dict(spec(), extra=1))
        with self.assertRaises(DraftStepError):
            validate_spec(spec(tag="not-a-tag"))


class CarrierTest(unittest.TestCase):
    def setUp(self):
        self.release = None
        self.creations = 0
        self.guards = 0

    def create_draft(self, tag):
        self.creations += 1
        self.release = DRAFT

    def release_by_tag(self):
        return self.release

    def carrier(self):
        return DraftCarrier(spec=spec(), create_draft=self.create_draft,
                            release_by_tag=self.release_by_tag)

    def test_advance_creates_once_under_the_guard_and_never_repeats(self):
        carrier = self.carrier()
        self.assertEqual(carrier.observe({}, {"step": "draft"}).status, "pending")

        def guard():
            self.guards += 1
        advanced = carrier.advance({}, {"step": "draft"}, before_write=guard)
        self.assertEqual(advanced.status, "verified")
        self.assertEqual(advanced.evidence["reference"], f"draft:{RELEASE_ID}")
        self.assertEqual(self.creations, 1)
        again = carrier.advance({}, {"step": "draft"}, before_write=guard)
        self.assertEqual(again.status, "verified")
        self.assertEqual(self.creations, 1, "verified state never re-creates")
        self.assertEqual(self.guards, 1, "the write guard fired exactly once")

    def test_creation_failure_is_unknown_and_recoverable(self):
        def failing(tag):
            raise RuntimeError("github unavailable")
        carrier = DraftCarrier(spec=spec(), create_draft=failing,
                               release_by_tag=lambda: self.release)
        self.assertEqual(carrier.advance({}, {"step": "draft"},
                                         before_write=lambda: None).status, "unknown")
        # The uncertain POST reconciled far-side; the next advance verifies
        # without another creation.
        self.release = DRAFT
        self.creations = 0
        advanced = carrier.advance({}, {"step": "draft"}, before_write=lambda: None)
        self.assertEqual(advanced.status, "verified")
        self.assertEqual(self.creations, 0, "recovery never re-creates")

    def test_carrier_refuses_an_untrusted_composition(self):
        with self.assertRaises(DraftStepError):
            DraftCarrier(spec=spec(), create_draft=None,
                         release_by_tag=lambda: None)
        with self.assertRaises(DraftStepError):
            DraftCarrier(spec=spec(**{"plan_sha256": "short"}), create_draft=lambda t: None,
                         release_by_tag=lambda: None)


if __name__ == "__main__":
    unittest.main()
