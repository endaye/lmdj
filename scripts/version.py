#!/usr/bin/env python3

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


@dataclass(frozen=True, order=True)
class ProductVersion:
    milestone: int
    minor: int
    build: int
    patch: int

    def __post_init__(self) -> None:
        fields = {
            "milestone": self.milestone,
            "minor": self.minor,
            "build": self.build,
            "patch": self.patch,
        }
        for name, value in fields.items():
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{name} must be an integer")
        if self.milestone < 1:
            raise ValueError("milestone must be >= 1")
        if min(self.minor, self.build, self.patch) < 0:
            raise ValueError("minor, build, and patch must be >= 0")
        if self.build == 0 and self.patch != 0:
            raise ValueError("patch requires a non-zero build")

    def __str__(self) -> str:
        return (
            f"{self.milestone}.{self.minor}."
            f"{self.build}.{self.patch}"
        )

    def product_tag(self) -> str:
        return f"lmdj-v{self}"

    def display(self, channel: str, revision: str) -> str:
        if channel not in {"canary", "dev", "beta", "stable"}:
            raise ValueError(f"invalid channel: {channel}")
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("revision must be a full lowercase Git SHA")
        return f"{self} · {channel} · g{revision[:8]}"


def load_version(path: str | Path) -> ProductVersion:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    expected_keys = {
        "contract",
        "product",
        "milestone",
        "minor",
        "build",
        "patch",
    }
    if not isinstance(data, dict) or set(data) != expected_keys:
        raise ValueError("invalid product version document shape")
    if data["contract"] != "lmdj.product-version.v1":
        raise ValueError("unsupported product version contract")
    if data["product"] != "lmdj":
        raise ValueError("unexpected product id")
    return ProductVersion(
        data["milestone"],
        data["minor"],
        data["build"],
        data["patch"],
    )


def _load_object(path: str | Path, label: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data


def _git_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    revision = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("git revision must be a full lowercase SHA")
    return revision


def _verify_assembly(
    version: ProductVersion,
    assembly_path: str | Path,
) -> None:
    assembly = _load_object(assembly_path, "assembly")
    product = assembly.get("product")
    if not isinstance(product, dict):
        raise ValueError("assembly.product must be an object")
    if product.get("id") != "lmdj":
        raise ValueError("assembly product id does not match lmdj")
    if product.get("version") != str(version):
        raise ValueError(
            "assembly product version does not match product version"
        )


def _verify_lock(
    version: ProductVersion,
    lock_path: str | Path,
) -> None:
    lock = _load_object(lock_path, "assembly lock")
    product = lock.get("product")
    if not isinstance(product, dict):
        raise ValueError("assembly lock product must be an object")
    if product.get("id") != "lmdj" or product.get("version") != str(version):
        raise ValueError("assembly lock product identity does not match")
    assembly_sha256 = lock.get("assembly_sha256")
    if not isinstance(assembly_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", assembly_sha256
    ):
        raise ValueError("assembly lock requires a lowercase assembly SHA-256")
    for field in ("modules", "contracts", "providers"):
        value = lock.get(field)
        if not isinstance(value, (dict, list)):
            raise ValueError(f"assembly lock {field} must be a collection")


def verify(
    version_file: str | Path,
    assembly_path: str | Path | None = None,
    lock_path: str | Path | None = None,
) -> ProductVersion:
    version = load_version(version_file)
    _git_revision()
    if assembly_path is not None:
        _verify_assembly(version, assembly_path)
    if lock_path is not None:
        _verify_lock(version, lock_path)
    return version


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect and verify LMDJ Product Build identity."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    current = subparsers.add_parser("current")
    current.add_argument("--version-file", required=True)
    current.add_argument(
        "--channel",
        choices=("canary", "dev", "beta", "stable"),
        required=True,
    )
    current.add_argument("--revision", required=True)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--version-file", required=True)
    verify_parser.add_argument("--assembly")
    verify_parser.add_argument("--lock")

    tag_name = subparsers.add_parser("tag-name")
    tag_name.add_argument("--version-file", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "current":
            version = load_version(args.version_file)
            print(version.display(args.channel, args.revision))
        elif args.command == "verify":
            version = verify(
                args.version_file,
                assembly_path=args.assembly,
                lock_path=args.lock,
            )
            print(f"version verification: PASS ({version})")
        elif args.command == "tag-name":
            print(load_version(args.version_file).product_tag())
        else:
            parser.error(f"unknown command: {args.command}")
    except (
        json.JSONDecodeError,
        OSError,
        subprocess.CalledProcessError,
        ValueError,
    ) as error:
        print(f"version error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
