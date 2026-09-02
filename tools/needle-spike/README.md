# Needle small-language-model spike

A technical validation, parallel to the product: can a 45M-parameter on-device
model turn spoken groovebox instructions into LMDJ tool calls the production
schema accepts?

This directory is **not product code**. It is not wired into
`scripts/core.sh`, it links no Core Module, it declares no Capability, and it
never mutates Project Truth. It reads `apps/core-mcp`'s tool table and reuses
that module's schema validator, so what it measures is conformance to the real
contract rather than to a second copy of it.

The model under test is [Needle 2](https://github.com/cactus-compute/needle)
(Cactus Compute, Apache-2.0): 45M parameters, a ~14 MB native library with the
weights baked in, byte-level grammar-constrained decoding for structured output.

## What the spike answers

`docs/research/2026-09-01-needle-on-device-tool-calling-spike.md` holds the
findings and the argument. In short, measured on the 30-utterance set in
`prompts/performance_intents.jsonl` over 15 tools:

| Measure | Result |
| --- | --- |
| Routing (right tool, or silence when wanted) | 24/30 (80%) |
| Schema validity of composed payloads | 25/25 (100%) |
| Argument accuracy | 11/15 (73%) |
| Latency p50 / p95 | 508 ms / 3.4 s |
| Peak RSS | 71 MB |

Three results drove the design here:

1. **Model-facing names matter more than surface size.** Presenting verb
   aliases (`set_tempo_and_groove`) instead of MCP wire names
   (`lmdj.sequence.settings.update`) is worth 13-22 points of routing accuracy.
   Cutting the surface from 15 tools to 8 was worth almost nothing.
2. **Confidence is unusable as a safety gate.** It runs *anti*-correlated with
   correctness on this set - wrong calls sit at median 0.995, correct ones at
   0.79-0.86 - and unlike the routing decision it is not even stable between
   runs.
3. **The `query` / `command` split in the MCP table is the gate that works.**
   The model does turn read-only questions into destructive commands ("am I
   still recording?" routed to `stop_recording`), so no `command` is ever
   auto-dispatchable regardless of confidence.

## Setup

The engine is a ~14 MB download on first use and is cached in
`~/.cache/cactus-needle/<engine version>/`. Nothing here is installed by the
repo's normal setup, on purpose.

```bash
python3 -m venv .venv
.venv/bin/pip install -r tools/needle-spike/requirements.txt
```

For an air-gapped machine, fetch the library elsewhere and point at it:

```bash
export NEEDLE_LIB_PATH=/path/to/libneedle.so
```

Telemetry: `cactus-needle` posts anonymous usage counts on each call. Every
entry point here sets `NEEDLE_TELEMETRY=0` before importing it, so running the
spike does not phone home.

## Use

```bash
cd tools/needle-spike

# One utterance, end to end.
../../.venv/bin/python -m needle_spike.cli "mute pad 3"

# See exactly what the model is shown.
../../.venv/bin/python -m needle_spike.cli --dump-surface

# Score the intent set. Add --verbose for per-case output.
../../.venv/bin/python -m needle_spike.bench
../../.venv/bin/python -m needle_spike.bench --naming mcp     # the A/B above
../../.venv/bin/python -m needle_spike.bench --surface full   # all 30 tools
../../.venv/bin/python -m needle_spike.bench --repeats 3      # stability check
```

Tests, from the repo root:

```bash
# No engine needed - pure schema projection and composition properties.
python3 tools/needle-spike/tests/tool_surface_test.py

# Needs the engine; SKIPs (exit 0) rather than fails when it is absent.
.venv/bin/python tools/needle-spike/tests/router_smoke_test.py
```

On one machine the routing decision is stable: across four fresh runs the three
ratios above and the exact set of six failing utterances were identical every
time. The `confidence` scalar is *not* stable - it moved between runs on cases
whose routing did not - which is one more reason not to build a gate on it.

## How it works

`tool_surface.py` projects each production MCP schema into two halves:

* **the model's half** - `bpm`, `slot`, `bars`, `swing_percent`, `playback`:
  what a person actually says;
* **the Host's half** - `project_path`, a fresh `command_id` per command,
  `expected_revision`, session handles, and every UUID entity reference.

The model never sees the Host's half. That is a correctness choice - a 45M model
asked for a UUID hallucinates one that fails the schema pattern - and a budget
choice: the engine has a fixed context window, and each hidden UUID field is a
~90-character regex. On the performance surface the projection cuts the tool
JSON from 6585 to 4861 bytes.

The window is small and does not grow: the parallel desk study in
`docs/research/2026-09-01-needle-class-on-device-command-models-for-lmdj.md`
records a 256-token sliding window with tools held as fixed KV sinks, which is
why raising `max_new_tokens` changes nothing and why every byte saved converts
directly into tools that fit.

`runtime.py` runs one utterance through Needle, maps the verb alias back to the
authoritative wire name, merges the Host's half back in, and validates the
result with `apps/core-mcp`'s own `validates`. It calls `complete`, never `run`,
so no tool body executes and nothing moves.

`bench.py` scores routing, schema validity and argument accuracy separately.
They fail for different reasons, and a run that routes perfectly but fills
`bpm: 120` for "set the tempo to 96" is useless.

## Known limits

* Entity references are stubbed on `HostContext`, not resolved. Turning "the
  drum loop" into an `asset_id` is a name-resolution problem this spike does not
  touch, and it is the largest missing piece before any of this is usable.
* `lmdj.sample.update_pad` requires the complete `playback` object, so the model
  invents values for every field the utterance never mentioned. "mute pad 3"
  routes correctly and validates cleanly while also setting `gain_millidb` to
  its floor - schema validation cannot see the problem, because each value is
  legal on its own. An adapter has to fetch, patch and resubmit rather than
  expose the raw schema.
* The 30-utterance set is hand-written by one person in one dialect of English,
  and the model was trained on smart-home and wearable tool calls, so absolute
  accuracy numbers here are indicative, not a benchmark.
* Fine-tuning (`pip install "cactus-needle[train]"`, JAX) is untested. The
  upstream 90 MB checkpoint plus LMDJ-specific intents is the obvious next
  experiment, and the one that would move the argument-accuracy number.
