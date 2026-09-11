#!/usr/bin/env python3
"""Reference framing tests for the C1 transport seam."""

import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "cardputer_transfer", ROOT / "scripts" / "cardputer-transfer.py"
)
assert spec and spec.loader
transfer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = transfer
spec.loader.exec_module(transfer)


class CardputerTransferTest(unittest.TestCase):
    def test_known_frame_roundtrip(self):
        frame = transfer.Frame(3, 9, bytes(range(16)), b"abc")
        self.assertEqual(transfer.decode(transfer.encode(frame)), frame)

    def test_crc_and_max_payload(self):
        frame = transfer.Frame(1, 1, payload=b"x" * transfer.MAX_PAYLOAD)
        wire = transfer.encode(frame)
        self.assertEqual(len(wire), transfer.MAX_FRAME)
        self.assertEqual(transfer.decode(wire), frame)

    def test_bad_magic_crc_and_length(self):
        frame = transfer.Frame(1, 1)
        wire = bytearray(transfer.encode(frame))
        wire[0] = ord("x")
        with self.assertRaises(ValueError):
            transfer.decode(bytes(wire))
        wire = bytearray(transfer.encode(frame))
        wire[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "bad crc"):
            transfer.decode(bytes(wire))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            transfer.decode(transfer.encode(frame)[:-1])

    def test_header_bounds(self):
        with self.assertRaises(ValueError):
            transfer.encode(transfer.Frame(1, 0))
        with self.assertRaises(ValueError):
            transfer.encode(transfer.Frame(7, 1))
        with self.assertRaises(ValueError):
            transfer.encode(transfer.Frame(1, 1, payload=b"x" * (transfer.MAX_PAYLOAD + 1)))


if __name__ == "__main__":
    unittest.main()
