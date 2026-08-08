#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
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
    def setUp(self) -> None:
        self.module = release_bundle
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-release-bundle-")
        self.root = Path(self.temporary.name)
        self.output = self.root / "staged"

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
            output_root=self.output,
            expected_product_build="1.0.15.2",
            expected_host_version="1.1.2",
            verifier=verifier,
            **extra,
        )

    def stage_valid(self, **extra):
        manifest = {
            "host_version": "1.1.2",
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
            ({"host_version": "1.1.2"}, "release bundle manifest is invalid"),
            (
                {"host_version": "1.1.2", "product_build": "1.0.15.3"},
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
        self.assertEqual(bundle.host_version, "1.1.2")
        self.assertRegex(bundle.archive_sha256, r"^[0-9a-f]{64}$")
        self.assertEqual(bundle.dist_root, (self.output / "dist").resolve())
        self.assertEqual(
            self.module.canonical_json(bundle),
            json.dumps(
                {
                    "archive_sha256": bundle.archive_sha256,
                    "dist_root": str(bundle.dist_root),
                    "host_version": "1.1.2",
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
                b'{"host_version":"1.1.2","product_build":"1.0.15.2"}',
            )
        checksum = self.write_checksum(
            hashlib.sha256(archive.read_bytes()).hexdigest(), archive.name
        )
        bundle = self.stage(archive, checksum)
        self.assertTrue(bundle.dist_root.is_dir())

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

        source_dist = REPO_ROOT / "build/web/host/dist"
        archive = self.root / "valid-release.zip"
        with zipfile.ZipFile(archive, "w") as output:
            for path in source_dist.rglob("*"):
                if path.is_file():
                    output.write(path, path.relative_to(source_dist.parent).as_posix())
        command = [
            sys.executable,
            str(RELEASE_BUNDLE_TOOL),
            "stage",
            "--repo-root",
            str(REPO_ROOT),
            "--archive",
            str(archive),
            "--checksum",
            "",
            "--output-root",
            str(self.output),
            "--expected-product-build",
            "1.0.15.2",
            "--expected-host-version",
            "1.1.2",
        ]
        checksum = self.write_checksum("0" * 64, archive.name)
        command[command.index("--checksum") + 1] = str(checksum)
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
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
