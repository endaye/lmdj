#!/usr/bin/env python3
"""The trusted entry gates bind production verifiers and never invent approval."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/build"))
from tools.release.entry_gates import (  # noqa: E402
    EntryGateError,
    authority_gate,
    main_observation,
    merged_gate,
    production_review_reader,
    review_gate,
)
from tools.release.model import canonical_sha256  # noqa: E402
from tools.release.orchestration_driver import Observation  # noqa: E402

MAIN = "c" * 40
CONTROL = "d" * 40
DIGEST = "e" * 64
HEAD = "a" * 40
MERGE = "b" * 40


def request(**changes):
    document = {"id": "release-" + "0" * 16, "repository": "endaye/lmdj",
                "actor_id": 34, "authority_ref": "issue:1301",
                "policy_digest": DIGEST, "control_revision": CONTROL,
                "base_revision": CONTROL, "mode": "new", "requested_tag": None}
    document.update(changes)
    return document


class GitStub:
    """The canonical Git interface the gates read, with controlled answers."""

    def __init__(self, *, main=MAIN, ancestors=(CONTROL, MERGE)):
        self.main, self.ancestors = main, set(ancestors)

    def main_revision(self):
        return self.main

    def is_main_ancestor(self, target):
        return target in self.ancestors


class GitHubStub:
    def __init__(self, actor=34):
        self.actor = actor

    def get_authenticated_actor(self):
        return self.actor


class PolicyStub:
    digest = DIGEST


class AuthorityGateTest(unittest.TestCase):
    def gate(self, **changes):
        return authority_gate(github=GitHubStub(), git=GitStub(),
                              policy=PolicyStub(), request=request(**changes))

    def test_the_original_request_passes_and_drift_fails_closed(self):
        authorize = self.gate()
        authorize(request())  # no raise
        with self.assertRaises(EntryGateError):
            authorize(request(authority_ref="issue:other"))
        with self.assertRaises(EntryGateError):
            authorize(request(actor_id=35))

    def test_a_mispinned_request_is_refused_at_assembly(self):
        with self.assertRaises(EntryGateError):
            self.gate(policy_digest="f" * 64)

    def test_live_authority_loss_fails_closed(self):
        authorize = authority_gate(github=GitHubStub(actor=35), git=GitStub(),
                                   policy=PolicyStub(), request=request())
        with self.assertRaises(EntryGateError):
            authorize(request())
        unreachable = authority_gate(github=GitHubStub(),
                                     git=GitStub(ancestors=()),
                                     policy=PolicyStub(), request=request())
        with self.assertRaises(EntryGateError):
            unreachable(request())

    def test_a_malformed_request_is_refused_at_assembly(self):
        with self.assertRaises(Exception):
            self.gate(mode="tag")


class DispatchAuthorityTest(unittest.TestCase):
    def spec(self, **changes):
        from tools.release.model import canonical_sha256

        document = {"request_sha256": canonical_sha256(request()), "actor_id": 34,
                    "control_revision": CONTROL}
        document.update(changes)
        return document

    def gate(self, **overrides):
        from tools.release.entry_gates import dispatch_authority

        arguments = dict(github=GitHubStub(), git=GitStub(),
                         policy=PolicyStub(), request=request())
        arguments.update(overrides)
        return dispatch_authority(**arguments)

    def test_the_bound_spec_passes_and_drift_fails_closed(self):
        authorize = self.gate()
        authorize(self.spec())  # no raise
        with self.assertRaises(EntryGateError):
            authorize(self.spec(request_sha256="0" * 64))
        with self.assertRaises(EntryGateError):
            authorize(self.spec(actor_id=35))
        with self.assertRaises(EntryGateError):
            authorize(self.spec(control_revision="9" * 40))
        with self.assertRaises(EntryGateError):
            authorize("not-a-spec")

    def test_a_spec_without_a_control_revision_still_binds_the_request(self):
        # The PR-sequence specs carry no control revision; the request binding
        # and actor checks still apply.
        spec = self.spec()
        del spec["control_revision"]
        self.gate()(spec)  # no raise
        with self.assertRaises(EntryGateError):
            self.gate()(self.spec(control_revision="9" * 40))

    def test_live_authority_loss_fails_closed(self):
        with self.assertRaises(EntryGateError):
            self.gate(github=GitHubStub(actor=35))(self.spec())
        with self.assertRaises(EntryGateError):
            self.gate(git=GitStub(ancestors=()))(self.spec())
        drifted = PolicyStub()
        drifted.digest = "f" * 64
        with self.assertRaises(EntryGateError):
            self.gate(policy=drifted)(self.spec())


class MainObservationTest(unittest.TestCase):
    def test_the_fetched_canonical_revision_is_returned(self):
        self.assertEqual(main_observation(git=GitStub())(), MAIN)

    def test_an_invalid_observation_fails_closed(self):
        with self.assertRaises(EntryGateError):
            main_observation(git=GitStub(main="not-a-sha"))()


class MergedGateTest(unittest.TestCase):
    """The merged gate against a real Git repository and the real GitRepository."""

    def setUp(self):
        import subprocess
        import tempfile

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name).resolve() / "repo"
        self.repo.mkdir()

        def git(*args):
            subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C",
                            str(self.repo), *args], check=True, capture_output=True)

        self.git = git
        git("init", "-q", "-b", "main")
        git("config", "user.name", "Seeder")
        git("config", "user.email", "seed@example.invalid")
        git("commit", "-q", "--allow-empty", "-m", "base")
        self.base = self.rev("HEAD")
        # The reviewed head, then its single-parent squash on main.
        git("checkout", "-q", "-b", "reviewed")
        (self.repo / "reviewed.txt").write_text("reviewed content\n")
        git("add", "reviewed.txt")
        git("commit", "-q", "-m", "reviewed head")
        self.head = self.rev("HEAD")
        git("checkout", "-q", "main")
        git("merge", "--squash", "reviewed")
        git("commit", "-q", "-m", "squash of reviewed head")
        self.squash = self.rev("HEAD")
        # A two-parent merge commit, also on main: reachable but not a squash.
        git("merge", "--no-ff", "-m", "not a squash", "reviewed")
        self.merge_commit = self.rev("HEAD")
        git("update-ref", "refs/lmdj-release/origin-main", "main")
        # A commit that never lands on main.
        git("checkout", "-q", "-b", "stray", self.base)
        git("commit", "-q", "--allow-empty", "-m", "stray")
        self.stray = self.rev("HEAD")
        git("checkout", "-q", "main")
        from tools.release.git_repository import GitRepository

        self.repository = GitRepository(self.repo)

    def rev(self, ref):
        import subprocess

        return subprocess.run(["git", "-C", str(self.repo), "rev-parse", ref],
                              check=True, capture_output=True).stdout.decode().strip()

    def row(self, **changes):
        document = {"merged": True, "merge_commit_sha": self.squash,
                    "number": 7, "head": {"sha": self.head}}
        document.update(changes)
        return document

    def receipt(self, kind="candidate"):
        return {"sha256": DIGEST, "reference": f"review:{kind}:pr-7"}

    def gate(self):
        return merged_gate(git=self.repository)

    def test_the_merged_squash_binds_merge_and_review(self):
        observed = self.gate()("candidate", {"head_sha": self.head}, self.row(),
                               self.receipt())
        self.assertIsInstance(observed, Observation)
        self.assertEqual(observed.status, "verified")
        self.assertEqual(observed.evidence["reference"],
                         "merged:candidate:" + self.squash)
        self.assertEqual(observed.evidence["sha256"],
                         canonical_sha256({"kind": "candidate",
                                           "merge": self.squash,
                                           "review": DIGEST}))

    def test_every_unproven_leg_fails_closed(self):
        gate = self.gate()
        with self.assertRaises(EntryGateError):
            gate("candidate", {"head_sha": self.head}, self.row(merged=False),
                 self.receipt())
        with self.assertRaises(EntryGateError):
            gate("candidate", {"head_sha": self.head},
                 self.row(merge_commit_sha="short"), self.receipt())
        with self.assertRaises(EntryGateError):
            gate("candidate", {"head_sha": self.head},
                 self.row(head={"sha": "9" * 40}), self.receipt())
        with self.assertRaises(EntryGateError):
            gate("candidate", {"head_sha": self.head},
                 self.row(merge_commit_sha=self.stray), self.receipt())
        with self.assertRaises(EntryGateError):
            gate("candidate", {"head_sha": self.head},
                 self.row(merge_commit_sha=self.merge_commit), self.receipt())
        with self.assertRaises(EntryGateError):
            gate("candidate", {"head_sha": self.head}, self.row(),
                 self.receipt("witness"))
        with self.assertRaises(EntryGateError):
            gate("candidate", {"head_sha": self.head}, self.row(),
                 {"sha256": "short", "reference": "review:candidate:pr-7"})
        with self.assertRaises(EntryGateError):
            gate("other", {"head_sha": self.head}, self.row(), self.receipt())


class ReviewGateTest(unittest.TestCase):
    """The real inventory collector plus the real current-head verifier."""

    def setUp(self):
        import ci_review_wait_test as wait_fixtures

        self.rest = wait_fixtures.AdmissionTests()
        self.rest.setUp()
        self.addCleanup(self.rest.doCleanups)
        self.head, self.number = wait_fixtures.A, 7
        self.repo_id = self.rest.repo["id"]

    def graphql_client(self, rows):
        from tools.release.github_api import GitHubClient, HttpResponse

        repo = {"databaseId": self.repo_id, "nameWithOwner": "endaye/lmdj"}
        pr = dict(id="PR_7", databaseId=41, number=self.number,
                  headRefOid=self.head, baseRefName="main", state="OPEN",
                  isDraft=False, merged=False, mergeCommit=None,
                  headRepository=deepcopy(repo))

        def http(method, url, headers, raw):
            request = json.loads(raw)
            variables = request["variables"]
            thread = variables.get("thread")
            kind = "threadComments" if thread else next(
                key for key in rows if f"{key}(first:" in request["query"])
            selected = deepcopy(rows.get(thread or kind, []))
            cursor = variables["cursor"]
            index = 0 if cursor is None else int(cursor)
            nodes = selected[index:index + 1]
            connection = {"totalCount": len(selected), "nodes": nodes,
                          "pageInfo": {"hasNextPage": index + len(nodes) < len(selected),
                                       "endCursor": str(index + 1) if nodes else None}}
            document = {"data": {"repository": {**repo, "pullRequest": deepcopy(pr)}}}
            if thread:
                document["data"]["node"] = {"__typename": "PullRequestReviewThread",
                                            "id": thread, "comments": connection}
            else:
                document["data"]["repository"]["pullRequest"][kind] = connection
            return HttpResponse(200, {}, json.dumps(document).encode())

        return GitHubClient(http_transport=http, token="fixture-only-no-credential")

    def rows(self):
        # The GraphQL review row must byte-match the REST fixture's published
        # review: bind_eligibility compares body bytes and author identity.
        review = self.rest.reviews[0]
        return {"reviews": [dict(id="R_60", databaseId=60, body=review["body"],
                                 state="COMMENTED",
                                 submittedAt="2026-09-10T01:00:00Z",
                                 updatedAt="2026-09-10T01:00:00Z",
                                 commit={"oid": self.head},
                                 author={"login": "github-actions[bot]",
                                         "databaseId": 20})],
                "comments": [], "reviewThreads": [], "closingIssuesReferences": []}

    def gate(self, client):
        import review_wait as wait

        return review_gate(client=client,
                           reader_for=lambda repository: wait.Reader(self.rest,
                                                                     repository),
                           repository_id=self.repo_id)

    def test_an_eligible_linked_review_verifies(self):
        # Sanity: the reused fixture environment is itself eligible.
        self.assertTrue(self.rest.check()["eligible"])
        observed = self.gate(self.graphql_client(self.rows()))(
            "candidate", {"head_sha": self.head}, {"number": self.number})
        self.assertEqual(observed.status, "verified")
        self.assertEqual(observed.evidence["reference"],
                         f"review:candidate:pr-{self.number}")

    def test_no_review_is_pending_and_a_lost_api_is_unknown(self):
        # Capture the aligned rows first, then empty the REST side: the
        # eligibility read finds no evidence while the inventory still
        # collects.
        rows = self.rows()
        rows["reviews"] = []
        self.rest.reviews = []
        observed = self.gate(self.graphql_client(rows))(
            "candidate", {"head_sha": self.head}, {"number": self.number})
        self.assertEqual(observed.status, "pending")
        self.rest._request = lambda *a, **k: (_ for _ in ()).throw(
            OSError("fixture API lost"))
        observed = self.gate(self.graphql_client(rows))(
            "candidate", {"head_sha": self.head}, {"number": self.number})
        self.assertEqual(observed.status, "unknown")

    def test_an_unlinked_or_mismatched_inventory_fails_closed(self):
        rows = self.rows()
        rows["reviews"][0]["body"] = "tampered review body"
        with self.assertRaises(Exception):
            self.gate(self.graphql_client(rows))(
                "candidate", {"head_sha": self.head}, {"number": self.number})

    def test_an_unresolved_thread_or_closing_relation_conflicts(self):
        rows = self.rows()
        rows["reviewThreads"] = [dict(id="T_1", isResolved=False,
                                      isOutdated=False,
                                      path="tools/release/example.py",
                                      comments={"totalCount": 1})]
        rows["T_1"] = [dict(id="RC_1_1", databaseId=411, body="thread comment",
                            createdAt="2026-09-13T01:00:00Z",
                            updatedAt="2026-09-13T01:00:00Z",
                            author={"login": "reviewer", "databaseId": 20},
                            originalCommit={"oid": self.head},
                            commit={"oid": self.head},
                            path="tools/release/example.py",
                            diffHunk="@@ -1 +1 @@\n-old\n+new",
                            originalLine=1, line=None,
                            pullRequest={"databaseId": 41, "number": self.number},
                            pullRequestReview={"id": "R_60", "databaseId": 60})]
        observed = self.gate(self.graphql_client(rows))(
            "candidate", {"head_sha": self.head}, {"number": self.number})
        self.assertEqual(observed.status, "conflict")
        rows = self.rows()
        rows["closingIssuesReferences"] = [dict(
            id="I_1", databaseId=300, number=1301,
            repository={"databaseId": self.repo_id,
                        "nameWithOwner": "endaye/lmdj"})]
        observed = self.gate(self.graphql_client(rows))(
            "candidate", {"head_sha": self.head}, {"number": self.number})
        self.assertEqual(observed.status, "conflict")

    def test_a_gate_without_an_exact_head_or_kind_fails_closed(self):
        gate = self.gate(self.graphql_client(self.rows()))
        with self.assertRaises(EntryGateError):
            gate("other", {"head_sha": self.head}, {"number": self.number})
        with self.assertRaises(EntryGateError):
            gate("candidate", {"head_sha": "short"}, {"number": self.number})
        with self.assertRaises(EntryGateError):
            gate("candidate", {"head_sha": self.head}, {"number": -1})


class BatchEvidenceConsumerTest(unittest.TestCase):
    def test_the_consumer_binds_only_the_reviewed_policy_source(self):
        from tools.release.entry_gates import batch_evidence_consumer
        from tools.release.model import load_policy

        policy = load_policy(ROOT / "tools/release/policy.json")
        source = policy.batch_evidence_source
        consumer = batch_evidence_consumer(api_get=lambda *a, **k: None,
                                           git_root=ROOT, policy=policy)
        self.assertEqual((consumer.repository_id, consumer.workflow_id,
                          consumer.producer_revision),
                         (source["repository_id"], source["workflow_id"],
                          source["producer_revision"]))

    def test_a_policy_without_a_batch_source_fails_closed(self):
        from tools.release.entry_gates import batch_evidence_consumer

        class NoSource:
            batch_evidence_source = None

        with self.assertRaises(EntryGateError):
            batch_evidence_consumer(api_get=lambda *a, **k: None,
                                    git_root=ROOT, policy=NoSource())


if __name__ == "__main__":
    unittest.main()
