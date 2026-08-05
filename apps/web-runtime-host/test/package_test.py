#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_TOOL = REPO_ROOT / "apps/web-runtime-host/tools/package.py"
OPERATOR_SCRIPT = REPO_ROOT / "scripts/web-runtime-host.sh"
LOCK_PATH = REPO_ROOT / "tools/web-runtime/emscripten.lock.json"
PRODUCT_VERSION_PATH = REPO_ROOT / "products/lmdj/version.json"
HOST_CMAKE_PATH = REPO_ROOT / "apps/web-runtime-host/CMakeLists.txt"


def load_package_module():
    spec = importlib.util.spec_from_file_location("lmdj_web_package", PACKAGE_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError("package module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def current_product_build() -> str:
    version = json.loads(PRODUCT_VERSION_PATH.read_text(encoding="utf-8"))
    return ".".join(
        str(version[name]) for name in ("milestone", "minor", "build", "patch")
    )


class PackageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="lmdj-web-package-")
        self.root = Path(self.temporary.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.runtime_js = self.runtime / "lmdj-web-runtime-host.js"
        self.runtime_wasm = self.runtime / "lmdj-web-runtime-host.wasm"
        self.runtime_js.write_text(
            'function findWasmBinary(){return locateFile("lmdj-web-runtime-host.wasm")}\n',
            encoding="utf-8",
            newline="\n",
        )
        self.runtime_wasm.write_bytes(b"\x00asm\x01\x00\x00\x00")
        self.identity = self.root / "toolchain-identity.json"
        identity = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        identity["emcc_version"] = (
            "emcc (Emscripten gcc/clang-like replacement + linker emulating GNU ld) "
            "6.0.5 (1db513782be24469589d7cb8a1f1834e9a33f271)"
        )
        self.identity.write_bytes(canonical_json(identity) + b"\n")
        self.dist = self.root / "dist"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_package(
        self, *extra: str, dist: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(PACKAGE_TOOL),
                "--repo-root",
                str(REPO_ROOT),
                "--runtime-root",
                str(self.runtime),
                "--identity",
                str(self.identity),
                "--dist-root",
                str(dist or self.dist),
                *extra,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_wrong_arity_is_rejected(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(PACKAGE_TOOL)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 64)
        self.assertIn("usage:", completed.stderr)

        completed = subprocess.run(
            [str(OPERATOR_SCRIPT), "clean", "unexpected"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 64)
        self.assertIn("usage:", completed.stderr)

    def test_clean_rejects_an_overridden_path_outside_the_exact_host_build(self) -> None:
        unsafe = self.root / "outside"
        unsafe.mkdir()
        marker = unsafe / "must-survive"
        marker.write_text("safe", encoding="utf-8")
        completed = subprocess.run(
            [str(OPERATOR_SCRIPT), "clean"],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "LMDJ_WEB_HOST_BUILD_ROOT": str(unsafe),
            },
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("unsafe build root", completed.stderr)
        self.assertTrue(marker.is_file())

    def test_toolchain_mismatch_fails_closed(self) -> None:
        identity = json.loads(self.identity.read_text(encoding="utf-8"))
        identity["emsdk_tag"] = "latest"
        self.identity.write_bytes(canonical_json(identity) + b"\n")
        completed = self.run_package()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("toolchain identity mismatch", completed.stderr)
        self.assertFalse(self.dist.exists())

    def test_missing_runtime_asset_fails_closed(self) -> None:
        self.runtime_wasm.unlink()
        completed = self.run_package()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("runtime asset is missing", completed.stderr)
        self.assertFalse(self.dist.exists())

    def test_existing_unowned_distribution_is_never_replaced(self) -> None:
        self.dist.mkdir()
        marker = self.dist / "must-survive"
        marker.write_text("unowned", encoding="utf-8")
        completed = self.run_package()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("existing distribution is not replaceable", completed.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "unowned")

    def test_symlink_distribution_target_is_never_followed_or_replaced(self) -> None:
        owned = self.root / "owned"
        first = self.run_package(dist=owned)
        self.assertEqual(first.returncode, 0, first.stderr)
        before = {
            path.relative_to(owned).as_posix(): path.read_bytes()
            for path in owned.rglob("*")
            if path.is_file()
        }
        self.dist.symlink_to(owned, target_is_directory=True)

        completed = self.run_package()

        self.assertEqual(completed.returncode, 2)
        self.assertIn("symlink", completed.stderr)
        self.assertTrue(self.dist.is_symlink())
        self.assertEqual(
            before,
            {
                path.relative_to(owned).as_posix(): path.read_bytes()
                for path in owned.rglob("*")
                if path.is_file()
            },
        )

    def test_failed_final_replace_rolls_back_owned_distribution_and_cleans_siblings(self) -> None:
        first = self.run_package()
        self.assertEqual(first.returncode, 0, first.stderr)
        before = {
            path.relative_to(self.dist).as_posix(): path.read_bytes()
            for path in self.dist.rglob("*")
            if path.is_file()
        }
        self.runtime_wasm.write_bytes(b"changed runtime")
        module = load_package_module()
        real_replace = os.replace
        calls = 0

        def fail_final_replace(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected final replacement failure")
            return real_replace(source, destination)

        with mock.patch.object(module.os, "replace", side_effect=fail_final_replace):
            with self.assertRaisesRegex(module.PackageError, "replacement failed"):
                module.build_distribution(
                    REPO_ROOT, self.runtime, self.identity, self.dist
                )

        self.assertEqual(
            before,
            {
                path.relative_to(self.dist).as_posix(): path.read_bytes()
                for path in self.dist.rglob("*")
                if path.is_file()
            },
        )
        self.assertEqual(
            [path.name for path in self.root.iterdir() if path.name.startswith(".lmdj-web-dist-")],
            [],
        )

    def test_every_template_rewrite_requires_exactly_one_match(self) -> None:
        module = load_package_module()
        self.assertEqual(
            module.replace_exact_once("before TOKEN after", "TOKEN", "value", "fixture"),
            "before value after",
        )
        for source in ("no match", "TOKEN and TOKEN"):
            with self.subTest(source=source):
                with self.assertRaisesRegex(module.PackageError, "exactly once"):
                    module.replace_exact_once(source, "TOKEN", "value", "fixture")

    def test_operator_proof_declares_clean_build_reproducibility_gate(self) -> None:
        script = OPERATOR_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("Web Runtime Host reproducibility: PASS", script)
        self.assertIn("trap cleanup_all EXIT", script)
        self.assertIn("trap 'exit 130' INT", script)
        self.assertIn("trap 'exit 143' TERM", script)

    def test_pre_js_declares_configure_and_link_dependencies(self) -> None:
        cmake = HOST_CMAKE_PATH.read_text(encoding="utf-8")
        self.assertRegex(
            cmake,
            r"CMAKE_CONFIGURE_DEPENDS[\s\S]*?src/web-runtime-pre\.js",
        )
        self.assertRegex(
            cmake,
            r"LINK_DEPENDS[\s\S]*?lmdj_web_runtime_pre_js_path",
        )

    def test_operator_term_cleans_owned_server_pid_and_ready_directory(self) -> None:
        packaged = self.run_package()
        self.assertEqual(packaged.returncode, 0, packaged.stderr)
        harness = REPO_ROOT / "scripts/.web-runtime-host-signal-test.sh"
        fake_bin = self.root / "signal-fake-bin"
        fake_bin.mkdir()
        started = self.root / "npm-started"
        fake_npm = fake_bin / "npm"
        fake_npm.write_text(
            "#!/usr/bin/env bash\n"
            'touch "$LMDJ_OPERATOR_NPM_STARTED"\n'
            "sleep 2\n",
            encoding="utf-8",
        )
        fake_npm.chmod(0o755)
        operator_tmp = self.root / "operator-tmp"
        operator_tmp.mkdir()
        script = OPERATOR_SCRIPT.read_text(encoding="utf-8")
        prefix, separator, _ = script.partition("\n[[ $# -ge 1 ]] ||")
        self.assertTrue(separator)
        harness.write_text(
            prefix
            + "\nrequire_playwright() { :; }\n"
            + 'run_browser_gate "$1"\n',
            encoding="utf-8",
            newline="\n",
        )
        harness.chmod(0o755)
        process = subprocess.Popen(
            [str(harness), str(self.dist)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={
                **os.environ,
                "LMDJ_OPERATOR_NPM_STARTED": str(started),
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                "TMPDIR": str(operator_tmp),
            },
        )
        server_pid = None
        try:
            for _ in range(200):
                ready_files = list(operator_tmp.glob("lmdj-web-host-server.*/ready.json"))
                if started.is_file() and ready_files:
                    server_pid = json.loads(
                        ready_files[0].read_text(encoding="utf-8")
                    )["pid"]
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.025)
            self.assertIsNone(process.poll())
            self.assertIsNotNone(server_pid)
            process.send_signal(signal.SIGTERM)
            self.assertEqual(process.wait(timeout=8), 143)
            with self.assertRaises(ProcessLookupError):
                os.kill(server_pid, 0)
            self.assertEqual(list(operator_tmp.iterdir()), [])
        finally:
            harness.unlink(missing_ok=True)
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

    def test_browser_gate_never_accepts_an_old_server_on_the_requested_port(self) -> None:
        packaged = self.run_package()
        self.assertEqual(packaged.returncode, 0, packaged.stderr)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        old_server = subprocess.Popen(
            [
                sys.executable,
                str(REPO_ROOT / "apps/web-runtime-host/tools/server.py"),
                "--root",
                str(self.dist),
                "--port",
                str(port),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        harness = REPO_ROOT / "scripts/.web-runtime-host-gate-test.sh"
        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        fake_npm = fake_bin / "npm"
        fake_npm.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        fake_npm.chmod(0o755)
        script = OPERATOR_SCRIPT.read_text(encoding="utf-8")
        prefix, separator, _ = script.partition("\n[[ $# -ge 1 ]] ||")
        self.assertTrue(separator)
        harness.write_text(
            prefix
            + "\nrequire_playwright() { :; }\n"
            + 'run_browser_gate "$1"\n',
            encoding="utf-8",
            newline="\n",
        )
        harness.chmod(0o755)
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/index.html", timeout=0.2
                    ).read()
                    break
                except OSError:
                    if old_server.poll() is not None:
                        break
                    time.sleep(0.05)
            self.assertIsNone(old_server.poll())
            completed = subprocess.run(
                [str(harness), str(self.dist)],
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "LMDJ_WEB_HOST_PORT": str(port),
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                },
                timeout=15,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("proof server did not become ready", completed.stderr)
        finally:
            harness.unlink(missing_ok=True)
            old_server.terminate()
            try:
                old_server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                old_server.kill()
                old_server.wait(timeout=5)
            if old_server.stdout is not None:
                old_server.stdout.close()
            if old_server.stderr is not None:
                old_server.stderr.close()

    def test_package_is_deterministic_and_binds_every_required_identity(self) -> None:
        first = self.run_package()
        self.assertEqual(first.returncode, 0, first.stderr)
        first_inventory = {
            path.relative_to(self.dist).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(self.dist.rglob("*"))
            if path.is_file()
        }
        second = self.run_package()
        self.assertEqual(second.returncode, 0, second.stderr)
        second_inventory = {
            path.relative_to(self.dist).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(self.dist.rglob("*"))
            if path.is_file()
        }
        self.assertEqual(second_inventory, first_inventory)

        manifest_bytes = (self.dist / "host-manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        self.assertEqual(manifest_bytes, canonical_json(manifest))
        self.assertEqual(
            set(manifest),
            {
                "assets",
                "distribution_contract",
                "emscripten",
                "heap_bytes",
                "host_version",
                "manifest_version",
                "product_build",
                "protocol_version",
                "resource_limits",
            },
        )
        self.assertEqual(
            manifest["distribution_contract"],
            "lmdj.web-runtime-host.distribution.v1",
        )
        self.assertEqual(manifest["manifest_version"], 1)
        self.assertEqual(manifest["product_build"], current_product_build())
        self.assertEqual(manifest["host_version"], "1.0.0")
        self.assertEqual(manifest["protocol_version"], 1)
        self.assertEqual(manifest["heap_bytes"], 536_870_912)
        self.assertEqual(
            manifest["resource_limits"],
            {
                "decoded_float_pcm_bytes_per_bank": 67_108_864,
                "decoded_float_pcm_bytes_total": 134_217_728,
                "decoded_frames_per_pad": 240_000,
                "imported_wav_bytes": 1_048_576,
            },
        )
        identity = json.loads(self.identity.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["emscripten"],
            {
                "emcc_version": identity["emcc_version"],
                "emscripten_releases_revision": identity[
                    "emscripten_releases_revision"
                ],
                "emsdk_revision": identity["emsdk_revision"],
                "emsdk_tag": identity["emsdk_tag"],
            },
        )

        roles = {asset["role"] for asset in manifest["assets"]}
        self.assertEqual(len(manifest["assets"]), 9)
        self.assertEqual(
            roles,
            {
                "host_main",
                "host_module",
                "host_style",
                "runtime_script",
                "runtime_wasm",
            },
        )
        self.assertEqual(
            [(Path(asset["path"]).name.split(".", 1)[0], asset["role"])
             for asset in manifest["assets"]],
            [
                ("diagnostic-project", "host_module"),
                ("input-adapters", "host_module"),
                ("main", "host_main"),
                ("preflight", "host_module"),
                ("protocol", "host_module"),
                ("runtime", "runtime_script"),
                ("runtime", "runtime_wasm"),
                ("state-machine", "host_module"),
                ("styles", "host_style"),
            ],
        )
        diagnostic_modules = [
            asset for asset in manifest["assets"]
            if re.fullmatch(
                r"assets/diagnostic-project\.[0-9a-f]{64}\.mjs",
                asset["path"],
            )
        ]
        self.assertEqual(len(diagnostic_modules), 1)
        self.assertFalse(any(self.dist.rglob("*.wav")))
        for asset in manifest["assets"]:
            self.assertEqual(set(asset), {"bytes", "path", "role", "sha256"})
            self.assertRegex(
                asset["path"],
                r"^assets/[a-z0-9-]+\.[0-9a-f]{64}\.(?:css|js|mjs|wasm)$",
            )
            path = self.dist / asset["path"]
            payload = path.read_bytes()
            self.assertGreater(asset["bytes"], 0)
            self.assertEqual(asset["bytes"], len(payload))
            self.assertEqual(asset["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertIn(f'.{asset["sha256"]}.', Path(asset["path"]).name)

        index = (self.dist / "index.html").read_text(encoding="utf-8")
        digest = hashlib.sha256(manifest_bytes).hexdigest()
        self.assertIn(
            f'<meta name="lmdj-host-manifest-sha256" content="{digest}">',
            index,
        )
        self.assertIn(
            '<meta name="lmdj-host-manifest-path" content="./host-manifest.json">',
            index,
        )
        self.assertIn(
            f'<meta name="lmdj-product-build" content="{current_product_build()}">',
            index,
        )
        self.assertIn(
            '<meta name="lmdj-host-version" content="1.0.0">', index
        )
        self.assertIn(
            '<meta name="lmdj-host-protocol-version" content="1">', index
        )
        self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)[^>]*>", index, re.I))


if __name__ == "__main__":
    unittest.main()
