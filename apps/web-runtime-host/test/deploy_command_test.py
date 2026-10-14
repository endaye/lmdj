#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from typing import cast


SOURCE_ROOT = Path(__file__).resolve().parents[3]
SOURCE_COMMAND = SOURCE_ROOT / "scripts/web-runtime-deploy.sh"
SOURCE_HELPER = SOURCE_ROOT / "apps/web-runtime-host/tools/deploy_orchestrator.py"
SOURCE_RELEASE_BUNDLE = SOURCE_ROOT / "apps/web-runtime-host/tools/release_bundle.py"
SOURCE_RELEASE_INIT = SOURCE_ROOT / "tools/release/__init__.py"
SOURCE_RELEASE_COMMANDS = SOURCE_ROOT / "tools/release/commands.py"
SOURCE_RELEASE_OPENPGP = SOURCE_ROOT / "tools/release/openpgp.py"
SOURCE_WEB_HOST_BUNDLE = SOURCE_ROOT / "tools/release/web_host_bundle.py"
SOURCE_WEB_DEPLOY_INIT = SOURCE_ROOT / "tools/web_deploy/__init__.py"
SOURCE_RELEASE_SELECTION = SOURCE_ROOT / "tools/web_deploy/release_selection.py"
SOURCE_TAG_VERIFIER = SOURCE_ROOT / "tools/release/tag_verifier.py"
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
CLOUDFLARE_TOKEN = "cloudflare-secret-value-should-never-leak"


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


