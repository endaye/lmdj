# Performance 产品对象记录哪些事件、复用 Stage 9 SequenceJournal 还是新会话类型、是否需要 lmdj.project.v4？

- 范围：Stage 10 Perform
- GitHub Issue: #384
- 来源：[2026-07-30 新内核设计](../../superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md) §8 把 Performances 列入用户可见 Project；[2026-08-23 Stage 9 决策](../decisions/2026-08-23-sequence-recording-semantics.md)明确把音频形态的导出（Resample / Perform Stereo WAV）排除在 Sequence 身份之外并要求另行决策。
- 为什么重要：`lmdj.project.v3` 没有任何 Performance 对象。事件词汇（Pad 击打、Pattern Launch、Bank 切换、FX 手势）、与 Stage 9 会话机制（writer lease、耐久 journal 链、幂等 flush、指纹门控恢复）的复用边界、Perform 录制与 Sequence 录制会话能否共存、以及 Replay 面对已变化 Project 的有效性门控，都是 Contract 级问题，不能在实施 Task 里静默决定。
- 处理时点：Stage 10 实施计划之前。
