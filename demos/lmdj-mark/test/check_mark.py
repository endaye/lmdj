#!/usr/bin/env python3
"""The site mark is the Creator LogoIcon, at Apple's two standard sizes.

One fact: the published SVG paths are the four LogoIcon paths, the app icon
is a 1024 RGB PNG, and the touch icon is a 180 RGB PNG of that same drawing.
"""

from __future__ import annotations

import re
import struct
import sys
import zlib
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1]
ROOT = DEMO.parents[1]
SOURCE = ROOT / "apps/creator-web/src/components/hardware_icons.tsx"


def logo_paths(source: str) -> list[tuple[str, str]]:
    start = source.index("export function LogoIcon")
    end = source.index("export function ProjectIcon")
    block = source[start:end]
    found = re.findall(
        r'<path\b[^>]*\bd="([^"]+)"[^>]*\bfill="(#[0-9A-Fa-f]{6})"',
        block,
    )
    if len(found) != 4:
        raise SystemExit(f"LogoIcon should contain 4 paths, found {len(found)}")
    return found


def png_rgb(path: Path) -> tuple[int, int, list[bytearray]]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{path.name} is not a PNG")
    pos = 8
    width = height = bit = color = inter = 0
    idat = b""
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        kind = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, bit, color, _comp, _filt, inter = struct.unpack(">IIBBBBB", chunk)
        elif kind == b"IDAT":
            idat += chunk
        elif kind == b"IEND":
            break
    if (bit, color, inter) != (8, 2, 0):
        raise SystemExit(
            f"{path.name} must be opaque 8-bit RGB, got bit {bit} color {color}"
        )
    raw = zlib.decompress(idat)
    stride = width * 3
    rows: list[bytearray] = []
    prev = bytearray(stride)
    index = 0
    for _y in range(height):
        filt = raw[index]
        index += 1
        row = bytearray(raw[index : index + stride])
        index += stride
        if filt == 1:
            for x in range(stride):
                left = row[x - 3] if x >= 3 else 0
                row[x] = (row[x] + left) & 255
        elif filt == 2:
            for x in range(stride):
                row[x] = (row[x] + prev[x]) & 255
        elif filt == 3:
            for x in range(stride):
                left = row[x - 3] if x >= 3 else 0
                row[x] = (row[x] + ((left + prev[x]) // 2)) & 255
        elif filt == 4:
            for x in range(stride):
                left = row[x - 3] if x >= 3 else 0
                up = prev[x]
                upper_left = prev[x - 3] if x >= 3 else 0
                row[x] = (row[x] + _paeth(left, up, upper_left)) & 255
        elif filt != 0:
            raise SystemExit(f"{path.name} uses PNG filter {filt}")
        prev = row
        rows.append(row)
    return width, height, rows


def _paeth(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    pa = abs(estimate - left)
    pb = abs(estimate - up)
    pc = abs(estimate - upper_left)
    if pa <= pb and pa <= pc:
        return left
    if pb <= pc:
        return up
    return upper_left


def pixel(rows: list[bytearray], x: int, y: int) -> tuple[int, int, int]:
    row = rows[y]
    i = x * 3
    return row[i], row[i + 1], row[i + 2]


def main() -> int:
    paths = logo_paths(SOURCE.read_text(encoding="utf-8"))
    mark = (DEMO / "mark.svg").read_text(encoding="utf-8")
    icon = (DEMO / "icon.svg").read_text(encoding="utf-8")
    for d, fill in paths:
        if d not in mark or d not in icon:
            raise SystemExit("a LogoIcon path is missing from the published SVG")
        if fill.upper() not in mark or fill.upper() not in icon:
            raise SystemExit(f"fill {fill} is missing from the published SVG")
    if 'viewBox="0 0 1024 1024"' not in icon or 'fill="#0a0b09"' not in icon:
        raise SystemExit("icon.svg is not the 1024 plate on #0a0b09")

    for name, size in (("icon-1024.png", 1024), ("apple-touch-icon.png", 180)):
        width, height, rows = png_rgb(DEMO / name)
        if (width, height) != (size, size):
            raise SystemExit(f"{name} is {width}x{height}, expected {size}")
        if pixel(rows, 0, 0) != (0x0A, 0x0B, 0x09):
            raise SystemExit(f"{name} corner is not the plate color")
        acid = any(
            pixel(rows, x, y) == (0xD9, 0xFA, 0x08)
            for y in range(0, height, 3)
            for x in range(0, width, 3)
        )
        if not acid:
            raise SystemExit(f"{name} does not contain the acid glyph")

    for page in ("index.html", "instrument.html", "icon.html"):
        text = (DEMO / page).read_text(encoding="utf-8")
        for needle in (
            'href="apple-touch-icon.png"',
            'sizes="180x180"',
            'href="index.html"',
            'href="instrument.html"',
            'href="icon.html"',
            'href="styles.css"',
        ):
            if needle not in text:
                raise SystemExit(f"{page} is missing {needle}")
    icon_page = (DEMO / "icon.html").read_text(encoding="utf-8")
    if 'src="icon-1024.png"' not in icon_page:
        raise SystemExit("icon page does not show the 1024 icon")

    print("lmdj mark: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
