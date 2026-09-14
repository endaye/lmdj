"""Standalone framing example for the PR review repair acceptance journey.

Wire format: a four-byte big-endian unsigned payload byte count, followed by
exactly that many payload bytes. The byte count excludes the header itself.
"""


def encode_frame(payload: bytes) -> bytes:
    """Encode one complete frame for a receiver using the wire format above."""
    payload_byte_count = len(payload)
    return payload_byte_count.to_bytes(4, "big") + payload


def payload_is_complete(frame: bytes) -> bool:
    """Return true only when the frame contains exactly the declared payload.

    Incomplete headers, truncated payloads and trailing bytes are invalid.
    """
    if len(frame) < 4:
        return False
    payload_byte_count = int.from_bytes(frame[:4], "big")
    return len(frame) - 4 == payload_byte_count
