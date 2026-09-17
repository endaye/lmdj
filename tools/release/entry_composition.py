"""Trusted composition wiring the enrolled carriers at the real release entry.

`cli.release_carriers` delegates here. One request's fourteen enrolled carriers
are assembled from production modules only: the entry gates from
`entry_gates`, the `carriers.enroll_*` recovery wrappers, and the durable
machinery (`candidate_preparation`, `durable_dispatch`, `publication_workspace`,
`task_verification`, the PR transports). Nothing is driven at assembly: every
wrapper recovers lazily, so today's incomplete scope still refuses before any
request or drive. The `scripts/ci` modules use bare sibling imports by design
(CI entry points), so this module appends that directory to `sys.path` once —
the same self-registration pattern `cli.py` and `tag_verifier.py` use for the
repository root.

One composition input has no production channel yet and stays a named,
fail-closed seam rather than an invention: the reviewed changelog editorial
input. While it is undefined that step honestly stays `pending`; the wiring
itself is complete and needs no change once the channel lands.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
_CI = str(ROOT / "scripts" / "ci")
if _CI not in sys.path:
    sys.path.append(_CI)

from .batch_reference import sha
from .carriers import (
    DeferredCandidate,
    checked_release_id,
    enroll_candidate,
    enroll_changelog,
    enroll_changelog_site,
    enroll_deployment,
    enroll_draft,
    enroll_final,
    enroll_intent,
    enroll_prepared,
    enroll_promotion,
    enroll_publication,
    enroll_published_record,
    enroll_tag,
    enroll_verification,
)
from .entry_gates import (
    EntryGateError,
    authority_gate,
    batch_evidence_consumer,
    dispatch_authority,
    main_observation,
    merged_gate,
    production_review_reader,
    review_gate,
)
from .model import canonical_sha256, load_ledger
from .orchestration import JournalError, RequestJournal, validate_request


def _fail(reason):
    raise JournalError(
        f"why: release entry composition {reason}; remedy: restore the trusted "
        "production input or authority the name calls for; never substitute a "
        "fixture on the real path")


# Every driver step now has an enrolled carrier, so `backend.missing(STEPS)` is
# empty and `run`/`resume` no longer refuse a scope for an unowned step. Each
# step still reports `pending` until its own identity exists.
ENROLLED_STEPS = ("candidate", "verification", "intent", "changelog", "prepared",
                  "tag", "draft", "publication", "published_record",
                  "changelog_site", "runtime", "creator", "promotion", "final")

_SITE_BASE_URL = "https://docs.lmdj.workers.dev"
_RUN_URL = re.compile(
    r"https://github\.com/endaye/lmdj/actions/runs/([1-9][0-9]*)\Z")
_FETCH_LIMIT = 2 * 1024 * 1024
_WORKFLOWS_DIR = ".github/workflows"
_LEDGER = "docs/release-evidence/release-intents.json"
_PUBLICATIONS = "docs/release-evidence/changelog-publications.json"


def release_journal_root(root, git):
    """The request journal lives beside the repository's own Git directory."""
    directory = git.runner.run(
        ("git", "-C", str(root), "rev-parse", "--absolute-git-dir")
    ).stdout.strip()
    return Path(directory) / "lmdj-release-requests"


class LiveLedger:
    """Re-reads the canonical ledger on every lookup: mid-run merges land."""

    def __init__(self, path, policy):
        self.path, self.policy = path, policy

    def intent_for_tag(self, tag):
        return load_ledger(self.path, self.policy).intent_for_tag(tag)


