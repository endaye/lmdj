#!/usr/bin/env python3
"""Contract tests: every Web proof owns the server its browsers drive.

Two runner services share the `ci-web-heavy` host. A Playwright-managed
`webServer` must know its URL before the server exists, so it can only bind a
fixed port: concurrent lanes contend for it, and a server leaked by a crashed
lane keeps holding it and fails every later lane at startup (issue #297). The
proofs therefore start their own server on a kernel-assigned ephemeral port
and pass its base URL in, and the Playwright config has no managed server and
no default base URL to fall back to.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYWRIGHT_CONFIG = REPO_ROOT / "tests/platform/web/playwright.config.mjs"
PLAYWRIGHT_INVOCATION = re.compile(
    r'npm --prefix "\$(?:web_test_root|repo_root/tests/platform/web)" test'
)
EXTERNAL_SERVER = re.compile(r"LMDJ_(?:WEB_HOST|CREATOR_WEB)_EXTERNAL_SERVER=1")
# Every script that drives the shared Playwright project, mapped to the
# environment variable naming the server it owns and, where the invocation is
# not a direct command, the shell function that owns both.
PROOF_SCRIPTS = {
    "scripts/web-toolchain-conformance.sh": ("LMDJ_WEB_HOST_BASE_URL", None),
    "scripts/web-runtime-host.sh": ("LMDJ_WEB_HOST_BASE_URL", None),
    "scripts/creator-web.sh": ("LMDJ_CREATOR_WEB_BASE_URL", None),
    # The deployment smoke builds its invocation into an array and runs it
    # expanded, so ownership is asserted over the function that does both.
    "scripts/web-runtime-deploy.sh": ("LMDJ_WEB_HOST_BASE_URL", "run_browser_smoke"),
}


def playwright_commands(text: str) -> list[str]:
    """Return each direct Playwright invocation with its leading environment."""
    commands: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not PLAYWRIGHT_INVOCATION.search(line):
            continue
        start = index
        while start > 0 and lines[start - 1].rstrip().endswith("\\"):
            start -= 1
        commands.append("\n".join(lines[start : index + 1]))
    return commands


def shell_function(text: str, name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{\n(.*?)^\}}$", text, re.DOTALL | re.MULTILINE)
    if match is None:
        raise AssertionError(f"shell function {name}() is missing")
    return match.group(1)


class PlaywrightConfigOwnsNoServer(unittest.TestCase):
    def setUp(self) -> None:
        self.source = "\n".join(
            line
            for line in PLAYWRIGHT_CONFIG.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("//")
        )

    def test_declares_no_managed_web_server(self) -> None:
        for forbidden in ("webServer", "reuseExistingServer"):
            self.assertNotIn(
                forbidden,
                self.source,
                f"{forbidden} reintroduces a fixed-port server shared by both "
                "runner services on the Web host",
            )

    def test_declares_no_fixed_loopback_port(self) -> None:
        self.assertNotRegex(
            self.source,
            r"127\.0\.0\.1:\d|\b41\d{2}\b",
            "the Playwright config must not name a port; the lane's own "
            "server publishes the ephemeral port it was given",
        )

    def test_fails_closed_without_an_owned_base_url(self) -> None:
        self.assertRegex(
            self.source,
            r"if \(!browserProofBaseURL\) \{\s*throw new Error\(",
            "a run with no owned base URL must fail closed instead of "
            "proving itself against whatever already listens",
        )


class ProofScriptsOwnTheirServer(unittest.TestCase):
    def test_toolchain_proof_binds_an_ephemeral_port(self) -> None:
        text = (REPO_ROOT / "scripts/web-toolchain-conformance.sh").read_text(
            encoding="utf-8"
        )
        self.assertRegex(
            text,
            r'server\.py" \\\n\s+--root "\$toolchain_root" \\\n'
            r"\s+--port 0 \\\n\s+--write-port",
            "the Proof server must take a kernel-assigned port and publish it",
        )
        self.assertIn(
            'service": "web-toolchain-conformance"',
            text,
            "the Proof must confirm the port it read serves this service",
        )

    def test_every_playwright_invocation_receives_an_owned_base_url(self) -> None:
        for relative, (base_url, function) in PROOF_SCRIPTS.items():
            text = (REPO_ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(script=relative):
                self.assertRegex(
                    text,
                    PLAYWRIGHT_INVOCATION,
                    "the script no longer drives Playwright; drop it from "
                    "PROOF_SCRIPTS instead of leaving it unchecked",
                )
                scopes = (
                    playwright_commands(text)
                    if function is None
                    else [shell_function(text, function)]
                )
                self.assertTrue(scopes, "no Playwright invocation was located")
                for scope in scopes:
                    self.assertIn(
                        f"{base_url}=",
                        scope,
                        f"{relative} runs Playwright without naming the "
                        "server it owns",
                    )
                    self.assertRegex(
                        scope,
                        EXTERNAL_SERVER,
                        f"{relative} runs Playwright without declaring the "
                        "server external, so Playwright would manage one",
                    )


if __name__ == "__main__":
    unittest.main()
