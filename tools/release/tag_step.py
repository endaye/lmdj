"""One carrier for the driver's `tag` step: push the exact local signed tag.

`push_tag(tag, context)` already refuses remote conflicts, reconciles the
already-pushed case, re-fetches and re-verifies the remote state against the
local signed tag and the prepared plan. This carrier adds the driver protocol:
observation compares the durable local and remote tag states against the
prepared spec, and advance runs push_tag exactly once under the driver's
durable write guard. Nothing here creates a Draft, publishes or deploys.
"""

from copy import deepcopy
import re

from .model import canonical_sha256
from .orchestration_driver import Observation


class TagStepError(ValueError):
    pass


def _fail(reason):
    raise TagStepError(
        f"why: tag step {reason}; remedy: restore the prepared local signed "
        "tag and the pushed remote state without moving a formal tag")


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_TAG = re.compile(r"lmdj-v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\."
                  r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
_OP_STEP = "tag"


def tag_operation_id(request_sha256):
    return canonical_sha256({"request": request_sha256, "step": _OP_STEP})


def validate_spec(spec):
    if type(spec) is not dict or set(spec) != {
            "operation_id", "request_sha256", "repository_id", "actor_id",
            "tag", "target_revision", "plan_sha256", "tag_object_id",
            "signer_fingerprint"}:
        _fail("scope fields are invalid")
    if not all(isinstance(spec[k], str) and _DIGEST.fullmatch(spec[k])
               for k in ("operation_id", "request_sha256", "plan_sha256")):
        _fail("scope digests are invalid")
    if spec["operation_id"] != tag_operation_id(spec["request_sha256"]):
        _fail("operation differs from the original request")
    if not all(isinstance(spec[k], str) and _SHA.fullmatch(spec[k])
               for k in ("target_revision", "tag_object_id")):
        _fail("scope revisions are invalid")
    if type(spec["signer_fingerprint"]) is not str \
            or re.fullmatch(r"[0-9A-F]{40}", spec["signer_fingerprint"]) is None:
        _fail("signer fingerprint is invalid")
    if type(spec["tag"]) is not str or _TAG.fullmatch(spec["tag"]) is None:
        _fail("tag is invalid")
    if type(spec["repository_id"]) is not int or spec["repository_id"] <= 0 \
            or type(spec["actor_id"]) is not int or spec["actor_id"] <= 0:
        _fail("numeric scope identities are invalid")


def _states_match(local, remote):
    return (local is not None and remote is not None
            and local.object_id == remote.object_id
            and local.target_revision == remote.target_revision
            and local.signer_fingerprint == remote.signer_fingerprint)


def read_back(local, remote, spec):
    """Far-side comparison of the durable local and remote tag identities.

    Returns the verified evidence dict, or "pending" while the remote tag is
    absent. Any present-but-divergent state fails closed; a missing local tag
    or a signer other than the prepared one fails closed too.
    """
    validate_spec(spec)
    if local is None:
        _fail("the local signed tag is missing")
    if (local.object_id != spec["tag_object_id"]
            or local.target_revision != spec["target_revision"]
            or local.signer_fingerprint != spec["signer_fingerprint"]):
        _fail("the local signed tag differs from the prepared spec")
    if remote is None:
        return "pending"
    if not _states_match(local, remote):
        _fail("the remote tag differs from the local signed tag")
    if remote.signer_fingerprint != spec["signer_fingerprint"]:
        _fail("the remote tag signer differs from the prepared signer")
    return {"status": "verified",
            "evidence": {"sha256": canonical_sha256({
                "tag": spec["tag"], "target_revision": spec["target_revision"],
                "plan_sha256": spec["plan_sha256"],
                "tag_object_id": spec["tag_object_id"],
                "signer_fingerprint": spec["signer_fingerprint"]}),
                "reference": "tag:" + spec["tag"]}}


class TagCarrier:
    def __init__(self, *, spec, push_tag, local_tag_state, remote_tag_state):
        """push_tag: trusted composition calling push_tag(tag, context) once.

        The state readers are zero-argument callables bound by trusted
        composition to the real Git repository.
        """
        validate_spec(spec)
        if not callable(push_tag) or not callable(local_tag_state) \
                or not callable(remote_tag_state):
            _fail("requires the trusted tag push controller and state readers")
        self.spec = deepcopy(spec)
        self.push_tag = push_tag
        self.local_tag_state = local_tag_state
        self.remote_tag_state = remote_tag_state

    def observe(self, state, operation):
        return Observation(self._read_back())

    def advance(self, state, operation, *, before_write):
        if not callable(before_write):
            _fail("requires the driver's durable write guard")
        observed = self._read_back()
        if isinstance(observed, dict):
            return Observation("verified", observed["evidence"])
        if observed != "pending":
            return Observation(observed)
        before_write()
        try:
            self.push_tag(self.spec["tag"])
        except Exception:
            # push_tag owns its own transport reconciliation; never half-report.
            return Observation("unknown")
        verified = self._read_back()
        if isinstance(verified, dict):
            return Observation("verified", verified["evidence"])
        # A completed push whose remote is not yet observable is an unknown
        # write result, never pending work: the next advance must reconcile,
        # not re-push over an unknown.
        return Observation("unknown")

    def _read_back(self):
        return read_back(self.local_tag_state(), self.remote_tag_state(), self.spec)
