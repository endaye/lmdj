# Perform 的 Bank 切换是纯 Runtime/Host 视图状态还是部分进入 Project Truth，四个 user Bank 是否必须全驻留以保证无缝切换？

- 范围：Stage 10 Perform
- GitHub Issue: #386
- 来源：[2026-07-30 新内核设计](../../superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md) §7 列出 Bank 切换；§6.1 要求记录触发的 Bank；§6.6 的 Pattern 事件已以 Bank + Pad 位置自描述。架构不变量先例：Provider 选择属于 Workspace/Host 设置而非 Project Truth。
- 为什么重要：长素材 Bank 配额链（#341 / #343 / #345，决策 D1：每 16-Pad user Bank 64 MiB、发布上限 128 MiB）与 #357 的记账问题正基于「Cooker 单代物化全部 64 Pad」的现状裁决；Perform 的无缝 Bank 切换是维持或放弃全驻留的最强产品论据，晚决会返工 #357 的结论。瞬时切换 vs SR-D11 式音乐边界切换语义亦未定。
- 处理时点：最好与 #357 同一次决策，或在其之前。
