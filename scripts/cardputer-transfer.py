#!/usr/bin/env python3
"""Bounded lmdj.cardputer-transfer.v1 framing reference implementation.

This module intentionally handles bytes only. Project/Runtime Content decoding
stays behind the Application Facade and is never inferred from a wire frame.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import os
import select
import struct
import termios
import time
from dataclasses import dataclass

MAGIC = b"LMCP"
VERSION = 1
HEADER = 28
MAX_PAYLOAD = 1024
MAX_FRAME = HEADER + MAX_PAYLOAD + 4
TRANSFER_ID_BYTES = 16
DATA_OFFSET_BYTES = TRANSFER_ID_BYTES + 8
BEGIN_IDENTITY_BYTES = TRANSFER_ID_BYTES + 8 + 32


@dataclass(frozen=True)
class Frame:
    opcode: int
    request_id: int
    nonce: bytes = bytes(16)
    payload: bytes = b""
    version: int = VERSION


@dataclass(frozen=True)
class ContentIdentity:
    sha256: bytes
    byte_length: int
    transfer_id: bytes = b""


class Receiver:
    """Fail-closed, ordered staging transaction for Runtime Content bytes."""

    def __init__(self, maximum_bytes: int, sink):
        self.maximum_bytes = maximum_bytes
        self.sink = sink
        self.clear()

    def clear(self):
        self.request_id = None
        self.identity = None
        self.buffer = bytearray()
        self.received = 0
        self.transfer_id = None
        self.last_progress_ms = None

    @property
    def receiving(self):
        return self.request_id is not None

    def begin(self, request_id: int, identity: ContentIdentity):
        if (request_id <= 0 or identity.byte_length < 0 or
                len(identity.sha256) != 32 or identity.byte_length > self.maximum_bytes):
            raise ValueError("unsupported content transaction")
        if self.receiving:
            if request_id == self.request_id and identity == self.identity:
                return "duplicate"
            raise ValueError("transaction already active")
        self.request_id, self.identity = request_id, identity
        self.buffer = bytearray(identity.byte_length)
        self.received = 0
        return "accepted"

    def begin_transfer(self, request_id: int, transfer_id: bytes,
                       identity: ContentIdentity, now_ms: int):
        """Begin the D1 transaction identified independently of request IDs."""
        if (len(transfer_id) != 16 or not any(transfer_id) or
                identity.transfer_id not in (b"", transfer_id)):
            raise ValueError("invalid transfer id")
        if self.receiving:
            if (request_id == self.request_id and transfer_id == self.transfer_id
                    and identity == self.identity):
                return "duplicate"
            raise ValueError("transaction already active")
        result = self.begin(request_id, identity)
        self.transfer_id = transfer_id
        self.last_progress_ms = now_ms
        return result

    def data(self, request_id: int, offset: int, chunk: bytes):
        if not self.receiving or request_id != self.request_id:
            raise ValueError("wrong transaction")
        if offset > self.received or offset > self.identity.byte_length:
            raise ValueError("offset mismatch")
        if len(chunk) > self.identity.byte_length - offset:
            raise ValueError("content exceeds declared length")
        if offset < self.received:
            overlap = min(self.received - offset, len(chunk))
            if chunk[:overlap] != self.buffer[offset:offset + overlap]:
                raise ValueError("conflicting duplicate data")
            if overlap == len(chunk):
                return "duplicate"
            chunk, offset = chunk[overlap:], offset + overlap
        if offset != self.received:
            raise ValueError("offset mismatch")
        self.buffer[offset:offset + len(chunk)] = chunk
        self.received += len(chunk)
        return "accepted"

    def data_transfer(self, request_id: int, transfer_id: bytes, offset: int,
                      chunk: bytes, now_ms: int):
        if transfer_id != self.transfer_id:
            raise ValueError("wrong transfer")
        if not chunk:
            raise ValueError("empty data chunk")
        # Session owns wire request sequencing; Receiver retains BEGIN's
        # request ID only as its legacy transaction handle.
        result = self.data(self.request_id, offset, chunk)
        if result == "accepted" and chunk:
            self.last_progress_ms = now_ms
        return result

    def commit(self, request_id: int):
        if not self.receiving or request_id != self.request_id:
            raise ValueError("wrong transaction")
        if self.received != self.identity.byte_length:
            raise ValueError("incomplete content")
        if hashlib.sha256(self.buffer).digest() != self.identity.sha256:
            self.clear()
            raise ValueError("content identity mismatch")
        try:
            accepted = bool(self.sink(bytes(self.buffer), self.identity))
        finally:
            self.clear()
        if not accepted:
            raise ValueError("content sink rejected")
        return "committed"

    def commit_transfer(self, request_id: int, transfer_id: bytes, now_ms: int):
        if transfer_id != self.transfer_id:
            raise ValueError("wrong transfer")
        return self.commit(self.request_id)

    def abort(self, request_id: int):
        if not self.receiving or request_id != self.request_id:
            raise ValueError("wrong transaction")
        self.clear()
        return "aborted"

    def abort_transfer(self, request_id: int, transfer_id: bytes):
        if transfer_id != self.transfer_id:
            raise ValueError("wrong transfer")
        return self.abort(request_id)

    def disconnect(self):
        self.clear()

    def expire(self, now_ms: int):
        if (not self.receiving or self.last_progress_ms is None or
                now_ms < self.last_progress_ms or
                now_ms - self.last_progress_ms < 5000):
            return False
        self.clear()
        return True


class Session:
    """Nonce and exact-next request sequencing around :class:`Receiver`."""

    def __init__(self, maximum_bytes: int, sink, nonce_source):
        self.receiver = Receiver(maximum_bytes, sink)
        self.nonce_source = nonce_source
        self.nonce = None
        self.next_request_id = 1

    def hello(self, request_id: int, nonce: bytes):
        if request_id != 1 or nonce != bytes(16):
            raise ValueError("bad hello")
        candidate = bytes(self.nonce_source())
        if len(candidate) != 16 or not any(candidate):
            raise ValueError("invalid session nonce")
        self.receiver.disconnect()
        self.nonce = candidate
        self.next_request_id = 2
        return "accepted"

    def _authorize(self, request_id: int, nonce: bytes):
        if self.nonce is None or nonce != self.nonce:
            raise ValueError("stale session")
        if self.next_request_id == 0 or request_id != self.next_request_id:
            raise ValueError("bad request id")
        self.next_request_id = 0 if request_id == 0xFFFFFFFF else request_id + 1

    def begin(self, request_id: int, nonce: bytes, transfer_id: bytes,
              identity: ContentIdentity, now_ms: int):
        self._authorize(request_id, nonce)
        return self.receiver.begin_transfer(request_id, transfer_id, identity, now_ms)

    def data(self, request_id: int, nonce: bytes, transfer_id: bytes,
             offset: int, chunk: bytes, now_ms: int):
        self._authorize(request_id, nonce)
        return self.receiver.data_transfer(request_id, transfer_id, offset, chunk, now_ms)

    def commit(self, request_id: int, nonce: bytes, transfer_id: bytes,
               now_ms: int):
        self._authorize(request_id, nonce)
        return self.receiver.commit_transfer(request_id, transfer_id, now_ms)

    def abort(self, request_id: int, nonce: bytes, transfer_id: bytes):
        self._authorize(request_id, nonce)
        return self.receiver.abort_transfer(request_id, transfer_id)

    def expire(self, now_ms: int):
        return self.receiver.expire(now_ms)


def content_frames(content: bytes, request_id: int, nonce: bytes,
                   chunk_size: int = MAX_PAYLOAD - DATA_OFFSET_BYTES,
                   transfer_id: bytes | None = None) -> list[bytes]:
    """Build a complete sender stream for one already-exported artifact."""
    if not (1 <= request_id <= 0xFFFFFFFF) or len(nonce) != 16:
        raise ValueError("invalid request or nonce")
    if not (1 <= chunk_size <= MAX_PAYLOAD - DATA_OFFSET_BYTES):
        raise ValueError("chunk size exceeds DATA payload bound")
    if transfer_id is None:
        # Deterministic reference default; a production sender should use a
        # fresh random 128-bit value for every transfer attempt.
        transfer_id = hashlib.sha256(content).digest()[:TRANSFER_ID_BYTES]
    if len(transfer_id) != TRANSFER_ID_BYTES or not any(transfer_id):
        raise ValueError("invalid transfer id")
    identity = hashlib.sha256(content).digest()
    frames = [encode(Frame(3, request_id, nonce,
                           transfer_id + struct.pack("<Q", len(content)) + identity))]
    request_id += 1
    for offset in range(0, len(content), chunk_size):
        chunk = content[offset:offset + chunk_size]
        frames.append(encode(Frame(4, request_id, nonce,
                                   transfer_id + struct.pack("<Q", offset) + chunk)))
        request_id += 1
    frames.append(encode(Frame(5, request_id, nonce, transfer_id)))
    return frames


def encode(frame: Frame) -> bytes:
    if frame.version != VERSION or not (1 <= frame.opcode <= 6 or 0x81 <= frame.opcode <= 0x86):
        raise ValueError("unsupported version or opcode")
    if not (1 <= frame.request_id <= 0xFFFFFFFF):
        raise ValueError("request id must be nonzero u32")
    if len(frame.nonce) != 16 or len(frame.payload) > MAX_PAYLOAD:
        raise ValueError("nonce/payload exceeds bounded frame")
    header = MAGIC + bytes((frame.version, frame.opcode))
    header += struct.pack("<HI", len(frame.payload), frame.request_id) + frame.nonce
    body = header + frame.payload
    return body + struct.pack("<I", binascii.crc32(body) & 0xFFFFFFFF)


def decode(data: bytes) -> Frame:
    if len(data) < HEADER + 4:
        raise ValueError("incomplete frame")
    if data[:4] != MAGIC:
        raise ValueError("bad magic")
    version, opcode, payload_size, request_id = struct.unpack_from("<BBHI", data, 4)
    size = HEADER + payload_size + 4
    if size > MAX_FRAME or len(data) != size:
        raise ValueError("invalid frame length")
    if version != VERSION or not (1 <= opcode <= 6 or 0x81 <= opcode <= 0x86) or request_id == 0:
        raise ValueError("invalid frame header")
    if (binascii.crc32(data[:size - 4]) & 0xFFFFFFFF) != struct.unpack_from("<I", data, size - 4)[0]:
        raise ValueError("bad crc")
    return Frame(opcode, request_id, data[12:28], data[28:size - 4], version)


def send_serial(path: str, content: bytes, timeout: float = 5.0) -> Frame:
    """Perform one HELLO -> BEGIN -> DATA -> COMMIT transaction on POSIX serial."""
    if not path or timeout <= 0:
        raise ValueError("invalid serial path or timeout")
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
    try:
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
        attrs[3] = 0
        attrs[4] = termios.B115200
        attrs[5] = termios.B115200
        termios.tcsetattr(fd, termios.TCSANOW, attrs)

        def exchange(frame: Frame) -> Frame:
            wire = encode(frame)
            view = memoryview(wire)
            while view:
                writable, _, _ = select.select([], [fd], [], timeout)
                if not writable:
                    raise TimeoutError("serial write timeout")
                count = os.write(fd, view)
                view = view[count:]
            deadline = time.monotonic() + timeout
            received = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("serial response timeout")
                readable, _, _ = select.select([fd], [], [], remaining)
                if not readable:
                    continue
                received.extend(os.read(fd, MAX_FRAME * 2))
                if len(received) < HEADER + 4:
                    continue
                if received[:4] != MAGIC:
                    del received[:1]
                    continue
                payload_size = struct.unpack_from("<H", received, 6)[0]
                size = HEADER + payload_size + 4
                if len(received) < size:
                    continue
                return decode(bytes(received[:size]))

        hello = exchange(Frame(1, 1, bytes(16)))
        if hello.opcode != 0x81 or len(hello.payload) < 4 or hello.payload[:2] != b"\0\0":
            raise ValueError("device rejected HELLO")
        nonce = hello.nonce
        transfer_id = os.urandom(TRANSFER_ID_BYTES)
        identity = hashlib.sha256(content).digest()
        request_id = 2
        begin = exchange(Frame(3, request_id, nonce,
                               transfer_id + struct.pack("<Q", len(content)) + identity))
        if begin.opcode != 0x83 or begin.payload[:2] != b"\0\0":
            raise ValueError("device rejected BEGIN; confirm receive on device")
        offset = 0
        request_id += 1
        while offset < len(content):
            chunk = content[offset:offset + MAX_PAYLOAD - DATA_OFFSET_BYTES]
            response = exchange(Frame(4, request_id, nonce,
                                       transfer_id + struct.pack("<Q", offset) + chunk))
            if response.opcode != 0x84 or response.payload[:2] != b"\0\0":
                raise ValueError("device rejected DATA")
            offset += len(chunk)
            request_id += 1
        response = exchange(Frame(5, request_id, nonce, transfer_id))
        if response.opcode != 0x85 or response.payload[:2] != b"\0\0":
            raise ValueError("device rejected COMMIT")
        return response
    finally:
        os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("encode", "decode", "send"))
    parser.add_argument("value")
    parser.add_argument("--output", default="-", help="send output path, or - for stdout")
    parser.add_argument("--port", help="POSIX serial device for a live transaction")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--request-id", type=int, default=1)
    parser.add_argument("--nonce", default="00" * 16)
    parser.add_argument("--chunk-size", type=int, default=MAX_PAYLOAD - DATA_OFFSET_BYTES)
    args = parser.parse_args()
    if args.command == "decode":
        frame = decode(bytes.fromhex(args.value))
        print(f"opcode={frame.opcode} request_id={frame.request_id} payload={frame.payload.hex()}")
    elif args.command == "encode":
        # CLI encode accepts a compact payload-only example and emits a HELLO-like frame.
        print(encode(Frame(1, 1, payload=bytes.fromhex(args.value))).hex())
    else:
        with open(args.value, "rb") as source:
            content = source.read()
        if args.port:
            if os.name == "nt":
                raise SystemExit("--port is supported on POSIX only")
            response = send_serial(args.port, content, args.timeout)
            print(f"committed={response.payload[2:].hex()}")
            return 0
        wire = b"".join(content_frames(content, args.request_id,
                                         bytes.fromhex(args.nonce), args.chunk_size))
        if args.output == "-":
            import sys
            sys.stdout.buffer.write(wire)
        else:
            with open(args.output, "wb") as target:
                target.write(wire)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
