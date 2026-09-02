#!/usr/bin/env python3
"""Gate: Integration Queue merge-evidence mode has one authority.

The eight enforcement sites named in
`.agents/pitfalls/queue-evidence-enforcement-sites.md` either consume
`change_scope.is_merge_evidence_mode` or are proven not to enforce
evidence mode. A site that accepts `requested` or rejects `focused`
where merge evidence is required fails this file with `why` and
`remedy`.
"""

from __future__ import annotations

from dataclasses import replace
import inspect
import io
import json
from pathlib import Path
import sys
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))

import change_scope as scope  # noqa: E402
import github_queue_api as api  # noqa: E402
import merge_queue as mq  # noqa: E402


SHA_A = "a" * 40
SHA_B = "b" * 40
MODE_TABLE = (None, "draft", "requested", "focused", "full", "unknown-mode")
CLOSED_EVIDENCE_MODES = frozenset({"focused", "full"})
SITES = (
    "classify merge:queue upgrade",
    "classify empty workflow_dispatch upgrade",
    "queue_validation_document",
    "validate_manifest",
    "merge_queue._validation_contract_error mode check",
    "merge_queue._validation_contract_error required-check conclusions",
    "parse_scope_manifest_zip",
    "parse_queue_validation_json",
)

WHY_DRIFT = (
    "why: the Integration Queue evidence contract is one rule, but it used "
    "to be copied into eight independent checks; a site that accepts a "
    "non-evidence mode or rejects `focused`/`full` where merge evidence is "
    "required will silently keep the old rule after the others change."
)
REMEDY_DRIFT = (
    "remedy: route every mode-enforcing site through "
    "change_scope.is_merge_evidence_mode and keep MERGE_EVIDENCE_MODES as "
    "the closed set {focused, full}; do not fold operator empty "
    "workflow_dispatch or SKIPPABLE_CHECKS into that predicate."
)


def changed(*paths: str) -> tuple[scope.ChangedFile, ...]:
    return tuple(scope.ChangedFile("M", (path,)) for path in paths)


