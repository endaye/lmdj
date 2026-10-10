# LMDJ 架构门户与文档影响规范

日期：2026-08-04

状态：已生效；本次 CI/合并流程调整在获明确授权的 O2 切换时生效，未合入草案不替代当前 main 规则。
适用范围：产品、Core Module、Host、Provider、Contract、Product Assembly、平台适配、测试/发布流程与门户本身。

## 1. 目的与 Source of Truth

`apps/docs-site/` 是 LMDJ 内部产品说明书的唯一发布源码。网站公开可读，但主要服务内部产品、工程、质量和发布协作。Product Build、Git revision、Module/Host/Provider/Contract 版本与 Assembly Lock hash 必须从 active manifests 生成，不得手填或猜测。

旧的独立 HTML、截图和 `demos/` 可以作为历史证据，但不是 current 产品说明书，也不是正常发布输入。

## 2. 强制文档影响声明

每个实施计划必须包含 `## Documentation Impact`，每个 Pull Request 必须填写以下二选一格式。

需要更新：

```text
Documentation impact: required
Affected portal pages: /core/modules/audio-runtime/ /platform/native-audio/
Reason: realtime trigger lifecycle changed
```

无需更新：

```text
Documentation impact: none
Reason: test fixture refactor does not change product behavior, public boundaries, versions, evidence, or operations
```

`Reason` 不得为空。`required` 必须列出绝对门户路由，并在同一个 Task/PR 修改对应 current 页面；`none` 不得制造无意义的门户改动或空提交。
唯一例外是纯候选 cut：changed files 只含 Product 身份再生成文件（`products/lmdj/version.json`、
`assembly(.lock).json`、`src/compiled_assembly.cpp`、`generated/web-runtime-identity.*`）、
`versions.json` 与 PR head 的 `version.json` 所指 Product Build 自身的不可变快照，且含该 Build
的快照元数据；任何其他 Build 的快照路径都不属于这次 cut。current 页面的身份
全部从 manifest 派生，此时没有可改的 current 页面，快照本身即满足 `required`。

## 3. 必须评估的变化

以下变化默认需要检查并通常更新门户：

- `packages/` 的公开 API、状态、错误、并发、生命周期、依赖或测试证据；
- `apps/` Host 的协议、输入输出、平台生命周期或 Assembly 成员身份；
- `providers/` 的 Capability、端口、Attempt、模型/实现身份或数据政策；
- `contracts/` 的 schema、兼容性或 active/retired 状态；
- `products/lmdj/` 的 Product Build、Assembly、Lock、Provider policy 或 wiring；
- 原生/Web 音频、存储、输入和设备验收；
- 测试层级、Proof、CI、版本、发布、部署和回滚流程；
- 已批准产品定位、能力地图、工作流或状态发生变化。

只有完全内部、不会改变上述事实且理由具体的变化才可声明 `none`。
Product Build、Assembly 或 Assembly Lock 发生变化时禁止声明 `none`，必须同步
current 页面和受影响的源图。

## 4. 页面与图的责任

页面 front matter 必须声明 `area`、`status`、`owners` 和可解析的 `source_paths`。状态只能为 `implemented`、`partial`、`designed`、`planned`、`retired`。自动化证据、CI、Product Build、部署和物理设备验收必须分别陈述。

Assembly Lock 中每个 Module、Host、Provider 和 Contract 必须恰好映射到 current 页面。每个 Core Module 必须有确定性 `.architecture.json` 源图及生成的 HTML/SVG；改变边界时同 Task 更新源图和页面，禁止手改生成图。

## 5. 稳定命令与 Task 所有权

```bash
scripts/docs-site.sh install
scripts/docs-site.sh dev
scripts/docs-site.sh check
scripts/docs-site.sh version PRODUCT_BUILD CHANNEL
scripts/docs-site.sh resume-version PRODUCT_BUILD CHANNEL SOURCE_REVISION
scripts/docs-site.sh smoke BASE_URL
```

实现 Task 的负责人同时负责相关 current 页面和源图。影响页面、源图、门户工具、投影身份或已记载源码事实的 Task，在提交前运行 `scripts/docs-site.sh check`，覆盖单测、元数据、current truth、确定性图、类型、生产构建、路由、身份和站内链接。无关 Task 不强制运行门户重构建，也不把它搬成所有 PR 的 pre-push 门禁；全量增量批次与显式完整候选／节点自测仍保留该 suite。

