# LMDJ Stage 10 Perform Design — 2026-08-28（草稿）

日期：2026-08-28

状态：**草稿，未经 brainstorming 评审**。本文汇集 Stage 10 Perform 的权威输入、
提议决策与开放问题绑定，供设计评审逐节批准使用。P10-Q1–Q5（#383–#387）为
产品/Contract 级开放问题，本文**不预先裁决它们**；依赖它们的提议决策均标注
`〔待 #NNN〕`，评审须在对应决策文件合入后才能锁定。不分配 Product Build，
不改代码。

关联问题：
[#383](https://github.com/endaye/lmdj/issues/383)
[#384](https://github.com/endaye/lmdj/issues/384)
[#385](https://github.com/endaye/lmdj/issues/385)
[#386](https://github.com/endaye/lmdj/issues/386)
[#387](https://github.com/endaye/lmdj/issues/387)

对应问题来源文件：`docs/prd/questions/perform-*.md`（五件）。

## 1. 结论（草案）

Stage 10 把已经能录 Sequence 的乐器变成能**演出**的乐器：在 Perform 表面上
现场演奏 Pad、按音乐边界切换 Pattern、切换 Bank、施加瞬时 FX，并把整场演出
记录为可回放、可命名、可导出、可 Resample 的 Performance。

Stage 10 的成功命题是：

> 用户可以在不绕过 Application Facade、不产生第二份 Pattern 真相、不打断
> 实时渲染的前提下，现场演出一段 Beat，事后完整回放它，并把它（或其中一段）
> 变成新的 Pad 声音。

新内核规格 §7 是范围权威：Pad 演奏、Pattern 切换、Bank 切换、八种 Momentary
FX（Filter / Delay / Reverb / Stutter / Gate / Reverse / Crush / Roll）、
Performance Events 录制、Stereo WAV 录制、Replay / 命名 / 导出 / Resample，
且 `Hold` 必须是显式状态。§4.2 定义 Perform Surface 的四要素：Pattern
Launch、Momentary FX、录制和 Resample。

Stage 9 已经交付了 Stage 10 直接站立其上的三块地基：整数有理数传输时钟
（SR-D25）、音乐边界提交的 selection request（SR-D11/D23）、以及 Project 级
录音会话机制（writer lease、耐久 journal 链、幂等 flush、指纹门控恢复，
SR-D20–D22）。Stage 10 的设计原则是**复用而非平行发明**：Performance 录制
不重建第二套会话/时钟/恢复机制。

## 2. 继承的既定约束（不需要重新评审）

| 来源 | 约束 |
| --- | --- |
| 新内核规格 §7 | 八种首版 FX 名单；`Hold` 显式状态；Resample 闭环 `Sound → Pad → Pattern → Performance → New Sound`。 |
| 新内核规格 §8 | Performances 是用户可见 Beat Project 的一部分。 |
| 新内核规格 §6.3 | Pattern 切换在 Beat / Bar / Pattern End，默认下一 Bar。 |
| 新内核规格 §6.6 | Pattern 事件引用 Pad Slot（Bank + Pad 位置）；冻结声音属于 Resample。 |
| 新内核规格 §11.4 | 录音路径：Audio Thread → lock-free Capture Ring → Background Writer → Immutable Audio Artifact → Authoring Command → Project Revision。 |
| 新内核规格 §12.1 | `ResamplePerformance` 是 Facade Command，必须原子并带 Expected Project Revision。 |
| SR-D25 | 整数有理数传输时钟是权威；Performance Events 的时间戳同样禁止浮点。 |
| SR-D11 / SR-D23 | 音乐边界提交的 selection request 语义与「禁止点击瞬间换目标、播放另候边界」的反模式。 |
| 2026-08-24 斜坡决策 | 渲染路径零分配 / 零锁 / `noexcept`；FX 与录制不得破坏该契约。 |
| 2026-08-23 决策第 6 条 | 音频形态导出位于 Sequence 身份之外，属本阶段另行决策（#384/#385/#387 即该决策）。 |
| CLAUDE.md 不变量 | Host 只用 Facade；Runtime Snapshot 永不持久化为 Project Truth；Provider 失败属 Attempt 状态。 |

## 3. 开放问题绑定

| ID | GitHub Issue | 一句话 | 阻塞的章节 |
| --- | --- | --- | --- |
| P10-Q1 | #383 | 八种 FX 与 Hold 的归属和离线复现确定性 | §4 P10-D5–D7、§7、§9 |
| P10-Q2 | #384 | Performance 对象的事件词汇、会话复用与 Contract 影响 | §4 P10-D8–D10、§6、§9 |
| P10-Q3 | #385 | ResamplePerformance 是现场捕获还是离线重渲染 | §4 P10-D11、§7 |
| P10-Q4 | #386 | Bank 切换的状态分类与四 Bank 驻留 | §4 P10-D4、§8 |
| P10-Q5 | #387 | Stereo WAV 录制在 Web/OPFS 的有界资源模型 | §4 P10-D12、§7 |

P10-Q4 与 #357（长素材 Bank 配额记账）互为约束，宜同场或先行决策。
P10-Q1 是 P10-Q3 的范围裁剪输入：若 Resample 走现场捕获，FX 离线确定性可以
降级为后续目标；若走离线重渲染，它是硬前置。

## 4. 提议决策（草案，逐条待评审）

| ID | 提议 | 依赖 |
| --- | --- | --- |
| P10-D1 | Stage 10 启用 Mode Rail 的 Perform 模式，继承 Stage 7 Creator Shell 与完整 4×4 Pad 平面；Sample / Sequence 行为不变。 | — |
| P10-D2 | Pattern Launch 复用 SR-D11/D23 的 selection request 机制：默认下一 Bar 生效，生效前仍听旧 Pattern；Perform 不引入第二套切换语义。首版仅暴露 Bar 边界，Beat / Pattern End 由规格 §6.3 保留给后续。 | #376 修复落地 |
| P10-D3 | Perform 演奏与 Launch 的对象就是同一批 16 个 Pattern 槽与 64 个 Pad；Perform 不创建平行的「演出版 Pattern」真相。 | — |
| P10-D4 | Bank 切换是瞬时的 Host/Runtime 视图切换（换的是手指能摸到的 Pad，不是已调度的声音），不进 Project Truth；为保证无缝，四个 user Bank 保持单代全驻留。 | 〔待 #386〕 |
| P10-D5 | 八种 FX 是母线级瞬时效果：按下生效、松开还原，`Hold` 是显式锁存开关而非长按计时。FX 手势不写 Project Truth 配置。 | 〔待 #383〕 |
| P10-D6 | FX 的 DSP 状态与缓冲在 Snapshot 发布时预分配，音频线程零分配；每种 FX 有固定内存与 CPU 预算上限。 | 〔待 #383〕 |
| P10-D7 | FX 手势作为 Performance Events 记录（含 Hold 进入/退出），回放时以事件重现；live 与 replay 的一致性规则由 #383 决策定义。 | 〔待 #383〕 |
| P10-D8 | Performance 是 Project Truth 中的命名对象：一条整数 tick 时间戳的事件流（Pad 击打、Pattern Launch、Bank 切换、FX 手势），事件引用 Slot/Pattern 身份，不引用 Asset。 | 〔待 #384〕 |
| P10-D9 | Performance 录制会话复用 Stage 9 的 Project 级会话机制（writer lease、耐久 journal、`session_id + flush_seq + command_id` 幂等 flush、指纹门控恢复），以新 session kind 区分；同一 Project 同时至多一个录制会话——Perform 录制与 Sequence 录制互斥。 | 〔待 #384〕 |
| P10-D10 | Replay 的有效性由录制时引用对象的 canonical fingerprint 门控（对齐 SR-D22）：引用的 Pattern/Pad 已删除或不兼容变化时 fail closed 并明示，不静默近似回放。 | 〔待 #384〕 |
| P10-D11 | ResamplePerformance 首版走现场捕获：录制期间母线经 §11.4 路径落为 Immutable Audio Artifact，Resample 对其做范围选择并派生新 Asset（记 Lineage、用户选目标 Pad、永不自动覆盖）；离线重渲染保留为后续能力。 | 〔待 #385、#383〕 |
| P10-D12 | Stereo WAV 录制为 PCM16 48 kHz 流式写 OPFS，有界 ring + 后台写手；写手落后到界限时按 SR-D17 先例干净封存（已耐久前缀有效），实时渲染永不 glitch。 | 〔待 #387〕 |
| P10-D13 | CLI、MCP、Native、Web Runtime、Creator 通过同一 Facade 表面暴露 Perform 语义；无 UI 的 Host 能完整驱动录制、回放与 Resample。 | — |

## 5. 明确非目标（草案）

- Song Mode / Arrangement / Set List。
- FX 参数自动化曲线、每 Pad insert FX、发送式效果链。
- Performance 的量化 / 编辑 / Piano Roll；Performance 只能整体或按范围使用。
- MIDI 时钟同步、Ableton Link、外部 transport。
- Learn / Arcade 的保护分层（`docs/prd/questions/performance-arcade-protection-tiers.md`，Stage 3）。
- 云端分享、发布、社区；导出仍是本地文件。
- 推翻 Stage 9 的 Sequence 身份与并发分类；Perform 不给 Sequence 增加新的 rebase 白名单项。
- 分配 Product Build、改活动 manifest、改 Portal current 页（留给实施 Task）。

## 6. 身份与数据（草案，待 #384）

持久化（Project Truth）：

- Performance：id、名称、创建时的 BPM 锚点、事件流。
- 事件（候选词汇，最终以 #384 为准）：`pad_hit {slot, onset_tick, duration_tick, velocity}`、`pattern_launch {slot, effective_tick}`、`bank_switch {bank, tick}`（若 #386 判定需要记录）、`fx_gesture {fx, on/off/hold, tick}`。
- 引用一律指向 Slot / Pattern 身份，不指向 Asset（对齐 §6.6）。

不持久化到 Project：

- 当前 Bank 视图、FX 按下的瞬时状态、录制会话、journal、未确认恢复件。
- 任何 Runtime Snapshot 派生物。

Stereo WAV 与 Resample 产物的身份归属由 #384/#385/#387 决定后补写本节。

## 7. 会话与数据流（草案）

```text
演奏输入（Pad / Launch / Bank / FX）
  → Facade admission（writer lease 内，对齐 SR-D20）
  → Performance Journal（耐久，先于 Project 变更）
  → flush 边界（停录 / 停 Play / 显式保存）以幂等 Command 原子写入 Performance
  → Project Revision → 新 Runtime Snapshot
并行（录制开启时）：
母线渲染 → lock-free Capture Ring → Background Writer → OPFS WAV（P10-D12）
```

时间戳一律取自 Runtime 的整数 tick 时钟在 admission 处的读数（对齐 Stage 9
Web 时序纪律：Host JS 不提供 `runtime_frame` / `input_sequence`）。

## 8. 并发分类（草案）

- Perform 录制会话沿用 Stage 9 分类框架：BPM / Quantize / Swing 可 rebase
  白名单对 Perform 是否成立由 #384 评审（初判：BPM 改变影响 tick→墙钟映射，
  与 SR-D14 同理可 rebase）；Sample 类 Command 在 Perform 录制中失败但录制
  继续；未知 Command fail closed。
- Perform 录制 vs Sequence 录制：互斥（P10-D9）。开启一方时另一方的 begin
  返回 `INVALID_ARGUMENT`。
- Pattern Launch 在录制中既是被记录的事件也是真实的 Runtime 切换；两者共享
  同一 effective boundary（不允许「记了事件、播放另候边界」——SR-D23 的
  Perform 版）。

## 9. Contract 影响（草案）

- Performance 对象与事件词汇大概率要求 `lmdj.project.v4`（major）；是否可
  additive 由 #384 决定。v3→v4 迁移必须是确定性总迁移（对齐 SR-D19/D28 的
  先例），旧 Project 无 Performance 时迁移为空集合。
- FX 若引入 Project 级配置（#383 选项 b）则进一步扩大 v4；选项 a 下 Contract
  只增加事件词汇。
- `lmdj.patch.v1` / `lmdj.materials.v1` 仍禁止复活。

## 10. 测试清单（草案，实施计划再展开为逐条 RED-GREEN）

1. Perform 模式启用且 Sample/Sequence 回归不变（Mode Rail enablement）。
2. Pattern Launch 默认下一 Bar 生效；生效前听旧 Pattern；边界上原子切换。
3. 录制中 Pattern Launch 被记录且与实际切换边界一致（SR-D23 Perform 版）。
4. Bank 切换瞬时、无准备延迟、无 glitch；不占 Project revision〔#386〕。
5. 每种 FX：按下可闻、松开还原、Hold 锁存显式可见；渲染线程零分配守卫。
6. FX 手势事件的 live 与 replay 一致性〔#383 规则〕。
7. Performance flush 幂等：重复 `command_id` 返回原 receipt。
8. 崩溃 / owner 丢失：已提交 flush 有效、tail 封存、下次打开提示恢复。
9. Replay 指纹门控：引用 Pattern 变化后 fail closed 并明示〔#384〕。
10. Perform 与 Sequence 录制互斥；第二 begin `INVALID_ARGUMENT`。
11. Stereo WAV：长录制流式落 OPFS；写手落后时封存且前缀可用〔#387〕。
12. WAV 录制全程实时渲染无 glitch（stress 层）。
13. ResamplePerformance：范围选择 → 派生 Asset → Lineage → 用户选 Pad；
    取消/失败不改 Project、Asset、Pad 或 revision〔#385〕。
14. Resample 产物落 Pad 的配额准入对齐 #341/#357 决策。
15. CLI/MCP 黑盒驱动完整「录制 → 回放 → Resample」旅程，与 Creator 同语义。
16. v3→v4 迁移跨语言 golden vectors〔#384〕。

## 11. Version Management

Version impact: none（本文是设计草稿，不改代码、Contract 工件、manifest 或
Product Build）。实施时的版本支付在 Stage 10 实施计划的 `## Version
Management` 中精确分配：预计含 `lmdj.project.v4`（major）、authoring-domain /
project-io / project-cooker / audio-runtime / application-facade /
web-runtime-platform 的 SemVer 级联与新 Product Build。

## 12. Documentation Impact

本草稿合入：Documentation impact: none（新增 spec 草稿与问题文件，不改
Portal current 页与活动 manifest）。

设计定稿与实施：required——新内核规格 §7 如需勘误随决策文件同 Task 更新；
Portal 的 Perform 相关 current 页与源图在实施 Task 内更新；Product Build /
Assembly 变更必须做 immutable snapshot。

## 13. 拒绝的替代（草案）

### 13.1 为 Perform 建平行的「演出 Pattern」副本

违反单一 Project Truth；Koala 与 Sampler 惯例都是演同一批 Pattern。P10-D3。

### 13.2 FX 作为回放时重排/重算旧事件的全局效果

与 SR-D27（Swing 录入时烘焙）同类教训：回放时重算破坏确定性与跨语言向量。
FX 的作用点必须在渲染，不在事件改写。

### 13.3 第二套 Performance 专用时钟或浮点时间戳

SR-D25 已裁决整数有理数时钟是唯一权威；引入第二套时钟制造漂移与合并噩梦。

### 13.4 Hold = 长按计时阈值

规格 §7 明文要求显式状态；隐式计时在触屏与 MIDI 上不可预测且不可测试。

### 13.5 录制 WAV 全量驻留内存再一次性写盘

512 MiB 固定堆下数分钟录制必然越界；与 #357 记账冲突。必须流式（P10-D12）。

## 14. 实施入口（前置条件）

Stage 10 实施计划在以下条件全部满足后才可编写并动工：

1. Stage 9 remediation 关闭：#371（伞）、#372–#376，及 #379/#380 的版本
   整合与快照——评审已裁定修复前 1.0.37.0 不得越过 canary。
2. P10-Q1–Q5（#383–#387）各自有已合入的 `docs/prd/decisions/` 决策文件，
   对应问题文件按约定在同一 Task 删除。
3. 本文按 brainstorming 评审逐节批准、状态行更新为已批准，提议决策去掉
   `〔待 #NNN〕` 标注或按决策改写。
4. 实施回归每 Task 一个 PR 的模型（Stage 9 评审的流程结论）。
