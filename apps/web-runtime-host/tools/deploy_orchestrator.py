#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from netlify_api import DraftDeploy, NetlifyClient, NetlifyError


CANONICAL_GITHUB_REPOSITORY = "endaye/lmdj"
CANONICAL_RELEASE_PREFIX = (
    f"https://github.com/{CANONICAL_GITHUB_REPOSITORY}/releases/tag/"
)
CANONICAL_PRODUCTION_URL = "https://lmdj-runtime.netlify.app"
CANONICAL_NETLIFY_SITE = "lmdj-runtime"
INITIAL_TAG = "lmdj-v1.0.15.2"
INITIAL_TAG_TARGET = "72ae40074620cc5681c462ba04a31a666449734f"
INITIAL_HOST_DIGEST = (
    "d56a7c99a3c489db068b93fcef70a254"
    "b498adf4bc65919253beccb199f3ad5a"
)
PRODUCT_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+")
HOST_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
SHA1_PATTERN = re.compile(r"[0-9a-f]{40}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
DEPLOY_ID_PATTERN = re.compile(r"[A-Za-z0-9-]+")


class DeployOrchestratorError(RuntimeError):
    pass


class _SecretCheckingNetlifyClient(NetlifyClient):
    def __init__(self, *, token: str, secrets: tuple[str, ...]) -> None:
        super().__init__(token=token)
        self._orchestrator_secrets = secrets

    def _json_request(
        self,
        method: str,
        endpoint: str,
        document: object | None,
        deadline: float | None,
    ) -> object:
        response = super()._json_request(method, endpoint, document, deadline)
        reject_secret_material(
            response,
            secrets=self._orchestrator_secrets,
            label="Netlify API response",
        )
        return response


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _secret_values() -> tuple[str, ...]:
    return tuple(
        value
        for name in ("GITHUB_TOKEN", "NETLIFY_AUTH_TOKEN")
        if (value := os.environ.get(name))
    )


def reject_secret_material(
    value: object, *, secrets: tuple[str, ...] | None = None, label: str
) -> None:
    selected = _secret_values() if secrets is None else tuple(secret for secret in secrets if secret)
    if not selected:
        return

    def visit(current: object) -> None:
        if isinstance(current, str):
            if any(secret in current for secret in selected):
                raise DeployOrchestratorError(f"{label} contains credential material")
            return
        if isinstance(current, Mapping):
            for key, nested in current.items():
                visit(key)
                visit(nested)
            return
        if isinstance(current, (list, tuple, set)):
            for nested in current:
                visit(nested)

    visit(value)


def parse_json_document(source: str, label: str) -> dict[str, object]:
    try:
        value = json.loads(source)
    except (TypeError, json.JSONDecodeError) as error:
        raise DeployOrchestratorError(f"{label} is invalid") from error
    if not isinstance(value, dict):
        raise DeployOrchestratorError(f"{label} is invalid")
    reject_secret_material(value, label=label)
    return value


def read_tag_identity(root: Path, expected_product: str) -> tuple[str, str]:
    try:
        product = json.loads(
            (root / "products/lmdj/version.json").read_text(encoding="utf-8")
        )
        host = json.loads(
            (root / "apps/web-runtime-host/module.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DeployOrchestratorError("tag-target identity manifests are invalid") from error
    if not isinstance(product, dict) or set(product) != {
        "contract",
        "product",
        "milestone",
        "minor",
        "build",
        "patch",
    }:
        raise DeployOrchestratorError("tag-target Product identity is invalid")
    if (
        product["contract"] != "lmdj.product-version.v1"
        or product["product"] != "lmdj"
    ):
        raise DeployOrchestratorError("tag-target Product identity is invalid")
    parts = [product[name] for name in ("milestone", "minor", "build", "patch")]
    if any(type(part) is not int or part < 0 for part in parts):
        raise DeployOrchestratorError("tag-target Product identity is invalid")
    observed_product = ".".join(str(part) for part in parts)
    if observed_product != expected_product:
        raise DeployOrchestratorError("tag-target Product Build does not match the tag")
    if (
        not isinstance(host, dict)
        or host.get("contract") != "lmdj.module.v1"
        or host.get("module") != "web-runtime-host"
        or not isinstance(host.get("version"), str)
        or HOST_PATTERN.fullmatch(host["version"]) is None
    ):
        raise DeployOrchestratorError("tag-target Host identity is invalid")
    reject_secret_material(
        (observed_product, host["version"]), label="tag-target identity"
    )
    return observed_product, host["version"]


def parse_release_metadata(
    source: str,
    *,
    tag: str,
    tag_target: str,
    product_build: str,
    host_version: str,
) -> tuple[str, str, str]:
    release = parse_json_document(source, "GitHub Release metadata")
    required = {
        "tagName",
        "isDraft",
        "isPrerelease",
        "targetCommitish",
        "assets",
        "url",
    }
    if set(release) != required:
        raise DeployOrchestratorError("GitHub Release metadata is invalid")
    if release["tagName"] != tag or release["isDraft"] is not False:
        raise DeployOrchestratorError(
            "GitHub Release is not the exact published Product tag"
        )
    if release["isPrerelease"] is not True:
        raise DeployOrchestratorError("GitHub Release is not a canary prerelease")
    if release["targetCommitish"] not in {tag, tag_target}:
        raise DeployOrchestratorError(
            "GitHub Release target does not match the Product tag"
        )
    assets = release["assets"]
    if not isinstance(assets, list) or any(
        not isinstance(asset, dict) for asset in assets
    ):
        raise DeployOrchestratorError("GitHub Release asset inventory is invalid")
    names = [asset.get("name") for asset in assets]
    if any(not isinstance(name, str) or not name for name in names):
        raise DeployOrchestratorError("GitHub Release asset inventory is invalid")
    archive = f"lmdj-web-runtime-host-{host_version}-product-{product_build}.zip"
    checksum = archive + ".sha256"
    host_archives = [
        name
        for name in names
        if name.startswith("lmdj-web-runtime-host-") and name.endswith(".zip")
    ]
    host_checksums = [
        name
        for name in names
        if name.startswith("lmdj-web-runtime-host-")
        and name.endswith(".zip.sha256")
    ]
    if host_archives != [archive] or host_checksums != [checksum]:
        raise DeployOrchestratorError("GitHub Release Host asset identity is invalid")
    expected_release_url = CANONICAL_RELEASE_PREFIX + tag
    if release["url"] != expected_release_url:
        raise DeployOrchestratorError("GitHub Release URL is invalid")
    return archive, checksum, expected_release_url


def validate_downloaded_assets(
    root: Path, archive_name: str, checksum_name: str
) -> None:
    expected = sorted((archive_name, checksum_name))
    try:
        entries = list(root.iterdir())
    except OSError as error:
        raise DeployOrchestratorError(
            "downloaded GitHub Release asset inventory is invalid"
        ) from error
    actual = sorted(
        path.name for path in entries if path.is_file() and not path.is_symlink()
    )
    if actual != expected or any(path.is_dir() or path.is_symlink() for path in entries):
        raise DeployOrchestratorError(
            "downloaded GitHub Release asset inventory is invalid"
        )


def parse_staged_bundle(
    source: str,
    *,
    stage_root: Path,
    product_build: str,
    host_version: str,
    tag: str,
) -> tuple[Path, str]:
    staged = parse_json_document(source, "staged Host bundle result")
    if set(staged) != {
        "archive_sha256",
        "dist_root",
        "host_version",
        "product_build",
    }:
        raise DeployOrchestratorError("staged Host bundle result is invalid")
    try:
        resolved_stage = stage_root.resolve()
        dist_root = Path(str(staged["dist_root"])).resolve(strict=True)
    except OSError as error:
        raise DeployOrchestratorError("staged Host bundle root is invalid") from error
    if (
        dist_root != resolved_stage / "dist"
        or not dist_root.is_dir()
        or dist_root.is_symlink()
    ):
        raise DeployOrchestratorError("staged Host bundle root is invalid")
    digest = staged["archive_sha256"]
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        raise DeployOrchestratorError("staged Host archive digest is invalid")
    if (
        staged["product_build"] != product_build
        or staged["host_version"] != host_version
    ):
        raise DeployOrchestratorError("staged Host identity is invalid")
    if tag == INITIAL_TAG and digest != INITIAL_HOST_DIGEST:
        raise DeployOrchestratorError("initial Host archive SHA-256 mismatch")
    return dist_root, digest


def collect_deploy_files(dist_root: Path, headers_path: Path) -> dict[str, bytes]:
    try:
        dist_root = dist_root.resolve(strict=True)
        headers_path = headers_path.resolve(strict=True)
    except OSError as error:
        raise DeployOrchestratorError("Netlify deploy inputs are unavailable") from error
    if not dist_root.is_dir() or dist_root.is_symlink():
        raise DeployOrchestratorError("staged distribution is unsafe")
    if not headers_path.is_file() or headers_path.is_symlink():
        raise DeployOrchestratorError("Netlify response rules are unavailable")
    files: dict[str, bytes] = {}
    for path in sorted(dist_root.rglob("*")):
        if path.is_symlink():
            raise DeployOrchestratorError("staged distribution contains a symlink")
        if path.is_dir():
            continue
        if not path.is_file():
            raise DeployOrchestratorError(
                "staged distribution contains an unsafe entry"
            )
        files["/" + path.relative_to(dist_root).as_posix()] = path.read_bytes()
    if not files:
        raise DeployOrchestratorError("staged distribution is empty")
    files["/_headers"] = headers_path.read_bytes()
    return files


def validate_draft(
    value: Mapping[str, object], *, site_id: str
) -> dict[str, str]:
    reject_secret_material(value, label="Netlify draft identity")
    required = {"deploy_ssl_url", "id", "site_id", "state"}
    if not required.issubset(value):
        raise DeployOrchestratorError("Netlify draft identity is invalid")
    deploy_id = value["id"]
    if (
        not isinstance(deploy_id, str)
        or DEPLOY_ID_PATTERN.fullmatch(deploy_id) is None
    ):
        raise DeployOrchestratorError("Netlify Deploy ID is invalid")
    if value["site_id"] != site_id or value["state"] != "ready":
        raise DeployOrchestratorError("Netlify draft identity is invalid")
    deploy_url = value["deploy_ssl_url"]
    expected_url = f"https://{deploy_id.lower()}--{CANONICAL_NETLIFY_SITE}.netlify.app"
    if deploy_url != expected_url:
        raise DeployOrchestratorError("Netlify immutable Deploy URL is invalid")
    return {
        "deploy_ssl_url": expected_url,
        "id": deploy_id,
        "site_id": site_id,
        "state": "ready",
    }


def create_draft(
    *,
    dist_root: Path,
    headers_path: Path,
    product_build: str,
    host_version: str,
    tag: str,
    site_id: str,
    token: str,
    client: NetlifyClient | None = None,
) -> dict[str, str]:
    files = collect_deploy_files(dist_root, headers_path)
    selected = (
        _SecretCheckingNetlifyClient(token=token, secrets=_secret_values())
        if client is None
        else client
    )
    draft = selected.create_draft(
        site_id=site_id,
        files=files,
        title=f"LMDJ Product {product_build} Host {host_version} ({tag})",
    )
    if not isinstance(draft, DraftDeploy):
        raise DeployOrchestratorError("Netlify draft identity is invalid")
    return validate_draft(
        {
            "deploy_ssl_url": draft.deploy_ssl_url,
            "id": draft.id,
            "site_id": draft.site_id,
            "state": draft.state,
        },
        site_id=site_id,
    )


def validate_published(
    value: Mapping[str, object], *, site_id: str, deploy_id: str
) -> dict[str, str]:
    reject_secret_material(value, label="Netlify published identity")
    required = {"id", "site_id", "ssl_url", "state"}
    if not required.issubset(value):
        raise DeployOrchestratorError("Netlify published identity is invalid")
    if (
        value["id"] != deploy_id
        or value["site_id"] != site_id
        or value["ssl_url"] != CANONICAL_PRODUCTION_URL
        or value["state"] != "ready"
    ):
        raise DeployOrchestratorError(
            "Netlify published identity is not the same ready Deploy"
        )
    return {
        "id": deploy_id,
        "site_id": site_id,
        "ssl_url": CANONICAL_PRODUCTION_URL,
        "state": "ready",
    }


def publish(
    *,
    site_id: str,
    deploy_id: str,
    token: str,
    client: NetlifyClient | None = None,
) -> dict[str, str]:
    selected = (
        _SecretCheckingNetlifyClient(token=token, secrets=_secret_values())
        if client is None
        else client
    )
    response = selected.publish_deploy(site_id=site_id, deploy_id=deploy_id)
    return validate_published(response, site_id=site_id, deploy_id=deploy_id)


def initialize_evidence_target(repo_root: Path, deploy_root: Path) -> None:
    repo_root = repo_root.resolve(strict=True)
    try:
        relative = deploy_root.relative_to(repo_root)
    except ValueError as error:
        raise DeployOrchestratorError("deployment evidence path is unsafe") from error
    current = repo_root
    for component in relative.parts:
        current = current / component
        if current.exists() or current.is_symlink():
            if current.is_symlink() or not current.is_dir():
                raise DeployOrchestratorError("deployment evidence path is unsafe")
        else:
            current.mkdir()
    evidence = deploy_root / "evidence.json"
    if evidence.is_symlink() or evidence.exists():
        evidence.unlink()


def write_evidence(
    *,
    output: Path,
    archive_sha256: str,
    deploy_id: str,
    deploy_url: str,
    git_revision: str,
    host_version: str,
    product_build: str,
    release_url: str,
    site_id: str,
    tag: str,
) -> None:
    evidence = {
        "archive_sha256": archive_sha256,
        "channel": "canary",
        "contract": "lmdj.web-runtime-host.deployment-evidence.v1",
        "deploy_id": deploy_id,
        "deploy_url": deploy_url,
        "git_revision": git_revision,
        "host_version": host_version,
        "product_build": product_build,
        "production_url": CANONICAL_PRODUCTION_URL,
        "release_url": release_url,
        "site_id": site_id,
        "tag": tag,
    }
    reject_secret_material(evidence, label="deployment evidence")
    if SHA256_PATTERN.fullmatch(archive_sha256) is None:
        raise DeployOrchestratorError("deployment evidence archive digest is invalid")
    if SHA1_PATTERN.fullmatch(git_revision) is None:
        raise DeployOrchestratorError("deployment evidence Git revision is invalid")
    if (
        DEPLOY_ID_PATTERN.fullmatch(deploy_id) is None
        or DEPLOY_ID_PATTERN.fullmatch(site_id) is None
        or deploy_url
        != f"https://{deploy_id.lower()}--{CANONICAL_NETLIFY_SITE}.netlify.app"
        or release_url != CANONICAL_RELEASE_PREFIX + tag
        or PRODUCT_PATTERN.fullmatch(product_build) is None
        or HOST_PATTERN.fullmatch(host_version) is None
    ):
        raise DeployOrchestratorError("deployment evidence live identity is invalid")
    serialized = canonical_json(evidence) + "\n"
    if output.is_symlink() or not output.parent.is_dir() or output.parent.is_symlink():
        raise DeployOrchestratorError("deployment evidence target is unsafe")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".evidence.", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as target:
            target.write(serialized)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary_name, output)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def require_environment(name: str) -> str:
    value = os.environ.get(name, "")
    if not value or "\n" in value or "\r" in value:
        raise DeployOrchestratorError(f"required environment is invalid: {name}")
    return value


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Web Runtime deployment orchestration")
    commands = parser.add_subparsers(dest="command", required=True)

    identity = commands.add_parser("tag-identity")
    identity.add_argument("root", type=Path)
    identity.add_argument("product_build")

    release = commands.add_parser("release-metadata")
    release.add_argument("tag")
    release.add_argument("tag_target")
    release.add_argument("product_build")
    release.add_argument("host_version")

    downloaded = commands.add_parser("downloaded-assets")
    downloaded.add_argument("root", type=Path)
    downloaded.add_argument("archive")
    downloaded.add_argument("checksum")

    staged = commands.add_parser("staged-bundle")
    staged.add_argument("stage_root", type=Path)
    staged.add_argument("product_build")
    staged.add_argument("host_version")
    staged.add_argument("tag")
    staged.add_argument("document")

    draft = commands.add_parser("create-draft")
    draft.add_argument("dist_root", type=Path)
    draft.add_argument("headers_path", type=Path)
    draft.add_argument("product_build")
    draft.add_argument("host_version")
    draft.add_argument("tag")

    publication = commands.add_parser("publish")
    publication.add_argument("site_id")
    publication.add_argument("deploy_id")

    evidence_init = commands.add_parser("evidence-init")
    evidence_init.add_argument("repo_root", type=Path)
    evidence_init.add_argument("deploy_root", type=Path)

    evidence_write = commands.add_parser("evidence-write")
    evidence_write.add_argument("output", type=Path)
    evidence_write.add_argument("archive_sha256")
    evidence_write.add_argument("deploy_id")
    evidence_write.add_argument("deploy_url")
    evidence_write.add_argument("git_revision")
    evidence_write.add_argument("host_version")
    evidence_write.add_argument("product_build")
    evidence_write.add_argument("release_url")
    evidence_write.add_argument("site_id")
    evidence_write.add_argument("tag")
    return parser.parse_args(argv)


def run(options: argparse.Namespace) -> None:
    if options.command == "tag-identity":
        print("\t".join(read_tag_identity(options.root, options.product_build)))
        return
    if options.command == "release-metadata":
        print(
            "\t".join(
                parse_release_metadata(
                    sys.stdin.read(),
                    tag=options.tag,
                    tag_target=options.tag_target,
                    product_build=options.product_build,
                    host_version=options.host_version,
                )
            )
        )
        return
    if options.command == "downloaded-assets":
        validate_downloaded_assets(options.root, options.archive, options.checksum)
        return
    if options.command == "staged-bundle":
        dist_root, digest = parse_staged_bundle(
            options.document,
            stage_root=options.stage_root,
            product_build=options.product_build,
            host_version=options.host_version,
            tag=options.tag,
        )
        print(f"{dist_root}\t{digest}")
        return
    if options.command == "create-draft":
        draft = create_draft(
            dist_root=options.dist_root,
            headers_path=options.headers_path,
            product_build=options.product_build,
            host_version=options.host_version,
            tag=options.tag,
            site_id=require_environment("NETLIFY_RUNTIME_SITE_ID"),
            token=require_environment("NETLIFY_AUTH_TOKEN"),
        )
        print(f"{draft['id']}\t{draft['deploy_ssl_url']}")
        return
    if options.command == "publish":
        publish(
            site_id=options.site_id,
            deploy_id=options.deploy_id,
            token=require_environment("NETLIFY_AUTH_TOKEN"),
        )
        return
    if options.command == "evidence-init":
        initialize_evidence_target(options.repo_root, options.deploy_root)
        return
    if options.command == "evidence-write":
        write_evidence(
            output=options.output,
            archive_sha256=options.archive_sha256,
            deploy_id=options.deploy_id,
            deploy_url=options.deploy_url,
            git_revision=options.git_revision,
            host_version=options.host_version,
            product_build=options.product_build,
            release_url=options.release_url,
            site_id=options.site_id,
            tag=options.tag,
        )
        return
    raise AssertionError(f"unsupported command: {options.command}")


def redacted_message(error: BaseException) -> str:
    message = str(error)
    for secret in _secret_values():
        message = message.replace(secret, "[REDACTED]")
    return message


def main(argv: list[str] | None = None) -> int:
    try:
        options = parse_arguments(sys.argv[1:] if argv is None else argv)
        run(options)
    except (DeployOrchestratorError, NetlifyError, OSError) as error:
        print(
            f"Web Runtime deployment orchestration error: {redacted_message(error)}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
