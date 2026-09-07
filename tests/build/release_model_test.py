#!/usr/bin/env python3
"""Contract tests for the closed release policy and intent ledger."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from dataclasses import replace
import subprocess


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.release.model import (  # noqa: E402
    ReleaseKind,
    ReleaseModelError,
    canonical_json,
    canonical_sha256,
    classify_tag,
    load_ledger,
    load_ledger_document,
    load_policy,
)


class ReleaseModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy(ROOT / "tools/release/policy.json")

    def ledger_fixture(
        self,
        *,
        disposition: str = "published",
        channel: str = "canary",
        profile: str = "web-runtime-host",
        with_exception: bool = False,
    ) -> dict[str, object]:
        document: dict[str, object] = {
            "schema": "lmdj.release-intents.v1",
            "entries": [{
                "tag": "lmdj-v1.2.3.4",
                "kind": "product",
                "identity": "1.2.3.4",
                "target_revision": "a" * 40,
                "channel": channel,
                "disposition": disposition,
                "profile": profile,
                "snapshot": "1.2.3.4",
                "merged_main_run_id": 123,
                "evidence_paths": ["docs/release-evidence/example.md"],
            }],
            "historical_exceptions": [],
        }
        if with_exception:
            document["historical_exceptions"] = [{
                "tag": "lmdj-v1.2.3.4",
                "target_revision": "a" * 40,
                "observed_before": "2026-08-12T23:59:59Z",
                "code": "pre-pipeline-ci-evidence",
                "reason": "A pre-control-plane run was cancelled.",
                "evidence_paths": ["docs/release-evidence/example.md"],
            }]
        return document

    def test_classifies_all_formal_tag_kinds_and_rejects_nonrelease_tags(self) -> None:
        cases = {
            "lmdj-v1.0.16.9": (ReleaseKind.PRODUCT, ("1.0.16.9",)),
            "module/project-io/v0.3.0": (ReleaseKind.MODULE, ("project-io", "0.3.0")),
            "contract/project-bundle/v2.1.0": (ReleaseKind.CONTRACT, ("project-bundle", "2.1.0")),
            "provider/local-proof/v1.4.2": (ReleaseKind.PROVIDER, ("local-proof", "1.4.2")),
        }
        for tag, expected in cases.items():
            with self.subTest(tag=tag):
                identity = classify_tag(tag, self.policy)
                self.assertEqual((identity.kind, identity.identity), expected)
        for tag in (
            "lmdj-m1-plan.1", "v0.2.0", "wip/chameleon-2d-2026-07-26",
            "lmdj-v1.2.3", "module/project-io/v1.2", "module//v1.2.3",
            "module/project-io/v01.2.3", "lmdj-v1.2.3.04",
        ):
            with self.subTest(tag=tag):
                with self.assertRaises(ReleaseModelError):
                    classify_tag(tag, self.policy)

    def test_policy_is_closed_and_uses_exact_trust_anchors(self) -> None:
        self.assertEqual(self.policy.repository, "endaye/lmdj")
        self.assertEqual(self.policy.branch, "main")
        self.assertEqual(self.policy.blocking_workflow, "Core CI")
        self.assertEqual(self.policy.product_fingerprint, "2B5EE362F058800036AD4FB5116ECE156F954D29")
        self.assertEqual(self.policy.checksum_fingerprint, "CB928A6E89DE498851688EF1AAC3E7019FC1478B")
        self.assertEqual(
            self.policy.product_profiles,
            frozenset(("core-package", "web-runtime-host", "web-hosts")),
        )
        self.assertEqual(self.policy.release_environment, "release")
        self.assertEqual(self.policy.runtime_canary_environment, "runtime-canary")
        self.assertEqual(self.policy.creator_canary_environment, "creator-canary")
        self.assertEqual(self.policy.channel_release("canary"), (True, False))
        self.assertEqual(self.policy.channel_release("stable", make_latest=False), (False, False))
        self.assertEqual(self.policy.channel_release("stable", make_latest=True), (False, True))

    def test_policy_requires_the_exact_canonical_blocking_workflow_key(self) -> None:
        document = json.loads((ROOT / "tools/release/policy.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            del document["blocking_workflow"]
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ReleaseModelError, "missing fields"):
                load_policy(path)

            document["blocking_workflow"] = "Unrelated workflow"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ReleaseModelError, "blocking workflow"):
                load_policy(path)

    def test_ledger_accepts_the_closed_dual_web_host_profile(self) -> None:
        ledger = load_ledger_document(
            self.ledger_fixture(profile="web-hosts"),
            self.policy,
        )
        self.assertEqual(ledger.entries[0].profile, "web-hosts")

    def test_ledger_rejects_unknown_fields_duplicate_identities_and_bad_scalars(self) -> None:
        cases: list[tuple[str, dict[str, object], str]] = []
        unknown = self.ledger_fixture()
        unknown["entries"][0]["unknown"] = "nope"  # type: ignore[index]
        cases.append(("unknown field", unknown, "unexpected"))
        duplicate = self.ledger_fixture()
        duplicate["entries"].append(copy.deepcopy(duplicate["entries"][0]))  # type: ignore[index]
        cases.append(("duplicate tag", duplicate, "duplicate"))
        bad_sha = self.ledger_fixture()
        bad_sha["entries"][0]["target_revision"] = "A" * 40  # type: ignore[index]
        cases.append(("uppercase sha", bad_sha, "target_revision"))
        bad_run = self.ledger_fixture()
        bad_run["entries"][0]["merged_main_run_id"] = True  # type: ignore[index]
        cases.append(("boolean run id", bad_run, "merged_main_run_id"))
        for name, document, message in cases:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ReleaseModelError, message):
                    load_ledger_document(document, self.policy)

    def test_ledger_enforces_kind_channel_profile_and_disposition_rules(self) -> None:
        cases: list[tuple[str, dict[str, object], str]] = []
        module = self.ledger_fixture()
        module["entries"][0] = {
            "tag": "module/project-io/v0.3.0", "kind": "module",
            "identity": "project-io@0.3.0", "target_revision": "b" * 40,
            "channel": "canary", "disposition": "published", "profile": "source-only",
            "merged_main_run_id": 456, "evidence_paths": ["docs/release-evidence/example.md"],
        }
        cases.append(("module channel", module, "channel"))
        wrong_profile = self.ledger_fixture(profile="source-only")
        cases.append(("product source-only", wrong_profile, "profile"))
        invalid_disposition = self.ledger_fixture()
        invalid_disposition["entries"][0]["disposition"] = "draft"  # type: ignore[index]
        cases.append(("unknown disposition", invalid_disposition, "disposition"))
        for name, document, message in cases:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ReleaseModelError, message):
                    load_ledger_document(document, self.policy)

    def test_make_latest_is_explicit_stable_product_only(self) -> None:
        stable_missing = self.ledger_fixture(channel="stable")
        with self.assertRaisesRegex(ReleaseModelError, "make_latest"):
            load_ledger_document(stable_missing, self.policy)
        stable = self.ledger_fixture(channel="stable")
        stable["entries"][0]["make_latest"] = True  # type: ignore[index]
        ledger = load_ledger_document(stable, self.policy)
        self.assertTrue(ledger.entries[0].make_latest)
        canary = self.ledger_fixture()
        canary["entries"][0]["make_latest"] = False  # type: ignore[index]
        with self.assertRaisesRegex(ReleaseModelError, "make_latest"):
            load_ledger_document(canary, self.policy)

    def test_exception_cannot_authorize_releasable_and_is_exact_historical_only(self) -> None:
        with self.assertRaisesRegex(ReleaseModelError, "historical exception"):
            load_ledger_document(
                self.ledger_fixture(disposition="releasable", with_exception=True), self.policy
            )
        future = self.ledger_fixture(with_exception=True)
        future["historical_exceptions"][0]["observed_before"] = "2026-08-13T00:00:00Z"  # type: ignore[index]
        with self.assertRaisesRegex(ReleaseModelError, "observed_before"):
            load_ledger_document(future, self.policy)

    def test_tracked_ledger_records_the_full_formal_inventory_and_lifecycle_rows(self) -> None:
        ledger = load_ledger(ROOT / "docs/release-evidence/release-intents.json", self.policy)
        formal = [entry for entry in ledger.entries if entry.tag in {
            "lmdj-v1.0.1.0", "lmdj-v1.0.2.0", "lmdj-v1.0.3.0", "lmdj-v1.0.4.0",
            "lmdj-v1.0.5.0", "lmdj-v1.0.6.0", "lmdj-v1.0.7.0", "lmdj-v1.0.8.0",
            "lmdj-v1.0.9.0", "lmdj-v1.0.10.0", "lmdj-v1.0.11.0", "lmdj-v1.0.13.0",
            "lmdj-v1.0.14.0", "lmdj-v1.0.15.2", "lmdj-v1.0.16.5", "lmdj-v1.0.16.8",
            "lmdj-v1.0.16.9",
        } or entry.kind is ReleaseKind.MODULE]
        self.assertEqual(len(formal), 28)
        superseded = ledger.intent_for_tag("lmdj-v1.0.20.0")
        self.assertIsNotNone(superseded)
        self.assertEqual(  # type: ignore[union-attr]
            superseded.disposition.value, "superseded-unreleased",
        )
        self.assertEqual(  # type: ignore[union-attr]
            superseded.target_revision,
            "f4674ada631d6af7ad8b9dd9f440671c2736d293",
        )
        allocated = ledger.intent_for_tag("lmdj-v1.0.21.0")
        self.assertIsNotNone(allocated)
        self.assertEqual(allocated.disposition.value, "allocated")  # type: ignore[union-attr]
        self.assertEqual(  # type: ignore[union-attr]
            allocated.target_revision,
            "5613158240f7e31385ccb5d175bded3c245ae33b",
        )
        self.assertEqual(allocated.snapshot, "1.0.21.0")  # type: ignore[union-attr]
        stage8 = ledger.intent_for_tag("lmdj-v1.0.22.0")
        self.assertIsNotNone(stage8)
        self.assertEqual(stage8.disposition.value, "allocated")  # type: ignore[union-attr]
        # The squash merge of #137, matching how 1.0.21.0 above records the
        # squash merge of #134: a release target must be reachable on main,
        # because prepare requires main ancestry and checks the revision out.
        self.assertEqual(  # type: ignore[union-attr]
            stage8.target_revision,
            "51d9e4748cc12a4423954a159949b7b165513789",
        )
        self.assertEqual(stage8.snapshot, "1.0.22.0")  # type: ignore[union-attr]
        candidate = ledger.intent_for_tag("lmdj-v1.0.36.0")
        self.assertIsNotNone(candidate)
        # Published 2026-08-26 through publish-release.yml run 32982586705.
        self.assertEqual(candidate.disposition.value, "published")  # type: ignore[union-attr]
        self.assertEqual(candidate.channel, "canary")  # type: ignore[union-attr]
        self.assertEqual(candidate.profile, "web-runtime-host")  # type: ignore[union-attr]
        self.assertEqual(  # type: ignore[union-attr]
            candidate.target_revision,
            "4a145f4aeba8594cf4b9c53cddfe8a67fabb5bf2",
        )
        self.assertEqual(candidate.snapshot, "1.0.36.0")  # type: ignore[union-attr]
        self.assertEqual(candidate.merged_main_run_id, 32857088479)  # type: ignore[union-attr]
        self.assertEqual(  # type: ignore[union-attr]
            candidate.evidence_paths,
            ("docs/release-evidence/2026-08-25-lmdj-1.0.36.0-canary-release-intent.md",),
        )
        stage9 = ledger.intent_for_tag("lmdj-v1.0.40.0")
        self.assertIsNotNone(stage9)
        # Published 2026-09-01 through publish-release.yml run 33453258287.
        # Its target is the squash merge of #420, which carries both the Task 10
        # version integration and the Task 11 immutable snapshot; the exact-main
        # full run was dispatched on that same SHA.
        self.assertEqual(stage9.disposition.value, "published")  # type: ignore[union-attr]
        self.assertEqual(stage9.channel, "canary")  # type: ignore[union-attr]
        self.assertEqual(stage9.profile, "web-runtime-host")  # type: ignore[union-attr]
        self.assertEqual(  # type: ignore[union-attr]
            stage9.target_revision,
            "bb0544c46d4b3fc3a7c96cb848e10cdecb4be040",
        )
        self.assertEqual(stage9.snapshot, "1.0.40.0")  # type: ignore[union-attr]
        self.assertEqual(stage9.merged_main_run_id, 33259586218)  # type: ignore[union-attr]
        self.assertEqual(  # type: ignore[union-attr]
            stage9.evidence_paths,
            ("docs/release-evidence/2026-08-31-lmdj-1.0.40.0-canary-release-intent.md",),
        )
        stage10 = ledger.intent_for_tag("lmdj-v1.0.42.0")
        self.assertIsNotNone(stage10)
        # Published 2026-09-06 through publish-release.yml run 34017371873.
        # Task 12 bound TARGET to the Task 11 squash on protected main, which
        # is the first main commit that contains the 1.0.42.0 squash witness.
        # The Task 10 squash (0ffa77c0) froze the snapshot but does not carry
        # that witness file. The Integration Queue merges with GITHUB_TOKEN, so
        # the squash produced no push-event Core CI run and the exact-main full
        # run was dispatched on that same SHA.
        self.assertEqual(stage10.disposition.value, "published")  # type: ignore[union-attr]
        self.assertEqual(stage10.channel, "canary")  # type: ignore[union-attr]
        self.assertEqual(stage10.profile, "web-hosts")  # type: ignore[union-attr]
        self.assertEqual(  # type: ignore[union-attr]
            stage10.target_revision,
            "59cc202b3f4d772814c8de8c1d0c0e6203485a11",
        )
        self.assertEqual(stage10.snapshot, "1.0.42.0")  # type: ignore[union-attr]
        self.assertEqual(stage10.merged_main_run_id, 33996811880)  # type: ignore[union-attr]
        self.assertEqual(  # type: ignore[union-attr]
            stage10.evidence_paths,
            ("docs/release-evidence/2026-09-06-lmdj-1.0.42.0-canary-release-intent.md",),
        )
        self.assertEqual(len(ledger.historical_exceptions), 3)

    def test_canonical_json_digest_and_slash_safe_output_name_are_deterministic(self) -> None:
        value = {"z": "中文", "a": [2, 1]}
        self.assertEqual(canonical_json(value), b'{"a":[2,1],"z":"\xe4\xb8\xad\xe6\x96\x87"}\n')
        self.assertEqual(canonical_sha256(value), hashlib.sha256(canonical_json(value)).hexdigest())
        identity = classify_tag("module/project-io/v0.3.0", self.policy)
        self.assertEqual(identity.output_name, "module%2Fproject-io%2Fv0.3.0")
        self.assertNotIn("/", identity.output_name)

    def future_policy(self):
        document = json.loads((ROOT / "tools/release/policy.json").read_text())
        document["prospective_ci_protocol"] = "complete-test-v2"
        document["batch_evidence_source"] = {"repository_id": 11, "workflow_id": 7,
            "workflow_path": ".github/workflows/self-test-report.yml", "producer_revision": "b" * 40}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(json.dumps(document))
            return load_policy(path)

    def batch_ledger(self):
        document = self.ledger_fixture(disposition="releasable")
        suites = sorted(suite["id"] for suite in json.loads((ROOT / "scripts/ci/self_test_policy.json").read_text())["suites"])
        document["entries"][0]["batch_test_evidence"] = {
            "schema": "lmdj.ci-batch-release-reference.v1", "executor_control_revision": "c" * 40,
            "executor_event": "schedule", "run_attempt": 1,
            "origin_record_digest": "d" * 64, "admission_record_digest": "e" * 64, "evidence_digest": "f" * 64,
            "request": {"id": "frozen-candidate", "kind": "candidate", "base": None,
                "target": "a" * 40, "control": "b" * 40, "policy": "f" * 64,
                "selection": {"kind": "full", "suites": suites, "reasons": ["explicit full request"]},
                "origin_run": {"run_id": 122, "attempt": 1}}}
        return document

    def test_current_policy_enables_two_strict_sixteen_suite_sources(self):
        self.assertEqual(self.policy.prospective_ci_protocol, "complete-test-v2")
        self.assertEqual(dict(self.policy.batch_evidence_source), {
            "repository_id": 1286600062, "workflow_id": 352307416,
            "workflow_path": ".github/workflows/self-test-report.yml",
            "producer_revision": "24ee0c4f79e0fe21a89be8813cb0566948583aa4"})

    def test_both_old_protocols_reject_batch_reference_before_legacy_fallback(self):
        for protocol in ("self-test-v1", "ci-scope-v2"):
            with self.subTest(protocol=protocol), self.assertRaisesRegex(ReleaseModelError, "not enabled"):
                load_ledger_document(self.batch_ledger(), replace(self.policy, prospective_ci_protocol=protocol))

    def test_future_model_binds_exact_target_executor_and_event(self):
        intent = load_ledger_document(self.batch_ledger(), self.future_policy()).entries[0]
        self.assertEqual(intent.target_revision, intent.batch_test_evidence["request"]["target"])
        self.assertEqual(intent.merged_main_run_id, 123)
        self.assertEqual(intent.batch_test_evidence["executor_event"], "schedule")
        self.assertIsNone(intent.self_test_evidence)

    def test_batch_reference_is_deeply_immutable_and_canonically_serializable(self):
        document = self.batch_ledger()
        original = copy.deepcopy(document["entries"][0]["batch_test_evidence"])
        reference = load_ledger_document(document, self.future_policy()).entries[0].batch_test_evidence
        document["entries"][0]["batch_test_evidence"]["request"]["target"] = "f" * 40
        self.assertEqual(canonical_json(reference), canonical_json(original))
        with self.assertRaises(TypeError):
            reference["request"]["target"] = "e" * 40
        with self.assertRaises(TypeError):
            reference["request"]["selection"]["suites"][0] = "other"
        with self.assertRaises(TypeError):
            reference["request"]["origin_run"]["attempt"] = 2

    def test_mixed_protocol_references_are_rejected(self):
        document = self.batch_ledger()
        document["entries"][0]["self_test_evidence"] = {}
        with self.assertRaisesRegex(ReleaseModelError, "mixes"):
            load_ledger_document(document, self.future_policy())

    def test_batch_target_cannot_differ_from_intent(self):
        document = self.batch_ledger()
        document["entries"][0]["batch_test_evidence"]["request"]["target"] = "c" * 40
        with self.assertRaisesRegex(ReleaseModelError, "exact intent target"):
            load_ledger_document(document, self.future_policy())

    def test_batch_reference_requires_explicit_executor_run(self):
        document = self.batch_ledger()
        del document["entries"][0]["merged_main_run_id"]
        with self.assertRaisesRegex(ReleaseModelError, "executor"):
            load_ledger_document(document, self.future_policy())

    def test_batch_event_and_nested_attempts_are_strict(self):
        for value in (None, "repository_dispatch", True):
            with self.subTest(value=value):
                document = self.batch_ledger()
                document["entries"][0]["batch_test_evidence"]["executor_event"] = value
                with self.assertRaisesRegex(ReleaseModelError, "event"):
                    load_ledger_document(document, self.future_policy())
        document = self.batch_ledger()
        document["entries"][0]["batch_test_evidence"]["request"]["origin_run"]["attempt"] = True
        with self.assertRaisesRegex(ReleaseModelError, "origin"):
            load_ledger_document(document, self.future_policy())

    def test_pure_reference_and_model_imports_do_not_load_api_or_runtime(self):
        result = subprocess.run([sys.executable, "-c", "import sys; from tools.release import model, batch_reference; assert 'tools.release.github_api' not in sys.modules; assert 'batch_runtime' not in sys.modules"],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_future_policy_requires_explicit_closed_source(self):
        for source in (None, {}, {"repository_id": True, "workflow_id": 7,
                "workflow_path": ".github/workflows/self-test-report.yml", "producer_revision": "b" * 40},
                {"repository_id": 11, "workflow_id": 7, "workflow_path": ".github/workflows/ci.yml", "producer_revision": "b" * 40}):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as directory:
                document = json.loads((ROOT / "tools/release/policy.json").read_text())
                document.update(prospective_ci_protocol="complete-test-v2", batch_evidence_source=source)
                path = Path(directory) / "policy.json"
                path.write_text(json.dumps(document))
                with self.assertRaisesRegex(ReleaseModelError, "batch source policy"):
                    load_policy(path)

    def test_old_current_policy_cannot_carry_a_new_source_block(self):
        document = json.loads((ROOT / "tools/release/policy.json").read_text())
        document["prospective_ci_protocol"] = "self-test-v1"
        document["batch_evidence_source"] = {}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(json.dumps(document))
            with self.assertRaisesRegex(ReleaseModelError, "old CI policy"):
                load_policy(path)

    def test_model_rejects_focused_and_none_batch_references(self):
        for kind in ("focused", "none"):
            with self.subTest(kind=kind):
                document = self.batch_ledger()
                document["entries"][0]["batch_test_evidence"]["request"]["selection"]["kind"] = kind
                with self.assertRaisesRegex(ReleaseModelError, "focused or none"):
                    load_ledger_document(document, self.future_policy())

    def test_reference_unknown_field_is_not_silently_discarded(self):
        document = self.batch_ledger()
        document["entries"][0]["batch_test_evidence"]["extra"] = "untrusted"
        with self.assertRaisesRegex(ReleaseModelError, "schema"):
            load_ledger_document(document, self.future_policy())


if __name__ == "__main__":
    unittest.main()
