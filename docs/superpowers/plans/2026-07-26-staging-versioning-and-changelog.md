# Staging Versioning and Changelog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After a verified staging activation, automatically assign or reuse one unified SemVer product Tag, publish an idempotent GitHub Release, and attach an identical per-version Markdown Changelog.

**Architecture:** A Python standard-library generator owns SemVer discovery, Conventional Commit classification, rollback guards, and deterministic Markdown rendering. A small Bash controller owns remote Tag and GitHub Release reconciliation. The existing deployment Workflow stages both controllers from current `main`, verifies the server revision, then invokes them after activation.

**Tech Stack:** Python 3.11 standard library, Bash, Git, GitHub CLI, GitHub Actions YAML, temporary Git repositories for tests.

## Global Constraints

- Product Tags strictly match `v<major>.<minor>.<patch>` with no prerelease suffix.
- The first newly deployed current `origin/main` SHA receives `v0.2.0`.
- Breaking changes bump major, `feat` bumps minor, and every other non-empty forward range bumps patch.
- Web, API, Audio Worker, and shared package versions remain independent internal metadata and are not modified.
- A Tag is created only after staging activation and exact `DEPLOYED_REVISION` verification.
- Existing Tags, Releases, bodies, and assets are never overwritten, moved, deleted, or force-pushed.
- Rollbacks reuse an existing version; an untagged old SHA never receives a new version.
- GitHub Release body and `CHANGELOG-vX.Y.Z.md` use one Markdown source.
- `main` remains PR-only; the deployment Workflow never commits generated files back to the repository.
- The current user turn produces one verified atomic commit, so implementation tasks do not make intermediate commits.

---

### Task 1: Version and Changelog generator

**Files:**
- Create: `scripts/release/release_version.py`
- Create: `scripts/release/tests/test_release_version.py`

**Interfaces:**
- Consumes: local Git history, `--target-sha`, `--repository`, `--run-url`, `--deployed-at`, `--output-dir`, optional `--github-output`
- Produces: `ReleasePlan(tag: str, previous_tag: str | None, existing: bool, target_sha: str, commits: tuple[Commit, ...])`, `CHANGELOG-<tag>.md`, and GitHub outputs `tag`, `previous_tag`, `existing`, `notes_file`

- [ ] **Step 1: Write failing Git-history tests**

Create temporary repositories with helpers equivalent to:

```python
def commit(repo: Path, subject: str, body: str = "") -> str:
    subprocess.run(["git", "-C", repo, "commit", "--allow-empty", "-m", subject,
                    *(["-m", body] if body else [])], check=True)
    return git(repo, "rev-parse", "HEAD")
```

Cover:

```python
def test_first_current_main_release_is_v020(): ...
def test_first_explicit_old_sha_is_rejected(): ...
def test_fix_and_nonconventional_commits_bump_patch(): ...
def test_feat_bumps_minor(): ...
def test_breaking_footer_and_bang_bump_major(): ...
def test_highest_change_wins(): ...
def test_existing_single_tag_is_reused(): ...
def test_multiple_tags_on_target_are_rejected(): ...
def test_latest_tag_must_be_target_ancestor(): ...
def test_markdown_categories_links_and_breaking_marker(): ...
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
python3 -m unittest scripts/release/tests/test_release_version.py -v
```

Expected: import or file-not-found failure for `scripts/release/release_version.py`.

- [ ] **Step 3: Implement SemVer and commit parsing**

Implement focused types and functions:

```python
@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

@dataclass(frozen=True)
class Commit:
    sha: str
    subject: str
    body: str
    kind: str | None
    scope: str | None
    description: str
    breaking: bool
    pull_request: int | None

@dataclass(frozen=True)
class ReleasePlan:
    tag: str
    previous_tag: str | None
    existing: bool
    target_sha: str
    commits: tuple[Commit, ...]

def parse_version_tag(tag: str) -> Version | None: ...
def parse_commit(sha: str, subject: str, body: str) -> Commit: ...
def plan_release(repo: Path, target_sha: str) -> ReleasePlan: ...
def render_notes(plan: ReleasePlan, repository: str, run_url: str,
                 deployed_at: str) -> str: ...
```

Select the numerically highest valid product Tag. For a new version, require it to be an ancestor of the target. For an existing target Tag, find the numerically previous Tag for the Changelog range.

- [ ] **Step 4: Implement the CLI output contract**

The CLI validates full lowercase SHAs and UTC ISO 8601 timestamps, writes:

