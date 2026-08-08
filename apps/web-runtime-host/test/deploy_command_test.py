#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit


SOURCE_ROOT = Path(__file__).resolve().parents[3]
SOURCE_COMMAND = SOURCE_ROOT / "scripts/web-runtime-deploy.sh"
SOURCE_HELPER = SOURCE_ROOT / "apps/web-runtime-host/tools/deploy_orchestrator.py"
SOURCE_NETLIFY = SOURCE_ROOT / "apps/web-runtime-host/tools/netlify_api.py"
SOURCE_RELEASE_BUNDLE = SOURCE_ROOT / "apps/web-runtime-host/tools/release_bundle.py"
REAL_EVIDENCE_ROOT = SOURCE_ROOT / "build/deploy/web-runtime-host"
TAG = "lmdj-v1.0.15.3"
PRODUCT_BUILD = "1.0.15.3"
TAG_TARGET = "b" * 40
INITIAL_TAG = "lmdj-v1.0.15.2"
INITIAL_TAG_TARGET = "72ae40074620cc5681c462ba04a31a666449734f"
HOST_VERSION = "1.1.2"
INITIAL_HOST_DIGEST = (
    "d56a7c99a3c489db068b93fcef70a254"
    "b498adf4bc65919253beccb199f3ad5a"
)
TRUSTED_FINGERPRINT = "2B5EE362F058800036AD4FB5116ECE156F954D29"
GITHUB_TOKEN = "github-secret-value-should-never-leak"
NETLIFY_TOKEN = "netlify-secret-value-should-never-leak"
SITE_ID = "site-123"
DEPLOY_ID = "deploy-456"
PRODUCTION_URL = "https://lmdj-runtime.netlify.app"


def snapshot_tree(root: Path) -> tuple[object, ...]:
    if root.is_symlink():
        return ("symlink", os.readlink(root))
    if not root.exists():
        return ("absent",)
    entries: list[object] = [("root", root.stat().st_mode)]
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            entries.append(("symlink", relative, os.readlink(path)))
        elif path.is_dir():
            entries.append(("directory", relative, path.stat().st_mode))
        else:
            entries.append(("file", relative, path.stat().st_mode, path.read_bytes()))
    return tuple(entries)


class FakeNetlifyHandler(BaseHTTPRequestHandler):
    server: "FakeNetlifyServer"

    def log_message(self, format: str, *args: object) -> None:
        return

    def send_json(self, status: int, document: object) -> None:
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self) -> object:
        size = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(size))

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        create_path = f"/api/v1/sites/{SITE_ID}/deploys"
        restore_path = f"/api/v1/sites/{SITE_ID}/deploys/{DEPLOY_ID}/restore"
        if parsed.path == create_path:
            document = self.read_json()
            self.server.create_document = document
            self.server.authorization_headers.append(
                self.headers.get("Authorization", "")
            )
            self.server.append_log("netlify create-draft")
            response: dict[str, object] = {
                "id": self.server.deploy_id,
                "site_id": SITE_ID,
                "deploy_ssl_url": self.server.deploy_url,
                "state": "ready",
                "required": [],
            }
            response.update(self.server.create_extra)
            self.send_json(200, response)
            return
        if parsed.path == restore_path:
            self.read_json()
            self.server.authorization_headers.append(
                self.headers.get("Authorization", "")
            )
            self.server.append_log("netlify publish same-id")
            document: dict[str, object] = {
                "id": self.server.published_id,
                "site_id": self.server.published_site_id,
                "ssl_url": self.server.production_url,
                "state": self.server.published_state,
            }
            document.update(self.server.restore_extra)
            self.send_json(200, document)
            return
        self.send_json(404, {"error": "not found"})


class FakeNetlifyServer(ThreadingHTTPServer):
    command_log: Path
    create_document: object | None
    deploy_id: str
    deploy_url: str
    published_id: str
    published_site_id: str
    production_url: str
    published_state: str
    create_extra: dict[str, object]
    restore_extra: dict[str, object]
    authorization_headers: list[str]

    def append_log(self, value: str) -> None:
        with self.command_log.open("a", encoding="utf-8") as output:
            output.write(value + "\n")


class DeployCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.real_evidence_before = snapshot_tree(REAL_EVIDENCE_ROOT)
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-deploy-command-test-")
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.bin = self.root / "bin"
        self.runner_temp = self.root / "runner-temp"
        self.log_path = self.root / "commands.log"
        self.details_path = self.root / "details.jsonl"
        self.worktree_path_record = self.root / "worktree-path"
        self.worktree_removed_record = self.root / "worktree-removed"
        self.block_ready = self.root / "block-ready"
        self.repo.mkdir()
        self.bin.mkdir()
        self.runner_temp.mkdir()

        self.server = cast(
            FakeNetlifyServer,
            FakeNetlifyServer(("127.0.0.1", 0), FakeNetlifyHandler),
        )
        self.server.command_log = self.log_path
        self.server.create_document = None
        self.reset_server()
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

        self.prepare_isolated_repository()
        self.write_fake_commands()
        self.command = self.repo / "scripts/web-runtime-deploy.sh"
        self.deploy_root = self.repo / "build/deploy/web-runtime-host"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=5)
        self.temporary.cleanup()
        self.assertEqual(snapshot_tree(REAL_EVIDENCE_ROOT), self.real_evidence_before)

    def reset_server(self) -> None:
        self.server.deploy_id = DEPLOY_ID
        self.server.deploy_url = f"https://{DEPLOY_ID}--lmdj-runtime.netlify.app"
        self.server.published_id = DEPLOY_ID
        self.server.published_site_id = SITE_ID
        self.server.production_url = PRODUCTION_URL
        self.server.published_state = "ready"
        self.server.create_extra = {}
        self.server.restore_extra = {}
        self.server.authorization_headers = []
        self.server.create_document = None

    def copy_source(self, source: Path, relative: str) -> Path:
        target = self.repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target

    def prepare_isolated_repository(self) -> None:
        command = self.copy_source(SOURCE_COMMAND, "scripts/web-runtime-deploy.sh")
        command.chmod(0o755)
        self.copy_source(
            SOURCE_HELPER, "apps/web-runtime-host/tools/deploy_orchestrator.py"
        )
        self.copy_source(
            SOURCE_RELEASE_BUNDLE, "apps/web-runtime-host/tools/release_bundle.py"
        )
        api_base = f"http://127.0.0.1:{self.server.server_port}/api/v1"
        netlify_source = SOURCE_NETLIFY.read_text(encoding="utf-8")
        original = '"https://api.netlify.com/api/v1"'
        self.assertEqual(netlify_source.count(original), 1)
        isolated_netlify = self.repo / "apps/web-runtime-host/tools/netlify_api.py"
        isolated_netlify.write_text(
            netlify_source.replace(original, json.dumps(api_base), 1),
            encoding="utf-8",
        )
        headers = self.repo / "apps/web-runtime-host/deploy/_headers"
        headers.parent.mkdir(parents=True)
        headers.write_text("/*\n  X-Robots-Tag: noindex\n", encoding="utf-8")
        key = self.repo / ".github/release-signing-keys/lmdj-product.asc"
        key.parent.mkdir(parents=True)
        key.write_text("test-only public key fixture\n", encoding="utf-8")
        smoke = self.repo / "apps/web-runtime-host/tools/deployment_smoke.py"
        smoke.write_text(
            textwrap.dedent(
                f"""
                #!{sys.executable}
                import os
                from pathlib import Path
                import sys

                for name in ("GITHUB_TOKEN", "NETLIFY_AUTH_TOKEN", "NETLIFY_RUNTIME_SITE_ID"):
                    if os.environ.get(name):
                        raise SystemExit("deployment credential reached HTTP smoke")
                immutable = "--expected-deploy-id" in sys.argv
                label = "immutable" if immutable else "production"
                with Path(os.environ["COMMAND_LOG"]).open("a", encoding="utf-8") as output:
                    output.write(f"http-smoke {{label}}\\n")
                failure = "FAIL_IMMUTABLE_SMOKE" if immutable else "FAIL_PRODUCTION_SMOKE"
                if os.environ.get(failure) == "1":
                    raise SystemExit(f"forced {{label}} smoke failure")
                """
            ).lstrip(),
            encoding="utf-8",
        )

    def write_executable(self, name: str, source: str) -> None:
        path = self.bin / name
        path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")
        path.chmod(0o755)

    def write_fake_commands(self) -> None:
        package_verifier = """import json
import os
from pathlib import Path

def verify_distribution(dist_root, repo_root):
    manifest = json.loads((dist_root / "host-manifest.json").read_text(encoding="utf-8"))
    product = json.loads((repo_root / "products/lmdj/version.json").read_text(encoding="utf-8"))
    expected_product = ".".join(str(product[name]) for name in ("milestone", "minor", "build", "patch"))
    host = json.loads((repo_root / "apps/web-runtime-host/module.json").read_text(encoding="utf-8"))
    if manifest != {"product_build": expected_product, "host_version": host["version"]}:
        raise RuntimeError("fixture distribution identity mismatch")
    actual = sorted(path.relative_to(dist_root).as_posix() for path in dist_root.rglob("*") if path.is_file())
    if actual != ["host-manifest.json", "index.html"]:
        raise RuntimeError("fixture distribution inventory mismatch")
    with Path(os.environ["COMMAND_LOG"]).open("a", encoding="utf-8") as output:
        output.write("release_bundle stage\\n")
    with Path(os.environ["DETAILS_LOG"]).open("a", encoding="utf-8") as output:
        output.write(json.dumps({"release_bundle_repo_root": str(repo_root), "dist_files": actual}, sort_keys=True) + "\\n")
"""
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
            product_build = os.environ.get("FAKE_PRODUCT_BUILD", {PRODUCT_BUILD!r})
            if args[:2] == ["cat-file", "-t"]:
                print(os.environ.get("FAKE_TAG_TYPE", "tag"))
            elif args[:2] == ["verify-tag", "--raw"]:
                with log.open("a", encoding="utf-8") as output:
                    output.write(f"git tag verify {{args[2]}}\\n")
                if os.environ.get("FAIL_TAG_VERIFY") == "1":
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
                parts = [int(value) for value in product_build.split(".")]
                checkout.joinpath("products/lmdj/version.json").write_text(
                    json.dumps({{
                        "contract": "lmdj.product-version.v1",
                        "product": "lmdj",
                        "milestone": parts[0],
                        "minor": parts[1],
                        "build": parts[2],
                        "patch": parts[3],
                    }}),
                    encoding="utf-8",
                )
                checkout.joinpath("apps/web-runtime-host/module.json").write_text(
                    json.dumps({{
                        "contract": "lmdj.module.v1",
                        "module": "web-runtime-host",
                        "version": {HOST_VERSION!r},
                        "api_version": 1,
                        "dependencies": {{}},
                    }}),
                    encoding="utf-8",
                )
                checkout.joinpath("apps/web-runtime-host/tools/package.py").write_text(
                    {package_verifier!r},
                    encoding="utf-8",
                )
                Path(os.environ["WORKTREE_PATH"]).write_text(str(checkout), encoding="utf-8")
            elif args[:3] == ["worktree", "remove", "--force"]:
                checkout = Path(args[3])
                shutil.rmtree(checkout, ignore_errors=True)
                Path(os.environ["WORKTREE_REMOVED"]).write_text(str(checkout), encoding="utf-8")
            else:
                raise SystemExit(97)
            """,
        )
        self.write_executable(
            "gh",
            f"""
            #!{sys.executable}
            import hashlib
            import json
            import os
            from pathlib import Path
            import signal
            import sys
            import time
            import zipfile

            args = sys.argv[1:]
            if os.environ.get("GH_REPO") or os.environ.get("GH_TOKEN") or os.environ.get("GH_HOST"):
                raise SystemExit("conflicting gh environment was not neutralized")
            if os.environ.get("GITHUB_TOKEN") != os.environ["EXPECTED_GITHUB_TOKEN"]:
                raise SystemExit("intended GitHub credential was not selected")
            if args.count("--repo") != 1 or args[args.index("--repo") + 1] != "endaye/lmdj":
                raise SystemExit("GitHub repository was not pinned")
            log = Path(os.environ["COMMAND_LOG"])
            if args[:2] == ["release", "view"]:
                tag = args[2]
                product_build = tag.removeprefix("lmdj-v")
                archive = os.environ.get(
                    "FAKE_ARCHIVE_NAME",
                    f"lmdj-web-runtime-host-{HOST_VERSION}-product-{{product_build}}.zip",
                )
                checksum = os.environ.get("FAKE_CHECKSUM_NAME", archive + ".sha256")
                assets = [{{"name": archive}}, {{"name": checksum}}]
                if os.environ.get("FAKE_DUPLICATE_ARCHIVE") == "1":
                    assets.append({{"name": archive}})
                if os.environ.get("FAKE_RELEASE_SECRET_FIELD") == "1":
                    assets[0]["label"] = os.environ["GITHUB_TOKEN"]
                with log.open("a", encoding="utf-8") as output:
                    output.write(f"gh release view {{tag}}\\n")
                print(json.dumps({{
                    "tagName": os.environ.get("FAKE_RELEASE_TAG", tag),
                    "isDraft": os.environ.get("FAKE_RELEASE_DRAFT") == "1",
                    "isPrerelease": os.environ.get("FAKE_RELEASE_PRERELEASE", "1") == "1",
                    "targetCommitish": os.environ.get("FAKE_RELEASE_TARGET", os.environ.get("FAKE_TAG_TARGET", {TAG_TARGET!r})),
                    "assets": assets,
                    "url": os.environ.get("FAKE_RELEASE_URL", f"https://github.com/endaye/lmdj/releases/tag/{{tag}}"),
                }}, sort_keys=True))
            elif args[:2] == ["release", "download"]:
                tag = args[2]
                with log.open("a", encoding="utf-8") as output:
                    output.write(f"gh release download {{tag}}\\n")
                if os.environ.get("BLOCK_GH_DOWNLOAD") == "1":
                    Path(os.environ["BLOCK_READY"]).write_text("ready", encoding="utf-8")
                    while True:
                        time.sleep(1)
                destination = Path(args[args.index("--dir") + 1])
                patterns = [args[index + 1] for index, value in enumerate(args) if value == "--pattern"]
                archive_name = next(name for name in patterns if name.endswith(".zip"))
                checksum_name = next(name for name in patterns if name.endswith(".zip.sha256"))
                destination.mkdir(parents=True, exist_ok=True)
                product_build = tag.removeprefix("lmdj-v")
                manifest = json.dumps({{"product_build": product_build, "host_version": {HOST_VERSION!r}}}, sort_keys=True, separators=(",", ":"))
                archive_path = destination / archive_name
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr("dist/index.html", "fixture index")
                    archive.writestr("dist/host-manifest.json", manifest)
                digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
                (destination / checksum_name).write_text(
                    f"{{digest}}  {{archive_name}}\\n", encoding="utf-8"
                )
                Path(os.environ["ARCHIVE_DIGEST"]).write_text(digest, encoding="utf-8")
            else:
                raise SystemExit(97)
            """,
        )
        self.write_executable(
            "npm",
            f"""
            #!{sys.executable}
            import os
            from pathlib import Path

            for name in ("GITHUB_TOKEN", "NETLIFY_AUTH_TOKEN", "NETLIFY_RUNTIME_SITE_ID"):
                if os.environ.get(name):
                    raise SystemExit("deployment credential reached browser smoke")
            base_url = os.environ.get("LMDJ_WEB_HOST_BASE_URL", "")
            immutable = base_url != {PRODUCTION_URL!r}
            label = "immutable" if immutable else "production"
            with Path(os.environ["COMMAND_LOG"]).open("a", encoding="utf-8") as output:
                output.write(f"playwright {{label}}\\n")
            failure = "FAIL_IMMUTABLE_PLAYWRIGHT" if immutable else "FAIL_PRODUCTION_PLAYWRIGHT"
            if os.environ.get(failure) == "1":
                raise SystemExit(f"forced {{label}} Playwright failure")
            """,
        )

    def environment(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        environment = os.environ.copy()
        environment.pop("LMDJ_NETLIFY_API_BASE", None)
        environment.update(
            {
                "PATH": f"{self.bin}{os.pathsep}{environment['PATH']}",
                "COMMAND_LOG": str(self.log_path),
                "DETAILS_LOG": str(self.details_path),
                "WORKTREE_PATH": str(self.worktree_path_record),
                "WORKTREE_REMOVED": str(self.worktree_removed_record),
                "BLOCK_READY": str(self.block_ready),
                "ARCHIVE_DIGEST": str(self.root / "archive-digest"),
                "RUNNER_TEMP": str(self.runner_temp),
                "GITHUB_TOKEN": GITHUB_TOKEN,
                "EXPECTED_GITHUB_TOKEN": GITHUB_TOKEN,
                "NETLIFY_RUNTIME_SITE_ID": SITE_ID,
                "NETLIFY_AUTH_TOKEN": NETLIFY_TOKEN,
                "GH_REPO": "attacker/example",
                "GH_TOKEN": "higher-precedence-hostile-token",
                "GH_HOST": "attacker.example",
            }
        )
        if extra:
            environment.update(extra)
        return environment

    def run_command(
        self, *arguments: str, environment: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.command), *arguments],
            cwd=self.repo,
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

    def reset_run_records(self) -> None:
        for path in (
            self.log_path,
            self.details_path,
            self.worktree_path_record,
            self.worktree_removed_record,
            self.block_ready,
            self.root / "archive-digest",
        ):
            path.unlink(missing_ok=True)
        shutil.rmtree(self.deploy_root, ignore_errors=True)
        self.reset_server()

    def assert_no_owned_temp(self) -> None:
        self.assertEqual(list(self.runner_temp.glob("lmdj-web-runtime-deploy.*")), [])

    def assert_no_secret_output(self, completed: subprocess.CompletedProcess[str]) -> None:
        combined = completed.stdout + completed.stderr
        self.assertNotIn(GITHUB_TOKEN, combined)
        self.assertNotIn(NETLIFY_TOKEN, combined)

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

    def test_deploy_orders_real_stage_api_smoke_restore_and_production_smoke(self) -> None:
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
        create = cast(dict[str, object], self.server.create_document)
        self.assertEqual(set(cast(dict[str, str], create["files"])), {
            "/_headers", "/host-manifest.json", "/index.html"
        })
        self.assertEqual(
            self.server.authorization_headers,
            [f"Bearer {NETLIFY_TOKEN}", f"Bearer {NETLIFY_TOKEN}"],
        )

    def test_release_stage_uses_real_bundle_wrapper_and_detached_tag_checkout(self) -> None:
        completed = self.run_command("verify", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        detail = next(item for item in self.details() if "release_bundle_repo_root" in item)
        checkout = Path(str(detail["release_bundle_repo_root"]))
        self.assertEqual(detail["dist_files"], ["host-manifest.json", "index.html"])
        self.assertNotEqual(checkout, self.repo)
        self.assertEqual(checkout.name, "tag-target")
        self.assertTrue(str(checkout).startswith(str(self.runner_temp.resolve())))
        self.assertFalse(checkout.exists())

    def test_publish_accepts_additive_official_response_fields(self) -> None:
        self.server.restore_extra = {
            "published_at": "2026-08-09T00:00:00Z",
            "admin_url": "https://app.netlify.com/sites/lmdj-runtime",
        }
        completed = self.run_command("deploy", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("http-smoke production", self.command_log())
        self.assertTrue((self.deploy_root / "evidence.json").is_file())

    def test_rejects_foreign_netlify_site_before_smoke_or_publish(self) -> None:
        self.server.deploy_url = f"https://{DEPLOY_ID}--attacker.netlify.app"
        completed = self.run_command("deploy", TAG)
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("http-smoke immutable", self.command_log())
        self.assertNotIn("netlify publish same-id", self.command_log())

    def test_publish_requires_same_id_site_production_url_and_ready_state(self) -> None:
        changes = (
            ("published_id", "deploy-789"),
            ("published_site_id", "other-site"),
            ("production_url", "https://other-site.netlify.app"),
            ("published_state", "building"),
        )
        for attribute, value in changes:
            with self.subTest(attribute=attribute):
                self.reset_run_records()
                setattr(self.server, attribute, value)
                completed = self.run_command("deploy", TAG)
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("netlify publish same-id", self.command_log())
                self.assertNotIn("http-smoke production", self.command_log())

    def test_missing_each_secret_fails_before_tag_verification(self) -> None:
        for name in ("GITHUB_TOKEN", "NETLIFY_RUNTIME_SITE_ID", "NETLIFY_AUTH_TOKEN"):
            with self.subTest(name=name):
                self.reset_run_records()
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
                self.reset_run_records()
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
                self.reset_run_records()
                completed = self.run_command("deploy", TAG, environment=environment)
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn("gh release view", "\n".join(self.command_log()))
                self.assert_no_owned_temp()

    def test_release_is_exact_published_canary_target_and_canonical_url(self) -> None:
        failures = (
            {"FAKE_RELEASE_DRAFT": "1"},
            {"FAKE_RELEASE_PRERELEASE": "0"},
            {"FAKE_RELEASE_TAG": "lmdj-v1.0.15.4"},
            {"FAKE_RELEASE_TARGET": "f" * 40},
            {"FAKE_RELEASE_URL": f"https://attacker.example/releases/tag/{TAG}"},
            {"FAKE_RELEASE_URL": f"https://github.com/attacker/lmdj/releases/tag/{TAG}"},
        )
        for environment in failures:
            with self.subTest(environment=environment):
                self.reset_run_records()
                completed = self.run_command("deploy", TAG, environment=environment)
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn(f"gh release download {TAG}", self.command_log())

    def test_hostile_gh_environment_is_neutralized_and_repo_is_pinned(self) -> None:
        completed = self.run_command("verify", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            [value for value in self.command_log() if value.startswith("gh release")],
            [f"gh release view {TAG}", f"gh release download {TAG}"],
        )

    def test_rejects_duplicate_or_mismatched_release_assets(self) -> None:
        failures = (
            {"FAKE_DUPLICATE_ARCHIVE": "1"},
            {"FAKE_ARCHIVE_NAME": "lmdj-web-runtime-host-1.1.2-product-1.0.99.0.zip"},
            {"FAKE_ARCHIVE_NAME": "lmdj-web-runtime-host-9.9.9-product-1.0.15.3.zip"},
            {"FAKE_CHECKSUM_NAME": "wrong.zip.sha256"},
        )
        for environment in failures:
            with self.subTest(environment=environment):
                self.reset_run_records()
                completed = self.run_command("deploy", TAG, environment=environment)
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn(f"gh release download {TAG}", self.command_log())

    def test_initial_tag_requires_exact_target_and_corrected_host_digest(self) -> None:
        completed = self.run_command(
            "deploy",
            INITIAL_TAG,
            environment={
                "FAKE_PRODUCT_BUILD": "1.0.15.2",
                "FAKE_TAG_TARGET": "e" * 40,
            },
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn(f"gh release view {INITIAL_TAG}", self.command_log())

        self.reset_run_records()
        completed = self.run_command(
            "deploy",
            INITIAL_TAG,
            environment={
                "FAKE_PRODUCT_BUILD": "1.0.15.2",
                "FAKE_TAG_TARGET": INITIAL_TAG_TARGET,
            },
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("release_bundle stage", self.command_log())
        self.assertNotIn("netlify create-draft", self.command_log())
        helper_source = SOURCE_HELPER.read_text(encoding="utf-8")
        self.assertIn(INITIAL_HOST_DIGEST[:32], helper_source)
        self.assertIn(INITIAL_HOST_DIGEST[32:], helper_source)

    def test_failed_immutable_smoke_and_browser_never_publish(self) -> None:
        for environment in (
            {"FAIL_IMMUTABLE_SMOKE": "1"},
            {"FAIL_IMMUTABLE_PLAYWRIGHT": "1"},
        ):
            with self.subTest(environment=environment):
                self.reset_run_records()
                completed = self.run_command("deploy", TAG, environment=environment)
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn("netlify publish same-id", self.command_log())
                self.assertFalse((self.deploy_root / "evidence.json").exists())

    def test_failed_production_smoke_does_not_write_evidence(self) -> None:
        completed = self.run_command(
            "deploy", TAG, environment={"FAIL_PRODUCTION_SMOKE": "1"}
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("netlify publish same-id", self.command_log())
        self.assertFalse((self.deploy_root / "evidence.json").exists())

    def test_owned_worktree_and_temp_are_removed_on_success_and_failure(self) -> None:
        for environment in ({}, {"FAIL_IMMUTABLE_SMOKE": "1"}):
            with self.subTest(environment=environment):
                self.reset_run_records()
                completed = self.run_command("deploy", TAG, environment=environment)
                self.assertEqual(completed.returncode == 0, not environment)
                checkout = Path(self.worktree_path_record.read_text(encoding="utf-8"))
                removed = Path(self.worktree_removed_record.read_text(encoding="utf-8"))
                self.assertEqual(checkout, removed)
                self.assertFalse(checkout.exists())
                self.assert_no_owned_temp()

    def test_success_writes_exact_atomic_evidence_without_credentials(self) -> None:
        completed = self.run_command("deploy", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        raw = (self.deploy_root / "evidence.json").read_text(encoding="utf-8")
        digest = (self.root / "archive-digest").read_text(encoding="utf-8")
        evidence = json.loads(raw)
        self.assertEqual(
            evidence,
            {
                "archive_sha256": digest,
                "channel": "canary",
                "contract": "lmdj.web-runtime-host.deployment-evidence.v1",
                "deploy_id": DEPLOY_ID,
                "deploy_url": f"https://{DEPLOY_ID}--lmdj-runtime.netlify.app",
                "git_revision": TAG_TARGET,
                "host_version": HOST_VERSION,
                "product_build": PRODUCT_BUILD,
                "production_url": PRODUCTION_URL,
                "release_url": f"https://github.com/endaye/lmdj/releases/tag/{TAG}",
                "site_id": SITE_ID,
                "tag": TAG,
            },
        )
        self.assertEqual(
            raw, json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n"
        )
        self.assert_no_secret_output(completed)
        self.assertNotIn(GITHUB_TOKEN, raw)
        self.assertNotIn(NETLIFY_TOKEN, raw)

    def test_rejects_credentials_in_release_draft_or_additive_restore_values(self) -> None:
        cases = ("release", "draft", "draft-additive", "restore")
        for case in cases:
            with self.subTest(case=case):
                self.reset_run_records()
                environment: dict[str, str] = {}
                if case == "release":
                    environment["FAKE_RELEASE_SECRET_FIELD"] = "1"
                elif case == "draft":
                    self.server.deploy_id = GITHUB_TOKEN
                    self.server.deploy_url = (
                        f"https://{GITHUB_TOKEN}--lmdj-runtime.netlify.app"
                    )
                elif case == "draft-additive":
                    self.server.create_extra = {"diagnostic": GITHUB_TOKEN}
                else:
                    self.server.restore_extra = {"diagnostic": NETLIFY_TOKEN}
                completed = self.run_command("deploy", TAG, environment=environment)
                self.assertNotEqual(completed.returncode, 0)
                self.assert_no_secret_output(completed)
                self.assertFalse((self.deploy_root / "evidence.json").exists())
                if case in {"draft", "draft-additive"}:
                    self.assertNotIn("http-smoke immutable", self.command_log())
                    self.assertNotIn("netlify publish same-id", self.command_log())

    def test_production_source_has_no_api_override_and_pins_github_repo(self) -> None:
        command_source = SOURCE_COMMAND.read_text(encoding="utf-8")
        helper_source = SOURCE_HELPER.read_text(encoding="utf-8")
        self.assertIn("--repo endaye/lmdj", command_source)
        self.assertNotIn("LMDJ_NETLIFY_API_BASE", command_source + helper_source)
        self.assertNotIn("api_base=", helper_source)

    def test_command_harness_isolated_from_real_deploy_evidence(self) -> None:
        completed = self.run_command("deploy", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue((self.deploy_root / "evidence.json").is_file())
        self.assertNotEqual(self.deploy_root, REAL_EVIDENCE_ROOT)
        self.assertEqual(snapshot_tree(REAL_EVIDENCE_ROOT), self.real_evidence_before)

    def test_smoke_command_runs_without_deployment_credentials(self) -> None:
        completed = self.run_command(
            "smoke",
            PRODUCTION_URL,
            PRODUCT_BUILD,
            HOST_VERSION,
            environment={
                "GITHUB_TOKEN": "",
                "NETLIFY_RUNTIME_SITE_ID": "",
                "NETLIFY_AUTH_TOKEN": "",
            },
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            self.command_log(), ["http-smoke production", "playwright production"]
        )

    def test_int_and_term_cleanup_owned_state_without_restore_or_evidence(self) -> None:
        for selected_signal, expected in ((signal.SIGINT, 130), (signal.SIGTERM, 143)):
            with self.subTest(signal=selected_signal):
                self.reset_run_records()
                process = subprocess.Popen(
                    [str(self.command), "deploy", TAG],
                    cwd=self.repo,
                    env=self.environment({"BLOCK_GH_DOWNLOAD": "1"}),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                )
                deadline = time.monotonic() + 10
                while not self.block_ready.exists() and process.poll() is None:
                    if time.monotonic() >= deadline:
                        process.kill()
                        self.fail("blocked gh download did not become ready")
                    time.sleep(0.02)
                os.killpg(process.pid, selected_signal)
                stdout, stderr = process.communicate(timeout=10)
                self.assertIn(process.returncode, {expected, -selected_signal})
                completed = subprocess.CompletedProcess(
                    process.args, process.returncode, stdout, stderr
                )
                self.assert_no_secret_output(completed)
                self.assertNotIn("netlify publish same-id", self.command_log())
                self.assertFalse((self.deploy_root / "evidence.json").exists())
                checkout = Path(self.worktree_path_record.read_text(encoding="utf-8"))
                removed = Path(self.worktree_removed_record.read_text(encoding="utf-8"))
                self.assertEqual(checkout, removed)
                self.assertFalse(checkout.exists())
                self.assert_no_owned_temp()

    def test_host_nonbrowser_gate_registers_isolated_command_test(self) -> None:
        source = (SOURCE_ROOT / "scripts/web-runtime-host.sh").read_text(encoding="utf-8")
        http_test = (
            'python3 "$repo_root/apps/web-runtime-host/test/deployment_smoke_test.py"'
        )
        command_test = (
            'python3 "$repo_root/apps/web-runtime-host/test/deploy_command_test.py"'
        )
        self.assertEqual(source.count(command_test), 1)
        self.assertLess(source.index(http_test), source.index(command_test))
        forbidden_real_cleanup = "shutil.rmtree(" + "REAL_EVIDENCE_ROOT"
        self.assertNotIn(forbidden_real_cleanup, Path(__file__).read_text())


if __name__ == "__main__":
    unittest.main()
