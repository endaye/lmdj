#!/usr/bin/env python3
"""Witness transport contracts; fixture review is never live GitHub approval."""
from copy import deepcopy
from hashlib import sha256
import errno
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import release_evidence_pr_test as pr_fixture
import release_evidence_branch_test as branch_fixture
import release_candidate_witness_task_test as task_fixture
from tools.release.candidate_pr import validate_spec as candidate_spec
from tools.release.candidate_pr_sequence import CandidatePrSequence, CandidateSequenceError
from tools.release.evidence_pr import EvidencePrError, validate_spec as publication_spec
from tools.release.evidence_branch import EvidenceBranchError
from tools.release.github_api import GitHubApiError, HttpResponse
from tools.release.model import canonical_json, canonical_sha256
from tools.release.orchestration import JournalError, RequestJournal
from tools.release.orchestration_driver import Observation
from tools.release.witness_pr import WitnessBranch, WitnessPullRequest, WitnessPrSequence, pr_document, validate_spec
from tools.release.witness_source import CandidateWitnessSourceVerifier, WitnessSourceError


def artifact(build, raw=b"fixture witness\n"):
    return {"path":f"apps/architecture-portal/versioned_provenance/version-{build}-squash-witness.json",
            "bytes":len(raw), "sha256":sha256(raw).hexdigest()}


def witness_spec(seed):
    spec = deepcopy(seed)
    spec.pop("tag")
    spec.update(product_build="1.0.42.0", source_sha="d" * 40,
        target_revision=spec["base_revision"], witness_receipt_sha256="6" * 64,
        task_binding_sha256="7" * 64, witness=artifact("1.0.42.0"))
    spec["operation_id"] = canonical_sha256({"request":spec["request_sha256"], "step":"candidate-witness"})
    return spec


