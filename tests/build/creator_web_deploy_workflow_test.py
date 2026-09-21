#!/usr/bin/env python3
"""Contract tests for signed Creator Web Host release deployment."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import re
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/deploy-creator-web.yml"
DEPLOY_SCRIPT = REPO_ROOT / "scripts/creator-web-deploy.sh"
PRODUCT_PUBLIC_KEY = REPO_ROOT / ".github/release-signing-keys/lmdj-product.asc"
CHECKSUM_PUBLIC_KEY = REPO_ROOT / ".github/release-signing-keys/lmdj-release-checksum.asc"
TRUSTED_TAG_FINGERPRINT = "2B5EE362F058800036AD4FB5116ECE156F954D29"
TRUSTED_CHECKSUM_FINGERPRINT = "CB928A6E89DE498851688EF1AAC3E7019FC1478B"
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
        "b7c566a772e6b6bfb58ed0dc250532a479d7789f",
        "v6.0.0",
    ),
}
# Retired with the Netlify sites; a reappearance is a regression, not a rename.
NETLIFY_CREDENTIALS = {
    "NETLIFY_CREATOR_SITE_ID",
    "NETLIFY_AUTH_TOKEN",
}
DEPLOY_CREDENTIALS = {"CLOUDFLARE_API_TOKEN"}
CREDENTIAL_ENVIRONMENT = DEPLOY_CREDENTIALS | {"GITHUB_TOKEN"}
# `github.token` is the scoped, ephemeral Actions token and the workflow grants it
# only `contents: read`, so the credential-free preflight may read Release metadata
# with it. The Netlify secrets are environment-scoped and stay in the deploy job.
GITHUB_TOKEN_STEPS = {
    "Verify signed Creator Web Host release",
    "Deploy signed Creator Web Host release to Cloudflare",
}


def openpgp_packets(payload: bytes):
    offset = 0
    while offset < len(payload):
        header = payload[offset]
        offset += 1
        if header & 0x80 == 0:
            raise ValueError("OpenPGP packet header is invalid")

        if header & 0x40:
            tag = header & 0x3F
            if offset >= len(payload):
                raise ValueError("truncated OpenPGP packet length")
            first_length = payload[offset]
            offset += 1
            if first_length < 192:
                length = first_length
            elif first_length < 224:
                if offset >= len(payload):
                    raise ValueError("truncated OpenPGP packet length")
                length = ((first_length - 192) << 8) + payload[offset] + 192
                offset += 1
            elif first_length == 255:
                if offset + 4 > len(payload):
                    raise ValueError("truncated OpenPGP packet length")
                length = int.from_bytes(payload[offset : offset + 4], "big")
                offset += 4
            else:
                raise ValueError("partial OpenPGP packet lengths are unsupported")
        else:
            tag = (header >> 2) & 0x0F
            length_type = header & 0x03
            if length_type == 3:
                raise ValueError("indeterminate OpenPGP packet lengths are unsupported")
            length_bytes = (1, 2, 4)[length_type]
            if offset + length_bytes > len(payload):
                raise ValueError("truncated OpenPGP packet length")
            length = int.from_bytes(payload[offset : offset + length_bytes], "big")
            offset += length_bytes

        end = offset + length
        if end > len(payload):
            raise ValueError("OpenPGP packet extends beyond the armored payload")
        yield tag, payload[offset:end]
        offset = end


def primary_fingerprints(armored_key: str) -> list[str]:
    lines = armored_key.splitlines()
    begin_marker = "-----BEGIN PGP PUBLIC KEY BLOCK-----"
    end_marker = "-----END PGP PUBLIC KEY BLOCK-----"
    if lines.count(begin_marker) != 1 or lines.count(end_marker) != 1:
        raise ValueError("expected exactly one public key block")
    try:
        start = lines.index(begin_marker) + 1
        end = lines.index(end_marker)
    except ValueError as error:
        raise ValueError("public key armor boundary is invalid") from error
    if end < start:
        raise ValueError("public key armor boundary is invalid")
    if any(line.strip() for line in lines[: start - 1] + lines[end + 1 :]):
        raise ValueError("unexpected data outside the public key block")

    body_started = False
    checksum_seen = False
    encoded_lines: list[str] = []
    for line in lines[start:end]:
        if not body_started:
            if line == "":
                body_started = True
            continue
        if line.startswith("="):
            if checksum_seen:
                raise ValueError("public key armor has duplicate checksums")
            checksum_seen = True
            continue
        if checksum_seen and line:
            raise ValueError("public key armor has data after its checksum")
        encoded_lines.append(line)
    if not encoded_lines:
        raise ValueError("public key armor body is empty")

    payload = base64.b64decode("".join(encoded_lines), validate=True)
    fingerprints: list[str] = []
    for tag, packet in openpgp_packets(payload):
        if tag in {5, 7}:
            raise ValueError("public key armor contains a secret key packet")
        if tag != 6:
            continue
        if not packet or packet[0] != 4:
            raise ValueError("only OpenPGP v4 primary keys are supported")
        if len(packet) > 0xFFFF:
            raise ValueError("OpenPGP v4 primary key packet is too large")
        digest_input = b"\x99" + len(packet).to_bytes(2, "big") + packet
        fingerprints.append(hashlib.sha1(digest_input).hexdigest().upper())
    return fingerprints


def armor_payload(payload: bytes) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return (
        "-----BEGIN PGP PUBLIC KEY BLOCK-----\n\n"
        f"{encoded}\n"
        "-----END PGP PUBLIC KEY BLOCK-----\n"
    )


class CreatorWebDeployWorkflowTest(unittest.TestCase):
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

    def job_block(self, source: str, name: str) -> str:
        return self.mapping_block(self.mapping_block(source, "jobs", 0), name, 2)

    def shell_function(self, script: str, name: str) -> str:
        lines = script.splitlines()
        try:
            start = lines.index(f"{name}() {{")
        except ValueError:
            self.fail(f"shell function is missing: {name}")
        for index in range(start + 1, len(lines)):
            if lines[index] == "}":
                return "\n".join(lines[start + 1 : index])
        self.fail(f"shell function is unterminated: {name}")

    def test_deployment_requires_manual_exact_tag(self) -> None:
        source = self.workflow_source()
        triggers = self.mapping_block(source, "on", 0)
        self.assertEqual(self.direct_mapping(triggers, 2), {"workflow_dispatch": ""})
        self.assertNotIn("release.published", source)
        workflow_dispatch = self.mapping_block(triggers, "workflow_dispatch", 2)
        self.assertEqual(
            set(self.direct_mapping(workflow_dispatch, 4)),
            {"inputs"},
        )
        self.assertIn("environment: creator-canary", source)
        self.assertIn("cancel-in-progress: false", source)
        permissions = self.mapping_block(source, "permissions", 0)
        self.assertEqual(self.direct_mapping(permissions, 2), {"contents": "read"})
        self.assertIn("ref: main", source)
        self.assertIn('scripts/cloudflare-host-deploy.sh "$tag"', source)
        self.assertIn("--target creator-web", source)
        self.assertIn("CLOUDFLARE_API_TOKEN", source)
        # The Netlify sites are deleted; the production path must not name them,
        # and must not invoke the retired verb that publishes to one.
        self.assertNotIn("NETLIFY", source)
        self.assertNotIn("netlify.app", source)
        self.assertNotIn("creator-web-deploy.sh deploy", source)

    def test_release_tag_selection_fails_closed(self) -> None:
        source = self.workflow_source()
        self.assertIn("inputs.tag", source)
        self.assertNotIn("github.event.release", source)
        self.assertNotIn("EVENT_NAME", source)
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
                if f"uses: actions/checkout@{checkout_pin} # {checkout_version}" in step
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
        self.assertEqual(set(self.direct_mapping(jobs, 2)), {"preflight", "deploy"})
        deploy_job = self.mapping_block(jobs, "deploy", 2)
        self.assertNotIn("env", self.direct_mapping(deploy_job, 4))

        deploy_step = self.step_named(source, "Deploy signed Creator Web Host release to Cloudflare")
        deploy_environment = self.direct_mapping(
            self.mapping_block(deploy_step, "env", 8),
            10,
        )
        self.assertEqual(
            deploy_environment,
            {
                "GITHUB_TOKEN": "${{ github.token }}",
                "CLOUDFLARE_API_TOKEN": "${{ secrets.CLOUDFLARE_API_TOKEN }}",
                "WRANGLER_SEND_METRICS": '"false"',
                "LMDJ_RELEASE_TAG": "${{ needs.preflight.outputs.tag }}",
                "LMDJ_RELEASE_REQUEST_ID": "${{ inputs.request_id }}",
                "LMDJ_PRIOR_SITE_SHA256": "${{ inputs.prior_site_sha256 }}",
            },
        )

        for step in self.workflow_steps(source):
            if step == deploy_step or "        env:" not in step:
                continue
            name = step.splitlines()[0].removeprefix("      - name: ")
            environment = self.direct_mapping(
                self.mapping_block(step, "env", 8),
                10,
            )
            self.assertTrue(
                DEPLOY_CREDENTIALS.isdisjoint(environment),
                f"Netlify credential leaked to non-deploy step: {name}",
            )
            if name not in GITHUB_TOKEN_STEPS:
                self.assertNotIn(
                    "GITHUB_TOKEN",
                    environment,
                    f"GitHub token leaked to an unrelated step: {name}",
                )

    def test_preflight_verifies_the_release_without_credentials_or_browsers(
        self,
    ) -> None:
        source = self.workflow_source()
        preflight_job = self.job_block(source, "preflight")
        preflight_mapping = self.direct_mapping(preflight_job, 4)
        self.assertNotIn("env", preflight_mapping)
        self.assertNotIn("needs", preflight_mapping)
        self.assertNotIn(
            "environment",
            preflight_mapping,
            "preflight must not join the deployment environment",
        )
        self.assertEqual(
            self.direct_mapping(self.mapping_block(preflight_job, "outputs", 4), 6),
            {"tag": "${{ steps.release-tag.outputs.tag }}"},
        )

        preflight_steps = self.workflow_steps(preflight_job)
        self.assertEqual(
            [step.splitlines()[0].removeprefix("      - name: ") for step in preflight_steps],
            [
                "Checkout protected main tooling",
                "Set up Python",
                "Record dispatch correlation",
                "Upload dispatch correlation",
                "Select exact signed Product tag",
                "Verify signed Creator Web Host release",
            ],
        )
        for step in preflight_steps:
            if "        env:" not in step:
                continue
            environment = self.direct_mapping(self.mapping_block(step, "env", 8), 10)
            self.assertTrue(
                DEPLOY_CREDENTIALS.isdisjoint(environment),
                f"preflight must stay credential-free: {step.splitlines()[0]}",
            )
        for forbidden in ("setup-node", "npm ci", "playwright", "chromium"):
            self.assertNotIn(
                forbidden,
                preflight_job,
                f"preflight must not install the browser toolchain: {forbidden}",
            )

        verify_step = self.step_named(preflight_job, "Verify signed Creator Web Host release")
        self.assertIn('scripts/creator-web-deploy.sh verify "$tag"', verify_step)
        self.assertIn("timeout --signal=TERM --kill-after=30s 300s", verify_step)
        self.assertEqual(
            self.direct_mapping(self.mapping_block(verify_step, "env", 8), 10),
            {
                "GITHUB_TOKEN": "${{ github.token }}",
                "LMDJ_RELEASE_TAG": "${{ steps.release-tag.outputs.tag }}",
            },
        )

        deploy_job = self.job_block(source, "deploy")
        self.assertEqual(self.direct_mapping(deploy_job, 4).get("needs"), "preflight")
        self.assertNotIn(
            "Select exact signed Product tag",
            deploy_job,
            "tag selection belongs to preflight only",
        )

        self.assertIn(
            'verify_release "$tag"',
            self.shell_function(DEPLOY_SCRIPT.read_text(encoding="utf-8"), "deploy_release"),
            "the deploy job must re-verify the same Release before mutating Netlify",
        )

    def test_workflow_installs_only_deployment_dependencies(self) -> None:
        source = self.workflow_source()
        self.assertIn("python-version: \"3.11\"", source)
        self.assertIn("node-version: \"26\"", source)
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
            "CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}",
            source,
        )
        self.assertIn(
            'WRANGLER_SEND_METRICS: "false"',
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
        self.assertIn("name: creator-host-deployment-evidence", source)
        self.assertIn("build/deploy/creator-web/evidence.json", source)
        # The Cloudflare path records recovery in the adapter's run store, not
        # as a second artifact member.
        self.assertNotIn("recovery-evidence.json", source)
        self.assertIn("build/deploy/creator-web/deployment.log", source)
        self.assertIn(
            "${{ runner.temp }}/host-state-${{ github.run_id }}/diagnostics",
            source,
        )
        self.assertIn("if-no-files-found: warn", source)

    def test_internal_timeout_leaves_bounded_recovery_and_upload_budget(self) -> None:
        source = self.workflow_source()
        deploy_step = self.step_named(source, "Deploy signed Creator Web Host release to Cloudflare")
        self.assertIn(
            "timeout --signal=TERM --kill-after=900s 1080s", deploy_step
        )
        self.assertIn("timeout-minutes: 80", source)

        preflight_budgets = {
            "Record dispatch correlation": 1,
            "Upload dispatch correlation": 1,
            "Checkout protected main tooling": 5,
            "Set up Python": 3,
            "Select exact signed Product tag": 2,
            "Verify signed Creator Web Host release": 7,
        }
        step_budgets = {
            "Checkout protected main tooling": 5,
            "Set up Python": 3,
            "Set up the pinned upload Node": 3,
            "Record the pinned upload Node": 1,
            "Set up Node": 3,
            "Verify the recorded upload Node survived": 1,
            "Install the pinned deploy CLI without deployment credentials": 5,
            "Install browser smoke dependencies": 5,
            "Install Chromium": 10,
            "Deploy signed Creator Web Host release to Cloudflare": 35,
            "Upload deployment evidence and failure logs": 5,
        }
        for job, budgets in (
            ("preflight", preflight_budgets),
            ("deploy", step_budgets),
        ):
            job_source = self.job_block(source, job)
            for name, minutes in budgets.items():
                with self.subTest(job=job, step=name):
                    step = self.step_named(job_source, name)
                    self.assertIn(f"timeout-minutes: {minutes}", step)

        preflight_job_budget = 20
        self.assertIn(f"timeout-minutes: {preflight_job_budget}", self.job_block(source, "preflight"))
        self.assertLessEqual(
            sum(preflight_budgets.values()) * 60 + 60,
            preflight_job_budget * 60,
        )
        verify_step = self.step_named(
            self.job_block(source, "preflight"), "Verify signed Creator Web Host release"
        )
        self.assertIn("kill-after=30s 300s", verify_step)
        self.assertLessEqual(
            300 + 30,
            preflight_budgets["Verify signed Creator Web Host release"] * 60,
        )

        script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
        recovery_api = 30
        recovery_http = 180
        recovery_browser = 180
        recovery_evidence = 30
        for name, seconds in (
            ("recovery_api_timeout_seconds", recovery_api),
            ("recovery_http_timeout_seconds", recovery_http),
            ("recovery_browser_timeout_seconds", recovery_browser),
            ("recovery_evidence_timeout_seconds", recovery_evidence),
        ):
            self.assertIn(f"{name}={seconds}", script)
        recovery_worst = (
            3 * recovery_api
            + 2 * recovery_http
            + 2 * recovery_browser
            + recovery_evidence
        )
        recovery_kill_budget = 900
        main_budget = 1080
        deploy_step_budget = step_budgets["Deploy signed Creator Web Host release to Cloudflare"] * 60
        setup_budget = sum(
            minutes
            for name, minutes in step_budgets.items()
            if name not in {
                "Deploy signed Creator Web Host release to Cloudflare",
                "Upload deployment evidence and failure logs",
            }
        ) * 60
        upload_budget = step_budgets["Upload deployment evidence and failure logs"] * 60
        job_budget = 80 * 60
        self.assertLessEqual(recovery_worst + 60, recovery_kill_budget)
        self.assertLessEqual(main_budget + recovery_kill_budget, deploy_step_budget)
        self.assertLessEqual(
            setup_budget + deploy_step_budget + upload_budget + 60,
            job_budget,
        )
        upload = self.step_named(source, "Upload deployment evidence and failure logs")
        self.assertIn("if: always()", upload)

    def test_role_public_keys_have_exactly_one_distinct_trusted_primary(self) -> None:
        expected = (
            (PRODUCT_PUBLIC_KEY, TRUSTED_TAG_FINGERPRINT),
            (CHECKSUM_PUBLIC_KEY, TRUSTED_CHECKSUM_FINGERPRINT),
        )
        self.assertNotEqual(TRUSTED_TAG_FINGERPRINT, TRUSTED_CHECKSUM_FINGERPRINT)
        for public_key_path, fingerprint in expected:
            with self.subTest(public_key_path=public_key_path):
                self.assertTrue(public_key_path.is_file(), "signing public key is missing")
                public_key = public_key_path.read_text(encoding="utf-8")
                self.assertEqual(primary_fingerprints(public_key), [fingerprint])
                self.assertIn("BEGIN PGP PUBLIC KEY BLOCK", public_key)
                self.assertNotIn("PRIVATE KEY", public_key)

    def test_public_key_parser_rejects_a_second_armored_key_block(self) -> None:
        public_key = PRODUCT_PUBLIC_KEY.read_text(encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exactly one public key block"):
            primary_fingerprints(public_key + public_key)

    def test_public_key_parser_rejects_secret_key_packets(self) -> None:
        secret_key_packet = bytes([0x94, 0x01, 0x04])
        with self.assertRaisesRegex(ValueError, "secret key packet"):
            primary_fingerprints(armor_payload(secret_key_packet))

    def test_public_key_parser_rejects_truncated_packet_lengths(self) -> None:
        with self.assertRaisesRegex(ValueError, "truncated OpenPGP packet"):
            list(openpgp_packets(bytes([0xC6])))


class CreatorWebDeployOperatorEnvironmentTest(unittest.TestCase):
    """The secret-stripping helper must survive an operator environment."""

    BARE_ENVIRONMENT = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": "/tmp"}
    SOCKET_BUDGET = 104

    @classmethod
    def _shell_fragment(cls) -> str:
        # The script dispatches on its arguments at the end of the file and
        # exits 64 for unknown usage, so it cannot be sourced. Lift exactly the
        # helpers under test out of its text instead of changing the script to
        # be sourceable.
        source = DEPLOY_SCRIPT.read_text(encoding="utf-8").splitlines()
        wanted = (
            "with_gh_environment_removed",
            "without_deploy_secrets",
            "owned_temp_parent_fits_gnupg_socket",
        )
        fragment: list[str] = []
        for line in source:
            if line.startswith("_GNUPG_SOCKET_BUDGET="):
                fragment.append(line)
        for name in wanted:
            starts = [
                index for index, line in enumerate(source)
                if line.startswith(name + "()")
            ]
            if not starts:
                # A helper this fragment does not find is reported by the test
                # that needs it, so the other tests still exercise real bash
                # behaviour instead of failing on extraction.
                continue
            start = starts[0]
            end = next(
                index for index in range(start, len(source)) if source[index] == "}"
            )
            fragment.extend(source[start:end + 1])
        return "\n".join(fragment)

    def _run(self, body: str, environment: dict, *arguments: str):
        program = "set -euo pipefail\n" + self._shell_fragment() + "\n" + body
        return subprocess.run(
            ["bash", "-c", program, "helper", *arguments],
            capture_output=True, text=True, env=environment,
            cwd=str(REPO_ROOT), check=False,
        )

    def test_helper_survives_an_environment_with_no_gh_variables(self) -> None:
        # bash 3.2 expands an empty array's "${a[@]}" to an unbound variable
        # error under set -u, and an `&&` append whose test fails aborts under
        # set -e. GitHub runners always export GITHUB_* names, which match GH*,
        # so only operator machines reach the empty case.
        self.assertFalse([n for n in self.BARE_ENVIRONMENT if n.startswith("GH")])
        completed = self._run("without_deploy_secrets printf ok\n", self.BARE_ENVIRONMENT)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "ok")

    def test_helper_still_strips_gh_variables_when_present(self) -> None:
        environment = dict(self.BARE_ENVIRONMENT)
        environment.update({"GH_TOKEN": "must-not-survive", "GITHUB_ACTIONS": "true"})
        body = "without_deploy_secrets sh -c 'printf \"[%s]\" \"${GH_TOKEN:-absent}\"'\n"
        completed = self._run(body, environment)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "[absent]")

    def test_owned_temp_parent_must_fit_the_gnupg_agent_socket(self) -> None:
        # A GnuPG home holds the agent socket, whose absolute path must fit the
        # platform sun_path limit. A long macOS per-user TMPDIR overflows it by
        # a single character and gpg then exits non-zero on an otherwise
        # successful public-key import.
        self.assertIn(
            "owned_temp_parent_fits_gnupg_socket", DEPLOY_SCRIPT.read_text(encoding="utf-8"),
            "the deploy script must bound its GnuPG home path",
        )
        long_parent = "/private/var/folders/kf/0jqm4t_j2v16b7ms9st4ph980000gn/T"
        projected = long_parent + "/lmdj-creator-web-deploy.XXXXXX/gnupg/S.gpg-agent"
        self.assertGreater(len(projected), self.SOCKET_BUDGET)
        body = (
            'if owned_temp_parent_fits_gnupg_socket "$1"; then printf fits;'
            " else printf overflows; fi\n"
        )
        overflowing = self._run(body, self.BARE_ENVIRONMENT, long_parent)
        self.assertEqual(overflowing.returncode, 0, overflowing.stderr)
        self.assertEqual(overflowing.stdout, "overflows")
        fitting = self._run(body, self.BARE_ENVIRONMENT, "/tmp")
        self.assertEqual(fitting.returncode, 0, fitting.stderr)
        self.assertEqual(fitting.stdout, "fits")


if __name__ == "__main__":
    unittest.main()
