# GitHub Stacked PR 对 LMDJ 并行开发工作流的适用性研究

日期：2026-09-09
状态：研究建议；不是已批准的流程变更、实现计划或平台验收。
LMDJ 源码基线：`72de97e359b7e49ebde3af777831665ff9cf9f21`。
范围：多 agent、多设备、GitHub Issue 项目管理、PR review、增量 CI 与发版的衔接。

## 1. 结论

建议把 GitHub 原生 stacked PR 作为**存在代码依赖的 Task 的可选试点**，普通独立任务继续分别向 main 提交 PR。它最可能减少的是等待上游合并的时间；不会自动减少测试成本，也不能消除多人修改同一接口的冲突。

对 LMDJ 而言，接入前最重要的工作是适配 review 的 base 判断和可信控制代码来源，并定义跨设备级联 rebase 的单一协调责任。当前工具链不能仅通过安装扩展就视为兼容。

本报告的合并只保存研究结果，不启用 stack、不更改 Git/CI/release 规则、不批准试点实现，也不选择 CLI 版本。

## 2. 证据范围与限制

- **官方事实**：来自下方 GitHub 官方文档，检索日期为 2026-09-09。该功能处于 public preview；服务文档是可变页面，摘录用于保存当日判断依据，后续实施必须重新核对。
- **仓库事实**：以下相对源码链接均以页首 SHA 为研究基线。分支推进后的文件可能变化，应在该 SHA 下复核。
- **线上快照**：当日成功读取 main 的 branch protection：required check 列表为空、strict=false、required approving review count=0、conversation resolution 与 enforce_admins 均启用。这只证明该次 API 返回的配置，不是未来保护状态或全部 ruleset 的完整审计。
- **建议和推断**：适用性、职责分配和试点评估方法是本报告提出的方案，尚无 LMDJ 原生 stack 实测数据。
- 初次远端查询曾返回 404；使用已有仓库访问身份后读取成功。不能把该 404 当作仓库不存在或功能不可用的证据。本次没有创建 stack，也未验证本仓库的原生 stack 可用性。

## 3. 官方功能及其含义

原生 stack 把同仓库中的依赖 PR 组织成一条链：底层面向 main，上层面向下层分支，每层有自己的差异和审查范围。GitHub 提供依赖关系展示、级联 rebase 和按顺序合并；这比仅手工设置 PR base 增加了平台对整条链的识别。[S1]

示例中的每层都包含自身行为需要的测试，不把必要测试留到更高层：

```text
main
 └─ PR A：Application Facade 能力 + 测试
     └─ PR B：Creator 接入 + 测试
         └─ PR C：交互完善 + 测试
```

合并 A 后，其余分支会更新依赖关系。选择较高层合并会连带包含下方未合并的 PR，不能把中层孤立落地；支持 squash，但自动化合并需要核对专用异步接口，目前不支持 auto-merge。[S2]

面向 stack trunk 的 PR workflow 会对各层触发，因此多层可能放大 CI 次数；官方提供 stack 元数据以帮助选择执行位置。这只解决事件路由，不保证自定义脚本理解这些字段。[S3]

级联 rebase 会改写受影响分支并更新远端；`gh stack sync` 也包含 rebase 和 push，不是只读 fetch。多人和多设备需要协调写入。命令的具体 flags、签名和冲突处理应在试点时按选定版本核验。[S4][S5]

## 4. 对多 agent、多设备协作的收益

| 场景 | 收益判断 | 使用建议 |
| --- | --- | --- |
| 上层 Task 等待已基本稳定的底层接口合并 | 高 | 下层进入 review 后，上层可提前开发并单独 review |
| 一个功能可以拆成若干有依赖的可验证 Task | 高 | 每层一个 Task/PR，保持小差异和清晰责任 |
| 多 agent 修改互不依赖的模块 | 低 | 各自从 main 分支即可，避免人为引入依赖 |
| 多 agent 反复修改同一底层接口 | 不确定 | 先收敛接口；stack 不会解决设计冲突 |
| 同一分支由多台设备同时写入 | 增加协调成本 | 不因使用 stack 而允许多写入者 |
| 希望 CI 或发版自然提速 | 仅间接 | 必须测量验证次数和集成等待，不能预先承诺 |

stack 的并行收益来自开发和审查时间的重叠，依赖本身仍然存在。底层变更越频繁、链越长，越可能把节省的等待时间换成上层返工和重复审查。

