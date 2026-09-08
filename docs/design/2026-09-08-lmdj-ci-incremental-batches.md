# LMDJ 主干增量批次自测

日期：2026-09-08

状态：Owner 已确认方向；本文交付设计，不代表线上能力已启用。
替代 [2026-09-07 spec](2026-09-07-lmdj-ci-capacity-redesign.md) 的每日自测策略；
旧 spec 的容量样本保留为历史证据，不重新当作当前吞吐基线。

## 1. 决策与边界

- 取消每日自动产品测试；没有新 main 提交且没有显式补测请求时，不运行产品测试。
- PR 保留 Task 相关验证、当前 head 审查、冲突和对话保护，不恢复全量 merge gate、
  strict 追 main 或 Integration Queue。
- 一次有效 AI review 同时产出测试范围。合入后不再调用 AI 决定范围。
- 同一时间最多一个自动主干自测批次运行；期间新合入改动合并到下一轮，
  不逐 PR 排重型测试，不取消当前批次。批次内独立 suite 可按资源约束并行。
- 范围覆盖区间内全部更新及受影响消费者，不仅最后一个 PR。
- 失败报告 issue，不冻结普通合并、不自动 revert、不自动关闭根因未确认的问题。
- 发布仍由 Owner 手动选择精确候选，要求完整有效证据。测试不分配 Product Build，
  不创建 tag／Release，不发布、部署或晋级 Channel。

接受的取舍：不是每个 main SHA 都被执行测试，而是每段变化都纳入影响分析，并在
选定的新目标上执行需要的集合。空闲期不主动发现环境漂移或偶发故障；保留手动
全量诊断和候选验收。范围完整依赖可审计的规则与测试，不是 AI 正确性的保证。

## 2. 当前实现与差距

本次源码检查基线：`5eb314f52ea71c879a8a4e00f749135791c16879`。

- [`ci.yml`](../../.github/workflows/ci.yml) 仍有 `0 16 * * *` 日测和手动固定目标入口。
- [`scope policy`](../../scripts/ci/scope_policy.json) 有 14 个分类 lane；
  [`self-test policy`](../../scripts/ci/self_test_policy.json) 有 16 个完整 suite，
  另含 TSan／Release stress。前者不能直接冒充完整集合。
- 现有完整 verdict、独立 reporter、精确候选证据消费者应复用，不复制测试实现。
- [`PR review`](../../.github/workflows/pr-review.yml) 尚不等于下文的单次有效审查回退链。
- 提交绑定范围、增量调度、验证债务和可靠接续仍需实现。

本 Task 不修改线上触发器。实施时重新读取实际 main 和现行治理，不把旧计划的状态
当作当前运行证据。

## 3. PR 范围协议

### 3.1 有限标签与最低规则

特殊标签为 `test:none`、`test:full`。普通标签为 `test:<suite-id>`，suite ID 来自
权威自测清单，例如 `test:creator`、`test:web_runtime_host`、`test:core_ubuntu`。
不维护另一套含义漂移的 host 别名；一个改动可以产生多个 suite 标签。

| 改动 | 最低验证范围 |
| --- | --- |
| 纯说明文档且无自动化消费者 | 可为 `test:none` |
| 某个 Host 的局部实现 | 该 Host 构建、行为测试及受影响依赖／调用方，不是仅编译 |
| Core 局部实现 | 受影响 Core suites 与跨边界消费者 |
| 底层 Contract、共享构建／依赖、Assembly、广泛并发影响 | `test:full` |
| 无法可靠分类、未知依赖 | `test:full`，记录 why 与 remedy |

`.md` 后缀不直接授予免测：治理、agent 指令、门户源文档、被测试读取的文档、
生成器输入和规范性契约仍路由到对应消费者。说明文档免合入后测试，不免除作者
对实际改动、链接和语法的 Task 验证责任。

规则显式覆盖所有 tracked paths、删除／重命名两端、共享 fixtures、生成输入、
支持平台及传递消费者。full 展开为全部 16-suite，包括两组 stress；不降低断言、
重复次数、平台覆盖或 coverage floor 来缩小范围。

### 3.2 一次有效审查，规则兜底

默认 GLM → Kimi → Grok 顺序尝试，获得一次有效审查即停止。限流、服务错误、
超时或非法结构化输出才触发下一后端；重试和总预算有界。审查发现代码缺陷是有效
结果，不为换到“无意见”而回退。若已有多个有效同 head 审查，取并集，不强制三跑。

