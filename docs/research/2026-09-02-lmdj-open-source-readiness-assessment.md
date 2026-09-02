# LMDJ 开源就绪度与分层开源策略评估

> 研究日期：2026-09-02
>
> 研究对象：LMDJ New Headless Core 仓库自身——许可证、治理体系、源边界、
> 依赖构成与仓库历史的开源可行性。
>
> 关联材料：[`LICENSE`](../../LICENSE)、
> [`docs/governance/version-management.md`](../governance/version-management.md)、
> [`docs/governance/git-workflow.md`](../governance/git-workflow.md)
>
> 研究性质：策略分析输入。不是许可证变更、仓库公开、组件发布或对外发布渠道的
> 决策或授权；任何实际开源动作都需要单独的产品级决策。

## 0. 结论先行

**LMDJ 在工程纪律上属于高度"开源就绪"的仓库，但当前整体开源的时机与动机都不
成熟。更合理的路径是按 `LICENSE` 第 3 条已经预留的机制，在产品闭环稳定后从
`contracts/` 开始分层、选择性开源。**

三句话概括：

1. 治理文档、版本策略、Contract SemVer、签名 tag、分层测试与 pitfall ledger
   使外部贡献者可以直接理解构建方式、贡献边界与流程约束——这是开源的资本。
2. 产品仍处于 M2 / Stage 10 中途，唯一版权人也是唯一维护者，整体公开只会
   换来维护负担与产品差异化外流，而换不来用户或贡献者。
3. `LICENSE` 第 3 条（Separately Licensed Components）已经为"指定文件、目录、
   组件单独以开源许可发布"留出口子，分层开源不需要改动现有专有许可框架。

---

## 1. 现状证据

### 1.1 许可与可见性

- GitHub 仓库 `endaye/lmdj` 当前为 **PRIVATE**。
- `LICENSE` 是一份明确的专有许可（版权人张远程，2026），默认不授予任何使用、
  复制、修改、分发权利；仓库访问本身不构成授权。
- 该许可第 3 条明确允许版权人将"specifically identified files, directories,
  components, or distributions"以单独条款（包括开源许可）发布，且不影响其余
  部分的专有地位。**分层开源在许可结构上已经是被预期的路径。**

### 1.2 工程与治理就绪度

以下机制通常是成熟开源项目才具备的，本仓库已经全部在位：

- 治理文档体系：git workflow、version management、architecture portal、
  pitfall ledger 均有 canonical 文档且被 CLAUDE.md / AGENTS.md 强制引用。
- 版本纪律：Product Build 四段版本、Core Module / Provider 独立 SemVer、
  Contract ID + Contract SemVer、不可变签名 tag。
- 测试分层：unit / component / stress 三层 + 双平台 ASan CI，
  `docs/quality/core-test-policy.md` 为 canonical 定义。
- 架构切分：`packages/`（产品中立 Core Module）、`contracts/`（跨语言合同）、
  `providers/`（Capability Provider）、`products/`（Product Assembly）边界
  清晰，天然支持"开源核心合同、保留产品装配"的分层策略。
- 第三方依赖极少：`third_party/` 仅 nlohmann-json 与 picosha2，均为宽松许可，
  无传染性（copyleft）风险。

### 1.3 不利于当前整体开源的事实

- README 自述未实现项：installable/offline PWA、Sample intelligence、
  Sequence 编辑、production Providers、云部署；五个 Web 物理设备验收行仍为
  `deferred / unverified`。产品闭环尚未完成。
- LMDJ 是有产品野心的 playable beat instrument，不是基础设施库；整体开源
  等于交出产品差异化。
- 单一版权人、单一维护者，Stage 10 仍在进行，没有社区运营带宽。
- 仓库历史约 660+ 提交，包含已退役的 `lmdj.patch.v1` / `lmdj.materials.v1`
  Web/API/Worker 产品；公开前需要一次完整的历史秘密扫描（token、密钥、
  内部 URL），这是独立工作项，尚未执行。

---

## 2. 分层开源建议（按顺序）

1. **`contracts/` 优先**。跨语言合同本来就是给外部消费者设计的，有稳定的
   Contract ID + SemVer 身份，开源成本最低、对外信号最好。
2. **其次是个别真正产品中立的 Core Module**（例如 Project I/O、Runtime
   Snapshot 一类），以其独立 SemVer 单独发布，仍受 `LICENSE` 第 3 条框架
   覆盖。
3. **产品本体最后**（`products/`、Web Host、Provider 实现）：留到产品形态
   稳定、明确需要社区时再评估；届时应通过 fork 出的干净新仓库发布（配合
   历史清理与秘密扫描流水线），而不是直接公开本仓库。

## 3. 任何公开动作前的必要前置

无论开源哪一层，公开前必须完成：

- 全历史秘密扫描（凭据、token、内部 URL、个人信息）；
- 明确所选组件的开源许可（倾向宽松许可以匹配现有依赖生态），并在对应目录
  放置独立 LICENSE 文件、在根 LICENSE 第 3 条框架下显式列举；
- 为公开组件补齐面向外部的 README / 贡献指引（现有治理文档以内部代理为
  主要读者，需要外部视角的裁剪）；
- 确认公开范围不泄露未公开产品能力或 `docs/prd/` 中未决的产品问题。

## 4. 结论与触发条件

当前动作：**不开源，维持 PRIVATE**。重新评估的触发条件：

- Stage 10 收尾且产品能跑出可演示的完整演奏闭环；或
- 出现明确的外部消费者需要 `contracts/` 或某个 Core Module；或
- 版权人出于产品策略主动决定公开。

届时按第 2 节顺序执行，并逐项完成第 3 节前置。本文档不构成上述任何一步的
授权。
