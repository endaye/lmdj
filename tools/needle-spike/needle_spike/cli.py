"""One-shot: say something, see the LMDJ call it would produce.

    python3 -m needle_spike.cli "mute pad 3"
"""

from __future__ import annotations

import argparse
import json
import sys

from .runtime import HostContext, NeedleRouter
from .tool_surface import dump_surface


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="needle-spike",
        description="Resolve one utterance into a validated LMDJ MCP payload.",
    )
    parser.add_argument("utterance", nargs="*", help="what you would say to the groovebox")
    parser.add_argument("--surface", choices=("performance", "full"), default="performance")
    parser.add_argument("--naming", choices=("verb", "mcp"), default="verb")
    parser.add_argument(
        "--dump-surface",
        action="store_true",
        help="print the tool schemas handed to the model, then exit",
    )
    arguments = parser.parse_args(argv)

    if arguments.dump_surface:
        print(dump_surface(arguments.surface, arguments.naming))
        return 0
    if not arguments.utterance:
        parser.error("give an utterance, or use --dump-surface")

    router = NeedleRouter(surface=arguments.surface, naming=arguments.naming)
    resolution = router.resolve(" ".join(arguments.utterance), HostContext())

    print(f"utterance   {resolution.utterance}")
    print(f"envelope    {resolution.envelope_type}")
    if resolution.error:
        print(f"error       {resolution.error}")
        return 1
    if resolution.confidence is not None:
        print(f"confidence  {resolution.confidence:.4f}")
    print(f"latency     {resolution.latency_ms:.0f} ms")
    if resolution.peak_ram_mb is not None:
        print(f"peak rss    {resolution.peak_ram_mb:.1f} MB")

    if not resolution.called_a_tool:
        print("tool        <none: the model chose to answer rather than act>")
        return 0

    print(f"tool        {resolution.tool_name}  (model said {resolution.model_tool_name})")
    print(f"model args  {json.dumps(resolution.model_arguments, sort_keys=True)}")
    rendered = json.dumps(resolution.payload, indent=2, sort_keys=True)
    print("payload     " + rendered.replace("\n", "\n            "))
    print(f"schema      {'valid' if resolution.schema_valid else 'INVALID'}")
    for reason in resolution.schema_reasons:
        print(f"            {reason}")

    # A schema-valid payload is not a safe one. Say which way the gate falls,
    # so a passing schema is never mistaken for permission to dispatch.
    if resolution.auto_dispatchable:
        print(f"gate        auto-dispatchable ({resolution.tool_surface})")
    else:
        print(f"gate        needs confirmation ({resolution.tool_surface})")
    return 0 if resolution.schema_valid else 1


if __name__ == "__main__":
    sys.exit(main())
