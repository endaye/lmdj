# Release Audit Exact-Target Failure Detail Design

日期：2026-08-21

状态：设计已批准

关联 Issue：#165

## 1. 结论

第一阶段只修复 `scripts/release.sh audit --remote` 的 per-intent exact-target
诊断输出。现有 validator 已经生成具体失败规则，错误字符串也已安全穿过 command、target
validation 和 Git repository 三层；detail 只在 `audit.py::_audit_remote_intent()` 的最后一个
异常边界被固定句覆盖。

实施应只修改：

- `tools/release/audit.py`；
- `tests/build/release_audit_test.py`。

`_audit_remote_intent()` 捕获异常对象后，使用现有 `_sanitized_reason()` 生成受限、安全的原因，
再追加到当前固定 finding message。Finding code、subject、sources、排序、exit code 与
`lmdj.release-audit.v1` JSON 形状保持不变。

本设计不运行任何 exact-tag remote audit，不修改 release intent ledger，不创建或修改 tag、
Draft、published GitHub Release、deployment 或 Channel，也不授权任何发布 mutation。

## 2. 背景与精确范围

Issue #165 记录的 2026-08-16 audit evidence 包含 7 个 Product intent 的相同 finding：

```text
[unverifiable] TAG: exact release target identity or support metadata is invalid
```

对应 exact tags 与当前 tracked ledger disposition 为：

| Tag | Ledger disposition |
| --- | --- |
| `lmdj-v1.0.13.0` | `published` |
| `lmdj-v1.0.14.0` | `published` |
| `lmdj-v1.0.15.2` | `published` |
| `lmdj-v1.0.16.5` | `published` |
| `lmdj-v1.0.16.8` | `published` |
| `lmdj-v1.0.16.9` | `published` |
| `lmdj-v1.0.21.0` | `allocated` |

这张表只描述 tracked ledger，不声称重新验证了当前 GitHub remote state。尤其
`lmdj-v1.0.15.2` 的 `pre-pipeline-ci-evidence` historical exception 只解释控制面生效前的
CI evidence；它不应掩盖或绕过 exact-target validation。

Issue 同时列出的 11 个 Module Release name conflict 不属于本阶段。是否存在 ledger、Release
metadata 或 validator drift，必须等具体失败规则可见后再独立判断，不能在本 Task 中猜测或修复。

## 3. 根因

### 3.1 正常数据流

当前 exact-target failure detail 的产生和传递顺序为：

```text
scripts/release.sh
  -> tools/release/cli.py::main
  -> tools/release/audit.py::audit
  -> tools/release/audit.py::_remote_report
  -> tools/release/audit.py::_audit_remote_intent
  -> GitRepository.detached_worktree(target_revision)
  -> GitRepository.validate_release_target(worktree, intent)
  -> target_validation.validate_release_target(...)
  -> kind-specific validator / supporting command
```

底层已经能够区分失败规则：

- `target_validation.py` 对 Product manifest/Assembly lock、Portal snapshot lock 和 Portal
  provenance 等规则抛出不同的 `TargetValidationError` 文本；
- `CommandRunner` 把失败命令的 `stderr or stdout` 先经 `sanitize_diagnostic()` 清理并限制长度，
  再放入 `CommandError.detail`；
- `target_validation._with_detail()` 把该安全 detail 追加到对应规则；
- `GitRepository.validate_release_target()` 通过 `GitRepositoryError(str(error))` 保留文本。

### 3.2 丢失点

`audit.py::_audit_remote_intent()` 当前使用未绑定异常对象的 broad catch：

```python
except Exception:
    return AuditFinding(
        "unverifiable",
        intent.tag,
        "exact release target identity or support metadata is invalid",
        ("exact-target",),
    )
```

因此，进入这一边界前仍然存在的具体规则被替换成固定句。后续
`AuditFinding.to_document()`、`format_report()` 和 JSON writer 都会完整保留 finding message，
所以它们不是 detail 丢失点。

现有 `test_remote_audit_requires_kind_specific_exact_target_validation` 只断言固定 message 中含有
`exact release target`，没有断言 fixture 的 `module manifest mismatch` 仍在输出中。因此测试会在
detail 被丢弃时继续通过。

### 3.3 根因假设的本地证明

使用现有 fake Git/GitHub audit context，在 validator 抛出
`RuntimeError("module manifest mismatch")` 时，当前 finding 仍只有固定句，sources 则保持
`("exact-target",)`。这证明错误不是 validator 未生成 detail，而是 audit boundary 未保留它。

## 4. 目标与非目标

### 4.1 目标

- 每个 exact-target `unverifiable` finding 在 human summary 和 JSON 中保留具体失败规则；
- 任意进入 audit boundary 的异常都必须经过共享 sanitizer，不能直接进入输出；
- 保持闭合 finding code、sources、report schema、排序和 exit semantics 不变；
- 用无网络 unit fixture 证明 detail threading 和 secret-safe projection；
- 让后续独立的只读审计能够区分 records drift 与 tooling drift。

