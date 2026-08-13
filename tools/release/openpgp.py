"""OpenPGP operations with an explicit agentless public-verification boundary."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Mapping

from .commands import CommandError, CommandRunner


class OpenPgpError(RuntimeError):
    """A release signature or public-key verification gate failed."""


_FINGERPRINT = re.compile(r"[0-9A-F]{40}\Z")


class OpenPgpVerifier:
    def __init__(
        self,
        *,
        gpg_program: str = "gpg",
        runner: CommandRunner | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.gpg_program = gpg_program
        self.runner = runner or CommandRunner(environment=environment)

    def public_prefix(self, home: Path) -> list[str]:
        return [
            self.gpg_program,
            "--batch",
            "--no-tty",
            "--no-autostart",
            "--homedir",
            str(home),
        ]

    def import_public_key(self, home: Path, key_path: Path, fingerprint: str) -> None:
        expected = _require_fingerprint(fingerprint)
        _require_keyring(home)
        if not key_path.is_file() or key_path.is_symlink():
            raise OpenPgpError("release signing public key is unavailable")
        try:
            self.runner.run([*self.public_prefix(home), "--import", str(key_path)])
            listed = self.runner.run([
                *self.public_prefix(home), "--with-colons", "--fingerprint", "--list-keys",
            ])
        except CommandError as error:
            raise OpenPgpError("release signing public key import failed") from None
        if _primary_fingerprints(listed.stdout) != [expected]:
            raise OpenPgpError("repository signing public key fingerprint mismatch")

    def verify_detached(
        self,
        home: Path,
        signature_path: Path,
        payload_path: Path,
        fingerprint: str,
    ) -> None:
        expected = _require_fingerprint(fingerprint)
        _require_keyring(home)
        if any(not path.is_file() or path.is_symlink() for path in (signature_path, payload_path)):
            raise OpenPgpError("release detached signature inputs are unavailable")
        try:
            verified = self.runner.run([
                *self.public_prefix(home), "--status-fd", "1", "--verify",
                str(signature_path), str(payload_path),
            ])
        except CommandError:
            raise OpenPgpError("release detached signature verification failed") from None
        signatures = _valid_signatures(verified.stdout)
        if len(signatures) != 1:
            raise OpenPgpError("release signature must contain exactly one VALIDSIG")
        if expected not in signatures[0]:
            raise OpenPgpError("release signature signer mismatch")

    def sign_detached(
        self,
        home: Path,
        payload_path: Path,
        signature_path: Path,
        fingerprint: str,
    ) -> None:
        signer = _require_fingerprint(fingerprint)
        _require_keyring(home)
        if not payload_path.is_file() or payload_path.is_symlink() or signature_path.exists():
            raise OpenPgpError("release detached signing inputs are invalid")
        try:
            self.runner.run([
                self.gpg_program,
                "--batch",
                "--no-tty",
                "--homedir",
                str(home),
                "--armor",
                "--local-user",
                signer,
                "--output",
                str(signature_path),
                "--detach-sign",
                str(payload_path),
            ])
        except CommandError:
            raise OpenPgpError("release detached signing failed") from None
        if not signature_path.is_file() or signature_path.is_symlink():
            raise OpenPgpError("release detached signing failed")


def _require_keyring(home: Path) -> None:
    try:
        if not home.is_dir() or home.is_symlink() or (home.stat().st_mode & 0o777) != 0o700:
            raise OpenPgpError("release keyring must be a private 0700 directory")
    except OSError:
        raise OpenPgpError("release keyring is unavailable") from None


def _require_fingerprint(value: str) -> str:
    fingerprint = value.upper()
    if _FINGERPRINT.fullmatch(fingerprint) is None:
        raise OpenPgpError("release signing fingerprint is invalid")
    return fingerprint


def _primary_fingerprints(output: str) -> list[str]:
    primary: list[str] = []
    expecting_primary = False
    for line in output.splitlines():
        fields = line.split(":")
        record = fields[0] if fields else ""
        if record == "pub":
            expecting_primary = True
        elif record == "fpr" and expecting_primary and len(fields) > 9:
            primary.append(fields[9].upper())
            expecting_primary = False
        elif record in {"sub", "sec", "ssb"}:
            expecting_primary = False
    return primary


def _valid_signatures(output: str) -> list[set[str]]:
    valid: list[set[str]] = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[:2] == ["[GNUPG:]", "VALIDSIG"]:
            fingerprints = {field.upper() for field in fields[2:] if _FINGERPRINT.fullmatch(field.upper())}
            valid.append(fingerprints)
    return valid
