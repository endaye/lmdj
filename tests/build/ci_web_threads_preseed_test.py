#!/usr/bin/env python3
"""Contract tests: Emscripten configures pre-seed the FindThreads result.

`find_package(Threads REQUIRED)` try-compiles a `-pthread` probe on every
configure. Under Emscripten the probe's answer is constant, but the probe
invokes emcc against the shared emsdk cache while sibling CI jobs link
against it, and the concurrent cache-metadata access intermittently fails
the probe and the whole wasm configure (issue #1783). Every Emscripten
configure therefore loads `tools/web-runtime/emscripten-threads-cache-init.cmake`,
which records the constant results so FindThreads never try-compiles on that
toolchain. Native configures must never load the file: their real probe is
the only thing that can answer the question there.
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
PRESEED = REPO_ROOT / "tools/web-runtime/emscripten-threads-cache-init.cmake"
PRESEED_RELATIVE = "tools/web-runtime/emscripten-threads-cache-init.cmake"
EMCMAKE_INVOCATION = re.compile(r"^\s*emcmake cmake\s*\\")
# Scripts whose proof lanes run Emscripten configures, mapped to the exact
# number of `emcmake cmake` invocations each one owns. A new invocation that
# is not counted here fails closed instead of configuring without the seed.
EMSCRIPTEN_PROOF_SCRIPTS = {
    "scripts/web-toolchain-conformance.sh": 3,
    "scripts/web-runtime-host.sh": 1,
    "scripts/creator-web.sh": 1,
}


def command_blocks(text: str, start: re.Pattern[str]) -> list[str]:
    """Return each logical (continuation-joined) command matching start."""
    blocks: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if start.search(lines[index]):
            end = index
            while lines[end].rstrip().endswith("\\"):
                end += 1
            blocks.append("\n".join(lines[index : end + 1]))
            index = end + 1
        else:
            index += 1
    return blocks


class PreseedFileContent(unittest.TestCase):
    def test_records_every_constant_findthreads_result(self) -> None:
        directives = "\n".join(
            line
            for line in PRESEED.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        for expected in (
            'set(THREADS_PREFER_PTHREAD_FLAG ON CACHE BOOL "")',
            'set(THREADS_HAVE_PTHREAD_ARG TRUE CACHE BOOL "")',
            'set(CMAKE_HAVE_LIBC_PTHREAD FALSE CACHE INTERNAL "")',
        ):
            self.assertIn(
                expected,
                directives,
                f"{expected} missing: without it FindThreads still "
                "try-compiles a probe that races concurrent CI jobs on the "
                "shared emsdk cache (#1783)",
            )


class EmscriptenConfiguresLoadThePreseed(unittest.TestCase):
    def test_every_emcmake_invocation_loads_the_preseed(self) -> None:
        for relative, count in EMSCRIPTEN_PROOF_SCRIPTS.items():
            text = (REPO_ROOT / relative).read_text(encoding="utf-8")
            blocks = command_blocks(text, EMCMAKE_INVOCATION)
            with self.subTest(script=relative):
                self.assertEqual(
                    len(blocks),
                    count,
                    f"{relative} owns {len(blocks)} `emcmake cmake` "
                    f"invocations, expected {count}: count them in "
                    "EMSCRIPTEN_PROOF_SCRIPTS and load the pre-seed in the "
                    "new one, or remove the stale entry",
                )
                for block in blocks:
                    self.assertIn(
                        f'-C "$repo_root/{PRESEED_RELATIVE}"',
                        block,
                        f"Emscripten configure without the Threads pre-seed "
                        f"reopens the shared-emsdk-cache probe race (#1783): "
                        f"{block}",
                    )


class NativeConfiguresNeverLoadThePreseed(unittest.TestCase):
    def test_only_the_emscripten_proof_scripts_reference_the_preseed(self) -> None:
        tracked = subprocess.run(
            ["git", "grep", "-l", PRESEED_RELATIVE, "--", ":!tests/build"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
        self.assertEqual(
            sorted(tracked),
            sorted(EMSCRIPTEN_PROOF_SCRIPTS),
            "the pre-seed must stay inside the Emscripten configure path; a "
            "native configure loading it would silently skip the real "
            "FindThreads probe (#1783)",
        )


if __name__ == "__main__":
    unittest.main()
