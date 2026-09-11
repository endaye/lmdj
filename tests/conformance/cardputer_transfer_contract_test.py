#!/usr/bin/env python3
"""Validate the checked-in C1 wire fixtures with the Python reader."""

import importlib.util
import hashlib
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("cardputer_transfer", ROOT / "scripts/cardputer-transfer.py")
assert spec and spec.loader
transfer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = transfer
spec.loader.exec_module(transfer)


class CardputerTransferContractTest(unittest.TestCase):
    def test_fixtures_round_trip_and_semantic_projection(self):
        fixture = json.loads((ROOT / "tests/fixtures/contracts/cardputer-transfer-v1.json").read_text())
        self.assertEqual(fixture["contract"], "lmdj.cardputer-transfer.v1")
        for item in fixture["frames"]:
            frame = transfer.decode(bytes.fromhex(item["hex"]))
            self.assertEqual(frame.version, item["version"])
            self.assertEqual(frame.opcode, item["opcode"])
            self.assertEqual(frame.request_id, item["request_id"])
            self.assertEqual(frame.nonce.hex(), item["nonce_hex"])
            self.assertEqual(frame.payload.hex(), item["payload_hex"])
            self.assertEqual(transfer.encode(frame).hex(), item["hex"])

    def test_fixture_corruption_is_rejected(self):
        fixture = json.loads((ROOT / "tests/fixtures/contracts/cardputer-transfer-v1.json").read_text())
        wire = bytearray(bytes.fromhex(fixture["frames"][0]["hex"]))
        wire[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "bad crc"):
            transfer.decode(bytes(wire))

    def test_ordered_transaction_publishes_only_after_identity_check(self):
        content = b"cardputer-runtime-content"
        published = []

        def sink(payload, identity):
            published.append((payload, identity))
            return True

        identity = transfer.ContentIdentity(hashlib.sha256(content).digest(), len(content))
        receiver = transfer.Receiver(1024, sink)
        self.assertEqual(receiver.begin(9, identity), "accepted")
        self.assertEqual(receiver.begin(9, identity), "duplicate")
        with self.assertRaisesRegex(ValueError, "offset mismatch"):
            receiver.data(9, 1, content[:1])
        self.assertEqual(receiver.data(9, 0, content[:8]), "accepted")
        self.assertEqual(receiver.data(9, 8, content[8:]), "accepted")
        self.assertEqual(receiver.data(9, 0, content[:8]), "duplicate")
        self.assertEqual(receiver.commit(9), "committed")
        self.assertEqual(published[0][0], content)
        self.assertFalse(receiver.receiving)

    def test_transaction_failure_discards_staging_and_disconnect_is_recoverable(self):
        content = b"retry"
        identity = transfer.ContentIdentity(b"0" * 32, len(content))
        receiver = transfer.Receiver(1024, lambda *_: True)
        receiver.begin(1, identity)
        receiver.data(1, 0, content)
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            receiver.commit(1)
        self.assertFalse(receiver.receiving)
        identity = transfer.ContentIdentity(hashlib.sha256(content).digest(), len(content))
        receiver.begin(2, identity)
        receiver.data(2, 0, content[:2])
        receiver.disconnect()
        self.assertFalse(receiver.receiving)

    def test_sender_binds_identity_and_chunks_to_receiver(self):
        content = bytes(range(251)) * 9
        published = []
        receiver = transfer.Receiver(
            4096, lambda payload, identity: published.append((payload, identity)) or True
        )
        wire = b"".join(transfer.content_frames(content, 17, bytes(range(16)), 97))
        frames = []
        cursor = 0
        while cursor < len(wire):
            size = transfer.HEADER + int.from_bytes(wire[cursor + 6:cursor + 8], "little") + 4
            frames.append(transfer.decode(wire[cursor:cursor + size]))
            cursor += size
        begin = frames.pop(0)
        total = int.from_bytes(begin.payload[:8], "little")
        identity = transfer.ContentIdentity(begin.payload[8:], total)
        self.assertEqual(receiver.begin(begin.request_id, identity), "accepted")
        for frame in frames[:-1]:
            offset = int.from_bytes(frame.payload[:8], "little")
            self.assertEqual(receiver.data(frame.request_id, offset, frame.payload[8:]), "accepted")
        self.assertEqual(receiver.commit(frames[-1].request_id), "committed")
        self.assertEqual(published[0][0], content)


if __name__ == "__main__":
    unittest.main()
