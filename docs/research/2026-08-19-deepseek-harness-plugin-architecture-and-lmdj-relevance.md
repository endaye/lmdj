# DeepSeek Harness 插件架构与 LMDJ 技术相关性报告

> 日期：2026-08-19
>
> 文档状态：技术研究报告，不是已批准设计、实现计划或发布证明
>
> DeepSeek Harness 基线：`0.1.0-rc.5`，源码提交 `47f943859bef60e4160492346772ded9b24f765a`（`deepseek-ai/deepseek-harness`，MIT，developer preview）
>
> LMDJ 基线：`7a11821ecf5f2b3eaccdb5338cd44802502df4bd`（Product Build `1.0.23.0`）
>
> 配套资料：本次研究产出的采纳决定见 [dsh 派生加固目标](../plans/2026-08-19-lmdj-dsh-derived-hardening.md) 及其两份实施计划

## 1. 结论先行

### 1.1 总体判断

DeepSeek Harness（下称 dsh）宣称的「一切皆插件」在产品层**基本兑现**，这在真实产品代码库里罕见。但它与 LMDJ 的最佳关系不是「照它的方式重做 Provider 体系」，而是：

> **保持 LMDJ 封闭世界、链接期组装、双重声明、内容寻址的 Provider 体系不变；只借入 dsh 围绕其动态性长出来的工程纪律。**

理由：

1. **dsh 的动态性是用「插件零隔离」换来的。** 每个插件拿到完整 `ctx`，因而拥有全部服务与完整 Node 权限；文档明说第三方 bundle 的安装钩子等于「在你机器上执行代码的许可」。它的微内核服务于**可替换性与可测试性**，不服务于**信任**。

2. **LMDJ 的产品形态需要相反的性质。** 可审计的 Attempt 溯源、签名 Product Build、不可伪造的模型身份，都要求「一个 Git SHA 对应一个可完整枚举的行为集合」。封闭世界正是这个性质的来源。

3. **真正可迁移的是纪律，不是机制。** 注册即可逆效果、模型可见即已入日志、生产日志即测试夹具、文档即编译产物、失败即制度化知识——这五条与封闭世界完全兼容，且每一条都命中 LMDJ 已知的缺口。

### 1.2 建议等级

| 建议 | 等级 | 依据 |
| --- | --- | --- |
| 基于 Attempt 记录的确定性重放 | **建议采纳** | 原料已备齐且优于 dsh 起点；是真实 Provider 落地后 CI 不依赖外部服务的唯一路径 |
| Event 层的分发语义契约 + 生成的生产者/消费者矩阵 | **建议采纳（随 §12.4 实施）** | 现在成本是一段文字，事后是一次迁移 |
| 运行时不变量检查 | **建议采纳** | LMDJ 的一致性保证全在构建期；运行期只有加载边界的 fail-closed |
| 运行期插件装载 / 热替换 | **建议否决** | 见 §1.1 第 1、2 点；且 dsh 为让热替换事务化付出 6 处框架级 fork |
| 默认 Provider 与静默回退 | **建议否决** | 与 Attempt 可审计性互为因果；规格 §24 已深思后否决 |
| Provider 贡献 API 表面 | **建议否决** | dsh 为此需要 UI 槽位目录、事件白名单等一整套防漂移机器 |
| 契约代码生成（Typert 式） | **建议否决** | 深度绑定单一语言编译器；LMDJ 跨 C++/Python/JS 的四点独立执行更稳健 |

## 2. 研究范围与证据口径

### 2.1 本次研究回答的问题

1. dsh 是什么，端到端如何运行，仓库如何分层。
2. 「一切皆插件」在代码里如何实现：插件接口、注册与发现、生命周期、通信机制、组装方式。
3. 哪些东西**不是**插件——真正的内核边界在哪。
4. 跨语言与跨进程边界怎么划，契约归属谁。
5. 版本、发布与测试策略——尤其是插件生态专属的测试规则。
6. 宣称与代码的差距。
7. 设计上真正独到之处。
8. 与 LMDJ Provider/Capability 体系的逐维对照，以及可迁移的部分。

### 2.2 证据标签

- **[源码]**：直接读取 `47f9438` 的源文件得出，含文件路径。
- **[生成文档]**：dsh 自身由源码生成并受 CI 新鲜度门禁保护的目录（`docs/module-graph.md`、`docs/capability-seams.md` 等）。
- **[宣称]**：README 或文档的表述，本报告对其单独核查。
- **[对照]**：与 LMDJ `7a11821e` 的源码对比得出。

