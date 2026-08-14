# LMDJ Standard Release Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repository-owned, fail-closed release control plane that prepares signed tags and exact assets locally, pushes one exact tag, creates only a Draft GitHub Release, publishes it through a protected manual workflow, and audits all release state without coupling publication to deployment.

**Architecture:** A Python 3.11 standard-library package under `tools/release/` owns closed schemas, deterministic plans, Git/GitHub projections, signing, state transitions, and audit findings. `scripts/release.sh` is the stable thin entry point. A tracked intent ledger authorizes identities, while freshly fetched Git/GitHub state remains authoritative for observed tag, Draft, and published states.

**Tech Stack:** Python 3.11 standard library, Bash, Git, GnuPG, GitHub CLI/REST API, GitHub Actions YAML, Python `unittest`, existing CTest and Architecture Portal gates.

**Spec:** `docs/superpowers/specs/2026-08-13-lmdj-standard-release-pipeline-design.md`

## Global Constraints

- Execute from a new `feat/standard-release-pipeline` branch in `.worktrees/standard-release-pipeline`, based on latest `origin/main`; do not implement on this documentation branch or primary `main`.
- Each numbered Task is one reviewable Conventional Commit. Run its tests, stage only declared files, inspect `git diff --cached --name-status`, run `git diff --cached --check`, inspect the staged diff, commit, then inspect the committed paths and status.
- `prepare`, `push-tag`, `create-draft`, publish workflow dispatch, deployment, and Channel promotion remain separately authorized.
- Canonical repository/branch are exactly `endaye/lmdj` and `main`.
- Product tag fingerprint is `2B5EE362F058800036AD4FB5116ECE156F954D29`; checksum fingerprint is `CB928A6E89DE498851688EF1AAC3E7019FC1478B`; roles never substitute for each other.
- Private keys/passphrases stay local. Actions receive only tracked public keys and a scoped ephemeral token.
- Product canary/dev/beta are prereleases with `latest=false`; stable is non-prerelease and becomes latest only through an explicit stable intent. Module/Contract/Provider use `prerelease=false`, `latest=false`.
- Release publication must not trigger Runtime deployment. Deployment remains exact-tag `workflow_dispatch` under `runtime-canary`.
- Normal tooling never force-pushes/moves tags, uses `--tags`, clobbers assets, edits published Releases, or deletes formal history.
- Historical exceptions explain exact pre-pipeline immutable state only; mutation commands always reject them.
- `audit` is read-only; network/API uncertainty is `external-error`, never a clean result.
- Version impact: none. Documentation impact: required for `/operations/version-and-release/`, `/operations/testing-and-proof/`, `/hosts/web-runtime/`; no Product snapshot is created.
- External branch push/PR/merge, Environment configuration, live rehearsal, formal Release, deployment, and Channel promotion require the separately named rollout authorization.

## File Structure

| Path | Single responsibility |
| --- | --- |
| `tools/release/model.py` | Pure closed enums/dataclasses, schemas, tag classification, canonical JSON/digest. |
| `tools/release/policy.json` | Repository, branch, tag syntax, key roles, profiles, channel and cutoff policy. |
| `tools/release/commands.py` | Injectable secret-safe subprocess execution. |
| `tools/release/openpgp.py` | Agentless public verification and local detached signing. |
| `tools/release/git_repository.py` | Scratch refs/worktrees and exact tag operations. |
| `tools/release/profiles.py` | Source-only, Core package, and Web Runtime Host asset builders/verifiers. |
| `tools/release/prepare.py` | Local gates and `lmdj.release-plan.v1` generation. |
| `tools/release/github_api.py` | Typed paginated REST projections and exact asset transfer. |
| `tools/release/transitions.py` | Remote tag, Draft and publication transitions/reconciliation. |
| `tools/release/audit.py` | Read-only local/remote findings. |
| `tools/release/rehearsal.py` | Nonformal test-Draft rehearsal and guarded cleanup. |
| `tools/release/cli.py` | Stable argument/exit/output contract. |
| `scripts/release.sh` | Thin Bash wrapper only. |
| `docs/release-evidence/release-intents.json` | Reviewed authorization/lifecycle ledger, not external-state cache. |
| `.github/workflows/publish-release.yml` | Dispatch-only protected Draft publication. |
| `.github/workflows/release-audit.yml` | Main local audit and scheduled/manual remote audit. |
| `.agents/skills/lmdj-release/SKILL.md` | Thin navigation with no duplicated policy/secrets/state. |

---

### Task 1: Closed release model, policy, and complete migration ledger

**Files:**
- Create: `tools/release/__init__.py`
- Create: `tools/release/model.py`
- Create: `tools/release/policy.json`
- Create: `docs/release-evidence/release-intents.json`
- Create: `docs/release-evidence/2026-08-13-tag-release-backfill.md`
- Create: `tests/build/release_model_test.py`
- Modify: `scripts/ci/scope_policy.json`
- Modify: `tests/build/ci_change_scope_test.py`
- Modify: `CMakeLists.txt`

