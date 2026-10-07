# 已确认：Pattern transport 与 Project 切换先停止 Performance 回放

- 日期：2026-10-07
- 决策来源：owner 于 [2026-10-04](https://github.com/endaye/lmdj/issues/1801#issuecomment-5976157940) 的明确选择。
- 替代：[2026-10-03 勘误](2026-10-03-performance-replay-authoring-erratum.md)第 4 条的待决状态；原文件保留为历史。
- 相关问题：[#1801](https://github.com/endaye/lmdj/issues/1801)。

## 结论

1. Performance 回放播放期间，Pattern transport 的 Play/Stop 或 Record
   命令先停止该回放，再照常执行。两者不并行播放，也不因为回放在播放就拒绝命令。
2. 切换 Project（创建或打开另一个 Project）也先停止旧 Project 的回放，
   再替换 Project。回到原 Project 不会恢复已经停止的回放。
3. 停止通过回放自身的 `performance.replay.stop` 完成，包括 neutral reset
   的确认；Host 的回放跟踪由该停止结果结束。真实停止失败或超时仍报告错误，
   不在停止尚未确认时执行后续命令。
4. transport 接手选中的 Pattern 的当前 Truth 视图；回放期间已提交的编辑
   随交接生效。Project 切换后发布新 Project 自己的视图。
5. 网格、Pad、BPM 编辑继续遵循 #1789：编辑照常提交，回放按 begin 时固定的
   revision 播放，Pattern 视图暂缓到回放结束；Bank 照常发布、Pad 编辑只停现场声音。

## 原因与代价

owner 选择一次只播放一个来源，与 Koala 的播放来源选择保持一致。代价是用户
正在听的 Performance 回放会被 transport 命令或 Project 切换打断。

## 实现边界

交接使用既有 Facade 操作与原请求 deadline，不增加拒绝词汇、Contract 或
Project 字段。音频已经 quiescent 并由 Engine Stop 清空 FX 时，回放 Stop
可以直接完成 neutral reset，不重新启动音频。普通编辑和自然回放结束的恢复
策略继续由原决策约束。
