#!/usr/bin/env python3
"""The release freeze is one repository variable the active request holds.

`scripts/release.sh run`/`resume` hold `LMDJ_RELEASE_FREEZE` as the request id
they drive and release it when the request completes; `retire` releases it.
The defects these tests catch: a second request silently taking over an
active freeze, a completed or retired request leaving the freeze behind, a
release clearing another request's freeze, and a hold or release treated as
done when the API refused it (#2422 item 10).
"""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.github_api import GitHubApiError  # noqa: E402
from tools.release.orchestration import JournalError  # noqa: E402
from tools.release.release_freeze import ReleaseFreeze, VARIABLE  # noqa: E402

REPOSITORY = "endaye/lmdj"
ONE, TWO = "release-" + "1" * 16, "release-" + "2" * 16


class FakeGitHub:
    def __init__(self, value=None, *, fail=None):
        self.value, self.fail, self.calls = value, fail, []

    def get_repository_variable(self, repository, name):
        self.calls.append(("get", repository, name))
        if self.fail == "get":
            raise GitHubApiError("GitHub release request was rejected")
        return self.value

    def create_repository_variable(self, repository, name, value):
        self.calls.append(("create", repository, name, value))
        if self.fail == "create":
            raise GitHubApiError("GitHub release request was rejected")
        self.value = value

    def update_repository_variable(self, repository, name, value):
        self.calls.append(("update", repository, name, value))
        self.value = value

    def delete_repository_variable(self, repository, name):
        self.calls.append(("delete", repository, name))
        if self.fail == "delete":
            raise GitHubApiError("GitHub release request was rejected")
        self.value = None


class ReleaseFreezeTest(unittest.TestCase):
    def test_variable_name_is_the_one_the_pr_contract_reads(self):
        self.assertEqual(VARIABLE, "LMDJ_RELEASE_FREEZE")

    def test_hold_creates_the_variable_for_the_request(self):
        github = FakeGitHub()
        ReleaseFreeze(github, REPOSITORY).hold(ONE)
        # read, create, then the confirming read that proves the create landed as ours
        self.assertEqual(github.calls, [("get", REPOSITORY, VARIABLE), ("create", REPOSITORY, VARIABLE, ONE),
                                        ("get", REPOSITORY, VARIABLE)])
        self.assertEqual(github.value, ONE)

    def test_hold_is_idempotent_for_the_same_request(self):
        github = FakeGitHub(ONE)
        ReleaseFreeze(github, REPOSITORY).hold(ONE)
        self.assertEqual(github.calls, [("get", REPOSITORY, VARIABLE)])

    def test_hold_refuses_while_another_request_holds_the_freeze(self):
        github = FakeGitHub(ONE)
        with self.assertRaisesRegex(JournalError, "another release request holds the freeze"):
            ReleaseFreeze(github, REPOSITORY).hold(TWO)
        self.assertEqual(github.value, ONE)
        self.assertEqual([call[0] for call in github.calls], ["get"])

    def test_a_create_the_api_refuses_is_settled_by_rereading_the_holder(self):
        # Two starts raced: the loser's create is refused (409) and the holder
        # it then reads is the winner; it refuses instead of taking over.
        class Racing(FakeGitHub):
            def create_repository_variable(self, repository, name, value):
                self.calls.append(("create", repository, name, value))
                self.value = TWO
                raise GitHubApiError("GitHub repository variable creation was rejected")
        github = Racing(None)
        with self.assertRaisesRegex(JournalError, "another release request holds the freeze"):
            ReleaseFreeze(github, REPOSITORY).hold(ONE)
        self.assertEqual(github.value, TWO)
        # Our own create landed although the API answered with an error: held.
        class Landed(FakeGitHub):
            def create_repository_variable(self, repository, name, value):
                self.value = value
                raise GitHubApiError("GitHub repository variable creation was rejected")
        github = Landed(None)
        ReleaseFreeze(github, REPOSITORY).hold(ONE)
        self.assertEqual(github.value, ONE)
        # Refused and still absent: the API error itself is the answer.
        with self.assertRaises(GitHubApiError):
            ReleaseFreeze(FakeGitHub(None, fail="create"), REPOSITORY).hold(ONE)

    def test_hold_confirms_the_variable_names_this_request_after_creating_it(self):
        class Overwritten(FakeGitHub):
            def create_repository_variable(self, repository, name, value):
                self.calls.append(("create", repository, name, value))
                self.value = TWO   # another writer landed between create and the confirming read
        github = Overwritten(None)
        with self.assertRaisesRegex(JournalError, "another release request holds the freeze"):
            ReleaseFreeze(github, REPOSITORY).hold(ONE)

    def test_release_deletes_only_this_requests_freeze(self):
        github = FakeGitHub(ONE)
        ReleaseFreeze(github, REPOSITORY).release(ONE)
        self.assertEqual(github.calls[-1], ("delete", REPOSITORY, VARIABLE))
        self.assertIsNone(github.value)
        github = FakeGitHub(ONE)
        with self.assertRaisesRegex(JournalError, "names another request"):
            ReleaseFreeze(github, REPOSITORY).release(TWO)
        self.assertEqual(github.value, ONE)
        github = FakeGitHub(None)
        ReleaseFreeze(github, REPOSITORY).release(ONE)   # already released: nothing to do
        self.assertEqual([call[0] for call in github.calls], ["get"])

    def test_read_reports_the_holder_or_none(self):
        self.assertEqual(ReleaseFreeze(FakeGitHub(ONE), REPOSITORY).read(), ONE)
        self.assertIsNone(ReleaseFreeze(FakeGitHub(None), REPOSITORY).read())

    def test_api_refusals_propagate_and_never_count_as_held_or_released(self):
        for fail in ("get", "create", "delete"):
            with self.subTest(fail=fail):
                github = FakeGitHub(None if fail != "delete" else ONE, fail=fail)
                freeze = ReleaseFreeze(github, REPOSITORY)
                with self.assertRaises(GitHubApiError):
                    freeze.hold(ONE) if fail != "delete" else freeze.release(ONE)

    def test_request_ids_are_validated_before_any_write(self):
        github = FakeGitHub(None)
        for bad in ("", "not an id", "release-" + "g" * 16, "RELEASE-" + "1" * 16):
            with self.subTest(bad=bad), self.assertRaises(JournalError):
                ReleaseFreeze(github, REPOSITORY).hold(bad)
        self.assertEqual(github.calls, [])


if __name__ == "__main__":
    unittest.main()
