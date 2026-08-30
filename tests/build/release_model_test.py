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
        self.assertEqual(self.policy.release_environment, "release")
        self.assertEqual(self.policy.runtime_canary_environment, "runtime-canary")
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
        # The Stage 9 Sequence recording candidate. Its target is the squash
        # merge of #420, which is the revision that carries both the Task 10
        # version integration and the Task 11 immutable snapshot; the exact-main
        # full run was dispatched on that same SHA.
        self.assertEqual(stage9.disposition.value, "releasable")  # type: ignore[union-attr]
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
        self.assertEqual(len(ledger.historical_exceptions), 3)

    def test_canonical_json_digest_and_slash_safe_output_name_are_deterministic(self) -> None:
        value = {"z": "中文", "a": [2, 1]}
        self.assertEqual(canonical_json(value), b'{"a":[2,1],"z":"\xe4\xb8\xad\xe6\x96\x87"}\n')
        self.assertEqual(canonical_sha256(value), hashlib.sha256(canonical_json(value)).hexdigest())
        identity = classify_tag("module/project-io/v0.3.0", self.policy)
        self.assertEqual(identity.output_name, "module%2Fproject-io%2Fv0.3.0")
        self.assertNotIn("/", identity.output_name)


if __name__ == "__main__":
    unittest.main()
