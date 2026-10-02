#!/usr/bin/env python3
"""Host promotion/recovery transaction over verified retained versions.

The trusted caller owns signed-artifact binding, candidate upload, a shared
operator lock, and a durable observer. Verification must check the exact bytes
bound to the supplied version; neither a version ID nor this module proves a
Release signature. No Netlify evidence Contract is emitted.
"""
import time

from cloudflare_api import CloudflareError, version_id

# A production version or route change is not served by every edge at once.
# Verifying the stable URL immediately after a mutation saw the previous bytes
# and failed both the promotion and its recovery (1.0.66.0 Creator). The
# stable check after a mutation therefore waits, bounded, for the exact
# expected bytes; it never accepts anything else.
SETTLE_SECONDS = 90
SETTLE_INTERVAL = 5


class TransactionError(RuntimeError):
    pass


def _reason(error):
    """A bounded, single-line reason for the retained adapter log."""
    text = " ".join(str(error).split()) or type(error).__name__
    return text[:400]


def promote(client, *, candidate, verify, observe, settle_seconds=None,
            interval=None, sleep=None, clock=None):
    """verify(version, url) returns exactly True; observe(event) persists it.

Observer failures stop progress. Unknown write receipts require manual
reconciliation: another operator could have issued the same version update.
Automatic recovery requires a positive deployment receipt still matching live
state. Pre/post checks detect observed races but do not replace the caller lock.
"""
    candidate = version_id(candidate)
    settle_seconds = SETTLE_SECONDS if settle_seconds is None else settle_seconds
    interval = SETTLE_INTERVAL if interval is None else interval
    sleep = time.sleep if sleep is None else sleep
    clock = time.monotonic if clock is None else clock
    stable = f"https://{client.worker}.lmdj.workers.dev"
    def preview(version):
        return f"https://{version[:8]}-{client.worker}.lmdj.workers.dev"
    def event(kind, **fields):
        observe({"event": kind, "worker": client.worker, **fields})
    def check(version, url):
        if verify(version, url) is not True:
            raise TransactionError("why: exact-version verification failed; remedy: inspect retained artifact and HTTP/browser evidence")
        event("verified", version=version, url=url)
    def settled(version, url):
        """`check` after a production mutation: retry until the exact bytes serve."""
        deadline = clock() + settle_seconds
        while True:
            try:
                return check(version, url)
            except Exception as error:
                if clock() >= deadline:
                    raise
                event("verification-pending", version=version, url=url, reason=_reason(error))
                sleep(interval)
    def unchanged(deployment, route):
        if client.deployment() != deployment or client.route() != route:
            raise TransactionError("why: observed concurrent deployment or route change; remedy: reconcile operator state")

    prior = client.deployment()
    prior_route = client.route()
    if not prior_route["previews_enabled"]:
        raise TransactionError("why: version previews are disabled; remedy: configure the isolated candidate path before promotion")
    client.require_version(candidate)
    event("prepared", candidate=candidate, prior=prior, prior_route=prior_route)
    published = None
    intended_route = {"enabled": True, "previews_enabled": True}
    try:
        if prior_route["enabled"]:
            client.require_version(prior["version_id"])
            check(prior["version_id"], preview(prior["version_id"]))
            check(prior["version_id"], stable)
        check(candidate, preview(candidate))
        unchanged(prior, prior_route)
        event("publication-starting", candidate=candidate, expected_deployment=prior["id"])
        published = client.publish(version=candidate, expected_deployment=prior["id"])
        event("published", deployment=published)
        # Do not silently overwrite a route edit observed since candidate smoke.
        unchanged(published, prior_route)
        event("route-starting", deployment=published, enabled=True)
        client.set_route(enabled=True, expected_deployment=published["id"])
        settled(candidate, stable)
        unchanged(published, intended_route)
        event("passed", deployment=published, route=intended_route)
        return published
    except Exception as error:
        failure = _reason(error)
        if isinstance(error, CloudflareError) and error.outcome_unknown:
            event("reconciliation-required", candidate=candidate, reason="unknown-mutation-receipt")
            raise TransactionError("why: mutation outcome unknown; remedy: reconcile live receipts before another mutation") from None
        if published is None:
            event("failed-before-publication", candidate=candidate, reason=failure)
            raise TransactionError(f"why: candidate/preflight failed ({failure}); remedy: inspect verification before publishing") from None
        try:
            current = client.deployment()
            route = client.route()
            if current != published or route not in (prior_route, intended_route):
                event("reconciliation-required", candidate=candidate, reason="concurrent-change")
                raise TransactionError("concurrent state")
            event("recovery-starting", published=published, prior=prior, prior_route=prior_route,
                  reason=failure)
            if prior_route["enabled"]:
                recovered = client.publish(version=prior["version_id"], expected_deployment=published["id"])
                client.set_route(enabled=True, expected_deployment=recovered["id"])
                check(prior["version_id"], preview(prior["version_id"]))
                settled(prior["version_id"], stable)
                unchanged(recovered, intended_route)
                event("recovered", deployment=recovered, route=intended_route)
            else:
                client.set_route(enabled=False, expected_deployment=published["id"])
                disabled = {"enabled": False, "previews_enabled": True}
                unchanged(published, disabled)
                event("disabled-first-publication", deployment=published, route=disabled)
        except Exception as recovery_error:
            recovery = _reason(recovery_error)
            event("recovery-unconfirmed", candidate=candidate, reason=failure, recovery=recovery)
            raise TransactionError(
                f"why: recovery not confirmed (production: {failure}; recovery: {recovery}); "
                "remedy: reconcile deployment, route and exact prior bytes") from None
        raise TransactionError(
            f"why: production verification failed and recovery completed ({failure}); "
            "remedy: inspect failed candidate before retry") from None