```text
<output-dir>/CHANGELOG-vX.Y.Z.md
```

When `--github-output` is supplied, append only single-line safe values:

```text
tag=vX.Y.Z
previous_tag=vX.Y.W
existing=false
notes_file=/absolute/path/CHANGELOG-vX.Y.Z.md
```

- [ ] **Step 5: Run generator tests and verify GREEN**

Run:

```bash
python3 -m unittest scripts/release/tests/test_release_version.py -v
```

Expected: all generator tests pass.

### Task 2: Idempotent GitHub publisher

**Files:**
- Create: `scripts/release/publish-staging-release.sh`
- Create: `scripts/release/tests/test-publish-staging-release.sh`
- Create: `scripts/release/tests/test-release-versioning.sh`

**Interfaces:**
- Consumes: positional `TARGET_SHA TAG NOTES_FILE`; environment `GITHUB_REPOSITORY`, `GITHUB_SERVER_URL`, `GITHUB_RUN_ID`, `GH_TOKEN`
- Produces: one immutable remote annotated Tag, one GitHub Release, one `CHANGELOG-<tag>.md` asset; no output repository mutations

- [ ] **Step 1: Write failing publisher tests with fake `gh` and a bare Git remote**

Exercise these cases:

```text
new target -> tag push, release create, release upload
existing matching tag -> no new tag
existing tag on another SHA -> fail
tag only -> create release and asset
release only missing asset -> read body and upload it
release and matching asset -> compare and succeed
release and mismatched asset -> fail without overwrite
```

The fake `gh` records arguments and stores Release body/assets under a temporary directory so the test can compare bytes.

- [ ] **Step 2: Run publisher tests and verify RED**

Run:

```bash
bash scripts/release/tests/test-publish-staging-release.sh
```

Expected: failure because `publish-staging-release.sh` does not exist.

- [ ] **Step 3: Implement immutable Tag reconciliation**

Validate inputs and use:

```bash
git fetch origin "refs/tags/$TAG:refs/tags/$TAG"
git rev-parse "$TAG^{commit}"
git tag -a "$TAG" "$TARGET_SHA" -m "Staging deployment $TAG

Workflow: $GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"
git push origin "refs/tags/$TAG"
```

An absent remote Tag is created. A present Tag must peel to `TARGET_SHA`; otherwise fail. Never use `--force`.

- [ ] **Step 4: Implement Release and asset reconciliation**

Use `gh release view/create/upload/download`:

```bash
gh release create "$TAG" --repo "$GITHUB_REPOSITORY" --verify-tag \
  --title "$TAG" --notes-file "$NOTES_FILE"
gh release upload "$TAG" "$NOTES_FILE" --repo "$GITHUB_REPOSITORY"
```

If the Release exists, replace the local notes file with its body before adding a missing asset. If an asset exists, download it and `cmp` it against the Release body; mismatch is an error.

- [ ] **Step 5: Add and run the aggregate release test**

`test-release-versioning.sh` runs:

```bash
python3 -m unittest scripts/release/tests/test_release_version.py -v
bash scripts/release/tests/test-publish-staging-release.sh
```

Expected: both suites pass.

### Task 3: Staging Workflow and CI integration

**Files:**
- Modify: `.github/workflows/deploy-server.yml`
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/deploy/tests/test-deploy-workflow.sh`

**Interfaces:**
- Consumes: existing resolved target SHA, SSH deployment configuration, GitHub token and run context
- Produces: post-activation revision proof followed by release generator/publisher execution

- [ ] **Step 1: Extend the static Workflow test first**

Add assertions for:

```text
job permissions include actions: read and contents: write
current main stages release_version.py and publish-staging-release.sh before target checkout
Verify staging revision appears after Activate staging release
Prepare staging release appears after revision verification
Publish staging release appears after preparation
release commands use RUNNER_TEMP controller copies
no force push, git commit, or direct main push appears
```

- [ ] **Step 2: Run the static test and verify RED**

Run:

```bash
bash scripts/deploy/tests/test-deploy-workflow.sh
```

Expected: failure reporting missing release controller staging or missing revision verification.

- [ ] **Step 3: Stage current-main release controllers**

Before `git checkout --detach "$target"`, extract:

```bash
git show origin/main:scripts/release/release_version.py \
  > "$RUNNER_TEMP/release_version.py"
git show origin/main:scripts/release/publish-staging-release.sh \
  > "$RUNNER_TEMP/publish-staging-release.sh"
