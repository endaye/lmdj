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
) -> tuple[str, str, str, str]:
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
    if (
        not isinstance(release["targetCommitish"], str)
        or not release["targetCommitish"]
        or "\n" in release["targetCommitish"]
        or "\r" in release["targetCommitish"]
    ):
        raise DeployOrchestratorError("GitHub Release target metadata is invalid")
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
    signature = checksum + ".asc"
    if sorted(names) != sorted((archive, checksum, signature)):
        raise DeployOrchestratorError("GitHub Release Host asset identity is invalid")
    expected_release_url = CANONICAL_RELEASE_PREFIX + tag
    if release["url"] != expected_release_url:
        raise DeployOrchestratorError("GitHub Release URL is invalid")
    return archive, checksum, signature, expected_release_url


def validate_downloaded_assets(
    root: Path, archive_name: str, checksum_name: str, signature_name: str
) -> None:
    expected = sorted((archive_name, checksum_name, signature_name))
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
    files["/_headers"] = render_deploy_headers(dist_root, headers_path)
    return files


def render_deploy_headers(dist_root: Path, headers_path: Path) -> bytes:
    """Append immutable cache rules for only the manifest-authorized nine assets."""
    try:
        dist_root = dist_root.resolve(strict=True)
        headers_path = headers_path.resolve(strict=True)
        base = headers_path.read_text(encoding="utf-8")
        manifest = json.loads(
            (dist_root / "host-manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DeployOrchestratorError("Netlify response rules are unavailable") from error
    if (
        not dist_root.is_dir()
        or dist_root.is_symlink()
        or not headers_path.is_file()
        or headers_path.is_symlink()
        or re.search(r"^/assets/\*$", base, re.MULTILINE) is not None
        or not isinstance(manifest, dict)
        or not isinstance(manifest.get("assets"), list)
        or len(manifest["assets"]) != 9
    ):
        raise DeployOrchestratorError("Netlify response rules are invalid")
    paths: list[str] = []
    for asset in manifest["assets"]:
        path = asset.get("path") if isinstance(asset, dict) else None
        if (
            not isinstance(path, str)
            or re.fullmatch(r"assets/[A-Za-z0-9._-]+", path) is None
            or path in paths
            or not (dist_root / path).is_file()
            or (dist_root / path).is_symlink()
        ):
            raise DeployOrchestratorError("Netlify immutable asset inventory is invalid")
        paths.append(path)
    rendered = base.rstrip() + "\n\n"
    rendered += "\n\n".join(
        f"/{path}\n  Cache-Control: public, max-age=31536000, immutable"
        for path in paths
    )
    return (rendered + "\n").encode("utf-8")


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


def current_site(
    *, site_id: str, token: str, client: NetlifyClient | None = None
) -> dict[str, object]:
    selected = (
        _SecretCheckingNetlifyClient(token=token, secrets=_secret_values())
        if client is None
        else client
    )
    site = selected.get_site(site_id=site_id)
    if (
        site.id != site_id
        or DEPLOY_ID_PATTERN.fullmatch(site_id) is None
        or site.ssl_url != CANONICAL_PRODUCTION_URL
        or site.state not in {"current", "disabled"}
    ):
        raise DeployOrchestratorError("Netlify site identity is invalid")
    prior = None
    if site.published_deploy is not None:
        deploy = site.published_deploy
        expected_url = (
            f"https://{deploy.id.lower()}--{CANONICAL_NETLIFY_SITE}.netlify.app"
        )
        if (
            DEPLOY_ID_PATTERN.fullmatch(deploy.id) is None
            or deploy.site_id != site_id
            or deploy.state != "ready"
            or deploy.deploy_ssl_url != expected_url
        ):
            raise DeployOrchestratorError("Netlify published deploy identity is invalid")
        prior = {
            "deploy_ssl_url": expected_url,
            "id": deploy.id,
            "site_id": site_id,
            "state": "ready",
        }
    result: dict[str, object] = {
        "id": site_id,
        "published_deploy": prior,
        "ssl_url": CANONICAL_PRODUCTION_URL,
        "state": site.state,
    }
    reject_secret_material(result, label="Netlify current site")
    return result


def disable_site(
    *, site_id: str, reason: str, token: str, client: NetlifyClient | None = None
) -> dict[str, str]:
    selected = (
        _SecretCheckingNetlifyClient(token=token, secrets=_secret_values())
        if client is None
        else client
    )
    selected.disable_site(site_id=site_id, reason=reason)
    result = {"action": "disabled", "site_id": site_id}
    reject_secret_material(result, label="Netlify disable result")
    return result


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
    for name in ("evidence.json", "recovery-evidence.json"):
        evidence = deploy_root / name
        if evidence.is_symlink() or evidence.exists():
            evidence.unlink()


def _valid_timestamp(value: object, pattern: re.Pattern[str]) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _valid_browser_evidence(value: object, timestamp: re.Pattern[str]) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"ended_at", "started_at", "status"}
        and value.get("status") == "passed"
        and _valid_timestamp(value.get("started_at"), timestamp)
        and _valid_timestamp(value.get("ended_at"), timestamp)
        and value["started_at"] <= value["ended_at"]
    )


