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
BUILD = "1.0.57.0"
BASE_URL = "https://docs.lmdj.workers.dev"


def page(**changes):
    """A deployed page that names this Build, as the site smoke lane requires."""
    build = changes.pop("product_build", BUILD)
    return f"<html><body>Product Build {build}</body></html>"


def site_spec(**changes):
    document = {"operation_id": site_operation_id(REQUEST), "request_sha256": REQUEST,
                "repository_id": 12, "actor_id": 34, "tag": "lmdj-v" + BUILD,
                "product_build": BUILD, "target_revision": TARGET,
                "site_base_url": BASE_URL}
    document.update(changes)
    return document


def final_spec(**changes):
    document = {"operation_id": final_operation_id(REQUEST), "request_sha256": REQUEST,
                "repository_id": 12, "actor_id": 34, "tag": "lmdj-v" + BUILD,
                "product_build": BUILD, "target_revision": TARGET,
                "site_base_url": BASE_URL, "release_id": 4096, "channel": "dev"}
    document.update(changes)
    return document


def served(**changes):
    """A fetch that proves the Build; changes override the (status, body)."""
    answer = changes.get("answer", (200, page()))
    return lambda url: answer


@dataclass(frozen=True)
class Row:
    tag: str = "lmdj-v" + BUILD
    target_revision: str = TARGET
    channel: str = "dev"
    disposition: str = "published"


RELEASE = {"draft": False, "id": 4096}


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
        for bad_channel in ("production", "stable"):
            with self.assertRaises(SiteStepError):
                validate_final_spec(final_spec(channel=bad_channel))


class ChangelogSiteCarrierTest(unittest.TestCase):
    def test_verified_when_both_routes_serve_this_build(self):
        carrier = ChangelogSiteCarrier(spec=site_spec(), fetch=served())
        observed = carrier.observe({}, {"step": "changelog_site"})
        self.assertIsInstance(observed, Observation)
        self.assertEqual(observed.status, "verified")

    def test_200_without_the_build_identity_is_a_conflict(self):
        carrier = ChangelogSiteCarrier(
            spec=site_spec(), fetch=served(answer=(200, "<html>catch-all</html>")))
        self.assertEqual(carrier.observe({}, {}).status, "conflict")
        other = ChangelogSiteCarrier(
            spec=site_spec(),
            fetch=served(answer=(200, page(product_build="1.0.58.0"))))
        self.assertEqual(other.observe({}, {}).status, "conflict")

    def test_the_body_digest_is_bound_into_the_evidence(self):
        first = ChangelogSiteCarrier(
            spec=site_spec(), fetch=served(answer=(200, page())))
        second = ChangelogSiteCarrier(
            spec=site_spec(),
            fetch=served(answer=(200, page() + "<!-- rebuilt -->")))
        self.assertNotEqual(first.observe({}, {}).evidence["sha256"],
                            second.observe({}, {}).evidence["sha256"])

    def test_404_is_absent_partial_404_is_conflict_unreachable_is_unknown(self):
        self.assertEqual(ChangelogSiteCarrier(
            spec=site_spec(),
            fetch=lambda url: (404, "") if "versions" in url else (200, page())
        ).observe({}, {}).status, "conflict")
        self.assertEqual(ChangelogSiteCarrier(
            spec=site_spec(), fetch=served(answer=(404, ""))
        ).observe({}, {}).status, "absent")
        self.assertEqual(ChangelogSiteCarrier(
            spec=site_spec(), fetch=served(answer=(503, ""))
        ).observe({}, {}).status, "unknown")
        # An unreachable site is unknown, never a pass and never absence.
        self.assertEqual(ChangelogSiteCarrier(
            spec=site_spec(),
            fetch=lambda url: (_ for _ in ()).throw(OSError("down"))
        ).observe({}, {}).status, "unknown")

    def test_a_fetch_defect_surfaces_instead_of_being_coerced(self):
        for answer in (200, (200,), (200, b"bytes"), ("200", page()),
                       (200, page(), "extra")):
            with self.assertRaises(SiteStepError):
                ChangelogSiteCarrier(
                    spec=site_spec(), fetch=served(answer=answer)).observe({}, {})

    def test_carrier_refuses_an_untrusted_fetch(self):
        with self.assertRaises(SiteStepError):
            ChangelogSiteCarrier(spec=site_spec(), fetch=None)


