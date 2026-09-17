#!/usr/bin/env python3
"""Stable local release command entry point."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Callable


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.release.commands import CommandError, CommandRunner  # noqa: E402
from tools.release.audit import (  # noqa: E402
    AuditContext,
    audit,
    format_report,
    write_report,
)
from tools.release.git_repository import GitRepository, GitRepositoryError  # noqa: E402
from tools.release.hydrate import (  # noqa: E402
    HydrateError,
    format_hydration,
    hydrate_release_intent_targets,
)
from tools.release.github_api import GitHubApiError, GitHubClient  # noqa: E402
from tools.release.model import CANONICAL_BRANCH, CANONICAL_REPOSITORY, ReleaseModelError, canonical_json, canonical_sha256  # noqa: E402
from tools.release.publication import PublicationError, collect_publication  # noqa: E402
from tools.release.publication_evidence import collect_publication_patch  # noqa: E402
from tools.release.changelog import ChangelogError  # noqa: E402
from tools.release.openpgp import OpenPgpError, OpenPgpVerifier  # noqa: E402
from tools.release.orchestration import (  # noqa: E402
    JournalError,
    RequestJournal,
    STEPS,
    validate_request,
)
from tools.release.orchestration_backend import ReleaseBackend  # noqa: E402
from tools.release.orchestration_driver import ReleaseDriver  # noqa: E402
from tools.release.orchestration_policy import (  # noqa: E402
    OrchestrationPolicyError,
    load_orchestration_policy,
)
from tools.release.entry_composition import compose_candidate  # noqa: E402
from tools.release.prepare import (  # noqa: E402
    PrepareContext, PrepareError, default_profile_builder, default_profile_verifier,
    load_authority_documents, prepare,
    read_product_snapshot_proof,
)
from tools.release.profiles import ProfileError, ProfileRuntime  # noqa: E402
from tools.release.rehearsal import (  # noqa: E402
    RehearsalContext,
    RehearsalError,
    cleanup_rehearsal,
    create_rehearsal_draft,
    load_rehearsal_state,
    prepare_rehearsal,
    push_rehearsal_tag,
)
from tools.release.promotion import (  # noqa: E402
    PromotionError,
    apply_promotion,
    parse_deployment_run_arguments,
    plan_promotion,
)
from tools.release.transitions import (  # noqa: E402
    TransitionError,
    create_draft,
    publish_draft,
    push_tag,
    verify_draft,
    verify_published,
)


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="scripts/release.sh")
    parser.add_argument("--repo-root", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    prepared = commands.add_parser("prepare")
    prepared.add_argument("tag")
    pushed = commands.add_parser("push-tag")
    pushed.add_argument("tag")
    drafted = commands.add_parser("create-draft")
    drafted.add_argument("tag")
    verified = commands.add_parser("verify-draft")
    verified.add_argument("tag")
    verified.add_argument("release_id", type=int)
    verified.add_argument("plan_sha256")
    published_verified = commands.add_parser("verify-published")
    published_verified.add_argument("tag")
    published_verified.add_argument("release_id", type=int)
    published_verified.add_argument("plan_sha256")
    recorded = commands.add_parser("publication-record")
    recorded.add_argument("tag")
    recorded.add_argument("release_id", type=int)
    recorded.add_argument("plan_sha256")
    evidence = commands.add_parser("publication-patch")
    evidence.add_argument("tag")
    evidence.add_argument("release_id", type=int)
    evidence.add_argument("plan_sha256")
    published = commands.add_parser("publish-draft")
    published.add_argument("tag")
    published.add_argument("release_id", type=int)
    published.add_argument("plan_sha256")
    promoted = commands.add_parser("promote")
    promoted.add_argument("tag")
    promoted.add_argument("channel")
    promoted.add_argument(
        "--deployment-run", action="append", default=[], metavar="HOST=RUN_ID",
        help="one completed Host deployment run per profile host",
    )
    promoted.add_argument(
        "--evidence", action="append", default=[], metavar="PATH",
        help="tracked acceptance document under docs/release-evidence/ or docs/quality/",
    )
    rehearsal = commands.add_parser("rehearsal")
    rehearsal_commands = rehearsal.add_subparsers(dest="rehearsal_command", required=True)
    for name in ("prepare", "push-tag", "create-draft", "cleanup"):
        selected = rehearsal_commands.add_parser(name)
        selected.add_argument("tag")
    commands.add_parser("hydrate")
    started = commands.add_parser("run")
    started.add_argument(
        "--authority", required=True, metavar="REF",
        help="opaque reference to the independently authenticated authorization record",
    )
    started.add_argument("--tag", help="exact Product tag for an already-frozen release scope")
    started.add_argument(
        "--base-revision", metavar="SHA",
        help="frozen main input revision; defaults to the canonical main revision",
    )
    continued = commands.add_parser("resume")
    continued.add_argument("request_id")
    reported = commands.add_parser("status")
    reported.add_argument("request_id", nargs="?")
    audited = commands.add_parser("audit")
    mode = audited.add_mutually_exclusive_group(required=True)
    mode.add_argument("--local", action="store_true")
    mode.add_argument("--remote", action="store_true")
    audited.add_argument("--tag")
    audited.add_argument("--json", type=Path)
    return parser.parse_args(argv)


def build_context(
    root: Path,
    *,
    git: GitRepository | object | None = None,
    github: GitHubClient | object | None = None,
    authority_reader: Callable | None = None,
) -> PrepareContext:
    """Build the shipped prepare context from freshly fetched canonical state."""
    selected_git = git or GitRepository(root)
    runner = getattr(selected_git, "runner", CommandRunner())
    selected_github = github or _authenticated_github_client(runner)
    selected_git.fetch_authority(CANONICAL_REPOSITORY, CANONICAL_BRANCH)
    with selected_git.detached_worktree(selected_git.main_revision()) as authority_tree:
        policy, ledger = (authority_reader or load_authority_documents)(authority_tree)
    home = Path.home() / ".gnupg-lmdj-release"
    runtime = ProfileRuntime(
        runner=runner,
        checksum_verifier=OpenPgpVerifier(),
        checksum_home=home,
        checksum_fingerprint=policy.checksum_fingerprint,
    )
    return PrepareContext(
        repo_root=root,
        policy=policy,
        ledger=ledger,
        git=selected_git,
        github=selected_github,
        profile_builder=default_profile_builder(runtime),
        profile_verifier=default_profile_verifier(runtime),
        proof_reader=read_product_snapshot_proof,
        tag_signer_fingerprint=policy.product_fingerprint,
        checksum_signer_fingerprint=policy.checksum_fingerprint,
        authority_reader=authority_reader or load_authority_documents,
    )


def build_audit_context(root: Path, *, remote: bool = False) -> AuditContext:
    """Build an audit context without contacting remote state."""
    policy, ledger = load_authority_documents(root)
    selected_git = GitRepository(root)
    selected_github = (
        _authenticated_github_client(selected_git.runner) if remote else GitHubClient()
    )
    return _audit_context_for_authority(
        root, policy, ledger, selected_git, selected_github,
        authority_reader=load_authority_documents,
    )


ORCHESTRATION_POLICY_PATH = Path("tools/release/orchestration-policy.json")


def release_journal_root(root: Path, git) -> Path:
    """The request journal lives beside the repository's own Git directory."""
    from tools.release.entry_composition import release_journal_root as impl

    return impl(root, git)


