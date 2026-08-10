#!/usr/bin/env python3
"""Contract tests for signed Web Runtime Host release deployment."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/deploy-web-runtime-host.yml"
DEPLOY_SCRIPT = REPO_ROOT / "scripts/web-runtime-deploy.sh"
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
        "ea165f8d65b6e75b540449e92b4886f43607fa02",
        "v4.6.2",
    ),
}
CREDENTIAL_ENVIRONMENT = {
    "GITHUB_TOKEN",
    "NETLIFY_RUNTIME_SITE_ID",
    "NETLIFY_AUTH_TOKEN",
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
        self.assertIn("build/deploy/web-runtime-host/recovery-evidence.json", source)
        self.assertIn("build/deploy/web-runtime-host/deployment.log", source)
        self.assertIn("if-no-files-found: warn", source)

    def test_internal_timeout_leaves_bounded_recovery_and_upload_budget(self) -> None:
        source = self.workflow_source()
        deploy_step = self.step_named(source, "Deploy signed Runtime Host release")
        self.assertIn(
            "timeout --signal=TERM --kill-after=900s 1080s", deploy_step
        )
        self.assertIn("timeout-minutes: 75", source)

        step_budgets = {
            "Checkout protected main tooling": 5,
            "Set up Python": 3,
            "Set up Node": 3,
            "Install browser smoke dependencies": 5,
            "Install Chromium": 10,
            "Select exact signed Product tag": 2,
            "Deploy signed Runtime Host release": 35,
            "Upload deployment evidence and failure logs": 5,
        }
        for name, minutes in step_budgets.items():
            with self.subTest(step=name):
                step = self.step_named(source, name)
                self.assertIn(f"timeout-minutes: {minutes}", step)

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
        deploy_step_budget = step_budgets["Deploy signed Runtime Host release"] * 60
        setup_and_select = sum(
            minutes
            for name, minutes in step_budgets.items()
            if name not in {
                "Deploy signed Runtime Host release",
                "Upload deployment evidence and failure logs",
            }
        ) * 60
        upload_budget = step_budgets["Upload deployment evidence and failure logs"] * 60
        job_budget = 75 * 60
        self.assertLessEqual(recovery_worst + 60, recovery_kill_budget)
        self.assertLessEqual(main_budget + recovery_kill_budget, deploy_step_budget)
        self.assertLessEqual(
            setup_and_select + deploy_step_budget + upload_budget + 60,
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


if __name__ == "__main__":
    unittest.main()
