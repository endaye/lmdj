# LMDJ Current Runtime Architecture Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the retired Patch/Worker-era “current product architecture” with a repository-evidenced Archify diagram and technical guide for the implemented Headless Core runtime.

**Architecture:** Keep one left-to-right application/control spine from current Hosts through the Web Runtime Platform/Application Facade to Project Truth, cooking, the immutable Runtime Snapshot, and Audio Runtime. Show the implemented Web Runtime Platform -> Audio Runtime realtime-trigger path and Audio Runtime -> Web Runtime Platform ordered-Voice-state return explicitly, keep Project I/O and Provider Attempts as short branches, and express Product Assembly, Foundation, Contracts, and forbidden paths in concise conclusion cards.

**Tech Stack:** Archify 2.15 architecture renderer and showcase validator, typed JSON, self-contained HTML/SVG, Markdown, `rg`, Git, and the existing Architecture Portal Node/Docusaurus checks.

## Global Constraints

- Work only in the existing isolated worktree on `docs/runtime-architecture-archify`; never edit or commit on `main`.
- Treat `products/lmdj/assembly.json`, `assembly.lock.json`, active manifests, current implementation, and Architecture Portal current pages as evidence; never use historical plans or `references/demos/` as current truth.
- Do not hand-enter Product Build, Module, Host, Provider, Contract, Channel, or revision versions into the diagram.
- Do not present, restore, wrap, translate, or emit `lmdj.patch.v1` or `lmdj.materials.v1` as active Contracts; current documentation may name them only to state explicitly that they are retired and outside the runtime.
- Show only implemented and currently assembled runtime components. Production Provider, cloud infrastructure, release state, deployment state, and physical-device acceptance remain outside the diagram.
- The Application Facade is every Host's only application/control-plane entry. The acceptance-only Native Test Host also uses the Audio Runtime adapter/realtime path for realtime audio, device, and capture verification; no Host parses Project bundles.
- Web Runtime Platform uses Facade for Project/Sample application operations. It sends realtime triggers directly to Audio Runtime; Audio Runtime publishes ordered Voice state to its ring, the Platform drains it and publishes `runtime.voice_state`, and Runtime Session observes it. Neither per-event direction traverses Facade/Domain/Cooker or changes Project Truth.
- Project Truth is authoritative; Runtime Snapshot is immutable derived state and never writes back.
- Provider selection and failure belong to Workspace/Attempt state, never Project Truth.
- Provider code receives Artifact input and an Artifact output sink, not a mutable Project or bundle path.
- Product-specific wiring remains in Product Assembly; Assembly is not a workflow node.
- Use Archify `architecture` mode with `meta.quality_profile: "showcase"`, the default static viewer, default classic visual preset, and no invented subtitle.
- Validate after every candidate edit. Final acceptance requires 9/9 showcase checks, zero errors, zero warnings, deterministic delivery, and human inspection of both light and dark screenshots.
- After two consecutive geometry repair rounds that do not reduce the best objective error count, stop and report the diagnostics instead of weakening labels or claiming success.
- Stage only the declared Task files. A local commit does not authorize push, Pull Request creation, merge, deploy, release, or publication.

## File Structure

| Path | Action | Responsibility |
| --- | --- | --- |
| `docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json` | Create | Reviewable Archify topology, evidence pointers, layout, relationships, and conclusion cards |
| `docs/architecture/assets/lmdj-current-runtime-architecture.html` | Create | Self-contained delivered viewer with theme and export controls |
| `docs/architecture/current-product-architecture.md` | Rewrite | Searchable technical explanation, component inventory, authority rules, and regeneration commands |
| `docs/architecture/assets/lmdj-current-product-architecture.mmd` | Delete | Retired Mermaid source for the removed Patch/Worker architecture |
| `docs/architecture/assets/lmdj-current-product-architecture.svg` | Delete | Retired generated image |
| `docs/architecture/assets/mermaid-config.json` | Delete after reference audit | Configuration used only by the retired Mermaid asset |

The JSON and generated HTML change together. The Markdown consumes the HTML by relative link and restates only stable responsibilities. The three retired assets are deleted in the same Task so the repository has one unambiguous “current architecture.”

## Version Management

Version impact: none.

Reason: this Task changes only documentation and visualization assets. It does not alter Product, Module, Host, Provider, Contract, Model, Assembly, runtime behavior, packaging, or release identity, and it does not allocate a Product Build.

