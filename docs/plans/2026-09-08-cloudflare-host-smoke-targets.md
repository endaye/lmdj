# Explicit isolated Host smoke targets

Relates to #873 and #924.

## Task

Allow the existing exact-byte Host HTTP verifier to validate the isolated recovery
Workers without accepting arbitrary production/foreign hosts. Add explicit
`--recovery-target` and require a hexadecimal eight-character version prefix for
Preview URLs. Keep all existing payload/header/negative-path checks.

Declared files: shared cloudflare_smoke.py, new cloudflare_smoke_target_test.py,
scripts/web-runtime-host.sh test registration, Creator/Runtime deployment runbooks,
current Creator/Runtime Portal Host pages, and this plan.

Validation: target matrix tests, shared API tests, shell syntax, staged ownership,
full docs-site check, and read-only checks of both retained signed distributions
against their current official URLs. Isolated cloud mutation and complete browser
journey remain separate work under #924. No new merge gate.

## Version Management

Version impact: none; deployment verification tooling, no Product/Assembly or
formal serialized Contract change. Results remain migration observations.

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/ /hosts/web-runtime/
