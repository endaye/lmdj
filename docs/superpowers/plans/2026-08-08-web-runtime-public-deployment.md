# Web Runtime Public Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the exact released Formal Web Runtime Host at `https://lmdj-runtime.netlify.app/` through a fail-closed, two-phase Netlify deployment with immutable pre-publication smoke evidence.

**Architecture:** A Python standard-library deployment tool validates the signed Product tag, GitHub Release assets, detached SHA-256, safe extraction, and canonical Host distribution before it creates a Netlify draft deploy through the digest API. HTTP and Chromium smoke run against the immutable deploy URL before the same Deploy ID is published with `restoreSiteDeploy`; Creator, Portal, Core, and the released Host bytes remain unchanged.

**Tech Stack:** Bash, Python 3.11 standard library, Git/GPG, GitHub CLI and Actions, Netlify REST API, Playwright 1.62.1 with Node 22, Docusaurus Architecture Portal.

## Global Constraints

- Work on `feat/web-runtime-public-deployment` in an isolated worktree created from updated `main`; do not implement on the docs branch or protected `main`.
- The approved specification is `docs/superpowers/specs/2026-08-08-web-runtime-public-deployment-design.md`.
- Public Runtime URL: `https://lmdj-runtime.netlify.app/`.
- Reserved future Creator URLs: `https://lmdj-canary.netlify.app/` and `https://lmdj-beta.netlify.app/`; this plan must not create or deploy them.
- Initial source release: tag `lmdj-v1.0.15.2`, Product Build `1.0.15.2`, Web Runtime Host `1.1.2`, channel `canary`.
- Deploy the original GitHub Release Host files without rebuilding or changing any product byte.
- Run deployment tooling from merged protected `main`, but load Product/Host manifests and the canonical distribution verifier from a detached checkout of the exact signed tag target.
- Use the Netlify digest API with `draft: true`; publish the same validated Deploy ID through `POST /api/v1/sites/{site_id}/deploys/{deploy_id}/restore`.
- Do not connect the Netlify project to a Git repository and do not enable Git-triggered auto publishing.
- Every response must retain the Formal Host COOP, COEP, CORP, CSP, `nosniff`, cache, and `X-Robots-Tag: noindex, nofollow, noarchive` contracts.
- Do not expose `apps/web-runtime-host/tools/server.py` publicly.
- Do not add analytics, telemetry, remote fonts, third-party scripts, network APIs, authentication, Creator UI, PWA, or SPA fallback.
- A remote automated smoke does not upgrade Safari, iPad Touch, Physical MIDI, acoustic latency, lifecycle, `beta`, or `stable` acceptance.
- `Version impact: none`: implementation changes deployment tooling and documentation only; Product, Host, Module, Provider, Contract, Assembly, and released distribution identities remain unchanged.
- `Documentation impact: required`: update `/operations/version-and-release/`, `/hosts/web-runtime/`, and `/platform/web-runtime/` current pages without freezing a new Product snapshot.
- Local commit does not authorize push, PR, merge, Netlify project creation, secret changes, deployment, rollback, or Channel promotion.

---

## Version Management

Canonical policy: `docs/governance/version-management.md`.

**Version impact: none.**

- Product Build remains `1.0.15.2`; the plan republishes the exact existing Host
  Release artifact and does not change Product Assembly or released bytes.
- Web Runtime Host remains `1.1.2`; deployment tooling, Netlify control headers,
  workflow policy, tests, and operations documentation are outside the Host
  distribution and public Host API.
- Core Modules, Providers, Models, and their SemVer identities remain unchanged.
- Contracts remain unchanged. The deployment evidence schema is an operations
  record, not a cross-language product Contract.
- The initial deployment consumes immutable signed tag `lmdj-v1.0.15.2`; it does
  not create, move, or replace a tag, GitHub Release, or Architecture Portal
  Product snapshot.
- Publishing to the `canary` diagnostic URL is not Creator Channel promotion and
  does not imply `beta`, `stable`, or deferred physical acceptance.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `apps/web-runtime-host/tools/release_bundle.py` | Validate detached checksum, safely extract one `dist/` root, call the canonical distribution verifier, and emit canonical staging metadata. |
