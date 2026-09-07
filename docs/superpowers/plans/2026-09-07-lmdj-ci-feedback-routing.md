# CI feedback 路由前置任务

日期：2026-09-07
基线：`22247897e9163a3f34e15f564bec133419d1f177`（T2 合入后的 main）。

## 结果与拆分边界

按 issue-done 的“先登记路由，后加入新文件”规则，将 T3/T4 的新路径登记单独交付。
`scope_policy.json` 属于现有合并控制面；若与 reporter/review 实现捆绑，整个 PR 都
不能走 Integration Queue。先加入尚不存在路径的精确规则不改变任何既有文件分类，
之后 T3/T4 可独立验证、交付，无需各自再携带同一个控制面文件。

只提取以下源提交的新增规则并取精确并集，不复制实现或修改既有规则：

- T3：`267f5b863fe6550b8e95aad1c1e1a201b88b4fb7`。
- T4：`c38a8f8fae5f08fc1c2aea5f928ffdb8b7360ab9`。

三个 exact 路径均归属 `ci_contract`：`.github/workflows/self-test-report.yml`、
`.github/workflows/pr-review.yml`、`.github/scripts/pr_review_target.py`。
不启用新 workflow，不修改 required checks、strict、队列、日测或发布授权。
T3/T4 的端到端验收仍由原任务承担，本任务的路由验证不代表功能已上线。

## 文件与本地提交

分支：`feat/ci-feedback-routing`。
Conventional Commit：`feat(ci): register independent feedback workflow routes`。
仅声明两个文件：

- `scripts/ci/scope_policy.json`。
- `docs/superpowers/plans/2026-09-07-lmdj-ci-feedback-routing.md`（本文）。

## 验证

1. 对照两笔源提交各自的 parent，证明当前新增规则恰为三个规则的并集；其余 policy
   数据完整相等。对基线全部 tracked paths 调用
   `policy_edit_is_classification_preserving`，必须返回既有分类未改变。
2. `python3 tests/build/ci_change_scope_test.py`（含 stage 后的新文件 ownership 检查）。
3. `python3 tests/build/ci_scope_policy_differential_test.py`。
4. `python3 tests/build/ci_scope_policy_consumer_parity_test.py`。
5. `python3 tests/build/ci_classification_inputs_test.py`。
6. `scripts/architecture-portal.sh check`，以及 staged diff 与 whitespace 检查。
7. 本地 commit 后运行 `scripts/local-ci.sh --base-ref origin/main --list --json`，
   核对最终完整范围。此任务预期 focused：`docs_static`、`ci_contract`；最终以分类器
   输出为准，不用声明覆盖实际结果。

没有 workflow YAML、action 或 shell 变更，pinned actionlint 无新增检查对象。
本 Task 只本地 commit；push、PR 和 merge 留给主 agent 的已授权 shipping 流程。

## Documentation Impact

Documentation impact: none
Reason: 仅提前登记尚不存在的路径及本任务计划，不改变现行测试、审查或发布行为，
无需修改 Architecture Portal 页面或图示。

Pitfall impact: none — 遵循既有 control-plane 拆分和 staged ownership 指引，
未出现新的流程事故或新的复发事实。

## Version Management

Version impact: none
Reason: 仅 CI 路由元数据与计划，不改变 Product Build、Module、Provider、Host 或 Contract。
