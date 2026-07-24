# 开放问题

更新时间：2026-07-24

这里记录 2026-07-18 Stage Memo 和 2026-07-24 本地决策之后仍未确认的问题。已经解决的旧问题已转入 [decision-log.md](decision-log.md)，不继续以“待决”状态保留。

## Stage 1 首条切片

| 问题 | 为什么重要 | 处理时点 | 状态 |
| --- | --- | --- | --- |
| MIDI Learn 是否需要支持多套 Controller Profile？ | 决定 `localStorage` 数据模型和设备切换体验。 | 首版只保存一套全局映射，Release Evidence 后再评估。 | 已收缩 |
| Key analysis 的最低可接受置信度是多少？ | 低置信度 Key 不能在 Export Manifest 中伪装为可靠结论。 | 用固定测试素材和 Ableton Smoke 记录置信度，再确定门槛。 | 待验证 |
| Export ZIP 的可选 Stem 缺失应显示 warning 还是阻止下载？ | 当前不同 Runner 可能输出不同 Stem 组合。 | 设计已确定“真实列出 + warning”；真实验收后复核。 | 待验证 |

## Stage 1 后续

| 问题 | 为什么重要 | 处理时点 | 状态 |
| --- | --- | --- | --- |
| 当前 empty Pad 后续按什么规则填充素材和功能？ | 16 个数据槽已经固定，但后续角色分配仍会影响 Patch Mapping。 | 首条 Creator 切片通过后，单独设计填充策略。 | 延后 |
| Sampler Edit 第一版最小参数集是否只含 Start/End、Loop、One-shot、Mute、Volume、Swap？ | 决定第二条 Stage 1 切片是否还能保持纵向闭环。 | Sampler Edit + Take 设计会。 | 待决 |
| Take 是只记录 Pad/MIDI 事件，还是同时生成音频 Bounce？ | 决定 Take contract、Web Audio 录制和 Export Pack。 | Sampler Edit + Take 设计会。 | 待决 |
| Prompt/Voice 首个 Generation Provider 使用第三方 API 还是本地模型？ | 影响成本、延迟、授权、失败恢复和 Agent Orchestration。 | Creator 基础闭环通过后。 | 延后 |
| Production Separator 最终选择哪个 checkpoint？ | 影响 Stem 质量、资源成本和生产 Runner 迁移。 | Phase 1D benchmark / blind listening review。 | 待验证 |
| Canonical Timing Analyzer 是否必须先于 Production Runner 晋级？ | 影响跨 Separator 的 Patch 稳定性。 | Runner Phase 2A 评审前。 | 待评审 |

## Stage 2–4

| 问题 | 为什么重要 | 处理时点 | 状态 |
| --- | --- | --- | --- |
| Project Bin / Global Library 使用本地、云端还是混合存储？ | 决定 Asset 生命周期、成本、离线和账号边界。 | Stage 2。 | 延后 |
| Stage 3 Curated Playable Packs 的内容来源和权利如何保证？ | 内容权利不能阻塞 Learn / Arcade，但也不能被忽略。 | Stage 3 前。 | 延后 |
| Performance / Arcade 的 Timing、内容和连续性保护强度如何分层？ | Learn 不能用保护伪造技能，Arcade 又需要连续音乐性。 | Stage 3。 | 延后 |
| Stage 4 的延迟阈值、屏幕触控和旋钮数量是什么？ | 决定 Hardware Proof 的验收与控制面。 | Stage 4。 | 延后 |