class WitnessPrTest(pr_fixture.PrTest):
    def setUp(self):
        super().setUp()
        self.publication = deepcopy(self.spec)
        self.spec = witness_spec(self.spec)
        self.document = pr_document(self.spec)
        self.controller = self.new_controller()

    def new_controller(self):
        return WitnessPullRequest(self.root, api=self.client.witness_pr_request,
            authorize=self.authorize, review=self.review, verify_merged=self.verify_merged)

    def resize(self, digits):
        self.spec["product_build"] = "1" * digits + ".0.0.0"
        self.spec["witness"] = artifact(self.spec["product_build"])

    def test_oversized_generated_document_is_rejected_before_enrollment(self):
        self.resize(20000)
        for invoke in (lambda: self.controller.observe(self.spec, initialize=True), lambda: self.advance()):
            with self.assertRaisesRegex(EvidencePrError, "document.*transport"):
                invoke()
        self.assertFalse(self.root.exists())
        self.assertFalse(self.calls)

    def test_largest_generated_document_within_transport_bound_is_sent(self):
        self.resize(1)
        baseline = pr_document(self.spec)["body"]
        count = baseline.count(self.spec["product_build"])
        self.resize(1 + (20000 - len(baseline)) // count)
        self.document = pr_document(self.spec)
        self.assertLessEqual(len(self.document["body"]), 20000)
        self.assertGreater(len(self.document["body"]) + count, 20000)
        self.assertEqual(self.advance()["status"], "verified")
        self.assertEqual([body for method, _, body in self.calls if method == "POST"], [self.document])

    def test_body_declares_required_task_checks_without_closing_issues(self):
        self.assertEqual(pr_fixture.check_pr_body(self.document["body"]), [])
        for text in ("scripts/docs-site.sh check", "python3 tests/build/ci_change_scope_test.py",
                     "git diff --cached --check", "/versions/1.0.42.0/", "Version impact: none",
                     self.spec["witness"]["sha256"], self.spec["witness_receipt_sha256"]):
            self.assertIn(text, self.document["body"])
        self.assertNotIn("releases/tag/", self.document["body"])

    def test_transport_does_not_offer_other_mutations(self):
        for method, route, body in (("DELETE", "/pulls/99", None), ("PATCH", "/pulls/99", {}),
            ("PUT", "/pulls/99/merge", {"sha":"b" * 40, "merge_method":"merge"}),
            ("POST", "/pulls", dict(self.document, base="other")),
            ("GET", "/pulls?state=open", None), ("GET", "https://foreign.invalid", None)):
            with self.assertRaises(GitHubApiError): self.client.witness_pr_request(method, route, body)
        self.assertFalse(self.calls)

    def test_all_three_transport_scopes_are_disjoint(self):
        for validator in (candidate_spec, publication_spec):
            with self.assertRaises(EvidencePrError): validator(self.spec)
        with self.assertRaises(EvidencePrError): validate_spec(self.publication)
        for prefix, api in (("feat/release-candidate-", self.client.candidate_pr_request),
                            ("docs/release-evidence-", self.client.release_pr_request)):
            foreign = dict(self.document, head=prefix + self.spec["operation_id"])
            for method, route, body in (("POST", "/pulls", foreign),
                ("GET", "/git/ref/heads/" + foreign["head"], None),
                ("GET", f"/pulls?state=all&head=endaye:{foreign['head']}&base=main&per_page=100&page=1", None)):
                with self.assertRaises(GitHubApiError): self.client.witness_pr_request(method, route, body)
            with self.assertRaises(GitHubApiError): api("POST", "/pulls", self.document)
        self.assertFalse(self.calls)

    def test_wrong_artifact_identity_refuses_before_enrollment(self):
        for change in ({"path":"../witness.json"}, {"bytes":True}, {"bytes":0},
                       {"bytes":64 * 1024 * 1024 + 1}, {"sha256":"x" * 64}):
            with self.subTest(change=change), self.assertRaises(EvidencePrError):
                self.advance(witness=dict(self.spec["witness"], **change))
        self.assertFalse(self.root.exists())
        self.assertFalse(self.calls)

    def test_wrong_candidate_or_operation_refuses_before_enrollment(self):
        for field, value in (("operation_id","8" * 64), ("target_revision",self.spec["head_sha"]),
                             ("source_sha",self.spec["target_revision"]), ("product_build","01.0.42.0")):
            with self.subTest(field=field), self.assertRaises(EvidencePrError): self.advance(**{field:value})
        self.assertFalse(self.root.exists())
        self.assertFalse(self.calls)


class WitnessBranchTest(branch_fixture.BranchTest):
    def setUp(self):
        super().setUp()
        self.spec = witness_spec(self.spec)
        self.bind_operation()

    def bind_operation(self):
        self.spec["operation_id"] = canonical_sha256({"request":self.spec["request_sha256"], "step":"candidate-witness"})
        self.ref = "refs/heads/" + pr_document(self.spec)["head"]

    def advance(self, spec=None):
        controller = WitnessBranch(self.journal, self.repo, token="SECRET-TOKEN", authorize=self.authorize)
        controller.api = self.api
        with patch.object(branch_fixture.module.subprocess, "run", side_effect=self.transport):
            return controller.advance(self.spec if spec is None else spec)

    def test_scope_rebound_and_corruption_refused(self):
        self.assertEqual(self.advance()["status"], "verified")
        with self.assertRaises(EvidenceBranchError): self.advance(dict(self.spec, task_evidence_sha256="f" * 64))
        (self.journal / "branch-state.json").write_bytes(b"{broken SECRET}")
        with self.assertRaisesRegex(EvidenceBranchError, "state is invalid"): self.advance()

    def test_real_controller_death_before_and_after_remote_effect(self):
        for mode, code in (("death-before",31), ("death-after",32)):
            with self.subTest(mode=mode):
                self.journal = self.root / mode
                self.spec["request_sha256"] = ("4" if code == 31 else "5") * 64
                self.bind_operation()
                child = os.fork()
                if child == 0:
                    self.mode = mode
                    self.advance()
                    os._exit(99)
                _, result = os.waitpid(child, 0)
                self.assertEqual(os.waitstatus_to_exitcode(result), code)
                # Controller exit does not prove every Git FD holder exited.
                # Wait for this exact writer, without invoking a remote effect.
                original_lock = (self.journal / "writer.lock").stat()
                state_raw = (self.journal / "branch-state.json").read_bytes()
                deadline = time.monotonic() + 5
                while True:
                    current_lock = (self.journal / "writer.lock").stat()
                    self.assertEqual((current_lock.st_dev, current_lock.st_ino),
                                     (original_lock.st_dev, original_lock.st_ino))
                    try:
                        with RequestJournal(self.journal): pass
                        break
                    except JournalError as error:
                        cause = error.__context__
                        if not isinstance(cause, BlockingIOError) or cause.errno not in (errno.EAGAIN, errno.EACCES):
                            raise
                        if time.monotonic() >= deadline:
                            self.fail("original Git writer did not exit after controller death")
                        time.sleep(0.025)
                self.assertEqual((self.journal / "branch-state.json").read_bytes(), state_raw)
                self.assertEqual(self.advance()["status"], "unknown" if code == 31 else "verified")
                self.assertEqual(self.pushes, 0)


class SequenceFixture(unittest.TestCase):
    def setUp(self):
        self.b, self.p = WitnessBranchTest(), WitnessPrTest()
        for fixture in (self.b, self.p):
            fixture.setUp()
            self.addCleanup(fixture.doCleanups)
        self.root = self.b.root / "sequence"
        self.b.journal, self.p.root = self.root / "branch", self.root / "pr"
        self.p.spec = deepcopy(self.b.spec)
        self.p.document = pr_document(self.p.spec)
        self.sequence = self.new_sequence()

    def new_sequence(self):
        branch = WitnessBranch(self.b.journal, self.b.repo, token="SECRET-TOKEN", authorize=self.b.authorize)
        branch.api = self.b.api
        return WitnessPrSequence(self.root, branch=branch, pr=self.p.new_controller())

    def call(self, method, **kwargs):
        if method == "advance": kwargs.setdefault("before_write", lambda: None)
        with patch.object(branch_fixture.module.subprocess, "run", side_effect=self.b.transport):
            return getattr(self.sequence, method)(self.b.spec, **kwargs)


class WitnessSequenceTest(SequenceFixture):
    def test_full_branch_pr_merge_and_cold_observation(self):
        self.assertEqual(self.call("advance")["status"], "unknown")
        self.assertEqual(self.call("observe", initialize=True)["status"], "absent")
        self.assertEqual(self.b.pushes, 0)
        self.assertFalse(self.p.writes())
        result = self.call("advance")
        self.assertEqual(result["status"], "merged")
        self.assertEqual(self.b.remote_sha(), self.b.spec["head_sha"])
        self.assertFalse((self.root / "candidate-pr-sequence.json").exists())
        self.assertEqual(json.loads((self.root / "witness-pr-sequence.json").read_bytes())["schema"], "lmdj.witness-pr-sequence.v1")
        self.sequence = self.new_sequence()
        self.assertEqual(self.call("observe"), result)
        self.assertEqual(self.call("advance"), result)
        self.assertEqual(self.b.pushes, 1)
        self.assertEqual([call[0] for call in self.p.writes()], ["POST", "PUT"])

    def test_pending_review_does_not_repeat_branch_or_create(self):
        self.call("observe", initialize=True)
        self.p.review_state = "pending"
        self.assertEqual(self.call("advance")["status"], "pending")
        self.sequence = self.new_sequence()
        self.assertEqual(self.call("advance")["status"], "pending")
        self.assertEqual(self.b.pushes, 1)
        self.assertEqual(len(self.p.writes()), 1)
        self.p.review_state = "verified"
        self.assertEqual(self.call("advance")["status"], "merged")

    def test_unknown_push_stops_before_pr_without_replay(self):
        self.call("observe", initialize=True)
        self.b.mode = "before"
        self.assertEqual(self.call("advance")["status"], "unknown")
        self.b.mode = None
        self.sequence = self.new_sequence()
        self.assertEqual(self.call("advance")["status"], "unknown")
        self.assertFalse(self.p.calls)
        self.assertEqual(self.b.pushes, 1)

    def test_missing_parent_is_not_reenrolled(self):
        self.call("observe", initialize=True)
        (self.root / "witness-pr-sequence.json").unlink()
        with self.assertRaises(CandidateSequenceError): self.call("observe", initialize=True)
        self.assertEqual(self.b.pushes, 0)

    def test_missing_pr_state_is_unknown_without_recreation(self):
        self.call("observe", initialize=True)
        self.p.review_state = "pending"
        self.call("advance")
        (self.p.root / "pr-state.json").unlink()
        self.assertEqual(self.call("advance")["status"], "unknown")
        self.assertEqual(self.call("observe", initialize=True)["status"], "unknown")
        self.assertFalse((self.p.root / "pr-state.json").exists())
        self.assertEqual(len(self.p.writes()), 1)

    def test_last_parent_guard_loss_prevents_push(self):
        self.call("observe", initialize=True)
        filename = self.root / "witness-pr-sequence.json"
        self.assertEqual(self.call("advance", before_write=filename.unlink)["status"], "unknown")
        self.assertEqual(self.b.pushes, 0)
        self.assertFalse(self.p.calls)

    def test_last_parent_guard_loss_prevents_post(self):
        self.check_late_guard_loss(after_post=False)

    def test_last_parent_guard_loss_prevents_put(self):
        self.check_late_guard_loss(after_post=True)

    def check_late_guard_loss(self, *, after_post):
        self.call("observe", initialize=True)
        filename = self.root / "witness-pr-sequence.json"
        def lose_parent():
            if self.b.pushes and (not after_post or self.p.writes()):
                filename.unlink()
        result = self.call("advance", before_write=lose_parent)
        self.assertNotEqual(result["status"], "merged")
        self.assertFalse(filename.exists(), "the final guard must actually fire")
        self.assertEqual(self.b.pushes, 1)
        self.assertEqual([call[0] for call in self.p.writes()], ["POST"] if after_post else [])
        self.sequence = self.new_sequence()
        self.assertEqual(self.call("advance")["status"], "unknown")
        self.assertEqual([call[0] for call in self.p.writes()], ["POST"] if after_post else [])

    def test_bound_state_rejects_other_sequence_schema(self):
        self.call("observe", initialize=True)
        filename = self.root / "witness-pr-sequence.json"
        state = json.loads(filename.read_bytes())
        state["schema"] = "lmdj.candidate-pr-sequence.v1"
        filename.write_bytes(canonical_json(state))
        with self.assertRaises(CandidateSequenceError): self.call("advance")
        self.assertEqual(self.b.pushes, 0)

    def test_parent_requires_its_concrete_children(self):
        with self.assertRaises(CandidateSequenceError):
            CandidatePrSequence(self.root, branch=self.sequence.branch, pr=self.sequence.pr)

    def test_actual_death_after_branch_recovers_next_leg(self):
        self.call("observe", initialize=True)
        original = WitnessPrSequence._save
        def terminate(journal, state, phase):
            original(journal, state, phase)
            if phase == "pr-initializing": os._exit(38)
        child = os.fork()
        if child == 0:
            with patch.object(WitnessPrSequence, "_save", side_effect=terminate): self.call("advance")
            os._exit(99)
        _, result = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(result), 38)
        self.assertEqual(self.b.remote_sha(), self.b.spec["head_sha"])
        self.sequence = self.new_sequence()
        self.assertEqual(self.call("advance")["status"], "merged")
        self.assertEqual(self.b.pushes, 0)


