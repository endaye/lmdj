#!/usr/bin/env python3
"""Real passive Git histories; no candidate allocation or external authority."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.release.candidate_inputs import CandidateInputs, CandidateInputError, VERSION
from tools.release.model import canonical_json


class CandidateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.version = {"contract":"lmdj.product-version.v1", "product":"lmdj",
                        "milestone":1, "minor":0, "build":57, "patch":0}
        self.write(VERSION, canonical_json(self.version))
        for filename in ("products/lmdj/assembly.lock.json", "packages/core/src/a.cpp",
                         "apps/creator-web/src/a.ts", "docs/guide.md"):
            self.write(filename, b"fixture\n")
        self.base = self.commit()
        self.reader = CandidateInputs(self.root)
        self.frozen = self.reader.freeze(self.base)

    def git(self, *args):
        env = {k:v for k,v in os.environ.items() if k in ("PATH", "TMPDIR", "TEMP", "TMP")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        result = subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull,
                                 "-C", str(self.root), *args], env=env,
                                capture_output=True, check=True)
        return result.stdout.decode().strip()

    def write(self, name, raw):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-m", "fixture")
        return self.git("rev-parse", "HEAD")

    def test_unchanged_and_docs_only_main_preserve_original_inputs(self):
        self.assertEqual(self.reader.verify(self.frozen, self.base)["observed_main"], self.base)
        for name in ("docs/guide.md", "docs/plans/new.md", "apps/docs-site/docs/guide.mdx",
                     "apps/docs-site/diagrams/a.mmd", "apps/docs-site/static/diagrams/a.svg"):
            self.write(name, b"new documentation\n")
        main = self.commit()
        before = (self.git("status", "--porcelain"), self.git("show-ref"))
        result = self.reader.verify(self.frozen, main)
        self.assertEqual((result["base_revision"], result["observed_main"]), (self.base, main))
        self.assertEqual(result["product_build"], "1.0.57.0")
        self.assertEqual(before, (self.git("status", "--porcelain"), self.git("show-ref")))
        self.assertEqual(self.reader.freeze(self.base), self.frozen)

    def test_source_changes_refuse_even_when_assembly_lock_is_identical(self):
        lock = self.git("rev-parse", self.base + ":products/lmdj/assembly.lock.json")
        for index, name in enumerate(("packages/core/src/a.cpp", "apps/creator-web/src/a.ts")):
            with self.subTest(name=name):
                self.git("checkout", "-b", "source-" + str(index), self.base)
                self.write(name, b"changed implementation\n")
                main = self.commit()
                self.assertEqual(self.git("rev-parse", main + ":products/lmdj/assembly.lock.json"), lock)
                with self.assertRaisesRegex(CandidateInputError, "changed since"):
                    self.reader.verify(self.frozen, main)

    def test_allocation_evidence_build_inputs_and_unknown_paths_are_not_docs(self):
        for name in ("products/lmdj/version.json", "docs/release-evidence/release-intents.json",
                     "docs/governance/version-management.md", "apps/docs-site/versioned_metadata/version-1.0.57.0.json",
                     "docs/quality/core-test-policy.md", "docs/quality/acceptance.md",
                     "apps/docs-site/scripts/build.mjs", "scripts/build.sh", "CMakeLists.txt",
                     "third_party/library.c", "unknown-input"):
            with self.subTest(name=name):
                self.git("checkout", "-b", "case-" + str(len(self.git("branch").splitlines())), self.base)
                raw = canonical_json({**self.version, "build":58}) if name == VERSION else b"new input\n"
                self.write(name, raw)
                main = self.commit()
                with self.assertRaisesRegex(CandidateInputError, "changed since"):
                    self.reader.verify(self.frozen, main)

    def test_deletion_changes_input_inventory(self):
        (self.root / "packages/core/src/a.cpp").unlink()
        main = self.commit()
        with self.assertRaisesRegex(CandidateInputError, "changed since"):
            self.reader.verify(self.frozen, main)

    def test_linked_document_source_and_directory_are_frozen(self):
        for index, target in enumerate(("../../../docs/source.cpp", "../../../docs")):
            with self.subTest(target=target):
                self.git("checkout", "-b", "linked-" + str(index), self.base)
                self.write("docs/source.cpp", b"int x=1;\n")
                (self.root / "packages/core/src/linked.cpp").symlink_to(target)
                base = self.commit()
                frozen = self.reader.freeze(base)
                self.reader.verify(frozen, base)
                self.write("docs/source.cpp", b"int x=2;\n")
                with self.assertRaisesRegex(CandidateInputError, "changed since"):
                    self.reader.verify(frozen, self.commit())

    def test_unsafe_link_targets_refuse(self):
        for index, target in enumerate(("/tmp/external", "../../../../outside", "missing",
                                        "a.cpp/../a.cpp", "linked.cpp", "..")):
            with self.subTest(target=target):
                self.git("checkout", "-b", "unsafe-" + str(index), self.base)
                (self.root / "packages/core/src/linked.cpp").symlink_to(target)
                with self.assertRaisesRegex(CandidateInputError, "symlink"):
                    self.reader.freeze(self.commit())

    def test_executable_mode_is_part_of_input_identity(self):
        self.git("update-index", "--chmod=+x", "packages/core/src/a.cpp")
        self.git("commit", "-m", "mode")
        with self.assertRaisesRegex(CandidateInputError, "changed since"):
            self.reader.verify(self.frozen, self.git("rev-parse", "HEAD"))

    def test_dirty_worktree_is_not_committed_version_truth(self):
        self.write(VERSION, b"untrusted local content")
        self.assertEqual(self.reader.freeze(self.base), self.frozen)
        self.assertEqual((self.root / VERSION).read_bytes(), b"untrusted local content")

    def test_forged_frozen_record_cannot_select_another_projection(self):
        for key in ("product_build", "projection_sha256", "base_tree", "entries"):
            with self.subTest(key=key):
                frozen = deepcopy(self.frozen)
                frozen[key] = [] if key == "entries" else "f" * 40
                with self.assertRaisesRegex(CandidateInputError, "baseline was changed"):
                    self.reader.verify(frozen, self.base)

    def test_missing_or_noncommit_revision_is_refused(self):
        for revision in ("main", "f" * 40, self.frozen["base_tree"]):
            with self.subTest(revision=revision), self.assertRaises(CandidateInputError):
                self.reader.freeze(revision)

    def test_divergent_history_is_not_current_main(self):
        self.write("docs/guide.md", b"first\n")
        first = self.commit()
        frozen = self.reader.freeze(first)
        self.git("checkout", "-b", "sibling", self.base)
        self.write("docs/guide.md", b"second\n")
        second = self.commit()
        with self.assertRaisesRegex(CandidateInputError, "ancestry"):
            self.reader.verify(frozen, second)

    def test_replace_refs_do_not_rewrite_frozen_history(self):
        self.write("packages/core/src/a.cpp", b"changed\n")
        newer = self.commit()
        self.git("replace", self.base, newer)
        self.assertEqual(self.reader.freeze(self.base), self.frozen)

    def test_shallow_history_is_not_complete_input_proof(self):
        self.write(".git/shallow", (self.base + "\n").encode())
        with self.assertRaisesRegex(CandidateInputError, "shallow"):
            self.reader.freeze(self.base)

    def test_product_version_uses_canonical_manifest_validation(self):
        for document in ({**self.version, "build":True}, {**self.version, "product":"other"},
                         {**self.version, "extra":1}):
            self.write(VERSION, canonical_json(document))
            main = self.commit()
            with self.assertRaises(CandidateInputError): self.reader.freeze(main)

    def test_duplicate_manifest_keys_are_not_accepted(self):
        raw = canonical_json(self.version)
        self.write(VERSION, b'{"build":99,' + raw[1:])
        main = self.commit()
        with self.assertRaises(CandidateInputError): self.reader.freeze(main)

    def test_missing_blob_is_not_hydrated_or_accepted(self):
        oid = self.git("rev-parse", self.base + ":packages/core/src/a.cpp")
        filename = self.root / ".git/objects" / oid[:2] / oid[2:]
        filename.rename(filename.with_name(filename.name + ".retained"))
        with self.assertRaisesRegex(CandidateInputError, "blobs are missing"):
            self.reader.freeze(self.base)


if __name__ == "__main__":
    unittest.main()
