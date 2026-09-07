#!/usr/bin/env python3
"""Temporary harness checks. These are fakes, NOT the real Actions acceptance."""
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import self_test_report as rep
import self_test_report_rehearsal as drill
sys.path.insert(0, str(ROOT / "tests/build"))
from ci_self_test_report_workflow_test import block, field, scalars


class FakeClient:
    """The small used REST surface, with real response author/label shapes."""
    def __init__(self, *, bot=True):
        self.issues, self.comments, self.labels = {}, {}, set()
        self.calls = []
        self.user = {"login": "github-actions[bot]" if bot else "endaye",
                     "type": "Bot" if bot else "User"}

    def _repo(self, suffix):
        return "/repos/endaye/lmdj" + suffix

    def _request(self, method, path, *, body=None):
        self.calls.append((method, path))
        if (method, path) == ("GET", self._repo("")):
            return {"full_name": "endaye/lmdj"}
        if method == "GET" and path.startswith(self._repo("/labels/")):
            name = path.rsplit("/", 1)[1]
            if name not in self.labels:
                raise rep.GitHubApiError(404, "Not Found")
            return {"name": name}
        if (method, path) == ("POST", self._repo("/labels")):
            if body["name"] in self.labels:
                raise rep.GitHubApiError(422, "Already exists")
            self.labels.add(body["name"])
            return deepcopy(body)
        if method == "GET" and path.startswith(self._repo("/issues/")):
            return deepcopy(self.issues[int(path.rsplit("/", 1)[1])])
        raise AssertionError((method, path))

    def list_issues(self, *, label, state):
        if state != "all":
            raise AssertionError(state)
        return [deepcopy(i) for i in self.issues.values() if label in {l["name"] for l in i["labels"]}]

    def list_comments(self, number):
        return deepcopy(self.comments[number])

    def create_issue(self, *, title, body, labels, assignees):
        if not set(labels) <= self.labels or tuple(assignees) != ("endaye",):
            raise rep.GitHubApiError(422, "Invalid labels or assignees")
        number = len(self.issues) + 1
        self.issues[number] = {"number": number, "title": title, "body": body,
                               "labels": [{"name": label} for label in labels],
                               "user": self.user, "state": "open", "html_url": f"https://github.com/endaye/lmdj/issues/{number}"}
        self.comments[number] = []
        return deepcopy(self.issues[number])

    def create_comment(self, number, body):
        result = {"id": 100 + sum(len(v) for v in self.comments.values()), "body": body, "user": self.user}
        self.comments[number].append(result)
        return deepcopy(result)

    def set_issue_state(self, number, state):
        if state not in {"open", "closed"}:
            raise AssertionError(state)
        self.issues[number]["state"] = state
        return deepcopy(self.issues[number])


