#!/usr/bin/env python3
"""Actual cut journal and Git squash trees, without remote/review authority."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import release_candidate_cut_test as fixture
from tools.release.candidate_source import CandidateSourceVerifier, CandidateSourceError


class SourceFixture(fixture.CutFixture):
    def setUp(self):
        super().setUp()
        self.cut_receipt = self.prepare_cut()
        self.verifier = CandidateSourceVerifier(self.cut)

    def check(self, **changes):
        arguments = dict(request=self.request, source=self.source, cut=self.cut_receipt,
                         frozen=self.fixture.frozen, main_revision=self.fixture.base)
        arguments.update(changes)
        return self.verifier.verify(**arguments)

    def commit_tree(self, tree, *parents):
        args = ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit-tree", tree]
        for parent in parents:
            args += ["-p", parent]
        return self.tool.git(*args, "-m", "fixture squash").decode().strip()

    def changed_tree(self, tree, name, raw):
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / "index"
            self.tool.git("read-tree", tree, index=index)
            oid = self.tool.git("hash-object", "-w", "--stdin", data=raw).decode().strip()
            self.tool.git("update-index", "--add", "--cacheinfo", "100644," + oid + "," + name, index=index)
            return self.tool.revision_from_index(index)


class SourceProjectionTest(SourceFixture):
    def test_original_cut_and_squash_with_docs_advance_preserve_actual_parent(self):
        before = tuple(self.tool.git(*args) for args in (("rev-parse", "HEAD"), ("write-tree",), ("show-ref",), ("status", "--porcelain")))
        self.assertIsNone(self.check()["merge_sha"])
        doc = "docs/plans/fixture.md"
        parent = self.commit_tree(self.changed_tree(self.fixture.base, doc, b"new docs"), self.fixture.base)
        merged = self.commit_tree(self.changed_tree(self.cut_receipt["tree"], doc, b"new docs"), parent)
        later = self.commit_tree(self.changed_tree(merged, "products/lmdj/later.txt", b"later change"), merged)
        proof = self.check(main_revision=later, merge_revision=merged)
        self.assertEqual(proof["merge_sha"], merged)
        self.assertEqual(proof["merge_parent"], parent)
        self.assertEqual(proof["observed_main"], later)
        self.assertEqual(before, tuple(self.tool.git(*args) for args in (("rev-parse", "HEAD"), ("write-tree",), ("show-ref",), ("status", "--porcelain"))))

    def test_squash_dropping_parent_document_is_rejected(self):
        parent = self.commit_tree(self.changed_tree(self.fixture.base, "docs/plans/fixture.md", b"preserve"), self.fixture.base)
        merged = self.commit_tree(self.cut_receipt["tree"], parent)
        with self.assertRaisesRegex(CandidateSourceError, "squash tree differs"):
            self.check(main_revision=merged, merge_revision=merged)

    def test_pre_squash_product_drift_is_rejected(self):
        parent = self.commit_tree(self.changed_tree(self.fixture.base, "products/lmdj/new-input", b"changed"), self.fixture.base)
        merged = self.commit_tree(self.changed_tree(self.cut_receipt["tree"], "products/lmdj/new-input", b"changed"), parent)
        with self.assertRaises(CandidateSourceError):
            self.check(main_revision=merged, merge_revision=merged)


class SourceBindingTest(SourceFixture):
    def test_rebound_cut_receipt_is_rejected(self):
        changed = deepcopy(self.cut_receipt)
        changed["commit"] = self.fixture.base
        with self.assertRaisesRegex(CandidateSourceError, "durable cut binding"):
            self.check(cut=changed)

    def test_unreachable_squash_is_rejected(self):
        merged = self.commit_tree(self.cut_receipt["tree"], self.fixture.base)
        with self.assertRaises(CandidateSourceError):
            self.check(merge_revision=merged)

    def test_two_parent_merge_is_not_a_squash(self):
        merged = self.commit_tree(self.cut_receipt["tree"], self.fixture.base, self.source["commit"])
        with self.assertRaisesRegex(CandidateSourceError, "distinct squash"):
            self.check(main_revision=merged, merge_revision=merged)


if __name__ == "__main__":
    unittest.main()
