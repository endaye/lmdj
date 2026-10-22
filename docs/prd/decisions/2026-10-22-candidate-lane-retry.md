# 已确认：候选批次的环境性失败车道可有界重跑一次，证据与原批次组合

- 日期：2026-10-22
- 关联：[#2422](https://github.com/endaye/lmdj/issues/2422) 第 8 项、
  [#2404](https://github.com/endaye/lmdj/issues/2404) 第 2 项。Owner 在三个
  方案（A 车道级重跑 + 组合证据；B 同 target 整批重派 + 取代规则；C 本轮
  不改契约）中选择 A。实施计划：
  [`docs/plans/2026-10-22-lmdj-candidate-lane-retry.md`](../../plans/2026-10-22-lmdj-candidate-lane-retry.md)。
- 结论：增加显式请求种类 `retry`。它只重跑同一候选未通过的车道，目标、
  policy 与原候选相同，请求内冻结每条车道的环境性证明；release 的
  `complete-test-v2` 接受「原候选结果 + 该重跑结果」的组合：每个 suite 的
  通过证据恰来自一个 attempt-1 run，全部 suite 都必须通过。
- 原因：2.0.122.0 的 11 个候选里至多 3 个败于真实产品缺陷，其余是负载、
  主机路由、派发错误或工作区被删；首轮全过 + 单一完整来源让每次环境性
  失败都要重新 cut 并再跑 4–5 小时。重跑只覆盖被证明是环境性的车道，
  不接受 attempt 2，不放宽任何断言或预算。
- 条件（reducer 与 release consumer 都失败关闭）：
  - 原候选对同一 target 已有持久结果；
  - 重跑 suite 恰等于原候选未通过的全部 suite，不做依赖闭包；
  - 每个 suite 的原结果是 `cancelled`、`infrastructure`、`missing`、
    `blocked`，或 `failed` 且其每个失败 job 的已认证 API 结论为
    `timed_out` / `cancelled`；断言失败永不合格；
  - 每个原候选只允许一次重跑；重跑不推进自动游标、不产生 debt、
    不影响 #2470 的发版让行。
- 非目标：不接受 Actions Re-run jobs；不自动派发（操作者像派候选一样派
  `kind=retry`）；不改 1 s deadline 或任何车道预算。
- 影响：`version-management.md` §12.1、发版流水线设计 §8 与 lmdj-release
  skill 中「不接受 Re-run jobs」「单一完整来源」的措辞在第二个 PR 改为
  「attempt 1 的组合来源」；操作命令写进 skill。
