"""Exact Git projections and local-only tag operations for release preparation."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import tempfile
from typing import Iterator, Mapping
from urllib.parse import urlparse

from .commands import CommandError, CommandRunner
from .model import (
    CANONICAL_BRANCH,
    CANONICAL_PRODUCT_FINGERPRINT,
    CANONICAL_REPOSITORY,
    ReleaseIntent,
)
from .openpgp import OpenPgpError, OpenPgpVerifier
from .target_validation import (
    TargetValidationError,
    validate_current_product_snapshot,
    validate_release_target,
)


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
        if repository != CANONICAL_REPOSITORY or branch != CANONICAL_BRANCH:
            raise GitRepositoryError("canonical fetch authority is invalid")
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

    def validate_release_target(self, worktree: Path, intent: ReleaseIntent) -> None:
        try:
            validate_release_target(worktree, intent, runner=self.runner)
        except TargetValidationError as error:
            raise GitRepositoryError(str(error)) from None

    def validate_current_product_snapshot(self, worktree: Path, identity: str) -> None:
        try:
            validate_current_product_snapshot(worktree, identity, runner=self.runner)
        except TargetValidationError as error:
            raise GitRepositoryError(str(error)) from None

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
        self._require_canonical_origin()
        reference = f"refs/tags/{tag}"
        self._run(["git", "push", "origin", f"{reference}:{reference}"])

    def remote_tag_object(self, tag: str) -> str | None:
        """Read the exact canonical remote ref without trusting a local tracking ref."""
        _require_tag(tag)
        self._require_canonical_origin()
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
        self._require_canonical_origin()
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
            if reference.startswith(self._tag_prefix):
                signer = self._verify_canonical_tag(reference)
            else:
                status = self._run(
                    ["git", "verify-tag", "--raw", reference], environment=environment,
                ).stderr
                signer = _signer_from_status(status)
        except GitRepositoryError:
            raise
        if not _sha(object_id) or not _sha(target) or signer is None:
            raise GitRepositoryError("release tag signature is invalid")
        return LocalTag(object_id, target, signer)

    def _verify_canonical_tag(self, reference: str) -> str:
        """Verify fetched tag bytes using only the Product key tracked on canonical main."""
        try:
            tag_bytes = self._run(["git", "cat-file", "tag", reference]).stdout.encode("utf-8")
            key_bytes = self._run([
                "git", "show",
                f"{self._main_ref}:.github/release-signing-keys/lmdj-product.asc",
            ]).stdout.encode("utf-8")
            with tempfile.TemporaryDirectory(prefix="lmdj-release-keyring-") as directory:
                home = Path(directory) / "gnupg"
                home.mkdir(mode=0o700)
                key_path = Path(directory) / "lmdj-product.asc"
                tag_path = Path(directory) / "tag.object"
                key_path.write_bytes(key_bytes)
                tag_path.write_bytes(tag_bytes)
                verifier = OpenPgpVerifier(runner=self.runner)
                verifier.import_public_key(home, key_path, CANONICAL_PRODUCT_FINGERPRINT)
                verifier.verify_inline_tag(home, tag_path, CANONICAL_PRODUCT_FINGERPRINT)
            return CANONICAL_PRODUCT_FINGERPRINT
        except (OSError, OpenPgpError):
            raise GitRepositoryError("release tag signature is invalid") from None

    def _require_canonical_origin(self) -> None:
        try:
            fetch_urls = self._run([
                "git", "remote", "get-url", "--all", "origin",
            ]).stdout.splitlines()
            push_urls = self._run([
                "git", "remote", "get-url", "--push", "--all", "origin",
            ]).stdout.splitlines()
        except GitRepositoryError:
            raise GitRepositoryError("canonical origin is unavailable") from None
        urls = [url.strip() for url in (*fetch_urls, *push_urls) if url.strip()]
        if (
            not fetch_urls or not push_urls or not urls
            or any(_repository_from_remote_url(url) != CANONICAL_REPOSITORY for url in urls)
        ):
            raise GitRepositoryError("canonical origin does not bind endaye/lmdj")

    def _run(
        self, arguments: list[str], *, environment: Mapping[str, str] | None = None,
    ):
        try:
            return self.runner.run(arguments, cwd=self.root, environment=environment)
        except CommandError as error:
            raise GitRepositoryError("Git release authority command failed") from None


def _signer_from_status(output: str) -> str | None:
    adverse = {"EXPKEYSIG", "EXPSIG", "REVKEYSIG", "KEYREVOKED", "BADSIG", "ERRSIG"}
    matches: list[str] = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == "[GNUPG:]" and fields[1] in adverse:
            return None
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


def _repository_from_remote_url(value: str) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path: str | None = None
    if value.startswith("git@github.com:"):
        path = value.removeprefix("git@github.com:")
    else:
        try:
            parsed = urlparse(value)
            port = parsed.port
        except ValueError:
            return None
        if (
            parsed.scheme in ("https", "ssh") and parsed.hostname == "github.com"
            and port is None and not parsed.params and not parsed.query and not parsed.fragment
            and (
                (parsed.scheme == "https" and parsed.username is None and parsed.password is None)
                or (parsed.scheme == "ssh" and parsed.username == "git" and parsed.password is None)
            )
        ):
            path = parsed.path.lstrip("/")
    if path is None:
        return None
    return path.removesuffix(".git")