def release_token(runner):
    """Workflow credentials when present, otherwise the logged-in gh identity."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        token = runner.run(("gh", "auth", "token")).stdout.strip()
    if not token:
        _fail("GitHub authentication is unavailable")
    return token


def resolve_repository_id(*, token):
    """The numeric repository identity from the authenticated read path."""
    reader = production_review_reader(token=token)("endaye/lmdj")
    document = reader.get("/repos/endaye/lmdj", fresh=True)
    identity = document.get("id") if isinstance(document, dict) else None
    if type(identity) is not int or identity <= 0:
        _fail("the canonical repository identity is unavailable")
    return identity


def site_fetch(url):
    """The production docs-site route fetch: (status, body), bounded."""
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "lmdj-release-entry"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read(_FETCH_LIMIT).decode(
                "utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        # An HTTP answer (404 et al.) is evidence, not a transport failure.
        return error.code, error.read(_FETCH_LIMIT).decode("utf-8", errors="replace")


def reviewed_changelog_editorial():
    """The reviewed editorial input channel is not defined yet.

    The changelog step binds a *reviewed* (changes, exclusions) pair and no
    production channel supplies one. Naming the seam keeps the step honestly
    `pending`; inventing an editorial default would settle an open product
    question inside tooling, which this composition must not do.
    """
    return None


_HOST_TOOLS = ROOT / "apps/web-runtime-host/tools"
# Read-only Cloudflare tools, run as installed trusted tools the same way the
# deployment effect runs its validator: never a candidate worktree's copy.
_WORKER_INSPECT = _HOST_TOOLS / "cloudflare_host.py"
_SITE_OBSERVATION = _HOST_TOOLS / "cloudflare_site_observation.py"
_HOST_ORIGINS = _HOST_TOOLS / "cloudflare_deployment_evidence.py"
_READ_TIMEOUT = 120


def _read_only_tool(tool, arguments, *, environment=None):
    """Run one installed read-only tool and return its document, or None.

    None is "could not read", never "read nothing": every caller turns it into
    `pending` rather than into an assumption about production.
    """
    env = {k: v for k, v in os.environ.items()
           if k in ("PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")}
    env.update(environment or {})
    try:
        result = subprocess.run([sys.executable, "-s", "-B", str(tool), *arguments],
                                capture_output=True, env=env, timeout=_READ_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        document = json.loads(result.stdout)
    except ValueError:
        return None
    return document if type(document) is dict else None


class _CloudflareReader:
    """The live facts the frozen projection cannot derive from the release.

    Each answer comes from an installed read-only tool, so this module states
    no Worker name, no URL shape and no deployment identity of its own. The
    Cloudflare token is the operator's; without it the Worker cannot be read
    and every projection stays `pending`.
    """

    def __init__(self, token, state_root):
        self._token = token
        self._state_root = Path(state_root)
        self._inspected = {}

    def _inspect(self, host):
        if host not in self._inspected:
            try:
                # Only the parent: the adapter's run store creates its own
                # journal root at 0700 and refuses one whose group or other
                # bits are set, so creating it here with the default mode
                # would make every inspection fail.
                self._state_root.parent.mkdir(parents=True, exist_ok=True)
                if self._state_root.is_dir():
                    os.chmod(self._state_root, 0o700)
            except OSError:
                _fail("the Cloudflare inspection workspace is unavailable")
            self._inspected[host] = _read_only_tool(
                _WORKER_INSPECT,
                ("inspect", "--target", host, "--state-root", str(self._state_root)),
                environment={"CLOUDFLARE_API_TOKEN": self._token})
        return self._inspected[host]

    def worker(self, host):
        document = self._inspect(host)
        if document is None or type(document.get("worker")) is not str:
            _fail(f"the live Worker identity for {host} is unavailable")
        return document["worker"]

    def version_url(self, host, version):
        document = _read_only_tool(_HOST_ORIGINS,
                                   ("urls", host, "--version", version))
        if document is None or type(document.get("version")) is not str:
            _fail(f"the immutable origin for {host} is unavailable")
        return document["version"]

    def replaced_version(self, host):
        from .deployment_projection import NO_DEPLOYMENT

        document = self._inspect(host)
        if document is None:
            return None
        if not document.get("exists") or document.get("deployment") is None:
            return NO_DEPLOYMENT
        deployment = document["deployment"]
        if type(deployment) is not dict \
                or type(deployment.get("version_id")) is not str:
            _fail("the live Worker deployment is unreadable")
        return deployment["version_id"]

    def observe(self, host):
        origins = _read_only_tool(_HOST_ORIGINS, ("urls", host))
        if origins is None or type(origins.get("production")) is not str:
            _fail(f"the production origin for {host} is unavailable")
        return _read_only_tool(_SITE_OBSERVATION, (origins["production"],))


_INSPECT_STATE = "cloudflare-inspection"


def deployment_projection(root, tag, step):
    """The frozen deployment projection for this step, or None while unreadable.

    Assembled once from this release's own prepared output plus one read of the
    live Worker and its public origin, then frozen: a resume after the dispatch
    reads those bytes back rather than observing a production the deployment
    has already replaced. The Cloudflare token is the authorized operator's and
    is never recorded; without it the Worker cannot be read and the step stays
    `pending`, which is also what an unprepared release reports.
    """
    from .deployment_projection import projection

    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        return None
    # Per tag, beside that tag's own frozen projection: a shared root would put
    # two concurrent drives in one adapter run store, and `build/release/` is
    # already ignored, so nothing untracked appears elsewhere in the tree.
    from .prepared_step import output_relative

    workspace = Path(root) / output_relative(tag) / _INSPECT_STATE
    return projection(root, tag, step,
                      reader=_CloudflareReader(token, workspace))


def _release_author(git):
    """The trusted local commit author identity; unset is fail-closed."""
    def read(key):
        result = git.runner.run(("git", "-C", str(git.root), "config",
                                 "--get", key)).stdout.strip()
        if not result:
            _fail(f"the release commit author identity is unavailable ({key})")
        return result
    return read("user.name"), read("user.email")


def _workflow_id(github, workflow):
    """The pinned workflow's numeric identity, resolved live and path-checked."""
    document = github.get_dispatch_evidence(f"/repos/endaye/lmdj/actions/workflows/{workflow}")
    identity = document.get("id") if isinstance(document, dict) else None
    if type(identity) is not int or identity <= 0 \
            or document.get("path") != f"{_WORKFLOWS_DIR}/{workflow}":
        _fail(f"the trusted workflow identity for {workflow} is unavailable")
    return identity


