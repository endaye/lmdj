"""Injectable subprocess execution with secret-safe diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
from typing import Callable, Mapping, Sequence


class CommandError(RuntimeError):
    """A command failed without exposing its environment or output secrets."""


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
            raise CommandError(f"release command failed: {vector[0]} (exit {completed.returncode})")
        return CommandResult(vector, completed.returncode, completed.stdout, completed.stderr)
