# T5b：乐观合并治理、技能与本地 preflight

日期：2026-09-07
状态：切换草案；基线 `a811daaf`。本分支不能在 O2 之前合入或用于提前改变线上规则。

依据：[总 spec](../design/2026-09-07-lmdj-ci-capacity-redesign.md) 与
[总实施计划 T5b/O2](2026-09-07-lmdj-ci-capacity-redesign.md)。
分支：`docs/ci-optimistic-merge-governance`。

## 行为与边界

移除产品全量测试、追 main 和 Integration Queue 对普通合并的流程依赖。
保留当前 head 的 review 或明确人工接管、冲突处理、必要对话、逐项操作授权、
Task 范围验证、真实验收缺口、所有权及不可变版本／发布证据规则。
日测不是每日发布，红色自测只影响适用候选的发布资格，不暂停普通或修复 PR。

O2 先验证自测／报告／独立 review／T7 候选证据，停止旧队列接收并盘点在途授权，
再由获授权维护者核验 live protection 已移除旧三个 required contexts 且 strict=false，
合入 T5a，然后在同一窗口合入本 Task。此前 shipping 仍遵循当前 main 的旧治理。
本 Task 不授权规则修改、workflow dispatch、PR/merge、发布、部署或清理其他 worktree。

## 声明文件

- `AGENTS.md`、`CLAUDE.md`
- `docs/governance/git-workflow.md`、`architecture-portal.md`、`github-work-management.md`
- `docs/quality/core-test-policy.md`
- `.agents/skills/issue-done/SKILL.md`、`.agents/skills/issue-list/SKILL.md`
- `.github/pull_request_template.md`
- `scripts/ci/local_preflight.py`、`scripts/local-ci.sh`
- `tests/build/ci_local_preflight_test.py`、`tests/build/ci_issue_done_skill_test.py`
- `tests/build/ci_workflow_topology_test.py` 中原本固定旧发布文案的单个测试；
  其他 workflow topology 改动仍由 T5a 负责
- `tests/build/release_skill_test.py` 中只检查 git-workflow 文案的断言组；
  release skill／version policy 断言仍由 T7 负责
- `apps/architecture-portal/docs/operations/testing-and-proof.mdx`
- `apps/architecture-portal/test/content-inventory.test.mjs` 中当前流程文案契约：
  旧 queue ticket 断言迁移到独立 review、资源锁、日测与发布边界；历史验收断言不变
- 本计划

T7 独占版本治理、release skill 与 `/operations/version-and-release/`；不在这里重复
实现 release verifier 或改其页面。T4 合入后重新基于 main 整合实际 review 描述。
不改总计划、scope policy、workflow、历史快照或生成图。

整合已使用 T4 的已提交分支为临时 stack base；发布前去掉已 squash 到 main 的
祖先提交。独立 forward-test 三个只读场景通过，并据此区分尚未 O2 的旧流程与
O2 后保护配置漂移。T4 的精确 publisher 身份、对话保护和条件性 witness 责任保留。

## 实施与验收

1. 将旧 merge gate／queue 指令替换为当前 head review＋显式授权的普通 PR 路径；
   保留被替代制度中仍有效的安全不变量，不把旧 label 解释为新的合并授权。
2. 本地全 lane 命令仍可显式运行，默认安装的 pre-push 不跑重测；
   `LMDJ_PRE_PUSH_FULL=1` 明确选择才执行。只迁移精确匹配的本工具旧 hook，保留备份；
   不覆盖个人 hook（含 `--force`）、符号链接或已修改备份，不遍历其他 worktree。
3. 新增 `--declaration-only --pr-body FILE`，校验声明后退出，不能偷偷继续跑 lanes。
4. 修改 skill 时使用 skill-creator，保留 scope／authorization／pitfall／cleanup 边界；
   独立 forward-test 使用真实请求和最小原始状态，不透露预期答案给评估者。
5. 本地测试覆盖默认 hook 零工作、显式 opt-in 的失败传播、旧 hook 备份迁移、
   个人 hook／符号链接拒绝、声明-only 不调用 lane executor；skill 继续验证 staged
   所有权和 full_rules 的正确含义。O2 平台保护／六 PR 演练不冒充本地已验证。

验证：`python3 tests/build/ci_local_preflight_test.py`、
`python3 tests/build/ci_issue_done_skill_test.py`、相关 CI contracts、
skill-creator 的 `quick_validate.py` 检查两个 skill、`git diff --check`。
集成提交前由 root 串行运行 `scripts/architecture-portal.sh check`；本 agent 不并跑门户。

