# Stage 9 Sequence Recording Review — 2026-08-27

- 审查对象：Stage 9 Sequence 录音的设计与交付，包括设计规格
  `docs/superpowers/specs/2026-08-22-sequence-recording-semantics-design.md`
  （SR-D1–D28）、实施计划
  `docs/superpowers/plans/2026-08-23-lmdj-stage9-sequence-recording.md`
  （Task 1–10）、PRD 决策
  `docs/prd/decisions/2026-08-23-sequence-recording-semantics.md`，以及实现范围
  `contracts/project/lmdj.project.v3.schema.json`、`packages/authoring-domain`、
  `packages/project-io`（SequenceJournal / ProjectStore）、
  `packages/project-cooker`、`packages/audio-runtime`、
  `packages/application-facade`、`packages/web-runtime-platform`、
  `apps/core-cli` / `apps/core-mcp` / `apps/native-host` /
  `apps/web-runtime-host` / `apps/creator-web`、版本与 Portal 快照、验收账本。
- 审查基线：交付提交为 PR #334 squash `1bc79006`（Task 2–10 及 18 个整合期
  修正提交；Task 1 先行以 PR #324 `5b425e5` 合入）；审查时 `origin/main` 位于
  `9b5c292`（#356，交付后的 merged-main 证据补录）。PR #334 全部 26 项 CI
  检查通过；exact-main Core CI run `33058032797` 通过。所有 `file:line` 证据
  以 `1bc79006` 检出的只读 worktree 为准。
- 方法：五个并行方向独立取证后交叉汇总——① Contract v3 / Domain / 迁移、
  ② Sequence Journal / Project I/O / 恢复、③ Facade / 整数时钟 / Cooker /
  Audio Runtime、④ CLI / MCP / Native / Web Runtime / Creator、⑤ 版本 /
  Portal / 验收与流程。三项最重发现（H1/H2、M1）由主审对关键代码路径二次
  抽查确认。本审查为静态审查加只读验证脚本
  （`scripts/version.py verify`、`tests/build/test_active_tree.sh`），未独立
  重跑构建与测试套件；测试结果以 CI 与验收账本为据。
- 性质：本文件是评审记录，不是实施计划。需要修复的事项应另行进入 Issue、
  实施计划与 Pull Request。

## 一、总体结论

Stage 9 的**底层机制质量很高**：整数有理数传输时钟（SR-D25）、量化/摇摆/时值
整数算法（§10.1）、journal 耐久链与 manifest 提交点（SR-D21）、canonical
fingerprint（SR-D22）、v3 Contract 与 v1/v2 总迁移（SR-D19/D28）均与设计
逐条吻合，且有跨语言 golden vectors、七点故障注入矩阵与 stress 层测试双重
证据；版本身份（1.0.37.0 与 12 个模块版本）与计划完全一致；Take 表面清退
干净；验收账本诚实——物理设备行如实记为 deferred，外部边界明确标注未授权。

但交付在**产品级集成与并发边界**上存在实质缺口：SR-D20 的核心句「一切
Authoring Command 的 admission 必须在写锁内、禁止无锁检查会话」被实现为
无锁的进程内存预检查，存在可复现的 TOCTOU 竞态（H1）；Stage 9 的两个标志性
交互——切槽后继续录音（SR-D11/D23）与录音中「叠加音下一圈可听」
（SR-D13）——在交付的产品中分别不可用（H2）与未接线（M1）；SR-D15/D18 的
武装 Pad 提交白名单未实现，Creator 的 trim overlay 实际走了 SR-D9 停录路径
（H3）。这三处均被「测试恰好停在缺口之前」掩盖。Creator（Task 8）是交付中
最薄弱的一环。

流程上，9 个实现 Task 加 18 个修正提交以单个 squash PR 合入，偏离了计划与
`CLAUDE.md` 规定的每 Task 一次可评审合并的模型；immutable snapshot 在修正后
refreeze，provenance 指向 squash 后已成悬挂对象的 revision，且未按既有机制
补 1.0.37.0 的 squash witness（#356 以树等价性记录部分弥补）。

| 严重度 | 数量 | 摘要 |
| --- | --- | --- |
| 高 | 3 | H1 admission 竞态；H2 切槽边界 flush 无 Host 发出；H3 SR-D15/D18 白名单缺失 |
| 中 | 8 | M1 叠加音未接线；M2 硬崩溃丢未 flush 事件；M3 重试卡死 journal；M4–M8 |
| 低 | 19 | 错误码偏差、恢复边角、文案残留、测试缺口等（第五节） |
| 信息 | 若干 | 正文列出，无需单独排期 |

**结论建议**：`1.0.37.0` 可作为 canary 候选保留，但在 H1–H3 与 M1–M3 修复
（或经决策记录明确收窄范围）之前，不应进入 beta/stable 晋升或任何 Release
边界。

### 整改处置账本（2026-08-28）

本账本只建立 source remediation 的责任链，不把 issue/Task/PR closure 写成
Product Build、物理验收或 Release 证据。统一 umbrella 为 #371；版本/current
truth integration 与不可变快照分别由 #379、#380 负责。

