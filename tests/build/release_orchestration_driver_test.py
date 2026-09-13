#!/usr/bin/env python3
"""Driver journeys use a separate filesystem as a far-side API fixture."""

from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.model import canonical_sha256
from tools.release.orchestration import JournalError, RequestJournal, STEPS
from tools.release.orchestration_driver import Observation, ReleaseDriver
from tools.release.orchestration_policy import OrchestrationPolicy


POLICY = OrchestrationPolicy("a" * 64, "web-hosts-dev", "web-hosts", "canary", "dev",
                             ("runtime", "creator"), ("github-release", "doc-site"), 3, 10, 30, 1)


def request():
    return {"id": "release-1", "repository": "example/product", "actor_id": 123,
            "authority_ref": "thread:release-1", "policy_digest": POLICY.digest,
            "control_revision": "b" * 40, "base_revision": "c" * 40,
            "mode": "new", "requested_tag": None}


class Crash(BaseException):
    pass


class Backend:
    def __init__(self, root):
        self.root = root
        self.calls = []
        self.observations = []
        self.override = {}
        self.crash = None
        self.failure = None
        self.auth = True
        self.post_pending = None

    def authenticate(self, bound, policy):
        if not self.auth:
            raise PermissionError("authority unavailable")
        if bound != request() or policy != POLICY:
            raise PermissionError("scope differs")

    def observe(self, state, operation):
        step = operation["step"]
        self.observations.append(step)
        if step in self.override:
            return self.override[step]
        target = self.root / operation["operation_id"]
        if not target.exists():
            return Observation("absent")
        payload = json.loads(target.read_text())
        if payload != {"request": state["request_digest"], "operation": operation["operation_id"],
                       "step": step}:
            return Observation("conflict")
        return Observation("verified", {"sha256": canonical_sha256(payload),
                                        "reference": "fixture:" + operation["operation_id"]})

    def execute(self, state, operation):
        assert state["transitions"][-1] == operation  # durable intent is passed to execution
        self.calls.append(operation["step"])
        if self.failure == operation["step"]:
            raise RuntimeError("sensitive-upstream-error-not-for-public-status")
        with (self.root / operation["operation_id"]).open("x") as output:
            json.dump({"request": state["request_digest"], "operation": operation["operation_id"],
                       "step": operation["step"]}, output)
        if self.crash == operation["step"]:
            raise Crash()
        if self.post_pending == operation["step"]:
            self.override[operation["step"]] = Observation("pending")


class ReleaseDriverTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.remote = self.root / "remote"
        self.remote.mkdir()
        self.backend = Backend(self.remote)
        self.journal = self.root / "journal"
        self.driver = ReleaseDriver(self.journal, POLICY, self.backend)

    def state(self):
        with RequestJournal(self.journal) as journal:
            return journal.read("release-1")

    def test_complete_journey_and_reopen_revalidate_every_far_side(self):
        result = self.driver.run(request())
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.verified_steps, STEPS)
        self.assertEqual(self.backend.calls, list(STEPS))
        self.assertEqual(len(list(self.remote.iterdir())), len(STEPS))
        self.backend.observations.clear()
        self.assertEqual(self.driver.resume("release-1"), result)
        self.assertEqual(self.backend.observations, list(STEPS))
        self.assertEqual(self.backend.calls, list(STEPS))

    def admit_requests(self, *requests):
        def authenticate(bound, policy):
            if not self.backend.auth or policy != POLICY or bound not in requests:
                raise PermissionError("untrusted request")
        self.backend.authenticate = authenticate

    def test_duplicate_request_resumes_original_baseline_and_operation(self):
        original = request()
        incoming = dict(original, id="release-2", base_revision="d" * 40,
                        authority_ref="thread:release-2")
        self.admit_requests(original, incoming)
        self.backend.post_pending = "changelog_site"
        first = self.driver.run(original)
        frozen = self.state()
        self.assertEqual(self.driver.run(incoming), first)
        self.assertEqual(self.state(), frozen)
        self.assertFalse((self.journal / "release-2.json").exists())
        self.backend.override.clear()
        self.backend.post_pending = None
        result = self.driver.run(incoming)
        self.assertEqual((result.request_id, result.status), ("release-1", "complete"))
        self.assertEqual(self.backend.calls, list(STEPS))

    def test_duplicate_request_cannot_replace_revoked_original_authority(self):
        original = request()
        incoming = dict(original, id="release-2", authority_ref="thread:release-2")
        self.backend.post_pending = "changelog_site"
        self.driver.run(original)
        frozen = self.state()
        calls = list(self.backend.calls)
        self.admit_requests(incoming)
        with self.assertRaises(JournalError): self.driver.run(incoming)
        self.assertEqual(self.state(), frozen)
        self.assertEqual(self.backend.calls, calls)
        self.assertFalse((self.journal / "release-2.json").exists())

    def test_duplicate_request_refuses_changed_scope(self):
        original = request()
        self.backend.post_pending = "changelog_site"
        self.driver.run(original)
        frozen = self.state()
        for key, value in {"actor_id":456, "control_revision":"d" * 40,
                           "policy_digest":"e" * 64, "mode":"tag"}.items():
            incoming = dict(original, id="release-2", **{key:value})
            if key == "mode": incoming["requested_tag"] = "lmdj-v1.0.56.0"
            self.admit_requests(original, incoming)
            with self.subTest(key=key), self.assertRaises(JournalError):
                self.driver.run(incoming)
            self.assertEqual(self.state(), frozen)
            self.assertFalse((self.journal / "release-2.json").exists())

    def test_completed_history_does_not_deduplicate_a_new_request(self):
        original = request()
        incoming = dict(original, id="release-2", authority_ref="thread:release-2")
        self.admit_requests(original, incoming)
        self.assertEqual(self.driver.run(original).status, "complete")
        result = self.driver.run(incoming)
        self.assertEqual((result.request_id, result.status), ("release-2", "complete"))
        self.assertEqual(self.backend.calls, list(STEPS) * 2)
        self.assertEqual(len(list(self.remote.iterdir())), len(STEPS) * 2)

    def test_duplicate_unknown_write_never_reexecutes(self):
        original = request()
        incoming = dict(original, id="release-2", authority_ref="thread:release-2")
        self.admit_requests(original, incoming)
        self.backend.failure = "draft"
        first = self.driver.run(original)
        self.backend.failure = None
        self.assertEqual(self.driver.run(incoming), first)
        self.assertEqual(self.backend.calls.count("draft"), 1)
        self.assertNotIn("publication", self.backend.calls)

    def test_same_id_still_refuses_changed_baseline(self):
        original = request()
        changed = dict(original, base_revision="d" * 40)
        self.admit_requests(original, changed)
        self.backend.post_pending = "changelog_site"
        self.driver.run(original)
        frozen = self.state()
        with self.assertRaises(JournalError): self.driver.run(changed)
        self.assertEqual(self.state(), frozen)

    def test_exact_tag_request_cannot_adopt_another_tag(self):
        original = dict(request(), mode="tag", requested_tag="lmdj-v1.0.56.0")
        incoming = dict(original, id="release-2", requested_tag="lmdj-v1.0.57.0")
        self.admit_requests(original, incoming)
        self.backend.post_pending = "changelog_site"
        self.driver.run(original)
        with self.assertRaises(JournalError): self.driver.run(incoming)
        self.assertFalse((self.journal / "release-2.json").exists())

    def test_ambiguous_active_inventory_is_not_resolved_by_first_match(self):
        original = request()
        incoming = dict(original, id="release-3")
        self.admit_requests(original, incoming)
        with RequestJournal(self.journal) as journal:
            state = journal.create(original)
            other = dict(original, id="release-2")
            # Reproduce retained conflicting state without weakening admission.
            state.update(request=other, request_digest=canonical_sha256(other))
            journal._save(state)
        for selected in (incoming, original):
            with self.subTest(id=selected["id"]), self.assertRaisesRegex(JournalError, "ambiguous"):
                self.driver.run(selected)
        self.assertEqual(self.backend.calls, [])
        self.assertFalse((self.journal / "release-3.json").exists())

    def test_corrupt_inventory_cannot_be_ignored_as_unrelated(self):
        original = request()
        incoming = dict(original, id="release-2")
        self.admit_requests(original, incoming)
        self.backend.post_pending = "changelog_site"
        self.driver.run(original)
        (self.journal / "broken.json").write_bytes(b"{}")
        (self.journal / "broken.json").chmod(0o600)
        calls = list(self.backend.calls)
        with self.assertRaisesRegex(JournalError, "fields are missing"): self.driver.run(incoming)
        self.assertEqual(self.backend.calls, calls)
        self.assertFalse((self.journal / "release-2.json").exists())

    def test_duplicate_admission_requires_the_existing_writer_lock(self):
        incoming = dict(request(), id="release-2")
        self.admit_requests(request(), incoming)
        with RequestJournal(self.journal) as journal:
            journal.create(request())
            with self.assertRaises(JournalError): self.driver.run(incoming)
        self.assertEqual(self.backend.calls, [])

    def test_inventory_change_during_resolution_refuses_before_advance(self):
        import os
        incoming = dict(request(), id="release-2")
        self.admit_requests(request(), incoming)
        self.backend.post_pending = "changelog_site"
        self.driver.run(request())
        original_list = os.listdir
        reads = 0
        def changed(directory):
            nonlocal reads
            reads += 1
            if reads == 2:
                (self.journal / ".new-entry").write_bytes(b"fixture")
            return original_list(directory)
        calls = list(self.backend.calls)
        with patch("tools.release.orchestration.os.listdir", side_effect=changed):
            with self.assertRaisesRegex(JournalError, "inventory changed"):
                self.driver.run(incoming)
        self.assertEqual(self.backend.calls, calls)
        self.assertFalse((self.journal / "release-2.json").exists())

    def test_crash_after_publication_recovers_same_operation_without_republish(self):
        self.backend.crash = "publication"
        with self.assertRaises(Crash):
            self.driver.run(request())
        frozen = {p.name: p.read_bytes() for p in self.remote.iterdir()}
        self.assertEqual(self.state()["transitions"][-1]["status"], "intent")
        self.backend.crash = None
        self.assertEqual(self.driver.resume("release-1").status, "complete")
        self.assertEqual(self.backend.calls.count("publication"), 1)
        for name, raw in frozen.items():
            self.assertEqual((self.remote / name).read_bytes(), raw)

    def test_unknown_write_is_not_retried_even_when_far_side_is_absent(self):
        self.backend.failure = "draft"
        result = self.driver.run(request())
        self.assertEqual((result.status, result.step), ("unknown", "draft"))
        self.assertNotIn("sensitive", repr(result))
        self.backend.failure = None
        self.assertEqual(self.driver.resume("release-1"), result)
        self.assertEqual(self.backend.calls.count("draft"), 1)
        self.assertNotIn("publication", self.backend.calls)

    def test_site_pending_prevents_hosts_then_resumes_without_new_release(self):
        self.backend.post_pending = "changelog_site"
        result = self.driver.run(request())
        self.assertEqual((result.status, result.step), ("pending", "changelog_site"))
        self.assertNotIn("runtime", self.backend.calls)
        self.backend.override.clear()
        self.assertEqual(self.driver.resume("release-1").status, "complete")
        self.assertEqual(self.backend.calls, list(STEPS))

    def test_creator_failure_retains_runtime_and_prevents_promotion(self):
        self.backend.failure = "creator"
        result = self.driver.run(request())
        self.assertEqual((result.status, result.step), ("unknown", "creator"))
        self.assertIn("runtime", result.verified_steps)
        self.assertNotIn("promotion", self.backend.calls)
        self.assertEqual(self.driver.resume("release-1"), result)
        self.assertEqual(self.backend.calls.count("runtime"), 1)

    def test_missing_saved_far_side_receipt_blocks_even_completed_request(self):
        self.driver.run(request())
        operation = self.state()["transitions"][0]
        (self.remote / operation["operation_id"]).unlink()
        result = self.driver.resume("release-1")
        self.assertEqual((result.status, result.step), ("evidence-absent", "candidate"))
        self.assertEqual(result.verified_steps, ())
        self.assertEqual(self.backend.calls, list(STEPS))

    def test_changed_receipt_digest_is_not_adopted(self):
        self.driver.run(request())
        self.backend.override["verification"] = Observation("verified", {
            "sha256": "f" * 64, "reference": "other:run"})
        result = self.driver.resume("release-1")
        self.assertEqual((result.status, result.step), ("evidence-conflict", "verification"))
        self.assertEqual(result.verified_steps, ("candidate",))

    def test_preflight_unknown_does_not_create_intent_or_execute(self):
        self.backend.override["candidate"] = Observation("unknown")
        self.assertEqual(self.driver.run(request()).status, "unknown")
        self.assertEqual(self.state()["transitions"], [])
        self.assertEqual(self.backend.calls, [])
        self.backend.override.clear()
        self.assertEqual(self.driver.resume("release-1").status, "complete")

    def test_authority_failure_does_not_create_request(self):
        self.backend.auth = False
        with self.assertRaisesRegex(JournalError, "authority"):
            self.driver.run(request())
        self.assertIsNone(self.state())
        self.assertEqual(self.backend.calls, [])

    def test_policy_change_does_not_resume_old_scope(self):
        self.backend.override["candidate"] = Observation("pending")
        self.driver.run(request())
        changed = ReleaseDriver(self.journal, replace(POLICY, digest="e" * 64), self.backend)
        with self.assertRaisesRegex(JournalError, "policy changed"):
            changed.resume("release-1")
        self.assertEqual(self.backend.calls, [])

    def test_invalid_observations_cannot_advance(self):
        for bad in (Observation("success"), Observation("verified"),
                    Observation("pending", {"sha256": "a" * 64, "reference": "run:1"})):
            with self.subTest(bad=bad):
                self.backend.override["candidate"] = bad
                with self.assertRaises(JournalError):
                    self.driver.run(request())
                self.assertEqual(self.state()["transitions"], [])
        self.assertEqual(self.backend.calls, [])

    def test_original_authority_rechecked_before_each_transition(self):
        execute = self.backend.execute
        def revoke(state, operation):
            execute(state, operation)
            self.backend.auth = False
        self.backend.execute = revoke
        with self.assertRaisesRegex(JournalError, "authority"):
            self.driver.run(request())
        self.assertEqual(self.backend.calls, ["candidate"])
        self.assertEqual(len(self.state()["transitions"]), 1)

    def test_read_exception_is_unknown_not_absence_or_public_error_text(self):
        def fail_read(state, operation):
            raise RuntimeError("secret-provider-token")
        self.backend.observe = fail_read
        result = self.driver.run(request())
        self.assertEqual(result.status, "unknown")
        self.assertNotIn("secret", repr(result))
        self.assertEqual(self.state()["transitions"], [])
        self.assertEqual(self.backend.calls, [])


if __name__ == "__main__":
    unittest.main()
