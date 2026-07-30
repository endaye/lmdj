# Core Hosts

`apps/` contains thin Hosts around the product-neutral Application Facade.

The M1 Headless Core Proof will add:

- `core-cli` — one-request JSON CLI for scripting and black-box tests;
- `core-mcp` — MCP stdio Host over the same C ABI.

Hosts may parse transport flags and protocol envelopes. They must not parse
`.lmdj` Project bundles, implement Domain behavior, call Project I/O directly,
or contain product-specific branches.

`creator-web` is a later Host and is intentionally absent from M1.