| Finding | Owner | Source disposition |
| --- | --- | --- |
| H1 | #378 | 实现 writer-lease 内 journal admission、本地 begin-vs-authoring critical section、孤儿 journal 先 seal，以及 settings-only Store rebase；以 Project Store 与 Facade deterministic component cases 阻断回归 |
| H2 | #376 | 实现共享 Web Runtime Session 的权威边界匹配、exact-once flush、串行 post-boundary admission，以及 Creator authority-only 状态转换；单元与 packaged-browser journey 覆盖乱序/重复通知、继续录音、stop、reload 和 committed-event inspection |
| H3 | #374 | open |
| M1 | #375 | open |
| M2 | #373 | source 修复：每次已接受 Pad event 在 acknowledgement 前写入单调、checksummed canonical tail；flush 消费 tail；真实子进程 `SIGKILL` 后重启 seal 两条事件并显式恢复；torn tail 携带 path/prefix/length/remedy fail closed |
| M3 | #372 | open |

H1/H2/M2 的 source 修复不改写或重新宣称 `1.0.37.0`；其 Module/Product
identity 与完整集成证据等待 #379，immutable snapshot 等待 #380。#360 的五项
物理/人工行继续保持未执行。

## 二、设计与计划文档评审

### 值得保持的实践

- 设计规格以 28 条编号决策（SR-D1–D28）加「明确非目标」与 7 条「拒绝的
  替代」组织，实现与验收都能逐条回链；§12 给出 20 条可执行的测试清单。
- §6/§10.1 把整数时钟、量化、摇摆、合并写成了唯一允许的整数公式，实现层
  没有解释空间——本次审查证实实现逐位吻合（见第六节）。
- 计划的「Locked Cross-Language Constants and Types」「Locked Project v3
  Migration」把跨语言常量与迁移语义钉死在计划层，Task 9 版本号精确到每个
  模块，且都被交付兑现。

### 文档缺陷

- **D1（低）** 规格状态行仍是「待用户再次 review」，未随决策合入（#324）
  更新为已批准状态。
- **D2（低）** 规格 §5 要求 journal 保存「当时的 BPM / Quantize / Swing」，
  计划锁定的 `ActiveSequenceJournal` 结构没有这三个字段，实现按计划执行
  （`packages/project-io/include/lmdj/project_io/sequence_journal.hpp:34-45`）。
  因量化/摇摆在采集时已烘焙进 tick，恢复正确性不受影响，但规格与计划的
  分歧未被任何勘误记录。
- **D3（低）** 计划锁定「九个操作名」，实现新增了第十个
  `sequence.record.settings.update`（SR-D14 所必需）。方向正确，但这是表面
  变更，未在计划或决策中补记。
- **D4（信息）** 计划 Task 1 文件清单列了 `docs/prd/decision-log.md`，而该
  账本自 2026-08-18 起冻结（决策改为独立文件），实际未改亦不该改；计划
  清单过期未修订。

## 三、高危发现

### H1 SR-D20 的写锁内 admission 未实现：无锁内存检查存在 TOCTOU 竞态

设计 §8.0：「一切 Authoring Command 的 admission **必须**在 Facade 已持有的
writer lease 内：先读 active Journal，再验 `expected_revision`，再执行。禁止
无锁检查会话」。实现相反：

- `reject_if_sequence_active`
  （`packages/application-facade/src/application.cpp:1758-1770`）只在
  `sequence_mutex` 下查**进程内存**的 `sequence_sessions` map，随后释放锁，
  store 稍后才执行。
- `ProjectStore::execute_with_identity`
  （`packages/project-io/src/project_store.cpp:2596-2646`）取 lease 后从不读
  `recovery/active/sequence.jsonl`；只有 flush 路径
  （`project_store.cpp:2805-2905`）正确地在 lease 内重读 journal。
- Native writer lease 进程内共享（`packages/project-io/src/native/`
  `storage_platform.cpp:1188-1206`）：会话持有的 lease 只排斥其他进程，对
  进程内并发零排斥。

后果一（竞态）：线程 A 的 `pad.assign` 通过预检查（尚无会话）→ 线程 B
`begin_sequence` 完成 → 线程 A 的 `AssignPad` 照常提交。Sample 类变更落在
录音中（违反 SR-D16），revision 超过 journal 的 `expected_revision`，之后
每次 flush 都 `REVISION_CONFLICT`，会话卡死直到 stop→owner_lost 恢复。

后果二（孤儿 journal）：owner 崩溃、lease 已释放、磁盘留有 active journal
时，新进程的 `pad.assign` / `asset.import` 不经 reconcile/seal 直接执行——
只有 `begin_sequence` 会先调 `reconcile_sequence_recovery`
（`application.cpp:1914`）。§8.0 要求先 reconcile → seal `owner_lost` →
才允许其他 Command。

