# Retained verified Host release inputs

Relates to #873 and #924.

## Task

The existing Host verifier discards its signed staging inputs on exit. Add
`stage TAG ABSOLUTE_OUTPUT_DIRECTORY` to both stable Host deploy scripts so
Cloudflare candidate/recovery commands can reuse retained release inputs.

Declared files:
- `scripts/creator-web-deploy.sh`
- `scripts/web-runtime-deploy.sh`
- `apps/web-runtime-host/tools/cloudflare_release_stage.py`
- `apps/web-runtime-host/test/cloudflare_release_stage_test.py`
- `scripts/web-runtime-host.sh` (test registration)
- `apps/creator-web/test/deploy_command_test.py`
- `apps/web-runtime-host/test/deploy_command_test.py`
- `docs/deploy/creator-web.md`
- `docs/deploy/web-runtime-host.md`
- this plan.

Reuse the existing exact remote tag/signature/Release/Host package checks. The
export helper is called only after verification, checks the verified archive and
entry-point digests, refuses existing/relative outputs and symlink inputs, copies
the signed archive/checksum/signature and verified dist, and archives the exact
verified source commit. Record every retained file's digest and byte length.
Flush the retained inputs and directories before writing the completion receipt.
Incomplete directories are preserved; no implicit overwrite or cleanup.

The receipt is private staging state, not a formal deployment evidence Contract
or permission to publish. Later operations must independently reverify retained
signatures and package resources before binding them to Cloudflare versions.
No candidate upload, route mutation, promotion or Channel operation occurs here.
Remove CLOUDFLARE_API_TOKEN from GitHub and source-verification child environments
so a caller preparing a later deployment does not leak that credential upstream.

Validation: six exporter tests covering both Hosts and corrupted/mismatched
inputs; existing Host orchestrator and release-bundle tests; shell syntax and
staged ownership checks. Exercise both stage commands with the already published
signed lmdj-v1.0.42.0 artifacts. Fixture exporter tests are not signature proof;
the existing signature verifier and actual stable-command run supply that proof.

## Version Management

Version impact: none; operator staging tooling only. No Product/Assembly or
formal Contract changes, and no Netlify evidence is repurposed.

## Documentation Impact

Documentation impact: none; current Portal deployment behavior and published
sites are unchanged. Both operator runbooks document the new staging-only mode.