def _valid_http_evidence(value: object, timestamp: re.Pattern[str]) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"ended_at", "result", "started_at", "status"}
        and value.get("status") == "passed"
        and isinstance(value.get("result"), dict)
        and _valid_timestamp(value.get("started_at"), timestamp)
        and _valid_timestamp(value.get("ended_at"), timestamp)
        and value["started_at"] <= value["ended_at"]
    )


def _valid_deploy_url(value: object, deploy_id: object) -> bool:
    return (
        isinstance(deploy_id, str)
        and DEPLOY_ID_PATTERN.fullmatch(deploy_id) is not None
        and value
        == f"https://{deploy_id.lower()}--{CANONICAL_NETLIFY_SITE}.netlify.app"
    )


def _valid_success_evidence(
    document: dict[str, object], timestamp: re.Pattern[str]
) -> bool:
    archive = document.get("archive")
    actions = document.get("github_actions")
    immutable = document.get("immutable")
    production = document.get("production")
    publication = document.get("publication")
    product = document.get("product_build")
    host = document.get("host_version")
    tag = document.get("tag")
    site_id = document.get("site_id")
    if (
        not isinstance(product, str)
        or PRODUCT_PATTERN.fullmatch(product) is None
        or not isinstance(host, str)
        or HOST_PATTERN.fullmatch(host) is None
        or tag != f"lmdj-v{product}"
        or not isinstance(site_id, str)
        or DEPLOY_ID_PATTERN.fullmatch(site_id) is None
        or document.get("channel") != "canary"
        or not isinstance(document.get("git_revision"), str)
        or SHA1_PATTERN.fullmatch(document["git_revision"]) is None
        or document.get("release_url") != CANONICAL_RELEASE_PREFIX + str(tag)
        or not _valid_timestamp(document.get("started_at"), timestamp)
        or not _valid_timestamp(document.get("ended_at"), timestamp)
        or document["started_at"] > document["ended_at"]
    ):
        return False
    expected_archive = f"lmdj-web-runtime-host-{host}-product-{product}.zip"
    if (
        not isinstance(archive, dict)
        or set(archive) != {"filename", "sha256"}
        or archive.get("filename") != expected_archive
        or not isinstance(archive.get("sha256"), str)
        or SHA256_PATTERN.fullmatch(archive["sha256"]) is None
        or not isinstance(actions, dict)
        or set(actions) != {"run_id", "run_url"}
        or not isinstance(actions.get("run_id"), str)
        or not actions["run_id"].isdigit()
        or actions.get("run_url")
        != f"https://github.com/{CANONICAL_GITHUB_REPOSITORY}/actions/runs/{actions.get('run_id')}"
    ):
        return False
    if (
        not isinstance(immutable, dict)
        or set(immutable) != {"browser", "deploy_id", "deploy_url", "http"}
        or not _valid_deploy_url(immutable.get("deploy_url"), immutable.get("deploy_id"))
        or not _valid_http_evidence(immutable.get("http"), timestamp)
        or not _valid_browser_evidence(immutable.get("browser"), timestamp)
        or not isinstance(production, dict)
        or set(production) != {"browser", "http", "url"}
        or production.get("url") != CANONICAL_PRODUCTION_URL
        or not _valid_http_evidence(production.get("http"), timestamp)
        or not _valid_browser_evidence(production.get("browser"), timestamp)
    ):
        return False
    response = publication.get("response") if isinstance(publication, dict) else None
    if (
        not isinstance(publication, dict)
        or set(publication) != {"response", "same_deploy_id"}
        or publication.get("same_deploy_id") != immutable.get("deploy_id")
        or not isinstance(response, dict)
        or response.get("id") != immutable.get("deploy_id")
        or response.get("site_id") != site_id
        or response.get("ssl_url") != CANONICAL_PRODUCTION_URL
        or response.get("state") != "ready"
    ):
        return False
    prior = document.get("prior_good")
    if prior is None:
        return True
    if not isinstance(prior, dict) or set(prior) != {
        "deploy_id", "deploy_url", "host_version", "immutable",
        "product_build", "production", "site_response",
    }:
        return False
    prior_id = prior.get("deploy_id")
    prior_immutable = prior.get("immutable")
    prior_production = prior.get("production")
    site_response = prior.get("site_response")
    return (
        _valid_deploy_url(prior.get("deploy_url"), prior_id)
        and isinstance(prior.get("product_build"), str)
        and PRODUCT_PATTERN.fullmatch(prior["product_build"]) is not None
        and isinstance(prior.get("host_version"), str)
        and HOST_PATTERN.fullmatch(prior["host_version"]) is not None
        and isinstance(prior_immutable, dict)
        and set(prior_immutable) == {"browser", "http"}
        and _valid_http_evidence(prior_immutable.get("http"), timestamp)
        and _valid_browser_evidence(prior_immutable.get("browser"), timestamp)
        and isinstance(prior_production, dict)
        and set(prior_production) == {"browser", "http"}
        and _valid_http_evidence(prior_production.get("http"), timestamp)
        and _valid_browser_evidence(prior_production.get("browser"), timestamp)
        and isinstance(site_response, dict)
        and set(site_response) == {"id", "published_deploy", "ssl_url", "state"}
        and site_response.get("id") == site_id
        and site_response.get("ssl_url") == CANONICAL_PRODUCTION_URL
        and site_response.get("state") == "current"
        and isinstance(site_response.get("published_deploy"), dict)
        and site_response["published_deploy"].get("id") == prior_id
        and site_response["published_deploy"].get("site_id") == site_id
        and site_response["published_deploy"].get("state") == "ready"
        and site_response["published_deploy"].get("deploy_ssl_url")
        == prior.get("deploy_url")
    )