## Documentation Impact

Architecture Portal impact: none.

Reason: the Portal current pages and Portal-owned diagrams already describe the implemented Headless Core correctly. This Task repairs the separate stale document under `docs/architecture/`; it changes no implementation fact, Assembly input, Portal route, manifest-derived identity, or immutable snapshot. `scripts/architecture-portal.sh check` remains a blocking verification gate.

---

### Task 1: Replace the stale current architecture as one atomic documentation change

**Files:**

- Create: `docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json`
- Create: `docs/architecture/assets/lmdj-current-runtime-architecture.html`
- Modify: `docs/architecture/current-product-architecture.md`
- Delete: `docs/architecture/assets/lmdj-current-product-architecture.mmd`
- Delete: `docs/architecture/assets/lmdj-current-product-architecture.svg`
- Delete: `docs/architecture/assets/mermaid-config.json`

**Interfaces:**

- Consumes: approved design `docs/design/2026-08-22-lmdj-current-runtime-architecture-design.md`, Product Assembly/Lock, active Module/Host/Provider manifests, current Core/Web Runtime sources, and Portal current diagrams/pages.
- Produces: Archify architecture specification schema version 1, self-contained HTML viewer, and current runtime guide with no runtime/API changes.

- [ ] **Step 1: Confirm the isolated, clean starting point**

Run:

```bash
test "$(git branch --show-current)" = "docs/runtime-architecture-archify"
test -z "$(git status --porcelain)"
git merge-base --is-ancestor origin/main HEAD
git log -2 --oneline
```

Expected: all three assertions exit 0; the log contains the committed design and implementation plan only, on top of the latest task base. If the worktree is dirty or `origin/main` is not an ancestor, stop and reconcile before editing.

- [ ] **Step 2: Capture the failing current-document evidence**

Run:

```bash
rg -n "lmdj\.patch\.v1|apps/api|apps/web|workers/audio|packages/patchify" \
  docs/architecture/current-product-architecture.md

test ! -e docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json
test ! -e docs/architecture/assets/lmdj-current-runtime-architecture.html
```

Expected: `rg` prints the obsolete Patch/Worker-era statements; both absence assertions exit 0. This is the red-state proof that the named “current” document is stale and the replacement artifact does not yet exist.

- [ ] **Step 3: Reconfirm live composition and asset ownership**

Run:

```bash
jq '{modules: [.modules[].id], hosts: [.hosts[].id], providers: [.providers[].id], contracts: [.contracts[].id]}' \
  products/lmdj/assembly.json

for manifest in packages/*/module.json apps/*/module.json providers/*/module.json; do
  jq -c '{module, version, dependencies}' "$manifest"
done

rg -n "lmdj-current-product-architecture\.(mmd|svg)|mermaid-config\.json" \
  --glob '!docs/design/2026-08-22-lmdj-current-runtime-architecture-design.md' \
  --glob '!docs/plans/2026-08-22-lmdj-current-runtime-architecture.md' .
```

Expected: Assembly lists the eight current modules, five current Hosts, two local Proof Providers, and active Contracts. Asset references appear only in the stale current document and the immutable historical 2026-07-14 implementation plan; no build script or other current document consumes them. Historical plan references are evidence and must not be rewritten.

- [ ] **Step 4: Load the Archify authoring contract and verify the renderer**

Read completely, in order:

```bash
: "${ARCHIFY_ROOT:?set ARCHIFY_ROOT to the Archify skill directory}"

sed -n '1,240p' "$ARCHIFY_ROOT/SKILL.md"
sed -n '1,260p' "$ARCHIFY_ROOT/schemas/architecture.schema.json"
sed -n '1,240p' "$ARCHIFY_ROOT/schemas/common.schema.json"
sed -n '1,260p' "$ARCHIFY_ROOT/examples/web-app.architecture.json"
sed -n '1,240p' "$ARCHIFY_ROOT/references/authoring-contract.md"
sed -n '1,180p' "$ARCHIFY_ROOT/references/delivery-contract.md"
```

Then run:

```bash
node "$ARCHIFY_ROOT/bin/archify.mjs" doctor
```

Expected: exit 0 with `Archify is ready.` and an `[ok]` entry for the architecture renderer, schema, example, visual-check runtime, and standalone validators.

