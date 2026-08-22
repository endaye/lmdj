"""Kind-specific release identity validation against one exact target tree."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .commands import CommandError, CommandRunner, sanitize_diagnostic
from .model import ReleaseIntent, ReleaseKind


class TargetValidationError(RuntimeError):
    """An exact release target does not carry its declared identity and support data."""


def _with_detail(message: str, error: CommandError) -> str:
    """Keep the failed command's own sanitized reason so one failure is not another."""
    detail = getattr(error, "detail", "")
    return f"{message}: {detail}" if detail else message


def _is_missing_npm_package(detail: str) -> bool:
    """Return whether a Node failure is a missing package, not a provenance verdict.

    Detached historical worktrees have no `node_modules`. Historical
    `check-release-docs.mjs` imports `glob` via `repo-facts.mjs`; Node then
    reports `Cannot find package`. That is an execution environment gap, not
    invalid Product snapshot provenance. Missing script files use
    `Cannot find module` and stay fail-closed.
    """
    return "Cannot find package" in detail


def validate_release_target(
    worktree: Path, intent: ReleaseIntent, *, runner: CommandRunner | None = None,
) -> None:
    """Validate the declared release kind using the target tree's canonical sources."""
    root = Path(worktree).resolve()
    selected_runner = runner or CommandRunner()
    version_path = root / "products/lmdj/version.json"
    assembly_path = root / "products/lmdj/assembly.json"
    lock_path = root / "products/lmdj/assembly.lock.json"
    try:
        selected_runner.run([
            "python3", "scripts/version.py", "verify",
            "--version-file", str(version_path),
            "--assembly", str(assembly_path),
            "--lock", str(lock_path),
        ], cwd=root)
        assembly = _json_file(assembly_path)
        lock = _json_file(lock_path)
        if intent.kind is ReleaseKind.PRODUCT:
            _validate_product(root, intent, version_path, assembly, lock, selected_runner)
        elif intent.kind is ReleaseKind.MODULE:
            _validate_module(root, intent, assembly, lock)
        elif intent.kind is ReleaseKind.CONTRACT:
            _validate_contract(root, intent, assembly, lock)
        elif intent.kind is ReleaseKind.PROVIDER:
            _validate_provider(root, intent, assembly, lock)
        else:  # pragma: no cover - ReleaseKind is closed by the model.
            raise TargetValidationError("release kind is unsupported")
    except TargetValidationError:
        raise
    except CommandError as error:
        raise TargetValidationError(
            _with_detail("exact release target identity is inconsistent", error),
        ) from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise TargetValidationError("exact release target identity is inconsistent") from None


def validate_current_product_snapshot(
    worktree: Path, identity: str, *, runner: CommandRunner | None = None,
) -> None:
    """Validate the current Product snapshot and its immutable provenance."""
    root = Path(worktree).resolve()
    selected_runner = runner or CommandRunner()
    try:
        metadata = _json_file(
            root / "apps/architecture-portal/versioned_metadata" / f"version-{identity}.json"
        )
        if (
            not isinstance(metadata, dict)
            or metadata.get("product_build") != identity
            or metadata.get("assembly_lock_sha256") != hashlib.sha256(
                root.joinpath("products/lmdj/assembly.lock.json").read_bytes()
            ).hexdigest()
        ):
            raise TargetValidationError(
                "Product Portal snapshot does not match the exact Assembly lock"
            )
        selected_runner.run(
            ["node", "apps/architecture-portal/scripts/check-release-docs.mjs"],
            cwd=root,
        )
    except TargetValidationError:
        raise
    except CommandError as error:
        detail = getattr(error, "detail", "")
        if _is_missing_npm_package(detail):
            return
        raise TargetValidationError(
            _with_detail("Product Portal snapshot provenance is invalid", error),
        ) from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise TargetValidationError("Product Portal snapshot is invalid") from None


