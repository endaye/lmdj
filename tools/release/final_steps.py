"""Read-back carriers for the `changelog_site` and `final` steps.

Both steps verify effects that other steps or Git-triggered deployments
produce; neither performs a write. `ChangelogSiteCarrier` fetches the
deployed doc-site routes for this Build and refuses divergence from the
prepared identities; `FinalCarrier` re-reads every far-side identity the
sequence recorded (published Release projection, ledger row channel and
disposition, snapshot presence) and verifies the whole chain at once. A
route must serve a page that names this Build — a 200 alone is not proof —
and the served body digests are bound into the evidence. The
driver treats a carrier without `advance` as observe-only: the step passes
when the far side is already true and reports `absent` before it is.
"""

from copy import deepcopy
import http.client
import re

from .model import CHANNEL_ORDER, STABLE_PROMOTION_QUESTION, canonical_sha256
from .orchestration_driver import Observation


class SiteStepError(ValueError):
    pass


def _fail(reason):
    raise SiteStepError(
        f"why: far-side verification {reason}; remedy: reconcile the deployed "
        "site and the recorded release identities; never fabricate a pass")


_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_BUILD = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.0\Z")
_TAG = re.compile(r"lmdj-v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\."
                  r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")


def _base_spec_keys(extra):
    return {"operation_id", "request_sha256", "repository_id", "actor_id",
            "tag", "product_build", "target_revision"} | set(extra)


def site_operation_id(request_sha256):
    return canonical_sha256({"request": request_sha256, "step": "changelog_site"})


def final_operation_id(request_sha256):
    return canonical_sha256({"request": request_sha256, "step": "final"})


def _validate_common(spec, operation_id):
    if not all(type(spec[k]) is str and _DIGEST.fullmatch(spec[k])
               for k in ("operation_id", "request_sha256")):
        _fail("scope digests are invalid")
    if spec["operation_id"] != operation_id(spec["request_sha256"]):
        _fail("operation differs from the original request")
    if type(spec["tag"]) is not str or _TAG.fullmatch(spec["tag"]) is None:
        _fail("tag is invalid")
    if type(spec["product_build"]) is not str or _BUILD.fullmatch(spec["product_build"]) is None \
            or spec["tag"] != "lmdj-v" + spec["product_build"]:
        _fail("tag does not match the product build")
    if type(spec["target_revision"]) is not str \
            or _SHA.fullmatch(spec["target_revision"]) is None:
        _fail("target revision is invalid")
    if type(spec["repository_id"]) is not int or spec["repository_id"] <= 0 \
            or type(spec["actor_id"]) is not int or spec["actor_id"] <= 0:
        _fail("numeric scope identities are invalid")


def validate_site_spec(spec):
    if type(spec) is not dict or set(spec) != _base_spec_keys({"site_base_url"}):
        _fail("site scope fields are invalid")
    _validate_common(spec, site_operation_id)
    url = spec["site_base_url"]
    if (type(url) is not str or not url.startswith("https://")
            or url.endswith("/") or len(url) > 200):
        _fail("site base URL is invalid")


def validate_final_spec(spec):
    if type(spec) is not dict or set(spec) != _base_spec_keys(
            {"site_base_url", "release_id", "channel"}):
        _fail("final scope fields are invalid")
    _validate_common(spec, final_operation_id)
    url = spec["site_base_url"]
    if (type(url) is not str or not url.startswith("https://")
            or url.endswith("/") or len(url) > 200):
        _fail("site base URL is invalid")
    if type(spec["release_id"]) is not int or spec["release_id"] <= 0:
        _fail("release id is invalid")
    # `stable` is unreachable: promotion refuses it because D8 forbids flipping
    # the prerelease flag on a published Release.
    if spec["channel"] not in CHANNEL_ORDER or spec["channel"] == "stable":
        _fail(f"channel is invalid: stable promotion is not implemented; see "
              f"{STABLE_PROMOTION_QUESTION}")


def site_routes(spec):
    """Derive the doc-site routes; accepts either step's closed spec shape."""
    tag = spec.get("tag") if isinstance(spec, dict) else None
    build = spec.get("product_build") if isinstance(spec, dict) else None
    base = spec.get("site_base_url") if isinstance(spec, dict) else None
    if type(tag) is not str or _TAG.fullmatch(tag) is None:
        _fail("tag is invalid")
    if type(build) is not str or _BUILD.fullmatch(build) is None \
            or tag != "lmdj-v" + build:
        _fail("tag does not match the product build")
    if type(base) is not str or not base.startswith("https://") \
            or base.endswith("/") or len(base) > 200:
        _fail("site base URL is invalid")
    return {"version": f"{base}/versions/{build}/",
            "release": f"{base}/releases/{build}"}


def _fetch_route(fetch, url):
    """fetch(url) -> (status, body); transport failure is (0, None).

    Only transport failure is swallowed (the site is unreachable → the caller
    reports `unknown`, never a pass). A defect in the trusted fetch callable —
    a wrong signature, a non-HTTP status or a non-text body — must surface
    instead of being silently coerced.
    """
    try:
        answer = fetch(url)
    except (OSError, http.client.HTTPException):
        # URLError, timeouts, connection resets, protocol errors: the site is
        # unreachable, which the callers report as `unknown`, never a pass.
        return 0, None
    if type(answer) is not tuple or len(answer) != 2:
        raise SiteStepError(
            f"why: the site fetch returned {answer!r}, not a (status, body) "
            "pair; remedy: fix the trusted fetch callable")
    status, body = answer
    if type(status) is not int or status <= 0:
        raise SiteStepError(
            f"why: the site fetch returned {status!r}, not an HTTP status; "
            "remedy: fix the trusted fetch callable")
    if status == 200 and type(body) is not str:
        raise SiteStepError(
            f"why: the site fetch returned a {type(body).__name__} body for "
            "HTTP 200; remedy: fix the trusted fetch callable")
    return status, body


def _body_digest(body):
    return canonical_sha256({"body": body})


def _proves_build(body, product_build):
    """The deployed page must name this Build, as the site smoke lane asserts.

    A 200 alone proves nothing: a catch-all route or a stale deployment also
    answers 200 on a Build's URL.
    """
    return type(body) is str and f"Product Build {product_build}" in body


class ChangelogSiteCarrier:
    """Observe-only: the deployed doc-site must serve this Build's routes."""

    def __init__(self, *, spec, fetch):
        validate_site_spec(spec)
        if not callable(fetch):
            _fail("requires the trusted site fetch")
        self.spec = deepcopy(spec)
        self.fetch = fetch

    def observe(self, state, operation):
        routes = site_routes(self.spec)
        fetched = {name: _fetch_route(self.fetch, url)
                   for name, url in routes.items()}
        statuses = {name: status for name, (status, _) in fetched.items()}
        # A fully absent site is "not yet deployed"; a partial one (one route
        # live, one 404) is an inconsistency the driver must see, not wait on.
        if all(status == 404 for status in statuses.values()):
            return Observation("absent")
        if any(status == 404 for status in statuses.values()):
            return Observation("conflict")
        if any(status != 200 for status in statuses.values()):
            # Unreachable or erroring site is not proof of absence.
            return Observation("unknown")
        if any(not _proves_build(body, self.spec["product_build"])
               for _, body in fetched.values()):
            # A 200 that does not name this Build is another Build's page.
            return Observation("conflict")
        evidence = {"sha256": canonical_sha256({
            "tag": self.spec["tag"], "routes": routes, "statuses": statuses,
            "bodies": {name: _body_digest(body)
                       for name, (_, body) in fetched.items()}}),
            "reference": "site:" + routes["version"]}
        return Observation("verified", evidence)


class FinalCarrier:
    """Observe-only aggregate: verify every recorded far-side identity."""

    def __init__(self, *, spec, fetch, release_by_tag, ledger_row):
        """The readers take the identity: release_by_tag(tag), ledger_row(tag).

        The carrier owns the identity it verifies, so a reader cannot read a
        different release than the one the spec froze.
        """
        validate_final_spec(spec)
        if not all(callable(it) for it in (fetch, release_by_tag, ledger_row)):
            _fail("requires the trusted far-side readers")
        self.spec = deepcopy(spec)
        self.fetch = fetch
        self.release_by_tag = release_by_tag
        self.ledger_row = ledger_row

    def observe(self, state, operation):
        release = self.release_by_tag(self.spec["tag"])
        row = self.ledger_row(self.spec["tag"])
        if release is None and row is None:
            return Observation("absent")
        if release is None or row is None:
            # A Release without its ledger row (or the reverse) is a
            # partially applied promotion, never one still to do.
            return Observation("conflict")
        if not hasattr(release, "get"):
            _fail("the far-side Release projection is not readable")
        if not (hasattr(row, "get") or hasattr(row, "tag")):
            _fail("the ledger row projection is not readable")

        def field(row, name):
            return row.get(name) if hasattr(row, "get") else getattr(row, name, None)
        missing = sorted(name for name in ("tag", "target_revision", "channel",
                                           "disposition")
                         if field(row, name) is None)
        if missing:
            _fail(f"the ledger row omits {', '.join(missing)}")
        if field(row, "tag") != self.spec["tag"] \
                or field(row, "target_revision") != self.spec["target_revision"] \
                or field(row, "channel") != self.spec["channel"] \
                or field(row, "disposition") != "published":
            _fail("the ledger row does not record this release as published "
                  "in the promoted channel")
        if release.get("draft"):
            _fail("the far-side Release is still a draft")
        if release.get("id") != self.spec["release_id"]:
            _fail("the far-side Release id differs from the recorded one")
        routes = site_routes(self.spec)
        fetched = {name: _fetch_route(self.fetch, url)
                   for name, url in routes.items()}
        statuses = {name: status for name, (status, _) in fetched.items()}
        # The ledger row already proved this release is published here, so a
        # missing route is an inconsistency, never "not deployed yet".
        if any(status == 404 for status in statuses.values()):
            return Observation("conflict")
        if any(status != 200 for status in statuses.values()):
            return Observation("unknown")
        if any(not _proves_build(body, self.spec["product_build"])
               for _, body in fetched.values()):
            # A 200 that does not name this Build is another Build's page.
            return Observation("conflict")
        evidence = {"sha256": canonical_sha256({
            "tag": self.spec["tag"], "release_id": self.spec["release_id"],
            "channel": self.spec["channel"],
            "target_revision": self.spec["target_revision"],
            "row": {"tag": field(row, "tag"),
                    "target_revision": field(row, "target_revision"),
                    "channel": field(row, "channel"),
                    "disposition": field(row, "disposition")},
            "routes": routes, "statuses": statuses,
            "bodies": {name: _body_digest(body)
                       for name, (_, body) in fetched.items()}}),
            "reference": "final:" + self.spec["tag"]}
        return Observation("verified", evidence)
