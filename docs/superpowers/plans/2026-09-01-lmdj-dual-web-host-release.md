# LMDJ Dual Web Host Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allocate Product Build `1.0.41.0`, publish Creator and Runtime as one exact signed six-asset Product Release, and add an independently gated Creator Netlify deployment path.

**Architecture:** Add a backward-compatible `web-hosts` release profile that builds and verifies two Host archives from one exact tag while retaining the historical `web-runtime-host` profile. Extract the existing Runtime deployment transaction into Host-configured shared tooling, keep two manual workflows and two Netlify sites, and freeze the `1.0.41.0` Portal snapshot only after all projected source and documentation are final.

**Tech Stack:** Python 3.11 standard library, Bash, GitHub Actions YAML, Node 22, Emscripten 4.0.10 from repository-local EMSDK 6.0.5, TypeScript/React/Vite, Playwright 1.62.1, Netlify REST API, OpenPGP/GnuPG, Docusaurus.

**Spec:** `docs/superpowers/specs/2026-09-01-lmdj-dual-web-host-release-design.md`

## Global Constraints

- Product Build is exactly `1.0.41.0`; `1.0.40.1` is forbidden for this capability.
- Candidate Product tag is exactly `lmdj-v1.0.41.0`; initial Channel is `canary`.
- `creator-web` and `web-runtime-host` remain at `2.1.1` unless implementation changes their public behavior or API.
- `web-hosts` contains exactly two ZIP/checksum/signature triplets; historical `web-runtime-host` Releases retain their original three-asset interpretation.
- Creator production URL is exactly `https://lmdj-creator.netlify.app/`; Runtime remains `https://lmdj-runtime.netlify.app/`.
- Creator and Runtime deployment workflows are `workflow_dispatch` only and are separate authorization, evidence, rollback, and Environment boundaries.
- Deployment consumes only signed published Release bytes; it never rebuilds from source.
- Published tags and Releases are immutable; `1.0.40.0` is never edited or reinterpreted.
- Product and checksum signing roles remain distinct and retain the canonical fingerprints from `tools/release/policy.json`.
- Project Truth, Runtime Snapshot, retired Contract, Provider, and user-audio semantics do not change.
- Documentation impact: required for `/hosts/creator-web/`, `/hosts/web-runtime/`, `/operations/version-and-release/`, and `/operations/testing-and-proof/`.
- Release intent is not bound on this pre-squash branch; it is a later reviewed exact-main evidence Task.

---

### Task 1: Extend the closed release policy for dual Web Hosts

**Files:**
- Modify: `tools/release/policy.json`
- Modify: `tools/release/model.py`
- Modify: `tests/build/release_model_test.py`
- Modify: `tests/build/release_skill_test.py`

**Interfaces:**
- Consumes: `ReleasePolicy.product_profiles`, `ReleasePolicy.release_environment`, and `ReleasePolicy.runtime_canary_environment`.
- Produces: accepted Product profile `web-hosts` and `ReleasePolicy.creator_canary_environment == "creator-canary"`.

- [ ] **Step 1: Add failing closed-policy tests**

```python
def test_policy_is_closed_and_uses_exact_trust_anchors(self) -> None:
    self.assertEqual(
        self.policy.product_profiles,
        frozenset(("core-package", "web-runtime-host", "web-hosts")),
    )
    self.assertEqual(self.policy.runtime_canary_environment, "runtime-canary")
    self.assertEqual(self.policy.creator_canary_environment, "creator-canary")

def test_ledger_accepts_the_closed_dual_web_host_profile(self) -> None:
    ledger = load_ledger_document(self.ledger_fixture(profile="web-hosts"), self.policy)
    self.assertEqual(ledger.entries[0].profile, "web-hosts")
```

- [ ] **Step 2: Run the focused tests and observe the failure**

Run: `python3 -m unittest tests.build.release_model_test tests.build.release_skill_test`

Expected: FAIL because `web-hosts` and `creator_canary` are not accepted by the closed schema.

- [ ] **Step 3: Implement the exact schema extension**

Change the policy document to:

