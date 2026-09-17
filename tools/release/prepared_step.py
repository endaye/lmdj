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


_AUTHORIZATION = {"operation_id", "request_sha256", "repository_id", "actor_id",
                  "tag", "target_revision"}


def validate_authorization(authorization):
    """The pre-write half of a `prepared` spec: what the reviewed intent binds.

    `plan_sha256` and `tag_object_id` are this step's own outputs — the spec is
    result-bound by ruling, not by omission — so they are absent here by
    construction. This stays a separate entry point from `validate_spec` on
    purpose: merging the two would let the weaker pre-write shape stand in for
    the complete one that `read_back` is the judge of.
    """
    if type(authorization) is not dict or set(authorization) != _AUTHORIZATION:
        _fail("authorization fields are invalid")
    if not all(isinstance(authorization[k], str) and _DIGEST.fullmatch(authorization[k])
               for k in ("operation_id", "request_sha256")):
        _fail("authorization digests are invalid")
    if authorization["operation_id"] != prepared_operation_id(
            authorization["request_sha256"]):
        _fail("operation differs from the original request")
    if not isinstance(authorization["target_revision"], str) \
            or _SHA.fullmatch(authorization["target_revision"]) is None:
        _fail("authorization revision is invalid")
    if type(authorization["tag"]) is not str \
            or _TAG.fullmatch(authorization["tag"]) is None:
        _fail("tag is invalid")
    if type(authorization["repository_id"]) is not int \
            or authorization["repository_id"] <= 0 \
            or type(authorization["actor_id"]) is not int \
            or authorization["actor_id"] <= 0:
        _fail("numeric authorization identities are invalid")


def freeze_spec(authorization, *, plan_sha256, tag_state):
    """The complete result-bound spec, frozen from what `prepare` produced.

    The authorization half comes from the reviewed intent row; the two derived
    fields come from the durable output. `validate_spec` remains the judge of
    the result, so a malformed digest or tag object id fails closed here rather
    than reaching `read_back`.
    """
    validate_authorization(authorization)
    return dict(authorization, plan_sha256=plan_sha256,
                tag_object_id=tag_state.object_id)


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
        if isinstance(observed, dict):
            # read_back reports the verified status and its evidence together;
            # a verified observation without evidence is not a valid one.
            return Observation("verified", observed["evidence"])
        return Observation(observed)

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


class AuthorizedPreparedCarrier:
    """`prepared` before its own outputs exist: authorize, drive once, freeze.

    This step's spec is result-bound: `plan_sha256` and `tag_object_id` are
    what `prepare()` produces. The carrier therefore holds only the
    authorization half — the fields the reviewed intent row froze — drives
    `prepare` once under the driver's guard, and only then freezes the complete
    spec from the durable output and verifies it through `read_back`.

    Freezing from the output makes two of `read_back`'s comparisons
    tautological: the recorded digest and the tag object id are where the spec
    just came from. The comparisons that carry the weight are not. The plan
    document bytes must hash to the recorded digest, so a swapped digest file
    cannot redefine what this step reports; and the signed tag must carry the
    reviewed `target_revision` and the trusted signer, which is what binds the
    derived witness back to the reviewed intent. `prepare()` itself re-verifies
    the intent authorization, the target's canonical main ancestry, the product
    proof, the profile assets and the changelog source before it writes, and
    refuses to move an existing formal tag.
    """

    def __init__(self, *, root, authorization, prepare, plan_digest, tag_state,
                 signer_fingerprint):
        """prepare: trusted composition calling prepare(tag, context) once.

        plan_digest and tag_state are zero-argument readers of the durable
        local output and the local signed tag; trusted composition binds them
        to the real repository and the policy's product fingerprint.
        """
        validate_authorization(authorization)
        if not callable(prepare) or not callable(plan_digest) \
                or not callable(tag_state) \
                or not isinstance(signer_fingerprint, str) or not signer_fingerprint:
            _fail("requires the trusted prepare controller, output readers and signer")
        self.root = Path(root).absolute()
        self.authorization = deepcopy(authorization)
        self.prepare = prepare
        self.plan_digest = plan_digest
        self.tag_state = tag_state
        self.signer_fingerprint = signer_fingerprint

    def observe(self, state, operation):
        status, evidence = self._verified()
        return Observation(status, evidence)

    def advance(self, state, operation, *, before_write):
        if not callable(before_write):
            _fail("requires the driver's durable write guard")
        status, evidence = self._verified()
        if status == "verified":
            return Observation(status, evidence)
        if status != "absent":
            # Present-but-unverified local state is never rebuilt over.
            return Observation(status)
        before_write()
        try:
            self.prepare(self.authorization["tag"])
        except Exception:
            # prepare() owns its own durable recovery; never half-report.
            return Observation("unknown")
        status, evidence = self._verified()
        return Observation(status, evidence)

    def _verified(self):
        plan = self.plan_digest()
        tag_state = self.tag_state()
        if plan is None:
            # Nothing this step writes exists yet. A local signed tag without
            # the output is the reconcile case prepare() owns, and prepare()
            # refuses a local tag that does not match the reviewed target, so
            # this is still positively absent work and not a partial result.
            return "absent", None
        if tag_state is None:
            # read_back's own verdict for a plan whose signed tag is gone:
            # present work that cannot be verified. Never absent, so the driver
            # waits for the restored tag instead of rebuilding over the drift.
            return "pending", None
        spec = freeze_spec(self.authorization, plan_sha256=plan,
                           tag_state=tag_state)
        observed = read_back(self.root, spec, tag_state=tag_state,
                             signer_fingerprint=self.signer_fingerprint)
        if isinstance(observed, dict):
            return "verified", observed["evidence"]
        return observed, None