**Interfaces:**
- Consumes: active manifests/Portal metadata and the exact inventory below.
- Produces: `ReleaseKind`, `Disposition`, `TagIdentity`, `ReleaseIntent`, `HistoricalException`, `AssetRecord`, `ReleasePlan`, `ReleasePolicy`, `ReleaseLedger`; `classify_tag()`, `load_policy()`, `load_ledger()`, `canonical_json()`, `canonical_sha256()`.

- [ ] **Step 1: Write failing pure-model tests**

Create table-driven tests for all four formal tag kinds, stage/legacy exclusion, malformed versions, closed fields, duplicate tag/identity, disposition/profile/channel rules, stable-only explicit `make_latest`, historical-exception restrictions, canonical JSON/digest, and slash-safe output names:

```python
def test_classifies_formal_tags_and_rejects_legacy(self) -> None:
    self.assertEqual(classify_tag("lmdj-v1.0.16.9", self.policy).kind.value, "product")
    self.assertEqual(classify_tag("module/project-io/v0.3.0", self.policy).identity, ("project-io", "0.3.0"))
    for tag in ("lmdj-m1-plan.1", "v0.2.0", "wip/chameleon-2d-2026-07-26"):
        with self.assertRaises(ReleaseModelError):
            classify_tag(tag, self.policy)

def test_exception_cannot_authorize_releasable(self) -> None:
    document = self.ledger_fixture(disposition="releasable", with_exception=True)
    with self.assertRaisesRegex(ReleaseModelError, "historical exception"):
        load_ledger_document(document, self.policy)
```

- [ ] **Step 2: Run RED**

Run `python3 tests/build/release_model_test.py`.

Expected: FAIL because `tools.release.model` is missing.

- [ ] **Step 3: Implement the pure model**

Use frozen dataclasses/`StrEnum`, explicit exact-key validation, lowercase 40-hex SHA and 64-hex digest validation, and no boolean-to-integer coercion. Public signatures:

Implement the first three signatures exactly as declared in **Interfaces**. The canonical serializer is:

```python
def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")
```

`canonical_sha256()` returns `hashlib.sha256(canonical_json(value)).hexdigest()`.

`policy.json` contains the exact repository/branch/fingerprints, anchored regexes, profile inventories, channel mapping, `release`/`runtime-canary` Environment names and `historical_cutoff: "2026-08-13T00:00:00Z"`. Ledger parsing allows `make_latest` only for Product `stable`; it must be absent for every other channel/kind, whose policy result is always false.

- [ ] **Step 4: Add the complete ledger and dated evidence**

Record all 28 current-policy formal tags, not only the 14 backfilled Releases. Product tag-only entries `1.0.1.0`–`1.0.11.0` are `superseded-unreleased` with exact target/run pairs:

```text
1.0.1.0 755fbc769a2ff9d8e0d69814428909a92022e1d0 30534333762
1.0.2.0 81d48c26e7755584ff8278c55addcc89a53af262 30558012921
1.0.3.0 a42753e0137a54d60e10d20708d2ea7171074e3c 30570587406
1.0.4.0 dedafa8623fb244a3322603b1faebe04d4c2d535 30585224858
1.0.5.0 85065627b5c582e2176c2f98d63da5c4d62b0271 30592745904
1.0.6.0 97825379333ba063812543e86c79fbedfe585015 30597776577
1.0.7.0 eb7d653d14fa88af0f634b7efb0b4ac5c4a113f3 30688638013
1.0.8.0 7ba6caafeac2a0bbc0e919ef56dae070faf566dc 30695843438
1.0.9.0 33116e01539768db533001b3fbb9c3fdcba8dd15 30697224003
1.0.10.0 4e508fc3b048bc871049ff302668bd27a46edbe4 30751690298
1.0.11.0 8aae11d772456c1f6eb2007f6b928cc8c46c6a0c 30761741614
```

Published Product rows:

```text
1.0.13.0 2aa15224db421f162917ea1133c8f4c8ad62fefb 30871002469 core-package
1.0.14.0 d4cf657bdd194e3eeee4e78e119dcb0b97f49cdf 31010598130 web-runtime-host
1.0.15.2 72ae40074620cc5681c462ba04a31a666449734f 31193044255 web-runtime-host
1.0.16.5 38a8c130e5f1ced6f27d8fd7d2cba2fd1d70f97f 31327104838 web-runtime-host
1.0.16.8 336a27c0799035b2f8d6455b32259ee227df20f6 31529410253 web-runtime-host
1.0.16.9 d1d8bb6a629b6e05b86b3c8843870ef27edcfe5c 31634688566 web-runtime-host
```

For `1.0.15.2`, record exact `pre-pipeline-ci-evidence`: main run `31193044255` cancelled, exact-target Nightly successes `31211206448`/`31273884702`, plus existing deployment acceptance. Mutation commands must reject this exception.

