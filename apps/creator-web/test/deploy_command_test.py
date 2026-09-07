#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
SOURCE_COMMAND = SOURCE_ROOT / "scripts/creator-web-deploy.sh"
SOURCE_HELPER = SOURCE_ROOT / "apps/creator-web/tools/deploy_orchestrator.py"
SOURCE_NETLIFY = SOURCE_ROOT / "apps/web-runtime-host/tools/netlify_api.py"
SOURCE_RELEASE_BUNDLE = SOURCE_ROOT / "apps/creator-web/tools/release_bundle.py"
SOURCE_RELEASE_INIT = SOURCE_ROOT / "tools/release/__init__.py"
SOURCE_RELEASE_COMMANDS = SOURCE_ROOT / "tools/release/commands.py"
SOURCE_RELEASE_OPENPGP = SOURCE_ROOT / "tools/release/openpgp.py"
SOURCE_WEB_HOST_BUNDLE = SOURCE_ROOT / "tools/release/web_host_bundle.py"
SOURCE_WEB_DEPLOY_INIT = SOURCE_ROOT / "tools/web_deploy/__init__.py"
SOURCE_RELEASE_SELECTION = SOURCE_ROOT / "tools/web_deploy/release_selection.py"
SOURCE_TAG_VERIFIER = SOURCE_ROOT / "tools/release/tag_verifier.py"
REAL_EVIDENCE_ROOT = SOURCE_ROOT / "build/deploy/creator-web"
TAG = "lmdj-v1.0.15.3"
PRODUCT_BUILD = "1.0.15.3"
TAG_TARGET = "b" * 40
INITIAL_TAG = "lmdj-v1.0.15.2"
INITIAL_TAG_TARGET = "72ae40074620cc5681c462ba04a31a666449734f"
HOST_VERSION = "1.2.0"
INITIAL_HOST_DIGEST = (
    "d56a7c99a3c489db068b93fcef70a254"
    "b498adf4bc65919253beccb199f3ad5a"
)
TRUSTED_TAG_FINGERPRINT = "2B5EE362F058800036AD4FB5116ECE156F954D29"
TRUSTED_CHECKSUM_FINGERPRINT = "CB928A6E89DE498851688EF1AAC3E7019FC1478B"
GITHUB_TOKEN = "github-secret-value-should-never-leak"
GITHUB_RUN_ID = "123456789"
NETLIFY_TOKEN = "netlify-secret-value-should-never-leak"
SITE_ID = "site-123"
DEPLOY_ID = "deploy-456"
PRIOR_DEPLOY_ID = "prior-123"
PRODUCTION_URL = "https://lmdj-creator.netlify.app"
CANDIDATE_INDEX_SHA256 = hashlib.sha256(b"fixture index").hexdigest()
PRIOR_INDEX_SHA256 = "c" * 64
PRIOR_MANIFEST_SHA256 = "d" * 64

# Readiness budgets for a spawned deploy subprocess, in seconds. A signal test
# must wait for the deploy to reach its blocking sentinel, and that wait covers
# real interpreter startup plus every stubbed pipeline stage before the block,
# so the budget scales with the stage count instead of guessing one wall-clock
# number. A fixed budget that passes locally becomes a deterministic CI failure
# once normal runner variance consumes its missing headroom; see
# `.agents/pitfalls/facade-surface-test-budget-headroom.md`. Four shards of this
# suite share one self-hosted host, so the allowance is deliberately generous:
# an over-long budget only delays a genuine hang, never a healthy run.
READINESS_STARTUP_SECONDS = 15.0
READINESS_PER_STAGE_SECONDS = 3.0
# Stages of `test_deploy_orders_real_stage_api_smoke_restore_and_production_smoke`
# the subprocess completes before each blocking sentinel is written.
GH_DOWNLOAD_READY_STAGES = 7
POST_PUBLISH_READY_STAGES = 21
# Budget for the signalled subprocess to unwind, reconcile and exit.
SHUTDOWN_BUDGET_SECONDS = 60.0