- [ ] **Step 5: Write the first Archify candidate from repository evidence**

Create `docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json` with exactly this first candidate. Do not add manual `via`, `labelAt`, `labelDx`, or `labelDy` controls before validation reports a concrete subject and supported fix.

```json
{
  "schema_version": 1,
  "diagram_type": "architecture",
  "meta": {
    "title": "LMDJ 当前端到端运行时架构",
    "output": "lmdj-current-runtime-architecture.html",
    "quality_profile": "showcase",
    "legend": {
      "mode": "auto",
      "entries": {
        "frontend": {"label": "Host"},
        "backend": {"label": "Core Module"},
        "database": {"label": "权威或派生状态"},
        "external": {"label": "Provider"}
      }
    },
    "viewBox": [2000, 1000]
  },
  "layout": {
    "mode": "grid",
    "origin": [40, 120],
    "cols": 7,
    "gapX": 90,
    "gapY": 90,
    "cellW": 190,
    "cellH": 72
  },
  "components": [
    {
      "id": "web-hosts",
      "type": "frontend",
      "label": "Web Hosts",
      "sublabel": "Creator Web · Formal Web Host",
      "pos": [40, 120],
      "size": [190, 72],
      "sources": [
        {"path": "apps/creator-web/module.json", "label": "Creator Host"},
        {"path": "apps/web-runtime-host/module.json", "label": "Formal Web Host"}
      ]
    },
    {
      "id": "cli-mcp-hosts",
      "type": "frontend",
      "label": "CLI / MCP Hosts",
      "sublabel": "终端 · stdio MCP",
      "pos": [40, 360],
      "size": [190, 72],
      "sources": [
        {"path": "apps/core-cli/module.json", "label": "CLI Host"},
        {"path": "apps/core-mcp/module.json", "label": "MCP Host"}
      ]
    },
    {
      "id": "native-test-host",
      "type": "frontend",
      "label": "Native Test Host",
      "sublabel": "验收 · 设备 · 采集",
      "pos": [1720, 360],
      "size": [190, 72],
      "sources": [
        {"path": "apps/native-test-host/module.json", "label": "Host dependencies"},
        {"path": "apps/native-test-host/src/main.cpp", "label": "Realtime acceptance"}
      ]
    },
    {
      "id": "web-runtime-platform",
      "type": "backend",
      "label": "Web Runtime Platform",
      "sublabel": "Manifest Gate · Session",
      "row": 0,
      "col": 1,
      "sources": [
        {"path": "packages/web-runtime-platform/module.json", "label": "Module manifest"},
        {"path": "packages/web-runtime-platform/web/runtime_session.mjs", "label": "Runtime Session"},
        {"path": "packages/web-runtime-platform/src/control_runtime.cpp", "label": "Control Runtime"}
      ]
    },
    {
      "id": "application-facade",
      "type": "backend",
      "label": "Application Facade",
      "sublabel": "应用 / 控制面入口",
      "row": 0,
      "col": 2,
      "sources": [
        {"path": "packages/application-facade/module.json", "label": "Module manifest"},
        {"path": "packages/application-facade/src/application.cpp", "label": "Application boundary"},
        {"path": "packages/application-facade/src/c_api.cpp", "label": "C ABI"}
      ]
    },
    {
      "id": "project-truth",
      "type": "database",
      "label": "Authoring Domain",
      "sublabel": "Project Truth · revision",
      "row": 0,
      "col": 3,
      "sources": [
        {"path": "packages/authoring-domain/module.json", "label": "Module manifest"},
        {"path": "packages/authoring-domain/src/project.cpp", "label": "Project Truth"},
        {"path": "packages/authoring-domain/src/command_handler.cpp", "label": "Commands"}
      ]
    },
    {
      "id": "project-cooker",
      "type": "backend",
      "label": "Project Cooker",
      "sublabel": "校验 · 派生",
      "row": 0,
      "col": 4,
      "sources": [
        {"path": "packages/project-cooker/module.json", "label": "Module manifest"},
        {"path": "packages/project-cooker/src/project_cooker.cpp", "label": "Cook path"}
      ]
    },
    {
      "id": "runtime-snapshot",
      "type": "database",
      "label": "Runtime Snapshot",
      "sublabel": "不可变派生状态",
      "row": 0,
      "col": 5,
      "sources": [
        {"path": "packages/project-cooker/src/project_cooker.cpp", "label": "Snapshot producer"},
        {"path": "apps/architecture-portal/docs/contracts/runtime-snapshot.mdx", "label": "Current contract"}
      ]
    },
    {
      "id": "audio-runtime",
      "type": "backend",
      "label": "Audio Runtime",
      "sublabel": "Prepared samples · Voice",
      "row": 0,
      "col": 6,
      "sources": [
        {"path": "packages/audio-runtime/module.json", "label": "Module manifest"},
        {"path": "packages/audio-runtime/src/realtime_engine.cpp", "label": "Realtime engine"},
        {"path": "packages/audio-runtime/src/offline_renderer.cpp", "label": "Offline renderer"}
      ]
    },
    {
      "id": "provider-sdk",
      "type": "backend",
      "label": "Provider SDK",
      "sublabel": "Capability · Attempt store",
      "row": 2,
      "col": 2,
      "sources": [
        {"path": "packages/provider-sdk/module.json", "label": "Module manifest"},
        {"path": "packages/provider-sdk/src/registry.cpp", "label": "Registry"},
        {"path": "packages/provider-sdk/src/attempt_store.cpp", "label": "Attempt Store"}
      ]
    },
    {
      "id": "project-io",
      "type": "database",
      "label": "Project I/O",
      "sublabel": "Store · Bundle · Cache",
      "row": 2,
      "col": 3,
      "sources": [
        {"path": "packages/project-io/module.json", "label": "Module manifest"},
        {"path": "packages/project-io/src/project_store.cpp", "label": "Atomic store"},
        {"path": "packages/project-io/src/project_bundle_transfer.cpp", "label": "Bundle transfer"}
      ]
    },
    {
      "id": "proof-providers",
      "type": "external",
      "label": "Proof Providers",
      "sublabel": "Local success / failure",
      "row": 4,
      "col": 2,
      "sources": [
        {"path": "providers/local-proof-success/module.json", "label": "Success Provider"},
        {"path": "providers/local-proof-failure/module.json", "label": "Failure Provider"}
      ]
    }
  ],
  "boundaries": [
    {
      "kind": "region",
      "label": "产品中立 Headless Core",
      "wraps": [
        "web-runtime-platform",
        "application-facade",
        "project-truth",
        "project-cooker",
        "runtime-snapshot",
        "audio-runtime",
        "provider-sdk",
        "project-io"
      ],
      "pad": 30
    }
  ],
  "connections": [
    {"id": "web-host-entry", "from": "web-hosts", "to": "web-runtime-platform", "variant": "emphasis"},
    {"id": "web-facade-api", "from": "web-runtime-platform", "to": "application-facade", "label": "Facade API", "variant": "emphasis"},
    {"id": "web-realtime-trigger", "from": "web-runtime-platform", "to": "audio-runtime", "label": "实时触发", "variant": "emphasis"},
    {"id": "audio-ordered-voice", "from": "audio-runtime", "to": "web-runtime-platform", "label": "ordered Voice state", "variant": "dashed"},
    {"id": "cli-mcp-facade-api", "from": "cli-mcp-hosts", "to": "application-facade", "label": "Facade API", "variant": "emphasis"},
    {"id": "native-test-control", "from": "native-test-host", "to": "application-facade", "label": "控制面", "variant": "dashed"},
    {"id": "native-test-realtime", "from": "native-test-host", "to": "audio-runtime", "label": "实时验收", "variant": "emphasis"},
    {"id": "facade-commands", "from": "application-facade", "to": "project-truth", "label": "命令", "variant": "emphasis"},
    {"id": "project-cook", "from": "project-truth", "to": "project-cooker", "label": "校验 / 派生", "variant": "emphasis"},
    {"id": "cooked-snapshot", "from": "project-cooker", "to": "runtime-snapshot", "label": "不可变快照", "variant": "emphasis"},
    {"id": "snapshot-audio", "from": "runtime-snapshot", "to": "audio-runtime", "label": "只读", "variant": "emphasis"},
    {"id": "project-persist", "from": "project-truth", "to": "project-io", "label": "原子持久化"},
    {"id": "facade-provider-sdk", "from": "application-facade", "to": "provider-sdk", "label": "Capability", "variant": "dashed"},
    {"id": "provider-artifacts", "from": "provider-sdk", "to": "proof-providers", "label": "Artifact I/O", "variant": "dashed"}
  ],
  "cards": [
    {
      "dot": "emerald",
      "title": "权威状态",
      "items": [
        "Authoring Domain 独占 Project Truth",
        "Runtime Snapshot 可丢弃、可重建、只读消费"
      ]
    },
    {
      "dot": "cyan",
      "title": "装配与契约",
      "items": [
        "Product Assembly 锁定 Module、Host、Provider 与 Contract",
        "Foundation 提供 Artifact、JSON 与 typed error 底座"
      ]
    },
    {
      "dot": "rose",
      "title": "禁止路径",
      "items": [
        "Host 不解析 Project Bundle；Provider 不接收 mutable Project",
        "Provider failure 与 Runtime state 不写入 Project Truth"
      ]
    }
  ]
}
```