| `apps/web-runtime-host/test/release_bundle_test.py` | Prove checksum, archive path, link, inventory, identity, and cleanup failures are fail-closed. |
| `apps/web-runtime-host/deploy/_headers` | Netlify-only response rules; it is never added to the Product Release ZIP or Host manifest. |
| `apps/web-runtime-host/tools/netlify_api.py` | Create a draft digest deploy, upload only required files, poll `ready`, publish/restore an exact Deploy ID, and verify the production pointer. |
| `apps/web-runtime-host/test/netlify_api_test.py` | Exercise Netlify request shapes, URL encoding, response schemas, state deadlines, token redaction, and same-Deploy publication with an in-process HTTP fake. |
| `apps/web-runtime-host/tools/deployment_smoke.py` | Verify immutable/production HTTP identity, headers, MIME, cache, manifest digest, assets, and negative routes. |
| `apps/web-runtime-host/test/deployment_smoke_test.py` | Serve valid and intentionally invalid responses through an in-process HTTP server. |
| `tests/platform/web/deployment/web_runtime_host_deployment.spec.mjs` | Run the minimal secure-context, cross-origin-isolation, diagnostic-load, audio-activation, trigger-outcome, and close smoke. |
| `scripts/web-runtime-deploy.sh` | Own the end-to-end order: tag/Release validation → stage → draft → immutable smoke → publish same Deploy ID → production smoke → evidence. |
| `apps/web-runtime-host/tools/deploy_orchestrator.py` | Parse and project trusted release/deploy metadata, call the canonical Netlify API client, and write secret-free evidence atomically. |
| `apps/web-runtime-host/test/deploy_command_test.py` | Prove command usage, cleanup, environment gates, tag selection, and that smoke precedes publish. |
| `.github/release-signing-keys/lmdj-product.asc` | Repository-pinned public key for Product tag verification. |
| `.github/workflows/deploy-web-runtime-host.yml` | Release/manual trigger, minimal permissions, GitHub Environment boundary, locked tool setup, deployment, and evidence upload. |
| `tests/build/web_runtime_deploy_workflow_test.py` | Static contract for workflow triggers, permissions, secrets, concurrency, signed tag, and no branch/PR deploy path. |
| `CMakeLists.txt` | Register the workflow contract test in the `contract` tier. |
| `scripts/web-runtime-host.sh` | Run the new offline Python deployment tests in Host test/proof. |
| `docs/deploy/web-runtime-host.md` | Operator runbook, initial activation, evidence, failure, and rollback. |
| `docs/quality/2026-08-08-web-runtime-public-deployment-acceptance.md` | Current pre-deploy evidence first; exact Netlify evidence only after activation. |
| `apps/architecture-portal/docs/operations/version-and-release.mdx` | Explain release-asset deployment and two-phase publication. |
| `apps/architecture-portal/docs/hosts/web-runtime.mdx` | Separate implemented Host, deployment readiness, and actual deployed state. |
| `apps/architecture-portal/docs/platform/web-runtime.mdx` | Record public runtime diagnostic surface and physical-evidence boundary. |

---

### Task 1: Release Bundle Provenance and Safe Staging

**Files:**
- Create: `apps/web-runtime-host/tools/release_bundle.py`
- Create: `apps/web-runtime-host/test/release_bundle_test.py`
- Modify: `scripts/web-runtime-host.sh`

**Interfaces:**
- Consumes: Release ZIP path, detached checksum path, repository root, empty output root, expected Product Build, expected Host version.
- Produces: `StagedBundle(dist_root: Path, product_build: str, host_version: str, archive_sha256: str)` and canonical JSON with those four fields.

- [ ] **Step 1: Write checksum and archive rejection tests**

Create tests that construct ZIPs in a temporary directory and assert exact `BundleError` messages:

```python
class ReleaseBundleTest(unittest.TestCase):
    def test_rejects_checksum_mismatch_before_extraction(self) -> None:
        archive = self.write_zip({"dist/index.html": b"host"})
        checksum = self.write_checksum("0" * 64, archive.name)
        with self.assertRaisesRegex(BundleError, "release archive checksum mismatch"):
            stage_release_bundle(
                repo_root=REPO_ROOT,
                archive_path=archive,
                checksum_path=checksum,
                output_root=self.output,
                expected_product_build="1.0.15.2",
                expected_host_version="1.1.2",
                verifier=lambda root, repo: None,
            )
        self.assertFalse(self.output.exists())

    def test_rejects_parent_absolute_duplicate_and_link_entries(self) -> None:
        for member in ("../escape", "/absolute", "dist/../escape"):
            with self.subTest(member=member):
                archive, checksum = self.archive_with_member(member)
                with self.assertRaisesRegex(BundleError, "unsafe release archive entry"):
                    self.stage(archive, checksum)
```

- [ ] **Step 2: Run the tests and verify the failure**

Run:

```bash
python3 apps/web-runtime-host/test/release_bundle_test.py
```

Expected: `ModuleNotFoundError` for `apps/web-runtime-host/tools/release_bundle.py`.

- [ ] **Step 3: Implement safe extraction and checksum parsing**

Implement these exact public surfaces:

```python
@dataclass(frozen=True)
class StagedBundle:
    dist_root: Path
    product_build: str
    host_version: str
    archive_sha256: str


class BundleError(RuntimeError):
    pass


def parse_detached_checksum(path: Path, expected_name: str) -> str:
    fields = path.read_text(encoding="utf-8").strip().split()
    if len(fields) != 2 or fields[1].removeprefix("*") != expected_name:
        raise BundleError("release checksum record is invalid")
    digest = fields[0].lower()
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise BundleError("release checksum digest is invalid")
    return digest


def stage_release_bundle(
    *,
    repo_root: Path,
    archive_path: Path,
    checksum_path: Path,
    output_root: Path,
    expected_product_build: str,
    expected_host_version: str,
    verifier: Callable[[Path, Path], None] | None = None,
) -> StagedBundle:
    """Validate and atomically stage exactly one dist/ tree."""
```

Use `zipfile.ZipInfo.external_attr` to reject symlinks and non-regular entries, reject duplicate normalized paths, require exactly one top-level `dist/`, extract into a sibling temporary directory, call `package.py::verify_distribution`, read `host-manifest.json`, compare both identities, then `os.replace` the staged root into the previously absent `output_root`. On every exception, remove only the owned temporary directory and leave `output_root` absent.

- [ ] **Step 4: Add identity, verifier, success, and canonical CLI tests**

Add tests proving:

```python
def test_success_calls_verifier_and_emits_canonical_metadata(self) -> None:
    observed: list[tuple[Path, Path]] = []
    bundle = self.stage_valid(
        verifier=lambda root, repo: observed.append((root, repo)),
    )
    self.assertEqual(observed, [(bundle.dist_root, REPO_ROOT)])
    self.assertEqual(bundle.product_build, "1.0.15.2")
    self.assertEqual(bundle.host_version, "1.1.2")
    self.assertRegex(bundle.archive_sha256, r"^[0-9a-f]{64}$")
```

