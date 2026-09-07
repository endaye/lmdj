#!/usr/bin/env python3
"""Prospective release evidence uses the complete self-test protocol, not scope."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import hashlib
import json
import base64
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/ci"))
import self_test
from tools.release.ci_evidence import verify_release_ci
from tools.release.github_api import SelfTestRunProjection, RunProjection, CiScopeUnavailableError
from tools.release.model import load_policy, load_ledger_document, canonical_json, Disposition, ReleaseModelError

TARGET, CONTROL = "a" * 40, "b" * 40
POLICY = self_test.load_policy(ROOT / "scripts/ci/self_test_policy.json")


def verdict():
    identity = self_test.Identity(self_test.EVIDENCE_SCHEMA, "candidate", CONTROL, TARGET, 123, 1, POLICY.revision)
    rows = [self_test.Observation(suite.id, job, 123, 1, TARGET, "success")
            for suite in POLICY.suites for job in suite.jobs]
    document = self_test.aggregate(identity, POLICY, rows).as_document()
    document["evidence_digest"] = self_test.digest_of(document)
    return document


def reference(document=None):
    doc = document or verdict()
    return {"schema": "lmdj.ci-self-test.v1", "request_kind": doc["identity"]["request_kind"],
            "control_revision": CONTROL, "run_attempt": 1,
            "policy_revision": POLICY.revision, "evidence_digest": doc["evidence_digest"]}


class FakeGitHub:
    def __init__(self):
        self.run = SelfTestRunProjection(123, "workflow_dispatch", CONTROL, "main", "Core CI", "completed", "success", 1)
        self.historical_run = self.run
        self.document = verdict()
        self.calls = []
        self.error = None
    def get_self_test_run(self, repository, run_id, *, run_attempt=None):
        self.calls.append("run" if run_attempt is None else f"attempt:{run_attempt}")
        return self.run if run_attempt is None else self.historical_run
    def verify_self_test_provenance(self, repository, run, target_revision):
        self.calls.append("provenance")
        return "d" * 40
    def get_self_test_verdict(self, repository, run, target_revision):
        self.calls.append("artifact")
        if self.error:
            raise self.error
        return deepcopy(self.document)
    def get_self_test_policy(self, repository, revision):
        self.calls.append("policy")
        return POLICY


class SelfTestReleaseEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy(ROOT / "tools/release/policy.json")
        self.github = FakeGitHub()
    def intent(self, ref=True, disposition="releasable"):
        item = {"tag": "module/application-facade/v1.0.1", "kind": "module",
                "identity": "application-facade@1.0.1", "target_revision": TARGET,
                "disposition": disposition, "profile": "source-only", "merged_main_run_id": 123,
                "evidence_paths": ["evidence.md"]}
        if ref:
            item["self_test_evidence"] = reference(self.github.document)
        return load_ledger_document({"schema": "lmdj.release-intents.v1", "entries": [item],
                                     "historical_exceptions": []}, self.policy).entries[0]
    def verify(self, **kwargs):
        return verify_release_ci(self.github, policy=self.policy, intent=self.intent(**kwargs))
    def test_new_policy_rejects_old_fourteen_lane_reference(self):
        self.assertEqual(self.verify(ref=False).code, "unverifiable")
        self.assertEqual(self.github.calls, [])
    def test_target_is_not_control_and_all_sixteen_suites_pass(self):
        self.assertEqual(len(POLICY.suites), 16)
        result = self.verify()
        self.assertEqual(result.code, "ok", result.message)
        self.assertEqual(result.run.head_sha, CONTROL)
    def test_missing_stress_digest_wrong_target_and_nonpass_fail(self):
        for mutation in ("core_tsan_stress", "core_release_stress", "digest", "target", "status", "attempt"):
            with self.subTest(mutation=mutation):
                self.github.document = verdict()
                if mutation in ("core_tsan_stress", "core_release_stress"):
                    self.github.document["suites"] = [suite for suite in self.github.document["suites"] if suite["id"] != mutation]
                if mutation == "digest": self.github.document["evidence_digest"] = "f" * 64
                if mutation == "target": self.github.document["identity"]["target_revision"] = "c" * 40
                if mutation == "status": self.github.document["status"] = "failed"
                if mutation == "attempt": self.github.document["identity"]["run_attempt"] = 2
                if mutation != "digest":
                    self.github.document["evidence_digest"] = self_test.digest_of({key: value for key, value in self.github.document.items() if key != "evidence_digest"})
                self.assertNotEqual(self.verify().code, "ok")
    def test_new_published_reference_does_not_require_retained_artifact(self):
        self.github.error = CiScopeUnavailableError("expired")
        self.assertEqual(self.verify(disposition="published").code, "ok")
        self.assertNotIn("artifact", self.github.calls)
    def test_prospective_expiration_fails_closed(self):
        self.github.error = CiScopeUnavailableError("expired")
        self.assertEqual(self.verify().code, "unverifiable")
    def test_rerun_is_rejected_even_when_successful(self):
        self.github.run = replace(self.github.run, run_attempt=2)
        self.assertEqual(self.verify().code, "conflict")
    def test_later_failed_rerun_does_not_rewrite_published_attempt_one(self):
        self.github.run = replace(self.github.run, run_attempt=2, conclusion="failure")
        self.assertEqual(self.verify().code, "conflict")
        self.assertEqual(self.verify(disposition="published").code, "ok")
        self.assertIn("attempt:1", self.github.calls)
        self.assertNotIn("artifact", self.github.calls)

    def test_closed_reference_rejects_unknown_fields_bad_digest_and_boolean_attempt(self):
        original = self.intent()
        for field, value in (("surprise", True), ("evidence_digest", "green"), ("run_attempt", True),
                             ("run_attempt", 2), ("schema", "lmdj.ci-scope.v2")):
            with self.subTest(field=field, value=value):
                item = {"tag": original.tag, "kind": original.kind.value, "identity": original.identity,
                        "target_revision": TARGET, "disposition": "releasable", "profile": "source-only",
                        "merged_main_run_id": 123, "evidence_paths": ["evidence.md"],
                        "self_test_evidence": dict(reference(), **{field: value})}
                with self.assertRaises(ReleaseModelError):
                    load_ledger_document({"schema": "lmdj.release-intents.v1", "entries": [item], "historical_exceptions": []}, self.policy)

    def test_schedule_and_node_can_be_explicitly_reused_for_same_candidate(self):
        for kind, event in (("schedule", "schedule"), ("node", "workflow_dispatch")):
            with self.subTest(kind=kind):
                self.github.run = replace(self.github.run, event=event)
                self.github.document = verdict()
                self.github.document["identity"]["request_kind"] = kind
                self.github.document["evidence_digest"] = self_test.digest_of({key: value for key, value in self.github.document.items() if key != "evidence_digest"})
                self.assertEqual(self.verify().code, "ok")
    def test_old_control_policy_and_missing_stress_policy_cannot_self_certify(self):
        for policy in (replace(POLICY, revision="f" * 64), replace(POLICY, suites=POLICY.suites[:-1])):
            with self.subTest(policy=policy.revision):
                self.github.get_self_test_policy = lambda repository, revision: policy
                self.assertEqual(self.verify().code, "conflict")

    def test_incomplete_or_unsuccessful_runs_are_not_candidate_proof(self):
        for status, conclusion in (("in_progress", None), ("completed", "failure"),
                                    ("completed", "cancelled"), ("completed", "timed_out"),
                                    ("completed", "skipped")):
            with self.subTest(status=status, conclusion=conclusion):
                self.github.run = replace(self.github.run, status=status, conclusion=conclusion)
                result = self.verify()
                self.assertEqual(result.code, "conflict")
                self.assertIn("why:", result.message)
                self.assertIn("remedy:", result.message)

    def test_real_transport_through_shared_validator_uses_one_policy_module(self):
        sys.path.insert(0, str(ROOT / "tests/build"))
        import release_github_api_test as fixtures
        from tools.release.github_api import GitHubClient, HttpResponse
        transport = fixtures.FakeTransport()
        client = GitHubClient(http_transport=transport, token="fixture-token")
        prefix = "/repos/endaye/lmdj"
        repo = {"id": 11, "full_name": "endaye/lmdj"}
        raw = fixtures.run_document(identifier=123, head_sha=CONTROL, run_attempt=1,
                                    repository=repo, head_repository=repo,
                                    name=f"Core CI / self-test {TARGET}")
        transport.json_route(f"{prefix}/actions/runs/123", raw)
        transport.json_route(f"{prefix}/actions/workflows/ci.yml", fixtures.workflow_document())
        authority = "d" * 40
        transport.json_route(f"{prefix}/branches/main", {"name": "main", "protected": True, "commit": {"sha": authority}})
        for base, head in (("22247897e9163a3f34e15f564bec133419d1f177", CONTROL), (CONTROL, authority), (TARGET, authority)):
            transport.json_route(f"{prefix}/compare/{base}...{head}", {"status": "ahead"})
        encoded = base64.b64encode((ROOT / "scripts/ci/self_test_policy.json").read_bytes()).decode()
        for revision in (CONTROL, authority):
            transport.json_route(f"{prefix}/contents/scripts/ci/self_test_policy.json?ref={revision}",
                                  {"type": "file", "path": "scripts/ci/self_test_policy.json", "encoding": "base64", "content": encoded})
        self.assertIsInstance(client.get_self_test_policy("endaye/lmdj", CONTROL), self_test.Policy)
        transport.json_route(f"{prefix}/actions/runs/123/attempts/1/jobs?per_page=100",
                              {"total_count": 1, "jobs": [fixtures.job_document(1, "Self-test verdict", run_id=123, head_sha=CONTROL)]})
        artifact = fixtures.artifact_document(name=f"self-test-verdict-{TARGET}-123-1", expires_at="2099-01-01T00:00:00Z",
                                              workflow_run={"id": 123, "repository_id": 11, "head_repository_id": 11, "head_branch": "main", "head_sha": CONTROL})
        transport.json_route(f"{prefix}/actions/runs/123/artifacts?per_page=100", {"total_count": 1, "artifacts": [artifact]})
        transport.route(artifact["archive_download_url"], HttpResponse(200, {"Content-Type": "application/zip"},
                        fixtures.scope_archive(members=(("verdict.json", json.dumps(verdict()).encode()),))))
        result = verify_release_ci(client, policy=self.policy, intent=self.intent())
        self.assertEqual(result.code, "ok", result.message)
        self.assertTrue(all(request[0] == "GET" for request in transport.requests))
        raw["workflow_id"] = 42
        transport.json_route(f"{prefix}/actions/runs/123", raw)
        result = verify_release_ci(client, policy=self.policy, intent=self.intent())
        self.assertEqual(result.code, "conflict")
        self.assertIn("stable workflow identity conflicts", result.message)
        self.assertIn("remedy:", result.message)


class SelfTestReleaseEntryPointsTest(unittest.TestCase):
    """Real orchestration + deterministic fake transports; never real release operations."""
    def fixture(self, *, transitions=False):
        # Reuse non-CI profile/signing fakes; select the real current policy and
        # real verifier rather than mocking the decision at an entry point.
        sys.path.insert(0, str(ROOT / "tests/build"))
        if transitions:
            import release_transitions_test as module
            fixture = module.ReleaseTransitionsTest()
        else:
            import release_prepare_test as module
            fixture = module.ReleasePrepareTest()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        fixture.policy = load_policy(ROOT / "tools/release/policy.json")
        return fixture
    def attach_evidence(self, fixture):
        evidence = FakeGitHub()
        for method in ("get_self_test_run", "verify_self_test_provenance", "get_self_test_policy", "get_self_test_verdict"):
            setattr(fixture.github, method, getattr(evidence, method))
        fixture.ledger = replace(fixture.ledger, entries=tuple(
            replace(intent, self_test_evidence=reference()) for intent in fixture.ledger.entries))
        return evidence
    def test_current_policy_old_green_scope_cannot_prepare_or_create_draft(self):
        from tools.release.prepare import prepare, PrepareError
        from tools.release.transitions import create_draft, TransitionError
        fixture = self.fixture()
        with self.assertRaisesRegex(PrepareError, "explicit complete self-test reference"):
            prepare(fixture.tag, fixture.context())
        self.assertIsNone(fixture.git.local_tag)
        self.assertEqual(fixture.github.remote_mutations, [])
        transition = self.fixture(transitions=True)
        transition.git.remote = transition.git.local
        with self.assertRaisesRegex(TransitionError, "CI evidence is invalid"):
            create_draft(transition.tag, transition.context())
        self.assertEqual(transition.github.create_calls, 0)
        self.assertEqual(transition.github.upload_calls, [])
    def test_remote_audit_uses_current_protocol_and_requires_actual_published_state(self):
        sys.path.insert(0, str(ROOT / "tests/build"))
        import release_ci_evidence_test as module
        from tools.release.audit import audit
        fixture = module.ProspectiveReleaseAuditTest()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        fixture.policy = load_policy(ROOT / "tools/release/policy.json")
        context = fixture.context()
        def finding():
            return next(item for item in audit(context, remote=True, tag=fixture.tag).findings if item.subject == fixture.tag)
        self.assertEqual(finding().code, "unverifiable")
        evidence = FakeGitHub()
        for method in ("get_self_test_run", "verify_self_test_provenance", "get_self_test_policy", "get_self_test_verdict"):
            setattr(context.github, method, getattr(evidence, method))
        intent = replace(context.ledger.entries[0], self_test_evidence=reference())
        context = replace(context, ledger=replace(context.ledger, entries=(intent,)))
        self.assertEqual(finding().code, "ok")
        # Merely changing an intent to published cannot manufacture the absent
        # remote tag/Release, even with a valid durable self-test reference.
        context = replace(context, ledger=replace(context.ledger, entries=(replace(intent, disposition=Disposition.PUBLISHED),)))
        self.assertNotEqual(finding().code, "ok")
    def test_prepare_binds_distinct_control_and_target_in_plan_and_rejects_wrong_binding(self):
        from tools.release.prepare import prepare, PrepareError
        fixture = self.fixture()
        evidence = self.attach_evidence(fixture)
        prepared = prepare(fixture.tag, fixture.context())
        document = json.loads((prepared.output_root / "release-plan.json").read_text())
        self.assertEqual(document["ci"]["head_sha"], CONTROL)
        self.assertEqual(document["ci"]["target_revision"], TARGET)
        self.assertEqual(document["ci"]["self_test_evidence"], reference())
        self.assertEqual(hashlib.sha256(canonical_json(document)).hexdigest(), prepared.digest)
        evidence.run = replace(evidence.run, head_sha="c" * 40)
        with self.assertRaises(PrepareError):
            prepare(fixture.tag, fixture.context())
    def prepared_transition(self):
        fixture = self.fixture(transitions=True)
        evidence = self.attach_evidence(fixture)
        document = fixture._plan()
        document["ci"] = {"run_id": 123, "event": "workflow_dispatch", "head_sha": CONTROL,
                          "conclusion": "success", "target_revision": TARGET, "self_test_evidence": reference()}
        output = fixture.root / "build/release" / fixture.tag
        (output / "release-plan.json").write_bytes(canonical_json(document))
        (output / "release-plan.sha256").write_text(hashlib.sha256(canonical_json(document)).hexdigest() + "\n")
        fixture.git.remote = fixture.git.local
        return fixture, evidence
    def test_published_new_reference_keeps_immutable_marker_after_artifact_expiry(self):
        from tools.release.transitions import create_draft, TransitionError
        fixture, evidence = self.prepared_transition()
        create_draft(fixture.tag, fixture.context())
        fixture.github.release = replace(fixture.github.release, draft=False)
        fixture.ledger = replace(fixture.ledger, entries=tuple(replace(i, disposition=Disposition.PUBLISHED) for i in fixture.ledger.entries))
        evidence.error = CiScopeUnavailableError("expired")
        evidence.run = replace(evidence.run, run_attempt=2, conclusion="failure")
        self.assertEqual(create_draft(fixture.tag, fixture.context()).status, "already-published")
        count = fixture.github.create_calls
        altered = dict(reference(), evidence_digest="f" * 64)
        fixture.ledger = replace(fixture.ledger, entries=tuple(replace(i, self_test_evidence=altered) for i in fixture.ledger.entries))
        with self.assertRaises(TransitionError):
            create_draft(fixture.tag, fixture.context())
        self.assertEqual(fixture.github.create_calls, count)
    def test_claimed_published_reference_cannot_create_missing_history_or_accept_wrong_signature(self):
        from tools.release.transitions import create_draft, TransitionError
        fixture, evidence = self.prepared_transition()
        fixture.ledger = replace(fixture.ledger, entries=tuple(replace(i, disposition=Disposition.PUBLISHED) for i in fixture.ledger.entries))
        for state in ("missing tag", "wrong signer", "missing release"):
            with self.subTest(state=state):
                fixture.git.remote = None if state == "missing tag" else fixture.git.local
                if state == "wrong signer":
                    fixture.git.remote = replace(fixture.git.local, signer_fingerprint="F" * 40)
                with self.assertRaises(TransitionError):
                    create_draft(fixture.tag, fixture.context())
                self.assertEqual(fixture.github.create_calls, 0)
                self.assertEqual(fixture.github.upload_calls, [])


    def test_fresh_remote_audit_binds_published_reference_to_permanent_v2_marker(self):
        sys.path.insert(0, str(ROOT / "tests/build"))
        import release_audit_test as module
        from tools.release.audit import audit
        from tools.release.transitions import marker_for_plan
        fixture = module.ReleaseAuditFixture()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        fixture.policy = load_policy(ROOT / "tools/release/policy.json")
        item = fixture.entry()
        tag = item["tag"]
        fixture.git.tags[tag] = fixture.tag_state()
        fixture.github.releases[tag] = fixture.release(tag)
        evidence = FakeGitHub()
        for method in ("get_self_test_run", "verify_self_test_provenance", "get_self_test_policy", "get_self_test_verdict"):
            setattr(fixture.github, method, getattr(evidence, method))
        item["self_test_evidence"] = reference()
        def finding():
            return next(result for result in audit(fixture.context([item]), remote=True, tag=tag).findings if result.subject == tag)
        # A v1 publication plus arbitrary new ledger references cannot
        # self-certify that a complete self-test was actually published.
        for digest in ("e" * 64, "f" * 64):
            item["self_test_evidence"] = dict(reference(), evidence_digest=digest)
            self.assertEqual(finding().code, "conflict")
        item["self_test_evidence"] = reference()
        document = {
            "schema": "lmdj.release-plan.v1", "tag": tag, "tag_object": module.TAG_OBJECT,
            "target_revision": TARGET, "kind": "module", "identity": item["identity"], "profile": "source-only",
            "ci": {"run_id": 123, "event": "workflow_dispatch", "head_sha": CONTROL, "conclusion": "success",
                   "target_revision": TARGET, "self_test_evidence": reference()},
        }
        marker = marker_for_plan(document, hashlib.sha256(canonical_json(document)).hexdigest())
        fixture.github.releases[tag] = fixture.release(tag, body=marker)
        evidence.error = CiScopeUnavailableError("expired")
        evidence.run = replace(evidence.run, run_attempt=2, conclusion="failure")
        self.assertEqual(finding().code, "ok")
        malformed = json.loads(marker.split(" ", 2)[2][:-4])
        malformed["ci"]["self_test_evidence"]["run_attempt"] = True
        fixture.github.releases[tag] = fixture.release(tag, body="<!-- lmdj.release-plan-marker.v2 " + json.dumps(malformed) + " -->")
        self.assertEqual(finding().code, "conflict")
        fixture.github.releases[tag] = fixture.release(tag, body=marker)
        for field in ("evidence_digest", "policy_revision", "control_revision", "run_id"):
            with self.subTest(field=field):
                item["self_test_evidence"] = reference()
                item["merged_main_run_id"] = 123
                evidence.historical_run = replace(evidence.historical_run, id=123, head_sha=CONTROL)
                if field == "run_id":
                    item["merged_main_run_id"] = 124
                    evidence.historical_run = replace(evidence.historical_run, id=124)
                elif field == "control_revision":
                    item["self_test_evidence"][field] = "c" * 40
                    evidence.historical_run = replace(evidence.historical_run, head_sha="c" * 40)
                else:
                    item["self_test_evidence"][field] = "f" * 64
                result = finding()
                self.assertEqual(result.code, "conflict")
                self.assertIn("permanent marker", result.message)
        self.assertEqual(fixture.github.mutations, [])
        self.assertEqual(fixture.git.mutations, [])


if __name__ == "__main__":
    unittest.main()
