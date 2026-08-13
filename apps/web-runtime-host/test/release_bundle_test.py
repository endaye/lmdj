#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RELEASE_BUNDLE_TOOL = REPO_ROOT / "apps/web-runtime-host/tools/release_bundle.py"
sys.path.insert(0, str(RELEASE_BUNDLE_TOOL.parent))
import release_bundle


class ReleaseBundleTest(unittest.TestCase):
    TRUSTED_CHECKSUM_FINGERPRINT = "CB928A6E89DE498851688EF1AAC3E7019FC1478B"

    def setUp(self) -> None:
        self.module = release_bundle
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-release-bundle-")
        self.root = Path(self.temporary.name)
        self.output = self.root / "staged"
        self.signature = self.root / "release.zip.sha256.asc"
        self.signature.write_text(
            "-----BEGIN PGP SIGNATURE-----\nfixture\n-----END PGP SIGNATURE-----\n",
            encoding="ascii",
        )
        self.checksum_public_key = self.root / "checksum.asc"
        self.checksum_public_key.write_text("fixture public key\n", encoding="ascii")
        self.fake_gpg = self.root / "fake-gpg"
        self.fake_gpg.write_text(
            "#!/bin/sh\n"
            "case \" $* \" in\n"
            "  *\" --list-keys \"*) printf 'pub:-:255:22:KEY::::::\\nfpr:::::::::CB928A6E89DE498851688EF1AAC3E7019FC1478B:\\n' ;;\n"
            "  *\" --verify \"*) printf '[GNUPG:] VALIDSIG CB928A6E89DE498851688EF1AAC3E7019FC1478B 2026-08-10 0 4 0 22 8 00 CB928A6E89DE498851688EF1AAC3E7019FC1478B\\n' ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        self.fake_gpg.chmod(0o755)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_zip(self, members: dict[str, bytes]) -> Path:
        archive = self.root / "release.zip"
        with zipfile.ZipFile(archive, "w") as output:
            for name, payload in members.items():
                output.writestr(name, payload)
        return archive

    def write_checksum(self, digest: str, name: str) -> Path:
        checksum = self.root / "release.zip.sha256"
        checksum.write_text(f"{digest}  {name}\n", encoding="utf-8")
        return checksum

    def run_stage_cli(self, archive: Path, checksum: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(RELEASE_BUNDLE_TOOL),
                "stage",
                "--repo-root",
                str(REPO_ROOT),
                "--archive",
                str(archive),
                "--checksum",
                str(checksum),
                "--checksum-signature",
                str(self.signature),
                "--checksum-public-key",
                str(self.checksum_public_key),
                "--trusted-checksum-fingerprint",
                self.TRUSTED_CHECKSUM_FINGERPRINT,
                "--gpg-program",
                str(self.fake_gpg),
                "--output-root",
                str(self.output),
                "--expected-product-build",
                "1.0.15.2",
                "--expected-host-version",
                "1.2.0",
            ],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "LMDJ_TEST_FINGERPRINT": self.TRUSTED_CHECKSUM_FINGERPRINT,
            },
        )

    def archive_with_member(self, member: str) -> tuple[Path, Path]:
        archive = self.write_zip({member: b"unsafe"})
        return archive, self.write_checksum(
            hashlib.sha256(archive.read_bytes()).hexdigest(), archive.name
        )

    def stage(self, archive: Path, checksum: Path, **extra):
        verifier = extra.pop("verifier", lambda root, repo: None)
        repo_root = extra.pop("repo_root", REPO_ROOT)
        return self.module.stage_release_bundle(
            repo_root=repo_root,
            archive_path=archive,
            checksum_path=checksum,
            signature_path=self.signature,
            checksum_public_key_path=self.checksum_public_key,
            trusted_checksum_fingerprint=self.TRUSTED_CHECKSUM_FINGERPRINT,
            output_root=self.output,
            expected_product_build="1.0.15.2",
            expected_host_version="1.2.0",
            verifier=verifier,
            checksum_authorizer=extra.pop(
                "checksum_authorizer", lambda checksum, signature, key, fingerprint: None
            ),
            **extra,
        )

    def stage_valid(self, **extra):
        manifest = {
            "host_version": "1.2.0",
            "product_build": "1.0.15.2",
        }
        archive = self.write_zip(
            {
                "dist/index.html": b"<!doctype html>",
                "dist/host-manifest.json": json.dumps(manifest).encode("utf-8"),
            }
        )
        checksum = self.write_checksum(
            hashlib.sha256(archive.read_bytes()).hexdigest(), archive.name
        )
        return self.stage(archive, checksum, **extra)

    def test_authorizes_detached_signature_before_parsing_checksum(self) -> None:
        archive = self.write_zip({"dist/index.html": b"host"})
        checksum = self.root / "release.zip.sha256"
        checksum.write_text("not-a-checksum\n", encoding="utf-8")
        observed: list[bytes] = []
        with self.assertRaisesRegex(self.module.BundleError, "checksum record"):
            self.stage(
                archive,
                checksum,
                checksum_authorizer=lambda path, signature, key, fingerprint: observed.append(
                    path.read_bytes()
                ),
            )
        self.assertEqual(observed, [b"not-a-checksum\n"])

    def test_rejects_noncanonical_signature_name_before_checksum_parse(self) -> None:
        archive = self.write_zip({"dist/index.html": b"host"})
        checksum = self.root / "release.zip.sha256"
        checksum.write_text("not-a-checksum\n", encoding="utf-8")
        wrong = self.root / "other.asc"
        wrong.write_text(self.signature.read_text(encoding="ascii"), encoding="ascii")
        with self.assertRaisesRegex(self.module.BundleError, "signature name"):
            self.module.stage_release_bundle(
                repo_root=REPO_ROOT,
                archive_path=archive,
                checksum_path=checksum,
                signature_path=wrong,
                checksum_public_key_path=self.checksum_public_key,
                trusted_checksum_fingerprint=self.TRUSTED_CHECKSUM_FINGERPRINT,
                output_root=self.output,
                expected_product_build="1.0.15.2",
                expected_host_version="1.2.0",
                verifier=lambda root, repo: None,
            )

    def test_rejects_checksum_mismatch_before_extraction(self) -> None:
        archive = self.write_zip({"dist/index.html": b"host"})
        checksum = self.write_checksum("0" * 64, archive.name)
        with self.assertRaisesRegex(
            self.module.BundleError, "release archive checksum mismatch"
        ):
            self.stage(archive, checksum)
        self.assertFalse(self.output.exists())

    def test_rejects_parent_absolute_duplicate_and_link_entries(self) -> None:
        for member in ("../escape", "/absolute", "dist/../escape"):
            with self.subTest(member=member):
                archive, checksum = self.archive_with_member(member)
                with self.assertRaisesRegex(
                    self.module.BundleError, "unsafe release archive entry"
                ):
                    self.stage(archive, checksum)
                self.assertFalse(self.output.exists())

        duplicate = self.root / "duplicate.zip"
        with zipfile.ZipFile(duplicate, "w") as output:
            output.writestr("dist/index.html", b"first")
            output.writestr("dist//index.html", b"second")
        checksum = self.write_checksum(
            hashlib.sha256(duplicate.read_bytes()).hexdigest(), duplicate.name
        )
        with self.assertRaisesRegex(
            self.module.BundleError, "duplicate release archive entry"
        ):
            self.stage(duplicate, checksum)

        linked = self.root / "linked.zip"
        entry = zipfile.ZipInfo("dist/link")
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(linked, "w") as output:
            output.writestr(entry, "target")
        checksum = self.write_checksum(
            hashlib.sha256(linked.read_bytes()).hexdigest(), linked.name
        )
        with self.assertRaisesRegex(
            self.module.BundleError, "unsafe release archive entry"
        ):
            self.stage(linked, checksum)

    def test_rejects_invalid_checksum_records(self) -> None:
        archive = self.write_zip({"dist/index.html": b"host"})
        for contents, message in (
            (f"{'a' * 64}  other.zip\n", "release checksum record is invalid"),
            (f"{'z' * 64}  {archive.name}\n", "release checksum digest is invalid"),
        ):
            with self.subTest(contents=contents):
                checksum = self.root / "invalid.sha256"
                checksum.write_text(contents, encoding="utf-8")
                with self.assertRaisesRegex(self.module.BundleError, message):
                    self.module.parse_detached_checksum(checksum, archive.name)

    def test_rejects_missing_or_mismatched_manifest_identity(self) -> None:
        for manifest, message in (
            ({"host_version": "1.2.0"}, "release bundle manifest is invalid"),
            (
                {"host_version": "1.2.0", "product_build": "1.0.15.3"},
                "release bundle Product Build mismatch",
            ),
            (
                {"host_version": "1.1.3", "product_build": "1.0.15.2"},
                "release bundle Host version mismatch",
            ),
        ):
            with self.subTest(manifest=manifest):
                archive = self.write_zip(
                    {
                        "dist/index.html": b"<!doctype html>",
                        "dist/host-manifest.json": json.dumps(manifest).encode("utf-8"),
                    }
                )
                checksum = self.write_checksum(
                    hashlib.sha256(archive.read_bytes()).hexdigest(), archive.name
                )
                with self.assertRaisesRegex(self.module.BundleError, message):
                    self.stage(archive, checksum)
                self.assertFalse(self.output.exists())

    def test_rejects_archive_without_exactly_one_dist_tree(self) -> None:
        archive = self.write_zip(
            {"other/index.html": b"host", "dist/index.html": b"host"}
        )
        checksum = self.write_checksum(
            hashlib.sha256(archive.read_bytes()).hexdigest(), archive.name
        )
        with self.assertRaisesRegex(
            self.module.BundleError, "release archive must contain exactly one dist tree"
        ):
            self.stage(archive, checksum)
        self.assertFalse(self.output.exists())

    def test_default_verifier_comes_from_supplied_repository_root(self) -> None:
        tagged_repo = self.root / "tagged-repository"
        package_path = tagged_repo / "apps/web-runtime-host/tools/package.py"
        package_path.parent.mkdir(parents=True)
        package_path.write_text(
            "from pathlib import Path\n"
            "def verify_distribution(dist_root, repo_root):\n"
            "    Path(repo_root, 'used-tagged-verifier').write_text(dist_root.name)\n",
            encoding="utf-8",
        )
        bundle = self.stage_valid(repo_root=tagged_repo, verifier=None)
        self.assertTrue(bundle.dist_root.is_dir())
        self.assertEqual(
            (tagged_repo / "used-tagged-verifier").read_text(encoding="utf-8"),
            "dist",
        )

    def test_verifier_failure_leaves_output_absent(self) -> None:
        observed_output_states: list[bool] = []

        def fail_while_staged(root: Path, repo: Path) -> None:
            observed_output_states.append(self.output.exists())
            raise ValueError()

        with self.assertRaisesRegex(self.module.BundleError, "release bundle verification failed"):
            self.stage_valid(verifier=fail_while_staged)
        self.assertEqual(observed_output_states, [False])
        self.assertFalse(self.output.exists())

    def test_success_calls_verifier_and_emits_canonical_metadata(self) -> None:
        observed: list[tuple[Path, Path]] = []
        bundle = self.stage_valid(
            verifier=lambda root, repo: (
                self.assertFalse(self.output.exists()), observed.append((root, repo))
            ),
        )
        self.assertEqual(len(observed), 1)
        self.assertNotEqual(observed[0][0], bundle.dist_root)
        self.assertEqual(observed[0][1], REPO_ROOT)
        self.assertEqual(bundle.product_build, "1.0.15.2")
        self.assertEqual(bundle.host_version, "1.2.0")
        self.assertRegex(bundle.archive_sha256, r"^[0-9a-f]{64}$")
        self.assertEqual(bundle.dist_root, (self.output / "dist").resolve())
        self.assertEqual(
            self.module.canonical_json(bundle),
            json.dumps(
                {
                    "archive_sha256": bundle.archive_sha256,
                    "dist_root": str(bundle.dist_root),
                    "host_version": "1.2.0",
                    "product_build": "1.0.15.2",
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    def test_accepts_explicit_directory_after_its_child_file(self) -> None:
        archive = self.root / "out-of-order.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("dist/index.html", b"<!doctype html>")
            output.writestr("dist/", b"")
            output.writestr(
                "dist/host-manifest.json",
                b'{"host_version":"1.2.0","product_build":"1.0.15.2"}',
            )
        checksum = self.write_checksum(
            hashlib.sha256(archive.read_bytes()).hexdigest(), archive.name
        )
        bundle = self.stage(archive, checksum)
        self.assertTrue(bundle.dist_root.is_dir())

    def test_cli_normalizes_checksum_and_unsupported_zip_input_errors(self) -> None:
        archive = self.write_zip({"dist/index.html": b"host"})
        checksum = self.root / "non-utf8.sha256"
        checksum.write_bytes(b"\xff")
        cases: list[tuple[str, Path, Path]] = [("checksum", archive, checksum)]

        for label, patches in (
            (
                "compression",
                ((b"PK\x03\x04", 8, lambda value: 99), (b"PK\x01\x02", 10, lambda value: 99)),
            ),
            (
                "encryption",
                (
                    (b"PK\x03\x04", 6, lambda value: value | 1),
                    (b"PK\x01\x02", 8, lambda value: value | 1),
                ),
            ),
        ):
            source = self.write_zip({"dist/index.html": b"host"})
            payload = bytearray(source.read_bytes())
            for signature, offset, mutate in patches:
                position = payload.find(signature)
                self.assertNotEqual(position, -1)
                value = int.from_bytes(
                    payload[position + offset : position + offset + 2], "little"
                )
                payload[position + offset : position + offset + 2] = mutate(value).to_bytes(
                    2, "little"
                )
            archive = self.root / f"{label}.zip"
            archive.write_bytes(payload)
            checksum = self.root / f"{label}.zip.sha256"
            checksum.write_text(
                f"{hashlib.sha256(payload).hexdigest()}  {archive.name}\n",
                encoding="utf-8",
            )
            cases.append((label, archive, checksum))

        for label, archive, checksum in cases:
            with self.subTest(label=label):
                completed = self.run_stage_cli(archive, checksum)
                self.assertEqual(completed.returncode, 2)
                self.assertIn("Web Runtime deployment bundle error:", completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)
                self.assertFalse(self.output.exists())

    def test_cli_requires_stage_and_all_arguments_and_prints_canonical_json(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(RELEASE_BUNDLE_TOOL)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 64)
        self.assertIn("usage:", completed.stderr)

        completed = subprocess.run(
            [sys.executable, str(RELEASE_BUNDLE_TOOL), "stage"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 64)
        self.assertIn("usage:", completed.stderr)

        tagged_repo = self.root / "tagged-repository"
        package_path = tagged_repo / "apps/web-runtime-host/tools/package.py"
        package_path.parent.mkdir(parents=True)
        package_path.write_text(
            "def verify_distribution(dist_root, repo_root):\n"
            "    if not (dist_root / 'host-manifest.json').is_file():\n"
            "        raise RuntimeError('manifest missing')\n",
            encoding="utf-8",
        )
        expected_product_build = "1.0.15.2"
        expected_host_version = "1.2.0"
        archive = self.root / "valid-release.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("dist/index.html", "<!doctype html>")
            output.writestr(
                "dist/host-manifest.json",
                json.dumps(
                    {
                        "host_version": expected_host_version,
                        "product_build": expected_product_build,
                    }
                ),
            )
        command = [
            sys.executable,
            str(RELEASE_BUNDLE_TOOL),
            "stage",
            "--repo-root",
            str(tagged_repo),
            "--archive",
            str(archive),
            "--checksum",
            "",
            "--checksum-signature",
            str(self.signature),
            "--checksum-public-key",
            str(self.checksum_public_key),
            "--trusted-checksum-fingerprint",
            self.TRUSTED_CHECKSUM_FINGERPRINT,
            "--gpg-program",
            str(self.fake_gpg),
            "--output-root",
            str(self.output),
            "--expected-product-build",
            expected_product_build,
            "--expected-host-version",
            expected_host_version,
        ]
        checksum = self.write_checksum("0" * 64, archive.name)
        command[command.index("--checksum") + 1] = str(checksum)
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "LMDJ_TEST_FINGERPRINT": self.TRUSTED_CHECKSUM_FINGERPRINT,
            },
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("Web Runtime deployment bundle error:", completed.stderr)
        self.assertFalse(self.output.exists())

        checksum = self.write_checksum(
            hashlib.sha256(archive.read_bytes()).hexdigest(), archive.name
        )
        command[command.index("--checksum") + 1] = str(checksum)
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "LMDJ_TEST_FINGERPRINT": self.TRUSTED_CHECKSUM_FINGERPRINT,
            },
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            json.dumps(json.loads(completed.stdout), sort_keys=True, separators=(",", ":"))
            + "\n",
        )
        self.assertEqual(
            json.loads(completed.stdout)["dist_root"],
            str((self.output / "dist").resolve()),
        )


if __name__ == "__main__":
    unittest.main()