The CLI must require `stage`, all six named arguments, print one sorted compact JSON object to stdout, print `Web Runtime deployment bundle error: ...` to stderr on failure, return `64` for usage and `2` for validation failure.

- [ ] **Step 5: Run Task 1 tests**

Run:

```bash
python3 apps/web-runtime-host/test/release_bundle_test.py
python3 apps/web-runtime-host/test/package_test.py
python3 apps/web-runtime-host/test/distribution_test.py
```

Expected: all tests pass with no network access.

- [ ] **Step 6: Add the release bundle test to Host test/proof**

In `run_nonbrowser_tests()` add exactly:

```bash
python3 "$repo_root/apps/web-runtime-host/test/release_bundle_test.py"
```

Place it after `package_test.py` and before browser work.

- [ ] **Step 7: Commit Task 1**

```bash
git add \
  apps/web-runtime-host/tools/release_bundle.py \
  apps/web-runtime-host/test/release_bundle_test.py \
  scripts/web-runtime-host.sh
git diff --cached --check
git commit -m "feat(deploy): verify released Runtime Host bundles"
```

---

### Task 2: Netlify Draft Deploy and Same-ID Publication Client

**Files:**
- Create: `apps/web-runtime-host/deploy/_headers`
- Create: `apps/web-runtime-host/tools/netlify_api.py`
- Create: `apps/web-runtime-host/test/netlify_api_test.py`
- Modify: `scripts/web-runtime-host.sh`

**Interfaces:**
- Consumes: verified `dist_root`, tracked `_headers`, `NETLIFY_RUNTIME_SITE_ID`, `NETLIFY_AUTH_TOKEN`, API base URL, bounded deadline.
- Produces: `DraftDeploy(id, site_id, deploy_ssl_url, state)`; `publish_deploy()` returns the same ID with the production `ssl_url`.

- [ ] **Step 1: Write request-contract tests against an in-process fake API**

```python
def test_create_draft_uploads_only_required_sha1_files(self) -> None:
    draft = self.client.create_draft(
        site_id="site-123",
        files={"/index.html": b"index", "/_headers": b"/*\n  X-Robots-Tag: noindex\n"},
        title="LMDJ Product 1.0.15.2 Host 1.1.2",
    )
    create = self.server.requests[0]
    self.assertEqual(create.method, "POST")
    self.assertEqual(create.path, "/api/v1/sites/site-123/deploys?title=LMDJ%20Product%201.0.15.2%20Host%201.1.2")
    self.assertEqual(create.json["draft"], True)
    self.assertEqual(create.json["files"]["/index.html"], hashlib.sha1(b"index").hexdigest())
    self.assertEqual([request.method for request in self.server.requests[1:]], ["PUT"])
    self.assertEqual(draft.id, "deploy-456")
```

Also test malformed JSON; missing or invalid required fields while accepting additive documented fields; foreign `site_id`; non-HTTPS deploy URL; required digest not present locally; encoded nested asset paths; API error body/header redaction and unreachable exception context; non-terminal poll states; error state; and deadline expiry. For every SHA-1 in `required`, select one deterministic local representative and upload it exactly once, including when multiple paths have identical content.

- [ ] **Step 2: Run the tests and verify the failure**

Run:

```bash
python3 apps/web-runtime-host/test/netlify_api_test.py
```

Expected: `ModuleNotFoundError` for `apps/web-runtime-host/tools/netlify_api.py`.

- [ ] **Step 3: Implement the typed Netlify client**

Use only `urllib.request`, `urllib.parse`, `hashlib`, `json`, `time`, and dataclasses:

```python
@dataclass(frozen=True)
class DraftDeploy:
    id: str
    site_id: str
    deploy_ssl_url: str
    state: str


class NetlifyError(RuntimeError):
    pass


class NetlifyClient:
    def __init__(self, *, token: str, api_base: str = "https://api.netlify.com/api/v1") -> None:
        if not token or "\n" in token or "\r" in token:
            raise NetlifyError("Netlify token is invalid")
        self._token = token
        self._api_base = api_base.rstrip("/")

    def create_draft(
        self,
        *,
        site_id: str,
        files: Mapping[str, bytes],
        title: str,
        deadline_seconds: float = 120.0,
    ) -> DraftDeploy:
        """Create draft digest, upload required files, and wait for ready."""

    def publish_deploy(self, *, site_id: str, deploy_id: str) -> dict[str, object]:
        """Restore exactly deploy_id and require it as the live ready production Deploy."""
```

Every request sends `Authorization: Bearer`, `Accept: application/json`, and a fixed user agent. Accept additive documented response fields, but reject malformed JSON and missing or invalid required fields. For every HTTP failure, close and discard the response; never include the token, raw response body, or response headers in an exception, cause, or context. Encode file paths segment-by-segment while preserving `/` separators.

- [ ] **Step 4: Add the exact deploy-control header template**

Create `apps/web-runtime-host/deploy/_headers` with the current proof-server CSP copied byte-for-byte:

```text
/*
  Cross-Origin-Opener-Policy: same-origin
  Cross-Origin-Embedder-Policy: require-corp
  Cross-Origin-Resource-Policy: same-origin
  Content-Security-Policy: default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; child-src 'self' blob:; connect-src 'self'; style-src 'self'; img-src 'self'; media-src 'self' blob:; manifest-src 'self'
  X-Content-Type-Options: nosniff
  X-Robots-Tag: noindex, nofollow, noarchive

/
  Cache-Control: no-store

/index.html
  Cache-Control: no-store

/host-manifest.json
  Cache-Control: no-store

/assets/*
  Cache-Control: public, max-age=31536000, immutable
```

