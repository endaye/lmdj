"""Bounded COMMENT metadata codec; model text keeps its independent budget."""
import base64
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
    raw = inflater.decompress(compressed, MAX_RAW_BYTES + 1)
    review_scope.require(len(raw) <= MAX_RAW_BYTES and not inflater.unconsumed_tail
                         and not inflater.unused_data and inflater.eof, "scope metadata is oversized, truncated or has trailing streams")
    return json.loads(raw, object_pairs_hook=change_scope.reject_duplicates)


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
