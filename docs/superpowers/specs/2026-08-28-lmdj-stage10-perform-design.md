# LMDJ Stage 10 Perform Design — 2026-08-28

日期：2026-08-28

修订：2026-08-28 同日第二版——P10-Q1–Q5 已由五个决策文件解决（#383–#387），
按 Koala 官方手册核对后 FX 改为连续滑条手势流、HOLD 改为全局显式模式、串联
链序进 Contract、Replay 改为按当前 Project 回放。2026-08-29 设计评审——
逐节批准全文；裁决四项待评审事项为 P10-D14–D17（FX 名单定版 Roll→Cutter、
整数标度与合并密度、Perform rebase 白名单、表面布局）；`pattern_launch`
定为引用槽位 index；重设计规格 §7 勘误同 Task 落笔。

状态：**已批准**——2026-08-28/29 brainstorming 评审逐节批准（P10-Q1–Q5 由
2026-08-28 决策文件裁决，其余章节与 P10-D14–D17 由 2026-08-29 评审裁决）。
本文定义 Stage 10 Perform 的产品与 Contract 边界，不分配 Product Build，
不改产品代码。

已解决的关联问题：
[#383](https://github.com/endaye/lmdj/issues/383)
[#384](https://github.com/endaye/lmdj/issues/384)
[#385](https://github.com/endaye/lmdj/issues/385)
[#386](https://github.com/endaye/lmdj/issues/386)
[#387](https://github.com/endaye/lmdj/issues/387)

## 1. 结论

Stage 10 把已经能录 Sequence 的乐器变成能**演出**的乐器：在 Perform 表面上
现场演奏 Pad、按音乐边界切换 Pattern、瞬时切换 Bank、以连续滑条手势施加
瞬时 FX，并把整场演出记录为「事件流 + 母线 WAV」双轨的 Performance——
事件流可按当前 Project 回放，WAV 是演出的冻结版本与 Resample 素材。

Stage 10 的成功命题是：

> 用户可以在不绕过 Application Facade、不产生第二份 Pattern 真相、不打断
> 实时渲染的前提下，现场演出一段 Beat，事后完整回放它，并把它（或其中一段）
> 变成新的 Pad 声音。

新内核规格 §7 是范围权威。Stage 9 交付的三块地基——整数有理数传输时钟
（SR-D25）、音乐边界提交的 selection request（SR-D11/D23）、Project 级
录音会话机制（SR-D20–D22）——Stage 10 全部复用而非平行发明。

Koala 官方手册（§2/§4/§5/§6/§9，2026-08-28 核对）是产品对照权威：Perform
FX 是作用于全混音的连续滑条、HOLD 是全局按钮、Record a Song 绑定
transport、resample 是含 live FX 的现场捕获、Bank 是即时视图切签。

## 2. 继承的既定约束（不需要重新评审）

| 来源 | 约束 |
| --- | --- |
| 新内核规格 §7 | 八种首版 FX 名单（2026-08-29 勘误后含 Cutter）；`Hold` 显式状态；Resample 闭环 `Sound → Pad → Pattern → Performance → New Sound`。 |
| 新内核规格 §8 | Performances 是用户可见 Beat Project 的一部分。 |
| 新内核规格 §6.3 | Pattern 切换在 Beat / Bar / Pattern End，默认下一 Bar。 |
| 新内核规格 §6.6 | Pattern 事件引用 Pad Slot（Bank + Pad 位置）；冻结声音属于 Resample。 |
| 新内核规格 §12.1 | `ResamplePerformance` 是 Facade Command，原子并带 Expected Project Revision。 |
| SR-D25 | 整数有理数传输时钟是权威；Performance Events 时间戳禁止浮点。 |
| SR-D11 / SR-D23 | 音乐边界提交的 selection request 与「禁止记录点和生效点分离」。 |
| 2026-08-24 斜坡决策 | 渲染路径零分配 / 零锁 / `noexcept`。 |
| 2026-08-26 D1 + 2026-08-28 记账修正案 | ingest（Host 层）/ prepared（Core 层）两层素材模型；Bank/Project/驻留三个命名量（`maximum_user_bank_bytes` / `maximum_generation_bytes` / `maximum_resident_bytes`）；选区 commit 与 Capture/导入同路径。 |
| 2026-08-26 D2 | time-stretch / pitch 永不进实时引擎（与 Stage 10 引入 FX DSP 并存，互不推翻）。 |
| CLAUDE.md 不变量 | Host 只用 Facade；Runtime Snapshot 永不持久化为 Project Truth；Provider 失败属 Attempt 状态。 |

## 3. 已解决的问题绑定

| ID | Issue | 决策文件 |
| --- | --- | --- |
| P10-Q1 | #383 | [`2026-08-28-perform-momentary-fx-transient-gestures.md`](../../prd/decisions/2026-08-28-perform-momentary-fx-transient-gestures.md) |
| P10-Q2 | #384 | [`2026-08-28-perform-performance-object-v4.md`](../../prd/decisions/2026-08-28-perform-performance-object-v4.md) |
| P10-Q3 | #385 | [`2026-08-28-perform-resample-live-capture.md`](../../prd/decisions/2026-08-28-perform-resample-live-capture.md) |
| P10-Q4 | #386 | [`2026-08-28-perform-bank-switch-view-state.md`](../../prd/decisions/2026-08-28-perform-bank-switch-view-state.md) |
| P10-Q5 | #387 | [`2026-08-28-perform-stereo-wav-host-streaming.md`](../../prd/decisions/2026-08-28-perform-stereo-wav-host-streaming.md) |

决策文件是产品权威；本文与其冲突处以决策文件为准并回评审勘误。

## 4. Approved Decisions

| ID | 决策 | 依据 |
| --- | --- | --- |
| P10-D1 | Stage 10 启用 Mode Rail 的 Perform 模式，继承 Stage 7 Creator Shell 与完整 4×4 Pad 平面；Sample / Sequence 行为不变。 | 规格 §4 |
| P10-D2 | Pattern Launch 复用 SR-D11/D23 selection request：默认下一 Bar 生效，生效前仍听旧 Pattern。首版仅暴露 Bar 边界；Beat / Pattern End 保留给后续（Koala SEQ SNAP 有 OFF/BEAT/BAR/SEQ END 四档，LMDJ 首版收缩）。 | 规格 §6.3；#376 机制 |
| P10-D3 | Perform 演奏与 Launch 的对象就是同一批 16 个 Pattern 槽与 64 个 Pad；不创建「演出版 Pattern」副本。 | 单一 Project Truth |
| P10-D4 | Bank 切换是瞬时 Host/Runtime 视图状态：不进 Project Truth、不走音乐边界、不记录事件（slot 自描述）；四个 user Bank 维持单代全驻留（与 2026-08-28 记账修正案 A1 一致：一个 generation 物化全部 64 Pad）。 | #386 决策 |
| P10-D5 | 八种 FX 是母线级瞬时状态，Project Truth 零 FX 配置。每个 FX 是连续滑条：手势事件为 `engage/move/release` 带整数量化参数值，时间戳取整数 tick 时钟 admission 读数；节拍锁定类按拍分段解释，双向类以带符号中点偏移编码。 | #383 决策 1/2 |
| P10-D6 | HOLD 是一颗全局显式模式按钮：开启时松手的 FX 冻结当前值，关闭时全部释放；事件为全局 `hold_on`/`hold_off`。无逐 FX latch，无长按计时。 | #383 决策 3 |
| P10-D7 | 八 FX 以 Contract 钉死的固定顺序串联；全部可同时激活；DSP 状态与缓冲在 Snapshot/引擎准备阶段预分配，`render` 保持零分配零锁 `noexcept`；CPU 预算按八效全开取最坏情形。live 与 Replay 跑同一段 DSP，给定相同 Snapshot、事件流与链序输出样本级一致。 | #383 决策 4/5 |
| P10-D8 | Performance 是 `lmdj.project.v4` 的命名事件流对象（Pad 击打、Pattern Launch at effective tick、FX 手势与全局 HOLD；无 Bank 事件），并引用录音 Artifact。v3→v4 总迁移，旧 Project 得空 `performances`。 | #384 决策 1/2/3 |
| P10-D9 | Performance 录制会话按 session kind 泛化 Stage 9 机制（writer-lease admission、耐久 journal 链、幂等 flush、封存、指纹门控恢复）；一个 Project 同时至多一个录制会话——Perform 与 Sequence 录制互斥，后到 begin 返回 `INVALID_ARGUMENT`。 | #384 决策 4 |
| P10-D10 | Replay 是只读回放，按**当前** Project 状态重放（Sampler 惯例，SR-D4 延伸）：换采样出新声音、被删/空槽的 Launch 该段落空并非致命提示。Replay 不做指纹门控；指纹门控只在写回真相的恢复路径。冻结版本由 WAV 承担。 | #384 决策 5 |
| P10-D11 | ResamplePerformance v1 = 现场捕获：在演出录音 Artifact 上选区，经 D1 长源路径 commit（同配额判定、同 `BANK_QUOTA_EXHAUSTED`、同 revision 绑定），Lineage 记源哈希+范围+Performance 身份；无新 Job 类别。离线重渲染立为具名后续能力，届时也永不进实时引擎。 | #385 决策 |
| P10-D12 | Stereo WAV 录制是 Host 层母线 tap（镜像 Stage 8B worklet 批量模式，走 JS 堆）流式写 OPFS，PCM16 48 kHz；录制待命后由 PLAY 启动、停播即停录、停录后显式命名保存或丢弃；上限是 Host manifest `resource_limits` 数值；写手落后/出错/到顶时按 SR-D17 先例封存（已耐久前缀是合法 WAV），tap 永不阻塞 `render`。 | #387 决策 |
| P10-D13 | CLI、MCP、Native、Web Runtime、Creator 通过同一 Facade 表面暴露 Perform 语义；无 UI 的 Host 能完整驱动录制、回放与 Resample commit（Web 的 WAV tap 除外，属 Host 层能力）。 | 规格 §10.2 |
| P10-D14 | **FX 名单定版（2026-08-29 评审）**：Filter（中点双向 HP/LP 共振）、Delay（节拍同步立体声，Koala TEMPO DELAY 对位）、Reverb、Stutter（节拍同步 beat repeat，½–1/64 bar）、Gate（阈值门）、Reverse、Crush（降采样 bitcrush）、**Cutter**（原 Roll 更名，节拍同步静音门，1–1/64 bar，Koala CUTTER 对位）。八项逐一有 Koala 手册 §9.1 定义，零发明 DSP；重设计规格 §7 勘误同 Task 落笔。DUB 式长反馈 delay 留作后续 FX 扩展。 | 2026-08-29 评审 |
| P10-D15 | **值标度与密度（2026-08-29 评审）**：FX 参数值为整数 0–1000，双向类以 500 为中点、带符号偏移解释。`move` 事件按输入到达在 admission 记录；同 FX 连续同值去重；Host 合并至每 FX 每音频 quantum（128 帧 ≈ 2.67 ms）至多一条——高于任何触控/MIDI 报告率，等效无损，且给 v4 事件体积可证明上界。 | 2026-08-29 评审 |
| P10-D16 | **Perform rebase 白名单（2026-08-29 评审）**：Perform 会话的选择性 rebase 白名单 = {BPM、Quantize/Swing}。BPM 同 SR-D14（已记 tick 不动）；Quantize/Swing 可 rebase 但对 Perform 事件**零语义作用**——演出记录原始 timing，不吸格、不烘焙。武装 Pad capture 提交在 v1 Perform 白名单中**排除**，按 Sample 类处理（Command 失败、录制继续、不封存，Host 须先停录）；未知 Authoring Command fail closed。 | 2026-08-29 评审 |
| P10-D17 | **表面布局（2026-08-29 评审）**：中部 Surface 自上而下 = Pattern Launch 槽条（16 槽，含 pending 切换指示）→ 八根竖向 FX 滑条（视觉顺序即 Contract 链序，左→右）→ HOLD 按钮在 FX 区底部（Koala 同位）。WAV 录制状态与停录命名入口在顶部 transport；底部 4×4 Pad 平面不变。像素级细节归实施评审。 | 2026-08-29 评审 |

## 5. 设计评审裁决记录（2026-08-29）

原「待 spec 评审事项」五项全部裁决：

1. Roll 更名 Cutter、Delay 取节拍同步 → P10-D14（规格 §7 勘误同 Task）。
2. 整数标度 0–1000 与 quantum 级合并密度 → P10-D15。
3. rebase 白名单适用性与武装 capture 排除 → P10-D16。
4. 表面布局要素与相对位置 → P10-D17。
5. `pattern_launch` 引用**槽位 index（0–15）**而非 `pattern_id`：Replay 启动
   当下占据该槽的 Pattern，与 P10-D10、Koala 槽位模型、SR-D4 惯例自洽；
   空槽 Launch 落空静默（非致命）。Stage 9 切换 journal 内部使用
   `PatternId` 属恢复写回路径，用途不同，不冲突。

## 6. 身份与数据

持久化（Project Truth，v4）：

- Performance：id、名称、创建时 BPM 锚点、事件流、录音 Artifact 引用
  （可空：允许只录事件不开 WAV，或 WAV 被封存后丢弃）。
- 事件：`pad_hit {slot, onset_tick, duration_tick, velocity}`、
  `pattern_launch {pattern_slot(0–15), effective_tick}`、
  `fx_engage/fx_move {fx, value(0–1000), tick}`、`fx_release {fx, tick}`、
  `hold_on/hold_off {tick}`。
- 引用一律指向 Slot（Pad Slot 或 Pattern 槽位），不指向 Asset 或
  `pattern_id`（§6.6 口径与 P10-D10/§5.5 裁决）。
- `move` 事件经同值去重与 quantum 级合并（P10-D15）后进 journal 与 flush。

持久化（Artifact，非 Project 字段）：

- 演出 WAV：不可变、内容哈希；Resample 派生 Asset 记 Lineage
  （源哈希、范围、Performance 身份、录制时 revision）。

不持久化到 Project：

- 当前 Bank 视图、FX 触点瞬时状态、全局 HOLD 的当下开关、录制会话、
  journal、未确认恢复件、任何 Runtime Snapshot 派生物。

## 7. 会话与数据流

```text
演奏输入（Pad / Launch / FX 手势 / HOLD）
  → Facade admission（writer lease 内，SR-D20 口径；时间戳在此处取整数 tick）
  → Performance Journal（耐久，先于 Project 变更）
  → flush 边界（停录 / 停 Play / 显式保存）以幂等 Command 原子写入 Performance
  → Project Revision → 新 Runtime Snapshot
并行（WAV 录制开启时，Host 层）：
render 输出 → Worklet tap（批量 Float32，JS 堆）→ 有界队列 → OPFS 流式写手
```

Host JS 不提供 `runtime_frame` / `input_sequence`（Stage 9 Web 时序纪律
不变）。

## 8. 并发分类

- Perform 录制会话沿用 Stage 9 分类框架，白名单按 P10-D16：BPM 与
  Quantize/Swing 可 rebase（后者零语义作用）；Sample 类 Command（含武装
  Pad capture 提交）在 Perform 录制中失败但录制继续、不封存；未知
  Authoring Command fail closed。
- Perform 录制 vs Sequence 录制：互斥（P10-D9）。
- 录制中的 Pattern Launch 既是被记录的事件也是真实 Runtime 切换，共享同一
  effective boundary（SR-D23 的 Perform 版）；FX 手势不占 Project revision。
- Bank 切换不进 admission（纯视图，P10-D4）。

## 9. Contract 影响

- `lmdj.project.v4`（major）：新增 `performances` 与事件词汇；v3→v4 确定性
  总迁移；跨语言 golden vectors 覆盖迁移与事件不变量。
- FX 链序、0–1000 标度、事件边界与合并规则是 Contract 不变量，须有跨语言
  测试向量。
- 无 Project 级 FX 配置字段；`lmdj.patch.v1` / `lmdj.materials.v1` 仍禁止
  复活。

## 10. 测试清单（实施计划再展开为逐条 RED-GREEN）

1. Perform 模式启用且 Sample/Sequence 回归不变。
2. Pattern Launch 默认下一 Bar 生效；生效前听旧 Pattern；边界上原子切换。
3. 录制中 Pattern Launch 记录点与实际切换边界一致（SR-D23 Perform 版）。
4. Bank 切换瞬时、无准备延迟、无 glitch、不占 revision、不产生事件。
5. 每种 FX（含定版后的 Cutter）：滑条值可闻变化、松手还原；渲染线程零分配
   守卫。
6. 全局 HOLD：开启后松手冻结当前值、关闭全部释放；事件序列正确。
7. FX 链序确定性：同 Snapshot + 同事件流 → 样本级一致输出（live vs replay）；
   move 去重与 quantum 合并的边界向量。
8. 八效全开的 CPU/underrun 预算（stress 层）。
9. Performance flush 幂等：重复 `command_id` 返回原 receipt。
10. 崩溃 / owner 丢失：已提交 flush 有效、tail 封存、恢复候选出现（含硬
    崩溃路径——吸取 Stage 9 M2 教训，不以优雅关闭替代）。
11. Perform 与 Sequence 录制互斥；第二 begin `INVALID_ARGUMENT`。
12. Replay 按当前 Project：换采样出新声音；重排 Pattern 后 Launch 跟槽位；
    空槽落空且非致命。
13. Perform 录制中改 Quantize/Swing：rebase 成功、录制继续、事件 timing
    不受影响（P10-D16）；录制中武装 capture 提交失败且不封存。
14. v3→v4 迁移跨语言 golden vectors；旧 Project 得空 `performances`。
15. WAV：长录制流式落 OPFS；写手落后时封存且前缀是合法 WAV。
16. WAV 录制全程实时渲染无 glitch（stress 层）。
17. Resample：录音上选区 → D1 路径 commit → Lineage 正确；取消/失败不改
    Project、Asset、Pad 或 revision；`BANK_QUOTA_EXHAUSTED` 非破坏。
18. CLI/MCP 黑盒驱动「录制 → 回放 → Resample commit」完整旅程（验收旅程
    按本清单逐句核对，不按已实现功能剪裁）。
19. OPFS 持续写带宽物理 fixture（macOS Safari + 实体 iPadOS）。

## 11. Version Management

Version impact: none（本文与其引用的五个决策文件均为纯文档权威；规格 §7
勘误为文字更名，不触碰任何 Contract 工件）。实施时支付在 Stage 10 实施计划
的 `## Version Management` 精确分配：预计含 `lmdj.project.v4`（Contract
major）、audio-runtime（FX DSP）、authoring-domain / project-io /
project-cooker / application-facade / web-runtime-platform 及各 Host 的
SemVer 级联、`resource_limits` 新键（manifest 级，触发 Product Build 与
Portal 快照义务）、新 Product Build。

## 12. Documentation Impact

本批准修订合入：Documentation impact: none（不改 Portal current 页与活动
manifest；规格勘误是设计文档内部更名）。实施：required——Perform 相关
Portal current 页与源图在实施 Task 内更新；manifest / Product Build 变更
必须做 immutable snapshot。

## 13. 拒绝的替代

### 13.1 为 Perform 建平行的「演出 Pattern」副本

违反单一 Project Truth；Koala 也是演同一批 Sequence。

### 13.2 FX 建模为开关 + 回放时重算

Koala 的 FX 是连续滑条，开关模型无法还原演出；回放时重算与 SR-D27 同款
教训，破坏确定性。作用点在渲染，不在事件改写。

### 13.3 逐 FX latch 或长按计时阈值的 Hold

Koala 的 HOLD 是全局按钮；逐 FX latch 与计时阈值在触屏与 MIDI 上不可预测
且不可测试。

### 13.4 Replay 做指纹门控或引用 pattern_id

把「换个采样/挪个槽」变成整场演出不可回放，违背 Sampler 惯例（SR-D4）；
冻结需求由 WAV 承担。门控只留给写回真相的恢复路径。

### 13.5 第二套 Performance 专用时钟或浮点时间戳

SR-D25 已裁决整数时钟唯一权威。

### 13.6 录制 WAV 全量驻留内存再一次性写盘

512 MiB 固定堆下数分钟录制必然越界。必须流式（P10-D12）。

### 13.7 引擎级音频 capture ring（v1）

改实时代码、需 stress 层验证、扩大 Stage 10 范围；Host 层 tap 复用 Stage
8B 已交付模式即可。Native Host 到来时再评估统一 ring 的价值。

### 13.8 离线重渲染作为 v1 Resample 权威

使八 FX 离线复现成为硬前置、范围翻倍；Koala 的 resample 本就是现场捕获。

### 13.9 保留 Roll 名字或另行发明 Roll DSP

名字不变但用 CUTTER 语义会造成永久的文档-对照错位；自行发明无 Koala 对照
的 DSP 需要额外设计与听测，违背「零发明 DSP」的首版原则（P10-D14）。

### 13.10 Performance 事件受 Quantize 吸格

演出的身份是真实手感；吸格烘焙与「WAV 录的就是听到的」相悖（P10-D16）。

## 14. 实施入口（前置条件）

Stage 10 实施计划在以下条件全部满足后才可编写并动工：

1. Stage 9 remediation 关闭：#371（伞）、#372–#376，及 #379/#380 的版本
   整合与快照——评审已裁定修复前 1.0.37.0 不得越过 canary。
2. ~~P10-Q1–Q5 决策文件合入~~——已于 2026-08-28 完成（见 §3）。
3. ~~本文 brainstorming 评审逐节批准~~——已于 2026-08-29 完成（见 §5）。
4. 实施回归每 Task 一个 PR 的模型（Stage 9 评审的流程结论）。
5. ~~#357 的记账决策合入且与 P10-D4 一致~~——已于 2026-08-28 完成
   （PR #389，修正案 A1「一个 generation 物化全部 64 Pad」与 P10-D4
   一致；实施计划采用 A1 定死的 `RuntimePreparationLimits` 字段名）。
