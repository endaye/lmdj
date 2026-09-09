# ESP32 固件开发经验手册

日期：2026-09-09。范围：文档整理，用户授权 commit + push；不创建或合并 PR。

## 目标与边界

让后续开发者从一个固定入口找到 ESP32 环境、构建留证、烧录恢复、排障和音频验收
经验，并能回到具名实验核对证据。复用现有研究与坑账，不创建并行知识账本。

不改固件、Core、依赖或工具链，不连接设备，不执行烧录/恢复，不刷新实验的人工验收
状态，不自动化固件脚本，不改变并发方案、硬件选型、产品版本或发布流程。

## Task 1 — 建立操作入口

一个 reviewable Conventional Commit，声明文件：

- 新增 `docs/deploy/esp32-firmware.md`：持续维护的中文手册。
- 修改 `docs/README.md`：仅增加手册入口指针。
- 新增 `docs/plans/2026-09-09-esp32-firmware-handbook.md`：本计划。

实现：按准备、EIM、构建、设备写入边界、分层音频对照、证据留存组织内容；历史数字
具名引用，不冒充通用容量或当前上游状态。已有回归覆盖的分配顺序缺陷只链接研究。
检索 `area:docs-governance` 及相关听感坑后，无本 Task 新确认的流程复发，不新增或
人为 bump 坑账。脚本化另行规划。

最低层验证：

1. 人工逐条核对历史结论、命令来源、授权边界；新增相对文件链接必须可解析，shell
   示例做 Bash 语法检查但不执行。这针对错引资料、错误命令与误报验收。
2. `git diff --check` 与 staged 文件清单审计，只允许上述三份文档。
3. 新文件 stage 后运行 `python3 tests/build/ci_change_scope_test.py`，确认路径有归属。
4. `scripts/docs-site.sh check`：按仓库要求核对文档涉及的已记载事实及门户机械一致性，
   不能用它替代第 1 项的内容审查。使用 Node 22 和独立 worktree 中的 locked install。
5. 提交后运行 `scripts/local-ci.sh --base-ref origin/main --list --json`，确认最终提交
   范围；push 后核对远端分支 SHA 与本地 commit 一致。

不新增 gate，不修改阈值，不执行固件或完整产品测试；文档检查不产生真机 PASS。

## Version Management

Version impact: none — 只整理既有经验，不修改 Product Build、Module、Host、Provider、
Contract、Assembly、外部依赖锁或固件身份，不分配测试 Build，也不生成快照。

## Documentation Impact

Documentation impact: none
Reason: 仅增加独立 ESP32 实验的操作入口和经验索引，不改变产品行为、平台支持、
既有实验结果、正式部署/验收规则或门户来源事实；无受影响门户路由。
