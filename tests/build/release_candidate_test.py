#!/usr/bin/env python3
"""Real Git and durable reservation tests; no actual Product allocation."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import release_candidate_inputs_test as fixtures
from tools.release.candidate import CandidateReservations, CATALOG
from tools.release.candidate_inputs import CandidateInputError, VERSION
from tools.release.orchestration import JournalError, RequestJournal
from tools.release.model import canonical_json, canonical_sha256


class ReservationTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CandidateTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.state = self.root / "private-state"
        self.reservations = CandidateReservations(self.root, self.state)
        # Derived, never restated: the fixture's Product Build is the history
        # floor, and a reservation is always the number above the floor. Pinning
        # the answer as a literal made these tests fail the next time anyone
        # moved the fixture's Build, which says nothing about reservations.
        self.floor = self.fixture.version["build"]
        self.reserved = f"1.0.{self.floor + 1}.0"
        self.after_reserved = f"1.0.{self.floor + 2}.0"
        self.request = {"id":"release-1", "repository":"example/product", "actor_id":123,
                        "authority_ref":"thread:release-1", "policy_digest":"a" * 64,
                        "control_revision":"b" * 40, "base_revision":self.fixture.base,
                        "mode":"new", "requested_tag":None}
        self.reservations.enroll(self.request["repository"])

    def reserve(self, request=None, frozen=None, main=None):
        return self.reservations.reserve(request or self.request, frozen or self.fixture.frozen,
                                         main or self.fixture.base)

    def commit(self):
        # State is outside the tracked fixture inventory, never stage it.
        self.fixture.git("add", "products", "packages", "apps", "docs")
        self.fixture.git("commit", "-m", "fixture")
        return self.fixture.git("rev-parse", "HEAD")

    def test_first_reservation_and_restart_reuse_exact_bytes(self):
        record = self.reserve()
        self.assertEqual(record["version"], self.reserved)
        raw = (self.state / CATALOG).read_bytes()
        self.reservations = CandidateReservations(self.root, self.state)
        self.assertEqual(self.reserve(), record)
        self.assertEqual((self.state / CATALOG).read_bytes(), raw)
        record["request"]["id"] = "changed"
        self.assertEqual(self.reserve()["request"], self.request)

    def test_new_request_never_reuses_failed_reservation(self):
        first = self.reserve()
        second = self.reserve(dict(self.request, id="release-2"))
        self.assertEqual((first["version"], second["version"]),
                         (self.reserved, self.after_reserved))
        self.assertEqual(self.reserve(), first)

    def test_reverted_higher_build_stays_consumed(self):
        self.fixture.write(VERSION, canonical_json({**self.fixture.version, "build":72}))
        self.commit()
        self.fixture.write(VERSION, canonical_json(self.fixture.version))
        base = self.commit()
        frozen = self.fixture.reader.freeze(base)
        record = self.reserve(dict(self.request, base_revision=base), frozen, base)
        self.assertEqual(record["history_floor"], 72)
        self.assertEqual(record["version"], "1.0.73.0")

    def test_new_build_resets_patch_not_build_or_product_line(self):
        self.fixture.write(VERSION, canonical_json({**self.fixture.version, "milestone":2, "minor":3, "patch":4}))
        base = self.commit()
        record = self.reserve(dict(self.request, base_revision=base), self.fixture.reader.freeze(base), base)
        self.assertEqual(record["version"], f"2.3.{self.floor + 1}.0")

    def test_concurrent_allocation_then_revert_is_still_candidate_changed(self):
        original = (self.state / CATALOG).read_bytes()
        self.fixture.write(VERSION, canonical_json({**self.fixture.version, "build":72}))
        self.commit()
        self.fixture.write(VERSION, canonical_json(self.fixture.version))
        main = self.commit()
        self.fixture.reader.verify(self.fixture.frozen, main)
        with self.assertRaisesRegex(JournalError, "candidate-changed"):
            self.reserve(main=main)
        self.assertEqual((self.state / CATALOG).read_bytes(), original)

    def test_merged_away_higher_build_is_in_full_history(self):
        self.fixture.git("checkout", "-b", "allocated-side", self.fixture.base)
        self.fixture.write(VERSION, canonical_json({**self.fixture.version, "build":72}))
        self.commit()
        self.fixture.git("checkout", "main")
        self.fixture.git("merge", "--no-ff", "-s", "ours", "allocated-side", "-m", "retain main tree")
        base = self.fixture.git("rev-parse", "HEAD")
        record = self.reserve(dict(self.request, base_revision=base), self.fixture.reader.freeze(base), base)
        self.assertEqual(record["version"], "1.0.73.0")

    def test_resume_competition_refuses_without_renumbering(self):
        first = self.reserve()
        raw = (self.state / CATALOG).read_bytes()
        self.fixture.write(VERSION,
                           canonical_json({**self.fixture.version,
                                           "build": self.floor + 1}))
        self.commit()
        self.fixture.write(VERSION, canonical_json(self.fixture.version))
        main = self.commit()
        with self.assertRaisesRegex(JournalError, "candidate-changed"):
            self.reserve(main=main)
        self.assertEqual((self.state / CATALOG).read_bytes(), raw)
        self.assertEqual(first["version"], self.reserved)

    def test_malformed_historical_manifest_is_not_skipped(self):
        raw = (self.state / CATALOG).read_bytes()
        self.fixture.write(VERSION, b'{"build":999}\n')
        self.commit()
        self.fixture.write(VERSION, canonical_json(self.fixture.version))
        base = self.commit()
        with self.assertRaisesRegex(JournalError, "historical Product version"):
            self.reserve(dict(self.request, base_revision=base), self.fixture.reader.freeze(base), base)
        self.assertEqual((self.state / CATALOG).read_bytes(), raw)

    def test_resume_reloads_historical_objects_instead_of_cached_versions(self):
        self.fixture.write(VERSION, canonical_json({**self.fixture.version, "build":72}))
        high = self.commit()
        oid = self.fixture.git("rev-parse", high + ":" + VERSION)
        self.fixture.write(VERSION, canonical_json(self.fixture.version))
        base = self.commit()
        frozen = self.fixture.reader.freeze(base)
        request = dict(self.request, base_revision=base)
        self.reserve(request, frozen, base)
        raw = (self.state / CATALOG).read_bytes()
        blob = self.root / ".git/objects" / oid[:2] / oid[2:]
        blob.rename(blob.with_name(blob.name + ".retained"))
        with self.assertRaisesRegex(JournalError, "historical Product version"):
            self.reserve(request, frozen, base)
        self.assertEqual((self.state / CATALOG).read_bytes(), raw)

    def test_docs_motion_preserves_original_reservation(self):
        record = self.reserve()
        self.fixture.write("docs/guide.md", b"new docs\n")
        main = self.commit()
        self.assertEqual(self.reserve(main=main), record)

    def test_source_competition_does_not_consume_or_retarget(self):
        raw = (self.state / CATALOG).read_bytes()
        self.fixture.write("packages/core/src/a.cpp", b"changed\n")
        main = self.commit()
        with self.assertRaisesRegex(CandidateInputError, "changed since"):
            self.reserve(main=main)
        self.assertEqual((self.state / CATALOG).read_bytes(), raw)

    def test_same_id_cannot_change_authority_or_scope(self):
        self.reserve()
        for change in ({"authority_ref":"thread:other"}, {"actor_id":124}, {"control_revision":"d" * 40}):
            with self.subTest(change=change), self.assertRaisesRegex(JournalError, "rebound"):
                self.reserve(dict(self.request, **change))

    def test_tag_mode_and_other_repository_refuse(self):
        for change in ({"mode":"tag", "requested_tag":"lmdj-v1.0.57.0"}, {"repository":"other/product"}):
            with self.subTest(change=change), self.assertRaises(JournalError):
                self.reserve(dict(self.request, **change))

    def test_missing_catalogue_never_reconstructs_on_resume_or_enrollment(self):
        self.reserve()
        (self.state / CATALOG).rename(self.state / "retained")
        with self.assertRaisesRegex(JournalError, "missing"):
            self.reserve()
        # Enrollment refuses real retained state: the extra "retained" entry
        # means this is not empty storage, so it never becomes an allocation.
        with self.assertRaisesRegex(JournalError, "changed during enrollment"):
            self.reservations.enroll(self.request["repository"])
        self.assertFalse((self.state / CATALOG).exists())

    def test_a_directory_holding_only_the_writer_lock_is_provisioned(self):
        # The entry's #1489 per-level private creation plus earlier journal
        # opens leave the directory present with just its writer lock; that
        # is empty storage, not enrolled history, and enrollment provisions
        # it. A missing CATALOG beside real state stays a refusal.
        (self.state / "writer.lock").write_bytes(b"")
        self.reservations.enroll(self.request["repository"])
        self.assertTrue((self.state / CATALOG).exists())

    def test_a_symlinked_catalogue_is_never_provisioned_over(self):
        target = self.root / "outside-catalogue"
        target.write_bytes(b"{}")
        link = self.state / "catalogue-link"
        link.symlink_to(target)
        # The real catalogue name is the directory name itself; simulate a
        # symlink planted at that name by swapping it in.
        real = self.state / CATALOG
        os.rename(real, self.state / "moved-catalogue")
        os.rename(link, real)
        with self.assertRaises(Exception):
            self.reservations.enroll(self.request["repository"])
        self.assertTrue(real.is_symlink())

    def test_missing_catalogue_with_real_state_is_not_new_enrollment(self):
        (self.state / CATALOG).rename(self.state / "retained")
        with self.assertRaisesRegex(JournalError,
                                    "changed during enrollment"):
            self.reservations.enroll(self.request["repository"])

    def test_unsafe_catalogue_is_not_read_or_replaced(self):
        filename = self.state / CATALOG
        filename.chmod(0o644)
        with self.assertRaisesRegex(JournalError, "private"):
            self.reserve()
        filename.chmod(0o600)
        retained = self.state / "retained"
        filename.rename(retained)
        filename.symlink_to(retained)
        with self.assertRaisesRegex(JournalError, "unsafe"):
            self.reserve()

    def test_corrupt_digest_and_sequence_refuse_without_repair(self):
        self.reserve()
        filename = self.state / CATALOG
        original = json.loads(filename.read_bytes())
        for valid_digest in (False, True):
            envelope = deepcopy(original)
            envelope["catalogue"]["reservations"][0]["version"] = "1.0.99.0"
            if valid_digest:
                envelope["sha256"] = canonical_sha256(envelope["catalogue"])
            raw = canonical_json(envelope)
            filename.write_bytes(raw)
            with self.subTest(valid_digest=valid_digest), self.assertRaisesRegex(JournalError, "differs"):
                self.reserve()
            self.assertEqual(filename.read_bytes(), raw)

    def test_second_writer_cannot_allocate(self):
        with RequestJournal(self.state):
            with self.assertRaisesRegex(JournalError, "another writer"):
                self.reserve()

    def test_crash_after_durable_save_resumes_same_number(self):
        child = os.fork()
        if child == 0:
            original = CandidateReservations._save
            def crash(journal, catalogue):
                original(journal, catalogue)
                os._exit(23)
            with patch.object(CandidateReservations, "_save", staticmethod(crash)):
                self.reserve()
            os._exit(99)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 23)
        self.assertEqual(self.reserve()["version"], self.reserved)
        envelope = json.loads((self.state / CATALOG).read_bytes())
        self.assertEqual(len(envelope["catalogue"]["reservations"]), 1)

    def test_pre_save_failure_consumes_no_externally_visible_number(self):
        raw = (self.state / CATALOG).read_bytes()
        with patch.object(CandidateReservations, "_save", side_effect=OSError("fixture")):
            with self.assertRaises(OSError): self.reserve()
        self.assertEqual((self.state / CATALOG).read_bytes(), raw)
        self.assertEqual(self.reserve()["version"], self.reserved)


if __name__ == "__main__":
    unittest.main()
