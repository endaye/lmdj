# LMDJ CI Capacity Redesign

> 2026-09-08 更新：本文保留为上一阶段的历史设计与容量证据。Owner 已取消
> “每日自动全量”，后续以 [主干增量批次自测 spec](2026-09-08-lmdj-ci-incremental-batches.md)
> 为准。本文的“当前”“待实施”和授权范围均属于当时记录，不代表新的线上状态。
> 新设计合入不等于触发器已切换；须按新版实施计划验证后切换。

日期：2026-09-07

状态：Owner 已确认“乐观合并、每日自测、手动发布”的方向；本文据此修订。
本次授权范围是 spec 更新与本地提交。实际 workflow、分支保护、自动 issue 报告、
runner 和队列迁移由后续实施与 rollout 完成，现行规则在切换前继续有效。

## 1. 设计结论与明确取舍

LMDJ 采用乐观集成：PR 以 AI review 为主要审查方式，产品全量测试不作为 PR merge
前置条件。每天及重要节点对固定的 main SHA 做全量自测；失败产生修复 issue，
普通 PR 继续合入。只有全量验证通过的精确候选可以进入手动发布流程。

**每日自测不是每日发布。测试通过不会自动创建 tag、发布版本、部署或晋级 Channel。**
Owner 决定是否发布、发布哪个已验证版本，以及何时执行发布。

这一选择改变了 main 的产品含义：main 是持续集成分支，允许暂时存在运行缺陷；
“可交付版本”由通过全量验证的精确候选标识。不能继续同时承诺“每个 main 提交
都已完整验证且可部署”。实施时必须同步修改 AGENTS.md 和现行治理中的对应表述。

本设计接受组合缺陷在合并后暴露，也接受某天无法产生新的可发布候选；保留代码审查、
问题追踪和发布验证，换取 PR 不再反复 update main、重跑 Core CI 和等待全仓库串行队列。

默认策略：

- 关闭要求 PR 随 main 前进而重验的 strict，退役自研 Integration Queue。
- 产品构建、单元／契约／集成／浏览器测试、sanitizer、coverage 和 package 验证
  全部从 merge required checks 移到独立自测流程。
- PR 可保留轻量 lint／typecheck 反馈，但默认非阻塞，不借其名称保留完整 Core CI。
- 日测和重要节点自测固定一个 SHA 运行到结论；新 PR 合入不取消该自测。
- 自测失败记录 issue，不自动暂停普通合并，也不自动 revert。
- 发布由 Owner 手动选择并触发，只消费完整、有效且匹配候选的验证证据。

## 2. 已核实证据与限制

### 2.1 PR #737 的完整运行

