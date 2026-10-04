# 修改已有 Pattern 的长度、复制 Pattern 时，Pattern 里的事件怎么处理？

- 范围：Creator 与 Core
- GitHub Issue: #1823
- 来源：[Sequence 硬件界面修订](../decisions/2026-10-04-sequence-hardware-ui-revision.md) 结论第 7 项（SETUP 层的 `BARS` 与 `COPY`）。
- 为什么重要：
  - 目前 Core 和 Host 都没有修改已有 Pattern 长度或复制 Pattern 的操作。
  - 缩短 Pattern 时，超出新长度的事件是删除，还是保留但隐藏？跨过新结尾的音符是截断还是删除？
  - 加长 Pattern 时，新增的小节留空，还是重复已有内容？
  - 复制出的 Pattern 放在原 Pattern 之后还是列表末尾？是否一并复制 Pattern 槽位分配？
  - 播放中能否执行这两个操作？
  - 这些都会改变 Project Truth，各应是一条撤销记录。
- 处理时点：在实现 SETUP 层 `BARS` 与 `COPY` 的 Task 之前。
