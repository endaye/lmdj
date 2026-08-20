# LMDJ Docs

`docs/` 是 LMDJ 的过程文档与工作区：治理规范、产品迭代、设计/计划、调研、
验收与发布证据。这份文件是 `docs/` 的唯一目录级索引；不需要也不维护逐文件清单。

当前产品说明书（架构、模块、Host、Provider、Contract、版本）不在 `docs/`，
唯一发布源是 [`apps/architecture-portal/`](../apps/architecture-portal/)，
由 `scripts/architecture-portal.sh check` 门禁；两者冲突时以门户为准。

## 目录地图

| 目录 | 用途 | 生命周期 | 命名 |
| --- | --- | --- | --- |
| `governance/` | canonical 治理规范（Git 工作流、版本管理、架构门户） | 持续维护 | 固定主题名 |
| `prd/` | 产品输入与迭代：素材池、工作版 PRD、开放问题、决策记录 | 活文档；每问题/每决策一个文件 | `questions/`、`decisions/` 见 `prd/README.md` |
| `superpowers/specs/` | 设计 spec（实施前的边界与验收设计） | 日期产物，完成即冻结，不删不改 | `YYYY-MM-DD-<slug>.md` |
| `superpowers/plans/` | 实施计划（Task 级步骤与验证） | 同上 | 同上 |
| `superpowers/sdd/` | 跨会话/跨执行器交接文档 | 用完即删 | `YYYY-MM-DD-<slug>.md` |
| `quality/` | 验收、评审、proof、测试政策与工作清单 | 政策持续维护；验收记录为日期产物；TODO 完成即删 | 政策固定名；其余 `YYYY-MM-DD-<slug>.md` |
| `release-evidence/` | 每次发布/canary 的证据与 artifacts | 不可变，只追加 | `YYYY-MM-DD-<slug>.md` |
| `research/` | 产品与技术调研 | 日期产物，完成即冻结 | 同上 |
| `architecture/` | 架构叙事与架构决策记录 | 持续维护 | 决策用 `YYYY-MM-DD-<decision>-decision.md` |
| `deploy/` | 部署运维 runbook（portal、runtime、staging） | 持续维护 | 固定主题名 |

## 入口指针

- 仓库规范与边界：根目录 `AGENTS.md`（`CLAUDE.md` 与其内容一致）。
- 当前架构：门户 current 页面 + `architecture/current-product-architecture.md`。
- 当前实施计划：AGENTS.md 的 Design authority 一节指向的 plan。
- 产品决策：`prd/decision-log.md` 与 `prd/decisions/`；
  架构决策在 `architecture/`，两者只记录已确认结论。
- 项目状态：根目录 `README.md` 的 Current status。

## 约定

- 日期产物（specs/plans/research/quality 验收/release-evidence）只增不改：
  修正进新文件或对应活文档，Git 历史即归档，不建手工归档目录。
- 工作清单（TODO/交接）完成即删；阶段 triage 记录保留为日期产物。
- 检索用日期前缀排序与 `git ls-files 'docs/**/*.md'`，不维护全量索引文件。
- PR/计划的 `Documentation impact` 声明按
  [`governance/architecture-portal.md`](governance/architecture-portal.md) 执行；
  运维操作看 [`deploy/architecture-portal.md`](deploy/architecture-portal.md)。
