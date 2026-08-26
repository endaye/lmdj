# 已确认：Stage 9 Sequence 录音只写 Pattern 事件、无 Take 对象；录音并发按分类处理，恢复由指纹门控

- 日期：2026-08-23
- 解决的问题：`docs/prd/questions/take-event-vs-audio-bounce.md` 与
  `docs/prd/questions/recording-concurrency-semantics.md`（两个问题文件已按约定
  在本决策的同一个 Task 删除），GitHub Issue
  [#238](https://github.com/endaye/lmdj/issues/238)（D4 + D5），落地 Task
  [#266](https://github.com/endaye/lmdj/issues/266)。完整设计与逐条批准记录见
  [2026-08-22 Sequence 录音语义设计](../../superpowers/specs/2026-08-22-sequence-recording-semantics-design.md)
  （SR-D1–D28），本文只固化产品权威结论，不重复全部细节。
- 结论：
  1. **Take 范围（D5）：只有事件，没有 Take。** Project Truth 只保存 Pattern
     事件 `{slot, onset_tick, duration_tick, velocity}`。不存在 Raw Take /
     Take 产品对象，不生成录音会话的音频 bounce，不保留第二份未吸格档案。
     产品与 Facade 语言是「录 Sequence / Pattern」，Take 一词退出产品表面。
     （SR-D1–D5）
  2. **新 Project Contract。** 实施时新增 `lmdj.project.v3`（Contract SemVer
     `3.0.0`）：删除 required `takes` 与 raw-take 定义；事件由 step 改为
     tick-native（PPQ 960，1/16 = 240 tick）；`quantize_enabled` 与
     `swing_percent`（50–75，默认 50）成为 Project Truth。v2→v3 是确定性的
     总迁移，禁止以空 `takes: {}` 假装兼容。（SR-D19、SR-D28）
  3. **录音并发（D4）：分类，不是一刀切。** Proof 的「任何 revision 变化均
     冲突并封存 Take」不得作为产品规则，仅保留为 Proof 安全规则。会话是
     Project 级的，一个 Project 同时只有一个 active Sequence session，落在
     bundle Journal 上、受 writer lease 保护，admission 在同一把写锁内完成。
     选择性 rebase 是封闭白名单：BPM、Quantize/Swing、以及进行中的 Pad
     Capture 提交到已武装的目标 Pad；Sample 类 Command 在录音中失败但录音
     继续、不封存；未知 Authoring Command fail closed。（SR-D14、SR-D16、
     SR-D18、SR-D20）
  4. **Flush 幂等与确定性时钟。** 每次 flush 有稳定
     `session_id + flush_seq + command_id`，先耐久写 Journal 意图再写
     Project；只有 manifest head 已原子发布且 reload 可见 receipt 才算
     completed。musical tick 由整数有理数锚点积分，禁止浮点时钟。
     （SR-D21、SR-D25）
  5. **恢复由指纹门控，且判定顺序钉死。** 恢复写回以目标 Pattern 的
     canonical fingerprint 为门，新鲜 revision 不单独构成写回理由。判定
     优先级固定为：目标 Pattern 已删除或恢复事件越界（`bars` 变短）时
     fail closed 并保留恢复件，**先于**「fingerprint 不一致 → 用户选新槽或
     放弃」的选择；实现须在
     [#267](https://github.com/endaye/lmdj/issues/267) /
     [#268](https://github.com/endaye/lmdj/issues/268) 提供跨语言共享测试
     向量锁定该顺序。（SR-D17、SR-D22 及 #266 补充验收）
  6. **Export Pack 影响。** Export Pack 只从 Project Truth（v3 Pattern 事件）
     派生，不包含任何录音会话音频产物。音频形态的导出属于后续 Resample /
     Perform Stereo WAV 工作，位于 Sequence 身份之外，另行决策。
     （#266 补充验收）
- 原因：用户演奏对标 Koala Sequence——Sequence 的身份是音符引用 Pad Slot，
  换采样后跟新声音走；冻结声音属于 Resample，不属于 Sequence。Proof 的严格
  冲突规则会把无关 Command 或 MCP 写入变成整轨演奏被封存，不可用作产品体验；
  而通用 auto-rebase 会破坏确定性。事件-only 的 Take 范围使白名单 rebase
  成立，两个问题互为前提，故在 #238 的同一次评审解决。
- 影响：本决策为纯文档权威，不改活动 manifest、Contract 工件、模块版本或
  Product Build。版本影响在实施时支付：`lmdj.project.v3`、相关 Core Module
  与 Host 的 SemVer 主版本、Product Build `1.0.37.0`，精确分配见
  [实施计划](../../superpowers/plans/2026-08-23-lmdj-stage9-sequence-recording.md)
  的 Version Management。重设计规格
  [§6.2 / §6.5 勘误](../../superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)
  与 `products/lmdj/README.md` 的 Proof-only 并发说明在同一 Task 更新；
  Quantize / Swing 由「非破坏」改为录入时破坏性烘焙进之后的新事件。实施
  工作项：umbrella [#265](https://github.com/endaye/lmdj/issues/265) 与
  Task Issues #266–#275；本决策合入后关闭 #238，产品代码 Task（#267 起）
  解除阻塞。
