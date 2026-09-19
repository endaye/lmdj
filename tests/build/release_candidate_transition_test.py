#!/usr/bin/env python3
"""Actual composed candidate; temporary Git/official witness, fake review/API.

Snapshot, Portal-check and install CONTENT are small fixtures. They execute via
the actual durable subprocess boundary but are not real npm/full Portal proof.
The full Portal journey is the separate content acceptance leg.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import release_fixture_interpreter as interpreter
sys.path.insert(0, str(ROOT / "tests/build"))
import release_candidate_witness_test as fixture
import release_orchestration_driver_test as driver_fixture
from tools.release import evidence_branch
from tools.release.candidate_checks import CandidateTaskChecks
from tools.release.candidate_transition import CandidateTransition, CandidateTransitionError
from tools.release.github_api import GitHubClient, HttpResponse
from tools.release.model import canonical_json, canonical_sha256
from tools.release.orchestration import RequestJournal
from tools.release.orchestration_driver import Observation, ReleaseDriver


class TransitionFixture(fixture.WitnessFixture):
    def _prepare_seed(self):
        material = fixture.cut_fixture.snapshot_fixture.fixture_module.material_fixture.MaterialTest
        original = material.commit
        original_setup = material.setUp
        def canonical_setup(item):
            original_setup(item)
            # Bind the canonical request before material/source generation,
            # using a new empty catalogue, never editing producer receipts.
            item.request.update(repository="endaye/lmdj", policy_digest=driver_fixture.POLICY.digest,
                                control_revision=item.base)
            item.state = item.container / "canonical-state"
            item.tool = fixture.cut_fixture.snapshot_fixture.fixture_module.material_fixture.CandidateBuildMaterial(item.root, item.state)
            item.tool.reservations.enroll(item.request["repository"])
        def seeded(item):
            filename = item.root / "tests/build/ci_change_scope_test.py"
            filename.parent.mkdir(parents=True, exist_ok=True)
            filename.write_text("print('ownership fixture')\n")
            return original(item)
        script = fixture.SCRIPT.replace("*) exit 64 ;;", """check)
  printf 'check\\n' >> .fixture-check-calls
  printf 'portal fixture\\n'
  ;;
