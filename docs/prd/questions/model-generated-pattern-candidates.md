# 模型产出的 Pattern 候选是否越过「不是 AI 音乐生成器」的定位边界？

- 范围：Stage 2–4
- GitHub Issue: #535
- 来源：[Needle 端侧小模型工具调用可行性验证](../../research/2026-09-01-needle-on-device-tool-calling-spike.md) §4.4
- 为什么重要：working-prd §1 明写 LMDJ 是生成模型**下游**的 Playable Layer、「不是 AI 音乐生成器」，而「帮我补齐 pattern」正压在这条线上。三种形态被混为一谈：选预制、具名变换、模型自己产事件。前两者确定性、可 hash、可重放，能当普通命令；第三种同一句话两次给出不同结果，当成命令会破坏已依赖的可重复性。契约上 `lmdj.project.create` 的 `initial_pattern` 今天就允许写入完整事件，只是没人决定过模型可否驱动它；若要，它的家是 `provider.run` → `attempt.inspect` 加 candidate adoption lineage，属于 Attempt 路径而非命令路径。
- 处理时点：任何允许模型产出 Pattern 事件的实现之前。这是产品定义变更，不得在实施 Task 内决定。