AI 在同一次审查输出 findings、建议 suites 和理由。可信 publisher 验证后计算：

`effective suites = deterministic floor ∪ valid AI suites`

AI 不能删除规则要求的 suite。任意 full 支配局部标签；none 只在规则明确允许且
最终集合为空时有效，不能覆盖非空范围。未知字段、截断 diff 或分页不全不是空集合。
三后端全失败时去重创建／更新审查基础设施 issue，保留错误与人工／agent 接管入口；
不伪造 review 通过。范围仍可由规则保守产生，不能把服务故障变成重型 merge gate。

PR 文本、diff、模型回答均为不可信数据，不执行其中命令。模型没有贴标、issue 写入
或 merge 权限；写操作由独立可信 publisher 执行。

### 3.3 标签是展示，提交绑定记录是依据

版本化范围记录至少包含 repository、PR number、reviewed head SHA、diff base SHA、
changed-path digest、可信 control revision、policy digest、审查后端与 run／attempt、
规则最低范围、AI 建议、最终 suites、理由和记录摘要。
记录须可认证并持久保存；标签只是其展示投影，不是可随意改小的权威。

新 push 使旧 head 记录失效；旧 review 晚到不能覆盖新 head。重复发布幂等。
手动改标签不能降低最低范围或改变在途批次；提升在途目标的范围走留痕补测请求。

合入时验证 PR head 与实际 main squash／merge commit 的对应关系。每个实际 main
增量重新执行便宜的文件规则，覆盖审查后 main 漂移、冲突解决和规则变化；
采用经验证的旧／新策略最低范围并集，无法证明则全量。没有第二次 AI 调用。
缺失／过期／身份不符的记录或缺 PR 映射按实际 main 改动规则兜底；无法完整读取
改动／规则时升级全量，GitHub API 错误不当作“没有变化”。

## 4. 主干批次与恢复

### 4.1 区间、目标与去重

B 为已持久化处理进度，T 为本轮选取的最新 main SHA，均为完整 SHA，B 必须是 T
祖先。枚举 main first-parent 区间 `(B,T]` 内每个提交相对 first parent 的变化，
覆盖 squash／merge 实际结果；合并路径并集和有效 PR 范围，再计算传递影响、suite 去重。
不能只看两端净 diff：“先改再回退”也纳入区间风险。历史、路径与 PR 分页必须完整。

本轮冻结 B、T、policy digest 和 suite 集合。所有 checkout、构建、测试与报告绑定 T，
实际 HEAD 必须核验。后续 main 或标签变化不改变在途目标或减少在途范围。

```text
已处理 A → 合入 B → 测试 B（范围 A→B）
                    期间合入 C、D、E
           B 结束 → 测试 E（范围 B→E，合并 C、D、E 的需求）
                    无新提交 → 空闲
```

### 4.2 调度与持久状态

main push 只唤醒轻量调度器，不直接展开矩阵；批次完成也唤醒调度器。
完成接续不得让 workflow 直接订阅自己的 `workflow_run`：实际平台已拒绝该配置。
既有 `self-test-report.yml` 保持唯一有状态控制器与执行调用者；只读
`incremental-completion.yml` 中继其真实终态，保留精确父 run／attempt 的认证收据。
控制器验证中继本身、原父运行及其与 durable active executor 的关联后才结算；
没有 active 时，已认证批次完成回调还须独立读取 main：main 不同于 durable processed
才复用原调度器恢复完整未处理区间。被取消且未取得 claim 的 push 也可能有此唤醒价值，
其 conclusion 不是测试证据。无变化的空闲回调不写 journal、不创建新请求；无关父运行
不能结算或抢占已有 active。main 读取失败阻断此次恢复，不把读取失败当作空闲。
artifact 只是可核验关联，不是调度状态、执行请求或测试通过证据。中继不写 journal、
不启动产品任务，也不迁移现有 writer／workflow 身份。
调度器采用可信 main control revision，重新读取真实 main 和持久状态，不按事件顺序推进：

1. 有在途批次：不取消，只更新最新待处理目标，不给每个 PR 创建重型 run。
2. 空闲且有变化：固定最新 T，先持久化不可变批次请求，再启动执行。
3. 有有效免测区间且无待补测范围：记录 `not-required` 及理由、推进进度，不启动测试。
4. 终态结果持久化后推进进度，再次读取 main；有变化接下一轮，否则退出。