Do not add a catch-all rewrite or authentication header.

- [ ] **Step 5: Prove same-ID publication and failed draft isolation**

```python
def test_publish_uses_restore_and_requires_the_same_deploy_id(self) -> None:
    published = self.client.publish_deploy(site_id="site-123", deploy_id="deploy-456")
    request = self.server.requests[-1]
    self.assertEqual(request.method, "POST")
    self.assertEqual(request.path, "/api/v1/sites/site-123/deploys/deploy-456/restore")
    self.assertEqual(published["id"], "deploy-456")
    self.assertEqual(published["site_id"], "site-123")
    self.assertEqual(published["ssl_url"], "https://runtime.example")
    self.assertEqual(published["state"], "ready")

def test_api_failure_never_calls_restore(self) -> None:
    self.server.fail_upload = True
    with self.assertRaises(NetlifyError):
        self.create_ready_draft()
    self.assertFalse(any(request.path.endswith("/restore") for request in self.server.requests))
```

The restore response must identify the exact requested Deploy ID and site, provide an HTTPS production `ssl_url`, and report the live state `ready`; it must not create or accept a second production Deploy.

- [ ] **Step 6: Run Task 2 tests and register them in Host proof**

Run:

```bash
python3 apps/web-runtime-host/test/netlify_api_test.py
python3 apps/web-runtime-host/test/server_test.py
```

Expected: all tests pass. Add `netlify_api_test.py` to `run_nonbrowser_tests()` immediately after the release bundle test.

- [ ] **Step 7: Commit Task 2**

```bash
git add \
  apps/web-runtime-host/deploy/_headers \
  apps/web-runtime-host/tools/netlify_api.py \
  apps/web-runtime-host/test/netlify_api_test.py \
  scripts/web-runtime-host.sh
git diff --cached --check
git commit -m "feat(deploy): stage atomic Netlify Runtime deploys"
```

---

### Task 3: Immutable HTTP and Chromium Deployment Smoke

**Files:**
- Create: `apps/web-runtime-host/tools/deployment_smoke.py`
- Create: `apps/web-runtime-host/test/deployment_smoke_test.py`
- Create: `tests/platform/web/deployment/web_runtime_host_deployment.spec.mjs`
- Modify: `scripts/web-runtime-host.sh`

**Interfaces:**
- Consumes: HTTPS base URL, expected Product Build, Host version, optional expected Deploy ID.
- Produces: canonical HTTP smoke JSON and Playwright pass/fail; performs no publication.

- [ ] **Step 1: Write HTTP smoke tests for identity and headers**

```python
def test_accepts_exact_host_identity_headers_mime_cache_and_negative_routes(self) -> None:
    result = smoke_http(
        base_url=self.server.base_url,
        expected_product_build="1.0.15.2",
        expected_host_version="1.1.2",
        require_https=False,
    )
    self.assertEqual(result["product_build"], "1.0.15.2")
    self.assertEqual(result["host_version"], "1.1.2")
    self.assertEqual(result["asset_count"], 9)

def test_rejects_missing_cross_origin_or_noindex_header(self) -> None:
    for header in REQUIRED_SECURITY_HEADERS:
        with self.subTest(header=header):
            self.server.omit_header = header
            with self.assertRaisesRegex(SmokeError, re.escape(header)):
                self.smoke()
```

Also cover HTTP URL rejection, redirects to a different origin, manifest digest mismatch, wrong Product/Host, wrong WASM MIME, wrong cache, asset digest mismatch, raw-source 200, unknown-path 200, and traversal 200.

- [ ] **Step 2: Run the HTTP tests and verify the failure**

Run:

```bash
python3 apps/web-runtime-host/test/deployment_smoke_test.py
```

Expected: `ModuleNotFoundError` for `apps/web-runtime-host/tools/deployment_smoke.py`.

- [ ] **Step 3: Implement bounded HTTP smoke**

```python
REQUIRED_SECURITY_HEADERS = {
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-embedder-policy": "require-corp",
    "cross-origin-resource-policy": "same-origin",
    "x-content-type-options": "nosniff",
    "x-robots-tag": "noindex, nofollow, noarchive",
}


class SmokeError(RuntimeError):
    pass


def smoke_http(
    *,
    base_url: str,
    expected_product_build: str,
    expected_host_version: str,
    require_https: bool = True,
    timeout_seconds: float = 10.0,
) -> dict[str, object]:
    """Validate index, manifest, every declared asset, and negative routes."""
```

Use a redirect handler that rejects cross-origin and HTTPS-to-HTTP redirects. Fetch `/index.html`, `/host-manifest.json`, every manifest asset, `/missing`, `/assets/missing.map`, and encoded traversal. Compare SHA-256 for every asset and the manifest meta digest in index. Print sorted compact JSON only after all checks pass.

- [ ] **Step 4: Write the deployment-only Chromium journey**

Create a separate spec that does not read repository audio fixtures:

```javascript
import { expect, test } from "@playwright/test";

test("published Runtime Host completes the minimal diagnostic journey", async ({ page }) => {
  test.setTimeout(360_000);
  await page.goto("/index.html");
  const identity = await page.evaluate(async () => {
    const manifest = await fetch("./host-manifest.json", { cache: "no-store" })
      .then((response) => response.json());
    return {
      secure: window.isSecureContext,
      isolated: window.crossOriginIsolated,
      sharedArrayBuffer: typeof SharedArrayBuffer === "function",
      productBuild: manifest.product_build,
      hostVersion: manifest.host_version,
      manifestReady: window.lmdjWebRuntimeHost.manifestReady,
      runtimeInitialized: window.lmdjWebRuntimeHost.runtimeInitialized,
    };
  });
  expect(identity).toEqual({
    secure: true,
    isolated: true,
    sharedArrayBuffer: true,
    productBuild: process.env.LMDJ_WEB_HOST_EXPECTED_PRODUCT_BUILD,
    hostVersion: process.env.LMDJ_WEB_HOST_EXPECTED_VERSION,
    manifestReady: true,
    runtimeInitialized: true,
  });
  await page.locator("#diagnostic-project-load").click();
  await expect(page.locator("#diagnostic-project-state")).toHaveText("ready", { timeout: 300_000 });
  await page.locator("#audio-activate").click();
  await expect(page.locator("#host-state")).toHaveText("running", { timeout: 60_000 });
  const marker = await page.evaluate(() =>
    window.lmdjWebRuntimeController.diagnostics().trigger_outcome_count,
  );
  await page.locator("#pad-0").click();
  await expect.poll(() => page.evaluate(() =>
    window.lmdjWebRuntimeController.diagnostics().trigger_outcome_count,
  )).toBe(marker + 1);
  expect(await page.evaluate(() => window.lmdjWebRuntimeController.close())).toBe(true);
  await expect(page.locator("#host-state")).toHaveText("closed");
});
```

Use the existing exact privacy-safe field `trigger_outcome_count`; do not add a new production diagnostic solely for the test. Fail if either expected-version environment variable is missing.

- [ ] **Step 5: Run local smoke against a verified dist**

Run:

```bash
source build/toolchains/emsdk/emsdk_env.sh
scripts/web-runtime-host.sh build
python3 apps/web-runtime-host/tools/server.py --root build/web/host/dist --port 4175 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT
LMDJ_WEB_HOST_EXTERNAL_SERVER=1 \
LMDJ_WEB_HOST_BASE_URL=http://127.0.0.1:4175 \
LMDJ_WEB_HOST_EXPECTED_PRODUCT_BUILD=1.0.15.2 \
LMDJ_WEB_HOST_EXPECTED_VERSION=1.1.2 \
npm --prefix tests/platform/web test -- \
  --project=chromium deployment/web_runtime_host_deployment.spec.mjs
```

Expected: one Chromium test passes and the owned server is terminated.

- [ ] **Step 6: Run Task 3 tests and register offline smoke tests**

Add `deployment_smoke_test.py` to `run_nonbrowser_tests()` after `netlify_api_test.py`, then run:

```bash
python3 apps/web-runtime-host/test/deployment_smoke_test.py
scripts/web-runtime-host.sh test
```

Expected: all Host tests pass; the deployment Playwright spec is run only by the explicit deployment command, not added to the formal Host spec glob.

- [ ] **Step 7: Commit Task 3**

```bash
git add \
  apps/web-runtime-host/tools/deployment_smoke.py \
  apps/web-runtime-host/test/deployment_smoke_test.py \
  tests/platform/web/deployment/web_runtime_host_deployment.spec.mjs \
  scripts/web-runtime-host.sh
git diff --cached --check
git commit -m "test(deploy): prove published Runtime Host behavior"
```

---

### Task 4: Fail-Closed Deployment Orchestrator

**Files:**
- Create: `scripts/web-runtime-deploy.sh`
- Create: `apps/web-runtime-host/tools/deploy_orchestrator.py`
- Create: `apps/web-runtime-host/test/deploy_command_test.py`
- Modify: `scripts/web-runtime-host.sh`

**Interfaces:**
- Consumes: exact Product tag argument and environment `GITHUB_TOKEN`, `NETLIFY_RUNTIME_SITE_ID`, `NETLIFY_AUTH_TOKEN`.
- Produces: `build/deploy/web-runtime-host/evidence.json`; exits before restore if any earlier gate fails.

- [ ] **Step 1: Write command usage and order tests with fake executables**

```python
def test_deploy_orders_draft_smoke_publish_and_production_smoke(self) -> None:
    completed = self.run_command("deploy", "lmdj-v1.0.15.2")
    self.assertEqual(completed.returncode, 0, completed.stderr)
    self.assertEqual(
        self.command_log(),
        [
            "git tag verify lmdj-v1.0.15.2",
            "gh release view lmdj-v1.0.15.2",
            "gh release download lmdj-v1.0.15.2",
            "release_bundle stage",
            "netlify create-draft",
            "http-smoke immutable",
            "playwright immutable",
            "netlify publish same-id",
            "http-smoke production",
            "playwright production",
        ],
    )

def test_failed_immutable_smoke_never_publishes(self) -> None:
    completed = self.run_command(
        "deploy", "lmdj-v1.0.15.2", environment={"FAIL_IMMUTABLE_SMOKE": "1"}
    )
    self.assertNotEqual(completed.returncode, 0)
    self.assertNotIn("netlify publish same-id", self.command_log())
```

Also test missing secrets, invalid tag grammar, `latest`, bare SHA, branch names, draft Release, non-prerelease Release, asset duplicates, Product/Host filename mismatch, foreign deploy hostname, production hostname mismatch, owned temp cleanup, and token absence from stdout/stderr/evidence.

- [ ] **Step 2: Run the tests and verify the failure**

Run:

```bash
python3 apps/web-runtime-host/test/deploy_command_test.py
```

Expected: failure because `scripts/web-runtime-deploy.sh` is absent.

- [ ] **Step 3: Implement the stable command entrypoint**

The public usage is exact:

```text
usage:
  scripts/web-runtime-deploy.sh verify TAG
  scripts/web-runtime-deploy.sh deploy TAG
  scripts/web-runtime-deploy.sh smoke BASE_URL PRODUCT_BUILD HOST_VERSION
```

