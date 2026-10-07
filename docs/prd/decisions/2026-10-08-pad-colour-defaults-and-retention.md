# 已确认：无类别 Pad 用中性色，标签按含义映射，换素材保留覆盖、删除清除，旧素材不补类别

- 日期：2026-10-08
- 补充：[Pad 颜色来源](2026-10-07-pad-colour-source.md)的"实施边界与待设计项"。该决定把这几项留给 Contract/Core 计划提出并评审。本文件记录 owner 在这份计划起草时做出的选择；原决定的结论 1–6 不变。
- 计划：[Pad 颜色 Contract/Core 计划](../../plans/2026-10-08-pad-colour-contract-core.md)。

## 结论

1. **无类别的素材和空 Pad 用中性色。** 它们不归入五个类别中的任何一个，显示为 Figma D02 中 EMPTY Pad 的灰色描边。有素材的 Pad 仍可手动选五色之一；空 Pad 不带颜色。
2. **类别标签按含义映射，`other` 不归类。**

   | 来源标签 | 类别 |
   |---|---|
   | Sound Set：kick、snare、clap、hat_closed、hat_open、perc、cymbal | DRUMS |
   | Sound Set：bass；stem：bass | BASS |
   | Sound Set：melody、chord | MELODIC |
   | Sound Set：vocal；stem：vocals | VOCAL |
   | Sound Set：fx | TEXTURE |
   | stem：drums | DRUMS |
   | Sound Set：other；stem：other | 无类别 |

3. **用户的颜色覆盖跟着 Pad 走。** 以下操作都保留覆盖：给 Pad 换素材（重新分配、导入、录音、安装 Sound Set、采用 Slice 或分离结果）、重新分离。删除 Pad 让它变空时，一并清除覆盖。"恢复类别默认色"也会清除覆盖。
4. **旧 Project 里的素材不补类别。** 本计划之前已经安装的 Sound Set 素材、导入的素材都视为无类别，显示中性色，用户可以手动选色。之后安装的 Sound Set 素材按第 2 条记录类别。

## 原因

- 不给未知素材猜类别，颜色才能真实反映素材；中性色与 D02 的 EMPTY 样式一致。
- `other` 本身没有含义，硬归一类会让颜色失去"一眼认出分轨"的作用。
- 覆盖跟着 Pad 走，用户按位置组织的颜色在换声音、重新分离后都还在。空 Pad 没有声音，不需要颜色。
- 回溯补类别需要依赖本机是否还留着 Sound Set 清单，结果因设备而异；不补则所有设备一致。

## 影响

- **Contract：** `lmdj.project.v5` 增加可选字段（Asset 类别、Pad 覆盖索引），为 Contract MINOR。具体字段见计划。
- **Core：** Domain 命令、颜色解析、各个改素材的命令对覆盖的处理、Sound Set 安装时记录类别、Project I/O 读写与 Undo/Redo、Facade 投影。
- **Creator：** Desktop Final 计划 T7 在以上完成后实施。