若 push 在取得 claim 前取消，而完成回调到达时已经空闲，执行同一第 2 步，
不是把被取消的父运行补记为已测。固定目标取重新读取的最新 main，不取父运行旧 head。

状态至少含 generation、processed SHA、active batch／request ID、pending target、
启动状态、结果引用、未覆盖 suite 债务和未解决失败引用。持久化介质、写者认证、
条件更新／互斥及保留策略必须在调度 Task 确定并验证，是开启自动触发的前置项。
不能把普通 Actions 单 pending concurrency 当持久队列，也不能只靠 30 天 artifact
保存进度。短调度锁不得跨重型执行持有，不与子 job 形成同名锁依赖环。

请求写入在先，启动在后；启动响应丢失先按请求身份查找真实 run，不盲目再次启动。
执行 claim 保证即使重复 dispatch 也最多一个实例执行重型集合。控制器崩溃、取消、
超时、乱序完成和旧 generation 回写都不能推进别人的进度。释放在途与读取最新 main
的交界必须防丢唤醒，不能无限等待下一次恰好有 PR。

恢复由 push、完成通知和显式 reconcile 驱动；可有轻量控制面健康巡检，仅恢复已有
请求／未处理变化，不能因日期变化运行产品测试。Actions 全局故障时不能承诺巡检
仍可执行，须保留可见不可用状态与人工恢复入口。

平台可能为无关或 idle 终态产生有界轻量中继／控制器外壳；它们不得制造新 admission
或重型执行。控制器→中继→控制器的跨 workflow 环仍需真实平台验收，不能从没有
直接自订阅推断其可用。完成链受平台深度上限约束，不承诺无限即时接续；独立巡检
必须真实证明能恢复上限处已有的尾部工作，追平后不因巡检或 idle 回调启动重型任务。

首次启用、状态丢失／不可认证或 B 非 T 祖先时，记录异常并做最新 T 的 bootstrap
全量，不猜测一个 baseline 跳过历史。历史无法完整获取时保持 blocked，不伪造已覆盖。
bootstrap 前须核对旧受控运行：无法证明旧批次已终止时暂停 admission，避免状态
丢失后与旧批次双跑。重新建立状态不表示历史缺陷或债务已被证明不存在。
显式 node／candidate 请求独立保存精确目标，不被自动 pending 替换；共享重型预算，
在批次边界有调度机会，不能被持续合入饿死。
显式请求不推进或回退自动 processed SHA，也不隐式充当自动批次完成通知。
历史候选成功只形成该目标的观察，不能清除较新 main 的失败或未覆盖义务；
自动批次要复用显式结果，必须独立证明目标、范围、策略及身份适用后留痕消费。

### 4.3 进度不是健康，失败不能遗忘

批次真实终态与结果持久化后可推进进度，即使存在失败；同时保存失败及未覆盖范围。
不能永远从最后全绿 SHA 重跑所有变化，也不能因新一轮只改文档就抹去 Core 失败。

- passed 只证明本轮选定 suite 在 T 成功，不证明未选 suites 或更新 SHA。
- 产品／测试失败保留 issue 和 suite 失败状态；相关改动或显式请求触发复验。
- 未执行、构建阻断、取消和基础设施故障保留验证债务，下一批次带上可执行债务。
  同一无变化故障有界重试后暂停该债务自动重试，记录 blocked 原因和恢复条件，
  不让无关文档合入持续重启已知坏掉的 runner。
- 暂停债务不等于已覆盖；相关基础设施修复或显式恢复触发补测，新变化的义务仍登记。
- 没有新变化且没有显式恢复，不为追绿无限产生批次。报告重试不重跑产品测试。

展示分别列出“处理到 T”“本轮结果”“未覆盖债务”“未解决缺陷”；none 或 focused
绿色不能成为整体全绿。后续通过追加观察，不改写历史失败，不自动关闭未确认根因的
issue。issue API 故障不阻断结果持久化或普通合并，待报告记录独立保留、幂等恢复。

这里区分报告业务写入与状态存储：若选用同一 API 承载状态，服务级故障时不能
承诺状态仍可持久化。此时保留可取得的临时结果，自动进度不推进、admission 为
blocked，恢复存储后再提交结果；临时证据过期明确记为丢失，不补造通过记录。

## 5. 结果与发布证据隔离

