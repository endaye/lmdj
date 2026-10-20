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


def github_release(body, *, draft=True, tag="lmdj-v1.0.57.0"):
    from tools.release.github_api import GitHubRelease
    return GitHubRelease(id=RELEASE_ID, tag_name=tag, name="LMDJ", body=body, draft=draft,
                         prerelease=False, make_latest=None, html_url="", upload_url="",
                         assets=(), target_commitish="main")


def marker(plan=PLAN, schema="lmdj.release-plan-marker.v4"):
    return f'<!-- {schema} {{"plan_sha256":"{plan}","tag":"lmdj-v1.0.57.0"}} -->'


class ReleaseProjectionTest(unittest.TestCase):
    """The production reader projects a real GitHubRelease for read_back."""

    def test_a_draft_with_its_plan_marker_verifies(self):
        from tools.release.draft_step import release_projection
        projected = release_projection(github_release("Notes.\n\n" + marker()))
        self.assertEqual(read_back(projected, spec())["status"], "verified")

    def test_no_release_is_pending(self):
        from tools.release.draft_step import release_projection
        self.assertEqual(read_back(release_projection(None), spec()), "pending")

    def test_a_body_without_exactly_one_marker_fails_closed(self):
        from tools.release.draft_step import release_projection
        for body in ("Notes only.", marker() + "\n" + marker(), marker(plan="short")):
            with self.assertRaises(DraftStepError, msg=body):
                read_back(release_projection(github_release(body)), spec())


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
        self.assets_complete = True
        self.verified_ids = []

    def verify_assets(self, release_id):
        self.verified_ids.append(release_id)
        if not self.assets_complete:
            raise RuntimeError("GitHub Release asset upload is incomplete")

    def create_draft(self, tag):
        self.creations += 1
        self.release = DRAFT

    def release_by_tag(self):
        return self.release

    def carrier(self):
        return DraftCarrier(spec=spec(), create_draft=self.create_draft,
                            release_by_tag=self.release_by_tag,
                            verify_assets=self.verify_assets)

    def test_observe_reports_the_verified_status_with_its_evidence(self):
        # read_back returns a status with its evidence; observe must unpack it
        # rather than hand the driver a malformed observation or a bare status.
        self.release = DRAFT
        observed = self.carrier().observe({}, {"step": "draft"})
        self.assertEqual(observed.status, "verified")
        self.assertEqual(observed.evidence["reference"], f"draft:{RELEASE_ID}")
        observed.validate()

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
                               release_by_tag=lambda: self.release,
                               verify_assets=self.verify_assets)
        self.assertEqual(carrier.advance({}, {"step": "draft"},
                                         before_write=lambda: None).status, "unknown")
        # The uncertain POST reconciled far-side; the next advance verifies
        # without another creation.
        self.release = DRAFT
        self.creations = 0
        advanced = carrier.advance({}, {"step": "draft"}, before_write=lambda: None)
        self.assertEqual(advanced.status, "verified")
        self.assertEqual(self.creations, 0, "recovery never re-creates")

    def test_deterministic_transition_error_surfaces(self):
        from tools.release.transitions import TransitionError
        def refusing(tag):
            raise TransitionError("published release intent cannot authorize a new Draft")
        carrier = DraftCarrier(spec=spec(), create_draft=refusing,
                               release_by_tag=lambda: None,
                               verify_assets=self.verify_assets)
        with self.assertRaises(TransitionError):
            carrier.advance({}, {"step": "draft"}, before_write=lambda: None)

    def test_a_draft_with_incomplete_assets_is_pending_work_not_verified(self):
        # 2.0.122.0's Draft passed on its metadata while one asset was a stalled
        # `starter` upload; publish-release.yml then failed at Reverify.
        self.release = DRAFT
        self.assets_complete = False
        carrier = self.carrier()
        self.assertEqual(carrier.observe({}, {"step": "draft"}).status, "pending")
        self.assertEqual(self.verified_ids, [RELEASE_ID])

        def repair(tag):
            self.creations += 1
            self.assets_complete = True
        carrier.create_draft = repair
        advanced = carrier.advance({}, {"step": "draft"}, before_write=lambda: None)
        self.assertEqual(advanced.status, "verified")
        self.assertEqual(self.creations, 1, "advance resumes create_draft to repair the assets")

    def test_a_divergent_draft_surfaces_create_drafts_named_refusal(self):
        # Pending is never a silent wait: advance runs create_draft, whose
        # deterministic refusal for a divergent asset reaches the driver.
        from tools.release.transitions import TransitionError
        self.release = DRAFT
        self.assets_complete = False

        def refusing(tag):
            raise TransitionError("GitHub Release asset digest conflicts with the release plan")
        carrier = DraftCarrier(spec=spec(), create_draft=refusing,
                               release_by_tag=self.release_by_tag,
                               verify_assets=self.verify_assets)
        self.assertEqual(carrier.observe({}, {"step": "draft"}).status, "pending")
        with self.assertRaisesRegex(TransitionError, "digest conflicts"):
            carrier.advance({}, {"step": "draft"}, before_write=lambda: None)

    def test_an_unavailable_asset_read_is_unknown_and_never_repairs(self):
        from tools.release.transitions import ReleaseReadUnavailable
        self.release = DRAFT

        def unavailable(release_id):
            raise ReleaseReadUnavailable("GitHub Release asset download is unavailable")
        carrier = DraftCarrier(spec=spec(), create_draft=self.create_draft,
                               release_by_tag=self.release_by_tag, verify_assets=unavailable)
        self.assertEqual(carrier.observe({}, {"step": "draft"}).status, "unknown")
        self.assertEqual(carrier.advance({}, {"step": "draft"}, before_write=lambda: None).status,
                         "unknown")
        self.assertEqual(self.creations, 0, "an outage never triggers create_draft")

    def test_carrier_refuses_an_untrusted_composition(self):
        with self.assertRaises(DraftStepError):
            DraftCarrier(spec=spec(), create_draft=None,
                         release_by_tag=lambda: None, verify_assets=lambda i: None)
        with self.assertRaises(DraftStepError):
            DraftCarrier(spec=spec(), create_draft=lambda t: None,
                         release_by_tag=lambda: None, verify_assets=None)
        with self.assertRaises(DraftStepError):
            DraftCarrier(spec=spec(**{"plan_sha256": "short"}), create_draft=lambda t: None,
                         release_by_tag=lambda: None, verify_assets=lambda i: None)


if __name__ == "__main__":
    unittest.main()