def release_carriers(context: PrepareContext, policy, request) -> tuple:
    """Step carriers enrolled for this scope, from the trusted composition.

    The twelve enrolled steps assemble as lazy request-bound wrappers; the
    `prepared` and `tag` steps stay unenrolled while their spec freezing is
    unsettled (#1404), and `run`/`resume` refuse a scope with an unowned step
    rather than half-driving it. Assembly performs no drives and no batch or
    site reads.
    """
    from tools.release.entry_composition import compose_carriers

    return compose_carriers(context, policy, request)


def _resume_request(root: Path, git, request_id: str):
    """The frozen request for a resume, read-only; None when the journal has none."""
    directory = release_journal_root(root, git)
    if not directory.is_dir():
        return None
    try:
        with RequestJournal(directory, writable=False) as journal:
            alias = journal.read_alias(request_id)
            if alias is not None:
                return alias["request"]
            state = journal.read(request_id)
    except JournalError:
        # The driver's own resume path reports the unreadable journal.
        return None
    return state["request"] if state is not None else None


def build_orchestration_policy(root: Path, context: PrepareContext):
    return load_orchestration_policy(root / ORCHESTRATION_POLICY_PATH, context.policy)


def build_request(
    context: PrepareContext,
    policy,
    *,
    authority_ref: str,
    tag: str | None = None,
    base_revision: str | None = None,
) -> dict:
    """Freeze one release request from the authenticated canonical control."""
    control = context.git.main_revision()
    base = base_revision or control
    # A frozen base revision is part of the immutable request identity, so it is
    # checked for canonical reachability before it is frozen, not after.
    if not context.git.is_main_ancestor(base):
        raise CommandError(
            "release base revision is not reachable canonical history",
            detail=f"{base} (remedy: use a merged main revision or omit --base-revision)",
        )
    scope = {
        "repository": context.policy.repository,
        "actor_id": context.github.get_authenticated_actor(),
        "authority_ref": authority_ref,
        "policy_digest": policy.digest,
        "control_revision": control,
        "base_revision": base,
        "mode": "tag" if tag else "new",
        "requested_tag": tag,
    }
    request = {"id": "release-" + canonical_sha256(scope)[:16], **scope}
    validate_request(request)
    return request


