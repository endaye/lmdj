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

## Producer handoff

The same trusted module now supplies `package_static` and a credential-free CLI
with `--source` and `--archive`. It emits a regular-member inner ZIP plus an
independently computed per-file digest/length manifest. The eventual GitHub
artifact may wrap that inner ZIP; authenticated bounded transport unwrapping is
still a publisher responsibility. The publisher must recompute the manifest;
producer-provided metadata cannot authenticate itself.

Only `_headers` and `.nojekyll` are omitted deliberately. The publisher must
supply known headers outside the untrusted output tree. Other hidden/config
files, symlinks, special files, oversize trees, existing outputs and an archive
path inside the source are rejected. Packaging validates the completed candidate
with the consumer before making the archive available. No untrusted process may
modify the source or destination concurrently; runner isolation remains required.

Verification of this extension: all 17 focused tests pass, including producer /
consumer round trip, attempted symlink leakage, executable config, self-inclusion
and preservation of existing output. A previously checked Portal build from the
#929 worktree packs and validates 3,764 files, a 58,053,946-byte archive and a
largest file of 1,392,522 bytes. This is local artifact compatibility evidence,
not proof of a GitHub PR build, authenticated download or Cloudflare Preview.

## Authenticated transport Task

Additional declared files: `scripts/ci/cloudflare_preview_download.py`,
`tests/build/ci_cloudflare_preview_download_test.py`, scope policy and this plan.
The trusted caller provides a GitHub read token and numeric PR/run/artifact IDs.
The downloader fetches all identity metadata itself and rejects redirects for
authenticated API requests. Only the artifact endpoint's authenticated 302 is
used; a fresh credential-free request downloads that signed storage URL.
No deployment token is required by this module.

The outer GitHub artifact must contain exactly one regular `static.zip` member.
Both transport download and inner extraction are bounded; current head is fetched
again after download before exposing the inner archive. The caller must still
invoke `extract_static`, run trusted content smoke, and revalidate current head
at publication/status time. No archive execution or platform mutation occurs.
The initial six transport tests cover authenticated identity selection, absent
storage credentials, moving head, foreign-run rejection before download, unsafe
outer member, bounded streaming and preservation of pre-existing output.
The subsequent review added nine API/redirect and missing-parent tests, bringing
the committed helper suite to 32 tests (17 archive/producer and 15 download/API).
Actual workflow/API
artifact acceptance remains pending; synthetic API fixtures are not live proof.
