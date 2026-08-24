# LMDJ 分发包内容准则

日期：2026-08-24

状态：已生效

适用范围：`scripts/package-core.py` 及未来任何产生面向用户/测试者分发包的
工具；`products/lmdj/` Product Assembly；`apps/` Host 与 `packages/` Core
Module 的成员资格决策。

## 1. 背景

分发包曾经在没有书面准则的情况下从 CLI + MCP + 库扩张到包含 Native Host。
本准则使"什么可以进入分发包"成为一条可审查的规则，而不是打包脚本的隐式
副作用（Issue #210 / 机器任务 A2）。

## 2. 准则

一个文件只有满足以下两类之一，才允许进入分发包：

1. **Assembly 成员产物**：它是 active Product Assembly
   （`products/lmdj/assembly.json` + `assembly.lock.json`）锁定的 Module、
   Host 或 Provider 的构建产物或运行必需清单；或
2. **分发元数据**：校验、使用或合法再分发该包本身所必需的文件（Build
   Manifest、Assembly/lock 副本、Contract schema、包 README、许可证文件
   `LICENSE`、启动器与分离的 SHA-256 摘要）。

推论：

- 不在 Assembly 中的组件不得出现在任何分发包中。
- 仅服务开发/验收的工具属于 `tests/` 或 `tools/`，不进入分发包；如果某
  个能力需要随包分发，它必须先成为 Assembly 锁定的正式组件，再进入包。
- 组件不得以 "test"、"lab"、"probe" 等名义绕过成员资格要求；名称必须
  反映其在 Assembly 中的真实角色。

## 3. 单一机械清单

`scripts/package-core.py` 的 `stage_package()` 是分发包内容的唯一机械
清单。禁止在 CI、release 工具或文档中维护第二份包内容列表。

向 `stage_package()` 添加或移除任何文件时，同一 Task 必须：

1. 说明该文件满足第 2 节的哪一条；
2. 更新 `packaging/core/README.md` 的内容描述；
3. 若涉及组件成员资格变化，同步 Product Assembly、portal current 页面与
   本准则（Assembly 变化按版本策略分配新 Product Build）。

## 4. 与版本和发布治理的关系

本准则不授权任何打包、发布或部署行为。Product Build 分配、tag、Release
与 Channel 晋级仍分别受 `docs/governance/version-management.md` 与
`.agents/skills/lmdj-release/SKILL.md` 约束。