chmod +x "$RUNNER_TEMP/release_version.py" \
  "$RUNNER_TEMP/publish-staging-release.sh"
```

This preserves rollback support when the target predates the release scripts.

- [ ] **Step 4: Add revision verification and release steps**

After activation:

```bash
remote_revision="$(ssh "$DEPLOY_USER@$DEPLOY_HOST" \
  "cat '$DEPLOY_PATH/DEPLOYED_REVISION'")"
test "$remote_revision" = "$TARGET_SHA"
```

Then fetch Tags, invoke the Python generator with `GITHUB_OUTPUT`, and invoke the Bash publisher with `GH_TOKEN`.

- [ ] **Step 5: Add release tests to CI**

In `deploy-config`, run:

```yaml
- run: bash scripts/release/tests/test-release-versioning.sh
```

before the existing deploy script tests.

- [ ] **Step 6: Run Workflow and release tests**

Run:

```bash
bash scripts/release/tests/test-release-versioning.sh
bash scripts/deploy/tests/test-deploy-workflow.sh
```

Expected: all pass.

### Task 4: Operations documentation and design status

**Files:**
- Modify: `docs/deploy/staging.md`
- Modify: `docs/superpowers/specs/2026-07-26-staging-versioning-and-changelog-design.md`

**Interfaces:**
- Consumes: implemented behavior from Tasks 1–3
- Produces: operator instructions for first release, forward deploy, rerun, metadata recovery, and rollback

- [ ] **Step 1: Update the staging runbook**

Document:

```text
first successful current-main deployment creates v0.2.0
Conventional Commit bump table
where to find the GitHub Release and Markdown asset
same-SHA reruns are idempotent
tagged rollback reuses the version
untagged old rollback activates but reports release metadata failure
how to rerun the same SHA after Tag/Release/asset partial failure
```

- [ ] **Step 2: Mark the design implemented**

Change the spec status from `待书面评审` to `已实现`, and add exact implementation paths without changing confirmed product decisions.

- [ ] **Step 3: Run documentation and diff checks**

Run:

```bash
git diff --check
rg -n "TBD|TODO|待定|待补" \
  docs/deploy/staging.md \
  docs/superpowers/specs/2026-07-26-staging-versioning-and-changelog-design.md
```

Expected: `git diff --check` succeeds and the placeholder scan returns no matches.

### Task 5: Completion audit and atomic commit

**Files:**
- Verify all files listed in Tasks 1–4

**Interfaces:**
- Consumes: the confirmed design and all implementation/test artifacts
- Produces: evidence that every explicit design requirement is implemented and one task-local Conventional Commit

- [ ] **Step 1: Run release and deployment suites**

```bash
bash scripts/release/tests/test-release-versioning.sh
bash scripts/deploy/tests/test-deploy-workflow.sh
bash scripts/deploy/tests/test-package-release.sh
bash scripts/deploy/tests/test-activate-release.sh
```

Expected: all pass with zero failures.

- [ ] **Step 2: Run syntax and repository checks**

```bash
python3 -m py_compile scripts/release/release_version.py
bash -n scripts/release/publish-staging-release.sh
bash -n scripts/release/tests/test-publish-staging-release.sh
bash -n scripts/release/tests/test-release-versioning.sh
git diff --check
```

Expected: all commands exit zero.

- [ ] **Step 3: Audit requirements against current files**

Re-read the confirmed spec and map every goal, invariant, failure case, test, and non-goal to direct code, Workflow, test, or documentation evidence. Treat any missing or indirect evidence as incomplete and fix it before committing.

- [ ] **Step 4: Stage only current-turn files and inspect**

```bash
git add \
  .github/workflows/ci.yml \
  .github/workflows/deploy-server.yml \
  docs/deploy/staging.md \
  docs/superpowers/plans/2026-07-26-staging-versioning-and-changelog.md \
  docs/superpowers/specs/2026-07-26-staging-versioning-and-changelog-design.md \
  scripts/deploy/tests/test-deploy-workflow.sh \
  scripts/release
git diff --cached --check
git diff --cached --name-status
```

Expected: only the listed release automation, Workflow, tests, plan, spec, and runbook files are staged.

- [ ] **Step 5: Create the atomic implementation commit**

```bash
git commit -m "feat(release): automate staging versions"
git show --stat --oneline HEAD
git show --format= --name-status HEAD
git status --short --branch
```

Expected: one Conventional Commit containing only this implementation scope and a clean worktree.
