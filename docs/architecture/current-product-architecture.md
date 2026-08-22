# LMDJ 当前端到端运行时架构

更新时间：2026-08-22

本文面向技术团队，说明当前仓库已经实现并由 Product Assembly 装配的运行时。它描述源码与
本地自动化证明，不把规划中的生产 Provider、云基础设施、部署状态、Release 状态或物理设备
验收写成已完成事实。

[打开 Archify 交互式架构图](assets/lmdj-current-runtime-architecture.html)

交互式图支持深浅主题、搜索、聚焦、关系追踪，以及 PNG、JPEG、WebP 和 SVG 导出。可审查的
图源位于
[`assets/lmdj-current-runtime-architecture.architecture.json`](assets/lmdj-current-runtime-architecture.architecture.json)。

## 如何阅读主路径

从左向右追踪绿色主路径：

```text
Web Hosts
  -> Web Runtime Platform
  -> Application Facade
  -> Authoring Domain / Project Truth
  -> Project Cooker
  -> Immutable Runtime Snapshot
  -> Audio Runtime
```

Native Hosts 直接进入 Application Facade。Project I/O 与 Provider SDK/Proof Providers 是从
其最近主路径节点向下延伸的支路，不是第二套 Project 或 Runtime。

Product Assembly 负责锁定 Module、Host、Provider、Contract 和 policy 的组合身份。它是声明式
装配边界，不执行用户工作流，也不动态增加 Facade operation。

## 当前组件职责

| 边界 | 组件 | 当前职责 | 源码位置 |
| --- | --- | --- | --- |
| Host | Creator Web / Formal Web Runtime Host | UI、Host identity、浏览器生命周期和协议适配 | `apps/creator-web/`、`apps/web-runtime-host/` |
| Host | Core CLI / Core MCP / Native Test Host | 通过同一 Facade 提供终端、stdio MCP 和原生验收入口 | `apps/core-cli/`、`apps/core-mcp/`、`apps/native-test-host/` |
| Core Module | Web Runtime Platform | Manifest Gate、Runtime Session、输入适配、Control Runtime 与浏览器资源生命周期 | `packages/web-runtime-platform/` |
| Core Module | Application Facade | Host 唯一 Core 入口、应用编排、稳定结果与错误语义 | `packages/application-facade/` |
| Core Module | Authoring Domain | Project Truth、命令规则、revision 与 Pad/Pattern/Sample 语义 | `packages/authoring-domain/` |
| Core Module | Project I/O | 原子 Project store、Take recovery、portable Bundle transfer 与 Workspace cache | `packages/project-io/` |
| Core Module | Project Cooker | 校验 Project 与 Artifact，派生 Runtime Snapshot | `packages/project-cooker/` |
| Derived state | Runtime Snapshot | 不可变、可丢弃、可重建的 Audio Runtime 输入 | `packages/project-cooker/`、`contracts/` |
| Core Module | Audio Runtime | prepared sample bank、离线渲染、实时 Engine、Voice 与 preview | `packages/audio-runtime/` |
| Core Module | Provider SDK | Capability、Registry、Attempt Store 和 Artifact output sink | `packages/provider-sdk/` |
| Provider | Local Proof Providers | 当前装配的成功/失败隔离证明，不代表生产模型或云服务 | `providers/local-proof-success/`、`providers/local-proof-failure/` |
| Foundation | Foundation | Artifact、JSON 和 typed error 的产品中立共同底座 | `packages/foundation/` |
| Product | LMDJ Assembly | 精确 Module、Host、Provider 与 Contract wiring | `products/lmdj/` |

`products/lmdj/assembly.json` 与 `assembly.lock.json` 是当前组合及精确身份的权威输入。本文不复制
版本号；当前 Product Build、Module、Host、Provider 与 Contract 身份应从 manifests、Lock 和
Architecture Portal 派生。

## 权威状态与数据边界

- **Project Truth**：Authoring Domain 独占的权威创作状态。成功命令按 revision 原子提交。
- **Project Bundle**：Project I/O 管理的 portable import/export 形式，不是 Host 自行解析的数据模型。
- **Runtime Snapshot**：由 Cooker 生成的不可变派生状态；可以丢弃和重建，不能反写为 Project Truth。
- **Workspace/Attempt State**：Provider 选择、进行中状态与失败记录；不属于 Project Truth。
- **Runtime State**：Voice、transport、buffer、cache、telemetry 和浏览器生命周期状态；不持久化为 Project Truth。

Facade 是控制面和应用用例边界，不是实时逐事件数据面的替代品。浏览器输入与 Audio Runtime 的
低延迟路径由 Web Runtime Platform 和 Runtime/Voice 机制承担；Host 不能用自己的业务规则绕过
Facade、Domain revision 或 Candidate commit 语义。

## Provider 边界

Application Facade 通过 Provider SDK 选择并运行 Capability。Provider 只接收不可变 Artifact
input 与 Artifact output sink，返回 Candidate/Attempt 结果；它不接收 mutable Project，也不接收
Project bundle path。Provider failure 只能更新 Attempt/Workspace State，不能修改 Project Truth。

当前 Assembly 只装配本地成功与失败 Proof Provider。生产模型、云 Gateway、鉴权、计费、数据
保留政策和区域控制尚未由这张图声明为已实现。

## 禁止路径

- Host 不解析 Project Bundle，也不直接依赖 Domain、Project I/O 或 Provider implementation。
- Provider 不读取或修改 mutable Project，不把 failure 写入 Project Truth。
- Runtime Snapshot 不持久化为 Project Truth，也不把 Runtime state 反写 Project。
- Pattern event 指向 Pad Slot，不直接指向 Asset。
- Provider selection 属于 Workspace/Host settings，不属于 Project Truth。
- `references/demos/` 是冻结参考材料，不属于 active product runtime。
- `lmdj.patch.v1` 与 `lmdj.materials.v1` 已退役，不属于当前链路。

## 当前证明边界

当前源码和自动化已经覆盖 Project command/store、Cook、Runtime Snapshot、离线与实时 Audio
Runtime、Provider Attempt 隔离、CLI/MCP parity、正式 Web Runtime 与 Creator Web 的多个 Host
路径。这不自动证明生产 Provider、云部署、公开 Release、Channel promotion 或所有物理设备门禁
已经完成；这些状态必须由各自独立证据确认。

Web Runtime Lab 是独立实验工具，不属于 Product Assembly，也不替代正式 Web Runtime Host 或
物理设备验收。

## 事实来源与维护

本图以以下 current truth 为准：

- `products/lmdj/assembly.json` 与 `assembly.lock.json`；
- `packages/*/module.json`、`apps/*/module.json` 与 `providers/*/module.json`；
- Application Facade、Web Runtime Platform、Authoring Domain、Project I/O、Project Cooker、
  Audio Runtime 与 Provider SDK 的当前实现；
- Architecture Portal 的 current pages 和 Portal-owned source diagrams。

历史计划、旧生成图和 `references/demos/` 不作为 current truth。

重新渲染与校验：

```bash
node /Users/endaye/.agents/skills/archify/bin/archify.mjs validate architecture \
  docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json \
  --quality showcase --repo-root . --json

node /Users/endaye/.agents/skills/archify/bin/archify.mjs deliver architecture \
  docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json \
  docs/architecture/assets/lmdj-current-runtime-architecture.html \
  --quality showcase --repo-root . --json

scripts/architecture-portal.sh check
```

不得手改生成的 HTML。任何组件、依赖或权威性边界变化，都先修改 JSON 图源和本文，再重新运行
Archify showcase validation、deterministic delivery、视觉检查及 Portal check。