```json
"profiles": {
  "product": ["core-package", "web-runtime-host", "web-hosts"],
  "source": ["source-only"]
},
"environments": {
  "release": "release",
  "runtime_canary": "runtime-canary",
  "creator_canary": "creator-canary"
}
```

Add `creator_canary_environment: str` to `ReleasePolicy`, require the exact three Environment keys, require the exact canonical tuple `("release", "runtime-canary", "creator-canary")`, and return the new value from `load_policy()`.

- [ ] **Step 4: Run the focused tests**

Run: `python3 -m unittest tests.build.release_model_test tests.build.release_skill_test`

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add tools/release/policy.json tools/release/model.py \
  tests/build/release_model_test.py tests/build/release_skill_test.py
git diff --cached --check
git commit -m "feat(release): define dual web host profile"
```

### Task 2: Build and verify the exact six signed Release assets

**Files:**
- Create: `tools/release/web_host_bundle.py`
- Create: `apps/creator-web/tools/release_bundle.py`
- Create: `apps/creator-web/test/release_bundle_test.py`
- Modify: `apps/web-runtime-host/tools/release_bundle.py`
- Modify: `tools/release/profiles.py`
- Modify: `tests/build/release_prepare_test.py`
- Modify: `tests/build/release_audit_test.py`
- Modify: `tests/build/release_transitions_test.py`

**Interfaces:**
- Consumes: `ProfileRuntime`, `ReleaseIntent`, both Host `module.json` files, both distribution verifiers, and the checksum signing role.
- Produces: `build_profile("web-hosts", ...) -> ProfileBuild` with six canonical `AssetBuild` records and `verify_existing_profile("web-hosts", ...)` that verifies both triplets.

- [ ] **Step 1: Add failing deterministic bundle tests**

Define the shared Host descriptor and archive interface:

```python
@dataclass(frozen=True)
class WebHostReleaseSpec:
    host_id: str
    script: str
    dist_relative: str
    module_relative: str
    archive_prefix: str
    verifier_relative: str

def create_dist_zip(dist: Path, archive: Path) -> None: ...
def stage_host_bundle(*, spec: WebHostReleaseSpec, repo_root: Path,
                      archive_path: Path, checksum_path: Path,
                      signature_path: Path, output_root: Path,
                      expected_product_build: str,
                      expected_host_version: str,
                      checksum_public_key_path: Path,
                      trusted_checksum_fingerprint: str) -> StagedBundle: ...
```

Tests must assert deterministic ZIP metadata, exactly one `dist/` tree, unsafe/duplicate member rejection, exact checksum pairing, wrong signer rejection, and Host-specific manifest verification for Creator.

- [ ] **Step 2: Add failing profile inventory tests**

```python
build = build_profile("web-hosts", root, output, intent, runtime)
self.assertEqual(
    tuple(asset.name for asset in build.assets),
    (
        "lmdj-creator-web-2.1.1-product-1.0.41.0.zip",
        "lmdj-creator-web-2.1.1-product-1.0.41.0.zip.sha256",
        "lmdj-creator-web-2.1.1-product-1.0.41.0.zip.sha256.asc",
        "lmdj-web-runtime-host-2.1.1-product-1.0.41.0.zip",
        "lmdj-web-runtime-host-2.1.1-product-1.0.41.0.zip.sha256",
        "lmdj-web-runtime-host-2.1.1-product-1.0.41.0.zip.sha256.asc",
    ),
)
```

Also add missing, extra, renamed, cross-paired, and persisted-asset verification failures while retaining a passing historical three-asset `web-runtime-host` fixture.

- [ ] **Step 3: Run the failing bundle/profile tests**

Run:

```bash
python3 apps/creator-web/test/release_bundle_test.py
python3 -m unittest \
  tests.build.release_prepare_test \
  tests.build.release_audit_test \
  tests.build.release_transitions_test
