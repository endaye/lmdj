# Current Product Architecture Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前 LMDJ 产品/业务架构整理成紧凑、可维护的 SVG，并在 `docs/architecture/` 提供配套说明与文档索引。

**Architecture:** 使用 Mermaid 源文件维护图的节点和关系，采用三层紧凑布局：用户旅程、当前处理链路、产品契约与规划能力。渲染后的 SVG 使用深色高对比配色，并将所有连线批注固定为深蓝底浅色字。

**Tech Stack:** Mermaid、SVG、Markdown、Chrome headless、PowerShell XML 校验。

## Global Constraints

- 保持当前业务关系正确，不把规划中的 Generation Worker、Render Worker、Cloud 标成已落地。
- `references/demos/lmdj-song-pipeline/` 必须明确标为参考实现，不属于正式产品源码边界。
- `lmdj.patch.v1` 继续作为 Web、API、Worker、Patchify 之间的统一契约中枢。
- 图中实线表示已落地链路，虚线表示规划能力，点线表示契约或约束关系。
- 所有连线批注必须具有不透明深色背景和高对比浅色文字。

---

### Task 1: 生成紧凑版架构图

**Files:**
- Create: `docs/architecture/assets/lmdj-current-product-architecture.mmd`
- Create: `docs/architecture/assets/lmdj-current-product-architecture.svg`

**Interfaces:**
- Consumes: 当前已确认的 LMDJ 产品业务链路与 `lmdj.patch.v1` 契约关系。
- Produces: 可维护 Mermaid 源文件和可直接嵌入 Markdown 的 SVG。

- [x] **Step 1: 编写三层 Mermaid 源文件**

  使用紧凑节点间距，分为用户旅程、当前处理链路、产品核心与规划能力，避免回到用户节点的大型回环。

- [x] **Step 2: 渲染 SVG**

  Run: `npx -y @mermaid-js/mermaid-cli -i docs/architecture/assets/lmdj-current-product-architecture.mmd -o docs/architecture/assets/lmdj-current-product-architecture.svg -b '#181818'`

  Expected: 命令退出码为 0，输出 SVG 存在。

- [x] **Step 3: 验证 SVG**

  使用 PowerShell XML 解析验证 SVG 结构，并用 Chrome headless 渲染 PNG 预览。预期宽度明显小于原图的 `3771.55`，所有连线批注可读。

### Task 2: 编写架构说明并加入索引

**Files:**
- Create: `docs/architecture/current-product-architecture.md`
- Modify: `docs/README.md`

**Interfaces:**
- Consumes: Task 1 的 SVG 和 Mermaid 源文件。
- Produces: 面向产品/业务理解的长期架构入口。

- [x] **Step 1: 编写架构说明**

  文档包括状态图例、当前闭环、组件职责、契约中枢、参考 Demo 边界、规划能力和仓库目录映射。

- [x] **Step 2: 更新 docs 索引**

  在 `docs/README.md` 的核心文档区域增加当前产品架构入口。

- [x] **Step 3: 验证文档链接与差异**

  Run: `git diff --check`

  Expected: 无空白错误；Markdown 中的 SVG 和仓库目录链接均存在；`git status` 只包含本计划涉及的文档文件。
