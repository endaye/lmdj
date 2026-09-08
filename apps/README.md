# Core Hosts

`apps/` contains thin Hosts around the product-neutral Application Facade.

Active Headless Core Hosts:

- `core-cli` — one-request JSON CLI for scripting and black-box tests;
- `core-mcp` — MCP stdio Host over the same C ABI.

Other Core-dependent applications are `native-host`, `web-runtime-host` and
`creator-web`. [`docs-site`](docs-site/README.md) is the repository's documentation
site; it reads product manifests but does not run Core. `architecture-portal`
retains only immutable historical snapshot storage, not an active application.

Independent experiments live in [`demos/`](../demos/README.md):
[`web-runtime-lab`](../demos/web-runtime-lab/README.md) and
[`chameleon-lab`](../demos/chameleon-lab/README.md). They do not use Core or
Product Assembly. The Audio Lab is distinct from the deployed
`apps/web-runtime-host` diagnostic application.

Hosts may parse transport flags and protocol envelopes. They must not parse
`.lmdj` Project bundles, implement Domain behavior, call Project I/O directly,
or contain product-specific branches.
