"""Bounded COMMENT metadata codec; model text keeps its independent budget."""
import base64
import binascii
import json
import re
import zlib

import change_scope
import review_scope
import test_scope

MAX_RAW_BYTES = 1000000
MAX_MARKER_BYTES = 40000
MAX_COMMENT_BYTES = 60000
PATTERN = re.compile(r"^<!-- lmdj-test-scope-record-v2 codec=zlib-base64 ([A-Za-z0-9+/=]+) -->$", re.MULTILINE)
UNAVAILABLE = re.compile(r"^<!-- lmdj-test-scope-unavailable-v1 ([A-Za-z0-9+/=]+) -->$", re.MULTILINE)
HISTORY_PATTERN = re.compile(
    r"^<!-- lmdj-review-history-v2 codec=zlib-base64 sha256=([0-9a-f]{64}) ([A-Za-z0-9+/=]+) -->$",
    re.MULTILINE,
)


def encode(record):
    raw = test_scope.self_test.canonical_json(record).encode()
    review_scope.require(len(raw) <= MAX_RAW_BYTES, "scope metadata exceeds raw budget")
    encoded = base64.b64encode(zlib.compress(raw, 9)).decode()
    marker = "<!-- lmdj-test-scope-record-v2 codec=zlib-base64 " + encoded + " -->"
    review_scope.require(len(marker) <= MAX_MARKER_BYTES, "scope metadata exceeds COMMENT budget")
    return marker


def decode(body):
    matches = PATTERN.findall(body)
    if not matches:
        return None
    review_scope.require(len(matches) == 1 and len(matches[0]) <= MAX_MARKER_BYTES, "ambiguous or oversized scope metadata")
    compressed = base64.b64decode(matches[0], validate=True)
    inflater = zlib.decompressobj()
    try:
        raw = inflater.decompress(compressed, MAX_RAW_BYTES + 1)
    except zlib.error as error:
        raise review_scope.ReviewScopeError("why: scope marker compression is invalid; remedy: regenerate the complete receipt") from error
    review_scope.require(len(raw) <= MAX_RAW_BYTES and not inflater.unconsumed_tail
                         and not inflater.unused_data and inflater.eof, "scope metadata is oversized, truncated or has trailing streams")
    return json.loads(raw, object_pairs_hook=change_scope.reject_duplicates)


def _inflate(encoded, label):
    """Decode one bounded zlib payload; markers are never trusted as JSON."""
    try:
        compressed = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise review_scope.ReviewScopeError(f"why: {label} marker encoding is invalid; remedy: regenerate the complete receipt") from error
    inflater = zlib.decompressobj()
    raw = inflater.decompress(compressed, MAX_RAW_BYTES + 1)
    review_scope.require(len(raw) <= MAX_RAW_BYTES and not inflater.unconsumed_tail
                         and not inflater.unused_data and inflater.eof,
                         f"{label} marker is oversized, truncated or has trailing streams")
    return raw


def encode_history(history):
    """Encode closed v2 history and bind the marker to its canonical digest."""
    review_scope.validate_history_v2(None, history)
    raw = review_scope.canonical_json(history)
    review_scope.require(len(raw) <= MAX_RAW_BYTES, "history metadata exceeds raw budget")
    encoded = base64.b64encode(zlib.compress(raw, 9)).decode()
    marker = "<!-- lmdj-review-history-v2 codec=zlib-base64 sha256=" + review_scope.history_digest(history) + " " + encoded + " -->"
    review_scope.require(len(marker) <= MAX_MARKER_BYTES, "history metadata exceeds COMMENT budget")
    return marker


def decode_history(body):
    """Read exactly one digest-bound v2 marker; absent means historical v1."""
    matches = HISTORY_PATTERN.findall(body)
    if not matches:
        return None
    review_scope.require(len(matches) == 1 and len(matches[0][1]) <= MAX_MARKER_BYTES,
                         "ambiguous or oversized history metadata")
    expected, encoded = matches[0]
    raw = _inflate(encoded, "history")
    history = json.loads(raw, object_pairs_hook=change_scope.reject_duplicates)
    review_scope.validate_history_v2(None, history)
    review_scope.require(review_scope.history_digest(history) == expected,
                         "history marker digest does not match its complete payload")
    return history


def unavailable(identity):
    test_scope._identity(identity)
    return "<!-- lmdj-test-scope-unavailable-v1 " + base64.b64encode(test_scope.self_test.canonical_json(identity).encode()).decode() + " -->"


def unavailable_identities(body):
    values = []
    for encoded in UNAVAILABLE.findall(body):
        review_scope.require(len(encoded) < 4000, "oversized scope-unavailable marker")
        identity = json.loads(base64.b64decode(encoded, validate=True), object_pairs_hook=change_scope.reject_duplicates)
        test_scope._identity(identity)
        values.append(identity)
    return values