测试覆盖：无。`tests/core/facade/sequence_surface_test.cpp` 只测单线程拒绝
与跨实例 `project_busy`；没有并发 begin-vs-authoring 测试，也没有孤儿
journal 后先发 authoring command 的测试。计划 Task 5 的「admission tests
proving the writer lease encloses owner check」勾选项实际未被验证。

整改方向：在 store 层修——`execute_with_identity` 在已持有的 lease 内读
active journal 再放行；发现无主 active journal 时先走 reconcile/seal。

### H2 切槽边界 flush 无任何 Host 发出：切槽后录音卡死，web 会话进入终态失败

Facade 的契约本身正确：切槽只在 `flush_sequence_locked` 内提交
（`application.cpp:2223-2241` 的 `switch_due` 分支调
`activate_switched_pattern`，`application.cpp:2071-2101`，也是唯一改 journal
目标的路径——SR-D23 的「禁止点击瞬间改目标」成立），并拒绝边界后事件：
`application.cpp:2009-2018`（`reason=switch_boundary_reached`）。MCP 黑盒
E2E 证明了完整路径（`tests/e2e/headless_core_proof.py:677-720`）。

但**没有任何交付的 Host 在边界上发这条 flush**：

- Web 桥只转发 Bar 边界通知（`packages/web-runtime-platform/src/`
  `bridge.cpp:670-694`、`control_runtime.cpp:2673-2691`；
  `runtime_session.mjs:2029-2059` 仅分发给监听者）。
- Creator 的边界回调只重新查询状态（`apps/creator-web/src/app.tsx:192-197`），
  reducer 直接把 phase 翻回 `recording`
  （`apps/creator-web/src/state/sequence_state.ts:75-79`）。
- `flushSequence` 在 `apps/creator-web/src` 中零调用（仅
  `runtime_types.ts:310` 的类型声明）；任何 JS/Host 源码中都没有
  `switch_boundary_reached` 的处理者。

后果链：录音中切槽 → 边界过去（引擎已在激活帧切换了可听 Pattern）→ 下一次
敲击 → Facade 拒绝 → `control_runtime.cpp:2186-2196` 把拒绝从 `trigger`
操作传出 → `runtime_session.mjs` 的 `dispatchTrigger` catch 调 `fail(error)`
（终态：整个会话状态机进入 `failed` 并做安全清理，
`runtime_session.mjs:1391-1431`）→ Creator 落入 ErrorPanel。即 Stage 9 的
标志性旅程「继续播、下一 Bar 切、继续录」在交付产品中不可用（fail-closed，
无数据损坏：边界前事件仍在 Stop 时 flush 进旧槽）。

测试覆盖：无。Creator Playwright 在切槽确认后立即停止
（`tests/platform/web/creator/creator_web_sequence.spec.mjs:98-115`）；
Stage 9 浏览器 Host 测试从不切槽；`control_runtime_test.cpp` 没有
switch-request 测试。

### H3 SR-D15/D24/D18 未实现：武装 Pad 提交白名单缺失，Creator trim 走了被禁止的 SR-D9 路径

PRD 决策明文：「选择性 rebase 是封闭白名单：BPM、Quantize/Swing、以及进行中
的 Pad Capture 提交到已武装的目标 Pad」
（`docs/prd/decisions/2026-08-23-sequence-recording-semantics.md` 结论 3）。
实现的白名单只有 `{BPM, Quantize, Swing}`（`application.cpp:4052-4145`，
settings rebase 本身正确，`:4118-4124` 会同步 journal）；
`sample.import.commit` 在会话中被无条件拒绝（`application.cpp:3568-3572`），
Facade 中不存在任何 armed-pad 概念（grep 仅命中 testing-hooks 注释）。

Creator 侧：`stopArmedCapture`（`apps/creator-web/src/app.tsx:685-692`）在
phase 为 recording/switch-pending 时**先调 `stopSequence()`** 再停采；
reducer 只允许从 `stopped` 进入 `trim-overlay`
（`sequence_state.ts:88-91`）。这正是设计 §7 明令禁止的路径——SR-D15 要求
「停采→trimming overlay，**会话继续**，提交成功后 rebase 会话」。

做对的部分：overlay 宿主留在 Sequence 表面、不导航（`app.tsx:909-928`）；
武装 Pad 的按下不进 trigger/journal（`input_controller.ts:516-520`，有
测试）。

验收账本把范围静默收窄为「settings-only selective rebase」
（`docs/quality/2026-08-23-stage9-sequence-recording-acceptance.md:47`），
但没有任何决策记录批准这次收窄。测试覆盖：没有测试断言会话在 trim overlay
中存活（它确实不能），浏览器测试完全未覆盖 Sequence 内 trim。

整改方向：要么实现 armed-pad 提交白名单并让 Creator 走会话内 overlay 路径，
要么按治理规则把收窄补一条 PRD 决策/勘误，并让账本与规格一致。

## 四、中危发现

### M1 SR-D13「下一圈可听」未接线：journal 叠加音在产品中不存在

