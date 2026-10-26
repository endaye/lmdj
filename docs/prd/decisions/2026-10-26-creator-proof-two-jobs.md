# 已确认：Creator Proof 拆成两个 CI job，各自保留 55 分钟上限

- 日期：2026-10-26
- 关联：[#2286](https://github.com/endaye/lmdj/issues/2286)、
  [#2422](https://github.com/endaye/lmdj/issues/2422)。Owner 于 2026-10-26 在会话中
  选择「拆成两个并行 job」，而不是再次提高上限或先压缩 journey（#2292）。
- 结论：`creator` lane 由 `creator-web` 与 `creator-web-serial` 两个 job 组成，两者都保留
  2026-10-15 决定的 55 分钟 hang 检测上限。`creator-web` 做一次 clean build 后运行独立的
  Chromium worker 池；`creator-web-serial` 负责两次 clean build 的字节一致性、单元测试、
  串行浏览器组与 deployment journey。batch verdict 要求两个 job 都通过；任何 journey、断言
  或预算都不减少。
- 执行方式的说明：两个 job 加入同一个 Web 主机容量队列（2026-10-15 已证实重叠运行这些
  CPU 受限的浏览器组会更慢且更易失败），所以在同一主机上先后执行，而不是并行。每个 job
  都在自己的上限内结束，代价是 serial job 再构建一次，整条 lane 的墙钟时间约多十几分钟。
- 原因：2026-10-26 的 main 批次里，netcup 上构建与单元测试约 14 分钟、Chromium 池约 35 分钟，
  其余串行组约 10 分钟，总计约 60 分钟，job 在 55 分钟处被取消，串行组从未运行。
- 影响：`.github/workflows/ci.yml`、`web-ci-proof` action 的 `creator-part` 输入、
  `scripts/creator-web.sh` 的 `LMDJ_CREATOR_WEB_PROOF_PART`，以及 change scope、
  scope/self-test 策略与 batch 证据校验中的 lane job 列表。
