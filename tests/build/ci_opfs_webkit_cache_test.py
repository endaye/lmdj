#!/usr/bin/env python3
"""The isolated OPFS WebKit survives workspace cleaning on self-hosted runners.

`scripts/prepare-opfs-webkit.sh` installs about 100 MB of WebKit. Into the
workspace alone, every web_toolchain job downloads it again because checkout
cleans `build/`; on a slow link that consumed a whole job budget (#2279, run
39007862259). With `LMDJ_BROWSER_CACHE_ROOT` set it installs into a versioned
directory beside the shared cache and links the workspace path to it. These
tests run the real script against a stubbed installer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/prepare-opfs-webkit.sh"
VERSION = "9.9.9-test"


class OpfsWebkitCacheTest(unittest.TestCase):
    def run_script(self, cache_root: str | None) -> tuple[Path, list[dict]]:
        temporary = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temporary, True)
        root = temporary / "repo"
        (root / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, root / "scripts/prepare-opfs-webkit.sh")
        playwright = root / "tests/platform/web/opfs-browser/node_modules/playwright"
        playwright.mkdir(parents=True)
        (playwright / "package.json").write_text(json.dumps({"version": VERSION}), encoding="utf-8")
        record = temporary / "installs.jsonl"
        (playwright / "cli.js").write_text(
            "const fs = require('fs');\n"
            "const target = process.env.PLAYWRIGHT_BROWSERS_PATH;\n"
            "fs.mkdirSync(target + '/webkit-test', {recursive: true});\n"
            "fs.writeFileSync(target + '/webkit-test/pw_run.sh', '');\n"
            f"fs.appendFileSync({json.dumps(str(record))}, JSON.stringify({{target, args: process.argv.slice(2)}}) + '\\n');\n",
            encoding="utf-8",
        )
        environment_check = root / "tests/platform/web/project_io/opfs_browser_environment.mjs"
        environment_check.parent.mkdir(parents=True)
        environment_check.write_text("", encoding="utf-8")
        bin_dir = temporary / "bin"
        bin_dir.mkdir()
        (bin_dir / "npm").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        (bin_dir / "npm").chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = f"{bin_dir}{os.pathsep}{environment['PATH']}"
        environment.pop("LMDJ_BROWSER_CACHE_ROOT", None)
        if cache_root is not None:
            environment["LMDJ_BROWSER_CACHE_ROOT"] = cache_root
        result = subprocess.run(
            ["bash", str(root / "scripts/prepare-opfs-webkit.sh")],
            env=environment, check=False, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        installs = [json.loads(line) for line in record.read_text(encoding="utf-8").splitlines()]
        return root, installs

    def test_self_hosted_cache_holds_the_browser_and_the_workspace_links_to_it(self) -> None:
        cache = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, cache, True)
        root, installs = self.run_script(str(cache))
        expected = cache / f"opfs-webkit-{VERSION}"
        self.assertEqual([entry["target"] for entry in installs], [str(expected)])
        self.assertEqual(installs[0]["args"], ["install", "webkit"])
        workspace = root / "build/toolchains/opfs-webkit"
        self.assertTrue(workspace.is_symlink(), "the workspace path must link to the cache")
        self.assertEqual(workspace.resolve(), expected.resolve())
        self.assertTrue((workspace / "webkit-test/pw_run.sh").exists())
        self.assertFalse((cache / "webkit-test").exists(),
                         "the OPFS browser must not land in the shared cache root")

    def test_without_a_cache_root_the_browser_stays_in_the_workspace(self) -> None:
        root, installs = self.run_script(None)
        workspace = root / "build/toolchains/opfs-webkit"
        self.assertEqual([entry["target"] for entry in installs], [str(workspace)])
        self.assertFalse(workspace.is_symlink())
        self.assertTrue((workspace / "webkit-test/pw_run.sh").exists())


if __name__ == "__main__":
    unittest.main()
