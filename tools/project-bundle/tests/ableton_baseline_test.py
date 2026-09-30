"""Synthetic parser tests are not native Live templates or DAW acceptance."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import gzip
import hashlib
import importlib.util
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest


TOOL = Path(__file__).resolve().parents[1] / "ableton_baseline.py"
SPEC = importlib.util.spec_from_file_location("ableton_baseline", TOOL)
baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(baseline)


class BaselineInspectionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def capture(self, xml=b'<Ableton Creator="Ableton Live 12.0.1"><Synthetic /></Ableton>',
                suffix=".adg", encoded=None):
        source = self.directory / ("synthetic" + suffix)
        data = gzip.compress(xml, mtime=0) if encoded is None else encoded
        source.write_bytes(data)
        return source, hashlib.sha256(data).hexdigest()

    def test_inspection_binds_complete_file_and_xml_identity(self):
        xml = b'<Ableton Creator="Ableton Live 12.0.1"><Synthetic /></Ableton>'
        source, digest = self.capture(xml)
        result = baseline.inspect_template(source, digest)
        self.assertEqual(result["sha256"], digest)
        self.assertEqual(result["byte_length"], source.stat().st_size)
        self.assertEqual(result["xml_sha256"], hashlib.sha256(xml).hexdigest())
        self.assertEqual(result["xml_byte_length"], len(xml))
        self.assertEqual(result["element_counts"], {"Ableton": 1, "Synthetic": 1})

    def test_changed_bytes_refuse_original_digest(self):
        source, digest = self.capture()
        source.write_bytes(source.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            baseline.inspect_template(source, digest)

    def test_invalid_expected_digest_refused(self):
        source, _ = self.capture()
        with self.assertRaisesRegex(ValueError, "invalid expected SHA-256"):
            baseline.inspect_template(source, "ABC")

    def test_other_extension_refused(self):
        source, digest = self.capture(suffix=".xml")
        with self.assertRaisesRegex(ValueError, "unsupported baseline extension"):
            baseline.inspect_template(source, digest)

    def test_encoded_size_limit(self):
        source, digest = self.capture(encoded=b"x" * (baseline.MAX_TEMPLATE_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "baseline exceeds 32 MiB"):
            baseline.inspect_template(source, digest)

    def test_plain_xml_is_not_a_native_gzip_baseline(self):
        source, digest = self.capture(encoded=b'<Ableton Creator="Ableton Live 12.0.1" />')
        with self.assertRaisesRegex(ValueError, "not gzip"):
            baseline.inspect_template(source, digest)

    def test_corrupt_gzip_trailer_refused(self):
        data = bytearray(gzip.compress(b'<Ableton Creator="Ableton Live 12.0.1" />', mtime=0))
        data[-8] ^= 1
        source, digest = self.capture(encoded=bytes(data))
        with self.assertRaisesRegex(ValueError, "invalid gzip"):
            baseline.inspect_template(source, digest)

    def test_truncated_gzip_refused(self):
        source, digest = self.capture(encoded=gzip.compress(b"synthetic")[:-1])
        with self.assertRaisesRegex(ValueError, "invalid gzip"):
            baseline.inspect_template(source, digest)

    def test_inflated_size_limit_checked_before_xml_parse(self):
        source, digest = self.capture(xml=b" " * (baseline.MAX_TEMPLATE_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "XML exceeds 32 MiB"):
            baseline.inspect_template(source, digest)

    def test_dtd_refused_before_entity_expansion(self):
        source, digest = self.capture(xml=b'<!DOCTYPE Ableton [<!ENTITY x "synthetic">]>'
                                           b'<Ableton Creator="Ableton Live 12.0.1">&x;</Ableton>')
        with self.assertRaisesRegex(ValueError, "DTD/entity"):
            baseline.inspect_template(source, digest)

    def test_non_utf8_xml_refused(self):
        source, digest = self.capture(xml=b"\xff\xfe")
        with self.assertRaisesRegex(ValueError, "not UTF-8"):
            baseline.inspect_template(source, digest)

    def test_malformed_xml_refused(self):
        source, digest = self.capture(xml=b"<Ableton")
        with self.assertRaisesRegex(ValueError, "malformed XML"):
            baseline.inspect_template(source, digest)

    def test_non_ableton_root_refused(self):
        source, digest = self.capture(xml=b'<Other Creator="Ableton Live 12.0.1" />')
        with self.assertRaisesRegex(ValueError, "root is not Ableton"):
            baseline.inspect_template(source, digest)

    def test_wrong_major_version_refused(self):
        for creator in ("Ableton Live 11.3.1", "Ableton Live 120.1", "LMDJ"):
            with self.subTest(creator=creator):
                source, digest = self.capture(xml=f'<Ableton Creator="{creator}" />'.encode())
                with self.assertRaisesRegex(ValueError, "does not declare Live 12"):
                    baseline.inspect_template(source, digest)

    def test_pair_reports_unassessed_manual_acceptance(self):
        rack, rack_digest = self.capture()
        live_set, set_digest = self.capture(suffix=".als")
        output = StringIO()
        with redirect_stdout(output):
            result = baseline.main(["--rack", str(rack), "--rack-sha256", rack_digest,
                                    "--set", str(live_set), "--set-sha256", set_digest])
        self.assertEqual(result, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["manual_acceptance"], "not-assessed")
        self.assertEqual(report["provenance"], "operator-must-verify")

    def test_mismatched_pair_version_produces_no_success_report(self):
        rack, rack_digest = self.capture()
        live_set, set_digest = self.capture(
            xml=b'<Ableton Creator="Ableton Live 12.1.1" />', suffix=".als")
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            result = baseline.main(["--rack", str(rack), "--rack-sha256", rack_digest,
                                    "--set", str(live_set), "--set-sha256", set_digest])
        self.assertEqual(result, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("versions differ", error.getvalue())

    def test_swapped_pair_produces_no_success_report(self):
        rack, rack_digest = self.capture()
        live_set, set_digest = self.capture(suffix=".als")
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            result = baseline.main(["--rack", str(live_set), "--rack-sha256", set_digest,
                                    "--set", str(rack), "--set-sha256", rack_digest])
        self.assertEqual(result, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("swapped", error.getvalue())


if __name__ == "__main__":
    unittest.main()
