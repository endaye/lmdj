# AI 提议的状态变更采用「确认在前」还是「撤销在后」？

- 范围：Stage 2–4
- GitHub Issue: #536
- 来源：[Needle 端侧小模型工具调用可行性验证](../../research/2026-09-01-needle-on-device-tool-calling-spike.md) §4.3、§4.4
- 为什么重要：确认在前安全但打断心流，这在可演奏乐器上代价很高；撤销在后保住心流，但要求每条 AI 可达命令完全可逆——那是对命令面本身的约束，不是 UI 选择。范围超出自然语言：Provider 建议、候选采纳、辅助编辑都适用。实测里有个两边都躲不开的陷阱：`"mute pad 3"` 路由正确、schema 通过，却同时把 `gain_millidb` 设到下限，因为 schema 要求 `playback` 全字段。所以确认只有在提议是**可读差分**时才是安全机制，撤销也必须能还原用户不知道被改过的字段；无论选哪个，read-modify-write 都是前置条件。
- 处理时点：第一个允许模型改动 Project Truth 的界面立项时。
