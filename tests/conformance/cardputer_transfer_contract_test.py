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
        transfer_id = bytes(range(1, 17))
        wire = b"".join(transfer.content_frames(
            content, 17, bytes(range(16)), 97, transfer_id))
        frames = []
        cursor = 0
        while cursor < len(wire):
            size = transfer.HEADER + int.from_bytes(wire[cursor + 6:cursor + 8], "little") + 4
            frames.append(transfer.decode(wire[cursor:cursor + size]))
            cursor += size
        begin = frames.pop(0)
        self.assertEqual(begin.payload[:16], transfer_id)
        total = int.from_bytes(begin.payload[16:24], "little")
        identity = transfer.ContentIdentity(begin.payload[24:], total, transfer_id)
        self.assertEqual(receiver.begin_transfer(begin.request_id, transfer_id, identity, 0), "accepted")
        for frame in frames[:-1]:
            self.assertEqual(frame.payload[:16], transfer_id)
            offset = int.from_bytes(frame.payload[16:24], "little")
            self.assertEqual(receiver.data_transfer(
                frame.request_id, transfer_id, offset, frame.payload[24:], 1), "accepted")
        self.assertEqual(frames[-1].payload, transfer_id)
        self.assertEqual(receiver.commit_transfer(frames[-1].request_id, transfer_id, 2), "committed")
        self.assertEqual(published[0][0], content)

    def test_transfer_id_is_independent_and_duplicate_data_does_not_extend_timeout(self):
        content = b"timed"
        transfer_id = bytes(range(1, 17))
        identity = transfer.ContentIdentity(hashlib.sha256(content).digest(), len(content))
        receiver = transfer.Receiver(1024, lambda *_: True)
        self.assertEqual(receiver.begin_transfer(2, transfer_id, identity, 100), "accepted")
        self.assertEqual(receiver.data_transfer(2, transfer_id, 0, content[:2], 200), "accepted")
        self.assertEqual(receiver.data_transfer(2, transfer_id, 0, content[:2], 4_900), "duplicate")
        self.assertFalse(receiver.expire(5_199))
        self.assertTrue(receiver.expire(5_200))
        self.assertFalse(receiver.receiving)

    def test_wrong_transfer_cannot_abort_or_mutate(self):
        content = b"safe"
        transfer_id = bytes(range(1, 17))
        identity = transfer.ContentIdentity(hashlib.sha256(content).digest(), len(content))
        receiver = transfer.Receiver(1024, lambda *_: True)
        receiver.begin_transfer(3, transfer_id, identity, 0)
        with self.assertRaisesRegex(ValueError, "wrong transfer"):
            receiver.abort_transfer(3, b"x" * 16)
        self.assertTrue(receiver.receiving)

    def test_session_nonce_and_exact_request_sequence(self):
        content = b"session"
        transfer_id = bytes(range(1, 17))
        identity = transfer.ContentIdentity(hashlib.sha256(content).digest(), len(content), transfer_id)
        session = transfer.Session(1024, lambda *_: True, lambda: bytes(range(1, 17)))
        with self.assertRaisesRegex(ValueError, "bad hello"):
            session.hello(2, bytes(16))
        self.assertEqual(session.hello(1, bytes(16)), "accepted")
        nonce = session.nonce
        with self.assertRaisesRegex(ValueError, "stale session"):
            session.begin(2, b"x" * 16, transfer_id, identity, 0)
        self.assertEqual(session.next_request_id, 2)
        self.assertEqual(session.begin(2, nonce, transfer_id, identity, 0), "accepted")
        with self.assertRaisesRegex(ValueError, "bad request id"):
            session.data(4, nonce, transfer_id, 0, content, 1)
        self.assertEqual(session.next_request_id, 3)
        self.assertEqual(session.data(3, nonce, transfer_id, 0, content, 1), "accepted")
        self.assertEqual(session.commit(4, nonce, transfer_id, 2), "committed")


if __name__ == "__main__":
    unittest.main()