Start with:

```bash
#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$script_dir/.." && pwd -P)"
deploy_root="$repo_root/build/deploy/web-runtime-host"
tag_pattern='^lmdj-v([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)$'
production_url='https://lmdj-runtime.netlify.app'
```

Use `mktemp -d` under `${RUNNER_TEMP:-${TMPDIR:-/tmp}}`, validate the cleanup prefix before removal, create a temporary `GNUPGHOME`, import only `.github/release-signing-keys/lmdj-product.asc`, run `git verify-tag --raw`, and require the exact trusted fingerprint from the key file test. Resolve `tag_target="$(git rev-parse "${tag}^{commit}")"`, create a detached verification checkout with `git worktree add --detach "$owned_temp/tag-target" "$tag_target"`, and treat it as read-only. The merged-`main` command must pass that checkout—not its own repository root—to `release_bundle.py --repo-root`, so Product/Host manifests and `package.py::verify_distribution` come from the exact signed tag target even when the initial tag predates the deployment tooling. Remove the detached worktree with `git worktree remove --force` before validating and deleting only the owned temporary root.

Resolve Release metadata with `gh release view --json tagName,isDraft,isPrerelease,targetCommitish,assets,url` and download exact asset names with `gh release download`.

Call the Python tools in order. Build Netlify deploy files from every verified dist file plus `_headers`; never mutate the staged dist. Write evidence atomically only after production smoke passes.

- [ ] **Step 4: Define canonical evidence JSON**

Build the successful record from the live staged bundle, draft deploy, verified tag
target, selected site, and GitHub Release URL; never use sample IDs or URLs:

```python
evidence = {
    "archive_sha256": staged.archive_sha256,
    "channel": "canary",
    "contract": "lmdj.web-runtime-host.deployment-evidence.v1",
    "deploy_id": draft.id,
    "deploy_url": draft.deploy_ssl_url,
    "git_revision": tag_target,
    "host_version": staged.host_version,
    "product_build": staged.product_build,
    "production_url": "https://lmdj-runtime.netlify.app",
    "release_url": release_url,
    "site_id": site_id,
    "tag": tag,
}
```

Serialize with sorted keys and a trailing newline, then atomically replace the evidence
file only after production smoke passes. For the initial deployment, require tag target
`72ae40074620cc5681c462ba04a31a666449734f` and Host archive SHA-256
`d56a7c99a3c489db068b93fcef70a254b498adf4bc65919253beccb199f3ad5a`;
the Core ZIP digest is invalid here. Tests must compare keys exactly and reject token-like
values.

- [ ] **Step 5: Run command tests and shell checks**

```bash
python3 apps/web-runtime-host/test/deploy_command_test.py
bash -n scripts/web-runtime-deploy.sh
bash tests/build/test_active_tree.sh
```

Expected: all pass without network access or deployment secrets.

- [ ] **Step 6: Register the command test in Host test/proof**

Add `deploy_command_test.py` after `deployment_smoke_test.py` in `run_nonbrowser_tests()`. Do not call `deploy` from ordinary Host Proof.

- [ ] **Step 7: Commit Task 4**

```bash
git add \
  scripts/web-runtime-deploy.sh \
  apps/web-runtime-host/tools/deploy_orchestrator.py \
  apps/web-runtime-host/test/deploy_command_test.py \
  scripts/web-runtime-host.sh
git diff --cached --check
git commit -m "feat(deploy): orchestrate Runtime Host publication"
```

---

### Task 5: Signed Release Deployment Workflow

**Files:**
- Create: `.github/release-signing-keys/lmdj-product.asc`
- Create: `.github/workflows/deploy-web-runtime-host.yml`
- Create: `tests/build/web_runtime_deploy_workflow_test.py`
- Modify: `CMakeLists.txt`

**Interfaces:**
- Consumes: GitHub `release.published` or manual exact tag, GitHub Environment `runtime-canary`, `NETLIFY_RUNTIME_SITE_ID`, `NETLIFY_AUTH_TOKEN`.
- Produces: one serialized deployment run and uploaded `runtime-host-deployment-evidence` artifact.

- [ ] **Step 1: Pin and verify the Product signing key**

On the trusted release workstation:

```bash
fingerprint=2B5EE362F058800036AD4FB5116ECE156F954D29
gpg --batch --armor --export "$fingerprint" > .github/release-signing-keys/lmdj-product.asc
observed="$({ gpg --batch --show-keys --with-colons .github/release-signing-keys/lmdj-product.asc; } | awk -F: '$1 == "fpr" {print $10; exit}')"
test "$observed" = "$fingerprint"
```

The file contains the public key only. Never export or copy private key material.

- [ ] **Step 2: Write the workflow contract test**

```python
def test_workflow_only_deploys_published_release_or_exact_manual_tag(self) -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    self.assertIn("release:\n    types: [published]", source)
    self.assertIn("workflow_dispatch:", source)
    self.assertNotIn("pull_request:", source)
    self.assertNotRegex(source, r"(?m)^  push:")
    self.assertIn("environment: runtime-canary", source)
    self.assertIn("cancel-in-progress: false", source)
    self.assertIn("permissions:\n  contents: read", source)
    self.assertNotIn("contents: write", source)
    self.assertIn("ref: main", source)
    self.assertIn("scripts/web-runtime-deploy.sh deploy", source)
    self.assertIn("NETLIFY_RUNTIME_SITE_ID", source)
    self.assertIn("NETLIFY_AUTH_TOKEN", source)
```

Add a key test that runs `gpg --show-keys --with-colons` and requires exactly the trusted fingerprint.

