# LMDJ 工作版 PRD

状态：`approved-for-planning` 摘要

更新时间：2026-07-24

上游依据：[LMDJ Software MVP Stage 1–4 Memo](https://fcn8wuu8uotg.feishu.cn/docx/ZK5eduti6oE9Dox8Pkbc8r0vnPb)（2026-07-18）

本文只保留当前开发排序所需的产品摘要。完整叙事、Stage 2–4 和团队协作机制以上游 Memo 为准；已经确认的本地收缩以 [decision-log.md](decision-log.md) 为准。

## 1. 产品定义

LMDJ 不是 AI 音乐生成器、简化 DAW 或音乐游戏，而是一层把音乐变成可编辑、可演奏、可继续制作的 AI-native Playable Layer：

```text
Suno / 其他生成模型
  → LMDJ Playable Patch
  → 人的编辑与演奏
  → DAW 二次制作
```

`Playable Patch Engine` 是核心资产；生成 Provider 可替换，DAW 是下游专业制作环境。

## 2. Stage Proof Chain

| Stage | 主命题 | 过关证明 |
| --- | --- | --- |
| Stage 1 | Creator Core | 生成/导入到 Patch、演奏和 DAW 导出的创作者闭环成立 |
| Stage 2 | Creator Depth + Asset Memory | AI 修改更快、可控、可回滚，且个人声音资产可积累复用 |
| Stage 3 | Learn + Content Loop | 新手通过 Learn 建立可观察的音乐技能 |
| Stage 4 | Hardware Proof | 核心演奏可映射到通用硬件并脱离鼠标键盘 |

Stage 是 Proof Gate，不是固定周数。每周发布可运行版本，但只在证据满足后进入下一 Stage。

## 3. 当前 Stage：Creator Core

当前优先用户是 DAW 创作者 / Prosumer。产品必须证明：

- 用户拥有的 WAV/MP3 能进入真实音频管线；
- 音频被转换为可播放的 Patch；
- 通用 MIDI Pad 可以触发正确素材；
- 用户可以获得完整、可检查的 Creator Export Pack；
- Export 能进入真实 DAW 继续制作；
- 失败状态明确，不用假数据或静默降级伪造成功。

现有仓库已经完成 Upload → Pipeline → Patchify → 8-pad Web Play，尚未完成 MIDI、Export Pack、DAW Smoke、Sampler Edit 和 Take。

## 4. 首条纵向切片

```text
Upload
  → Make It Playable
  → 16 Data Pads / 16-position UI
  → Keyboard + MIDI Play
  → Creator Export ZIP
  → Ableton Live Smoke Test
```

已确认范围：

- 输入 WAV/MP3，默认最大 `200 MiB`、`600 秒`；
- 复用现有 Audio Pipeline 和 `lmdj.patch.v1`；
- `patch.json` 固定包含 16 个数据 Pad，索引为 `0..15`；
- UI 使用与数据一一对应的 2×8 十六位布局；未使用位置是 `action: "empty"` 的真实 Pad；
- 8-pad Controller 使用 Bank A/B 覆盖全部十六个逻辑位置；
- MIDI 是验收项，键盘和鼠标是备用输入；
- Creator Export 使用通用 ZIP，包含 Patch、真实存在的 Stems、Samples/Slices、MIDI 和 BPM/Key/Loop Manifest；
- 首个 DAW 验收目标为 Ableton Live；
- 同一固定测试音频连续运行三次；
- 非开发者可以在无口头指导下完成 Upload、MIDI 演奏和 Export。

详细设计见 [Stage 1 Creator Core 首条纵向切片设计](../superpowers/specs/2026-07-24-stage1-creator-core-slice-design.md)。

## 5. 首条切片不做

- Prompt / Voice 生成；
- Agent Orchestration 实现；
- AI Replace / Variation；
- Sampler Start/End、Loop、Swap、Roll、Chop；
- Take 录制；
- Asset Library、账号和云同步；
- `.als` 等专有 DAW 工程格式；
- Learn / Arcade；
- 自研硬件。

## 6. 后续开发顺序

1. 完成首条 Upload → MIDI Play → Export ZIP 纵向切片和 Release Evidence。
2. Stage 1 第二切片：Sampler Edit + Take Recording，并把 Take 纳入 Creator Export。
3. Stage 1 后段：Prompt/Voice → Generation → 同一个 Patch Engine。
4. Stage 2：AI Variation、Patch Versioning、Project Bin / Global Library。
5. Stage 3：Learn / Arcade 与内容循环。
6. Stage 4：通用 MIDI、音频接口和 21:9 屏幕原型的 Hardware Proof。

Separator benchmark、Timing Analysis、生产 Runner 迁移继续作为技术风险消除工作，但不能替代当前 Creator 纵向切片。
