"""Drive one Host's complete Cloudflare deployment and record its evidence.

The shared adapter (`cloudflare_host.py`) owns each individual transition and
its exact-signed HTTP verification; `cloudflare_deployment_evidence.py` owns the
document the release driver reads. This module is the sequence between them:
read the pre-dispatch prior, upload and verify a candidate, check it in a real
browser, promote it, check production in a real browser, and only then write the
evidence.

Two properties shape the code.

Every result in the document is observed here. The adapter runs its own
exact-signed HTTP verification and refuses to proceed without it, but this
module records nothing on that basis: it re-runs `cloudflare_smoke` against the
signed distribution the adapter staged, so `immutable.http` and `production.http`
say what this module saw rather than what another module promised. A document
must never assert a check nobody in it performed.

Both verifiers must return exactly `True`, the idiom `cloudflare_transaction`
already uses. Not raising is too weak a signal: a check that skipped, returned
a falsy result or reported a soft failure would otherwise be written down as
`passed`.

The bytes each check runs against are provably this run's. The adapter stages
under the `--state-root` it was given and reports the workspace, so the reported
path is resolved and required to sit inside that root before anything is
verified: a stale or unrelated staging tree cannot be substituted by a
malformed result.

Nothing is written unless every leg passed. A deployment whose browser check
failed must not leave behind a document saying the HTTP check passed: the
release driver would read that as a verified deployment. Failure raises and the
output path is never created.
"""

from __future__ import annotations

import json
from pathlib import Path

from cloudflare_deployment_evidence import (
    CloudflareEvidenceError,
    WORKERS,
    production_url,
    version_url,
    write_document,
)

CONTRACT_HOSTS = tuple(sorted(WORKERS))


class CloudflareDeployError(RuntimeError):
    """One leg of the deployment did not complete; nothing was recorded."""

    def __init__(self, reason):
        super().__init__(
            f"why: Cloudflare deployment {reason}; remedy: inspect the "
            "retained run store and live Worker state, then reconcile the "
            "exact target before another attempt")


def _release_fields(release, what):
    if (not isinstance(release, dict)
            or set(release) != {"archive", "host_version", "product_build",
                                "release_files"}):
        raise CloudflareDeployError(f"has no complete {what} description")
    return release


def _parsed(output, what):
    """Every adapter read goes through here so only one exception type escapes."""
    try:
        return json.loads(output)
    except (TypeError, ValueError):
        raise CloudflareDeployError(f"{what} did not return a readable result") from None


def _adapter_result(output, what):
    document = _parsed(output, what)
    if not isinstance(document, dict) or not isinstance(document.get("result"), dict):
        raise CloudflareDeployError(f"{what} did not return a result")
    return document