```

Expected: FAIL because shared bundle tooling and `web-hosts` builder do not exist.

- [ ] **Step 4: Implement shared deterministic archive and Host staging**

Move archive safety, checksum parsing, detached-signature verification, safe extraction, manifest identity reading, and `StagedBundle` serialization into `tools/release/web_host_bundle.py`. Keep `apps/web-runtime-host/tools/release_bundle.py` as the existing CLI-compatible Runtime adapter and add the same CLI shape for Creator.

- [ ] **Step 5: Implement the dual profile builder**

In `tools/release/profiles.py`, define exact Creator and Runtime `WebHostReleaseSpec` constants. Refactor the single Runtime path through `_build_web_host(spec, ...)`, then implement:

```python
def build_web_hosts(worktree, output, intent, runtime) -> ProfileBuild:
    creator = _build_web_host(CREATOR_WEB_SPEC, worktree, output, intent, runtime)
    runtime_host = _build_web_host(WEB_RUNTIME_SPEC, worktree, output, intent, runtime)
    return ProfileBuild(tuple(sorted(
        (*creator.assets, *runtime_host.assets), key=lambda asset: asset.name
    )))
```

`verify_existing_profile()` must partition by exact expected names, verify both checksum signatures in fresh keyrings, and stage both archives through their Host verifier. Do not change historical profile interpretation.

- [ ] **Step 6: Run the focused tests**

Run the commands from Step 3.

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add tools/release/web_host_bundle.py tools/release/profiles.py \
  apps/web-runtime-host/tools/release_bundle.py \
  apps/creator-web/tools/release_bundle.py \
  apps/creator-web/test/release_bundle_test.py \
  tests/build/release_prepare_test.py tests/build/release_audit_test.py \
  tests/build/release_transitions_test.py
git diff --cached --check
git commit -m "feat(release): package both web hosts"
```

### Task 3: Make Release deployment selection Host-aware

**Files:**
- Create: `tools/web_deploy/__init__.py`
- Create: `tools/web_deploy/release_selection.py`
- Create: `tests/build/web_host_release_selection_test.py`
- Modify: `apps/web-runtime-host/tools/deploy_orchestrator.py`
- Modify: `apps/web-runtime-host/test/deploy_orchestrator_test.py`
- Modify: `scripts/web-runtime-deploy.sh`
- Modify: `apps/web-runtime-host/test/deploy_command_test.py`

**Interfaces:**
- Consumes: a published GitHub Release projection and exact Product/Host identities.
- Produces: `select_host_assets(release, *, host_id, host_version, product_build) -> HostAssetSelection`, while requiring the full profile inventory to be canonical.

- [ ] **Step 1: Write the failing selection tests**

```python
@dataclass(frozen=True)
class HostAssetSelection:
    archive: str
    checksum: str
    signature: str
    release_url: str

selection = select_host_assets(
    six_asset_release(), host_id="creator-web",
    host_version="2.1.1", product_build="1.0.41.0",
)
self.assertEqual(selection.archive,
                 "lmdj-creator-web-2.1.1-product-1.0.41.0.zip")
```

Add failures for an incomplete other-Host triplet, extra seventh asset, unknown Host ID, wrong Product Build, wrong Release URL, Draft, and non-prerelease canary.

- [ ] **Step 2: Run the focused tests and observe failure**

Run:

```bash
python3 tests/build/web_host_release_selection_test.py
python3 apps/web-runtime-host/test/deploy_orchestrator_test.py
python3 apps/web-runtime-host/test/deploy_command_test.py
```

Expected: FAIL because deployment still requires exactly one Runtime triplet.

- [ ] **Step 3: Implement full-inventory validation and role selection**

Implement `release_selection.py` with exact prefixes for `creator-web` and `web-runtime-host`. A six-asset `web-hosts` Release must be fully valid before returning one triplet. Retain a compatibility branch for historical `web-runtime-host` three-asset Releases so the existing `1.0.40.0` Runtime deployment remains auditable and recoverable.

- [ ] **Step 4: Adapt the Runtime orchestrator and shell command**

Pass `host_id="web-runtime-host"` explicitly through release metadata parsing, downloaded-asset validation, and staging. Download the complete canonical Release inventory, validate it, then pass only the Runtime triplet to the Runtime bundle verifier.

- [ ] **Step 5: Run the focused tests**