The 11 Module Releases are `source-only`: four `0.2.0/1.0.1` rows target `4e508fc3b048bc871049ff302668bd27a46edbe4` run `30751690298`; seven `0.3.0/1.1.0/1.0.2/1.0.0` rows target `8aae11d772456c1f6eb2007f6b928cc8c46c6a0c` run `30761741614`.

Add `abandoned` Product rows: `1.0.16.6` at `fa0e619d3abd99f124e9dcce34e958815c21a23c`, `1.0.16.7` at `8f43f666b3b78bb9571c342c0c64951a7929aed5`, `1.0.18.0` at `561fa2d6324d2fe2025eaf692026e5eedcb350bb`; `1.0.19.0` is `superseded-unreleased` at `35c09053fd2bc64859b1a01c9cbbc2b5fb3a986d`. The implemented ledger later records `1.0.20.0` as `superseded-unreleased` and current `1.0.21.0` as `allocated` at `5613158240f7e31385ccb5d175bded3c245ae33b`; it remains non-releasable without an exact successful merged-main run.

Historical exceptions: legacy Release `v0.2.0`, target `9a2811bc326d7b63e538c77eeec428f617484ebe`, numeric ID `359913165`; legacy WIP tag `wip/chameleon-2d-2026-07-26`, target `a0f30e91d8f566eb7004430a3eb4de88cd25e4c3`. The dated evidence labels the 14 new backfills as a subset of the full history and says live audit wins over this snapshot.

- [ ] **Step 5: Wire ownership and CTest**

Map `tools/release/`, `scripts/release.sh`, ledger, `tests/build/release_*`, and the two new workflows to `deploy_contract` + `ci_contract`; keep signing-control changes full. Add exact scope cases. Register `build.release_model` as contract tier, timeout 30.

- [ ] **Step 6: Verify and commit**

```bash
python3 tests/build/release_model_test.py
python3 -m unittest tests.build.ci_change_scope_test
bash tests/build/test_active_tree.sh
scripts/architecture-portal.sh check
git add -- tools/release/__init__.py tools/release/model.py tools/release/policy.json \
  docs/release-evidence/release-intents.json \
  docs/release-evidence/2026-08-13-tag-release-backfill.md \
  tests/build/release_model_test.py scripts/ci/scope_policy.json \
  tests/build/ci_change_scope_test.py CMakeLists.txt
git diff --cached --check
git commit -m "feat(release): define release policy and intent ledger"
```

---

### Task 2: Local prepare, asset profiles, signing, and agentless verification

**Files:**
- Create: `tools/release/commands.py`, `openpgp.py`, `git_repository.py`, `profiles.py`, `prepare.py`, `cli.py`
- Create: `tools/release/github_api.py` with read-only branch/run projections
- Create: `scripts/release.sh`
- Create: `tests/build/release_openpgp_test.py`, `release_prepare_test.py`
- Modify: `apps/web-runtime-host/tools/release_bundle.py`
- Modify: `apps/web-runtime-host/test/release_bundle_test.py`
- Modify: `scripts/web-runtime-deploy.sh`
- Modify: `apps/web-runtime-host/test/deploy_command_test.py`
- Modify: `CMakeLists.txt`

**Interfaces:**
- Consumes: Task 1 types/policy/ledger; existing Core/Host package and release-bundle verifier.
- Produces: `CommandRunner.run()`, read-only `GitHubClient.get_branch()/list_runs_for_sha()`, `OpenPgpVerifier.import_public_key()/verify_detached()/sign_detached()`, `GitRepository.create_local_tag()`, `build_profile()`, `prepare()`.

- [ ] **Step 1: Write failing tests**

Prove command errors redact environment values; all public GPG calls include `--batch --no-tty --no-autostart --homedir`; fresh 0700 keyrings import each real public key without an agent socket; exactly one matching primary fingerprint/`VALIDSIG` is required. Prepare tests cover wrong SHA/non-main/red CI/branch Proof/snapshot drift/forbidden disposition/historical exception/local tag conflict/role mismatch, exact profiles, and zero remote mutation.

```python
def test_public_import_is_agentless(self) -> None:
    with tempfile.TemporaryDirectory(prefix="lmdj-gpg-") as directory:
        home = Path(directory); home.chmod(0o700)
        self.verifier.import_public_key(home, PRODUCT_KEY, PRODUCT_FINGERPRINT)
        self.assertFalse((home / "S.gpg-agent").exists())

def test_prepare_stops_at_local_plan(self) -> None:
    prepared = prepare("lmdj-v1.0.21.0", self.context())
    self.assertEqual(prepared.plan.target_revision, self.target_sha)
    self.assertEqual(len(prepared.plan.assets), 3)
    self.assertEqual(self.remote_mutations, [])
```

- [ ] **Step 2: Run RED**

Run `python3 tests/build/release_openpgp_test.py` and `python3 tests/build/release_prepare_test.py`.

Expected: missing-module failures.

- [ ] **Step 3: Implement command/OpenPGP layers and reuse them**

Public verification prefix is exact:

```python
["gpg", "--batch", "--no-tty", "--no-autostart", "--homedir", str(home)]
```