### 2.3 不在本报告中承诺的事项

- 不承诺任何 dsh 代码可直接引入 LMDJ。dsh 是 TypeScript/Node 生态，LMDJ Core 是 C++20；不存在直接复用路径。
- 不评价 dsh 的产品质量、性能或商业前景。仓库内 `BENCHMARK.md` 只有三行说明、无任何数据，本报告不推测其性能。
- 不构成对 LMDJ 规格 §12.3（Job）、§12.4（Event）的设计批准。相关约束以采纳文档为准。
- 不涉及 Provider 字节访问缺口的裁定，该问题已由 `docs/prd/decisions/2026-08-24-provider-artifact-byte-access.md` 裁定。

## 3. dsh 是什么

### 3.1 定位

**[宣称]** README 开篇：dsh 是 DeepSeek AI 开源的 agent harness，架构上「everything is a plugin」，由 Cordis 框架驱动。

**[源码]** 一份藏在翻译校准文件 `docs/i18n/style-samples.md` 里的表述给出真实定位——dsh 是 **DeepSeek Code 产品的地基**：「内核刻意做小：一组抽象服务加一个具体的循环插件（`dsh-agent-loop`），每个产品功能都是针对扩展 API 的插件」。

约 2,500 个 PR 的历史，MIT，developer preview，明确声明「会有破坏兼容的变更」。

### 3.2 端到端路径

**[源码]** `npx @deepseek-ai/dsh web` → `apps/cli/src/bin.ts` 解析 argv 为 `profile`/`plugin`/`dump-config` 三种模式 → `runProfile`（`apps/cli/src/profile-boot.ts`）在 `$DSH_HOME/profiles/<name>` 解析 profile，在**空插件表**上叠加 bundle patch 层 → `boot()` → Cordis Loader 挂载整棵插件树 → 树内含 HTTP 服务器、Typert RPC 网关，以及**运行在浏览器里的第二棵 Cordis 树**，落地在 `http://127.0.0.1:3080`。

`dsh --profile headless "task"` 挂载一次性 runner，完全无服务器。Python 调用方通过 stdio 上的换行分隔 JSON-RPC 驱动打包好的单文件运行时。

### 3.3 仓库拓扑

| 目录 | 内容 |
| --- | --- |
| `vendor/` | 9 个钉版本的 Cordis 系源码拷贝，重命名到 `@deepseek-ai/*`（框架层） |
| `packages/` | 213 个 workspace，47 个分组（core、llm、tool、sandbox、session、client…） |
| `apps/cli` · `apps/web` | `dsh` 命令行入口；浏览器前端构建 |
| `python/sdk` · `python/sdk-runtime` | Python SDK 与打包运行时 |
| `native/landlock-run` | 约 300 行 C11 的 Landlock 自限制启动器，静态 musl |
| `examples/` | 可运行的 `cordis.yml` 叶子，单一 workspace 成员 |
| `docs/` · `.agents/` | 双语文档、6 份生成目录、4 篇编号 postmortem、Agent Notes 制度 |

**[生成文档]** 依赖图由 `peerDependencies` 推导（「唯一权威的运行时依赖信号」），`docs/module-graph.md` 由 `pnpm run gen-module-graph` 生成并受 CI 新鲜度门禁保护。

## 4. 「一切皆插件」的实现机制

### 4.1 Cordis 微内核：插件 = 挂在上下文树上的可逆效果

**[源码]** `vendor/cordis/src/registry.ts` — 插件是函数、类或对象，接收 `(ctx, config)`：

```ts
export interface Base<T = any> {
  name?: string
  Config?: StandardSchemaV1<any, T>   // Schemastery 或任何 standard-schema
  inject?: Inject                     // 所需服务全部在场时才挂载
  provide?: string | string[]
  intercept?: Dict<boolean>
}
```

三条纪律撑起整个体系：

1. **注册即效果。** 一切贡献走 `ctx.effect()` / `ctx.on()`，注册函数返回销毁器。卸载插件的 Fiber，其全部注册自动收回。每个注册表都配一个「HMR 安全测试」：销毁 Fiber，断言贡献消失。
2. **服务随 Fiber 生灭。** `vendor/cordis/src/service.ts` 的 `Service` 基类在构造时向反射层登记，宿主 Fiber 卸载即自动注销。
3. **加载是动态、配置驱动的。** Loader 读 YAML 条目表，按包名解析、逐行挂载为 Fiber；HMR 插件对**代码和配置都**做热替换。

