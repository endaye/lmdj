#!/usr/bin/env python3
"""Contract tests for the original default asset Worker deployment.

`deploy-default-assets.yml` hands the Cloudflare deploy token to Wrangler. It
used to call Wrangler inline, with no metrics opt-out and no step budgets.
These tests pin it to the deploy-workflow standard the Web Host deployments
follow: one locked Wrangler, SHA-pinned actions, no persisted checkout
credentials, its protected Environment, metrics off, a budget on every step,
and `scripts/asset-server.sh deploy` as the only deploy entry point.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/deploy-default-assets.yml"
SCRIPT = ROOT / "scripts/asset-server.sh"
ENVIRONMENT = "creator-canary"
WRANGLER_PREFIX = "$RUNNER_TEMP/default-assets-wrangler"
EXPECTED_ACTION_PINS = {
    "actions/checkout": ("de0fac2e4500dabe0009e67214ff5f5447ce83dd", "v6.0.2"),
    "actions/setup-python": ("a309ff8b426b58ec0e2a45f0f869d46889d02405", "v6.2.0"),
    "actions/setup-node": ("249970729cb0ef3589644e2896645e5dc5ba9c38", "v6.5.0"),
    "actions/upload-artifact": ("b7c566a772e6b6bfb58ed0dc250532a479d7789f", "v6.0.0"),
}
DEPLOY_STEP = "Deploy independent asset Worker"


def directives(source: str) -> str:
    """Comments may explain retired forms; only directives are policed."""
    return "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))


def steps(source: str) -> dict[str, str]:
    """Map each step name to its whole block."""
    blocks = re.split(r"(?m)^      - ", source.split("\n    steps:\n", 1)[1])[1:]
    named = {}
    for item in blocks:
        name = re.search(r"(?m)^(?:        )?name: (.+)$", item)
        named[name.group(1).strip() if name else item.splitlines()[0]] = item
    return named


class DefaultAssetsDeployWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = directives(WORKFLOW.read_text(encoding="utf-8"))
        self.steps = steps(self.source)

    def test_job_runs_in_its_protected_environment(self) -> None:
        self.assertRegex(self.source, rf"(?m)^    environment: {re.escape(ENVIRONMENT)}$",
                         "why: the deploy token is scoped to a protected Environment; remedy: keep "
                         f"environment: {ENVIRONMENT} on the deploy job")

    def test_wrangler_is_installed_once_from_the_locked_manifest(self) -> None:
        install = self.steps["Install pinned Wrangler"]
        self.assertIn(f'cp tools/wrangler/package.json tools/wrangler/package-lock.json "{WRANGLER_PREFIX}/"',
                      install)
        self.assertIn(f'npm ci --prefix "{WRANGLER_PREFIX}" --ignore-scripts --no-audit --no-fund', install,
                      "why: Wrangler receives the deploy token and must come from the lockfile without install "
                      "scripts; remedy: npm ci --ignore-scripts from tools/wrangler")
        self.assertNotRegex(self.source, r"npm (?:install|i|add)\b|npx\b",
                            "why: an unlocked install resolves dependencies at run time; remedy: use the locked "
                            "npm ci install")

    def test_deploy_runs_the_locked_wrangler_through_the_asset_server_script(self) -> None:
        deploy = self.steps[DEPLOY_STEP]
        self.assertRegex(deploy, r"(?m)^ +scripts/asset-server\.sh deploy 2>&1 \| tee build/default-assets/"
                                 r"deployment\.log$",
                         "why: the script runs the corpus check and owns the Wrangler invocation; remedy: deploy "
                         "through scripts/asset-server.sh deploy")
        self.assertIn("LMDJ_WRANGLER: ${{ runner.temp }}/default-assets-wrangler/node_modules/wrangler/bin/"
                      "wrangler.js", deploy,
                      "why: the script must run the Wrangler installed from the lock; remedy: point LMDJ_WRANGLER "
                      "at the npm ci prefix")
        run_lines = [line for item in self.steps.values() for line in item.splitlines()
                     if "wrangler.js" in line and "LMDJ_WRANGLER:" not in line]
        self.assertEqual(run_lines, [], "why: an inline Wrangler call bypasses the deploy entry point; remedy: "
                                        "invoke Wrangler only through scripts/asset-server.sh deploy")

    def test_script_deploy_only_runs_the_supplied_wrangler(self) -> None:
        script = directives(SCRIPT.read_text(encoding="utf-8"))
        deploy = re.search(r"(?ms)^  deploy\)\n(.*?)^    ;;$", script)
        self.assertIsNotNone(deploy, "scripts/asset-server.sh has no deploy command")
        body = deploy.group(1)
        self.assertIn('"$LMDJ_WRANGLER" deploy --config "$repo_root/tools/asset-server/wrangler.json"', body)
        self.assertNotRegex(body, r"\bnpm\b|\bnpx\b|wrangler@",
                            "why: the deploy command must not install its own unlocked Wrangler; remedy: run the "
                            "executable the caller installed from tools/wrangler")

    def test_wrangler_metrics_are_disabled_beside_the_token(self) -> None:
        self.assertIn("WRANGLER_SEND_METRICS: 'false'", self.steps[DEPLOY_STEP],
                      "why: Wrangler otherwise sends telemetry from the deploy runner; remedy: set "
                      "WRANGLER_SEND_METRICS: 'false' on the deploy step")

    def test_deploy_token_reaches_only_the_deploy_step(self) -> None:
        holders = [name for name, item in self.steps.items() if "secrets.CLOUDFLARE_API_TOKEN" in item]
        self.assertEqual(holders, [DEPLOY_STEP])

    def test_actions_use_the_verified_sha_pins(self) -> None:
        uses = re.findall(r"(?m)^\s*(?:- )?uses: (.+)$", self.source)
        self.assertEqual({value.split("@")[0] for value in uses}, set(EXPECTED_ACTION_PINS))
        for value in uses:
            with self.subTest(uses=value):
                match = re.fullmatch(r"([\w.-]+/[\w.-]+)@([0-9a-f]{40}) # (v\d+\.\d+\.\d+)", value.strip())
                self.assertIsNotNone(match, f"why: {value} is not a full SHA pin; remedy: pin <sha> # <tag>")
                self.assertEqual(EXPECTED_ACTION_PINS[match.group(1)], match.group(2, 3))

    def test_checkout_does_not_persist_credentials(self) -> None:
        checkout = self.steps["Checkout exact protected integration revision"]
        self.assertRegex(checkout, r"(?m)^ +persist-credentials: false$",
                         "why: a persisted job token sits in .git/config beside the deploy token; remedy: set "
                         "persist-credentials: false")

    def test_job_and_every_step_have_a_budget(self) -> None:
        self.assertRegex(self.source, r"(?m)^    timeout-minutes: 20$")
        self.assertEqual(len(self.steps), 8, "the step scan no longer sees every deploy step")
        for name, item in self.steps.items():
            with self.subTest(step=name):
                budget = re.search(r"(?m)^        timeout-minutes: (\d+)$", item)
                self.assertIsNotNone(budget, "why: a hung step holds the deploy token until the job limit; "
                                             "remedy: give every step its own timeout-minutes")
                self.assertLessEqual(int(budget.group(1)), 5)


if __name__ == "__main__":
    unittest.main()
