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
from tools.release.github_api import GitHubApiError, GitHubClient  # noqa: E402
from tools.release.model import CANONICAL_BRANCH, CANONICAL_REPOSITORY, ReleaseModelError  # noqa: E402
from tools.release.openpgp import OpenPgpError, OpenPgpVerifier  # noqa: E402
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
from tools.release.transitions import (  # noqa: E402
    TransitionError,
    create_draft,
    publish_draft,
    push_tag,
    verify_draft,
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
    published = commands.add_parser("publish-draft")
    published.add_argument("tag")
    published.add_argument("release_id", type=int)
    published.add_argument("plan_sha256")
    rehearsal = commands.add_parser("rehearsal")
    rehearsal_commands = rehearsal.add_subparsers(dest="rehearsal_command", required=True)
    for name in ("prepare", "push-tag", "create-draft", "cleanup"):
        selected = rehearsal_commands.add_parser(name)
        selected.add_argument("tag")
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
    selected_github = github or GitHubClient()
    selected_git.fetch_authority(CANONICAL_REPOSITORY, CANONICAL_BRANCH)
    with selected_git.detached_worktree(selected_git.main_revision()) as authority_tree:
        policy, ledger = (authority_reader or load_authority_documents)(authority_tree)
    runner = getattr(selected_git, "runner", CommandRunner())
    home = Path(os.environ.get("GNUPGHOME", Path.home() / ".gnupg"))
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


def build_audit_context(root: Path) -> AuditContext:
    """Build an audit context without contacting remote state."""
    policy, ledger = load_authority_documents(root)
    selected_git = GitRepository(root)
    selected_github = GitHubClient()
    return _audit_context_for_authority(
        root, policy, ledger, selected_git, selected_github,
        authority_reader=load_authority_documents,
    )


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
    home = Path(os.environ.get("GNUPGHOME", Path.home() / ".gnupg"))
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
        if options.command == "audit":
            report = audit(
                build_audit_context(root), remote=options.remote, tag=options.tag,
            )
            if options.json is not None:
                destination = options.json if options.json.is_absolute() else root / options.json
                write_report(report, destination)
            print(format_report(report))
            return report.exit_code
        context = build_context(root)
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
        CommandError, GitHubApiError, GitRepositoryError, OpenPgpError, PrepareError,
        ProfileError, RehearsalError, ReleaseModelError, TransitionError, OSError,
    ) as error:
        detail = error.detail if isinstance(error, CommandError) else ""
        suffix = f": {detail}" if detail else ""
        print(f"release verification error: {error}{suffix}", file=sys.stderr)
        return 2
    return 0


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
