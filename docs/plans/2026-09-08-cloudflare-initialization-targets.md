# Isolated Cloudflare first-deployment acceptance

Relates to #924 and #873. Existing recovery Workers retain versions and cannot
prove never-deployed behavior. Add fixed creator-initialization and
runtime-initialization targets mapping to creator-initialization and
lab-initialization in the existing account. Preserve production and recovery
resources. No arbitrary Worker names or account overrides are admitted.

Declared files: this plan; shared cloudflare_api.py, cloudflare_host.py,
cloudflare_smoke.py; cloudflare_smoke_target_test.py and cloudflare_host_test.py;
docs/deploy/cloudflare-hosts.md. All Python paths are under
apps/web-runtime-host/tools or apps/web-runtime-host/test respectively.

Validation: explicit initialization selection accepts only the matching Host,
account and fixed Worker; production/recovery/initialization targets cannot be
confused. Run existing API, command, target and transaction tests. Real stable
CLI candidate --initialize must start from positive absence, verify signed bytes
and preserve a disabled fixed route. Exercise first promotion failure with real
HTTP verification and require disabled-route recovery. Retain observations and
versions; no site deletion, Release or Channel mutation.

## Version Management

Version impact: none. Internal operator targets only; no Product, Assembly or
serialized deployment Contract change.

## Documentation Impact

Documentation impact: none. Existing Portal command descriptions stay valid;
the operator runbook names the additional isolated acceptance targets.