Run the commands from Step 2.

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add tools/web_deploy tests/build/web_host_release_selection_test.py \
  apps/web-runtime-host/tools/deploy_orchestrator.py \
  apps/web-runtime-host/test/deploy_orchestrator_test.py \
  apps/web-runtime-host/test/deploy_command_test.py \
  scripts/web-runtime-deploy.sh
git diff --cached --check
git commit -m "refactor(deploy): select signed host payloads"
```

### Task 4: Add Creator HTTP and Chromium deployment smoke

**Files:**
- Create: `apps/creator-web/tools/deployment_smoke.py`
- Create: `apps/creator-web/test/deployment_smoke_test.py`
- Create: `tests/platform/web/deployment/creator_web_deployment.spec.mjs`
- Modify: `tests/platform/web/playwright.config.mjs`
- Create: `apps/creator-web/deploy/_headers`

**Interfaces:**
- Consumes: a Creator immutable or production base URL plus expected Product Build, Host version, and optional Netlify deploy ID.
- Produces: privacy-bounded canonical JSON HTTP result and a Playwright `creator-deployment` project.

- [ ] **Step 1: Write failing HTTP smoke tests**

Port the Runtime HTTP transport guards, then assert Creator-specific identity and inventory:

```python
result = smoke(
    base_url="https://lmdj-creator.netlify.app/",
    expected_product="1.0.41.0",
    expected_host="2.1.1",
    expected_host_id="creator-web",
    expected_deploy_id="creator-deploy-1",
)
self.assertEqual(result["host_id"], "creator-web")
```

Add tests for CSP/COOP/COEP/CORP, hashed assets, cache policy, redirects, source maps, retired markers, wrong hostname, wrong deploy ID, and credential/environment scrubbing.

- [ ] **Step 2: Write the failing packaged Chromium journey**

Create a deployment spec that asserts secure/cross-origin-isolated boot, exact identity, workspace rendering, Project create/open, deterministic WAV import, Pad assignment, explicit audio activation, one admitted/outcome pair, Sample and Sequence surfaces, and durable reload.

- [ ] **Step 3: Run the failing smoke tests**

Run:

```bash
python3 apps/creator-web/test/deployment_smoke_test.py
LMDJ_CREATOR_WEB_EXTERNAL_SERVER=1 \
LMDJ_CREATOR_WEB_BASE_URL=http://127.0.0.1:9 \
npx --prefix tests/platform/web playwright test \
  --project=creator-deployment deployment/creator_web_deployment.spec.mjs
```

Expected: Python tests fail because the smoke module is absent; Playwright fails because the project/spec is absent or the owned server is unreachable.

- [ ] **Step 4: Implement the HTTP smoke and deployment project**

Keep the result allowlist to URL, Product/Host identity, deploy ID, index/manifest digests, asset count, and start/end/status. Do not serialize browser storage, Project IDs, audio bytes, or full response headers.

- [ ] **Step 5: Run HTTP tests and the spec against an owned packaged Creator server**

Run:

```bash
python3 apps/creator-web/test/deployment_smoke_test.py
scripts/creator-web.sh package
scripts/creator-web.sh serve --port 4174
```

In a second command while the owned server is live:

```bash
LMDJ_CREATOR_WEB_EXTERNAL_SERVER=1 \
LMDJ_CREATOR_WEB_BASE_URL=http://127.0.0.1:4174 \
npx --prefix tests/platform/web playwright test \
  --project=creator-deployment deployment/creator_web_deployment.spec.mjs
```

Expected: PASS; then stop the owned server.

- [ ] **Step 6: Commit Task 4**

```bash
git add apps/creator-web/deploy/_headers \
  apps/creator-web/tools/deployment_smoke.py \
  apps/creator-web/test/deployment_smoke_test.py \
  tests/platform/web/deployment/creator_web_deployment.spec.mjs \
  tests/platform/web/playwright.config.mjs