`Fiber`（754 行）是生命周期引擎，是整个框架里最承重的单个文件。

### 4.2 插件间通信：四条全类型化通道

**[源码]** ① **服务定位 + 声明式注入**（约 60 个 `ctx.*` 键）；② **类型化事件总线**（约 60 个事件）；③ **注册表模式**（`register()` 返回销毁器）；④ **配置面组合**（patch 行内 `!!js` 表达式在该行自己的注入上下文中求值）。

事件的**四种分发模式是公开契约的一部分**：

| 模式 | 等待 | 顺序 | 返回值 | 用途 |
| --- | --- | --- | --- | --- |
| `emit` | 否 | 注册序 | 无 | 通知 |
| `waterfall` | 否 | 注册序 | 有 | **环绕式中间件**：拿到 `next()`，可短路 |
| `parallel` | 是 | 并行 | 无 | 扇出 |
| `serial` | 是 | 注册序 | 有 | 串行裁决 |

`waterfall` 是这套体系的关键：监听者收到 `(...args, next)`，调 `next()` 委托下去，不调则短路。规范里是硬性要求——**waterfall 监听者必须调 `next()`**。

**[生成文档]** 事件扇出是真实负载而非装饰：`agent/pre-step`（waterfall）有 **13 个监听包**（压缩、计划模式、钩子桥接、技能注入、时间与 tmux 上下文注入、子代理驱动、会话检查点策略…），`session/event` 有 23 个。这就是「一切皆插件」的实际含义：**新功能 = 新的事件监听者或新的服务实现，主循环代码一行不改**。

### 4.3 配置面组装：bundle × profile × patch 层叠

**[源码]** 三个概念、三个 `package.json` 清单键：

- **bundle**：包声明「我贡献哪些插件行」，指向一个 `cordis.patch.yml`。
- **profile**：用户目录声明「装哪些 bundle、什么顺序」。
- **client 插件**：包声明浏览器侧那一半（39 个包声明了它）。

叠加顺序（`apps/cli/src/profile-boot.ts`），起点是**空表** `[]`：bundle 顺序 → profile 自身 patch → 家目录 patch → 命令行 `--patch`。后层按行覆盖前层，且 **patch 替换整个 `config`，无深合并**（文档记录的已知限制）。

`dsh --dump-config` 用**同一套**解析器与叠加函数渲染最终结果，保证「看到的即挂载的」。

### 4.4 双平面组合：每个会话一棵自己的插件子树

**[源码]** 这是 dsh 最锋利的设计。**agent preset** 是第二棵、会话平面的 Cordis 子树：进程内挂载一次，每个声明使用它的会话把自己的 agent 作用域挂到该子树下。服务解析按 `agent → preset → global` 就近遮蔽。

preset 里的服务行**必须**放在带 `isolate` realm 的分组里，否则挂载直接被拒——`apps/cli/config/agent-presets/code/agent.cordis.yml` 原文警告：没有 isolate 就会发布到 root realm，变成进程全局，第二个会话挂载时与第一个碰撞。

结果：`minimal` preset 可以用裸 `fs-local` **遮蔽宿主的沙箱化 `ctx.fs`**、只给模型两个工具；同一进程里 `code` preset 的会话跑着完整工具集。**每会话能力集是一份配置文件，不是一条代码路径。**

### 4.5 插件类别：约 25 条接缝、约 40 个可换实现

**[源码]** 每一类都是「一个服务定义 + 多个可换 provider」。这张表是「一切皆插件」的具体含义：

