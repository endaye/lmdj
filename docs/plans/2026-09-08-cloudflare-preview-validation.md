# Cloudflare Preview artifact validation

Relates to #922 and #873. This is the input-validation portion of the approved
trusted publisher alternative, not a complete Preview deployment pipeline.

## Task and declared files

- `scripts/ci/cloudflare_preview_artifact.py`: pure validation of authenticated
  GitHub metadata and untrusted static ZIP contents; no network, subprocess or
  deployment operation.
- `tests/build/ci_cloudflare_preview_artifact_test.py`: current/stale head,
  unsuccessful build, foreign source, wrong attempt/run, exact extraction,
  traversal, symlinks, uploaded configuration, expansion and existing output.
- `scripts/ci/scope_policy.json`: route both files to their CI discovery lane.
- This plan.

The eventual build workflow is named `cloudflare-preview-build.yml`. Its producer
must emit regular ZIP members, no directory records, and omit upload config and
hidden files. The publisher generates its own fixed config and headers outside
this tree. Limits here are conservative publisher policy, not an authenticated
Cloudflare account entitlement. The upload directory is private and new; caller
must not share it with untrusted processes or consume partial output.

The caller must retrieve metadata and the selected artifact from authenticated
GitHub APIs, enforce download size while streaming, supply the exact run's
artifact, and re-read current PR head immediately before publication/status.
This module alone cannot authenticate caller-supplied dictionaries, establish
runner isolation, validate content identity, run smoke or publish a status.
Those remaining responsibilities stay in #922. Malformed input fails closed.

## Validation

Run `python3 -m unittest discover -s tests/build -p
'ci_cloudflare_preview_artifact_test.py'` and staged
`python3 tests/build/ci_change_scope_test.py`. Tests name concrete stale-evidence
and archive-boundary failures; no new merge gate is introduced. Review before
using this module with a deployment credential.

## Version Management

Version impact: none. Internal unpublished helper; no Product/Host/Contract or
serialized production deployment evidence changes.

## Documentation Impact

Documentation impact: none. No current Portal page or deployed workflow changes;
this plan explicitly retains the remaining producer/publisher integration work.
