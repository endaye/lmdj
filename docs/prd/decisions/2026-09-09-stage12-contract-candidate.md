# 已确认：Stage 12 Slice Contract 与 Candidate 采纳规则

- 日期：2026-09-09。
- 确认依据：用户对 PR #1046 的完整 R1、R2-A～F 方案回复「确认」。
- 关联：#467、#471；实施子任务 K1～K5、L1～L5。
- 权威定义：[完整评审包](../../design/2026-09-09-stage12-contract-candidate-review.md)。
  本次逐项确认该文件的 R1 与 R2-A～F，包括 descriptor JSON、profile、
  参数/输出上限、错误归属、区间规则、生命周期和 lineage 字段表。
  评审包原有「待确认」文字保留历史；本条是确认依据。

## 结论

1. R1：首个消费方为 sample.slice.v1；采用评审包中的完整公开定义。
   新消费方、WAV profile、slice-points Schema 初始版本均为 1.0.0。
   capability.v2 外壳不变。初始参考注册只声明 test；native 支持须分别实测。
   资源数值仍是待测起点，不是 hard timeout 或总 RSS 保证。
2. R2-A：SDK 保留单 Candidate；Facade 所有的 Workspace 状态从一个
   slice-points Artifact 派生多个 recipe，持久化独立的 Set/recipe 身份。
3. R2-B：有 onset 时以去重后的 0、onset、EOF 划分完整半开区间；
   无 onset 时零候选。源 Asset 与字节保留，采纳物化独立派生 Artifact。
4. R2-C：同 Job 串行 Attempt。失败或取消保留旧 active set，成功耐久
   发布才替换；Job/Index 原子发布，terminal 不回写。取消不宣称中断
   direct Provider 执行。重启仅检查已记录的 Attempt，不扫描 blobs。
5. R2-D：明确目标 Pad 的多候选采纳一次原子 revision；重复目标拒绝，
   同候选可投向不同 Pad 并分别记账。旧 revision 重试拒绝，新 revision
   的新确认是新采纳；首版不承诺幂等重放，未知提交结果先 inspect。
6. R2-E：校验 Project/Asset 身份和完整 ArtifactRef；无关 Project 编辑
   不使源绑定未变的候选失效。无自动 TTL；discard/supersede 不触发 GC。
7. R2-F：复用 Asset.lineage，增加一个封闭 capability_adoption 派生类型，
   字段权威取自 terminal、源绑定和 Core recipe；保留 resample/soundset
   的原字段。Preview 不改真相，采纳前完整预演所有目标配额。

这替代旧 Candidate 草案中 plural SDK 结果、SDK 所有 Job 状态和自由可选
lineage 字段的提议。无需为 Candidate 再分配一次 SDK 2.0.0。
Pattern Merge、Project Bin、GC、后续 Stem/recipe 变体保持各自独立边界。

## 实施与验收

K1 按[当前文件清单](../../plans/2026-09-09-stage12-review-delivery.md)执行。
K2～K5 仍依次完成 SDK 字节边界、参考 Provider、产品注册和 Host 接线。
L1～L5 的产品问题已确认；每个 Task 仍须补齐精确文件、测试、版本和依赖
清单。批准规则不等于实现已完成，不提前关闭父 Issue。

本确认记录 Task 声明文件：本文件、review-delivery 计划、decision-followups
计划；检查相对链接、staged 路径归属和 whitespace。实现 K1 为下一独立 Task。
本条记录既有评审包的批准，不新增源码事实或检查门禁。

## Version Management

Version impact: none for this confirmation Task；新 Contract 的上述初始版本
由 K1 落入 active 文件。SDK MAJOR、Project 后继 Contract 与其他依赖版本
仍在各自实施时按当前 manifests 分配，不分配 Product Build 或 Channel。

## Documentation Impact

Documentation impact: none for this confirmation Task；仅 retained 决策状态。
K1 同步更新当前 Contract 页面；后续产品可用性随真实实现更新。
