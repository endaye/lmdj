# 已确认：Pattern 改长度与复制按 Koala 做，缩短删除超出部分，复制只在源占槽时占槽

- 日期：2026-10-08
- 解决的问题：[#1823](https://github.com/endaye/lmdj/issues/1823)（修改已有 Pattern 的长度、复制 Pattern 时事件怎么处理）。本文件删除对应的问题文件 `questions/pattern-length-change-and-copy.md`。
- 依据：
  - owner 的要求是"和 Koala 保持一致，并添加 Undo"。
  - [Koala 手册](https://manual.koalasampler.com/one-page/) §5.4–5.5：
    - BARS 菜单里，DOUBLE UP 让所选 Sequence 长度翻倍并复制全部音符和设置，`+` 加一小节，`-` 减一小节；
    - 把录好的 Sequence 拖到空槽就是复制它；
    - UNDO 撤销上一步。
  - Koala 业务流程调研 Q9、Q26、Q27（`docs/research/2026-07-28-koala-sampler-business-flows.md`）。
  - [Sequence 硬件界面修订](2026-10-04-sequence-hardware-ui-revision.md) 结论第 7 项。
- 计划：[Pattern 改长度与复制计划](../../plans/2026-10-08-pattern-length-and-copy.md)。

## 结论

1. **长度仍只有 1、2、4、8 小节。** 不放开到任意小节数，`lmdj.project.v5` 与内核规格 §6.2 不变。BARS 对应 Koala 的方式：
   - **DOUBLE UP**：长度翻倍，并把原有全部音符复制到后半段，同 Koala。8 小节时不可用。
   - **直接选更长的长度**：新增的小节为空，对应 Koala 的 `+`。
   - **直接选更短的长度**：见第 2 条。
2. **缩短时删除超出部分。** Koala 手册没有写减小节时超出的音符怎么处理，由 owner 决定：
   - 起点在新结尾及之后的音符删除；
   - 跨过新结尾的音符按现有的不跨循环接缝规则截断到新结尾；
   - Project Truth 里只留下听得到的音符；之后再加长，被删的音符不会回来，要恢复就用 Undo。
3. **COPY 生成新 Pattern 并选中它。**
   - 副本有相同的长度和全部音符，用新的 Pattern id。
   - 源 Pattern 占了 Perform 的 Pattern 槽时，副本放进源之后的第一个空槽。
   - 源之后没有空槽，或者源本身不占槽时，副本不占槽，但复制照常进行。
   - Sequence 页的 Pattern 顺序维持现状（按 Pattern id 排序，与新建 Pattern 一致），本决定不新增 Pattern 顺序。
4. **每个操作是一条 Undo 记录。**
   - 改长度、DOUBLE UP、COPY 各自一次提交、一条撤销记录。
   - COPY 的槽位分配与新 Pattern 在同一次提交里。
   - 不改变任何内容的操作，例如选当前长度，不产生记录。
5. **播放中不可用。**
   - COPY：owner 已确认播放中不可用，与新建 Pattern 一致。
   - BARS 与 DOUBLE UP：沿用同一边界。正在播放的 Pattern 改长度会移动播放头的循环点，首版不处理。这一条 owner 可以在计划评审时改。
   - 录音中三者都被拒绝，沿用 Sequence 录音语义第 3 项。

## 原因

- owner 要求与 Koala 一致。DOUBLE UP 和 `+` 的行为都直接来自 Koala 手册。Koala 用拖到空槽表达复制，LMDJ 对应到 Perform 的 Pattern 槽。
- 删除超出部分，让 Project Truth 不含听不到的事件；需要恢复时由 Undo 负责。
- 只有 1/2/4/8 小节时，DOUBLE UP 和直接选长度已经覆盖 Koala `+`/`-` 能达到的所有长度，不需要改 Contract。

## 影响

- **Core：**
  - 新增三个内部 Authoring Command：改长度、DOUBLE UP、复制；
  - Project I/O 的内部命令日志与 Undo/Redo 记录它们；
  - Facade 提供对应操作。
  - 不改 Contract，因为 Pattern 的 `bars` 与事件形状都不变。
- **Web Host：** 录音中或有命令在途时拒绝；停止时立即重新发布当前 Pattern。
- **Creator：** Desktop Final 计划的 T8 启用 SETUP 层的 BARS、DOUBLE UP 与 COPY。
