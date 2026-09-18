#!/usr/bin/env python3
"""Scope consistency gates; no mocks stand in for Git history operations."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import incremental_batch
import test_scope as scope


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.policy = scope.load_policy(ROOT)
        self.identity = dict(repository="endaye/lmdj", pr_number=123, head_sha="a" * 40,
                             base_sha="b" * 40, control_sha="c" * 40,
                             backend="kimi", run_id=456, run_attempt=1)

    def record(self, **kwargs):
        return scope.build_record(self.policy, changed_paths=["apps/creator-web/src/App.tsx"],
                                  **self.identity, **kwargs)

    def test_full_uses_complete_authoritative_inventory(self):
        selection = scope.select(self.policy, ["contracts/example/schema.json"])
        self.assertEqual(set(selection["suites"]), set(self.policy.suite_ids))
        self.assertEqual(len(selection["suites"]), 16)
        self.assertIn("core_tsan_stress", selection["suites"])
        self.assertIn("core_release_stress", selection["suites"])

    def test_explanatory_docs_can_be_none(self):
        self.assertEqual(scope.select(self.policy, ["docs/notes/design.md"])["kind"], "none")

    def test_suffix_alone_is_not_none(self):
        for path in ["AGENTS.md", "README.md", "docs/governance/git-workflow.md",
                     "apps/docs-site/docs/operations/testing-and-proof.md",
                     "docs/notes/generator.json", "contracts/example.md"]:
            with self.subTest(path=path):
                self.assertNotEqual(scope.select(self.policy, [path])["kind"], "none")

    def test_document_consumer_overrides_exemption(self):
        path = "docs/plans/2026-08-07-lmdj-stage7-creator-editor.md"
        self.assertIn("portal", scope.select(self.policy, [path])["suites"])

    def test_host_includes_behavior_and_consumers(self):
        selected = scope.select(self.policy, ["apps/web-runtime-host/src/main.mjs"])["suites"]
        self.assertTrue({"web_runtime_host", "creator", "web_runtime_lab", "portal"} <= set(selected))

    def test_core_routes_web_and_stress_consumers(self):
        selected = scope.select(self.policy, ["packages/project-io/src/io.cpp"])["suites"]
        self.assertTrue({"core_tsan_stress", "core_release_stress", "web_toolchain", "creator",
                         "web_runtime_host", "core_macos"} <= set(selected))

    def test_shared_concurrency_boundary_is_full(self):
        self.assertEqual(scope.select(self.policy, ["packages/audio-runtime/src/clock.cpp"])["kind"], "full")

    def test_removing_concurrency_full_rule_breaks_full_invariant(self):
        mutant = copy.deepcopy(self.policy)
        mutant.config["full_prefixes"].remove("packages/audio-runtime/")
        self.assertNotEqual(scope.select(mutant, ["packages/audio-runtime/src/clock.cpp"])["kind"], "full",
                            "why: fixture no longer isolates the concurrency full rule; remedy: restore mutation fixture")

    def test_removing_contract_full_rule_breaks_full_invariant(self):
        mutant = copy.deepcopy(self.policy)
        mutant.routing["full_rules"] = [r for r in mutant.routing["full_rules"] if r["match"]["value"] != "contracts/"]
        self.assertNotEqual(scope.select(mutant, ["contracts/example.md"])["kind"], "full",
                            "why: fixture no longer isolates contract routing; remedy: restore mutation fixture")

    def test_removing_host_dependency_breaks_consumer_invariant(self):
        mutant = copy.deepcopy(self.policy)
        mutant.config["dependencies"]["web_runtime_host"].remove("creator")
        self.assertNotIn("creator", scope.select(mutant, ["apps/web-runtime-host/src/main.mjs"])["suites"],
                         "why: fixture no longer isolates host dependency; remedy: restore mutation fixture")

    def test_unknown_path_is_full(self):
        self.assertEqual(scope.select(self.policy, ["new-root/unknown"])["kind"], "full")

    def test_incomplete_inventory_is_full_even_with_none(self):
        selected = scope.select(self.policy, [], ["test:none"], complete=False)
        self.assertEqual(selected["kind"], "full")
        self.assertIn("remedy:", selected["reasons"][0])

    def test_ai_cannot_subtract_floor(self):
        self.assertEqual(scope.select(self.policy, ["contracts/a"], ["test:none"])["kind"], "full")

    def test_bundle_e2e_paths_keep_the_executor_floor_under_ai_selection(self):
        # These are CTest-registered e2e suites. Their source-level executor
        # contract is derived by ci_change_scope_test from CMake and the
        # runner scripts; this test keeps the public selector from dropping
        # that floor when an AI label is present.
        paths = (
            "tests/e2e/project_bundle_writer_level_test.py",
            "tests/e2e/project_bundle_browser_reader_test.py",
        )
        for path in paths:
            with self.subTest(path=path):
                selected = set(scope.select(self.policy, [path])["suites"])
                self.assertTrue({"core_asan", "core_coverage"} <= selected)
                ai_selected = set(scope.select(self.policy, [path], ["test:none"])["suites"])
                self.assertTrue(selected <= ai_selected,
                                "why: AI selection removed an executor floor; "
                                "remedy: union AI lanes with deterministic routing")

    def test_full_dominates_none(self):
        self.assertEqual(scope.select(self.policy, ["docs/notes/a.md"], ["test:none", "test:full"])["kind"], "full")

    def test_ai_addition_receives_dependency_closure(self):
        result = scope.select(self.policy, ["docs/notes/a.md"], ["test:web_runtime_host"])
        self.assertTrue({"creator", "web_runtime_lab"} <= set(result["suites"]))

    def test_invalid_labels_are_rejected_with_remedy(self):
        for labels in [["test:unknown"], [None], "test:none", ["test:creator", 1]]:
            with self.subTest(labels=labels), self.assertRaisesRegex(scope.ScopeError, "why:.*remedy:"):
                scope.select(self.policy, [], labels)

    def test_union_deduplicates_and_full_dominates(self):
        host = scope.select(self.policy, ["apps/creator-web/src/App.tsx"])
        full = scope.select(self.policy, ["contracts/a"])
        self.assertEqual(scope.union_selections(self.policy, [host, host]), host)
        self.assertEqual(scope.union_selections(self.policy, [host, full])["kind"], "full")

    def test_union_rejects_inconsistent_kind(self):
        with self.assertRaisesRegex(scope.ScopeError, "why:.*remedy:"):
            scope.union_selections(self.policy, [{"kind": "none", "suites": ["creator"], "reasons": []}])

    def test_policy_changes_use_old_new_union(self):
        old = copy.deepcopy(self.policy)
        old.routing["rules"].append({"match": {"kind": "prefix", "value": "docs/notes/"}, "lanes": ["creator"]})
        result = scope.select_across_policies(["docs/notes/a.md"], [self.policy, old])
        self.assertIn("creator", result["suites"])

    def test_missing_old_policy_is_full(self):
        self.assertEqual(scope.select_across_policies(["docs/notes/a.md"], [self.policy, None])["kind"], "full")

    def test_old_selection_receives_current_dependency_closure(self):
        old = copy.deepcopy(self.policy)
        old.routing["rules"].append({"match": {"kind": "prefix", "value": "docs/notes/"},
                                     "lanes": ["web_toolchain"]})
        old.config["dependencies"] = {}
        result = scope.select_across_policies(["docs/notes/a.md"], [self.policy, old])
        self.assertTrue({"web_toolchain", "web_runtime_host", "creator", "web_runtime_lab"}
                        <= set(result["suites"]),
                        "why: old selection lost current consumers; remedy: close the union across policies")

    def test_cross_policy_dependency_edges_reach_a_fixed_point(self):
        old = copy.deepcopy(self.policy)
        old.routing["rules"].append({"match": {"kind": "prefix", "value": "docs/notes/"},
                                     "lanes": ["web_toolchain"]})
        old.config["dependencies"] = {"web_runtime_lab": ["chameleon_lab"]}
        result = scope.select_across_policies(["docs/notes/a.md"], [self.policy, old])
        self.assertIn("chameleon_lab", result["suites"],
                      "why: dependency chain crosses policy versions; remedy: close all applicable edges")

    def test_policy_digest_binds_all_three_documents(self):
        files = ["scope_policy.json", "self_test_policy.json", "test_scope_policy.json"]
        docs = [json.loads((ROOT / "scripts/ci" / name).read_text()) for name in files]
        for position, key in [(0, "slo_seconds"), (1, "note"), (2, "none_prefixes")]:
            changed = copy.deepcopy(docs)
            if position == 0:
                changed[position][key]["portal"] += 1
            elif position == 1:
                changed[position][key] += " changed"
            else:
                changed[position][key].append("docs/extra-notes/")
            self.assertNotEqual(scope.parse_policy(*changed).digest, self.policy.digest)

    def test_record_roundtrip(self):
        record = self.record(ai_labels=["test:creator"])
        self.assertEqual(scope.validate_record(record, self.policy, self.identity), record)

    def test_json_duplicate_fields_rejected(self):
        encoded = json.dumps(self.record())
        encoded = encoded[:-1] + ', "schema": "lmdj.ci-test-scope.v1"}'
        with self.assertRaisesRegex(scope.ScopeError, "duplicate JSON key"):
            scope.parse_record(encoded, self.policy, self.identity)

    def test_record_parser_roundtrip(self):
        record = self.record()
        self.assertEqual(scope.parse_record(json.dumps(record), self.policy, self.identity), record)

    def test_unknown_schema_is_not_accepted(self):
        record = self.record()
        record["schema"] = "lmdj.ci-test-scope.v99"
        with self.assertRaisesRegex(scope.ScopeError, "inconsistent"):
            scope.validate_record(record, self.policy, self.identity)

    def test_bad_path_is_not_none(self):
        for path in ["../a", "/a", "docs/../a.md", "docs/notes/a\nb.md"]:
            with self.subTest(path=path), self.assertRaisesRegex(scope.ScopeError, "why:.*remedy:"):
                scope.select(self.policy, [path])

    def test_record_identity_is_independently_bound(self):
        for key, value in [("repository", "attacker/repo"), ("pr_number", 999), ("head_sha", "d" * 40),
                           ("base_sha", "e" * 40), ("control_sha", "f" * 40), ("run_id", 99),
                           ("run_attempt", 2), ("backend", "grok")]:
            identity = {**self.identity, key: value}
            with self.subTest(key=key), self.assertRaisesRegex(scope.ScopeError, "identity is stale"):
                scope.validate_record(self.record(), self.policy, identity)

    def test_record_is_closed(self):
        record = self.record()
        for key in record:
            changed = {k: v for k, v in record.items() if k != key}
            with self.subTest(key=key), self.assertRaisesRegex(scope.ScopeError, "schema is not closed"):
                scope.validate_record(changed, self.policy, self.identity)
        with self.assertRaisesRegex(scope.ScopeError, "schema is not closed"):
            scope.validate_record({**record, "trusted": True}, self.policy, self.identity)

    def test_recomputed_digest_does_not_allow_forged_scope(self):
        record = self.record()
        record["effective"] = {"kind": "none", "suites": [], "reasons": []}
        record["record_digest"] = scope.self_test.digest_of({k: v for k, v in record.items() if k != "record_digest"})
        with self.assertRaisesRegex(scope.ScopeError, "inconsistent"):
            scope.validate_record(record, self.policy, self.identity)

    def test_record_changed_paths_digest_tamper_rejected(self):
        record = self.record()
        record["changed_paths"] = []
        with self.assertRaisesRegex(scope.ScopeError, "inconsistent"):
            scope.validate_record(record, self.policy, self.identity)

    def test_record_boolean_id_is_not_integer(self):
        with self.assertRaisesRegex(scope.ScopeError, "positive integer"):
            scope.build_record(self.policy, changed_paths=[], **{**self.identity, "run_id": True})

    def test_none_cannot_hide_unknown_policy_fields(self):
        config = copy.deepcopy(self.policy.config)
        config["skip_all"] = True
        inventory = json.loads((ROOT / "scripts/ci/self_test_policy.json").read_text())
        with self.assertRaisesRegex(scope.ScopeError, "schema is not closed"):
            scope.parse_policy(self.policy.routing, inventory, config)

    def test_every_tracked_path_preserves_canonical_consumers(self):
        paths = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "-z"]).decode().split("\0")
        for path in filter(None, paths):
            lanes, full = scope.change_scope.path_classification(self.policy.routing, path)
            result = scope.select(self.policy, [path])
            if result["kind"] == "none":
                self.assertEqual(lanes, {"docs_static"}, f"why: none hides consumer {path}; remedy: restore routing")
                self.assertFalse(full)
            else:
                self.assertTrue(lanes <= set(result["suites"]), f"why: consumers omitted for {path}; remedy: restore scope union")
            if full:
                self.assertEqual(result["kind"], "full", f"why: full rule lost for {path}; remedy: expand authoritative suites")


class GitIntervalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-b", "main")
        self.git("config", "user.email", "scope-test@example.invalid")
        self.git("config", "user.name", "Scope Test")
        self.base = self.commit("README.md", "base")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.PIPE).decode().strip()

    def commit(self, path, text):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        self.git("add", path)
        self.git("commit", "-m", "test: change")
        return self.git("rev-parse", "HEAD")

    def test_revert_is_not_erased_by_net_diff(self):
        first = self.commit("contracts/a.json", "contract")
        self.git("revert", "--no-edit", first)
        target = self.git("rev-parse", "HEAD")
        self.assertEqual(self.git("diff", "--name-only", self.base, target), "")
        interval = scope.collect_interval(self.repo, self.base, target)
        self.assertEqual(interval["paths"], ["contracts/a.json"])
        self.assertEqual([c["changes"][0]["status"] for c in interval["commits"]], ["A", "D"])

    def test_rename_preserves_both_ends(self):
        base = self.commit("contracts/a.json", "contract")
        self.git("mv", "contracts/a.json", "contracts/b.json")
        self.git("commit", "-m", "test: rename")
        result = scope.collect_interval(self.repo, base, self.git("rev-parse", "HEAD"))
        self.assertEqual(result["paths"], ["contracts/a.json", "contracts/b.json"])

    def test_merge_uses_actual_first_parent_result(self):
        self.git("checkout", "-b", "feat/example")
        side = self.commit("apps/creator-web/a", "side")
        self.git("checkout", "main")
        self.commit("docs/notes/a.md", "main")
        self.git("merge", "--no-ff", "feat/example", "-m", "test: merge")
        result = scope.collect_interval(self.repo, self.base, self.git("rev-parse", "HEAD"))
        self.assertEqual(len(result["commits"]), 2)
        self.assertNotIn(side, [c["sha"] for c in result["commits"]])
        self.assertEqual(result["paths"], ["apps/creator-web/a", "docs/notes/a.md"])

    def test_squash_includes_all_result_paths(self):
        self.git("checkout", "-b", "feat/example")
        self.commit("apps/creator-web/a", "a")
        self.commit("apps/web-runtime-host/b", "b")
        self.git("checkout", "main")
        self.git("merge", "--squash", "feat/example")
        self.git("commit", "-m", "test: squash")
        result = scope.collect_interval(self.repo, self.base, self.git("rev-parse", "HEAD"))
        self.assertEqual(len(result["commits"]), 1)
        self.assertEqual(result["paths"], ["apps/creator-web/a", "apps/web-runtime-host/b"])

    def test_merge_commit_changes_absent_from_reviewed_branch_are_included(self):
        self.git("checkout", "-b", "feat/example")
        self.commit("docs/notes/a.md", "reviewed")
        self.git("checkout", "main")
        self.git("merge", "--no-ff", "--no-commit", "feat/example")
        target = self.commit("contracts/merge-resolution.json", "actual merge result")
        result = scope.collect_interval(self.repo, self.base, target)
        self.assertIn("contracts/merge-resolution.json", result["paths"])
        self.assertEqual(scope.select(scope.load_policy(ROOT), result["paths"])["kind"], "full")

    def test_side_parent_baseline_is_rejected(self):
        self.git("checkout", "-b", "feat/example")
        side = self.commit("side", "a")
        self.git("checkout", "main")
        self.commit("main-file", "b")
        self.git("merge", "--no-ff", "feat/example", "-m", "test: merge")
        with self.assertRaisesRegex(scope.ScopeError, "first-parent"):
            scope.collect_interval(self.repo, side, self.git("rev-parse", "HEAD"))

    def test_missing_history_is_not_empty(self):
        with self.assertRaisesRegex(scope.ScopeError, "why:.*remedy:"):
            scope.collect_interval(self.repo, "e" * 40, self.base)

    def test_shallow_history_is_rejected(self):
        self.commit("second", "a")
        with tempfile.TemporaryDirectory() as clone:
            subprocess.check_call(["git", "clone", "--quiet", "--depth", "1", self.repo.as_uri(), clone])
            with self.assertRaisesRegex(scope.ScopeError, "shallow history"):
                scope.collect_interval(clone, self.base, self.git("rev-parse", "HEAD"))

    def test_annotated_tag_object_is_not_commit_endpoint(self):
        self.git("tag", "-a", "test-tag", "-m", "test tag")
        with self.assertRaisesRegex(scope.ScopeError, "not a commit"):
            scope.collect_interval(self.repo, self.base, self.git("rev-parse", "test-tag"))

    def test_large_inventory_has_no_page_truncation(self):
        for number in range(105):
            (self.repo / f"file-{number}").write_text(str(number))
        self.git("add", ".")
        self.git("commit", "-m", "test: inventory")
        result = scope.collect_interval(self.repo, self.base, self.git("rev-parse", "HEAD"))
        self.assertEqual(len(result["paths"]), 105)

    def test_no_change_is_explicit_empty_interval(self):
        result = scope.collect_interval(self.repo, self.base, self.base)
        self.assertEqual(result["commits"], [])
        self.assertEqual(result["paths"], [])



class BoundedReasonsTests(unittest.TestCase):
    """The admit record is bounded by construction; see .agents/pitfalls/journal-record-grows-with-backlog.md."""

    def encoded(self, reasons):
        return len(json.dumps(reasons, separators=(",", ":")).encode())

    def test_small_explanation_is_canonical_and_unchanged(self):
        self.assertEqual(scope.bounded_reasons(["b", "a", "a"]), ["a", "b"])

    def test_large_explanation_keeps_canonical_prefix_and_counts_the_distinct_rest(self):
        reasons = [f"broad foundational or concurrency impact: packages/p/file_{i:05d}.cpp" for i in range(5000)]
        bounded = scope.bounded_reasons(reversed(reasons), budget=2000)
        self.assertLessEqual(self.encoded(bounded), 2000,
                             "why: bounded explanation exceeds its budget; remedy: measure the encoded record")
        notices = [r for r in bounded if r.startswith(scope.OMISSION_MARKER)]
        kept = [r for r in bounded if not r.startswith(scope.OMISSION_MARKER)]
        self.assertEqual(len(notices), 1)
        self.assertTrue(kept and kept == sorted(reasons)[:len(kept)],
                        "why: bound reordered or skipped reasons; remedy: keep the canonical prefix")
        self.assertIn(f"{5000 - len(kept)} further distinct selection reasons were omitted", notices[0])
        self.assertIn("remedy:", notices[0])
        self.assertEqual(scope.bounded_reasons(bounded, budget=2000), bounded,
                         "why: bound is not idempotent; remedy: a stored request must rebuild to itself")

    def test_notice_cannot_be_confused_with_a_real_why_reason(self):
        """Real reasons use the why/remedy form, so the notice needs its own marker."""
        reasons = [f"why: real reason {i:03d} {'x' * 100}; remedy: fix it" for i in range(60)]
        bounded = scope.bounded_reasons(reasons, budget=2000)
        self.assertEqual(len([r for r in bounded if r.startswith(scope.OMISSION_MARKER)]), 1)
        self.assertGreater(len([r for r in bounded if r.startswith("why:")]), 1,
                           "why: the fixture kept no real why-prefixed reason; remedy: keep the collision in the test")

    def test_duplicates_are_collapsed_before_the_distinct_count(self):
        reasons = [f"reason {i:04d} {'x' * 200}" for i in range(400)]
        once = scope.bounded_reasons(reasons, budget=2000)
        twice = scope.bounded_reasons(reasons + reasons, budget=2000)
        self.assertEqual(once, twice, "why: duplicate input changed the notice; remedy: count distinct canonical reasons")

    def test_budget_below_one_notice_is_refused_not_exceeded(self):
        reasons = [f"reason {i:03d} " + "x" * 50 for i in range(40)]
        with self.assertRaisesRegex(scope.ScopeError, "smaller than one omission notice"):
            scope.bounded_reasons(reasons, budget=100)
        self.assertEqual(scope.bounded_reasons(reasons[:1], budget=100), reasons[:1],
                         "why: a fitting explanation was refused; remedy: check the budget only when bounding")

    def test_every_request_kind_is_bounded_by_construction(self):
        """Bootstrap, debt recovery and explicit commands all build through make_request."""
        policy = scope.load_policy(ROOT)
        crowded = [f"broad foundational or concurrency impact: packages/p/file_{i:05d}.cpp" for i in range(4000)]
        run = {"run_id": 17, "attempt": 1}
        for kind, base in (("bootstrap", None), ("auto", "a" * 40), ("node", "a" * 40), ("candidate", "a" * 40)):
            with self.subTest(kind=kind):
                selection = scope._selection(policy, policy.suite_ids, crowded)
                request = incremental_batch.make_request(policy, request_id=f"r:{kind}", kind=kind, base_sha=base,
                                                         target_sha="b" * 40, control_sha="c" * 40,
                                                         selection=selection, origin_run=run)
                self.assertLessEqual(self.encoded(request["selection"]["reasons"]), scope.REASON_BUDGET)
                self.assertEqual(request["selection"]["suites"], sorted(policy.suite_ids))
                incremental_batch._request(policy, request)


if __name__ == "__main__":
    unittest.main()