Audio Runtime 侧已交付并有引擎级测试：
`PreparedPatternView::from_snapshot_with_overlay`
（`packages/audio-runtime/src/prepared_sample_bank.cpp:274`）、按
`(slot, onset_tick)` 合并（`prepared_sample_bank.cpp:106-121`）、next-Bar
发布测试（`tests/core/audio/realtime_engine_test.cpp:1684-1750`，带分配
拦截守卫）。但 `from_snapshot_with_overlay` **零生产调用**：Facade 只暴露
`pending_event_count`；web 桥只在 flush 后重发**已提交** snapshot
（`control_runtime.cpp:2371-2387`，经 `from_snapshot`）；Creator 录音期间
从不调 `flushSequence`。净效果：录音中敲的音只有当次 live voice，下一圈
听不到，直到 Stop——直接违反 SR-D13 与 §6「下一圈即可听到」。无测试断言
未 flush 音的下一圈可听性。

### M2 未 flush 事件只在内存：硬崩溃静默丢 tail 且无恢复件

`record_sequence_event` 纯内存暂存（`application.cpp:1980-2057`，不写
journal）；唯一持久化 pending tail 的路径是 `abandon_sequence_sessions()`
（`application.cpp:2630-2656`），由 `~Impl()`（`application.cpp:1615`）与
`control_runtime.cpp:1191` 调用——即只有优雅关闭。SIGKILL / tab 崩溃 / 断电
后 journal 无未完成 flush，开机 reconcile 直接清理，**不出现恢复提示**——
而 SR-D17 明确把「崩溃、音频中断、owner 丢失」列为需 seal 恢复件的场景，
规格 §5 要求 journal 含「尚未 commit 的事件」。现有 restart 测试
（`tests/host/mcp_facade_parity_test.py:690-889`）用 `mcp.close()` 优雅关闭
走析构路径，掩盖了该缺口；浏览器双窗口测试可佐证磁盘 journal 在 flush 间
为空（`web_runtime_host_browser.spec.mjs:2438-2449` 观察到
`pendingEventCount: 0`）。无 kill -9 / 硬崩溃重启测试。

**#373 source disposition（2026-08-29）**：Project I/O journal 新增单调
canonical tail snapshot；Facade 先耐久 append、成功后才更新 acknowledgement
ordering，press 以既有 240-tick 默认时值进入恢复 tail，release snapshot 再替换
真实时值。flush record 消费同一 tail；若 F1 append 后 execute 在 commit point 前
失败，继续录音的 F2 必须 canonical 覆盖全部 unresolved flush 与最新 tail，F2
completed 时同步 supersede 更早批次，recovery 只保留其后真正未提交 tail。
component regression 由真实子进程接受 `press/release/press`
三个 Pad event 请求后（最后一个 press 未释放）
`SIGSTOP`，父进程发送 `SIGKILL` 并验证 signal exit；新 owner reconcile 后得到恰
一个含两条事件的 `owner_lost` candidate，显式 apply 后 identity/order 保持且
revision 只增加一次。独立 Project I/O case 证明 reload/flush consumption，并证明
无终止换行的 torn tail、checksum mismatch、非单调 tail identity 与非 canonical
event order 均保留原字节、以 `INVALID_PROJECT` 加 path、record offset/durable
prefix、observed length、stable reason 与 repair/discard remedy fail closed。补充的
F1→F2 regression 证明较早失败批次不会二次恢复，且 F1 旧同-key event 不会覆盖
F2 已提交的新值；apply 只增加一次 revision，之后 apply/discard 均不再改变状态。
第二次 re-review 补齐 inverse completion：F0…F31 可在任何 completion 前耐久；F0
先完成时，以相同 session/pattern/expected-revision 和 canonical key/value coverage
resolve 所有等价较晚 retry，而不是只按 `flush_seq <= F0`。非等价较晚 batch 只扣
精确已提交 event，同-key 新值与新增 key 保留为 recovery residual。独立 case 还
覆盖 F0 manifest 已提交但 completion 报错、其后 F1 等价 retry 已 append 的歧义态；
restart reconcile 只回放 F0 receipt，不产生已提交工作的 candidate。
第三次 re-review 补齐 latest-tail residual：若 F0 manifest/receipt 已提交但
completion 报错，录音继续耐久写入 A+B 或 A+A'+B、且没有 append 较晚 flush，
重启回放 F0 completion 也从当前 `pending_events` 扣除精确已提交 A。新增 B 与
同-key 不同值 A' 保持 canonical 顺序成为唯一 recovery residual，显式 apply 只
增加一次 revision；等价-only tail 被完全 resolve，不产生 candidate 或第二次写入。
过滤不重置 `next_tail_seq`/`last_input_sequence`，因此后续 acknowledgement 的
单调性证据仍连续。
最终 integration review 还发现 #372 exact-command replay 与 #373 residual filtering
共用同一字段：F0(A) 完成会把已耐久 F1(A+B) 改写为 B，导致原始 F1(A+B) retry 被
拒绝、残余 B 反而可能冒充同一 command。修复后每条 flush 永久保存 original
canonical payload 作为 command identity，另存 effective recovery residual；append
replay/collision 只比较前者，reconcile/status/apply 只读取后者。sealed v2 显式要求
两个字段，旧 recovery-only snapshot 不猜测缺失的 original。Project I/O 与 Facade
回归覆盖 exact A+B retry、B/其他 payload collision、serialize/reload、只恢复并单次
apply B，以及 32-thread inverse completion。
该 source disposition 不是 merge、Product
Build、immutable snapshot、远端 CI 或物理验收证据；这些仍分别等待 #379、#380
与 #360。