class DeployCommandTest(unittest.TestCase):
    def setUp(self) -> None:
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

        self.prepare_isolated_repository()
        self.write_fake_commands()
        self.command = self.repo / "scripts/web-runtime-deploy.sh"

    def tearDown(self) -> None:
        self.temporary.cleanup()

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
        key = self.repo / ".github/release-signing-keys/lmdj-product.asc"
        key.parent.mkdir(parents=True)
        key.write_text("test-only public key fixture\n", encoding="utf-8")
        checksum_key = self.repo / ".github/release-signing-keys/lmdj-release-checksum.asc"
        checksum_key.write_text("test-only checksum public key fixture\n", encoding="utf-8")
    def write_executable(self, name: str, source: str) -> None:
        path = self.bin / name
        path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")
        path.chmod(0o755)

    def write_fake_commands(self) -> None:
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
                            "GH_ENTERPRISE_TOKEN", "CLOUDFLARE_API_TOKEN",
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
    host = json.loads((repo_root / "apps/web-runtime-host/module.json").read_text(encoding="utf-8"))
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

            def record_uncredentialed_checkout(program):
                observed = sorted(
                    name for name in (
                        "GITHUB_TOKEN", "CLOUDFLARE_API_TOKEN",
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
                    if os.environ.get("CLOUDFLARE_API_TOKEN"):
                        raise SystemExit("Cloudflare credential reached authenticated Git fetch")
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
                                    "GITHUB_TOKEN", "CLOUDFLARE_API_TOKEN",
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
            if os.environ.get("CLOUDFLARE_API_TOKEN"):
                raise SystemExit("Cloudflare credential reached GitHub child")
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
                    f"lmdj-web-runtime-host-{HOST_VERSION}-product-{{product_build}}.zip",
                )
                checksum = os.environ.get("FAKE_CHECKSUM_NAME", archive + ".sha256")
                signature = os.environ.get("FAKE_SIGNATURE_NAME", checksum + ".asc")
                assets = [{{"name": archive}}, {{"name": checksum}}, {{"name": signature}}]
                if os.environ.get("FAKE_DUAL_RELEASE") == "1":
                    creator = f"lmdj-creator-web-2.1.1-product-{{product_build}}.zip"
                    assets = [
                        {{"name": creator}},
                        {{"name": creator + ".sha256"}},
                        {{"name": creator + ".sha256.asc"}},
                        *assets,
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
                        f"lmdj-web-runtime-host-{HOST_VERSION}-product-{{product_build}}.zip",
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
                if os.environ.get("FAKE_DUAL_RELEASE") == "1":
                    creator_name = f"lmdj-creator-web-2.1.1-product-{{product_build}}.zip"
                    creator_path = destination / creator_name
                    creator_path.write_bytes(b"creator")
                    creator_digest = hashlib.sha256(creator_path.read_bytes()).hexdigest()
                    (destination / (creator_name + ".sha256")).write_text(
                        f"{{creator_digest}}  {{creator_name}}\\n", encoding="ascii"
                    )
                    (destination / (creator_name + ".sha256.asc")).write_text(
                        "-----BEGIN PGP SIGNATURE-----\\nfixture\\n"
                        "-----END PGP SIGNATURE-----\\n", encoding="ascii"
                    )
                Path(os.environ["ARCHIVE_DIGEST"]).write_text(digest, encoding="utf-8")
            else:
                raise SystemExit(97)
            """,
        )
    def environment(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.bin}{os.pathsep}{environment['PATH']}",
                "COMMAND_LOG": str(self.log_path),
                "DETAILS_LOG": str(self.details_path),
                "CHECKOUT_PATH": str(self.checkout_path_record),
                "BLOCK_READY": str(self.block_ready),
                "ARCHIVE_DIGEST": str(self.root / "archive-digest"),
                "RUNNER_TEMP": str(self.runner_temp),
                "GITHUB_TOKEN": GITHUB_TOKEN,
                "EXPECTED_GITHUB_TOKEN": GITHUB_TOKEN,
                "CLOUDFLARE_API_TOKEN": CLOUDFLARE_TOKEN,
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
        ):
            path.unlink(missing_ok=True)

    def assert_no_owned_temp(self) -> None:
        self.assertEqual(list(self.runner_temp.glob("lmdj-web-runtime-deploy.*")), [])

    def assert_no_secret_output(self, completed: subprocess.CompletedProcess[str]) -> None:
        combined = completed.stdout + completed.stderr
        self.assertNotIn(GITHUB_TOKEN, combined)
        self.assertNotIn(CLOUDFLARE_TOKEN, combined)

    def test_usage_is_exact(self) -> None:
        completed = self.run_command()
        self.assertEqual(completed.returncode, 64)
        self.assertEqual(
            completed.stderr,
            "usage:\n"
            "  scripts/web-runtime-deploy.sh verify TAG\n"
            "  scripts/web-runtime-deploy.sh stage TAG ABSOLUTE_OUTPUT_DIRECTORY\n"
        )

    def test_the_removed_netlify_verbs_are_usage_errors_that_run_nothing(self) -> None:
        for arguments in (("deploy", TAG), ("smoke", "https://example.invalid", PRODUCT_BUILD, "1.2.0")):
            with self.subTest(verb=arguments[0]):
                self.reset_run_records()
                completed = self.run_command(*arguments)
                self.assertEqual(completed.returncode, 64)
                self.assertTrue(completed.stderr.startswith("usage:\n"), completed.stderr)
                self.assertEqual(self.command_log(), [])

    def test_dual_release_validates_full_inventory_and_stages_runtime_triplet(self) -> None:
        completed = self.run_command(
            "verify", TAG, environment={"FAKE_DUAL_RELEASE": "1"}
        )
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

    def test_release_stage_uses_real_bundle_wrapper_and_detached_tag_checkout(self) -> None:
        completed = self.run_command("verify", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        detail = next(item for item in self.details() if "release_bundle_repo_root" in item)
        checkout = Path(str(detail["release_bundle_repo_root"]))
        self.assertEqual(len(cast(list[str], detail["dist_files"])), 11)
        self.assertNotEqual(checkout, self.repo)
        self.assertEqual(checkout.name, "tag-target")
        # `create_owned_temp` in scripts/web-runtime-deploy.sh prefers RUNNER_TEMP but
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
        self.assertTrue(resolved.parent.name.startswith("lmdj-web-runtime-deploy."), resolved)
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
                completed = self.run_command("verify", value)
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
                completed = self.run_command("verify", TAG, environment=environment)
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
                completed = self.run_command("verify", TAG, environment=environment)
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

    def test_no_orchestrator_child_receives_a_deployment_credential(self) -> None:
        completed = self.run_command("verify", TAG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        children = [
            detail for detail in self.details() if detail.get("program") == "python3"
        ]
        self.assertTrue(children)
        for detail in children:
            self.assertEqual(detail["credential_environment"], [], detail)

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

    def test_stage_rejects_invalid_signature_before_retaining_files(self) -> None:
        output = self.root / "retained-stage"
        completed = self.run_command("stage", TAG, str(output), environment={"FAKE_WRONG_SIGNATURE": "1"})
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("verification failed", completed.stderr)
        self.assertFalse(output.exists())

    def test_cloudflare_token_is_removed_before_git_verification(self) -> None:
        command = self.bin / "git"
        first, rest = command.read_text().split("\n", 1)
        command.write_text(first + "\nimport os\nif os.environ.get('CLOUDFLARE_API_TOKEN'): raise SystemExit('unexpected Cloudflare credential')\n" + rest)
        completed = self.run_command("verify", TAG, environment={"CLOUDFLARE_API_TOKEN": "test-only-cf-credential"})
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_verify_missing_github_token_fails_before_tag_work(self) -> None:
        completed = self.run_command(
            "verify", TAG, environment={"GITHUB_TOKEN": ""}
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(self.command_log(), [])
        self.assertEqual(
            completed.stderr,
            "Web Runtime deployment error: required environment is missing: "
            "GITHUB_TOKEN\n",
        )
        self.assert_no_owned_temp()

    def test_rejects_duplicate_or_mismatched_release_assets(self) -> None:
        failures = (
            {"FAKE_DUPLICATE_ARCHIVE": "1"},
            {"FAKE_ARCHIVE_NAME": "lmdj-web-runtime-host-1.2.0-product-1.0.99.0.zip"},
            {"FAKE_ARCHIVE_NAME": "lmdj-web-runtime-host-9.9.9-product-1.0.15.3.zip"},
            {"FAKE_CHECKSUM_NAME": "wrong.zip.sha256"},
            {"FAKE_SIGNATURE_NAME": "wrong.zip.sha256.asc"},
        )
        for environment in failures:
            with self.subTest(environment=environment):
                self.reset_run_records()
                completed = self.run_command("verify", TAG, environment=environment)
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn(f"gh release download {TAG}", self.command_log())

    def test_future_coherent_archive_and_checksum_require_valid_checksum_signature(self) -> None:
        for environment in (
            {"FAKE_MISSING_SIGNATURE": "1"},
            {"FAKE_WRONG_SIGNATURE": "1"},
        ):
            with self.subTest(environment=environment):
                self.reset_run_records()
                completed = self.run_command("verify", TAG, environment=environment)
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn("release_bundle stage", self.command_log())

    def test_product_tag_key_cannot_substitute_for_checksum_key(self) -> None:
        command = self.repo / "scripts/web-runtime-deploy.sh"
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

    def test_initial_tag_requires_exact_target_and_corrected_host_digest(self) -> None:
        completed = self.run_command(
            "verify",
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
            "verify",
            INITIAL_TAG,
            environment={
                "FAKE_PRODUCT_BUILD": "1.0.15.2",
                "FAKE_TAG_TARGET": INITIAL_TAG_TARGET,
            },
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("release_bundle stage", self.command_log())
        helper_source = SOURCE_HELPER.read_text(encoding="utf-8")
        self.assertIn(INITIAL_HOST_DIGEST[:32], helper_source)
        self.assertIn(INITIAL_HOST_DIGEST[32:], helper_source)

    def test_owned_tag_checkout_and_temp_are_removed_on_success_and_failure(self) -> None:
        for environment in ({}, {"FAKE_WRONG_SIGNATURE": "1"}):
            with self.subTest(environment=environment):
                self.reset_run_records()
                completed = self.run_command("verify", TAG, environment=environment)
                self.assertEqual(completed.returncode == 0, not environment)
                checkout = Path(self.checkout_path_record.read_text(encoding="utf-8"))
                self.assertFalse(checkout.exists())
                self.assert_no_owned_temp()

    def test_production_source_pins_github_repo(self) -> None:
        command_source = SOURCE_COMMAND.read_text(encoding="utf-8")
        self.assertIn("--repo endaye/lmdj", command_source)

    def test_int_and_term_cleanup_owned_state(self) -> None:
        for selected_signal, expected in ((signal.SIGINT, 130), (signal.SIGTERM, 143)):
            with self.subTest(signal=selected_signal):
                self.reset_run_records()
                process = subprocess.Popen(
                    [str(self.command), "verify", TAG],
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
                        # The whole group, not the leader. `start_new_session`
                        # made the command a session leader; killing only it
                        # leaves the deploy script's children -- the blocked gh
                        # stub, the fake Playwright -- alive into the next
                        # subcase, which then inherits their load and their
                        # temp state (#454).
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                        self.fail("blocked gh download did not become ready")
                    time.sleep(0.02)
                os.killpg(process.pid, selected_signal)
                stdout, stderr = process.communicate(timeout=10)
                self.assertIn(process.returncode, {expected, -selected_signal})
                completed = subprocess.CompletedProcess(
                    process.args, process.returncode, stdout, stderr
                )
                self.assert_no_secret_output(completed)
                checkout = Path(self.checkout_path_record.read_text(encoding="utf-8"))
                self.assertFalse(checkout.exists())
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
        relative = "apps/web-runtime-host/test/deploy_command_test.py"
        self.assertEqual(job.count(relative), 1)
        host_script = (SOURCE_ROOT / "scripts/web-runtime-host.sh").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(relative, host_script)


SHARD_ENV = "LMDJ_DEPLOY_COMMAND_TEST_SHARDS"
DEFAULT_SHARD_CEILING = 4

# Every other test in this file is hermetic and load-insensitive: it builds its
# own repository and fake-command directory. This one is the only test with
# wall-clock budgets. It drives the command to a blocking point, signals its
# process group, and then asserts on bounded readiness and post-signal cleanup
# windows, so competing shard load can exceed the window and fail a correct
# command. It runs alone after the parallel phase instead of being weakened or
# dropped.
SERIAL_TEST_IDS = (
    "DeployCommandTest.test_int_and_term_cleanup_owned_state",
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


class HarnessIsolationTest(unittest.TestCase):
    """The harness must not be able to contaminate its own next subcase (#454).

    Lives in this file rather than in tests/build so it runs in the same lane
    as the harness it pins: a change here reaches the Deploy contract lane,
    and a contract elsewhere would not run on that change.
    """

    def test_every_session_leader_is_reaped_as_a_group(self) -> None:
        source = Path(__file__).read_text(encoding="utf-8")
        self.assertIn("start_new_session=True", source)
        # Match the call as a statement, so this test's own prose about the
        # call does not trip it (see gate-matches-its-own-prose in the ledger).
        self.assertIsNone(
            re.search(r"^\s*process\.kill\(\)\s*$", source, re.MULTILINE),
            msg=("why: the command is a session leader, so killing only it leaves "
                 "the deploy script's children -- blocked gh stub, fake Playwright "
                 "-- alive into the next subcase, where they consume its readiness "
                 "budget and its temp state; remedy: os.killpg(process.pid, ...) "
                 "followed by process.wait(), never process.kill()"),
        )
        # Statements only, again: this test's own text would otherwise count
        # as a second occurrence and hide the loss of the branch.
        group_kills = re.findall(
            r"^\s*os\.killpg\(process\.pid, signal\.SIGKILL\)\s*$", source, re.MULTILINE
        )
        self.assertEqual(
            len(group_kills), 1,
            "why: exactly one readiness-timeout branch spawns a session leader, "
            "and it must kill its group on timeout; remedy: keep one "
            "os.killpg(...SIGKILL) statement per branch, no more and no fewer",
        )


if __name__ == "__main__":
    sys.exit(main(sys.argv))
