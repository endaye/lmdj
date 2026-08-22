# LMDJ Current Runtime Architecture Design

日期：2026-08-22

状态：已批准；本文只定义文档替换与 Archify 产物边界，不改变运行时

## 1. 结论

用一张面向技术团队的 Archify 分层主路径图，替换
`docs/architecture/current-product-architecture.md` 当前仍描述的旧产品链路。新文档只陈述
当前仓库已经实现并由 `products/lmdj/assembly.json` 装配的 Headless Core 运行时：

```text
Web Hosts
    |
    v
Web Runtime Platform
    | application/control plane
    v
Application Facade -> Authoring Domain / Project Truth -> Project Cooker
                                                           |
                                                           v
                                               Immutable Runtime Snapshot
                                                           |
                                                           v
                                                   Audio Runtime

Web Runtime Platform ---------------- realtime data / Voice ------------> Audio Runtime
```

Core CLI 与 Core MCP 只进入 Application Facade；验收专用的 Native Test Host 同时连接
Application Facade 的应用/控制面和 Audio Runtime 的 adapter/realtime 路径。Project I/O 与
Provider SDK/Proof Providers 作为短支路呈现。Product Assembly 是声明式装配与身份边界，
不画成业务流程节点。

正式产物包括可审查的 Archify JSON 源文件、自包含 HTML，以及重写后的 Markdown 技术说明。
旧 Mermaid 源、旧 SVG 和仅供旧图使用的 Mermaid 配置删除，避免仓库继续同时发布两份互相
矛盾的“当前架构”。

## 2. 背景与当前问题

`docs/architecture/current-product-architecture.md` 更新时间为 2026-07-14，仍把以下已经退出
active source 的内容描述为“当前已经跑通”：

- `apps/web/` 与 `apps/api/`；
- `workers/audio/`、`workers/generation/` 与 `workers/render/`；
- `packages/patchify/` 与 `packages/core-models/`；
- `lmdj.patch.v1`、8-Pad Patch 工作台及 Song Pipeline 到 Patchify 的产品闭环。

这与当前仓库的 clean-break 约束冲突。现行源树明确禁止新代码或 current documentation 使用
`lmdj.patch.v1` 和 `lmdj.materials.v1`，`references/demos/` 也只能作为冻结参考材料。

Architecture Portal 已经描述 Headless Core、正式 Web Runtime、Creator Web、Provider Attempt
与 Product Assembly 的当前边界。本任务不重新发明一套产品事实，而是用当前 manifests、实现、
Portal current pages 和测试证据重建 `docs/architecture/` 下已经过时的总览文档。

## 3. 目标

- 给技术团队提供一张从 Host 到 Audio Runtime 的端到端当前运行时图。
- 清楚区分 Host、Web Runtime Platform、Application Facade、Core Modules、Provider 和
  Product Assembly 的所有权。
- 把 `Project Truth -> Cook -> Immutable Runtime Snapshot -> Audio Runtime` 设为主数据路径。
- 明确 Project Bundle、Project I/O、Provider Attempt 和 Runtime Snapshot 的权威性边界。
- 明确 Facade 是 Host 唯一应用/控制面入口，而不是实时逐事件数据面的替代品；Native Test Host
  直接使用 Audio Runtime 只用于实时音频、设备与采集验收。
- 明确 Web Runtime Platform 的 Project/Sample 应用操作进入 Facade，而实时触发与 ordered Voice
  数据面直接连接 Audio Runtime，不逐次穿过 Domain/Cook 链。
- 只呈现当前实现；规划中的生产 Provider、云基础设施和物理设备验收不进入主图。
- 用 Archify 提供深浅主题和 PNG、JPEG、WebP、SVG 导出能力。
- 删除旧图源和旧生成图，恢复“当前架构”名称的单一含义。

## 4. 非目标

本任务不包含：

- 修改任何 Runtime、Core、Host、Provider、Contract 或 Product Assembly 实现；
- 分配 Product Build，修改 Module/Host/Provider/Contract 版本或 Assembly Lock；
- 改变 Application Facade 操作、Project schema、Provider Capability 或 Error Contract；
- 把规划中的生产 Provider、云服务、鉴权、计费、对象存储或数据库画成已实现能力；
- 把 Web Runtime Lab 画成 Product Assembly 成员或正式 Product Host；
- 把 Runtime Snapshot、Workspace State 或 Provider Attempt 写入 Project Truth；
- 修改或重新冻结 Architecture Portal 的 immutable Product Build snapshots；
- 发布 Portal、部署 Web Runtime、push、创建 Pull Request、merge、tag 或 release。

