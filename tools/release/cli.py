#!/usr/bin/env python3
"""Stable local release command entry point."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.release.git_repository import GitRepository  # noqa: E402
from tools.release.github_api import GitHubClient  # noqa: E402
from tools.release.model import ReleaseModelError, load_ledger, load_policy  # noqa: E402
from tools.release.openpgp import OpenPgpVerifier  # noqa: E402
from tools.release.prepare import (  # noqa: E402
    PrepareContext, PrepareError, default_profile_builder, prepare, unavailable_proof_reader,
)
from tools.release.profiles import ProfileRuntime  # noqa: E402


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="scripts/release.sh")
    parser.add_argument("--repo-root", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    prepared = commands.add_parser("prepare")
    prepared.add_argument("tag")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        options = parse_arguments(argv or sys.argv[1:])
        root = options.repo_root.expanduser().resolve(strict=True)
        policy = load_policy(root / "tools/release/policy.json")
        ledger = load_ledger(root / "docs/release-evidence/release-intents.json", policy)
        home = Path(os.environ.get("GNUPGHOME", Path.home() / ".gnupg"))
        runtime = ProfileRuntime(
            runner=GitRepository(root).runner,
            checksum_verifier=OpenPgpVerifier(),
            checksum_home=home,
            checksum_fingerprint=policy.checksum_fingerprint,
        )
        context = PrepareContext(
            repo_root=root,
            policy=policy,
            ledger=ledger,
            git=GitRepository(root, runner=runtime.runner),
            github=GitHubClient(),
            profile_builder=default_profile_builder(runtime),
            proof_reader=unavailable_proof_reader,
            tag_signer_fingerprint=policy.product_fingerprint,
            checksum_signer_fingerprint=policy.checksum_fingerprint,
        )
        prepared = prepare(options.tag, context)
    except argparse.ArgumentError:
        return 64
    except SystemExit as error:
        return int(error.code) if isinstance(error.code, int) else 64
    except (PrepareError, ReleaseModelError, OSError) as error:
        print(f"release prepare verification error: {error}", file=sys.stderr)
        return 2
    print(f"release plan sha256: {prepared.digest}")
    print(f"next command: scripts/release.sh push-tag {options.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
