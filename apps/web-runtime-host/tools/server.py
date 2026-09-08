#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_SERVER = REPO_ROOT / "tools/web-runtime/serve_distribution.py"
PACKAGE_TOOL = Path(__file__).with_name("package.py")


def _load_shared():
    spec = importlib.util.spec_from_file_location("lmdj_shared_web_server", SHARED_SERVER)
    if spec is None or spec.loader is None:
        raise RuntimeError("shared Web distribution server cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_shared = _load_shared()
CSP = _shared.CSP
SECURITY_HEADERS = _shared.SECURITY_HEADERS
HASHED_ASSET = _shared.HASHED_ASSET
CONTENT_TYPES = _shared.CONTENT_TYPES
ServerError = _shared.ServerError
ProofServer = _shared.ProofServer
ProofHandler = _shared.ProofHandler
read_file_no_follow = _shared.read_file_no_follow


def load_distribution_verifier():
    return _shared.load_verifier(PACKAGE_TOOL)


# No `catalog_upstream` parameter, on purpose. The diagnostic Host has no Sound
# Set surface, so its entry point cannot configure a Catalog to forward to --
# the same gate the Lab's `wrangler.json` closes by carrying neither the
# variable nor the route (#901).
def make_server(
    root: Path,
    host: str = "127.0.0.1",
    port: int = 4175,
    verbose: bool = False,
) -> ProofServer:
    return _shared.make_server(
        root,
        load_distribution_verifier(),
        REPO_ROOT,
        host,
        port,
        verbose,
    )


def main() -> int:
    return _shared.main(
        default_verifier=PACKAGE_TOOL,
        default_repo_root=REPO_ROOT,
    )


if __name__ == "__main__":
    raise SystemExit(main())