| 类别 | 服务键 | 可换实现 |
| --- | --- | --- |
| 模型适配器 | `ctx.llm` | `llm-deepseek`、`llm-pi-ai`、`llm-retry`、`test-support/llm-replay` |
| 模型侧工具 | `ctx.tools` | `tool-bash`、`tool-fs`、`tool-fs-search`、`tool-str-replace-editor`、`tool-web`、`tool-todo`、`tool-skill`、`tool-subagent`、`tool-jobs`、`tool-workflow`、`tool-ralph`、`tool-goal`、`tool-lsp`、`tool-terminal`、`tool-pwsh`、`tool-ask-user`、`tool-session-query`、`tool-cordis`，外加经 `mcp-client` 接入的全部 MCP 工具 |
| 会话持久化 | `ctx.sessionPersistence` | `session-persistence-jsonl`、`session-persistence-sqlite` |
| 会话检索 | `ctx.sessionQuery` | `session-query-sqlite`（FTS）、`session-log-export` |
| 会话投影/标题/遥测 | `ctx.sessionProjections` 等 | `session-projection-cache`、`session-title-first-prompt-llm`、`session-title-all-prompts-llm`、`session-telemetry-otel` |
| shell / PTY / 子进程 | `ctx.shell`、`ctx.terminals`、`ctx.subprocess` | `bash-local`、`bash-sandbox`、`pwsh-local`、`pwsh-sandbox`、`terminal-bash`、`subprocess-local`、`subprocess-e2b` |
| 文件系统 | `ctx.fs` | `fs-local`、`fs-sandbox`、`fs-observation-policy`、`fs-e2b` |
| 进程围栏 | `ctx.sandbox` | `sandbox-local`（bwrap/Landlock/Seatbelt）、`sandbox-windows-acl` |
| 代码执行 | `ctx.codeRuntime` | `code-runtime-worker-thread` |
| 子代理 | `ctx.subagents` | `subagent-spawn-in-process`、`subagent-fork-in-process`、`subagent-dsh-sdk`、`subagent-acp`、`subagent-claude-code`、`subagent-codex` |
| 工作流 / 后台任务 / 技能 | `ctx.workflowEngine`、`ctx.jobs`、`ctx.skills` | `workflow-worker-thread`、`jobs-local`、`skill-filesystem`、`skill-badge` |
| 网页访问 | `ctx.web` | `web-search-deepseek`、`web-search-exa`、`web-search-perplexity`、`web-fetch-http` |
| 上下文压缩 | `ctx.compaction` | `compaction-basic`、`compaction-tool-result-pruner`、`command-compact` |
| 人机交互 | `ctx.approval`、`ctx.userQuestions` | `user-approval`、`user-questions`、`commands`、`permission-presets` |
| 设置/凭据/存储 | `ctx.settings`、`ctx.credentials`、`ctx.storage` | `settings-file`、`credentials-local`、`storage-json`、`storage-sqlite`、`spill-local`、`attachment-local` |
| Web 宿主 | `ctx.webServer` 等 | `host/webserver`、`host/apiproxy`、`host/frontend-static`、`host/directory-picker-*` |
| 浏览器 UI | 槽位注册 | 30 个 `packages/client/ui-*` 插件 |
| 协议通道 | — | `sdk/server`（JSON-RPC）、`acp/acp`、`hooks-claude-code`、`hooks-codex` |
| 诊断 / 自我修改 | `ctx.invariants`、`ctx.cordisInspect` | `runtime-diagnostics/invariants`、`extensions/cordis-host-runner`、`tool-cordis`、`ui-cordis` |

**[源码]** 已核实连主循环也是普通插件：`packages/core/agent-loop/src/index.ts` 的 `AgentLoop extends Service`，`static inject = ['agents','sessions','llm','tools','systemPrompt']`；`SessionStore`、`ToolRuntime`、`AgentRegistry`、`LlmRuntime` 同理。

依赖方向有明文规则并被清单核实：**「扩展插件依赖服务定义，绝不依赖具体 provider」**。`dsh-agent-loop` 只出现在 `bundle/base` 与 `examples/agent-spine-demo` 两个组装包的依赖里，规则成立。

反例值得记：`packages/schedule` 只有一个实现，**没有可换接缝**，也没有对应的 `ctx` 键给替代实现——说明「一切皆插件」在边缘处也有例外。

### 4.6 真正的内核边界

**不是插件的**：

1. **vendored 框架本身**（`vendor/`，Cordis 核心 2,693 行 + Loader/Include/Group/HMR/Timer）。配置面不可达，只能改 vendored 源码——**且已有 18 处本地改动记录**，其中 6 处专为让配置调和事务化、无死锁。
2. **启动器** `apps/cli/src/{bin,args,profile-boot,plugin,dump-config,process-shutdown}.ts`（832 行）。硬编码层叠优先级、`DSH_TELEMETRY_DISABLED` 开关、信号→退出码映射（SIGTERM→0、SIGINT→130）、按字面包名兜底挂载 timer/hmr。
3. **约 15 个明确标注为纯库的包**：`util/*`、`core/scope`、`sdk/protocol`（「无插件、无 Config、无注册」）、`sdk/client`、`typert/protocol`、`typert/generator`、`hooks/hook-protocol`、`boot/app-boot`。

