#!/usr/bin/env python3
"""Render Cloudflare response metadata for an already verified Creator dist."""

import importlib.util
import json
from pathlib import Path
import sys


def render(dist: Path) -> bytes:
    deploy = Path(__file__).resolve().parent
    sys.path.insert(0, str(deploy.parent / "tools"))
    spec = importlib.util.spec_from_file_location(
        "creator_deploy", deploy.parent / "tools/deploy_orchestrator.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    validated = module.render_deploy_headers(dist, deploy / "_headers").decode()
    # Cloudflare combines matching rules instead of Netlify's override behavior.
    # Keep the broad no-store once and reset it for each exact immutable asset.
    blocks = validated.strip().split("\n\n")
    base = (blocks[0] + "\n").encode()
    manifest = json.loads((dist / "host-manifest.json").read_text())
    types = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css"}
    routes = [("/", "text/html"), ("/index.html", "text/html")]
    for asset in manifest["assets"]:
        suffix = Path(asset["path"]).suffix
        block = f"\n/{asset['path']}\n  ! Cache-Control\n  Cache-Control: public, max-age=31536000, immutable\n"
        if suffix != ".wasm":
            block += f"  Content-Type: {types[suffix]}; charset=utf-8\n"
        base += block.encode()
    # Cloudflare does not attach UTF-8 charset parameters automatically.
    # Only manifest-authorized assets get MIME overrides; WASM has no charset.
    return base + "".join(
        f"\n{route}\n  Content-Type: {mime}; charset=utf-8\n"
        for route, mime in routes
    ).encode()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: cloudflare_headers.py VERIFIED_DIST")
    sys.stdout.buffer.write(render(Path(sys.argv[1])))
