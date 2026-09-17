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

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

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


ROOT = Path(__file__).resolve().parents[3]
BROWSER = {
    "creator-web": ("creator-deployment",
                    "deployment/creator_web_deployment.spec.mjs",
                    "LMDJ_CREATOR_WEB"),
    "web-runtime-host": ("chromium",
                         "deployment/web_runtime_host_deployment.spec.mjs",
                         "LMDJ_WEB_HOST"),
}
# An allowlist, not a denylist: the browser runs third-party test code, and a
# denylist silently admits every credential nobody thought to name.
BROWSER_ENVIRONMENT = ("CI", "HOME", "LANG", "LC_ALL", "PATH",
                       "PLAYWRIGHT_BROWSERS_PATH", "TMPDIR",
                       # A runner behind an egress proxy cannot reach the
                       # deployed origin without these, and that failure would
                       # read as a regression rather than an environment.
                       "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
                       "http_proxy", "https_proxy", "no_proxy")
# Any environment name that looks like a credential: a fixed list only protects
# the names someone remembered, and these tools are handed new ones over time.
SECRET_NAME = re.compile(r"TOKEN|SECRET|PASSWORD|CREDENTIAL|API_KEY|APIKEY",
                         re.IGNORECASE)
# Credentials this process never held still appear in the text tools echo.
# Each captures its prefix and the value separately; `_mask` decides per match,
# so one already-redacted value on a line cannot shield a second real one.
SECRET_TEXT = (
    # To end of line: a header value is not one token ("Bearer <secret>").
    re.compile(r"(?i)(authorization\s*:\s*)(.+)"),
    re.compile(r"(?i)(\bbearer\s+)(\S+)"),
    re.compile(r"(?i)((?:token|secret|password|api[_-]?key)\s*[=:]\s*)(\S+)"),
)


def _redacted(text):
    """Remove credentials tools echo on failure, by value and by shape.

    Value replacement covers what this process held, and is deliberately not
    length-limited beyond a floor: below four characters a value is not
    plausibly a credential but is very likely a substring of unrelated output,
    and a diagnostic mangled into uselessness protects nobody. Above it,
    replacement stands however short the value is.

    Value replacement alone is not enough either, because it can only remove
    what this process held; an adapter that minted its own token, or read one
    from a config file, still echoes it. So credential-carrying shapes are
    redacted too, at any length, which is what covers a genuinely short token
    appearing as `token=abc` or behind an `Authorization` header.
    """
    # Values first, so a credential this process held is named in the marker
    # and an operator can tell which one leaked. The shape patterns then skip
    # what is already replaced, and catch the ones held elsewhere.
    # Below four characters a value is not a credential but is very likely a
    # substring of unrelated output, and a mangled diagnostic helps nobody.
    # Shape redaction below still covers assignments and headers at any length.
    named = {value: name for name, value in os.environ.items()
             if value and len(value) >= 4 and SECRET_NAME.search(name)}
    if named:
        # One pass, longest value first. Replacing in iteration order lets a
        # shorter credential that is a prefix of a longer one consume only part
        # of it and leave the tail behind; and a single pass cannot re-enter a
        # marker it just wrote, so one credential's name cannot be rewritten by
        # another's value.
        values = sorted(named, key=len, reverse=True)
        text = re.compile("|".join(re.escape(value) for value in values)).sub(
            lambda match: f"[REDACTED {named[match.group(0)]}]", text)
    for pattern in SECRET_TEXT:
        text = pattern.sub(_mask, text)
    return text


def _mask(match):
    """Redact this match unless its value is already a marker.

    Per match, not per line: a line carrying one redacted value must not shield
    a second, still-real secret beside it.
    """
    prefix, value = match.group(1), match.group(2)
    return prefix + (value if "[REDACTED" in value else "[REDACTED]")


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def _log_name(prefix, label):
    """A retained diagnostic never takes its name from an unsanitised value."""
    cleaned = _SAFE_NAME.sub("_", str(label) if label else "")
    return f"{prefix}-{cleaned or 'unknown'}.log"


def _diagnostic(directory, name, result):
    """Retain a failed command's output without putting it in the error.

    The output is redacted by value and the file is owner-only: a failing
    deployment tool commonly echoes the token or header it failed with, and a
    retained diagnostic must not be where that ends up readable.
    """
    if directory.is_symlink():
        raise CloudflareDeployError("diagnostic directory is unsafe")
    directory.mkdir(parents=True, exist_ok=True)
    # Containment after creation catches an ancestor that pointed elsewhere; it
    # does not close the swap-between-check-and-open race, which #1487 owns.
    if directory.resolve().parent != directory.parent.resolve():
        raise CloudflareDeployError("diagnostic directory resolves outside its root")
    path = directory / name
    body = _redacted((result.stdout or "") + (result.stderr or ""))
    # O_NOFOLLOW: the directory is an operator-supplied path that other local
    # operators may share, and the diagnostic name is predictable, so a
    # pre-placed link must not redirect this write.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError:
        raise CloudflareDeployError("could not retain a diagnostic safely") from None
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(body)
    return path