### 4.2 非目标

- 不判断 7 个 intent 当前分别触发哪一条规则；
- 不运行任何 exact-tag remote audit；
- 不修改 `target_validation.py` 中的 validation 规则或通过条件；
- 不修改 `commands.py`、`git_repository.py`、`cli.py` 或 `scripts/release.sh`；
- 不修改 ledger disposition、historical exception 或 evidence path；
- 不处理 11 个 Module Release name conflict；
- 不改变 `prepare`、`push-tag`、`create-draft` 或 publish workflow 的错误文案；
- 不创建、移动或删除 tag，不编辑 Draft/published Release，不部署或提升 Channel；
- 不新增 machine-readable error code，不扩展 `lmdj.release-audit.v1`。

## 5. 方案比较

### 5.1 方案 A：在现有 audit boundary 追加安全 detail（推荐）

捕获 `_audit_remote_intent()` 的异常对象，使用现有 `_sanitized_reason()`，把结果追加到当前固定
message。

优点：

- 修复准确位于 detail 的唯一丢失点；
- 只修改一个 runtime 文件和一个 test 文件；
- 复用 #149/#150 已验证的 sanitization 和 bounded diagnostic 模式；
- finding taxonomy 与 JSON contract 不变；
- 不扩大到 release transition 或 validator 重构。

代价：

- 输出仍是 human-readable reason，不提供稳定的 machine rule code；
- broad catch 仍保持现有分类，只增加可诊断性。

### 5.2 方案 B：抽取共享 target-validation finding helper

新增 helper，统一 detached worktree、validation、sanitization 和 finding 构造，并考虑让 local
active projection 与 per-intent remote audit 共用。

优点是边界更集中；缺点是改变更多控制流，并会把已经工作的 local static projection 纳入重构。
第一阶段没有证据表明该重构是必要的，因此不采用。

### 5.3 方案 C：结构化 `TargetValidationError` rule code

为每条规则分配稳定 code，跨 `TargetValidationError`、`GitRepositoryError` 和 `AuditFinding`
传递，必要时扩展 JSON report。

优点是机器处理最强；缺点是需要重新设计 error/schema contract、修改更多调用者和测试，并可能
产生 governance 与 documentation impact。Issue #165 第一阶段只要求显示已有具体规则，因此不采用。

## 6. 推荐设计

### 6.1 Runtime change

在 `tools/release/audit.py::_audit_remote_intent()` 中：

1. 在进入 detached worktree 前把 diagnostic root 初始化为 canonical authority root；
2. 成功进入 worktree 后把 diagnostic root 更新为 exact target worktree；
3. 将 `except Exception` 改为 `except Exception as error`；
4. 调用 `_sanitized_reason(diagnostic_root, error)`；
5. 把安全 reason 以括号追加到固定 message。

预期 message 形状为：

```text
exact release target identity or support metadata is invalid
(GitRepositoryError: Product Portal snapshot provenance is invalid: <sanitized command rule>)
```

实现可以在同一字符串中输出，换行只用于本设计展示。以下字段保持不变：

```text
code = unverifiable
subject = exact intent tag
sources = (exact-target)
```

如果 detached worktree 在进入前失败，diagnostic root 使用 authority root fallback；如果已经进入，
使用 exact worktree root。共享 sanitizer 还会清理其他绝对路径，因此两种路径都不能泄露本机目录。

### 6.2 Sanitization 与 error handling

禁止直接拼接 raw exception output。`_sanitized_reason()` 必须继续委托
`sanitize_diagnostic()`，并继承当前规则：

- collapse whitespace；
- 把 repo root 变为 `<repo>`；
- 清理 URL user information；
- 清理 Basic/Bearer/token values；
- 清理 token-shaped literals；
- 清理 environment 或 sensitive flag assignments；
- 清理绝对路径；
- 保留有界文本的 head 与 tail，使 rule prefix 与最终 fatal reason 都可见；
- 保留异常类型，区分 `GitRepositoryError`、`RuntimeError` 等来源。

底层 `CommandError.detail` 已经被 sanitize；audit boundary 再执行一次 sanitizer 是 defense in
depth，并允许安全处理 fake、unexpected 或未来新增的 exception 类型。重复 sanitization 必须保持
既有 `<repo>`、`<path>` 和 `[redacted]` marker 可读。

本阶段不改变异常分类。既有 broad catch 捕获的错误仍报告 `unverifiable`，不会在此 Task 中改为
`external-error`、`conflict` 或其他 code。

### 6.3 Output contract

Human summary 和 JSON report 使用同一 `AuditFinding.message`。实施不得在 formatter 或 writer
中复制、重新 sanitize 或截断 reason。这样 unit test 可在 `audit()` 返回的 finding、
`format_report()` 和 `report.to_document()` 三个观察面验证同一 detail。

