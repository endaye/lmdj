# LMDJ CI reliability, recovery and execution cost：T12 集成验收报告

日期：2026-09-10（Asia/Shanghai）
范围：Orca Run `run_71c2492cd783`、批准计划 [`docs/plans/2026-09-10-lmdj-ci-reliability-and-cost.md`](../plans/2026-09-10-lmdj-ci-reliability-and-cost.md)、报告记录的 `origin/main` 验证基线
报告记录的 exact main 验证基线：`996a557357902dc447750dd94b32b568a9be36e0`（PR [#1145](https://github.com/endaye/lmdj/pull/1145) 的 merge commit；前一验证基线为 [PR #1144](https://github.com/endaye/lmdj/pull/1144) 的 `32b6baf9dc17fc12a8d0b928840c57e5d3ea6fe5`）

## 结论

T0–T11d、T8c 的已批准实现与 T12a 的 Issue/工作流卫生切片均已合入；本报告补齐
当前文档、合并 provenance、测试计数、成本观测和保留的外部验收缺口。当前
该验证基线下的 `main` 保持可继续集成的状态，不把这次报告解释为产品发布就绪、完整 CI 健康
或 O1/O2 自动化通过。

已落地的行为包括：撤除不可达 admission 与 merge queue/phase gate；PR 上的
selected advisory contract 与 current-head review 证据；事务内不可变 journal
proof 复用；GitHub quota/debt 的 fail-closed 处理；source-bound shared event
聚合；新 managed bucket 的有条件恢复；Canary Planning 的手动冻结；两台受信
主机的角色资格与只读 inventory；以及 T12a 的默认 `ci:storage` 排除和合并前
GitHub 实际 closing-reference 核对流程。

下列结论仍明确保留为未完成：远端 report/discovery 恢复尚无三次连续成功观察；
#666 的成因未解决；#782 的 TSan race、#939 的 backend diagnosis、#714 的
clean-thread retirement、#914 更广泛的 runner discovery 和 P1.4 的 genuine
publication 仍需各自的证据与授权。没有执行 release、deploy、Channel promotion、
Canary init/readiness、journal reset、主机配置变更或额外 hosted spend。

## 1. 合入与 review provenance

以下清单按本次计划所列的 durable GitHub PR provenance 整理，只列本次计划的 Task；每行同时给出实际 squash
merge SHA 和该 Task 最终接受的 reviewed head。PR [#1092](https://github.com/endaye/lmdj/pull/1092) 是 T5a 前置实现，随后
由 #1115 完成范围收紧；PR #1101 是 P1.4b 的最终发布审计修订。

| Task/目的 | PR | merge SHA | reviewed head |
| --- | ---: | --- | --- |
| T0 计划与交接 | [#1098](https://github.com/endaye/lmdj/pull/1098) | `1586b5f2367fad451bbc5dd85fa92e5fc92b3b41` | `7ca996dbbcf4c4ac25eda4c2d2feee9ade72bf19` |
| P1.1 pitfall area | [#1099](https://github.com/endaye/lmdj/pull/1099) | `9d4bf08361966e6062bc6c109706e769b2cc3161` | `83d591e8487194804286153ce08407f6dbcba83d` |
| T5a 前置 Contract profile admission | [#1092](https://github.com/endaye/lmdj/pull/1092) | `dae1cac2d248e55dbe46996900aceaacdbb22cc9` | `df7e71cc621773fd71821167a26c753af13a0b87` |
| T1a/P2.2b retired pre-heavy admission | [#1100](https://github.com/endaye/lmdj/pull/1100) | `c6b6e5f3fa1b18e626143279fe07630c89b9d0e4` | `4453911ed964ad88c97b5271ff05e7e195d3a937` |
| P1.4b post-publication audit repair | [#1101](https://github.com/endaye/lmdj/pull/1101) | `0ecfb282bf8435c3509214cd16610007e880fc34` | `6d7dffc645af2d43266027f28c9682294af8d099` |
| T1b/P2.1 retired queue and phase gates | [#1103](https://github.com/endaye/lmdj/pull/1103) | `deed5377e9c118c35b1d68d51e390f101251db17` | `9e4dfd5a1f5c0ad456d355e828ecb40eb0d82966` |
| T2 placeholder review rejection | [#1114](https://github.com/endaye/lmdj/pull/1114) | `97322e612a395dabc7076d5137f14ec2ba9497a2` | `878785beee6c686201cebb92dd0454391c82fb0e` |
| T5a Contract profile restriction | [#1115](https://github.com/endaye/lmdj/pull/1115) | `1b36c9fd7467ac8d9c858d95a91f00842bf13723` | `06941414400173ff62b2b56c4207f5f1773cd379` |
| T3 current-head review admission | [#1116](https://github.com/endaye/lmdj/pull/1116) | `f987a7c305c9e9da00285d3be08abda7fdf62deb` | `621e86ce45ab160f5d66e9d622bac7b4131ac7e0` |
| T4 executable-test routing | [#1117](https://github.com/endaye/lmdj/pull/1117) | `67d823e2e037ce6779a408e47c81ca8dbb57b759` | `cc5949da7edb23d92c889efdfe2aecb5c1011d70` |
| T5b Catalog admission parity | [#1119](https://github.com/endaye/lmdj/pull/1119) | `7882c8879f7a24a9185b9be85f4748042c9b788d` | `ec719265f70c721cc509206bef5a5c826801d25b` |
| T10 Canary automatic trigger freeze | [#1120](https://github.com/endaye/lmdj/pull/1120) | `428e808c57d39cef5770a34418891b3f29e40e3e` | `32ae802cedf7c733e08a9dd899c2a04e1d0761f4` |
| T11c stress diagnostic | [#1121](https://github.com/endaye/lmdj/pull/1121) | `3ee64eab3ba988e571a725ece363ed53ac8dbd49` | `1ccedff9fdbb643306c532ff6cc00e6fb86b1517` |
| T12a Issue/closing-reference hygiene | [#1123](https://github.com/endaye/lmdj/pull/1123) | `656d17868e424dd9cf554eb9942e3e2fadde427a` | `e7994917c6660d0cfc29fde1514eafc84a46fdfb` |
| T6 quota recovery | [#1125](https://github.com/endaye/lmdj/pull/1125) | `03bc48c2ee5f647891671e0f51875bc39ec95a14` | `725b7e11d968121c289caa223416aa5ebebcdda5` |
| T7a transaction-local proof reuse | [#1133](https://github.com/endaye/lmdj/pull/1133) | `bfe0e755c24dd40bc8faea914a511bc3d5d2b603` | `98b7c01043c25ab7070be149e47b9b0070d31940` |
| Final premerge live-rule refresh | [#1128](https://github.com/endaye/lmdj/pull/1128) | `73c8009af49d1962be01c2c3f0ed3ffc50a52834` | `2814ad5d7a46812b1e8c53683e002cb55d19a19b` |
| T11a control-host eligibility | [#1135](https://github.com/endaye/lmdj/pull/1135) | `0e6838d2dfc391114529b6d990651aefbadb9b41` | `2af3abc815e623252dc548dea57712f694af2f39` |
| T7b checkpoint protocol design | [#1136](https://github.com/endaye/lmdj/pull/1136) | `f1bf0d5d94f1657f168f55034878b5f31cf2fc14` | `a6512631846ef3cb6d206ffd5453fee82c5dcb33` |
| T11b explicit host inventory | [#1137](https://github.com/endaye/lmdj/pull/1137) | `04aea557b4472cf52a74390ae300a3d77c6d1ce6` | `a21dc166a6690da2ff9b6fd327d0cd614161dbe9` |
| T11d inventory sanitizer observation | [#1138](https://github.com/endaye/lmdj/pull/1138) | `9545faa8325c16cb09500be0a86cdc83ab08231c` | `163a07bb607b52a98792cd9d319b2cc84f3f6244` |
| T9 selected PR advisory | [#1139](https://github.com/endaye/lmdj/pull/1139) | `53278e06f898c48087f0d87588d72286807e9894` | `5ede25419b5ec864d94bfcbe5209b9ed3b1aa72e` |
| T8a shared event aggregation | [#1140](https://github.com/endaye/lmdj/pull/1140) | `0ed20350990180c7bc06efb4d519b6dcad7d708d` | `e294400651cc48035a4987e892b8d2ed94a79900` |
| T8b managed bucket recovery | [#1144](https://github.com/endaye/lmdj/pull/1144) | `32b6baf9dc17fc12a8d0b928840c57e5d3ea6fe5` | `d0bc36239cd85520a09f96d722412ff1c1ad1a6c` |
| T8c canonical scheduler projection | [#1145](https://github.com/endaye/lmdj/pull/1145) | `996a557357902dc447750dd94b32b568a9be36e0` | `119b17a0f4ac5c2a44a948e6b283492d444da81f` |

每个 PR 的 independent review、findings/disposition、冲突与对话保护由协调器
在 exact reviewed head 上复核；失败的 bot/backend run 保留为失败证据，不被清除
或重标为通过。PR #1121 暴露的 closing-parser recurrence 已由 PR #1123 修复，后者将
deterministic body lint 与 GitHub `closingIssuesReferences` 的外部核对都纳入流程，避免把否定性句子
误解为保留 Issue 的安全表达。

PR #1144 合入后的第一次完整 Linux advisory run [34401624578](https://github.com/endaye/lmdj/actions/runs/34401624578)
在 reviewed head `d0bc36239cd85520a09f96d722412ff1c1ad1a6c` 上实际失败：2159 tests、
4 failures、17 errors、170.807s。失败根因是 report runtime 将 `_result_order` 混入
canonical `scheduler_state`，破坏 O1 claim/cancel consumer 的严格状态相等断言；该
失败不是通过、跳过或可接受的 advisory 绿灯，修复由独立 T8c Task 单独承担，原始日志
继续保留在本地收据中。

随后在 T8c reviewed head `119b17a0f4ac5c2a44a948e6b283492d444da81f` 上完成的 Linux
advisory run [34404037938](https://github.com/endaye/lmdj/actions/runs/34404037938)，其
`ci_contract` job [102642953315](https://github.com/endaye/lmdj/actions/runs/34404037938/job/102642953315)
为 durable PASS：2167 tests、497.904s、无 skip、退出码 0。该结果证明当前 head
的 CI contract discovery 集成通过，但不替代远端 report/discovery recovery 所需的连续
source-bound observations。

## 2. Task 验证摘要

以下是任务记录中的实际命令/计数；“skip”只记录既有 environment 或 platform 条件
限制，不等同于通过。环境限制（如未配置 pinned actionlint）与平台限制（如 Linux
`/proc` guard）分别保留。任务范围以 [`docs/plans/2026-09-10-lmdj-ci-reliability-and-cost.md`](../plans/2026-09-10-lmdj-ci-reliability-and-cost.md)
为准；各任务的 durable provenance 由下列 PR 与 workflow run 链接提供，本地 body/log
仅作为可选收据。

| Task | 验证与结果 |
| --- | --- |
| T0 | `ci_change_scope_test.py` 66/66；计划 byte-identical、body lint、whitespace PASS；bot run `34379291343` 失败证据保留。 |
| T1a/T1b | pinned actionlint 1.7.12 PASS；最终 full discovery 分别 2209 tests/12 skips、2084 tests/12 skips（T1b 1064.844s，之前的 UTC recurrence failure 已由 #1123 修正）。 |
| T2/T3 | review scope 41、review pipeline 45；review-wait/current-head suite 81，均 PASS。 |
| T4/T5a/T5b | T4 声明 suite 117/117；T5a metadata 20/20、handoff 27/27；T5b Node 22/26 Worker parity 各 16/16，Python parity 6/6（Node26 58.599s），Portal 116 tests/44 pages/10 sources/20 outputs/44 routes。 |
| T6 | runtime、batch、report/HTTP regressions 由 coordinator 与 worker 按声明范围验证；Issues #979/#1048 仍保留为更广泛 live acceptance。 |
| T7a/T7b | T7a journal 68 tests、runtime 68 tests PASS；同一完整 two-page/four-writer fixture 为 18 → 15 HTTP calls，输出与完整 history 等价；T7b checkpoint design 70 scope tests PASS，未实现新协议或迁移。 |
| T8a/T8b/T8c | T8a coordinator independent 191 tests；T8b runtime 77 + outbox 28 + self-test-report 80 = 185 tests，worker docs 116 tests/44 pages/10 diagrams/20 outputs/44 routes；T8c 独立 claim/cancel 58 tests、report 78 tests PASS。完整 Linux advisory run `34401624578` 的 2159/4/17 failure 与旧版本地 2166/4/17/13 failure 均保留；修复后远端 Linux run `34404037938` 的 `ci_contract` job `102642953315` 为 2167 tests、497.904s、无 skip、PASS；final local CI contract discovery 为 2167 tests、13 skips、966.154s、OK，skip 分别受既有 environment/platform 条件限制。远端 report recovery 仍需独立验收。 |
| T9 | topology 51/51、scope 71/71、host policy 10/10、pinned actionlint PASS；旧 Documentation impact job `102613155971` exit 127 保留，新 Node22 job `102616656415` SUCCESS。最终 Linux `ci_contract` job `102616656429` 所属 run `34396230481`：2137 tests，529.014s，no skips，SUCCESS。 |
| T10/T11 | Canary entry 53、Canary planning 34；T11a control policy 80、T11b inventory probe 11、workflow 14、topology 46、host policy 9；pinned actionlint/docs checks PASS。两台已登记主机均执行了只读 inventory workflow（初始 runs [34392594667](https://github.com/endaye/lmdj/actions/runs/34392594667)/[34392614755](https://github.com/endaye/lmdj/actions/runs/34392614755)，更正 runs [34393629780](https://github.com/endaye/lmdj/actions/runs/34393629780)/[34393633850](https://github.com/endaye/lmdj/actions/runs/34393633850)）；没有执行重型产品 proof、provisioning 或配置写入。 |
| T12a | 默认 issue query 返回 117 条且无 `ci:storage` label；独立 storage audit 返回 8 条。T12a 已合入并作为本报告的前置 provenance。 |

本次集成的本地 `python3 -m unittest discover -s tests/build -p 'ci_*_test.py'`
在 T8c 合入后的 exact main `996a557357902dc447750dd94b32b568a9be36e0` 上完成：
`Ran 2167 tests in 966.154s`、`OK (skipped=13)`、退出码 0。结果记录在
`/tmp/lmdj-ci-program/t12-final-ci-discovery.log`；13 个 skip 来自既有 environment/platform
条件：本地未配置 pinned actionlint 的 YAML semantic test 属于 environment 限制，Linux
`/proc` 相关 canary guard 属于 platform 限制，不能将 13 个 skip 统称为 platform-only。
此前 pre-T8c 本地 CI contract discovery 为 2166 tests、4 failures、17 errors、13 skips、983.521s，
另有远端 advisory failure `34401624578` 的 2159/4/17/170.807s，以及修复后远端
Linux PASS `34404037938` 的 2167/497.904s/no skips；前者保留为失败证据，后者与
本地 final CI contract discovery 共同证明当前 head 的 CI contract discovery 通过，但两者都不构成
远端 report recovery 的连续验收。
`LMDJ_ACTIONLINT_COMPAT_QUEUE_ONLY` 的既有 queue compatibility ignore 只用于 actionlint，
不是新 bypass。

## 3. 成本与请求计数证据

T7a 的同 fixture 对照是可复现的单样本，不是生产平均值：page-local baseline
18 calls，事务内不可变 proof reuse 15 calls；两次均保留完整 history、provenance、
terminal cursor 与输出等价。该结果不能外推整体成本或声称固定比例节省。

T9 的历史本地 full discovery 为 2104 tests、12 skips、993.026s；这是上一阶段
树的本地参考，不替代当前远端结果，也不是“几分钟”承诺。当前 exact run
`34396230481` 的 `ci_contract` 为 2137 tests、529.014s、无 skip；两者执行环境、
tree 与 runner 不同，不能直接当作性能基线。

三次真实 report-only 观察如下。请求数严格区分 REST、GraphQL、artifact；elapsed
是实际步骤耗时；burst 不能替代长期平均。观察发生于 2026-09-09 UTC（报告日期为
2026-09-10 Asia/Shanghai），三次都不是 recovery PASS。

1. Run [34391959278](https://github.com/endaye/lmdj/actions/runs/34391959278)：scheduled 18:55:25Z，job start 18:55:29Z；report
   18:55:40–19:08:27，1726 requests（1714 REST、12 GraphQL、0 artifact），
   765753ms，1725 HTTP 2xx、1 HTTP 5xx，minimum remaining core 1491、GraphQL
   4895。18:59:55Z 出现 `journal-blocked` 503，remaining 4792，reset
   `1788983800`；最终 report unknown。Discovery 19:08:27–19:09:57，369
   requests（364 REST、5 GraphQL、0 artifact），89804ms，368 2xx、1 unavailable
   transport error，minimum remaining core 1240、GraphQL 4890，
   `admission_evidence=false`。整体于 19:10:07Z cancelled；日志为
   `/tmp/lmdj-ci-program/report-observation-34391959278.log`。该次没有可用
   backlog/oldest count。
2. Run [34394118563](https://github.com/endaye/lmdj/actions/runs/34394118563)：queue 1104s（18m24s），controller/report 各 860
   requests；report 274608ms，REST 855、GraphQL 4、artifact 1，响应 859 2xx、
   1 3xx，minimum remaining core 1735、GraphQL 4854。输出为 green step，但
   callback source `34394043658` 既非 active 也非 settled；`reports()` source
   guard 返回 ignored，且 output JSON 不存在、报告未上传 artifact。这是由源记录支持的推断，不能当作 report delivery
   recovery。捕获 state 为 43 results、0 explicit queued requests、1 active，
   `ci_contract` cancellation debt，oldest age unknown。摘要与日志为
   `/tmp/lmdj-ci-program/report-observation-34394118563-summary.json` 和同前缀 log。
3. Run [34395128138](https://github.com/endaye/lmdj/actions/runs/34395128138)：queue 1055s（17m35s），report 3069 requests（3049 REST、
   20 GraphQL、0 artifact），882667ms，3069 2xx；步骤实际 exit 1，unknown
   report errors。Discovery 71 requests（69 REST、2 GraphQL、0 artifact），
   15245ms，57 2xx、14 HTTP 4xx，实际 exit 1，blocked；没有 artifact。workflow
   最终 cancelled；API step 的 continue-on-error projections 显示 success，
   不能覆盖日志中的 exit 1。4xx subtype/root cause、backlog 和 oldest age
   均不可得，不能推断 quota 或权限原因。证据在 `/tmp/lmdj-ci-program/
   report-observation-34395128138-summary.json` 与同前缀 log。

因此，report/discovery 的外部 live acceptance gap 仍是：在 source-bound bounded
observations 中连续三次取得真实已认证来源、report 与 discovery 的可核验终态，
同时记录 backlog size/oldest age、HTTP 请求/elapsed/queue 及 workload denominator，
并证明失败债务得以按规则处理。green skipped DAG、continue-on-error 的绿投影、
controller 成功或 callback artifact 存在都不满足该条件。

## 4. 主机 inventory 与能力限制

T11 inventory 的两主机 provenance 与限制见 [PR #1137](https://github.com/endaye/lmdj/pull/1137) 与
[PR #1138](https://github.com/endaye/lmdj/pull/1138)；本地 inventory summary/log 仅作为可选收据。

- Netcup：16 cores、62 GiB memory、1.9T workspace free、Ubuntu 24.04.4、
  kernel 6.8.0-137-generic；Contabo：8 cores、23 GiB、237G free、同 distro、
  kernel 6.8.0-138-generic。
- 两台均报告 8 项 native tools（Clang/LLVM 22.1.8、ccache 4.9.1、CMake 3.28.3、
  Ninja 1.11.1、Python 3.12.3、git-lfs 3.4.1 等）。工具存在不等于 lane readiness。
- T11a 的 control workflows 可在两台已登记的 `ci-general` 主机运行；产品
  `ci-core`/`ci-web-heavy` 角色与控制面分离。T11b/T11d 的同 revision 只读
  probe 均成功，但 workflow SHA、config digest 和 git revision 匹配也不构成
  当前 runner execution 或 TSan readiness。
- 源 workflow 只记录了 `mmap_rnd_bits` 需要 root 权限的预期限制；当前权限、值和
  repository pin 28 均未被 live 证明，不能把 source expectation 当作现场状态。两台 kernel config 缺少
  `CONFIG_PARAVIRT_TIME_ACCOUNTING` 与 `CONFIG_IRQ_TIME_ACCOUNTING`，采到的
  5 秒 irq/softirq/steal delta 是 Netcup 0/3/1、Contabo 0/13/0，不能证明主机
  空闲或性能可接受。
- 产品 proof/TSan rerun、runner provisioning 和配置写入均未执行；控制面只读 inventory
  dispatch 已由两台已登记主机完成；
  下一步必须由协调器按授权进行，并保留 runner name、queue/execute/lock/wall
  clock、实际 workload denominator 和终态。

## 5. Issue hygiene 与 per-issue proof recommendation

T12a 已把工作查询默认限定为非 `ci:storage` Issue；明确 storage audit 时才使用
正向 label 查询。当前 smoke 结果为 actionable 117、storage audit 8，默认结果中
没有 storage label。State journal 的不可变正文不是人类 todo，不用于批量关闭或
重写报告 bucket；协调器保留 Issue mutation authority。

建议逐 Issue 取证如下，均不是本报告的状态变更：

| Issue | 当前状态 | 后续所需证明 |
| ---: | --- | --- |
| #666 | OPEN / REOPENED | 保留最新 host-load `callback_overruns` 失败；先做 source-bounded causal experiment，再以同 workload/CPU accounting 的结果解释成因。三次安静 tick 不能替代成因证据。 |
| #782 | OPEN | 独立 TSan data-race reproduction、精确 runtime/host 条件与修复后的完整 stress evidence；不能由一般绿色 suite 推断。 |
| #939 | OPEN | 每个 review backend 的真实 runtime category、request/elapsed/attempt 与 provider recovery 证据；本计划的 fallback/placeholder 规则不等于 backend diagnosis。 |
| #714 | OPEN | clean-thread retirement 的独立 bounded implementation、review evidence、删除/编辑保护和回归测试。 |
| #914 | OPEN | 继续发现全部 executable tests 到真实 runner invocation 的覆盖，补足 T4 未覆盖的 broader runner discovery。 |
| #979 | OPEN | quota reset、授权错误、未知写入和 later health recovery 的真实 source-bound observations；保留 503、unknown 与 unavailable。 |
| #1048 | OPEN | report progress 在产品批次运行期间的真实完整链路；T7a 的 18→15 fixture 只是成本/等价性证据。 |
| #1089 | OPEN | 汇总本报告中已实现与未完成项，由协调器在所有独立 acceptance 条件具备后决定 umbrella 状态。 |
| #1056/#1062/#1078 | CLOSED / COMPLETED | 各自实现与 review 证据已在 merged inventory 中，不能外推为 umbrella 或 live recovery 完成。 |
| P1.4 | pending genuine publication | 需要另一次明确 release authorization、exact candidate、protected publication 与 post-publication evidence；本报告不启动它。 |

机器恢复的新增 managed bucket 只有同时满足 authenticated causal/policy identity、
required suite/dependency coverage、same-policy selected PASS、无 verification debt、
成功 comment receipt 与 close PATCH receipt，才可按恢复协议处理。历史、人工编辑、
candidate/node、独立缺陷和未确认写入仍由人工分诊；报告运行本身不改变这些状态。

## 6. 实现与延期边界

### 本轮已实现

- PR advisory 采用确定性 selected `ci_contract`/`docs_static`，不新增 required
  check，不执行 fork 内容，不展开完整 Product DAG。
- current-head review、owner takeover/waiver、body lint 与 GitHub 实际
  `closingIssuesReferences` 核对成为 shipping procedure；不把工具或 label 当作
  独立 review 或 merge 授权。
- admission/queue/phase gate 退役；自动 Canary Planning 保持 manual-only；
  report outbox、quota/debt、transaction-local immutable proof、shared-event
  aggregation 和 managed-bucket recovery 按各自 source/receipt 条件运行。
- `ci:storage` 默认从 actionable work query 排除；storage audit 保持显式可用。
- 两台 host 的角色、inventory、sanitizer observation 和 capability limits 进入
  当前 guidance，但不声称 live readiness。

### 明确延期

- T7b 的 durable journal checkpoint 是 design-only；没有协议实现、迁移或 journal
  reset。
- 没有新增或恢复每日 product test、自动 Canary、release/deploy/channel 流程，
  也没有为证明成本而增加 hosted spend。
- 三次 report-only source-bound success、complete report/discovery backlog recovery、
  TSan race root cause、backend diagnosis、clean-thread retirement、broader runner
  discovery 和 genuine publication 均等待各自独立 Task/授权/证据。

## Version Management

Version impact: none. 本报告和当前文档只记录 CI/治理验收；没有 Product Build、
Core Module、Provider、Contract、release tag、deployment 或 Channel identity 变更。

## Documentation impact

Documentation impact: required. 影响 current governance 与 Architecture Portal 的
testing/proof 页面；affected route 为 `/operations/testing-and-proof/`。
未生成或修改任何 frozen snapshot。

## Evidence index

- Approved scope and task ledger: [`docs/plans/2026-09-10-lmdj-ci-reliability-and-cost.md`](../plans/2026-09-10-lmdj-ci-reliability-and-cost.md)；实现 provenance 由 [PR #1098](https://github.com/endaye/lmdj/pull/1098)、[PR #1128](https://github.com/endaye/lmdj/pull/1128)、[PR #1123](https://github.com/endaye/lmdj/pull/1123)、[PR #1133](https://github.com/endaye/lmdj/pull/1133)、[PR #1135](https://github.com/endaye/lmdj/pull/1135)、[PR #1136](https://github.com/endaye/lmdj/pull/1136)、[PR #1137](https://github.com/endaye/lmdj/pull/1137)、[PR #1138](https://github.com/endaye/lmdj/pull/1138)、[PR #1139](https://github.com/endaye/lmdj/pull/1139)、[PR #1140](https://github.com/endaye/lmdj/pull/1140)、[PR #1144](https://github.com/endaye/lmdj/pull/1144) 及表格所列其他 PR 提供。
- T7a fixture: [PR #1133](https://github.com/endaye/lmdj/pull/1133)；T9 exact live contract: [PR #1139](https://github.com/endaye/lmdj/pull/1139)。
- Report observations: [run 34391959278](https://github.com/endaye/lmdj/actions/runs/34391959278)、[run 34394118563](https://github.com/endaye/lmdj/actions/runs/34394118563)、[run 34395128138](https://github.com/endaye/lmdj/actions/runs/34395128138)；临时日志仅作为本地可选收据。
- CI contract discovery advisory provenance: [run 34404037938](https://github.com/endaye/lmdj/actions/runs/34404037938)，`ci_contract` job [102642953315](https://github.com/endaye/lmdj/actions/runs/34404037938/job/102642953315)，2167 tests、497.904s、无 skip、PASS；此前失败 [run 34401624578](https://github.com/endaye/lmdj/actions/runs/34401624578) 保留。
- Host inventory: [PR #1137](https://github.com/endaye/lmdj/pull/1137) 与 [PR #1138](https://github.com/endaye/lmdj/pull/1138)；主机现场日志仅作为本地可选收据。
- T12 issue-list smoke: [PR #1123](https://github.com/endaye/lmdj/pull/1123)；本地 JSONL 仅作为可选收据。