- [ ] **Step 6: Validate the first candidate at showcase quality**

Run:

```bash
node "$ARCHIFY_ROOT/bin/archify.mjs" validate architecture \
  docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json \
  --quality showcase \
  --repo-root . \
  --json
```

Expected: exit 0; receipt reports the exact `showcase` profile, all 9 artifact checks, 0 composition errors, and 0 warnings.

If it fails, edit only the diagnostic `subject`, using one listed `supportedFixes` control. Preserve every semantic label unless both endpoints fully imply it; do not delete a protocol, action, direction, synchronization, or cross-boundary label to make geometry pass. Rerun this exact command after each single correction. Stop after two consecutive corrections fail to improve the best objective error count.

- [ ] **Step 7: Atomically deliver the self-contained HTML**

Run once after the JSON has a passing validation receipt:

```bash
node "$ARCHIFY_ROOT/bin/archify.mjs" deliver architecture \
  docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json \
  docs/architecture/assets/lmdj-current-runtime-architecture.html \
  --quality showcase \
  --repo-root . \
  --json
```

Expected: exit 0; receipt reports specification and artifact byte counts/SHA-256 values, 9/9 showcase checks, 0 errors, and 0 warnings. Record the receipt values for final handoff. Do not edit the JSON after this receipt without rerunning validate and deliver.

- [ ] **Step 8: Collect and inspect bounded visual evidence without polluting the worktree**

Run:

```bash
visual_evidence_dir=$(mktemp -d /tmp/lmdj-runtime-architecture-visual.XXXXXX)
cp docs/architecture/assets/lmdj-current-runtime-architecture.html "$visual_evidence_dir/lmdj-current-runtime-architecture.html"
shasum -a 256 \
  docs/architecture/assets/lmdj-current-runtime-architecture.html \
  "$visual_evidence_dir/lmdj-current-runtime-architecture.html"

node "$ARCHIFY_ROOT/bin/archify.mjs" visual-check \
  "$visual_evidence_dir/lmdj-current-runtime-architecture.html" \
  --json
```

Expected: both SHA-256 lines match; visual-check exits 0, reports containment at 1440×900, 1600×1000, 1920×1080, and 2048×1320, and writes light/dark screenshots plus a contact sheet under the temporary directory.

Open the returned contact sheet and inspect every source capture with an image viewer. Require:

- no horizontal or vertical overflow at any desktop viewport;
- readable node and relationship labels in light and dark themes;
- no edge crossing an unrelated node, ambiguous corridor, clipped boundary, or masked route;
- a balanced first-screen composition at 2048×1320 without a conspicuous empty lower band;
- legible cards and legend, with the green runtime spine visually dominant.

If a visible defect exists, apply one focused JSON correction, rerun Steps 6–8, and increment `correction_rounds`. Perform at most two focused visual correction rounds. A visual-check exit 2 is `skipped`, not success, and blocks this Task because the approved acceptance requires visual inspection.

- [ ] **Step 9: Rewrite the searchable current runtime guide**

Replace all content in `docs/architecture/current-product-architecture.md` with:

````markdown
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

Core CLI 与 Core MCP 只通过 Application Facade 进入应用/控制面。Native Test Host 是验收专用
Host：它通过 Facade 执行应用/控制面操作，同时直接连接 Audio Runtime 的 adapter/realtime 路径，
用于实时音频、设备与采集验证；它不是产品 UI，也不解析 Project Bundle。Project I/O 与
Provider SDK/Proof Providers 是从其最近主路径节点延伸的支路，不是第二套 Project 或 Runtime。

