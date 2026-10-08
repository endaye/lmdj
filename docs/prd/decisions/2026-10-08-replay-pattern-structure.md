# 已确认：Performance 回放期间也允许改 Pattern 长度、DOUBLE UP 与 COPY

- 日期：2026-10-08
- 补充：[Pattern 改长度与复制](2026-10-08-pattern-length-and-copy.md)结论第 5 条的"播放中不可用"，以及 [Performance 回放期间允许编辑](2026-10-02-performance-replay-authoring.md)第 1 条的编辑清单。
- 来源：[#1888](https://github.com/endaye/lmdj/pull/1888) 独立评审指出：Host 只在 Pattern transport 播放时拒绝这三个操作，回放期间会准入。这实际上回答了"回放算不算播放"，需要 owner 确认。

## 结论

1. **"播放中不可用"只指 Pattern transport 播放。** Performance 回放期间，改长度（`pattern.resize`）、DOUBLE UP（`pattern.double`）和 COPY（`pattern.copy`）照常准入并写入 Project Truth，与 `pattern.create`、`pattern.events.edit` 一致。
2. **回放听到的内容不变。** 沿用 2026-10-02 决策第 2、3 条：回放按开始时固定的 resolved revision 播放；改长度不把新视图发布到回放之上，结果为 `publication: "deferred"`，回放结束后 Runtime 按当前 Truth 恢复。
3. **录音中仍然拒绝**，规则不变。

## 原因

- owner 要求与 Koala 一致，不确定时保持允许。Koala 没有事件级的演奏回放；最接近的体验是一边播放录好的歌一边改 Sequence，这在 Koala 中是允许的（见 2026-10-02 决策的原因）。
- 回放播放的是冻结的投影，编辑不会改变本次回放听到的内容。

## 影响

- Web Runtime Platform 模块页的"Performance replay authoring"清单补上这三个操作。现有实现不需要改动。
