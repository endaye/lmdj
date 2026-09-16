#!/usr/bin/env python3
"""The observe-only changelog_site and final carriers verify without writes."""
from dataclasses import dataclass
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.orchestration_driver import Observation  # noqa: E402
from tools.release.final_steps import (  # noqa: E402
    ChangelogSiteCarrier,
    FinalCarrier,
    SiteStepError,
    final_operation_id,
    site_operation_id,
    site_routes,
    validate_final_spec,
    validate_site_spec,
)

REQUEST = "4" * 64
TARGET = "6" * 40
BASE_URL = "https://docs.lmdj.workers.dev"


def site_spec(**changes):
    document = {"operation_id": site_operation_id(REQUEST), "request_sha256": REQUEST,
                "repository_id": 12, "actor_id": 34, "tag": "lmdj-v1.0.57.0",
                "product_build": "1.0.57.0", "target_revision": TARGET,
                "site_base_url": BASE_URL}
    document.update(changes)
    return document


def final_spec(**changes):
    document = {"operation_id": final_operation_id(REQUEST), "request_sha256": REQUEST,
                "repository_id": 12, "actor_id": 34, "tag": "lmdj-v1.0.57.0",
                "product_build": "1.0.57.0", "target_revision": TARGET,
                "site_base_url": BASE_URL, "release_id": 4096, "channel": "dev"}
    document.update(changes)
    return document


@dataclass(frozen=True)
class Row:
    tag: str = "lmdj-v1.0.57.0"
    target_revision: str = TARGET
    channel: str = "dev"
    disposition: str = "published"


class SiteSpecTest(unittest.TestCase):
    def test_specs_are_closed_and_routes_are_derived(self):
        validate_site_spec(site_spec())
        validate_final_spec(final_spec())
        routes = site_routes(site_spec())
        self.assertEqual(routes["version"], BASE_URL + "/versions/1.0.57.0/")
        self.assertEqual(routes["release"], BASE_URL + "/releases/1.0.57.0")
        for bad in (site_spec(operation_id="0" * 64), dict(site_spec(), extra=1),
                    site_spec(site_base_url="http://insecure"),
                    site_spec(tag="lmdj-v1.0.58.0")):
            with self.assertRaises(SiteStepError):
                validate_site_spec(bad)
        with self.assertRaises(SiteStepError):
            validate_final_spec(final_spec(channel="production"))


class ChangelogSiteCarrierTest(unittest.TestCase):
    def test_verified_when_both_routes_serve_200(self):
        carrier = ChangelogSiteCarrier(spec=site_spec(), fetch=lambda url: 200)
        observed = carrier.observe({}, {"step": "changelog_site"})
        self.assertIsInstance(observed, Observation)
        self.assertEqual(observed.status, "verified")

    def test_404_is_absent_partial_404_is_conflict_unreachable_is_unknown(self):
        self.assertEqual(ChangelogSiteCarrier(
            spec=site_spec(), fetch=lambda url: 404 if "versions" in url else 200
        ).observe({}, {}).status, "conflict")
        self.assertEqual(ChangelogSiteCarrier(
            spec=site_spec(), fetch=lambda url: 404
        ).observe({}, {}).status, "absent")
        self.assertEqual(ChangelogSiteCarrier(
            spec=site_spec(), fetch=lambda url: 503
        ).observe({}, {}).status, "unknown")
        # An unreachable site is unknown, never a pass and never absence.
        self.assertEqual(ChangelogSiteCarrier(
            spec=site_spec(),
            fetch=lambda url: (_ for _ in ()).throw(OSError("down"))
        ).observe({}, {}).status, "unknown")
        # A defect in the fetch callable surfaces instead of being coerced.
        with self.assertRaises(SiteStepError):
            ChangelogSiteCarrier(
                spec=site_spec(), fetch=lambda url: "200"
            ).observe({}, {})

    def test_carrier_refuses_an_untrusted_fetch(self):
        with self.assertRaises(SiteStepError):
            ChangelogSiteCarrier(spec=site_spec(), fetch=None)