verdict 记录 base／target／control SHA、区间、PR 映射及缺口、范围依据、policy digest、
request／run／attempt、各 selected suite 结果和未选套件的 `not-selected` 理由。
selection kind 明确为 none、focused 或 full；not-selected／not-required 都不是 pass。
日志可按现有期限保留，进度与债务不能随日志删除消失，过期证据如实显示。

复用完整 16-suite 清单及执行入口。独立 suite 继续收集各自结果，失败构建依赖项
记为 blocked。保留主机锁、sanitizer／stress 隔离与断言，不默认扩容 runner。

focused／none 与旧 complete 协议严格分离；新的 full 触发来源仍需通过发布消费者
的独立身份校验，不能直接允许任意绿色 workflow。候选必须有同一精确 SHA、
适用策略、完整 16-suite 且有效的通过证据；不拼接不同 SHA 局部结果，不把进度
当作完整证明。始终保留手动精确 full 入口，本文不授权发布或更改发布安全边界。

## 6. 必须验证的场景

| 场景 | 必须观察到的结果 |
| --- | --- |
| 全区间仅合规说明文档 | 留下 none 记录，进度追平，无重型 run 或发布 |
| 两个 host PR | 最新 T 各执行所需集合一次，含行为／依赖测试 |
| 任一 Contract／未知路径 | 全部 16-suite，含两组 stress |
| rename／delete／revert／超过单页 | 区间完整，不只看净 diff 或第一页 |
| AI 漏标、none 与 full 冲突 | 最低范围不减，full 支配 |
| GLM 限流、Kimi 成功 | Grok 不启动，同次审查给出 findings 和范围 |
| 三后端故障／输出非法 | issue 去重、规则兜底，不伪造审查通过 |
| 新 head、旧 review 晚到、手动改标签 | 不覆盖新记录，不减少被冻结的范围 |
| main 漂移／缺 PR 映射 | 实际提交规则兜底，不明确则 full |
| B 在跑、C/D/E 合入 | B 不取消，下一轮唯一 E 覆盖全部 B→E |
| 完成边界合入、乱序 push | 不丢尾部、不倒退、不双跑 |
| 请求已写未启动、启动响应丢失、重启 | 按同一身份恢复，claim 防重复执行 |
| 取消／失败后文档合入 | 失败和债务保留，不能显示整体全绿 |
| 基础设施持续故障 | 有界恢复，其他可执行范围继续，无无限重跑 |
| 状态丢失／过期／非祖先 baseline | 可见 bootstrap full 或 blocked，不猜已覆盖 |
| issue 写后响应丢失 | 结果不改色、不丢记录、恢复不重复建 issue |
| 持续合入且有显式候选 | 不覆盖或饿死候选，目标不漂移 |
| 自动已处理 E，历史候选 B 完成 | 自动进度仍为 E，较新失败／债务不被 B 清除 |
| focused／跨 SHA／过期证据作候选 | 拒绝，保留精确手动 full |
| 无新变化经过一天 | 不因 cron 日期启动产品测试 |

本地纯状态机与真实 Git fixtures 先验证；平台事件、权限、启动与远端幂等另需受控
演练。mock 不等于 GitHub 行为验证，生产故障注入须有隔离和适用授权。

## 7. 迁移、回退与指标

顺序：范围协议／规则 → 审查 publisher 与调度逻辑 → focused 执行／报告消费者
→ 受控演练 → 同一切换移除每日产品 cron 和“每日未启动”告警，启用 main 唤醒。
先处理旧在途批次和初始化状态，不先关闭已知入口再假设新调度已经可靠。
同步治理、技能及门户，保留 PR／冲突／对话保护，不恢复 strict。

故障回退停止新的自动 admission，保留进度、在途结果和手动 full；不静默恢复日测
或旧合并门禁。普通产品测试失败本身不触发策略回退。
记录改动至选入／终态延迟、积压提交年龄、范围升级原因、runner 分钟、债务年龄及
报告成功率。合批减少排队数量，不承诺固定的全量执行分钟数。

## Documentation Impact

Documentation impact: none

Reason: 本 Task 仅设计与计划，不修改运行行为、active manifests 或 Portal 页面。
切换 Task 必须更新 `/operations/testing-and-proof/`、`/operations/version-and-release/`
及相关源图／治理，不提前把 current 页面写成新调度已启用。

## Version Management

Version impact: none

Reason: CI 设计不改变 Product Build、Assembly、Module、Host、Provider 或产品 Contract。
内部 CI 记录需版本化 schema，不为此分配产品版本。
