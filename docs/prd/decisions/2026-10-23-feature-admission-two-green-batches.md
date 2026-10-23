# 已确认：计时敏感特性须在候选主机上连续通过两个绿色 main 批次才进入发版范围

- 日期：2026-10-23
- 关联：[#2422](https://github.com/endaye/lmdj/issues/2422) 第 12 项、
  [#2404](https://github.com/endaye/lmdj/issues/2404) 第 4 项。Owner 于 2026-10-22
  在会话中选择「N=2，决策记录 + skill 规则」，暂不做工具强制。
- 结论：一个计时敏感特性只有在它合入 main 之后，连续两个自动 main 批次
  （不是候选或 node 批次）在候选主机上全部通过——每个批次的 executor run 成功、
  `batch-verdict-<target>-<run>-1` 里拥有该特性车道的 suite 为 `passed`、没有
  为这些 suite 新建的 triage Issue——才可以进入候选的发版范围。不满足时，
  该特性从 cut 中撤出（revert 或推迟 cut），不以「本地通过」「PR 车道通过」
  或单个绿色批次代替。仓库目前没有 release-scope flag 机制，所以撤出是唯一
  路径；flag 机制另议。
- 计时敏感特性的判定：改动触及音频调度、Control 线程/worker、count-in、
  录音切换、Runtime 或 Creator 的浏览器 Proof journey、带 deadline 或预算的
  stress/gates 车道（core_macos gates、core_release_stress、core_tsan_stress、
  web_runtime_host、creator），或者它的 PR 车道在 batch-only 车道留下未验证
  的声明。有疑问时按计时敏感处理。
- 候选主机（2026-10-22 决定）：macOS gates 与 Release stress 在 M1，Web lane 在
  netcup，Linux Core 在 ci-core（contabo）。溢出主机（M4 Pro、en-home）上的绿色
  批次不计入这两次。
- 原因：COUNT-IN（#2342、#2359）在 2026-10-18 cut 当天合入，其延迟缺陷
  （#2394、#2395）只在较慢主机上显现，PR 阶段的检查看不到；两个候选因此丢失，
  Owner 最终撤回了该特性。两个连续批次在候选主机上通过，才能把「只在慢主机上
  出现」的缺陷挡在 cut 之前，同时不要求每个特性都等待一次完整发版。
- 非目标：不改 PR 合并门禁；不自动判定特性是否计时敏感；不做工具强制
  （以后若需要，再把这条规则接到 release 驱动器的 candidate 步骤）。
- 影响：lmdj-release skill 在候选准入段记录这条规则；`tests/build/release_skill_test.py`
  钉住措辞。
