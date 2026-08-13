"""Exact Git projections and local-only tag operations for release preparation."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile
from typing import Iterator

from .commands import CommandError, CommandRunner


class GitRepositoryError(RuntimeError):
    """A Git release authority or local-tag gate failed."""


@dataclass(frozen=True)
class LocalTag:
    object_id: str
    target_revision: str
    signer_fingerprint: str


class GitRepository:
    """Uses scratch refs and detached worktrees; it intentionally has no push API."""

    def __init__(self, root: Path, *, runner: CommandRunner | None = None) -> None:
        self.root = root.expanduser().resolve()
        self.runner = runner or CommandRunner()
        self._main_ref = "refs/lmdj-release/origin-main"
        self._tag_prefix = "refs/lmdj-release/tags/"

    def fetch_authority(self, branch: str) -> None:
        self._run([
            "git", "fetch", "--no-tags", "origin",
            f"+refs/heads/{branch}:{self._main_ref}",
            f"+refs/tags/*:{self._tag_prefix}*",
        ])

    def is_main_ancestor(self, target: str) -> bool:
        try:
            self._run(["git", "merge-base", "--is-ancestor", target, self._main_ref])
            return True
        except GitRepositoryError:
            return False

    def remote_tag_state(self, tag: str) -> LocalTag | None:
        return self._tag_state(f"{self._tag_prefix}{tag}")

    def local_tag_state(self, tag: str) -> LocalTag | None:
        return self._tag_state(f"refs/tags/{tag}")

    @contextmanager
    def detached_worktree(self, target: str) -> Iterator[Path]:
        with tempfile.TemporaryDirectory(prefix="lmdj-release-worktree-") as directory:
            path = Path(directory) / "target"
            try:
                self._run(["git", "worktree", "add", "--detach", str(path), target])
                status = self._run(["git", "-C", str(path), "status", "--porcelain=v1", "--untracked-files=all"])
                if status.stdout.strip():
                    raise GitRepositoryError("release detached worktree is not clean")
                yield path
            finally:
                if path.exists() and not path.is_symlink():
                    try:
                        self._run(["git", "worktree", "remove", "--force", str(path)])
                    except GitRepositoryError:
                        shutil.rmtree(path, ignore_errors=True)

    def create_local_tag(self, tag: str, target: str, signer: str, message: str) -> LocalTag:
        self._run([
            "git", "tag", "--sign", "--local-user", signer, "--message", message, tag, target,
        ])
        state = self.local_tag_state(tag)
        if state is None:
            raise GitRepositoryError("local signed tag was not created")
        if state.target_revision != target or state.signer_fingerprint != signer:
            raise GitRepositoryError("local signed tag verification failed")
        return state

    def _tag_state(self, reference: str) -> LocalTag | None:
        try:
            object_id = self._run(["git", "rev-parse", "--verify", reference]).stdout.strip()
        except GitRepositoryError:
            return None
        try:
            if self._run(["git", "cat-file", "-t", reference]).stdout.strip() != "tag":
                raise GitRepositoryError("release tag must be annotated")
            target = self._run(["git", "rev-parse", "--verify", f"{reference}^{{commit}}"]).stdout.strip()
            status = self._run(["git", "verify-tag", "--raw", reference]).stderr
        except GitRepositoryError:
            raise
        signer = _signer_from_status(status)
        if not _sha(object_id) or not _sha(target) or signer is None:
            raise GitRepositoryError("release tag signature is invalid")
        return LocalTag(object_id, target, signer)

    def _run(self, arguments: list[str]):
        try:
            return self.runner.run(arguments, cwd=self.root)
        except CommandError as error:
            raise GitRepositoryError("Git release authority command failed") from None


def _signer_from_status(output: str) -> str | None:
    matches: list[str] = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[:2] == ["[GNUPG:]", "VALIDSIG"]:
            candidates = [field.upper() for field in fields[2:] if len(field) == 40 and all(char in "0123456789ABCDEF" for char in field.upper())]
            if candidates:
                matches.append(candidates[-1])
    return matches[0] if len(matches) == 1 else None


def _sha(value: str) -> bool:
    return len(value) == 40 and all(character in "0123456789abcdef" for character in value)
