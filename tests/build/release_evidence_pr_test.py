#!/usr/bin/env python3
"""Production PR transport with durable crash/unknown-result state fixtures."""

from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/build"))
from ci_pr_body_lint import check_pr_body
from tools.release.evidence_pr import EvidencePrError, EvidencePullRequest, pr_document
from tools.release.github_api import GitHubApiError, GitHubClient, HttpResponse
from tools.release.model import canonical_json
from tools.release.orchestration import JournalError, RequestJournal
from tools.release.orchestration_driver import Observation


class PrTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lmdj-evidence-pr-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "journal"
        self.spec = dict(operation_id="1" * 64, request_sha256="2" * 64, repository_id=12,
            actor_id=34, base_revision="a" * 40, head_sha="b" * 40, tree_sha="c" * 40,
            tag="lmdj-v1.0.42.0", target_revision="d" * 40, task_evidence_sha256="3" * 64)
        self.document = pr_document(self.spec)
        self.row = None
        self.calls = []
        self.mode = None
        self.review_state = "verified"
        self.merged_state = "verified"
        self.authorizations = 0
        self.reviews = 0
        self.fail_auth_at = None
        self.change_review_at = None
        self.client = GitHubClient(http_transport=self.http, token="fixture-private-token")
        self.controller = self.new_controller()

    def new_controller(self):
        return EvidencePullRequest(self.root, api=self.client.release_pr_request,
            authorize=self.authorize, review=self.review, verify_merged=self.verify_merged)

    def authorize(self, spec):
        self.assertEqual(spec, self.spec)
        self.authorizations += 1
        if self.authorizations == self.fail_auth_at:
            raise RuntimeError("SECRET-AUTHORITY-ERROR")

    def review(self, spec, row):
        self.assertEqual(spec, self.spec)
        self.assertEqual(row["head"]["sha"], self.spec["head_sha"])
        self.reviews += 1
        state = "conflict" if self.reviews == self.change_review_at else self.review_state
        return Observation(state, {"sha256": "4" * 64, "reference": "review:fixture"} if state == "verified" else None)

    def verify_merged(self, spec, row, review_receipt):
        self.assertTrue(row["merged"])
        self.assertEqual(row["head"]["sha"], spec["head_sha"])
        self.assertEqual(review_receipt, {"sha256": "4" * 64, "reference": "review:fixture"})
        return Observation(self.merged_state, {"sha256": "5" * 64, "reference": "merged:fixture"}
                           if self.merged_state == "verified" else None)

    def new_row(self):
        repo = {"id": 12, "full_name": "endaye/lmdj"}
        return {"id": 101, "number": 99, "html_url": "https://github.com/endaye/lmdj/pull/99",
            "user": {"id": 34}, "title": self.document["title"], "body": self.document["body"],
            "state": "open", "draft": False, "merged": False, "merged_at": None,
            "merge_commit_sha": None, "mergeable": True,
            "head": {"ref": self.document["head"], "sha": self.spec["head_sha"], "repo": deepcopy(repo)},
            "base": {"ref": "main", "sha": "a" * 40, "repo": repo}}

    def merge_row(self):
        self.row.update(merged=True, state="closed", merged_at="2026-09-13T00:00:00Z", merge_commit_sha="e" * 40)

    def http(self, method, url, headers, body):
        self.calls.append((method, url, None if body is None else json.loads(body)))
        prefix = "/repos/endaye/lmdj"
        suffix = url.removeprefix(prefix)
        response_code = 200
        if method == "GET":
            if suffix == "":
                value = {"id": 12, "full_name": "endaye/lmdj"}
            elif suffix == "/user":
                value = {"id": 34}
            elif suffix == "/branches/main":
                value = {"name": "main", "protected": self.mode != "unprotected", "commit": {"sha": "a" * 40}}
            elif suffix.startswith("/git/ref/heads/"):
                value = {"ref": "refs/heads/" + self.document["head"], "object": {"type": "commit",
                    "sha": "f" * 40 if self.mode == "branch-drift" else self.spec["head_sha"]}}
            elif suffix.startswith("/pulls?"):
                value = [] if self.row is None or self.mode == "hidden-pr" else [{"number": 99}]
                if self.mode == "duplicate-inventory":
                    value *= 2
            elif suffix == "/pulls/99":
                value = deepcopy(self.row)
            else:
                raise AssertionError((method, suffix))
        elif method == "POST":
            self.assertEqual(suffix, "/pulls")
            self.assertEqual(json.loads(body), self.document)
            self.assertTrue(json.loads((self.root / "pr-state.json").read_text())["create_intent"])
            if self.mode != "create-before-effect":
                self.row = self.new_row()
            if self.mode in ("create-before-effect", "create-after-effect"):
                raise TimeoutError("SECRET-CREATE-RESPONSE")
            value, response_code = {}, 201  # Deliberately insufficient ACK.
        elif method == "PUT":
            self.assertEqual(suffix, "/pulls/99/merge")
            self.assertEqual(json.loads(body), {"sha": self.spec["head_sha"], "merge_method": "squash"})
            self.assertTrue(json.loads((self.root / "pr-state.json").read_text())["merge_intent"])
            self.assertGreaterEqual(self.reviews, 2)
            if self.mode != "merge-before-effect":
                self.merge_row()
            if self.mode in ("merge-before-effect", "merge-after-effect"):
                raise TimeoutError("SECRET-MERGE-RESPONSE")
            value = {"merged": True}
        else:
            raise AssertionError(method)
        return HttpResponse(response_code, {"Content-Type": "application/json"}, canonical_json(value))

    def advance(self, **changes):
        return self.controller.advance(dict(self.spec, **changes))

    def writes(self):
        return [call for call in self.calls if call[0] != "GET"]

    def test_create_review_merge_reopen_verifies_once_only(self):
        first = self.advance()
        self.assertEqual(first["status"], "verified")
        self.assertEqual(first["merge_sha"], "e" * 40)
        self.controller = self.new_controller()
        self.assertEqual(self.advance(), first)
        self.assertEqual([call[0] for call in self.writes()], ["POST", "PUT"])

    def test_oversized_state_cannot_replace_recoverable_journal(self):
        self.review_state = "pending"
        self.assertEqual(self.advance()["status"], "review-pending")
        with RequestJournal(self.root) as journal:
            state = self.controller._state(journal, self.spec)
            original = (self.root / "pr-state.json").read_bytes()
            inventory = sorted(p.name for p in self.root.iterdir())
            state["spec"]["tag"] = "lmdj-v" + "1" * 65536 + ".0.0.0"
            with self.assertRaisesRegex(EvidencePrError, "durable state exceeds"):
                self.controller._save(journal, state)
            self.assertEqual((self.root / "pr-state.json").read_bytes(), original)
            self.assertEqual(sorted(p.name for p in self.root.iterdir()), inventory)
            self.assertEqual(self.controller._state(journal, self.spec)["number"], 99)

    def test_create_timeout_before_effect_never_reposts_even_if_absent(self):
        self.mode = "create-before-effect"
        self.assertEqual(self.advance()["status"], "unknown-create")
        self.mode = None
        self.controller = self.new_controller()
        self.assertEqual(self.advance()["status"], "unknown-create")
        self.assertEqual(len(self.writes()), 1)

    def test_missing_state_after_unknown_create_never_reposts(self):
        self.mode = "create-before-effect"
        self.assertEqual(self.advance()["status"], "unknown-create")
        (self.root / "pr-state.json").unlink()
        self.controller = self.new_controller()
        with self.assertRaisesRegex(EvidencePrError, "enrolled.*state is missing"):
            self.advance()
        self.assertEqual(len(self.writes()), 1)

    def test_same_type_authority_exception_is_not_exposed(self):
        def fail(_):
            raise EvidencePrError("SECRET-AUTHORITY-TEXT")
        self.controller.authorize = fail
        result = self.advance()
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertFalse(self.writes())

    def test_initial_authority_failure_preserves_resumable_initial_state(self):
        self.fail_auth_at = 1
        self.assertEqual(self.advance()["status"], "unavailable")
        self.assertFalse(self.writes())
        self.fail_auth_at = None
        self.controller = self.new_controller()
        self.assertEqual(self.advance()["status"], "verified")
        self.assertEqual([call[0] for call in self.writes()], ["POST", "PUT"])

    def test_missing_enrollment_marker_is_not_reconstructed(self):
        self.review_state = "pending"
        self.advance()
        (self.root / "pr-enrolled").unlink()
        with self.assertRaisesRegex(EvidencePrError, "enrollment marker is missing"):
            self.advance()
        self.assertEqual(len(self.writes()), 1)

    def test_process_exit_during_enrollment_cannot_restart_as_fresh(self):
        child = os.fork()
        if child == 0:
            try:
                with patch.object(EvidencePullRequest, "_save", side_effect=lambda *_: os._exit(73)):
                    self.advance()
            except BaseException:
                os._exit(74)
            os._exit(75)
        _, child_status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(child_status), 73)
        self.assertEqual((self.root / "pr-enrolled").read_bytes(), b"")
        self.assertFalse((self.root / "pr-state.json").exists())
        self.controller = self.new_controller()
        with self.assertRaisesRegex(EvidencePrError, "enrolled.*state is missing"):
            self.advance()
        self.assertFalse(self.calls)

    def test_same_type_review_exception_is_not_exposed(self):
        self.row = self.new_row()
        def fail(*_):
            raise EvidencePrError("SECRET-REVIEW-TEXT")
        self.controller.review = fail
        result = self.advance()
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertFalse(self.writes())

    def test_same_type_merged_verifier_exception_is_not_exposed(self):
        self.row = self.new_row()
        self.merge_row()
        def fail(*_):
            raise EvidencePrError("SECRET-VERIFIER-TEXT")
        self.controller.verify_merged = fail
        result = self.advance()
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertFalse(self.writes())

    def test_same_type_api_exception_is_not_exposed(self):
        def fail(*_):
            raise EvidencePrError("SECRET-API-TEXT")
        self.controller.api = fail
        result = self.advance()
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertFalse(self.writes())

    def test_late_create_effect_is_adopted_without_second_post(self):
        self.mode = "create-before-effect"
        self.advance()
        self.row, self.mode = self.new_row(), None
        self.assertEqual(self.advance()["status"], "verified")
        self.assertEqual([call[0] for call in self.writes()], ["POST", "PUT"])

    def test_create_timeout_after_effect_reconciles_without_ack(self):
        self.mode = "create-after-effect"
        self.assertEqual(self.advance()["status"], "verified")
        self.assertEqual([call[0] for call in self.writes()], ["POST", "PUT"])

    def test_merge_timeout_before_effect_never_repeats_put(self):
        self.mode = "merge-before-effect"
        self.assertEqual(self.advance()["status"], "unknown-merge")
        self.mode = None
        self.assertEqual(self.advance()["status"], "unknown-merge")
        self.merge_row()
        self.assertEqual(self.advance()["status"], "verified")
        self.assertEqual([call[0] for call in self.writes()], ["POST", "PUT"])

    def test_merge_timeout_after_effect_is_verified_from_get(self):
        self.mode = "merge-after-effect"
        self.assertEqual(self.advance()["status"], "verified")
        self.assertEqual(len(self.writes()), 2)

    def test_pending_review_then_same_pr_resumes(self):
        self.review_state = "pending"
        self.assertEqual(self.advance()["status"], "review-pending")
        self.assertEqual(len(self.writes()), 1)
        self.review_state = "verified"
        self.assertEqual(self.advance()["status"], "verified")
        self.assertEqual([call[0] for call in self.writes()], ["POST", "PUT"])

    def test_review_changed_at_write_boundary_prevents_merge(self):
        self.change_review_at = 2
        self.assertEqual(self.advance()["status"], "review-conflict")
        self.assertFalse(self.row["merged"])
        self.assertEqual(len(self.writes()), 1)

    def test_merged_api_is_not_enough_without_source_verification(self):
        self.merged_state = "unknown"
        self.assertEqual(self.advance()["status"], "merged-source-unknown")
        self.merged_state = "verified"
        self.assertEqual(self.advance()["status"], "verified")
        self.assertEqual(len(self.writes()), 2)

    def test_rebound_spec_does_not_make_another_write(self):
        self.review_state = "pending"
        self.advance()
        with self.assertRaisesRegex(EvidencePrError, "corrupt or rebound"):
            self.advance(task_evidence_sha256="6" * 64)
        self.assertEqual(len(self.writes()), 1)

    def test_wrong_pr_identities_are_not_adopted(self):
        for field, value in (("head", dict(self.new_row()["head"], sha="f" * 40)),
                             ("user", {"id": 98}), ("body", "edited"), ("draft", True),
                             ("state", "closed")):
            with self.subTest(field=field):
                self.row = self.new_row()
                self.row[field] = value
                with self.assertRaises(EvidencePrError):
                    self.advance()
        self.assertFalse(self.writes())

    def test_branch_or_protection_drift_prevents_create(self):
        for mode in ("unprotected", "branch-drift"):
            self.mode = mode
            with self.assertRaises(EvidencePrError):
                self.advance()
        self.assertFalse(self.writes())

    def test_invalid_gate_return_does_not_authorize_merge(self):
        self.controller.review = lambda *_: True
        with self.assertRaisesRegex(EvidencePrError, "invalid observation"):
            self.advance()
        self.assertEqual(len(self.writes()), 1)

    def test_authority_error_is_sanitized_and_not_a_write_authorization(self):
        self.fail_auth_at = 3
        output = self.advance()
        self.assertEqual(output["status"], "unavailable")
        self.assertNotIn("SECRET", json.dumps(output))
        self.assertFalse(self.writes())
        self.fail_auth_at = None
        self.assertEqual(self.advance()["status"], "unknown-create")

    def test_corrupt_state_is_preserved(self):
        self.review_state = "pending"
        self.advance()
        state = self.root / "pr-state.json"
        state.write_bytes(b"broken")
        with self.assertRaises(ValueError):
            self.advance()
        self.assertEqual(state.read_bytes(), b"broken")
        self.assertEqual(len(self.writes()), 1)

    def test_second_writer_is_refused(self):
        with RequestJournal(self.root):
            with self.assertRaises(JournalError):
                self.advance()
        self.assertFalse(self.writes())

    def crash_after_effect(self, boundary):
        remote_state = Path(self.temp.name) / "far-side.json"
        child = os.fork()
        if child == 0:
            original = self.http
            def terminate(method, url, headers, body):
                response = original(method, url, headers, body)
                if method == boundary:
                    with remote_state.open("wb") as output:
                        output.write(canonical_json({"row": self.row, "writes": self.writes()}))
                        output.flush()
                        os.fsync(output.fileno())
                    os._exit(73)
                return response
            self.client._http_transport = terminate
            try:
                self.advance()
            except BaseException:
                os._exit(74)
            os._exit(75)
        _, wait_status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(wait_status), 73)
        remote = json.loads(remote_state.read_bytes())
        self.row = remote["row"]
        self.controller = self.new_controller()
        self.assertEqual(self.advance()["status"], "verified")
        writes = remote["writes"] + self.writes()
        self.assertEqual([write[0] for write in writes], ["POST", "PUT"])

    def test_process_death_after_create_adopts_original_pr(self):
        self.crash_after_effect("POST")

    def test_process_death_after_merge_verifies_without_another_put(self):
        self.crash_after_effect("PUT")

    def test_duplicate_inventory_is_not_an_absence_observation(self):
        self.row = self.new_row()
        self.mode = "duplicate-inventory"
        with self.assertRaisesRegex(EvidencePrError, "repeats or lacks identity"):
            self.advance()
        self.assertFalse(self.writes())

    def test_multiple_pr_inventory_stops_before_per_row_read_amplification(self):
        rows = [{"number": number} for number in range(1, 101)]
        with patch.object(self.controller, "_request", side_effect=[rows, []]), \
                patch.object(self.controller, "_pr", return_value={}) as detail:
            with self.assertRaisesRegex(EvidencePrError, "multiple PRs"):
                self.controller._find(self.spec)
        self.assertLessEqual(detail.call_count, 1)
        self.assertFalse(self.writes())

    def test_conflict_after_mergeable_observation_never_repeats_merge_put(self):
        def conflict(method, url, headers, body):
            if method == "PUT":
                self.calls.append((method, url, json.loads(body)))
                self.assertTrue(self.row["mergeable"])
                self.assertEqual(json.loads(body), {"sha": self.spec["head_sha"], "merge_method": "squash"})
                return HttpResponse(409, {"Content-Type": "application/json"}, b'{"message":"SECRET conflict"}')
            return self.http(method, url, headers, body)
        self.client = GitHubClient(http_transport=conflict, token="fixture-private-token")
        self.controller = self.new_controller()
        first = self.advance()
        self.assertEqual(first["status"], "unknown-merge")
        self.assertNotIn("SECRET", json.dumps(first))
        self.assertFalse(self.row["merged"])
        self.controller = self.new_controller()
        self.assertEqual(self.advance()["status"], "unknown-merge")
        self.assertEqual(sum(call[0] == "PUT" for call in self.calls), 1)

    def test_saved_merge_identity_cannot_be_replaced(self):
        self.advance()
        self.row["merge_commit_sha"] = "f" * 40
        with self.assertRaisesRegex(EvidencePrError, "saved merge identity changed"):
            self.advance()
        self.assertEqual(len(self.writes()), 2)

    def test_unknown_mergeability_yields_without_merge_intent(self):
        self.row = self.new_row()
        self.row["mergeable"] = None
        self.assertEqual(self.advance()["status"], "mergeability-pending")
        self.assertFalse(json.loads((self.root / "pr-state.json").read_bytes())["merge_intent"])
        self.assertFalse(self.writes())
        self.row["mergeable"] = True
        self.assertEqual(self.advance()["status"], "verified")

    def test_body_declares_required_task_checks_without_closing_issues(self):
        self.assertEqual(check_pr_body(self.document["body"]), [])
        for command in ("scripts/docs-site.sh check", "python3 tests/build/ci_change_scope_test.py", "git diff --cached --check"):
            self.assertIn(command, self.document["body"])
        self.assertIn("/releases/1.0.42.0/", self.document["body"])

    def test_transport_does_not_offer_other_mutations(self):
        for method, route, body in (("DELETE", "/pulls/99", None), ("PATCH", "/pulls/99", {}),
            ("PUT", "/pulls/99/merge", {"sha": "b" * 40, "merge_method": "merge"}),
            ("POST", "/pulls", dict(self.document, base="other")),
            ("GET", "/pulls?state=open", None), ("GET", "https://foreign.invalid", None)):
            with self.assertRaises(GitHubApiError):
                self.client.release_pr_request(method, route, body)
        self.assertFalse(self.calls)


if __name__ == "__main__":
    unittest.main()
