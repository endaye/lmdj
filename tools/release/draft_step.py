"""One carrier for the driver's `draft` step: create/resume the GitHub Draft.

`create_draft(tag, context)` already owns the effect — create or resume one
Draft, verify its metadata and assets against the prepared plan, and report
draft-created / draft-verified / already-published. This carrier adds the
driver protocol: observation reads the far-side Release projection and fails
closed on any divergence from the prepared plan digest, and advance runs the
trusted create_draft controller exactly once under the driver's durable write
guard. Nothing here publishes, deploys or promotes.
"""

from copy import deepcopy
import re

from .model import canonical_sha256
from .orchestration_driver import Observation


class DraftStepError(ValueError):
    pass


def _fail(reason):
    raise DraftStepError(
        f"why: draft step {reason}; remedy: restore the prepared plan and the "
        "far-side Draft without clobbering existing state or publishing")


_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_TAG = re.compile(r"lmdj-v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\."
                  r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
_OP_STEP = "draft"


def draft_operation_id(request_sha256):
    return canonical_sha256({"request": request_sha256, "step": _OP_STEP})


def validate_spec(spec):
    if type(spec) is not dict or set(spec) != {
            "operation_id", "request_sha256", "repository_id", "actor_id",
            "tag", "target_revision", "plan_sha256"}:
        _fail("scope fields are invalid")
    if not all(isinstance(spec[k], str) and _DIGEST.fullmatch(spec[k])
               for k in ("operation_id", "request_sha256", "plan_sha256")):
        _fail("scope digests are invalid")
    if spec["operation_id"] != draft_operation_id(spec["request_sha256"]):
        _fail("operation differs from the original request")
    if type(spec["tag"]) is not str or _TAG.fullmatch(spec["tag"]) is None:
        _fail("tag is invalid")
    if type(spec["repository_id"]) is not int or spec["repository_id"] <= 0 \
            or type(spec["actor_id"]) is not int or spec["actor_id"] <= 0:
        _fail("numeric scope identities are invalid")


def read_back(release, spec):
    """Far-side read-back of the Release projection for this step.

    `release` is a projection with `id`, `draft`, `tag`, `plan_sha256`
    attributes, or None while no Release exists. Returns the verified evidence
    dict for a draft bound to the prepared plan, "pending" while absent, and
    fails closed on any present-but-divergent state; an already-published
    Release is `published`, which this step's driver mapping reports as an
    Observation the same way.
    """
    validate_spec(spec)
    if release is None:
        return "pending"
    if release.tag != spec["tag"] or release.plan_sha256 != spec["plan_sha256"]:
        _fail("the far-side Release differs from the prepared plan")
    evidence = {"sha256": canonical_sha256({
        "tag": spec["tag"], "plan_sha256": spec["plan_sha256"],
        "release_id": release.id}),
        "reference": "draft:" + str(release.id)}
    if not release.draft:
        return {"status": "published", "evidence": evidence}
    return {"status": "verified", "evidence": evidence}


class DraftCarrier:
    def __init__(self, *, spec, create_draft, release_by_tag):
        """create_draft: trusted composition calling create_draft(tag, context).

        release_by_tag: a zero-argument callable returning the far-side
        Release projection (or None); trusted composition binds the real
        GitHub transport.
        """
        validate_spec(spec)
        if not callable(create_draft) or not callable(release_by_tag):
            _fail("requires the trusted draft controller and release reader")
        self.spec = deepcopy(spec)
        self.create_draft = create_draft
        self.release_by_tag = release_by_tag

    def observe(self, state, operation):
        return Observation(self._read_back())

    def advance(self, state, operation, *, before_write):
        if not callable(before_write):
            _fail("requires the driver's durable write guard")
        observed = self._read_back()
        if isinstance(observed, dict):
            return Observation(observed["status"], observed["evidence"])
        if observed != "pending":
            return Observation(observed)
        before_write()
        try:
            self.create_draft(self.spec["tag"])
        except Exception:
            # create_draft owns its own uncertain-POST reconciliation; never
            # half-report a creation it could not confirm.
            return Observation("unknown")
        verified = self._read_back()
        if isinstance(verified, dict):
            return Observation(verified["status"], verified["evidence"])
        return Observation("unknown")

    def _read_back(self):
        return read_back(self.release_by_tag(), self.spec)
