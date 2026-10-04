#!/usr/bin/env python3

"""The Creator tab icon is the LogoIcon plate, linked once from the shell."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
ICONS = REPO_ROOT / "apps/creator-web/src/components/hardware_icons.tsx"
FAVICON = REPO_ROOT / "apps/creator-web/public/favicon.svg"
INDEX = REPO_ROOT / "apps/creator-web/index.html"
PATH_FILL = re.compile(
    r'<path\b[^>]*\bd="([^"]+)"[^>]*\bfill="(#[0-9A-Fa-f]{6})"'
)


def logo_paths(source: str) -> list[tuple[str, str]]:
    start = source.index("export function LogoIcon")
    end = source.index("export function ProjectIcon", start)
    return PATH_FILL.findall(source[start:end])


class CreatorFaviconTest(unittest.TestCase):
    def test_public_favicon_is_the_logoicon_plate(self) -> None:
        paths = logo_paths(ICONS.read_text(encoding="utf-8"))
        self.assertEqual(len(paths), 4)
        svg = FAVICON.read_text(encoding="utf-8")
        for geometry, fill in paths:
            self.assertEqual(svg.count(f'd="{geometry}"'), 1)
            self.assertIn(f'fill="{fill}"', svg)
        self.assertIn('viewBox="0 0 32 32"', svg)
        self.assertIn('fill="#0a0b09"', svg)
        self.assertIn("translate(2 2) scale(0.35)", svg)
        index = INDEX.read_text(encoding="utf-8")
        self.assertEqual(
            index.count(
                '<link rel="icon" href="/favicon.svg" type="image/svg+xml" />'
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
