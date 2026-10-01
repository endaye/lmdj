# Original default Sound Set assets

`products/lmdj/assets/default-kit` contains sixteen original synthesized WAV
objects and the canonical Sound Set/Catalog manifests. `RIGHTS.md` records their
CC0 provenance. Generate with `python3 tools/asset-server/kit.py`, then run
`scripts/asset-server.sh check`. Review changed source and immutable object hashes
together; never replace an existing hash with different bytes.

The independent `lmdj-default-assets` Cloudflare Worker uses the established
account from the Creator deployment configuration. Its public surface is:

- `GET|HEAD /catalog/index.json`
- `GET|HEAD /object/manifest/<sha256>`
- `GET|HEAD /object/blob/<sha256>`
- `GET|HEAD /health`

Only those routes reach storage. Objects have immutable cache headers; the Catalog
has a short revalidation lifetime. Direct corpus files are not public routes.

Dispatch `deploy-default-assets.yml` on protected `main` after review and Task
verification. It uses the existing `creator-canary` protected environment and
Cloudflare credential, deploys this independent Worker, then authenticates every
live object against committed bytes. An environment approval remains external to
source verification. The retained artifact binds the actual workers.dev origin,
source revision and live GET evidence. A green source test is not deployment.

Bind Creator's `CATALOG_UPSTREAM` to the reported verified origin with a trailing
slash in the streaming boot Task. Creator continues fetching its same-origin
`/soundset-catalog/` proxy under the existing CSP. This service deployment does not
deploy Creator or promote a Product Channel. Keep prior immutable object hashes
available when updating the Catalog so existing cached Set identities can resolve.
