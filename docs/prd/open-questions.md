# 开放问题

更新时间：2026-08-03

这里记录 2026-07-18 Stage Memo 和 2026-07-24 本地决策之后仍未确认的问题。已经解决的旧问题已转入 [decision-log.md](decision-log.md)，不继续以“待决”状态保留。

## 新内核（Playable Beat Instrument）

来自 [2026-07-30 新内核设计](../superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)评审。

| 问题 | 为什么重要 | 处理时点 | 状态 |
| --- | --- | --- | --- |
| 素材 BPM ≠ Project BPM 时，Loop 类素材是否/如何 Time-stretch 跟随全局 BPM（含 Pitch-shift）？ | “完整歌曲变成可演奏素材”+ 全局 BPM/Key 几乎必然遇到速度不匹配；决定 Audio Runtime 的 DSP 范围和 Capability 清单（Koala 有 Time-stretch 作为对照）。 | Audio Runtime Contract 定稿前的设计评审。 | 待决 |
| 产品级录音并发语义如何定义：哪些无关 Command 不应触发冲突，是否允许选择性 rebase？ | Headless Core Proof 为保证确定性，暂用“任何 revision 变化均冲突并封存 Take”的严格规则；该规则不能替代用户产品中的冲突分类，仍会影响录音 Journal、Take 提交体验与公开 Contract。 | Sequence / Take Contract 进入用户产品实现前单独设计评审（新内核设计 §25）。 | 待设计评审 |
| Provider 输入 Artifact 的字节级 Schema 校验由谁解析与验证？ | 已批准的 `lmdj.capability.v2` 能用显式端口确定声明的 Schema 身份，但 `ArtifactRef` 不携带 Schema provenance，AttemptStore 也没有输入 Artifact resolver，不能把端口身份校验伪装成字节级 Schema 校验。 | 首个需要解析结构化 Artifact bytes 的正式 Capability 实现前单独设计 resolver 与验证器边界。 | 待架构设计 |
| Build Manifest 是随归档内嵌，还是与归档并列 detached 发布？ | `create_zip()` 已固定时间戳、排序与文件模式以求可复现，但 `build-manifest.json` 在归档内且含 `build_time`，于是同一源码每次打包的 ZIP 字节都不同，"下载方自行重建并比对 hash"无法实现。`build_time` 是 version-management.md §4 明文要求的，所以这不是实现缺陷，而是两个都正确的要求装进了同一个容器。选项：manifest 改为 detached 并列发布；或从归档内剔除可变字段并保留 detached 副本；或接受不可复现并明确放弃该验证手段。这会改变已发布产物的形态。 | 首个对外分发（进入 `dev` 及以上 Channel）之前的发行治理评审。 | 待决 |
| `native-test-host` 属于产品面组件还是验收工具？ | 它已进入 `products/lmdj/assembly.json` 的 `hosts` 并随每个分发包发出，但 module id 含 "test"。`CLAUDE.md` 对 `apps/` 的定义是 "thin Core Hosts"，没有"测试 Host"这一类，二者必有一错。选项：承认它是产品面组件并改名 `native-host`（Module 重命名 + Assembly 变更，属 breaking）；或从 Assembly 与发行包移出、退回 `tests/`。同时缺一条"什么可以进分发包"的书面准则——包内容已从 CLI + MCP + 库扩张到含该 Host，全程无准则约束。 | 下一次触及 Assembly 成员或发行包清单的 Task 之前。 | 待决 |

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
