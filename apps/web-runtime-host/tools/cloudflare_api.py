#!/usr/bin/env python3
"""Bounded Workers API transport for the fixed Host deployment targets.

No upload or automatic retry. A failed mutation receipt is unknown until the
caller reconciles live state. Deployment checks detect observed concurrency;
they are not an atomic compare-and-swap or a distributed operator lock.
"""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ACCOUNT = "0b62b8881c07f48f7935f5380a1f55db"
TARGETS = {"creator-web": "creator", "web-runtime-host": "lab",
           "creator-recovery": "creator-recovery", "runtime-recovery": "lab-recovery",
           "creator-initialization": "creator-initialization",
           "runtime-initialization": "lab-initialization"}
MAX_RESPONSE = 1024 * 1024
_ABSENT = object()


class CloudflareError(RuntimeError):
    def __init__(self, message, *, outcome_unknown=False):
        super().__init__(f"why: {message}; remedy: reconcile the exact Worker state before another mutation")
        self.outcome_unknown = outcome_unknown


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def version_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value):
        raise CloudflareError("invalid Cloudflare version identity")
    return value


class CloudflareClient:
    def __init__(self, *, token, target, account=ACCOUNT):
        if account != ACCOUNT or target not in TARGETS:
            raise CloudflareError("unconfigured Cloudflare account or Host target")
        if not isinstance(token, str) or not token or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise CloudflareError("invalid Cloudflare credential")
        self.worker = TARGETS[target]
        self._token = token
        self._base = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/workers/scripts/{self.worker}/"
        self._opener = build_opener(NoRedirect())

    def _request(self, endpoint, payload=None, *, allow_absent=False):
        # Only callers below select literal endpoints or validated UUID suffixes.
        mutation = payload is not None
        req = Request(self._base + endpoint, headers={"Authorization": "Bearer " + self._token,
                      "Content-Type": "application/json"},
                      data=json.dumps(payload).encode() if mutation else None)
        try:
            with self._opener.open(req, timeout=30) as response:
                if response.geturl() != req.full_url or response.status != 200:
                    raise ValueError("unexpected transport response")
                raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise ValueError("oversize response")
                envelope = json.loads(raw)
                if not isinstance(envelope, dict) or envelope.get("success") is not True or "result" not in envelope:
                    raise ValueError("invalid API envelope")
                return envelope["result"]
        except (HTTPError, URLError, OSError, ValueError) as error:
            if isinstance(error, HTTPError):
                try:
                    if allow_absent and not mutation and error.code == 404:
                        raw = error.read(MAX_RESPONSE + 1)
                        body = json.loads(raw) if len(raw) <= MAX_RESPONSE else None
                        errors = body.get('errors') if isinstance(body, dict) else None
                        if (body.get('success') is False and isinstance(errors, list)
                                and len(errors) == 1 and isinstance(errors[0], dict)
                                and errors[0].get('code') == 10007):
                            return _ABSENT
                except (ValueError, OSError, AttributeError):
                    pass
                finally:
                    error.close()
            raise CloudflareError("Cloudflare API receipt unavailable or invalid", outcome_unknown=mutation) from None

    def exists(self):
        result = self._request('settings', allow_absent=True)
        if result is _ABSENT:
            return False
        if not isinstance(result, dict):
            raise CloudflareError('invalid Worker settings receipt')
        return True

    def deployment(self):
        result = self._request("deployments")
        rows = result.get("deployments") if isinstance(result, dict) else None
        if not isinstance(rows, list) or not rows:
            raise CloudflareError("no usable active deployment")
        row = rows[0]
        if not isinstance(row, dict):
            raise CloudflareError("invalid active deployment")
        identity = version_id(row.get("id"))
        versions = row.get("versions")
        if (not isinstance(versions, list) or len(versions) != 1 or not isinstance(versions[0], dict)
                or type(versions[0].get("percentage")) not in (int, float) or versions[0]["percentage"] != 100):
            raise CloudflareError("Host deployment is not a single version at 100 percent")
        return {"id": identity, "version_id": version_id(versions[0].get("version_id"))}

    def route(self):
        result = self._request("subdomain")
        if not isinstance(result, dict) or any(type(result.get(k)) is not bool for k in ("enabled", "previews_enabled")):
            raise CloudflareError("invalid Worker route receipt")
        return {k: result[k] for k in ("enabled", "previews_enabled")}

    def require_version(self, value):
        value = version_id(value)
        result = self._request("versions/" + value)
        if not isinstance(result, dict) or result.get("id") != value:
            raise CloudflareError("version does not match this Worker")
        return value

    def _expect(self, expected_deployment):
        version_id(expected_deployment)
        if self.deployment()["id"] != expected_deployment:
            raise CloudflareError("active deployment changed concurrently")

    def publish(self, *, version, expected_deployment):
        version = self.require_version(version)
        self._expect(expected_deployment)
        # The same operation restores a retained version; it never rebuilds it.
        receipt = self._request("deployments", {"strategy": "percentage", "versions": [{"version_id": version, "percentage": 100}]})
        try:
            if not isinstance(receipt, dict):
                raise CloudflareError("invalid publication identity receipt")
            receipt_id = version_id(receipt.get("id"))
            current = self.deployment()
            if current != {"id": receipt_id, "version_id": version}:
                raise CloudflareError("publication was superseded or unconfirmed")
            return current
        except CloudflareError:
            raise CloudflareError("publication requires reconciliation", outcome_unknown=True) from None

    def set_route(self, *, enabled, expected_deployment):
        if type(enabled) is not bool:
            raise CloudflareError("route enabled flag must be boolean")
        self._expect(expected_deployment)
        self._request("subdomain", {"enabled": enabled, "previews_enabled": True})
        try:
            result = self.route()
            self._expect(expected_deployment)
            if result != {"enabled": enabled, "previews_enabled": True}:
                raise CloudflareError("route mutation unconfirmed")
            return result
        except CloudflareError:
            raise CloudflareError("route mutation requires reconciliation", outcome_unknown=True) from None