def _producer_revision(root, git, workflow, control_revision):
    """The last control-side revision that touched the workflow definition."""
    result = git.runner.run(
        ("git", "-C", str(root), "log", "-1", "--format=%H", control_revision,
         "--", f"{_WORKFLOWS_DIR}/{workflow}")).stdout.strip()
    if not sha(result):
        _fail(f"the producer pin for {workflow} is unavailable")
    return result


def _batch_journal_load(root, token):
    """The authenticated batch journal reader over the pinned CI storage.

    Lazy: the transport and its pinned configuration are assembled on the
    first actual read, so carrier assembly itself touches nothing.
    """
    held = {}

    def journal_load():
        if "load" not in held:
            from batch_github_journal import GitHubJournalTransport
            from incremental_batch_journal import IssueBodyAnchor, Journal

            path = root / "scripts" / "ci" / "incremental_storage.json"
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                _fail("the pinned batch journal configuration is unreadable")
            config = document.get("scheduler") if type(document) is dict else None
            if type(config) is not dict:
                _fail("the pinned batch journal configuration is not a document")
            transport = GitHubJournalTransport(
                repository=config["repository"],
                issue_number=config["issue_number"],
                issue_node_id=config["issue_node_id"],
                bot_node_id=config["bot_node_id"],
                workflows={".github/workflows/self-test-report.yml":
                           config["workflow_id"]},
                writer={"repository": config["repository"],
                        "issue_number": config["issue_number"]},
                token=token, lock_held=lambda: False)
            anchor = IssueBodyAnchor(config["issue_number"], transport,
                                     transport.authenticate, lambda: False)
            held["load"] = Journal(config["issue_number"], transport, anchor,
                                   transport.authenticate, lambda: False).load
        return held["load"]()

    return journal_load


def _batch_reference_for(root, token):
    """Read the terminal batch result's reference for one witness revision."""
    load = _batch_journal_load(root, token)

    def batch_reference_for(witness):
        events = load()
        matches = [event["data"] for event in events
                   if type(event) is dict and event.get("type") == "result"
                   and type(event.get("data")) is dict
                   and event["data"].get("target") == witness
                   and event["data"].get("terminal") is True]
        if not matches:
            _fail("the batch journal has no terminal result for the verified "
                  "witness revision")
        if len(matches) > 1:
            _fail("the batch journal binds the witness revision ambiguously")
        reference = matches[0].get("reference")
        if type(reference) is not str or not reference:
            _fail("the terminal batch result has no durable reference")
        return reference

    return batch_reference_for


