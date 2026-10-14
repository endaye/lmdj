#!/usr/bin/env python3
"""One Wrangler, locked once, installed the same way everywhere.

Every Cloudflare deploy workflow hands Wrangler the deploy token. Before this
gate each one ran `npm install` of a hard-coded version with no lockfile, so
Wrangler's transitive dependencies resolved at run time and their install
scripts ran on the runner. The version was also copied into the upload adapter
and the deploy runbooks, and changing it meant finding every copy.

`tools/wrangler/package.json` and its lockfile are now the single source. This
gate fails when a workflow installs Wrangler any other way, when the lockfile
disagrees with the manifest, or when a current source names a Wrangler version
instead of reading the manifest. Frozen Portal snapshots are history and keep
the version they were cut with.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tools/wrangler/package.json"
LOCKFILE = ROOT / "tools/wrangler/package-lock.json"
FROZEN_SNAPSHOTS = "apps/architecture-portal/versioned_docs/"

# A Wrangler version named in a source: `wrangler@4.1.0`, `Wrangler 4.1.0`.
VERSION_LITERAL = re.compile(r"(?i)wrangler[ @]v?\d+\.\d+\.\d+")
WRANGLER_MODULE = re.compile(r"(\S*)/node_modules/wrangler/bin/wrangler\.js")
LOCKED_INSTALL = re.compile(
    r'(?m)^ +cp tools/wrangler/package\.json tools/wrangler/package-lock\.json "(?P<dir>[^"]+)/"\n'
    r' +npm ci --prefix "(?P=dir)" --ignore-scripts --no-audit --no-fund$'
)
WORKFLOW_EXPRESSIONS = {"${{ runner.temp }}": "$RUNNER_TEMP", "${{ github.run_id }}": "$GITHUB_RUN_ID"}


def directives(source: str) -> str:
    """Comments may explain the old install; only directives are policed."""
    return "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))


def shell_path(source: str) -> str:
    """Spell workflow expressions as the shell variables the install step uses."""
    for expression, variable in WORKFLOW_EXPRESSIONS.items():
        source = source.replace(expression, variable)
    return source


def wrangler_workflows() -> dict[str, str]:
    workflows = {}
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        source = directives(path.read_text(encoding="utf-8"))
        if re.search(r"(?i)wrangler", source.replace("wrangler.json", "")):
            workflows[path.name] = source
    return workflows


class LockedManifestTest(unittest.TestCase):
    def test_manifest_locks_exactly_one_exact_wrangler(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertTrue(manifest.get("private"), "why: the tool manifest must never publish; remedy: keep private: true")
        self.assertEqual(set(manifest.get("dependencies", {})), {"wrangler"},
                         "why: the manifest exists only to lock Wrangler; remedy: depend on wrangler alone")
        self.assertNotIn("devDependencies", manifest,
                         "why: a production-mode npm ci omits devDependencies; remedy: list wrangler in dependencies")
        self.assertRegex(manifest["dependencies"]["wrangler"], r"^\d+\.\d+\.\d+$",
                         "why: a range lets the lockfile and the version check disagree; remedy: pin one exact version")

    def test_lockfile_resolves_the_manifest_from_the_public_registry(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        lock = json.loads(LOCKFILE.read_text(encoding="utf-8"))
        self.assertEqual(lock["lockfileVersion"], 3)
        self.assertEqual(lock["packages"][""]["dependencies"], manifest["dependencies"],
                         "why: npm ci refuses a lockfile that disagrees with its manifest; remedy: regenerate it "
                         "with npm install --package-lock-only --ignore-scripts in tools/wrangler")
        self.assertEqual(lock["packages"]["node_modules/wrangler"]["version"], manifest["dependencies"]["wrangler"])
        for name, entry in lock["packages"].items():
            if not name:
                continue
            with self.subTest(package=name):
                self.assertTrue(entry.get("resolved", "").startswith("https://registry.npmjs.org/"), entry)
                self.assertTrue(entry.get("integrity", "").startswith("sha512-"), entry)


class WorkflowInstallTest(unittest.TestCase):
    def test_the_scan_finds_every_known_wrangler_workflow(self):
        self.assertEqual(set(wrangler_workflows()), {
            "cloudflare-preview-publish.yml", "deploy-cloudflare-portal.yml", "deploy-creator-web.yml",
            "deploy-default-assets.yml", "deploy-web-runtime-host.yml"})

    def test_workflows_install_wrangler_only_from_the_locked_manifest(self):
        for name, source in wrangler_workflows().items():
            with self.subTest(workflow=name):
                installs = {match["dir"] for match in LOCKED_INSTALL.finditer(source)}
                self.assertEqual(len(installs), 1,
                                 "why: Wrangler receives the deploy token and must come from one locked install "
                                 "without install scripts; remedy: copy tools/wrangler's package.json and "
                                 "package-lock.json into one directory and npm ci --ignore-scripts there")
                self.assertNotRegex(source, r"npm (?:install|i|add)\b[^\n]*wrangler|npx[^\n]*wrangler",
                                    "why: an unlocked install resolves dependencies at run time; remedy: use the "
                                    "locked npm ci install")
                modules = {match.strip('"') for match in WRANGLER_MODULE.findall(shell_path(source))}
                self.assertTrue(modules, "why: the workflow never runs the installed Wrangler")
                self.assertEqual(modules, installs,
                                 "why: the workflow runs a Wrangler other than the one it installed from the lock; "
                                 "remedy: point every wrangler.js path at the npm ci prefix")


class SingleSourceTest(unittest.TestCase):
    def test_no_current_source_names_a_wrangler_version(self):
        listed = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], check=True, capture_output=True)
        offenders = []
        for name in listed.stdout.decode().split("\0"):
            if not name or name.startswith(FROZEN_SNAPSHOTS) or name == "tests/build/ci_wrangler_lock_test.py":
                continue
            path = ROOT / name
            if not path.is_file() or path.is_symlink():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            offenders += [f"{name}: {match}" for match in VERSION_LITERAL.findall(text)]
        self.assertEqual(offenders, [],
                         "why: a copied Wrangler version drifts from the lock; remedy: refer to tools/wrangler "
                         "instead of naming the version (frozen Portal snapshots are exempt)")

    def test_the_upload_adapter_reads_the_version_from_the_manifest(self):
        version = json.loads(MANIFEST.read_text(encoding="utf-8"))["dependencies"]["wrangler"]
        adapter = (ROOT / "apps/web-runtime-host/tools/cloudflare_host.py").read_text(encoding="utf-8")
        self.assertIn("tools/wrangler/package.json", adapter)
        self.assertNotIn(version, adapter,
                         "why: the adapter's own copy of the version drifts from the lock; remedy: read it "
                         "through locked_wrangler_version()")


if __name__ == "__main__":
    unittest.main()