def deploy(*, host, tag, release, run_id, git_revision, state_root, output,
           node, wrangler, adapter, verify_http, browser, read_site, clock,
           prior_tag=None, prior_release=None):
    """Run the whole deployment and write its evidence, or raise having written nothing.

    `adapter(arguments)` runs `scripts/cloudflare-host.sh` and returns its
    stdout. `verify_http(distribution, url, preview)` runs `cloudflare_smoke`
    against the staged signed bytes and `browser(url)` runs the Host's existing
    Playwright deployment spec against that URL; both must return exactly
    `True`. `read_site(url)` returns the recorded production response the
    pre-dispatch prior digest is taken over.
    """
    if host not in WORKERS:
        raise CloudflareDeployError("names an unconfigured Host")
    _release_fields(release, "release")
    if (prior_tag is None) != (prior_release is None):
        raise CloudflareDeployError(
            "must describe its prior release exactly when it names a prior tag")
    if prior_release is not None:
        _release_fields(prior_release, "prior release")

    started_at = clock()
    common = ["--target", host, "--state-root", str(state_root)]

    # The prior is read before anything mutates, so the digest the release
    # driver froze before dispatch is the one this deployment replaced.
    root = Path(state_root).resolve()
    live = _live(adapter, common)
    prior_deployment = live["deployment"] if live["exists"] else None
    prior_site_response = read_site(production_url(host))
    if not isinstance(prior_site_response, dict) or not prior_site_response:
        raise CloudflareDeployError("read no prior production response")

    if prior_deployment is None:
        if prior_tag is not None:
            raise CloudflareDeployError(
                "names a prior tag for a Worker that has no deployment")
        prior_good = None
    else:
        if prior_tag is None:
            raise CloudflareDeployError(
                "must name the signed prior tag of the deployment it replaces")
        prior_version = prior_deployment.get("version_id")
        if not isinstance(prior_version, str):
            raise CloudflareDeployError("read a deployment with no version identity")
        prior_good = {
            "version_id": prior_version,
            "version_url": version_url(host, prior_version),
            "product_build": prior_release["product_build"],
            "host_version": prior_release["host_version"],
            "release_files": dict(prior_release["release_files"]),
            "site_response": prior_site_response,
        }

    uploaded = _adapter_result(
        adapter(["candidate", tag, *common, "--node", node,
                 "--wrangler", wrangler]), "candidate")
    version = uploaded["result"].get("version_id")
    if not isinstance(version, str):
        raise CloudflareDeployError("candidate returned no version identity")
    immutable_url = version_url(host, version)
    # The adapter stages the signed release at `<workspace>/<host>` and reports
    # the workspace, so the bytes it verified against are the bytes checked here.
    distribution = _distribution(uploaded, host, root)

    # Both legs this module records, in the order production may be touched: a
    # candidate that only serves correct bytes is not yet a working Host.
    _passed(verify_http(distribution, immutable_url, True), "HTTP", immutable_url)
    _passed(browser(immutable_url), "browser", immutable_url)

    promoted = _adapter_result(
        adapter(["promote", tag, *common, "--version", version,
                 *(("--prior-tag", prior_tag) if prior_tag else ())]),
        "promote")["result"]
    if promoted.get("version_id") != version:
        raise CloudflareDeployError("promoted a version other than the candidate")
    deployment = promoted.get("id")
    if not isinstance(deployment, str):
        raise CloudflareDeployError("promotion returned no deployment identity")

    live_url = production_url(host)
    _passed(verify_http(distribution, live_url, False), "HTTP", live_url)
    _passed(browser(live_url), "browser", live_url)

    document = {
        "contract": _contract(host),
        "tag": tag,
        "product_build": release["product_build"],
        "host_version": release["host_version"],
        "git_revision": git_revision,
        "channel": "canary",
        "worker": WORKERS[host],
        "release_url": f"https://github.com/endaye/lmdj/releases/tag/{tag}",
        "archive": dict(release["archive"]),
        "release_files": dict(release["release_files"]),
        "publication": {"version_id": version, "deployment_id": deployment,
                        "percentage": 100},
        "prior_good": prior_good,
        "immutable": {
            "version_id": version, "url": immutable_url,
            "http": _result(immutable_url, release),
            "browser": _result(immutable_url, release),
        },
        "production": {
            "url": live_url,
            "http": _result(live_url, release),
            "browser": _result(live_url, release),
        },
        "github_actions": {
            "run_id": str(run_id),
            "run_url": f"https://github.com/endaye/lmdj/actions/runs/{run_id}",
        },
        "started_at": started_at,
        "ended_at": clock(),
    }
    try:
        return write_document(Path(output), document, host=host)
    except CloudflareEvidenceError as error:
        # The deployment happened; the document describing it did not validate.
        # That is a defect in this composition, never something to write anyway.
        raise CloudflareDeployError(f"composed invalid evidence ({error})") from None


def _contract(host):
    from cloudflare_deployment_evidence import CONTRACTS

    return CONTRACTS[host]


def _result(url, release):
    return {"status": "passed", "url": url,
            "product_build": release["product_build"],
            "host_version": release["host_version"]}


def _passed(result, kind, url):
    """A verifier reports exactly True; anything else is not a passed check."""
    if result is not True:
        raise CloudflareDeployError(f"{kind} verification of {url} did not pass")


def _distribution(uploaded, host, root):
    workspace = uploaded.get("workspace")
    if not isinstance(workspace, str) or not workspace:
        raise CloudflareDeployError("candidate reported no staging workspace")
    # The adapter stages under the state root it was given, so a reported path
    # outside it is not this run's staging tree and must not be verified.
    resolved = Path(workspace).resolve()
    if resolved != root and root not in resolved.parents:
        raise CloudflareDeployError(
            "candidate reported a workspace outside this run's state root")
    distribution = resolved / host / "dist"
    if not distribution.is_dir():
        raise CloudflareDeployError("candidate staged no signed distribution")
    return distribution


def _live(adapter, common):
    document = _parsed(adapter(["inspect", *common]), "inspect")
    if not isinstance(document, dict) or "exists" not in document:
        raise CloudflareDeployError("could not read the live Worker state")
    if document["exists"] and not isinstance(document.get("deployment"), dict):
        raise CloudflareDeployError("read an existing Worker with no deployment")
    return document