class WitnessJourneyTest(task_fixture.TaskFixture):
    def test_actual_task_bytes_reach_real_remote_squash_and_cold_consumer(self):
        self.journey(corrupt=False)

    def test_changed_far_side_witness_is_not_merged_acceptance_or_replayed(self):
        self.journey(corrupt=True)

    def journey(self, *, corrupt):
        # Snapshot is the narrow fixture; official witness bytes and Task are
        # real. The prior retained full Portal journey proves full snapshots.
        task = self.prepare_task()
        history = (self.journal / "witness-state.json").read_bytes()
        binding_raw = (self.task_journal / "binding.json").read_bytes()
        raw = self.artifact.read_bytes()
        b, p = WitnessBranchTest(), WitnessPrTest()
        for fixture in (b, p):
            fixture.setUp()
            self.addCleanup(fixture.doCleanups)
        b.repo = self.destination
        b.spec = dict(operation_id=task["operation_id"], request_sha256=task["request_sha256"],
            repository_id=12, actor_id=34, base_revision=task["base_revision"], head_sha=task["commit"],
            tree_sha=task["tree"], target_revision=task["target_revision"], product_build=self.source["product_build"],
            source_sha=self.source["commit"], witness_receipt_sha256=task["receipt_sha256"],
            task_binding_sha256=sha256(binding_raw).hexdigest(),
            task_evidence_sha256=canonical_sha256({"fixture_task_phases":self.phases}), witness=task["witness"])
        # This digest names actual narrow fixture checks, not full Portal gates.
        root = b.root / "sequence"
        b.journal, p.root = root / "branch", root / "pr"
        p.spec, p.document = deepcopy(b.spec), pr_document(b.spec)
        b.ref = "refs/heads/" + p.document["head"]
        far = b.root / "far"
        b.git("clone", str(b.remote), str(far))
        b.git("-C", str(far), "config", "user.name", "Fixture")
        b.git("-C", str(far), "config", "user.email", "fixture@example.invalid")
        merged = []
        verified_blobs = []
        source_results = []
        source_verifier = CandidateWitnessSourceVerifier(self.task)
        def source_check(merge=None):
            return source_verifier.verify(b.spec, receipt=self.receipt, request=self.request,
                source=self.source, cut=self.cut_receipt, frozen=self.fixture.frozen,
                main_revision=self.main, merge_revision=merge)
        self.assertIsNone(source_check()["merge_sha"])
        original_http = p.http
        def http(method, url, headers, body):
            if method == "GET" and url.endswith("/git/ref/heads/" + p.document["head"]):
                # Keep this local read outside the scratch-transport seam.
                self.assertEqual(b.git("-C", str(b.remote), "rev-parse", b.ref).strip(), task["commit"])
            response = original_http(method, url, headers, body)
            if method == "GET" and url.endswith("/branches/main"):
                value = json.loads(response.body)
                value["commit"]["sha"] = merged[0] if merged else self.base
                return HttpResponse(response.status, response.headers, canonical_json(value))
            return response
        p.client._http_transport = http
        original_row = p.new_row
        def new_row():
            row = original_row()
            row["base"]["sha"] = self.base
            return row
        p.new_row = new_row
        def merge_row():
            b.git("-C", str(far), "fetch", "origin", b.ref)
            b.git("-C", str(far), "checkout", "-b", "main", self.base)
            b.git("-C", str(far), "merge", "--squash", task["commit"])
            if corrupt:
                (far / self.witness_name).write_bytes(raw + b" ")
                b.git("-C", str(far), "add", "--", self.witness_name)
            b.git("-C", str(far), "-c", "commit.gpgsign=false", "commit", "-m", "fixture witness squash")
            sha = b.git("-C", str(far), "rev-parse", "HEAD").strip()
            merged.append(sha)
            # Reproduce far-side object availability explicitly. The production
            # source verifier never fetches on miss or moves a retained ref.
            b.git("-C", str(self.destination), "fetch", "--no-tags", str(far), sha)
            self.main = sha
            p.row.update(merged=True, state="closed", merged_at="2026-09-14T00:00:00Z", merge_commit_sha=sha)
        p.merge_row = merge_row
        def authorize(spec):
            self.assertEqual(spec, b.spec)
            self.assertEqual((self.task_journal / "binding.json").read_bytes(), binding_raw)
            self.assertEqual((self.journal / "witness-state.json").read_bytes(), history)
            self.assertEqual(self.task.git("cat-file", "blob", task["commit"] + ":" + self.witness_name), raw)
        def verify_merged(spec, row, review):
            self.assertEqual(review, {"sha256":"4" * 64, "reference":"review:fixture"})
            self.assertEqual(row["merge_commit_sha"], merged[0])
            self.assertEqual(b.git("-C", str(far), "rev-parse", "HEAD^").strip(), self.base)
            actual = branch_fixture.subprocess.check_output(
                ["git", "-C", str(far), "cat-file", "blob", merged[0] + ":" + self.witness_name])
            verified_blobs.append(actual)
            try:
                proof = source_check(merged[0])
            except WitnessSourceError as error:
                self.assertTrue(corrupt, str(error))
                self.assertIn("squash differs", str(error))
                source_results.append("refused")
                return Observation("conflict", None)
            source_results.append(proof)
            self.assertEqual(actual, raw)
            self.assertEqual(b.git("-C", str(far), "rev-parse", "HEAD^{tree}").strip(), task["tree"])
            return Observation("verified", {"sha256":canonical_sha256({"merge":merged[0], "witness":task["witness"]}),
                                             "reference":"fixture-merged:" + merged[0]})
        def new_sequence():
            branch = WitnessBranch(b.journal, b.repo, token="SECRET-TOKEN", authorize=authorize)
            branch.api = b.api
            pr = WitnessPullRequest(p.root, api=p.client.witness_pr_request,
                authorize=authorize, review=p.review, verify_merged=verify_merged)
            return WitnessPrSequence(root, branch=branch, pr=pr)
        with patch.object(branch_fixture.module.subprocess, "run", side_effect=b.transport):
            sequence = new_sequence()
            self.assertEqual(sequence.observe(b.spec, initialize=True)["status"], "absent")
            result = sequence.advance(b.spec, before_write=lambda: authorize(b.spec))
            self.assertEqual(result["status"], "conflict" if corrupt else "merged")
            self.assertEqual(new_sequence().observe(b.spec), result)
            self.assertEqual(new_sequence().advance(b.spec, before_write=lambda: authorize(b.spec)), result)
        self.assertTrue(verified_blobs, "far-side blob verification must actually fire")
        self.assertEqual(set(verified_blobs), {raw + b" " if corrupt else raw})
        self.assertTrue(source_results, "production source proof must actually fire")
        if corrupt:
            self.assertEqual(set(source_results), {"refused"})
        else:
            self.assertTrue(all(value["merge_sha"] == merged[0] for value in source_results))
        self.assertEqual(b.pushes, 1)
        self.assertEqual([call[0] for call in p.writes()], ["POST", "PUT"])
        self.assertEqual(len(merged), 1)
        self.assertEqual(self.task.revision("HEAD"), task["commit"])
        self.assertEqual((self.journal / "witness-state.json").read_bytes(), history)


if __name__ == "__main__":
    unittest.main()
