# ResamplePerformance 捕获现场母线音频还是从 Performance Events 离线重渲染，Command/Job 与 Lineage 语义是什么？

- 范围：Stage 10 Perform
- GitHub Issue: #385
- 来源：[2026-07-30 新内核设计](../../superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md) §12.1 已把 `ResamplePerformance` 列为 Facade Command，但无任何契约；§11.4 定义了 Capture Ring → Background Writer → Immutable Audio Artifact 的录音路径；§7 允许对完整演出或选中片段 Resample。
- 为什么重要：capture-vs-rerender 决定 FX 离线确定性（#383）是否是 Stage 10 硬前置；产品核心闭环 `Sound → Pad → Pattern → Performance → New Sound` 依赖本 Command。派生 Asset 的 Lineage、expected-revision 绑定、core Job 与 Capability/Provider 的归类、以及 resample 产物落 Pad 时压在未决 Bank 配额（#341 / #357）上的准入行为都待定。
- 处理时点：Stage 10 实施计划之前；范围裁剪影响 Stage 10 design spec。