## 5. 跨语言与跨进程边界

**[源码]** 五条边界，每条有明确的契约归属方。这一节对 LMDJ 有直接参考价值，因为 LMDJ 自己也要跨 C++/Python/JS。

| 边界 | 机制 | 契约归属 |
| --- | --- | --- |
| TS ↔ Python | 换行分隔 JSON-RPC 2.0 over stdio | `packages/sdk/protocol`；服务端 `sdk/server` 是一个 Cordis 插件；`python/sdk` 的 `client.py` **镜像这些形状但不 import 它们** |
| TS ↔ native | **进程 exec，不是 FFI** | `native/landlock-run` 只暴露三个函数：`launcherPath()`、`probe()` → `'full'\|'partial'\|'unusable'`、`grantArgs({readOnly, readWrite})`；调用方自行 spawn |
| 宿主 ↔ 浏览器 | Typert RPC over Connection | `packages/typert/*` + `packages/api/*`，见下 |
| 进程内隔离 | worker 线程 | `code-runtime-worker-thread`、`workflow-worker-thread`；文档明说**「不是安全边界」** |
| 外部 agent 协议 | ACP、Claude Code / Codex hooks、MCP | `packages/acp/acp`、`hooks-claude-code`、`hooks-codex`、`mcp/mcp-client` |

值得单独记的两点：

**JSON-RPC 上流的是完整会话日志包络。** 文档原文：「协议流的是完整的 session-log envelope，所以会话词汇是线协议的一部分」。这与 LMDJ 把 Attempt 记录声明为**实现私有格式、明确不是跨语言契约**恰好相反——dsh 选择把内部日志形状暴露成协议，代价是内部重构即协议变更（它用「无兼容承诺」承担了这个代价）。

**native 包 fail-closed，无安装期构建兜底。** 入口包 + `-linux-x64`/`-linux-arm64` 可选依赖；平台包缺失时解析出的路径根本不存在，探测报 `unusable`，调用方**向关闭方向失败**。这与 LMDJ 的加载器哲学同构。

### 5.1 Typert：从 TS 源类型编译 RPC 契约

**[源码]** 这是整个仓库里最不寻常的工程。构建期跑 `ts.Program` 遍历 `tsconfig.host.json`，把源类型树转成与编译器无关的 `FaceModel` + `TypeGraph`，然后产出**类型锚定的** Zod schema（`z.ZodType<SourceType>`）与一份 `TYPERT` 贡献产物。**不支持的 Zod 投影直接编译失败，而不是压平或弱化源类型。**

声明方式是装饰器 `@Remote('name')` / `@RemoteScope(key)`。复杂宿主对象过不了线，包需要在可合并扩展的 `TypertLookupMap` 里声明关联——例如名为 `agent` 的 `Agent` 参数在线上变成 `agentId` 字段，由网关先解析再调用。取消是带外的 `signal: AbortSignal` 末参，「永不变成 JSON 参数」。

错误分类是 17 个稳定码的封闭联合。**事件转发白名单**（`packages/api/remotes/src/remote-events.ts`）被编入宿主与客户端**两侧**，物理上不可漂移。

Schema 栈共三层：Schemastery 管插件 `Config`（109 个源文件引用）→ Zod 管 Typert 线契约（38 个）→ 裸 JSON Schema 管模型可见的工具参数。插件 `Config` 是 standard-schema 槽位，任何 standard-schema 校验器都能用。

## 6. dsh 的版本、发布与测试策略

**[源码]** 这一节记下来是因为 LMDJ 有相似的门禁文化，可作对照。

**发布分三个独立家族**（`scripts/release/families.ts`）：`dsh`（`packages/` + `apps/`）、`vendor`（9 个重命名框架包）、`native`（landlock-run 的 3 个包）。各自有版本基线、tag 命名与发布集，「发布其中一个绝不会连带重发另一个」。vendored 包**保留上游版本号**（cordis `4.0.0-rc.7` 等），dsh 包锁步在 `0.1.0-rc.5`。

**兼容立场**明确写在 `AGENTS.md` 并标注「首个 tagged release 时删除本节」：「尚无外部消费者，优先要正确的地基而非兼容垫片：自由重命名或重打包，同时更新所有引用。后端拒绝旧的磁盘格式。」`SESSION_FORMAT_VERSION` 钉在 `0`、无兼容承诺。

