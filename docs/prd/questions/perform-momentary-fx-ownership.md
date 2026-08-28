# 八种 Momentary FX 与显式 Hold 状态归属于 Runtime 瞬态、Performance Events 还是 Project Truth，如何保证离线复现确定性？

- 范围：Stage 10 Perform
- GitHub Issue: #383
- 来源：[2026-07-30 新内核设计](../../superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md) §7 首版列出 Filter / Delay / Reverb / Stutter / Gate / Reverse / Crush / Roll 八种 FX，并要求 `Hold` 是显式状态；当前 `packages/` 与 `contracts/` 中不存在任何 FX 实现。
- 为什么重要：归属决定 Project Contract 是否升 v4、Runtime Snapshot 形状是否变化、以及什么进入 lock-free 实时渲染路径。Delay/Reverb 需要不可在音频线程分配的 DSP 状态与缓冲（2 ms 斜坡决策已立下零分配 / 零锁 / `noexcept` 先例），Web 端受 512 MiB 固定堆约束。live 渲染、offline render 与 ResamplePerformance（#385）三者的样本级一致性规则也由本决策定义。
- 处理时点：Stage 10 design spec 锁定 FX 章节之前。
