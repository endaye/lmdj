"""Explicit hydration of release intent target objects.

An allocated intent in `docs/release-evidence/release-intents.json` may record a
pre-squash `target_revision` whose branch was deleted after merge, so no
advertised ref reaches it and a fresh full clone lacks the object. The audit
then correctly reports the intent unverifiable, and every consumer used to carry
its own inline `git fetch --no-tags origin <sha>` workaround.

Hydration lives here, in one explicit subcommand, rather than inside the audit:
`docs/superpowers/specs/2026-08-13-lmdj-standard-release-pipeline-design.md`
§12 states `Audit 不创建、push、编辑或删除任何 Git/GitHub 状态`, and `git fetch`
writes new objects into the local object store, which is Git state. A
self-healing audit would therefore break its own read-only contract. This module
is the one boundary that is allowed to write, so the audit can stay read-only
and still name a remedy when an object is missing.

The operation is idempotent: it probes each recorded revision first and fetches
only the ones the local object store does not already have.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .commands import CommandError, CommandRunner


LEDGER_PATH = "docs/release-evidence/release-intents.json"


class HydrateError(RuntimeError):
    """Release intent target hydration failed without exposing credentials."""

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message)
        self.detail = detail


@dataclass(frozen=True)
class HydrationResult:
    """Which recorded intent targets were already local and which were fetched."""

    present: tuple[str, ...]
    hydrated: tuple[str, ...]


def read_intent_target_revisions(root: Path) -> tuple[str, ...]:
    """Read every recorded intent target revision, entries and exceptions alike.

    Both lists are hydrated because both are audited: a historical exception
    binds the same kind of commit as an entry, and neither is filtered by
    disposition here. Selecting which intents an audit must verify belongs to
    the audit, not to the step that makes objects reachable.
    """
    path = root / LEDGER_PATH
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise HydrateError(
            f"release intent ledger is unreadable: {LEDGER_PATH}",
            detail=type(error).__name__,
        ) from None
    if not isinstance(document, dict):
        raise HydrateError(f"release intent ledger is not an object: {LEDGER_PATH}")
    ordered: list[str] = []
    for section in ("entries", "historical_exceptions"):
        rows = document.get(section)
        if not isinstance(rows, list):
            raise HydrateError(
                f"release intent ledger has no {section} list: {LEDGER_PATH}",
            )
        for row in rows:
            revision = row.get("target_revision") if isinstance(row, dict) else None
            if not _is_sha(revision):
                raise HydrateError(
                    f"release intent ledger holds a target_revision that is not a "
                    f"40-character lowercase hex commit id in {section}: {LEDGER_PATH}",
                )
            assert isinstance(revision, str)
            if revision not in ordered:
                ordered.append(revision)
    if not ordered:
        raise HydrateError(f"release intent ledger records no target: {LEDGER_PATH}")
    return tuple(ordered)


def hydrate_release_intent_targets(
    root: Path, *, runner: CommandRunner | None = None,
) -> HydrationResult:
    """Fetch by SHA exactly the recorded intent targets the object store lacks."""
    selected = runner or CommandRunner()
    revisions = read_intent_target_revisions(root)
    present: list[str] = []
    missing: list[str] = []
    for revision in revisions:
        (present if _has_commit(root, revision, selected) else missing).append(revision)
    if missing:
        try:
            selected.run(
                ["git", "fetch", "--no-tags", "origin", *missing], cwd=root,
            )
        except CommandError as error:
            raise HydrateError(
                "release intent target objects are not reachable from origin, so "
                "no release audit can verify the intents that bind them; remedy: "
                "confirm the fetch credential reaches the canonical remote and "
                "that the recorded target_revision values still exist there, then "
                "rerun scripts/release.sh hydrate",
                detail=error.detail,
            ) from None
        still_missing = [
            revision for revision in missing
            if not _has_commit(root, revision, selected)
        ]
        if still_missing:
            raise HydrateError(
                "fetch reported success but "
                f"{len(still_missing)} release intent target object(s) are still "
                "absent from the local object store, so a release audit would "
                "still report those intents unverifiable; remedy: rerun "
                "scripts/release.sh hydrate against a repository whose origin is "
                "the canonical remote",
            )
    return HydrationResult(tuple(present), tuple(missing))


def format_hydration(result: HydrationResult) -> str:
    """Report present versus hydrated targets so a green run is still legible."""
    lines = [
        f"release intent targets already present: {len(result.present)}",
        f"release intent targets hydrated: {len(result.hydrated)}",
    ]
    for revision in result.hydrated:
        lines.append(f"hydrated intent target: {revision}")
    if not result.hydrated:
        lines.append("all release intent targets were already present")
    return "\n".join(lines)


def _has_commit(root: Path, revision: str, runner: CommandRunner) -> bool:
    try:
        runner.run(["git", "cat-file", "-e", f"{revision}^{{commit}}"], cwd=root)
        return True
    except CommandError:
        return False


def _is_sha(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )
