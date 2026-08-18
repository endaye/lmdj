# 产品级录音并发语义如何定义：哪些无关 Command 不应触发冲突，是否允许选择性 rebase？

- 范围：新内核（Playable Beat Instrument）
- 状态：待设计评审
- 来源：[2026-07-30 新内核设计](../../superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)评审
- 为什么重要：Headless Core Proof 为保证确定性，暂用“任何 revision 变化均冲突并封存 Take”的严格规则；该规则不能替代用户产品中的冲突分类，仍会影响录音 Journal、Take 提交体验与公开 Contract。
- 处理时点：Sequence / Take Contract 进入用户产品实现前单独设计评审（新内核设计 §25）。
