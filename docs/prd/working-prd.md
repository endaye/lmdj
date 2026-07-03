# LMDJ 工作版 PRD

状态：脑暴中  
更新时间：2026-07-02  
口径：当前文档是工作版，不是定稿。内容可以快速改写，已确认结论以 [decision-log.md](decision-log.md) 为准。

## 1. 一句话方向

LMDJ 想把音乐素材转化为可被玩家“演奏”的 Playable Patch，让用户通过清晰的引导和有限输入参与音乐，而不是只听一段生成结果。

## 2. 当前核心假设

- 用户价值不只是“生成一首歌”，而是“把音乐变成可以上手玩的东西”。
- Playable Patch 是核心产品对象，应该比单纯的音频文件或 MIDI 文件更重要。
- 高嘉丰的 `lmdj-song-pipeline` demo 可以作为技术参考，但最终系统边界需要重新定义。
- web prototype 的第一目标是帮助团队对齐链路和体验，不是做营销页。

## 3. 目标用户与场景

待补。当前需要先明确第一阶段服务谁：

- 内部团队：用来验证生成链路、演奏体验和 package contract。
- 创作者：输入音乐想法，得到可演奏 patch。
- 玩家：直接体验一个可演奏音乐片段。

## 4. 核心体验草案

```text
输入音乐意图或音乐素材
  -> 生成 / 转换为 Playable Patch
  -> 展示 patch 结构和可演奏部分
  -> 用户跟随 MIDI 视觉引导进行演奏
  -> 系统给出回放和表现反馈
```

## 5. Playable Patch 暂定定义

Playable Patch 是一个可被运行时加载和演奏的音乐对象，至少包含：

- 声音素材：samples 或 loops。
- 谱面信息：MIDI notes 或等价事件序列。
- lane 映射：输入键位、音色、pitch、可演奏/自动播放属性。
- 元数据：BPM、loop 长度、来源、生成参数、质量报告。

待定问题：Playable Patch 是否必须由 AI 生成，还是也支持人工导入和编辑。

## 6. V1 Prototype 可能范围

当前倾向先做团队对齐型 prototype：

- 可以接收 prompt 或素材输入。
- 可以产生或加载一个 Playable Patch。
- 可以显示 package / patch 结构。
- 可以用固定键位完成一次 guided performance。
- 可以明确展示失败、拒绝、无效 package 等状态。

不急于做：

- 账号系统。
- 商店或社区。
- 完整 DAW 编辑器。
- 移动端触控演奏。
- 商业化版权承诺。

## 7. 成功标准草案

- 团队能看懂从输入到 Playable Patch 再到演奏的完整链路。
- 至少一个真实或 fixture patch 可以稳定进入 runtime。
- 用户能通过有限键位完成一次可感知的演奏。
- 失败状态不会被隐藏，能知道失败发生在哪一段。
- PRD 能持续迭代，不被单个 demo 或单份素材绑死。

## 8. 当前依赖和参考资产

- 高嘉丰 web prototype PRD 素材：[../lmdj-web-prototype-spec.md](../lmdj-web-prototype-spec.md)。
- 高嘉丰 demo 工具：[../../lmdj-song-pipeline/README.md](../../lmdj-song-pipeline/README.md)。

## 9. 下一步

- 明确第一阶段目标用户：内部团队、创作者、玩家三者谁优先。
- 明确 V1 是否必须 live generation，还是允许 fixture-first prototype。
- 盘点现有 rhythm runtime 能力，确认最短可跑通路径。
- 把 Playable Patch 的字段从“技术输出”整理成“产品对象”。
