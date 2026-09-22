"""Fresh read-only Cloudflare Host proof at managed deployment boundaries.

The trusted parent supplies an authenticated frozen projection. This module
neither discovers release authority nor composes itself into production.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import sys
from urllib.request import Request, build_opener

from .batch_reference import digest
from .dispatch_receipt import unique
from .deployment_effect import DeploymentEffect
from .model import canonical_sha256
from .orchestration import JournalError
from .orchestration_driver import Observation

ROOT = Path(__file__).resolve().parents[2]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "apps/web-runtime-host/tools" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_api = _load("_release_cloudflare_api", "cloudflare_api.py")
_evidence = _load("_release_cloudflare_evidence", "cloudflare_deployment_evidence.py")
_smoke = _load("_release_cloudflare_smoke", "cloudflare_smoke.py")
_origin = _load("_release_cloudflare_origin", "cloudflare_site_observation.py")
HOSTS = {"runtime": "web-runtime-host", "creator": "creator-web"}


def require(value, reason):
    if not value:
        raise JournalError(f"why: live Host verification {reason}; remedy: reconcile the frozen release and current Worker without deploying or changing its pointer")


class WorkerReader(_api.CloudflareClient):
    """The parser used by `cloudflare_host inspect`, behind a closed GET transport."""
    def __init__(self, *, token, target):
        require(target in HOSTS.values(), "reader target is outside the managed Hosts")
        super().__init__(token=token, target=target)

    def _request(self, endpoint, payload=None, *, allow_absent=False):
        require(endpoint in ("deployments", "subdomain") and payload is None
                and allow_absent is False, "API operation is outside the read-only Worker scope")
        operation = Request(self._base + endpoint, method="GET", headers={
            "Accept": "application/json", "Authorization": "Bearer " + self._token,
            "User-Agent": "LMDJ-Release-Worker-Verification/1"})
        try:
            opener = build_opener(_api.NoRedirect())
            opener.addheaders = []
            with opener.open(operation, timeout=10) as response:
                require(response.status == 200 and response.geturl() == operation.full_url,
                        "API response identity differs")
                payload = response.read(_api.MAX_RESPONSE + 1)
                require(len(payload) <= _api.MAX_RESPONSE, "API response exceeds the size bound")
            envelope = json.loads(payload, object_pairs_hook=unique)
            require(type(envelope) is dict and envelope.get("success") is True
                    and "result" in envelope, "API envelope is invalid")
            return envelope["result"]
        except Exception as error:
            closer = getattr(error, "close", None)
            if callable(closer):
                try: closer()
                except Exception: pass
            raise JournalError("why: Worker API is unavailable or invalid; remedy: restore read access and reconcile the original Worker without mutation") from None

    def publish(self, **kwargs):
        require(False, "deployment writes are disabled")

    def set_route(self, **kwargs):
        require(False, "route writes are disabled")


class LiveHostVerifier:
    def __init__(self, reader):
        require(type(reader) is WorkerReader, "trusted read-only Worker reader is missing")
        self.reader = reader

    def verify(self, host, expected):
        expected = deepcopy(expected)
        require(type(host) is str and host in HOSTS and type(expected) is dict and set(expected) == {
            "worker", "version_id", "deployment_id", "product_build", "host_version", "index_sha256", "manifest_sha256"},
            "frozen Host projection is missing")
        host_id = HOSTS[host]
        require(expected["worker"] == _evidence.worker_for(host_id) == self.reader.worker
                and type(expected["product_build"]) is str
                and re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}", expected["product_build"])
                and type(expected["host_version"]) is str
                and re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", expected["host_version"])
                and digest(expected["index_sha256"]) and digest(expected["manifest_sha256"]),
                "frozen Host identity is invalid")
        try:
            _api.version_id(expected["deployment_id"])
            immutable = _evidence.version_url(host_id, expected["version_id"])
        except Exception:
            require(False, "frozen deployment identity is invalid")
        production = _evidence.production_url(host_id)

        def current():
            try:
                deployment = self.reader.deployment()
                require(deployment == {"id": expected["deployment_id"], "version_id": expected["version_id"]},
                        "production pointer differs from the frozen deployment")
                route = self.reader.route()
                require(route == {"enabled": True, "previews_enabled": True}, "required Worker routes are disabled")
                return {"worker": self.reader.worker, "deployment": deployment, "route": route}
            except Exception:
                raise JournalError("why: current Worker identity differs or is unreadable; remedy: reconcile the frozen deployment and routes without deploying") from None

        before = current()
        proofs = {}
        try:
            for side, url in (("immutable", immutable), ("production", production)):
                proofs[side] = _smoke.smoke_frozen(base_url=url, host_id=host_id,
                    **{k:expected[k] for k in ("product_build", "host_version", "index_sha256", "manifest_sha256")},
                    preview=side == "immutable")
            # Reuse the canonical public-origin observation, as the projection
            # producer does. Observation alone is never a complete Host proof.
            observed = _origin.observe(production)
            require(all(observed[k] == expected[k] for k in ("product_build", "host_version"))
                    and observed["release_files"] == {k:expected[k] for k in ("index_sha256", "manifest_sha256")},
                    "production observation differs from the frozen bytes")
        except Exception:
            raise JournalError("why: live Host HTTP verification failed; remedy: reconcile immutable and production content without replacing the deployment") from None
        require(current() == before, "Worker changed during live verification")
        evidence = {"schema": "lmdj.live-host-verification.v1", "host": host,
                    "expected": expected, "worker": before, "http": proofs, "origin": observed}
        # A stable digest is neither a cache nor continuous observation.
        return {"sha256": canonical_sha256(evidence), "reference": production, "record": evidence}


class LiveDeploymentEffect:
    """Reauthenticate recorded evidence on both sides of fresh HTTP proof."""
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
                **{k:expected[k] for k in ("product_build", "host_version")},
                **expected["release_files"], "worker":expected["site_id"],
                "version_id":document["immutable"]["version_id"],
                "deployment_id":document["publication"]["deployment_id"]})
            require(self.recorded(state, operation, binding) == before,
                    "recorded deployment changed during live verification")
            return Observation("verified", {"sha256":canonical_sha256({"recorded":before.evidence, "live":live["sha256"]}),
                "reference":live["reference"]})
        except Exception:
            return Observation("unknown")
