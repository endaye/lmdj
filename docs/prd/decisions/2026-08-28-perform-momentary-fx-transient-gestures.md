# 已确认：Momentary FX 是母线级瞬时 Runtime 状态；手势是连续滑条参数流、HOLD 是全局显式模式、串联链序进 Contract；Project Truth 零 FX 配置

- 日期：2026-08-28
- 2026-08-31 修订：FX quantum 合并、raw input 时间权威与 owner-loss 闭合由
  [`2026-08-31-stage10-performance-contract-repair.md`](2026-08-31-stage10-performance-contract-repair.md)
  补充；Core 是唯一语义合并权威，Host 不决定事件取舍。
- 解决的问题：`docs/prd/questions/perform-momentary-fx-ownership.md`
  （问题文件已按约定在本决策的同一个 Task 删除），GitHub Issue
  [#383](https://github.com/endaye/lmdj/issues/383)。
- 结论：
  1. **归属：瞬时 Runtime 状态（选项 a）。** 八种 FX（重设计规格 §7）作用于
     母线，是按下生效、松开还原的瞬时状态。Stage 10 的 Project Truth 不含
     任何 FX 配置字段；FX 的可用集合与参数标度由 Contract 固定，不是用户
     数据。Project 级 FX 预设（选项 b）不实施、不预留字段，将来若需要走
     新决策。
  2. **手势是连续滑条参数流，不是开关。** 对照 Koala 手册 §6.3/§9.1：每个
     FX 是一根 bar，触点位置即参数值。手势事件为
     `engage(fx, value)` / `move(fx, value)` / `release(fx)` 三类，值量化为
     整数标度（拟 0–1000，精确标度与采样密度在实施计划锁定），时间戳一律
     取 SR-D25 整数 tick 时钟在 admission 处的读数。节拍锁定类 FX
     （如 Stutter）的值按拍分段语义解释；双向类 FX（如 Filter 的
     high-pass/low-pass）以带符号的中点偏移编码。
  3. **HOLD 是一颗全局显式模式按钮。** 对照 Koala 手册 §6.3/§2.3：HOLD 开启
     时，松开的 FX 冻结在松手时的值而不还原；HOLD 关闭时全部冻结 FX 释放。
     事件为全局 `hold_on` / `hold_off`。不做逐 FX latch，不做长按计时阈值。
  4. **固定串联链序是 Contract 不变量。** 对照 Koala「signal flows left to
     right, top to bottom」：八 FX 以 Contract 钉死的固定顺序串联；全部 FX
     可同时激活（多点触控）；CPU 预算按八效全开取最坏情形。
  5. **确定性规则。** live 渲染、Performance Replay 与将来任何离线渲染执行
     同一段引擎 DSP 代码；给定相同的 Runtime Snapshot、相同的整数手势事件流
     与相同链序，输出样本级一致。DSP 状态与缓冲（Delay/Reverb 等）在引擎/
     Snapshot 准备阶段预分配，`render` 保持零分配、零锁、`noexcept`
     （[2026-08-24 斜坡决策](2026-08-24-render-path-amplitude-ramp.md)先例）。
     这是实时路径首次引入 DSP，不与
     [2026-08-26 D2](2026-08-26-long-material-quota-and-bpm-stretch.md)
     冲突——该条钉死的是 time-stretch/pitch 不进实时引擎，维持不变。
  6. **命名事项移交 spec 评审（不在本决策内裁决）。** 规格 §7 的 "Roll" 在
     Koala 的 16 个 perform FX 中无对位物（最近为 CUTTER/STUTTER）；Koala 的
     Delay 分 DUB 与 TEMPO DELAY 两种而规格只列一个 Delay。八 FX 名单以
     规格为权威，其逐项定义与可能的更名在 Stage 10 设计评审确认。
- 原因：选项 a 使 v1 Contract 面最小且与「录下即听到」的 Resample 语义自洽
  （见[同日 Resample 决策](2026-08-28-perform-resample-live-capture.md)）；
  选项 c 的「live 近似、离线权威」与现场捕获冲突被否定。连续滑条、全局
  HOLD 与固定链序均为 Koala 实测行为，简化为开关会使录下的手势无法还原
  演出。
- 影响：本决策为纯文档权威，不改活动 manifest、Contract 工件、模块版本或
  Product Build。实施时支付：`audio-runtime`（八 FX DSP 与预分配）、
  Performance 事件词汇中的 FX 手势事件（归
  [Performance 对象决策](2026-08-28-perform-performance-object-v4.md)的
  v4 Contract）、各消费模块 SemVer 级联。Stage 10 规格草稿的 P10-D5–D7 与
  §6 事件词汇在同一 Task 按本决策改写。关闭 #383。