def _valid_recovery_evidence(
    document: dict[str, object], timestamp: re.Pattern[str]
) -> bool:
    action = document.get("action")
    attempted = document.get("attempted_deploy")
    prior = document.get("prior_deploy")
    validation = document.get("validation")
    if (
        action not in {
            "alias-not-new", "disabled-first-publication", "not-started",
            "restored-prior",
        }
        or type(document.get("original_status")) is not int
        or document["original_status"] == 0
        or not _valid_timestamp(document.get("recorded_at"), timestamp)
        or not isinstance(attempted, dict)
        or set(attempted) != {"id", "url"}
        or not _valid_deploy_url(attempted.get("url"), attempted.get("id"))
        or not isinstance(document.get("reconcile"), dict)
        or not isinstance(validation, dict)
        or set(validation) != {
            "immutable_browser", "immutable_http", "production_browser",
            "production_http", "status",
        }
        or validation.get("status") not in {"failed", "passed"}
    ):
        return False
    if prior is not None and (
        not isinstance(prior, dict)
        or set(prior) != {"id", "url"}
        or not _valid_deploy_url(prior.get("url"), prior.get("id"))
    ):
        return False
    response = document.get("recovery_response")
    if action == "alias-not-new":
        return validation["status"] == "passed" and response is None
    if action == "disabled-first-publication":
        return (
            prior is None
            and validation["status"] == "passed"
            and isinstance(response, dict)
            and set(response) == {"action", "site_id"}
            and response.get("action") == "disabled"
            and isinstance(response.get("site_id"), str)
            and DEPLOY_ID_PATTERN.fullmatch(response["site_id"]) is not None
        )
    if action == "not-started":
        return validation["status"] == "failed" and response is None
    if not isinstance(prior, dict) or not isinstance(response, dict):
        return False
    if (
        response.get("id") != prior.get("id")
        or not isinstance(response.get("site_id"), str)
        or DEPLOY_ID_PATTERN.fullmatch(response["site_id"]) is None
        or response.get("state") != "ready"
        or response.get("ssl_url") != CANONICAL_PRODUCTION_URL
    ):
        return False
    if validation["status"] == "failed":
        return True
    return (
        _valid_http_evidence(validation.get("immutable_http"), timestamp)
        and _valid_browser_evidence(validation.get("immutable_browser"), timestamp)
        and _valid_http_evidence(validation.get("production_http"), timestamp)
        and _valid_browser_evidence(validation.get("production_browser"), timestamp)
    )


