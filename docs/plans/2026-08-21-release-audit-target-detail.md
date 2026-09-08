# Release Audit Exact-Target Failure Detail Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让每个 release audit exact-target `unverifiable` finding 在 human 与 JSON 输出中保留具体、安全、有界的失败规则。

**Architecture:** 保持现有 validator、Git repository adapter、`AuditFinding` schema 和 finding taxonomy 不变，只在 `tools/release/audit.py::_audit_remote_intent()` 这个唯一丢失 detail 的边界捕获异常对象并复用 `_sanitized_reason()`。用现有无网络 fake Git/GitHub audit context 完成 TDD，证明 detail threading、sanitization、human output 和 JSON projection。

**Tech Stack:** Python 3 standard library、`unittest`、LMDJ `tools.release` audit/command infrastructure、Bash repository verification scripts。

## Global Constraints

- Implementation 只有一个 reviewable Task 和一个 Conventional Commit。
- 未来 implementation branch 使用 `fix/release-audit-target-detail`，并在从届时最新 `origin/main` 创建的独立 worktree 中执行；不得继续使用当前 docs design branch 实现代码。
- Declared implementation files 只能是 `tools/release/audit.py` 与 `tests/build/release_audit_test.py`。
- 不修改 `target_validation.py`、`commands.py`、`git_repository.py`、`cli.py`、`scripts/release.sh`、release intent ledger、historical exception、Portal page 或 report schema。
- 保持 finding `code == "unverifiable"`、exact intent subject、`sources == ("exact-target",)`、排序、exit semantics 与 `lmdj.release-audit.v1` JSON shape 不变。
- 任意异常文本必须通过现有 `_sanitized_reason(root: Path, exception: BaseException) -> str`；禁止直接拼接 raw exception output。
- Sanitization 必须继续清理 URL user information、Basic/Bearer/token values、token-shaped literals、environment 或 sensitive flag assignments 和绝对路径，并使用现有 `_REASON_LIMIT = 480` 保持有界 head/tail。
- 不改变 broad catch 的现有分类；本 Task 只增加诊断 detail，不把错误改为 `external-error`、`conflict` 或其他 code。
- 不新增 machine-readable error code，不扩展 `AuditFinding`，不改变 formatter 或 JSON writer。
- 不运行任何 `scripts/release.sh audit --remote --tag TAG` 或其他 remote audit。
- 不调用 `prepare`、`push-tag`、`create-draft`、publication workflow、Runtime deployment 或 Channel promotion。
- 不创建、移动、编辑或删除任何 local/remote tag、Draft、published Release、GitHub Issue 或 release evidence。
- 不把 Issue #165 的历史 audit evidence 表述为当前 canonical remote state。
- Local commit 不授权 push、Pull Request、merge、tag、Release、deployment 或 Channel mutation。

---

### Task 1: Preserve sanitized exact-target failure detail in release audit

**Files:**

- Modify: `tools/release/audit.py:430-468`
- Test: `tests/build/release_audit_test.py:22,388-397`

**Interfaces:**

- Consumes: `_sanitized_reason(root: Path, exception: BaseException) -> str` from `tools.release.audit`; it delegates to `sanitize_diagnostic(exception, root=root, limit=_REASON_LIMIT)` with `_REASON_LIMIT == 480` and prefixes the concrete exception type.
- Consumes: `ReadOnlyGit.target_validation_error: Exception | None` and its no-network `detached_worktree()` fixture from `tests/build/release_audit_test.py`.
- Preserves: `_audit_remote_intent(context: object, intent: ReleaseIntent, tag_state: _ObservedTag | None, release: GitHubRelease | None, exception: HistoricalException | None, latest_release_id: int | None) -> AuditFinding`.
- Produces: the existing `AuditFinding.message` prefix plus one parenthesized sanitized reason; no new function, class, field, schema, or public interface.

- [ ] **Step 1: Confirm the isolated implementation baseline and declared scope**

Run:

```bash
git fetch --prune origin
git branch --show-current
git status --short --branch
git rev-parse HEAD origin/main
```

Expected:

- current branch is exactly `fix/release-audit-target-detail`, never `main` or the docs design branch；
- worktree is clean before test edits；
- the branch was created from the then-current `origin/main`；
- no release audit or release mutation command is run。

- [ ] **Step 2: Write the RED tests for detail propagation and sanitization**

In `tests/build/release_audit_test.py`, extend the audit import exactly as follows:

```python
from tools.release.audit import AuditContext, audit, format_report, write_report  # noqa: E402
```

Replace `test_remote_audit_requires_kind_specific_exact_target_validation` and add the adjacent sanitizer test with this code:

