#!/usr/bin/env python3
"""Render the Creator LogoIcon vector into the mark SVG and the two icon PNGs.

The path data is read from the product component. This demo does not redraw it.
Called by hand:

    python3 demos/lmdj-mark/tools/render_icon.py

The pages load the files it writes. Nothing in apps/ or packages/ imports it.
"""

from __future__ import annotations

import re
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "apps/creator-web/src/components/hardware_icons.tsx"
OUT = Path(__file__).resolve().parents[1]
BACKGROUND = "#0a0b09"
APP_ICON = 1024
TOUCH_ICON = 180
# 80-unit mark scaled by 8 sits in a 640px box. 192px on each side is the
# margin the iOS squircle mask must not be asked to invent.
MARK_SCALE = 8
MARK_ORIGIN = (APP_ICON - 80 * MARK_SCALE) // 2


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


def escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def mark_svg(paths: list[tuple[str, str]]) -> str:
    body = "\n".join(
        f'  <path d="{escape(d)}" fill="{fill.upper()}"/>' for d, fill in paths
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80" '
        'role="img" aria-labelledby="title">\n'
        "  <title id=\"title\">LMDJ</title>\n"
        f"{body}\n"
        "</svg>\n"
    )


def icon_svg(paths: list[tuple[str, str]]) -> str:
    body = "\n".join(
        f'    <path d="{escape(d)}" fill="{fill.upper()}"/>' for d, fill in paths
    )
    x, y = MARK_ORIGIN, MARK_ORIGIN
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{APP_ICON}" height="{APP_ICON}" '
        f'viewBox="0 0 {APP_ICON} {APP_ICON}">\n'
        f'  <rect width="{APP_ICON}" height="{APP_ICON}" fill="{BACKGROUND}"/>\n'
        f'  <g transform="translate({x} {y}) scale({MARK_SCALE})">\n'
        f"{body}\n"
        "  </g>\n"
        "</svg>\n"
    )


def png_ihdr(path: Path) -> tuple[int, int, int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{path.name} is not a PNG")
    length, kind = struct.unpack(">I4s", data[8:16])
    if kind != b"IHDR" or length < 13:
        raise SystemExit(f"{path.name} has no IHDR")
    width, height, bit, color = struct.unpack(">IIBB", data[16:26])
    return width, height, bit, color


def flatten_rgb(path: Path) -> None:
    """Apple's 1024 icon is opaque. Drop the alpha channel librsvg still writes."""
    width, height, bit, color = png_ihdr(path)
    if bit != 8 or color not in (2, 6):
        raise SystemExit(f"{path.name} is not 8-bit RGB or RGBA")
    if color == 2:
        return
    data = path.read_bytes()
    pos = 8
    idat = b""
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        kind = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"IDAT":
            idat += chunk
        elif kind == b"IEND":
            break
    raw = zlib.decompress(idat)
    channels = 4
    stride = width * channels
    out = bytearray()
    prev = bytearray(stride)
    index = 0
    for _y in range(height):
        filt = raw[index]
        index += 1
        row = bytearray(raw[index : index + stride])
        index += stride
        if filt == 1:
            for x in range(stride):
                left = row[x - channels] if x >= channels else 0
                row[x] = (row[x] + left) & 255
        elif filt == 2:
            for x in range(stride):
                row[x] = (row[x] + prev[x]) & 255
        elif filt == 3:
            for x in range(stride):
                left = row[x - channels] if x >= channels else 0
                row[x] = (row[x] + ((left + prev[x]) // 2)) & 255
        elif filt == 4:
            for x in range(stride):
                left = row[x - channels] if x >= channels else 0
                up = prev[x]
                upper_left = prev[x - channels] if x >= channels else 0
                row[x] = (row[x] + _paeth(left, up, upper_left)) & 255
        elif filt != 0:
            raise SystemExit(f"unsupported PNG filter {filt}")
        rgb = bytearray()
        for x in range(0, stride, 4):
            alpha = row[x + 3]
            if alpha != 255:
                raise SystemExit(
                    f"{path.name} has a translucent pixel; the icon must be opaque"
                )
            rgb += row[x : x + 3]
        prev = row
        out.append(0)
        out += rgb
    compressed = zlib.compress(bytes(out), 9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(b"".join((
        b"\x89PNG\r\n\x1a\n",
        _chunk(b"IHDR", ihdr),
        _chunk(b"IDAT", compressed),
        _chunk(b"IEND", b""),
    )))


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


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(
        ">I", zlib.crc32(kind + payload) & 0xFFFFFFFF
    )


def rasterize(svg: Path, png: Path, size: int) -> None:
    rsvg = shutil.which("rsvg-convert")
    if rsvg is None:
        raise SystemExit("rsvg-convert is required to rasterize the icon")
    subprocess.run(
        [rsvg, "-w", str(size), "-h", str(size), "-o", str(png), str(svg)],
        check=True,
    )
    flatten_rgb(png)
    width, height, bit, color = png_ihdr(png)
    if (width, height, bit, color) != (size, size, 8, 2):
        raise SystemExit(f"{png.name} became {width}x{height} color {color}")


def main() -> int:
    paths = logo_paths(SOURCE.read_text(encoding="utf-8"))
    mark = OUT / "mark.svg"
    icon = OUT / "icon.svg"
    mark.write_text(mark_svg(paths), encoding="utf-8")
    icon.write_text(icon_svg(paths), encoding="utf-8")
    rasterize(icon, OUT / "icon-1024.png", APP_ICON)
    rasterize(icon, OUT / "apple-touch-icon.png", TOUCH_ICON)
    print(f"wrote {mark.relative_to(ROOT)}")
    print(f"wrote {icon.relative_to(ROOT)}")
    print("wrote demos/lmdj-mark/icon-1024.png")
    print("wrote demos/lmdj-mark/apple-touch-icon.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
