#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.release.web_host_bundle import (  # noqa: E402
    BundleError,
    StagedBundle,
    WebHostReleaseSpec,
    canonical_json,
    stage_host_bundle,
)


CREATOR_WEB_SPEC = WebHostReleaseSpec(
    host_id="creator-web",
    script="scripts/creator-web.sh",
    dist_relative="build/web/creator/dist",
    module_relative="apps/creator-web/module.json",
    archive_prefix="lmdj-creator-web",
    verifier_relative="apps/creator-web/tools/package.py",
)


class UsageError(RuntimeError):
    pass


class UsageParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(f"release bundle usage error: {message}", file=sys.stderr)
        raise UsageError(message)


def stage_release_bundle(
    *,
    repo_root: Path,
    archive_path: Path,
    checksum_path: Path,
    signature_path: Path,
    checksum_public_key_path: Path,
    trusted_checksum_fingerprint: str,
    output_root: Path,
    expected_product_build: str,
    expected_host_version: str,
    verifier: Callable[[Path, Path], None] | None = None,
    checksum_authorizer: Callable[[Path, Path, Path, str], None] | None = None,
    gpg_program: str = "gpg",
) -> StagedBundle:
    return stage_host_bundle(
        spec=CREATOR_WEB_SPEC,
        repo_root=repo_root,
        archive_path=archive_path,
        checksum_path=checksum_path,
        signature_path=signature_path,
        checksum_public_key_path=checksum_public_key_path,
        trusted_checksum_fingerprint=trusted_checksum_fingerprint,
        output_root=output_root,
        expected_product_build=expected_product_build,
        expected_host_version=expected_host_version,
        verifier=verifier,
        checksum_authorizer=checksum_authorizer,
        gpg_program=gpg_program,
    )


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = UsageParser(description="Validate and stage a released Creator Web bundle")
    commands = parser.add_subparsers(
        dest="command",
        required=True,
        parser_class=UsageParser,
    )
    stage = commands.add_parser("stage")
    stage.add_argument("--repo-root", required=True, type=Path)
    stage.add_argument("--archive", required=True, type=Path)
    stage.add_argument("--checksum", required=True, type=Path)
    stage.add_argument("--checksum-signature", required=True, type=Path)
    stage.add_argument("--checksum-public-key", required=True, type=Path)
    stage.add_argument("--trusted-checksum-fingerprint", required=True)
    stage.add_argument("--gpg-program", default="gpg")
    stage.add_argument("--output-root", required=True, type=Path)
    stage.add_argument("--expected-product-build", required=True)
    stage.add_argument("--expected-host-version", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    try:
        options = parse_arguments(arguments)
        bundle = stage_release_bundle(
            repo_root=options.repo_root,
            archive_path=options.archive,
            checksum_path=options.checksum,
            signature_path=options.checksum_signature,
            checksum_public_key_path=options.checksum_public_key,
            trusted_checksum_fingerprint=options.trusted_checksum_fingerprint,
            output_root=options.output_root,
            expected_product_build=options.expected_product_build,
            expected_host_version=options.expected_host_version,
            gpg_program=options.gpg_program,
        )
    except UsageError:
        return 64
    except (BundleError, OSError) as error:
        print(f"Creator Web deployment bundle error: {error}", file=sys.stderr)
        return 2
    print(canonical_json(bundle))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
