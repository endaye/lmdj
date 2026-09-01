# LMDJ Dual Web Host Release and Deployment Design

Date: 2026-09-01

Status: Approved

## 1. Problem

Product Build `1.0.40.0` contains both `creator-web` and
`web-runtime-host` in Product Assembly, but its `web-runtime-host` Release
profile publishes only the diagnostic Runtime Host archive. The manual Netlify
deployment workflow consumes that one archive and publishes only
`https://lmdj-runtime.netlify.app/`.

The result is technically correct but incomplete as a product delivery:

- the deployed Runtime URL is a diagnostic and acceptance surface, not the
  user-facing Creator;
- Creator has a production distribution builder and proof suite, but no signed
  Product Release asset;
- Creator has no independent Netlify site, deployment workflow, production
  smoke test, rollback evidence, or canonical production URL;
- adding Creator files to the already-published `1.0.40.0` Release would violate
  the immutable published-Release boundary.

## 2. Decision

Allocate Product Build `1.0.41.0` and introduce one closed `web-hosts` Product
Release profile. One signed Product tag and one GitHub Release publish exactly
two independently verifiable Host archives:

1. the Formal Web Runtime Host;
2. the Creator Web Host.

The two Hosts deploy to separate Netlify sites and remain separate authorization,
verification, rollback, and evidence boundaries:

| Host | Purpose | Production URL | Environment |
| --- | --- | --- | --- |
| Creator Web Host | User-facing creation surface | `https://lmdj-creator.netlify.app/` | `creator-canary` |
| Web Runtime Host | Diagnostic and Runtime acceptance surface | `https://lmdj-runtime.netlify.app/` | `runtime-canary` |

Release publication does not trigger either deployment. A successful deployment
of one Host does not authorize or imply deployment of the other.

## 3. Alternatives

### 3.1 Selected: one Product Release with two Host payloads

This keeps Product Build, tag target, source revision, Assembly lock, CI evidence,
and release notes unified while allowing each Host to deploy and roll back
independently.

### 3.2 Rejected: separate Product Releases for each Host

One Product tag cannot canonically identify two separately mutable GitHub
Releases. Separate tags would either invent two Product identities for one
Assembly or make Host delivery state appear to be Product Build state.

### 3.3 Rejected: build Creator inside the deployment workflow

Deployment must consume immutable, signed, published Release bytes. Rebuilding
from source during deployment would make the production payload different from
the audited Release inventory and would prevent exact byte rollback.

## 4. Scope

This work includes:

1. Product Build `1.0.41.0` and its immutable Architecture Portal snapshot;
2. a closed `web-hosts` Release profile with exact six-asset inventory;
3. deterministic Creator archive construction and verification;
4. backward-compatible audit and verification of historical single-Host
   Releases, including `1.0.40.0`;
5. a manual-only Creator Netlify deployment workflow;
6. Creator immutable-deploy and production smoke tests;
7. Creator failure recovery to the exact prior published Netlify deploy;
8. independent deployment evidence for both Host roles;
9. release, deployment, testing, and Host documentation updates.

This work does not include:

- editing or replacing `1.0.40.0` tag or Release assets;
- automatic deployment after Release publication;
- coupling the two Host deployment mutations into one workflow;
- Channel promotion;
- a custom apex domain, DNS migration, PWA/offline installation, Creator feature
  changes, or Runtime behavior changes;
- storing Netlify credentials, private signing keys, device identities, Project
  Truth, or user audio in repository or deployment evidence.

## 5. Product and Host Identity

The new Product identity is `1.0.41.0`, with tag candidate
`lmdj-v1.0.41.0` and initial Channel `canary`.

`1.0.40.1` is not used. The prospective version policy forbids PATCH from
changing Product Assembly identity or adding delivery capability. A new
user-facing production Host deployment and a new Product Release inventory are
a new integrated Product Build.

The Host implementations remain `creator-web@2.1.1` and
`web-runtime-host@2.1.1` unless implementation changes a Host public API or
behavior. The distributions embed Product Build `1.0.41.0`, so their bytes and
manifests still bind to the new Product Build even when Host SemVer is unchanged.

The existing `lmdj.creator-web.distribution.v1` and
`lmdj.web-runtime-host.distribution.v1` contracts remain independent. The new
`web-hosts` name is a repository release profile, not a public cross-language
Contract.

## 6. Closed Release Inventory

The `web-hosts` profile produces exactly these six custom assets, with Host
versions and Product Build derived from exact-tag source manifests:

```text
lmdj-web-runtime-host-2.1.1-product-1.0.41.0.zip
lmdj-web-runtime-host-2.1.1-product-1.0.41.0.zip.sha256
lmdj-web-runtime-host-2.1.1-product-1.0.41.0.zip.sha256.asc
lmdj-creator-web-2.1.1-product-1.0.41.0.zip
lmdj-creator-web-2.1.1-product-1.0.41.0.zip.sha256
lmdj-creator-web-2.1.1-product-1.0.41.0.zip.sha256.asc
```

