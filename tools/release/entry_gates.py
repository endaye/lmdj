"""Trusted entry gates for the managed candidate step's callbacks.

`CandidateTransition` requires `authorize` / `observe_main` / `review` /
`verify_merged` callables that only tests ever supplied. This module assembles
them from the production pieces: the release GitHub client and canonical Git
repository for authority and main observation, `review_inventory` plus the
`scripts.ci.review_wait` current-head verifier for exact-head review
eligibility, and canonical ancestry for the merged-squash proof. Every gate is
fail-closed: an unavailable API, a moved head or a missing receipt never reads
as approval, and callback errors carry no upstream response text.
"""

from copy import deepcopy
import re

from .model import canonical_json, canonical_sha256
from .orchestration import validate_request
from .orchestration_driver import Observation


class EntryGateError(ValueError):
    pass


def _fail(reason):
    raise EntryGateError(
        f"why: release entry gate {reason}; remedy: restore the authenticated "
        "authority, canonical main observation or complete review evidence; "
        "unavailable is never approval")


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_GATE_KINDS = ("candidate", "witness")


def authority_gate(*, github, git, policy, request):
    """The `authorize` callback: revalidate the original request's authority.

    Re-pins what the driver authenticates per transition — the authenticated
    actor, the pinned policy digest and the reachable canonical control — plus
    the request's own identity, so a gate invocation under a drifted request
    fails closed. The `authority_ref` stays an opaque reference to the
    independently authenticated authorization record; nothing here re-reads it.
    """
    validate_request(request)
    frozen = canonical_json(request)
    if policy.digest != request["policy_digest"]:
        _fail("the request's pinned policy is not the enrolled policy")

    def authorize(incoming):
        if canonical_json(incoming) != frozen:
            _fail("the gate was invoked under a different request")
        if github.get_authenticated_actor() != request["actor_id"]:
            _fail("the authenticated actor no longer matches the request")
        if not git.is_main_ancestor(request["control_revision"]):
            _fail("the pinned control revision is no longer canonical history")
        if policy.digest != request["policy_digest"]:
            _fail("the pinned policy no longer matches the request")

    return authorize


def main_observation(*, git):
    """The `observe_main` callback: the fetched canonical main revision.

    Reads the pinned `refs/lmdj-release/origin-main` the trusted fetch
    installed; it never fetches and never substitutes a local branch.
    """

    def observe_main():
        revision = git.main_revision()
        if type(revision) is not str or _SHA.fullmatch(revision) is None:
            _fail("the canonical main observation is invalid")
        return revision

    return observe_main


def review_gate(*, client, reader_for, repository_id, repository="endaye/lmdj"):
    """The `review` callback: exact-head eligibility over the complete inventory.

    Collects the complete review inventory through the release GitHub client,
    runs the current-head verifier over the authenticated REST reader, and
    binds the two trusted reader outputs with `bind_eligibility`. Only an
    eligible, linked result verifies; pending waits, a stale or invalid
    observation conflicts, and an unavailable eligibility read is unknown —
    never a pass. An unreadable inventory or a binding mismatch raises, which
    the PR controller's own gate guard reports as unavailable.
    """
    from scripts.ci.review_wait import check

    from .review_inventory import ReviewInventory, bind_eligibility

    def review(kind, spec, row):
        if kind not in _GATE_KINDS:
            _fail("unknown review gate kind")
        number = row.get("number") if isinstance(row, dict) else None
        head = spec.get("head_sha") if isinstance(spec, dict) else None
        if type(number) is not int or number <= 0 \
                or type(head) is not str or _SHA.fullmatch(head) is None:
            _fail("the review gate received no exact PR head")
        collected = ReviewInventory(client).collect(repository_id, number, head)
        eligibility = check(reader_for(repository), repository, number, head)
        if eligibility.get("eligible") is not True \
                or eligibility.get("status") != "eligible":
            mapped = {"pending": "pending", "stale": "conflict",
                      "invalid": "conflict"}.get(eligibility.get("status"),
                                                 "unknown")
            return Observation(mapped)
        linked = bind_eligibility(collected, eligibility)
        return Observation("verified", {
            "sha256": canonical_sha256({"kind": kind, "binding": linked}),
            "reference": f"review:{kind}:pr-{number}"})

    return review


