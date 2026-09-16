"""Step carriers enrolled at the real release entry.

Each step's frozen spec is only derivable once earlier steps have run: a
`new`-mode request carries no tag until the candidate step allocates the Build,
and later steps need values their predecessors produce. A carrier is therefore
built for the step's own operation from the running request plus what the
journal and workspace already recorded, and a step whose identity is not yet
derivable is `pending` — never `absent`, which would claim a negative proof the
carrier does not have.

`RecoveredStep` is the one wrapper every step uses. It deliberately exposes
`advance` only for a step that drives its own write: the driver treats any
carrier with a callable `advance` as self-driving and takes that path instead of
the managed one, so exposing it unconditionally would bypass the managed
adapters for every step.
"""

from copy import deepcopy
from typing import Any, Callable, NoReturn
import json
from pathlib import Path
import re

from .orchestration import JournalError, STEPS
from .orchestration_driver import Observation

_BUILD = re.compile(r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}\.0\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")

# The managed candidate transition persists the allocated identity here, inside
# its own root; nothing else records which Build a `new`-mode request got.
CANDIDATE_STATE = "candidate-transition.json"


def _fail(reason: str) -> NoReturn:
    raise JournalError(
        f"why: release enrollment {reason}; remedy: reconcile the running "
        "request with the candidate and ledger records it must agree with")


class RecoveredStep:
    """One driver step: recover this step's identity, then delegate.

    `recover(state, operation)` returns the concrete carrier for the step, or
    `None` when the identity it needs does not exist yet. `drives` marks a step
    whose carrier performs its own write under the driver's guard.
    """

    def __init__(self, step: str, recover: Callable[[dict, dict], Any], *,
                 drives: bool = False):
        if step not in STEPS:
            _fail(f"unknown step {step!r}")
        if not callable(recover):
            _fail("requires a callable spec recovery")
        self.step = step
        self._recover = recover
        self._waiting = None
        if drives:
            # Instance attribute on purpose: only a self-driving step may look
            # like one to the driver.
            self.advance = self._advance

    def carrier(self, state, operation) -> Any:
        """The concrete carrier for this operation, or None when not derivable."""
        if operation.get("step") != self.step:
            _fail("operation does not belong to this step")
        return self._recover(state, operation)

    def observe(self, state, operation):
        carrier = self.carrier(state, operation)
        if carrier is None:
            # The identity this step verifies does not exist yet; the run waits.
            self._waiting = operation.get("operation_id")
            return Observation("pending")
        self._waiting = None
        return carrier.observe(state, operation)

    def execute(self, state, operation):
        carrier = self.carrier(state, operation)
        if carrier is None:
            # The driver executes only a step it just observed absent or
            # verified, so an identity that is gone now is an anomaly, not a
            # wait: never report the step done with no write and no error.
            _fail("the step's identity disappeared before it could be executed")
        execute = getattr(carrier, "execute", None)
        if callable(execute):
            execute(state, operation)

    def _advance(self, state, operation, *, before_write):
        carrier = self.carrier(state, operation)
        if carrier is None:
            if self._waiting == operation.get("operation_id"):
                # The driver asks a self-driving step to act precisely when the
                # identity is not yet derivable; it re-observes after the call,
                # so writing nothing keeps the step honestly pending.
                return
            _fail("the step's identity is not derivable but it was asked to act")
        carrier.advance(state, operation, before_write=before_write)


def read_candidate_identity(candidate_root, request_digest):
    """The identity the managed candidate step allocated for this request.

    Returns `{product_build, target_revision, snapshot_sha256}` or None before
    that step has run. A state file that belongs to another request, or that is
    unreadable, fails closed rather than reporting the step absent.
    """
    path = Path(candidate_root) / CANDIDATE_STATE
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text())
    except (OSError, ValueError):
        _fail("the candidate transition state is unreadable")
    if type(document) is not dict:
        _fail("the candidate transition state is not a document")
    scope = document.get("scope")
    cut = scope.get("cut_spec") if type(scope) is dict else None
    if type(cut) is not dict:
        _fail("the candidate transition state records no checked cut")
    if cut.get("request_sha256") != request_digest:
        _fail("the candidate transition belongs to another request")
    build = cut.get("product_build")
    if type(build) is not str or _BUILD.fullmatch(build) is None:
        _fail("the candidate transition records no valid product build")
    snapshot = cut.get("snapshot_sha256")
    if type(snapshot) is not str or _DIGEST.fullmatch(snapshot) is None:
        # The cut froze its snapshot before anything else could run, so a
        # missing or malformed one is corrupt state, not an absent fact.
        _fail("the candidate transition records no valid frozen snapshot")
    merge = document.get("cut_merge")
    revision = merge.get("merge", {}).get("merge_sha") \
        if type(merge) is dict and type(merge.get("merge")) is dict else None
    if type(revision) is not str or _SHA.fullmatch(revision) is None:
        # The cut is not merged yet: the identity exists but is not frozen.
        return None
    return {"product_build": build, "target_revision": revision,
            "snapshot_sha256": snapshot}


