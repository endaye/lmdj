#!/usr/bin/env python3
"""One Clang/LLVM major, declared once, used everywhere.

The Core build, coverage, and sanitizer lanes pin a compiler major by name:
`CC=clang-NN`, `command -v llvm-cov-NN`, `/usr/lib/llvm-NN/bin` on PATH. Before
#693 that major appeared as a literal in five workflow blocks, two test files,
a lane manifest and two documents, and moving it meant finding every copy.
This gate reads the pin from the one place that installs it,
`scripts/ci/host/install-llvm-toolchain.sh`, and fails on any lane, manifest,
or policy document that names a different major.

Comments are excluded from the workflow scan on purpose: a comment may explain
what the Hosted image ships or what the pin used to be, and the gate must not
forbid the explanation of the thing it enforces.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SCRIPT = REPO_ROOT / "scripts/ci/host/install-llvm-toolchain.sh"

# Directive-only scan: comment lines are dropped before matching.
WORKFLOW_FILES = sorted(
    list((REPO_ROOT / ".github/workflows").glob("*.yml"))
    + list((REPO_ROOT / ".github/actions").glob("*/action.yml"))
)
# Whole-text scan: these name the pin as current state, not history.
PROSE_FILES = (
    REPO_ROOT / "docs/quality/core-test-policy.md",
    REPO_ROOT / "scripts/ci/local_lanes.json",
    REPO_ROOT / "apps/architecture-portal/docs/operations/testing-and-proof.mdx",
)

TOOL_MAJOR = re.compile(
    r"(?<![\w.])(?:clang\+\+|clang|llvm-cov|llvm-profdata|lld)-(\d+)(?![\w.])"
)
LLVM_PATH_MAJOR = re.compile(r"/usr/lib/llvm-(\d+)/")


def directives(source: str) -> str:
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )


def majors_named(text: str) -> set[str]:
    return set(TOOL_MAJOR.findall(text)) | set(LLVM_PATH_MAJOR.findall(text))


class ToolchainPinTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = INSTALL_SCRIPT.read_text(encoding="utf-8")
        match = re.search(r'^major="\$\{1:-(\d+)\}"$', source, flags=re.MULTILINE)
        assert match is not None, (
            "why: the install script no longer declares a default major, so "
            "there is no single source for the pin; remedy: keep "
            'major="${1:-NN}" in scripts/ci/host/install-llvm-toolchain.sh'
        )
        cls.pin = match.group(1)

    def test_the_pin_is_a_current_llvm_major(self) -> None:
        self.assertEqual(self.pin, "22")

    def test_every_workflow_directive_names_the_pinned_major(self) -> None:
        self.assertTrue(WORKFLOW_FILES)
        for path in WORKFLOW_FILES:
            with self.subTest(file=path.relative_to(REPO_ROOT).as_posix()):
                named = majors_named(directives(path.read_text(encoding="utf-8")))
                self.assertLessEqual(
                    named,
                    {self.pin},
                    msg=(
                        f"why: {path.relative_to(REPO_ROOT)} pins Clang/LLVM "
                        f"{sorted(named - {self.pin})} while the Core pin is "
                        f"{self.pin}, so that lane would build or measure on a "
                        "different compiler than the one the hosts carry; "
                        "remedy: name clang-NN/llvm-cov-NN/llvm-NN with the "
                        "major install-llvm-toolchain.sh installs, or move the "
                        "pin there first"
                    ),
                )

    def test_policy_and_manifests_name_the_pinned_major(self) -> None:
        for path in PROSE_FILES:
            with self.subTest(file=path.relative_to(REPO_ROOT).as_posix()):
                named = majors_named(path.read_text(encoding="utf-8"))
                self.assertLessEqual(
                    named,
                    {self.pin},
                    msg=(
                        f"why: {path.relative_to(REPO_ROOT)} documents "
                        f"Clang/LLVM {sorted(named - {self.pin})} as the pinned "
                        f"toolchain while the hosts carry {self.pin}; remedy: "
                        "update the document in the same Task that moves the pin"
                    ),
                )

    def test_the_lanes_that_depend_on_the_pin_still_name_it(self) -> None:
        """A gate that passes on an empty set would pass after the pin was deleted."""
        ci = directives((REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
        nightly = directives(
            (REPO_ROOT / ".github/workflows/core-nightly.yml").read_text(encoding="utf-8")
        )
        self.assertIn(f"CC=clang-{self.pin}", ci)
        self.assertIn(f"command -v llvm-cov-{self.pin}", ci)
        self.assertIn(f"CC=clang-{self.pin}", nightly)
        self.assertIn(f"command -v clang++-{self.pin}", nightly)


if __name__ == "__main__":
    unittest.main()