Parse status/colon output only. Detached signing uses local exact fingerprint and never passes a passphrase. Replace `release_bundle.py` inline verification with the shared verifier; update deploy Product-key import/verification to be no-autostart. Extend existing fake-GPG tests to fail if the flag or signature-before-checksum order disappears.

Implement the read-only portion of `GitHubClient` here so `prepare` can prove canonical main protection and exact-target successful CI without calling raw `gh` inside orchestration. Task 3 extends the same class with Release mutation methods.

- [ ] **Step 4: Implement Git target and profiles**

Freshly fetch canonical main/tag scratch refs, use detached clean worktrees, verify main ancestry/CI/snapshot, and create annotated policy-signed local tags. No push method is called here.

```python
PROFILE_BUILDERS = {
    "source-only": build_source_only,
    "core-package": build_core_package,
    "web-runtime-host": build_web_runtime_host,
}
```

`source-only` returns zero assets. Core invokes `scripts/core.sh package`, locates one ZIP/checksum, signs and reruns acceptance. Web invokes locked Host configure/build/test/proof, creates deterministic one-`dist/` ZIP/checksum/signature, and stages it through `release_bundle` using exact Product/Host identities. Reject symlinks, unsafe/duplicate members, extra files and noncanonical checksums.

- [ ] **Step 5: Implement prepare and wrapper**

`scripts/release.sh` only resolves repo root then execs `python3 "$repo_root/tools/release/cli.py" --repo-root "$repo_root" "$@"`. Add `scripts/release.sh prepare TAG`. Write notes/assets/final plan atomically below `build/release/`, using `urllib.parse.quote(tag, safe="")` as the single directory name; print digest and exact next `push-tag` command; stop. Exit `0` success/reconcile, `2` verification, `64` usage.

- [ ] **Step 6: Verify and commit**

```bash
python3 tests/build/release_openpgp_test.py
python3 tests/build/release_prepare_test.py
python3 apps/web-runtime-host/test/release_bundle_test.py
python3 apps/web-runtime-host/test/deploy_command_test.py --shards 4
bash -n scripts/release.sh scripts/web-runtime-deploy.sh
git add -- tools/release/commands.py tools/release/openpgp.py \
  tools/release/github_api.py \
  tools/release/git_repository.py tools/release/profiles.py \
  tools/release/prepare.py tools/release/cli.py scripts/release.sh \
  tests/build/release_openpgp_test.py tests/build/release_prepare_test.py \
  apps/web-runtime-host/tools/release_bundle.py \
  apps/web-runtime-host/test/release_bundle_test.py \
  scripts/web-runtime-deploy.sh apps/web-runtime-host/test/deploy_command_test.py \
  CMakeLists.txt
git diff --cached --check
git commit -m "feat(release): prepare signed release artifacts"
```

---

### Task 3: Exact tag push, Draft reconcile, and safe rehearsal helper

**Files:**
- Create: `tools/release/transitions.py`, `rehearsal.py`
- Modify: `tools/release/github_api.py`
- Create: `tests/build/release_transitions_test.py`, `release_rehearsal_test.py`
- Modify: `tools/release/cli.py`, `tools/release/git_repository.py`, `CMakeLists.txt`

**Interfaces:**
- Consumes: Task 2 verified tag/plan/assets.
- Produces: typed `GitHubRelease`/`GitHubAsset`; `push_tag()`, `create_draft()`, `verify_draft()`; guarded rehearsal subcommands.

- [ ] **Step 1: Write failing transition/rehearsal tests**

Cover one exact refspec/no `--tags`, fresh post-push fetch, identical reconcile, conflict rejection, Draft creation, zero/three assets, partial resume, extra/same-name-different-digest rejection, published read-only result, API uncertainty reconcile, numeric ID, download/rehash, marker validation, pagination cycles, and secret-safe errors.

Rehearsal tag syntax is exactly `^release-rehearsal/[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$`; it requires a test signer, Draft marker and exact ID/object cleanup, and rejects every formal tag and any published Release.

```python
def test_push_uses_one_refspec(self) -> None:
    transitions.push_tag("module/core-cli/v1.0.2", self.context)
    self.assertIn(["git", "push", "origin",
        "refs/tags/module/core-cli/v1.0.2:refs/tags/module/core-cli/v1.0.2"], self.commands)

def test_rehearsal_refuses_formal_tags(self) -> None:
    for tag in ("lmdj-v1.0.21.0", "module/core-cli/v1.0.3"):
        with self.assertRaises(RehearsalError):
            validate_rehearsal_tag(tag)
```

- [ ] **Step 2: Run RED**

Run both new test files; expect missing modules.

- [ ] **Step 3: Implement typed REST and exact transitions**

Use numeric REST IDs, validated response shapes, API-provided upload URL with one encoded name, octet-stream downloads, complete Link pagination with cycle/page-cap rejection. Never use `gh release upload --clobber` or edit a published Release.