def _completed(command, *, cwd, timeout, environment=None):
    """Run one command, turning every launch and timeout failure into ours."""
    try:
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout, env=environment)
    except subprocess.TimeoutExpired as expired:
        # Always launched with text=True, so whatever was captured is str.
        return type("Expired", (), {
            "returncode": 124, "stdout": expired.stdout or "",
            "stderr": f"timed out after {timeout}s"})()
    except OSError:
        # A missing interpreter or unresolvable PATH is a failed leg, not a
        # traceback out of the entry point.
        return type("Unlaunched", (), {
            "returncode": 127, "stdout": "", "stderr": "command could not be launched"})()


def real_adapter(diagnostics, *, timeout=2400):
    """`scripts/cloudflare-host.sh`, with its output retained rather than raised.

    The adapter talks to Cloudflare and GitHub, so its stderr is exactly the
    text that must not become an error message; it is written beside the run
    instead and the failure names the file.
    """
    def run(arguments):
        result = _completed(
            ["bash", str(ROOT / "scripts" / "cloudflare-host.sh"), *arguments],
            cwd=ROOT, timeout=timeout)
        if result.returncode:
            path = _diagnostic(diagnostics, _log_name("adapter", arguments[0]),
                               result)
            raise CloudflareDeployError(f"{arguments[0]} failed; inspect {path}")
        return result.stdout
    return run


def real_http_verification():
    """The Host smoke, reported as the exact True the sequence requires."""
    from cloudflare_smoke import smoke

    def verify(distribution, url, preview):
        try:
            observed = smoke(distribution, url, preview=preview)
        except Exception:
            # Upstream text may embed credentials; the category is the report.
            raise CloudflareDeployError(
                f"exact signed HTTP verification of {url} failed") from None
        return isinstance(observed, dict) and observed.get("status") == "passed"
    return verify


def real_browser(host, diagnostics, *, timeout=900):
    """The Host's existing Playwright deployment spec, against one base URL."""
    project, spec, prefix = BROWSER[host]

    def check(url):
        environment = {name: os.environ[name] for name in BROWSER_ENVIRONMENT
                       if name in os.environ}
        environment.update({"LMDJ_WEB_HOST_CLEAN_ROOM": "1",
                            f"{prefix}_EXTERNAL_SERVER": "1",
                            f"{prefix}_BASE_URL": url})
        result = _completed(
            ["npm", "--prefix", str(ROOT / "tests/platform/web"), "test", "--",
             f"--project={project}", "--reporter=json", spec],
            cwd=ROOT, timeout=timeout, environment=environment)
        if result.returncode or not _browser_ran(result.stdout):
            path = _diagnostic(diagnostics,
                               _log_name("browser", urlsplit(url).hostname),
                               result)
            raise CloudflareDeployError(f"browser check of {url} failed; inspect {path}")
        return True
    return check


def _browser_ran(output):
    """True only when the spec actually ran and every test passed.

    A zero exit is not proof: a project or spec filter that matches nothing, or
    a skipped spec, exits cleanly and would otherwise be written into the
    evidence as a passed browser check.
    """
    try:
        report = json.loads(output)
    except (TypeError, ValueError):
        return False
    stats = report.get("stats") if isinstance(report, dict) else None
    if not isinstance(stats, dict):
        return False
    expected = stats.get("expected")
    return (isinstance(expected, int) and expected > 0
            and stats.get("unexpected") == 0 and stats.get("flaky") == 0
            and stats.get("skipped") == 0)


def real_site_reader():
    from cloudflare_site_observation import ObservationError, observe

    def read(url):
        try:
            return observe(url)
        except ObservationError as error:
            raise CloudflareDeployError(f"could not observe {url} ({error})") from None
        except Exception:
            raise CloudflareDeployError(f"could not observe {url}") from None
    return read


def _clock():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Deploy one Host to Cloudflare")
    parser.add_argument("tag")
    parser.add_argument("--target", required=True, choices=CONTRACT_HOSTS)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--wrangler", required=True)
    parser.add_argument("--prior-tag")
    arguments = parser.parse_args(argv)
    # Beside this run's own state, not beside the evidence: a failed run must
    # not create anything at or around the output path a caller checks for.
    diagnostics = arguments.state_root / "diagnostics"
    try:
        if not arguments.state_root.is_absolute():
            raise CloudflareDeployError(
                "requires an absolute state root shared by all local operators")
        written = deploy(
            host=arguments.target, tag=arguments.tag, run_id=arguments.run_id,
            state_root=arguments.state_root, output=arguments.output,
            node=arguments.node, wrangler=arguments.wrangler,
            adapter=real_adapter(diagnostics),
            verify_http=real_http_verification(),
            browser=real_browser(arguments.target, diagnostics),
            read_site=real_site_reader(), clock=_clock,
            prior_tag=arguments.prior_tag)
    except CloudflareDeployError as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception:
        # A backstop, not a substitute for attributing failures above: an
        # unexpected exception must not become a traceback whose text could
        # carry credentials into the log.
        print(str(CloudflareDeployError("failed for an unattributed reason")),
              file=sys.stderr)
        return 2
    print(json.dumps({"host": arguments.target, "tag": arguments.tag,
                      "evidence": str(written)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