class FinalCarrierTest(unittest.TestCase):
    def carrier(self, spec: dict | None = None, fetch=None,
                release: object = RELEASE, row: object = Row()):
        return FinalCarrier(
            spec=spec or final_spec(),
            fetch=fetch or served(),
            release_by_tag=lambda _tag: release,
            ledger_row=lambda _tag: row)

    def test_verified_binds_every_recorded_identity(self):
        observed = self.carrier().observe({}, {"step": "final"})
        self.assertEqual(observed.status, "verified")
        self.assertEqual(observed.evidence["reference"], "final:" + "lmdj-v" + BUILD)

    def test_empty_far_side_is_absent(self):
        self.assertEqual(self.carrier(release=None, row=None)
                         .observe({}, {}).status, "absent")

    def test_drift_fails_closed(self):
        with self.assertRaises(SiteStepError):
            self.carrier(release={"draft": True}).observe({}, {})
        with self.assertRaises(SiteStepError):
            self.carrier(row=Row(disposition="releasable")).observe({}, {})
        with self.assertRaises(SiteStepError):
            self.carrier(row=Row(tag="lmdj-v1.0.58.0")).observe({}, {})
        with self.assertRaises(SiteStepError):
            self.carrier(release={"draft": False, "id": 1234}).observe({}, {})
        with self.assertRaises(SiteStepError):
            self.carrier(release={"draft": False}).observe({}, {})
        with self.assertRaises(SiteStepError):
            self.carrier(release="not-a-projection").observe({}, {})

    def test_a_row_missing_a_compared_field_is_malformed(self):
        with self.assertRaises(SiteStepError) as raised:
            self.carrier(row={"tag": "lmdj-v" + BUILD,
                              "target_revision": TARGET}).observe({}, {})
        self.assertIn("omits", str(raised.exception))

    def test_missing_or_foreign_routes_are_a_conflict_not_absent(self):
        self.assertEqual(self.carrier(fetch=served(answer=(404, "")))
                         .observe({}, {}).status, "conflict")
        # 200 but another Build's page — a catch-all also answers 200.
        self.assertEqual(self.carrier(
            fetch=served(answer=(200, page(product_build="1.0.58.0"))))
            .observe({}, {}).status, "conflict")

    def test_readers_receive_the_frozen_spec_identity(self):
        seen = []
        carrier = FinalCarrier(
            spec=final_spec(), fetch=served(),
            release_by_tag=lambda tag: (seen.append(("release", tag)) or RELEASE),
            ledger_row=lambda tag: (seen.append(("row", tag)) or Row()))
        carrier.observe({}, {})
        self.assertEqual(seen, [("release", "lmdj-v" + BUILD),
                                ("row", "lmdj-v" + BUILD)])

    def test_partially_applied_promotion_is_a_conflict(self):
        self.assertEqual(self.carrier(release=RELEASE, row=None)
                         .observe({}, {}).status, "conflict")
        self.assertEqual(self.carrier(release=None, row=Row())
                         .observe({}, {}).status, "conflict")

    def test_a_str_subclass_cannot_smuggle_the_target_revision(self):
        class Sneaky(str):
            pass

        spec = final_spec()
        spec["target_revision"] = Sneaky(spec["target_revision"])
        with self.assertRaises(SiteStepError):
            validate_final_spec(spec)

    def test_site_failure_is_unknown_never_a_pass(self):
        self.assertEqual(self.carrier(fetch=served(answer=(503, "")))
                         .observe({}, {}).status, "unknown")

    def test_carrier_refuses_an_untrusted_composition(self):
        with self.assertRaises(SiteStepError):
            FinalCarrier(spec=final_spec(), fetch=None,
                         release_by_tag=lambda _tag: None,
                         ledger_row=lambda _tag: None)


if __name__ == "__main__":
    unittest.main()