def fixture_manifest(product_build: str) -> str:
    assets = [
        {
            "bytes": 1,
            "path": f"assets/asset-{index}.{str(index) * 64}.mjs",
            "role": "host_module",
            "sha256": str(index) * 64,
        }
        for index in range(9)
    ]
    return json.dumps(
        {
            "assets": assets,
            "product_build": product_build,
            "host_version": HOST_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


CANDIDATE_MANIFEST_SHA256 = hashlib.sha256(
    fixture_manifest(PRODUCT_BUILD).encode()
).hexdigest()


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
        restore_prefix = f"/api/v1/sites/{SITE_ID}/deploys/"
        if parsed.path.startswith(restore_prefix) and parsed.path.endswith("/restore"):
            self.read_json()
            requested_id = parsed.path.removeprefix(restore_prefix).removesuffix("/restore")
            self.server.authorization_headers.append(
                self.headers.get("Authorization", "")
            )
            self.server.append_log(
                "netlify publish same-id"
                if requested_id == DEPLOY_ID
                else "netlify restore prior-id"
            )
            if requested_id == PRIOR_DEPLOY_ID:
                if not self.server.restore_keeps_candidate:
                    self.server.current_deploy_id = PRIOR_DEPLOY_ID
                    self.server.current_deploy_url = (
                        f"https://{PRIOR_DEPLOY_ID}--lmdj-creator.netlify.app"
                    )
                self.send_json(
                    201,
                    {
                        "id": PRIOR_DEPLOY_ID,
                        "site_id": SITE_ID,
                        "ssl_url": PRODUCTION_URL,
                        "deploy_ssl_url": f"https://{PRIOR_DEPLOY_ID}--lmdj-creator.netlify.app",
                        "state": "ready",
                        "published_at": "2026-08-09T00:00:00Z",
                    },
                )
                return
            document: dict[str, object] = {
                "id": self.server.published_id,
                "site_id": self.server.published_site_id,
                "ssl_url": self.server.production_url,
                "deploy_ssl_url": self.server.deploy_url,
                "state": self.server.published_state,
                "published_at": "2026-08-09T00:00:00Z",
            }
            document.update(self.server.restore_extra)
            if self.server.publish_switches_alias:
                self.server.current_deploy_id = self.server.published_id
                self.server.current_deploy_url = self.server.deploy_url
            if self.server.publish_error_after_switch:
                self.send_json(500, {"error": "publish failed after alias switch"})
                return
            self.send_json(201, document)
            return
        self.send_json(404, {"error": "not found"})

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == f"/api/v1/sites/{SITE_ID}/files":
            self.server.authorization_headers.append(
                self.headers.get("Authorization", "")
            )
            self.server.append_log("netlify get-current-files")
            self.send_json(
                200,
                self.server.site_files_response
                if self.server.current_deploy_id
                else [],
            )
            if self.server.change_site_after_files:
                self.server.current_deploy_id = "other-789"
                self.server.current_deploy_url = (
                    "https://other-789--lmdj-creator.netlify.app"
                )
            return
        if path != f"/api/v1/sites/{SITE_ID}":
            self.send_json(404, {"error": "not found"})
            return
        self.server.authorization_headers.append(self.headers.get("Authorization", ""))
        if (
            self.server.reconcile_override_deploy_id
            and "netlify publish same-id" in self.server.command_log.read_text(encoding="utf-8")
        ):
            self.server.current_deploy_id = self.server.reconcile_override_deploy_id
            self.server.current_deploy_url = self.server.reconcile_override_deploy_url
        prior = None
        if self.server.current_deploy_id:
            prior = {
                "id": self.server.current_deploy_id,
                "site_id": SITE_ID,
                "deploy_ssl_url": self.server.current_deploy_url,
                "state": "ready",
            }
        self.server.append_log("netlify get-current-site")
        self.send_json(
            200,
            {
                "id": SITE_ID,
                "state": self.server.site_state,
                "disabled": self.server.site_disabled,
                "ssl_url": PRODUCTION_URL,
                "published_deploy": prior,
            },
        )

    def do_PUT(self) -> None:
        if urlsplit(self.path).path == f"/api/v1/sites/{SITE_ID}/disable":
            self.server.authorization_headers.append(self.headers.get("Authorization", ""))
            if not self.server.disable_keeps_enabled:
                self.server.site_disabled = True
            self.server.append_log("netlify disable-site")
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
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
    current_deploy_id: str
    current_deploy_url: str
    site_state: str
    site_disabled: bool
    publish_switches_alias: bool
    publish_error_after_switch: bool
    restore_keeps_candidate: bool
    disable_keeps_enabled: bool
    reconcile_override_deploy_id: str
    reconcile_override_deploy_url: str
    site_files_response: object
    change_site_after_files: bool

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
        self.checkout_path_record = self.root / "checkout-path"
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
        self.command = self.repo / "scripts/creator-web-deploy.sh"
        self.deploy_root = self.repo / "build/deploy/creator-web"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=5)
        self.temporary.cleanup()
        self.assertEqual(snapshot_tree(REAL_EVIDENCE_ROOT), self.real_evidence_before)

    def reset_server(self) -> None:
        self.server.deploy_id = DEPLOY_ID
        self.server.deploy_url = f"https://{DEPLOY_ID}--lmdj-creator.netlify.app"
        self.server.published_id = DEPLOY_ID
        self.server.published_site_id = SITE_ID
        self.server.production_url = PRODUCTION_URL
        self.server.published_state = "ready"
        self.server.current_deploy_id = PRIOR_DEPLOY_ID
        self.server.current_deploy_url = (
            f"https://{PRIOR_DEPLOY_ID}--lmdj-creator.netlify.app"
        )
        self.server.site_state = "current"
        self.server.site_disabled = False
        self.server.publish_switches_alias = True
        self.server.publish_error_after_switch = False
        self.server.restore_keeps_candidate = False
        self.server.disable_keeps_enabled = False
        self.server.reconcile_override_deploy_id = ""
        self.server.reconcile_override_deploy_url = ""
        self.server.site_files_response = [
            {
                "id": "prior-index",
                "path": "/index.html",
                "sha": "a" * 40,
                "mime_type": "text/html",
                "size": 13,
            }
        ]
        self.server.change_site_after_files = False
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
        command = self.copy_source(SOURCE_COMMAND, "scripts/creator-web-deploy.sh")
        command.chmod(0o755)
        self.copy_source(
            SOURCE_HELPER, "apps/creator-web/tools/deploy_orchestrator.py"
        )
        self.copy_source(
            SOURCE_RELEASE_BUNDLE, "apps/creator-web/tools/release_bundle.py"
        )
        self.copy_source(SOURCE_RELEASE_INIT, "tools/release/__init__.py")
        self.copy_source(SOURCE_RELEASE_COMMANDS, "tools/release/commands.py")
        self.copy_source(SOURCE_RELEASE_OPENPGP, "tools/release/openpgp.py")
        self.copy_source(SOURCE_WEB_HOST_BUNDLE, "tools/release/web_host_bundle.py")
        self.copy_source(SOURCE_WEB_DEPLOY_INIT, "tools/web_deploy/__init__.py")
        self.copy_source(
            SOURCE_RELEASE_SELECTION,
            "tools/web_deploy/release_selection.py",
        )
        self.copy_source(SOURCE_TAG_VERIFIER, "tools/release/tag_verifier.py")
        api_base = f"http://127.0.0.1:{self.server.server_port}/api/v1"
        netlify_source = SOURCE_NETLIFY.read_text(encoding="utf-8")
        original = '"https://api.netlify.com/api/v1"'
        self.assertEqual(netlify_source.count(original), 1)
        isolated_netlify = self.repo / "apps/creator-web/tools/netlify_api.py"
        isolated_netlify.write_text(
            netlify_source.replace(original, json.dumps(api_base), 1),
            encoding="utf-8",
        )
        headers = self.repo / "apps/creator-web/deploy/_headers"
        headers.parent.mkdir(parents=True)
        headers.write_text("/*\n  X-Robots-Tag: noindex\n", encoding="utf-8")
        key = self.repo / ".github/release-signing-keys/lmdj-product.asc"
        key.parent.mkdir(parents=True)
        key.write_text("test-only public key fixture\n", encoding="utf-8")
        checksum_key = self.repo / ".github/release-signing-keys/lmdj-release-checksum.asc"
        checksum_key.write_text("test-only checksum public key fixture\n", encoding="utf-8")
        smoke = self.repo / "apps/creator-web/tools/deployment_smoke.py"
        smoke.write_text(
            textwrap.dedent(
                f"""
                #!{sys.executable}
                import os
                import json
                from pathlib import Path
                import sys

                for name in os.environ:
                    if (
                        name.startswith("GH")
                        or name in ("GITHUB_TOKEN", "NETLIFY_AUTH_TOKEN", "NETLIFY_CREATOR_SITE_ID")
                    ) and os.environ.get(name):
                        raise SystemExit("deployment credential reached HTTP smoke")
                if len(sys.argv) > 1 and sys.argv[1] == "discover-identity":
                    with Path(os.environ["COMMAND_LOG"]).open("a", encoding="utf-8") as output:
                        output.write("http-discover prior\\n")
                    print(json.dumps({{
                        "host_version": {HOST_VERSION!r},
                        "manifest_sha256": "a" * 64,
                        "product_build": {PRODUCT_BUILD!r},
                    }}, sort_keys=True, separators=(",", ":")))
                    raise SystemExit(0)
                base_url = sys.argv[1]
                immutable = "--expected-deploy-id" in sys.argv
                if {PRIOR_DEPLOY_ID!r} in base_url:
                    label = "prior-immutable"
                else:
                    label = "immutable" if immutable else "production"
                with Path(os.environ["COMMAND_LOG"]).open("a", encoding="utf-8") as output:
                    output.write(f"http-smoke {{label}}\\n")
                should_fail = (
                    label == "immutable" and os.environ.get("FAIL_IMMUTABLE_SMOKE") == "1"
                )
                if label == "production" and os.environ.get("FAIL_PRODUCTION_SMOKE") == "1":
                    marker = Path(os.environ["FAILURE_MARKER"])
                    published = "netlify publish same-id" in Path(os.environ["COMMAND_LOG"]).read_text(encoding="utf-8")
                    should_fail = published and not marker.exists()
                    if should_fail:
                        marker.write_text("failed", encoding="utf-8")
                if should_fail:
                    raise SystemExit(f"forced {{label}} smoke failure")
                log_text = Path(os.environ["COMMAND_LOG"]).read_text(encoding="utf-8")
                publish_position = log_text.rfind("netlify publish same-id")
                restored = log_text.rfind("netlify restore prior-id") > publish_position
                prior = label == "prior-immutable" or (
                    label == "production" and (publish_position < 0 or restored)
                )
                phase = "PRIOR" if prior else "CANDIDATE"
                surface = "IMMUTABLE" if immutable else "PRODUCTION"
                default_index = {PRIOR_INDEX_SHA256!r} if prior else {CANDIDATE_INDEX_SHA256!r}
                default_manifest = {PRIOR_MANIFEST_SHA256!r} if prior else {CANDIDATE_MANIFEST_SHA256!r}
                index_sha256 = os.environ.get(f"FAKE_{{phase}}_{{surface}}_INDEX_SHA", default_index)
                manifest_sha256 = os.environ.get(f"FAKE_{{phase}}_{{surface}}_MANIFEST_SHA", default_manifest)
                expected_product = sys.argv[2]
                expected_host = sys.argv[3]
                result = {{
                    "asset_count": 5,
                    "completed_at": "2026-08-09T00:00:00Z",
                    "host_id": "creator-web",
                    "host_version": expected_host,
                    "index_sha256": index_sha256,
                    "manifest_sha256": manifest_sha256,
                    "product_build": expected_product,
                    "started_at": "2026-08-09T00:00:00Z",
                    "status": "passed",
                    "url": base_url.rstrip("/") + "/",
                }}
                if immutable:
                    result["deploy_id"] = sys.argv[sys.argv.index("--expected-deploy-id") + 1]
                print(json.dumps(result, sort_keys=True, separators=(",", ":")))
                """
            ).lstrip(),
            encoding="utf-8",
        )

    def write_executable(self, name: str, source: str) -> None:
        path = self.bin / name
        path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")
        path.chmod(0o755)

    def write_fake_commands(self) -> None:
        self.write_executable(
            "timeout",
            f"""
            #!{sys.executable}
            import os
            import sys

            args = sys.argv[1:]
            while args and args[0].startswith("--"):
                args.pop(0)
            if not args:
                raise SystemExit(64)
            args.pop(0)
            if not args:
                raise SystemExit(64)
            os.execvp(args[0], args)
            """,
        )
        self.write_executable(
            "env",
            f"""
            #!{sys.executable}
            import json
            import os
            from pathlib import Path
            import sys

            args = sys.argv[1:]
            secrets = tuple(
                value
                for value in (
                    os.environ.get("EXPECTED_GITHUB_TOKEN", ""),
                    os.environ.get("NETLIFY_AUTH_TOKEN", ""),
                )
                if value
            )
            with Path(os.environ["DETAILS_LOG"]).open("a", encoding="utf-8") as output:
                output.write(json.dumps({{
                    "program": "env",
                    "argument_count": len(args),
                    "credential_in_argv": any(
                        secret in argument for argument in args for secret in secrets
                    ),
                }}, sort_keys=True) + "\\n")
            preserved = []
            for name, value in os.environ.items():
                if (
                    name.startswith(("FAKE_", "FAIL_", "BLOCK_"))
                    or name in {{
                        "COMMAND_LOG", "DETAILS_LOG", "CHECKOUT_PATH",
                        "BLOCK_READY", "ARCHIVE_DIGEST",
                        "EXPECTED_GITHUB_TOKEN", "RUNNER_TEMP",
                    }}
                ):
                    preserved.append(f"{{name}}={{value}}")
            forwarded = (
                [args[0], *preserved, *args[1:]]
                if args and args[0] == "-i"
                else args
            )
            os.execv("/usr/bin/env", ["/usr/bin/env", *forwarded])
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
            secrets = tuple(
                value
                for value in (
                    os.environ.get("EXPECTED_GITHUB_TOKEN", ""),
                    os.environ.get("NETLIFY_AUTH_TOKEN", ""),
                )
                if value
            )
            command = ""
            if len(args) >= 2 and args[0].endswith("deploy_orchestrator.py"):
                command = args[1]
            with Path(os.environ["DETAILS_LOG"]).open("a", encoding="utf-8") as output:
                output.write(json.dumps({{
                    "program": "python3",
                    "command": command,
                    "argument_count": len(args),
                    "credential_environment": sorted(
                        name
                        for name in os.environ
                        if name in {{
                            "GITHUB_TOKEN", "GH_TOKEN", "GITHUB_ENTERPRISE_TOKEN",
                            "GH_ENTERPRISE_TOKEN", "NETLIFY_AUTH_TOKEN",
                            "NETLIFY_CREATOR_SITE_ID",
                        }}
                        or name.startswith("GH_")
                    ),
                    "credential_in_argv": any(
                        secret in argument for argument in args for secret in secrets
                    ),
                }}, sort_keys=True) + "\\n")
            os.execv(sys.executable, [sys.executable, *args])
            """,
        )
        package_verifier = """import json
import os
from pathlib import Path

def verify_distribution(dist_root, repo_root):
    manifest = json.loads((dist_root / "host-manifest.json").read_text(encoding="utf-8"))
    product = json.loads((repo_root / "products/lmdj/version.json").read_text(encoding="utf-8"))
    expected_product = ".".join(str(product[name]) for name in ("milestone", "minor", "build", "patch"))
    host = json.loads((repo_root / "apps/creator-web/module.json").read_text(encoding="utf-8"))
    if manifest.get("product_build") != expected_product or manifest.get("host_version") != host["version"]:
        raise RuntimeError("fixture distribution identity mismatch")
    if not isinstance(manifest.get("assets"), list) or len(manifest["assets"]) != 9:
        raise RuntimeError("fixture asset identity mismatch")
    actual = sorted(path.relative_to(dist_root).as_posix() for path in dist_root.rglob("*") if path.is_file())
    expected_files = sorted(["host-manifest.json", "index.html", *[asset["path"] for asset in manifest["assets"]]])
    if actual != expected_files:
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
            home=''
            previous=''
            for argument in "$@"; do
              if [ "$previous" = '--homedir' ]; then
                home="$argument"
              fi
              previous="$argument"
            done
            for required in --batch --no-tty --no-autostart --homedir; do
              case " $* " in *" $required "*) ;; *) exit 70 ;; esac
            done
            if [ "${{GPG_OPERATION_LOG:-}}" ]; then
              printf '%s\n' "$*" >> "$GPG_OPERATION_LOG"
            fi
            case " $* " in
              *" --show-keys "*)
                printf 'pub:-:4096:1:116ECE156F954D29:0:0::::::\nfpr:::::::::{TRUSTED_TAG_FINGERPRINT}:\n'
                ;;
              *" --list-keys "*)
                fingerprint="$(cat "$home/lmdj-imported-fingerprint")"
                printf 'pub:-:255:22:AAC3E7019FC1478B:0:0::::::\nfpr:::::::::%s:\n' "$fingerprint"
                ;;
              *" --import "*)
                case " $* " in
                  *"lmdj-product.asc"*) fingerprint='{TRUSTED_TAG_FINGERPRINT}' ;;
                  *) fingerprint='{TRUSTED_CHECKSUM_FINGERPRINT}' ;;
                esac
                if [ -n "$home" ]; then
                  printf '%s' "$fingerprint" > "$home/lmdj-imported-fingerprint"
                fi
                ;;
              *" --verify "*)
                if [ "${{FAIL_TAG_VERIFY:-}}" = 1 ]; then exit 1; fi
                for argument in "$@"; do
                  case "$argument" in
                    *.asc) grep -q 'wrong-signature' "$argument" && exit 1 ;;
                  esac
                done
                fingerprint="${{FAKE_SIGNATURE_FINGERPRINT:-$(cat "$home/lmdj-imported-fingerprint")}}"
                printf '[GNUPG:] VALIDSIG %s 2026-08-10 0 4 0 22 8 00 %s\n' "$fingerprint" "$fingerprint"
                ;;
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
            import sys

            raw_args = sys.argv[1:]
            args = raw_args.copy()
            git_config = []
            while args[:1] == ["-c"]:
                if len(args) < 2:
                    raise SystemExit(64)
                git_config.append(args[1])
                args = args[2:]
            git_cwd = None
            if args[:1] == ["-C"]:
                if len(args) < 3:
                    raise SystemExit(64)
                git_cwd = Path(args[1])
                args = args[2:]
            log = Path(os.environ["COMMAND_LOG"])
            target = os.environ.get("FAKE_TAG_TARGET", {TAG_TARGET!r})
            product_build = os.environ.get("FAKE_PRODUCT_BUILD", {PRODUCT_BUILD!r})

            def populate_checkout(checkout):
                checkout.joinpath("products/lmdj").mkdir(parents=True)
                checkout.joinpath("apps/creator-web/tools").mkdir(parents=True)
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
                checkout.joinpath("apps/creator-web/module.json").write_text(
                    json.dumps({{
                        "contract": "lmdj.module.v1",
                        "module": "creator-web",
                        "version": {HOST_VERSION!r},
                        "api_version": 1,
                        "dependencies": {{}},
                    }}),
                    encoding="utf-8",
                )
                checkout.joinpath("apps/creator-web/tools/package.py").write_text(
                    {package_verifier!r},
                    encoding="utf-8",
                )

            def record_uncredentialed_checkout(program):
                observed = sorted(
                    name for name in (
                        "GITHUB_TOKEN", "NETLIFY_AUTH_TOKEN", "NETLIFY_CREATOR_SITE_ID",
                    ) if os.environ.get(name)
                )
                with Path(os.environ["DETAILS_LOG"]).open("a", encoding="utf-8") as output:
                    output.write(json.dumps({{
                        "program": program,
                        "credential_environment": observed,
                        "credential_in_argv": os.environ["EXPECTED_GITHUB_TOKEN"] in raw_args,
                        "lfs_skip_smudge": os.environ.get("GIT_LFS_SKIP_SMUDGE", ""),
                    }}, sort_keys=True) + "\\n")
                if observed:
                    raise SystemExit("deployment credential reached tag checkout")

            if args[:3] == ["remote", "get-url", "origin"]:
                print(os.environ.get("FAKE_ORIGIN_URL", "https://github.com/endaye/lmdj.git"))
            elif args[:2] == ["update-ref", "-d"]:
                pass
            elif args[:2] == ["fetch", "--no-tags"]:
                if git_cwd is not None:
                    record_uncredentialed_checkout("git-fetch-local")
                    with log.open("a", encoding="utf-8") as output:
                        output.write("git fetch detached tag\\n")
                    raise SystemExit(0)
                if os.environ.get("FAIL_REMOTE_FETCH") == "1":
                    raise SystemExit(1)
                if os.environ.get("FAKE_PRIVATE_FETCH") == "1":
                    if os.environ.get("GITHUB_TOKEN") != os.environ["EXPECTED_GITHUB_TOKEN"]:
                        raise SystemExit("private canonical fetch was not authenticated")
                    if os.environ.get("NETLIFY_AUTH_TOKEN") or os.environ.get("NETLIFY_CREATOR_SITE_ID"):
                        raise SystemExit("Netlify credential reached authenticated Git fetch")
                    if "credential.username=x-access-token" not in git_config:
                        raise SystemExit("authenticated Git fetch username was not pinned")
                    helpers = [
                        value for value in git_config
                        if value.startswith("credential.helper=")
                    ]
                    if len(helpers) != 1 or "$GITHUB_TOKEN" not in helpers[0]:
                        raise SystemExit("authenticated Git fetch helper was not pinned")
                    with Path(os.environ["DETAILS_LOG"]).open("a", encoding="utf-8") as output:
                        output.write(json.dumps({{
                            "program": "git-fetch",
                            "credential_environment": sorted(
                                name for name in (
                                    "GITHUB_TOKEN", "NETLIFY_AUTH_TOKEN",
                                    "NETLIFY_CREATOR_SITE_ID",
                                ) if os.environ.get(name)
                            ),
                            "credential_in_argv": os.environ["EXPECTED_GITHUB_TOKEN"] in raw_args,
                        }}, sort_keys=True) + "\\n")
                with log.open("a", encoding="utf-8") as output:
                    output.write(f"git remote fetch {{args[-1]}}\\n")
            elif args[:2] == ["cat-file", "-t"]:
                print(os.environ.get("FAKE_TAG_TYPE", "tag"))
            elif args[:1] == ["cat-file"]:
                # Real git rejects a bare `cat-file <object>`; the fake must be
                # exactly as strict, or an invalid invocation in the deploy
                # script only fails on real runners (issue #349).
                if len(args) != 3 or args[1] != "tag":
                    raise SystemExit("git cat-file requires <type> <object>")
                print(
                    "object " + target + "\\n"
                    "type commit\\n"
                    "tag " + {TAG!r} + "\\n"
                    "tagger fixture <fixture@example.invalid> 0 +0000\\n\\n"
                    "fixture tag\\n"
                    "-----BEGIN PGP SIGNATURE-----\\n"
                    "fixture\\n"
                    "-----END PGP SIGNATURE-----"
                )
            elif args[:2] == ["rev-parse", "--verify"]:
                print(target)
            elif args[:2] == ["merge-base", "--is-ancestor"]:
                if os.environ.get("FAKE_TAG_NOT_MAIN") == "1":
                    raise SystemExit(1)
            elif args[:1] == ["clone"]:
                record_uncredentialed_checkout("git-clone")
                checkout = Path(args[-1])
                checkout.mkdir()
                checkout.joinpath(".git").mkdir()
                Path(os.environ["CHECKOUT_PATH"]).write_text(str(checkout), encoding="utf-8")
                with log.open("a", encoding="utf-8") as output:
                    output.write("git clone detached\\n")
            elif args[:1] == ["init"]:
                record_uncredentialed_checkout("git-init")
                checkout = Path(args[-1])
                checkout.mkdir()
                checkout.joinpath(".git").mkdir()
                Path(os.environ["CHECKOUT_PATH"]).write_text(str(checkout), encoding="utf-8")
                with log.open("a", encoding="utf-8") as output:
                    output.write("git init detached\\n")
            elif args[:2] == ["checkout", "--detach"] and git_cwd is not None:
                record_uncredentialed_checkout("git-checkout")
                if (
                    os.environ.get("REQUIRE_LFS_SKIP_SMUDGE") == "1"
                    and os.environ.get("GIT_LFS_SKIP_SMUDGE") != "1"
                ):
                    raise SystemExit("LFS smudge was not disabled")
                populate_checkout(git_cwd)
                with log.open("a", encoding="utf-8") as output:
                    output.write("git checkout detached\\n")
            elif args[:3] == ["worktree", "add", "--detach"]:
                if os.environ.get("REJECT_LINKED_WORKTREE") == "1":
                    raise SystemExit("linked worktrees are unavailable")
                checkout = Path(args[3])
                populate_checkout(checkout)
                Path(os.environ["CHECKOUT_PATH"]).write_text(str(checkout), encoding="utf-8")
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
            if os.environ.get("NETLIFY_AUTH_TOKEN") or os.environ.get("NETLIFY_CREATOR_SITE_ID"):
                raise SystemExit("Netlify credential reached GitHub child")
            if os.environ.get("GITHUB_TOKEN") != os.environ["EXPECTED_GITHUB_TOKEN"]:
                raise SystemExit("intended GitHub credential was not selected")
            log = Path(os.environ["COMMAND_LOG"])
            if args[:1] == ["api"]:
                if args[1:2] != ["repos/endaye/lmdj/branches/main"]:
                    raise SystemExit("GitHub repository was not pinned")
                print(os.environ.get("FAKE_MAIN_PROTECTED", "true"))
                raise SystemExit(0)
            if args.count("--repo") != 1 or args[args.index("--repo") + 1] != "endaye/lmdj":
                raise SystemExit("GitHub repository was not pinned")
            if args[:2] == ["release", "view"]:
                tag = args[2]
                product_build = tag.removeprefix("lmdj-v")
                archive = os.environ.get(
                    "FAKE_ARCHIVE_NAME",
                    f"lmdj-creator-web-{HOST_VERSION}-product-{{product_build}}.zip",
                )
                checksum = os.environ.get("FAKE_CHECKSUM_NAME", archive + ".sha256")
                signature = os.environ.get("FAKE_SIGNATURE_NAME", checksum + ".asc")
                runtime = f"lmdj-web-runtime-host-2.1.1-product-{{product_build}}.zip"
                assets = [
                    {{"name": archive}},
                    {{"name": checksum}},
                    {{"name": signature}},
                    {{"name": runtime}},
                    {{"name": runtime + ".sha256"}},
                    {{"name": runtime + ".sha256.asc"}},
                ]
                if os.environ.get("FAKE_DUPLICATE_ARCHIVE") == "1":
                    assets.append({{"name": archive}})
                if os.environ.get("FAKE_RELEASE_SECRET_FIELD") == "1":
                    assets[0]["label"] = os.environ["GITHUB_TOKEN"]
                if "--jq" in args:
                    assets = [{{"name": asset["name"]}} for asset in assets]
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
                product_build = tag.removeprefix("lmdj-v")
                patterns = [args[index + 1] for index, value in enumerate(args) if value == "--pattern"]
                if patterns:
                    archive_name = next(name for name in patterns if name.endswith(".zip"))
                    checksum_name = next(name for name in patterns if name.endswith(".zip.sha256"))
                    signature_name = next(name for name in patterns if name.endswith(".zip.sha256.asc"))
                else:
                    archive_name = os.environ.get(
                        "FAKE_ARCHIVE_NAME",
                        f"lmdj-creator-web-{HOST_VERSION}-product-{{product_build}}.zip",
                    )
                    checksum_name = os.environ.get("FAKE_CHECKSUM_NAME", archive_name + ".sha256")
                    signature_name = os.environ.get("FAKE_SIGNATURE_NAME", checksum_name + ".asc")
                destination.mkdir(parents=True, exist_ok=True)
                assets = [{{
                    "bytes": 1,
                    "path": f"assets/asset-{{index}}.{{str(index) * 64}}.mjs",
                    "role": "host_module",
                    "sha256": str(index) * 64,
                }} for index in range(9)]
                manifest = {fixture_manifest(PRODUCT_BUILD)!r}.replace({PRODUCT_BUILD!r}, product_build)
                archive_path = destination / archive_name
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr("dist/index.html", "fixture index")
                    archive.writestr("dist/host-manifest.json", manifest)
                    for asset in assets:
                        archive.writestr("dist/" + asset["path"], "x")
                digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
                (destination / checksum_name).write_text(
                    f"{{digest}}  {{archive_name}}\\n", encoding="utf-8"
                )
                if os.environ.get("FAKE_MISSING_SIGNATURE") != "1":
                    signature_payload = (
                        "wrong-signature"
                        if os.environ.get("FAKE_WRONG_SIGNATURE") == "1"
                        else "fixture"
                    )
                    (destination / signature_name).write_text(
                        "-----BEGIN PGP SIGNATURE-----\\n" + signature_payload
                        + "\\n-----END PGP SIGNATURE-----\\n",
                        encoding="ascii",
                    )
                runtime_name = f"lmdj-web-runtime-host-2.1.1-product-{{product_build}}.zip"
                runtime_path = destination / runtime_name
                runtime_path.write_bytes(b"runtime")
                runtime_digest = hashlib.sha256(runtime_path.read_bytes()).hexdigest()
                (destination / (runtime_name + ".sha256")).write_text(
                    f"{{runtime_digest}}  {{runtime_name}}\\n", encoding="ascii"
                )
                (destination / (runtime_name + ".sha256.asc")).write_text(
                    "-----BEGIN PGP SIGNATURE-----\\nfixture\\n"
                    "-----END PGP SIGNATURE-----\\n", encoding="ascii"
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
            import time

            for name in os.environ:
                if (
                    name.startswith("GH")
                    or name in ("GITHUB_TOKEN", "NETLIFY_AUTH_TOKEN", "NETLIFY_CREATOR_SITE_ID")
                ) and os.environ.get(name):
                    raise SystemExit("deployment credential reached browser smoke")
            base_url = os.environ.get("LMDJ_CREATOR_WEB_BASE_URL", "")
            immutable = base_url != {PRODUCTION_URL!r}
            label = (
                "prior-immutable"
                if {PRIOR_DEPLOY_ID!r} in base_url
                else "immutable" if immutable else "production"
            )
            with Path(os.environ["COMMAND_LOG"]).open("a", encoding="utf-8") as output:
                output.write(f"playwright {{label}}\\n")
            if label == "production" and os.environ.get("BLOCK_PRODUCTION_PLAYWRIGHT") == "1":
                marker = Path(os.environ["BLOCK_ONCE_MARKER"])
                published = "netlify publish same-id" in Path(os.environ["COMMAND_LOG"]).read_text(encoding="utf-8")
                if published and not marker.exists():
                    marker.write_text("blocked", encoding="utf-8")
                    Path(os.environ["BLOCK_READY"]).write_text("ready", encoding="utf-8")
                    while True:
                        time.sleep(1)
            should_fail = label == "immutable" and os.environ.get("FAIL_IMMUTABLE_PLAYWRIGHT") == "1"
            if label == "production" and os.environ.get("FAIL_PRODUCTION_PLAYWRIGHT") == "1":
                marker = Path(os.environ["FAILURE_MARKER"])
                published = "netlify publish same-id" in Path(os.environ["COMMAND_LOG"]).read_text(encoding="utf-8")
                should_fail = published and not marker.exists()
                if should_fail:
                    marker.write_text("failed", encoding="utf-8")
            if should_fail:
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
                "CHECKOUT_PATH": str(self.checkout_path_record),
                "BLOCK_READY": str(self.block_ready),
                "ARCHIVE_DIGEST": str(self.root / "archive-digest"),
                "FAILURE_MARKER": str(self.root / "failure-marker"),
                "BLOCK_ONCE_MARKER": str(self.root / "block-once-marker"),
                "RUNNER_TEMP": str(self.runner_temp),
                "GITHUB_TOKEN": GITHUB_TOKEN,
                "GITHUB_RUN_ID": GITHUB_RUN_ID,
                "GITHUB_REPOSITORY": "endaye/lmdj",
                "GITHUB_SERVER_URL": "https://github.com",
                "EXPECTED_GITHUB_TOKEN": GITHUB_TOKEN,
                "NETLIFY_CREATOR_SITE_ID": SITE_ID,
                "NETLIFY_AUTH_TOKEN": NETLIFY_TOKEN,
                "GH_REPO": "attacker/example",
                "GH_TOKEN": "higher-precedence-hostile-token",
                "GH_HOST": "attacker.example",
                "GH_SECRET_SENTINEL": "must-not-reach-deployment-children",
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
            self.checkout_path_record,
            self.block_ready,
            self.root / "archive-digest",
            self.root / "failure-marker",
            self.root / "block-once-marker",
        ):
            path.unlink(missing_ok=True)
        shutil.rmtree(self.deploy_root, ignore_errors=True)
        self.reset_server()

    def wait_for_block_ready(
        self,
        process: "subprocess.Popen[str]",
        stages: int,
        stage_label: str,
    ) -> None:
        """Wait for a spawned deploy to reach its blocking sentinel.

        The budget is proportional to the pipeline stages the wait covers, and
        the failure names the elapsed time, the budget, the sentinel path and
        the stages actually reached, so a recurrence is diagnosable from the
        run log alone without reading this harness.
        """
        budget = READINESS_STARTUP_SECONDS + READINESS_PER_STAGE_SECONDS * stages
        started = time.monotonic()
        while not self.block_ready.exists() and process.poll() is None:
            elapsed = time.monotonic() - started
            if elapsed >= budget:
                reached = self.command_log()
                process.kill()
                self.fail(
                    f"{stage_label} did not become ready after {elapsed:.1f}s "
                    f"(budget {budget:.1f}s = {READINESS_STARTUP_SECONDS:.1f}s "
                    f"startup + {stages} stages x "
                    f"{READINESS_PER_STAGE_SECONDS:.1f}s); why: the sentinel "
                    f"{self.block_ready} was never written; the deploy reached "
                    f"{len(reached)} stages: {reached}. Remedy: if the last "
                    "stage shows the deploy still progressing, the host was "
                    "slower than this budget - raise "
                    "READINESS_PER_STAGE_SECONDS; otherwise the deploy stalled "
                    "at the stage after the last one listed."
                )
            time.sleep(0.02)

    def assert_no_owned_temp(self) -> None:
        self.assertEqual(list(self.runner_temp.glob("lmdj-creator-web-deploy.*")), [])

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
            "  scripts/creator-web-deploy.sh verify TAG\n"
            "  scripts/creator-web-deploy.sh deploy TAG\n"
            "  scripts/creator-web-deploy.sh smoke BASE_URL PRODUCT_BUILD HOST_VERSION\n",
        )

    def test_deploy_orders_real_stage_api_smoke_restore_and_production_smoke(self) -> None:
        completed = self.run_command("deploy", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            self.command_log(),
            [
                f"git remote fetch refs/tags/{TAG}:refs/lmdj-deploy/tags/{TAG}",
                "git remote fetch refs/heads/main:refs/lmdj-deploy/origin-main",
                "git init detached",
                "git fetch detached tag",
                "git checkout detached",
                f"gh release view {TAG}",
                f"gh release download {TAG}",
                "release_bundle stage",
                "netlify get-current-site",
                "netlify get-current-files",
                "netlify get-current-site",
                "http-discover prior",
                "http-smoke prior-immutable",
                "playwright prior-immutable",
                "http-smoke production",
                "playwright production",
                "netlify create-draft",
                "http-smoke immutable",
                "playwright immutable",
                "netlify publish same-id",
                "http-smoke production",
                "playwright production",
            ],
        )
        create = cast(dict[str, object], self.server.create_document)
        files = set(cast(dict[str, str], create["files"]))
        self.assertEqual(len(files), 12)
        self.assertTrue({"/_headers", "/host-manifest.json", "/index.html"}.issubset(files))
        self.assertEqual(len([path for path in files if path.startswith("/assets/")]), 9)
        self.assertEqual(
            self.server.authorization_headers,
            [f"Bearer {NETLIFY_TOKEN}"] * 5,
        )

    def test_dual_release_validates_full_inventory_and_stages_creator_triplet(self) -> None:
        completed = self.run_command("verify", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("release_bundle stage", self.command_log())

    def test_product_tag_verification_uses_the_agentless_gpg_boundary(self) -> None:
        gpg_log = self.root / "gpg-operations.log"
        completed = self.run_command("verify", TAG, environment={"GPG_OPERATION_LOG": str(gpg_log)})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        operations = gpg_log.read_text(encoding="utf-8").splitlines()
        verified = [
            operation for operation in operations
            if " --verify " in f" {operation} " and "tag.asc" in operation and "tag.payload" in operation
        ]
        self.assertEqual(len(verified), 1)
        self.assertIn("--batch --no-tty --no-autostart --homedir", verified[0])
        self.assertNotIn("git tag verify", self.command_log())

    def test_empty_initial_published_deploy_is_treated_as_first_publication(self) -> None:
        self.server.site_files_response = []
        completed = self.run_command("deploy", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        log = self.command_log()
        self.assertEqual(
            log[log.index("release_bundle stage") + 1 : log.index("netlify create-draft")],
            [
                "netlify get-current-site",
                "netlify get-current-files",
                "netlify get-current-site",
            ],
        )
        self.assertNotIn("http-discover prior", log)
        evidence = json.loads(
            (self.deploy_root / "evidence.json").read_text(encoding="utf-8")
        )
        self.assertIsNone(evidence["prior_good"])

    def test_site_identity_change_during_file_inventory_fails_before_draft(self) -> None:
        self.server.site_files_response = []
        self.server.change_site_after_files = True
        completed = self.run_command("deploy", TAG)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("changed during file inventory", completed.stderr)
        self.assertNotIn("netlify create-draft", self.command_log())

    def test_release_stage_uses_real_bundle_wrapper_and_detached_tag_checkout(self) -> None:
        completed = self.run_command("verify", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        detail = next(item for item in self.details() if "release_bundle_repo_root" in item)
        checkout = Path(str(detail["release_bundle_repo_root"]))
        self.assertEqual(len(cast(list[str], detail["dist_files"])), 11)
        self.assertNotEqual(checkout, self.repo)
        self.assertEqual(checkout.name, "tag-target")
        # `create_owned_temp` in scripts/creator-web-deploy.sh prefers RUNNER_TEMP but
        # deliberately falls back to /tmp when the requested parent would push a
        # projected GnuPG agent socket past its length budget. A macOS
        # TemporaryDirectory lives under /private/var/folders/... and exceeds that
        # budget, so on this platform the documented fallback fires and the
        # checkout legitimately lands under /tmp. Pinning RUNNER_TEMP specifically
        # therefore asserted the Linux runner's path length, not the contract. The
        # contract is that the tag checkout lives in an owned temp root the script
        # created, outside the repository.
        resolved = Path(checkout).resolve()
        allowed_parents = (self.runner_temp.resolve(), Path("/tmp").resolve())
        self.assertTrue(
            any(resolved.is_relative_to(parent) for parent in allowed_parents),
            resolved,
        )
        self.assertTrue(resolved.parent.name.startswith("lmdj-creator-web-deploy."), resolved)
        self.assertFalse(checkout.exists())

    def test_tag_checkout_does_not_require_linked_worktree_metadata(self) -> None:
        completed = self.run_command(
            "verify", TAG, environment={"REJECT_LINKED_WORKTREE": "1"}
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("git init detached", self.command_log())
        self.assertIn("git fetch detached tag", self.command_log())
        self.assertIn("git checkout detached", self.command_log())
        checkout_details = [
            detail for detail in self.details()
            if detail.get("program")
            in {"git-init", "git-fetch-local", "git-checkout"}
        ]
        self.assertEqual(len(checkout_details), 3)
        for detail in checkout_details:
            self.assertEqual(detail["credential_environment"], [])
            self.assertFalse(detail["credential_in_argv"])
        checkout = next(
            detail
            for detail in checkout_details
            if detail["program"] == "git-checkout"
        )
        self.assertEqual(checkout["lfs_skip_smudge"], "1")

    def test_tag_checkout_materializes_remote_ref_without_lfs_smudge(self) -> None:
        completed = self.run_command(
            "verify",
            TAG,
            environment={"REQUIRE_LFS_SKIP_SMUDGE": "1"},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("git clone detached", self.command_log())
        self.assertIn("git init detached", self.command_log())
        self.assertIn("git fetch detached tag", self.command_log())
        self.assertIn("git checkout detached", self.command_log())
        checkout_details = [
            detail
            for detail in self.details()
            if detail.get("program")
            in {"git-init", "git-fetch-local", "git-checkout"}
        ]
        self.assertEqual(len(checkout_details), 3)
        for detail in checkout_details:
            self.assertEqual(detail["credential_environment"], [])
            self.assertFalse(detail["credential_in_argv"])
        checkout = next(
            detail
            for detail in checkout_details
            if detail["program"] == "git-checkout"
        )
        self.assertEqual(checkout["lfs_skip_smudge"], "1")

    def test_publish_accepts_additive_official_response_fields(self) -> None:
        self.server.restore_extra = {
            "published_at": "2026-08-09T00:00:00.740Z",
            "admin_url": "https://app.netlify.com/sites/lmdj-creator",
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
                self.assertNotIn("Creator Web Host deployment: PASS", completed.stdout)

    def test_missing_each_secret_fails_before_tag_verification(self) -> None:
        for name in ("GITHUB_TOKEN", "NETLIFY_CREATOR_SITE_ID", "NETLIFY_AUTH_TOKEN"):
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
            {"FAKE_SIGNATURE_FINGERPRINT": TRUSTED_CHECKSUM_FINGERPRINT},
            {"FAIL_TAG_VERIFY": "1"},
        ):
            with self.subTest(environment=environment):
                self.reset_run_records()
                completed = self.run_command("deploy", TAG, environment=environment)
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn("gh release view", "\n".join(self.command_log()))
                self.assert_no_owned_temp()

    def test_ignores_local_tag_shadow_and_attests_only_canonical_remote_ref(self) -> None:
        completed = self.run_command(
            "verify", TAG, environment={"FAKE_LOCAL_TAG_TARGET": "f" * 40}
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("git tag verify", self.command_log())

    def test_accepts_actions_checkout_canonical_origin_url(self) -> None:
        completed = self.run_command(
            "verify",
            TAG,
            environment={"FAKE_ORIGIN_URL": "https://github.com/endaye/lmdj"},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_authenticates_private_canonical_fetch_without_credential_leakage(self) -> None:
        completed = self.run_command(
            "verify", TAG, environment={"FAKE_PRIVATE_FETCH": "1"}
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        fetch_details = [
            detail for detail in self.details() if detail.get("program") == "git-fetch"
        ]
        self.assertEqual(len(fetch_details), 2)
        for detail in fetch_details:
            self.assertEqual(detail["credential_environment"], ["GITHUB_TOKEN"])
            self.assertFalse(detail["credential_in_argv"])

    def test_rejects_noncanonical_origin_unprotected_main_and_non_main_tag(self) -> None:
        for environment in (
            {"FAKE_ORIGIN_URL": "https://github.com/attacker/lmdj.git"},
            {"FAKE_MAIN_PROTECTED": "false"},
            {"FAKE_TAG_NOT_MAIN": "1"},
        ):
            with self.subTest(environment=environment):
                self.reset_run_records()
                completed = self.run_command("verify", TAG, environment=environment)
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn(f"gh release view {TAG}", self.command_log())

    def test_release_is_exact_published_canary_target_and_canonical_url(self) -> None:
        failures = (
            {"FAKE_RELEASE_DRAFT": "1"},
            {"FAKE_RELEASE_PRERELEASE": "0"},
            {"FAKE_RELEASE_TAG": "lmdj-v1.0.15.4"},
            {"FAKE_RELEASE_URL": f"https://attacker.example/releases/tag/{TAG}"},
            {"FAKE_RELEASE_URL": f"https://github.com/attacker/lmdj/releases/tag/{TAG}"},
        )
        for environment in failures:
            with self.subTest(environment=environment):
                self.reset_run_records()
                completed = self.run_command("deploy", TAG, environment=environment)
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn(f"gh release download {TAG}", self.command_log())

        completed = self.run_command(
            "verify", TAG, environment={"FAKE_RELEASE_TARGET": "main"}
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_hostile_gh_environment_is_neutralized_and_repo_is_pinned(self) -> None:
        completed = self.run_command("verify", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            [value for value in self.command_log() if value.startswith("gh release")],
            [f"gh release view {TAG}", f"gh release download {TAG}"],
        )

    def test_github_token_is_inherited_without_argv_assignment(self) -> None:
        completed = self.run_command("verify", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        env_invocations = [
            detail for detail in self.details() if detail.get("program") == "env"
        ]
        self.assertTrue(env_invocations)
        self.assertFalse(
            any(detail["credential_in_argv"] for detail in env_invocations)
        )
        source = SOURCE_COMMAND.read_text(encoding="utf-8")
        self.assertNotIn('GITHUB_TOKEN="$GITHUB_TOKEN"', source)

    def test_each_child_receives_only_its_required_deployment_credentials(self) -> None:
        completed = self.run_command("deploy", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        netlify_commands = {
            "create-draft", "publish", "site-current", "site-preflight", "disable-site"
        }
        for detail in self.details():
            if detail.get("program") != "python3":
                continue
            observed = set(cast(list[str], detail["credential_environment"]))
            if detail.get("command") in netlify_commands:
                self.assertEqual(
                    observed, {"NETLIFY_AUTH_TOKEN", "NETLIFY_CREATOR_SITE_ID"}
                )
            else:
                self.assertEqual(observed, set(), detail)

    def test_release_metadata_uses_stdin_without_credential_argv(self) -> None:
        completed = self.run_command(
            "verify", TAG, environment={"FAKE_RELEASE_SECRET_FIELD": "1"}
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        invocation = next(
            detail
            for detail in self.details()
            if detail.get("program") == "python3"
            and detail.get("command") == "release-metadata"
        )
        self.assertEqual(invocation["argument_count"], 6)
        self.assertFalse(invocation["credential_in_argv"])
        self.assertNotIn(GITHUB_TOKEN, self.details_path.read_text(encoding="utf-8"))
        self.assert_no_secret_output(completed)

    def test_verify_missing_github_token_fails_before_tag_work(self) -> None:
        completed = self.run_command(
            "verify", TAG, environment={"GITHUB_TOKEN": ""}
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(self.command_log(), [])
        self.assertEqual(
            completed.stderr,
            "Creator Web deployment error: required environment is missing: "
            "GITHUB_TOKEN\n",
        )
        self.assert_no_owned_temp()

    def test_rejects_duplicate_or_mismatched_release_assets(self) -> None:
        failures = (
            {"FAKE_DUPLICATE_ARCHIVE": "1"},
            {"FAKE_ARCHIVE_NAME": "lmdj-creator-web-1.2.0-product-1.0.99.0.zip"},
            {"FAKE_ARCHIVE_NAME": "lmdj-creator-web-9.9.9-product-1.0.15.3.zip"},
            {"FAKE_CHECKSUM_NAME": "wrong.zip.sha256"},
            {"FAKE_SIGNATURE_NAME": "wrong.zip.sha256.asc"},
        )
        for environment in failures:
            with self.subTest(environment=environment):
                self.reset_run_records()
                completed = self.run_command("deploy", TAG, environment=environment)
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn(f"gh release download {TAG}", self.command_log())

    def test_future_coherent_archive_and_checksum_require_valid_checksum_signature(self) -> None:
        for environment in (
            {"FAKE_MISSING_SIGNATURE": "1"},
            {"FAKE_WRONG_SIGNATURE": "1"},
        ):
            with self.subTest(environment=environment):
                self.reset_run_records()
                completed = self.run_command("deploy", TAG, environment=environment)
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn("release_bundle stage", self.command_log())
                self.assertNotIn("netlify create-draft", self.command_log())

    def test_product_tag_key_cannot_substitute_for_checksum_key(self) -> None:
        command = self.repo / "scripts/creator-web-deploy.sh"
        source = command.read_text(encoding="utf-8")
        checksum_key = "lmdj-release-checksum.asc"
        self.assertEqual(source.count(checksum_key), 1)
        command.write_text(
            source.replace(checksum_key, "lmdj-product.asc"),
            encoding="utf-8",
        )
        completed = self.run_command("verify", TAG)
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("release_bundle stage", self.command_log())
        self.assertNotIn("netlify create-draft", self.command_log())

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

    def test_prior_good_requires_identical_immutable_and_production_bytes(self) -> None:
        completed = self.run_command(
            "deploy",
            TAG,
            environment={"FAKE_PRIOR_PRODUCTION_INDEX_SHA": "e" * 64},
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("netlify create-draft", self.command_log())

    def test_candidate_immutable_must_match_staged_release_bytes(self) -> None:
        completed = self.run_command(
            "deploy",
            TAG,
            environment={"FAKE_CANDIDATE_IMMUTABLE_MANIFEST_SHA": "e" * 64},
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("netlify publish same-id", self.command_log())

    def test_candidate_production_byte_mismatch_restores_prior(self) -> None:
        completed = self.run_command(
            "deploy",
            TAG,
            environment={"FAKE_CANDIDATE_PRODUCTION_INDEX_SHA": "e" * 64},
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("netlify restore prior-id", self.command_log())
        recovery = json.loads(
            (self.deploy_root / "recovery-evidence.json").read_text(encoding="utf-8")
        )
        self.assertEqual(recovery["status"], "passed")

    def test_reconcile_rejects_unknown_third_deploy_id(self) -> None:
        self.server.reconcile_override_deploy_id = "unknown-789"
        self.server.reconcile_override_deploy_url = (
            "https://unknown-789--lmdj-creator.netlify.app"
        )
        completed = self.run_command(
            "deploy", TAG, environment={"FAIL_PRODUCTION_SMOKE": "1"}
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("netlify restore prior-id", self.command_log())
        recovery = json.loads(
            (self.deploy_root / "recovery-evidence.json").read_text(encoding="utf-8")
        )
        self.assertEqual(recovery["action"], "unsafe-unknown-alias")
        self.assertEqual(recovery["status"], "failed")

    def test_restore_requires_post_action_get_to_confirm_exact_prior(self) -> None:
        self.server.restore_keeps_candidate = True
        completed = self.run_command(
            "deploy", TAG, environment={"FAIL_PRODUCTION_SMOKE": "1"}
        )
        self.assertNotEqual(completed.returncode, 0)
        recovery = json.loads(
            (self.deploy_root / "recovery-evidence.json").read_text(encoding="utf-8")
        )
        self.assertEqual(recovery["action"], "restored-prior")
        self.assertEqual(recovery["status"], "failed")
        self.assertEqual(
            recovery["post_recovery_site"]["published_deploy"]["id"], DEPLOY_ID
        )

    def test_disable_requires_post_action_get_to_confirm_disabled_state(self) -> None:
        self.server.current_deploy_id = ""
        self.server.current_deploy_url = ""
        self.server.disable_keeps_enabled = True
        completed = self.run_command(
            "deploy", TAG, environment={"FAIL_PRODUCTION_SMOKE": "1"}
        )
        self.assertNotEqual(completed.returncode, 0)
        recovery = json.loads(
            (self.deploy_root / "recovery-evidence.json").read_text(encoding="utf-8")
        )
        self.assertEqual(recovery["action"], "disabled-first-publication")
        self.assertEqual(recovery["recovery_response"], {"status_code": 204})
        self.assertEqual(recovery["status"], "failed")
        self.assertEqual(recovery["post_recovery_site"]["state"], "current")

    def test_failed_production_smoke_restores_prior_and_writes_atomic_recovery_evidence(self) -> None:
        completed = self.run_command(
            "deploy", TAG, environment={"FAIL_PRODUCTION_SMOKE": "1"}
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("netlify publish same-id", self.command_log())
        self.assertFalse((self.deploy_root / "evidence.json").exists())
        recovery_path = self.deploy_root / "recovery-evidence.json"
        recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
        self.assertEqual(
            recovery["contract"],
            "lmdj.creator-web.deployment-recovery-evidence.v1",
        )
        self.assertEqual(recovery["action"], "restored-prior")
        self.assertEqual(recovery["prior_deploy"]["id"], PRIOR_DEPLOY_ID)
        self.assertEqual(recovery["recovery_response"]["id"], PRIOR_DEPLOY_ID)
        self.assertEqual(recovery["validation"]["status"], "passed")
        self.assertEqual(recovery["validation"]["immutable_http"]["status"], "passed")
        self.assertEqual(recovery["validation"]["production_browser"]["status"], "passed")

    def test_first_publication_failure_disables_site_instead_of_fake_rollback(self) -> None:
        self.server.current_deploy_id = ""
        self.server.current_deploy_url = ""
        completed = self.run_command(
            "deploy", TAG, environment={"FAIL_PRODUCTION_SMOKE": "1"}
        )
        self.assertNotEqual(completed.returncode, 0)
        log = self.command_log()
        self.assertIn("netlify publish same-id", log)
        self.assertIn("netlify disable-site", log)
        self.assertNotIn("netlify restore prior-id", log)
        self.assertTrue(self.server.site_disabled)
        recovery = json.loads(
            (self.deploy_root / "recovery-evidence.json").read_text(encoding="utf-8")
        )
        self.assertEqual(recovery["action"], "disabled-first-publication")
        self.assertIsNone(recovery["prior_deploy"])
        self.assertEqual(recovery["recovery_response"], {"status_code": 204})
        self.assertEqual(recovery["status"], "passed")
        self.assertEqual(recovery["post_recovery_site"]["state"], "disabled")

    def test_publish_api_error_reconciles_alias_and_restores_exact_prior(self) -> None:
        self.server.publish_error_after_switch = True
        completed = self.run_command("deploy", TAG)
        self.assertNotEqual(completed.returncode, 0)
        log = self.command_log()
        publish_index = log.index("netlify publish same-id")
        self.assertIn("netlify get-current-site", log[publish_index:])
        self.assertIn("netlify restore prior-id", log[publish_index:])
        self.assertEqual(self.server.current_deploy_id, PRIOR_DEPLOY_ID)
        self.assertTrue((self.deploy_root / "recovery-evidence.json").is_file())

    def test_publish_error_accepts_only_exact_prior_still_current(self) -> None:
        self.server.publish_switches_alias = False
        self.server.publish_error_after_switch = True
        completed = self.run_command("deploy", TAG)
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("netlify restore prior-id", self.command_log())
        recovery = json.loads(
            (self.deploy_root / "recovery-evidence.json").read_text(encoding="utf-8")
        )
        self.assertEqual(recovery["action"], "prior-still-current")
        self.assertEqual(recovery["status"], "passed")
        self.assertEqual(recovery["post_recovery_site"], recovery["reconcile"])

    def test_first_publish_error_with_no_alias_is_safe_no_publication(self) -> None:
        self.server.current_deploy_id = ""
        self.server.current_deploy_url = ""
        self.server.publish_switches_alias = False
        self.server.publish_error_after_switch = True
        completed = self.run_command("deploy", TAG)
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("netlify disable-site", self.command_log())
        recovery = json.loads(
            (self.deploy_root / "recovery-evidence.json").read_text(encoding="utf-8")
        )
        self.assertEqual(recovery["action"], "no-publication")
        self.assertEqual(recovery["status"], "passed")
        self.assertIsNone(recovery["reconcile"]["published_deploy"])

    def test_pre_disabled_site_refuses_automatic_enable_or_publication(self) -> None:
        self.server.site_disabled = True
        completed = self.run_command("deploy", TAG)
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("netlify create-draft", self.command_log())
        self.assertNotIn("netlify publish same-id", self.command_log())

    def test_owned_tag_checkout_and_temp_are_removed_on_success_and_failure(self) -> None:
        for environment in ({}, {"FAIL_IMMUTABLE_SMOKE": "1"}):
            with self.subTest(environment=environment):
                self.reset_run_records()
                completed = self.run_command("deploy", TAG, environment=environment)
                self.assertEqual(completed.returncode == 0, not environment)
                checkout = Path(self.checkout_path_record.read_text(encoding="utf-8"))
                self.assertFalse(checkout.exists())
                self.assert_no_owned_temp()

    def test_success_writes_exact_atomic_evidence_without_credentials(self) -> None:
        completed = self.run_command("deploy", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        raw = (self.deploy_root / "evidence.json").read_text(encoding="utf-8")
        digest = (self.root / "archive-digest").read_text(encoding="utf-8")
        evidence = json.loads(raw)
        self.assertEqual(
            set(evidence),
            {
                "archive", "channel", "contract", "ended_at", "git_revision",
                "github_actions", "host_version", "immutable", "prior_good",
                "product_build", "production", "publication", "release_url",
                "release_files", "site_id", "started_at", "tag",
            },
        )
        self.assertEqual(
            evidence["archive"],
            {
                "filename": f"lmdj-creator-web-{HOST_VERSION}-product-{PRODUCT_BUILD}.zip",
                "sha256": digest,
            },
        )
        self.assertEqual(evidence["contract"], "lmdj.creator-web.deployment-evidence.v1")
        self.assertEqual(
            evidence["release_files"],
            {
                "index_sha256": CANDIDATE_INDEX_SHA256,
                "manifest_sha256": CANDIDATE_MANIFEST_SHA256,
            },
        )
        self.assertEqual(
            evidence["github_actions"],
            {
                "run_id": GITHUB_RUN_ID,
                "run_url": f"https://github.com/endaye/lmdj/actions/runs/{GITHUB_RUN_ID}",
            },
        )
        self.assertEqual(evidence["immutable"]["deploy_id"], DEPLOY_ID)
        self.assertEqual(evidence["immutable"]["http"]["status"], "passed")
        self.assertEqual(
            evidence["immutable"]["http"]["result"]["asset_count"], 5
        )
        self.assertEqual(evidence["immutable"]["browser"]["status"], "passed")
        self.assertEqual(evidence["publication"]["same_deploy_id"], DEPLOY_ID)
        self.assertEqual(evidence["publication"]["response"]["id"], DEPLOY_ID)
        self.assertEqual(evidence["production"]["url"], PRODUCTION_URL)
        self.assertEqual(evidence["production"]["http"]["status"], "passed")
        self.assertEqual(
            evidence["production"]["http"]["result"]["asset_count"], 5
        )
        self.assertEqual(evidence["production"]["browser"]["status"], "passed")
        self.assertEqual(evidence["prior_good"]["deploy_id"], PRIOR_DEPLOY_ID)
        self.assertEqual(
            evidence["prior_good"]["immutable"]["http"]["result"][
                "asset_count"
            ],
            5,
        )
        self.assertRegex(evidence["started_at"], r"Z$")
        self.assertRegex(evidence["ended_at"], r"Z$")
        self.assertEqual(
            raw, json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n"
        )
        self.assert_no_secret_output(completed)
        self.assertNotIn(GITHUB_TOKEN, raw)
        self.assertNotIn(NETLIFY_TOKEN, raw)

    def test_rejects_credentials_in_release_draft_or_additive_restore_values(self) -> None:
        cases = ("draft", "draft-additive", "restore")
        for case in cases:
            with self.subTest(case=case):
                self.reset_run_records()
                environment: dict[str, str] = {}
                if case == "draft":
                    self.server.deploy_id = GITHUB_TOKEN
                    self.server.deploy_url = (
                        f"https://{GITHUB_TOKEN}--lmdj-creator.netlify.app"
                    )
                elif case == "draft-additive":
                    self.server.create_extra = {"diagnostic": NETLIFY_TOKEN}
                else:
                    self.server.restore_extra = {"diagnostic": NETLIFY_TOKEN}
                completed = self.run_command("deploy", TAG, environment=environment)
                self.assertNotEqual(completed.returncode, 0)
                self.assert_no_secret_output(completed)
                self.assertFalse((self.deploy_root / "evidence.json").exists())
                if case in {"draft", "draft-additive"}:
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
                "NETLIFY_CREATOR_SITE_ID": "",
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
                self.wait_for_block_ready(
                    process, GH_DOWNLOAD_READY_STAGES, "blocked gh download"
                )
                os.killpg(process.pid, selected_signal)
                stdout, stderr = process.communicate(timeout=SHUTDOWN_BUDGET_SECONDS)
                self.assertIn(process.returncode, {expected, -selected_signal})
                completed = subprocess.CompletedProcess(
                    process.args, process.returncode, stdout, stderr
                )
                self.assert_no_secret_output(completed)
                self.assertNotIn("netlify publish same-id", self.command_log())
                self.assertFalse((self.deploy_root / "evidence.json").exists())
                checkout = Path(self.checkout_path_record.read_text(encoding="utf-8"))
                self.assertFalse(checkout.exists())
                self.assert_no_owned_temp()

    def test_post_publish_int_and_term_reconcile_and_restore_prior_good(self) -> None:
        for selected_signal, expected in ((signal.SIGINT, 130), (signal.SIGTERM, 143)):
            with self.subTest(signal=selected_signal):
                self.reset_run_records()
                process = subprocess.Popen(
                    [str(self.command), "deploy", TAG],
                    cwd=self.repo,
                    env=self.environment({"BLOCK_PRODUCTION_PLAYWRIGHT": "1"}),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                )
                self.wait_for_block_ready(
                    process, POST_PUBLISH_READY_STAGES, "post-publish Playwright"
                )
                os.killpg(process.pid, selected_signal)
                stdout, stderr = process.communicate(timeout=SHUTDOWN_BUDGET_SECONDS)
                self.assertIn(process.returncode, {expected, -selected_signal})
                completed = subprocess.CompletedProcess(
                    process.args, process.returncode, stdout, stderr
                )
                self.assert_no_secret_output(completed)
                log = self.command_log()
                self.assertIn("netlify publish same-id", log)
                self.assertIn("netlify get-current-site", log)
                self.assertIn("netlify restore prior-id", log)
                restore_index = log.index("netlify restore prior-id")
                self.assertIn("http-smoke prior-immutable", log[restore_index:])
                self.assertIn("playwright prior-immutable", log[restore_index:])
                self.assertIn("http-smoke production", log[restore_index:])
                self.assertIn("playwright production", log[restore_index:])
                self.assertEqual(self.server.current_deploy_id, PRIOR_DEPLOY_ID)
                recovery = json.loads(
                    (self.deploy_root / "recovery-evidence.json").read_text(encoding="utf-8")
                )
                self.assertEqual(recovery["action"], "restored-prior")
                self.assert_no_owned_temp()

    def test_deploy_contract_lane_registers_isolated_command_test(self) -> None:
        workflow = (SOURCE_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        match = re.search(
            r"^  deploy-contract:\n(?P<body>.*?)(?=^  [a-z0-9-]+:|\Z)",
            workflow,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, "ci.yml is missing the deploy-contract job")
        assert match is not None
        job = match.group("body")
        relative = "apps/creator-web/test/deploy_command_test.py"
        self.assertEqual(job.count(relative), 1)
        host_script = (SOURCE_ROOT / "scripts/creator-web.sh").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(relative, host_script)
        forbidden_real_cleanup = "shutil.rmtree(" + "REAL_EVIDENCE_ROOT"
        self.assertNotIn(forbidden_real_cleanup, Path(__file__).read_text())


SHARD_ENV = "LMDJ_DEPLOY_COMMAND_TEST_SHARDS"
DEFAULT_SHARD_CEILING = 4

# Every other test in this file is hermetic and load-insensitive: it builds its
# own repository, fake-command directory, and fake Netlify server on port 0.
# These two are the only ones with wall-clock budgets. They drive the deploy
# command to a blocking point, signal its process group, and then assert on
# bounded readiness and post-signal cleanup windows, so competing shard load
# can exceed the window and fail a correct command. They run alone after the
# parallel phase instead of being weakened or dropped.
SERIAL_TEST_IDS = (
    "DeployCommandTest.test_int_and_term_cleanup_owned_state_without_restore_or_evidence",
    "DeployCommandTest.test_post_publish_int_and_term_reconcile_and_restore_prior_good",
)


def relative_test_id(test_id: str) -> str:
    """Return an id `unittest` can resolve against this file's `__main__`."""
    prefix = "__main__."
    return test_id[len(prefix):] if test_id.startswith(prefix) else test_id


def discover_test_ids() -> list[str]:
    """Return every test id this file defines, in a deterministic order."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules["__main__"])
    if getattr(loader, "errors", None):
        raise SystemExit("test discovery failed:\n" + "\n".join(loader.errors))

    collected: list[str] = []

    def walk(item: object) -> None:
        if isinstance(item, unittest.TestSuite):
            for child in item:
                walk(child)
            return
        collected.append(relative_test_id(cast(unittest.TestCase, item).id()))

    walk(suite)
    if not collected:
        raise SystemExit("test discovery found no tests")
    if len(set(collected)) != len(collected):
        raise SystemExit("test discovery produced duplicate test ids")
    return sorted(collected)


def resolve_shard_count(requested: int | None) -> int:
    """Resolve the shard count from the flag, the environment, or the default."""
    if requested is not None:
        count = requested
    else:
        raw = os.environ.get(SHARD_ENV, "").strip()
        if raw:
            try:
                count = int(raw)
            except ValueError:
                raise SystemExit(f"{SHARD_ENV} is not an integer: {raw!r}") from None
        else:
            count = min(DEFAULT_SHARD_CEILING, os.cpu_count() or 1)
    if count < 1:
        raise SystemExit(f"shard count must be at least 1, got {count}")
    return count


class ShardRecordingResult(unittest.TextTestResult):
    """A result that records exactly which tests the shard actually started."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.executed_ids: list[str] = []

    def startTest(self, test: unittest.TestCase) -> None:
        self.executed_ids.append(relative_test_id(test.id()))
        super().startTest(test)


def run_shard(report_path: str, test_ids: list[str]) -> int:
    """Run one shard's tests in this process and report what it executed."""
    if not test_ids:
        raise SystemExit("a shard worker requires at least one test id")
    suite = unittest.TestLoader().loadTestsFromNames(
        test_ids, sys.modules["__main__"]
    )
    result = unittest.TextTestRunner(
        verbosity=2, stream=sys.stderr, resultclass=ShardRecordingResult
    ).run(suite)
    Path(report_path).write_text(
        json.dumps(
            {
                "executed": getattr(result, "executed_ids", []),
                "successful": result.wasSuccessful(),
            }
        ),
        encoding="utf-8",
    )
    return 0 if result.wasSuccessful() else 1


def run_worker_phase(
    groups: list[tuple[str, list[str]]], directory: Path, self_path: str
) -> tuple[list[str], list[str]]:
    """Run one phase of worker processes concurrently and report the outcome."""
    workers = []
    for label, bucket in groups:
        slug = label.replace(" ", "-")
        report = directory / f"{slug}.json"
        log = directory / f"{slug}.log"
        handle = log.open("wb")
        process = subprocess.Popen(
            [sys.executable, self_path, "--shard-report", str(report), *bucket],
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        workers.append((label, bucket, process, handle, report, log))

    executed: list[str] = []
    failed: list[str] = []
    for label, bucket, process, handle, report, log in workers:
        returncode = process.wait()
        handle.close()
        successful = False
        if report.exists():
            try:
                payload = json.loads(report.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {}
            executed.extend(payload.get("executed", []))
            successful = bool(payload.get("successful"))
        if returncode != 0 or not successful:
            failed.append(label)
            sys.stderr.write(
                f"\n===== {label} failed: exit {returncode}, "
                f"{len(bucket)} assigned tests =====\n"
            )
            sys.stderr.write(log.read_text(encoding="utf-8", errors="replace"))
        else:
            sys.stderr.write(f"{label}: {len(bucket)} tests OK\n")
        sys.stderr.flush()
    return executed, failed


def run_sharded(shards: int) -> int:
    """Run the suite across worker processes, failing closed on any drift."""
    test_ids = discover_test_ids()
    unknown_serial = sorted(set(SERIAL_TEST_IDS) - set(test_ids))
    if unknown_serial:
        raise SystemExit(
            "SERIAL_TEST_IDS names tests this file no longer defines: "
            + ", ".join(unknown_serial)
        )
    serial_ids = [test_id for test_id in test_ids if test_id in SERIAL_TEST_IDS]
    parallel_ids = [test_id for test_id in test_ids if test_id not in SERIAL_TEST_IDS]

    parallel_groups = [
        (f"shard {index} of {shards}", bucket)
        for index, bucket in enumerate(
            parallel_ids[offset::shards] for offset in range(shards)
        )
        if bucket
    ]
    phases = [parallel_groups]
    if serial_ids:
        phases.append([("serial phase", serial_ids)])

    started = time.monotonic()
    executed: list[str] = []
    failed: list[str] = []
    self_path = str(Path(__file__).resolve())
    with tempfile.TemporaryDirectory(prefix="lmdj-deploy-command-shards-") as directory:
        for phase in phases:
            if not phase:
                continue
            phase_executed, phase_failed = run_worker_phase(
                phase, Path(directory), self_path
            )
            executed.extend(phase_executed)
            failed.extend(phase_failed)

    duration = time.monotonic() - started
    missing = sorted(set(test_ids) - set(executed))
    unexpected = sorted(set(executed) - set(test_ids))
    status = 1 if failed else 0
    if len(executed) != len(test_ids) or missing or unexpected:
        status = 1
        sys.stderr.write(
            f"\nshard accounting failed: discovered {len(test_ids)} tests, "
            f"executed {len(executed)}\n"
        )
        if missing:
            sys.stderr.write("never executed: " + ", ".join(missing) + "\n")
        if unexpected:
            sys.stderr.write("unexpected: " + ", ".join(unexpected) + "\n")

    sys.stderr.write(
        f"\nRan {len(executed)} of {len(test_ids)} discovered tests across "
        f"{len(parallel_groups)} shards plus {len(serial_ids)} serial tests "
        f"in {duration:.3f}s: {'FAILED' if status else 'OK'}\n"
    )
    if failed:
        sys.stderr.write("failed workers: " + ", ".join(failed) + "\n")
    sys.stderr.flush()
    return status


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--shards", type=int, default=None)
    parser.add_argument("--shard-report", default=None)
    options, rest = parser.parse_known_args(argv[1:])

    if options.shard_report is not None:
        return run_shard(options.shard_report, rest)
    if rest:
        # Explicit test selection or unittest flags keep the serial behavior.
        unittest.main(argv=[argv[0], *rest])
    shards = resolve_shard_count(options.shards)
    if shards == 1:
        unittest.main(argv=[argv[0]])
    return run_sharded(shards)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
