"""Injectable subprocess execution with secret-safe diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
from typing import Callable, Mapping, Sequence


_URL_CREDENTIALS = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/@]*@")
_AUTHORIZATION = re.compile(r"(?i)\b(basic|bearer|token)\s+\S+")
_TOKEN_LIKE = re.compile(r"\b(gh[pousra]|github_pat)_[A-Za-z0-9_]{16,}")
_ASSIGNMENT = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)=\S+")
_ABSOLUTE_PATH = re.compile(r"(?<![\w<>])/[^\s'\"]*")


def sanitize_diagnostic(
    text: object, *, root: Path | None = None, limit: int = 160,
) -> str:
    """Reduce free-form tool output to a bounded diagnostic that carries no secret.

    Failing tools describe themselves on stderr, and that description is the only
    way to tell one failure apart from another in a retained audit report. The
    text is therefore kept, but every shape that can carry a credential or an
    environment value is removed first: URL user information, `basic`/`bearer`
    authorization values, token literals, `NAME=value` pairs, and absolute paths.
    """
    collapsed = " ".join(str(text).split())
    if root is not None:
        collapsed = collapsed.replace(str(root), "<repo>")
    collapsed = _URL_CREDENTIALS.sub("<redacted>@", collapsed)
    collapsed = _AUTHORIZATION.sub(r"\1 [redacted]", collapsed)
    collapsed = _TOKEN_LIKE.sub("[redacted]", collapsed)
    collapsed = _ASSIGNMENT.sub(r"\1=[redacted]", collapsed)
    collapsed = _ABSOLUTE_PATH.sub("<path>", collapsed)
    if len(collapsed) > limit:
        collapsed = collapsed[:limit].rstrip() + "..."
    return collapsed


class CommandError(RuntimeError):
    """A command failed without exposing its environment or output secrets.

    `detail` carries the sanitized tail of the failed command's own output so a
    caller can say which failure happened; it is never the raw output.
    """

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message)
        self.detail = detail


@dataclass(frozen=True)
class CommandResult:
    arguments: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


Executor = Callable[..., subprocess.CompletedProcess[str]]


class CommandRunner:
    """Run explicit argument vectors and retain no secret-bearing diagnostics."""

    def __init__(
        self,
        *,
        environment: Mapping[str, str] | None = None,
        executor: Executor | None = None,
    ) -> None:
        self._environment = dict(environment or {})
        self._executor = executor or subprocess.run

    def run(
        self,
        arguments: Sequence[str | Path],
        *,
        cwd: Path | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> CommandResult:
        vector = tuple(str(argument) for argument in arguments)
        if not vector or not all(vector):
            raise CommandError("release command is invalid")
        selected_environment = dict(os.environ)
        selected_environment.update(self._environment)
        if environment:
            selected_environment.update(environment)
        try:
            completed = self._executor(
                vector,
                cwd=str(cwd) if cwd is not None else None,
                env=selected_environment,
                check=False,
                capture_output=True,
                text=True,
            )
        except (OSError, ValueError) as error:
            raise CommandError(f"release command is unavailable: {vector[0]}") from None
        if completed.returncode != 0:
            raise CommandError(
                f"release command failed: {vector[0]} (exit {completed.returncode})",
                detail=sanitize_diagnostic(completed.stderr or completed.stdout),
            )
        return CommandResult(vector, completed.returncode, completed.stdout, completed.stderr)
