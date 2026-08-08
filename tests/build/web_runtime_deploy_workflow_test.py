#!/usr/bin/env python3
"""Contract tests for signed Web Runtime Host release deployment."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/deploy-web-runtime-host.yml"
PUBLIC_KEY = REPO_ROOT / ".github/release-signing-keys/lmdj-product.asc"
TRUSTED_FINGERPRINT = "2B5EE362F058800036AD4FB5116ECE156F954D29"


class WebRuntimeDeployWorkflowTest(unittest.TestCase):
    def workflow_source(self) -> str:
        self.assertTrue(WORKFLOW.is_file(), "deployment workflow is missing")
        return WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_only_deploys_published_release_or_exact_manual_tag(
        self,
    ) -> None:
        source = self.workflow_source()
        self.assertIn("release:\n    types: [published]", source)
        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("pull_request:", source)
        self.assertNotRegex(source, r"(?m)^  push:")
        self.assertIn("environment: runtime-canary", source)
        self.assertIn("cancel-in-progress: false", source)
        self.assertIn("permissions:\n  contents: read", source)
        self.assertNotIn("contents: write", source)
        self.assertIn("ref: main", source)
        self.assertIn('scripts/web-runtime-deploy.sh deploy "$tag"', source)
        self.assertIn("NETLIFY_RUNTIME_SITE_ID", source)
        self.assertIn("NETLIFY_AUTH_TOKEN", source)

    def test_release_tag_selection_fails_closed(self) -> None:
        source = self.workflow_source()
        self.assertIn("github.event.release.tag_name", source)
        self.assertIn("github.event.release.prerelease", source)
        self.assertIn("inputs.tag", source)
        self.assertIn('[[ "$release_prerelease" == "true" ]]', source)
        self.assertIn(
            "^lmdj-v[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$",
            source,
        )

    def test_workflow_uses_protected_main_tooling_checkout(self) -> None:
        source = self.workflow_source()
        checkout = re.search(
            r"(?ms)^      - uses: actions/checkout@v\d+\n"
            r"        with:\n(?P<with>.*?)(?=^      - )",
            source,
        )
        self.assertIsNotNone(checkout, "checkout step is missing")
        assert checkout is not None
        self.assertIn("ref: main", checkout.group("with"))
        self.assertIn("fetch-depth: 0", checkout.group("with"))
        self.assertNotRegex(checkout.group("with"), r"ref:.*(?:tag|inputs)")

    def test_workflow_installs_only_deployment_dependencies(self) -> None:
        source = self.workflow_source()
        self.assertIn("python-version: \"3.11\"", source)
        self.assertIn("node-version: \"22\"", source)
        self.assertIn("working-directory: tests/platform/web", source)
        self.assertIn("run: npm ci", source)
        self.assertIn("playwright install --with-deps chromium", source)
        self.assertNotIn("webkit", source)
        self.assertNotIn("emsdk", source.lower())
        self.assertNotIn("emscripten", source.lower())
        self.assertNotIn("scripts/core.sh", source)

    def test_workflow_scopes_secrets_and_always_uploads_evidence(self) -> None:
        source = self.workflow_source()
        self.assertIn(
            "NETLIFY_RUNTIME_SITE_ID: ${{ secrets.NETLIFY_RUNTIME_SITE_ID }}",
            source,
        )
        self.assertIn(
            "NETLIFY_AUTH_TOKEN: ${{ secrets.NETLIFY_AUTH_TOKEN }}",
            source,
        )
        self.assertIn("uses: actions/upload-artifact@v4", source)
        self.assertIn("if: always()", source)
        self.assertIn("name: runtime-host-deployment-evidence", source)
        self.assertIn("build/deploy/web-runtime-host/evidence.json", source)
        self.assertIn("build/deploy/web-runtime-host/deployment.log", source)
        self.assertIn("if-no-files-found: warn", source)

    def test_public_key_has_exactly_one_trusted_primary_fingerprint(self) -> None:
        self.assertTrue(PUBLIC_KEY.is_file(), "Product signing public key is missing")
        completed = subprocess.run(
            [
                "gpg",
                "--batch",
                "--show-keys",
                "--with-colons",
                str(PUBLIC_KEY),
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

        primary_fingerprints: list[str] = []
        awaiting_primary_fingerprint = False
        for line in completed.stdout.splitlines():
            fields = line.split(":")
            record_type = fields[0]
            if record_type == "pub":
                awaiting_primary_fingerprint = True
            elif record_type == "fpr" and awaiting_primary_fingerprint:
                primary_fingerprints.append(fields[9])
                awaiting_primary_fingerprint = False
            elif record_type in {"sub", "sec", "ssb"}:
                awaiting_primary_fingerprint = False

        self.assertEqual(primary_fingerprints, [TRUSTED_FINGERPRINT])
        self.assertIn("BEGIN PGP PUBLIC KEY BLOCK", PUBLIC_KEY.read_text())
        self.assertNotIn("PRIVATE KEY", PUBLIC_KEY.read_text())


if __name__ == "__main__":
    unittest.main()
