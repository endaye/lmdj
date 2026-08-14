#!/usr/bin/env python3
"""Contract tests for secret-safe, agentless OpenPGP release verification."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.release.commands import CommandError, CommandRunner  # noqa: E402
from tools.release.openpgp import OpenPgpError, OpenPgpVerifier  # noqa: E402


PRODUCT = ROOT / ".github/release-signing-keys/lmdj-product.asc"
CHECKSUM = ROOT / ".github/release-signing-keys/lmdj-release-checksum.asc"
PRODUCT_FINGERPRINT = "2B5EE362F058800036AD4FB5116ECE156F954D29"
CHECKSUM_FINGERPRINT = "CB928A6E89DE498851688EF1AAC3E7019FC1478B"


class ReleaseOpenPgpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-release-openpgp-")
        self.root = Path(self.temporary.name)
        self.log = self.root / "gpg.jsonl"
        self.fake_gpg = self.root / "fake-gpg"
        self.fake_gpg.write_text(
            "#!" + sys.executable + "\n"
            "import json, os, pathlib, sys\n"
            "args = sys.argv[1:]\n"
            "pathlib.Path(os.environ['LMDJ_GPG_LOG']).open('a', encoding='utf-8').write(json.dumps(args) + '\\n')\n"
            "required = ['--batch', '--no-tty', '--no-autostart', '--homedir']\n"
            "if '--detach-sign' not in args and any(flag not in args for flag in required): raise SystemExit(70)\n"
            "if '--list-keys' in args:\n"
            " print('pub:-:255:22:fixture::::::')\n"
            " print('fpr:::::::::' + os.environ['LMDJ_GPG_FINGERPRINT'] + ':')\n"
            "elif '--verify' in args:\n"
            " fingerprint = os.environ['LMDJ_GPG_FINGERPRINT']\n"
            " print('[GNUPG:] VALIDSIG ' + fingerprint + ' 2026-08-13 0 4 0 22 8 00 ' + fingerprint)\n"
            "elif '--detach-sign' in args:\n"
            " pathlib.Path(args[args.index('--output') + 1]).write_text('signature', encoding='ascii')\n"
            "else:\n"
            " raise SystemExit(0)\n",
            encoding="utf-8",
        )
        self.fake_gpg.chmod(self.fake_gpg.stat().st_mode | stat.S_IXUSR)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_command_errors_redact_environment_values(self) -> None:
        secret = "release-secret-must-not-appear"
        runner = CommandRunner(
            environment={"RELEASE_SECRET": secret},
            executor=lambda *args, **kwargs: (_ for _ in ()).throw(
                OSError(secret)
            ),
        )
        with self.assertRaises(CommandError) as raised:
            runner.run(["does-not-exist"])
        self.assertNotIn(secret, str(raised.exception))
        self.assertIn("does-not-exist", str(raised.exception))

    def test_public_import_is_agentless_for_each_real_repository_key(self) -> None:
        verifier = OpenPgpVerifier()
        for key, fingerprint in ((PRODUCT, PRODUCT_FINGERPRINT), (CHECKSUM, CHECKSUM_FINGERPRINT)):
            with self.subTest(key=key.name), tempfile.TemporaryDirectory(prefix="lmdj-gpg-") as directory:
                home = Path(directory)
                home.chmod(0o700)
                verifier.import_public_key(home, key, fingerprint)
                self.assertFalse((home / "S.gpg-agent").exists())

    def test_public_verification_requires_agentless_prefix_and_one_matching_primary_signature(self) -> None:
        home = self.root / "home"
        home.mkdir(mode=0o700)
        signature = self.root / "artifact.asc"
        payload = self.root / "artifact.sha256"
        signature.write_text("fixture", encoding="ascii")
        payload.write_text("fixture", encoding="ascii")
        verifier = OpenPgpVerifier(
            gpg_program=str(self.fake_gpg),
            environment={
                "LMDJ_GPG_LOG": str(self.log),
                "LMDJ_GPG_FINGERPRINT": CHECKSUM_FINGERPRINT,
            },
        )
        verifier.import_public_key(home, CHECKSUM, CHECKSUM_FINGERPRINT)
        verifier.verify_detached(home, signature, payload, CHECKSUM_FINGERPRINT)
        invocations = [
            __import__("json").loads(line)
            for line in self.log.read_text(encoding="utf-8").splitlines()
        ]
        self.assertGreaterEqual(len(invocations), 3)
        for arguments in invocations:
            self.assertEqual(arguments[:5], [
                "--batch", "--no-tty", "--no-autostart", "--homedir", str(home),
            ])

    def test_public_verification_rejects_multiple_or_wrong_primary_fingerprints(self) -> None:
        home = self.root / "home"
        home.mkdir(mode=0o700)
        signature = self.root / "artifact.asc"
        payload = self.root / "artifact.sha256"
        signature.write_text("fixture", encoding="ascii")
        payload.write_text("fixture", encoding="ascii")
        fake = self.root / "invalid-gpg"
        fake.write_text(
            "#!/bin/sh\n"
            "case \" $* \" in\n"
            "  *' --list-keys '*) printf 'pub:-::::\\nfpr:::::::::CB928A6E89DE498851688EF1AAC3E7019FC1478B:\\n' ;;\n"
            "  *' --verify '*) printf '[GNUPG:] VALIDSIG CB928A6E89DE498851688EF1AAC3E7019FC1478B x\\n[GNUPG:] VALIDSIG CB928A6E89DE498851688EF1AAC3E7019FC1478B x\\n' ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        verifier = OpenPgpVerifier(gpg_program=str(fake))
        verifier.import_public_key(home, CHECKSUM, CHECKSUM_FINGERPRINT)
        with self.assertRaisesRegex(OpenPgpError, "exactly one"):
            verifier.verify_detached(home, signature, payload, CHECKSUM_FINGERPRINT)

    def test_public_verification_rejects_adverse_status_even_with_validsig(self) -> None:
        home = self.root / "home"
        home.mkdir(mode=0o700)
        signature = self.root / "artifact.asc"
        payload = self.root / "artifact.sha256"
        signature.write_text("fixture", encoding="ascii")
        payload.write_text("fixture", encoding="ascii")
        for status in ("EXPKEYSIG", "EXPSIG", "REVKEYSIG", "KEYREVOKED", "BADSIG", "ERRSIG"):
            with self.subTest(status=status):
                fake = self.root / f"invalid-gpg-{status.lower()}"
                fake.write_text(
                    "#!/bin/sh\n"
                    "case \" $* \" in\n"
                    "  *' --list-keys '*) printf 'pub:-::::\\nfpr:::::::::CB928A6E89DE498851688EF1AAC3E7019FC1478B:\\n' ;;\n"
                    f"  *' --verify '*) printf '[GNUPG:] {status} CB928A6E89DE498851688EF1AAC3E7019FC1478B fixture\\n"
                    "[GNUPG:] VALIDSIG CB928A6E89DE498851688EF1AAC3E7019FC1478B x\\n' ;;\n"
                    "esac\n",
                    encoding="utf-8",
                )
                fake.chmod(0o755)
                verifier = OpenPgpVerifier(gpg_program=str(fake))
                verifier.import_public_key(home, CHECKSUM, CHECKSUM_FINGERPRINT)
                with self.assertRaisesRegex(OpenPgpError, "status|signature"):
                    verifier.verify_detached(home, signature, payload, CHECKSUM_FINGERPRINT)

    def test_detached_signing_uses_the_exact_local_signer_without_a_passphrase_argument(self) -> None:
        home = self.root / "home"
        home.mkdir(mode=0o700)
        payload = self.root / "artifact.sha256"
        signature = self.root / "artifact.sha256.asc"
        payload.write_text("fixture", encoding="ascii")
        verifier = OpenPgpVerifier(
            gpg_program=str(self.fake_gpg),
            environment={
                "LMDJ_GPG_LOG": str(self.log),
                "LMDJ_GPG_FINGERPRINT": CHECKSUM_FINGERPRINT,
            },
        )
        verifier.sign_detached(home, payload, signature, CHECKSUM_FINGERPRINT)
        arguments = __import__("json").loads(self.log.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(arguments[arguments.index("--local-user") + 1], CHECKSUM_FINGERPRINT)
        self.assertNotIn("--passphrase", arguments)
        self.assertTrue(signature.is_file())

    def test_inline_annotated_tag_verification_uses_the_agentless_prefix(self) -> None:
        home = self.root / "home"
        home.mkdir(mode=0o700)
        tag = self.root / "tag-object"
        tag.write_bytes(
            b"object " + b"a" * 40 + b"\n"
            b"type commit\n"
            b"tag lmdj-v1.0.21.0\n\n"
            b"fixture\n"
            b"-----BEGIN PGP SIGNATURE-----\nfixture\n-----END PGP SIGNATURE-----\n"
        )
        verifier = OpenPgpVerifier(
            gpg_program=str(self.fake_gpg),
            environment={
                "LMDJ_GPG_LOG": str(self.log),
                "LMDJ_GPG_FINGERPRINT": PRODUCT_FINGERPRINT,
            },
        )
        verifier.verify_inline_tag(home, tag, PRODUCT_FINGERPRINT)
        arguments = __import__("json").loads(self.log.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(arguments[:5], [
            "--batch", "--no-tty", "--no-autostart", "--homedir", str(home),
        ])
        self.assertIn("--verify", arguments)


if __name__ == "__main__":
    unittest.main()