class FinalCarrierTest(unittest.TestCase):
    def test_verified_binds_every_recorded_identity(self):
        carrier = FinalCarrier(spec=final_spec(), fetch=lambda url: 200,
                               release_by_tag=lambda _tag: {"draft": False, "id": 4096},
                               ledger_row=lambda _tag: Row())
        observed = carrier.observe({}, {"step": "final"})
        self.assertEqual(observed.status, "verified")
        self.assertEqual(observed.evidence["reference"], "final:lmdj-v1.0.57.0")

    def test_absent_only_before_the_whole_far_side_exists(self):
        carrier = FinalCarrier(spec=final_spec(), fetch=lambda url: 200,
                               release_by_tag=lambda _tag: None,
                               ledger_row=lambda _tag: None)
        self.assertEqual(carrier.observe({}, {}).status, "absent")

    def test_drift_fails_closed(self):
        carrier = FinalCarrier(spec=final_spec(), fetch=lambda url: 200,
                               release_by_tag=lambda _tag: {"draft": True},
                               ledger_row=lambda _tag: Row())
        with self.assertRaises(SiteStepError):
            carrier.observe({}, {})
        still_draft = FinalCarrier(
            spec=final_spec(), fetch=lambda url: 200,
            release_by_tag=lambda _tag: {"draft": False},
            ledger_row=lambda _tag: Row(disposition="releasable"))
        with self.assertRaises(SiteStepError):
            still_draft.observe({}, {})
        wrong_tag = FinalCarrier(
            spec=final_spec(), fetch=lambda url: 200,
            release_by_tag=lambda _tag: {"draft": False, "id": 4096},
            ledger_row=lambda _tag: Row(tag="lmdj-v1.0.58.0"))
        with self.assertRaises(SiteStepError):
            wrong_tag.observe({}, {})
        wrong_id = FinalCarrier(
            spec=final_spec(), fetch=lambda url: 200,
            release_by_tag=lambda _tag: {"draft": False, "id": 1234},
            ledger_row=lambda _tag: Row())
        with self.assertRaises(SiteStepError):
            wrong_id.observe({}, {})
        missing_id = FinalCarrier(
            spec=final_spec(), fetch=lambda url: 200,
            release_by_tag=lambda _tag: {"draft": False},
            ledger_row=lambda _tag: Row())
        with self.assertRaises(SiteStepError):
            missing_id.observe({}, {})

    def test_missing_routes_after_publish_are_a_conflict_not_absent(self):
        carrier = FinalCarrier(spec=final_spec(),
                               fetch=lambda url: 404,
                               release_by_tag=lambda _tag: {"draft": False, "id": 4096},
                               ledger_row=lambda _tag: Row())
        self.assertEqual(carrier.observe({}, {}).status, "conflict")

    def test_readers_receive_the_frozen_spec_identity(self):
        seen = []
        carrier = FinalCarrier(
            spec=final_spec(), fetch=lambda url: 200,
            release_by_tag=lambda tag: (seen.append(("release", tag))
                                        or {"draft": False, "id": 4096}),
            ledger_row=lambda tag: (seen.append(("row", tag)) or Row()))
        carrier.observe({}, {})
        self.assertEqual(seen, [("release", "lmdj-v1.0.57.0"),
                                ("row", "lmdj-v1.0.57.0")])

    def test_partially_applied_promotion_is_a_conflict(self):
        release_only = FinalCarrier(
            spec=final_spec(), fetch=lambda url: 200,
            release_by_tag=lambda _tag: {"draft": False, "id": 4096},
            ledger_row=lambda _tag: None)
        self.assertEqual(release_only.observe({}, {}).status, "conflict")
        row_only = FinalCarrier(
            spec=final_spec(), fetch=lambda url: 200,
            release_by_tag=lambda _tag: None, ledger_row=lambda _tag: Row())
        self.assertEqual(row_only.observe({}, {}).status, "conflict")
        neither = FinalCarrier(
            spec=final_spec(), fetch=lambda url: 200,
            release_by_tag=lambda _tag: None, ledger_row=lambda _tag: None)
        self.assertEqual(neither.observe({}, {}).status, "absent")

    def test_a_str_subclass_cannot_smuggle_the_target_revision(self):
        class Sneaky(str):
            pass

        spec = final_spec()
        spec["target_revision"] = Sneaky(spec["target_revision"])
        with self.assertRaises(SiteStepError):
            validate_final_spec(spec)

    def test_site_failure_is_unknown_never_a_pass(self):
        carrier = FinalCarrier(spec=final_spec(), fetch=lambda url: 503,
                               release_by_tag=lambda _tag: {"draft": False, "id": 4096},
                               ledger_row=lambda _tag: Row())
        self.assertEqual(carrier.observe({}, {}).status, "unknown")

    def test_carrier_refuses_an_untrusted_composition(self):
        with self.assertRaises(SiteStepError):
            FinalCarrier(spec=final_spec(), fetch=None,
                         release_by_tag=lambda _tag: None, ledger_row=lambda _tag: None)


if __name__ == "__main__":
    unittest.main()