建议每层记录一个写入负责人（agent 与设备），每个 stack 指定一个协调负责人，集中负责级联 rebase、拓扑调整、同步和合并。跨层更新前确认受影响设备已保存工作并停止推送；更新后记录各 PR 新 head，其他设备核对后继续。单写入责任是建议的协作规则，不是 GitHub 提供的跨设备锁。

保留独立 worktree。`gh stack` 的导航和批量操作是否能安全处理其他 worktree 已 checkout 的分支，需要实测；不能让工具切换或重置其他活跃会话的工作目录。

## 5. 与当前仓库的适配差距

### 5.1 分支与交付规则

[Git workflow](../governance/git-workflow.md) 当前要求 Task 从最新 origin/main 创建短分支，并向 main 提 PR；[issue-done](../../.agents/skills/issue-done/SKILL.md) 也使用固定 `--base main` 的交付路径。上层 stack 的 base 是下层分支，正式接入需要明确例外及操作流程。

每层仍应对应一个可审查 Task，声明自己的文件、最低层级验证和验收边界；保留 Conventional Commit 与逐 Task squash 的历史语义。若更改根 AGENTS.md，需按仓库规则同时更新字节一致的 CLAUDE.md。

### 5.2 Review 的直接兼容性问题

基线中以下路径明确依赖直接面向 main 的 PR：

- [pr_review_target.py](../../.github/scripts/pr_review_target.py)：`resolve_target` 的 base.ref 检查拒绝非 main 目标，后续目标校验也要求 main。
- [review_scope.py](../../scripts/ci/review_scope.py)：认证 review scope 时校验 base.ref 为 main。
- [pr-review.yml](../../.github/workflows/pr-review.yml)：使用 PR 的 base.sha checkout review 控制代码。
- [review_pipeline.py](../../scripts/ci/review_pipeline.py)：采集 base/head 差异，并验证 control_sha 的 main 来源。

因此，workflow 被平台触发不等于上层 PR 能得到有效 review。也不能仅删除 `base == main` 检查：这会留下可信来源与差异来源混用的问题。

建议明确两个不同基准：

1. **差异基准**：本层实际 base/head，供本层审查与变更范围计算。
2. **可信控制基准**：固定并验证来自受信任 main 的控制代码，不把尚未合并的下层 PR 当作可信执行来源。

认证还需绑定实际 stack trunk、层级关系、PR head/base 和最终合并 SHA；可变的标签或客户端自报 stack 元数据不能替代服务端验证。这里指出的是接入风险和适配方向，不是已证明的现有漏洞或完整安全设计。

### 5.3 Rebase 后的证据更新

[当前 Git 规则](../governance/git-workflow.md) 要求 head 改变后重新 review 当前变更。底层改动传播后，上层旧 head 的 review 不能直接作为新 head 的合并证据；实际受影响的 Task 验证也应重做。

跨设备同步时记录更新前后的 head，并重新核对 PR 状态、冲突和未解决讨论。按完整 SHA 和来源验证证据，避免一个设备仍向旧分支历史推送时另一设备合并。

stack 合并接口可能影响多个 PR。交付工具需显示并验证将合入的完整前缀，确认所有 Task 均已获授权，并具备处理并发 head 更新与异步结果回读的办法；不能只检查用户点选的顶层 PR。

### 5.4 CI 的适配与成本

当前 [增量批次设计](../design/2026-09-08-lmdj-ci-incremental-batches.md) 与 [Git workflow](../governance/git-workflow.md) 将 Task 验证、PR review 和 main 上的增量验证区分开来。建议沿用该分工，先验证原生 stack 与既有证据链兼容，再考虑减少重复执行。

- 每层保持足够证明该 Task 可独立落地的验证。
- 只测顶层不能证明底层单独合入后的状态正确；高层修复可能掩盖低层缺陷。
- 合入 main 后，增量控制器仍应覆盖完整未处理提交区间，保留既有验证债务。
- 试点核对每层 review scope 与 squash introducing SHA 的映射，检查批量合入是否造成漏记、重复或错误清债。
- PR 事件增加不能成为把昂贵全矩阵重新加回每层 merge gate 的理由。

这些是兼容性验收要求，不是本次已运行的 CI/stack 验收结果。

## 6. GitHub Issue 管理与发版衔接