def format_request_status(root: Path, git, request_id: str | None = None) -> str:
    """Report the local request journal: progress record, never far-side proof."""
    directory = release_journal_root(root, git)
    if not directory.is_dir():
        # No request has ever been created here; reading must not create one.
        return "release request journal: no requests\n"
    report = []
    with RequestJournal(directory, writable=False) as journal:
        if request_id is not None:
            state = journal.read(request_id)
            if state is None:
                raise JournalError(
                    "why: request is missing; remedy: use the request ID printed by `run`"
                )
            states = [state]
        else:
            states = []
            for name in sorted(os.listdir(directory)):
                if not name.endswith(".json"):
                    continue
                try:
                    state = journal.read(name[:-5])
                except JournalError as error:
                    # A listing reports what it can read and names the rest; the
                    # named-request form below is what fails closed.
                    report.append(f"unreadable journal entry: {name} ({error})\n")
                    continue
                if state is None:
                    continue
                states.append(state)
        for state in states:
            records = state["transitions"]
            verified = [record["step"] for record in records if record["status"] == "verified"]
            # The next step is the first record that is not verified: a verified
            # count indexes the wrong step if the journal is not a verified prefix.
            outstanding = next(
                (record["step"] for record in records if record["status"] != "verified"), None
            )
            unresolved = bool(records) and records[-1]["status"] == "intent"
            report.append(
                f"release request: {state['request']['id']}\n"
                f"  scope: mode={state['request']['mode']} "
                f"tag={state['request']['requested_tag'] or '-'}\n"
                f"  verified: {len(verified)}/{len(STEPS)}\n"
                f"  step: {outstanding or '-'}\n"
                f"  outstanding intent: {outstanding if unresolved else '-'}\n"
            )
    if not report:
        return "release request journal: no requests\n"
    return "source: local request journal; run `resume` to re-verify against live state\n" + "".join(report)


