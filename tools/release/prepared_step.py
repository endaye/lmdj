"""One carrier for the driver's `prepared` step: local build, tag and plan.

`prepare(tag, context)` already builds, signs the local annotated tag and
writes the atomic plan output; it is its own recovery through the existing
reconcile path. This carrier adds the driver protocol around it: observation
is read-back verification of the durable local state — the plan document and
its recorded digest, the local signed tag identity, and the plan's binding to
the exact tag/target — and advance runs prepare once under the driver's
durable write guard. Nothing here pushes, publishes or deploys.
"""

from copy import deepcopy
from pathlib import Path
import re

from .model import canonical_sha256
from .orchestration_driver import Observation


class PreparedStepError(ValueError):
    pass


def _fail(reason):
    raise PreparedStepError(
        f"why: prepared step {reason}; remedy: restore the verified local "
        "output and signed tag without rebuilding over drift or pushing "
        "anything remote")


_TAG = re.compile(r"lmdj-v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\."
                  r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_OP_STEP = "prepared"
_PLAN_DOCUMENT = "release-plan.json"
_PLAN_DIGEST = "release-plan.sha256"


def prepared_operation_id(request_sha256):
    return canonical_sha256({"request": request_sha256, "step": _OP_STEP})


def validate_spec(spec):
    if type(spec) is not dict or set(spec) != {
            "operation_id", "request_sha256", "repository_id", "actor_id",
            "tag", "target_revision", "plan_sha256", "tag_object_id"}:
        _fail("scope fields are invalid")
    if not all(isinstance(spec[k], str) and _DIGEST.fullmatch(spec[k])
               for k in ("operation_id", "request_sha256", "plan_sha256")):
        _fail("scope digests are invalid")
    if spec["operation_id"] != prepared_operation_id(spec["request_sha256"]):
        _fail("operation differs from the original request")
    if not all(isinstance(spec[k], str) and _SHA.fullmatch(spec[k])
               for k in ("target_revision", "tag_object_id")):
        _fail("scope revisions are invalid")
    if type(spec["tag"]) is not str or _TAG.fullmatch(spec["tag"]) is None:
        _fail("tag is invalid")
    if type(spec["repository_id"]) is not int or spec["repository_id"] <= 0 \
            or type(spec["actor_id"]) is not int or spec["actor_id"] <= 0:
        _fail("numeric scope identities are invalid")


def output_relative(tag):
    from urllib.parse import quote
    if type(tag) is not str or _TAG.fullmatch(tag) is None:
        _fail("tag is invalid")
    return Path("build/release") / quote(tag, safe="")


def read_back(root, spec, *, tag_state, signer_fingerprint):
    """Far-side read-back of the durable local prepared state, or a status str.

    Returns the verified evidence dict, or "absent"/"pending" when the output
    does not exist yet. Any present-but-divergent or unreadable state fails
    closed: only a missing plan document is absent.
    """
    validate_spec(spec)
    output = Path(root) / output_relative(spec["tag"])
    try:
        document = (output / _PLAN_DOCUMENT).read_bytes()
        recorded = (output / _PLAN_DIGEST).read_text(encoding="ascii").strip()
    except FileNotFoundError:
        return "absent"
    except OSError:
        _fail("the prepared output exists but is unreadable")
        raise  # unreachable; _fail always raises
    if recorded != spec["plan_sha256"]:
        _fail("the recorded plan digest differs from the spec")
    import hashlib
    if hashlib.sha256(document).hexdigest() != spec["plan_sha256"]:
        _fail("the plan document bytes differ from the recorded digest")
    if tag_state is None:
        return "pending"
    if (tag_state.object_id != spec["tag_object_id"]
            or tag_state.target_revision != spec["target_revision"]
            or tag_state.signer_fingerprint != signer_fingerprint):
        _fail("the local signed tag identity differs from the spec")
    return {"status": "verified",
            "evidence": {"sha256": canonical_sha256({
                "tag": spec["tag"], "target_revision": spec["target_revision"],
                "plan_sha256": spec["plan_sha256"],
                "tag_object_id": spec["tag_object_id"]}),
                "reference": "prepared:" + spec["tag"]}}


class PreparedCarrier:
    def __init__(self, *, root, spec, prepare, tag_state, signer_fingerprint):
        """prepare: trusted composition calling prepare(tag, context) once.

        tag_state: a zero-argument callable returning the current LocalTag
        (or None); trusted composition binds the real Git repository and the
        policy's product fingerprint.
        """
        validate_spec(spec)
        if not callable(prepare) or not callable(tag_state) \
                or not isinstance(signer_fingerprint, str) or not signer_fingerprint:
            _fail("requires the trusted prepare controller, tag reader and signer")
        self.root = Path(root).absolute()
        self.spec = deepcopy(spec)
        self.prepare = prepare
        self.tag_state = tag_state
        self.signer_fingerprint = signer_fingerprint

    def observe(self, state, operation):
        observed = self._read_back()
        return Observation(observed["status"] if isinstance(observed, dict) else observed)

    def advance(self, state, operation, *, before_write):
        if not callable(before_write):
            _fail("requires the driver's durable write guard")
        observed = self._read_back()
        if isinstance(observed, dict):
            return Observation("verified", observed["evidence"])
        if observed not in ("absent", "pending"):
            return Observation(observed)
        before_write()
        try:
            self.prepare(self.spec["tag"])
        except Exception:
            # prepare() owns its own durable recovery; never half-report.
            return Observation("unknown")
        verified = self._read_back()
        if isinstance(verified, dict):
            return Observation("verified", verified["evidence"])
        return Observation(verified)

    def _read_back(self):
        return read_back(self.root, self.spec, tag_state=self.tag_state(),
                         signer_fingerprint=self.signer_fingerprint)