Each ZIP is deterministic and contains exactly one `dist/` tree. Each checksum
names exactly its paired archive. Each checksum has its own armored detached
signature made by the existing Release checksum signing role. The Product tag
continues to use the separate Product signing role.

The Release plan lists all six assets in canonical name order. Verification
requires exact cardinality, exact names, regular-file safety, sizes, SHA-256
digests, checksum contents, checksum signatures, and the Host-specific
distribution verifier for both archives. Missing, extra, duplicated, renamed,
or cross-paired assets fail closed.

The existing `web-runtime-host` profile remains valid and unchanged for
historical Releases. Audit selects inventory rules from each exact intent; it
does not reinterpret old Releases under the new profile.

## 7. Build and Verification Flow

The profile builder runs from the exact release target in the existing scratch
worktree and locked Node/Emscripten environment.

For the Runtime Host it retains the existing configure, build, test, proof,
package, deterministic ZIP, and release-bundle verification path.

For Creator it runs the existing Creator configure, build, test, proof, and
package path, then:

1. verifies `build/web/creator/dist` with the Creator distribution verifier;
2. creates the deterministic Creator ZIP using the same safe `dist/` archive
   rules as the Runtime Host;
3. creates and verifies its detached checksum;
4. signs and verifies the checksum in an isolated public-key-only keyring;
5. re-stages the archive into a temporary directory and reruns the Creator
   distribution verifier against extracted bytes.

Shared deterministic archive and signed-checksum operations become
product-neutral helpers inside release tooling. Host-specific manifest and
distribution verification stays owned by the corresponding Host package.

## 8. Deployment Architecture

### 8.1 Independent workflow entry points

The Runtime deployment remains:

```text
.github/workflows/deploy-web-runtime-host.yml
scripts/web-runtime-deploy.sh
```

Creator adds:

```text
.github/workflows/deploy-creator-web.yml
scripts/creator-web-deploy.sh
```

Both workflows are `workflow_dispatch` only and accept one exact signed Product
tag. Each independently verifies that the tag resolves to a published,
non-Draft Release with the canonical `web-hosts` inventory. Each selects only
its Host's signed archive triplet for staging, while still requiring the entire
six-asset Release to pass canonical verification.

Neither workflow calls the other, publishes a Release, promotes a Channel, or
uses source-tree build output as a deployment payload.

### 8.2 Netlify sites and credentials

Runtime retains `NETLIFY_RUNTIME_SITE_ID` and the existing Netlify access token
inside `runtime-canary`.

Creator uses `NETLIFY_CREATOR_SITE_ID` and a Netlify access token inside
`creator-canary`. The expected production hostname is fixed in repository
deployment policy as `lmdj-creator.netlify.app`; a mismatched Site identity or
production hostname fails before publication.

Creating the Netlify Site, adding Environment secrets, and configuring GitHub
Environment branch policy are external state transitions. They require separate
authorization and live verification after the workflow is merged. Repository
code never creates or prints credentials.

### 8.3 Creator deployment transaction

Creator follows the Runtime deployment transaction:

1. verify exact tag, published Release, complete inventory, signatures, and
   Creator distribution;
2. read and validate the current production Site and prior published deploy;
3. create a draft deploy from the verified extracted Creator `dist/`;
4. run HTTP and Chromium smoke against the immutable draft URL;
5. publish that exact deploy ID;
6. run HTTP and Chromium smoke against the production URL;
7. write privacy-bounded deployment evidence.

If publication was attempted but completion is not proven, recovery first
reconciles the current published deploy ID. When the attempted deploy is current
and post-publication verification fails, recovery restores the exact prior
published deploy and reruns bounded smoke. It never uploads reconstructed bytes
or chooses a rollback target by timestamp.

## 9. Creator Production Smoke

The HTTP smoke requires HTTPS, exact Netlify deploy identity, cache policy,
cross-origin isolation headers, CSP, canonical index and manifest bytes, complete
hashed asset inventory, Product Build `1.0.41.0`, Host `creator-web@2.1.1`, and
no source maps, local paths, fixtures, or forbidden retired-contract markers.

The Chromium smoke uses the packaged production surface and proves:

1. the page boots in a secure, cross-origin-isolated context;
2. Runtime and Creator manifests agree on Product, Host, Platform, protocol,
   toolchain, and resource limits;
3. the Creator workspace renders without fatal diagnostics;
4. a browser-local Project can be created or opened through the Application
   Facade;
5. a deterministic WAV fixture can be imported and assigned to a Pad;
6. audio can be activated through an explicit gesture and the assigned Pad
   yields one admitted and one completed Runtime outcome;
7. Sample Editor and Sequence Recording surfaces remain present;
8. reload reopens durable Project Truth without persisting Runtime Snapshot as
   Project Truth.

The deployment smoke does not claim physical MIDI, physical Touch, microphone,
latency, long-duration foreground operation, accessibility, or subjective audio
quality. Those remain separately retained physical/manual gates.

## 10. Evidence and Privacy

Each Host writes an independent deployment-evidence document containing:

- exact tag, target revision, Product Build, Host ID/version, Release ID, and
  selected asset digests;
- Netlify Site ID only where existing policy already treats it as operational
  identity, attempted immutable deploy ID/URL, prior deploy ID/URL, and final
  production pointer;
