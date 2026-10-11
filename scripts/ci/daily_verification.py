#!/usr/bin/env python3
"""Daily workloads within canonical ownership; deferred is never passing evidence.

This policy is deliberately conservative. It reduces execution for audited path
families, not ownership, and leaves unknown inputs at complete verification.
Callers must supply the complete changed-path union, including deleted paths.
"""
from __future__ import annotations

MODES = frozenset({"deferred", "quick", "journey", "full"})
ORDER = {"deferred": 0, "quick": 1, "journey": 2, "full": 3}
SUITES = frozenset({
    "docs_static", "portal", "ci_contract", "core_ubuntu", "core_asan",
    "core_coverage", "core_macos", "web_toolchain", "web_runtime_host",
    "creator", "web_runtime_lab", "deploy_contract", "package",
    "core_tsan_stress", "core_release_stress",
})
# Presentation-only components have unit coverage plus the durable browser
# smoke. New components and mutation/capture/recovery surfaces keep journeys.
SMOKE_COMPONENTS = frozenset({
    "creator_details.tsx", "parameter_slider.tsx", "fx_slider_bank.tsx",
    "diagnostics_log.tsx", "error_panel.tsx", "touch_kit.tsx",
    "value_slider.tsx", "modal_dialog.tsx", "hardware_icons.tsx",
    "hardware_console.tsx", "overview_display.tsx", "project_overview.tsx",
    "sample_overview.tsx", "sequence_overview.tsx", "perform_overview.tsx",
})
# Workload names are an execution contract, never arbitrary command strings.
ALLOWED = {suite: {"deferred", "full"} for suite in SUITES}
ALLOWED.update(core_ubuntu={"deferred", "quick", "full"},
               ci_contract={"deferred", "quick", "full"},
               creator={"deferred", "quick", "journey", "full"},
               web_runtime_host={"deferred", "journey", "full"})


def validate(workloads, selected):
    if (not isinstance(workloads, dict) or set(workloads) != set(selected)
            or not set(selected) <= SUITES
            or any(not isinstance(mode, str) or mode not in ALLOWED[suite]
                   for suite, mode in workloads.items())):
        raise ValueError("why: daily workload inventory is invalid; remedy: rebuild from complete canonical scope and paths")
    return dict(sorted(workloads.items()))


def select(routing, selected, paths, *, profile="quick", complete=True, classifier=None):
    """Return every selected suite with an explicit, independently named mode.

Full always executes all selected suites. Quick preserves canonical lanes but
moves repeated cross-platform, coverage, reproducibility and packaging work to
full verification unless an owning risk below requires it now. Unknown paths,
foundational code and shared build/Contract changes keep the full fallback.
"""
    if classifier is None:
        import change_scope as classifier
    selected = set(selected)
    if not selected <= SUITES or profile not in {"quick", "full"} or type(complete) is not bool:
        raise ValueError("why: invalid daily selection inputs; remedy: supply canonical suites and quick/full profile")
    if not isinstance(paths, (list, tuple)) or not all(isinstance(path, str) for path in paths):
        raise ValueError("why: changed paths are not a complete list; remedy: collect both sides of the Git interval")
    full = {suite: "full" for suite in sorted(selected)}
    for path in paths:
        classifier._validate_path(path)
    if profile == "full" or not complete:
        return full
    modes = {suite: "deferred" for suite in sorted(selected)}

    def require(names, mode):
        for suite in set(names) & selected:
            if ORDER[mode] > ORDER[modes[suite]]:
                modes[suite] = mode

    def native():
        require(["core_ubuntu"], "quick")
        require(["web_runtime_host", "creator"], "journey")

    for path in paths:
        lanes, reasons = classifier.path_classification(routing, path)
        if not lanes and not reasons:
            return full
        # These are verification implementations, not product source. Their
        # own contract selector retains all tests/seam for unmapped consumers.
        if path.startswith(("scripts/ci/", "tests/build/ci_", "tests/fixtures/ci/")):
            require(["ci_contract"], "quick")
        elif path.startswith(("packages/audio-runtime/", "packages/application-facade/",
                              "packages/foundation/", "contracts/", "products/", "cmake/",
                              "third_party/")) or reasons:
            return full
        elif path.startswith(("docs/", "apps/docs-site/", ".agents/", ".claude/")) or path in {
                "AGENTS.md", "CLAUDE.md", "README.md", "LICENSE"}:
            require(lanes, "full")
        elif path.startswith("apps/creator-web/"):
            if (path.startswith("apps/creator-web/src/components/")
                    and path.removeprefix("apps/creator-web/src/components/") in SMOKE_COMPONENTS
                    or path.startswith("apps/creator-web/test/") or path.endswith(".css")):
                require(["creator"], "quick")
            else:
                require(["creator"], "journey")
            require(lanes & {"deploy_contract"}, "full")
        elif path.startswith(("packages/authoring-domain/", "packages/project-cooker/",
                              "tests/core/domain/", "tests/core/cooker/")):
            native()
        elif path.startswith(("packages/project-io/", "tests/core/project_io/", "tests/host/",
                              "apps/core-cli/", "apps/core-mcp/", "apps/native-host/")):
            native()
            # Native persistence/host journeys and their platform variants do
            # not belong to the fast tier. Keep their complete owning lanes.
            require(["core_ubuntu", "core_asan", "core_macos"], "full")
        elif path.startswith(("apps/web-runtime-host/", "packages/web-runtime-platform/",
                              "tests/platform/web/host/", "tests/platform/web/creator/")):
            require(lanes & {"core_ubuntu", "core_asan", "core_macos"}, "full")
            require(["web_runtime_host", "creator"], "journey")
            require(lanes & {"deploy_contract"}, "full")
        elif path.startswith(("demos/web-runtime-lab/", "apps/web-runtime-lab/")):
            require(["web_runtime_lab"], "full")
        else:
            return full
        # Portal and static checks retain the same obligations as source scope.
        require(lanes & {"docs_static", "portal"}, "full")
        require(lanes & {"ci_contract"}, "quick")
    return validate(modes, selected)