`push-tag` verifies plan/intent/local tag, pushes one exact refspec, then always refetches/reconciles canonical tag object/signature/target/main ancestry. `create-draft` creates `draft=true`, writes one canonical `lmdj.release-plan-marker.v1` HTML comment, uploads only absent declared assets, redownloads/rehashes all, and reruns Product verifier. Existing matching published state returns read-only `already-published`.

`verify_draft` must not depend on the local ignored `build/release/` directory: reconstruct canonical plan fields from the protected-main ledger/policy, freshly fetched tag target, CI/snapshot evidence and downloaded Release assets, then compare its digest with both the marker and caller input. This is what makes it usable in a fresh Actions checkout.

CLI adds:

```text
scripts/release.sh push-tag TAG
scripts/release.sh create-draft TAG
scripts/release.sh verify-draft TAG RELEASE_ID PLAN_SHA256
```

- [ ] **Step 4: Implement guarded rehearsal commands**

Add `rehearsal prepare|push-tag|create-draft|cleanup`. Use ephemeral non-Product key and small deterministic asset. Cleanup requires exact Draft ID/tag object/marker, deletes Draft first, proves absence, deletes only exact rehearsal ref, then proves absence. It refuses formal/published/unknown state.

- [ ] **Step 5: Verify and commit**

```bash
python3 tests/build/release_transitions_test.py
python3 tests/build/release_rehearsal_test.py
python3 tests/build/release_prepare_test.py
bash -n scripts/release.sh
git add -- tools/release/github_api.py tools/release/transitions.py \
  tools/release/rehearsal.py tools/release/cli.py \
  tools/release/git_repository.py tests/build/release_transitions_test.py \
  tests/build/release_rehearsal_test.py CMakeLists.txt
git diff --cached --check
git commit -m "feat(release): reconcile tags and draft releases"
```

---

### Task 4: Protected Draft publication and manual-only Runtime deployment

**Files:**
- Create: `.github/workflows/publish-release.yml`
- Create: `tests/build/release_publish_workflow_test.py`
- Modify: `tools/release/transitions.py`, `tools/release/cli.py`
- Modify: `tests/build/release_transitions_test.py`
- Modify: `.github/workflows/deploy-web-runtime-host.yml`
- Modify: `tests/build/web_runtime_deploy_workflow_test.py`
- Modify: `.github/workflows/ci.yml`, `scripts/ci/local_lanes.json`
- Modify: `tests/build/ci_local_preflight_test.py`, `CMakeLists.txt`

**Interfaces:**
- Consumes: Task 3 `verify_draft()` and exact IDs/digest.
- Produces: `publish_draft()` and workflow inputs `tag`, `release_id`, `plan_sha256`.

- [ ] **Step 1: Write failing workflow/transition tests**

Assert publish workflow is only `workflow_dispatch`; exact three inputs; top-level `contents: read`; read-only preflight; publish job `contents: write` plus `environment: release`; protected-main checkout with `persist-credentials: false`; Draft verification in preflight and again immediately before publication; no Netlify/deploy/repository-dispatch strings. Update deployment test to require only explicit dispatch and unchanged `runtime-canary`.

```python
def test_deployment_requires_manual_exact_tag(self) -> None:
    triggers = self.mapping_block(self.workflow_source(), "on", 0)
    self.assertEqual(self.direct_mapping(triggers, 2), {"workflow_dispatch": ""})
    self.assertNotIn("release.published", self.workflow_source())
    self.assertIn("environment: runtime-canary", self.workflow_source())

def test_publish_changes_only_draft(self) -> None:
    result = publish_draft(self.tag, self.release_id, self.plan_sha, self.context)
    self.assertEqual(self.github.patch_calls, [(self.release_id, {"draft": False})])
    self.assertEqual(result.assets, self.original_assets)
```

- [ ] **Step 2: Run RED**

Run the new publish workflow test, transition test and deployment workflow test. Expect missing workflow/publish behavior and the still-present Release trigger.

- [ ] **Step 3: Implement publication**

Add `scripts/release.sh publish-draft TAG RELEASE_ID PLAN_SHA256`, restricted to `GITHUB_ACTIONS=true` and `GITHUB_EVENT_NAME=workflow_dispatch` except injected tests. It re-verifies Draft, PATCHes only `{"draft": false}`, rereads by ID/tag, re-downloads assets, and proves all metadata/IDs/digests are unchanged except Draft state. Ambiguous API results reconcile by numeric ID and never create a second Release.

- [ ] **Step 4: Create the protected workflow**

Required skeleton:

```yaml
name: Publish verified Draft Release
on:
  workflow_dispatch:
    inputs:
      tag: {description: Exact verified tag, required: true, type: string}
      release_id: {description: Numeric Draft Release ID, required: true, type: string}
      plan_sha256: {description: Exact plan SHA-256, required: true, type: string}
permissions:
  contents: read
jobs:
  preflight:
    permissions: {contents: read, actions: read}
  publish:
    needs: preflight
    environment: release
    permissions: {contents: write, actions: read}
```