Issue 管理目标、负责人、优先级、依赖和验收；stack 表达代码合入顺序。建议整体功能使用父 Issue，各 Task 关联自己的 Issue/PR，并记录依赖 PR、预期 base、负责人和验收状态。Issue 依赖可能分叉，不能强行全部转成一条 stack。

只在 Task 满足对应 Issue 全部验收时声明关闭；部分交付使用 `Relates to`。未直接面向默认分支的 PR，其 Issue 链接/关闭行为应在试点中回读确认。父 Issue 保留到整体验收完成，不能以整条 stack 已合并替代设备验收。

以下状态分别记录：Task 完成、PR review 完成、代码已进入 main、集成验证完成、物理验收完成、已发布/部署。

发版继续依据 [version-management](../governance/version-management.md) 与既有 release 流程，从明确选定的 main 历史候选建立精确版本证据，执行快照、tag、签名、发布、部署及 Channel 验证。stack 完成不自动分配 Product Build，不证明候选可发布，也不授权移动已冻结的候选身份。

## 7. 建议的最小试点与退出条件

建议选择一个 2–3 层、底层接口已基本稳定、没有开放 Contract 决策的真实功能链。独立 Task 继续普通 PR；试点需要另立实施 Task 并声明具体文件与验证，本研究不直接启用它。

建议的验收顺序与远端观察点：

1. 确认原生功能可用并固定 CLI 版本；在独立 worktree 建立依赖层，远端回读每层的 head/base 与 trunk。
2. 为上层触发 review；证明输入只含本层差异，控制代码来自可信 main，发布证据绑定当前 head。
3. 底层做一次实质修改并级联更新；证明上层拾取修改、旧证据不能冒充当前结果，另一设备可以保留本地工作并接续新 head。
4. 分别演练冲突中止/恢复和并发更新；证明未知或过期状态不会触发合并，不覆盖另一写入者的提交。
5. 从底层逐层 squash；每步确认真实 main 合入 SHA、下一层 base/head、Issue 状态和 review 映射。
6. 检查 main 增量批次对该区间的归属和保留债务；批次处理完成与健康结果分别记录。

先采用逐层合并，避免首轮同时引入整栈异步合并编排。需要批量合并时，再验证完整前缀授权、并发 head 保护和部分失败结果；不能用一次成功代替这些路径。

评估记录等待上游合并时间、Task 到 main 的耗时、重复 review 次数、级联冲突/返工次数和 CI 运行成本，与类似普通 PR Task 比较。没有实测前不设提速百分比。

如果改写分支频繁干扰其他设备，或现有 review/CI 证据无法可靠映射，则暂停扩大使用，逐层处理既有工作并回到普通 PR。不能把 `unstack` 当作自动恢复 main base 或自动回滚代码；退出时回读每层实际 base，保留未合并工作。[S4]

## Version Management

Version impact: none

仅新增研究文档，不修改 Product Build、Module、Host、Provider、Contract 或 Assembly 的版本身份。

## Documentation Impact

Documentation impact: none

研究未改变已批准的产品行为、架构门户页面或现行操作流程；未来若采纳建议，需要在实施 Task 中重新评估治理文档、技能和门户影响。本文件没有自动化运行时消费者。

## 8. 来源

以下均检索于 **2026-09-09**。链接是移动服务文档，短摘录保存当日依据，不构成版本选择或未来兼容承诺。

- **[S1]** [About stacked pull requests](https://docs.github.com/en/pull-requests/get-started/about-stacked-prs)。摘录：“This feature is in public preview and subject to change.”
- **[S2]** [Merging stacked pull requests](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/merging-stacked-pull-requests)。摘录：“Auto-merge is not supported for stacked pull requests.” “you'll need use the asynchronous merge API for stacks.”
- **[S3]** [Optimizing CI for stacked pull requests](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/optimizing-ci-for-stacked-pull-requests)。摘录：“GitHub Actions workflows trigger as if each pull request in the stack targets the base of the stack.”
- **[S4]** [Managing stacked pull requests](https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/managing-stacked-pull-requests)。摘录：“Each keeps its current base branch but is no longer linked to the others”.
- **[S5]** [Stacked pull requests CLI commands](https://docs.github.com/en/pull-requests/reference/stacked-prs-cli-commands)。`gh stack sync` 摘录：“Fetch, rebase, push, and sync pull request state in a single command.”