class RehearsalHarnessTest(unittest.TestCase):
    def invoke(self, client, *, execute=True, actions=True, cleanup=False):
        args = ["drill", "--checkout", str(ROOT), "--drill-id", "abcdef123456", "--run-id", "12345"]
        if execute:
            args += ["--execute", "--confirm-repository", "endaye/lmdj"]
        if cleanup:
            args += ["--cleanup"]
        env = {"GITHUB_ACTIONS": "true" if actions else "false", "GITHUB_REPOSITORY": "endaye/lmdj",
               "GITHUB_RUN_ID": "12345", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_TOKEN": "test-only-not-a-credential"}
        output = io.StringIO()
        with mock.patch.object(sys, "argv", args), mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.dict(sys.modules, {"self_test_report": rep}), \
             mock.patch("socket.create_connection", side_effect=AssertionError("Unexpected real network in unit test")), \
             mock.patch.object(rep, "UrllibGitHubApi", return_value=client) as factory, \
             mock.patch.object(drill.time, "sleep") as sleep, mock.patch("sys.stdout", output):
            result = drill.main()
        return result, output.getvalue(), factory, sleep

    def test_default_has_no_network_and_no_token_client(self):
        result, _, factory, _ = self.invoke(FakeClient(), execute=False)
        self.assertEqual(result, 0)
        factory.assert_not_called()

    def test_local_human_context_is_refused_before_client_construction(self):
        with self.assertRaisesRegex(RuntimeError, "real repository Actions context"):
            self.invoke(FakeClient(), actions=False)

    def test_full_sequence_keeps_original_bot_trust_and_exactly_once_markers(self):
        client = FakeClient()
        predicate = rep._trusted_marker_author
        result, output, _, sleep = self.invoke(client)
        self.assertEqual(result, 0)
        self.assertIs(rep._trusted_marker_author, predicate)
        self.assertEqual(len(client.issues), 2)
        self.assertEqual(sum(map(len, client.comments.values())), 4)
        self.assertTrue(all(i["state"] == "closed" for i in client.issues.values()))
        self.assertEqual(sleep.call_args_list, [mock.call(5.0), mock.call(5.0)])
        stages = [json.loads(line) for line in output.splitlines()]
        refusal = next(row for row in stages if row["stage"] == "injected-refusal")
        self.assertFalse(refusal["request_sent"])
        self.assertEqual(sum(row["stage"] == "injected-response-loss" for row in stages), 2)
        self.assertIn("drill-assertions-passed", output)
        self.assertNotIn("test-only-not-a-credential", output)
        self.assertTrue(all("12345/1/drill-" in i["body"] for i in client.issues.values()))

    def test_real_user_author_is_not_rewritten_and_owned_issue_is_closed(self):
        client = FakeClient(bot=False)
        with self.assertRaisesRegex(RuntimeError, "Real author is not"):
            self.invoke(client)
        self.assertEqual(len(client.issues), 1)
        self.assertEqual(client.issues[1]["user"]["login"], "endaye")
        self.assertEqual(client.issues[1]["state"], "closed")
        self.assertEqual(client.comments[1], [])

    def test_existing_namespace_is_a_stop_not_an_overwrite(self):
        client = FakeClient()
        client.labels.add("self-test-drill-abcdef123456")
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            self.invoke(client)
        self.assertEqual(client.issues, {})
        self.assertFalse(any(method == "POST" for method, _ in client.calls))

    def test_production_issue_cannot_be_selected_for_cleanup(self):
        client = FakeClient()
        client.issues[99] = {"number": 99, "state": "open", "title": "Production failure",
                             "body": "production", "labels": [{"name": "self-test-drill-abcdef123456"},
                                                                 {"name": "self-test"}]}
        with self.assertRaisesRegex(RuntimeError, "outside exact drill ownership"):
            self.invoke(client, cleanup=True)
        self.assertEqual(client.issues[99]["state"], "open")

    def test_repeated_cleanup_only_closes_owned_issues(self):
        client = FakeClient()
        self.invoke(client)
        before = deepcopy(client.issues)
        self.invoke(client, cleanup=True)
        self.assertEqual(before, client.issues)

    def test_branch_workflow_separates_authority_and_is_not_a_production_entry(self):
        source = (ROOT / ".github/workflows/self-test-report.yml").read_text()
        original = block(source, "report", 2)
        self.assertIn("!(github.event_name == 'workflow_dispatch' && inputs.rehearsal_only)", field(original, "if", 4))
        job = block(source, "rehearsal", 2)
        self.assertIn("github.run_attempt == 1", field(job, "if", 4))
        self.assertIn("refs/heads/feat/ci-report-controlled-rehearsal", field(job, "if", 4))
        self.assertEqual(scalars(block(job, "permissions", 4), 6), {"contents": "read", "issues": "write"})
        self.assertIn("ref: d360d3805f21a18ec75d86bb0fc69cda747e9d9d", job)
        self.assertIn("ref: ${{ github.sha }}", job)
        self.assertEqual(job.count("persist-credentials: false"), 2)
        self.assertIn("--cleanup", job)
        self.assertIn("name: reporter-rehearsal-${{ github.run_id }}-${{ github.run_attempt }}", job)
        self.assertNotIn("name: self-test-verdict-", job)


if __name__ == "__main__":
    unittest.main()
