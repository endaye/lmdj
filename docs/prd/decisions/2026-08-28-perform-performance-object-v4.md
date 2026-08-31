# 已确认：Performance 是 lmdj.project.v4 的命名事件流对象，复用 Stage 9 会话机制且与 Sequence 录制互斥；Replay 按当前 Project 回放、不做指纹门控

- 日期：2026-08-28
- 2026-08-31 修订：Pattern 槽 authority、耐久 draft、stop/save/discard、恢复、
  两阶段 rebase 与精确 Facade shape 由
  [`2026-08-31-stage10-performance-contract-repair.md`](2026-08-31-stage10-performance-contract-repair.md)
  补充；冲突处以后者为准。
- 解决的问题：`docs/prd/questions/perform-performance-object-persistence.md`
  （问题文件已按约定在本决策的同一个 Task 删除），GitHub Issue
  [#384](https://github.com/endaye/lmdj/issues/384)。
- 结论：
  1. **Performance 进 Project Truth，Contract 升 v4。** Performance 是命名
     产品对象（重设计规格 §8 用户可见 Project 的一部分）。实施时新增
     `lmdj.project.v4`（Contract major），v3→v4 是确定性总迁移，旧 Project
     迁移为空 `performances`（SR-D19/D28 先例）。
  2. **事件词汇。** Performance 是整数 tick 时间戳（SR-D25 时钟）的事件流：
     - Pad 击打 `{slot, onset_tick, duration_tick, velocity}`（与 Pattern
       事件同型，slot 自描述 Bank+Pad）；
     - Pattern Launch `{pattern_slot, effective_tick}`，记录在**已确认的
       生效边界**上，与 Runtime 实际切换同点（SR-D23 口径）；
     - FX 手势与全局 HOLD 事件，按
       [同日 FX 决策](2026-08-28-perform-momentary-fx-transient-gestures.md)
       第 2/3 条；
     - **无** Bank 切换事件
       （[同日 Bank 决策](2026-08-28-perform-bank-switch-view-state.md)）。
  3. **录音 Artifact 引用。** 演出期间捕获的 Stereo WAV（见
     [同日 WAV 决策](2026-08-28-perform-stereo-wav-host-streaming.md)）保存
     为不可变、内容哈希的 Artifact，由 Performance 引用并记 Lineage；删除
     Performance 后该 Artifact 依既有 GC 规则回收。
  4. **会话机制按 session kind 泛化 Stage 9。** Performance 录制会话复用
     writer-lease 内 admission、耐久 journal 链、
     `session_id + flush_seq + command_id` 幂等 flush、封存与指纹门控恢复
     （SR-D20–D22）的同一套机制，以新 session kind 区分。**一个 Project
     同时至多一个录制会话**：Perform 录制与 Sequence 录制互斥，后到的
     begin 返回 `INVALID_ARGUMENT`。录音中并发 Command 沿用 Stage 9 分类
     框架（可 rebase 白名单、Sample 类失败但录制继续、未知 fail closed）；
     白名单对 Perform 会话的逐项适用性在 Stage 10 设计评审逐条确认。
  5. **Replay 按当前 Project 回放，不做指纹门控。** Replay 是只读回放，
     沿 Sampler 惯例（SR-D4：换采样后以新音色回放）对**当前** Project 状态
     重放事件流：换过的 Pad 出新声音；引用已删除 Pattern 的 Launch 该段
     落空并以非致命方式提示。指纹门控只保留在**写回真相**的恢复路径
     （SR-D22）。演出的冻结版本由录音 WAV 承担，不由事件回放伪造。
  6. **与 Koala 的分歧明示。** Koala 没有事件级 Performance 录制/回放——
     其 Record a Song（手册 §6.2）只产出音频。「Performance Events +
     Replay」是重设计规格 §7/§8 授权的 LMDJ 自有扩展；Koala 对位路径由
     第 3 条的 WAV 录音覆盖。
- 原因：事件与音频双轨使「回放跟当前 Project、冻结靠 WAV」各得其所，避免
  回放指纹门控把「换个采样」变成整场演出不可回放；复用 Stage 9 会话机制
  避免第二套时钟/耐久/恢复语义；互斥来自「一个 Project 一个 active 录制
  会话」的既有不变量的自然扩展。
- 影响：本决策为纯文档权威，不改活动 manifest、Contract 工件、模块版本或
  Product Build。实施时支付：`lmdj.project.v4`（major）与总迁移、
  authoring-domain / project-io（journal session kind 泛化）/
  project-cooker / application-facade / 各 Host 的 SemVer 级联、新
  Product Build；跨语言 golden vectors 覆盖 v3→v4 迁移与事件词汇。Stage 10
  规格草稿 P10-D8–D10 与 §6 在同一 Task 按本决策改写（P10-D10 原
  指纹门控提案被本条第 5 款替代）。关闭 #384。
