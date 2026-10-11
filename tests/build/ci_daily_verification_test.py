#!/usr/bin/env python3
"""Independent workload expectations for the daily/full execution boundary."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import change_scope
import daily_verification as daily

ALL = {"docs_static", "portal", "ci_contract", "core_ubuntu", "core_asan",
       "core_coverage", "core_macos", "web_toolchain", "web_runtime_host",
       "creator", "web_runtime_lab", "deploy_contract", "package",
       "core_tsan_stress", "core_release_stress"}


class DailyVerificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routing = change_scope.load_policy(ROOT / "scripts/ci/scope_policy.json")

    def plan(self, *paths, selected=ALL, **options):
        return daily.select(self.routing, selected, list(paths), **options)

    def assert_work(self, result, expected):
        self.assertEqual({suite: mode for suite, mode in result.items() if mode != "deferred"}, expected)
        self.assertEqual(set(result), ALL)

    def test_ui_has_build_units_and_complete_smoke_not_full_browser_matrix(self):
        self.assert_work(self.plan("apps/creator-web/src/components/fx_slider_bank.tsx"),
                         {"creator": "quick", "portal": "full"})

    def test_runtime_owner_keeps_complete_journeys(self):
        self.assert_work(self.plan("apps/creator-web/src/app.tsx"),
                         {"creator": "journey", "portal": "full"})

    def test_capture_mutation_and_unknown_components_keep_all_browser_legs(self):
        for name in ("capture_panel.tsx", "perform_surface.tsx", "project_surface.tsx",
                     "recovery_prompt.tsx", "authoring_history.tsx", "new_surface.tsx"):
            with self.subTest(name=name):
                self.assert_work(self.plan("apps/creator-web/src/components/" + name),
                                 {"creator": "journey", "portal": "full"})

    def test_ci_control_change_does_not_compile_every_product(self):
        self.assert_work(self.plan("scripts/ci/batch_controller.py"), {"ci_contract": "quick"})

    def test_project_storage_keeps_native_persistence_and_host_consumers(self):
        self.assert_work(self.plan("packages/project-io/src/project_repository.cpp"), {
            "portal": "full", "core_ubuntu": "full", "core_asan": "full",
            "core_macos": "full", "web_runtime_host": "journey", "creator": "journey"})

    def test_domain_change_keeps_fast_core_and_complete_host_journeys(self):
        self.assert_work(self.plan("packages/authoring-domain/src/project.cpp"), {
            "portal": "full", "core_ubuntu": "quick",
            "web_runtime_host": "journey", "creator": "journey"})

    def test_core_concurrency_and_shared_contracts_remain_conservative(self):
        for path in ("packages/audio-runtime/src/engine.cpp", "packages/foundation/include/value.hpp",
                     "packages/application-facade/src/application.cpp", "contracts/new/schema.json",
                     "CMakeLists.txt", "products/lmdj/assembly.json", "cmake/new.cmake"):
            with self.subTest(path=path):
                self.assertEqual(self.plan(path), {suite: "full" for suite in ALL})

    def test_unknown_or_unmapped_paths_do_not_silently_defer(self):
        for path in ("unknown/component.rs", "apps/new-host/main.cpp", "scripts/core.sh",
                     "tests/platform/audio/new_test.cpp", "tests/platform/web/playwright.config.mjs",
                     "tests/platform/web/deployment/creator_web_deployment.spec.mjs"):
            with self.subTest(path=path):
                self.assertEqual(self.plan(path), {suite: "full" for suite in ALL})

    def test_mixed_paths_union_work_and_never_shrink_to_last_path(self):
        paths = ["apps/creator-web/src/app.tsx", "apps/creator-web/src/components/fx_slider_bank.tsx",
                 "scripts/ci/local_preflight.py", "docs/plans/example.md"]
        expected = {"creator": "journey", "ci_contract": "quick", "portal": "full", "docs_static": "full"}
        self.assert_work(self.plan(*paths), expected)
        self.assert_work(self.plan(*reversed(paths)), expected)

    def test_deleted_path_retains_ownership_without_reading_its_file(self):
        self.assert_work(self.plan("apps/creator-web/src/components/deleted.tsx"),
                         {"creator": "journey", "portal": "full"})

    def test_full_and_incomplete_inventory_retain_all_fifteen_suites(self):
        self.assertEqual(self.plan("apps/creator-web/src/components/button.tsx", profile="full"),
                         {suite: "full" for suite in ALL})
        self.assertEqual(self.plan(complete=False), {suite: "full" for suite in ALL})

    def test_does_not_invent_unselected_passes_or_suites(self):
        self.assertEqual(self.plan("docs/plans/example.md", selected={"docs_static"}), {"docs_static": "full"})
        self.assertEqual(self.plan(selected=set()), {})
        self.assertTrue(all(mode == "deferred" for mode in self.plan().values()))

    def test_workload_schema_is_closed_and_modes_are_suite_specific(self):
        for workloads, selected in [({"creator": "skip"}, {"creator"}), ({}, {"creator"}),
                                    ({"core_macos": "quick"}, {"core_macos"}),
                                    ({"extra": "full"}, {"extra"})]:
            with self.subTest(workloads=workloads):
                with self.assertRaisesRegex(ValueError, "why:.*remedy:"):
                    daily.validate(workloads, selected)

    def test_invalid_inputs_cannot_become_empty_success(self):
        for args in [(self.routing, ALL, ["../escape"]), (self.routing, {"foreign"}, []),
                     (self.routing, ALL, "not-a-list")]:
            with self.assertRaises(ValueError):
                daily.select(*args)


if __name__ == "__main__":
    unittest.main()
