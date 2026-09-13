"""Fresh read-only Host verification using the canonical Netlify/HTTP validators.

The frozen projection comes from authenticated parent evidence/configuration,
not discovery of whatever happens to be online. This is a point-in-time HTTP
and Site-pointer check, not browser acceptance or release-operation authority.
"""
from dataclasses import asdict
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import sys
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .batch_reference import digest
from .dispatch_receipt import unique
from .deployment_effect import DeploymentEffect
from .model import canonical_sha256
from .orchestration import JournalError
from .orchestration_driver import Observation

ROOT = Path(__file__).resolve().parents[2]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_netlify = _load("_lmdj_release_site_api", "apps/web-runtime-host/tools/netlify_api.py")
_smoke = _load("_lmdj_release_http_smoke", "apps/web-runtime-host/tools/deployment_smoke.py")
HOSTS = {"runtime":("web-runtime-host", "lmdj-runtime"), "creator":("creator-web", "lmdj-creator")}
API_BASE = "https://api.netlify.com/api/v1"
SITE_PATTERN = re.compile(r"[A-Za-z0-9-]+")


def require(value, reason):
    if not value:
        raise JournalError(f"why: live Host verification {reason}; remedy: reconcile the frozen release and current Site state without deploying or changing its pointer")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        fp.close()
        raise JournalError("why: Site API redirected; remedy: restore direct trusted API access; credentials were not forwarded")


class SiteReader(_netlify.NetlifyClient):
    """Reuse canonical get_site parsing, with a closed GET-only transport."""
    def __init__(self, *, token):
        super().__init__(token=token, api_base=API_BASE)

    def _request_with_status(self, *args, **kwargs):
        require(False, "general deployment transport is disabled")

    def _json_request(self, method, endpoint, document, deadline):
        require(method == "GET" and document is None and deadline is None
                and re.fullmatch(r"/sites/[A-Za-z0-9-]+", endpoint) is not None,
                "API operation is outside the read-only Site scope")
        operation = Request(API_BASE + endpoint, method="GET", headers={
            "Accept":"application/json", "Authorization":"Bearer " + self._token,
            "User-Agent":"LMDJ-Release-Site-Verification/1"})
        try:
            opener = build_opener(_NoRedirect())
            opener.addheaders = []
            with opener.open(operation, timeout=10) as response:
                require(response.status == 200 and response.geturl() == API_BASE + endpoint,
                        "API response identity differs")
                payload = response.read(1024 * 1024 + 1)
                require(len(payload) <= 1024 * 1024, "API response exceeds the size bound")
            return json.loads(payload, object_pairs_hook=unique)
        except Exception as error:
            # Never expose credential material or a response body in diagnostics.
            closer = getattr(error, "close", None)
            if callable(closer):
                try: closer()
                except Exception: pass
            raise JournalError("why: Site API is unavailable or invalid; remedy: restore read access and reconcile the original Site without mutation") from None


class LiveHostVerifier:
    def __init__(self, reader):
        require(type(reader) is SiteReader, "trusted read-only Site reader is missing")
        self.reader = reader

    def verify(self, host, expected):
        expected = deepcopy(expected)
        require(host in HOSTS and type(expected) is dict and set(expected) == {
            "site_id", "deploy_id", "product_build", "host_version", "index_sha256", "manifest_sha256"},
            "frozen Host projection is missing")
        require(all(type(expected[k]) is str and SITE_PATTERN.fullmatch(expected[k])
                    for k in ("site_id", "deploy_id"))
                and type(expected["product_build"]) is str and re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}", expected["product_build"])
                and type(expected["host_version"]) is str and re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", expected["host_version"])
                and digest(expected["index_sha256"]) and digest(expected["manifest_sha256"]),
                "frozen Host identity is invalid")
        host_id, site_name = HOSTS[host]
        production = f"https://{site_name}.netlify.app"
        immutable = f"https://{expected['deploy_id'].lower()}--{site_name}.netlify.app"

        def site():
            try:
                current = self.reader.get_site(site_id=expected["site_id"])
            except Exception:
                raise JournalError("why: current Site identity is unreadable; remedy: restore trusted read access without deploying") from None
            require(current.id == expected["site_id"] and current.state == "current"
                    and current.ssl_url == production and current.published_deploy is not None
                    and current.published_deploy.id == expected["deploy_id"]
                    and current.published_deploy.site_id == expected["site_id"]
                    and current.published_deploy.deploy_ssl_url == immutable
                    and current.published_deploy.state == "ready", "production pointer differs from the frozen deployment")
            return asdict(current)

        before = site()
        proofs = {}
        for name, url in (("immutable", immutable), ("production", production)):
            try:
                result = _smoke.smoke_http(base_url=url,
                    expected_product_build=expected["product_build"], expected_host_version=expected["host_version"],
                    expected_host_id=host_id, expected_deploy_id=expected["deploy_id"] if name == "immutable" else None,
                    expected_index_sha256=expected["index_sha256"], expected_manifest_sha256=expected["manifest_sha256"],
                    require_https=True, timeout_seconds=10)
            except Exception:
                raise JournalError("why: live Host HTTP verification failed; remedy: reconcile immutable and production content without replacing the deployment") from None
            require(all(result[k] == expected[k] for k in ("index_sha256", "manifest_sha256")),
                    "published bytes differ from the frozen release")
            proofs[name] = result
        require(site() == before, "Site changed during live verification")
        # Stable identity for durable comparison; every invocation does fresh I/O.
        # A stable digest is not a cache or proof that the Site stayed unchanged.
        evidence = {"schema":"lmdj.live-host-verification.v1", "host":host,
                    "expected":dict(expected), "site":before, "http":proofs}
        return {"sha256":canonical_sha256(evidence), "reference":production, "record":evidence}


class LiveDeploymentEffect:
    """Compose recorded and fresh evidence at the real managed Host boundary."""
    def __init__(self, *, recorded, live):
        require(type(recorded) is DeploymentEffect and type(live) is LiveHostVerifier,
                "trusted recorded/live verifiers are missing")
        self.recorded, self.live = recorded, live

    def __call__(self, state, operation, binding):
        try:
            before = self.recorded(state, operation, binding)
            if before.status != "verified": return before
            document, artifact, _, _ = self.recorded._document(binding)
            require(canonical_sha256({"document":document, "artifact":artifact}) == before.evidence["sha256"],
                    "retained deployment changed before live verification")
            expected = self.recorded.expected
            live = self.live.verify(self.recorded.step, {
                **{k:expected[k] for k in ("site_id", "product_build", "host_version")},
                **expected["release_files"], "deploy_id":document["immutable"]["deploy_id"]})
            require(self.recorded(state, operation, binding) == before,
                    "recorded deployment changed during live verification")
            return Observation("verified", {"sha256":canonical_sha256({"recorded":before.evidence, "live":live["sha256"]}),
                "reference":live["reference"]})
        except Exception:
            return Observation("unknown")