### M3 同 `command_id` 重试可永久卡死 journal（SR-D21 幂等契约的可用性破口）

`SequenceJournal::append_flush` 不做 `command_id` 去重
（`packages/project-io/src/sequence_journal.cpp:694-760`），而 Facade 的
幂等回放短路要求 `pending_events.empty()`（`application.cpp:2141-2150`）。
若 flush 在 Project 已提交**之后**失败（如 receipt reload 的瞬时 IO 错——
交付自己建模的 `sequence_receipt_reload` 故障点），Host 按 §8.6 契约用同一
`command_id` 重试且期间有新事件到达时，journal 会追加一条同 `command_id`、
新 `flush_seq` 的记录。此后：

- `execute_sequence_flush` 对新记录永远失败：「command id is bound to a
  different Sequence flush identity」（`project_store.cpp:2888-2900`）；
- `reconcile_sequence_recovery` 把该身份不匹配当**硬失败**而非跳过
  （`project_store.cpp:2714-2725`、`:2976-2980`），reconcile 在 seal 之前
  就失败，而 begin 先 reconcile（`application.cpp:1914`）——flush、stop、
  reconcile、begin 全部永久失败，该 bundle 的 Sequence 功能砖死，只能手工
  删除 `recovery/active/sequence.jsonl`。

SR-D22 指纹门保证 Project Truth 不会双写（无数据腐化），这是可用性缺陷。
故障矩阵（`tests/core/project_io/sequence_journal_test.cpp:439`）每个故障
用全新 bundle、从不重试提交后故障的 flush，未覆盖。

**整改状态（2026-08-29，#372）：** journal append 现在在同一 append mutex
与 writer lease 内按 `command_id` 查重；相同 payload 返回原 flush record，冲突
payload 在写入前拒绝。Facade 在 journal append 后保留 exact in-flight record，
post-commit 返回失败的重试先执行原 identity，并只从 pending 集合移除该批原
事件，期间到达的事件必须由新的命令提交。组件测试覆盖 receipt reload 与
journal completion 的 same-bundle retry、restart reconcile，以及 Facade 中间
录入、后续 flush、stop 和 journal 清理。版本身份与整体验收仍由 #379 刷新。

### M4 Pending switch 期间改 BPM 留下陈旧边界（SR-D23）

`request_sequence_switch` 用请求时的锚点算 `effective_runtime_frame`
（`application.cpp:2329-2360`）；`sequence.settings.update` 改 BPM 冻结新
锚点（`application.cpp:4125-4132`）但从不重算 pending 边界。改速后，存储的
边界帧、引擎已按旧 BPM 发布的激活帧、新锚点下的音乐 Bar 三者分裂——正是
SR-D23 禁止的边界不同一。未测试。

### M5 恢复不可发现、恢复 UI 无指纹信息（SR-D17/D22 的 UX 半途）

Creator 的 `refreshSequence` 只在停录失败、settings 更新后、recover/discard
后与手动「Refresh authority」按钮触发（`app.tsx:630,680,718,877,890,896`）；
打开工程、reload、进入 Sequence 模式都不触发——「下次打开提示恢复」退化为
「用户碰巧点了刷新才看到」。恢复候选不携带指纹匹配信息
（`runtime_types.ts:259-265`；Facade `SequenceRecoveryInfo`
`application.cpp:2439-2470` 同），`sequence_surface.tsx:100-104` 对每个候选
无条件提供「写回原槽」，失败时用户只看到裸错误码
（`sequence_surface.tsx:131`）。Facade 层 fail-closed 成立
（`application.cpp:2519-2527`、失败路径保留恢复件 `:2557-2572`），不会
静默写回，但计划 Task 8「原槽仅在指纹匹配时提供、失败解释原因」未达成。
Creator 无 mismatch 路径测试，浏览器无 reload→recover 证据。

### M6 交付形态偏离逐 Task 合并模型；快照 provenance 指向悬挂 revision

计划 Issue Map 与 Final Acceptance Boundary 要求十个 Task Issue「各自合并、
各自验收」；`CLAUDE.md` 要求每 Task 一条可评审 Conventional Commit。实际
Task 2–10 以单个 squash PR #334 合入，消息列出 27 个成分提交：9 个计划 Task
提交外**混入 18 个未在计划中的提交**（8 个 `fix(...)` 修正、7 个
`test(...)`、3 个 `docs(portal)/docs(quality)`）。8 个修正提交落在同一评审
单元内，正是逐 Task 模型要防止的形态。

