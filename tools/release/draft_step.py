"""One carrier for the driver's `draft` step: create/resume the GitHub Draft.

`create_draft(tag, context)` already owns the effect — create or resume one
Draft, verify its metadata and assets against the prepared plan, and report
draft-created / draft-verified / already-published. This carrier adds the
driver protocol: observation reads the far-side Release projection and fails
closed on any divergence from the prepared plan digest, and advance runs the
trusted create_draft controller exactly once under the driver's durable write
guard. Nothing here publishes, deploys or promotes.
"""

from collections import namedtuple
from copy import deepcopy
import json
import re

from .model import canonical_sha256
from .orchestration_driver import Observation
from .commands import describe_failure
from .transitions import IncompleteAssetError, ReleaseReadUnavailable, TransitionError


class DraftStepError(ValueError):
    pass


def _fail(reason):
    raise DraftStepError(
        f"why: draft step {reason}; remedy: restore the prepared plan and the "
        "far-side Draft without clobbering existing state or publishing")


_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_PLAN_MARKER = re.compile(r"<!-- lmdj\.release-plan-marker\.v[1-9][0-9]* (\{[^\r\n]*\}) -->")

ReleaseProjection = namedtuple("ReleaseProjection", ("id", "draft", "tag", "plan_sha256"))


def release_projection(release):
    """The projection `read_back` compares, from one GitHub Release (or None).

    The plan digest is taken from the Release body's single plan marker. A
    body without exactly one well-formed marker projects no digest, so
    `read_back` refuses it as differing from the prepared plan.
    """
    if release is None:
        return None
    markers = _PLAN_MARKER.findall(release.body or "")
    digest = None
    if len(markers) == 1:
        try:
            value = json.loads(markers[0]).get("plan_sha256")
        except (ValueError, AttributeError):
            value = None
        digest = value if isinstance(value, str) and _DIGEST.fullmatch(value) else None
    return ReleaseProjection(release.id, release.draft, release.tag_name, digest)
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
    fails closed on any present-but-divergent state. An already-published
    Release is reported as `published` — the driver's later publication steps
    own its asset verification; this step never treats it as its own verified
    work.
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
    def __init__(self, *, spec, create_draft, release_by_tag, verify_assets):
        """create_draft: trusted composition calling create_draft(tag, context).

        release_by_tag: a zero-argument callable returning the far-side
        Release projection (or None); trusted composition binds the real
        GitHub transport.

        verify_assets: a callable taking the Draft's numeric ID that downloads
        and checks every asset against the prepared plan (`verify_draft`),
        raising on any incomplete, missing or divergent asset. A Draft is this
        step's verified work only once its assets verify: a Release whose
        upload was interrupted otherwise passes on its metadata alone.
        """
        validate_spec(spec)
        if not callable(create_draft) or not callable(release_by_tag) or not callable(verify_assets):
            _fail("requires the trusted draft controller, release reader and asset verifier")
        self.spec = deepcopy(spec)
        self.create_draft = create_draft
        self.release_by_tag = release_by_tag
        self.verify_assets = verify_assets

    def observe(self, state, operation):
        return self._observation(*self._read_back())

    def advance(self, state, operation, *, before_write):
        if not callable(before_write):
            _fail("requires the driver's durable write guard")
        observed, diagnostic = self._read_back()
        if isinstance(observed, dict) or observed != "pending":
            # A published Release is not this step's verified work: report the
            # status so the driver surfaces it instead of marking draft done.
            return self._observation(observed, diagnostic)
        before_write()
        try:
            self.create_draft(self.spec["tag"])
        except ReleaseReadUnavailable as error:
            # An outage during the repair proves nothing about the Draft: the
            # same unknown the read path reports, with its sanitized cause.
            return Observation("unknown", diagnostic=describe_failure(error))
        except TransitionError:
            # create_draft raises TransitionError only after its own
            # reconciliation: a deterministic pre-write or unrecoverable
            # creation failure that must surface, not hide as unknown.
            raise
        except Exception:
            # A raw transport failure during the POST is an unresolved write;
            # the next advance reconciles far-side state.
            return Observation("unknown")
        verified, diagnostic = self._read_back()
        if isinstance(verified, dict):
            return Observation(verified["status"], verified["evidence"])
        return Observation("unknown" if verified == "pending" else verified,
                           diagnostic=diagnostic)

    def _read_back(self):
        """(observation, diagnostic) for the Draft, verifying every asset.

        Only an interrupted upload is pending Draft work that `create_draft`
        repairs. A read outage is unknown. Any other asset verification
        failure — divergent or undeclared asset, a declared asset that is
        missing, a Release that is no longer this Draft — is a conflict whose
        cause names it; it is never retried as a write.
        """
        release = self.release_by_tag()
        observed = read_back(release, self.spec)
        if isinstance(observed, dict) and observed["status"] == "verified":
            try:
                self.verify_assets(release.id)
            except IncompleteAssetError:
                return "pending", None
            except ReleaseReadUnavailable as error:
                return "unknown", describe_failure(error)
            except Exception as error:
                return "conflict", describe_failure(error)
        return observed, None

    @staticmethod
    def _observation(observed, diagnostic):
        if isinstance(observed, dict):
            return Observation(observed["status"], observed["evidence"])
        return Observation(observed,
                           diagnostic=diagnostic if observed in ("unknown", "conflict") else None)