def release_identity(state, *, candidate_root, repository_id, ledger):
    """The Build this request is releasing, or None while it is not allocated.

    A `tag`-mode request names the tag itself; a `new`-mode request learns it
    from the managed candidate step. An allocation is the authoritative target
    revision; a tag already recorded in the ledger takes it from the intent row,
    and a tag that ledger does not authorize fails closed. `repository_id` is the
    numeric identity the frozen request does not carry (it records only
    `owner/name`), resolved once per drive from GitHub.
    """
    if type(state) is not dict or type(state.get("request")) is not dict:
        _fail("requires the running request state")
    if type(repository_id) is not int or repository_id <= 0:
        _fail("requires the resolved numeric repository identity")
    request, digest = state["request"], state.get("request_digest")
    if type(digest) is not str or _DIGEST.fullmatch(digest) is None:
        _fail("the running request carries no valid digest")
    allocated = read_candidate_identity(candidate_root, digest)
    tag = request.get("requested_tag")
    if tag is None:
        if allocated is None:
            return None
        tag = "lmdj-v" + allocated["product_build"]
    if type(tag) is not str or not tag.startswith("lmdj-v"):
        _fail("the request names no valid product tag")
    build = tag[len("lmdj-v"):]
    if _BUILD.fullmatch(build) is None:
        _fail("the request names no valid product build")
    if allocated is not None and allocated["product_build"] != build:
        _fail("the candidate transition and the request disagree on the build")
    intent = ledger.intent_for_tag(tag)
    if intent is None:
        _fail(f"the intent ledger does not authorize {tag}")
    identity = {"tag": tag, "product_build": build,
                "request_sha256": digest,
                "repository_id": repository_id,
                "actor_id": request.get("actor_id"),
                "channel": intent.current_channel,
                "disposition": str(intent.disposition)}
    if allocated is not None:
        identity["target_revision"] = allocated["target_revision"]
        identity["snapshot_sha256"] = allocated["snapshot_sha256"]
    else:
        identity["target_revision"] = intent.target_revision
    return identity


# The fields every step spec validates, in the shape the validators require.
_BASE_FIELDS = ("operation_id", "request_sha256", "repository_id", "actor_id",
                "tag", "product_build", "target_revision")


def spec_identity(state, *, candidate_root, repository_id, ledger, operation_id):
    """The fields every step spec shares, or None while they are not frozen.

    `operation_id` is the step's own derivation (each carrier module exposes
    one) so a spec built here is judged by the validator that owns it. Only the
    shared fields are returned: each step's spec is closed, so a step that needs
    more adds exactly its own.
    """
    identity = release_identity(state, candidate_root=candidate_root,
                               repository_id=repository_id, ledger=ledger)
    if identity is None or identity.get("target_revision") is None:
        # The Build is allocated but its target is not frozen yet.
        return None
    fields = {key: deepcopy(identity[key]) for key in _BASE_FIELDS
              if key != "operation_id"}
    fields["operation_id"] = operation_id(identity["request_sha256"])
    return fields


def enroll_changelog_site(*, candidate_root, repository_id, ledger, fetch,
                          site_base_url):
    """The `changelog_site` step: the deployed doc-site must serve this Build.

    Observe-only — no write can make a deployment appear, so the step is
    `pending` until the Build exists and the far side is read honestly.
    """
    from .final_steps import ChangelogSiteCarrier, site_operation_id, validate_site_spec

    def recover(state, operation):
        fields = spec_identity(state, candidate_root=candidate_root,
                               repository_id=repository_id, ledger=ledger,
                               operation_id=site_operation_id)
        if fields is None:
            return None
        spec = dict(fields, site_base_url=site_base_url)
        validate_site_spec(spec)
        return ChangelogSiteCarrier(spec=spec, fetch=fetch)

    return RecoveredStep("changelog_site", recover)