def _create_draft(context):
    from .transitions import create_draft

    return lambda tag: create_draft(tag, context)


def _push_tag(context):
    """The trusted `push_tag` controller: the real command, bound to this run.

    `push_tag` refuses remote conflicts, reconciles an already-pushed tag, and
    re-verifies the remote state against the local signed tag and the prepared
    plan, so the carrier calls it once and never re-pushes over an unknown.
    """
    from .transitions import push_tag

    return lambda tag: push_tag(tag, context)


def _prepare_release(context):
    """The trusted `prepare` controller: the real command, bound to this run.

    `prepare` builds, signs the local annotated tag and writes the atomic plan
    output; it owns its own reconcile path, so the carrier calls it once and
    never retries an unknown result.
    """
    from .prepare import prepare

    return lambda tag: prepare(tag, context)


def _dispatch_transition(context, root, operations, step, workflow, spec,
                         expected, bind, github, token, repository_id,
                         dispatch_authorize, release_by_tag):
    """Assemble one step's concrete DispatchTransition from production parts."""
    from .deployment_effect import DeploymentEffect
    from .dispatch_evidence import DispatchEvidenceConsumer
    from .dispatch_transition import DispatchTransition
    from .durable_dispatch import DurableDispatch
    from .publication_effect import PublicationEffect

    consumer = DispatchEvidenceConsumer(
        api_get=github.get_dispatch_evidence, git_root=root,
        repository_id=repository_id, workflow=workflow,
        workflow_id=spec["workflow_id"],
        producer_revision=spec["producer_revision"])

    if step == "publication":
        def ready(spec):
            release = release_by_tag(spec["inputs"]["tag"])
            if checked_release_id(release) != int(spec["inputs"]["release_id"]):
                _fail("the dispatch Draft is unavailable")
            if not release.get("draft"):
                _fail("the release is no longer a draft")

        effect = PublicationEffect(context=context, consumer=consumer,
                                   spec=spec, expected=expected)
    else:
        def ready(spec):
            release = release_by_tag(spec["inputs"]["tag"])
            if checked_release_id(release) is None or release.get("draft"):
                _fail("the published release is unavailable")

        effect = DeploymentEffect(consumer=consumer, spec=spec,
                                  expected=expected)
    controller = DurableDispatch(operations / f"dispatch-{step}",
                                 client=github, consumer=consumer,
                                 authorize=dispatch_authorize, ready=ready)
    return DispatchTransition(controller, spec, bind=bind, verify_effect=effect)


