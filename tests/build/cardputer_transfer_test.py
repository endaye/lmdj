#!/usr/bin/env python3
"""Reference framing tests for the C1 transport seam."""

import importlib.util
import pathlib
import sys
import unittest
from unittest import mock
import hashlib
import struct


ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "cardputer_transfer", ROOT / "scripts" / "cardputer-transfer.py"
)
assert spec and spec.loader
transfer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = transfer
spec.loader.exec_module(transfer)


class CardputerTransferTest(unittest.TestCase):
    def serial_transaction(self, mutate=None, wire_transform=None):
        sent, incoming = [], []
        nonce, transfer_id, content = b"n" * 16, b"t" * 16, b"music"

        def write(fd, wire):
            request = transfer.decode(bytes(wire))
            sent.append(request)
            if request.opcode == 1:
                payload = struct.pack("<HH", 0, 1024)
            elif request.opcode == 3:
                payload = b"\0\0" + transfer_id + struct.pack("<Q", 0)
            elif request.opcode == 4:
                payload = b"\0\0" + transfer_id + struct.pack("<Q", len(content))
            else:
                payload = b"\0\0" + struct.pack("<Q", len(content)) + hashlib.sha256(content).digest()
            response = transfer.Frame(request.opcode | 0x80, request.request_id, nonce, payload)
            if mutate:
                response = mutate(response)
            wire_response = transfer.encode(response)
            incoming.extend(wire_transform(wire_response) if wire_transform else [wire_response])
            return len(wire)

        self.sent = sent
        with mock.patch.object(transfer.os, "open", return_value=123), \
                mock.patch.object(transfer.os, "close"), \
                mock.patch.object(transfer.os, "urandom", return_value=transfer_id), \
                mock.patch.object(transfer.os, "write", side_effect=write), \
                mock.patch.object(transfer.os, "read", side_effect=lambda *args: incoming.pop(0)), \
                mock.patch.object(transfer.termios, "tcgetattr", return_value=[0] * 7), \
                mock.patch.object(transfer.termios, "tcsetattr"), \
                mock.patch.object(transfer.select, "select", side_effect=lambda *args:
                    ([123], [], []) if incoming else self.fail("waited again with complete buffered response")):
            return transfer.send_serial("fake-serial", content)

    def test_serial_complete_acknowledged_identity(self):
        result = self.serial_transaction()
        self.assertEqual([frame.opcode for frame in self.sent], [1, 3, 4, 5])
        self.assertEqual(result.payload, b"\0\0" + struct.pack("<Q", 5) + hashlib.sha256(b"music").digest())

    def test_serial_boot_noise_and_fragmented_magic(self):
        self.serial_transaction(wire_transform=lambda wire: [b"boot log\nL", wire[1:]])

    def test_serial_corrupt_frame_then_valid_in_same_read(self):
        def transform(wire):
            corrupt = bytearray(wire)
            corrupt[-1] ^= 1
            return [bytes(corrupt) + wire]
        self.serial_transaction(wire_transform=transform)

    def test_serial_overwide_header_cannot_hold_valid_reply(self):
        def transform(wire):
            bad = bytearray(wire[:28])
            struct.pack_into("<H", bad, 6, 65535)
            return [bytes(bad) + wire]
        self.serial_transaction(wire_transform=transform)

    def test_response_parser_retains_only_bounded_partial_input(self):
        buffer = bytearray(b"noise" * transfer.MAX_FRAME + b"LMC")
        self.assertIsNone(transfer.pop_response(buffer))
        self.assertEqual(buffer, b"LMC")
        frame = transfer.Frame(0x84, 3, b"n" * 16, b"x" * transfer.MAX_PAYLOAD)
        wire = transfer.encode(frame)
        buffer = bytearray(wire[:-1])
        self.assertIsNone(transfer.pop_response(buffer))
        self.assertEqual(len(buffer), transfer.MAX_FRAME - 1)
        buffer.extend(wire[-1:])
        self.assertEqual(transfer.pop_response(buffer), frame)
        self.assertFalse(buffer)

    def test_serial_wrong_request_or_nonce_stops_before_data(self):
        for field in ("request_id", "nonce"):
            with self.subTest(field=field):
                def mutate(response):
                    if response.opcode != 0x83:
                        return response
                    return transfer.Frame(response.opcode,
                        99 if field == "request_id" else response.request_id,
                        b"x" * 16 if field == "nonce" else response.nonce, response.payload)
                with self.assertRaises(ValueError):
                    self.serial_transaction(mutate)
                self.assertEqual([frame.opcode for frame in self.sent], [1, 3])

    def test_serial_bad_ack_payload_never_advances(self):
        for opcode in (0x81, 0x83, 0x84, 0x85):
            with self.subTest(opcode=opcode):
                def mutate(response):
                    if response.opcode != opcode:
                        return response
                    payload = bytearray(response.payload)
                    payload[-1] ^= 1
                    return transfer.Frame(response.opcode, response.request_id, response.nonce, bytes(payload))
                with self.assertRaises(ValueError):
                    self.serial_transaction(mutate)
                self.assertEqual(self.sent[-1].opcode, opcode & 0x7f)

    def test_serial_rejects_zero_hello_nonce(self):
        def mutate(response):
            return transfer.Frame(response.opcode, response.request_id, bytes(16), response.payload)
        with self.assertRaisesRegex(ValueError, "empty session nonce"):
            self.serial_transaction(mutate)
        self.assertEqual([frame.opcode for frame in self.sent], [1])

    def test_serial_rejects_incomplete_and_extra_ack_fields(self):
        for opcode in (0x81, 0x83, 0x84, 0x85):
            for extra in (False, True):
                with self.subTest(opcode=opcode, extra=extra):
                    def mutate(response):
                        if response.opcode != opcode:
                            return response
                        payload = response.payload + b"\0" if extra else response.payload[:-1]
                        return transfer.Frame(response.opcode, response.request_id, response.nonce, payload)
                    with self.assertRaises(ValueError):
                        self.serial_transaction(mutate)
                    self.assertEqual(self.sent[-1].opcode, opcode & 0x7f)

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
