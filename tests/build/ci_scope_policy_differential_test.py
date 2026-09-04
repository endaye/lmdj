#!/usr/bin/env python3
"""A routing rule for a path the branch introduces need not cost a full run.

`full_rules` carries the prefix `scripts/ci/`, so any edit under that directory
upgrades the run to the full manifest. That is right for rewriting the
classifier and wrong for adding one rule, which cannot change how any other
path is classified. Combined with the tracked-path ownership gate, which
requires every newly tracked file to carry a rule, the standing result was that
every Pull Request adding a file paid a full run.

The exemption is narrow and has to stay narrow: it applies only to
`scripts/ci/scope_policy.json`, only when the edit provably leaves every path
that existed at the merge base classified exactly as before, and it suppresses
only that one path's contribution.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts/ci"))

from change_scope import (  # noqa: E402
    CLASSIFICATION_INERT_POLICY_PATHS,
    SCOPE_POLICY_PATH,
    ChangedFile,
    classify,
    load_policy,
    path_classification,
    policy_edit_is_classification_preserving,
)

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40


def _changed(*paths: str) -> tuple[ChangedFile, ...]:
    return tuple(ChangedFile("M", (path,)) for path in paths)


class ScopePolicyDifferentialTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy(REPO_ROOT / "scripts/ci/scope_policy.json")

    # ---- the differential itself -------------------------------------------------

    def test_adding_a_rule_for_a_new_path_preserves_classification(self) -> None:
        head = copy.deepcopy(self.policy)
        head["rules"].append(
            {"match": {"kind": "exact", "value": "tests/build/brand_new_helper.py"},
             "lanes": ["ci_contract"]}
        )
        preserving, reason = policy_edit_is_classification_preserving(
            self.policy, head, ["tests/build/ci_change_scope_test.py", "packages/README.md"]
        )
        self.assertTrue(preserving, reason)

    def test_widening_a_rule_over_existing_paths_is_not_preserving(self) -> None:
        """The circular case the full upgrade exists for.

        What disqualifies an edit is its effect, not the shape of the rule. A
        prefix rule that adds a lane an existing path did not already carry
        changes that path's routing, so the new policy cannot be trusted to
        scope its own change.
        """
        head = copy.deepcopy(self.policy)
        head["rules"].append(
            {"match": {"kind": "prefix", "value": "packages/"}, "lanes": ["core_macos"]}
        )
        preserving, reason = policy_edit_is_classification_preserving(
            self.policy, head, ["packages/README.md"]
        )
        self.assertFalse(preserving)
        self.assertIn("packages/README.md", reason)

    def test_a_rule_whose_lanes_a_path_already_has_is_preserving(self) -> None:
        """A differential measures effect, so a redundant rule is not a change."""
        head = copy.deepcopy(self.policy)
        existing_lanes, _ = path_classification(self.policy, "packages/README.md")
        head["rules"].append(
            {"match": {"kind": "prefix", "value": "packages/"},
             "lanes": sorted(existing_lanes)}
        )
        preserving, reason = policy_edit_is_classification_preserving(
            self.policy, head, ["packages/README.md"]
        )
        self.assertTrue(preserving, reason)

    def test_removing_a_top_level_admission_is_not_preserving(self) -> None:
        head = copy.deepcopy(self.policy)
        head["known_top_levels"] = [
            name for name in head["known_top_levels"] if name != "docs"
        ]
        preserving, reason = policy_edit_is_classification_preserving(
            self.policy, head, ["docs/prd/decision-log.md"]
        )
        self.assertFalse(preserving)
        self.assertIn("docs/prd/decision-log.md", reason)

    def test_a_non_routing_key_change_is_not_preserving(self) -> None:
        """`draft_lanes` never surfaces per path, so a path differential misses it."""
        for key, value in (
            ("draft_lanes", ["docs_static"]),
            ("slo_seconds", {"docs_static": 1}),
            ("expensive_families", {"core": ["core_ubuntu"]}),
        ):
            with self.subTest(key=key):
                head = copy.deepcopy(self.policy)
                head[key] = value
                preserving, reason = policy_edit_is_classification_preserving(
                    self.policy, head, ["packages/README.md"]
                )
                self.assertFalse(preserving)
                self.assertIn(key, reason)

    def test_an_identical_policy_is_preserving(self) -> None:
        preserving, _ = policy_edit_is_classification_preserving(
            self.policy, copy.deepcopy(self.policy), ["packages/README.md"]
        )
        self.assertTrue(preserving)

    def test_an_empty_tracked_path_inventory_fails_closed(self) -> None:
        preserving, reason = policy_edit_is_classification_preserving(
            self.policy, copy.deepcopy(self.policy), []
        )
        self.assertFalse(preserving)
        self.assertIn("tracked path inventory", reason)

    def test_path_classification_reports_lanes_and_reasons(self) -> None:
        lanes, reasons = path_classification(self.policy, SCOPE_POLICY_PATH)
        self.assertIn("ci_contract", lanes)
        self.assertTrue(any("full rule" in reason for reason in reasons))

    # ---- how the exemption reaches the manifest ----------------------------------

    def test_a_preserving_policy_edit_alone_does_not_force_full(self) -> None:
        manifest = classify(
            self.policy, _changed(SCOPE_POLICY_PATH),
            base_sha=BASE_SHA, head_sha=HEAD_SHA, event_name="pull_request",
            draft=False, labels=set(), policy_edit_preserving=True,
        )
        self.assertEqual(manifest["mode"], "focused")
        self.assertEqual(manifest["lanes"]["ci_contract"], True)
        self.assertEqual(manifest["lanes"]["core_asan"], False)

    def test_without_the_proof_the_same_edit_still_forces_full(self) -> None:
        manifest = classify(
            self.policy, _changed(SCOPE_POLICY_PATH),
            base_sha=BASE_SHA, head_sha=HEAD_SHA, event_name="pull_request",
            draft=False, labels=set(),
        )
        self.assertEqual(manifest["mode"], "full")

    def test_the_exemption_covers_only_the_policy_file(self) -> None:
        """A classifier edit in the same change keeps the full upgrade.

        Without this the exemption would let `change_scope.py` ride along on a
        proof that says nothing about it.
        """
        manifest = classify(
            self.policy, _changed(SCOPE_POLICY_PATH, "scripts/ci/change_scope.py"),
            base_sha=BASE_SHA, head_sha=HEAD_SHA, event_name="pull_request",
            draft=False, labels=set(), policy_edit_preserving=True,
        )
        self.assertEqual(manifest["mode"], "full")
        self.assertTrue(
            any("central CI control plane" in reason for reason in manifest["reasons"]),
            manifest["reasons"],
        )

    def test_the_exemption_does_not_suppress_an_unrelated_full_rule(self) -> None:
        manifest = classify(
            self.policy, _changed(SCOPE_POLICY_PATH, ".github/workflows/ci.yml"),
            base_sha=BASE_SHA, head_sha=HEAD_SHA, event_name="pull_request",
            draft=False, labels=set(), policy_edit_preserving=True,
        )
        self.assertEqual(manifest["mode"], "full")

    def test_the_policy_routes_itself_so_the_exemption_leaves_a_lane(self) -> None:
        """Suppressing the upgrade without a rule would only make it unclassified.

        `unclassified path` is itself a full-upgrade reason, so the exemption
        would have been a no-op without this route.
        """
        rules = json.loads(
            (REPO_ROOT / "scripts/ci/scope_policy.json").read_text(encoding="utf-8")
        )["rules"]
        self.assertTrue(
            any(
                rule["match"] == {"kind": "exact", "value": SCOPE_POLICY_PATH}
                and rule["lanes"] == ["ci_contract"]
                for rule in rules
            ),
            "why: exempting the policy path from its full rule leaves it with no "
            "lane, and an unclassified path is itself a full upgrade, so the "
            "exemption silently does nothing; remedy: keep the exact rule "
            f"routing {SCOPE_POLICY_PATH} to ci_contract",
        )

    # ---- the second, differently proved exemption --------------------------------

    def test_a_classification_inert_policy_edit_does_not_force_full(self) -> None:
        """No differential is needed: nothing that decides lanes reads the file.

        Recording a hosted job used to cost a full manifest because the file
        sits under the `scripts/ci/` prefix. It now selects the one lane that
        actually validates it.
        """
        for relative in sorted(CLASSIFICATION_INERT_POLICY_PATHS):
            with self.subTest(path=relative):
                manifest = classify(
                    self.policy, _changed(relative),
                    base_sha=BASE_SHA, head_sha=HEAD_SHA, event_name="pull_request",
                    draft=False, labels=set(),
                )
                self.assertEqual(manifest["mode"], "focused")
                self.assertEqual(manifest["lanes"]["ci_contract"], True)
                self.assertEqual(manifest["lanes"]["core_asan"], False)

    def test_the_inert_exemption_does_not_cover_the_classifier(self) -> None:
        for relative in sorted(CLASSIFICATION_INERT_POLICY_PATHS):
            for companion in ("scripts/ci/change_scope.py", ".github/workflows/ci.yml"):
                with self.subTest(path=relative, companion=companion):
                    manifest = classify(
                        self.policy, _changed(relative, companion),
                        base_sha=BASE_SHA, head_sha=HEAD_SHA,
                        event_name="pull_request", draft=False, labels=set(),
                    )
                    self.assertEqual(manifest["mode"], "full")

    def test_every_inert_path_is_routed_so_the_exemption_leaves_a_lane(self) -> None:
        """Same trap as the policy's own route: unclassified is itself a full upgrade."""
        for relative in sorted(CLASSIFICATION_INERT_POLICY_PATHS):
            lanes, _ = path_classification(self.policy, relative)
            with self.subTest(path=relative):
                self.assertTrue(
                    lanes,
                    "why: exempting {0} from its full rule leaves it with no lane, "
                    "and an unclassified path is itself a full upgrade, so the "
                    "exemption silently does nothing; remedy: add an exact rule "
                    "routing {0} to ci_contract".format(relative),
                )


if __name__ == "__main__":
    unittest.main()
