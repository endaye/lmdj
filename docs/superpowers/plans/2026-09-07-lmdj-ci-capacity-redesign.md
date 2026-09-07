# LMDJ 乐观合并与每日自测实施计划

日期：2026-09-07
状态：待实施；本次仅提交计划，不改变线上 CI 或合并规则。

设计依据：[CI Capacity Redesign spec（固定修订）](https://github.com/endaye/lmdj/blob/c6c3f0f00ac41a2f4313c8d5092231226e3889fd/docs/superpowers/specs/2026-09-07-lmdj-ci-capacity-redesign.md)，
[spec PR #752](https://github.com/endaye/lmdj/pull/752)。
计划检查基线：`0d713914`；各 Task 开始前重新读取最新 `origin/main` 和现行治理，
不得覆盖其他任务刚落地的 CI、release hydrate 或审查监控修复。

## 1. 交付结果与边界

目标流程是：PR 当前 head 的 AI review／人工接管 → 明确授权后合并；
每天和重要节点对固定 main SHA 做全量自测 → 失败提出或更新 issue；
Owner 手动选择版本候选 → 核验该 SHA 的完整证据 → 分别授权发布操作。

- 日测不是每日发布。绿色日测不创建 tag、Release、部署或 Channel promotion。
- 普通产品缺陷使自测为红、候选不可发布，但不暂停普通 PR 或修复 PR 合并。
- 不用新的 merge queue、全量本地 pre-push 或长时间 AI 状态轮询替代旧瓶颈。
- 这是有意接受 main 短时不稳定的策略；生效时同步修改“main 始终可部署”的旧治理。
- 保留短分支、隔离 worktree、PR、冲突处理、审查对话以及逐步操作授权。
- 不改变测试断言、覆盖率底线、stress 重复次数、签名或不可变版本快照规则。

本计划不是远端操作授权。代码提交、push、PR、merge、规则修改、受控故障演练
以及 release 操作分别遵循当时有效的授权边界。下文复选框均未完成。

## 2. 最短落地路径

| 顺序 | 交付 | 退出证据 |
| --- | --- | --- |
| T0–T2 | 所有权、固定 SHA 全量自测 | 完整套件清单；一个真实目标的终态报告 |
| T3–T4 | 去重 issue 报告、AI review 独立入口 | 失败可定位且可重试；review 不依赖重型任务 |
| O1 | 切换前受控验收 | 自测、报告、旧手动候选路径均可用 |
| T5 + O2 + T6 | 切换规则、停止重复触发、退役队列 | 落后但无冲突的 PR 不 update、不等全量即可合并 |
| T7 | 新日测证据接入发布验证器 | 精确完整证据可复用；无效证据拒绝 |
| T8 + O3 | 资源收缩与稳定性验收 | 无重型 merge 等待；日测问题反馈持续有效 |

T0–T4 期间现有门禁仍生效。新自测先仅手动演练，不同时开启两套每日全量任务。
O1 通过后由维护者确定一个有开始、截止和回退负责人的切换窗口；不无限期双跑，
也不为采样而强制等待七天。T7、T8 不应延迟已具备反馈和候选路径的合并政策切换。

每个 T Task 是一个 reviewable Conventional Commit，使用独立短分支及 worktree。
若文件范围实际过大，在实现前按行为边界拆 Task，而不是合为一个巨型控制面 PR。
O Task 是远端操作与证据检查点，不通过空 commit 伪装成代码交付。

## 3. 实现约定

### 3.1 保持一个全量定义

当前清单来自 `scripts/ci/scope_policy.json` 的 14 个 logical lanes：

`docs_static`、`portal`、`ci_contract`、`core_ubuntu`、`core_asan`、
`core_coverage`、`core_macos`、`web_toolchain`、`web_runtime_host`、
`creator`、`web_runtime_lab`、`deploy_contract`、`chameleon_lab`、`package`。

另须纳入 `core-nightly.yml` 当前执行的 TSan stress 和 Release stress
（`--repeat until-fail:20`）。不要把 `core.sh test dev full` 或 `proof`
误称为上述全量；它们排除 stress。Linux ASan 保留 full + stress 和 Python-hosted
覆盖；macOS 保留 native sanitizer 覆盖。Mac runner 选择／fallback 的控制分支
可以按明确定义跳过，但对应 logical suite 必须有真实成功结果。

T1 为此定义一个权威的自测套件清单和校验器。旧 scope policy 在兼容期用于旧 CI，
用 parity test 对照两个入口；不得长期手工维护两份互不校验的“全量”列表。

### 3.2 固定目标，不伪造事件身份

自测证据区分 `control_revision`、`target_revision`、run ID、run attempt、
suite ID、policy revision、结论、产物摘要和开始／结束时间。
所有目标都是完整 40 位 SHA，并证明属于 main 历史；checkout 后实际 HEAD 必须一致。

定时事件选择一个 main 目标后不再漂移。手动重要节点和候选可明确选择旧 main SHA，
但 GitHub run 的 head SHA 可能是控制工作流修订，不能覆盖成候选 SHA 来“满足”旧验证器。
T7 使用新协议显式验证两者及可信 resolver、checkout、suite 结果的绑定。
产物命名包含目标、run ID 和 attempt；重跑追加观察，不能覆盖旧失败记录。

### 3.3 无长驻排队控制器

执行中的批次不因新 main 取消。普通日测 pending 可合并为最新尚未覆盖的目标；
显式节点／候选请求不可被普通 pending 替换，重复同 SHA 请求可复用有效结果或订阅同批次。

优先采用短生命周期的入口／结束回调加 Actions 状态查询，不增加数据库或常驻服务。
不要在自托管 runner 上保留数小时 polling job。原生 pending 替换不保证业务目标
按新旧顺序保留：resolver 必须在启动时检查规范目标与未完成请求，延迟旧事件不得吞掉新目标。
有限容量溢出必须明确拒绝并给重试办法，不能静默丢掉显式候选。

### 3.4 日测结果与报告状态分开

独立 suite 失败不取消其他独立 suite；构建失败的下游为 blocked/not-run，
缺失结果、异常取消、超时或 artifact 失效均不算全量通过。
reporter 失败不改变测试 verdict；自身产生可见的 reporting-error。

去重键是稳定 suite/test ID + 规范化错误类别，SHA 和日期属于观察记录而非问题身份。
并发与重试通过单写者短报告任务和幂等 observation key
（run ID / attempt / suite / failure fingerprint）收敛到同一个 issue。
日志只作数据，截断、脱敏、转义；不得执行 artifact 内容或让 AI 指令获得写入权限。

## 4. Tasks

### T0：预先登记新增控制面路径

**分支／commit：** `feat/ci-self-test-ownership` /
`feat(ci): register self-test control-plane ownership`

**修改文件：** `scripts/ci/scope_policy.json`、
`tests/build/ci_change_scope_test.py`；必要时补同目录 policy parity 测试。

- [ ] 登记后续新增的 `.github/workflows/self-test.yml`、`self-test-report.yml`、
  `pr-review.yml` 为显式控制面路径；新 `scripts/ci/` 文件已有 full rule，
  仍逐一核实路径覆盖。测试文件使用既有规则。
- [ ] 分类 fixture 验证全量升级原因与完整 lane 集合；不降低 unknown-path 的安全含义。
- [ ] 本 Task 只有路由及其测试，不捎带新工作流实现；先走现行普通受保护 PR，
  不让改路由的 PR 使用正在修改的 Integration Queue。

**验证：** `python3 tests/build/ci_change_scope_test.py`，
`python3 tests/build/ci_scope_policy_differential_test.py`。
Documentation impact: none；纯预登记，不改变任何现存路径行为或门户操作说明。

### T1：自测清单、身份及终态协议

**分支／commit：** `feat/ci-self-test-contract` /
`feat(ci): define exact-revision self-test evidence`

**新增文件（计划路径）：** `scripts/ci/self_test_policy.json`、
`scripts/ci/self_test.py`、`tests/build/ci_self_test_test.py`。

- [ ] 先写测试：完整集合成功、缺 suite、重复身份、未知 mandatory suite、错误 SHA、
  混合 run attempt、上传失败、空结果、合法 Mac 分支跳过和 required suite 跳过。
- [ ] 实现 resolve / aggregate 的纯逻辑接口；协议版本是 CI 内部证据版本，
  不是 Product 或跨语言 Contract 版本，不向 `contracts/` 添加新产品 Contract。
- [ ] 清单涵盖 §3.1 的全部现存覆盖，parity test 在旧 policy 增减 lane 时失败并指出 remedy。
- [ ] 判定明确区分 test failure、infrastructure failure、blocked、expected supersession；
  普通失败保留可行动的 why / remedy，不借分类把失败改成通过。
- [ ] 固定输出及 digest；外部 API、时间和存储采用严格测试替身，
  替身拒绝真实工具不接受的参数形状。

**验证：** `python3 tests/build/ci_self_test_test.py`，
`python3 tests/build/ci_change_scope_test.py`。
Documentation impact: none；此时协议尚未接入任何执行或发布入口。

### T2：独立手动全量入口，日测触发预备

**分支／commit：** `feat/ci-self-test-runner` /
`feat(ci): run complete self-tests on a fixed main revision`

**新增：** `.github/workflows/self-test.yml`、
`tests/build/ci_self_test_workflow_test.py`。
**修改：** T1 协议实现和测试；
`apps/architecture-portal/docs/operations/testing-and-proof.mdx`、
`docs/quality/core-test-policy.md`。

- [ ] 使用现有 proof、Web action、Mac action 和 package 命令实现所有 suites，
  包含 nightly 两个 stress 工作负载；第一版只启用 workflow_dispatch。
  保留现有资源锁、工具链、LFS、sanitizer host prerequisite 和 release hydrate 调用。
- [ ] 尽量复用现有组件；若为隔离旧入口而短期复制 job 定义，列出原 job 到新 suite
  的对应关系和 parity test，并在 T6 消除旧自动执行，不创建长期第二套测试实现。
- [ ] 当前控制代码负责解析、checkout、清单和汇总；测试进程无 issues/PR/contents 写权限，
  无签名、发布或部署凭证。不得在高权限 `pull_request_target` 中执行 PR 代码。
- [ ] 测试工件与报告放在 checkout 之外，避免弄脏目标让 package 拒绝或记录错误 revision。
- [ ] 加入 failure collection 与最终汇总；按真实 build 依赖串联，独立 suite 继续运行。
  默认矩阵 fail-fast 不得取消其余覆盖。
- [ ] 验证 main A 测试中出现 B 时，全部 suite 和 package 仍指向 A；
  错误／非 main 目标被拒绝。先不改 release verifier。
- [ ] 门户准确标注“新增手动入口，旧门禁仍生效”，不提前宣布乐观合并已上线。

**验证：** T1/T2 测试；现存 `ci_workflow_topology_test.py`、
`ci_nightly_workflow_test.py`、`ci_toolchain_pin_test.py`；
CI contract 的 pinned actionlint；portal check。
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/

### T3：失败 issue 闭环与漏跑告警

**分支／commit：** `feat/ci-self-test-reporting` /
`feat(ci): report self-test failures idempotently`

**新增：** `.github/workflows/self-test-report.yml`、
`scripts/ci/self_test_report.py`、
`tests/build/ci_self_test_report_test.py`、
`tests/build/ci_self_test_report_workflow_test.py`。
**修改：** 测试门户页面；`docs/governance/github-work-management.md`。

- [ ] 用受保护默认分支代码处理 workflow completion 和显式重试；
  校验 repository、稳定 workflow 身份、允许事件、run ID/attempt、目标和 artifact。
  不从被测 checkout 加载可执行 reporter；下载解压拒绝路径穿越。
- [ ] 单独 job 最小权限 `contents: read`、`actions: read`、`issues: write`；
  不给测试执行 job issue 写权限，不借用 Queue 的 merge 凭证。
- [ ] 正常 API 下失败后 5 分钟内创建或更新 issue，列 SHA、suite/test、日志／artifact、
  未运行集合、分类、严重程度、负责人和下一步；默认负责人使用明确配置的维护者。
- [ ] 两天同一缺陷只更新一条 issue；同一 observation 重送不重复评论。
  已关闭问题再现可重新打开并记录新观察；一次偶然绿色不自动关闭 flaky issue。
  单写者串行化不能用会丢 pending 的默认队列吞掉通知；短任务须核对未报告 run，
  重启后补齐遗漏 observation，并测试两个不同失败几乎同时完成的情况。
- [ ] API 故障有限退避，保留失败报告和 reporting-error 供显式重试；
  测试红色不因 reporter job 绿色而被摘要掩盖。
- [ ] 完成回调覆盖异常取消／启动失败；另设轻量检查发现“应有日测但根本没启动”，
  不把完全依赖同一个重测试队列的 watchdog 叫独立检测。其自身运行缺失须有
  维护者检查途径，不能声称 Actions 完全不可用时它仍必然告警。
- [ ] 规定每日值守人查看报告，产品缺陷与基础设施故障分别 triage；
  高严重度问题影响适用候选资格，不影响普通 PR 合并。

**验证：** reporter 两套新增测试；恶意日志、重复通知、并发首报、API 403/429/5xx、
丢 artifact、异常取消、漏跑、关闭后复现 fixtures；portal check。
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/

### T4：准备不依赖重测试的 AI review 入口

**分支／commit：** `feat/ci-pr-review-entry` /
`feat(ci): prepare independent PR review feedback`

**新增：** `.github/workflows/pr-review.yml`、
`tests/build/ci_pr_review_workflow_test.py`。
**按实际接口修改：** `.github/scripts/advisory_review_liveness.py`、
`.github/scripts/grok_review.py`、`.github/scripts/retire_clean_review_threads.py`
及各自 `ci_*_test.py`；测试门户页面。

- [ ] 提取现有后端选择、Claude/Grok review 与线程处理所需能力，
  新入口先仅手动验证；不得与旧入口对同一 PR head 长期双写审查。
- [ ] 审查结果绑定 PR 当前 head，过期 head、缺失、超时、API 故障均真实显示；
  给出明确人工接管方法，不用无限自动重试等待 AI 自己通过。
- [ ] 重型 lane 不依赖 review，新 review 也不依赖 scope/full-test/queue ticket。
  不增加不可接管的“解析模型自由文本为通过／拒绝”的硬门禁。
- [ ] 限制审查凭证与 agent 工具能力；仓库文本、PR 描述不能授权 push/merge，
  不让带高权限的 AI 任意执行 PR 提供的代码。
- [ ] 监控以确切 workflow run 和 head 绑定为准，空 check rollup、NEUTRAL 或旧 head
  不算审查完成；保留最新主干已修复的 merge-ref 可见性约束。

**验证：** 新 review 测试及现存 Claude/Grok/liveness/thread tests；portal check。
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/

### O1：切换前验收，尚不移除 required checks

- [ ] 维护者授权一个真实 main SHA 的新全量批次；记录 suite 完整集合和终态。
  产品已知失败可以如实报告，但必须证明整套调度／汇总／报告链路可工作。
- [ ] 授权隔离演练目标与测试 issue，复演首报 → 重送 → 再现 → API 故障 → 重试；
  不将 mock 通过描述为真实 GitHub side effects 已验证，不污染正式问题列表。
- [ ] 验证 review 新入口同一 head、过期 head、人工接管三条路径。
- [ ] 核实保留的 `ci.yml` 手动 full 入口能为准确 main SHA 产生旧验证器接受的证据。
  过渡期候选还须记录同 SHA 的 TSan/Release stress 结果；
  旧 full manifest 本身不证明已包含 Nightly。
- [ ] 若旧手动入口不能可靠固定目标，先修复目标绑定或将 T7 提前；
  不伪造 event/head_branch 绕过验证器，也不切换到没有可用候选验证路径的状态。
- [ ] 记录双跑截止、操作者、现行保护规则备份、现有队列 ticket 处置清单、
  scheduled 时间与资源预算。证据缺失时停在这里，旧门禁保持有效。

### T5：准备切换配置与一致的治理说明

**分支／commit：** `feat/ci-optimistic-merge-cutover` /
`feat(ci): separate optimistic PR merges from self-tests`

**修改文件：** `.github/workflows/ci.yml`、`core-nightly.yml`、
`merge-queue.yml`、新 self-test/review workflows；
`AGENTS.md`、`CLAUDE.md`（若有同义约束）、
`docs/governance/git-workflow.md`、`architecture-portal.md`、
`github-work-management.md`、`docs/quality/core-test-policy.md`；
`.agents/skills/issue-done/SKILL.md`、`issue-list/SKILL.md`、
`.github/pull_request_template.md`、`scripts/ci/local_preflight.py`；
对应 workflow/skill/preflight contract tests 及两个 operations 门户页面。

- [ ] 提交可审查的切换 diff 和 O2 runbook；此 PR 仍走当前保护规则。
  O2 移除旧 required contexts 前，不能先让仍被要求的 producer 消失。
- [ ] 切换后 PR 仅自动做 AI review 和可选轻量 advisory；普通 main push 不再启动产品全量。
  保留旧 `ci.yml` 的显式 full 候选入口及其真实 scope/gate，直至 T7 迁移通过。
  同次切换启用新 review 的 PR 事件并停用旧 review，避免对同一 head 重复审查。
- [ ] 新 self-test 接管每日 16:00 UTC 及重要节点入口，旧 Core CI / Nightly cron 同时停用；
  不保留两套自动全量。显式候选仍独立于普通 pending 的合并规则。
- [ ] 停止旧 queue 新 ticket 入口和 watchdog 自动补发；明确已在途 ticket 的完成、
  停止或人工交接，旧 label 不再被任何新代码解释为新的合并授权。
- [ ] 更新 skills 与 PR 模板：不再为合并等待全量／反复 update main／发 queue ticket；
  task-specific 本地验证保留，但不得强制执行所有产品 lanes 后才允许 push/merge。
- [ ] pre-push 的重型检查变为显式 opt-in；已有 hook 的迁移给出可识别、可恢复方案，
  只替换本工具安装的 hook，不覆盖个人 hook，不自动遍历修改用户 worktree。
- [ ] 调整 portal check 的位置与治理说明：仍是受影响任务的本地验证和自测 suite，
  不留下“全量门户生产构建必须远端绿色才能 merge”的隐形门禁。
- [ ] 门户区分 main 集成状态与版本资格；涉及的内嵌流程图随页面更新，
  若现有架构源图实际引用旧流程则同 Task 更新，禁止改历史快照或手写生成图。

**验证：** 全 `ci_*_test.py`，release CI evidence 回归，
portal check；静态扫描所有活跃消费者的 queue/required/strict/full-test 假设。
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/ /operations/version-and-release/

### O2：明确授权后的规则切换

- [ ] 再次读取 live protection/rulesets，确认没有其他约束覆盖此次修改；保存精确旧配置。
- [ ] 停止队列接收新请求，逐个核对既有 ticket 的授权与状态，不批量盲目合并。
- [ ] 在新自测、报告、review 和候选兼容入口 ready 的前提下，移除旧三个 required
  contexts，关闭 strict up-to-date；保留 PR、冲突、必要对话和其他未获准修改的保护。
- [ ] 核对实际生效配置后，在已有明确 merge 授权下合入 T5 切换 PR；
  不在 YAML 上创建假的同名成功 context 来填空。
- [ ] 若 T5 不能在约定窗口内合入／生效，恢复备份并停止，不把中间状态留到无人值守。
- [ ] 复核六个已获各自合并授权、当前 head 已审查、无冲突的 PR：即便落后 main，
  日测在途或红色，也可合并；记录每次实际 merged SHA 和等待时间。
- [ ] 本步骤完成后停止；不顺带发布、删除用户分支或变更 runner 主机。

### T6：删除已退役的队列依赖

**分支／commit：** `fix/ci-retire-merge-queue` /
`refactor(ci): retire integration queue control paths`。

**目标文件：** `.github/workflows/merge-queue.yml`、
`scripts/ci/merge_queue.py`、`github_queue_api.py`、`merge_queue_watchdog.py`；
`ci.yml` 中 queue 输入、ticket 工件与 pre-heavy review gate；
`scripts/ci/change_scope.py`、`pr_gate.py`、`phase_gate.py`、
`scope_policy.json`、对应 queue/phase/classification tests、受影响门户页面。

- [ ] 先列引用和现有消费者，确认无在途旧授权；仅删除确实专属 queue 的文件与测试。
  通用 GitHub API 或新 self-test 已复用的逻辑先迁移，不能连新报告一起删掉。
- [ ] 保留旧手动 full 入口在 T7 前仍需的 Change Scope、PR Gate 和 scope artifact；
  名称虽有 PR，当前仍是 release 证据依赖，不能按名称一并删除。
- [ ] 保留测试资产而非盲删所有旧测试：有效身份、安全、所有权与 failure readability
  断言移到新控制面；只退休旧 queue 行为断言。
- [ ] 不在本 Task 增加新的 merge controller，也不顺手提高物理主机并发。

**验证：** 全 CI contract + release evidence 回归；无活跃 queue 调用；
portal check。
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/ /operations/version-and-release/

### T7：发布验证器接入完整日测证据

**分支／commit：** `feat/ci-self-test-release-evidence` /
`feat(release): verify complete self-test evidence for exact candidates`

**修改文件：** `tools/release/ci_evidence.py`、`github_api.py`、
`model.py`、`policy.json` 及实际消费它们的 audit/prepare 接口；
`tests/build/release_ci_evidence_test.py`、`release_github_api_test.py`、
`release_audit_test.py`、`release_prepare_test.py`、`release_model_test.py`；
`.agents/skills/lmdj-release/SKILL.md`、`docs/governance/version-management.md`、
release pipeline spec、版本发布门户页面；必要时修改 T1/T2 的证据 producer。

- [ ] 实现新旧显式版本分支，不仅扩大 event allow-list：新证据核验可信稳定 workflow、
  控制修订、目标 main SHA、run/attempt、完整 policy suite 集合、全部 required 结果、
  artifact 摘要和有效保留期；workflow 名称或绿色总结文本不是证据。
- [ ] 允许可信 schedule 或手动 self-test 被 Owner 为同 SHA 候选显式引用；
  不能从新 target input 猜测其等于 GitHub run.head_sha。
- [ ] 优先单批次汇总全套 suites；若平台实现必须跨 runs，枚举每个成员的
  workflow/run/attempt/target 和结论，不用任意两个绿色 run 拼成“全量”。
- [ ] 缺少 TSan/Release stress、requested/focused、失败、未运行、错误 SHA、
  不可信控制代码、过期／不可读 artifact、混合 attempt 一律拒绝。
- [ ] 保留历史已发布 intent 的只读审计语义；证据保留期到期不改写已发布历史。
  新候选缺失有效证据则重新补测，不能借历史豁免绕过 prospective 核验。
- [ ] 旧兼容入口仅在新 producer + consumer 真实演练通过后退休；
  当切换 prospective policy 时不再允许只含旧 14 lanes 的证据绕过新全量定义。
- [ ] release 操作者仍先做 fresh exact-tag remote audit，沿稳定 `scripts/release.sh`
  接口逐边界执行；测试通过不调用 prepare/push-tag/create-draft/publish/deploy/promote。
  保留刚落地的显式 `hydrate` 与只读 audit 分离。
- [ ] 不自动修改 release intent、分配 Product Build 或产出永久门户快照。

**验证：** 全 `release_*_test.py` + 新 self-test 协议测试、skill tests、
portal check；真实候选的只读证据演练需另获授权，不以测试替身代替。
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/ /operations/version-and-release/

### T8：按测量收缩资源与重复执行

**分支／commit：** `fix/ci-self-test-capacity` /
`perf(ci): bound self-test work to measured host capacity`

**声明范围：** 新 self-test workflow、实际使用的 reusable actions、
`scripts/ci/host/` 的相关配置（如需）、对应 runner/topology tests、
测试门户页面；实施前按实测选定精确文件。

- [ ] 回看七天历史可用数据并报告样本数、负载来源、冷／热缓存、排队与执行耗时；
  PR #737 的拥堵样本只作为 burst，不把它当平日均值。
- [ ] 列物理主机上的 Native/Web/Portal/Nightly 共驻关系。
  保留现有隔离直到替代方案被验证；只给 TSan 加锁不代表主机独占。
- [ ] 如果合并 native 阶段到一次 admission，验证父任务持锁不会等待同锁子任务；
  不为节约等待把覆盖率 profile 或构建目录跨并发批次共享。
- [ ] 删除已经无消费者的旧自动全量副本、轮询和多余触发；不先采购主机或取消安全锁。
- [ ] 主机安装／systemd／ASLR 修改属于单独授权的运维动作，不由 PR 合并隐式执行。

**验证：** 受影响 contract tests、同主机重叠运行的受控测量、portal check。
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/

## 5. O3：最终验收矩阵

下列是实施后证据，不是本计划文档检查的结果。

| Spec 场景 | 负责 Task | 必须看到的后置事实 |
| --- | --- | --- |
| 落后 main 无冲突 PR | T5/O2 | 不 update、不等全量，当前 head 审查后实际 merged SHA 可查 |
| review 缺失／失败／旧 head | T4/O1 | 可见真实状态，人工接管有记录，旧结论不冒充当前 |
| 六 PR 与重型日测并行 | O2/T8 | 各自授权的合并完成，重型等待不出现在 merge 依赖中 |
| A 运行时 B 合入 | T2/O1 | A 全部结果仍属于 A；B 未被假记为已覆盖 |
| 重复／延迟触发 | T1/T2 | 最新普通目标保留，显式候选不被替换 |
| 同缺陷连续两天 | T3/O1 | 同一个 issue 两次观察，重送不增重复 issue/comment |
| build 失败 | T2/T3 | 全批未通过且列 not-run 集合；普通 PR 仍可合并 |
| issue API 故障 | T3/O1 | 测试 verdict 不变，reporting-error 可见，恢复重试只写一次 |
| 修复后节点自测 | T2/T3 | 固定新 SHA 完整报告，旧失败仍可查 |
| 日测通过但无发布指令 | T2/T7 | 无 tag/Release/deploy/promotion 调用和实际变更 |
| 选择已验证候选 | T7 | 同 SHA 完整有效证据可复用，构建产物仍绑定该候选 |
| 新／失败候选 | T7 | 候选拒绝或补测，不影响普通 PR |
| schedule 协议迁移 | T7 | 旧协议明确拒绝，新协议仅接受完整可信证据 |
| 混合重型负载 | T8 | 物理隔离实测成立，断言、floor、stress 次数未削弱 |

初始观测目标：产品全量导致的 PR merge 等待为 0；review 完成且获授权后无冲突
合并通常不超过 3 分钟；AI review p90 目标 10 分钟（含故障接管统计）。
每个有新 main 的日测日有目标结论或明确漏跑告警；正常 API 下失败报告 5 分钟内。
全量执行 p90 先以 90 分钟为优化目标，排队单列；没有足够样本不宣称已达到。

回退仅针对新自动化自身失效（漏跑不报、错误证据被接受、越权 mutation、报告风暴等），
普通产品测试失败不是恢复全量 PR 门禁的理由。若必须恢复旧门禁，
先恢复并验证其 producer，再恢复 required contexts/strict；不能制造永远 pending 的检查。

## 6. Documentation Impact

本次计划文档 Task：
Documentation impact: none
Reason: 仅新增实施计划，不修改 current 门户页面、实际 CI、发布资格或产品行为。

执行本计划：
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/ /operations/version-and-release/
Reason: T2 起的操作行为及 T5/T7 的合并、测试和发布证据边界必须同步反映到 current 页面。
每个 Task 按上文范围修改页面及实际受影响的源图；不改写 immutable snapshots。

## Version Management

Version impact: none
Reason: 本计划及所列 CI 控制面重构不改变 Product、Module、Host、Provider、
Contract、Assembly 或 Channel 身份；不分配 Product Build，不创建 tag。
CI 内部 evidence schema 演进按 producer/consumer 兼容迁移处理，不冒充产品 Contract 变更。

若后续候选准备需要 Product Build 或 Assembly 变更，另开版本 Task，
遵循现行 version policy 和不可变门户快照义务，不混入本计划的 CI Task。

## 7. 提交与验证约定

每个 Task：核对非 main 分支 → task-specific tests → portal check →
仅 stage 声明文件 → 完整 staged diff 与 whitespace 检查 →
有新文件时在 staging 后运行 ownership suite → Conventional Commit →
核对 committed files 与 clean status。push/PR/merge 不从本地 commit 推导授权。

本次唯一新增文件：
`docs/superpowers/plans/2026-09-07-lmdj-ci-capacity-redesign.md`。

本次文档验证：
`git diff --cached --check`；
`python3 tests/build/ci_change_scope_test.py`（stage 后）；
`scripts/architecture-portal.sh check`；
核对计划引用与 spec 的 14 条验收覆盖。
这些检查不证明上述未来 workflow 或远端流程已实现。

实施 Task 的共用回归命令：

```bash
python3 -m unittest discover -s tests/build -p 'ci_*_test.py'
python3 -m unittest discover -s tests/build -p 'release_*_test.py'
scripts/architecture-portal.sh check
```

只运行与 Task 风险相称的组合；未来新增测试路径在对应 Task 创建后才可执行。
actionlint 使用仓库 CI contract 固定版本及既有 schema 例外，不另装随意版本。

Pitfall impact: none — reason: 本计划应用现有容量、身份、报告与发布顺序知识，
没有执行新的远端故障或把历史观察当作新 recurrence。实施时新发现按 ledger 另行记录。
