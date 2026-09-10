"""Finite-secret projection and manual-only preflight; all HTTP is mocked."""
import contextlib
import importlib.util
import io
import json
from http.client import BadStatusLine
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("credential_preflight", ROOT / "scripts/ci/pr_agent_credential_preflight.py")
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)


def body(**overrides):
    return json.dumps({"is_available": True, "balance_infos": [
        {"currency": "USD", "total_balance": "10.00", "granted_balance": "0", "topped_up_balance": "10"}], **overrides}).encode()


def opener(raw):
    response = Mock(status=200)
    response.read.return_value = raw
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    result = Mock()
    result.open.return_value = context
    return result


class CredentialPreflightTest(unittest.TestCase):
    def test_success_projects_no_balance_amount(self):
        result = subject.check("fake-secret-value", opener(body()))
        self.assertEqual(result, {"authentication": "passed", "supplier_available": True,
                                 "positive_balance": True, "currencies": ["USD"], "status": "passed"})

    def test_missing_key_does_not_request(self):
        client = Mock()
        self.assertEqual(subject.check("", client)["status"], "credential_missing_or_invalid")
        client.open.assert_not_called()

    def test_header_injection_does_not_request(self):
        client = Mock()
        subject.check("bad\r\nheader", client)
        client.open.assert_not_called()

    def test_fixed_read_only_endpoint(self):
        client = opener(body())
        subject.check("fake-secret-value", client)
        request = client.open.call_args.args[0]
        self.assertEqual((request.full_url, request.method, request.data), (subject.ENDPOINT, "GET", None))
        self.assertEqual(client.open.call_args.kwargs, {"timeout": 15})
        self.assertEqual(client.open.call_count, 1)

    def test_redirects_refused(self):
        self.assertIsNone(subject.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.invalid"))

    def test_no_ambient_proxy(self):
        with patch.object(subject, "build_opener", return_value=opener(body())) as build:
            subject.check("fake-secret-value")
        self.assertEqual(build.call_args.args[0].proxies, {})

    def test_http_error_body_not_printed_or_read(self):
        client = Mock()
        payload = Mock()
        client.open.side_effect = HTTPError(subject.ENDPOINT, 401, "fake-secret-value", {}, payload)
        self.assertEqual(subject.check("fake-secret-value", client), {"status": "http_error", "http_status": 401})
        payload.read.assert_not_called()

    def test_transport_error_is_finite(self):
        client = Mock()
        client.open.side_effect = URLError("fake-secret-value")
        self.assertEqual(subject.check("fake-secret-value", client), {"status": "transport_error"})

    def test_oversized_response_fails(self):
        self.assertEqual(subject.check("key", opener(b" " * (subject.MAX_BYTES + 1)))["status"], "invalid_response")

    def test_malformed_http_status_does_not_disclose(self):
        client = Mock()
        client.open.side_effect = BadStatusLine("fake-secret-value")
        self.assertEqual(subject.check("key", client), {"status": "transport_error"})

    def test_inconsistent_balance_is_not_available(self):
        raw = body(balance_infos=[{"currency": "USD", "total_balance": "20", "granted_balance": "0", "topped_up_balance": "10"}])
        self.assertEqual(subject.check("key", opener(raw))["status"], "invalid_response")

    def test_zero_balance_cannot_pass(self):
        raw = body(balance_infos=[{"currency": "USD", "total_balance": "0", "granted_balance": "0", "topped_up_balance": "0"}])
        self.assertEqual(subject.check("key", opener(raw))["status"], "unavailable")

    def test_availability_is_a_boolean_not_truthy_data(self):
        self.assertEqual(subject.check("key", opener(body(is_available="true")))["status"], "invalid_response")

    def test_duplicate_keys_fail(self):
        self.assertEqual(subject.check("key", opener(b'{"is_available":true,"is_available":false}'))["status"], "invalid_response")

    def test_invalid_balance_failures(self):
        for value in ("NaN", "Infinity", "-1", 10, "1e9999"):
            with self.subTest(value=value):
                raw = body(balance_infos=[{"currency": "USD", "total_balance": value, "granted_balance": "0", "topped_up_balance": "10"}])
                self.assertEqual(subject.check("key", opener(raw))["status"], "invalid_response")

    def test_unavailable_is_not_passed(self):
        self.assertEqual(subject.check("key", opener(body(is_available=False)))["status"], "unavailable")

    def test_main_removes_environment_key_and_does_not_disclose(self):
        with patch.dict(os.environ, {"PR_AGENT_DEEPSEEK_API_KEY": "fake-secret-value"}), patch.object(subject, "build_opener", return_value=opener(body())):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(subject.main(), 0)
            self.assertNotIn("PR_AGENT_DEEPSEEK_API_KEY", os.environ)
        receipt = json.loads(output.getvalue())
        self.assertNotIn("fake-secret-value", output.getvalue())
        self.assertEqual(receipt["funding_admission"], "not_evaluated")
        self.assertEqual(receipt["inference_requests"], 0)

    def test_workflow_has_no_automatic_or_arbitrary_target(self):
        import yaml
        workflow = yaml.safe_load((ROOT / ".github/workflows/pr-agent-credential-preflight.yml").read_text())
        self.assertEqual(workflow.get("on", workflow.get(True)), {"workflow_dispatch": None})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        job = workflow["jobs"]["deepseek"]
        self.assertEqual(job["if"], "github.ref == 'refs/heads/main' && github.actor == github.repository_owner")
        self.assertEqual(job["runs-on"], ["self-hosted", "Linux", "X64", "netcup", "ci-general"])
        checkout, probe = job["steps"]
        self.assertEqual(checkout["with"], {"ref": "${{ github.sha }}", "persist-credentials": False})
        self.assertEqual(probe["env"], {"PR_AGENT_DEEPSEEK_API_KEY": "${{ secrets.PR_AGENT_DEEPSEEK_API_KEY }}"})
        self.assertEqual(probe["run"], "python3 -I scripts/ci/pr_agent_credential_preflight.py")


if __name__ == "__main__":
    unittest.main()
