#!/usr/bin/env python3
"""Creator Web entry point of the shared Web Host deployment orchestrator.

The implementation is apps/web-runtime-host/tools/deploy_orchestrator.py. This
file loads it as a separate module, selects the Creator Host, and re-exports
its names so callers and tests use it exactly as before.
"""

import importlib.util
from pathlib import Path

_SHARED_PATH = (
    Path(__file__).resolve().parents[2] / "web-runtime-host/tools/deploy_orchestrator.py"
)
_spec = importlib.util.spec_from_file_location(
    "creator_web_deploy_orchestrator", _SHARED_PATH
)
assert _spec is not None and _spec.loader is not None
_shared = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_shared)
_shared.HOST_ID = "creator-web"
globals().update(
    {name: value for name, value in vars(_shared).items() if not name.startswith("__")}
)

if __name__ == "__main__":
    raise SystemExit(_shared.main())