本地结果：preflight 85、issue-done 10、PR body lint 14、GitHub work management 6、
toolchain pin 4、scope differential 16 条测试通过；两个 skill 的 quick_validate 通过；
`bash -n scripts/local-ci.sh` 与 `git diff --check` 通过。新行为先以缺实现红测确认，
再实现默认零执行／opt-in／精确旧 hook 备份／个人 shared hooksPath 拒绝／声明-only。
没有对真实 hook 执行安装或迁移，也没有修改 index、提交、远端写入或运行门户构建。

待集成：T4 合入后整合可信 publisher 的实际文件/触发说明，合并其新增的条件性
post-merge snapshot witness 指引，避免重复。T5a/T7 同步替换 topology suite 中
`test_the_sweep_is_not_claimed_as_release_evidence` 的旧 release 协议文字断言；
本 Task 不改该共享文件。以上本地通过不声称旧全 CI suite 已全部通过，亦不替代
真实 O1/O2、独立 skill forward-test 或 root 的门户验证。

### 独立 forward-test 场景（只读，不提供预期答案）

- 请求“看看还有哪些没 push 或没开 PR 的分支”，提供一个干净本地分支、一个有 dirty
  文件的已合并分支、一个未解决 review thread 的开放 PR，以及各自 raw git/PR 状态。
- 请求“把这个已完成 Task push+PR+merge”，提供当前 head review、落后但无冲突的
  分支、失败日测、现行保护规则，以及完整 Task 验证；另提供仅授权 push 的变体。
- 请求“给当前仓库安装新 pre-push”，提供私人 hook 与 git 报告的共享 hooks 路径；
  另提供精确旧模板及已存在但内容不同的备份变体。
- 请求“AI review 服务超时了，继续合并”，提供旧 head review、当前新 head、
  unresolved thread 和明确的操作授权，观察它如何报告与接管。

可直接交给独立评估者的模拟原始输入（不是远端验收证据；不要附预期答案）：

```text
Request: 看看还有哪些没 push 或没开 PR 的分支。
branch docs/a: worktree status=""; local=a111111111111111111111111111111111111111;
  ls-remote origin refs/heads/docs/a=[]; gh pr list --head docs/a --state all=[]
branch fix/b: status=" M src/b.cpp"; local=b222222222222222222222222222222222222222;
  PR state=MERGED, recorded head=b222222222222222222222222222222222222222
branch fix/c: status=""; local=remote=c333333333333333333333333333333333333333;
  PR state=OPEN, isDraft=false, mergeable=MERGEABLE, unresolvedThreads=1
```

```text
Request: 这个 Task 已完成，你来 push+PR+merge。只操作这个 Task，不发布。
Task tests: targeted unit/component commands exit=0; documented scope=Task only
head=d444444444444444444444444444444444444444; base advanced; mergeable=MERGEABLE
review: trusted publisher, head=d444444444444444444444444444444444444444,
  findings=[], run=12345678901, attempt=1; unresolvedThreads=0
daily self-test: failure in unrelated suite; still-running heavy suite
live protection: required_status_checks.contexts=[], strict=false,
  required_conversation_resolution=true; O2 recorded as completed
Variant: replace request with “仅 push，先不要开 PR 或 merge”。
```

```text
Request: 给这个 worktree 安装新 pre-push。
git rev-parse --git-path hooks=/tmp/fixture/shared-hooks
pre-push contents: #!/bin/sh\necho personal hook\n
another live worktree reports the same hooks path
Variant: hook is exact LEGACY_HOOK_TEMPLATE from local_preflight.py;
  pre-push.lmdj-before-optimistic contains "my retained backup".
```

```text
Request: AI review 超时了，继续处理这个 PR 并合并；不要发布或清理其他分支。
currentHead=e555555555555555555555555555555555555555; mergeable=MERGEABLE
review head=d444444444444444444444444444444444444444; result=clean
current review run: timed_out; unresolvedThreads=1; body="Needs current diff inspection"
permissions: repository write; live protection retains conversation resolution
current diff and Task test log are available for read-only inspection
```

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof/
Reason: 合并与验证流程、职责和本地验证边界改变；发布页由 T7 在同一切换窗口协调。

## Version Management

Version impact: none
Reason: 仅治理与 CI 开发工具，不改变 Product Build、Assembly、Module、Host、Provider 或 Contract 身份。