def _published_record_transition(context, root, operations, worktrees, inputs,
                                 github, token, authorize, review,
                                 verify_merged, author, path):
    """Drive the evidence commit and Task verification, then build the adapter."""
    from .evidence_pr import EvidencePullRequest
    from .evidence_pr_transition import EvidencePrTransition
    from .evidence_source import PublishedPrSourceGate
    from .publication import collect_publication_state
    from .publication_evidence import plan_publication_patch
    from .publication_workspace import PublicationWorkspace
    from .task_verification import PublicationTaskVerifier, task_scope

    tag = inputs["tag"]
    record, intent = collect_publication_state(tag, inputs["release_id"],
                                               inputs["plan_sha256"], context)
    base = inputs["main_revision"]
    branch = "docs/release-evidence-" + inputs["operation_id"]
    worktree = worktrees / "published-record"
    git = context.git
    if not worktree.exists():
        git.runner.run(("git", "-C", str(root), "worktree", "add", "-b",
                        branch, str(worktree), base))
    verifier = PublicationTaskVerifier(operations / "published-record-task",
                                       root, authorize=authorize, path=path)

    def verify(worktree_root):
        # The worktree content must be exactly the complete planned patch;
        # whitespace is checked against the patch base, and the durable
        # verifier below independently re-runs the declared commands on the
        # committed content.
        if plan_publication_patch(Path(worktree_root), context.policy, intent,
                                  record):
            _fail("the evidence worktree content differs from the plan")
        git.runner.run(("git", "-C", str(worktree_root), "diff", "--cached",
                        "--check"))

    prepared = PublicationWorkspace(worktree).prepare(
        base_revision=base, operation_id=inputs["operation_id"],
        policy=context.policy, intent=intent, record=record,
        author_name=author[0], author_email=author[1],
        timestamp=int(time.time()), verify=verify)
    partial = {"operation_id": inputs["operation_id"],
               "request_sha256": inputs["request_sha256"],
               "repository_id": inputs["repository_id"],
               "actor_id": inputs["actor_id"], "base_revision": base,
               "head_sha": prepared["commit"], "tree_sha": prepared["tree"],
               "tag": tag, "target_revision": inputs["target_revision"],
               "task_evidence_sha256": "0" * 64}
    receipt = verifier.run(task_scope(partial, inputs["control_revision"]))
    spec = dict(partial, task_evidence_sha256=receipt["sha256"])
    source_gate = PublishedPrSourceGate(
        root, context_factory=lambda: context,
        release_id=inputs["release_id"], plan_sha256=inputs["plan_sha256"])

    def authorize_spec(spec):
        authorize(spec)
        verifier.verify(spec, inputs["control_revision"])
        source_gate.verify(spec)

    def merged(spec, row, receipt):
        gate = verify_merged("published_record", spec, row, receipt)
        if gate.status == "verified":
            source_gate.verify(spec, merge_revision=row["merge_commit_sha"])
        return gate

    controller = EvidencePullRequest(
        operations / "published-record-pr", api=github.release_pr_request,
        authorize=authorize_spec,
        review=lambda spec, row: review("published_record", spec, row),
        verify_merged=merged)
    return EvidencePrTransition(controller, spec)


def _candidate_arguments(context, root, operations, worktrees, repository_id,
                         github, token, authorize, observe_main, review,
                         verify_merged, clock, path, author):
    return dict(preparation_root=operations / "candidate-preparation",
                repository_root=root,
                source_root=worktrees / "candidate-source",
                reservation_root=release_journal_root(root, context.git)
                / "build-reservations",
                transition_root=operations / "candidate-transition",
                witness_root=worktrees / "candidate-witness-task",
                repository_id=repository_id, client=github, token=token,
                authorize=authorize, observe_main=observe_main, review=review,
                verify_merged=verify_merged, clock=clock, path=path,
                author_name=author[0], author_email=author[1],
                source_timestamp=int(time.time()))


def compose_candidate(context, policy, request):
    """The concrete managed candidate adapter, driving the preparation layer.

    Only a `new`-mode request has a checked-cut allocation; a `tag`-mode
    request has no candidate transition and the step rides its deferred
    backend wrapper, which fails closed there.
    """
    if request["mode"] != "new":
        return None
    git, github = context.git, context.github
    token = release_token(git.runner)
    repository_id = resolve_repository_id(token=token)
    root = Path(context.repo_root)
    operations = release_journal_root(root, git) / "operations" / request["id"]
    worktrees = root / ".local" / "release-worktrees" / request["id"]
    authorize = authority_gate(github=github, git=git, policy=policy,
                               request=request)
    observe_main = main_observation(git=git)
    review = review_gate(client=github,
                         reader_for=production_review_reader(token=token),
                         repository_id=repository_id)
    return enroll_candidate(
        request=request, drive=True,
        **_candidate_arguments(context, root, operations, worktrees,
                               repository_id, github, token, authorize,
                               observe_main, review, merged_gate(git=git),
                               lambda: int(time.time()),
                               os.environ.get("PATH", ""),
                               _release_author(git)))