def _authenticated_github_client(runner: CommandRunner) -> GitHubClient:
    """Use workflow credentials when present, otherwise the logged-in gh identity."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        token = runner.run(("gh", "auth", "token")).stdout.strip()
    if not token:
        raise GitHubApiError("GitHub authentication is unavailable")
    return GitHubClient(token=token)


def _audit_context_for_authority(
    root: Path,
    policy,
    ledger,
    selected_git,
    selected_github,
    *,
    authority_reader=None,
) -> AuditContext:
    """Rebuild every path/key-dependent audit verifier for one authority tree."""
    runner = selected_git.runner
    home = Path.home() / ".gnupg-lmdj-release"
    runtime = ProfileRuntime(
        runner=runner,
        checksum_verifier=OpenPgpVerifier(),
        checksum_home=home,
        checksum_fingerprint=policy.checksum_fingerprint,
    )
    return AuditContext(
        repo_root=root,
        policy=policy,
        ledger=ledger,
        git=selected_git,
        github=selected_github,
        profile_verifier=default_profile_verifier(runtime),
        proof_reader=read_product_snapshot_proof,
        tag_signer_fingerprint=policy.product_fingerprint,
        checksum_signer_fingerprint=policy.checksum_fingerprint,
        trust_anchor_verifier=lambda authority_root, canonical_policy: (
            _verify_audit_trust_anchors(
                authority_root, canonical_policy, OpenPgpVerifier(runner=runner),
            )
        ),
        authority_reader=authority_reader,
        authority_context_builder=lambda authority_root, canonical_policy, canonical_ledger: (
            _audit_context_for_authority(
                authority_root, canonical_policy, canonical_ledger,
                selected_git, selected_github,
            )
        ),
    )


def _verify_audit_trust_anchors(root: Path, policy, verifier: OpenPgpVerifier) -> None:
    """Import each canonical public key alone and prove its primary role anchor."""
    import tempfile

    for name, fingerprint in (
        ("lmdj-product.asc", policy.product_fingerprint),
        ("lmdj-release-checksum.asc", policy.checksum_fingerprint),
    ):
        with tempfile.TemporaryDirectory(prefix="lmdj-release-audit-key-") as directory:
            home = Path(directory)
            home.chmod(0o700)
            verifier.import_public_key(
                home, root / ".github/release-signing-keys" / name, fingerprint,
            )


def main(argv: list[str] | None = None) -> int:
    try:
        options = parse_arguments(argv if argv is not None else sys.argv[1:])
        root = options.repo_root.expanduser().resolve(strict=True)
        if options.command == "hydrate":
            # The only subcommand that writes to the local object store on
            # purpose. It stays separate from `audit` because the pipeline
            # design's read-only audit contract forbids the audit creating Git
            # state, and `git fetch` creates objects. Pitfall:
            # .agents/pitfalls/release-intent-target-reachability.md
            print(format_hydration(hydrate_release_intent_targets(root)))
            return 0
        if options.command == "audit":
            report = audit(
                build_audit_context(root, remote=options.remote),
                remote=options.remote,
                tag=options.tag,
            )
            if options.json is not None:
                destination = options.json if options.json.is_absolute() else root / options.json
                write_report(report, destination)
            print(format_report(report))
            return report.exit_code
        if options.command == "promote":
            report = audit(build_audit_context(root, remote=True), remote=True, tag=options.tag)
            print(format_report(report))
            if report.exit_code != 0:
                raise PromotionError("exact-tag remote audit must pass before promotion")
            context = build_context(root)
            plan = plan_promotion(
                context,
                tag=options.tag,
                channel=options.channel,
                deployment_runs=parse_deployment_run_arguments(options.deployment_run),
                evidence_paths=options.evidence,
            )
            written = apply_promotion(root, plan, context.policy)
            print(f"promotion recorded: {plan.tag} {plan.from_channel} -> {plan.to_channel}")
            print(f"ledger: {written.ledger_path}")
            print(f"evidence document: {written.evidence_document}")
            print("next step: commit both files as a docs Pull Request through the Integration Queue")
            return 0
        if options.command == "status":
            print(format_request_status(root, GitRepository(root), options.request_id), end="")
            return 0
        context = build_context(root)
        if options.command in ("run", "resume"):
            policy = build_orchestration_policy(root, context)
            request = (
                build_request(
                    context, policy, authority_ref=options.authority,
                    tag=options.tag, base_revision=options.base_revision,
                )
                if options.command == "run"
                else _resume_request(root, context.git, options.request_id)
            )
            if request is None:
                # Let the driver report the missing request from its own
                # journal evidence rather than composing against nothing.
                driver = ReleaseDriver(
                    release_journal_root(root, context.git), policy,
                    ReleaseBackend(context.git, context.github, carriers=()))
                result = driver.resume(options.request_id)
                _print_drive_result(result)
                return 0 if result.status == "complete" else 2
            carriers = release_carriers(context, policy, request)
            backend = ReleaseBackend(context.git, context.github, carriers=carriers)
            unowned = backend.missing(STEPS)
            if unowned:
                # Refuse before the request is created: an unowned step is never
                # reported absent, and no later transition may run without it.
                raise CommandError(
                    "release scope has steps without an enrolled carrier",
                    detail=", ".join(unowned),
                )
            candidate = compose_candidate(context, policy, request)
            driver = ReleaseDriver(release_journal_root(root, context.git), policy,
                                   backend, candidate=candidate)
            result = (
                driver.run(request)
                if options.command == "run" else driver.resume(options.request_id)
            )
            _print_drive_result(result)
            return 0 if result.status == "complete" else 2
        if options.command == "prepare":
            prepared = prepare(options.tag, context)
            print(f"release plan sha256: {prepared.digest}")
            print(f"next command: scripts/release.sh push-tag {options.tag}")
        elif options.command == "push-tag":
            result = push_tag(options.tag, context)
            print(f"remote tag status: {result.status}")
            print(f"release plan sha256: {result.plan_sha256}")
        elif options.command == "create-draft":
            result = create_draft(options.tag, context)
            _print_release_result(result)
        elif options.command == "verify-draft":
            result = verify_draft(
                options.tag, options.release_id, options.plan_sha256, context,
            )
            _print_release_result(result)
        elif options.command == "verify-published":
            result = verify_published(
                options.tag, options.release_id, options.plan_sha256, context,
            )
            _print_release_result(result)
        elif options.command == "publication-record":
            record = collect_publication(options.tag, options.release_id, options.plan_sha256, context)
            print(canonical_json(record).decode("utf-8"), end="")
        elif options.command == "publication-patch":
            print(collect_publication_patch(options.tag, options.release_id, options.plan_sha256, context), end="")
        elif options.command == "publish-draft":
            result = publish_draft(
                options.tag, options.release_id, options.plan_sha256, context,
            )
            _print_release_result(result)
        else:
            _run_rehearsal(options, root, context)
    except SystemExit as error:
        return 0 if error.code == 0 else 64
    except (
        CommandError, GitHubApiError, GitRepositoryError, HydrateError, JournalError,
        OpenPgpError, OrchestrationPolicyError,
        PrepareError, ProfileError, PromotionError, RehearsalError, ReleaseModelError,
        TransitionError, PublicationError, ChangelogError, OSError,
    ) as error:
        detail = error.detail if isinstance(error, (CommandError, HydrateError)) else ""
        suffix = f": {detail}" if detail else ""
        print(f"release verification error: {error}{suffix}", file=sys.stderr)
        return 2
    return 0


def _print_drive_result(result) -> None:
    print(f"release request: {result.request_id}")
    print(f"request status: {result.status}")
    print(f"step: {result.step or '-'}")
    print(f"verified steps: {len(result.verified_steps)}/{len(STEPS)}")
    if result.status != "complete":
        print("next step: reconcile the reported step, then resume this same request ID")


def _print_release_result(result) -> None:
    print(f"release status: {result.status}")
    print(f"release ID: {result.release_id}")
    print(f"release URL: {result.release_url}")
    print(f"release plan sha256: {result.plan_sha256}")


def _run_rehearsal(options: argparse.Namespace, root: Path, context: PrepareContext) -> None:
    production_keys = {
        context.policy.product_fingerprint, context.policy.checksum_fingerprint,
    }
    selected = RehearsalContext(
        root, context.policy.repository, context.git, context.github,
        frozenset(production_keys),
    )
    if options.rehearsal_command == "prepare":
        state = prepare_rehearsal(
            options.tag, selected, product_fingerprints=production_keys,
        )
    elif options.rehearsal_command == "push-tag":
        state = push_rehearsal_tag(
            options.tag, selected, product_fingerprints=production_keys,
        )
    elif options.rehearsal_command == "create-draft":
        state = create_rehearsal_draft(
            load_rehearsal_state(options.tag, root), selected,
            product_fingerprints=production_keys,
        )
    else:
        state = load_rehearsal_state(options.tag, root)
        cleanup_rehearsal(state, selected)
    print(f"rehearsal status: {options.rehearsal_command}")
    print(f"rehearsal tag: {state.tag}")
    if state.release_id is not None:
        print(f"rehearsal Release ID: {state.release_id}")


if __name__ == "__main__":
    raise SystemExit(main())