但会话日志的版本机制本身相当克制：`SessionEventMap` 成员**默认读时必需**——不认识某个事件类型的构建会**拒绝整份日志**，除非该事件带 `ignorable: true`；只有结构性格式变更才动 `SESSION_FORMAT_VERSION`。

**测试分层**：

| 层 | 内容 |
| --- | --- |
| 单元 | vitest；**每个注册表都要有 HMR 安全测试**——销毁 fiber，断言清理干净 |
| 覆盖率门禁 | `packages/*/*/src` **逐文件 100%**。原话：「未覆盖的行往往是门禁正确标出的死代码」 |
| 真实 API e2e | 带 key 打真实服务，按 key 自跳过。策略原文：「我们就是 DeepSeek——不要限量真实 API 测试」 |
| 快照 | 无 key 的确定性重放，夹具即生产日志 |
| 浏览器快照 | Chromium 对比，Linux 上是必需的 PR 门禁 |

**插件生态专属规则**（`packages/AGENTS.md`）值得摘录三条：

- 「产品可见的插件需要一个非单元的**真实组装**测试。手搭的 `ctx.plugin(...)` 套件不够。要通过 Loader 与 app/process 启动一份测试用 `cordis.yml`。」
- 「『真实入口路径』指已构建的产物：包的 `bin` 要跑构建后的 `lib/bin.js`、用普通 `node`，暴露 tsx 会掩盖的失败。」
- 对无 `inject` 的插件，Loader smoke 在「默认导出替换了具名导出」时仍会绿——所以必须显式加 `expect('default' in mod).toBe(false)`，并且要求**先引入回归、看它变红、再回退**。这条来自编号 postmortem `0001`：混用默认导出与具名导出使 Loader 丢弃了插件命名空间，静默丢掉了 `inject`。

另有约 30 个文档与卫生门禁：`knip`、`publint`、`jscpd` 克隆检测、`verify-vendored-links`（断言每个 vendored 名字都解析到 workspace `link:`、注册表里没有副本）、`verify-cordis-config`、`verify-runtime-closure`、`verify-export-jsdoc`、`verify-doc-budgets`、`verify-translation-pairing`，以及六个目录生成器的 `--check` 模式。

## 7. 宣称与代码的差距

**[宣称]** 文档的强形式：*「Every part of the product is a plugin… There is no privileged core to patch.」*

逐条核查：

| 宣称 | 代码现实 |
| --- | --- |
| 没有特权核心 | **有。** vendored Cordis 配置面不可达，且已积累 18 处本地 fork，含 Fiber 生命周期加固、事务化配置调和、HMR 死锁修复等承重改动。宣称对**产品层为真，对框架层为假** |
| 一切可从配置替换 | **启动器不可。** 层叠优先级、遥测开关、信号映射、兜底挂载全部硬编码 |
| 微内核 + 细粒度插件 | 实际组合单元是 **bundle 而非行**：`dsh-base` 是一份 451 行、约 85 个依赖的单块 patch；覆盖一行须整体重写其 `config`（无深合并） |
| 插件沙箱 / 能力安全 | **不存在。** 插件拿到完整 `ctx` 即全部服务；第三方 bundle 以完整 Node 权限进程内运行。`ctx.sandbox` 围栏的是**子进程**，不是插件。动态插件的 `node:vm` 与 worker 线程都**自述「不是安全边界」** |
| 稳定插件 API | 会话格式版本钉在 `0`、「无兼容承诺」；JSON-RPC 无协议版本协商；贡献指南明言「自由重命名重打包」。包清单里整列的「Product — stable API」目前是愿景 |
| `agent-loop` 可换 | 结构上成立（仅两个组装包依赖它），但库内**只有一个实现**，可换性从未被第二实现检验 |

**核查结论：差距不在「可组合性」——那部分兑现得异常扎实——而在「隔离」。** 全系统真正的安全边界只有两个：子进程沙箱（landlock-run 一族）与人工审批门。

## 8. 设计上真正独到之处

1. **事件溯源硬不变量：「模型可见 ⟺ 已入日志」。** 任何进入模型请求的内容必须可从会话日志重建，且有运行时不变量断言。崩溃恢复不截断未闭合的 turn，而是追加合成的 `turn/end {kind:'interrupted'}`——且 `interrupted` 是任何循环都不会主动发出的终止原因，**被修复的 turn 永远可辨认**。