Web Runtime Platform 向 Audio Runtime 发送实时触发；Audio Runtime 把 ordered Voice state 发布到
ring，Platform drain 后发布 `runtime.voice_state`，Runtime Session 观察。两个逐事件方向都不经过
Facade/Domain/Cooker，也不改变 Project Truth；Project/Sample mutation 仍必须进入 Facade。

Product Assembly 负责锁定 Module、Host、Provider、Contract 和 policy 的组合身份。它是声明式
装配边界，不执行用户工作流，也不动态增加 Facade operation。

## 当前组件职责

| 边界 | 组件 | 当前职责 | 源码位置 |
| --- | --- | --- | --- |
| Host | Creator Web / Formal Web Runtime Host | UI、Host identity、浏览器生命周期和协议适配 | `apps/creator-web/`、`apps/web-runtime-host/` |
| Host | Core CLI / Core MCP | 只通过 Facade 提供终端与 stdio MCP 应用/控制面入口 | `apps/core-cli/`、`apps/core-mcp/` |
| Acceptance Host | Native Test Host | 通过 Facade 执行应用/控制面操作，并直接使用 Audio Runtime adapter/realtime 路径验证实时音频、设备与采集；不是产品 UI | `apps/native-test-host/` |
| Core Module | Web Runtime Platform | Manifest Gate、Runtime Session、输入适配、Control Runtime、向 Audio Runtime 发送实时触发并接收 ordered Voice state，以及浏览器资源生命周期 | `packages/web-runtime-platform/` |
| Core Module | Application Facade | Host 唯一应用/控制面入口、应用编排、稳定结果与错误语义 | `packages/application-facade/` |
| Core Module | Authoring Domain | Project Truth、命令规则、revision 与 Pad/Pattern/Sample 语义 | `packages/authoring-domain/` |
| Core Module | Project I/O | 原子 Project store、Take recovery、portable Bundle transfer 与 Workspace cache | `packages/project-io/` |
| Core Module | Project Cooker | 校验 Project 与 Artifact，派生 Runtime Snapshot | `packages/project-cooker/` |
| Derived state | Runtime Snapshot | 不可变、可丢弃、可重建的 Audio Runtime 输入 | `packages/project-cooker/`、`apps/architecture-portal/docs/contracts/runtime-snapshot.mdx` |
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

Facade 是控制面和应用用例边界，不是实时逐事件数据面的替代品。Web Runtime Platform 向
Audio Runtime 发送实时触发；Audio Runtime 反向发布 ordered Voice state，Platform drain 后以
`runtime.voice_state` 交给 Runtime Session 观察。这两个逐事件方向都不经过 Facade、Domain 或
Cooker，也不授权 Platform 执行 Project/Sample mutation、revision 或 Candidate commit，更不改变
Project Truth。Native Test Host 的直接 Audio Runtime 依赖只服务验收环境中的 adapter/realtime、
设备与采集生命周期，不扩展为产品业务入口。

## Provider 边界

Application Facade 通过 Provider SDK 选择并运行 Capability。Provider 只接收不可变 Artifact
input 与 Artifact output sink，返回 Candidate/Attempt 结果；它不接收 mutable Project，也不接收
Project bundle path。Provider failure 只能更新 Attempt/Workspace State，不能修改 Project Truth。

当前 Assembly 只装配本地成功与失败 Proof Provider。生产模型、云 Gateway、鉴权、计费、数据
保留政策和区域控制尚未由这张图声明为已实现。

## 禁止路径

- Host 不解析 Project Bundle，也不直接依赖 Domain、Project I/O 或 Provider implementation。
- Web Runtime Platform -> Audio Runtime 只承载实时触发；Audio Runtime -> Web Runtime Platform
  只返回 ordered Voice state。两个方向都不逐次经过 Facade/Domain/Cooker，也不改变 Project Truth。
- Native Test Host 的直接依赖仅限 Audio Runtime 验收路径；它仍通过 Facade 进入应用/控制面。
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
node "$ARCHIFY_ROOT/bin/archify.mjs" validate architecture \
  docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json \
  --quality showcase --repo-root . --json