- [ ] **Step 3: Run the contract test and verify the failure**

```bash
python3 tests/build/web_runtime_deploy_workflow_test.py
```

Expected: failure because the workflow and public key are absent.

- [ ] **Step 4: Implement the workflow**

Use this topology:

```yaml
name: Deploy Web Runtime Host

on:
  release:
    types: [published]
  workflow_dispatch:
    inputs:
      tag:
        description: Exact signed Product tag
        required: true
        type: string

permissions:
  contents: read

concurrency:
  group: web-runtime-host-production
  cancel-in-progress: false

jobs:
  deploy:
    environment: runtime-canary
    runs-on: ubuntu-24.04
    timeout-minutes: 30
```

Steps must checkout protected `main` with `ref: main` and `fetch-depth: 0`, set Python 3.11 and Node 22, run `npm ci` under `tests/platform/web`, install only Chromium, derive the tag from `github.event.release.tag_name` or `inputs.tag`, require `github.event.release.prerelease == true` on release events, execute `scripts/web-runtime-deploy.sh deploy "$tag"`, and upload `build/deploy/web-runtime-host/evidence.json` plus failure logs with `if: always()` and `if-no-files-found: warn`. The command creates the detached tag-target verification checkout described in Task 4; the workflow must not replace the protected-`main` tooling checkout with a tag checkout.

Do not install Emscripten or rerun Core CI in this workflow; it verifies the published asset and runs deployment-specific smoke.

- [ ] **Step 5: Register the workflow contract in Core contract tier**

Add:

```cmake
lmdj_add_test(
  NAME build.web_runtime_deploy_workflow
  TIER contract
  COMMAND
    "${Python3_EXECUTABLE}"
    tests/build/web_runtime_deploy_workflow_test.py
  WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
  TIMEOUT 10
)
```

- [ ] **Step 6: Run Task 5 verification**

```bash
python3 tests/build/web_runtime_deploy_workflow_test.py
scripts/core.sh configure dev
scripts/core.sh build dev
ctest --test-dir build/core/dev --output-on-failure -R '^build\.(active_tree|web_runtime_deploy_workflow)$'
```

Expected: both selected CTests pass.

- [ ] **Step 7: Commit Task 5**

```bash
git add \
  .github/release-signing-keys/lmdj-product.asc \
  .github/workflows/deploy-web-runtime-host.yml \
  tests/build/web_runtime_deploy_workflow_test.py \
  CMakeLists.txt
git diff --cached --check
git commit -m "ci(deploy): publish signed Runtime Host releases"
```

---

### Task 6: Pre-Deployment Operations and Portal Current Truth

**Files:**
- Create: `docs/deploy/web-runtime-host.md`
- Create: `docs/quality/2026-08-08-web-runtime-public-deployment-acceptance.md`
- Modify: `apps/architecture-portal/docs/operations/version-and-release.mdx`
- Modify: `apps/architecture-portal/docs/hosts/web-runtime.mdx`
- Modify: `apps/architecture-portal/docs/platform/web-runtime.mdx`

**Interfaces:**
- Consumes: Tasks 1–5 commands and current Product `1.0.15.2` / Host `1.1.2` identities.
- Produces: operator runbook and truthful pre-deploy Portal state; no deploy ID is invented.

- [ ] **Step 1: Write the operator runbook**

Document exact prerequisites and commands:

```bash
gh auth status
git fetch origin --tags
git tag -v lmdj-v1.0.15.2
scripts/web-runtime-deploy.sh verify lmdj-v1.0.15.2
gh workflow run deploy-web-runtime-host.yml --ref main -f tag=lmdj-v1.0.15.2
```

Include separate sections for Netlify project creation, Git-disconnection/auto-publish-off verification, GitHub Environment secrets, evidence inspection, production smoke, failed draft, failed production alias, rollback by exact prior Deploy ID, credential rotation, and why `lmdj-canary` is not created in this Task.

- [ ] **Step 2: Create the acceptance record in pre-deploy state**

The initial table must say:

```markdown
| Gate | Current result |
| --- | --- |
| Local deployment tooling tests | pending implementation verification |
| PR review and CI | not run |
| Netlify project `lmdj-runtime` | not authorized / not created |
| GitHub Environment secrets | not authorized / not configured |
| Immutable Deploy URL | absent |
| Production URL publication | not performed |
| Physical gates | deferred / unverified; unchanged |
```

Do not pre-fill a Deploy ID, site ID, immutable URL, run URL, or deployment time.

- [ ] **Step 3: Update the three Portal routes**

State that the two-phase deployment path is implemented only after the code exists, but public deployment remains absent until an exact evidence record is committed. Keep `proof-only server does not belong to production` true; Netlify serves the verified static dist and is not that Python server.

- [ ] **Step 4: Run documentation and full feature gates**

```bash
git diff --check
scripts/architecture-portal.sh check
python3 apps/web-runtime-host/test/release_bundle_test.py
python3 apps/web-runtime-host/test/netlify_api_test.py
python3 apps/web-runtime-host/test/deployment_smoke_test.py
python3 apps/web-runtime-host/test/deploy_command_test.py
python3 tests/build/web_runtime_deploy_workflow_test.py
scripts/web-runtime-host.sh proof
scripts/core.sh proof
```

Expected: all gates pass. Host Proof still proves Product `1.0.15.2`, Host `1.1.2`; no product/version file changes exist.

- [ ] **Step 5: Inspect scope and commit Task 6**

