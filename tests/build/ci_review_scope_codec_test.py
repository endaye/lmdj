import base64
import json
from pathlib import Path
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/ci"))
import review_scope_codec as codec


class CodecTests(unittest.TestCase):
    def marker(self, raw):
        return "<!-- lmdj-test-scope-record-v2 codec=zlib-base64 " + base64.b64encode(raw).decode() + " -->"

    def test_roundtrip(self):
        value = {"paths": ["x" * 1000] * 100}
        self.assertEqual(codec.decode(codec.encode(value)), value)

    def test_duplicate_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            codec.decode(self.marker(zlib.compress(b'{"a":1,"a":2}')))

    def test_bomb_rejected_before_unbounded_expansion(self):
        with self.assertRaisesRegex(ValueError, "oversized"):
            codec.decode(self.marker(zlib.compress(b"x" * (codec.MAX_RAW_BYTES + 1))))

    def test_trailing_stream_rejected(self):
        with self.assertRaisesRegex(ValueError, "trailing"):
            codec.decode(self.marker(zlib.compress(b"{}") + zlib.compress(b"{}")))

    def test_trailing_bytes_rejected(self):
        with self.assertRaisesRegex(ValueError, "trailing"):
            codec.decode(self.marker(zlib.compress(b"{}") + b"garbage"))

    def test_truncated_stream_rejected(self):
        with self.assertRaisesRegex(ValueError, "truncated"):
            codec.decode(self.marker(zlib.compress(b"{}")[:-1]))

    def test_multiple_markers_rejected(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            codec.decode(codec.encode({}) + "\n" + codec.encode({}))


if __name__ == "__main__":
    unittest.main()
