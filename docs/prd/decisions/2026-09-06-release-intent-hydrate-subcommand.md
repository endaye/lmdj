# 已确认：release intent target 的补全是显式的 `scripts/release.sh hydrate` 子命令，audit 不做 fetch-on-miss

- 日期：2026-09-06
- 结论：稳定接口新增一个显式子命令 `scripts/release.sh hydrate`。它读
  `docs/release-evidence/release-intents.json`，把 `entries` 与
  `historical_exceptions` 两个列表里的 `target_revision` 全部收集起来，先用
  `git cat-file -e <sha>^{commit}` 逐个探测，只对本地缺失的那些执行一次
  `git fetch --no-tags origin <missing shas>`，然后分别报告"本来就在"与
  "这次补全了哪些"。它是幂等的：什么都不缺时不发起任何 fetch，重复执行也不
  改变结果。它是 `scripts/release.sh` 里唯一被允许写本地 object store 的
  子命令。

  `audit` 保持只读，绝不 fetch-on-miss。缺失 target 仍然是一个
  `unverifiable` finding，但消息现在同时携带 `why`（该 intent 无法与它记录
  的 commit 绑定，且 audit 不得自行 fetch）与 `remedy`（`remedy: run
  scripts/release.sh hydrate`），满足
  [`../../governance/pitfall-ledger.md`](../../governance/pitfall-ledger.md)
  的 gate failure message 规则。

  `ci.yml` 的 Deploy contract lane、`release-audit.yml`、
  `publish-release.yml` 的 `preflight` 与 `publish` 两个 job 里各自那份内联
  hydrate-by-SHA 脚本全部替换为调用该子命令，环境变量式 git 凭据
  （`GIT_CONFIG_COUNT` / `GIT_CONFIG_KEY_0` / `GIT_CONFIG_VALUE_0` 配
  `url.https://x-access-token:TOKEN@github.com/.insteadOf`）原样保留，凭据
  仍然不落盘。本文件解决 Issue
  [#332](https://github.com/endaye/lmdj/issues/332)，它是 pitfall
  `release-intent-target-reachability` 的 recurrence-2 升级。

- 原因：三个候选方案里只有显式子命令同时满足"消除每个消费方各自的内联副本"
  与"audit 保持只读"。

  1. **audit 内部 fetch-on-miss（自愈）**——否决。标准发行流水线设计
     [§12 Read-only audit](../../design/2026-08-13-lmdj-standard-release-pipeline-design.md)
     原文写的是 `Audit 不创建、push、编辑或删除任何 Git/GitHub 状态`。
     `git fetch` 会把新对象写进本地 Git object store，也就是创建 Git 状态，
     所以 fetch-on-miss 直接违反 audit 自己的只读契约。要说清楚的是：
     `audit --local` 今天完全不联网，fetch-on-miss 会凭空给它加上一次网络
     写入；`audit --remote` 确实会 `fetch_authority` 一个固定、有界的
     refspec 到 `refs/lmdj-release/*` scratch ref，但那是**读取** canonical
     远端真相的手段，与 fetch-on-miss 在性质上不同——后者修复的正是 audit
     本该报告的那一处缺陷，于是在全新 clone 上这个 finding 会静默自愈、永远
     不会被看见。审计工具把自己要报告的问题顺手修掉，等于放弃了报告。
  2. **显式 `hydrate` 子命令**——采纳。写入边界只有一个、有名字、可被授权
     和审计；audit 的只读契约不动；消费方从"每个都得知道那段 workaround"
     变成"调用一个稳定命令"；operator 在全新 clone 上也走同一条路径，不再
     依赖长期 runner 工作区里残留的对象。
  3. **限制 intent 只能记录 protected-main ancestor**——否决。它与
     [`release-intent-binding`](../../../.agents/pitfalls/release-intent-binding.md)
     覆盖同一件事（`prepare` 已经拒绝非 protected-main ancestor 的 target），
     而且它修不了已经记录在案的 `lmdj-v1.0.25.0`：那一行的
     `target_revision` 是不可改的历史事实，改它就是重写发行意图。这个方案只
     能约束未来的 intent，对当前每次审计都在报的那个 finding 无效。

  这条 pitfall 之所以反复出现（PR #328、Issue #331、PR #400），根因不是某个
  workflow 写错了，而是"哪里补全对象"这件事一直没有归属：谁需要它谁就复制一
  份，副本之间还会各自漂移。给它一个名字就是把归属定下来。

- 影响：operator 的动作变了一步——在全新 clone 上先跑
  `scripts/release.sh hydrate`，再跑 `scripts/release.sh audit`。什么都不缺
  时 `hydrate` 打印 `all release intent targets were already present` 并
  返回 0，所以无条件先跑一次是安全的，不需要先判断"这台机器缺不缺"。
  `hydrate` 只做本地补全：它不创建 tag、不 push、不碰 GitHub Release，也
  不构成任何发行授权。

  `audit` 的 finding 文案变了（新增 target SHA、why 与 remedy），依赖精确
  finding 字符串的下游读者需要跟着更新；finding code 仍是 `unverifiable`，
  JSON report 的形状不变。四个 CI job 少了各自那 17 行内联 Python。防复发
  gate 是 `tests/build/release_hydrate_test.py`：它断言每个调用
  `scripts/release.sh` 的 job 都先跑 `hydrate`、三个 workflow 里都不再出现
  内联的 ledger 读取或按 SHA fetch、audit 的 directives 里没有 fetch、以及
  audit remedy 里写的子命令名确实被 `release.sh` 的 subparser 接受。

  版本影响：无。这是发行工具与治理改动，不涉及 Product Build、Core Module、
  Provider 或 Contract。