```bash
git status --short
git diff --name-only
git add \
  docs/deploy/web-runtime-host.md \
  docs/quality/2026-08-08-web-runtime-public-deployment-acceptance.md \
  apps/architecture-portal/docs/operations/version-and-release.mdx \
  apps/architecture-portal/docs/hosts/web-runtime.mdx \
  apps/architecture-portal/docs/platform/web-runtime.mdx
git diff --cached --check
git commit -m "docs(deploy): govern public Runtime Host publication"
```

---

### Task 7: Review, Merge, and Controlled Initial Activation

**Files:**
- Modify after real deployment: `docs/quality/2026-08-08-web-runtime-public-deployment-acceptance.md`
- Modify after real deployment: `apps/architecture-portal/docs/operations/version-and-release.mdx`
- Modify after real deployment: `apps/architecture-portal/docs/hosts/web-runtime.mdx`
- Modify after real deployment: `apps/architecture-portal/docs/platform/web-runtime.mdx`

**Interfaces:**
- Consumes: merged Tasks 1–6, separately authorized Netlify project/secrets, exact workflow evidence.
- Produces: live `lmdj-runtime.netlify.app` and a later evidence-only documentation commit/PR.

- [ ] **Step 1: Push and open the implementation PR only after explicit authorization**

The PR declaration is exact:

```text
Documentation impact: required
Affected portal pages: /operations/version-and-release/, /hosts/web-runtime/, /platform/web-runtime/
Version impact: none
Reason: adds deployment tooling and operations for unchanged released Host bytes
```

Do not create the Netlify project or secrets from a Pull Request job.

- [ ] **Step 2: Require implementation PR gates before merge**

Require Architecture Portal, Core contract tests, Web Runtime Host Proof, and code review. Squash merge only after authorization. Do not trigger deployment from PR or merge; the workflow has no branch push trigger.

- [ ] **Step 3: Obtain separate authorization for external state**

Resolve exact targets read-only first:

```text
Netlify project name: lmdj-runtime
Production URL: https://lmdj-runtime.netlify.app
GitHub Environment: runtime-canary
Secrets: NETLIFY_RUNTIME_SITE_ID, NETLIFY_AUTH_TOKEN
Initial tag: lmdj-v1.0.15.2
```

Create/configure them only after the user approves those exact targets.

- [ ] **Step 4: Run the initial deployment from merged `main`**

```bash
gh workflow run deploy-web-runtime-host.yml --ref main -f tag=lmdj-v1.0.15.2
```

Wait for the run to finish. Require the workflow evidence artifact, immutable URL smoke, same-ID restore response, and production alias smoke. A queued, in-progress, canceled, or draft-only run is not deployed.

- [ ] **Step 5: Verify live state independently**

Run from updated `main`:

```bash
scripts/web-runtime-deploy.sh smoke \
  https://lmdj-runtime.netlify.app \
  1.0.15.2 \
  1.1.2
```

Then open the production URL in Chromium and manually confirm:

```text
Load diagnostic project -> ready -> Activate audio -> running -> Pad 1 sounds
```

Manual sound is supplementary evidence, not the Physical MIDI/Touch/latency gate.

- [ ] **Step 6: Create a new evidence branch and update exact deployment truth**

From updated `main`, create `docs/web-runtime-public-deployment-evidence` in a new isolated worktree. Replace only the pre-deploy rows with actual Product/Host/tag/SHA/archive digest, workflow run URL, Netlify site ID, Deploy ID, immutable URL, production URL, HTTP/browser smoke results, and timestamps. Keep all physical rows deferred/unverified.

- [ ] **Step 7: Verify and commit the evidence update**

```bash
scripts/architecture-portal.sh check
git diff --check
git add \
  docs/quality/2026-08-08-web-runtime-public-deployment-acceptance.md \
  apps/architecture-portal/docs/operations/version-and-release.mdx \
  apps/architecture-portal/docs/hosts/web-runtime.mdx \
  apps/architecture-portal/docs/platform/web-runtime.mdx
git diff --cached --check
git commit -m "docs(deploy): record Runtime Host canary publication"
```

Push/PR/merge this evidence commit only with separate authorization. Publication may be reported after live smoke passes even while the evidence PR is pending, but Portal current truth is not synchronized until that PR merges and its production Portal deployment is smoke-verified.

---

## Final Verification Matrix

| Boundary | Required evidence |
| --- | --- |
| Released bytes | Detached SHA-256, safe extraction, canonical Host verifier, Product/Host identity |
| Tag authority | Annotated signed tag, pinned fingerprint, exact target SHA, prerelease metadata |
| Draft isolation | `draft: true`, immutable URL, no restore request before smoke |
| HTTP contract | HTTPS, headers, noindex, MIME, cache, manifest/index/asset hashes, negative routes |
| Browser contract | Secure context, cross-origin isolation, diagnostic ready, audio running, exact trigger outcome, close cleanup |
| Publication | Restore response identifies the same Deploy ID; production alias repeats smoke |
| Failure | Current production remains unchanged or restores prior exact Deploy ID |
| Documentation | Pre-deploy truth before activation; exact evidence only after live verification |
| Product status | No new Product/Host version, no Creator/PWA claim, physical gates unchanged |

## Plan Self-review

- [x] Every approved design decision maps to Tasks 1–7.
- [x] Product files remain byte-identical; `_headers` is a separate deploy-control artifact.
- [x] The same Deploy ID is smoked before publication and restored into production.
- [x] Workflow has no Pull Request or branch-push production path.
- [x] External Netlify state and secrets remain separately authorized.
- [x] Initial deployment and post-deploy evidence are separated from implementation merge.
- [x] Version impact and the three required Portal routes are explicit.
- [x] All named functions, environment variables, commands, outputs, and failure states are defined.
- [x] No unresolved implementation markers remain.