Task 10 要求快照来自「Task 9 的干净头」；账本记录 Task 9 revision 为
`e0f2de5b…`，而交付的 provenance
（`apps/architecture-portal/versioned_metadata/version-1.0.37.0.json`，
`revision: f9b82d40…`）指向修正后 refreeze 的分支头，squash 合并后该
revision 无任何分支可达（悬挂对象）。缓解：偏离在账本中透明记录；metadata
内嵌 `source_commit.raw_base64` 自证；交付后 #356 补录了树等价性（final PR
head 与合入 commit 同树 `4339692…`）。但仓库既有的 squash-witness 机制
（`versioned_provenance/*-squash-witness.json`，1.0.16.8–1.0.31.0 均有）
**没有为 1.0.37.0 留档**。建议补 witness 或记录豁免。

### M7 承诺的跨语言共享向量只交付了 fingerprint 一组

规格 §10.1 与计划 traceability（SR-D26/D27、迁移向量）要求 quantize / swing
/ merge / migration 的共享跨语言测试向量。实际只有 SR-D22 fingerprint 向量
真正跨语言（`tests/fixtures/golden/sequence-pattern-fingerprint-v1.json`，
C++ / Python / JS 三方消费且逐字节复核一致）；量化/摇摆/合并/迁移语义仅
C++ 覆盖（`tests/core/domain/project_test.cpp:73-116`、
`command_handler_test.cpp:567-698`、`project_store_test.cpp:591-758`）。
缓解：Host 被源边界测试禁止且实际未复制这些数学（Web 经同一 C++ Wasm），
实际分歧风险低，但计划勾选项按字面不成立。

### M8 计划要求的 Playwright 全旅程未交付

Task 8 要求「record → overdub → switch → trim → reload → recover」浏览器
证据。已交付：settings + 单键录音 + 切槽**确认即止** + stop + report
（`creator_web_sequence.spec.mjs`，121 行）；record/press-release 顺序、
overdub 合并、幂等 stop 回放、快照 reload 可见、双窗口共享状态 + 观察者
`PROJECT_BUSY`（`web_runtime_host_browser.spec.mjs:2383-2521`）。缺失：
Sequence 内 trim、reload→recover、任何边界后录音。验收账本对此如实描述
（未虚报），但计划勾选项不满足——且正是缺失的两段掩盖了 H2/H3。

## 五、低危发现

Journal / Project I/O：

- **L1** reconcile 把无 flush 的 begin-only journal seal 成 `owner_lost`
  （`project_store.cpp:~3000-3010` 的 `flushes.empty()` 分支），产生用户
  必须手动丢弃的零事件恢复候选；§8.0/§8.6 要求仅在仍有未提交事件时 seal。
  该分支无测试。
- **L2** `seal` 先写 sealed 文件再删 active（顺序正确，
  `sequence_journal.cpp:973-980`），但两步之间崩溃会在下次 reconcile 生成
  `-1` 后缀的重复 sealed 候选（`:959-972`）；`apply_sequence_recovery` 只删
  被应用的候选（`application.cpp:2588-2592`），两个同事件候选可分别 apply
  到不同 Pattern 造成事件重复（同槽双 apply 被指纹门挡住）。未测试。
- **L3** 带换行结尾但 checksum 损坏的 journal 记录使 `read_journal` 直接
  `invalid_project`（`sequence_journal.cpp:230-241,517-524`），此后一切
  journal 操作与 reconcile 报错，又一个只能手工删文件的状态；末条记录的
  checksum 失败可证明是未确认写入，本可安全截断。无 journal 层损坏记录
  测试（平台层截断有测试）。
- **L4** Web 侧「sequence flush fault matrix」守卫只是常量字面量断言
  （`project_io_web_conformance.spec.mjs:41-50`），浏览器 harness 并不注入
  这些故障；`project_io_web_faults.mjs:36-38` 的注释言过其实。
- **L5** 混合 committed/uncommitted 的多 flush reconcile（§8.6 的核心行为）
  已实现但全部测试都是单 flush，无覆盖。
- **L6** `remove_active_if_complete` 只检查全部 flush completed，不检查
  会话状态已 stopped/abandoned（`sequence_journal.cpp:1063-1071`），
  「会话结束」仅靠 Facade 调用顺序保证。

Facade / Runtime：

- **L7** 错误码偏差三处：会话中 settings 更新遇真 stale revision 返回
  `INVALID_ARGUMENT`「owner does not match」而非 `REVISION_CONFLICT`
  （`application.cpp:4097-4101`）；恢复指纹不匹配返回
  `REVISION_CONFLICT` + `reason=pattern_changed`（`application.cpp:2522-2526`），
  §10 把该码保留给真 stale revision；恢复事件越界报 journal 层
  `INVALID_ARGUMENT` 而非 §8.7 的 `INVALID_PROJECT` +
  `reason=events_out_of_range`。未新增公开错误码的要求成立。
- **L8** admission 是 7 处散点 opt-in 调用（`application.cpp:3214,3568,
  3664,3744,4027,4168,4220`）而非封闭分类表；今日表面覆盖完整、未知操作被
  封闭注册表拒绝（`application.cpp:2879`），但未来新增 authoring command
  忘记调用即静默绕过 SR-D16——结构性 fail-open。