Both jobs checkout `main`, full history, credentials disabled, with existing pinned action SHAs. Preflight calls `verify-draft`; publish calls it again and then calls `publish-draft`, whose postcondition performs the immediate published-state reread. Task 5 adds exact-tag audit after the audit command exists. Concurrency is per numeric Release ID, non-cancelling.

- [ ] **Step 5: Remove implicit deployment and wire CI/local tests**

Remove `.github/workflows/deploy-web-runtime-host.yml` `release` trigger and release-event selection branch; keep exact tag validation/Environment/secrets/deploy/recovery unchanged. Add the publish test to `deploy-contract` and matching local lane. Strengthen local preflight test to compare all release-test files between CI job and local commands.

- [ ] **Step 6: Verify and commit**

```bash
python3 tests/build/release_publish_workflow_test.py
python3 tests/build/release_transitions_test.py
python3 tests/build/web_runtime_deploy_workflow_test.py
python3 -m unittest tests.build.ci_local_preflight_test
python3 -m unittest discover -s tests/build -p 'ci_*_test.py'
bash -n scripts/release.sh scripts/web-runtime-deploy.sh
git add -- .github/workflows/publish-release.yml \
  tests/build/release_publish_workflow_test.py \
  tools/release/transitions.py tools/release/cli.py \
  tests/build/release_transitions_test.py \
  .github/workflows/deploy-web-runtime-host.yml \
  tests/build/web_runtime_deploy_workflow_test.py .github/workflows/ci.yml \
  scripts/ci/local_lanes.json tests/build/ci_local_preflight_test.py CMakeLists.txt
git diff --cached --check
git commit -m "feat(release): publish drafts through protected workflow"
```

---

### Task 5: Read-only audit and scheduled drift reporting

**Files:**
- Create: `tools/release/audit.py`
- Create: `tests/build/release_audit_test.py`
- Create: `.github/workflows/release-audit.yml`
- Create: `tests/build/release_audit_workflow_test.py`
- Modify: `tools/release/cli.py`
- Modify: `.github/workflows/publish-release.yml`
- Modify: `.github/workflows/ci.yml`, `scripts/ci/local_lanes.json`, `CMakeLists.txt`

**Interfaces:**
- Consumes: policy/ledger, active manifests/snapshots, Git/GitHub/profile projections.
- Produces: `AuditFinding`, `AuditReport`, `audit()` and `lmdj.release-audit.v1` JSON.

- [ ] **Step 1: Write failing audit/workflow tests**

Fixture every result: `ok`, `ok-with-historical-exception`, `missing`, `conflict`, `unauthorized`, `unverifiable`, `external-error`. Prove no mutation method is called; unknown formal remote state is unauthorized; pre-cutoff exact exceptions remain visible; post-cutoff unknown state fails; tag-only superseded entries are accepted; abandoned entries with tag/Release fail; asset/signature mismatch fails; pagination/network errors are external errors.

```python
def test_network_failure_is_external_error(self) -> None:
    self.github.error = TimeoutError("fixture")
    report = audit(self.context, remote=True)
    self.assertEqual({item.code for item in report.findings}, {"external-error"})

def test_abandoned_remote_tag_is_unauthorized(self) -> None:
    self.remote_tags.add("lmdj-v1.0.18.0")
    report = audit(self.context, remote=True, tag="lmdj-v1.0.18.0")
    self.assertEqual(report.findings[0].code, "unauthorized")
```

Workflow test requires `push` on main, weekly `schedule`, manual dispatch, `contents/actions: read`, push `--local`, schedule/dispatch `--remote`, always-upload JSON, and no write/deploy/secret.

- [ ] **Step 2: Run RED**

Run both new tests; expect missing files.

- [ ] **Step 3: Implement audit and CLI**

Add:

```text
scripts/release.sh audit --local [--tag TAG] [--json PATH]
scripts/release.sh audit --remote [--tag TAG] [--json PATH]
```

Local validates schemas, evidence paths, active identity, snapshot/provenance, intended target, disposition and policy trust anchors. Remote freshly fetches refs and paginates Releases/assets/runs; verifies protected-main ancestry, signature roles, exact metadata, downloaded bytes/checksum/profile. Local same-name tags are diagnostics only. Reports include observed UTC, repository, mode, findings, incomplete sources; JSON writes atomically and refuses symlink destinations. Only `ok`/`ok-with-historical-exception` exit 0, and human output always prints exceptions.

- [ ] **Step 4: Add release audit workflow**

Use weekly cron `0 3 * * 1`, main push and manual dispatch. Push runs local audit; schedule/dispatch remote audit. Upload `build/release/audit/report.json` with `if: always()`. Use pinned actions, credential persistence off, 15-minute timeout and non-cancelling concurrency.

- [ ] **Step 5: Wire publish/CI and verify**

Ensure publish workflow exact-tag audit resolves to this command. Add tests to deploy-contract/local lane and CTest.