install) printf 'install\\n' >> .fixture-install-calls ;;
*) exit 64 ;;""")
        with patch.object(material, "commit", seeded), patch.object(material, "setUp", canonical_setup), patch.object(fixture, "SCRIPT", script):
            super()._prepare_seed()

    def prepare_cut(self):
        checks = CandidateTaskChecks(self.cut, control_revision=self.fixture.base,
                                     authorize=lambda scope: None, path=interpreter.fixture_path())
        checked = checks.prepare(request=self.request, source=self.source, snapshot_sha256=self.receipt["sha256"],
            author_name="Fixture", author_email="fixture@example.invalid", timestamp=2000000000)
        type(self).seed_checked_cut = deepcopy(checked)
        return checked["cut"]

    def setUp(self):
        super().setUp()
        self.main = self.fixture.base
        self.checked = deepcopy(self.seed_checked_cut)
        self.checks = CandidateTaskChecks(self.cut, control_revision=self.fixture.base,
            authorize=lambda scope: None, path=interpreter.fixture_path())
        self.parent_root = self.root.parent / "release-parent"
        self.transition_root = self.root.parent / "candidate-transition"
        self.destination = self.root.parent / "witness-task"
        self.remote = self.root.parent / "remote.git"
        self.tool.git("init", "--bare", str(self.remote))
        self.real_run = subprocess.run
        self.calls, self.rows, self.pushes = [], {}, []
        self.review_status = {"candidate":"verified", "witness":"verified"}
        self.merged_status = {"candidate":"verified", "witness":"verified"}
        self.authorized = True
        self.client = GitHubClient(token="FIXTURE-NOT-A-SECRET", http_transport=self.http)
        self.transition = self.new_transition()
        self.operation = dict(step="candidate", operation_id=self.source["operation_id"])
        # Only transport's canonical-remote seam changes; all Git effects are
        # real create-only pushes and source/Task object proofs remain actual.
        self.remote_patch = patch.object(evidence_branch, "REMOTE", self.remote.as_uri())
        self.remote_patch.start()
        self.addCleanup(self.remote_patch.stop)
        self.transport_patch = patch.object(evidence_branch.subprocess, "run", side_effect=self.transport)
        self.transport_patch.start()
        self.addCleanup(self.transport_patch.stop)

    def authorize(self, request):
        if not self.authorized or request != self.request:
            raise RuntimeError("PRIVATE-AUTHORITY")

    def review(self, kind, spec, row):
        self.assertEqual(row["head"]["sha"], spec["head_sha"])
        status = self.review_status[kind]
        return Observation(status, dict(sha256=canonical_sha256(dict(kind=kind, head=spec["head_sha"])),
            reference="fixture-independent-review:" + kind) if status == "verified" else None)

    def merged_review(self, kind, spec, row, receipt):
        self.assertTrue(row["merged"])
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt["sha256"], canonical_sha256(dict(kind=kind, head=spec["head_sha"])))
        status = self.merged_status[kind]
        return Observation(status, dict(sha256=canonical_sha256(dict(kind=kind, id=row["id"],
            merge=row["merge_commit_sha"], review=receipt)), reference="fixture-historical-review:" + kind)
            if status == "verified" else None)

    def new_transition(self):
        return CandidateTransition(self.transition_root, checks=self.checks, request=self.request,
            source=self.source, checked_cut=self.checked, frozen=self.fixture.frozen, repository_id=12,
            client=self.client, token="FIXTURE-NOT-A-SECRET", authorize=self.authorize,
            observe_main=lambda: self.main, review=self.review, verify_merged=self.merged_review,
            witness_root=self.destination, author_name="Fixture", author_email="fixture@example.invalid",
            timestamp=2000000001)

    def transport(self, command, **kwargs):
        if len(command) < 2 or not command[1].startswith("--git-dir="):
            return self.real_run(command, **kwargs)
        self.assertEqual(kwargs["env"]["GIT_ALLOW_PROTOCOL"], "https")
        if "init" not in command:
            self.assertIn(self.remote.as_uri(), command)
        else:
            self.assertIn("--bare", command)
        self.assertNotIn("FIXTURE-NOT-A-SECRET", " ".join(command))
        actual = deepcopy(kwargs)
        actual["env"]["GIT_ALLOW_PROTOCOL"] = "file"
        actual["env"].pop("GIT_CONFIG_VALUE_0")
        actual["env"]["GIT_CONFIG_COUNT"] = "0"
        if "push" in command:
            self.pushes.append(command[-1])
            self.assertIn("--force-with-lease=" + command[-1].split(":", 1)[1] + ":", command)
        return self.real_run(command, **actual)

    def http(self, method, url, headers, body):
        document = None if body is None else json.loads(body)
        self.calls.append((method, url, deepcopy(document)))
        suffix = url.removeprefix("/repos/endaye/lmdj")
        repo = dict(id=12, full_name="endaye/lmdj")
        code = 200
        if method == "GET":
            if suffix == "":
                value = repo
            elif suffix == "/user":
                value = dict(id=self.request["actor_id"])
            elif suffix == "/branches/main":
                value = dict(name="main", protected=True, commit=dict(sha=self.main))
            elif suffix.startswith("/git/ref/heads/"):
                ref = suffix.removeprefix("/git/ref/")
                oid = self.tool.git("--git-dir=" + str(self.remote), "rev-parse", "refs/" + ref).decode().strip()
                value = dict(ref="refs/" + ref, object=dict(type="commit", sha=oid))
            elif suffix.startswith("/pulls?"):
                head = parse_qs(urlsplit(suffix).query)["head"][0].removeprefix("endaye:")
                value = [dict(number=row["number"]) for row in self.rows.values() if row["head"]["ref"] == head]
            elif suffix.startswith("/pulls/"):
                value = deepcopy(self.rows[int(suffix.rsplit("/", 1)[1])])
            else:
                raise AssertionError((method, suffix))
        elif method == "POST":
            self.assertEqual(suffix, "/pulls")
            number = len(self.rows) + 101
            oid = self.tool.git("--git-dir=" + str(self.remote), "rev-parse", "refs/heads/" + document["head"]).decode().strip()
            self.rows[number] = dict(id=number + 1000, number=number,
                html_url=f"https://github.com/endaye/lmdj/pull/{number}", user=dict(id=self.request["actor_id"]),
                title=document["title"], body=document["body"], state="open", draft=False,
                merged=False, merged_at=None, merge_commit_sha=None, mergeable=True,
                head=dict(ref=document["head"], sha=oid, repo=repo),
                base=dict(ref="main", sha=self.main, repo=repo))
            value, code = {}, 201
        elif method == "PUT":
            self.assertTrue(suffix.endswith("/merge"))
            row = self.rows[int(suffix.split("/")[2])]
            self.assertEqual(document, dict(sha=row["head"]["sha"], merge_method="squash"))
            self.assertFalse(row["merged"])
            # Real distinct single-parent squash. The candidate source verifier
            # and witness source verifier independently assert the exact tree.
            tree = self.tool.revision(row["head"]["sha"] + "^{tree}")
            self.main = self.commit_tree(tree, self.main)
            row.update(merged=True, state="closed", merged_at="2026-09-14T00:00:00Z", merge_commit_sha=self.main)
            value = {}
        else:
            raise AssertionError((method, suffix))
        return HttpResponse(code, {"Content-Type":"application/json"}, canonical_json(value))

    def parent_state(self):
        with RequestJournal(self.parent_root) as journal:
            return journal.read(self.request["id"])

    def enroll(self):
        with RequestJournal(self.parent_root) as journal:
            state = journal.create(self.request)
            self.assertEqual(self.transition.observe(state, self.operation).status, "absent")
            journal.begin(self.request["id"], "candidate")

    def advance_candidate(self):
        state = self.parent_state()
        return self.transition.advance(state, state["transitions"][-1], before_write=lambda: self.authorize(self.request))

    def mutations(self):
        return [method for method, _, _ in self.calls if method != "GET"]


class TransitionTest(TransitionFixture):
    def _unknown_cut_write(self, method):
        self.enroll()
        original = self.client._http_transport
        def uncertain(sent, url, headers, body):
            if sent == method:
                # No positive far-side receipt. The transport outcome alone
                # cannot tell the controller whether the effect happened.
                self.calls.append((sent, url, json.loads(body)))
                raise OSError("fixture transport outcome lost")
            return original(sent, url, headers, body)
        self.client._http_transport = uncertain
        self.assertEqual(self.advance_candidate()["status"], "unknown")
        expected = ["POST"] if method == "POST" else ["POST", "PUT"]
        self.assertEqual(self.mutations(), expected)
        self.client._http_transport = original
        self.transition = self.new_transition()
        state = self.parent_state()
        self.assertEqual(self.transition.observe(state, state["transitions"][-1]).status, "unknown")
        self.assertEqual(self.advance_candidate()["status"], "unknown")
        self.assertEqual(self.mutations(), expected)
        self.assertEqual(len(self.pushes), 1)
        self.assertEqual(self.witness_calls(), [])
        self.assertFalse(self.destination.exists())

    def test_unknown_cut_post_cannot_be_replayed_by_parent(self):
        self._unknown_cut_write("POST")

    def test_unknown_cut_put_cannot_be_replayed_by_parent(self):
        self._unknown_cut_write("PUT")

    def test_confirmed_witness_recovers_after_parent_checkpoint_interruption(self):
        self.enroll()
        original = self.transition.witness.run
        def interrupted(**inputs):
            original(**inputs)
            # Simulated controller termination after the actual child receipt,
            # before its parent checkpoint; not an OS process-death claim.
            raise SystemExit(41)
        self.transition.witness.run = interrupted
        with self.assertRaises(SystemExit) as stopped:
            self.advance_candidate()
        self.assertEqual(stopped.exception.code, 41)
        saved = json.loads((self.transition_root / self.transition.STATE).read_bytes())
        self.assertTrue(saved["witness_started"])
        self.assertIsNone(saved["witness"])
        self.assertEqual(self.witness_calls(), ["generate", "verify"])
        self.transition = self.new_transition()
        state = self.parent_state()
        self.assertEqual(self.transition.observe(state, state["transitions"][-1]).status, "pending")
        recovered = json.loads((self.transition_root / self.transition.STATE).read_bytes())
        self.assertIsNotNone(recovered["witness"])
        self.assertEqual(recovered["witness"]["receipt"]["witness"]["sha256"],
                         sha256(self.artifact.read_bytes()).hexdigest())
        self.assertEqual(self.witness_calls(), ["generate", "verify"])
        self.assertEqual(self.mutations(), ["POST", "PUT"])
        self.assertFalse(self.destination.exists())

    def test_started_workspace_without_child_enrollment_is_not_recreated(self):
        self.enroll()
        def interrupted(**inputs):
            raise SystemExit(41)
        self.transition.workspace.prepare = interrupted
        with self.assertRaises(SystemExit) as stopped:
            self.advance_candidate()
        self.assertEqual(stopped.exception.code, 41)
        saved = json.loads((self.transition_root / self.transition.STATE).read_bytes())
        self.assertTrue(saved["workspace_started"])
        self.assertIsNone(saved["workspace"])
        self.assertFalse((self.transition_root / "workspace" / self.transition.workspace.MARKER).exists())
        self.transition = self.new_transition()
        self.assertEqual(self.advance_candidate()["status"], "unknown")
        self.assertFalse((self.transition_root / "workspace" / self.transition.workspace.MARKER).exists())
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.witness_calls(), ["generate", "verify"])
        self.assertEqual(self.mutations(), ["POST", "PUT"])

    def test_main_observer_cannot_recreate_missing_parent_history(self):
        self.enroll()
        filename = self.transition_root / self.transition.STATE
        lost = False
        def main():
            nonlocal lost
            state = json.loads(filename.read_bytes())
            if state["witness"] is not None and state["workspace_base"] is None:
                filename.unlink()
                lost = True
            return self.main
        self.transition.observe_main = main
        with self.assertRaisesRegex(CandidateTransitionError, "history.*missing|history changed"):
            self.advance_candidate()
        self.assertTrue(lost)
        self.assertFalse(filename.exists())
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.mutations(), ["POST", "PUT"])
        self.assertEqual(self.witness_calls(), ["generate", "verify"])
        self.transition = self.new_transition()
        state = self.parent_state()
        with self.assertRaisesRegex(CandidateTransitionError, "history.*missing"):
            self.transition.observe(state, state["transitions"][-1])
        self.assertFalse(filename.exists())
        self.assertEqual(self.mutations(), ["POST", "PUT"])

    def test_original_authority_exception_has_no_secret_traceback(self):
        with RequestJournal(self.parent_root) as journal:
            state = journal.create(self.request)
        def authority(request):
            raise CandidateTransitionError("PRIVATE-AUTHORITY")
        self.transition.authorize = authority
        with self.assertRaises(CandidateTransitionError) as failure:
            self.transition.observe(state, self.operation)
        self.assertNotIn("PRIVATE-AUTHORITY", "".join(traceback.format_exception(failure.exception)))
        self.assertEqual(self.mutations(), [])
        self.assertEqual(self.pushes, [])

    def test_cut_merge_is_pending_until_the_reviewed_witness_squash(self):
        self.enroll()
        self.review_status["witness"] = "pending"
        result = self.advance_candidate()
        self.assertEqual(result["status"], "pending")
        self.assertEqual(self.mutations(), ["POST", "PUT", "POST"])
        self.assertEqual(self.witness_calls(), ["generate", "verify"])
        saved = json.loads((self.transition_root / self.transition.STATE).read_bytes())
        self.assertIsNotNone(saved["cut_merge"])
        self.assertIsNone(saved["witness_merge"])
        self.assertEqual(saved["workspace_base"], saved["cut_merge"]["merge"]["merge_sha"])
        self.assertEqual((self.destination / ".fixture-install-calls").read_text().splitlines(), ["install"])
        self.assertEqual((self.destination / ".fixture-check-calls").read_text().splitlines(), ["check", "check"])
        self.transition = self.new_transition()
        state = self.parent_state()
        self.assertEqual(self.transition.observe(state, state["transitions"][-1]).status, "pending")
        self.assertEqual(self.mutations(), ["POST", "PUT", "POST"])
        self.review_status["witness"] = "verified"
        complete = self.advance_candidate()
        self.assertEqual(complete["status"], "verified")
        self.assertEqual(self.mutations(), ["POST", "PUT", "POST", "PUT"])
        candidate = complete["candidate"]
        self.assertEqual(candidate["target_revision"], self.rows[101]["merge_commit_sha"])
        self.assertEqual(candidate["witness_revision"], self.rows[102]["merge_commit_sha"])
        self.assertNotEqual(candidate["target_revision"], candidate["witness_revision"])
        self.assertEqual(self.tool.git("show", self.main + ":" + candidate["witness"]["path"]),
                         self.artifact.read_bytes())
        self.transition = self.new_transition()
        self.assertEqual(self.advance_candidate(), complete)
        self.assertEqual(self.transition.verified_candidate(state, state["transitions"][-1]), candidate)
        # Driver must consume the same verified candidate and stop at the
        # separate complete-test boundary, not invoke its opaque candidate.
        effects = self.root.parent / "later-effects"
        effects.mkdir()
        backend = driver_fixture.Backend(effects)
        backend.authenticate = lambda request, policy: self.authorize(request)
        backend.override["verification"] = Observation("pending")
        driver = ReleaseDriver(self.parent_root, driver_fixture.POLICY, backend, candidate=self.transition)
        driven = driver.resume(self.request["id"])
        self.assertEqual((driven.status, driven.step, driven.verified_steps), ("pending", "verification", ("candidate",)))
        self.assertEqual(self.parent_state()["transitions"][0]["evidence"], complete["evidence"])
        self.assertEqual(backend.calls, [])
        self.assertEqual(len(self.pushes), 2)
        self.assertEqual(self.witness_calls(), ["generate", "verify"])
        # A later main commit does not select a new candidate or rebind either
        # squash receipt. This is an actual descendant commit in fixture Git.
        self.main = self.commit_tree(self.tool.revision(self.main + "^{tree}"), self.main)
        self.assertNotEqual(self.main, candidate["witness_revision"])
        original_history = (self.transition_root / self.transition.STATE).read_bytes()
        self.transition = self.new_transition()
        self.assertEqual(self.transition.verified_candidate(state, state["transitions"][-1]), candidate)
        self.assertEqual((self.transition_root / self.transition.STATE).read_bytes(), original_history)
        self.assertEqual(self.mutations(), ["POST", "PUT", "POST", "PUT"])
        self.assertEqual(self.witness_calls(), ["generate", "verify"])
        # Finally corrupt the real retained witness. A cached successful parent
        # receipt must not hide the lost source artifact after cold reopen.
        self.artifact.write_bytes(self.artifact.read_bytes() + b"\n")
        self.transition = self.new_transition()
        with self.assertRaises(CandidateTransitionError):
            self.transition.verified_candidate(state, state["transitions"][-1])
        self.assertEqual(self.mutations(), ["POST", "PUT", "POST", "PUT"])
        self.assertEqual(len(self.pushes), 2)
        self.assertEqual(self.witness_calls(), ["generate", "verify"])

    def test_cut_review_pending_cannot_generate_witness_or_install(self):
        self.review_status["candidate"] = "pending"
        effects = self.root.parent / "later-effects"
        effects.mkdir()
        backend = driver_fixture.Backend(effects)
        backend.authenticate = lambda request, policy: self.authorize(request)
        driver = ReleaseDriver(self.parent_root, driver_fixture.POLICY, backend, candidate=self.transition)
        result = driver.run(self.request)
        self.assertEqual((result.status, result.step, result.verified_steps), ("pending", "candidate", ()))
        self.assertEqual(self.mutations(), ["POST"])
        self.assertEqual(self.witness_calls(), [])
        self.assertFalse(self.destination.exists())
        self.assertEqual(len(self.pushes), 1)
        self.assertEqual(backend.calls, [])
        self.transition = self.new_transition()
        driver = ReleaseDriver(self.parent_root, driver_fixture.POLICY, backend, candidate=self.transition)
        self.assertEqual(driver.resume(self.request["id"]), result)
        self.assertEqual(self.mutations(), ["POST"])
        self.assertEqual(backend.calls, [])


if __name__ == "__main__":
    unittest.main()
