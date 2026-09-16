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
    as "absent"; the step that needs it decides what that means for itself, and
    this enrollment reports it as `pending` because it cannot drive `prepare`
    (see #1404). Only an absent pair means that: the digest is checked against
    the plan document bytes it names, so a swapped digest file cannot silently
    redefine what a later step binds, and half of the pair is drift. Which
    *reviewed* digest authorizes the plan is still open (#1404): no ledger row
    records it yet.
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
        if release is not None and not hasattr(release, "get"):
            _fail("the far-side Release projection is not readable")
        if recorded is None:
            # The publication record does not name this tag yet, so there is
            # no confirmed Release identity to bind, whatever the far side
            # shows; the step waits rather than guessing one.
            return None
        if type(recorded) is not int or recorded <= 0:
            _fail("the publication record carries no valid numeric Release "
                  "identity")
        if release is None:
            _fail("the publication record names a Release the far side does "
                  "not have")
        if release.get("draft"):
            _fail("the publication record names a Release that is still a "
                  "draft")
        if release.get("id") != recorded:
            _fail("the publication record and the far-side Release disagree "
                  "on the Release identity")
        spec = dict(fields, site_base_url=site_base_url, release_id=recorded)
        validate_final_spec(spec)
        # The carrier passes the frozen tag to both readers itself, so the
        # identity they answer for cannot drift from the one it verifies.
        return FinalCarrier(spec=spec, fetch=fetch, release_by_tag=release_by_tag,
                            ledger_row=ledger_row)

    return RecoveredStep("final", recover)


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


def enroll_candidate(*, request, preparation_root, repository_root, source_root,
                     reservation_root, transition_root, witness_root,
                     repository_id, client, token, authorize, observe_main,
                     review, verify_merged, clock, path, author_name,
                     author_email, source_timestamp):
    """The managed `candidate` adapter for this exact frozen request.

    Managed, not self-driving: the returned `CandidateTransition` goes to the
    driver's `candidate=` slot and follows the managed path, so nothing here
    exposes a carrier `advance`. The assembly drives the trusted preparation
    layer (source setup, official snapshot and the six cut checks) to its
    verified receipts — resumable, re-executing nothing — then binds the
    transition to those receipts. A `tag`-mode request is refused by the
    preparation and transition layers themselves: a checked-cut allocation
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
    if observed["status"] == "verified":
        driven = observed
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
