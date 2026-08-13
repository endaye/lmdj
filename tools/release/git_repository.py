"""Exact Git projections and local-only tag operations for release preparation."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import tempfile
from typing import Iterator, Mapping

from .commands import CommandError, CommandRunner


class GitRepositoryError(RuntimeError):
    """A Git release authority or local-tag gate failed."""


@dataclass(frozen=True)
class LocalTag:
    object_id: str
    target_revision: str
    signer_fingerprint: str


class GitRepository:
    """Uses scratch refs, exact tag refspecs, and detached worktrees."""

    def __init__(self, root: Path, *, runner: CommandRunner | None = None) -> None:
        self.root = root.expanduser().resolve()
        self.runner = runner or CommandRunner()
        self._main_ref = "refs/lmdj-release/origin-main"
        self._tag_prefix = "refs/lmdj-release/tags/"

    def fetch_authority(self, repository: str, branch: str) -> None:
        remote = f"https://github.com/{repository}.git"
        self._run([
            "git", "fetch", "--no-tags", "--prune", remote,
            f"+refs/heads/{branch}:{self._main_ref}",
            f"+refs/tags/*:{self._tag_prefix}*",
        ])

    def main_revision(self) -> str:
        revision = self._run(["git", "rev-parse", "--verify", self._main_ref]).stdout.strip()
        if not _sha(revision):
            raise GitRepositoryError("canonical main revision is invalid")
        return revision

    def is_main_ancestor(self, target: str) -> bool:
        return self.is_revision_ancestor(target, self._main_ref)

    def is_revision_ancestor(self, ancestor: str, descendant: str) -> bool:
        try:
            self._run(["git", "merge-base", "--is-ancestor", ancestor, descendant])
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

    def create_rehearsal_tag(
        self, tag: str, target: str, signer: str, message: str, gpg_home: Path,
    ) -> LocalTag:
        """Create and verify a test-only tag with its isolated ephemeral keyring."""
        _require_tag(tag)
        environment = {"GNUPGHOME": str(gpg_home)}
        self._run([
            "git", "tag", "--sign", "--local-user", signer, "--message", message, tag, target,
        ], environment=environment)
        state = self._tag_state(f"refs/tags/{tag}", environment=environment)
        if state is None or state.target_revision != target or state.signer_fingerprint != signer:
            raise GitRepositoryError("local rehearsal tag verification failed")
        return state

    def local_rehearsal_tag_state(self, tag: str, gpg_home: Path) -> LocalTag | None:
        return self._tag_state(
            f"refs/tags/{tag}", environment={"GNUPGHOME": str(gpg_home)},
        )

    def push_tag(self, tag: str) -> None:
        """Push exactly one local tag without branches, wildcard tags, or force."""
        _require_tag(tag)
        reference = f"refs/tags/{tag}"
        self._run(["git", "push", "origin", f"{reference}:{reference}"])

    def remote_tag_object(self, tag: str) -> str | None:
        """Read the exact canonical remote ref without trusting a local tracking ref."""
        _require_tag(tag)
        reference = f"refs/tags/{tag}"
        output = self._run(["git", "ls-remote", "--refs", "origin", reference]).stdout.strip()
        if not output:
            return None
        lines = output.splitlines()
        if len(lines) != 1:
            raise GitRepositoryError("remote tag projection is ambiguous")
        fields = lines[0].split()
        if len(fields) != 2 or fields[1] != reference or not _sha(fields[0]):
            raise GitRepositoryError("remote tag projection is invalid")
        return fields[0]

    def delete_remote_tag(self, tag: str, expected_object: str) -> None:
        """Delete only a rehearsal tag whose exact remote object was just proven."""
        _require_tag(tag)
        if not _sha(expected_object) or self.remote_tag_object(tag) != expected_object:
            raise GitRepositoryError("remote rehearsal tag object changed")
        reference = f"refs/tags/{tag}"
        self._run(["git", "push", "origin", f":{reference}"])
        if self.remote_tag_object(tag) is not None:
            raise GitRepositoryError("remote rehearsal tag deletion was not observed")

    def _tag_state(
        self, reference: str, *, environment: Mapping[str, str] | None = None,
    ) -> LocalTag | None:
        try:
            object_id = self._run(
                ["git", "rev-parse", "--verify", reference], environment=environment,
            ).stdout.strip()
        except GitRepositoryError:
            return None
        try:
            if self._run(
                ["git", "cat-file", "-t", reference], environment=environment,
            ).stdout.strip() != "tag":
                raise GitRepositoryError("release tag must be annotated")
            target = self._run(
                ["git", "rev-parse", "--verify", f"{reference}^{{commit}}"],
                environment=environment,
            ).stdout.strip()
            status = self._run(
                ["git", "verify-tag", "--raw", reference], environment=environment,
            ).stderr
        except GitRepositoryError:
            raise
        signer = _signer_from_status(status)
        if not _sha(object_id) or not _sha(target) or signer is None:
            raise GitRepositoryError("release tag signature is invalid")
        return LocalTag(object_id, target, signer)

    def _run(
        self, arguments: list[str], *, environment: Mapping[str, str] | None = None,
    ):
        try:
            return self.runner.run(arguments, cwd=self.root, environment=environment)
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


def _require_tag(tag: object) -> None:
    if (
        not isinstance(tag, str) or not tag or tag.startswith("-") or tag.endswith("/")
        or ".." in tag or "//" in tag or "@{" in tag
        or re.search(r"[\x00-\x20\x7f~^:?*\\[]", tag) is not None
    ):
        raise GitRepositoryError("release tag reference is invalid")
