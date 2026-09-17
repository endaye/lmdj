#!/usr/bin/env python3
"""Actual nested controllers; fake GitHub gates and filesystem release effects."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/build"))
import release_evidence_pr_test as pr_fixture
import release_orchestration_driver_test as driver_fixture
from tools.release.evidence_pr import EvidencePrError, pr_document
from tools.release.evidence_pr_transition import EvidencePrTransition
from tools.release.model import canonical_sha256
from tools.release.orchestration import JournalError, RequestJournal, STEPS
from tools.release.orchestration_driver import Observation, ReleaseDriver


class ManagedTest(unittest.TestCase):
    def setUp(self):
        self.pr = pr_fixture.PrTest()
        self.pr.setUp()
        self.addCleanup(self.pr.doCleanups)
        self.parent = self.pr.root.parent / "parent"
        remote = self.pr.root.parent / "release-effects"
        remote.mkdir()
        self.request = dict(driver_fixture.request(), repository="endaye/lmdj", actor_id=34)
        digest = canonical_sha256(self.request)
        self.pr.spec.update(request_sha256=digest, operation_id=canonical_sha256({"request": digest, "step": "published_record"}))
        self.pr.document = pr_document(self.pr.spec)
        self.pr.controller = self.pr.new_controller()
        self.backend = driver_fixture.Backend(remote)
        def authenticate(request, policy):
            if not self.backend.auth or request != self.request or policy != driver_fixture.POLICY:
                raise RuntimeError("SECRET-AUTH")
        self.backend.authenticate = authenticate
        self.adapter = EvidencePrTransition(self.pr.controller, self.pr.spec)
        self.driver = self.new_driver()

    def new_driver(self):
        return ReleaseDriver(self.parent, driver_fixture.POLICY, self.backend, publication_pr=self.adapter)

    def state(self):
        with RequestJournal(self.parent) as journal:
            return journal.read(self.request["id"])

    def mutations(self):
        return [method for method, _, _ in self.pr.calls if method != "GET"]

    def test_pending_review_then_first_merge_then_site_then_hosts(self):
        self.pr.review_state = "pending"
        result = self.driver.run(self.request)
        self.assertEqual((result.status, result.step), ("pending", "published_record"))
        self.assertEqual(self.mutations(), ["POST"])
        self.assertNotIn("runtime", self.backend.calls)
        frozen = {p.name: p.read_bytes() for p in self.backend.root.iterdir()}
        self.pr.review_state = "verified"
        self.backend.override["changelog_site"] = Observation("pending")
        self.driver = self.new_driver()  # Reopen with the same durable journals.
        result = self.driver.resume(self.request["id"])
        self.assertEqual((result.status, result.step), ("pending", "changelog_site"))
        self.assertEqual(self.mutations(), ["POST", "PUT"])
        self.assertNotIn("runtime", self.backend.calls)
        self.backend.override.clear()
        complete = self.driver.resume(self.request["id"])
        self.assertEqual(complete.status, "complete")
        self.assertEqual(complete.verified_steps, STEPS)
        self.assertEqual(self.backend.calls, [step for step in STEPS if step != "published_record"])
        self.assertEqual(self.driver.resume(self.request["id"]), complete)
        self.assertEqual(self.mutations(), ["POST", "PUT"])
        for name, raw in frozen.items():
            self.assertEqual((self.backend.root / name).read_bytes(), raw)

    def test_opaque_recovery_cannot_advance_a_later_first_merge(self):
        # Causal baseline: the old opaque-write composition keeps observing the
        # pending PR forever, even when the first merge is now admissible.
        observe, execute = self.backend.observe, self.backend.execute
        self.backend.observe = lambda state, op: self.adapter.observe(state, op) if op["step"] == "published_record" else observe(state, op)
        # Explicit fixture authority, not a production opaque-backend guard.
        guard = lambda: self.backend.authenticate(self.request, driver_fixture.POLICY)
        self.backend.execute = lambda state, op: self.adapter.advance(state, op, before_write=guard) if op["step"] == "published_record" else execute(state, op)
        opaque = ReleaseDriver(self.parent, driver_fixture.POLICY, self.backend)
        self.pr.review_state = "pending"
        self.assertEqual(opaque.run(self.request).status, "pending")
        self.pr.review_state = "verified"
        self.assertEqual(opaque.resume(self.request["id"]).status, "pending")
        self.assertEqual(self.mutations(), ["POST"])

    def test_unknown_create_never_reposts_and_late_pr_is_adopted(self):
        self.pr.mode = "create-before-effect"
        self.assertEqual(self.driver.run(self.request).status, "unknown")
        self.pr.mode = None
        self.assertEqual(self.driver.resume(self.request["id"]).status, "unknown")
        self.assertEqual(self.mutations(), ["POST"])
        self.pr.row = self.pr.new_row()  # Same delayed request becomes visible.
        self.assertEqual(self.driver.resume(self.request["id"]).status, "complete")
        self.assertEqual(self.mutations(), ["POST", "PUT"])

    def test_unknown_merge_never_reputs_and_late_merge_is_verified(self):
        self.pr.mode = "merge-before-effect"
        self.assertEqual(self.driver.run(self.request).status, "unknown")
        self.pr.mode = None
        self.assertEqual(self.driver.resume(self.request["id"]).status, "unknown")
        self.assertEqual(self.mutations(), ["POST", "PUT"])
        self.pr.merge_row()
        self.assertEqual(self.driver.resume(self.request["id"]).status, "complete")
        self.assertEqual(self.mutations(), ["POST", "PUT"])

    def test_lost_write_ack_uses_positive_far_side_only(self):
        self.pr.mode = "create-after-effect"
        self.assertEqual(self.driver.run(self.request).status, "complete")
        self.assertEqual(self.mutations(), ["POST", "PUT"])

    def test_child_crash_after_create_resumes_only_first_merge(self):
        real = self.pr.controller._request
        def crash(method, path, document=None):
            result = real(method, path, document)
            if method == "POST":
                raise driver_fixture.Crash()
            return result
        self.pr.controller._request = crash
        with self.assertRaises(driver_fixture.Crash):
            self.driver.run(self.request)
        self.assertEqual(self.state()["transitions"][-1]["status"], "intent")
        self.pr.controller._request = real
        self.assertEqual(self.driver.resume(self.request["id"]).status, "complete")
        self.assertEqual(self.mutations(), ["POST", "PUT"])

    def _process_death(self, boundary):
        far_side = self.pr.root.parent / "api-state.json"
        pid = os.fork()
        if pid == 0:
            original = self.pr.http
            def crash(method, url, headers, body):
                result = original(method, url, headers, body)
                if method == boundary:
                    with far_side.open("w") as output:
                        json.dump({"row": self.pr.row, "mutations": self.mutations()}, output)
                        output.flush()
                        os.fsync(output.fileno())
                    os._exit(41)
                return result
            self.pr.client._http_transport = crash
            try:
                self.driver.run(self.request)
            except BaseException:
                os._exit(42)
            os._exit(43)
        _, wait_status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(wait_status), 41)
        observed = json.loads(far_side.read_text())
        self.pr.row = observed["row"]
        frozen = {p.name: p.read_bytes() for p in self.backend.root.iterdir()}
        self.assertEqual(self.state()["transitions"][-1]["status"], "intent")
        self.driver = self.new_driver()
        self.assertEqual(self.driver.resume(self.request["id"]).status, "complete")
        self.assertEqual(observed["mutations"] + self.mutations(), ["POST", "PUT"])
        self.assertNotIn("publication", self.backend.calls)
        for name, raw in frozen.items():
            self.assertEqual((self.backend.root / name).read_bytes(), raw)

    def test_process_death_after_post_reopens_both_journals(self):
        self._process_death("POST")

    def test_process_death_after_put_does_not_remerge(self):
        self._process_death("PUT")

    def test_parent_crash_before_child_effect_preserves_initialized_state(self):
        advance = self.adapter.advance
        def crash(*args, **kwargs):
            raise driver_fixture.Crash()
        self.adapter.advance = crash
        with self.assertRaises(driver_fixture.Crash):
            self.driver.run(self.request)
        self.assertTrue((self.pr.root / "pr-state.json").is_file())
        self.assertEqual(self.mutations(), [])
        self.adapter.advance = advance
        self.assertEqual(self.driver.resume(self.request["id"]).status, "complete")
        self.assertEqual(self.mutations(), ["POST", "PUT"])

    def test_missing_child_state_after_parent_intent_does_not_restart(self):
        self.pr.review_state = "pending"
        self.driver.run(self.request)
        (self.pr.root / "pr-state.json").unlink()
        self.pr.review_state = "verified"
        self.assertEqual(self.driver.resume(self.request["id"]).status, "unknown")
        self.assertEqual(self.mutations(), ["POST"])
        self.assertFalse((self.pr.root / "pr-state.json").exists())

    def test_previous_evidence_must_pass_before_next_child_mutation(self):
        self.pr.review_state = "pending"
        self.driver.run(self.request)
        self.pr.review_state = "verified"
        self.backend.override["publication"] = Observation("conflict")
        result = self.driver.resume(self.request["id"])
        self.assertEqual((result.status, result.step), ("evidence-conflict", "publication"))
        self.assertEqual(self.mutations(), ["POST"])

    def test_original_authority_rechecked_before_managed_frontier(self):
        self.pr.review_state = "pending"
        self.driver.run(self.request)
        self.pr.review_state = "verified"
        self.backend.auth = False
        with self.assertRaisesRegex(JournalError, "authority"):
            self.driver.resume(self.request["id"])
        self.assertEqual(self.mutations(), ["POST"])

    def _lost_parent_at_child_write(self, boundary, fault):
        real = self.pr.controller._request
        faulted = False
        def request(method, path, document=None):
            nonlocal faulted
            result = real(method, path, document)
            child = self.pr.root / "pr-state.json"
            if not faulted and method == "GET" and path == "/branches/main" and child.exists():
                saved = json.loads(child.read_bytes())
                if saved[boundary + "_intent"]:
                    faulted = True
                    if fault == "authority":
                        self.backend.auth = False
                    else:
                        (self.parent / "writer.lock").rename(self.parent / "retained.lock")
                        fd = os.open(self.parent / "writer.lock", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                        os.close(fd)
            return result
        self.pr.controller._request = request
        try:
            self.driver.run(self.request)
        except JournalError:
            pass  # A replaced parent writer may also refuse the final read.
        self.assertTrue(faulted)
        expected = [] if boundary == "create" else ["POST"]
        self.assertEqual(self.mutations(), expected)
        raw = (self.pr.root / "pr-state.json").read_bytes()
        self.assertTrue(json.loads(raw)[boundary + "_intent"])
        self.backend.auth = True
        self.pr.controller._request = real
        # New controller opens the actual retained journals. Even positive
        # absence cannot authorize replay of a durable, unresolved intent.
        self.driver = self.new_driver()
        result = self.driver.resume(self.request["id"])
        self.assertEqual((result.status, result.step), ("unknown", "published_record"))
        self.assertEqual(self.mutations(), expected)
        self.assertEqual((self.pr.root / "pr-state.json").read_bytes(), raw)

    def test_parent_authority_lost_before_child_create_blocks_post(self):
        self._lost_parent_at_child_write("create", "authority")

    def test_parent_writer_replaced_before_child_create_blocks_post(self):
        self._lost_parent_at_child_write("create", "writer")

    def test_parent_authority_lost_before_child_merge_blocks_put(self):
        self._lost_parent_at_child_write("merge", "authority")

    def test_parent_writer_replaced_before_child_merge_blocks_put(self):
        self._lost_parent_at_child_write("merge", "writer")

    def _child_writer_replaced_in_parent_guard(self, boundary):
        authenticate = self.backend.authenticate
        faulted = False
        def guard(request, policy):
            nonlocal faulted
            authenticate(request, policy)
            child = self.pr.root / "pr-state.json"
            if not faulted and child.exists() and json.loads(child.read_bytes())[boundary + "_intent"]:
                faulted = True
                (self.pr.root / "writer.lock").rename(self.pr.root / "retained.lock")
                fd = os.open(self.pr.root / "writer.lock", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
        self.backend.authenticate = guard
        result = self.driver.run(self.request)
        self.assertTrue(faulted)
        self.assertEqual((result.status, result.step), ("unknown", "published_record"))
        self.assertEqual(self.mutations(), [] if boundary == "create" else ["POST"])

    def test_child_writer_rechecked_after_parent_create_guard(self):
        self._child_writer_replaced_in_parent_guard("create")

    def test_child_writer_rechecked_after_parent_merge_guard(self):
        self._child_writer_replaced_in_parent_guard("merge")

    def test_managed_pr_requires_callable_parent_guard(self):
        self.pr.review_state = "pending"
        self.driver.run(self.request)
        state = self.state()
        with self.assertRaisesRegex(JournalError, "final parent guard"):
            self.adapter.advance(state, state["transitions"][-1], before_write=None)
        self.assertEqual(self.mutations(), ["POST"])

    def _private_guard_error(self, boundary):
        def guard():
            saved = json.loads((self.pr.root / "pr-state.json").read_bytes())
            if saved[boundary + "_intent"]:
                raise EvidencePrError("PRIVATE-GUARD-SENTINEL")
        # Exercise the actual public child entrypoint without the parent's
        # exception wrapper masking its own responsibility to sanitize gates.
        result = self.pr.controller.advance(self.pr.spec, before_write=guard)
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("PRIVATE-GUARD-SENTINEL", repr(result))
        self.assertEqual(self.mutations(), [] if boundary == "create" else ["POST"])

    def test_create_guard_same_type_exception_is_sanitized(self):
        self._private_guard_error("create")

    def test_merge_guard_same_type_exception_is_sanitized(self):
        self._private_guard_error("merge")

    def test_child_binding_rebound_cannot_create_or_merge(self):
        self.adapter.spec["request_sha256"] = "f" * 64
        result = self.driver.run(self.request)
        self.assertEqual((result.status, result.step), ("unknown", "published_record"))
        self.assertEqual(self.mutations(), [])

    def test_observation_never_performs_external_writes(self):
        self.assertEqual(self.pr.controller.observe(self.pr.spec)["status"], "unknown")
        self.assertEqual(self.pr.controller.observe(self.pr.spec, initialize=True)["status"], "absent")
        state_raw = (self.pr.root / "pr-state.json").read_bytes()
        self.assertEqual(self.pr.controller.observe(self.pr.spec)["status"], "absent")
        self.assertEqual((self.pr.root / "pr-state.json").read_bytes(), state_raw)
        self.assertEqual(self.mutations(), [])

    def test_oversized_observation_refused_before_enrollment(self):
        oversized = dict(self.pr.spec, tag="lmdj-v" + "1" * 10000 + ".0.0.0")
        with self.assertRaisesRegex(EvidencePrError, "document.*bounds"):
            self.pr.controller.observe(oversized, initialize=True)
        self.assertFalse(self.pr.root.exists())
        self.assertEqual(self.pr.calls, [])

    def test_postmerge_source_drift_prevents_completion_or_future_writes(self):
        self.backend.override["changelog_site"] = Observation("pending")
        self.assertEqual(self.driver.run(self.request).step, "changelog_site")
        self.pr.merged_state = "conflict"
        self.backend.override.clear()
        result = self.driver.resume(self.request["id"])
        self.assertEqual((result.status, result.step), ("evidence-conflict", "published_record"))
        self.assertNotIn("runtime", self.backend.calls)
        self.assertEqual(self.mutations(), ["POST", "PUT"])

    def test_arbitrary_managed_callback_is_not_admitted(self):
        with self.assertRaisesRegex(JournalError, "unsupported managed"):
            ReleaseDriver(self.parent, driver_fixture.POLICY, self.backend, publication_pr=lambda: None)


if __name__ == "__main__":
    unittest.main()