def write_evidence_document(
    *, output: Path, source: str, expected_contract: str
) -> None:
    document = parse_json_document(source, "deployment evidence")
    if document.get("contract") != expected_contract:
        raise DeployOrchestratorError("deployment evidence contract is invalid")
    timestamp = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
    if expected_contract == "lmdj.web-runtime-host.deployment-evidence.v2":
        required = {
            "archive", "channel", "contract", "ended_at", "git_revision",
            "github_actions", "host_version", "immutable", "prior_good",
            "product_build", "production", "publication", "release_url",
            "site_id", "started_at", "tag",
        }
        if set(document) != required:
            raise DeployOrchestratorError("deployment evidence schema is invalid")
        if not _valid_success_evidence(document, timestamp):
            raise DeployOrchestratorError("deployment evidence schema is invalid")
    elif expected_contract == "lmdj.web-runtime-host.deployment-recovery-evidence.v1":
        required = {
            "action", "attempted_deploy", "contract", "original_status",
            "prior_deploy", "reconcile", "recorded_at", "recovery_response",
            "validation",
        }
        if set(document) != required or not _valid_recovery_evidence(document, timestamp):
            raise DeployOrchestratorError("deployment recovery evidence schema is invalid")
    else:
        raise DeployOrchestratorError("deployment evidence contract is unsupported")
    serialized = canonical_json(document) + "\n"
    if output.is_symlink() or not output.parent.is_dir() or output.parent.is_symlink():
        raise DeployOrchestratorError("deployment evidence target is unsafe")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
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
    downloaded.add_argument("signature")

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

    headers = commands.add_parser("render-headers")
    headers.add_argument("dist_root", type=Path)
    headers.add_argument("headers_path", type=Path)

    publication = commands.add_parser("publish")
    publication.add_argument("site_id")
    publication.add_argument("deploy_id")

    site = commands.add_parser("site-current")
    site.add_argument("site_id")

    disable = commands.add_parser("disable-site")
    disable.add_argument("site_id")
    disable.add_argument("reason")

    evidence_init = commands.add_parser("evidence-init")
    evidence_init.add_argument("repo_root", type=Path)
    evidence_init.add_argument("deploy_root", type=Path)

    evidence_document = commands.add_parser("evidence-write-document")
    evidence_document.add_argument("output", type=Path)
    evidence_document.add_argument("contract")
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
        validate_downloaded_assets(
            options.root, options.archive, options.checksum, options.signature
        )
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
    if options.command == "render-headers":
        sys.stdout.buffer.write(render_deploy_headers(options.dist_root, options.headers_path))
        return
    if options.command == "publish":
        result = publish(
            site_id=options.site_id,
            deploy_id=options.deploy_id,
            token=require_environment("NETLIFY_AUTH_TOKEN"),
        )
        print(canonical_json(result))
        return
    if options.command == "site-current":
        print(
            canonical_json(
                current_site(
                    site_id=options.site_id,
                    token=require_environment("NETLIFY_AUTH_TOKEN"),
                )
            )
        )
        return
    if options.command == "disable-site":
        print(
            canonical_json(
                disable_site(
                    site_id=options.site_id,
                    reason=options.reason,
                    token=require_environment("NETLIFY_AUTH_TOKEN"),
                )
            )
        )
        return
    if options.command == "evidence-init":
        initialize_evidence_target(options.repo_root, options.deploy_root)
        return
    if options.command == "evidence-write-document":
        write_evidence_document(
            output=options.output,
            source=sys.stdin.read(),
            expected_contract=options.contract,
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