```bash
python3 tests/build/release_audit_test.py
python3 tests/build/release_audit_workflow_test.py
python3 tests/build/release_publish_workflow_test.py
python3 -m unittest discover -s tests/build -p 'ci_*_test.py'
scripts/release.sh audit --local --json build/release/audit/local.json
git add -- tools/release/audit.py tests/build/release_audit_test.py \
  .github/workflows/release-audit.yml tests/build/release_audit_workflow_test.py \
  tools/release/cli.py .github/workflows/publish-release.yml \
  .github/workflows/ci.yml scripts/ci/local_lanes.json CMakeLists.txt
git diff --cached --check
git commit -m "feat(release): audit release identity and drift"
```

---

### Task 6: Project governance, Portal truth, and thin repo-local skill

**Files:**
- Create: `.agents/skills/lmdj-release/SKILL.md`
- Create: `tests/build/release_skill_test.py`
- Modify: `AGENTS.md`, `CLAUDE.md`
- Modify: `docs/governance/git-workflow.md`, `docs/governance/version-management.md`
- Modify: `.github/pull_request_template.md`
- Modify: `apps/architecture-portal/docs/operations/version-and-release.mdx`
- Modify: `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- Modify: `apps/architecture-portal/docs/hosts/web-runtime.mdx`
- Modify: `tests/build/web_runtime_public_deployment_docs_test.py`
- Modify: `tests/build/test_active_tree.sh`, `CMakeLists.txt`

**Interfaces:**
- Consumes: stable Task 1–5 commands.
- Produces: governing instructions, Release Impact declaration, implemented Portal truth, thin skill.

- [ ] **Step 1: Read required skill-authoring instructions**

Read the complete current `skill-creator/SKILL.md` and `superpowers:writing-skills/SKILL.md` before editing the skill; follow both. If advertised paths moved, locate them from current skill roots rather than using stale paths.

- [ ] **Step 2: Write failing skill/docs tests**

Assert the skill begins with remote read-only audit; names stable commands; pauses after one mutation; prints next authorization/unperformed states; contains no fingerprints, `endaye/lmdj`, asset names, private-key paths, `--clobber`, `git push --tags`, deploy command or cached state. Docs tests require Draft/publication/manual-deployment/history-exception wording on all three routes.

```python
def test_skill_is_navigation_not_policy(self) -> None:
    source = SKILL.read_text(encoding="utf-8")
    for command in ("audit", "prepare", "push-tag", "create-draft", "verify-draft"):
        self.assertIn(f"scripts/release.sh {command}", source)
    for forbidden in (PRODUCT_FINGERPRINT, CHECKSUM_FINGERPRINT,
                      "endaye/lmdj", "--clobber", "git push --tags",
                      "web-runtime-deploy.sh deploy"):
        self.assertNotIn(forbidden, source)
```

- [ ] **Step 3: Run RED**

Run release skill test, existing deployment docs test, and active-tree; expect missing governance/skill assertions.

- [ ] **Step 4: Update governance and synchronized instructions**

Add normal-path `scripts/release.sh`, each authority boundary, forbidden handwritten/one-step/clobber/all-tags flows, emergency incident requirements, and mandatory skill reference to `AGENTS.md`; copy byte-for-byte to `CLAUDE.md`. Git workflow adds Draft/publish states. Version policy adds ledger/profile/history exception/Draft/latest/published immutability rules.

PR template adds:

```markdown
## Release Impact
Release impact: none
Candidate tag: none
Profile: none
Channel: none
Intent disposition: none
Release assets: none
Release gates: none
Reason: <!-- Explain why release state changes or remains unchanged. -->
```

- [ ] **Step 5: Update Portal and create the thin skill**

Portal explains four stages, key boundary, audit, protected `release`, manual-only Runtime deployment, and that tooling does not mean `1.0.20.0` is released/deployed/promoted.

Skill flow: read policies/ledger/spec; run exact-tag remote audit; explain/confirm authorization; invoke at most one authorized mutation; rerun audit; report verified/next/unperformed state; print workflow inputs without approving Environment; keep deployment/Channel separate. It never duplicates policy values.

- [ ] **Step 6: Verify and commit**

```bash
python3 tests/build/release_skill_test.py
python3 tests/build/web_runtime_public_deployment_docs_test.py
bash tests/build/test_active_tree.sh
scripts/architecture-portal.sh check
git add -- .agents/skills/lmdj-release/SKILL.md tests/build/release_skill_test.py \
  AGENTS.md CLAUDE.md docs/governance/git-workflow.md \
  docs/governance/version-management.md .github/pull_request_template.md \
  apps/architecture-portal/docs/operations/version-and-release.mdx \
  apps/architecture-portal/docs/operations/testing-and-proof.mdx \
  apps/architecture-portal/docs/hosts/web-runtime.mdx \
  tests/build/web_runtime_public_deployment_docs_test.py \
  tests/build/test_active_tree.sh CMakeLists.txt