git diff --cached --check
git commit -m "test(creator): add production deployment smoke"
```

### Task 5: Add the independently gated Creator deployment transaction

**Files:**
- Create: `scripts/creator-web-deploy.sh`
- Create: `.github/workflows/deploy-creator-web.yml`
- Create: `apps/creator-web/tools/deploy_orchestrator.py`
- Create: `apps/creator-web/test/deploy_orchestrator_test.py`
- Create: `apps/creator-web/test/deploy_command_test.py`
- Create: `tests/build/creator_web_deploy_workflow_test.py`
- Modify: `scripts/ci/local_lanes.json`
- Modify: `scripts/ci/scope_policy.json`
- Modify: `.github/actions/web-ci-proof/action.yml`

**Interfaces:**
- Consumes: exact signed Product tag, published `web-hosts` Release, `NETLIFY_CREATOR_SITE_ID`, `NETLIFY_AUTH_TOKEN`, `GITHUB_TOKEN`, and `creator-canary` Environment.
- Produces: a verified Netlify deployment at `https://lmdj-creator.netlify.app/` and `lmdj.creator-web.deployment-evidence.v1` or exact rollback evidence.

- [ ] **Step 1: Write failing workflow contract tests**

Assert exact manual trigger, one `tag` input, `contents: read`, non-cancelling `creator-web-production` concurrency, credential-free preflight, `environment: creator-canary`, Environment-scoped Creator Site secret, pinned Actions, artifact upload on success/failure, and absence of Release publication or Runtime deployment calls.

- [ ] **Step 2: Write failing transaction and rollback tests**

Mirror the existing Runtime transaction matrix with Creator identities. Required cases are: credential scrubbing, exact six-asset verification, Creator triplet staging, existing Site/hostname preflight, no-prior-deploy bootstrap, immutable HTTP/Chromium pass, exact deploy publication, production pass, publication uncertainty reconciliation, attempted-deploy mismatch stop, exact prior-deploy restore, restored HTTP/Chromium pass, and privacy-bounded evidence.

- [ ] **Step 3: Run the failing deployment contract tests**

Run:

```bash
python3 tests/build/creator_web_deploy_workflow_test.py
python3 apps/creator-web/test/deploy_orchestrator_test.py
python3 apps/creator-web/test/deploy_command_test.py
```

Expected: FAIL because Creator workflow and transaction do not exist.

- [ ] **Step 4: Implement the Creator orchestrator and shell entry point**

Use the existing `NetlifyClient` transport and exact-ID recovery semantics. The Creator orchestrator must validate Site `ssl_url == "https://lmdj-creator.netlify.app"`, stage only the selected Creator triplet, and emit only the evidence allowlist. The shell interface is exactly:

```text
scripts/creator-web-deploy.sh verify TAG
scripts/creator-web-deploy.sh deploy TAG
scripts/creator-web-deploy.sh smoke BASE_URL PRODUCT_BUILD HOST_VERSION
```

- [ ] **Step 5: Implement the manual Creator workflow and CI ownership**

Use `NETLIFY_CREATOR_SITE_ID: ${{ secrets.NETLIFY_CREATOR_SITE_ID }}` only in the `creator-canary` deploy job. Register the new workflow/scripts/tests in deploy-contract and Creator ownership without weakening unknown-path fail-closed behavior.

- [ ] **Step 6: Run Creator and Runtime deployment contracts**

Run:

```bash
python3 tests/build/creator_web_deploy_workflow_test.py
python3 tests/build/web_runtime_deploy_workflow_test.py
python3 apps/creator-web/test/deploy_orchestrator_test.py
python3 apps/creator-web/test/deploy_command_test.py
python3 apps/web-runtime-host/test/deploy_orchestrator_test.py
python3 apps/web-runtime-host/test/deploy_command_test.py
```

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```bash
git add scripts/creator-web-deploy.sh .github/workflows/deploy-creator-web.yml \
  apps/creator-web/tools/deploy_orchestrator.py \
  apps/creator-web/test/deploy_orchestrator_test.py \
  apps/creator-web/test/deploy_command_test.py \
  tests/build/creator_web_deploy_workflow_test.py \
  scripts/ci/local_lanes.json scripts/ci/scope_policy.json \
  .github/actions/web-ci-proof/action.yml
git diff --cached --check
git commit -m "feat(deploy): add Creator production workflow"
```

