"""Drive one Host's complete Cloudflare deployment and record its evidence.

The shared adapter (`cloudflare_host.py`) owns each individual transition and
its exact-signed HTTP verification; `cloudflare_deployment_evidence.py` owns the
document the release driver reads. This module is the sequence between them:
read the pre-dispatch prior, upload and verify a candidate, check it in a real
browser, promote it, check production in a real browser, and only then write the
evidence.

Three properties shape the code.

The release the document describes is the one that was staged. `cloudflare_host`
stages a verified signed release at `<workspace>/<host>` and leaves its receipt
there, so the Product Build, Host version, source revision, archive digest and
served-file digests are all read back from that receipt rather than accepted
from the caller. A caller cannot describe a deployment as something other than
what it actually published.

The prior is described from what production was serving, observed once before
anything mutates. Re-staging its signed release afterwards would describe what
that release *should* have been rather than what was live, would read the
candidate's own receipt on a same-tag redeploy, and would move a whole class of
failure to after the promotion — leaving production changed with no document.

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

Nothing is written unless every leg passed, and nothing is undone either. When
a check fails after promotion, production is left serving a version that passed
exact-signed HTTP but failed its browser leg, and no document is recorded, so
the release driver sees an unverified deployment rather than a verified one.
This module does not roll that back. `cloudflare_transaction.promote` owns
recovery inside its own transaction, with preconditions it verified; issuing a
second production mutation from out here, on a failure this module cannot
characterise, is exactly the blind retry the run store exists to prevent. The
operator reconciles with the adapter's `recover`.

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


_STAGE = "stage.json"


def _receipt(directory, tag, host, what):
    """The staging receipt `cloudflare_host` left beside the distribution."""
    try:
        document = json.loads((directory / _STAGE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise CloudflareDeployError(f"has no readable {what} staging receipt") from None
    if not isinstance(document, dict) or document.get("kind") != "verified-host-stage":
        raise CloudflareDeployError(f"has no verified {what} staging receipt")
    if document.get("tag") != tag or document.get("host_id") != host:
        raise CloudflareDeployError(f"staged another tag or Host for its {what}")
    return document


def _described(receipt, what):
    """The release fields the evidence document carries, from the receipt."""
    archive = receipt.get("archive")
    files = receipt.get("files")
    if (not isinstance(archive, dict) or not isinstance(files, dict)
            or not isinstance(archive.get("name"), str)
            or not isinstance(archive.get("sha256"), str)):
        raise CloudflareDeployError(f"has an incomplete {what} staging receipt")
    served = {}
    for member, key in (("index.html", "index_sha256"),
                        ("host-manifest.json", "manifest_sha256")):
        entry = files.get(member)
        if not isinstance(entry, dict) or not isinstance(entry.get("sha256"), str):
            raise CloudflareDeployError(f"staged no {member} for its {what}")
        served[key] = entry["sha256"]
    for field in ("product_build", "host_version", "source"):
        if not isinstance(receipt.get(field), str):
            raise CloudflareDeployError(f"has no {field} in its {what} receipt")
    return {"product_build": receipt["product_build"],
            "host_version": receipt["host_version"],
            "archive": {"filename": archive["name"], "sha256": archive["sha256"]},
            "release_files": served}


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


def deploy(*, host, tag, run_id, state_root, output,
           node, wrangler, adapter, verify_http, browser, read_site, clock,
           prior_tag=None):
    """Run the whole deployment and write its evidence, or raise having written nothing.

    `adapter(arguments)` runs `scripts/cloudflare-host.sh` and returns its
    stdout. `verify_http(distribution, url, preview)` runs `cloudflare_smoke`
    against the staged signed bytes and `browser(url)` runs the Host's existing
    Playwright deployment spec against that URL; both must return exactly
    `True`. `read_site(url)` observes what production is serving right now and
    returns `{response, product_build, host_version, release_files}`, where
    `response` is the recorded document the frozen prior digest is taken over.
    """
    if host not in WORKERS:
        raise CloudflareDeployError("names an unconfigured Host")

    started_at = clock()
    common = ["--target", host, "--state-root", str(state_root)]

    # The prior is read before anything mutates, so the digest the release
    # driver froze before dispatch is the one this deployment replaced.
    root = Path(state_root).resolve()
    live = _live(adapter, common)
    prior_deployment = live["deployment"] if live["exists"] else None
    observed = read_site(production_url(host))

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
        prior_good = _prior(observed, host, prior_version)

    uploaded = _adapter_result(
        adapter(["candidate", tag, *common, "--node", node,
                 "--wrangler", wrangler]), "candidate")
    version = uploaded["result"].get("version_id")
    if not isinstance(version, str):
        raise CloudflareDeployError("candidate returned no version identity")
    immutable_url = version_url(host, version)
    # The adapter stages the signed release at `<workspace>/<host>` and reports
    # the workspace, so the bytes it verified against are the bytes checked here.
    staged = _staged(uploaded, host, root)
    distribution = staged / "dist"
    if not distribution.is_dir():
        raise CloudflareDeployError("candidate staged no signed distribution")
    receipt = _receipt(staged, tag, host, "release")
    release = _described(receipt, "release")

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
        "git_revision": receipt["source"],
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


def _prior(observed, host, version):
    """The replaced deployment, from what production was serving beforehand."""
    if not isinstance(observed, dict):
        raise CloudflareDeployError("read no prior production observation")
    response = observed.get("response")
    if not isinstance(response, dict) or not response:
        raise CloudflareDeployError("read no prior production response")
    files = observed.get("release_files")
    if (not isinstance(files, dict)
            or set(files) != {"index_sha256", "manifest_sha256"}
            or not all(isinstance(files[key], str) for key in files)):
        raise CloudflareDeployError("observed no prior served-file digests")
    for field in ("product_build", "host_version"):
        if not isinstance(observed.get(field), str):
            raise CloudflareDeployError(f"observed no prior {field}")
    return {"version_id": version, "version_url": version_url(host, version),
            "product_build": observed["product_build"],
            "host_version": observed["host_version"],
            "release_files": dict(files), "site_response": response}


def _staged(reported, host, root, sub=()):
    """The adapter's staging directory for this Host, inside this run's root."""
    workspace = reported.get("workspace")
    if not isinstance(workspace, str) or not workspace:
        raise CloudflareDeployError("reported no staging workspace")
    # The adapter stages under the state root it was given, so a reported path
    # outside it is not this run's staging tree and must not be trusted.
    resolved = Path(workspace).resolve()
    if resolved != root and root not in resolved.parents:
        raise CloudflareDeployError(
            "reported a workspace outside this run's state root")
    staged = resolved.joinpath(*sub, host)
    if not staged.is_dir():
        raise CloudflareDeployError("staged no signed release")
    return staged


def _live(adapter, common):
    document = _parsed(adapter(["inspect", *common]), "inspect")
    if not isinstance(document, dict) or "exists" not in document:
        raise CloudflareDeployError("could not read the live Worker state")
    if document["exists"] and not isinstance(document.get("deployment"), dict):
        raise CloudflareDeployError("read an existing Worker with no deployment")
    return document
