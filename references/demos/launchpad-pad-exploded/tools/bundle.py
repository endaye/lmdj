#!/usr/bin/env python3
"""Bundle the demo into one self-contained HTML file.

Reads index.html, styles.css, data.js, diagrams.js and main.js from the demo
root, inlines the CSS, concatenates the three ES modules into a single
<script type="module"> (Three.js is still loaded from jsDelivr), and writes
dist/launchpad-pad-exploded.html. The output keeps a full <!doctype html>
document so it opens directly from disk or any static host.

Usage: python3 tools/bundle.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / "launchpad-pad-exploded.html"
THREE_URL = "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js"


def strip_module(src: str) -> str:
    src = re.sub(r"^import .*?;\n", "", src, flags=re.M | re.S)
    return re.sub(r"^export (const|function|let|class) ", r"\1 ", src, flags=re.M)


def main() -> int:
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    modules = [strip_module((ROOT / name).read_text(encoding="utf-8")) for name in ("data.js", "diagrams.js", "main.js")]
    js = f'import * as THREE from "{THREE_URL}";\n' + "\n".join(modules)

    body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
    body = re.sub(r'\s*<script type="module" src="./main.js"></script>', "", body).rstrip()
    page = (
        "<!doctype html>\n<html lang=\"zh-CN\">\n<head>\n"
        '<meta charset="UTF-8" />\n<meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        "<title>Launchpad Pad 爆炸机构图</title>\n"
        f"<style>\n{css}\n</style>\n</head>\n<body>{body}\n"
        f'<script type="module">\n{js}\n</script>\n</body>\n</html>\n'
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(page.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