### Task 6: Update release and deployment documentation

**Files:**
- Modify: `docs/governance/version-management.md`
- Modify: `docs/governance/git-workflow.md`
- Modify: `docs/deploy/web-runtime-host.md`
- Create: `docs/deploy/creator-web.md`
- Modify: `docs/superpowers/specs/2026-08-13-lmdj-standard-release-pipeline-design.md`
- Modify: `apps/architecture-portal/docs/hosts/creator-web.mdx`
- Modify: `apps/architecture-portal/docs/hosts/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/operations/version-and-release.mdx`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- Modify: `apps/architecture-portal/diagrams/lmdj-product.architecture.json`
- Modify: `tests/build/web_runtime_public_deployment_docs_test.py`
- Create: `tests/build/creator_web_public_deployment_docs_test.py`

**Interfaces:**
- Consumes: implemented workflow, profile, Environment, URLs, evidence contracts, and authorization boundaries from Tasks 1–5.
- Produces: current operator documentation and Portal pages that state exact implemented behavior without claiming external Site provisioning or deployment.

- [ ] **Step 1: Add failing documentation-contract assertions**

Assert exact Creator URL, `creator-canary`, `NETLIFY_CREATOR_SITE_ID`, manual-only dispatch, `web-hosts` six assets, independent rollback, no publication fan-out, and historical `1.0.40.0` immutability.

- [ ] **Step 2: Run documentation tests and observe failure**

Run:

```bash
python3 tests/build/web_runtime_public_deployment_docs_test.py
python3 tests/build/creator_web_public_deployment_docs_test.py
```

Expected: FAIL because current docs describe only Runtime deployment.

- [ ] **Step 3: Update governance, operator docs, Portal pages, and diagrams**

Document source truth versus Release assets versus deployment state, both Host URLs, separate deployment authorization, exact rollback, external Site provisioning, and the physical/manual evidence boundary. Do not claim the Creator Site exists before live provisioning evidence.

- [ ] **Step 4: Run docs and Portal checks**

Run:

```bash
python3 tests/build/web_runtime_public_deployment_docs_test.py
python3 tests/build/creator_web_public_deployment_docs_test.py
scripts/architecture-portal.sh check
```

Expected: PASS.

- [ ] **Step 5: Commit Task 6**

```bash
git add docs/governance/version-management.md \
  docs/governance/git-workflow.md \
  docs/deploy/web-runtime-host.md docs/deploy/creator-web.md \
  docs/superpowers/specs/2026-08-13-lmdj-standard-release-pipeline-design.md \
  apps/architecture-portal/docs/hosts/creator-web.mdx \
  apps/architecture-portal/docs/hosts/web-runtime.mdx \
  apps/architecture-portal/docs/operations/version-and-release.mdx \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx \
  apps/architecture-portal/diagrams/lmdj-product.architecture.json \
  tests/build/web_runtime_public_deployment_docs_test.py \
  tests/build/creator_web_public_deployment_docs_test.py
git diff --cached --check
git commit -m "docs: document dual web host delivery"
```

### Task 7: Allocate Product Build 1.0.41.0

**Files:**
- Modify: `products/lmdj/version.json`
- Modify: `products/lmdj/assembly.json`
- Regenerate: `products/lmdj/assembly.lock.json`
- Regenerate: `products/lmdj/src/compiled_assembly.cpp`
- Regenerate: `products/lmdj/generated/web-runtime-identity.json`
- Regenerate: `products/lmdj/generated/web-runtime-identity.mjs`
- Modify: `tests/build/version_test.py`
- Modify: `apps/architecture-portal/docs/assembly/lmdj.mdx`
- Modify: `apps/architecture-portal/docs/hosts/creator-web.mdx`
- Modify: `apps/architecture-portal/docs/hosts/overview.mdx`
- Modify: `apps/architecture-portal/docs/hosts/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- Modify: `apps/architecture-portal/docs/operations/version-and-release.mdx`
- Modify: `apps/architecture-portal/docs/overview/index.mdx`
- Modify: `apps/architecture-portal/docs/platform/input.mdx`
- Modify: `apps/architecture-portal/docs/platform/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/product/capability-map.mdx`

**Interfaces:**
- Consumes: final Host/module identities and all release/deployment source from Tasks 1–6.
- Produces: internally consistent Product Build `1.0.41.0` with unchanged Host SemVer `2.1.1`.

- [ ] **Step 1: Change Product version sources to 1.0.41.0**

Set the Product version parts to milestone `1`, minor `0`, build `41`, patch `0` and set `assembly.json` product version to `1.0.41.0`.

- [ ] **Step 2: Regenerate lock and Web identities using canonical tools**

Run:

```bash
python3 scripts/version.py lock \
  --version-file products/lmdj/version.json \
  --assembly products/lmdj/assembly.json \
  --output products/lmdj/assembly.lock.json
