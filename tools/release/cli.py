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
from tools.release.git_repository import GitRepository, GitRepositoryError  # noqa: E402
from tools.release.github_api import GitHubApiError, GitHubClient  # noqa: E402
from tools.release.model import CANONICAL_BRANCH, CANONICAL_REPOSITORY, ReleaseModelError  # noqa: E402
from tools.release.openpgp import OpenPgpError, OpenPgpVerifier  # noqa: E402
from tools.release.prepare import (  # noqa: E402
    PrepareContext, PrepareError, default_profile_builder, load_authority_documents, prepare,
    read_product_snapshot_proof,
)
from tools.release.profiles import ProfileError, ProfileRuntime  # noqa: E402


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="scripts/release.sh")
    parser.add_argument("--repo-root", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    prepared = commands.add_parser("prepare")
    prepared.add_argument("tag")
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
        proof_reader=read_product_snapshot_proof,
        tag_signer_fingerprint=policy.product_fingerprint,
        checksum_signer_fingerprint=policy.checksum_fingerprint,
        authority_reader=authority_reader or load_authority_documents,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        options = parse_arguments(argv if argv is not None else sys.argv[1:])
        root = options.repo_root.expanduser().resolve(strict=True)
        context = build_context(root)
        prepared = prepare(options.tag, context)
    except SystemExit as error:
        return 0 if error.code == 0 else 64
    except (
        CommandError, GitHubApiError, GitRepositoryError, OpenPgpError, PrepareError,
        ProfileError, ReleaseModelError, OSError,
    ) as error:
        print(f"release prepare verification error: {error}", file=sys.stderr)
        return 2
    print(f"release plan sha256: {prepared.digest}")
    print(f"next command: scripts/release.sh push-tag {options.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
