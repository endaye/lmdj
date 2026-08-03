# Core Hosts

`apps/` contains thin Hosts around the product-neutral Application Facade.

Active Headless Core Hosts:

- `core-cli` — one-request JSON CLI for scripting and black-box tests;
- `core-mcp` — MCP stdio Host over the same C ABI.

`web-runtime-lab` is a product-neutral experimental Host for isolated browser
AudioWorklet, WebAssembly, SharedArrayBuffer, MIDI, and lifecycle evidence. It
is not Product Assembly and does not claim that `creator-web` exists.

Hosts may parse transport flags and protocol envelopes. They must not parse
`.lmdj` Project bundles, implement Domain behavior, call Project I/O directly,
or contain product-specific branches.

`creator-web` remains a later Host and is intentionally absent.