python3 tools/web-runtime/generate_runtime_identity.py --repo-root .
```

The lock command atomically regenerates both `assembly.lock.json` and
`src/compiled_assembly.cpp`; the identity generator writes both generated Web
identity files. Do not hand-edit any of those four outputs.

- [ ] **Step 3: Update exact current-product assertions and Portal source pages**

Update `tests/build/version_test.py` assertions that intentionally bind the
current Product Build. Update the ten current Portal pages listed in this Task
from source candidate `1.0.40.0` to `1.0.41.0` while retaining every historical
`1.0.40.0` evidence statement. Then run the exact verification commands in
Step 4 without weakening historical fixtures.

- [ ] **Step 4: Run version and active-tree gates**

Run:

```bash
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
bash tests/build/test_active_tree.sh
bash scripts/verify-core-dependencies.sh
```

Expected: PASS.

- [ ] **Step 5: Commit Task 7**

```bash
git add products/lmdj/version.json products/lmdj/assembly.json \
  products/lmdj/assembly.lock.json \
  products/lmdj/src/compiled_assembly.cpp \
  products/lmdj/generated/web-runtime-identity.json \
  products/lmdj/generated/web-runtime-identity.mjs \
  tests/build/version_test.py \
  apps/architecture-portal/docs/assembly/lmdj.mdx \
  apps/architecture-portal/docs/hosts/creator-web.mdx \
  apps/architecture-portal/docs/hosts/overview.mdx \
  apps/architecture-portal/docs/hosts/web-runtime.mdx \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx \
  apps/architecture-portal/docs/operations/version-and-release.mdx \
  apps/architecture-portal/docs/overview/index.mdx \
  apps/architecture-portal/docs/platform/input.mdx \
  apps/architecture-portal/docs/platform/web-runtime.mdx \
  apps/architecture-portal/docs/product/capability-map.mdx
