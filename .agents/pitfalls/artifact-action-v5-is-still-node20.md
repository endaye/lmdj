---
id: artifact-action-v5-is-still-node20
area: ci-release
status: open
recurrences:
  - date: 2026-09-14
    occurrence: https://github.com/endaye/lmdj/actions/runs/34766080482
    observed_by: Hermes Agent
exit: none
---

# An Actions major-version bump does not imply the runtime the release notes advertise; read the pinned ref's `action.yml`.

## Why

`actions/upload-artifact@v5.0.0` and `actions/download-artifact@v5.0.0`/`v6.0.0`
announce "Node 24 support" in their release notes, yet their `action.yml` still
declares `runs.using: node20`; the first releases whose `action.yml` declares
`node24` are upload-artifact `v6.0.0` and download-artifact `v7.0.0`. Trusting
the release-note headline leaves the Node 20 deprecation warning in place while
appearing to fix it. The runtime declaration is not derivable from the version
number or the notes, and no offline contract test can pin it because verifying
it requires a network read of the upstream `action.yml`.

## How to apply

When bumping a JS action to clear a runner-runtime deprecation, fetch
`action.yml` at the exact tag (or commit SHA) you are about to pin and read
`runs.using:`. Pin first-node24 majors: upload-artifact v6, download-artifact
v7, cache v5. Re-check on every future runtime migration; do not infer the
runtime from the major version or the release notes.