## 5. 当前运行时事实来源

### 5.1 Product Assembly

`products/lmdj/assembly.json` 和 `products/lmdj/assembly.lock.json` 是当前 Product 组合及精确
身份的权威输入。图只显示稳定的组件/职责名称，不手写 Product Build、Module、Host、Provider
或 Contract 版本，避免复制 manifest identity。

当前装配包括：

- Core Modules：Foundation、Authoring Domain、Project I/O、Project Cooker、Audio Runtime、
  Provider SDK、Application Facade、Web Runtime Platform；
- Hosts：Core CLI、Core MCP、Native Test Host、Formal Web Runtime Host、Creator Web；
- Providers：本地成功与失败 Proof Provider；
- Contracts：Project、Project Bundle、Capability、Assembly、Error、Module 与 Product Version。

### 5.2 代码与 Portal current truth

图的组件和连接必须由以下当前证据交叉验证：

- `packages/*/module.json` 与 `apps/*/module.json` 的依赖方向；
- `packages/application-facade/` 的 assembly loader、应用编排与 C ABI；
- `packages/web-runtime-platform/` 的 Manifest Gate、Runtime Session、Control Runtime 与浏览器
  adapter，以及它对 Application Facade/Audio Runtime 的双依赖与 RealtimeEngine 所有权；
- `packages/authoring-domain/`、`project-io/`、`project-cooker/` 与 `audio-runtime/` 的实现边界；
- `packages/provider-sdk/` 与 `providers/local-proof-*` 的 Capability/Attempt 边界；
- Architecture Portal 的 current product、workflow、module、Host 与 Provider 页面；
- `apps/architecture-portal/diagrams/lmdj-product.architecture.json`、`lmdj-core.architecture.json`
  和 `web-runtime-platform.architecture.json`。

历史计划、旧 Mermaid 图和 `references/demos/` 不作为 current truth。

## 6. 方案比较

### 6.1 采用：分层主路径

从左到右显示 Host 到 Audio Runtime 的主链，把持久化、Provider 与 Assembly 放在就近短支路
或说明卡中。

优点：

- 一眼可以追踪主要数据与控制路径；
- 组件所有权和禁止路径清楚；
- 可在十二个左右的节点内完成，不需要交叉箭头；
- 适合作为仓库级技术总览，并能链接到 Portal 的模块细节页。

代价是控制面与实时面不会分成两张独立图；通过 Web Runtime Platform -> Audio Runtime 的显式
`实时数据面 / Voice` 边明确 Facade 不承载实时逐事件数据。

### 6.2 未采用：控制面 / 实时面双平面

将 Facade/Project/Cook 与 Input/Runtime Session/Engine/Voice 分成上下两层。它更适合专门解释
浏览器实时音频，但作为全仓库总览信息密度较高，Provider 与 Assembly 也容易变成第三层。

### 6.3 未采用：运行时旅程

按“打开/编辑 -> Cook -> 播放”组织。它适合产品演示，但弱化 Module 依赖、权威状态与 Host
入口规则，不满足本次技术团队受众的主要目标。

## 7. 图的组件与布局

图采用 Archify `architecture` 模式和静态布局，不启用 trace animation。主视图包含以下节点：

| 位置 | 节点 | 副标题/职责 |
| --- | --- | --- |
| 左上 | Web Hosts | Creator Web · Formal Runtime Host |
| 左下 | CLI / MCP Hosts | terminal · stdio MCP |
| 右下 | Native Test Host | acceptance · device · capture |
| 中左 | Web Runtime Platform | manifest gate · browser runtime session |
| 中部入口 | Application Facade | application/control-plane entry · orchestration |
| 中部 | Authoring Domain | Project Truth · commands · revision |
| 中右 | Project Cooker | validate · derive |
| 右上 | Runtime Snapshot | immutable derived state |
| 最右 | Audio Runtime | prepared samples · realtime/offline/preview |
| 下方支路 | Project I/O | atomic store · bundle transfer · workspace cache |
| 下方支路 | Provider SDK | capability · registry · attempt store |
| 下方终点 | Proof Providers | artifact input/output · isolated failure |

