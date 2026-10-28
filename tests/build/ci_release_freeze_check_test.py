#!/usr/bin/env python3
"""The PR Contract refuses CI and release-tool changes while a release request is active.

`scripts/ci/release_freeze_check.py` reads the repository variable
`LMDJ_RELEASE_FREEZE` (set by `scripts/release.sh run` for the request it
drives, cleared when the request completes or is retired) and the PR's
changed files from the frozen change-scope manifest file. The defects these
tests catch: passing a frozen PR while a request is active, failing a PR that
touches nothing frozen, failing when no request is active, widening or
narrowing the frozen path set silently, treating an unreadable manifest as a
pass (#2422 item 10, #2404 item 1), and losing a manifest larger than the
128 KiB argv/env string limit (#2511).
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts/ci"))
import release_freeze_check as check  # noqa: E402

SCRIPT = REPO_ROOT / "scripts/ci/release_freeze_check.py"
REQUEST = "release-0123456789abcdef"


def manifest(*paths: str) -> str:
    return json.dumps({"schema": "lmdj.ci-scope.v2", "changed_files": [
        {"result": "modified", "paths": [path]} for path in paths]})


class ReleaseFreezeCheckTest(unittest.TestCase):
    def run_check(self, freeze: str, manifest_json: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pr-contract-manifest.json"
            path.write_text(manifest_json, encoding="utf-8")
            return self.run_check_file(freeze, str(path))

    def run_check_file(self, freeze: str, path: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--freeze", freeze, "--manifest-file", path],
            capture_output=True, text=True, check=False, timeout=30)

    def test_frozen_paths_are_the_ci_and_release_control_plane(self) -> None:
        self.assertEqual(check.FROZEN_PREFIXES,
                         (".github/workflows/", ".github/actions/", "scripts/ci/", "tools/release/"))
        self.assertEqual(check.FROZEN_EXACT, ("scripts/release.sh",))
        self.assertEqual(check.frozen_paths([
            ".github/workflows/ci.yml", ".github/actions/web-ci-proof/action.yml", "scripts/ci/batch_controller.py",
            "scripts/ci/host/runner-network-admission.sh", "tools/release/cli.py", "scripts/release.sh",
            "apps/creator-web/src/app.tsx", "products/lmdj/version.json", "docs/governance/git-workflow.md",
            ".github/CODEOWNERS", "scripts/core.sh", "tests/build/release_cli_test.py"]), [
            ".github/actions/web-ci-proof/action.yml", ".github/workflows/ci.yml", "scripts/ci/batch_controller.py",
            "scripts/ci/host/runner-network-admission.sh", "scripts/release.sh", "tools/release/cli.py"])

    def test_no_active_request_passes_whatever_the_pr_touches(self) -> None:
        result = self.run_check("", manifest(".github/workflows/ci.yml", "tools/release/cli.py"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no release request holds the freeze", result.stdout)

    def test_an_active_request_refuses_a_pr_that_touches_frozen_paths(self) -> None:
        result = self.run_check(REQUEST, manifest("scripts/ci/batch_controller.py", "apps/creator-web/src/app.tsx"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("why:", result.stderr)
        self.assertIn(REQUEST, result.stderr)
        self.assertIn("scripts/ci/batch_controller.py", result.stderr)
        self.assertNotIn("apps/creator-web/src/app.tsx", result.stderr)
        self.assertIn("remedy:", result.stderr)
        self.assertIn("scripts/release.sh status", result.stderr)

    def test_an_active_request_passes_a_pr_outside_the_frozen_paths(self) -> None:
        result = self.run_check(REQUEST, manifest("apps/creator-web/src/app.tsx", "products/lmdj/version.json",
                                                  "docs/release-evidence/release-intents.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(REQUEST, result.stdout)
        self.assertIn("touches no frozen path", result.stdout)

    def test_a_malformed_freeze_value_or_manifest_fails_closed(self) -> None:
        for freeze, document in (("not a request id", manifest("README.md")),
                                 (REQUEST, "not json"),
                                 (REQUEST, json.dumps({"changed_files": "nope"})),
                                 (REQUEST, json.dumps({"changed_files": [{"paths": "x"}]}))):
            with self.subTest(freeze=freeze, document=document[:20]):
                result = self.run_check(freeze, document)
                self.assertEqual(result.returncode, 1)
                self.assertIn("why:", result.stderr)
                self.assertIn("remedy:", result.stderr)

    def test_a_missing_manifest_file_fails_closed_even_without_a_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_check_file("", str(Path(directory) / "absent.json"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("why: the change-scope manifest file", result.stderr)
        self.assertIn("remedy:", result.stderr)

    def test_a_manifest_beyond_the_argv_string_limit_is_read_whole(self) -> None:
        # The PR #2511 manifest was 276 KB; Linux refuses one argv or env
        # string above 128 KiB, so the check never ran. The frozen path sits
        # last so only a complete read can find it.
        paths = [f"apps/architecture-portal/versioned_docs/version-2.0.{n}.0/page.mdx" for n in range(4000)]
        document = manifest(*paths, "tools/release/cli.py")
        self.assertGreater(len(document.encode()), 256 * 1024)
        result = self.run_check(REQUEST, document)
        self.assertEqual(result.returncode, 1)
        self.assertIn("tools/release/cli.py", result.stderr)


if __name__ == "__main__":
    unittest.main()
