"""Real Git + canonical scope projection; no remote receipt authenticity claim."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.canary import planning as p, records as r


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        for name in ("scope_policy.json", "self_test_policy.json", "test_scope_policy.json"):
            self.write("scripts/ci/" + name, (ROOT / "scripts/ci" / name).read_text())
        self.write("tools/canary/policy.json", (ROOT / "tools/canary/policy.json").read_text())
        for host in ("creator-web", "web-runtime-host"):
            relative = "apps/" + host + "/module.json"
            self.write(relative, (ROOT / relative).read_text())
        self.base = self.commit("baseline")
        self.progress = self.progress_at(self.base)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def write(self, name, text):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def commit(self, message):
        self.git("add", ".")
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD")

    def change(self, name, text="changed"):
        self.write(name, text)
        return self.commit("change " + name)

    def progress_at(self, revision):
        result = r.initial_progress("endaye/lmdj")
        pointer = {"revision": revision, "receipt_digest": "a" * 64}
        result["version_accounted"] = deepcopy(pointer)
        result["formal"] = deepcopy(pointer)
        result["deployments"] = {site: deepcopy(pointer) for site in r.SITES}
        return r.seal(result)

    def plan(self, target=None, **kwargs):
        latest = self.git("rev-parse", "main")
        return p.plan_batch(self.root, main_sha=latest, target_sha=target or latest,
                            control_sha=kwargs.pop("control_sha", self.base),
                            progress=kwargs.pop("progress", self.progress),
                            request_id="request:one", **kwargs)

    def test_no_change_selects_nothing_and_is_not_admission(self):
        result = self.plan()
        self.assertEqual(result["deploy_sites"], [])
        self.assertEqual(result["build_hosts"], [])
        self.assertEqual(result["test_floor"]["kind"], "none")
        self.assertEqual(result["purpose"], "read-only-preview")
        self.assertFalse(result["admission_evidence"])

    def test_docs_and_explanatory_docs_are_distinct(self):
        explanation = self.change("docs/design/note.md")
        self.assertEqual(self.plan(explanation)["deploy_sites"], [])
        target = self.change("apps/docs-site/docs/overview/index.mdx")
        result = self.plan(target)
        self.assertEqual(result["deploy_sites"], ["docs"])
        self.assertEqual(result["build_hosts"], [])

    def test_creator_change_builds_complete_candidate_but_selects_one_product_site(self):
        result = self.plan(self.change("apps/creator-web/src/example.ts"))
        # Canonical ownership also selects portal: Host source facts are docs
        # inputs. Preserve that real dependency rather than hiding it for T1.
        self.assertEqual(result["deploy_sites"], ["creator", "docs"])
        self.assertEqual([host["id"] for host in result["build_hosts"]],
                         ["creator-web", "web-runtime-host"])
        self.assertEqual(result["test_floor"]["suites"], ["creator", "portal"])

    def test_runtime_dependency_closure_includes_creator(self):
        result = self.plan(self.change("apps/web-runtime-host/src/example.mjs"))
        self.assertEqual(result["deploy_sites"], list(r.SITES))
        self.assertTrue({"creator", "web_runtime_host", "web_runtime_lab"}
                        <= set(result["test_floor"]["suites"]))

    def test_shared_foundation_requires_full_and_all_sites(self):
        result = self.plan(self.change("packages/foundation/src/example.cpp"))
        self.assertEqual(result["deploy_sites"], list(r.SITES))
        self.assertEqual(result["test_floor"]["kind"], "full")
        self.assertEqual(len(result["test_floor"]["suites"]), 16)

    def test_changelog_is_also_a_docs_consumer(self):
        result = self.plan(self.change("apps/creator-web/CHANGELOG.md"))
        self.assertEqual(result["deploy_sites"], ["creator", "docs"])

    def test_revert_keeps_changed_paths_in_complete_interval(self):
        self.change("apps/creator-web/src/example.ts")
        self.git("revert", "--no-edit", "HEAD")
        target = self.git("rev-parse", "HEAD")
        self.assertEqual(self.git("diff", "--name-only", self.base, target), "")
        result = self.plan(target)
        self.assertEqual(result["deploy_sites"], ["creator", "docs"])
        self.assertIn("apps/creator-web/src/example.ts", result["version_interval"]["paths"])
        self.assertEqual(len(result["version_interval"]["commits"]), 2)

    def test_rename_and_delete_cover_both_owners(self):
        self.change("apps/creator-web/src/example.ts")
        self.write("apps/web-runtime-host/src/.keep", "")
        self.git("mv", "apps/creator-web/src/example.ts", "apps/web-runtime-host/src/example.ts")
        self.commit("move across Hosts")
        self.git("rm", "apps/web-runtime-host/src/example.ts")
        result = self.plan(self.commit("delete"))
        self.assertTrue({"creator", "runtime"} <= set(result["deploy_sites"]))
        self.assertTrue({"apps/creator-web/src/example.ts", "apps/web-runtime-host/src/example.ts"}
                        <= set(result["version_interval"]["paths"]))

    def test_deployment_and_version_and_formal_progress_remain_independent(self):
        creator = self.change("apps/creator-web/src/example.ts")
        target = self.change("apps/docs-site/docs/overview/index.mdx")
        progress = deepcopy(self.progress)
        progress["version_accounted"] = {"revision": creator, "receipt_digest": "b" * 64}
        progress["deployments"]["creator"] = {"revision": target, "receipt_digest": "c" * 64}
        result = self.plan(target, progress=r.seal(progress))
        self.assertEqual(result["deploy_sites"], ["docs"])
        self.assertEqual(result["version_interval"]["paths"], ["apps/docs-site/docs/overview/index.mdx"])
        self.assertEqual(len(result["formal_interval"]["commits"]), 2)
        self.assertEqual(result["site_intervals"]["creator"]["paths"], [])
        self.assertEqual(result["site_intervals"]["runtime"]["base_sha"], self.base)

    def test_late_manual_request_does_not_erase_unselected_site_or_test_scope(self):
        self.change("apps/creator-web/src/example.ts")
        target = self.change("apps/docs-site/docs/overview/index.mdx")
        result = self.plan(target, kind="manual", sites=["docs"])
        self.assertEqual(result["affected_sites"], ["creator", "docs"])
        self.assertEqual(result["deploy_sites"], ["docs"])
        self.assertEqual(result["build_hosts"], [])
        self.assertIn("creator", result["test_floor"]["suites"])

    def test_already_delivered_other_host_changes_are_not_pending_test_work(self):
        target = self.change("apps/creator-web/src/example.ts")
        progress = self.progress_at(target)
        progress["deployments"]["runtime"] = deepcopy(self.progress["deployments"]["runtime"])
        result = self.plan(target, progress=r.seal(progress))
        self.assertEqual(result["deploy_sites"], [])
        self.assertEqual(result["test_floor"]["kind"], "none")
        self.assertEqual(result["site_intervals"]["runtime"]["base_sha"], self.base)

    def test_empty_interval_does_not_redeploy_for_missing_old_policy(self):
        self.git("rm", "scripts/ci/test_scope_policy.json")
        target = self.commit("missing historical policy")
        self.write("scripts/ci/test_scope_policy.json", (ROOT / "scripts/ci/test_scope_policy.json").read_text())
        control = self.commit("restore policy")
        result = self.plan(target, progress=self.progress_at(target), control_sha=control)
        self.assertEqual(result["deploy_sites"], [])
        self.assertEqual(result["test_floor"]["kind"], "none")

    def test_manual_force_is_preview_only_and_stable_across_replay(self):
        result = self.plan(kind="manual", sites=["creator"], force=True)
        self.assertEqual(result["affected_sites"], [])
        self.assertEqual(result["deploy_sites"], ["creator"])
        self.assertEqual(len(result["build_hosts"]), 2)
        self.assertEqual(result, self.plan(kind="manual", sites=["creator"], force=True))
        self.assertFalse(result["admission_evidence"])

    def test_daily_cannot_silently_become_filtered_or_forced(self):
        for kwargs in ({"force": True}, {"sites": ["creator"]}, {"sites": []},
                       {"kind": "unknown"}, {"force": 1}, {"sites": ["creator", "creator"]}):
            with self.subTest(kwargs=kwargs), self.assertRaises(r.CanaryError):
                self.plan(**kwargs)

    def test_bootstrap_selects_all_but_does_not_invent_commit_interval(self):
        result = self.plan(progress=r.initial_progress("endaye/lmdj"))
        self.assertEqual(result["deploy_sites"], list(r.SITES))
        self.assertEqual(result["version_interval"]["kind"], "bootstrap")
        self.assertIsNone(result["version_interval"]["commits"])
        self.assertEqual(result["test_floor"]["kind"], "full")

    def test_old_target_stays_pinned_when_main_moves(self):
        target = self.change("apps/creator-web/src/example.ts")
        first = self.plan(target)
        self.change("packages/foundation/src/later.cpp")
        self.assertEqual(first, self.plan(target))

    def test_dirty_candidate_code_and_policy_are_never_executed_or_used(self):
        target = self.change("apps/creator-web/src/example.ts")
        self.write("tools/canary/policy.json", "not committed")
        self.write("scripts/ci/test_scope.py", "raise RuntimeError('untrusted target code')")
        before = self.git("status", "--porcelain"), self.git("show-ref")
        result = self.plan(target)
        self.assertEqual(result["deploy_sites"], ["creator", "docs"])
        self.assertEqual((self.git("status", "--porcelain"), self.git("show-ref")), before)

    def test_missing_old_policy_conservatively_selects_full(self):
        self.git("rm", "scripts/ci/test_scope_policy.json")
        missing = self.commit("old policy unavailable")
        self.write("scripts/ci/test_scope_policy.json", (ROOT / "scripts/ci/test_scope_policy.json").read_text())
        control = self.commit("restore control")
        self.progress = self.progress_at(missing)
        result = self.plan(control, control_sha=control)
        self.assertEqual(result["test_floor"]["kind"], "full")
        self.assertEqual(result["deploy_sites"], list(r.SITES))

    def test_missing_current_policy_is_error_not_no_change(self):
        self.git("rm", "tools/canary/policy.json")
        target = self.commit("missing planner policy")
        with self.assertRaisesRegex(r.CanaryError, "why:.*remedy:"):
            self.plan(target, control_sha=target)

    def test_historical_scope_policy_cannot_shrink_the_floor(self):
        old = json.loads((self.root / "scripts/ci/test_scope_policy.json").read_text())
        old["full_prefixes"].append("apps/creator-web/")
        self.write("scripts/ci/test_scope_policy.json", json.dumps(old))
        prior = self.commit("broader policy")
        self.write("scripts/ci/test_scope_policy.json", (ROOT / "scripts/ci/test_scope_policy.json").read_text())
        current = self.commit("restore policy")
        self.progress = self.progress_at(prior)
        result = self.plan(self.change("apps/creator-web/src/example.ts"), control_sha=current)
        self.assertEqual(result["test_floor"]["kind"], "full")

    def test_missing_noncommit_or_side_parent_baseline_is_error(self):
        blob = self.git("rev-parse", self.base + ":tools/canary/policy.json")
        self.git("checkout", "-b", "side")
        side = self.change("docs/design/side.md")
        self.git("checkout", "main")
        target = self.change("docs/design/main.md")
        self.git("merge", "--no-ff", "side", "-m", "merge side")
        target = self.git("rev-parse", "HEAD")
        for revision in ("f" * 40, blob, side):
            with self.subTest(revision=revision), self.assertRaises(r.CanaryError):
                self.plan(target, progress=self.progress_at(revision))

    def test_target_must_be_first_parent_main_and_control_must_be_main_history(self):
        self.git("checkout", "-b", "side")
        side = self.change("docs/design/side.md")
        self.git("checkout", "main")
        with self.assertRaises(r.CanaryError):
            self.plan(side)
        with self.assertRaises(r.CanaryError):
            self.plan(control_sha=side)

    def test_shallow_repository_fails_closed(self):
        clone = self.root / "shallow"
        subprocess.run(["git", "clone", "--depth", "1", self.root.as_uri(), str(clone)],
                       check=True, capture_output=True)
        with self.assertRaises(r.CanaryError):
            p.plan_batch(clone, main_sha=self.base, target_sha=self.base,
                         control_sha=self.base, progress=self.progress, request_id="one")

    def test_record_identity_and_changed_request_inputs_affect_digests(self):
        first = self.plan()
        second = self.plan(kind="manual", sites=["docs"])
        self.assertNotEqual(first["input_digest"], second["input_digest"])
        changed = deepcopy(first)
        changed["deploy_sites"] = ["creator"]
        with self.assertRaises(r.CanaryError):
            r.verify_seal(changed)

    def test_unknown_paths_select_all_and_invalid_host_manifest_refuses_build(self):
        target = self.change("unknown-new-owner/source.txt")
        self.assertEqual(self.plan(target)["deploy_sites"], list(r.SITES))
        target = self.change("apps/creator-web/module.json", '{"module":"invented","version":42}')
        with self.assertRaises(r.CanaryError):
            self.plan(target)


if __name__ == "__main__":
    unittest.main()