- immutable and production HTTP/Chromium smoke results;
- publication response projection and any recovery result;
- workflow run ID and UTC start/end timestamps.

Evidence excludes tokens, secret names with values, browser storage contents,
Project/Pattern/Asset UUIDs, uploaded audio bytes, MIDI device identity, raw MIDI
messages, absolute local paths, and full Netlify API responses.

## 11. Failure Semantics

- A failure before Netlify draft creation changes no production state.
- A failed immutable smoke leaves the draft unpromoted.
- A Site/hostname mismatch stops before upload or publication.
- A Release inventory or signature mismatch stops both Host deployments for
  that exact tag until a new corrective Product identity is released; published
  assets are never overwritten.
- A Creator production smoke failure after publication triggers exact prior
  deploy recovery and records both attempted and restored identities.
- Failure of one Host deployment does not roll back or mutate the other Host.
- An uncertain Netlify response is reconciled by exact deploy and Site IDs
  before any retry; the workflow does not blindly create or publish another
  deploy.

## 12. Authorization Boundaries

The following remain separate decisions and verification boundaries:

```text
implementation commit
  -> branch push
  -> Pull Request creation
  -> squash merge
  -> exact-main full CI evidence
  -> release-intent binding
  -> prepare
  -> exact tag push
  -> Draft creation
  -> protected publication
  -> Creator Site provisioning/configuration
  -> Creator deployment
  -> Runtime deployment
  -> Channel promotion
```

The implementation PR allocates Product Build `1.0.41.0` and its immutable
snapshot but does not bind a release intent to a pre-squash revision. Intent
binding occurs in a later reviewed evidence Task after the exact protected-main
squash SHA and qualifying full CI run exist.

## 13. Testing

Repository tests cover:

- closed release-policy schema and `web-hosts` intent acceptance;
- exact six-asset build, canonical order, persistence, reconstruction, Draft,
  publication, and remote audit paths;
- historical `web-runtime-host` three-asset compatibility;
- Creator deterministic ZIP and Host-specific bundle verification;
- missing/extra/renamed/cross-paired asset failures;
- wrong checksum signer and Product/checksum signer role swapping;
- both workflows remaining manual-only and environment-isolated;
- deployment scripts selecting only their Host payload while validating the
  complete Release;
- Creator Site identity, draft deploy, immutable smoke, publication,
  production smoke, uncertain response reconciliation, and exact rollback;
- secret/environment scrubbing and evidence allowlists;
- Product/Assembly/version/snapshot consistency and Architecture Portal checks.

Before the implementation commit, run the complete release test family,
Creator proof, Runtime Host proof, deployment contract tests, version checks,
and Architecture Portal check. Release preparation later reruns the exact-tag
profile build and verification from clean source.

## 14. Version Management

Version impact: required.

- Product Build: `1.0.40.0` -> `1.0.41.0`.
- Product tag candidate: `lmdj-v1.0.41.0`.
- Initial Channel: `canary`.
- Product Assembly and generated lock: update to Product Build `1.0.41.0`.
- Creator Web Host: remains `2.1.1` unless implementation changes Host public
  behavior or API.
- Web Runtime Host: remains `2.1.1` unless implementation changes Host public
  behavior or API.
- Module, Provider, Model, and public Contract versions: no change expected.
- Release profile: add repository-internal `web-hosts`; this is not a public
  Contract identity.
- Compatibility: Project Truth and Runtime Snapshot contracts are unchanged;
  historical Releases retain their original inventory interpretation.
- Rollback: each Netlify site restores its own exact prior published deploy;
  immutable tag and Release identities are never moved or edited.

The implementation Task allocates and snapshots the Product Build but does not
authorize or execute tag creation, tag push, Draft, publication, deployment, or
Channel promotion.

## 15. Documentation Impact

Documentation impact: required.

Affected current Architecture Portal routes:

- `/hosts/creator-web/`
- `/hosts/web-runtime/`
- `/operations/version-and-release/`
- `/operations/testing-and-proof/`
- `/operations/deployment/` where represented by the current portal taxonomy

The Task updates source diagrams and current pages, then freezes the immutable
`1.0.41.0` canary snapshot using the canonical Architecture Portal command.
Permanent production documentation is Git-triggered; no manual Portal upload is
performed.

## 16. Completion Criteria

Implementation is complete only when:

- `1.0.41.0` manifests, Assembly lock, generated identities, and immutable
  snapshot agree;
- `web-hosts` produces and verifies exactly six signed assets;
- historical single-Host Release tests remain green;
- Creator and Runtime deployment workflows are manual-only and independently
  gated;
- Creator deployment transaction, smoke, evidence, and exact rollback tests
  pass;
- Creator and Runtime proofs, release tests, deployment contracts, version
  checks, and Portal checks pass;
- the implementation is committed on its isolated feature branch.

The Product Build is released only after the later exact-main intent, signed
tag, Draft, protected publication, Creator deployment, Runtime deployment, and
canonical verification boundaries have each been separately authorized and
proven. Channel promotion is not implied by completing those deployments.