新 identity-only allocation cut 的 S0 本地 source checkpoint 采用
[canonical S0/S1 顺序](git-workflow.md#product-cut-source-and-snapshot-phases)。它仍实际运行
完整 `scripts/docs-site.sh check`，并另行取得整个 `check:current` 与全部 owning
source/version/conformance checks 的 PASS。完整 check 可能在 `check:release-docs`
提前停止，不能把这个执行前缀当成 type/build/routes 全通过。

只有新 Build 的 `versions.json` 条目、snapshot source 与 metadata 三项均不存在，
且完整 check 的错误集合恰为以下三条，才能把该非零结果保留为同 PR 未完成的生成
前置；任何该 Build 的既有/部分 snapshot 字节都不能借此被忽略。下文 `B` 指实际
已声明的新 Build，不是本治理文档分配的版本：

```text
Product Build B is missing from versions.json
Product Build B snapshot source is missing
Product Build B metadata is missing
```

其他 identity/hash、unit、current docs、diagram、changelog、type、production build、
route、既有 snapshot 或 provenance 错误全部停止 S0。该非零结果不记录为 PASS，
不授予 standalone push/PR/merge、分发或完成资格。S1 正式冻结和提交前必须通过原
完整 check，整个 cut 仍完成版本事实、snapshot/provenance、适用 Task 与 batch-only
验证、独立 current-head review、冲突、findings/conversations、live protection 和
实际 merge 核验。accepted-risk、旧结果、current-only 或生成文件过滤不能替代这些
最终要求；S0/S1 只能在同一 PR 中一起 shipping。

## 6. 构建与快照分级

| 场景 | 文档门禁 |
| --- | --- |
| 本地构建、普通 CI、Pull Request Preview | 校验 current 页面；不创建永久快照 |
| 分配 Product Build 并交付团队测试（`canary`、`dev`、`beta`） | 强制同步 current 页面，并冻结匹配 Product Build 的不可变快照 |
| `stable` 发布 | 强制使用匹配快照，并补齐 Release、生产部署和 release verification 证据 |

current 路由跟随 `main` 并明确标为非正式快照。任何已经分配 Product Build、准备
交付给测试者或正式发布的构建，都必须在同一版本 cut PR 的 S1 Task 中运行：

```bash
scripts/docs-site.sh version MILESTONE.MINOR.BUILD.PATCH CHANNEL
```

`CHANNEL` 只能是 `canary`、`dev`、`beta` 或 `stable`；省略时仅为兼容旧流程而按
`canary` 处理。命令生成不可变 `/versions/PRODUCT_BUILD/`、sidebar、版本专属图表资产与冻结元数据，
并要求版本精确匹配、工作区干净且快照不存在。已冻结版本不得重写；同一 Build
后续 Channel 晋级复用该快照，在独立发布记录中追加晋级证据。

新快照使用 metadata schema 2。元数据必须自认证完整 source commit，记录 source
commit time/tree 与投影清单、生成器得到的完整 source-document inventory（每个
source/snapshot document 的路径、byte size 和 SHA-256）、source/sidebar 与 snapshot
hash、canonical manifest 选中的每个 diagram ID 对应的 current/versioned HTML 与 SVG
路径、byte size 和 SHA-256、source revision 重建的 Product/Assembly facts，以及
freeze time。生成阶段只允许
当前 HEAD 加精确生成边界；提交后和未来 HEAD 必须证明 introducing commit 是当前
HEAD 的祖先、不可变路径从 introducing commit 起未变化、时间满足
`source <= freeze <= introducing`，并满足 direct-parent 或已批准的
squash-equivalent source projection。若 fresh clone 在 squash 后不再包含 source
commit object，验证器仍须用冻结的 raw commit bytes 自认证 canonical revision、tree
与 committer time，并从 introducing squash tree 重建和逐项核对 projection、facts、
source docs/sidebar/diagrams；对象缺失本身不能放宽证据。`versions.json` 允许追加未来版本，但每个
Product Build 条目必须唯一。仓库只保留最近 5 个 Product Build 快照
（`versioned_docs`、`versioned_sidebars`、`versioned_metadata`、
`versioned_provenance`、`static/versions/` 五类文件与 `versions.json`
同步增删）；更旧的快照作为历史发布证据保留在其发布时的 Git revision
中，可按 revision 检出审计，不随 HEAD 携带。既有 schema-1 快照保持只读
兼容，不回写。

Build/BOM 已在 `main` 的 snapshot-only Task 优先建立 direct-parent：冻结是从当前
`main` 切出的分支上首个且唯一的提交，并在 `main` 前进之前合并。新 allocation cut
按 S0/S1 在同一 PR 建立 clean source 与 matching snapshot，其 source commit 被
squash 替换，因此必须实际证明 byte-identical squash projection，而不把 source
branch SHA 称为 `main`。冻结之后不修改 source projection；需要 witness 时只走
下述官方机制，不能从历史两提交实例或本地检查推断来源已经成立。

冻结中断时保留原 source HEAD、日志与生成字节；
`scripts/docs-site.sh resume-version PRODUCT_BUILD CHANNEL SOURCE_REVISION` 仅验证
完整但尚未提交的原 freeze，严格回读其原 SHA/channel、metadata、inventory、provenance
与完整 check，绝不补生成或覆盖历史。部分、不匹配或无法核实的 freeze 停止 shipping，
等待显式 reconciliation；不执行通用删除/refreeze 来掩盖失败，也不手写 metadata。

若 squash introducing tree 合法包含冻结之后的 mutable current/non-projection
更新，因而不能逐字等同 source projection，必须另行提交由
`scripts/docs-site.sh witness PRODUCT_BUILD [INTRODUCING_REVISION]`
生成的 source-tree witness。省略 INTRODUCING_REVISION 时，命令按验证器同一套解析
逻辑从当前 HEAD 推导 introducing revision，推导不出即 fail closed 并拒绝写入；
显式传入的 revision 仍按原有规则校验。验证器在报告 witness 缺失时也会直接给出这条
可复制的补救命令及其两个参数。witness 只记录从 exact introducing tree 反向恢复 source
tree 所需的有序差异；验证器必须把差异应用到临时 Git index，重建出 raw source
commit 已认证的精确 tree hash，并重新物化相同 commit object 后，才能读取和核对
projection、facts、source docs/sidebar/diagrams。缺失、重复、非 canonical base64、
身份不匹配或不能得到精确 source tree/commit 的 witness 一律 fail closed；它不能
替代普通 direct-parent 或 byte-identical squash，也不能改写任何不可变快照文件。

版本页导航以 Docusaurus active doc ID 解析当前版本的实际 path；缺失或重复 ID
必须 fail closed。canonical manifest 选中的每个架构图 ID 都先通过 current diagram
validation，再把该 ID 对应的 HTML/SVG 输出精确复制到
`static/versions/PRODUCT_BUILD/diagrams/`。schema-2 版本页不得
引用可变 `/diagrams/*`；缺失、符号链接、越界、重复或 hash 漂移必须阻断冻结或构建。

快照 commit 不改变 Product/Module/Provider/Contract 的版本语义，只记录该 Product Build 对应的说明书。

## 7. CI、发布与回滚证据

当前正式入口为 `https://docs.lmdj.workers.dev`。生成的 canonical、Open Graph
URL 与 sitemap 使用该固定地址，版本 Preview 沿用正式 canonical，不把临时版本
地址当作正式来源。此设置不修改自有域名，也不为旧 `netlify.app` 地址建立重定向；
旧入口退役由迁移验收单独决定。冻结快照源码与来源元数据保持不可变。


全量增量批次与显式完整候选／节点自测运行 Architecture Portal suite；可选 PR Preview 是反馈，不是合并必过项。
受影响 Task 本地校验文档影响声明和 changed files；Product Build/Assembly 变化不能选择
`none`。完整门户检查同时验证
当前 Product Build 存在匹配的 `versions.json` 条目、快照源码和冻结元数据，并比对
Product、Assembly Lock、Module、Host、Provider、Contract、Channel、完整 Git 来源、
source projection、版本文档/sidebar/图表 inventory 与冻结/introducing 时间。正常生产发布只能由合入后的 Git/Cloudflare 构建触发；禁止把本地目录或
单个 HTML 通过 API/拖拽手工上传到生产站点。手工 deploy 仅可用于明确标记的临时
诊断站点。

发布验证必须记录 Git SHA、Cloudflare version ID、deployment ID/URL、HTTP 200、`Content-Type: text/html`、current Product Build/revision、正式快照路由及关键页面/图。回滚恢复 Cloudflare 的先前版本分配和路由状态，并重新运行相同 smoke；回滚不删除失败 deploy 或改写 Git/快照历史。

## 8. 公开内容边界

门户公开可读，因此不得包含密钥、token、cookie、私有 endpoint、未公开商业条款、个人数据、客户素材或仅限内部的安全细节。需要受限的信息只链接到相应权限系统，并在公开页保留不泄密的边界说明。