2. **生产日志即测试夹具的确定性重放。** `packages/test-support/llm-replay` 直接把生产 `session.jsonl` 当夹具，按 `(turn, step)` 重组每次流式调用；「录制」= 跑一次真 agent 收割日志。嵌套子代理各有一份日志，按**首次调用顺序**绑定（因为线上 session id 是随机的）。不可重建的失败形态（流前抛错、挂起/取消）用带校验的 sidecar 补齐。

3. **运行时不变量注册表。** `ctx.invariants` + 全部 213 个包各带一个 `./invariant` 导出（或书面豁免，由 `verify-package-invariants` 门禁）。明确**排除**类型层、加载期或单测已能保证的东西，只检查真实的事件/数据关系：会话包络、收件箱 FIFO 守恒、流语法、工具流水线阶段序、审批「问/答」配对审计。

4. **文档是编译产物。** 六份生成目录（模块图、工具、配置、能力接缝、持久化、事件生产者/消费者矩阵）配 `--check` 新鲜度门禁。配置目录生成器把运行时 Schemastery schema 与文档里粘贴的 TS 声明互相核对，「粘贴藏不住 loader 接受的字段」。

5. **Agent 可修改自己的运行时。** `packages/extensions/tool-cordis` 给模型五个工具（inspect/define/run/stop/undefine），可在它正运行的进程里定义并收回 Cordis 插件。模型读到的 API 目录与人类文档**出自同一个 AST 遍历**，「模型读的数据与渲染的文档不可能分叉」。

6. **事务化的双热替换。** 代码与配置皆可热载；被拒的读取/解析/挂载让**上一棵好树继续运行**并广播失败事件。`profile-boot.ts` 对每一代做 `structuredClone`，因为 include 会把 `insert` 行按引用推入已挂载的树，复用同一对象会把用户覆盖烧进 bundle 的内存行里，使移除覆盖再也无法回退。

7. **Typert：从 TS 源类型编译 RPC 契约。** 构建期跑编译器把源类型树转成模型无关的 FaceModel，产出**类型锚定的** Zod schema（`z.ZodType<SourceType>`）；不支持的投影**直接编译失败而非静默弱化**；事件转发白名单单文件编入两端，物理上不可漂移。

8. **fail-closed 的原生沙箱与诚实的 partial 上报。** landlock-run 先自我限制再 exec（规则集经 execve 继承，宿主本身不受限）；内核无法执行即拒绝运行。老 ABI 与 Windows ACL 只能如实上报 `partial`——连误报 partial 的事故都有编号 postmortem。

9. **失败知识的制度化。** 防御模式手册 + 4 篇编号 postmortem + 四态 Agent Notes（提议/已实施/已否决/归档冻结），并规定「非平凡变更必须在同一 PR 附 Note」「归档笔记冻结，永不当作现行权威」。样例规则：「dispose 必须到达静默而非仅请求静默——测试要证明 `await fiber.dispose()` 后进程立即消失，而不是最终会死」。

## 9. dsh 与 LMDJ 的逐维对照

**[对照]** 两套系统都自认「核心极小、扩展在外」，但对「插件边界要保卫什么」给出相反答案。dsh 保卫**可替换性**：任何座位都能换人，代价是坐上去的人全权限。LMDJ 保卫**信任与可复现**：每次执行都可追溯到确定性来源包哈希与双向策略交集，代价是换人必须重新链接、重新声明、重新分配 Build 号。

| 维度 | dsh | LMDJ |
| --- | --- | --- |
| 扩展单元 | 插件行 / bundle（YAML patch） | Provider（静态库 + 工厂函数 + 双重声明） |
| 装载时机 | 运行期动态解析包名，可热替换 | 链接期封闭；`assembly.json` 是编译目录之上的**白名单**，非发现机制 |
| 身份与溯源 | 包名 + 版本；会话格式无兼容承诺 | 确定性来源包哈希注入编译；模型身份不可伪造；每次 Attempt 落盘完整身份 |
| 信任边界 | **无插件隔离**；沙箱只围子进程 | 双向策略交集在调用**前**裁决；Provider 只见 Artifact 输入与输出 sink |
| 失败与回退 | 各接缝自定；普遍有默认实现 | **无默认、无静默回退**；失败进 Attempt 态，永不进 Project Truth |
| 扩展的对称性 | 插件可贡献 API、事件、UI、工具——一切表面 | **不对称**：Provider 只能扩展计算，永远不能扩展 Facade 操作面 |
| 契约机制 | Schemastery（配置）+ Zod/Typert（RPC）+ JSON Schema（工具），从 TS 类型生成 | 4 层独立版本化 JSON Schema；无代码生成，各语言重实现 + 4 处独立 fail-closed 执行点 |
| 事件系统 | 60 个事件、4 种分发模式、生成的生产者/消费者矩阵 | 规格 §12.4 已设计，**代码未实现** |
| 异步与作业 | Jobs/Workflow/Subagent 全套插件化 | Job §12.3 已设计未实现；`Provider::run` 同步阻塞，超时/重试声明了但不执行 |
| 文档纪律 | 6 份生成目录 + 新鲜度门禁 + 双语流水线 | 架构门户从活动清单生成、禁止手填；不可变快照绑定 Build |