git diff --cached --check
git commit -m "feat(product): allocate build 1.0.41.0"
```

### Task 8: Freeze the immutable 1.0.41.0 canary Portal snapshot

**Files:**
- Create: generated `apps/architecture-portal/versioned_docs/version-1.0.41.0/**`
- Create: generated `apps/architecture-portal/versioned_sidebars/version-1.0.41.0-sidebars.json`
- Create: generated `apps/architecture-portal/versions.json` entry and snapshot metadata/diagram outputs
- Test: `apps/architecture-portal/test/release-docs.test.mjs`

**Interfaces:**
- Consumes: a clean committed Task 7 branch tip whose projected source and docs are final.
- Produces: immutable Product Build `1.0.41.0` canary snapshot whose source projection equals the branch tree.

- [ ] **Step 1: Require a clean branch and freeze the snapshot**

Run:

```bash
test -z "$(git status --porcelain=v1 --untracked-files=all)"
scripts/architecture-portal.sh version 1.0.41.0 canary
```

Expected: snapshot generation succeeds once and refuses an existing version.

- [ ] **Step 2: Run pre-merge provenance and Portal verification**

Run:

```bash
scripts/architecture-portal.sh check
node --test apps/architecture-portal/test/release-docs.test.mjs
```

Expected: PASS with snapshot Product Build, Assembly lock, and source projection matching the current branch.

- [ ] **Step 3: Commit Task 8 with exact staging**

Inspect `git status --short`, stage only the generated `1.0.41.0` snapshot files and canonical version registry changes, run `git diff --cached --check`, then:

```bash
git commit -m "docs(portal): freeze 1.0.41.0 canary snapshot"
```

- [ ] **Step 4: Prohibit post-freeze projected edits**

Run `scripts/architecture-portal.sh check` again. If any later fix changes projected source or current Portal docs, delete only the unmerged generated `1.0.41.0` snapshot through its canonical development remedy, re-freeze at the new branch tip, and replace this local snapshot commit before push. Never hand-edit immutable snapshot content.

### Task 9: Run the complete local completion gate

**Files:**
- No intentional source changes.
- Inspect: every committed file since `origin/main`.

**Interfaces:**
- Consumes: Tasks 1–8.
- Produces: evidence that the local implementation is ready for shipping; no push, PR, Release, Site provisioning, or deployment.

- [ ] **Step 1: Run the complete release and deployment contracts**

```bash
python3 -m unittest discover -s tests/build -p 'release_*_test.py'
python3 tests/build/web_runtime_deploy_workflow_test.py
python3 tests/build/creator_web_deploy_workflow_test.py
python3 tests/build/web_runtime_public_deployment_docs_test.py
python3 tests/build/creator_web_public_deployment_docs_test.py
python3 apps/web-runtime-host/test/deploy_command_test.py
python3 apps/creator-web/test/deploy_command_test.py
```

- [ ] **Step 2: Run both Web Host proofs with the locked toolchain**

```bash
export EMSDK=/Users/endaye/Projects/lmdj/build/toolchains/emsdk
scripts/web-runtime-host.sh proof
scripts/creator-web.sh proof
```

- [ ] **Step 3: Run Product and Portal gates**

```bash
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
bash tests/build/test_active_tree.sh
bash scripts/verify-core-dependencies.sh
scripts/architecture-portal.sh check
```

- [ ] **Step 4: Audit commit and worktree boundaries**

```bash
git log --oneline --decorate origin/main..HEAD
git diff --check origin/main...HEAD
git status --short --branch
```

Expected: every planned Task has one reviewable Conventional Commit, no unrelated paths are present, and the worktree is clean.

## Version Management

- Version impact: required.
- Product Build changes from `1.0.40.0` to `1.0.41.0` because this adds a user-facing production Host delivery and changes Product Release inventory.
- Product tag candidate is `lmdj-v1.0.41.0`; the implementation plan does not authorize creating or pushing it.
- Creator Web Host and Web Runtime Host remain `2.1.1` unless implementation changes Host public behavior/API; any such change requires reevaluation before Task 7.
- Module, Provider, Model, Project Truth, Runtime Snapshot, and public Contract versions remain unchanged.
- `web-hosts` is repository-internal release policy, not a public Contract.
- The immutable `1.0.41.0` canary snapshot is frozen only after all projected implementation and docs commits.
- Release intent binding waits for the exact protected-main squash SHA and qualifying exact-main full CI evidence.

## Documentation Impact

- Documentation impact: required.
- Affected routes: `/hosts/creator-web/`, `/hosts/web-runtime/`, `/operations/version-and-release/`, and `/operations/testing-and-proof/`.
- Update current pages and source diagrams in Task 6; freeze their immutable `1.0.41.0` projection in Task 8.
- No local build, PR preview, or implementation commit is described as a permanent production deployment.

## Post-Merge Release Boundary

After this plan is implemented, pushed, reviewed, and squash-merged under separate authorization, do not reuse the feature-branch SHA as release identity. Verify the exact main SHA, obtain or dispatch full exact-main CI evidence under its own authorization, create the squash witness if the landed snapshot requires it, and bind a separately reviewed `releasable` intent for `lmdj-v1.0.41.0` with profile `web-hosts`.

All later mutations remain one-at-a-time `lmdj-release` boundaries: prepare, exact tag push, Draft creation, protected publication, Creator Site provisioning/configuration, Creator deployment, Runtime deployment, and optional Channel promotion. Audit after every boundary and never infer one Host's deployment from the other.
