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
EXPECTED_ACTION_PINS = {
    "actions/checkout": (
        "de0fac2e4500dabe0009e67214ff5f5447ce83dd",
        "v6.0.2",
    ),
    "actions/setup-python": (
        "a309ff8b426b58ec0e2a45f0f869d46889d02405",
        "v6.2.0",
    ),
    "actions/setup-node": (
        "48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e",
        "v6.4.0",
    ),
    "actions/upload-artifact": (
        "ea165f8d65b6e75b540449e92b4886f43607fa02",
        "v4.6.2",
    ),
}
CREDENTIAL_ENVIRONMENT = {
    "GITHUB_TOKEN",
    "NETLIFY_RUNTIME_SITE_ID",
    "NETLIFY_AUTH_TOKEN",
}


class WebRuntimeDeployWorkflowTest(unittest.TestCase):
    def workflow_source(self) -> str:
        self.assertTrue(WORKFLOW.is_file(), "deployment workflow is missing")
        return WORKFLOW.read_text(encoding="utf-8")

    def mapping_block(self, source: str, key: str, indent: int) -> str:
        lines = source.splitlines()
        header = f"{' ' * indent}{key}:"
        try:
            start = lines.index(header)
        except ValueError:
            self.fail(f"workflow mapping is missing: {key}")

        end = len(lines)
        for index in range(start + 1, len(lines)):
            line = lines[index]
            if not line.strip():
                continue
            line_indent = len(line) - len(line.lstrip(" "))
            if line_indent <= indent:
                end = index
                break
        return "\n".join(lines[start + 1 : end])

    def direct_mapping(self, source: str, indent: int) -> dict[str, str]:
        entries: dict[str, str] = {}
        pattern = re.compile(
            rf"^ {{{indent}}}([A-Za-z_][A-Za-z0-9_-]*):(?:\s+(.*?))?\s*$"
        )
        for line in source.splitlines():
            match = pattern.fullmatch(line)
            if match is not None:
                key = match.group(1)
                self.assertNotIn(key, entries, f"duplicate workflow mapping: {key}")
                entries[key] = match.group(2) or ""
        return entries

    def workflow_steps(self, source: str) -> list[str]:
        steps: list[list[str]] = []
        current: list[str] | None = None
        for line in source.splitlines():
            if line.startswith("      - "):
                if current is not None:
                    steps.append(current)
                current = [line]
            elif current is not None:
                current.append(line)
        if current is not None:
            steps.append(current)
        return ["\n".join(step) for step in steps]

    def step_named(self, source: str, name: str) -> str:
        for step in self.workflow_steps(source):
            if step.splitlines()[0] == f"      - name: {name}":
                return step
        self.fail(f"workflow step is missing: {name}")

    def test_workflow_only_deploys_published_release_or_exact_manual_tag(
        self,
    ) -> None:
        source = self.workflow_source()
        triggers = self.mapping_block(source, "on", 0)
        self.assertEqual(
            self.direct_mapping(triggers, 2),
            {"release": "", "workflow_dispatch": ""},
        )
        release = self.mapping_block(triggers, "release", 2)
        self.assertEqual(self.direct_mapping(release, 4), {"types": "[published]"})
        workflow_dispatch = self.mapping_block(triggers, "workflow_dispatch", 2)
        self.assertEqual(
            set(self.direct_mapping(workflow_dispatch, 4)),
            {"inputs"},
        )
        self.assertIn("environment: runtime-canary", source)
        self.assertIn("cancel-in-progress: false", source)
        permissions = self.mapping_block(source, "permissions", 0)
        self.assertEqual(self.direct_mapping(permissions, 2), {"contents": "read"})
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
        checkout_pin, checkout_version = EXPECTED_ACTION_PINS["actions/checkout"]
        checkout = next(
            (
                step
                for step in self.workflow_steps(source)
                if step.splitlines()[0]
                == f"      - uses: actions/checkout@{checkout_pin} # {checkout_version}"
            ),
            None,
        )
        self.assertIsNotNone(checkout, "pinned checkout step is missing")
        assert checkout is not None
        checkout_options = self.mapping_block(checkout, "with", 8)
        self.assertEqual(
            self.direct_mapping(checkout_options, 10),
            {
                "ref": "main",
                "fetch-depth": "0",
                "persist-credentials": "false",
            },
        )

    def test_all_third_party_actions_use_verified_full_sha_pins(self) -> None:
        source = self.workflow_source()
        uses_lines = [line.strip() for line in source.splitlines() if "uses:" in line]
        observed: dict[str, tuple[str, str]] = {}
        for line in uses_lines:
            match = re.fullmatch(
                r"-?\s*uses: (actions/[a-z-]+)@([0-9a-f]{40}) # (v[0-9]+(?:\.[0-9]+){1,2})",
                line,
            )
            self.assertIsNotNone(match, f"action is not pinned to a full SHA: {line}")
            assert match is not None
            observed[match.group(1)] = (match.group(2), match.group(3))
        self.assertEqual(observed, EXPECTED_ACTION_PINS)

    def test_credentials_exist_only_in_the_deploy_step(self) -> None:
        source = self.workflow_source()
        self.assertNotIn("env", self.direct_mapping(source, 0))
        jobs = self.mapping_block(source, "jobs", 0)
        self.assertEqual(set(self.direct_mapping(jobs, 2)), {"deploy"})
        deploy_job = self.mapping_block(jobs, "deploy", 2)
        self.assertNotIn("env", self.direct_mapping(deploy_job, 4))

        deploy_step = self.step_named(source, "Deploy signed Runtime Host release")
        deploy_environment = self.direct_mapping(
            self.mapping_block(deploy_step, "env", 8),
            10,
        )
        self.assertEqual(
            deploy_environment,
            {
                "GITHUB_TOKEN": "${{ github.token }}",
                "NETLIFY_RUNTIME_SITE_ID": (
                    "${{ secrets.NETLIFY_RUNTIME_SITE_ID }}"
                ),
                "NETLIFY_AUTH_TOKEN": "${{ secrets.NETLIFY_AUTH_TOKEN }}",
                "LMDJ_RELEASE_TAG": "${{ steps.release-tag.outputs.tag }}",
            },
        )

        for step in self.workflow_steps(source):
            if step == deploy_step or "        env:" not in step:
                continue
            environment = self.direct_mapping(
                self.mapping_block(step, "env", 8),
                10,
            )
            self.assertTrue(
                CREDENTIAL_ENVIRONMENT.isdisjoint(environment),
                f"credential leaked to non-deploy step: {step.splitlines()[0]}",
            )

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
        upload_pin, upload_version = EXPECTED_ACTION_PINS[
            "actions/upload-artifact"
        ]
        self.assertIn(
            f"uses: actions/upload-artifact@{upload_pin} # {upload_version}",
            source,
        )
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
