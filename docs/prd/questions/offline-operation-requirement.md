# 离线可用是 LMDJ 的硬需求还是可选便利？

- 范围：新内核（Playable Beat Instrument）
- GitHub Issue: #534
- 来源：[Needle 端侧小模型工具调用可行性验证](../../research/2026-09-01-needle-on-device-tool-calling-spike.md)
- 为什么重要：这一条决定端侧模型是否有存在理由，而它从未被写下。云端在讨论过的每项任务上都更准，成本也不构成约束；只有离线与即时延迟能为端侧辩护。影响面超出自然语言：Generation Provider、Project Bin 存储、Stage 4 硬件要背什么都取决于它，不明确就会被各自分别且不一致地默认掉。它同时决定「降级」允许是什么含义——规格 §24.5 已拒绝 Provider 静默回退，working-prd §3 要求失败状态明确，因此「联网才有、断网悄悄没有」这种形态已被排除。
- 处理时点：任何把端侧模型纳入产品路线的决定之前；应先于 [generation-provider-hosting](generation-provider-hosting.md) 收敛。
