"""The closed deployment evidence document for a promoted Cloudflare version.

`tools/release/deployment_evidence.py` verifies a Host deployment run by
reading `evidence.json` out of its artifact and matching the document's
`contract` against that Host's prefix in `tools/release/policy.json`. The two
Netlify orchestrators own every document behind those prefixes today, and both
of their field sets are closed around a Netlify `site_id` and `publication`
record. A Cloudflare deployment has no such identity, so each Host gets one new
version behind the same prefix rather than a loosened shape; the driver keeps
matching on the prefix and needs no change.

This module owns the shape, its validation and its atomic write. Running the
immutable and production checks stays with the existing smoke tooling the
deployment workflow invokes, exactly as the Netlify path splits it today: the
caller composes the document, and this module is the judge of it.

Validation binds every check result to the exact identity being deployed. A
`passed` status is not enough on its own: a smoke result carrying another
Product Build, another Host version or another URL is a different deployment's
evidence, and it fails closed here rather than reaching the release driver.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile

CANONICAL_GITHUB_REPOSITORY = "endaye/lmdj"
CANONICAL_RELEASE_PREFIX = (
    f"https://github.com/{CANONICAL_GITHUB_REPOSITORY}/releases/tag/"
)

# One contract version per Host, behind the prefix the release driver matches.
CONTRACTS = {
    "creator-web": "lmdj.creator-web.deployment-evidence.v2",
    "web-runtime-host": "lmdj.web-runtime-host.deployment-evidence.v3",
}
# The Worker each Host is promoted to; `cloudflare_api.TARGETS` is the source.
WORKERS = {"creator-web": "creator", "web-runtime-host": "lab"}
ARCHIVE_STEMS = {
    "creator-web": "lmdj-creator-web",
    "web-runtime-host": "lmdj-web-runtime-host",
}
CHANNEL = "canary"

_PRODUCT = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+")
_HOST = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_SHA1 = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_VERSION = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_PASSED = "passed"

DOCUMENT_FIELDS = {
    "archive", "channel", "contract", "ended_at", "git_revision",
    "github_actions", "host_version", "immutable", "prior_good",
    "product_build", "production", "publication", "release_files",
    "release_url", "started_at", "tag", "worker",
}


class CloudflareEvidenceError(ValueError):
    """The composed document does not describe exactly this deployment."""

    def __init__(self, reason):
        super().__init__(
            f"why: Cloudflare deployment evidence {reason}; remedy: compose "
            "the document from this run's own verified promotion and checks, "
            "never from another deployment's results")


def production_url(host):
    """The fixed public URL this Host is promoted to."""
    if host not in WORKERS:
        raise CloudflareEvidenceError("names an unconfigured Host")
    return f"https://{WORKERS[host]}.lmdj.workers.dev"


def version_url(host, version):
    """The immutable per-version preview URL Cloudflare serves."""
    if host not in WORKERS:
        raise CloudflareEvidenceError("names an unconfigured Host")
    if not isinstance(version, str) or _VERSION.fullmatch(version) is None:
        raise CloudflareEvidenceError("names an invalid version identity")
    return f"https://{version[:8]}-{WORKERS[host]}.lmdj.workers.dev"


def _digest(value):
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _check(section, *, url, product_build, host_version):
    """One `http` or `browser` result, bound to the identity it checked."""
    return (
        isinstance(section, dict)
        and set(section) == {"host_version", "product_build", "status", "url"}
        and section["status"] == _PASSED
        and section["url"] == url
        and section["product_build"] == product_build
        and section["host_version"] == host_version
    )


def _checked_side(side, *, url, product_build, host_version, extra=()):
    if not isinstance(side, dict) or set(side) != {"browser", "http", "url", *extra}:
        return False
    if side["url"] != url:
        return False
    return all(
        _check(side[check], url=url, product_build=product_build,
               host_version=host_version)
        for check in ("browser", "http")
    )


def validate_document(document, *, host):
    """Raise unless the document is exactly this Host's closed Cloudflare shape."""
    if host not in CONTRACTS:
        raise CloudflareEvidenceError("names an unconfigured Host")
    if not isinstance(document, dict) or set(document) != DOCUMENT_FIELDS:
        raise CloudflareEvidenceError("field set is not the closed shape")
    if document["contract"] != CONTRACTS[host]:
        raise CloudflareEvidenceError("declares a foreign contract")

    product = document["product_build"]
    version = document["host_version"]
    if (not isinstance(product, str) or _PRODUCT.fullmatch(product) is None
            or not isinstance(version, str) or _HOST.fullmatch(version) is None):
        raise CloudflareEvidenceError("carries an invalid identity")
    tag = f"lmdj-v{product}"
    if document["tag"] != tag:
        raise CloudflareEvidenceError("names a tag its Product Build does not")
    if document["release_url"] != CANONICAL_RELEASE_PREFIX + tag:
        raise CloudflareEvidenceError("names a foreign Release URL")
    if document["channel"] != CHANNEL:
        raise CloudflareEvidenceError("names another Channel")
    if document["worker"] != WORKERS[host]:
        raise CloudflareEvidenceError("names another Worker")
    revision = document["git_revision"]
    if not isinstance(revision, str) or _SHA1.fullmatch(revision) is None:
        raise CloudflareEvidenceError("names an invalid target revision")

    for key in ("started_at", "ended_at"):
        stamp = document[key]
        if not isinstance(stamp, str) or _TIMESTAMP.fullmatch(stamp) is None:
            raise CloudflareEvidenceError(f"has an invalid {key}")
    if document["started_at"] > document["ended_at"]:
        raise CloudflareEvidenceError("ended before it started")

    archive = document["archive"]
    expected = f"{ARCHIVE_STEMS[host]}-{version}-product-{product}.zip"
    if (not isinstance(archive, dict) or set(archive) != {"filename", "sha256"}
            or archive["filename"] != expected or not _digest(archive["sha256"])):
        raise CloudflareEvidenceError("does not name this release's archive")

    files = document["release_files"]
    if (not isinstance(files, dict)
            or set(files) != {"index_sha256", "manifest_sha256"}
            or not all(_digest(files[key]) for key in files)):
        raise CloudflareEvidenceError("does not digest its served files")

    actions = document["github_actions"]
    if (not isinstance(actions, dict) or set(actions) != {"run_id", "run_url"}
            or not isinstance(actions["run_id"], str)
            or not actions["run_id"].isdigit()):
        raise CloudflareEvidenceError("does not name its own run")
    # Bound to a name on purpose: written inline, the adjacent string literals
    # would concatenate across the `or`, and any reformatting that separated
    # them would silently weaken the comparison to a bare prefix.
    expected_run = (f"https://github.com/{CANONICAL_GITHUB_REPOSITORY}"
                    f"/actions/runs/{actions['run_id']}")
    if actions["run_url"] != expected_run:
        raise CloudflareEvidenceError("does not name its own run")

    publication = document["publication"]
    if (not isinstance(publication, dict)
            or set(publication) != {"deployment_id", "percentage", "version_id"}
            or not isinstance(publication["version_id"], str)
            or _VERSION.fullmatch(publication["version_id"]) is None
            or not isinstance(publication["deployment_id"], str)
            or _VERSION.fullmatch(publication["deployment_id"]) is None
            or publication["percentage"] != 100):
        raise CloudflareEvidenceError("does not record a complete promotion")

    # `None` is the first deployment of a Worker, which has no prior version;
    # `tools/release/deployment_effect.py` already branches on exactly that.
    # When a prior exists it must carry everything that consumer projects, so
    # the Cloudflare document is a drop-in for the Netlify one it replaces.
    prior = document["prior_good"]
    if prior is not None:
        if (not isinstance(prior, dict)
                or set(prior) != {"host_version", "product_build",
                                  "release_files", "site_response",
                                  "version_id", "version_url"}
                or not isinstance(prior["version_id"], str)
                or _VERSION.fullmatch(prior["version_id"]) is None
                or prior["version_url"] != version_url(host, prior["version_id"])
                or not isinstance(prior["product_build"], str)
                or _PRODUCT.fullmatch(prior["product_build"]) is None
                or not isinstance(prior["host_version"], str)
                or _HOST.fullmatch(prior["host_version"]) is None
                or not isinstance(prior["release_files"], dict)
                or set(prior["release_files"]) != {"index_sha256", "manifest_sha256"}
                or not all(_digest(prior["release_files"][key])
                           for key in prior["release_files"])
                or not isinstance(prior["site_response"], dict)
                or not prior["site_response"]):
            raise CloudflareEvidenceError("records an invalid prior version")
        if prior["version_id"] == publication["version_id"]:
            # A prior that is the version just promoted is not a rollback
            # target; recording it would make recovery a no-op.
            raise CloudflareEvidenceError(
                "names the promoted version as its own prior")

    immutable = document["immutable"]
    if (not isinstance(immutable, dict) or "version_id" not in immutable
            or immutable["version_id"] != publication["version_id"]):
        # The immutable side must be the version that was actually promoted;
        # checking some other version proves nothing about this deployment.
        raise CloudflareEvidenceError(
            "verified a version other than the promoted one")
    if not _checked_side(immutable, url=version_url(host, immutable["version_id"]),
                         product_build=product, host_version=version,
                         extra=("version_id",)):
        raise CloudflareEvidenceError("immutable checks did not pass for this version")
    if not _checked_side(document["production"], url=production_url(host),
                         product_build=product, host_version=version):
        raise CloudflareEvidenceError("production checks did not pass for this Host")
    return document


def write_document(path, document, *, host):
    """Validate, then write the document atomically as `evidence.json`."""
    validate_document(document, host=host)
    target = Path(path)
    # A refusal to overwrite a link someone placed here, not a race guard: the
    # write lands in a sibling temporary file and `os.replace` is `rename(2)`,
    # which replaces a destination symlink itself rather than following it, so
    # a link appearing after this check cannot redirect the bytes.
    if target.is_symlink() or not target.parent.is_dir() or target.parent.is_symlink():
        raise CloudflareEvidenceError("target is unsafe")
    serialized = json.dumps(document, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.",
                                             dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        # The rename is what publishes the document, so persist the directory
        # entry too: the promotion it describes has already happened remotely,
        # and evidence lost after that leaves a real deployment unverifiable.
        # Not every platform allows fsync on a directory; failing to harden is
        # not a reason to fail a written document.
        try:
            handle = os.open(target.parent, os.O_RDONLY)
        except OSError:
            pass
        else:
            try:
                os.fsync(handle)
            except OSError:
                pass
            finally:
                os.close(handle)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return target