- **L9** 恢复 apply 失败时把新起的 journal seal 成 `recovery_failed`
  （`application.cpp:2556-2571`），原候选正确保留，但会多出一个空的重复
  候选。
- **L10** 引擎循环长度 `loop_frames = ceil(ticks·D/rate)`
  （`realtime_engine.cpp:299-305`）与 Facade 精确积分的 tick 网格在非整除
  BPM 下漂移（140 BPM 约 2 ms / 10 min）。短期无感，值得账本备注。

Hosts / Creator：

- **L11** 边界回调把 UI 直接标成新槽 `recording`，而 Facade 权威仍是
  `switching`（`app.tsx:192-197` + `sequence_state.ts:76-79`）；transport
  只显示「Next Bar frame」，不显示 pending 目标 Pattern
  （`sequence_transport.tsx:20-23`）——违反「UI 不预测成功」。H2 修复时应
  一并处理。
- **L12** `authority`/`recovery` reducer 动作不守卫 `trim-overlay`
  （`sequence_state.ts:55-66,82-86`），trimming 中一次刷新或边界回调即卸载
  overlay（`app.tsx:909-912`），可能丢采集缓冲。
- **L13** SR-D2 残留用户可见「take」文案：「The take is unchanged — discard
  it to record again.」（`apps/creator-web/src/components/`
  `capture_panel.tsx:26-30`，本次交付改过该文件）。CLI/MCP/Sequence UI 其余
  干净。
- **L14** `clearAdversePressed` 先清手势 map 再调 adapter 释放回调
  （`input_controller.ts`），窗口失焦/隐藏时按住的 gate Pad 不发
  `session.release`：runtime 卡音，journal 侧按下一次 flush 以默认 1/16
  时值收尾。指针离开与键盘 auto-repeat 均处理正确。
- **L15** Native 采集把释放合成在按下同帧（`capture_writer.cpp:83-92`），
  经 `normalize_duration_tick` 得 1 tick 时值；web one_shot 按下即止事件在
  flush 收尾为 240 tick——同一手势跨 Host 产生不同 Project Truth。
- **L16** 快速连续两次切槽选择的第二次请求被 Facade 拒绝并以错误弹窗呈现
  （`app.tsx:757-770`）；失败安全，体验粗糙。

Contract / 迁移 / 流程：

- **L17** v1/v2 loader 额外接受 tick 形状事件（`project_store.cpp:525-531`
  的 `allow_legacy_events` 双形状），超出 v2 schema 允许范围，比「有界的
  v1/v2 读迁移」更宽。未测试。
- **L18** v3 schema 表达不了 `onset+duration > L` 的跨字段约束（JSON Schema
  固有限制，Domain 层已兜底），`project-v3-invalid-event.json` 未含该 case
  与 velocity 0（velocity 0 有 Domain 测试）。
- **L19** 两份跟踪账本停在决策合入状态：
  `docs/quality/2026-08-16-outstanding-work-before-stage9.md`（D4/D5 节）与
  `docs/quality/2026-08-17-machine-task-todo.md:119` 均无 #334/1.0.37.0 已
  合入的行。#356 只更新了验收账本。

## 六、验证为正确的方面（抽样证据）

- **整数时钟（SR-D25）**：`tick_numerator = N + (frame−F)·bpm·960`、
  `D = 2,880,000` 静态断言等于 `48000·60`
  （`prepared_sample_bank.hpp:20-44`）；溢出全程 checked；frame 倒退返回
  类型化错误；`freeze_transport_bpm` 保留全精度分子不取整
  （`prepared_sample_bank.cpp:211-225`）；音乐时间路径无任何 float/double；
  C++/Python/worklet 向量一致；uint64 余量约 52 年。
- **量化/摇摆/时值（§10.1）**：`(loop_tick+119)/240` 与「余数 ≤120 取更早
  格」逐点等价（r=120 同格、r=121 进位）；wrap L→0 落偶数格故摇摆正确不
  作用；摇摆 `(480·swing+50)/100` 精确（50→240、75→360）；时值来自 raw
  attack/release 且双向防下溢（`project.cpp:103-186`）；合并键
  `(bank,pad,onset)` 后写覆盖 + 五元 canonical 排序与规格逐字对应。
- **v3 Contract 与迁移（SR-D19/D28）**：schema 必填集、界值、
  `additionalProperties:false`、按 bars 的 onset 上限全对；迁移按原数组序
  last-write-wins（先归并后排序，`project_store.cpp:574`）、`step×240`、
  默认值注入、`takes` 校验后丢弃、writer 仅发 v3 且 canonical 字节稳定，
  含 v2 重复 step 向量与回放字节一致测试。