def production_review_reader(*, token):
    """The review gate's REST reader factory over the authenticated transport."""
    from scripts.ci.review_wait import Reader
    from scripts.ci.self_test_report import UrllibGitHubApi

    def reader_for(repository):
        return Reader(UrllibGitHubApi(repository, token), repository)

    return reader_for


def dispatch_authority(*, github, git, policy, request):
    """The dispatch controller's `authorize`: the spec under live authority.

    The durable dispatch passes its own spec (not the request), so re-pin the
    spec's request binding, actor and control revision against the original
    request, and revalidate the live authority exactly as `authority_gate`
    does. An unavailable check raises; unavailable is never approval.
    """
    validate_request(request)
    digest = canonical_sha256(request)

    def authorize(spec):
        if type(spec) is not dict or spec.get("request_sha256") != digest:
            _fail("the dispatch spec does not bind the original request")
        if spec.get("actor_id") != request["actor_id"] \
                or spec.get("control_revision") != request["control_revision"]:
            _fail("the dispatch spec drifted from the original request")
        if github.get_authenticated_actor() != request["actor_id"]:
            _fail("the authenticated actor no longer matches the request")
        if not git.is_main_ancestor(request["control_revision"]):
            _fail("the pinned control revision is no longer canonical history")
        if policy.digest != request["policy_digest"]:
            _fail("the pinned policy no longer matches the request")

    return authorize


def merged_gate(*, git):
    """The `verify_merged` callback: the squash is real, canonical and reviewed.

    Proves the merged identity (the PR merged with the reviewed head, the
    squash is reachable canonical history) and binds the retained review
    receipt this gate's `review` produced at the merge boundary. The merged
    source content itself is proven by the transition's own source verifier
    immediately after this gate returns verified.
    """

    def verify_merged(kind, spec, row, receipt):
        if kind not in _GATE_KINDS:
            _fail("unknown merge gate kind")
        merge_sha = row.get("merge_commit_sha") if isinstance(row, dict) else None
        head = row.get("head") if isinstance(row, dict) else None
        if not isinstance(row, dict) or row.get("merged") is not True \
                or type(merge_sha) is not str or _SHA.fullmatch(merge_sha) is None:
            _fail("the far-side PR is not a merged squash")
        if not isinstance(head, dict) or head.get("sha") != spec.get("head_sha"):
            _fail("the merged PR head differs from the reviewed head")
        if not git.is_main_ancestor(merge_sha):
            _fail("the squash is not reachable canonical history")
        # The controller only ever issues squash merges, but an external merge
        # could have landed another shape: the release target must be the
        # single-parent squash of the reviewed head.
        parents = git.runner.run(
            ("git", "-C", str(git.root), "rev-list", "--parents", "-n", "1",
             merge_sha)).stdout.split()
        if len(parents) != 2:
            _fail("the merged commit is not a single-parent squash")
        digest = receipt.get("sha256") if isinstance(receipt, dict) else None
        reference = receipt.get("reference") if isinstance(receipt, dict) else None
        if type(digest) is not str or _DIGEST.fullmatch(digest) is None \
                or type(reference) is not str \
                or reference != f"review:{kind}:pr-{row.get('number')}":
            _fail("the retained review receipt does not bind this gate's proof")
        return Observation("verified", {
            "sha256": canonical_sha256({"kind": kind, "merge": merge_sha,
                                        "review": digest}),
            "reference": f"merged:{kind}:{merge_sha}"})

    return verify_merged


def batch_evidence_consumer(*, api_get, git_root, policy):
    """The batch evidence consumer bound to the reviewed policy source.

    Repository/workflow identities and the producer pin come only from the
    pinned policy's `batch_evidence_source` — never from a candidate
    reference. A policy without one fails closed.
    """
    from .batch_evidence import BatchEvidenceConsumer

    source = policy.batch_evidence_source
    if source is None:
        _fail("the pinned policy has no batch evidence source")
    return BatchEvidenceConsumer(
        api_get=api_get, git_root=git_root, repository="endaye/lmdj",
        repository_id=source["repository_id"], workflow_id=source["workflow_id"],
        producer_revision=source["producer_revision"])
