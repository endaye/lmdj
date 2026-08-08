#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
COMMAND = REPO_ROOT / "scripts/web-runtime-deploy.sh"
DEPLOY_ROOT = REPO_ROOT / "build/deploy/web-runtime-host"
TAG = "lmdj-v1.0.15.2"
TAG_TARGET = "72ae40074620cc5681c462ba04a31a666449734f"
HOST_DIGEST = "d56a7c99a3c489db068b93fcef70a254b498adf4bc65919253beccb199f3ad5a"
ARCHIVE = "lmdj-web-runtime-host-1.1.2-product-1.0.15.2.zip"
CHECKSUM = ARCHIVE + ".sha256"
TRUSTED_FINGERPRINT = "2B5EE362F058800036AD4FB5116ECE156F954D29"


class DeployCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-deploy-command-test-")
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.runner_temp = self.root / "runner-temp"
        self.bin.mkdir()
        self.runner_temp.mkdir()
        self.log_path = self.root / "commands.log"
        self.details_path = self.root / "details.jsonl"
        shutil.rmtree(DEPLOY_ROOT, ignore_errors=True)
        self.write_fake_commands()

    def tearDown(self) -> None:
        shutil.rmtree(DEPLOY_ROOT, ignore_errors=True)
        self.temporary.cleanup()

    def write_executable(self, name: str, source: str) -> None:
        path = self.bin / name
        path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")
        path.chmod(0o755)

    def write_fake_commands(self) -> None:
        self.write_executable(
            "gpg",
            f"""
            #!/bin/sh
            set -eu
            case " $* " in
              *" --show-keys "*)
                printf 'pub:-:4096:1:116ECE156F954D29:0:0::::::\nfpr:::::::::{TRUSTED_FINGERPRINT}:\n'
                ;;
              *" --import "*) exit 0 ;;
              *) exit 2 ;;
            esac
            """,
        )
        self.write_executable(
            "git",
            f"""
            #!{sys.executable}
            import json
            import os
            from pathlib import Path
            import shutil
            import sys

            args = sys.argv[1:]
            log = Path(os.environ["COMMAND_LOG"])
            target = os.environ.get("FAKE_TAG_TARGET", {TAG_TARGET!r})
            if args[:2] == ["cat-file", "-t"]:
                print(os.environ.get("FAKE_TAG_TYPE", "tag"))
            elif args[:2] == ["verify-tag", "--raw"]:
                with log.open("a", encoding="utf-8") as output:
                    output.write(f"git tag verify {{args[2]}}\\n")
                if os.environ.get("FAIL_TAG_VERIFY") == "1":
                    print("tag signature verification failed", file=sys.stderr)
                    raise SystemExit(1)
                fingerprint = os.environ.get(
                    "FAKE_SIGNATURE_FINGERPRINT", {TRUSTED_FINGERPRINT!r}
                )
                print(
                    f"[GNUPG:] VALIDSIG {{fingerprint}} 2026-08-07 0 4 0 1 10 00 {{fingerprint}}",
                    file=sys.stderr,
                )
            elif args[:2] == ["rev-parse", "--verify"]:
                print(target)
            elif args[:3] == ["worktree", "add", "--detach"]:
                checkout = Path(args[3])
                checkout.joinpath("products/lmdj").mkdir(parents=True)
                checkout.joinpath("apps/web-runtime-host/tools").mkdir(parents=True)
                checkout.joinpath("products/lmdj/version.json").write_text(
                    json.dumps({{
                        "contract": "lmdj.product-version.v1",
                        "product": "lmdj",
                        "milestone": 1,
                        "minor": 0,
                        "build": 15,
                        "patch": 2,
                    }}),
                    encoding="utf-8",
                )
                checkout.joinpath("apps/web-runtime-host/module.json").write_text(
                    json.dumps({{
                        "contract": "lmdj.module.v1",
                        "module": "web-runtime-host",
                        "version": "1.1.2",
                        "api_version": 1,
                        "dependencies": {{}},
                    }}),
                    encoding="utf-8",
                )
                checkout.joinpath("apps/web-runtime-host/tools/package.py").write_text(
                    "def verify_distribution(*args): pass\\n", encoding="utf-8"
                )
                Path(os.environ["WORKTREE_PATH"]).write_text(str(checkout), encoding="utf-8")
            elif args[:3] == ["worktree", "remove", "--force"]:
                checkout = Path(args[3])
                shutil.rmtree(checkout, ignore_errors=True)
                Path(os.environ["WORKTREE_REMOVED"]).write_text(str(checkout), encoding="utf-8")
            else:
                print(f"unexpected fake git arguments: {{args!r}}", file=sys.stderr)
                raise SystemExit(97)
            """,
        )
        self.write_executable(
            "gh",
            f"""
            #!{sys.executable}
            import json
            import os
            from pathlib import Path
            import sys

            args = sys.argv[1:]
            log = Path(os.environ["COMMAND_LOG"])
            if args[:2] == ["release", "view"]:
                tag = args[2]
                with log.open("a", encoding="utf-8") as output:
                    output.write(f"gh release view {{tag}}\\n")
                archive = os.environ.get("FAKE_ARCHIVE_NAME", {ARCHIVE!r})
                checksum = os.environ.get("FAKE_CHECKSUM_NAME", archive + ".sha256")
                assets = [{{"name": archive}}, {{"name": checksum}}]
                if os.environ.get("FAKE_DUPLICATE_ARCHIVE") == "1":
                    assets.append({{"name": archive}})
                print(json.dumps({{
                    "tagName": os.environ.get("FAKE_RELEASE_TAG", tag),
                    "isDraft": os.environ.get("FAKE_RELEASE_DRAFT") == "1",
                    "isPrerelease": os.environ.get("FAKE_RELEASE_PRERELEASE", "1") == "1",
                    "targetCommitish": os.environ.get("FAKE_RELEASE_TARGET", {TAG_TARGET!r}),
                    "assets": assets,
                    "url": os.environ.get(
                        "FAKE_RELEASE_URL",
                        f"https://github.com/endaye/lmdj/releases/tag/{{tag}}",
                    ),
                }}, sort_keys=True))
            elif args[:2] == ["release", "download"]:
                tag = args[2]
                with log.open("a", encoding="utf-8") as output:
                    output.write(f"gh release download {{tag}}\\n")
                destination = Path(args[args.index("--dir") + 1])
                patterns = [args[index + 1] for index, value in enumerate(args) if value == "--pattern"]
                destination.mkdir(parents=True, exist_ok=True)
                for name in patterns:
                    destination.joinpath(name).write_text("fake release asset", encoding="utf-8")
            else:
                print(f"unexpected fake gh arguments: {{args!r}}", file=sys.stderr)
                raise SystemExit(97)
            """,
        )
        self.write_executable(
            "python3",
            f"""
            #!{sys.executable}
            import json
            import os
            from pathlib import Path
            import sys

            args = sys.argv[1:]
            log = Path(os.environ["COMMAND_LOG"])
            details = Path(os.environ["DETAILS_LOG"])

            def append_log(value):
                with log.open("a", encoding="utf-8") as output:
                    output.write(value + "\\n")

            def append_details(value):
                with details.open("a", encoding="utf-8") as output:
                    output.write(json.dumps(value, sort_keys=True) + "\\n")

            if args and args[0].endswith("release_bundle.py"):
                append_log("release_bundle stage")
                output_root = Path(args[args.index("--output-root") + 1])
                repo_root = args[args.index("--repo-root") + 1]
                output_root.joinpath("dist/assets").mkdir(parents=True)
                output_root.joinpath("dist/index.html").write_text("index", encoding="utf-8")
                output_root.joinpath("dist/assets/runtime.js").write_text("runtime", encoding="utf-8")
                append_details({{"release_bundle_repo_root": repo_root}})
                print(json.dumps({{
                    "archive_sha256": os.environ.get("FAKE_ARCHIVE_DIGEST", {HOST_DIGEST!r}),
                    "dist_root": str(output_root / "dist"),
                    "host_version": "1.1.2",
                    "product_build": "1.0.15.2",
                }}, sort_keys=True, separators=(",", ":")))
            elif args[:2] == ["-", "netlify-create-draft"]:
                sys.stdin.read()
                append_log("netlify create-draft")
                dist_root = Path(args[2])
                headers = Path(args[3])
                if dist_root.joinpath("_headers").exists() or not headers.is_file():
                    print("deploy control mutated the staged distribution", file=sys.stderr)
                    raise SystemExit(2)
                append_details({{
                    "deploy_files": sorted(
                        "/" + path.relative_to(dist_root).as_posix()
                        for path in dist_root.rglob("*") if path.is_file()
                    ) + ["/_headers"]
                }})
                print(json.dumps({{
                    "id": os.environ.get("FAKE_DEPLOY_ID", "deploy-456"),
                    "site_id": os.environ["NETLIFY_RUNTIME_SITE_ID"],
                    "deploy_ssl_url": os.environ.get(
                        "FAKE_DEPLOY_URL", "https://deploy-456--lmdj-runtime.netlify.app"
                    ),
                    "state": "ready",
                }}, sort_keys=True, separators=(",", ":")))
            elif args[:2] == ["-", "netlify-publish"]:
                sys.stdin.read()
                append_log("netlify publish same-id")
                print(json.dumps({{
                    "id": os.environ.get("FAKE_PUBLISHED_ID", args[3]),
                    "site_id": os.environ.get("FAKE_PUBLISHED_SITE_ID", args[2]),
                    "ssl_url": os.environ.get(
                        "FAKE_PRODUCTION_URL", "https://lmdj-runtime.netlify.app"
                    ),
                    "state": os.environ.get("FAKE_PUBLISHED_STATE", "ready"),
                }}, sort_keys=True, separators=(",", ":")))
            elif args and args[0].endswith("deployment_smoke.py"):
                base_url = args[1]
                immutable = "--expected-deploy-id" in args
                label = "immutable" if immutable else "production"
                append_log(f"http-smoke {{label}}")
                failure = "FAIL_IMMUTABLE_SMOKE" if immutable else "FAIL_PRODUCTION_SMOKE"
                if os.environ.get(failure) == "1":
                    print(f"forced {{label}} smoke failure", file=sys.stderr)
                    raise SystemExit(2)
                print(json.dumps({{
                    "asset_count": 2,
                    "host_version": args[3],
                    "product_build": args[2],
                    **({{"deploy_id": args[-1]}} if immutable else {{}}),
                }}, sort_keys=True, separators=(",", ":")))
            else:
                os.execv(os.environ["REAL_PYTHON"], [os.environ["REAL_PYTHON"], *args])
            """,
        )
        self.write_executable(
            "npm",
            f"""
            #!{sys.executable}
            import os
            from pathlib import Path
            import sys

            base_url = os.environ.get("LMDJ_WEB_HOST_BASE_URL", "")
            immutable = base_url != "https://lmdj-runtime.netlify.app"
            label = "immutable" if immutable else "production"
            with Path(os.environ["COMMAND_LOG"]).open("a", encoding="utf-8") as output:
                output.write(f"playwright {{label}}\\n")
            failure = "FAIL_IMMUTABLE_PLAYWRIGHT" if immutable else "FAIL_PRODUCTION_PLAYWRIGHT"
            if os.environ.get(failure) == "1":
                print(f"forced {{label}} Playwright failure", file=sys.stderr)
                raise SystemExit(2)
            """,
        )

    def environment(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.bin}{os.pathsep}{environment['PATH']}",
                "REAL_PYTHON": sys.executable,
                "COMMAND_LOG": str(self.log_path),
                "DETAILS_LOG": str(self.details_path),
                "WORKTREE_PATH": str(self.root / "worktree-path"),
                "WORKTREE_REMOVED": str(self.root / "worktree-removed"),
                "RUNNER_TEMP": str(self.runner_temp),
                "GITHUB_TOKEN": "github-secret-value-should-never-leak",
                "NETLIFY_RUNTIME_SITE_ID": "site-123",
                "NETLIFY_AUTH_TOKEN": "netlify-secret-value-should-never-leak",
            }
        )
        if extra:
            environment.update(extra)
        return environment

    def run_command(
        self, *arguments: str, environment: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(COMMAND), *arguments],
            cwd=REPO_ROOT,
            env=self.environment(environment),
            check=False,
            capture_output=True,
            text=True,
        )

    def command_log(self) -> list[str]:
        if not self.log_path.exists():
            return []
        return self.log_path.read_text(encoding="utf-8").splitlines()

    def details(self) -> list[dict[str, object]]:
        if not self.details_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.details_path.read_text(encoding="utf-8").splitlines()
        ]

    def assert_no_owned_temp(self) -> None:
        self.assertEqual(list(self.runner_temp.glob("lmdj-web-runtime-deploy.*")), [])

    def test_usage_is_exact(self) -> None:
        completed = self.run_command()
        self.assertEqual(completed.returncode, 64)
        self.assertEqual(
            completed.stderr,
            "usage:\n"
            "  scripts/web-runtime-deploy.sh verify TAG\n"
            "  scripts/web-runtime-deploy.sh deploy TAG\n"
            "  scripts/web-runtime-deploy.sh smoke BASE_URL PRODUCT_BUILD HOST_VERSION\n",
        )

    def test_deploy_orders_draft_smoke_publish_and_production_smoke(self) -> None:
        completed = self.run_command("deploy", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            self.command_log(),
            [
                f"git tag verify {TAG}",
                f"gh release view {TAG}",
                f"gh release download {TAG}",
                "release_bundle stage",
                "netlify create-draft",
                "http-smoke immutable",
                "playwright immutable",
                "netlify publish same-id",
                "http-smoke production",
                "playwright production",
            ],
        )

    def test_failed_immutable_smoke_never_publishes(self) -> None:
        completed = self.run_command(
            "deploy", TAG, environment={"FAIL_IMMUTABLE_SMOKE": "1"}
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("netlify publish same-id", self.command_log())
        self.assertFalse((DEPLOY_ROOT / "evidence.json").exists())

    def test_failed_immutable_browser_smoke_never_publishes(self) -> None:
        completed = self.run_command(
            "deploy", TAG, environment={"FAIL_IMMUTABLE_PLAYWRIGHT": "1"}
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("netlify publish same-id", self.command_log())

    def test_missing_each_secret_fails_before_tag_verification(self) -> None:
        for name in ("GITHUB_TOKEN", "NETLIFY_RUNTIME_SITE_ID", "NETLIFY_AUTH_TOKEN"):
            with self.subTest(name=name):
                self.log_path.unlink(missing_ok=True)
                completed = self.run_command("deploy", TAG, environment={name: ""})
                self.assertNotEqual(completed.returncode, 0)
                self.assertEqual(self.command_log(), [])
                self.assertIn(name, completed.stderr)

    def test_rejects_movable_or_non_product_tag_arguments(self) -> None:
        for value in (
            "latest",
            TAG_TARGET,
            "main",
            "refs/heads/main",
            "lmdj-v1.0.15",
            "lmdj-v1.0.15.2^{commit}",
        ):
            with self.subTest(value=value):
                self.log_path.unlink(missing_ok=True)
                completed = self.run_command("deploy", value)
                self.assertEqual(completed.returncode, 64)
                self.assertEqual(self.command_log(), [])

    def test_rejects_lightweight_or_untrusted_product_tags(self) -> None:
        for environment in (
            {"FAKE_TAG_TYPE": "commit"},
            {"FAKE_SIGNATURE_FINGERPRINT": "A" * 40},
            {"FAIL_TAG_VERIFY": "1"},
        ):
            with self.subTest(environment=environment):
                self.log_path.unlink(missing_ok=True)
                completed = self.run_command("deploy", TAG, environment=environment)
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn("gh release view", "\n".join(self.command_log()))
                self.assert_no_owned_temp()

    def test_release_must_be_published_canary_for_the_exact_tag_and_target(self) -> None:
        failures = (
            {"FAKE_RELEASE_DRAFT": "1"},
            {"FAKE_RELEASE_PRERELEASE": "0"},
            {"FAKE_RELEASE_TAG": "lmdj-v1.0.15.3"},
            {"FAKE_RELEASE_TARGET": "f" * 40},
        )
        for environment in failures:
            with self.subTest(environment=environment):
                self.log_path.unlink(missing_ok=True)
                completed = self.run_command("deploy", TAG, environment=environment)
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn(f"gh release download {TAG}", self.command_log())

    def test_initial_tag_requires_the_exact_target(self) -> None:
        completed = self.run_command(
            "deploy", TAG, environment={"FAKE_TAG_TARGET": "e" * 40}
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn(f"gh release view {TAG}", self.command_log())

    def test_rejects_duplicate_or_mismatched_release_assets(self) -> None:
        failures = (
            {"FAKE_DUPLICATE_ARCHIVE": "1"},
            {"FAKE_ARCHIVE_NAME": "lmdj-web-runtime-host-1.1.2-product-1.0.99.0.zip"},
            {"FAKE_ARCHIVE_NAME": "lmdj-web-runtime-host-9.9.9-product-1.0.15.2.zip"},
            {"FAKE_CHECKSUM_NAME": "wrong.zip.sha256"},
        )
        for environment in failures:
            with self.subTest(environment=environment):
                self.log_path.unlink(missing_ok=True)
                completed = self.run_command("deploy", TAG, environment=environment)
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn(f"gh release download {TAG}", self.command_log())

    def test_initial_tag_requires_the_host_archive_digest_not_the_core_digest(self) -> None:
        completed = self.run_command(
            "deploy", TAG, environment={"FAKE_ARCHIVE_DIGEST": "a" * 64}
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("netlify create-draft", self.command_log())

    def test_release_bundle_uses_the_detached_tag_target_checkout(self) -> None:
        completed = self.run_command("verify", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        detail = next(item for item in self.details() if "release_bundle_repo_root" in item)
        checkout = Path(str(detail["release_bundle_repo_root"]))
        self.assertNotEqual(checkout, REPO_ROOT)
        self.assertEqual(checkout.name, "tag-target")
        self.assertTrue(str(checkout).startswith(str(self.runner_temp.resolve())))
        self.assertFalse(checkout.exists())
        self.assertNotIn("netlify create-draft", self.command_log())

    def test_rejects_foreign_immutable_deploy_hostname_before_smoke_or_publish(self) -> None:
        completed = self.run_command(
            "deploy",
            TAG,
            environment={"FAKE_DEPLOY_URL": "https://deploy-456--runtime.example.com"},
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("http-smoke immutable", self.command_log())
        self.assertNotIn("netlify publish same-id", self.command_log())

    def test_publish_must_restore_same_id_site_and_production_hostname(self) -> None:
        failures = (
            {"FAKE_PUBLISHED_ID": "deploy-789"},
            {"FAKE_PUBLISHED_SITE_ID": "other-site"},
            {"FAKE_PRODUCTION_URL": "https://other-site.netlify.app"},
            {"FAKE_PUBLISHED_STATE": "building"},
        )
        for environment in failures:
            with self.subTest(environment=environment):
                self.log_path.unlink(missing_ok=True)
                completed = self.run_command("deploy", TAG, environment=environment)
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("netlify publish same-id", self.command_log())
                self.assertNotIn("http-smoke production", self.command_log())

    def test_failed_production_smoke_does_not_write_evidence(self) -> None:
        DEPLOY_ROOT.mkdir(parents=True, exist_ok=True)
        (DEPLOY_ROOT / "evidence.json").write_text("stale\n", encoding="utf-8")
        completed = self.run_command(
            "deploy", TAG, environment={"FAIL_PRODUCTION_SMOKE": "1"}
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("netlify publish same-id", self.command_log())
        self.assertFalse((DEPLOY_ROOT / "evidence.json").exists())

    def test_owned_worktree_and_temporary_root_are_removed_on_success_and_failure(self) -> None:
        for environment in ({}, {"FAIL_IMMUTABLE_SMOKE": "1"}):
            with self.subTest(environment=environment):
                self.log_path.unlink(missing_ok=True)
                completed = self.run_command("deploy", TAG, environment=environment)
                self.assertEqual(completed.returncode == 0, not environment)
                checkout = Path(
                    (self.root / "worktree-path").read_text(encoding="utf-8")
                )
                removed = Path(
                    (self.root / "worktree-removed").read_text(encoding="utf-8")
                )
                self.assertEqual(checkout, removed)
                self.assertFalse(checkout.exists())
                self.assert_no_owned_temp()

    def test_success_writes_exact_atomic_evidence_without_tokens(self) -> None:
        completed = self.run_command("deploy", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        evidence_path = DEPLOY_ROOT / "evidence.json"
        raw = evidence_path.read_text(encoding="utf-8")
        self.assertTrue(raw.endswith("\n"))
        evidence = json.loads(raw)
        self.assertEqual(
            evidence,
            {
                "archive_sha256": HOST_DIGEST,
                "channel": "canary",
                "contract": "lmdj.web-runtime-host.deployment-evidence.v1",
                "deploy_id": "deploy-456",
                "deploy_url": "https://deploy-456--lmdj-runtime.netlify.app",
                "git_revision": TAG_TARGET,
                "host_version": "1.1.2",
                "product_build": "1.0.15.2",
                "production_url": "https://lmdj-runtime.netlify.app",
                "release_url": f"https://github.com/endaye/lmdj/releases/tag/{TAG}",
                "site_id": "site-123",
                "tag": TAG,
            },
        )
        self.assertEqual(raw, json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n")
        combined = completed.stdout + completed.stderr + raw
        self.assertNotIn("github-secret-value-should-never-leak", combined)
        self.assertNotIn("netlify-secret-value-should-never-leak", combined)
        self.assertFalse(any("token" in str(value).lower() for value in evidence.values()))
        deploy_files = next(item["deploy_files"] for item in self.details() if "deploy_files" in item)
        self.assertEqual(deploy_files, ["/assets/runtime.js", "/index.html", "/_headers"])

    def test_token_like_live_identity_is_rejected_without_evidence(self) -> None:
        completed = self.run_command(
            "deploy", TAG, environment={"FAKE_DEPLOY_ID": "ghp_not-a-deploy-id"}
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse((DEPLOY_ROOT / "evidence.json").exists())

    def test_smoke_command_runs_http_then_browser_without_deployment_secrets(self) -> None:
        completed = self.run_command(
            "smoke",
            "https://lmdj-runtime.netlify.app",
            "1.0.15.2",
            "1.1.2",
            environment={
                "GITHUB_TOKEN": "",
                "NETLIFY_RUNTIME_SITE_ID": "",
                "NETLIFY_AUTH_TOKEN": "",
            },
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(self.command_log(), ["http-smoke production", "playwright production"])

    def test_host_nonbrowser_gate_registers_deploy_command_after_http_smoke(self) -> None:
        source = (REPO_ROOT / "scripts/web-runtime-host.sh").read_text(encoding="utf-8")
        http_test = (
            'python3 "$repo_root/apps/web-runtime-host/test/deployment_smoke_test.py"'
        )
        command_test = (
            'python3 "$repo_root/apps/web-runtime-host/test/deploy_command_test.py"'
        )
        self.assertEqual(source.count(command_test), 1)
        self.assertLess(source.index(http_test), source.index(command_test))


if __name__ == "__main__":
    unittest.main()