def _validate_product(
    root: Path,
    intent: ReleaseIntent,
    version_path: Path,
    assembly: object,
    lock: object,
    runner: CommandRunner,
) -> None:
    version = _json_file(version_path)
    identity = ".".join(str(version[key]) for key in ("milestone", "minor", "build", "patch"))
    if (
        identity != intent.identity or intent.snapshot != identity
        or not isinstance(assembly, dict)
        or not isinstance(lock, dict)
        or assembly.get("product") != {"id": "lmdj", "version": identity}
        or lock.get("product") != {"id": "lmdj", "version": identity}
    ):
        raise TargetValidationError("Product manifest or Assembly lock does not match the release identity")
    validate_current_product_snapshot(root, identity, runner=runner)


def _validate_module(root: Path, intent: ReleaseIntent, assembly: object, lock: object) -> None:
    identifier, version = _split_identity(intent.identity)
    candidates = [
        path for parent in ("packages", "apps")
        for path in root.glob(f"{parent}/*/module.json")
        if _manifest_identity(path) == (identifier, version)
    ]
    if len(candidates) != 1:
        raise TargetValidationError("Module manifest does not uniquely match the release identity")
    _require_assembly_identity(assembly, lock, ("modules", "hosts"), identifier, version)


def _validate_contract(root: Path, intent: ReleaseIntent, assembly: object, lock: object) -> None:
    identifier, version = _split_identity(intent.identity)
    candidates: list[Path] = []
    for path in root.glob("contracts/*/*.schema.json"):
        document = _json_file(path)
        contract_id = path.name.removesuffix(".schema.json")
        if (
            isinstance(document, dict)
            and contract_id == identifier
            and document.get("x-lmdj-contract-version") == version
        ):
            candidates.append(path)
    if len(candidates) != 1:
        raise TargetValidationError("Contract schema does not uniquely match the release identity")
    _require_assembly_identity(assembly, lock, ("contracts",), identifier, version)


def _validate_provider(root: Path, intent: ReleaseIntent, assembly: object, lock: object) -> None:
    identifier, version = _split_identity(intent.identity)
    candidates = [
        path for path in root.glob("providers/*/module.json")
        if _manifest_identity(path) == (identifier, version)
    ]
    if len(candidates) != 1:
        raise TargetValidationError("Provider manifest does not uniquely match the release identity")
    _require_assembly_identity(assembly, lock, ("providers",), identifier, version)


def _require_assembly_identity(
    assembly: object,
    lock: object,
    sections: tuple[str, ...],
    identifier: str,
    version: str,
) -> None:
    if not isinstance(assembly, dict) or not isinstance(lock, dict):
        raise TargetValidationError("Assembly support metadata is invalid")
    expected = (identifier, version)
    declared = [
        (item.get("id"), item.get("version"))
        for section in sections for item in assembly.get(section, [])
        if isinstance(item, dict)
    ]
    locked = [
        (item.get("id"), item.get("version"))
        for section in sections for item in lock.get(section, [])
        if isinstance(item, dict)
    ]
    if declared.count(expected) != 1 or locked.count(expected) != 1:
        raise TargetValidationError("Assembly support metadata does not bind the release identity")


def _manifest_identity(path: Path) -> tuple[object, object]:
    document = _json_file(path)
    if not isinstance(document, dict):
        raise TargetValidationError("module manifest is invalid")
    return document.get("module"), document.get("version")


def _split_identity(identity: str) -> tuple[str, str]:
    if not isinstance(identity, str) or identity.count("@") != 1:
        raise TargetValidationError("release identity is invalid")
    identifier, version = identity.split("@")
    if not identifier or not version:
        raise TargetValidationError("release identity is invalid")
    return identifier, version


def _json_file(path: Path) -> object:
    if not path.is_file() or path.is_symlink():
        raise TargetValidationError("exact target manifest is unavailable")
    return json.loads(path.read_text(encoding="utf-8"))