node "$ARCHIFY_ROOT/bin/archify.mjs" deliver architecture \
  docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json \
  docs/architecture/assets/lmdj-current-runtime-architecture.html \
  --quality showcase --repo-root . --json

node "$ARCHIFY_ROOT/bin/archify.mjs" visual-check \
  docs/architecture/assets/lmdj-current-runtime-architecture.html --json

scripts/architecture-portal.sh check
```

不得手改生成的 HTML。任何组件、依赖或权威性边界变化，都先修改 JSON 图源和本文，再重新运行
Archify showcase validation、deterministic delivery、视觉检查及 Portal check。
````

- [ ] **Step 10: Remove the retired Mermaid assets after the completed reference audit**

Run:

```bash
git rm \
  docs/architecture/assets/lmdj-current-product-architecture.mmd \
  docs/architecture/assets/lmdj-current-product-architecture.svg \
  docs/architecture/assets/mermaid-config.json
```

Expected: exactly those three tracked files are marked deleted. Do not modify the historical 2026-07-14 plan that records their former paths.

- [ ] **Step 11: Run content, Archify, and repository acceptance gates**

Run the forbidden-current-path scan:

```bash
if rg -n "apps/api/|apps/web/|workers/audio/|packages/patchify/|8-Pad Patch|Song Pipeline" \
  docs/architecture/current-product-architecture.md \
  docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json; then
  exit 1
fi

rg -n "已退役，不属于当前链路" docs/architecture/current-product-architecture.md
```

Expected: the active-path scan emits no output and exits 0; the retired-contract boundary sentence matches exactly once. Current documentation may name the retired Contracts only to exclude them explicitly.

Re-run deterministic diagram checks without changing the frozen candidate:

```bash
node "$ARCHIFY_ROOT/bin/archify.mjs" validate architecture \
  docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json \
  --quality showcase --repo-root . --json

node "$ARCHIFY_ROOT/bin/archify.mjs" check \
  docs/architecture/assets/lmdj-current-runtime-architecture.html

scripts/architecture-portal.sh check
git diff --check
```

Expected: Archify reports 9/9 showcase checks, 0 errors, and 0 warnings; HTML check exits 0; Portal reports 50 passing tests, valid docs/diagrams, a successful production build, and valid routes/internal links; Git diff check emits no output.

- [ ] **Step 12: Inspect and commit the exact documentation boundary**

Run:

```bash
git status --short
git diff --name-status
git diff -- \
  docs/architecture/current-product-architecture.md \
  docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json \
  docs/architecture/assets/lmdj-current-runtime-architecture.html \
  docs/architecture/assets/lmdj-current-product-architecture.mmd \
  docs/architecture/assets/lmdj-current-product-architecture.svg \
  docs/architecture/assets/mermaid-config.json

git add \
  docs/architecture/current-product-architecture.md \
  docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json \
  docs/architecture/assets/lmdj-current-runtime-architecture.html \
  docs/architecture/assets/lmdj-current-product-architecture.mmd \
  docs/architecture/assets/lmdj-current-product-architecture.svg \
  docs/architecture/assets/mermaid-config.json

git diff --cached --name-status
git diff --cached --check
git diff --cached
```

Expected staged boundary:

```text
M  docs/architecture/current-product-architecture.md
A  docs/architecture/assets/lmdj-current-runtime-architecture.architecture.json
A  docs/architecture/assets/lmdj-current-runtime-architecture.html
D  docs/architecture/assets/lmdj-current-product-architecture.mmd
D  docs/architecture/assets/lmdj-current-product-architecture.svg
D  docs/architecture/assets/mermaid-config.json
```

Commit:

```bash
git commit -m "docs(architecture): replace stale runtime map"
```

Expected: one non-empty Conventional Commit containing exactly the six declared documentation paths.

- [ ] **Step 13: Verify the committed file list and final worktree state**

Run:

```bash
git show --name-status --format='%H%n%s' HEAD
git status --short --branch
```

Expected: committed file list matches Step 12 exactly; worktree is clean; branch is ahead of `origin/main` by the local design, plan, and implementation commits only. Report the absolute HTML/JSON/Markdown paths, specification/artifact SHA-256 receipt, `validation: 9/9 showcase, 0 errors, 0 warnings`, truthful `visual_review`, and `correction_rounds`. Stop without push, PR, merge, deploy, release, or publication.
