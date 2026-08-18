# `native-test-host` 属于产品面组件还是验收工具？

- 范围：新内核（Playable Beat Instrument）
- 状态：待决
- 来源：[2026-07-30 新内核设计](../../superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)评审
- 为什么重要：它已进入 `products/lmdj/assembly.json` 的 `hosts` 并随每个分发包发出，但 module id 含 "test"。`CLAUDE.md` 对 `apps/` 的定义是 "thin Core Hosts"，没有"测试 Host"这一类，二者必有一错。选项：承认它是产品面组件并改名 `native-host`（Module 重命名 + Assembly 变更，属 breaking）；或从 Assembly 与发行包移出、退回 `tests/`。同时缺一条"什么可以进分发包"的书面准则——包内容已从 CLI + MCP + 库扩张到含该 Host，全程无准则约束。
- 处理时点：下一次触及 Assembly 成员或发行包清单的 Task 之前。
