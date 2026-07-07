from __future__ import annotations

import argparse
from pathlib import Path

from lmdj_patchify.patchify import patchify_package


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create an LMDJ patch.json from a pipeline package.")
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    patchify_package(args.package_dir, args.out)
    out_path = args.out or args.package_dir.resolve() / "patch.json"
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