Foundation 不额外制造指向所有 Module 的扇出箭头，而在说明卡中描述为 Artifact、JSON 和 typed
error 的共同底座。Contracts 同样放入说明卡，说明它们是 versioned cross-language boundaries，
而不是运行时服务。

Product-neutral Core 使用一个边界框包住七个显式 Module 节点和 Runtime Snapshot；Foundation
作为第八个 Module 放在说明卡中，避免扇出箭头。Host、Proof Provider、Product Assembly 说明卡
位于该边界外，保持产品装配与产品中立代码的区别。

## 8. 连接与权威性语义

### 8.1 主路径

```text
Web Hosts
  -> Web Runtime Platform
  -> Application Facade
  -> Authoring Domain / Project Truth
  -> Project Cooker
  -> Runtime Snapshot
  -> Audio Runtime
```

- Web Hosts 通过 shared Web Runtime Platform 完成 Host identity、preflight、Runtime Session、
  input/lifecycle 和 typed protocol adaptation。
- Web Runtime Platform 的 Project/Sample 应用操作进入 Facade；已经准备的运行时状态、实时触发
  与 ordered Voice state 通过 Platform 的 Audio Runtime 接线流动，不逐次经过 Domain/Cooker。
- Application Facade 是所有 Host 的唯一应用/控制面入口，负责跨模块应用编排和稳定错误语义。
- Authoring Domain 是 Project Truth 唯一所有者。
- Project Cooker 校验 Project 和 Artifact，生成可丢弃、可重建的 Runtime Snapshot。
- Audio Runtime 只读消费 Snapshot 准备的运行时数据；它不把运行时状态写回 Project。

### 8.2 支路

- Web Runtime Platform -> Audio Runtime：ControlRuntime、input adapter 与 AudioWorklet 的实时
  数据面/Voice 路径；不得借此绕过 Facade 修改 Project Truth。
- Core CLI / Core MCP -> Application Facade：不经过浏览器 adapter，也不解析 Project bundle。
- Native Test Host -> Application Facade：应用/控制面操作仍经 Facade，不解析 Project bundle。
- Native Test Host -> Audio Runtime：仅通过 adapter/realtime 路径验证实时音频、设备与采集；
  它不是产品 UI，也不得承载产品业务规则。
- Authoring Domain/Application Facade -> Project I/O：事务式 store、revision、Take recovery、
  portable Bundle transfer 与 Workspace cache。
- Application Facade -> Provider SDK -> Proof Providers：Provider 只接收 Artifact input 和
  Artifact output sink，运行状态/失败保存在 Attempt/Workspace State。
- Product Assembly：通过说明卡表达 exact module/Host/provider/contract wiring，不连接成业务
  请求链。

### 8.3 禁止路径

图和 Markdown 必须显式列出：

- Host 不解析 Project Bundle；
- Provider 不接收 mutable Project 或 Project bundle path；
- Provider selection 和 Provider failure 不进入 Project Truth；
- Runtime Snapshot 不持久化成 Project Truth，也不反写 Project；
- Pattern event 指向 Pad Slot，不直接指向 Asset；
- `references/demos/` 和退役 Contract 不属于 active runtime。

## 9. 视觉编码

- 绿色 emphasis 箭头：端到端主要运行路径；
- 中性实线：就近持久化、导入/导出或装配关系；
- 虚线：Provider Attempt 等隔离支路；
- `c-frontend`：Host；
- `c-backend`：Core control/application module；
- `c-database`：Project Truth、Project I/O 或 immutable derived state；
- `c-external`：Proof Provider；
- amber region：Product-neutral Core 边界；
- 说明卡：Foundation、Contracts、Product Assembly 和禁止路径。

边标签只用于跨边界或不明显的语义，例如 `typed API`、`commands`、`derive`、`read-only`、
`atomic persist` 和 `artifact I/O`。相邻主路径不重复写无信息量标签。

节点名称保持短而稳定；目录路径或职责进入副标题。颜色只使用 Archify CSS class/variable，保证
深浅主题一致，并保留键盘可操作的主题和导出菜单。

## 10. 文档与资产替换

Implementation 修改范围：

- Rewrite：`docs/architecture/current-product-architecture.md`；
- Add：`docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json`；
- Add：`docs/architecture/assets/lmdj-current-runtime-architecture.html`；
- Delete：`docs/architecture/assets/lmdj-current-product-architecture.mmd`；
- Delete：`docs/architecture/assets/lmdj-current-product-architecture.svg`；
- Delete：`docs/architecture/assets/mermaid-config.json`，但仅在引用审计证明它只服务于旧图时。

