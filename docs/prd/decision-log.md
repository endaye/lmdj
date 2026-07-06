# 决策记录

这里记录已经确认的产品和技术决策。没有确认的内容不要写进这里，先放到 [open-questions.md](open-questions.md)。

## 2026-07-02

### 已确认：当前处于脑暴和 PRD 快速迭代阶段

- 结论：当前仓库先服务于素材整理、工作版 PRD、开放问题和决策记录。
- 原因：已有输入包括高嘉丰 PRD 素材和 demo 工具，但它们都不是最终版本。
- 影响：文档中需要明确区分“素材”“假设”“待决”“已确认”。

### 已确认：`lmdj-song-pipeline` 是高嘉丰 demo 工具

- 结论：`lmdj-song-pipeline` 是后续可参考、可复用的 demo 工具，不是 LMDJ 最终系统架构定稿。
- 原因：该工具能证明音频到 playable patch 包的技术链路，但产品系统仍在脑暴。
- 影响：后续 PRD 可以参考它的 package contract 和运行方式，但不默认继承全部设计。

## 2026-07-06

### 已确认：`lmdj-song-pipeline` 是参考项目，不是最终代码边界

- 结论：`lmdj-song-pipeline` 是高嘉丰提供的个人参考项目和可复用技术素材库；LMDJ 可以吸收其中的功能和代码，但最终云端系统、产品对象、服务边界和 package contract 需要按 LMDJ 自己的架构定义。
- 原因：当前产品方向已经从 demo pipeline 扩展为 AI-native sampler workstation，核心对象是 `Patch / Pad / Scene / Element`，不应被参考项目的目录结构、API、CLI 或状态模型锁死。
- 影响：后续技术方案需要区分“复用 pipeline 能力”和“继承系统架构”。`Patchify` 应作为参考 pipeline 输出到 LMDJ 产品对象之间的 adapter layer；正式实现不写入 `lmdj-song-pipeline`。

## 2026-07-07

### 已确认：Patchify 进入正式源码边界重新编写

- 结论：`references/demos/lmdj-song-pipeline/` 和 `references/demos/ascii-matrix-camera/` 都只作为参考 demo；Patchify 需要作为 LMDJ-owned code 在正式目录中重新编写，第一落点是 `packages/patchify/`。
- 原因：Patchify 是产品核心能力，需要服务 Web、CLI、Audio Worker、云端 API 和后续 community/lineage，不应被参考 demo 的 CLI、API、状态模型或目录结构锁定。
- 影响：新实现计划采用 Path B：先建立 `apps/`、`packages/`、`workers/` 边界，再实现独立 `packages/patchify`，只消费参考 pipeline 可能产出的 `samples/*.wav`、`chart.mid`、`lanes.json`、`report.json`。