- **Journal 耐久链（SR-D21）**：意图先耐久（store 拒绝未 journal 的身份，
  `project_store.cpp:2820-2832`）→ manifest 原子发布（写侧文件→fsync→身份
  校验→rename→目录 fsync）→ reload 可见 receipt → `complete_flush` → 全部
  completed 才删；七点故障矩阵 + 无缝隙 `flush_seq` 并发 stress；重复身份
  回放原 receipt 不再 apply。§8.6 重启矩阵四行均有实现与测试。
- **Fingerprint（SR-D22）**：`{bars,events}` 精确前像、字节序键、无空白/
  BOM/末尾换行/pattern_id、小写 hex（`sequence_journal.cpp:583-594`）；
  三个 golden hash 经独立重算一致；三语言消费同一 fixture 文件；completion
  指纹取自提交后 manifest head 的 Pattern（正确快照）。
- **跨 Host 表面**：CLI 纯 JSON 直通单一 Facade 适配器（十操作全注册）；
  MCP schema 与锁定结构 1:1；跨 Host flush 幂等黑盒测试（MCP flush → CLI
  同身份回放 `replayed:true`、单 revision、`project.inspect` 字节一致）；
  重启后恰一个恢复候选、无自动 resume；观察者 `PROJECT_BUSY` 双窗口证明。
- **Web 时序纪律**：所有 sequence 时间戳来自
  `engine.telemetry().rendered_frames` 的 admission 处
  （`control_runtime.cpp:583-603,2292-2316`）；JS 不提供
  `runtime_frame`/`input_sequence`；源边界测试主动禁止 Host JS 中的墙钟、
  journal、指纹与 fallback sequencer 代码
  （`web_host_source_boundary_test.py:116-186`）。
- **版本与 Take 清退**：1.0.37.0 与 12 个模块版本、Assembly v3-only 锁与
  计划逐项一致，三个摘要独立重算相符；active 代码零 Take 符号，
  `take_journal.*` 与其 1431 行测试删除；渲染线程零分配/零锁有守卫测试。
- **验收账本**：命令、计数、revision、CI run id、摘要俱全且诚实；物理行
  记为 deferred 不折算；#356 补录了 merged-main 与树等价性证据。

## 七、测试覆盖缺口汇总（对照设计 §12）

§12 的 20 条中 17 条有明确覆盖（含难点：manifest 发布故障注入、owner 丢失
reconcile、stress 层、三语言指纹向量、迁移重复 step 向量）。缺口与被掩盖项：

| 缺口 | 关联发现 |
| --- | --- |
| 并发 begin-vs-authoring / 孤儿 journal 后先发 authoring command | H1 |
| 边界后继续录音（任何层级都停在切槽确认） | H2 |
| Sequence 内 trim overlay 全流程（会话存活、提交 rebase、冲突保留） | H3 |
| 未 flush 音的下一圈可听性 | M1 |
| ~~kill -9 / 硬崩溃后恢复候选出现~~ | M2 source gate 已由 #373 的真实 `SIGKILL` component journey 覆盖；集成身份/快照仍待 #379/#380 |
| 提交后故障 + 同 `command_id` 重试 | M3 |
| Pending switch 中改 BPM | M4 |
| reload → recover 浏览器旅程；恢复指纹 mismatch 的 Creator 路径 | M5/M8 |
| 「切 Sample：停录 flush 后 Trim 成功」的正半段 | §12 |
| 「Record 中切 Sample 表面再开麦：会话已结束不叠加」 | §12 |
| Native/Web 对非整 tick frame 的同 `raw_tick` 跨目标断言（现仅 C++ 单侧） | §12 |
| 混合 committed/uncommitted reconcile；journal 层损坏记录 | L3/L5 |

## 八、整改建议与优先级

晋升门槛（beta / Release 前必须）：

1. **H1**：store 层在持有 lease 内读 active journal 做 admission；孤儿
   journal 先 reconcile/seal 再放行其他 Command；补并发与孤儿测试。
2. **H2**：让 web 桥或 Creator 在 Bar 边界通知上发 `sequence.record.flush`
   （或 Facade 内部在边界自动执行 flush——需小幅设计确认），并把 Playwright
   旅程延伸到边界后录音；连带修 L11。
3. **H3**：实现 armed-pad 提交白名单 + Creator 会话内 overlay 路径，或走
   决策记录正式收窄 SR-D15/D18 并勘误规格与账本。
4. **M1–M3**：接线 journal 叠加发布；录音事件按批耐久写 journal（或决策
   记录接受「flush 粒度耐久」并勘误 SR-D17/§5）；journal 层 `command_id`
   去重 + reconcile 对身份不匹配降级为可跳过。

跟进 Issue（不阻塞 canary）：M4–M8、L1–L19，其中 M6 的 squash witness 补录
与 L19 的账本刷新属流程收尾，成本低应尽快完成。

流程改进建议：后续 Stage 交付回归每 Task 一 PR 的模型；若确需聚合交付，
在计划中先行修订并为 refreeze 的快照补 squash witness；「测试止步于缺口
前」的三处（切槽确认即停、优雅关闭代崩溃、trim 不进浏览器旅程）说明验收
旅程应按设计 §12 的完整旅程逐句核对，而非按已实现功能剪裁。
