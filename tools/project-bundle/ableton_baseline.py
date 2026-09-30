#!/usr/bin/env python3
"""Inspect supplied Live 12 native baselines; does not certify Live compatibility."""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zlib


MAX_TEMPLATE_BYTES = 32 * 1024 * 1024


def inspect_template(source: Path, expected_sha256: str) -> dict:
    """Bind observations to operator-supplied native bytes, never to a new template."""
    if source.suffix.lower() not in (".adg", ".als"):
        raise ValueError("why: unsupported baseline extension; remedy: supply .adg or .als")
    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise ValueError("why: invalid expected SHA-256; remedy: supply 64 lowercase hex digits")
    with source.open("rb") as stream:
        encoded = stream.read(MAX_TEMPLATE_BYTES + 1)
    if len(encoded) > MAX_TEMPLATE_BYTES:
        raise ValueError("why: baseline exceeds 32 MiB; remedy: create a minimal native baseline")
    actual_sha256 = hashlib.sha256(encoded).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError("why: baseline SHA-256 mismatch; remedy: check the original capture identity")
    if not encoded.startswith(b"\x1f\x8b"):
        raise ValueError("why: baseline is not gzip; remedy: supply the unmodified native file")
    # GzipFile caps inflated bytes before XML parsing, including concatenated members.
    try:
        with gzip.GzipFile(fileobj=BytesIO(encoded)) as stream:
            decoded = stream.read(MAX_TEMPLATE_BYTES + 1)
    except (OSError, EOFError, zlib.error) as error:
        raise ValueError("why: invalid gzip baseline; remedy: recapture the original native file") from error
    if len(decoded) > MAX_TEMPLATE_BYTES:
        raise ValueError("why: XML exceeds 32 MiB; remedy: create a minimal native baseline")
    # Native templates have no reason to declare DTDs. Exclude them before the
    # parser can expand entities; this tool accepts UTF-8 XML only.
    try:
        xml = decoded.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("why: XML is not UTF-8; remedy: inspect the native capture encoding") from error
    if re.search(r"<!\s*(DOCTYPE|ENTITY)\b", xml, re.IGNORECASE):
        raise ValueError("why: baseline declares a DTD/entity; remedy: supply a minimal native template")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        raise ValueError("why: malformed XML baseline; remedy: recapture the native file") from error
    if root.tag != "Ableton":
        raise ValueError("why: XML root is not Ableton; remedy: check the selected file")
    creator = root.get("Creator", "")
    if re.match(r"^Ableton Live 12(?:[. ]|$)", creator) is None:
        raise ValueError("why: baseline does not declare Live 12; remedy: capture it in the target Live version")
    tags = Counter(element.tag for element in root.iter())
    return {
        "file": source.name,
        "byte_length": len(encoded),
        "sha256": actual_sha256,
        "xml_byte_length": len(decoded),
        "xml_sha256": hashlib.sha256(decoded).hexdigest(),
        "root_attributes": dict(sorted(root.attrib.items())),
        "element_counts": dict(sorted(tags.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rack", type=Path, required=True)
    parser.add_argument("--rack-sha256", required=True)
    parser.add_argument("--set", dest="live_set", type=Path, required=True)
    parser.add_argument("--set-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.rack.suffix.lower() != ".adg" or args.live_set.suffix.lower() != ".als":
            raise ValueError("why: rack/set inputs are swapped; remedy: supply an .adg rack and .als set")
        rack = inspect_template(args.rack, args.rack_sha256)
        live_set = inspect_template(args.live_set, args.set_sha256)
        if rack["root_attributes"]["Creator"] != live_set["root_attributes"]["Creator"]:
            raise ValueError("why: baseline Live versions differ; remedy: capture both in one target version")
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps({
        "inspection": "bytes-and-xml-only",
        "manual_acceptance": "not-assessed",
        "provenance": "operator-must-verify",
        "rack": rack,
        "live_set": live_set,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