引用审计允许历史 implementation plan 继续记录这些旧路径；历史计划是不可改写的实施记录，
不是 current consumer。删除前必须证明除待重写的 current 文档和历史记录外，没有构建脚本、
current 文档或其他活跃资产依赖它们。

重写后的 Markdown 包含：

1. 自包含 Archify HTML 的相对链接；
2. 如何阅读主路径和支路；
3. 当前组件职责表；
4. 权威状态、禁止路径和当前实现边界；
5. 图的事实来源与重新渲染/校验命令。

HTML 是可打开、可导出的视觉产物；JSON 是可 review、可重复渲染的源文件。Markdown 是仓库内
可搜索的技术说明。三者表达同一 topology，不分别维护不同事实。

## 11. 错误处理与防漂移

- Archify schema、layout 或 HTML check 任一失败都阻止提交；不得手改 renderer 生成的 HTML。
- 节点重叠、越界、标签碰撞、未知 connection endpoint 或对角双点箭头必须修正 JSON 源。
- HTML 必须保持主题切换和导出脚本完整，SVG 内不新增硬编码色值。
- 图不手写版本号和 Product Build；精确身份继续由 Assembly/Lock 与 Portal facts 展示。
- Markdown 不声明 CI、物理设备、部署、Release 或 Channel 已通过，除非当前证据明确支持。
- 若实现审计发现 Web Runtime 或 Provider 实际连接不同于本规格，先修正规格并再次取得用户批准，
  不以“让图更顺”代替代码证据。

## 12. 验证与验收

### 12.1 Archify 验证

从 Archify skill 目录运行：

```bash
node bin/archify.mjs render architecture \
  /absolute/path/to/lmdj-current-runtime-architecture.architecture.json \
  /absolute/path/to/lmdj-current-runtime-architecture.html

node bin/archify.mjs validate architecture \
  /absolute/path/to/lmdj-current-runtime-architecture.architecture.json --json

node bin/archify.mjs check \
  /absolute/path/to/lmdj-current-runtime-architecture.html
```

### 12.2 仓库验证

```bash
if rg -n "apps/api/|apps/web/|workers/audio/|packages/patchify/|8-Pad Patch|Song Pipeline" \
  docs/architecture/current-product-architecture.md \
  docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json; then
  exit 1
fi

rg -n "已退役，不属于当前链路" docs/architecture/current-product-architecture.md

scripts/architecture-portal.sh check
git diff --check
```

第一条命令预期无匹配并退出 0；第二条命令必须精确命中一次，证明 current 文档只为明确排除而
提及退役 Contract。另需审计 `mermaid-config.json` 的所有引用后才能删除该文件。

### 12.3 视觉验收

- 在浏览器分别检查深色和浅色主题；
- 主路径无需回看图例即可从左向右追踪；
- 所有组件、边界、标签和 legend 在 viewBox 内，无重叠或截断；
- 导出菜单可生成至少一种 raster 格式和 SVG；
- 在常见桌面宽度下，Markdown 链接能直接打开自包含 HTML；
- 图中的每条关键连接都能回溯到本规格第 5 节的当前证据。

## 13. Version Management

Version impact: none.

原因：该 Task 只修复和替换架构文档及其可视化资产，不改变 Product、Module、Host、Provider、
Contract、Model、Assembly、Runtime behavior 或发布产物身份，不分配 Product Build。

## 14. Documentation Impact

Architecture Portal impact: none.

原因：当前 Portal pages 和 Portal-owned diagrams 已正确陈述现行 Headless Core；本 Task 修复的是
`docs/architecture/` 下独立且过时的旧产品架构文档，不改变任何实现事实、Assembly、Portal route
或 immutable snapshot。Portal 仍运行完整 check，证明新增文档没有造成 current truth、diagram、
build、route 或 identity 漂移。

## 15. 提交与操作边界

- 设计规范单独形成一个 `docs:` Conventional Commit；
- 用户 review 并批准本规范后，另写 implementation plan；
- 正式文档替换与 Archify 产物形成后续独立 `docs:` Commit；
- 每个 commit 只 stage 本 Task 声明的文件，并在提交前检查 staged diff；
- 本任务的本地 commit 不授权 push、Pull Request、merge、deploy、release 或 publication。
