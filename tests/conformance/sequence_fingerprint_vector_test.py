#!/usr/bin/env python3
"""Verify the shared SR-D22 canonical JSON/SHA-256 byte vectors."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VECTORS = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "golden"
    / "sequence-pattern-fingerprint-v1.json"
)


def main() -> None:
    document = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert document["contract"] == "lmdj.sequence-pattern-fingerprint-v1"
    for vector in document["vectors"]:
        canonical = vector["canonical_json"]
        encoded = canonical.encode("utf-8")
        assert not encoded.startswith(b"\xef\xbb\xbf"), vector["name"]
        assert not encoded.endswith(b"\n"), vector["name"]
        assert json.dumps(
            json.loads(canonical),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ) == canonical, vector["name"]
        assert hashlib.sha256(encoded).hexdigest() == vector["sha256"], (
            vector["name"]
        )
    print(f"sequence fingerprint vectors: {len(document['vectors'])} passed")


if __name__ == "__main__":
    main()