[Core CI run 34062231152](https://github.com/endaye/lmdj/actions/runs/34062231152)
于 2026-09-06T21:49:57Z 创建，PR Gate 于 2026-09-07T02:35:12Z 完成，
端到端约 285.3 分钟。以下以 job API 的时间戳计算，单位为分钟：

| job | 等待：started_at − created_at | 执行：completed_at − started_at |
| --- | ---: | ---: |
| creator-web（前置关键路径） | 22.2 | 23.2 |
| Architecture Portal / portal | 33.6 | 1.4 |
| core (ubuntu-latest) | 51.2 | 1.4 |
| Core package | 62.2 | 4.5 |
| core-coverage | 44.0 | 5.7 |
| core-asan | 28.2 | 6.4 |
| 后五个串行 job 合计 | 219.2 | 19.4 |

等待包含 concurrency admission、runner 可用性及平台调度，不能把每一分钟全部归因于锁。
前置阶段到 Pre-heavy Gate 完成另需约 46.4 分钟；消除后五项等待并不等于整个 PR
能在 20 分钟内完成。Core Ubuntu 实际运行 `scripts/core.sh proof`，并非只有
unit＋component 的 `fast` tier；1.4 分钟是这次 job 的执行时间，不是冷构建承诺。

这是拥堵期间一个 PR 的完整样本，证明排队放大确实发生，不代表仓库日常 p50／p90。
此前 13 个成功 heavy job 的抽样均值和 45 个失败 run 的分布缺少完整样本清单、
实际执行分母与缺陷去重，本修订不使用它们决定扩容或检查后移。测量须遵循
[突发负载与基线区分](../../../.agents/pitfalls/burst-sample-taken-as-baseline.md)。

### 2.2 重复 Main 工作与两层串行

2026-09-07 评审读取的 `ci.yml` 按 SHA 为 main run 分组，并不取消旧 main run。
以下 push 在后续 main 提交已存在时仍继续验证自己的历史 SHA：

| run | head SHA 前缀 | created_at → 终态 updated_at（UTC） |
| --- | --- | --- |
| [34059271071](https://github.com/endaye/lmdj/actions/runs/34059271071) | 8b62b4e9 | 09-06 20:51:22 → 09-07 02:07:16 |
| [34059327353](https://github.com/endaye/lmdj/actions/runs/34059327353) | e7d223e8 | 09-06 20:52:30 → 09-07 02:24:54 |
| [34059777525](https://github.com/endaye/lmdj/actions/runs/34059777525) | 063ab993 | 09-06 21:01:42 → 09-07 02:49:30 |
| [34069290849](https://github.com/endaye/lmdj/actions/runs/34069290849) | c4ff1fcd | 09-07 00:16:34 → 09-07 03:31:52 |

后续 main 提交 `ea0b8781` 对应 run
[34069446070](https://github.com/endaye/lmdj/actions/runs/34069446070)。

当前系统不是“单线程 CI”：Integration Queue 一次处理一个 PR；另外，
`lmdj-native-heavy` 在仓库级串行处理 Portal、Core Ubuntu、Package、Coverage、
ASan 及相关 Nightly／benchmark 工作。其他 job 和编译内部仍可并行。

根据 [GitHub concurrency 文档](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)，
`queue: max` 最多保留 100 个 pending，超出后取消新增工作，不是无界队列。
它按进入 concurrency 等待的顺序处理，不保证 workflow 创建顺序；链上每一环重新入队，
会放大单个 PR 的完成延迟。扩大 pending 上限不能增加吞吐。

### 2.3 实际主机与保护规则

评审时的远端状态：

- main 的 required checks 是 `core (ubuntu-latest)`、`core (macos-latest)`、
  `PR Gate`，`strict: true`，并要求 conversation resolution。
- Contabo 承接 `ci-general`；Netcup 同时承接 `ci-general`、`ci-core`、
  `ci-web-heavy`；macOS 在独立 Mac runner 上执行。
- 上述 PR 的 Portal 实际运行于 `netcup-lmdj-linux-08`，与 Native／Web 共用物理主机。
  `ci-general` 角色不保证 Portal 离开争用机器。
- 多个 runner 服务共享物理资源；已有普通 Core／Coverage 与 Portal 争用导致超时的
  [事故记录](../../../.agents/pitfalls/shared-host-runner-capacity.md)。
  不能由任务名称断言只有 TSan 需要资源隔离。

这些是带日期的评审事实，不是未来 rollout 的 live inventory；实施前需重新读取。

### 2.4 原生 Merge Queue 的可用性

2026-09-07 核实：仓库是个人账户拥有的私有仓库。
[GitHub 官方文档](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)
仍限定原生 Merge Queue 可用于组织公开仓库，或 Enterprise Cloud 组织私有仓库。
Rulesets 可用不等于其中每一种规则都适用于 Team 私有仓库。

本方案退役串行集成验证队列，不依赖原生 Merge Queue，也不要求账户／套餐迁移。
未来若恢复合并前组合验证，再单独评估原生队列及其成本；平台队列仍需运行
base＋前序 PR＋当前 PR 的组合验证，不会自动消除测试开销。

## 3. 目标流程

| 阶段 | 触发 | 行为 | 是否阻塞 PR／自动发布 |
| --- | --- | --- | --- |
| PR 审查 | PR 当前 head 创建或更新 | AI review；作者处理反馈，按既有授权进行合并 | 不等待产品全量测试；不授权发布 |
| 每日自测 | 每日定时 | 固定 main SHA，执行完整测试集合并保存结论 | 不阻塞 PR，不自动发布 |
| 重要节点自测 | Owner 显式触发；指定节点的自动触发须另有配置 | 对固定 main SHA 跑同一套全量测试 | 不阻塞 PR，不自动发布 |
| 失败报告 | 自测出现失败或未完成 | 创建／更新对应修复 issue，保留精确运行证据 | 不暂停普通合并，不自动回退 |
| 发布前验证 | Owner 选择候选 | 复用候选有效的完整证据；不足时补跑同一套全量测试 | 失败只阻止该候选发布 |
| 手动发布 | Owner 明确决定发布 | 使用既有签名、发布、部署及 Channel 流程 | 不由日测绿色状态自动触发 |

不再对每次 main push 自动跑一套重复全量测试。单个 PR 的 AI review 与多个 PR 的
合并可以独立推进；GitHub 必需的短暂 ref 更新顺序不再扩展成等待测试的串行锁。
重要节点默认用手动 dispatch 表达，不由 agent 猜测“重要”并制造额外全量 run。

## 4. PR 合并政策

### 4.1 审查、反馈与授权

AI review 是主要审查手段，不是运行正确性的证明。当前 head 的 review 应有可见状态、
结论或失败原因，不能用旧 head 的审查冒充新改动已经被审查。作者处理明确的严重问题；
AI 意见有争议时由维护者裁决，不把模型的自由文本直接转成无人能解除的硬性 gate。

AI 服务异常时允许人工审查接管；不得因服务超时无限挂起全仓库的合并，也不把
“review 没有运行”显示成“review 已通过”。review job 本身成功与代码得到批准分开表达。

现有 PR、授权、代码冲突处理、受保护分支写入与 review conversation 规则继续有明确
归属。移除 CI required checks 不等于允许 agent 自行 push 或 merge；合并仍需原有的
用户授权。本文不新增自动批准、直接写 main 或自动解决 review thread 的权限。

### 4.2 移除重验循环

目标分支保护移除 Core Ubuntu、Core macOS 和现有 PR Gate 的 required 身份，关闭
strict。保留 PR 合入路径及实际代码冲突检查；PR 不必只因 main 前进而 update-branch。

自研队列、queue ticket、update-branch 控制器及其 watchdog 在迁移后退役。
不另建一个“轻量队列”重复维护 base／head drift 重验。已获授权的合并由 GitHub
普通 PR 合并路径完成；是否使用平台 auto-merge 是合并授权选择，不依赖全量自测。

PR 快速反馈可以包含现有便宜的文档、语法或 typecheck，但默认 advisory：
不等待独占资源、不调用完整 proof、不成为旧 PR Gate 的新名字。若以后要增加任何
required 检查，必须说明它能在当前容量下稳定完成的耗时与确切阻塞范围，单独评审。
本地仍可按 Task 执行小范围验证；不得通过 pre-push hook 或 shipping skill 把退出 CI
的全量门禁搬回开发者机器，使合并实际上仍需等待同一套测试。

关闭 strict 后，A、B 各自可审查但组合可能失败，这是已接受的乐观策略；
组合正确性由固定目标的全量自测负责，不以“已经合并”推断测试已通过。

## 5. 每日与重要节点自测

### 5.1 触发与精确目标

每日定时和手动节点 dispatch 共享同一套自测入口。优先复用现有 16:00 UTC
（Asia/Shanghai 次日 00:00）的定时窗口；实施时根据可用容量确认窗口。
cron 表示预期触发时间，不承诺平台精确到点执行。

每次自测在触发／目标解析时固定 main 上的完整 SHA，并记录来源事件、目标和运行 ID。
所有 checkout、构建、测试与报告绑定该目标。运行过程中 main 前进不改变目标，
不取消运行，也不在旧事件中 checkout 新 main 后继续沿用旧 SHA 报告。

重要节点默认由 Owner 显式选择目标并 dispatch。只有经配置的确定性节点才可自动
增加自测；普通 PR merge 不属于这种自动触发。重复请求同一目标时复用适用的在途或
已完成证据；显式诊断重跑保留 attempt 与原因，不能静默丢弃先前失败。

每天没有新 main 变化时，允许跳过重复的常规定时自测并保留已有完整结果；
时间敏感的 soak／外部环境检查另列目的。需要刷新发布证据时走显式候选验证，
不能把旧结果的日期改成今天。

### 5.2 全量的定义

全量自测至少覆盖当前 Core CI 正式 full 所选的全部产品与工程检查，包括：

- Docs／Portal、CI／deploy contracts、Chameleon Lab 和全部相关 Web lane；
- Linux Core proof、macOS Core 及其支持平台检查；
- Linux ASan／UBSan 的 full 与 stress，macOS native sanitizer 覆盖；
- Coverage floor、Package／资产清单与完整浏览器验证；
- 当前 Nightly 的 TSan 和 Release stress，由同一自测批次关联报告，避免又跑一套
  重复的普通 full；保留现有执行语义，不把 stress 排除后仍声称已覆盖并发可靠性。

这里的 full 不能用 `scripts/core.sh test dev full` 一条命令代替：该命令排除 stress，
也不代表已经执行浏览器、sanitizer、coverage、package 和跨平台验证。
macOS native sanitizer 不替代 Linux Python-hosted sanitizer 覆盖。

实施复用现有检查入口和集合映射，形成一个可枚举的完整执行清单；PR feedback、
自测和发布消费者不能各自维护互相漂移的“全量”定义。保留 coverage floor、
行为断言、支持平台和关键用户旅程，不通过删测试或只保留页面打开来降低耗时。

各独立 suite 尽可能继续执行以一次收集多个问题；必需构建／环境准备失败时依赖项
记为 blocked／not-run。整批只有在完整清单的必需项全部成功时才报告通过。
部分成功、取消、基础设施失败或未执行项目均不是全量通过。

### 5.3 排队与取消

自测允许串行使用真实重型资源，但不占用 PR merge 的授权通道。
运行中的日测允许完成；普通重复定时请求可只保留一个最新 pending。
GitHub concurrency 按等待顺序调度，延迟事件／rerun 不得覆盖掉唯一的新待测目标；
实施必须重新核对目标和未处理请求，不能靠组名声称最新版本一定会被测到。

Owner 显式指定的重要节点或发布候选不能被后续普通定时请求静默替换。
按精确目标去重，保留这些显式请求；超容量时报告等待与预计完成时间，Owner 可明确取消。
使用现有 Actions 和有界调度能力实现，不先建设新的控制器服务或多级队列产品。

每日自测可在 main 前进期间正常得出历史目标的结论。后续提交等待下一次自测或
显式节点验证，不承诺每个 main SHA 都自动获得完整证据。

## 6. 自测失败与修复 issue

失败的默认产物是可执行的修复 issue，不是合并锁。自动报告属于后续获准部署的能力，
本次 spec 更新不在 GitHub 创建 issue 或发送消息。

每条报告至少包含：

- 自测 target SHA、workflow run／attempt 和可定位的日志或 artifact；
- 失败 suite／test ID、实际错误，以及哪些依赖检查未执行；
- 首次／最近出现的时间、影响范围、产品回归／测试偶发／基础设施故障分类；
- 发布影响、负责人和下一步复现／修复动作；尚未分诊时明确标为待分诊。

用 suite／test 身份与稳定故障类别去重，不以 SHA 作为新 issue 的唯一键；
同一个故障跨日、跨 SHA 失败更新已有开放 issue，而不是每天新开一个。
同 run／attempt 的重复通知幂等；错误指纹变化或已关闭问题复发时保留独立发生记录。
一次重跑绿色不自动关闭根因未确认的 flaky issue。
按既定去重策略替换的普通 pending 不视为测试失败，无需开 issue；已经选定执行的
自测异常中断、应触发而漏触发或必需项未运行则保留可定位的问题记录。

基础设施或 sanitizer runtime 启动失败同样可报告，但不能自动归罪于最新产品 PR，
也不能为使自测转绿而降低 coverage floor、放宽断言或吞掉退出码。
多个 PR 组合后发现故障时，从最后已知成功目标到失败目标定位，不自动 revert 最后一个 PR。

负责人按影响优先修复：数据丢失、核心路径不可用或无法构建影响发布候选资格；
其他问题进入正常修复流程。普通 PR 继续合入，修复 PR 同样不等待全量自测才能 merge。
修复后可以对固定新目标显式触发节点自测，无需等到第二天。

报告器与测试结果分离：issue API 故障不能把失败自测变绿，也不能造成 PR 阻塞。
保留可见的报告失败状态与重试入口。报告器使用受保护的可信代码和所需最小权限；
测试执行侧不持有 issue 写权限，来自日志／artifact 的文本不作为指令执行。

## 7. 手动发布与证据资格

Owner 手动决定是否发布及其候选。日测通过、issue 已关闭、PR 已合并都不自动触发
tag、Release、部署或 Channel promotion，也不替代相应授权。

候选处理规则：

1. 固定待发布的精确 main SHA，读取完整测试清单及该目标的有效证据。
2. 若日测／节点自测已经覆盖同一目标、同一适用测试协议且证据有效，直接复用；
   不强制另跑同义的“发布 CI”。否则显式执行该目标的同一套全量自测。
3. 只有完整结果通过，且没有已知适用于候选的阻断发布缺陷，才进入手动发布流程。
   失败生成／更新 issue；修复后的新 SHA 需要自己的验证，不能继承旧 SHA 的绿色状态。
4. 从已验证候选构建／核验发布产物，后续签名、发布、部署和 Channel 按现行入口执行；
   构建身份与资产校验仍必须成立，不能悄悄用最新 main 替换已经验证的候选。

测试证据只证明它记录的精确目标。main 后续即使已经合入多个 PR，Owner 仍可选择
先前通过的候选；后续发现适用于该候选的严重缺陷时，需先解决其发布资格。
新的 main 未经测试不等于历史绿色候选失效，也不等于新 main 自动获得绿色资格。

### 7.1 当前协议与迁移

当前 `tools/release/ci_evidence.py` 只接受符合协议的 `push` 或
`workflow_dispatch`，要求精确 main SHA、稳定 Core CI 身份、成功的同 run
Change Scope／PR Gate 和保留的完整可信 scope manifest；schedule 目前不被接受。
现有 full CI 证据也不能自动推断第 5.2 节关联的 Nightly 检查已通过。

因此“日测结果可直接用于手动发布”需要显式迁移证据生产者和消费者：
按验证的精确目标、可信生产者、完整测试集合、结果及保留期限判定，而不是靠事件名、
一个 workflow 绿色状态或缩小后的 PR feedback 冒充完整证明。

后续计划需列出旧／新协议兼容方式；选择受保护定时触发完整验证入口，或明确接纳
新的定时自测协议。完整支持第 5.2 节集合并验证 schedule 可信来源后才可宣称日测
可用于发布。迁移前沿用已支持的显式完整证据入口，不提前放宽 verifier。

显式候选验证与普通定时请求分开取消处理。过期／缺失 artifact 要重新验证，
不能重建一个“曾经应该通过”的结果。签名、不可变 tag、发布、Host 部署与 Channel
边界不因 CI 重构合并；日测流程不持有执行这些发布动作的权限。

## 8. 自测资源容量

解除 merge gate 消除了 PR 等待测试的问题，但没有增加物理计算能力。自测仍需在
下一周期前完成，避免将原来的 PR 积压转成自测积压。

实施前记录 CPU／内存／I/O、同机业务负载、runner 角色、编译并行度和测试 worker 数。
Netcup 的 Web／Core／Portal 一起预算；多个 runner 服务不是独立物理机。

- 轻量 PR／AI review 与重型自测使用明确的角色／容量分配，避免日测使 review 无法运行。
- 普通 Core、Coverage、Web 和 Portal 是否可并跑以同 revision 的主机测量决定。
- TSan、stress 或 benchmark 若需独占，须约束同主机所有不兼容任务；
  只有 TSan 加入 concurrency group 不能阻止其他任务与它同跑。
- 使用现有 runner 放置、资源隔离和共同 admission；替代隔离证明前保留现有资源锁。
- 可将需要串行的短 Native 工作合成一次 admission，内部逐项报告，减少重复排队；
  不让持锁的父 workflow 等待需要同名锁的子 job。
- Nightly 与每日全量纳入统一容量规划，复用准备工作；不独立重复构建相同普通套件。
- 日测、节点验证、候选验证按精确目标去重；显式请求不能被普通定时替换。

当前硬件不是不可改变的前提，也不预设扩容。若固定频率与测试量超出容量，
用基线提出频率、并行度或硬件成本选择；不能无限增加同机 runner、删测试或
降低断言来伪造容量达标。

## 9. 验收指标

目标按乐观策略重新定义，不再用“每个 PR 全量转绿”衡量合并流程：

| 指标 | 目标与统计口径 |
| --- | --- |
| PR 因产品全量测试产生的等待 | 0；required checks／workflow needs／控制器均无间接全量依赖 |
| 审查与合并授权完成后的合并 | 无冲突时通常 ≤ 3 分钟；平台故障单列，不要求更新无冲突的落后 PR |
| AI review 反馈 | 正常服务 p90 ≤ 10 分钟的初始目标；失败／缺失可见，有人工接管路径 |
| 每日自测覆盖 | 每个有新 main 变化的日周期至少有一个固定目标得到完整结论；未触发、排队或未完成须可见 |
| 自测耗时 | 先以已有样本回放确定预算；初始目标常规执行 p90 ≤ 90 分钟，排队单列；未达标须给出实际原因，不自动减少集合 |
| 问题报告 | 失败结论后正常服务下 ≤ 5 分钟形成／更新 issue；报告故障与测试故障分开 |
| 重复工作 | 同一有效目标／测试协议不无故重跑；同一故障不按天或按 SHA 重复开 issue |
| 发布资格 | 每次手动发布的精确候选均有完整有效证据；失败、缺失、取消、部分结果不得通过 |
| 突发 PR | 6 个同时就绪 PR 不等待自测排队；按各自审查／授权完成情况合法合并，无需 bypass |

回溯已有 Actions 连续 7 天记录作为基线，包含活跃与空闲时段，不要求空等七天才能
实施已验证的改动。报告样本数和冷／热缓存分层；一次拥堵 run 不能代表日常分位数。

保存 run／attempt、事件、SHA、测试集合、job 时间戳、runner／主机和失败原因。
统计 runner 分钟、日测结论年龄、未完成请求、问题去重与修复耗时；取消和失败不能
从成本统计中消失。不设置控制面提交占比或删除代码行数配额。

日测频率意味着缺陷可能到下个周期才被发现；重要节点和准备发布时可显式补测。
不继续沿用上一方案“每次 main 合入后 45 分钟内完整验证”的承诺。

## 10. 迁移顺序与回退

每个实施 Task 声明修改文件、验证集合、Documentation Impact 与 Version Management。
本 spec 确认目标流程，不直接修改远端保护或启停控制器。

### Phase 0：建立独立自测与报告

复用完整测试入口，增加固定目标的每日／手动触发、结果汇总和 issue 去重报告。
先以受控样本验证通过、产品失败、基础设施失败、取消／未运行和报告失败路径；
明确现有 Nightly 如何纳入完整清单。测量资源预算，不追加另一个永久重复 full workflow。

迁移验证期间可短暂保留旧 required checks；该并行窗口必须在计划中声明起止条件，
不得把双份全量验证变成常态。新报告器生效前通过受控远端演练证明 issue 幂等。

验收：固定目标可完整执行；新 main 不取消旧目标；失败形成可定位且去重的问题；
自测与报告均不执行 merge、tag、Release、部署或 Channel 动作。

### Phase 1：切换合并政策并退役队列

在自测、报告和候选证据路径可用后，迁移 AGENTS.md、Git 工作流与相关门户说明，
明确 main 为允许暂时不稳定的集成分支。同步移除旧 Core／PR Gate required contexts，
关闭 strict，产品全量退出 PR 和每次 main push。
同步调整 issue-done／issue-list 等相关 agent 技能及 local preflight／hook：保留操作授权
和任务范围验证，删除“必须排队、追 main、全量绿后才能合并”的旧自动化指令。

切换前盘点在途 queue 项及已有合并授权，停止旧队列接收新项；在途项明确完成或取消，
不把旧 label 的残留状态当作新合并路径授权。不删除尚未处理的用户意图。
然后退役控制器、queue inputs、watchdog 和只服务串行重验的测试／文档；
保留发布消费者仍需要的完整验证入口，不能因 PR Gate 不再 required 就删掉发布证明。

验收：落后但无冲突的 PR 可经审查和明确授权合并；自测红色或在途均不阻断普通 PR；
AI 服务失效可人工接管；同一 PR 没有两个合并控制器。

### Phase 2：发布证据统一与资源收缩

完成第 7.1 节新证据协议的验证与启用，让日测／节点结果可直接支持同 SHA 的手动发布，
避免额外重复全量；必要的候选补测保留。合并重复 Nightly／Main 工作并实施有测量依据的
主机隔离，删除废弃 CI 聚合与控制面镜像。

验收：完整证据可复用，部分／错误／过期证据被拒绝；自测绿色没有任何自动发布动作；
连续观察窗口包含每日运行、节点补测和突发 PR，达到第 9 节指标。

若新流程漏跑必需测试、错误授予发布资格或产生非授权 mutation，停止相关自动化并
恢复可验证路径。普通产品自测失败本身不触发策略回退或合并暂停。
若需要恢复旧合并门禁，必须先恢复能发布那些 contexts 的 workflow，再配置 required
checks；不得先加一个已经不存在的检查把所有 PR 锁死。

## 11. 必需验证场景

本节是后续 implementation 的验收，不能用本次文档检查声称这些能力已实现。

| 场景 | 预期观察 |
| --- | --- |
| PR 无冲突但落后 main | 当前 head 得到审查与明确授权后合并，不 update-branch，不等待全量 |
| AI review 缺失／失败／旧 head | 状态真实可见；人工可接管，旧结论不冒充新 head 审查 |
| 六个 PR 就绪，日测占用重型槽 | PR 各自审查并合并，重型排队不进入 merge 的依赖路径 |
| 日测 A 在跑，新 main B 合入 | A 继续完成并报告 A；B 由后续日测或节点请求处理 |
| 重复定时＋延迟事件 | 最新未处理目标不遗失；普通 pending 可合并，显式候选不被替换 |
| 同一失败连续两天出现 | 一个开放 issue 更新两次观察；重复通知不创建重复 issue |
| 构建失败使部分测试未运行 | 整批未通过，报告失败与未覆盖集合；普通 PR 仍可合入 |
| issue API 不可用 | 测试失败不变，报告故障可见，可重试；不阻断 PR |
| 修复合入并触发节点自测 | 验证固定新 SHA，保存完整结论；旧 SHA 失败不被覆盖改写 |
| 日测全部通过，没有发布指令 | 没有 tag、Release、部署或 Channel mutation |
| Owner 手动选择已验证候选 | 同 SHA 有效证据复用；所发布产物仍匹配候选 |
| Owner 选择未验证或失败的新 SHA | 补测／修复，候选未取得发布资格；普通 PR 不受影响 |
| schedule 与现有发布协议不兼容 | 迁移前明确拒绝；新协议生效后仅接受完整可信的精确证据 |
| Native／Web／Portal／Nightly 重叠 | 同主机隔离实际成立，测试断言及完整集合未被削弱 |

本地确定性测试验证状态逻辑；GitHub 保护规则、事件触发、issue API、runner admission
和取消语义需受控远端演练。mock 不能替代平台行为验证。

## 12. Documentation Impact

Documentation impact: none

Reason: 本 Task 仅修订设计 spec，不改变运行行为、active manifest、Product Build 或
Architecture Portal 页面。现行合并／发布规则在后续实施切换前保持有效。

实施必须同步 AGENTS.md、`docs/governance/git-workflow.md`、
`docs/governance/github-work-management.md`、`docs/quality/core-test-policy.md`，
以及 `.agents/skills/issue-done/SKILL.md`、`.agents/skills/issue-list/SKILL.md` 的相关流程，
并更新 `/operations/testing-and-proof/`、`/operations/version-and-release/`
门户路由与相关 source diagrams；发布证据协议变化还需同步版本／发布治理。
不能只修改 YAML 而留下“main 每次合入前全量通过”的旧承诺。

## 13. Version Management

Version impact: none

Reason: 本 Task 只修改 CI 流程设计，不改变 Product Build、Assembly、Core Module、
Provider、Host 或 Contract 身份。后续纯 CI 重构不自动分配产品版本；
若涉及产物格式或公开接口，应在对应实施计划重新评估。

## 14. 本次文档 Task

声明文件仅为 `docs/superpowers/specs/2026-09-07-lmdj-ci-capacity-redesign.md`。
验证包括事实与设计一致性复核、文档引用检查、`git diff --check`、
`scripts/architecture-portal.sh check` 和 staged diff 检查，随后创建本地 Conventional Commit。
本 Task 不执行 push、PR、merge、自动 issue 报告或任何发布／部署动作。

Pitfall impact: none — 本 Task 复核已有运行与 pitfall，修订尚未实施的设计，
没有操作新的故障路径；不把同一历史事故重复计为 recurrence。后续实施发现新的
过程不变量时，在对应修复 Task 按 issue-done 记录。
