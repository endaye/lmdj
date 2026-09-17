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
import os
from pathlib import Path
import re

from .orchestration import JournalError, RequestJournal, STEPS
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

    Returns `{product_build, target_revision, snapshot_sha256,
    witness_revision}` or None before that step has run; `witness_revision` is
    None until the witness PR merge is verified, and is the revision the full
    batch certifies — the release target the `intent` step must bind. A state
    file that belongs to another request, or that is unreadable, fails closed
    rather than reporting the step absent.
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
    witness_merge = document.get("witness_merge")
    witness = witness_merge.get("merge", {}).get("merge_sha") \
        if type(witness_merge) is dict and type(witness_merge.get("merge")) is dict \
        else None
    if witness_merge is not None \
            and (type(witness) is not str or _SHA.fullmatch(witness) is None):
        _fail("the candidate transition records no valid witness merge")
    return {"product_build": build, "target_revision": revision,
            "snapshot_sha256": snapshot, "witness_revision": witness}


def release_identity(state, *, candidate_root, repository_id, ledger):
    """The Build this request is releasing, or None while it is not allocated.

    A `tag`-mode request names the tag itself; a `new`-mode request learns it
    from the managed candidate step. The intent row is authoritative for
    `target_revision`/`channel`/`disposition` in both modes: it binds the
    batch-certified witness merge, while the allocation only proves the Build
    and its frozen snapshot. A `new`-mode request whose intent step has not
    landed yet has no authoritative row, so the identity is not derivable and
    the caller waits; a `tag`-mode request whose tag the ledger does not
    authorize fails closed. When both records exist they must agree on the
    witness merge. `repository_id` is the numeric identity the frozen request
    does not carry (it records only `owner/name`), resolved once per drive
    from GitHub.
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
        if request.get("requested_tag") is None:
            # The intent row is this run's own intent step output; every
            # enrolled step that uses this identity runs after that step, so a
            # missing row means it has not landed, not that the tag is foreign.
            return None
        _fail(f"the intent ledger does not authorize {tag}")
    identity = {"tag": tag, "product_build": build,
                "request_sha256": digest,
                "repository_id": repository_id,
                "actor_id": request.get("actor_id"),
                "channel": intent.current_channel,
                "disposition": str(intent.disposition)}
    revision = intent.target_revision
    if type(revision) is not str or _SHA.fullmatch(revision) is None:
        _fail(f"the intent ledger records no valid target revision for {tag}")
    identity["target_revision"] = revision
    if allocated is not None:
        witness = allocated["witness_revision"]
        if witness is None:
            # The row exists, so the intent step completed, so the witness
            # merge was verified; a candidate state without it is drift.
            _fail("the intent row exists but the candidate state records no "
                  "witness merge")
        if revision != witness:
            _fail("the intent row and the candidate witness merge disagree on "
                  "the release target")
        identity["snapshot_sha256"] = allocated["snapshot_sha256"]
    return identity


# The identity fields each step's closed spec binds, named per step.
_SITE_FIELDS = ("tag", "product_build", "target_revision", "repository_id",
                "actor_id", "request_sha256")
_FINAL_FIELDS = _SITE_FIELDS + ("channel",)
_DRAFT_FIELDS = ("tag", "target_revision", "repository_id", "actor_id",
                 "request_sha256")


def spec_identity(state, *, candidate_root, repository_id, ledger, operation_id,
                  fields):
    """The spec fields this step shares, or None while they are not frozen.

    Each step's spec is closed, and the steps disagree on which identity fields
    they bind (a site spec carries the Product Build, a draft spec carries the
    prepared plan instead), so the caller names exactly the fields it wants and
    the step's own validator remains the judge. `operation_id` is the step's own
    derivation, which each carrier module exposes.
    """
    identity = release_identity(state, candidate_root=candidate_root,
                               repository_id=repository_id, ledger=ledger)
    if identity is None or identity.get("target_revision") is None:
        # The Build is allocated but its target is not frozen yet.
        return None
    absent = sorted(key for key in fields if identity.get(key) is None)
    if absent:
        _fail(f"the frozen identity omits {', '.join(absent)}")
    spec = {key: deepcopy(identity[key]) for key in fields}
    spec["operation_id"] = operation_id(identity["request_sha256"])
    return spec


def read_prepared_plan(root, tag):
    """The plan digest `prepare` wrote for this tag, or None before it ran.

    The path is the one `prepared_step` reads back from, so the enrollment and
    the step agree on where the plan lives. `None` means the prepared output is
    not there yet, which is the same condition `prepared_step.read_back` reports
    as "absent"; the step that needs it decides what that means for itself.
    Only an absent pair means that: the digest is checked against the plan
    document bytes it names, so a swapped digest file cannot silently redefine
    what a later step binds, and half of the pair is drift.

    No ledger row records this digest and none needs to. The plan is a
    deterministic function of the reviewed intent row, the policy and the
    signed tag object, so `plan_sha256` is a derived witness rather than an
    independently reviewed fact; `enroll_prepared` freezes it from this reader
    after its own drive, and later steps bind the same value.
    """
    from . import prepared_step

    output = Path(root) / prepared_step.output_relative(tag)
    path = output / prepared_step._PLAN_DIGEST
    try:
        digest = path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        # prepare writes the document and its digest together, so a document
        # without its digest is a partial or tampered output, not an absent one.
        if (output / prepared_step._PLAN_DOCUMENT).exists():
            _fail("the prepared plan document has no recorded digest")
        return None
    except (OSError, UnicodeDecodeError):
        _fail("the prepared plan digest is unreadable")
    if _DIGEST.fullmatch(digest) is None:
        _fail("the prepared plan digest is malformed")
    try:
        document = (output / prepared_step._PLAN_DOCUMENT).read_bytes()
    except FileNotFoundError:
        _fail("the prepared output records a digest without its plan document")
    except OSError:
        _fail("the prepared plan document is unreadable")
    import hashlib
    if hashlib.sha256(document).hexdigest() != digest:
        _fail("the prepared plan digest does not match its document")
    return digest


_PREPARED_FIELDS = ("tag", "target_revision", "repository_id", "actor_id",
                    "request_sha256")

_TAG_FIELDS = ("tag", "target_revision", "repository_id", "actor_id",
               "request_sha256")


def enroll_prepared(*, root, candidate_root, repository_id, ledger, prepare,
                    local_tag_state, signer_fingerprint):
    """The `prepared` step: it drives `prepare` and freezes its own outputs.

    This step's spec is result-bound, so the enrollment recovers only the
    authorization half from the reviewed intent row and lets the carrier freeze
    `plan_sha256` / `tag_object_id` from the durable output after the drive.
    Before that row exists the identity is not derivable and the step stays
    `pending`; it never reports absent work as done.
    """
    from .prepared_step import AuthorizedPreparedCarrier, prepared_operation_id

    def recover(state, operation):
        authorization = spec_identity(state, candidate_root=candidate_root,
                                      repository_id=repository_id, ledger=ledger,
                                      operation_id=prepared_operation_id,
                                      fields=_PREPARED_FIELDS)
        if authorization is None:
            return None
        # The carrier is built per recovery and lives for one operation, so the
        # tag its readers query is the one the authorization just named and
        # cannot drift from the identity `read_back` compares against.
        tag = authorization["tag"]
        return AuthorizedPreparedCarrier(
            root=root, authorization=authorization, prepare=prepare,
            plan_digest=lambda: read_prepared_plan(root, tag),
            tag_state=lambda: local_tag_state(tag),
            signer_fingerprint=signer_fingerprint)

    return RecoveredStep("prepared", recover, drives=True)


def enroll_tag(*, root, candidate_root, repository_id, ledger, push_tag,
               local_tag_state, remote_tag_state, signer_fingerprint):
    """The `tag` step: it pushes the exact local signed tag `prepare` created.

    Every field of a `tag` spec exists by the time this step runs, so unlike
    `prepared` there is nothing to freeze in two phases: the prepared output
    supplies `plan_sha256` and the local signed tag supplies `tag_object_id`.
    The step waits while either is missing rather than pushing a tag it cannot
    name. `signer_fingerprint` comes from the pinned policy, never from the tag
    being verified, so the trusted-signer comparison in `read_back` stays a
    real check on both the local and the remote side.
    """
    from .tag_step import TagCarrier, tag_operation_id, validate_spec

    def recover(state, operation):
        fields = spec_identity(state, candidate_root=candidate_root,
                               repository_id=repository_id, ledger=ledger,
                               operation_id=tag_operation_id,
                               fields=_TAG_FIELDS)
        if fields is None:
            return None
        plan = read_prepared_plan(root, fields["tag"])
        if plan is None:
            # `prepared` has not written its output yet; this step has nothing
            # to bind and must not push.
            return None
        tag = fields["tag"]
        local = local_tag_state(tag)
        if local is None:
            # The prepared output exists but its signed tag does not. Waiting
            # is the only honest answer: `read_back` would fail closed on it,
            # and this step never creates the tag it pushes.
            return None
        spec = dict(fields, plan_sha256=plan, tag_object_id=local.object_id,
                    signer_fingerprint=signer_fingerprint)
        validate_spec(spec)
        # The carrier is built per recovery and lives for one operation, so the
        # tag its readers query is the one the spec just named.
        return TagCarrier(spec=spec, push_tag=push_tag,
                          local_tag_state=lambda: local_tag_state(tag),
                          remote_tag_state=lambda: remote_tag_state(tag))

    return RecoveredStep("tag", recover, drives=True)


def enroll_draft(*, root, candidate_root, repository_id, ledger, create_draft,
                 release_by_tag):
    """The `draft` step: it creates the Draft and re-reads it to verify.

    A `draft` spec binds the prepared plan, so the step stays `pending` until
    `prepare` has written one.
    """
    from .draft_step import DraftCarrier, draft_operation_id, validate_spec

    def recover(state, operation):
        fields = spec_identity(state, candidate_root=candidate_root,
                               repository_id=repository_id, ledger=ledger,
                               operation_id=draft_operation_id,
                               fields=_DRAFT_FIELDS)
        if fields is None:
            return None
        plan = read_prepared_plan(root, fields["tag"])
        if plan is None:
            return None
        spec = dict(fields, plan_sha256=plan)
        validate_spec(spec)
        tag = spec["tag"]
        # draft_step takes a zero-argument far-side reader, and the enrollment
        # owns the identity the carrier verifies: the tag comes from the spec
        # that was just validated, and DraftCarrier deep-copies that spec, so
        # the identity the reader queries cannot drift from the one read_back
        # compares against. The carrier is built per recovery and lives for one
        # operation, so it is tag-stable for its lifetime by construction; a
        # far-side Release under another tag is caught by read_back's own tag
        # comparison, never silently read as this step's work.
        return DraftCarrier(spec=spec, create_draft=create_draft,
                            release_by_tag=lambda: release_by_tag(tag))

    return RecoveredStep("draft", recover, drives=True)


_BATCH_EVIDENCE = re.compile(r"batch-result:([1-9][0-9]*):([0-9a-f]{40})\Z")


def read_verified_batch(state, *, batch_reference_for):
    """The verification step's frozen batch reference, or None before it ran.

    The driver's journal records the verification step as a digest plus the
    compact reference `batch-result:<run_id>:<witness>` the verification carrier
    produced, where the run id is the origin run it verified. The reference
    document itself comes from the same authenticated batch journal through
    `batch_reference_for(witness)`, which the composition supplies, so the
    enrollment never parses evidence text into an identity: the document's own
    origin run must equal the recorded run id or this fails closed.
    """
    if type(state) is not dict or type(state.get("transitions")) is not list:
        _fail("requires the running request state")
    verified = [entry for entry in state["transitions"]
                if type(entry) is dict and entry.get("step") == "verification"
                and entry.get("status") == "verified"]
    if not verified:
        return None
    evidence = verified[-1].get("evidence")
    reference = evidence.get("reference") if type(evidence) is dict else None
    if type(reference) is not str:
        _fail("the verified verification step exposes no reference")
    matched = _BATCH_EVIDENCE.fullmatch(reference)
    if matched is None:
        _fail("the verification reference is not a batch result")
    run_id, witness = int(matched.group(1)), matched.group(2)
    if not callable(batch_reference_for):
        _fail("requires the trusted batch reference reader")
    document = batch_reference_for(witness)
    if isinstance(document, str):
        # The journal stores the encoded reference; decode it through the same
        # entry point the verification carrier uses, and report an undecodable
        # payload as this module's own refusal rather than leaking its error.
        from scripts.ci.batch_runtime import decode_reference

        try:
            document = decode_reference(document)
        except Exception:
            _fail("the batch reference is undecodable")
    if type(document) is not dict:
        _fail("the batch reference is not a document")
    if document.get("request", {}).get("origin_run", {}).get("run_id") != run_id:
        _fail("the batch reference does not bind the verified origin run")
    return {"batch_reference": deepcopy(document), "batch_run_id": run_id,
            "witness_revision": witness}


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
                               operation_id=site_operation_id,
                               fields=_SITE_FIELDS)
        if fields is None:
            return None
        spec = dict(fields, site_base_url=site_base_url)
        validate_site_spec(spec)
        return ChangelogSiteCarrier(spec=spec, fetch=fetch)

    return RecoveredStep("changelog_site", recover)


def enroll_final(*, candidate_root, repository_id, ledger, fetch,
                 release_by_tag, ledger_row, release_id_for, site_base_url):
    """The `final` step: every recorded far-side identity must agree at once.

    Observe-only like `changelog_site` — no write can make the far side true.
    Its spec additionally binds the numeric Release identity, which the
    enrollment cross-confirms from the publication record and the far-side
    Release: while the record does not name this tag (nothing published, the
    Release still a draft, or the record step has not landed) the identity is
    not derivable and the step waits; a record that names a Release the far
    side lacks, still holds as a draft, or numbers differently is drift and
    fails closed.
    """
    from .final_steps import FinalCarrier, final_operation_id, validate_final_spec

    for name, reader in (("fetch", fetch), ("release_by_tag", release_by_tag),
                         ("ledger_row", ledger_row),
                         ("release_id_for", release_id_for)):
        if not callable(reader):
            _fail(f"requires a callable {name}")

    def recover(state, operation):
        fields = spec_identity(state, candidate_root=candidate_root,
                               repository_id=repository_id, ledger=ledger,
                               operation_id=final_operation_id,
                               fields=_FINAL_FIELDS)
        if fields is None:
            return None
        tag = fields["tag"]
        release = release_by_tag(tag)
        recorded = release_id_for(tag)
        far_id = checked_release_id(release)
        if recorded is None:
            # The publication record does not name this tag yet, so there is
            # no confirmed Release identity to bind, whatever the far side
            # shows; the step waits rather than guessing one.
            return None
        if type(recorded) is not int or recorded <= 0:
            _fail("the publication record carries no valid numeric Release "
                  "identity")
        if far_id is None:
            _fail("the publication record names a Release the far side does "
                  "not have")
        if release.get("draft"):
            _fail("the publication record names a Release that is still a "
                  "draft")
        if far_id != recorded:
            _fail("the publication record and the far-side Release disagree "
                  "on the Release identity")
        spec = dict(fields, site_base_url=site_base_url, release_id=recorded)
        validate_final_spec(spec)
        # The carrier passes the frozen tag to both readers itself, so the
        # identity they answer for cannot drift from the one it verifies.
        return FinalCarrier(spec=spec, fetch=fetch, release_by_tag=release_by_tag,
                            ledger_row=ledger_row)

    return RecoveredStep("final", recover)


def checked_release_id(release):
    """The numeric identity of a far-side Release projection, or None if absent.

    An unreadable projection, or a present Release without a valid numeric
    identity, fails closed. A draft is a Release and returns its id — each
    caller decides what draft means for its own step.
    """
    if release is None:
        return None
    if not hasattr(release, "get"):
        _fail("the far-side Release projection is not readable")
    release_id = release.get("id")
    if type(release_id) is not int or release_id <= 0:
        _fail("the far-side Release carries no valid numeric identity")
    return release_id


def enroll_intent(*, candidate_root, repository_id, batch_reference_for,
                  commit_for, sequence_for):
    """The `intent` step: record the reviewed intent docs PR for this request.

    This step drives its own write (the owned docs commit plus the reviewed PR
    sequence), so it is enrolled with `drives=True`. Its identity cannot come
    from `release_identity`: the intent ledger row is this step's own output
    and does not exist yet. Instead the spec binds what the earlier steps
    already froze — the allocation and snapshot from the candidate state, and
    the batch-certified revision from the verified `verification` transition.
    The ledger model requires the row's target to equal the batch reference's
    target, and the verification step binds the batch to the candidate's
    witness merge, so the spec's `target_revision` is that witness revision,
    cross-checked against the candidate state's own witness record.

    A `tag`-mode request has no candidate state (the managed candidate
    transition only runs in `new` mode), so the identity is not derivable and
    the step waits rather than re-recording an intent that already exists.
    `commit_for(spec)` / `sequence_for(spec)` are the trusted composition's
    factories for the concrete `IntentCommit` / `IntentPrSequence`; the
    carrier's own type checks refuse anything else.
    """
    from .intent import intent_operation_id, validate_spec
    from .intent_carrier import IntentCarrier

    for name, factory in (("batch_reference_for", batch_reference_for),
                          ("commit_for", commit_for),
                          ("sequence_for", sequence_for)):
        if not callable(factory):
            _fail(f"requires a callable {name}")

    def recover(state, operation):
        if type(state) is not dict or type(state.get("request")) is not dict:
            _fail("requires the running request state")
        request, digest = state["request"], state.get("request_digest")
        if type(digest) is not str or _DIGEST.fullmatch(digest) is None:
            _fail("the running request carries no valid digest")
        if type(repository_id) is not int or repository_id <= 0:
            _fail("requires the resolved numeric repository identity")
        actor_id = request.get("actor_id")
        if type(actor_id) is not int or actor_id <= 0:
            _fail("the request carries no valid actor identity")
        allocated = read_candidate_identity(candidate_root, digest)
        if allocated is None or allocated["witness_revision"] is None:
            # No allocation, or the cut merged but its witness merge is not
            # verified yet: nothing the batch could have certified.
            return None
        batch = read_verified_batch(state, batch_reference_for=batch_reference_for)
        if batch is None:
            return None
        if batch["witness_revision"] != allocated["witness_revision"]:
            _fail("the candidate witness merge and the verified batch disagree "
                  "on the certified revision")
        spec = {"operation_id": intent_operation_id(digest),
                "request_sha256": digest,
                "repository_id": repository_id, "actor_id": actor_id,
                "target_revision": batch["witness_revision"],
                "product_build": allocated["product_build"],
                "tag": "lmdj-v" + allocated["product_build"],
                "snapshot_sha256": allocated["snapshot_sha256"],
                "batch_reference": batch["batch_reference"],
                "batch_run_id": batch["batch_run_id"]}
        validate_spec(spec)
        return IntentCarrier(commit=commit_for(spec), sequence=sequence_for(spec))

    return RecoveredStep("intent", recover, drives=True)


def enroll_changelog(*, candidate_root, repository_id, ledger, main_revision,
                     changelog_binding, commit_for, sequence_for):
    """The `changelog` step: bind the reviewed frozen changelog via a docs PR.

    This step drives its own write — the owned docs commit on canonical main
    plus the reviewed PR sequence — so it is enrolled with `drives=True`. The
    shared identity comes from `spec_identity`, which under the reconciled
    rules waits until the intent row exists (it is authoritative for the
    target revision) and cross-checks it against the candidate witness merge.
    `main_revision()` resolves the canonical main tip the commit lands on, and
    `changelog_binding()` returns the reviewed document's binding digests
    (`changelog.binding`: `sha256`/`notes_sha256`); the commit recomputes the
    freeze at the write boundary and refuses any divergence, so a drifted
    binding cannot pass. The closed spec carries the commit's own
    `head_sha`/`tree_sha`, which exist only after the commit lands: the
    enrollment binds deterministic placeholders the carrier replaces with the
    durable commit's real identities before the PR transport reads them
    (`evidence_branch` pushes and merges on `head_sha`), so the placeholders
    never persist anywhere. `commit_for(spec)` / `sequence_for(spec)` are the
    trusted composition's factories; the carrier's own type checks refuse
    anything else.
    """
    from .changelog_step import ChangelogCarrier, changelog_operation_id, validate_spec
    from .model import canonical_sha256

    for name, factory in (("main_revision", main_revision),
                          ("changelog_binding", changelog_binding),
                          ("commit_for", commit_for),
                          ("sequence_for", sequence_for)):
        if not callable(factory):
            _fail(f"requires a callable {name}")

    def recover(state, operation):
        fields = spec_identity(state, candidate_root=candidate_root,
                               repository_id=repository_id, ledger=ledger,
                               operation_id=changelog_operation_id,
                               fields=_SITE_FIELDS)
        if fields is None:
            return None
        base = main_revision()
        if type(base) is not str or _SHA.fullmatch(base) is None:
            _fail("the canonical main revision is unavailable")
        bound = changelog_binding()
        digests = {key: bound.get(key) if type(bound) is dict else None
                   for key in ("sha256", "notes_sha256")}
        if any(type(value) is not str or _DIGEST.fullmatch(value) is None
               for value in digests.values()):
            _fail("the reviewed changelog binding is unavailable")
        placeholder = canonical_sha256({"request": fields["request_sha256"],
                                        "step": "changelog", "placeholder": "head"})
        placeholder_tree = canonical_sha256({"request": fields["request_sha256"],
                                             "step": "changelog", "placeholder": "tree"})
        spec = dict(fields, base_revision=base,
                    head_sha=placeholder[:40], tree_sha=placeholder_tree[:40],
                    changelog_sha256=digests["sha256"],
                    notes_sha256=digests["notes_sha256"])
        validate_spec(spec)
        return ChangelogCarrier(commit=commit_for(spec), sequence=sequence_for(spec))

    return RecoveredStep("changelog", recover, drives=True)


def enroll_promotion(*, candidate_root, repository_id, ledger, main_revision,
                     promotion_binding, commit_for, sequence_for):
    """The `promotion` step: record the reviewed dev promotion via a docs PR.

    This step drives its own write — the owned docs commit on canonical main
    plus the reviewed PR sequence — so it is enrolled with `drives=True`. The
    shared identity comes from `spec_identity` (the intent row is
    authoritative for the target revision, cross-checked against the
    candidate witness merge in `new` mode); the row's current channel is the
    promotion's `from_channel`. The reviewed promotion itself is injected by
    the trusted composition: `promotion_binding()` returns None while the
    runtime/creator deployment evidence does not exist yet (the step waits),
    otherwise the plan's binding — `from_channel`, `to_channel` and the
    `deployment_runs_sha256`/`attestation_sha256` digests the committed ledger
    record is verified against. The promotion must move strictly forward and
    `stable` is refused here as `plan_promotion` refuses it. As with the
    changelog step, the closed spec's `head_sha`/`tree_sha` are deterministic
    placeholders the carrier replaces with the durable commit's real
    identities before the PR transport reads them.
    """
    from .model import canonical_sha256, channel_rank
    from .promotion_step import (
        PromotionCarrier,
        promotion_operation_id,
        validate_spec,
    )

    for name, factory in (("main_revision", main_revision),
                          ("promotion_binding", promotion_binding),
                          ("commit_for", commit_for),
                          ("sequence_for", sequence_for)):
        if not callable(factory):
            _fail(f"requires a callable {name}")

    def recover(state, operation):
        fields = spec_identity(state, candidate_root=candidate_root,
                               repository_id=repository_id, ledger=ledger,
                               operation_id=promotion_operation_id,
                               fields=_DRAFT_FIELDS + ("channel",))
        if fields is None:
            return None
        base = main_revision()
        if type(base) is not str or _SHA.fullmatch(base) is None:
            _fail("the canonical main revision is unavailable")
        bound = promotion_binding()
        if bound is None:
            # The deployment evidence this promotion attests does not exist
            # yet; the step waits rather than inventing a record.
            return None
        if type(bound) is not dict:
            _fail("the reviewed promotion binding is not readable")
        keys = ("from_channel", "to_channel", "deployment_runs_sha256",
                "attestation_sha256")
        if any(key not in bound for key in keys):
            _fail("the reviewed promotion binding omits a required field")
        from_channel, to_channel = bound["from_channel"], bound["to_channel"]
        if from_channel != fields["channel"]:
            _fail("the reviewed promotion starts from a channel the intent row "
                  "is not on")
        try:
            forward = channel_rank(to_channel) > channel_rank(from_channel)
        except Exception:
            _fail("the reviewed promotion names an unknown channel")
        if not forward or to_channel == "stable":
            _fail("the reviewed promotion does not move strictly forward to an "
                  "implemented channel")
        for key in ("deployment_runs_sha256", "attestation_sha256"):
            if type(bound[key]) is not str or _DIGEST.fullmatch(bound[key]) is None:
                _fail("the reviewed promotion binding carries no valid digests")
        placeholder = canonical_sha256({"request": fields["request_sha256"],
                                        "step": "promotion", "placeholder": "head"})
        placeholder_tree = canonical_sha256({"request": fields["request_sha256"],
                                             "step": "promotion",
                                             "placeholder": "tree"})
        spec = {"operation_id": fields["operation_id"],
                "request_sha256": fields["request_sha256"],
                "repository_id": fields["repository_id"],
                "actor_id": fields["actor_id"],
                "base_revision": base,
                "head_sha": placeholder[:40], "tree_sha": placeholder_tree[:40],
                "tag": fields["tag"], "target_revision": fields["target_revision"],
                "to_channel": to_channel, "from_channel": from_channel,
                "deployment_runs_sha256": bound["deployment_runs_sha256"],
                "attestation_sha256": bound["attestation_sha256"]}
        validate_spec(spec)
        return PromotionCarrier(commit=commit_for(spec),
                                sequence=sequence_for(spec))

    return RecoveredStep("promotion", recover, drives=True)


def enrolled_candidate_timestamp(transition_root):
    """The Task author timestamp the enrolled candidate scope froze, or None.

    The managed transition's enrolled scope binds the author identity
    (including the timestamp) at first enrollment, and every later
    reconstruction must reproduce it exactly. A missing transition journal
    means nothing was enrolled; a present-but-misshapen record is corrupt
    state and fails closed.
    """
    from .candidate_snapshot import read
    from .candidate_transition import CandidateTransition

    root = Path(transition_root).absolute()
    if not root.is_dir():
        return None
    with RequestJournal(root, writable=False) as journal:
        enrolled = read(journal, CandidateTransition.MARKER, optional=True)
    if enrolled is None:
        return None
    author = enrolled.get("author") if type(enrolled) is dict else None
    timestamp = author.get("timestamp") if type(author) is dict else None
    if type(timestamp) is not int or not 1 <= timestamp <= 253402300799:
        _fail("the enrolled candidate scope records no valid Task timestamp")
    return timestamp


def enrolled_candidate_scope_env(preparation_root):
    """The (PATH, source_timestamp) this request's enrollment froze, or None.

    `compose_candidate` binds the process PATH and a Task timestamp into the
    candidate scope at first enrollment. Both change across shells and
    processes, so a resumed run can only adopt its own enrollment by reading
    the recorded values back: the PATH lives in the source-setup marker, the
    timestamp in the parent candidate-preparation marker. A missing journal
    means nothing was enrolled; a present-but-misshapen record is corrupt
    state and fails closed. The parent marker is read with a raw nofollow
    open rather than a journal context: intermediate directories created by
    our own umask may be world-readable, and the privacy invariant belongs
    to the journals themselves, not to ancestors this function never owned.
    """
    from .candidate_snapshot import read
    from .candidate_preparation import CandidatePreparation
    from .orchestration import RequestJournal

    parent = Path(preparation_root).absolute()
    root = parent / "source-setup"
    if not parent.is_dir():
        return None
    path = timestamp = None
    if root.is_dir():
        with RequestJournal(root, writable=False) as journal:
            marker = read(journal, "source-setup-operation.json", optional=True)
        if marker is not None:
            if type(marker) is not dict:
                _fail("the enrolled source-setup scope is corrupt")
            path = marker.get("path")
            if type(path) is not str or not path:
                _fail("the enrolled source-setup scope records no valid PATH")
    marker_path = parent / CandidatePreparation.MARKER
    try:
        fd = os.open(marker_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except (FileNotFoundError, NotADirectoryError):
        fd = None
    except OSError:
        _fail("the enrolled candidate scope is unreadable")
    if fd is not None:
        try:
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(65537)
            if len(raw) > 65536:
                _fail("the enrolled candidate scope is corrupt")
            parent_marker = json.loads(raw)
            timestamp = parent_marker.get("source_timestamp") if type(parent_marker) is dict else None
            if type(timestamp) is not int or not 1 <= timestamp <= 253402300799:
                _fail("the enrolled candidate scope records no valid Task timestamp")
        finally:
            os.close(fd)
    if path is None and timestamp is None:
        return None
    return path, timestamp


def enroll_candidate(*, request, preparation_root, repository_root, source_root,
                     reservation_root, transition_root, witness_root,
                     repository_id, client, token, authorize, observe_main,
                     review, verify_merged, clock, path, author_name,
                     author_email, source_timestamp, drive=True):
    """The managed `candidate` adapter for this exact frozen request.

    Managed, not self-driving: the returned `CandidateTransition` goes to the
    driver's `candidate=` slot and follows the managed path, so nothing here
    exposes a carrier `advance`. With `drive=True` the assembly drives the
    trusted preparation layer (source setup, official snapshot and the six cut
    checks) to its verified receipts — resumable, re-executing nothing — then
    binds the transition to those receipts. With `drive=False` the assembly is
    read-only: it returns None while the preparation is not verified, so an
    observation never executes anything. A `tag`-mode request is refused by
    the preparation and transition layers themselves: a checked-cut allocation
    only exists for `new` mode. Any leg that cannot reach verified fails
    closed — the entry never receives a half-prepared adapter.
    """
    from .candidate_preparation import CandidatePreparation

    for name, callback in (("authorize", authorize), ("observe_main", observe_main),
                           ("review", review), ("verify_merged", verify_merged),
                           ("clock", clock)):
        if not callable(callback):
            _fail(f"requires a callable {name}")
    preparation = CandidatePreparation(
        preparation_root, repository_root=repository_root,
        source_root=source_root, reservation_root=reservation_root,
        request=request, authorize=authorize, observe_main=observe_main,
        path=path, author_name=author_name, author_email=author_email,
        source_timestamp=source_timestamp, clock=clock)
    observed = preparation.observe(initialize=True)
    if observed["status"] == "pending" and drive:
        # A prior process enrolled this request under its own PATH and Task
        # timestamp; both are bound into the scope and change across shells.
        # Adopt the recorded values so the scope binding survives the process
        # boundary instead of drifting into a permanent "rebound" refusal.
        recorded = enrolled_candidate_scope_env(preparation_root)
        if recorded is not None and recorded != (path, source_timestamp):
            preparation = CandidatePreparation(
                preparation_root, repository_root=repository_root,
                source_root=source_root, reservation_root=reservation_root,
                request=request, authorize=authorize, observe_main=observe_main,
                path=recorded[0], author_name=author_name,
                author_email=author_email, source_timestamp=recorded[1],
                clock=clock)
            observed = preparation.observe(initialize=True)
    if observed["status"] == "verified":
        driven = observed
    elif not drive:
        return None
    elif observed["status"] == "pending":
        # Only a positively incomplete preparation is drivable; drift or an
        # unreadable state is never prepared over.
        driven = preparation.prepare(
            before_write=lambda: authorize(deepcopy(request)))
        if driven["status"] != "verified":
            _fail("candidate preparation did not reach its verified receipts")
    else:
        _fail("candidate preparation is not in a derivable state")
    return assemble_candidate_transition(
        request=request, checks=preparation.checks, source=driven["source"],
        checked_cut=driven["checked_cut"], frozen=driven["frozen"],
        transition_root=transition_root, witness_root=witness_root,
        repository_id=repository_id, client=client, token=token,
        authorize=authorize, observe_main=observe_main, review=review,
        verify_merged=verify_merged, clock=clock, author_name=author_name,
        author_email=author_email)


def assemble_candidate_transition(*, request, checks, source, checked_cut,
                                  frozen, transition_root, witness_root,
                                  repository_id, client, token, authorize,
                                  observe_main, review, verify_merged, clock,
                                  author_name, author_email):
    """Bind the managed candidate transition to verified preparation receipts.

    The Task author timestamp comes from the enrolled transition scope when
    one exists, so a resumed drive in a new process reproduces the identical
    adapter rather than failing the scope binding; otherwise it is read from
    the trusted clock.
    """
    from .candidate_transition import CandidateTransition

    timestamp = enrolled_candidate_timestamp(transition_root)
    if timestamp is None:
        timestamp = clock()
    return CandidateTransition(
        transition_root, checks=checks, request=request, source=source,
        checked_cut=checked_cut, frozen=frozen, repository_id=repository_id,
        client=client, token=token, authorize=authorize,
        observe_main=observe_main, review=review, verify_merged=verify_merged,
        witness_root=witness_root, author_name=author_name,
        author_email=author_email, timestamp=timestamp)


_DISPATCH_STEPS = ("publication", "runtime", "creator")


class RecoveredDispatch:
    """One managed dispatch step: recover the spec, then delegate.

    The dispatch counterpart of `RecoveredStep`. The dispatch slots on the
    driver accept only the concrete `DispatchTransition`, and a dispatch spec
    exists only after prior steps land, so this lazy wrapper rides the backend
    carrier path: its `advance` takes the driver's `before_write` guard and
    forwards it as the delegate's `before_post`. A step whose dispatch inputs
    are not yet derivable from prior steps' records is `pending`, never
    `absent`.
    """

    def __init__(self, step, recover):
        if step not in _DISPATCH_STEPS:
            _fail(f"unknown dispatch step {step!r}")
        if not callable(recover):
            _fail("requires a callable spec recovery")
        self.step = step
        self._recover = recover
        self._waiting = None
        self._observed = None

    def adapter(self, state, operation):
        """The concrete DispatchTransition for this operation, or None."""
        if operation.get("step") != self.step:
            _fail("operation does not belong to this step")
        return self._recover(state, operation)

    def observe(self, state, operation):
        adapter = self.adapter(state, operation)
        if adapter is None:
            # The inputs this step dispatches on do not exist yet; the run
            # waits rather than claiming absence.
            self._waiting = operation.get("operation_id")
            self._observed = None
            return Observation("pending")
        self._waiting = None
        self._observed = (operation.get("operation_id"), adapter)
        return adapter.observe(state, operation)

    def advance(self, state, operation, *, before_write):
        # The driver holds one writer lock across observe → advance, so the
        # adapter the observation just produced is the one to drive; only
        # without it is a fresh recovery needed.
        if self._observed is not None \
                and self._observed[0] == operation.get("operation_id") \
                and operation.get("step") == self.step:
            adapter = self._observed[1]
        else:
            adapter = self.adapter(state, operation)
        if adapter is None:
            if self._waiting == operation.get("operation_id"):
                # The driver asks the managed step to act precisely when the
                # inputs are not derivable; it re-observes after the call, so
                # writing nothing keeps the step honestly pending.
                return
            _fail("the step's dispatch inputs are not derivable but it was "
                  "asked to act")
        adapter.advance(state, operation, before_post=before_write)


def enroll_publication(*, root, candidate_root, repository_id, ledger,
                       workflow_id, producer_revision, release_by_tag,
                       transition_for):
    """The `publication` step: dispatch publish-release.yml for the reviewed Draft.

    Managed adapter: the returned `RecoveredDispatch` follows the driver's
    managed dispatch path. The spec's inputs come from prior steps' records —
    the tag and target revision from the intent row (authoritative per the
    reconciled identity), the plan digest from the `prepared` output, the
    numeric Release identity from the far-side Draft the `draft` step created,
    and the changelog digests from the row's frozen changelog binding. Until
    all four exist the step is `pending`; a Release that disappeared or
    carries no numeric identity, or a record that drifts between recovery and
    the dispatch boundary, fails closed. `workflow_id`/`producer_revision` are
    the trusted composition's pins for the publish workflow.
    `transition_for(spec, expected, bind)` is the trusted composition's
    factory for the concrete `DispatchTransition` (controller and the
    `PublicationEffect` verifier); the enrollment owns `bind`, which
    re-derives every external input from the current records and requires
    they still match the spec at the dispatch boundary.
    """
    from .batch_reference import thaw
    from .changelog import binding as changelog_binding
    from .durable_dispatch import validate_spec as validate_dispatch_spec
    from .model import canonical_sha256

    if not callable(release_by_tag) or not callable(transition_for):
        _fail("requires the trusted far-side reader and transition factory")

    def operation_id(digest):
        return canonical_sha256({"request": digest, "step": "publication"})

    def recover_inputs(state):
        """The dispatch inputs from current records, or None while underivable."""
        fields = spec_identity(state, candidate_root=candidate_root,
                               repository_id=repository_id, ledger=ledger,
                               operation_id=operation_id, fields=_DRAFT_FIELDS)
        if fields is None:
            return None
        tag = fields["tag"]
        plan = read_prepared_plan(root, tag)
        if plan is None:
            return None
        release = release_by_tag(tag)
        if release is None:
            # The draft step has not created the Release yet.
            return None
        if not hasattr(release, "get"):
            _fail("the far-side Release projection is not readable")
        release_id = release.get("id")
        if type(release_id) is not int or release_id <= 0:
            _fail("the far-side Release carries no valid numeric identity")
        intent = ledger.intent_for_tag(tag)
        changelog = getattr(intent, "changelog", None) if intent is not None else None
        if changelog is None:
            # The changelog step has not bound its frozen record yet.
            return None
        digests = changelog_binding(thaw(changelog))
        op_id = fields["operation_id"]
        spec = {"request_sha256": fields["request_sha256"],
                "operation_id": op_id,
                "repository_id": fields["repository_id"],
                "actor_id": fields["actor_id"],
                "workflow": "publish-release.yml",
                "workflow_id": workflow_id,
                "control_revision": state["request"]["control_revision"],
                "producer_revision": producer_revision,
                "inputs": {"tag": tag, "release_id": str(release_id),
                           "plan_sha256": plan, "request_id": op_id}}
        expected = {"target_revision": fields["target_revision"],
                    "changelog_sha256": digests["sha256"],
                    "notes_sha256": digests["notes_sha256"]}
        return spec, expected

    def recover(state, operation):
        recovered = recover_inputs(state)
        if recovered is None:
            return None
        spec, expected = recovered
        validate_dispatch_spec(spec)

        def bind(state, operation, bound=spec, expected=expected):
            """Re-derive every external input; the records must still agree.

            Both halves are re-derived: the spec inputs and the frozen effect
            expectation (target revision and changelog digests), so a ledger
            or changelog drift between recovery and the dispatch boundary
            fails closed instead of dispatching against a stale expectation.
            """
            current = recover_inputs(state)
            if current is None or current != (bound, expected):
                _fail("the dispatch inputs drifted from the enrolled spec")

        return transition_for(spec, expected, bind)

    return RecoveredDispatch("publication", recover)


_DEPLOY_WORKFLOWS = {"runtime": "deploy-web-runtime-host.yml",
                     "creator": "deploy-creator-web.yml"}


def enroll_deployment(step, *, candidate_root, repository_id, ledger,
                      workflow_id, producer_revision, projection_for,
                      transition_for):
    """The `runtime`/`creator` step: dispatch the Host deploy for this release.

    Managed adapter, one per step; both share this recovery. The identity
    (tag, target revision, Product Build) comes from the intent row through
    `spec_identity`. The frozen deployment projection — release asset digests,
    host version, site identity and the pre-dispatch Site prior — is injected
    by the trusted composition as `projection_for(tag)`: it must answer the
    same frozen projection for the request's whole drive, including resume
    after the dispatch, and returns None while it is not assembled yet (the
    step waits `pending`). The projection must bind this release's target and
    Build; the step's own effect verifier revalidates the full projection
    against the run's retained evidence. `bind` re-derives both the spec and
    the expectation at the dispatch boundary and fails closed on drift; one
    layer down, the durable child refuses a rebound spec. `workflow_id` /
    `producer_revision` are the trusted composition's pins for the deploy
    workflow. `transition_for(spec, expected, bind)` builds the concrete
    `DispatchTransition` with the `DeploymentEffect` verifier.
    """
    from .durable_dispatch import validate_spec as validate_dispatch_spec
    from .model import canonical_sha256

    if step not in _DEPLOY_WORKFLOWS:
        _fail(f"unknown deployment step {step!r}")
    if not callable(projection_for) or not callable(transition_for):
        _fail("requires the trusted projection reader and transition factory")
    workflow = _DEPLOY_WORKFLOWS[step]

    def operation_id(digest):
        return canonical_sha256({"request": digest, "step": step})

    def recover_inputs(state):
        """The dispatch spec and frozen expectation, or None while underivable."""
        fields = spec_identity(state, candidate_root=candidate_root,
                               repository_id=repository_id, ledger=ledger,
                               operation_id=operation_id, fields=_SITE_FIELDS)
        if fields is None:
            return None
        projection = projection_for(fields["tag"])
        if projection is None:
            # The composition has not assembled the frozen projection yet.
            return None
        if type(projection) is not dict:
            _fail("the frozen deployment projection is not readable")
        expected = deepcopy(projection)
        missing = sorted(key for key in ("target_revision", "product_build",
                                         "prior_site_sha256")
                         if key not in expected)
        if missing:
            _fail(f"the frozen deployment projection omits {', '.join(missing)}")
        if expected["target_revision"] != fields["target_revision"] \
                or expected["product_build"] != fields["product_build"]:
            _fail("the frozen deployment projection does not bind this release")
        prior_digest = expected["prior_site_sha256"]
        if type(prior_digest) is not str or _DIGEST.fullmatch(prior_digest) is None:
            _fail("the frozen deployment projection has no valid prior digest")
        op_id = fields["operation_id"]
        spec = {"request_sha256": fields["request_sha256"],
                "operation_id": op_id,
                "repository_id": fields["repository_id"],
                "actor_id": fields["actor_id"],
                "workflow": workflow,
                "workflow_id": workflow_id,
                "control_revision": state["request"]["control_revision"],
                "producer_revision": producer_revision,
                "inputs": {"tag": fields["tag"], "request_id": op_id,
                           "prior_site_sha256": prior_digest}}
        return spec, expected

    def recover(state, operation):
        recovered = recover_inputs(state)
        if recovered is None:
            return None
        spec, expected = recovered
        validate_dispatch_spec(spec)

        def bind(state, operation, bound=spec, expected=expected):
            """Re-derive both halves; the records must still agree."""
            current = recover_inputs(state)
            if current is None or current != (bound, expected):
                _fail("the deployment dispatch drifted from the enrolled spec")

        return transition_for(spec, expected, bind)

    return RecoveredDispatch(step, recover)


def enroll_published_record(*, root, candidate_root, repository_id, ledger,
                            release_by_tag, transition_for):
    """The `published_record` step: land the publication record via a reviewed PR.

    The step drives its own write (the evidence commit plus the reviewed
    `EvidencePrTransition` PR leg), so the wrapper is a `drives=True`
    `RecoveredStep`: the driver's `publication_pr` slot accepts only the
    concrete transition, so this lazy wrapper rides the backend carrier path,
    whose guard signature (`before_write`) is exactly the managed slot's.

    Recovery: the identity comes from the intent row via `spec_identity`; the
    plan digest from the `prepared` output; the numeric Release identity from
    the far side — published and non-draft, since this step runs after
    `publication`. Nothing published, a still-draft Release, or a missing plan
    is `pending`; an unreadable or id-less Release fails closed. The
    publication record file itself is this step's output, so no record read
    participates here. `transition_for(...)` is the trusted composition's
    factory: it drives the durable evidence commit (`PublicationWorkspace`)
    and Task verification, then builds the concrete `EvidencePrTransition`;
    the enrollment refuses anything else.
    """
    from .evidence_pr_transition import EvidencePrTransition
    from .model import canonical_sha256

    if not callable(release_by_tag) or not callable(transition_for):
        _fail("requires the trusted far-side reader and transition factory")

    def operation_id(digest):
        return canonical_sha256({"request": digest, "step": "published_record"})

    def recover(state, operation):
        fields = spec_identity(state, candidate_root=candidate_root,
                               repository_id=repository_id, ledger=ledger,
                               operation_id=operation_id, fields=_DRAFT_FIELDS)
        if fields is None:
            return None
        tag = fields["tag"]
        plan = read_prepared_plan(root, tag)
        if plan is None:
            return None
        release = release_by_tag(tag)
        release_id = checked_release_id(release)
        if release_id is None:
            # Nothing published under this tag yet.
            return None
        if release.get("draft"):
            # A draft means the publication step has not completed.
            return None
        adapter = transition_for(tag=tag,
                                 target_revision=fields["target_revision"],
                                 repository_id=fields["repository_id"],
                                 actor_id=fields["actor_id"],
                                 request_sha256=fields["request_sha256"],
                                 operation_id=fields["operation_id"],
                                 release_id=release_id, plan_sha256=plan)
        if type(adapter) is not EvidencePrTransition:
            _fail("the composition did not build the concrete publication "
                  "evidence transition")
        return adapter

    return RecoveredStep("published_record", recover, drives=True)


def enroll_verification(*, candidate_root, journal_load, consumer,
                        fresh_receipts):
    """The `verification` step: the exact-target full batch must certify it.

    Observe-only: the batch is produced by main's own CI when the witness
    merge lands, never by this step, so the wrapper exposes no `advance`.
    `BatchVerification` carries no spec — its inputs are the authenticated
    batch journal (`journal_load`), the policy-pinned evidence consumer, and
    the trusted candidate receipts (`fresh_receipts`) — so the wrapper's
    recovery only decides whether anything exists to verify: no allocation,
    or a cut merged without its verified witness merge, is `pending` (never
    `absent`), and the delegate then reports its own honest `pending` until
    the batch result lands. A `tag`-mode request has no candidate state, so
    the step waits, matching the managed candidate transition's own refusal.
    """
    from .verification import BatchVerification

    for name, factory in (("journal_load", journal_load),
                          ("fresh_receipts", fresh_receipts)):
        if not callable(factory):
            _fail(f"requires a callable {name}")

    def recover(state, operation):
        if type(state) is not dict or type(state.get("request")) is not dict:
            _fail("requires the running request state")
        digest = state.get("request_digest")
        if type(digest) is not str or _DIGEST.fullmatch(digest) is None:
            _fail("the running request carries no valid digest")
        allocated = read_candidate_identity(candidate_root, digest)
        if allocated is None or allocated["witness_revision"] is None:
            # Nothing certified exists to verify a batch against yet.
            return None
        # BatchVerification itself enforces the concrete consumer type.
        return BatchVerification(journal_load=journal_load, consumer=consumer,
                                 fresh_receipts=fresh_receipts)

    return RecoveredStep("verification", recover)


class DeferredCandidate:
    """The `candidate` step at the real entry: deferred, request-free assembly.

    The driver's `candidate=` slot accepts only the concrete
    `CandidateTransition`, whose receipts exist only after the trusted
    preparation layer runs — so at carrier-list time there is nothing concrete
    to build. This adapter rides the backend carrier path: `observe` is
    read-only (`pending` until the preparation is verified), and `advance`
    drives the preparation and then the transition under the driver's guard.
    The composition passes `enroll(request, drive)`; a `tag`-mode request is
    refused by the preparation layer itself.
    """

    step = "candidate"

    def __init__(self, enroll):
        if not callable(enroll):
            _fail("requires the callable candidate assembly")
        self._enroll = enroll

    def _operation(self, operation):
        if operation.get("step") != "candidate":
            _fail("operation does not belong to this step")

    def observe(self, state, operation):
        self._operation(operation)
        adapter = self._enroll(state["request"], drive=False)
        if adapter is None:
            return Observation("pending")
        return adapter.observe(state, operation)

    def advance(self, state, operation, *, before_write):
        self._operation(operation)
        adapter = self._enroll(state["request"], drive=True)
        adapter.advance(state, operation, before_write=before_write)

    def execute(self, state, operation):
        # The backend execute path is for steps whose far side is created by a
        # bare execute; the candidate step only ever advances.
        _fail("the candidate step cannot be driven through a bare execute")