不新增 JSON 字段，不改变 `_REPORT_SCHEMA`，现有消费者无需迁移。

## 7. TDD 设计

### 7.1 RED

先在 `tests/build/release_audit_test.py` 修改或补充无网络 fixture：

1. 让 `ReadOnlyGit.target_validation_error` 抛出唯一规则
   `module manifest mismatch`；
2. 断言 finding 保持 `code == "unverifiable"`、subject 与
   `sources == ("exact-target",)`；
3. 断言 finding message 同时包含固定上下文和 `module manifest mismatch`；
4. 断言 `format_report(report)` 与 `report.to_document()` 都包含该规则。

当前实现会在第 3 步失败，因此该测试构成有效 RED。

再加入安全性 fixture，异常文本同时包含 fixture token、credential assignment、绝对路径和足够长的
前后文。断言：

- 具体失败规则仍可见；
- fixture secret 与绝对路径不可见；
- `[redacted]` 或 `<path>` marker 可见；
- 输出长度受现有 bound 限制；
- finding code 与 sources 未变化。

### 7.2 GREEN

只实现第 6 节的异常捕获与 `_sanitized_reason()` 调用，使 RED 通过。不得同时重构 validator、
transition 或 report model。

### 7.3 Regression verification

实现 Task 的最小验证集合为：

```bash
python3 -m unittest tests.build.release_audit_test
python3 -m unittest discover -s tests/build -p 'release_*_test.py'
scripts/release.sh audit --local
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
scripts/architecture-portal.sh check
```

`scripts/release.sh audit --local` 只验证 tracked/local authority，不是 exact-tag remote audit。上述命令
均不授权或执行 tag、Release、deployment 或 Channel mutation。

## 8. Files and commit boundary

未来 implementation Task 的 declared files 只有：

```text
tools/release/audit.py
tests/build/release_audit_test.py
```

两者组成一个 reviewable Conventional Commit。不得把 spec、ledger、Portal 页面或其他顺手重构混入
implementation commit。实现开始前仍须从届时最新 `origin/main` 创建新的 `fix/...` 隔离 worktree；
当前设计分支不作为实现分支继续使用。

## 9. Version Management

Version impact: none

Reason: 本设计及其推荐实现只改变 release audit failure diagnostic text，不改变 Product behavior、
Product Assembly、Assembly Lock、Module/Host API、Contract、Provider、Model identity、Release
asset 或已发布产品字节。`lmdj.release-audit.v1` 的 shape 与 finding taxonomy 均不变。

本设计不分配 Product Build，不创建 Product tag，也不创建 Architecture Portal immutable snapshot。

## 10. Documentation Impact

Documentation impact: none

Reason: 本 Task 新增的是已批准实现方案的 repository design record；推荐实现不改变 Architecture
Portal 的 current product、architecture、release state、deployment boundary 或操作 policy，因此
不需要修改 Portal route。失败输出仍遵守现行 read-only audit policy。

## 11. Release Impact and authority boundaries

Release impact: none

本设计和推荐实现不改变任何 release identity、intent、tag object、Release metadata、asset、
publication、deployment 或 Channel state。明确边界如下：

- 不运行 `scripts/release.sh audit --remote --tag TAG`；
- 不调用 `prepare`、`push-tag`、`create-draft` 或 publication workflow；
- 不编辑 GitHub Issue、tag、Draft 或 published Release；
- 不修改 `docs/release-evidence/release-intents.json`；
- 不把 Issue 中的历史 audit evidence 表述为当前 canonical remote state；
- 不根据新 detail 自动创建 historical exception 或远端修复。

代码合入后，若用户另行授权一个 exact-tag read-only audit，才能观察某个 intent 的当前具体规则。
该 audit 仍不授权任何 mutation。对于 `published`、`allocated`、`unverifiable` 或 `conflict` 状态，
下一发布 mutation 均不由本设计产生授权。

## 12. Acceptance criteria

设计对应的未来实现只有在以下条件全部满足后，才可报告为 implemented：

- 失败 fixture 先证明当前代码丢失唯一规则；
- exact-target finding 在 human 和 JSON 输出中保留安全、具体、有界的失败规则；
- secret、credential assignment 和绝对路径不进入报告；
- finding code、sources、schema、排序和 exit semantics 不变；
- release audit unit suite 与完整 release test suite 通过；
- local authority audit、active-tree、version 与 Architecture Portal checks 通过；
- implementation commit 只包含两个 declared files；
- 没有运行 exact-tag remote audit；
- 没有发生 tag、Release、deployment 或 Channel mutation。

本 design commit 只证明规格已记录并本地验证；它不代表 implementation、push、PR、merge、
release audit、Release、deployment 或 Channel promotion 已完成。