git diff --cached --check
git commit -m "docs(release): standardize release operations"
```

---

### Task 7: Branch-local full verification before remote transitions

**Files:**
- Modify only a declared focused set if a gate reveals a defect; each repair is a new Conventional Commit.

**Interfaces:**
- Consumes: committed Tasks 1–6.
- Produces: clean review evidence; no remote state and no verification-only commit.

- [ ] **Step 1: Run release/deployment contracts**

```bash
python3 -m unittest discover -s tests/build -p 'release_*_test.py'
python3 tests/build/web_runtime_deploy_workflow_test.py
python3 tests/build/web_runtime_public_deployment_docs_test.py
python3 apps/web-runtime-host/test/release_bundle_test.py
python3 apps/web-runtime-host/test/deploy_command_test.py --shards 4
```

- [ ] **Step 2: Run CI/active/version/Portal gates**

```bash
python3 -m unittest discover -s tests/build -p 'ci_*_test.py'
bash tests/build/test_active_tree.sh
scripts/local-ci.sh --list
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
bash scripts/verify-core-dependencies.sh
scripts/architecture-portal.sh check
```

- [ ] **Step 3: Inspect exact branch state**

```bash
git status --short --branch
git log --oneline --decorate origin/main..HEAD
git diff --check origin/main...HEAD
git diff --name-status origin/main...HEAD
```

Expected: clean; six implementation commits unless documented repair commits exist; no tracked build output, real tag, Release, deployment, or Channel mutation.

## Separately Authorized Remote Rollout

These boundaries are not authorized by plan approval. Stop/report after each.

### Boundary A: Push branch and create Draft PR

With explicit authorization, push only `feat/standard-release-pipeline`; create Draft PR; declare `ci:full`, selected lanes, Version none, three Documentation routes, Release impact none. Do not configure Environment or rehearse.

### Boundary B: Review, full CI, and merge

With separate Ready/merge authorization, require exact-head full PR Gate/all lanes, review permission summary, squash merge, verify main SHA/full push run. Merge does not authorize Environment or release operations.

### Boundary C: Configure protected `release` Environment

With repository-settings authorization, configure solo-maintainer mode: zero required reviewers, no prevent-self-review setting, and one exact `main` custom branch policy. Add no private signing/Netlify credential. Re-read API and retain secret-safe protection evidence. Do not dispatch.

### Boundary D: Safe Draft rehearsal and cleanup

With explicit rehearsal authorization:

```bash
tag="release-rehearsal/20260813-$(openssl rand -hex 6)"
scripts/release.sh rehearsal prepare "$tag"
scripts/release.sh rehearsal push-tag "$tag"
scripts/release.sh rehearsal create-draft "$tag"
```

Record numeric Draft ID/tag object. Verify formal publish workflow rejects the namespace without changing Draft. Run the exact cleanup command printed by create-draft; verify numeric Draft and remote tag absent; report deleted targets/recoverability and prove formal state unchanged.

### Boundary E: Full current remote audit

```bash
scripts/release.sh audit --remote --json build/release/audit/current.json
```

Expected: all formal tags/Releases match ledger; `v0.2.0`, legacy WIP and `1.0.15.2` CI appear only as explicit exceptions; abandoned identities have no remote state; no signature/asset mismatch; no deployment/Channel inference.

### Boundary F: Evidence-only follow-up Task

On a new `docs/release-rollout-evidence` isolated branch/worktree, record Environment projection, rehearsal IDs/cleanup, workflow rejection run, audit report digest, exact main SHA/CI run. Update Portal only if observed truth differs. Portal-check and commit `docs(release): record release pipeline rollout evidence`; its push/PR/merge remain separate authorizations.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

Version impact: none

Reason: These Tasks add operational schemas/tooling/tests/governance/current documentation/skill only. Product behavior, Assembly/lock, Module/Host API, Contract, Provider and Model identities and released bytes remain unchanged. The three `lmdj.release-*.v1` schemas are repository-internal operational records, not public Contracts. No Product Build, version bump, formal tag/Release, deployment or promotion is allocated.

If implementation changes a Product archive shape, Host distribution bytes, active manifest, Assembly/lock or public Contract beyond consuming existing package output, stop and create a separate version-impact design/plan.

## Documentation Impact

Documentation impact: required

Affected portal pages:

- `/operations/version-and-release/`
- `/operations/testing-and-proof/`
- `/hosts/web-runtime/`

Reason: Normal release procedure, Draft/publication authorization, audit evidence, CI ownership and Release-to-deployment triggering change. Task 6 updates all three current pages. No Product/Assembly change means no new immutable snapshot.

## Completion Checklist

- [ ] Six Task-scoped implementation commits pass all declared gates.
- [ ] No private signing material/token appears in Git, logs, assets, plans or evidence.
- [ ] Published Release cannot trigger deployment.
- [ ] `release` Environment is separately authorized/configured/verified.
- [ ] Test Draft rehearsal is authorized, rejected by formal publish, and cleaned.
- [ ] Remote audit explains every formal identity/historical exception with no unexplained finding.
- [ ] No formal tag/Release, deployment or Channel promotion occurs during implementation/rehearsal.
- [ ] Final report separately lists `implemented`, `committed`, `pushed`, `merged`, `environment-configured`, `rehearsed`, `release-audited`, `released`, `deployed`, `channel-promoted`.
