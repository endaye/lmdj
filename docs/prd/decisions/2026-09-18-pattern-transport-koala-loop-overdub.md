# 已确认：Pattern transport 采用 Koala 式循环叠录，录制输入即时落盘且必须可恢复

- 日期：2026-09-18。
- 关联：GitHub issue [#1230](https://github.com/endaye/lmdj/issues/1230)
  的物理验收（row T1，Product Build `1.0.60.0`，revision `12e2adc1`）；本条
  确认两个此前未定的行为，并派生 issue #1513 与 #1515。

## 结论

1. **录制中的循环叠录是可闻的。** 一圈里录进去的内容，在**下一圈**就播放
   出来，不需要先关闭 Record。节拍不重起，循环边界无可闻断点；随后关闭
   Record 的提交仍然恰好一次，已经在响的那一遍不重复也不丢失。这就是
   Koala 的叠录逻辑，`#1230` 的六状态转换表从未涉及这一点。
2. **录制输入即时落盘，被打断的 take 以"录到哪儿停到哪儿"收尾。** 页面在
   录制中重载不再等同于丢弃：已经耐久 admit 的输入必须能恢复成 Pattern
   事件。重载瞬间仍未释放的按压按既有的 240-tick 默认形态收尾。
3. **"结果不可知"的拒绝只保留在真的有 cutoff fence 待裁决时。** 不得因为
   transfer 非终结就整条录制拒绝。

## 原因

- 引擎与 overlay 机制本就实现了这一语义，只是没接到全局 transport 的录制
  路径上：overlay 合并见
  [`prepared_sample_bank.cpp`](../../../packages/audio-runtime/src/prepared_sample_bank.cpp)
  的 `from_snapshot_with_overlay` / `merge_pattern_events`，Facade 投影见
  [`application.cpp`](../../../packages/application-facade/src/application.cpp)
  的 `query_sequence_overlay`，不带显式激活帧的发布落在下一个小节边界
  （[`realtime_engine.cpp`](../../../packages/audio-runtime/src/realtime_engine.cpp)，
  `activation_frame = origin + (bars + 1) * bar_frames`）。legacy Sequence
  路径每录一个 Pad 事件就发布一次 overlay；transport 路径只 admit，直到
  录制关闭才发布一次。
- 输入并未丢失：每个被 admit 的 Pad 事件在返回 `retained` 之前就已耐久
  追加（[`pattern_admission_controller.cpp`](../../../packages/application-facade/src/pattern_admission_controller.cpp)
  的 `append_admission_candidate`），换算所需的 timing profile 与 fence
  也都耐久（[`sequence_admission_codec.cpp`](../../../packages/project-io/src/sequence_admission_codec.cpp)）。
  缺的只是转换：`canonical_recovery_events` 从不读 `admission.candidates`。
- 现行拒绝的理由是 cutoff fence 结果不可知。该不确定性属于 **Stop 路径**：
  按下 Stop 时哪些尾部事件落在截止点之前，要由音频线程回执裁决。录制中
  重载没有 Stop，也就没有 cutoff 待裁决，却被同一条规则整条拒绝。
- 对一台演奏乐器而言，"录完必须停下来才听得到" 与 "刷新一次就只能丢弃"
  都不是可接受的取舍；两者同源，共用同一个转换器是预期形状。

## 影响

- 派生两个 issue，互为 relates，共用同一条转换逻辑的两端：#1513（录制**进行
  中**转换并发布，使当圈可闻）与 #1515（owner 丢失**之后**转换已落盘输入，
  使 take 可恢复）。本条只记录决策方向，不代表实现或验收完成。
- 物理验收 ledger
  [`2026-09-16-pattern-transport-physical-acceptance.md`](../../quality/2026-09-16-pattern-transport-physical-acceptance.md)
  新增 T-L7：既有 T-L6 只断言"叠加发生且第一遍完好"，在上述缺陷下照样通过，
  因此它不是这条行为的守门人。T-L7 绑定到 T1 与 T2 两行。
- T-N2 的措辞（"选 recover 保留已封存事件"）**不需要修改**：它本来就是正确
  的期望，当前实现不满足它，该行按 FAIL 记录，不得反向削弱断言去迁就实现。
- 三处现有测试把"诚实拒绝"钉死，改行为时必须有意识地改写而不是消音：
  `tests/platform/web/creator/creator_web_sequence.spec.mjs` 的
  `owner loss surfaces the interrupted recording for honest refusal and discard`、
  `tests/core/facade/sequence_surface_test.cpp` 与
  `tests/core/facade/pattern_transport_controller_test.cpp` 中断言
  `sequence_admission_unresolved` 的用例。
- 本条不分配 Product Build，不改动任何 Contract、模块版本或 Project Truth
  形状；版本影响由各自 issue 的实施计划评估。
