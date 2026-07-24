# 素材池

这里记录收到的 PRD、demo、参考产品和技术样例。除非状态明确标为 `approved-for-planning` 或已经进入 [decision-log.md](decision-log.md)，素材只代表输入，不代表最终方案。

## 已收到素材

| 日期 | 来源 | 类型 | 位置 | 当前用途 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 2026-07-02 | 高嘉丰 | PRD 素材 | [../lmdj-web-prototype-spec.md](../lmdj-web-prototype-spec.md) | 参考 web prototype 的端到端链路、状态设计和 package contract | 素材 |
| 2026-07-02 | 高嘉丰 | Demo 工具 | [../../references/demos/lmdj-song-pipeline/README.md](../../references/demos/lmdj-song-pipeline/README.md) | 参考音频生成/分轨/切片/MIDI/验收的技术链路 | 素材 |
| 2026-07-02 | 高嘉丰 | Mood board | [Pinterest: LMDJ](https://www.pinterest.com/gaoplusfeng/lmdj/) | 参考视觉气质、音乐/演奏场景联想和界面氛围 | 素材 |
| 2026-07-06 | 内部整理 | Visual demo | [../../references/demos/ascii-matrix-camera/README.md](../../references/demos/ascii-matrix-camera/README.md) | 参考 ASCII matrix、摄像头输入和黑绿视觉气质 | 素材 |
| 2026-07-18 | 团队决策 Memo | 最新 PRD / Roadmap | [LMDJ Software MVP Stage 1–4 Memo](https://fcn8wuu8uotg.feishu.cn/docx/ZK5eduti6oE9Dox8Pkbc8r0vnPb) | 当前产品定义、Stage 1–4 Proof Chain、范围和验收依据 | `approved-for-planning` |

## 当前可提取信息

### 高嘉丰 web prototype PRD 素材

- 关注链路：prompt -> pipeline package -> Playable Patch -> guided performance。
- 强调真实系统边界：不隐藏生成/处理失败，不用静态 fixture 冒充主流程成功。
- 给出了 package contract：`samples/*.wav`、`chart.mid`、`lanes.json`、`report.json`、preview 音频。
- 给出了固定键位方向：`Z X N M`。
- 仍待评审：是否采用线性三步流程、是否必须 live generation、runtime 范围、backend API 粒度。

### lmdj-song-pipeline demo

- 可运行价值：证明音频可以被转换为有限 samples + MIDI chart + lane map。
- 可复用方向：package 输出格式、验收报告、FastAPI job 状态、快速测试 fixture。
- 项目来源：这是高嘉丰提供的个人参考项目和技术素材库，不是 LMDJ 最终系统源码边界。
- 需要谨慎：demo 的 pipeline 结构、目录结构、API、CLI、状态模型不等于最终产品架构；输出格式也可能根据 LMDJ 的 `Patch / Pad / Scene / Element` 产品对象重定。
- 建议用法：先把它当作 Audio Worker / pipeline capability reference；通过 `Patchify` adapter 把其输出转换为 LMDJ 自己的产品 contract。

### 高嘉丰 Pinterest mood board

- 当前用途：作为视觉方向和情绪参考，不直接等同于 UI 设计稿。
- 可提取方向：音乐演奏氛围、视觉材质、界面情绪、角色/场景联想、品牌语气。
- 需要谨慎：Pinterest 内容可能混合多个来源和风格，进入 PRD 前需要二次筛选和归类。

### ascii-matrix-camera visual demo

- 当前用途：作为视觉互动参考 demo，不纳入正式产品源码边界。
- 可提取方向：黑底绿色 ASCII、falling matrix、摄像头输入、静态 fallback subject。
- 需要谨慎：它证明一种视觉气质，不等于最终 LMDJ Web App 或 Performance View 的技术架构。

### 2026-07-18 Stage 1–4 Memo

- 当前用途：作为产品路线和开发排序的最新 `approved-for-planning` 输入。
- 核心定义：LMDJ 是把音乐变成可编辑、可演奏、可继续制作的 AI-native Playable Layer。
- 当前优先：Stage 1 Creator Core，先证明 Upload / Generate → Patch → Play / Take → DAW Export。
- 首条切片：Upload → Make It Playable → Play → Creator Export Pack。
- 2026-07-24 的本地决策：固定 16 个数据 Pad，UI 与数据一一对应；未使用位置为真实 empty Pad；通用 ZIP + Ableton Smoke；MIDI 是验收项。

## 待补素材

- lmdj-pad-rhythm 当前 runtime 能力和限制。
- LMDJ 核心玩家体验定义。
- Playable Patch 的产品语言和生命周期。
- 目标 demo 的首轮验收标准。
- 竞品或相邻产品参考。