def scope_zip(document: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ci-scope.json", json.dumps(document))
    return buffer.getvalue()


def _raised(action) -> bool:
    try:
        action()
    except (ValueError, TypeError):
        return True
    return False


class QueueEvidenceModeGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = scope.load_policy(ROOT / "scripts/ci/scope_policy.json")
        cls.queue = scope.parse_queue_inputs(
            "mq:123:1", "220", SHA_A, SHA_B
        )
        cls.evaluation = scope.QueueEvaluation(
            classification="valid",
            observed_base_sha=SHA_A,
            observed_head_sha=SHA_B,
            pull_request_body="body",
            reason="queue context is valid",
        )
        cls.attempt = mq.QueueAttempt(
            number=220,
            base_sha=SHA_A,
            head_sha=SHA_B,
            head_tree="tree",
            ticket="mq:123:1",
            validation_budget_seconds=60,
        )

    def assert_gate(self, condition: bool, detail: str) -> None:
        self.assertTrue(
            condition,
            f"{detail}\n{WHY_DRIFT}\n{REMEDY_DRIFT}",
        )

    def classify(self, paths, **kwargs):
        defaults = {
            "base_sha": SHA_A,
            "head_sha": SHA_B,
            "event_name": "pull_request",
            "draft": False,
            "labels": (),
            "trusted_head": True,
        }
        defaults.update(kwargs)
        return scope.classify(self.policy, changed(*paths), **defaults)

    def focused_queue_manifest(self) -> dict:
        return self.classify(
            ["docs/guide.md"],
            event_name="workflow_dispatch",
            labels=("merge:queue",),
            queue=self.queue,
        )

    def full_queue_manifest(self) -> dict:
        return self.classify(
            ["scripts/ci/change_scope.py"],
            event_name="workflow_dispatch",
            labels=("merge:queue",),
            queue=self.queue,
        )

    def focused_pr_manifest(self) -> dict:
        return self.classify(["docs/guide.md"])

    def full_pr_manifest(self) -> dict:
        return self.classify(["scripts/ci/change_scope.py"])

    def validation_result(self, **changes) -> mq.ValidationResult:
        result = mq.ValidationResult(
            classification="valid",
            run_id=9001,
            run_status="completed",
            run_conclusion="success",
            run_event="workflow_dispatch",
            workflow_path=".github/workflows/ci.yml",
            head_sha=SHA_B,
            manifest_mode="full",
            trusted_head=True,
            ticket="mq:123:1",
            base_sha=SHA_A,
            required_checks=(
                mq.RequiredCheck("core (ubuntu-latest)", 15368, "success"),
                mq.RequiredCheck("core (macos-latest)", 15368, "success"),
                mq.RequiredCheck("PR Gate", 15368, "success"),
            ),
            queue_seconds=10,
            execution_seconds=20,
        )
        return replace(result, **changes)

    def queue_validation_payload(self, mode: object) -> dict[str, object]:
        return {
            "schema": "lmdj.queue-validation.v1",
            "classification": "valid",
            "queue_ticket": "mq:123:1",
            "queue_pr_number": 220,
            "queue_base_sha": SHA_A,
            "queue_head_sha": SHA_B,
            "observed_base_sha": SHA_A,
            "observed_head_sha": SHA_B,
            "manifest_mode": mode,
            "trusted_head": True,
        }

    def test_inventory_names_all_eight_pitfall_sites(self) -> None:
        self.assertEqual(
            len(SITES),
            8,
            "why: the pitfall names eight enforcement sites and this gate "
            "must keep that inventory closed.\n"
            "remedy: add or remove a row in SITES only together with a "
            "behavior test that drives the real shipped function.",
        )
        self.assertEqual(len(set(SITES)), 8)

    def test_closed_evidence_set_and_predicate_agree(self) -> None:
        self.assertEqual(
            scope.MERGE_EVIDENCE_MODES,
            CLOSED_EVIDENCE_MODES,
            "why: merge evidence is the focused/full classification; adding "
            "a mode to MERGE_EVIDENCE_MODES without a product decision "
            "would authorize squash merges on operator lane selection or "
            "draft breadth.\n"
            f"{REMEDY_DRIFT}",
        )
        for mode in MODE_TABLE:
            with self.subTest(mode=mode):
                self.assertEqual(
                    scope.is_merge_evidence_mode(mode),
                    mode in CLOSED_EVIDENCE_MODES,
                    f"why: is_merge_evidence_mode({mode!r}) drifted from "
                    "MERGE_EVIDENCE_MODES, so callers no longer share one "
                    "authority.\n"
                    f"{REMEDY_DRIFT}",
                )

    def test_enforcing_sites_call_the_shared_predicate(self) -> None:
        enforcing = {
            "queue_validation_document": scope.queue_validation_document,
            "validate_manifest": scope.validate_manifest,
            "_validation_contract_error": mq._validation_contract_error,
            "parse_scope_manifest_zip": api.parse_scope_manifest_zip,
            "parse_queue_validation_json": api.parse_queue_validation_json,
        }
        for name, function in enforcing.items():
            source = inspect.getsource(function)
            self.assert_gate(
                "is_merge_evidence_mode" in source,
                f"site {name} no longer calls is_merge_evidence_mode",
            )
        classify_source = inspect.getsource(scope.classify)
        self.assert_gate(
            "is_merge_evidence_mode" not in classify_source,
            "classify started consulting the merge-evidence predicate; "
            "sites 1 and 2 must stay independent of that authority",
        )

    def test_site_1_merge_queue_label_does_not_enforce_evidence_mode(self) -> None:
        # Site 1 used to add a full reason for merge:queue. The label is
        # authorization only; it must not change classified breadth.
        for paths, expected in (
            (["docs/guide.md"], "focused"),
            (["scripts/ci/change_scope.py"], "full"),
        ):
            with self.subTest(paths=paths):
                plain = self.classify(paths)
                labelled = self.classify(paths, labels={"merge:queue"})
                self.assert_gate(
                    plain["mode"] == expected and labelled["mode"] == expected,
                    f"merge:queue changed docs/control-plane classification "
                    f"from {plain['mode']!r}/{expected!r} to "
                    f"{labelled['mode']!r}",
                )
                self.assertEqual(labelled["lanes"], plain["lanes"])

    def test_site_2_empty_dispatch_is_operator_full_not_evidence_mode(self) -> None:
        # Site 2 is release evidence, not merge evidence. An operator's empty
        # workflow_dispatch stays unconditionally full; a queue dispatch of
        # the same docs-only tree classifies.
        operator = self.classify(
            ["docs/guide.md"], event_name="workflow_dispatch"
        )
        queued = self.classify(
            ["docs/guide.md"],
            event_name="workflow_dispatch",
            labels=("merge:queue",),
            queue=self.queue,
        )
        self.assert_gate(
            operator["mode"] == "full",
            f"operator empty workflow_dispatch of a docs-only change "
            f"classified as {operator['mode']!r} instead of full",
        )
        self.assert_gate(
            queued["mode"] == "focused",
            f"queue dispatch of a docs-only change classified as "
            f"{queued['mode']!r} instead of focused; site 2 leaked into "
            "the queue path",
        )
        self.assertIn("full event: workflow_dispatch", operator["reasons"])
        self.assertNotIn("full event: workflow_dispatch", queued["reasons"])

    def test_site_3_queue_validation_document_consumes_the_authority(self) -> None:
        for mode in MODE_TABLE:
            with self.subTest(mode=mode):
                accepted = not _raised(
                    lambda current=mode: scope.queue_validation_document(
                        self.queue,
                        self.evaluation,
                        manifest_mode=current,
                        trusted_head=True,
                    )
                )
                expected = mode is None or scope.is_merge_evidence_mode(mode)
                self.assert_gate(
                    accepted is expected,
                    f"queue_validation_document mode={mode!r} accepted="
                    f"{accepted} expected={expected}",
                )

    def test_site_4_queue_validate_manifest_consumes_the_authority(self) -> None:
        focused = self.focused_queue_manifest()
        full = self.full_queue_manifest()
        self.assertEqual(focused["mode"], "focused")
        self.assertEqual(full["mode"], "full")
        for mode in MODE_TABLE:
            with self.subTest(mode=mode):
                if mode == "full":
                    document = dict(full)
                else:
                    document = dict(focused)
                    document["mode"] = mode
                accepted = not _raised(
                    lambda current=document: scope.validate_manifest(
                        current, self.policy
                    )
                )
                expected = scope.is_merge_evidence_mode(mode)
                self.assert_gate(
                    accepted is expected,
                    f"validate_manifest queue mode={mode!r} accepted="
                    f"{accepted} expected={expected}",
                )

    def test_site_5_validation_contract_mode_consumes_the_authority(self) -> None:
        for mode in MODE_TABLE:
            with self.subTest(mode=mode):
                result = self.validation_result(manifest_mode=mode)
                error = mq._validation_contract_error(result, self.attempt)
                mode_rejected = error is not None and any(
                    item.startswith("field:manifest_mode=")
                    for item in error[1]
                )
                expected_reject = not scope.is_merge_evidence_mode(mode)
                self.assert_gate(
                    mode_rejected is expected_reject,
                    f"_validation_contract_error mode={mode!r} "
                    f"mode_rejected={mode_rejected} "
                    f"expected_reject={expected_reject} error={error!r}",
                )

    def test_site_6_required_check_skippability_is_not_a_mode_check(self) -> None:
        # Site 6 is a conclusion rule. Core contexts may be skipped at any
        # merge-evidence breadth because PR Gate vouches; PR Gate itself
        # may not. Folding this into is_merge_evidence_mode would either
        # reject a focused skip or allow a skipped PR Gate.
        for mode in ("focused", "full"):
            with self.subTest(mode=mode):
                skipped_core = self.validation_result(
                    manifest_mode=mode,
                    required_checks=(
                        mq.RequiredCheck(
                            "core (ubuntu-latest)", 15368, "skipped"
                        ),
                        mq.RequiredCheck(
                            "core (macos-latest)", 15368, "success"
                        ),
                        mq.RequiredCheck("PR Gate", 15368, "success"),
                    ),
                )
                self.assertIsNone(
                    mq._validation_contract_error(skipped_core, self.attempt),
                    f"why: skipped Core was rejected at mode={mode!r}; "
                    "SKIPPABLE_CHECKS is a conclusion rule, not a mode "
                    "check.\n"
                    f"{REMEDY_DRIFT}",
                )
                skipped_gate = self.validation_result(
                    manifest_mode=mode,
                    required_checks=(
                        mq.RequiredCheck(
                            "core (ubuntu-latest)", 15368, "success"
                        ),
                        mq.RequiredCheck(
                            "core (macos-latest)", 15368, "success"
                        ),
                        mq.RequiredCheck("PR Gate", 15368, "skipped"),
                    ),
                )
                error = mq._validation_contract_error(
                    skipped_gate, self.attempt
                )
                self.assert_gate(
                    error is not None
                    and "check:PR Gate=skipped" in error[1],
                    f"skipped PR Gate was accepted at mode={mode!r}; "
                    "PR Gate is never skippable",
                )
        source = inspect.getsource(mq._validation_contract_error)
        skip_block = source.split("if not is_merge_evidence_mode", 1)[1]
        self.assert_gate(
            "SKIPPABLE_CHECKS" in skip_block,
            "required-check skippability no longer uses SKIPPABLE_CHECKS",
        )

    def test_site_7_parse_scope_manifest_zip_consumes_the_authority(self) -> None:
        focused = self.focused_pr_manifest()
        full = self.full_pr_manifest()
        self.assertEqual(focused["mode"], "focused")
        self.assertEqual(full["mode"], "full")
        for mode in MODE_TABLE:
            with self.subTest(mode=mode):
                if mode == "full":
                    document = dict(full)
                else:
                    document = dict(focused)
                    document["mode"] = mode
                accepted = not _raised(
                    lambda current=document: api.parse_scope_manifest_zip(
                        scope_zip(current), SHA_B
                    )
                )
                expected = scope.is_merge_evidence_mode(mode)
                self.assert_gate(
                    accepted is expected,
                    f"parse_scope_manifest_zip mode={mode!r} accepted="
                    f"{accepted} expected={expected}",
                )

    def test_site_8_parse_queue_validation_json_consumes_the_authority(self) -> None:
        for mode in MODE_TABLE:
            with self.subTest(mode=mode):
                accepted = not _raised(
                    lambda current=mode: api.parse_queue_validation_json(
                        self.queue_validation_payload(current)
                    )
                )
                expected = mode is None or scope.is_merge_evidence_mode(mode)
                self.assert_gate(
                    accepted is expected,
                    f"parse_queue_validation_json mode={mode!r} accepted="
                    f"{accepted} expected={expected}",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
