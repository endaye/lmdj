#!/usr/bin/env python3
"""Policy data exempted as classification-inert must stay unread by the classifier.

`change_scope.py` exempts `CLASSIFICATION_INERT_POLICY_PATHS` from the
`scripts/ci/` full upgrade unconditionally. That exemption rests on a claim
about the file's role rather than on a computed differential: nothing which
decides lanes reads it, so editing it cannot change what runs.

A claim of that shape is the kind that goes stale silently. This repository has
no human reviewer to notice when it does, so it is held by a gate instead of by
a sentence in a document. Add a read of one of these files from a
classification module and this test fails, which is the moment the exemption
stops being true.

Limitation, stated rather than left implicit: this matches a literal reference
to the filename, which is how such a dependency would in practice be written.
A path assembled at runtime would evade it. That gap is accepted; closing it
would mean tracing file handles through the classifier, which costs more than
the risk it removes.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts/ci"))

from change_scope import CLASSIFICATION_INERT_POLICY_PATHS  # noqa: E402

# Everything that participates in deciding which lanes a change selects. The
# CLI, the pure classifier and the local mirror of it all live here; a new
# module that reaches the manifest belongs in this list.
CLASSIFICATION_MODULES = (
    "scripts/ci/change_scope.py",
    "scripts/ci/local_preflight.py",
)


def _source_without_the_declaration(module: Path) -> str:
    """Module source with the exemption list itself removed.

    The declaration necessarily names the paths it exempts, so scanning the
    raw source would always match. Only uses outside the declaration are
    reads, and reads are what this test bans.
    """
    source = module.read_text(encoding="utf-8")
    return re.sub(
        r"CLASSIFICATION_INERT_POLICY_PATHS = frozenset\(\{.*?\}\)",
        "",
        source,
        flags=re.DOTALL,
    )


class ClassificationInputsTest(unittest.TestCase):
    def test_inert_policy_files_exist(self) -> None:
        """An exemption for a file that is gone records nothing."""
        for relative in sorted(CLASSIFICATION_INERT_POLICY_PATHS):
            with self.subTest(path=relative):
                self.assertTrue(
                    (REPO_ROOT / relative).is_file(),
                    msg=(
                        f"why: {relative} is exempted from the scripts/ci/ full "
                        "upgrade as classification-inert, but the file does not "
                        "exist, so the exemption describes nothing; remedy: "
                        "remove it from CLASSIFICATION_INERT_POLICY_PATHS in the "
                        "same change that removed or moved the file"
                    ),
                )

    def test_no_classification_module_reads_an_inert_policy_file(self) -> None:
        for module in CLASSIFICATION_MODULES:
            source = _source_without_the_declaration(REPO_ROOT / module)
            for relative in sorted(CLASSIFICATION_INERT_POLICY_PATHS):
                stem = Path(relative).name
                with self.subTest(module=module, path=relative):
                    self.assertNotIn(
                        stem,
                        source,
                        msg=(
                            f"why: {module} references {stem}, but {relative} is "
                            "exempted from the scripts/ci/ full upgrade on the "
                            "grounds that no module deciding lanes reads it; a "
                            "classification result depending on it would change "
                            "silently while the edit still looked exempt; remedy: "
                            "either remove the dependency, or drop the path from "
                            "CLASSIFICATION_INERT_POLICY_PATHS so its edits select "
                            "the full manifest again"
                        ),
                    )

    def test_the_declared_modules_are_the_ones_that_classify(self) -> None:
        """The list above is the test's own blind spot if it goes stale."""
        for module in CLASSIFICATION_MODULES:
            with self.subTest(module=module):
                self.assertTrue((REPO_ROOT / module).is_file())
        classifier = (REPO_ROOT / "scripts/ci/change_scope.py").read_text(encoding="utf-8")
        self.assertIn(
            "def classify(",
            classifier,
            msg=(
                "why: this test assumes scripts/ci/change_scope.py is where lane "
                "selection is decided; if that moved, the module list no longer "
                "covers the classifier and the exemption is unguarded; remedy: "
                "update CLASSIFICATION_MODULES to name wherever classify now lives"
            ),
        )


if __name__ == "__main__":
    unittest.main()