def compose_carriers(context, policy, request):
    """The fourteen enrolled step carriers for this exact request (lazy).

    Assembly performs no drives and no batch/site reads: the wrappers recover
    per observation from the records prior steps land. One repository identity
    resolution and the workflow pins are the only entry reads.
    """
    validate_request(request)
    root = Path(context.repo_root)
    git, github = context.git, context.github
    token = release_token(git.runner)
    repository_id = resolve_repository_id(token=token)
    ledger = LiveLedger(root / _LEDGER, context.policy)
    operations = release_journal_root(root, git) / "operations" / request["id"]
    worktrees = root / ".local" / "release-worktrees" / request["id"]
    authorize = authority_gate(github=github, git=git, policy=policy,
                               request=request)
    spec_authorize = dispatch_authority(github=github, git=git, policy=policy,
                                        request=request)
    observe_main = main_observation(git=git)
    review = review_gate(client=github,
                         reader_for=production_review_reader(token=token),
                         repository_id=repository_id)
    verify_merged = merged_gate(git=git)
    author = _release_author(git)
    clock = lambda: int(time.time())
    path = os.environ.get("PATH", "")
    candidate_root = operations / "candidate-transition"

    def release_by_tag(tag):
        release = github.get_release_by_tag("endaye/lmdj", tag)
        if release is None:
            return None
        return {"draft": release.draft, "id": release.id}

    def ledger_row(tag):
        intent = ledger.intent_for_tag(tag)
        if intent is None:
            return None
        return {"tag": intent.tag, "target_revision": intent.target_revision,
                "channel": intent.current_channel,
                "disposition": intent.disposition.value}

    publications = root / _PUBLICATIONS

    def release_id_for(tag):
        if not publications.is_file():
            return None
        try:
            document = json.loads(publications.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _fail("the publication record is unreadable")
        entries = document.get("entries") if type(document) is dict else None
        if type(entries) is not list:
            _fail("the publication record is not a document")
        matches = [entry.get("release_id") for entry in entries
                   if type(entry) is dict and entry.get("tag") == tag]
        if len(matches) > 1:
            _fail("the publication record names a tag more than once")
        return matches[0] if matches else None

    def candidate_enroll(req, drive):
        return enroll_candidate(
            request=req, drive=drive,
            **_candidate_arguments(context, root, operations, worktrees,
                                   repository_id, github, token, authorize,
                                   observe_main, review, verify_merged, clock,
                                   path, author))

    def pr_sequence(sequence_cls, branch_cls, pr_cls, sequence_root, kind):
        branch = branch_cls(sequence_root / "branch", sequence_root,
                            token=token, authorize=spec_authorize)
        pr = pr_cls(sequence_root / "pr", api=github.witness_pr_request,
                    authorize=spec_authorize,
                    review=lambda spec, row: review(kind, spec, row),
                    verify_merged=lambda spec, row, receipt: verify_merged(
                        kind, spec, row, receipt))
        return sequence_cls(sequence_root, branch=branch, pr=pr)

    def portal_freeze(build):
        def freeze(worktree_root):
            result = subprocess.run(
                ["bash", "scripts/docs-site.sh", "version", build, "canary"],
                cwd=worktree_root, capture_output=True, timeout=1800)
            if result.returncode != 0:
                _fail("the official Portal snapshot freeze failed")
        return freeze

    def intent_commit_for(spec):
        from .intent import IntentCommit

        return IntentCommit(worktrees / "intent", root, spec=spec,
                            freeze=portal_freeze(spec["product_build"]),
                            author_name=author[0], author_email=author[1])

    def intent_sequence_for(spec):
        from .intent_carrier import (
            IntentBranch,
            IntentPrSequence,
            IntentPullRequest,
        )

        return pr_sequence(IntentPrSequence, IntentBranch, IntentPullRequest,
                           operations / "intent-sequence", "intent")

    def changelog_commit_for(spec):
        from .changelog_step import ChangelogCommit

        return ChangelogCommit(worktrees / "changelog", root, spec=spec,
                               editorial=reviewed_changelog_editorial,
                               author_name=author[0], author_email=author[1])

    def changelog_sequence_for(spec):
        from .changelog_step import (
            ChangelogBranch,
            ChangelogPrSequence,
            ChangelogPullRequest,
        )

        return pr_sequence(ChangelogPrSequence, ChangelogBranch,
                           ChangelogPullRequest,
                           operations / "changelog-sequence", "changelog")

    def promotion_plan(spec):
        from .promotion import plan_promotion

        return plan_promotion(
            context, tag=spec["tag"], channel=spec["to_channel"],
            deployment_runs=_deployment_runs(root, git, request),
            evidence_paths=())

    def promotion_commit_for(spec):
        from .promotion_step import PromotionCommit

        return PromotionCommit(worktrees / "promotion", root, spec=spec,
                               plan=promotion_plan(spec),
                               main_tip=observe_main,
                               author_name=author[0], author_email=author[1])

    def promotion_sequence_for(spec):
        from .promotion_step import (
            PromotionBranch,
            PromotionPrSequence,
            PromotionPullRequest,
        )

        return pr_sequence(PromotionPrSequence, PromotionBranch,
                           PromotionPullRequest,
                           operations / "promotion-sequence", "promotion")

    def dispatch_for(step, workflow):
        def transition_for(spec, expected, bind):
            return _dispatch_transition(
                context, root, operations, step, workflow, spec, expected, bind,
                github, token, repository_id, spec_authorize, release_by_tag)
        return transition_for

    def record_transition_for(**inputs):
        return _published_record_transition(
            context, root, operations, worktrees,
            dict(inputs, main_revision=observe_main(),
                 control_revision=request["control_revision"]),
            github, token, spec_authorize, review, verify_merged, author, path)

    carriers = (
        DeferredCandidate(candidate_enroll),
        enroll_verification(
            candidate_root=candidate_root,
            journal_load=_batch_journal_load(root, token),
            consumer=batch_evidence_consumer(api_get=github.get_batch_evidence,
                                             git_root=root,
                                             policy=context.policy),
            fresh_receipts=_fresh_candidate_receipts(candidate_enroll,
                                                     verify_merged)),
        enroll_intent(candidate_root=candidate_root,
                      repository_id=repository_id,
                      batch_reference_for=_batch_reference_for(root, token),
                      commit_for=intent_commit_for,
                      sequence_for=intent_sequence_for),
        enroll_changelog(candidate_root=candidate_root, repository_id=repository_id,
                         ledger=ledger, main_revision=observe_main,
                         changelog_binding=lambda: reviewed_changelog_editorial(),
                         commit_for=changelog_commit_for,
                         sequence_for=changelog_sequence_for),
        enroll_prepared(root=root, candidate_root=candidate_root,
                        repository_id=repository_id, ledger=ledger,
                        prepare=_prepare_release(context),
                        local_tag_state=lambda tag: git.local_tag_state(tag),
                        signer_fingerprint=context.tag_signer_fingerprint),
        enroll_tag(root=root, candidate_root=candidate_root,
                   repository_id=repository_id, ledger=ledger,
                   push_tag=_push_tag(context),
                   local_tag_state=lambda tag: git.local_tag_state(tag),
                   remote_tag_state=lambda tag: git.remote_tag_state(tag),
                   signer_fingerprint=context.tag_signer_fingerprint),
        enroll_draft(root=root, candidate_root=candidate_root,
                     repository_id=repository_id, ledger=ledger,
                     create_draft=_create_draft(context),
                     release_by_tag=release_by_tag),
        enroll_publication(root=root, candidate_root=candidate_root,
                           repository_id=repository_id, ledger=ledger,
                           workflow_id=_workflow_id(github,
                                                    "publish-release.yml"),
                           producer_revision=_producer_revision(
                               root, git, "publish-release.yml",
                               request["control_revision"]),
                           release_by_tag=release_by_tag,
                           transition_for=dispatch_for("publication",
                                                       "publish-release.yml")),
        enroll_published_record(root=root, candidate_root=candidate_root,
                                repository_id=repository_id, ledger=ledger,
                                release_by_tag=release_by_tag,
                                transition_for=record_transition_for),
        enroll_changelog_site(candidate_root=candidate_root,
                              repository_id=repository_id, ledger=ledger,
                              fetch=site_fetch, site_base_url=_SITE_BASE_URL),
        enroll_deployment("runtime", candidate_root=candidate_root,
                          repository_id=repository_id, ledger=ledger,
                          workflow_id=_workflow_id(github,
                                                   "deploy-web-runtime-host.yml"),
                          producer_revision=_producer_revision(
                              root, git, "deploy-web-runtime-host.yml",
                              request["control_revision"]),
                          projection_for=lambda tag, step="runtime":
                              deployment_projection(root, tag, step),
                          transition_for=dispatch_for("runtime",
                                                      "deploy-web-runtime-host.yml")),
        enroll_deployment("creator", candidate_root=candidate_root,
                          repository_id=repository_id, ledger=ledger,
                          workflow_id=_workflow_id(github,
                                                   "deploy-creator-web.yml"),
                          producer_revision=_producer_revision(
                              root, git, "deploy-creator-web.yml",
                              request["control_revision"]),
                          projection_for=lambda tag, step="creator":
                              deployment_projection(root, tag, step),
                          transition_for=dispatch_for("creator",
                                                      "deploy-creator-web.yml")),
        enroll_promotion(candidate_root=candidate_root,
                         repository_id=repository_id, ledger=ledger,
                         main_revision=observe_main,
                         promotion_binding=_reviewed_promotion_binding(
                             context, policy, request, ledger, root, git),
                         commit_for=promotion_commit_for,
                         sequence_for=promotion_sequence_for),
        enroll_final(candidate_root=candidate_root, repository_id=repository_id,
                     ledger=ledger, fetch=site_fetch,
                     release_by_tag=release_by_tag, ledger_row=ledger_row,
                     release_id_for=release_id_for,
                     site_base_url=_SITE_BASE_URL),
    )
    if tuple(carrier.step for carrier in carriers) != ENROLLED_STEPS:
        _fail("the assembled carriers do not match the declared enrollment")
    return carriers


def _fresh_candidate_receipts(candidate_enroll, verify_merged):
    """The verification step's trusted receipts from the managed candidate."""
    def fresh_receipts(state):
        adapter = candidate_enroll(state["request"], drive=False)
        if adapter is None:
            raise EntryGateError("the candidate receipts are unavailable")
        operation = {"step": "candidate", "operation_id": canonical_sha256(
            {"request": state["request_digest"], "step": "candidate"})}
        return adapter.verified_candidate(state, operation)
    return fresh_receipts


def _reviewed_promotion_binding(context, policy, request, ledger, root, git):
    """The promotion binding from the reviewed plan over recorded run evidence."""
    from .promotion import plan_promotion

    def promotion_binding(tag):
        intent = ledger.intent_for_tag(tag)
        if intent is None:
            return None
        runs = _deployment_runs(root, git, request)
        if runs is None:
            return None
        target = policy.profiles["web-hosts-dev"]["target_channel"]
        plan = plan_promotion(context, tag=tag, channel=target,
                              deployment_runs=runs, evidence_paths=())
        return {"from_channel": plan.from_channel, "to_channel": plan.to_channel,
                "deployment_runs_sha256": canonical_sha256({"runs": [
                    {"host": run.host, "run_id": run.run_id,
                     "evidence_sha256": run.evidence_sha256}
                    for run in plan.deployment_runs]}),
                "attestation_sha256": canonical_sha256(
                    {"attestation": plan.attestation})}
    return promotion_binding


def _deployment_runs(root, git, request):
    """The verified deployment run identities from the request's own journal.

    Reads only the durable journal: each Host deploy step's verified evidence
    reference is the run URL its effect verifier produced. Returns the
    host → run_id mapping, or None while either Host's step is unverified —
    the promotion waits rather than planning without evidence. A read-only
    journal read never joins the writer lock, so this is safe mid-drive.
    """
    directory = release_journal_root(root, git)
    if not directory.is_dir():
        return None
    with RequestJournal(directory, writable=False) as journal:
        state = journal.read(request["id"])
    if state is None:
        return None
    transitions = state["transitions"]
    runs = {}
    for host, step in (("runtime", "runtime"), ("creator", "creator")):
        verified = [row for row in transitions
                    if type(row) is dict and row.get("step") == step
                    and row.get("status") == "verified"]
        if not verified:
            return None
        reference = verified[-1].get("evidence", {})
        reference = reference.get("reference") if type(reference) is dict else None
        matched = _RUN_URL.fullmatch(reference) if type(reference) is str else None
        if matched is None:
            _fail(f"the verified {step} deployment exposes no run identity")
        runs[host] = int(matched.group(1))
    return runs
