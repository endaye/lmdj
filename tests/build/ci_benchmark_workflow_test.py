#!/usr/bin/env python3
"""Contract tests for the non-authoritative self-hosted Web benchmark."""

from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = REPO_ROOT / ".github/workflows/ci-self-hosted-benchmark.yml"
FORMAL = REPO_ROOT / ".github/workflows/ci.yml"
ACTION = REPO_ROOT / ".github/actions/web-ci-proof/action.yml"


class CiBenchmarkWorkflowTest(unittest.TestCase):
    def test_benchmark_is_dispatch_only_and_non_authoritative(self) -> None:
        source = BENCHMARK.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", source)
        self.assertNotRegex(source, r"(?m)^  (?:pull_request|push|schedule):")
        self.assertIn("permissions:\n  contents: read", source)
        self.assertNotIn("PR Gate", source)
        self.assertNotIn("pr_gate.py", source)

    def test_benchmark_targets_only_the_web_role(self) -> None:
        source = BENCHMARK.read_text(encoding="utf-8")
        self.assertIn(
            "runs-on: [self-hosted, Linux, X64, lmdj-linux, "
            "lmdj-linux-pool, ci-web-heavy]",
            source,
        )
        for lane in ("web_toolchain", "web_runtime_host", "creator"):
            self.assertIn(f"- {lane}", source)

    def test_benchmark_revision_is_the_dispatched_trusted_sha(self) -> None:
        source = BENCHMARK.read_text(encoding="utf-8")
        self.assertIn('[[ "$REVISION" =~ ^[0-9a-f]{40}$ ]]', source)
        self.assertIn('[[ "$REVISION" == "$TRUSTED_SHA" ]]', source)
        self.assertIn("TRUSTED_SHA: ${{ github.sha }}", source)

    def test_formal_and_benchmark_workflows_share_one_proof_action(self) -> None:
        formal = FORMAL.read_text(encoding="utf-8")
        benchmark = BENCHMARK.read_text(encoding="utf-8")
        for source in (formal, benchmark):
            self.assertIn("uses: ./.github/actions/web-ci-proof", source)

    def test_persistent_emsdk_install_is_serialized_atomic_and_group_readable(self) -> None:
        source = ACTION.read_text(encoding="utf-8")
        self.assertIn('flock 9', source)
        self.assertIn('mktemp -d "$cache_root/.install-', source)
        self.assertIn('chmod 2770 "$temporary"', source)
        self.assertIn('mv "$temporary" "$target"', source)


if __name__ == "__main__":
    unittest.main()
