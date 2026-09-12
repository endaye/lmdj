"""Exercise firmware identity derivation through the real CMake include."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class IdentityTest(unittest.TestCase):
    def run_identity(self, *, locked_build="9.8.7.6", host="3.2.1",
                     locked_host="3.2.1", missing_host=False, bad_digest=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            product = root / "products/lmdj"
            app = root / "apps/cardputer-host"
            product.mkdir(parents=True)
            app.mkdir(parents=True)
            assembly = b'{"fixture":true}\n'
            digest = hashlib.sha256(assembly).hexdigest()
            (product / "assembly.json").write_bytes(assembly)
            (product / "version.json").write_text(json.dumps(
                dict(milestone=9, minor=8, build=7, patch=6)))
            (app / "module.json").write_text(json.dumps(dict(version=host)))
            (product / "assembly.lock.json").write_text(json.dumps(dict(
                assembly_sha256="0" * 64 if bad_digest else digest,
                product=dict(version=locked_build),
                hosts=[] if missing_host else [dict(id="cardputer-host", version=locked_host)])))
            script = root / "probe.cmake"
            script.write_text(
                f'include("{ROOT / "apps/cardputer-host/identity.cmake"}")\n'
                'message(STATUS "IDENTITY=${LMDJ_CARDPUTER_PRODUCT_BUILD}|'
                '${LMDJ_CARDPUTER_HOST_VERSION}|${LMDJ_CARDPUTER_ASSEMBLY_SHA256}")\n')
            result = subprocess.run(["cmake", f"-DLMDJ_SOURCE_ROOT={root}",
                                     "-P", str(script)], capture_output=True, text=True)
            return result, digest

    def test_uses_supplied_manifests_not_literal_versions(self):
        result, digest = self.run_identity()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"IDENTITY=9.8.7.6|3.2.1|{digest}", result.stdout)

    def test_rejects_stale_product_version(self):
        result, _ = self.run_identity(locked_build="9.8.7.5")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("identity manifests disagree", result.stderr)

    def test_rejects_changed_assembly_bytes(self):
        result, _ = self.run_identity(bad_digest=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("identity manifests disagree", result.stderr)

    def test_rejects_stale_host_version(self):
        result, _ = self.run_identity(locked_host="3.2.0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Host version differs", result.stderr)

    def test_rejects_missing_host(self):
        result, _ = self.run_identity(missing_host=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Host is absent", result.stderr)


if __name__ == "__main__":
    unittest.main()
