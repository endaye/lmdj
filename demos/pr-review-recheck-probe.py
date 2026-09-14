"""Standalone framing example for the PR review repair acceptance journey.

Wire format: a four-byte big-endian unsigned payload byte count, followed by
exactly that many payload bytes. The byte count excludes the header itself.
"""


def encode_frame(payload: bytes) -> bytes:
    """Encode one complete frame for a receiver using the wire format above."""
    payload_size = len(payload) + 1
    return payload_size.to_bytes(4, "big") + payload
