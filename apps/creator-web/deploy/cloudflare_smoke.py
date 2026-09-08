#!/usr/bin/env python3
"""Creator compatibility entry point for shared Cloudflare deployment tooling."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[2] / "web-runtime-host/tools/cloudflare_smoke.py"), run_name="__main__")