```python
    def test_remote_audit_requires_kind_specific_exact_target_validation(self) -> None:
        tag = str(self.entry()["tag"])
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag)
        self.git.target_validation_error = RuntimeError("module manifest mismatch")

        report = audit(self.context(), remote=True, tag=tag)

        finding = next(item for item in report.findings if item.subject == tag)
        self.assertEqual(finding.code, "unverifiable")
        self.assertEqual(finding.subject, tag)
        self.assertEqual(finding.sources, ("exact-target",))
        self.assertIn("exact release target", finding.message)
        self.assertIn("RuntimeError: module manifest mismatch", finding.message)
        self.assertIn("module manifest mismatch", format_report(report))
        self.assertIn("module manifest mismatch", json.dumps(report.to_document(), sort_keys=True))

    def test_remote_exact_target_detail_is_sanitized_and_bounded(self) -> None:
        tag = str(self.entry()["tag"])
        self.git.tags[tag] = self.tag_state()
        self.github.releases[tag] = self.release(tag)
        secret = "ghs_fixturesecret000111222333"
        self.git.target_validation_error = RuntimeError(
            "target rule failed "
            f"GITHUB_TOKEN={secret} "
            f"https://token:{secret}@github.com/endaye/lmdj "
            "at /home/runner/work/lmdj/lmdj "
            + ("middle " * 200)
            + "final exact-target rule"
        )

        report = audit(self.context(), remote=True, tag=tag)

        finding = next(item for item in report.findings if item.subject == tag)
        prefix = "exact release target identity or support metadata is invalid"
        self.assertEqual(finding.code, "unverifiable")
        self.assertEqual(finding.sources, ("exact-target",))
        self.assertTrue(finding.message.startswith(f"{prefix} (RuntimeError: target rule failed"))
        self.assertIn("GITHUB_TOKEN=[redacted]", finding.message)
        self.assertIn("<path>", finding.message)
        self.assertIn("final exact-target rule", finding.message)
        self.assertNotIn(secret, finding.message)
        self.assertNotIn("/home/runner", finding.message)
        self.assertLessEqual(
            len(finding.message),
            len(prefix) + 3 + len("RuntimeError: ") + audit_module._REASON_LIMIT,
        )
```

The first test proves all three output surfaces use the same preserved message. The second test deliberately supplies an arbitrary exception rather than a pre-sanitized `CommandError`, proving the audit boundary itself is safe.

- [ ] **Step 3: Run the two tests and prove RED for the intended reason**

Run:

```bash
python3 -m unittest \
  tests.build.release_audit_test.ReleaseAuditTest.test_remote_audit_requires_kind_specific_exact_target_validation \
  tests.build.release_audit_test.ReleaseAuditTest.test_remote_exact_target_detail_is_sanitized_and_bounded \
  -v
```

Expected: non-zero exit with assertion failures because the current fixed message does not contain `RuntimeError: module manifest mismatch`, `GITHUB_TOKEN=[redacted]`, `<path>`, or the final rule. The failure must not be an import error, syntax error, network call, fixture setup error, or unrelated assertion.

- [ ] **Step 4: Implement the minimal GREEN change at the detail-loss boundary**

In `tools/release/audit.py::_audit_remote_intent()`, replace only the current exact-target `try/except` block with:

```python
    diagnostic_root = Path(context.repo_root)
    try:
        with context.git.detached_worktree(intent.target_revision) as worktree:
            diagnostic_root = Path(worktree)
            context.git.validate_release_target(diagnostic_root, intent)
    except Exception as error:
        reason = _sanitized_reason(diagnostic_root, error)
        return AuditFinding(
            "unverifiable", intent.tag,
            f"exact release target identity or support metadata is invalid ({reason})",
            ("exact-target",),
        )
```

This keeps the authority root as a safe fallback when worktree entry fails, switches to the exact target root after entry, and runs every captured exception through the shared bounded sanitizer. Do not create a helper or alter any other error boundary.

- [ ] **Step 5: Run the two focused tests and prove GREEN**

Run:

```bash
python3 -m unittest \
  tests.build.release_audit_test.ReleaseAuditTest.test_remote_audit_requires_kind_specific_exact_target_validation \
  tests.build.release_audit_test.ReleaseAuditTest.test_remote_exact_target_detail_is_sanitized_and_bounded \
  -v
```

Expected: both named tests report `ok`; final result is `Ran 2 tests` and `OK`.

- [ ] **Step 6: Run the release audit unit module**

Run:

```bash
python3 -m unittest tests.build.release_audit_test -v
```

Expected: every `ReleaseAuditTest` reports `ok` and the final result is `OK`; no test contacts the canonical GitHub remote or records a mutation in `ReadOnlyGit.mutations` or `ReadOnlyGitHub.mutations`.

- [ ] **Step 7: Run the complete release tooling regression suite**

Run:

```bash
python3 -m unittest discover -s tests/build -p 'release_*_test.py'
```

Expected: exit code 0 and final result `OK`. Existing prepare/transition behavior, report schema, workflow contracts, OpenPGP verification, API projections, CI evidence and rehearsal fixtures remain unchanged.

- [ ] **Step 8: Verify local release authority without any exact-tag remote audit**

Run:

```bash
scripts/release.sh audit --local
```

Expected: exit code 0 with only successful local authority findings. The command performs no fresh remote tag/Release/API projection and no mutation. Do not replace it with `audit --remote` or add `--tag`.

- [ ] **Step 9: Run repository identity and active-tree gates**

Run:

```bash
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
```

Expected: both commands exit 0. The Product Build, Assembly Lock, active source boundaries and version identities remain unchanged.

- [ ] **Step 10: Run the Architecture Portal gate**

Run:

```bash
scripts/architecture-portal.sh check
```

Expected: exit code 0; Portal tests, docs validation, diagram validation, facts generation, release-doc verification, typecheck, production build and built-route checks all pass. If a fresh worktree lacks Portal dependencies, run `scripts/architecture-portal.sh install` once and rerun the exact check; ignored dependency installation must not add tracked files.

- [ ] **Step 11: Inspect and stage only the declared implementation files**

Run:

```bash
git status --short
git diff -- tools/release/audit.py tests/build/release_audit_test.py
git add -- tools/release/audit.py tests/build/release_audit_test.py
git diff --cached --name-status
git diff --cached --check
git diff --cached -- tools/release/audit.py tests/build/release_audit_test.py
```

Expected staged file list exactly:

```text
M tools/release/audit.py
M tests/build/release_audit_test.py
```

`git diff --cached --check` exits 0. The complete staged diff contains only the two test methods, one import addition, and the minimal exact-target exception block. If any plan, spec, ledger, Portal page, generated file or unrelated user change is staged, stop and remove it from this commit without discarding the owner's work.

- [ ] **Step 12: Create the single atomic implementation commit**

Run:

```bash
git commit -m "fix(release): surface exact-target audit detail"
```

Expected: one new Conventional Commit containing exactly the two declared files. This local commit does not authorize push, PR, merge, remote audit or release mutation.

- [ ] **Step 13: Verify the committed file list and clean final worktree**

Run:

```bash
git show --format=fuller --stat --name-status --oneline HEAD
git diff-tree --no-commit-id --name-status -r HEAD
git status --short --branch
```

Expected:

```text
M tools/release/audit.py
M tests/build/release_audit_test.py
```

The worktree is clean, the implementation branch is ahead by one Task commit, and no push, PR, merge, tag, Release, deployment or Channel transition has occurred.

## Version Management

Version impact: none

Reason: 该 Task 只把已有 release audit failure detail 通过共享 sanitizer 送入既有 message，不改变 Product behavior、Product Assembly、Assembly Lock、Module/Host API、Contract、Provider、Model identity、Release asset 或已发布产品字节。`lmdj.release-audit.v1` shape、finding taxonomy、code、sources、排序和 exit semantics 均不变。

- Version domains affected: none；Product、Module、Contract、Provider 与 Model 均无 bump。
- Starting/target versions: none；不分配或修改任何版本。
- Product Build/Channel: none；不分配 Product Build，不改变 Channel。
- Manifest/schema files: none；不修改 `version.json`、`module.json`、Contract schema、Provider manifest、Assembly 或 Assembly Lock。
- Compatibility/migration: none；Project、Contract、report JSON consumers 与 release state machine 均无需迁移。
- Tag name/target/message: none；本 Task 不创建、签名、push、移动或删除 tag。
- Version gate: release unit suite、local authority audit、active-tree、version test 与 Portal check 必须通过后才能提交。
- Publication authority: none；commit 不授权 push、PR、merge、Release、deployment 或 Channel promotion。
- Rollback: revert the single implementation commit；所有现有 Product/Module/Contract/Provider identity 与已发布 remote state 保持原样。

## Documentation Impact

Documentation impact: none

Reason: 该 Task 只改变内部 failure diagnostic text，不改变 Architecture Portal 的 current product、architecture、release state、deployment boundary、测试层级或操作 policy。设计与计划已在 repository docs 中单独记录；implementation commit 不修改 Portal route 或 immutable snapshot。

## Release Authority Boundary

Release impact: none

- 本计划的执行只允许本地代码、测试、local audit 与 local commit。
- 禁止运行任何 exact-tag remote audit，包括全部 7 个 Issue #165 historical Product intents。
- 禁止修改 `docs/release-evidence/release-intents.json`、historical exception 或 GitHub Release metadata。
- 禁止调用 `prepare`、`push-tag`、`create-draft`、publish workflow、Runtime deployment 或 Channel promotion。
- 禁止编辑 GitHub Issue、tag、Draft、published Release、asset 或 deployment state。
- Unit fixture 中的 `remote=True` 只选择 fake in-memory remote audit path；它不使用 `GitRepository`/`GitHubClient` canonical network projection，也不构成 remote audit evidence。
- 完成 implementation 与 local commit 只建立 `implemented`/`committed` 状态，不建立 `pushed`、`merged`、`release-audited`、`released`、`deployed` 或 `channel-promoted` 状态。