值得注意的**互认**：dsh 在自己的封闭处（native 包无安装期构建兜底，探测不到就 fail-closed）与 LMDJ 同构；LMDJ 在自己的开放处（新增 Host 零核心改动）与 dsh 同构。两者共享同一条底层直觉——**组装结果必须可被机器完整核验**：dsh 用 `--dump-config` 复用同一解析器，LMDJ 用加载器对双编码组装做逐项互查。

## 10. 对 LMDJ 的启示与已落地部分

### 10.1 三项采纳

采纳理由与约束以 [dsh 派生加固目标](../plans/2026-08-19-lmdj-dsh-derived-hardening.md) 为准，此处只记研究侧依据：

1. **确定性 Attempt 重放。** LMDJ 的原料**优于** dsh 起点：终态 Attempt 记录已含 provider 身份（id、版本、来源包 sha256、模型身份）、能力身份、`parameters_sha256`、内容寻址的输入输出，且成功的 attempt 在磁盘上保留了 minted 字节。「录制」不是新机制，就是「跑一次真 Provider 并保留目录」。

2. **Event 层的两条纪律。** dsh 的事件总线能在约 60 事件、单点 13 监听者的规模下工作，正因为这两条从早期就在；事后补是昂贵的。LMDJ 正处在「成本是一段文字」的窗口。

3. **运行时不变量。** LMDJ 的一致性测试全在构建期，运行期只有加载边界的 fail-closed 校验。dsh 证明「每包一个 `./invariant` + 严格排除规则」在 200+ 包规模下可执行，且最高价值的检查是廉价的账实比对。

### 10.2 研究已产出的实际改动

本报告不只停在建议。基于它的采纳已落地在 `main`：

| 提交 | 内容 |
| --- | --- |
| `eff1eb6a` | 加固目标文档，含三条 track 与四条**反目标**（否决项） |
| `6388c4de` | 两份实施计划；Provider 字节访问缺口的第二消费方记入既有问题文件 |
| `7a11821e` | 四个运行时不变量测试：Attempt 账本（12 条关系）、Host settings（4 条）、快照发布计数（6 条）、并发守恒律（stress 层） |

研究过程中另外发现并已记录 5 项真实缺陷（机器任务清单 `G1`–`G5`），其中 3 项已由测试钉成可观察事实：孤立 attempt 预留**永久烧掉该 id**；孤立 settings 锁使**写入永久失败而读取照常成功**；`publish_queue_full` 在当前等容量下**可证明不可达**、其回滚分支是死代码。

### 10.3 不要照搬的部分

见 §1.2 的四条「建议否决」。补充一点研究侧观察：dsh 处处有默认实现，这适合「开箱即用的开发者工具」；LMDJ 的 `PROVIDER_NOT_FOUND`-而非-默认是规格 §24 深思后的否决项，与 Attempt 可审计性互为因果。同样，dsh 允许插件贡献一切表面，换来的是 UI 槽位目录、事件白名单、边界文档等一整套防漂移机器；LMDJ 用一条结构性禁令（Provider 只扩展计算）替代了这整套机器——在 Host 数量少、操作面收敛的现阶段，这是更便宜的正确。

## 11. 方法与可复核性

两次并行全库源码探查：dsh 侧覆盖 `vendor/`、`packages/` 213 包清单、`docs/` 全部架构页与 4 篇 postmortem、`apps/cli` 启动链、`packages/preset/agent-presets`、`packages/typert/*`、`native/landlock-run`；LMDJ 侧覆盖 `packages/provider-sdk`、`packages/application-facade`、assembly 加载链、`contracts/` 与 conformance suite、`packages/audio-runtime` 发布路径。

所有接口摘录与行为描述出自源码而非文档转述；§7 的每一行都是对 §3–§4 所述宣称的独立核查。两侧基线 SHA 见文档头，可按 SHA 复核。
