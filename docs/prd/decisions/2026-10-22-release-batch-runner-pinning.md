# 已确认：候选与重跑批次钉死在主用主机上，溢出主机的准入变化碰不到发版

- 日期：2026-10-22
- 关联：[#2422](https://github.com/endaye/lmdj/issues/2422) 第 11 项、
  [#2404](https://github.com/endaye/lmdj/issues/2404)「Runner selection drift」。
  Owner 在三个方案（A 选择器层钉死；B 再把 en-home 收窄到非计时车道；C 再让准入
  脚本在候选进行时冻结标签）中选择 A。
- 结论：`select-macos-runner` 与 `select-web-runner` 从冻结的执行 manifest 读
  `identity.request_kind`；为 `candidate` 或 `retry` 时，macOS gates 只选 M1
  （忙则排队；只有 M1 离线/缺失/标签不符才回落 GitHub-hosted），四条 Web lane
  只选 netcup，无论 M4 Pro 或 en-home 是否空闲且已准入。自动批次与 `node`
  诊断保持 2026-10-15 与 2026-10-16 的溢出路由不变。
- 原因：2.0.122.0 期间 en-home 溢出准入（#2371/#2375）在发版中途改变了车道
  主机，候选证据来自预算未经测量的主机。会改标签的只有两个溢出主机的准入脚本
  （M4 Pro 的 `ci-macos-gates`、en-home 的 `ci-web-overflow`，每分钟按主机条件
  增删）；把冻结放在标签的消费者（选择器）而不是生产者（脚本），不需要跨主机
  信号，发版车道从此不读准入标签。部署与发布 workflow 全在 GitHub-hosted 上运行，
  标签影响不到。
- 非目标：不改准入脚本；不收窄自动批次的 en-home 车道集合（哪些 Web lane 算
  「非计时」没有测量依据，另议）；不改任何预算或 hosted 回落。
- 影响：`.github/workflows/ci.yml` 两个选择器各加一个 `BATCH_REQUEST_KIND` 分支；
  `tests/build/ci_runner_fallback_test.py` 用真实选择器脚本覆盖候选/重跑/自动三类；
  `docs/quality/core-test-policy.md` 与 lmdj-release skill 记录规则。
