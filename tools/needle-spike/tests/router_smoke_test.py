#!/usr/bin/env python3
"""Drive the real 45M engine over a few utterances.

Skips - it does not fail - when `cactus-needle` or its cached native engine is
absent, because the engine is a ~14 MB download and this spike must never turn
a clean checkout into a network dependency. See the README for setup.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

spike_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(spike_root))

os.environ.setdefault("NEEDLE_TELEMETRY", "0")


def skip(reason: str) -> None:
    print(f"needle spike router smoke tests: SKIP ({reason})")
    raise SystemExit(0)


try:
    import needle  # noqa: F401
except ImportError:
    skip("cactus-needle not installed")

from needle.agent import fetch  # noqa: E402

cached = (
    Path.home() / ".cache" / "cactus-needle" / fetch.ENGINE_VERSION / fetch._lib_name()
)
if not os.environ.get("NEEDLE_LIB_PATH") and not cached.exists():
    skip(f"engine not cached at {cached}")

from needle_spike.runtime import HostContext, NeedleRouter  # noqa: E402

router = NeedleRouter(surface="performance")
assert len(router.tools) == 15
host = HostContext()

# Two utterances with an unambiguous target, one that must not act at all.
# Routing accuracy is the bench's job; this asserts the plumbing holds.
for utterance in ("list the available providers", "make a four bar pattern"):
    router.reset()
    resolution = router.resolve(utterance, host)
    assert resolution.error is None, resolution.error
    assert resolution.called_a_tool, f"{utterance!r} produced no call"
    assert resolution.tool_name in {tool.name for tool in router.tools}
    assert resolution.tool_name != resolution.model_tool_name, "alias was not mapped back"
    assert resolution.payload is not None
    assert resolution.schema_valid, resolution.schema_reasons
    assert resolution.tool_surface in ("query", "command")

    # Host plumbing must be present and must be the Host's values.
    tool = {item.name: item for item in router.tools}[resolution.tool_name]
    for key in tool.host_parameters:
        assert key in resolution.payload, f"{key} missing from composed payload"
    if "project_path" in tool.host_parameters:
        assert resolution.payload["project_path"] == host.project_path

# A command may never be auto-dispatchable, however confident the model is.
router.reset()
pattern = router.resolve("make a four bar pattern", host)
assert pattern.tool_surface == "command"
assert not pattern.auto_dispatchable, "commands must require confirmation"

router.reset()
providers = router.resolve("list the available providers", host)
assert providers.tool_surface == "query"
assert providers.auto_dispatchable

print("needle spike router smoke tests: PASS")
