#!/usr/bin/env python3
"""Contract tests for the pinned, immutable PR-Agent review boundary.

The pure tests exercise authentication, coverage and budget admission without a
network.  The integration tests run the pinned PR-Agent reviewer and stock
LiteLLMAIHandler against LiteLLM's actual ``acompletion`` seam; only that seam
is replaced, so a green test cannot come from replacing the reviewer itself.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import shutil


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import pr_agent_review as adapter


FIXTURES = ROOT / "tests/fixtures/ci/pr-agent"
SOURCE_ROOT = Path(os.environ.get("PR_AGENT_TEST_SOURCE_ROOT", "/tmp/lmdj-pr-agent-packaging/upstream-53072488"))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def signed_input(mutator=None):
    document = json.loads((FIXTURES / "complete-input.json").read_text(encoding="utf-8"))
    if mutator:
        mutator(document)
    unsigned = copy.deepcopy(document)
    unsigned.pop("input_sha256", None)
    document["input_sha256"] = hashlib.sha256(canonical(unsigned)).hexdigest()
    return document


def blob(data: bytes, encoding="utf-8"):
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "byte_length": len(data),
        "data_b64": base64.b64encode(data).decode("ascii"),
        "encoding": encoding,
    }


class FakeCompletion(dict):
    """Mapping-shaped LiteLLM response with the SDK response logging method."""

    def dict(self):
        return dict(self)


def test_config(enabled=("deepseek",), *, per_pr=1.0, backoff=0):
    providers = {}
    for provider in adapter.SUPPORTED_PROVIDERS:
        if provider not in enabled:
            providers[provider] = {
                "enabled": False,
                "endpoint": None,
                "model": None,
                "credential_ref": None,
                "pricing_revision": None,
                "input_price_usd_per_token": None,
                "output_price_usd_per_token": None,
                "pricing_verified": False,
                "funding_ref": None,
                "funding_verified": False,
            }
        else:
            credential_provider = {"deepseek": "DEEPSEEK", "glm": "ZAI", "xai": "XAI", "kimi": "KIMI"}[provider]
            providers[provider] = {
                "enabled": True,
                "endpoint": f"https://{provider}.invalid.example/v1",
                "model": f"fixture-{provider}-model",
                "credential_ref": f"PR_AGENT_{credential_provider}_API_KEY",
                "pricing_revision": "fixture-price-v1",
                "input_price_usd_per_token": 0.000001,
                "output_price_usd_per_token": 0.000001,
                "pricing_verified": True,
                "funding_ref": "fixture-funding-v1",
                "funding_verified": True,
            }
    return adapter._safe_config({
        "schema": adapter.CONFIG_SCHEMA,
        "provider_order": list(adapter.SUPPORTED_PROVIDERS),
        "budget": {
            "approval_id": "fixture-approval",
            "timezone": "Asia/Shanghai",
            "monthly_usd": 20.0,
            "pilot_usd": 20.0,
            "per_pr_usd": per_pr,
            "max_requests": 8,
            "max_requests_per_provider": 2,
            "request_timeout_seconds": 60,
            "backoff_seconds": backoff,
            "engine_deadline_seconds": 600,
            "input_token_cap": 100,
            "output_token_cap": 50,
        },
        "providers": providers,
    })


def bound_source(source_root: Path, destination: Path) -> Path:
    shutil.copytree(source_root, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    digest = adapter._source_tree_sha256(destination)
    (destination / "IDENTITY").write_text(
        "schema=lmdj.pr-agent-bundle.v1\n"
        f"source_commit={adapter.UPSTREAM_COMMIT}\n"
        f"source_version={adapter.UPSTREAM_VERSION}\n"
        f"source_tree_sha256={digest}\n",
        encoding="utf-8",
    )
    return destination


class InputAndPolicyTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((FIXTURES / "complete-input.json").read_text(encoding="utf-8"))
        self.authenticated = adapter.authenticate_input(self.document)

    def test_fixture_authenticates_and_prompt_contains_full_base_head_and_deleted_content(self):
        prompt = adapter.render_prompt_input(self.authenticated)
        self.assertTrue(self.authenticated["input_complete"])
        self.assertEqual(len(adapter.expected_coverage(self.authenticated)), 2)
        self.assertIn("return 1", prompt)
        self.assertIn("return 2", prompt)
        self.assertIn("removed content", prompt)
        self.assertIn("LMDJ-HUNK path=obsolete.txt id=obsolete-h1", prompt)
        coverage = adapter._make_coverage(self.authenticated, provider="deepseek", model="fixture", prompt=prompt, usage=None)
        self.assertTrue(coverage["complete"])
        self.assertEqual(coverage["expected_hunks"], coverage["observed_hunks"])

    def test_marker_only_prompt_is_incomplete_coverage(self):
        markers = "\n".join(
            f"LMDJ-HUNK path={hunk['path']} id={hunk['id']} sha256={hunk['patch_sha256']}"
            for hunk in adapter.expected_coverage(self.authenticated)
        )
        coverage = adapter._make_coverage(self.authenticated, provider="deepseek", model="fixture",
                                          prompt=markers, usage=None)
        self.assertFalse(coverage["complete"])
        self.assertEqual(coverage["observed_hunks"], [])

    def test_digest_mismatch_is_rejected(self):
        tampered = copy.deepcopy(self.document)
        tampered["diff"]["text"] += "forged"
        with self.assertRaisesRegex(adapter.EngineError, "input authentication digest"):
            adapter.authenticate_input(tampered)

    def test_changed_file_without_both_immutable_blobs_is_rejected(self):
        def remove_head(document):
            document["files"][0]["head"] = None

        with self.assertRaisesRegex(adapter.EngineError, "missing base or head bytes"):
            adapter.authenticate_input(signed_input(remove_head))

    def test_added_file_without_head_bytes_is_rejected(self):
        def add_missing_head(document):
            file = document["files"][0]
            file["change_kind"] = "added"
            file["base"] = None
            file["head"] = None

        with self.assertRaisesRegex(adapter.EngineError, "missing head bytes"):
            adapter.authenticate_input(signed_input(add_missing_head))

    def test_unreadable_content_is_visible_but_never_complete(self):
        def add_unreadable(document):
            marker = "@@ -0,0 +0,0 @@\n"
            document["diff"]["text"] += marker
            document["diff"]["byte_length"] = len(document["diff"]["text"].encode())
            document["diff"]["sha256"] = hashlib.sha256(document["diff"]["text"].encode()).hexdigest()
            document["files"].append({
                "path": "secret.bin",
                "old_path": None,
                "change_kind": "unreadable",
                "patch": marker,
                "patch_sha256": hashlib.sha256(marker.encode()).hexdigest(),
                "base": None,
                "head": None,
                "hunks": [{
                    "id": "secret-marker",
                    "patch": marker,
                    "patch_sha256": hashlib.sha256(marker.encode()).hexdigest(),
                    "right_lines": [],
                }],
            })

        authenticated = adapter.authenticate_input(signed_input(add_unreadable))
        self.assertFalse(authenticated["input_complete"])
        coverage = adapter._make_coverage(authenticated, provider="deepseek", model="fixture",
                                          prompt=adapter.render_prompt_input(authenticated), usage=None)
        self.assertFalse(coverage["complete"])
        self.assertIn("secret.bin", {hunk["path"] for hunk in coverage["expected_hunks"]})

    def test_oversized_diff_is_rejected_before_engine_import(self):
        def enlarge(document):
            document["diff"]["text"] = "x" * (adapter.MAX_INPUT_BYTES + 1)

        with self.assertRaisesRegex(adapter.EngineError, "diff is oversized"):
            adapter.authenticate_input(signed_input(enlarge))

    def test_wrong_side_and_outside_diff_findings_are_rejected(self):
        wrong_side = {"review": {"key_issues_to_review": [{
            "relevant_file": "src/example.py", "issue_header": "Bug", "issue_content": "bad",
            "start_line": 1, "end_line": 1,
        }]}}
        with self.assertRaisesRegex(adapter.EngineError, "changed RIGHT-side line"):
            adapter._validate_native_mapping(wrong_side, self.authenticated)

        outside = {"review": {"key_issues_to_review": [{
            "relevant_file": "not-changed.py", "issue_header": "Bug", "issue_content": "bad",
            "start_line": 2, "end_line": 2,
        }]}}
        with self.assertRaisesRegex(adapter.EngineError, "outside the changed path"):
            adapter._validate_native_mapping(outside, self.authenticated)

    def test_missing_native_findings_list_is_not_a_clean_review(self):
        class StubReviewer:
            @staticmethod
            def _load_review_yaml(_text):
                return {"review": {"general_comments": "clean"}}

        upstream = {"PRReviewer": StubReviewer}
        with self.assertRaisesRegex(adapter.EngineError, "missing its findings list"):
            adapter._strict_native_yaml(upstream, "review:\n  general_comments: clean\n")

    def test_trusted_config_requires_verified_activation_and_keeps_provider_mapping_closed(self):
        config = test_config()
        self.assertEqual(config["providers"]["deepseek"]["litellm_provider"] if "litellm_provider" in config["providers"]["deepseek"] else "deepseek", "deepseek")
        invalid = copy.deepcopy(config)
        invalid["providers"]["deepseek"]["funding_verified"] = False
        with self.assertRaisesRegex(adapter.EngineError, "enabled provider lacks"):
            adapter._safe_config({"schema": adapter.CONFIG_SCHEMA, "budget": config["budget"],
                                  "providers": {**invalid["providers"]}, "provider_order": config["provider_order"]})

    def test_trusted_config_enforces_approved_dollar_caps_and_order(self):
        config = test_config()
        for key, value in (("monthly_usd", 20.01), ("pilot_usd", 20.01), ("per_pr_usd", 1.01)):
            invalid_budget = {**config["budget"], key: value}
            with self.assertRaisesRegex(adapter.EngineError, "dollar budget"):
                adapter._safe_config({"schema": adapter.CONFIG_SCHEMA, "budget": invalid_budget,
                                      "providers": config["providers"], "provider_order": config["provider_order"]})
        invalid_budget = {**config["budget"], "monthly_usd": 0.5, "pilot_usd": 0.6}
        with self.assertRaisesRegex(adapter.EngineError, "dollar budget"):
            adapter._safe_config({"schema": adapter.CONFIG_SCHEMA, "budget": invalid_budget,
                                  "providers": config["providers"], "provider_order": config["provider_order"]})

    def test_ledger_shares_the_per_pr_cap_across_provider_fallback(self):
        config = test_config(per_pr=0.00025)["budget"]
        with tempfile.TemporaryDirectory() as directory:
            ledger = adapter.Ledger(Path(directory) / "ledger.jsonl", config)
            kwargs = dict(approval_id="fixture-approval", attempt_id="run:1", model="fixture-model",
                          input_price=0.000001, output_price=0.000001, input_token_cap=100,
                          output_token_cap=50, max_requests=8, max_provider_requests=2,
                          per_pr_usd=0.00025, monthly_usd=20.0, pilot_usd=20.0,
                          price_revision="fixture-price-v1")
            ledger.admit(request_id="run:1:deepseek:1", provider="deepseek", **kwargs)
            with self.assertRaisesRegex(adapter.AdmissionDenied, "request cost budget exhausted"):
                ledger.admit(request_id="run:1:glm:1", provider="glm", **kwargs)

    def test_uncertain_reservation_is_retained(self):
        config = test_config(per_pr=0.0002)["budget"]
        with tempfile.TemporaryDirectory() as directory:
            ledger = adapter.Ledger(Path(directory) / "ledger.jsonl", config)
            reservation = ledger.admit(
                approval_id="fixture-approval", attempt_id="run:2", request_id="run:2:deepseek:1",
                provider="deepseek", model="fixture-model", input_price=0.000001, output_price=0.000001,
                input_token_cap=100, output_token_cap=50, max_requests=8, max_provider_requests=2,
                per_pr_usd=0.0002, monthly_usd=20.0, pilot_usd=20.0, price_revision="fixture-price-v1")
            ledger.reconcile(reservation, status="uncertain", actual_amount=None, usage=None)
            with self.assertRaisesRegex(adapter.AdmissionDenied, "request cost budget exhausted"):
                ledger.admit(
                    approval_id="fixture-approval", attempt_id="run:2", request_id="run:2:glm:1",
                    provider="glm", model="fixture-model", input_price=0.000001, output_price=0.000001,
                    input_token_cap=100, output_token_cap=50, max_requests=8, max_provider_requests=2,
                    per_pr_usd=0.0002, monthly_usd=20.0, pilot_usd=20.0, price_revision="fixture-price-v1")

    def test_ledger_rejects_corrupt_record_before_budget_calculation(self):
        config = test_config()["budget"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            path.write_text(json.dumps({"schema": adapter.LEDGER_SCHEMA, "request_id": "truncated"}) + "\n", encoding="utf-8")
            ledger = adapter.Ledger(path, config)
            with self.assertRaisesRegex(adapter.AdmissionDenied, "invalid record"):
                ledger.admit(
                    approval_id="fixture-approval", attempt_id="run:3", request_id="run:3:deepseek:1",
                    provider="deepseek", model="fixture-model", input_price=0.000001,
                    output_price=0.000001, input_token_cap=100, output_token_cap=50,
                    max_requests=8, max_provider_requests=2, per_pr_usd=1.0,
                    monthly_usd=20.0, pilot_usd=20.0, price_revision="fixture-price-v1")

    def test_ledger_rejects_nonfinite_record_amount(self):
        config = test_config()["budget"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            path.write_text(json.dumps({
                "schema": adapter.LEDGER_SCHEMA, "approval_id": "fixture-approval", "currency": "USD",
                "attempt_id": "run:4", "request_id": "run:4:deepseek:1", "provider": "deepseek",
                "effective_model": "fixture-model", "price_revision": "fixture-price-v1",
                "reserved_amount_usd": float("nan"), "actual_amount_usd": None, "status": "reserved",
                "month": "2026-09", "created_at": "2026-09-10T00:00:00Z",
            }) + "\n", encoding="utf-8")
            ledger = adapter.Ledger(path, config)
            with self.assertRaisesRegex(adapter.AdmissionDenied, "invalid record"):
                ledger._records()

    def test_ledger_amounts_round_up_conservatively(self):
        config = test_config()["budget"]
        with tempfile.TemporaryDirectory() as directory:
            ledger = adapter.Ledger(Path(directory) / "ledger.jsonl", config)
            reservation = ledger.admit(
                approval_id="fixture-approval", attempt_id="run:5", request_id="run:5:deepseek:1",
                provider="deepseek", model="fixture-model", input_price=0.0000000000001,
                output_price=0.0000000000001, input_token_cap=1, output_token_cap=1,
                max_requests=8, max_provider_requests=2, per_pr_usd=1.0,
                monthly_usd=20.0, pilot_usd=20.0, price_revision="fixture-price-v1")
            self.assertEqual(reservation["reserved_amount_usd"], 0.000000000001)
            ledger.reconcile(reservation, status="reconciled", actual_amount=0.0000000000001,
                             usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
            record = json.loads(Path(directory, "ledger.jsonl").read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(record["actual_amount_usd"], 0.000000000001)

    def test_ledger_uses_larger_reconciled_usage_for_future_admission(self):
        config = test_config(per_pr=0.0004)["budget"]
        with tempfile.TemporaryDirectory() as directory:
            ledger = adapter.Ledger(Path(directory) / "ledger.jsonl", config)
            reservation = ledger.admit(
                approval_id="fixture-approval", attempt_id="run:6", request_id="run:6:deepseek:1",
                provider="deepseek", model="fixture-model", input_price=0.000001,
                output_price=0.000001, input_token_cap=100, output_token_cap=50,
                max_requests=8, max_provider_requests=2, per_pr_usd=0.0004,
                monthly_usd=20.0, pilot_usd=20.0, price_revision="fixture-price-v1")
            ledger.reconcile(reservation, status="reconciled", actual_amount=0.0003,
                             usage={"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300})
            with self.assertRaisesRegex(adapter.AdmissionDenied, "request cost budget exhausted"):
                ledger.admit(
                    approval_id="fixture-approval", attempt_id="run:6", request_id="run:6:deepseek:2",
                    provider="deepseek", model="fixture-model", input_price=0.000001,
                    output_price=0.000001, input_token_cap=100, output_token_cap=50,
                    max_requests=8, max_provider_requests=2, per_pr_usd=0.0004,
                    monthly_usd=20.0, pilot_usd=20.0, price_revision="fixture-price-v1")

    def test_ledger_rejects_nonfinite_admission_price(self):
        config = test_config()["budget"]
        with tempfile.TemporaryDirectory() as directory:
            ledger = adapter.Ledger(Path(directory) / "ledger.jsonl", config)
            with self.assertRaisesRegex(adapter.AdmissionDenied, "pricing is invalid"):
                ledger.admit(
                    approval_id="fixture-approval", attempt_id="run:7", request_id="run:7:deepseek:1",
                    provider="deepseek", model="fixture-model", input_price=float("nan"),
                    output_price=0.000001, input_token_cap=100, output_token_cap=50,
                    max_requests=8, max_provider_requests=2, per_pr_usd=1.0,
                    monthly_usd=20.0, pilot_usd=20.0, price_revision="fixture-price-v1")

    def test_ledger_rejects_duplicate_reservation_and_mismatched_finalization(self):
        config = test_config()["budget"]
        with tempfile.TemporaryDirectory() as directory:
            ledger = adapter.Ledger(Path(directory) / "ledger.jsonl", config)
            kwargs = dict(approval_id="fixture-approval", attempt_id="run:duplicate", model="fixture-model",
                          input_price=0.000001, output_price=0.000001, input_token_cap=100,
                          output_token_cap=50, max_requests=8, max_provider_requests=2,
                          per_pr_usd=1.0, monthly_usd=20.0, pilot_usd=20.0,
                          price_revision="fixture-price-v1")
            reservation = ledger.admit(request_id="run:duplicate:deepseek:1", provider="deepseek", **kwargs)
            with self.assertRaisesRegex(adapter.AdmissionDenied, "duplicate request admission"):
                ledger.admit(request_id="run:duplicate:deepseek:1", provider="deepseek", **kwargs)
            mismatched = {**reservation, "effective_model": "other-model"}
            with self.assertRaisesRegex(adapter.AdmissionDenied, "reservation identity"):
                ledger.reconcile(mismatched, status="uncertain", actual_amount=None, usage=None)
            ledger.reconcile(reservation, status="uncertain", actual_amount=None, usage=None)
            with self.assertRaisesRegex(adapter.AdmissionDenied, "already finalized"):
                ledger.reconcile(reservation, status="uncertain", actual_amount=None, usage=None)

    def test_ledger_rejects_unknown_usage_instead_of_refunding_reservation(self):
        config = test_config()["budget"]
        with tempfile.TemporaryDirectory() as directory:
            ledger = adapter.Ledger(Path(directory) / "ledger.jsonl", config)
            reservation = ledger.admit(
                approval_id="fixture-approval", attempt_id="run:unknown", request_id="run:unknown:deepseek:1",
                provider="deepseek", model="fixture-model", input_price=0.000001, output_price=0.000001,
                input_token_cap=100, output_token_cap=50, max_requests=8, max_provider_requests=2,
                per_pr_usd=1.0, monthly_usd=20.0, pilot_usd=20.0, price_revision="fixture-price-v1")
            with self.assertRaisesRegex(adapter.AdmissionDenied, "validated usage"):
                ledger.reconcile(reservation, status="reconciled", actual_amount=0.0,
                                 usage={"prompt_tokens": "unknown", "completion_tokens": 0, "total_tokens": 0})
            self.assertEqual(len(ledger._records()), 1)

    def test_request_count_cap_is_per_attempt_not_global(self):
        config = test_config()["budget"]
        with tempfile.TemporaryDirectory() as directory:
            ledger = adapter.Ledger(Path(directory) / "ledger.jsonl", config)
            kwargs = dict(approval_id="fixture-approval", model="fixture-model", input_price=0.000001,
                          output_price=0.000001, input_token_cap=1, output_token_cap=1, max_requests=2,
                          max_provider_requests=2, per_pr_usd=1.0, monthly_usd=20.0, pilot_usd=20.0,
                          price_revision="fixture-price-v1", provider="deepseek")
            ledger.admit(attempt_id="run:a", request_id="run:a:deepseek:1", **kwargs)
            ledger.admit(attempt_id="run:a", request_id="run:a:deepseek:2", **kwargs)
            with self.assertRaisesRegex(adapter.AdmissionDenied, "request count"):
                ledger.admit(attempt_id="run:a", request_id="run:a:deepseek:3", **kwargs)
            ledger.admit(attempt_id="run:b", request_id="run:b:deepseek:1", **kwargs)

    def test_engine_cwd_inside_worktree_dot_git_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").write_text("gitdir: /nowhere\n", encoding="utf-8")
            with self.assertRaisesRegex(adapter.EngineError, "must not be inside a repository"):
                with adapter._isolated_environment(root, "__never_read__", "__never_read__"):
                    pass

    def test_engine_cwd_symlink_into_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "sub").mkdir(parents=True)
            (repo / ".git").write_text("gitdir: /nowhere\n", encoding="utf-8")
            link = root / "engine"
            link.symlink_to(repo / "sub", target_is_directory=True)
            with self.assertRaisesRegex(adapter.EngineError, "symlink"):
                with adapter._isolated_environment(link, "__never_read__", "__never_read__"):
                    pass

    def test_unapproved_credential_reference_is_rejected(self):
        config = test_config()
        invalid = copy.deepcopy(config)
        invalid["providers"]["deepseek"]["credential_ref"] = "GITHUB_TOKEN"
        invalid["providers"]["deepseek"].update(pricing_verified=True, funding_verified=True)
        with self.assertRaisesRegex(adapter.EngineError, "model or credential"):
            adapter._safe_config({"schema": adapter.CONFIG_SCHEMA, "budget": config["budget"],
                                  "providers": invalid["providers"], "provider_order": config["provider_order"]})

    def test_upstream_import_does_not_leave_source_path_in_process_path(self):
        if not SOURCE_ROOT.joinpath("pr_agent").is_dir():
            self.skipTest(f"pinned PR-Agent source is unavailable: {SOURCE_ROOT}")
        before = list(sys.path)
        with tempfile.TemporaryDirectory() as directory:
            source = bound_source(SOURCE_ROOT, Path(directory) / "source")
            with adapter._isolated_environment(Path(directory) / "engine", "__never_read__", "__never_read__"):
                try:
                    with mock.patch.object(adapter, "TRUSTED_ENGINE_ROOT", source):
                        adapter._import_upstream(source)
                except adapter.EngineError as exc:
                    self.assertEqual(exc.error_class, "engine_unavailable")
        self.assertEqual(sys.path, before)

    def test_upstream_import_rejects_unbound_source(self):
        if not SOURCE_ROOT.joinpath("pr_agent").is_dir():
            self.skipTest(f"pinned PR-Agent source is unavailable: {SOURCE_ROOT}")
        with self.assertRaisesRegex(adapter.EngineError, "immutable engine installation"):
            adapter._import_upstream(SOURCE_ROOT)

    def test_upstream_import_rejects_recomputed_manifest_after_source_forgery(self):
        if not SOURCE_ROOT.joinpath("pr_agent").is_dir():
            self.skipTest(f"pinned PR-Agent source is unavailable: {SOURCE_ROOT}")
        with tempfile.TemporaryDirectory() as directory:
            source = bound_source(SOURCE_ROOT, Path(directory) / "source")
            target = source / "pr_agent" / "algo" / "types.py"
            target.write_text(target.read_text(encoding="utf-8") + "\n# forged\n", encoding="utf-8")
            (source / "IDENTITY").write_text(
                "schema=lmdj.pr-agent-bundle.v1\n"
                f"source_commit={adapter.UPSTREAM_COMMIT}\n"
                f"source_version={adapter.UPSTREAM_VERSION}\n"
                f"source_tree_sha256={adapter._source_tree_sha256(source)}\n",
                encoding="utf-8",
            )
            with mock.patch.object(adapter, "TRUSTED_ENGINE_ROOT", source):
                with self.assertRaisesRegex(adapter.EngineError, "source identity is missing"):
                    adapter._import_upstream(source)

    def test_upstream_import_rejects_supplied_bytecode(self):
        if not SOURCE_ROOT.joinpath("pr_agent").is_dir():
            self.skipTest(f"pinned PR-Agent source is unavailable: {SOURCE_ROOT}")
        with tempfile.TemporaryDirectory() as directory:
            source = bound_source(SOURCE_ROOT, Path(directory) / "source")
            cache = source / "pr_agent" / "__pycache__"
            cache.mkdir()
            (cache / "forged.cpython-312.pyc").write_bytes(b"not verified")
            with mock.patch.object(adapter, "TRUSTED_ENGINE_ROOT", source):
                with self.assertRaisesRegex(adapter.EngineError, "unverified bytecode"):
                    adapter._import_upstream(source)


class RealHandlerIntegrationTests(unittest.TestCase):
    """Run in a Python 3.12 environment containing the locked PR-Agent deps."""

    def setUp(self):
        if os.environ.get("PR_AGENT_RUN_INTEGRATION") != "1":
            self.skipTest(
                "actual PR-Agent seam is an explicit bundle-lane proof; set "
                "PR_AGENT_RUN_INTEGRATION=1 with PR_AGENT_TEST_PYTHON and "
                "PR_AGENT_TEST_SOURCE_ROOT to run it"
            )
        if not SOURCE_ROOT.joinpath("pr_agent").is_dir():
            self.fail(f"pinned PR-Agent source is unavailable: {SOURCE_ROOT}")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source_root = SOURCE_ROOT if (SOURCE_ROOT / "IDENTITY").is_file() else bound_source(SOURCE_ROOT, self.root / "source")
        self.trusted_engine_root = mock.patch.object(adapter, "TRUSTED_ENGINE_ROOT", self.source_root)
        self.trusted_engine_root.start()
        self.addCleanup(self.trusted_engine_root.stop)
        self.input_path = self.root / "input.json"
        self.input_path.write_text(json.dumps(json.loads((FIXTURES / "complete-input.json").read_text()), indent=2), encoding="utf-8")
        self.config_path = self.root / "config.toml"
        self.config_path.write_text(
            "schema = \"lmdj.pr-agent-config.v1\"\nprovider_order = [\"deepseek\"]\n\n"
            "[budget]\napproval_id = \"fixture-approval\"\ntimezone = \"Asia/Shanghai\"\nmonthly_usd = 20.0\n"
            "pilot_usd = 20.0\nper_pr_usd = 1.0\nmax_requests = 8\nmax_requests_per_provider = 2\n"
            "request_timeout_seconds = 60\nbackoff_seconds = 0\nengine_deadline_seconds = 600\n"
            "input_token_cap = 100\noutput_token_cap = 50\n\n[providers.deepseek]\n"
            "enabled = true\nendpoint = \"https://deepseek.invalid.example/v1\"\nmodel = \"fixture-deepseek-model\"\n"
            "credential_ref = \"PR_AGENT_DEEPSEEK_API_KEY\"\npricing_revision = \"fixture-price-v1\"\n"
            "input_price_usd_per_token = 0.000001\noutput_price_usd_per_token = 0.000001\n"
            "pricing_verified = true\nfunding_ref = \"fixture-funding-v1\"\nfunding_verified = true\n\n"
            "[providers.glm]\nenabled = false\n\n[providers.xai]\nenabled = false\n\n"
            "[providers.kimi]\nenabled = false\n",
            encoding="utf-8",
        )

    def run_with_fake(self, fake):
        hostile = self.root / "engine"
        hostile.mkdir()
        (hostile / "pyproject.toml").write_text("not = [valid", encoding="utf-8")
        (hostile / ".pr_agent.toml").write_text("PR_AGENT_TEST_KEY = 'must not be read'", encoding="utf-8")
        ledger = self.root / "ledger.jsonl"
        with adapter._isolated_environment(hostile, "__never_read__", "__never_read__"):
            upstream = adapter._import_upstream(self.source_root)
        upstream["litellm_ai_handler"].acompletion = fake
        with mock.patch.object(adapter, "_import_upstream", return_value=upstream), \
                mock.patch.object(adapter, "TRUSTED_CONFIG_ROOT", self.root), \
                mock.patch.dict(os.environ, {"PR_AGENT_DEEPSEEK_API_KEY": "fixture-secret", "GITHUB_TOKEN": "must-not-leak",
                                              "PR_AGENT_CONFIG_BRANCH": "must-not-read", "DYNACONF_CONFIG__MODEL": "must-not-read",
                                              "OPENAI_API_KEY": "must-not-read"}, clear=False):
            return adapter.run_engine(self.input_path, config_path=self.config_path, source_root=self.source_root,
                                      engine_cwd=hostile, ledger_path=ledger), upstream, ledger

    def test_stock_reviewer_receives_every_authenticated_segment_and_captures_native_output(self):
        calls = []
        response_text = (FIXTURES / "valid-native-review.yaml").read_text(encoding="utf-8")

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            self.assertEqual(os.environ.get("DEEPSEEK_API_KEY"), "fixture-secret")
            for name in ("GITHUB_TOKEN", "PR_AGENT_CONFIG_BRANCH", "DYNACONF_CONFIG__MODEL", "OPENAI_API_KEY"):
                self.assertIsNone(os.environ.get(name), name)
            return FakeCompletion({"choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                                   "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}})

        result, upstream, ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(result["selected_attempt"], 0)
        attempt = result["attempts"][0]
        self.assertTrue(attempt["coverage"]["complete"])
        self.assertEqual(attempt["engine"]["source_commit"], adapter.UPSTREAM_COMMIT)
        self.assertEqual(attempt["review"]["findings"][0]["path"], "src/example.py")
        self.assertEqual(len(calls), 1, "why: one complete prompt is the pilot contract; remedy: disable hidden chunk/retry paths")
        prompt = "\n".join(str(item.get("content", "")) for item in calls[0]["messages"])
        for expected in ("return 1", "return 2", "removed content", "src-example-h1", "obsolete-h1"):
            self.assertIn(expected, prompt)
        self.assertNotIn("must-not-leak", prompt)
        records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual({record["status"] for record in records}, {"reserved", "reconciled"})
        self.assertNotIn("fixture-secret", ledger.read_text(encoding="utf-8"))
        self.assertEqual(
            list(self.source_root.rglob("*.pyc")), [],
            "why: the trusted source must not acquire unverified bytecode during import; "
            "remedy: keep PYTHONDONTWRITEBYTECODE enabled for the engine boundary",
        )

    def test_authentication_failure_is_not_retried_by_the_stock_decorator(self):
        calls = []

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            raise RuntimeError("401 unauthorized fixture")

        result, _upstream, _ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["attempts"][0]["error_class"], "authentication_error")
        self.assertEqual(len(calls), 1, "why: authentication errors cannot improve on replay; remedy: advance or stop")

    def test_transient_failure_uses_one_stock_retry_and_two_ledger_admissions(self):
        calls = []
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise RuntimeError("503 temporary network fixture")
            return FakeCompletion({"choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                                   "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})

        result, _upstream, ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["attempts"][0]["usage"]["num_ai_calls"], 2)
        records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(records), 4)
        self.assertEqual({record["request_id"] for record in records},
                         {"t2-fixture-run:1:deepseek:1", "t2-fixture-run:1:deepseek:2"})

    def test_rate_limit_failure_uses_one_bounded_retry(self):
        calls = []
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise RuntimeError("429 rate limit fixture")
            return FakeCompletion({"choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                                   "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})

        result, _upstream, _ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(len(calls), 2)

    def test_timeout_failure_has_one_actual_seam_call_and_retains_uncertain_reservation(self):
        calls = []
        response_text = (FIXTURES / "clean-native-review.yaml").read_text(encoding="utf-8")

        async def fake_acompletion(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise TimeoutError("timed out fixture")
            return FakeCompletion({"choices": [{"message": {"content": response_text}, "finish_reason": "stop"}],
                                   "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})

        result, _upstream, ledger = self.run_with_fake(fake_acompletion)
        self.assertEqual(result["status"], "not-reviewed")
        self.assertEqual(result["attempts"][0]["error_class"], "timeout")
        self.assertEqual(len(calls), 1, "why: timeout is not retryable by the approved design; remedy: retain the uncertain reservation and advance or stop")
        records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.assertEqual({record["status"] for record in records}, {"reserved", "uncertain"})


class IntegrationProxyTests(unittest.TestCase):
    def test_litellm_import_uses_bundled_cost_map_without_metadata_http(self):
        """The pinned engine import must not fetch mutable LiteLLM metadata."""
        if os.environ.get("PR_AGENT_RUN_INTEGRATION") != "1":
            self.skipTest(
                "bundled LiteLLM map proof is an explicit pinned-runtime lane; set "
                "PR_AGENT_RUN_INTEGRATION=1 with PR_AGENT_TEST_PYTHON and "
                "PR_AGENT_TEST_SOURCE_ROOT to run it"
            )
        runtime_value = os.environ.get("PR_AGENT_TEST_PYTHON")
        source_value = os.environ.get("PR_AGENT_TEST_SOURCE_ROOT")
        if not runtime_value or not source_value:
            self.fail(
                "why: bundled LiteLLM map proof lacks its pinned runtime/source; "
                "remedy: provide PR_AGENT_TEST_PYTHON and PR_AGENT_TEST_SOURCE_ROOT"
            )
        runtime = Path(runtime_value)
        source_root = Path(source_value)
        if not runtime.is_file() or not (source_root / "IDENTITY").is_file():
            self.fail(
                "why: bundled LiteLLM map proof inputs are unavailable; "
                "remedy: run the pinned integration preparation first"
            )
        probe = r'''
import importlib.metadata
import json
import os
import sys
from pathlib import Path

import httpx

calls = []
def forbidden_get(url, *args, **kwargs):
    calls.append({"url": url, "timeout": kwargs.get("timeout")})
    raise AssertionError("LiteLLM attempted mutable model metadata HTTP")

httpx.get = forbidden_get
os.environ.pop("LITELLM_LOCAL_MODEL_COST_MAP", None)
sys.path.insert(0, sys.argv[1])
import pr_agent_review as adapter

source_root = Path(sys.argv[2])
adapter.TRUSTED_ENGINE_ROOT = source_root
upstream = adapter._import_upstream(source_root)
litellm = upstream["litellm_ai_handler"].litellm
from litellm.litellm_core_utils.get_model_cost_map import get_model_cost_map_source_info

info = get_model_cost_map_source_info()
assert importlib.metadata.version("litellm") == "1.100.0"
assert os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP") == "true"
assert calls == [], calls
assert info["source"] == "local", info
assert info["is_env_forced"] is True, info
assert info["url"] is None, info
assert len(litellm.model_cost) > 0
print(json.dumps({"calls": calls, "source": info, "model_cost_entries": len(litellm.model_cost)}))
'''
        environment = dict(os.environ)
        environment.pop("LITELLM_LOCAL_MODEL_COST_MAP", None)
        completed = subprocess.run(
            [str(runtime), "-c", probe, str(ROOT / "scripts/ci"), str(source_root)],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=120,
        )
        self.assertEqual(
            completed.returncode,
            0,
            "why: the trusted engine import must select its bundled LiteLLM map "
            "without metadata HTTP; remedy: force the local-map boundary before "
            f"the first LiteLLM import\nstdout={completed.stdout}\nstderr={completed.stderr}",
        )

    def test_real_handler_suite_runs_in_pinned_python_environment(self):
        if os.environ.get("PR_AGENT_RUN_INTEGRATION") != "1":
            self.skipTest(
                "actual PR-Agent seam is an explicit bundle-lane proof; set "
                "PR_AGENT_RUN_INTEGRATION=1 with PR_AGENT_TEST_PYTHON and "
                "PR_AGENT_TEST_SOURCE_ROOT to run it"
            )
        runtime_value = os.environ.get("PR_AGENT_TEST_PYTHON")
        source_value = os.environ.get("PR_AGENT_TEST_SOURCE_ROOT")
        if not runtime_value or not source_value:
            self.fail(
                "why: integration proof was explicitly enabled without its pinned runtime and source; "
                "remedy: provide PR_AGENT_TEST_PYTHON and an identity-bound PR_AGENT_TEST_SOURCE_ROOT"
            )
        runtime = Path(runtime_value)
        source_root = Path(source_value)
        if not runtime.is_file() or not source_root.is_dir():
            self.fail(
                "why: the explicitly selected pinned integration inputs are unavailable; "
                "remedy: prepare the locked Python runtime and identity-bound bundle source before this lane"
            )
        if not (source_root / "IDENTITY").is_file():
            self.fail(
                "why: the explicitly selected integration source has no bundle identity; "
                "remedy: use the preparation command to create the pinned source manifest"
            )
        environment = dict(os.environ)
        environment["PR_AGENT_RUN_INTEGRATION"] = "1"
        environment["PR_AGENT_TEST_SOURCE_ROOT"] = str(source_root)
        completed = subprocess.run(
            [str(runtime), str(Path(__file__)), "--integration-child"],
            cwd=ROOT, env=environment, text=True, capture_output=True, timeout=120,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


def run_suite(integration_child=False):
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(RealHandlerIntegrationTests if integration_child else InputAndPolicyTests))
    if not integration_child:
        suite.addTests(loader.loadTestsFromTestCase(IntegrationProxyTests))
    return unittest.TextTestRunner(verbosity=2).run(suite)


if __name__ == "__main__":
    failed = not run_suite("--integration-child" in sys.argv).wasSuccessful()
    raise SystemExit(1 if failed else 0)
