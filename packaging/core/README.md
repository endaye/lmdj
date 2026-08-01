# LMDJ Core

This package contains the LMDJ Headless Core CLI and MCP stdio Hosts for one
platform. Both launchers use the bundled Product Assembly by default.

## Requirements

- macOS or Linux matching the package name
- Python 3.11 or newer for `bin/lmdj-core-mcp`

## CLI

Pass an absolute Workspace path and a JSON request:

```bash
bin/lmdj-core \
  --workspace /absolute/path/to/workspace \
  query \
  --request '{"operation":"provider.list"}'
```

Supply `--assembly /absolute/path/to/assembly.json` to override the bundled
Assembly explicitly.

## MCP

Start the strict stdio Host with an absolute Workspace path:

```bash
bin/lmdj-core-mcp --workspace /absolute/path/to/workspace
```

The launcher resolves its Python package, C ABI library, and Product Assembly
inside this extraction. The caller does not need a source checkout or
`PYTHONPATH`.

`build-manifest.json` records the Product Build, source revision, Assembly lock,
and SHA-256 identity of every shipped file.
