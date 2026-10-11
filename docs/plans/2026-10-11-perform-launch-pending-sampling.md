# 当前 Task：PR2010 main-first 三父源码集成

本节是此文件唯一当前 Task 声明；后面的完整保留原文全部是历史，原文中的
“当前”、139 路径、134 inherited upstream、e220、Build89、双父路线和旧窗口均只指
旧候选。历史失败、UNKNOWN 和 UNRUN 不被新 Task 覆盖或改写。

## 当前前提、范围与父节点

本前缀记录Root在2026-10-11T09:16:40Z批准的epoch1 source/light刷新；最终运行结果
必须来自本epoch新外部日志，不从下方历史或epoch0继承PASS。此前own epoch0未提交候选
HEAD968 / stagedTree `fb1304b2deaf0c90a2384c3423ccb155bdee774a`，两计划7883-byte
prefix、完整raw index/HEAD/ORIG_HEAD/MERGE_HEAD/status/stages/fullpatch/wholeplans
已封存在own `.local/pr2010-main-first-source/epoch0-retained/`。Root已完整认证epoch0
40900-byte xz checkpoint `f3c54c020822c4d700a4497a6a75d703b1517455989227db4c0781cc560c4ad1`，
其Node、77 scope、15 pitfall的实际PASS仅属于当时968 source/light，不是Portal/runtime接受。
本次仅在own新WT用supported merge --abort、ordinary --ff-only推进67，再重建builtin
ours三父准备；绝不对旧FAILED139 WT或foreign worktree/ref做恢复、清理或控制。

- Task `task_037161940ca3` / Dispatch `ctx_0cf7b127a3eb`；普通 UID501，独立
  `fix/perform-oracle-main-final-integration` 工作树。Root 已 prospectively 将本次选定基线刷新为 exact main
  `67d66bf20d7701d339ab2554ac2090bae78ec483`，tree `83ee0d02b16b727e9cd8c843f2b2b2da91236a6c`。
- fresh read-only GitHub/remote 验证实际 main 已从968推进到选定67；PR2010仍为 OPEN、non-draft，head
  `b62f810eb89ae9076d6937741c65446e91289303`，本次fresh查询 mergeable/mergeStateStatus 均为 UNKNOWN，
  不当作无冲突；较早 CONFLICTING 是历史。Root 保留后续非强制 FF push、PR、
  current-head 独立评审、findings/conversations、保护、精确 committed batch evidence
  和 shipping 权限；本 dispatch 不 push、不发 PR、不 merge main。
- 实际 builtin `git merge --no-commit --no-ff --strategy=ours`，独立参数依次为
  `b62f810eb89ae9076d6937741c65446e91289303`、`756bd99a830373490aff42dff1e76c421119bf7d`。编辑前真实 HEAD 为 selected-main67，
  `MERGE_HEAD` 有序为 `[b62,756]`，初始索引 tree 与 selected-main67 完全相等。
  最终一个 Conventional integration commit 必须有真实有序 parents `[67,b62,756]`；
  b62 和 756 互不为祖先且不冗余，不使用 `-Xours`、commit-tree 或替代 HEAD。
- 原 e220 到 selected-main67 的五个输入路径逐一核对，全部 mode/blob 不变。selected-main67 已
  保留后续 F1 native、Build90 身份、两代 snapshot/witness、Catalog、schema、Assembly
  与其他后继源码。本 Task 从 main 起步，只覆盖下面五文件；所有其他路径的
  mode/type/blob 必须与 selected-main67 完全相等。旧139/134清单只是历史，不是新 diff。

唯一完整声明为 first-parent **3M2A**，五个模式均为 `100644`：

1. M `apps/docs-site/docs/hosts/creator-interactions.mdx`
2. M `apps/docs-site/docs/hosts/creator-web.mdx`
3. A `docs/plans/2026-10-11-perform-launch-pending-sampling.md`
4. A `docs/plans/2026-10-11-perform-replay-neutral-fx-monitor-oracle.md`
5. M `tests/platform/web/creator/creator_web_perform.spec.mjs`

只有两份计划可相对 reviewed756变化。三个非计划文件使用完整756逐字节源码：
spec blob `e4e17c4e7665c6b162d8511460b4d5a6f08f234a`，96,493 bytes，SHA-256
`bbdd31930b9b34d21763a814672aa70214afb539ab3800a79cdb83d6b09d4179`；
interactions blob `bceb9e251e3e104bbd0b2ea1c2bf161d1978be69`；web blob
`77062e54eada9bea5e5a40245b02f284c0e7bfee`。未引入 PR2011 quick-profile、
PR2001 App/history 或 K1 私有映射变更。PR2008已merge，其下面四条是选定main67的
完整继承输入，不是本Task额外authoring或unmerged donor：

- `packages/application-facade/include/lmdj/facade/performance_ports.hpp`
- `packages/application-facade/src/performance_engine_adapter.cpp`
- `packages/web-runtime-platform/test/performance_bridge_test.cpp`
- `tests/core/facade/performance_engine_adapter_test.cpp`

四条mode/type/blob与选定67完全一致；后续Performance producer/consumer/native/Web
full129/eight前提必须由Root按实际新候选验证，五文件无overlap不代替这些证明。

## 最小检查与完整语义边界

| 必做检查 | 捕获的缺陷 | 当前阶段 |
| --- | --- | --- |
| inherited Node syntax | 完整 Perform spec 的 JavaScript 语法错误 | 本epoch必须重新运行，实际退出/工具身份留在own external receipts；不借epoch0 PASS |
| 既有 ci_change_scope_test.py | 新增计划未入已声明路径所有权或 scope policy 漂移 | 本epoch最终暂存后重新运行，实际数量/child.wait/outer以own external receipts为准 |
| 既有 ci_pitfall_ledger_test.py | selected-main pitfall 格式/退出契约失效 | 本epoch重新运行，实际数量/child.wait/outer以own external receipts为准 |
| staged whitespace、五文件/mode/whole-main/原字节守卫 | 额外路径、main后继丢失、非计划源码替换或历史段落改写 | 本epoch要求仅3M2A、outside-five差异0，实际守卫单独留档 |
| 原完整 bash scripts/docs-site.sh check | current docs、metadata、图、facts、原snapshot来源、type/build/routes/links不一致 | UNRUN；只在 Root 新 prospective Portal 窗口后执行，必须完整PASS才提交 |

这是源码集成 Task，不新增产品 gate；最低层检查不缩减后续验收。完整 Performspec
保持756的13个字面量声明及1个参数化声明、严格断言、标签、预算、所有原旅程腿和11个既有能力skip。
MASTER=37、三个命名 neutral FX=500、HOLD=false、Pattern2 idle 独立预期保留；
native.send 的 receiver/参数/requestID/result/rejection、clock/status/loss诊断转发不变。
原选择→queue→withdraw→requeue→apply→applied boundary→Stop→Truth idle→noRecord
完整保留；原300000ms整条、6000ms尾段、30000ms等待，以及恰好两处5000ms/50ms
pending check、missing/multiple返回null均不改。原诊断在post-assertion一次写入
testInfo.outputPath JSON并attach PATH；可读实际文件及body/request-result回读为后续UNRUN，
源码存在不等于运行证明。未使用 ProbePolling donor。

## 保留失败与当前验证债

旧 Task `task_48caf37d6f4a` / `ctx_523e7111edfd` 为 FAILED、无提交：原工作树
保留 HEAD b62、MERGE_HEAD756、139路径/84A55M，stageTree
`1f2b2d2aa9beab20fb69b7823635579c945c3e0c`。实际两计划的 working/stage/archive
bytes及旧report/receipt/raw输出已在新Task只读认证，完整旧段落逐字保留在下方。
未 abort/reset/stash/checkout/write-tree 旧工作树或改写其cache/index/输出。

旧正式 Portal 在08:11:16.055948–08:11:39.087271Z为真实child.wait1/outer1；
176/176 Node PASS后 `snapshot introducing commit cannot be resolved: snapshot metadata
path is absent at HEAD`。typecheck/build/routes UNRUN；旧raw15918bytes/SHA-256
`be20656240d1c42e27f59b26fcf2f0594618aad4ca742c44603b21788db399af`保留。
旧exact-run raw-index equality仍UNKNOWN，不因新守卫改写。新 Task 没有旧窗口 entitlement
或 Portal PASS；selected-main67已有实际Build90 metadata及原introducing历史，维持原单父introducing
validator、snapshots、witnesses、routes、facts，不用S0例外/HEAD覆盖/witness再生。

新准备阶段 Portal dependency 未就绪（own apps/docs-site/node_modules不存在）；
缺依赖、重资源或新增tracked path只向Root报告prospective需要，不自行install/copy/symlink。
目前本Task未运行compiler/configure/ctest/native/Web/browser/full/Portal；P0/S6 MBP资源
仅由Root协调。Root在2026-10-11T09:24:06Z已给出本Task新的prospective执行窗口：
新的source/light与no-heavy census通过后，可用独立own cache/TMP运行一次官方locked
install；其实际成功与输入守卫通过后才可进入一次原完整Portal，均不借旧窗口。
本前缀的UNRUN仅记录这次源码准备时的实际执行状态；后续真实退出/完整日志另行保留。
任何失败gate都停在commit前，保留实际退出、全raw日志与新的结束census/输入守卫。

新 committed HEAD 的own native/Web preparation、canonical Creator full129/eight suites
（原workers/budgets）和可读retained diagnostics均UNRUN，需后续独立Task-owned output/
dependency范围及P0handoff。aba旧118P0F11S仅为aba89，0ff旧117P1F11S/UNKNOWN保留，
exact756 full及新final90 full均UNRUN；旧89 JS/WASM/native/CLI/manifest不作为90 proof。
Root较早的exact-committed-head batch-only证据义务继续；轻检查不产生pass key或risk接受。
PR2001后续必须自行完成新integrated App/history full129/eight，不能借本Task证据。
本Task不结清整个Goal、V1、D03/D04/M1/K1/BPM、物理/听感、release或deploy债。

## Version Management

Version impact: none — 此五文件源码集成只保留已实现的内部检查与当前手册，不改
API/ABI、Contract、product/Facade/SDK/App、Assembly/lock/manifest或任何身份，不分配新版本。
选定实际输入Product Build `2.0.90.0` 由selected-main67的 `products/lmdj/version.json`读取，
是继承身份，不是本Task allocation，也不把历史89产物重新标为90。

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-interactions/ /hosts/creator-web/
Reason: 同一Task完整继承reviewed756的两页MASTER监听保持和Stop Replay neutral事实。
身份继续由实际active manifests派生，原snapshot/provenance/图/witness保持selected-main67字节。

## 完整保留的失败Task与更早计划历史

下面从旧retained stage/archive读取的整个原文件保持逐字节顺序；其中所有旧“当前”及
验收/授权声明只解释各自历史候选，不能用于本Task新窗口或新HEAD的通过结论。

---

# Perform Launch 短暂排队状态的采样

## 2026-10-11 PR2010 双父最终验收整合 Task（当前）

本节是一个新的 139 路径 source integration Task；以下 S4 收敛及原 968／b62
计划的“当前”、完成和待办均保留为对应旧候选的历史，不改写旧证明。
Task `task_48caf37d6f4a`／dispatch `ctx_523e7111edfd` 仅授权此隔离工作树的
源码整合、声明轻量检查、获 Root prospective admission 后的 Portal precommit
检查和一个本地 Conventional Commit；push／PR 更新／review adoption／merge
由 Root 在后续 Task 处理，不涉及 release、deployment 或 cleanup。

### 来源、两个父节点与整个树

- 第一父节点固定为 PR2010 的实际 OPEN／non-draft head
  `b62f810eb89ae9076d6937741c65446e91289303`；实时状态 DIRTY／CONFLICTING。
  PR REST base `deb95de722b845d708371e90bcac138ae5e25e01` 是另一个投影，
  不冒充当前 remote main。
- 第二父节点固定为真实 reviewed author chain 的
  `756bd99a830373490aff42dff1e76c421119bf7d`，tree
  `b32082d1cd142f3ef87d5d4590d7c375d3d3a319`；其父为
  `aba649075833312afc4c5f8c99669928023e899e`，再继承 0ff9 与实际 merged S4
  `e220c98ca1b0f4a3c08646bfeb328ffa186a263d`。
- b62 不是 756 的祖先；实际 merge-base 是
  `46045119801d9f03707aaa6f8ed50fbd651e8e95`。在原 Root-owned 隔离工作树创建
  `fix/perform-oracle-final-integration`，从 exact b62 开始，执行实际独立 argv
  `git merge --no-commit --no-ff 756bd99a830373490aff42dff1e76c421119bf7d`。
  不复制／重建旧实现提交，不直接 push756，不 force-update 原 PR。
- 原命名 `feat/perform-oracle-main-convergence` ref 保留在 exact756，所有旧
  ignored evidence 保持；只有本 Task 新 fix 分支可推进。实际冲突仅为两份计划
  和 spec；五个拥有路径全部恢复到完整756 bytes 后，计划更新前的 index tree
  实际等于上述756 tree。
- 最终 whole tree 必须精确等于756，只有这两份既有计划允许追加新的 source／
  证据事实。134 个 inherited upstream 路径的 mode／type／blob 逐项等于 e220；
  不更新到新 main、不纳入私有 K1／P0／history／BPM 或开放 PR2011 的
  quick-profile／production filter。PR2008 adapter／ports 和 PR2001 App／history
  也不是输入。K1 的同 spec／Portal 归属保持协调 hold，不作为 donor。
- 当前 remote main 只读刷新为
  `96802c0f8764d04cbf3d3c913e82292a01284ac9`，tree
  `12447580f3cb82cb1df9077560cc12e8dbffe72a`；e220→a61／968 没有五拥有路径
  交集，治理文件逐字相同。当前 main Build90／F1 和选定 inherited Build89
  有不同产品输入，本 Task 不把无关 main movement 变成 rebase 或完整 gate。

### 一个 Task 的完整139路径声明

第一父 b62→reviewed756 的真实 diff 为 139 路径：84 added／55 modified；
其中五个 owning acceptance 路径如下，其余134为已合并 e220 的精确保留输入。
完整134路径清单见 Launch sampling 计划下方的 pinned inventory；两份计划共享
同一个139路径声明，不能只暂存五文件或把 inherited 路径当作未声明变化。

1. `tests/platform/web/creator/creator_web_perform.spec.mjs`
2. `docs/plans/2026-10-11-perform-launch-pending-sampling.md`
3. `docs/plans/2026-10-11-perform-replay-neutral-fx-monitor-oracle.md`
4. `apps/docs-site/docs/hosts/creator-interactions.mdx`
5. `apps/docs-site/docs/hosts/creator-web.mdx`

Spec 必须为 blob `e4e17c4e7665c6b162d8511460b4d5a6f08f234a`，96493 bytes，
SHA256 `bbdd31930b9b34d21763a814672aa70214afb539ab3800a79cdb83d6b09d4179`；
两页 Portal 分别为 `bceb9e251e3e104bbd0b2ea1c2bf161d1978be69` 和
`77062e54eada9bea5e5a40245b02f284c0e7bfee`，只有两份计划有新 final blob。

保留全部13 Perform declarations、每条原完整旅程和远端断言：早期唯一一次
MASTER=37 接受读回，Stop Replay 后命名 neutral FX=500、MASTER=37、HOLD=false、
Pattern2 idle；300000 整体／6000 录制尾段／30000 等待保持。Launch 两次 pending
依旧各5000 ms／50 ms；literal data-launch 的 single-element evaluateAll，
missing／multiple→null；queue／withdraw／requeue／applied／Stop／Truth-idle／
no-Record 所有腿保持。native.send receiver／args／response／rejection identity
及真实 command IDs、clock、status、loss 诊断保持，没有新的 polling probe。
756 的同一次 post-assertion JSON.stringify(await page.evaluate(...)) 快照使用
writeFile 写到 testInfo.outputPath，再 attach PATH，不恢复 discarded body 附件。
existing capability skips 不转成 waiver，不扩大 timeout 或控制预算。

### 最低层检查、原缺陷与 prospective Portal 边界

- `node --check tests/platform/web/creator/creator_web_perform.spec.mjs`：检查精确
  最终 spec 的 Node26 语法；不执行浏览器或增加测试。
- `python3 tests/build/ci_change_scope_test.py`：运行当前完整 existing suite，
  检查已暂存84新增路径的 owning policy 和 scope；不硬编码历史77的数量。
- `python3 tests/build/ci_pitfall_ledger_test.py`：运行当前完整 existing ledger
  suite，检查保留的 ledger contract；不硬编码历史15的数量。
- 静态检查完整 staged139 集合、84／55 status、134 个 e220 mode/type/blob、
  五 owning net diff、whole-tree 与756只差两份计划、13 declarations 和整个
  spec 字节相等；捕捉漏带 upstream、丢原旅程、错父节点或隐藏路径。
  检查非 main 新fix分支、git diff --cached --check、committed first-parent清单
  和最终 clean status。没有新 gate 或独立发明的 accepted-risk 证据。
- `bash scripts/docs-site.sh check` 是本 source 的 REQUIRED precommit 检查：
  两条 owning Host Portal 路由和当前文档事实需完整检查，不复用 b62／e220／
  aba／capture 的旧收据。先向 Root 提供 fresh UID／磁盘／bounded process census、
  tools／cache／源码状态，等待 prospective admission；peer P0 的重负载资源不因
  历史 ps 或源码完成而自动释放。未获批前，不运行 Portal／native／browser／
  Emscripten／full proof，也不创建 unverified 临时提交。

本节 source 冻结前的轻量检查和 Portal 实际结果写在下面及新 ignored
`.local/pr2010-dual-parent-integration/` 原始收据。所有 precommit检查通过后，
创建一个本地 `test(creator): integrate reviewed Perform acceptance candidate`
双父 Conventional Commit；完整 Creator 必须由 Root 在另一个 prospective
admitted committed-head Task 上运行，不能本次顺带执行或复用新head旧证明。

### 负面历史与尚未运行的验收

- 原0ff9b591db08161c327a3bec6a37396c619db89c full129／8：117PASS／1FAIL／
  11 configured SKIP，actual child.wait1／outer1；Launch 第二次 pending 的
  原失败与 causal UNKNOWN 继续保留，不因后来的 pass 清除。
- aba649075833312afc4c5f8c99669928023e899e 在 inherited Build89 的官方
  full129／8：118PASS／0FAIL／11 existing capability SKIP，actual child.wait0／
  outer0，仅证明 aba 的 configured run。passing line reporter 未留下 body JSON；
  native 第二次 envelope／ACK／activation／后续inspect及capture loss仍 UNKNOWN。
- exact756 的 PATH capture-retention runtime／full proof为 UNRUN；本双父整合
  commit 的完整129／8及实际 retained JSON parse也为 UNRUN，必须取得新证据。
  旧0ff9与aba的 raw logs／traces／error-context／inputs／reports一律保持。
- 新 full若失败，先保存原始日志、真实 child.wait／outerexit、未达腿和实际
  path JSON，不 retry-to-green，不把历史configured skip借作新 waiver。
  若通过，也不说明 UNKNOWN 产品原因已修复，不等于 current-main Build90 proof。
- 原968／b62／S4的历史数据保留在下方。物理设备、听感、whole-main／Goal、
  V1／API／ABI／版本验收债仍未由本 source Task 结清；不生产 local-ci PASS key。

### Version Management（此双父整合 Task）

Version impact: none — 没有 NEW Product Build／Module／ABI／Contract／Assembly／
snapshot 分配。第一父diff中的 products manifests／Assembly和Build89 snapshot
属于已经 merged e220 的134 inherited输入，按原blob保留；不能声称第一父没有
manifest差异，也不能把 inherited89或旧89dist描述为当前Build90/F1验收。

### Documentation Impact（此双父整合 Task）

Documentation impact: required
Affected portal pages: `/hosts/creator-interactions/`、`/hosts/creator-web/`。
保留 reviewed756 的两个完整 Host Portal 页面及其 S4 SEQ SNAP／MASTER事实，
本 Task 的 required 不被旧 sampling-only／capture-only 的 none 替代。身份由
保留的 active manifests 派生，不手填／生成新的 Product snapshot。

### 本 Task 的 Portal 前源码冻结记录

截至两份计划本次 Portal 前冻结：Node26 syntax actual exit0；完整当前 ownership
suite实际77／77 exit0，完整当前 pitfall suite实际15／15 exit0；cached／working
whitespace检查exit0。完整 staged139／84 added／55 modified、134 e220原blob／mode、
13 declarations、整份spec756字节相等以及whole-tree只差两份计划均已核对。

Root在 `relay_5912997a3721`（2026-10-11T08:04:40Z）主动给出本Task exactly-one
prospective Portal precommit admission：其已实际收到P0 source-only hold与零heavy
收据；本worker仍须刷新实际MBP UID501／资源／source guard后才启动。
本节冻结时 Portal实际尚为UNRUN。后续真实Portal child.wait／outerexit、rawlog、
时刻／counts／hash／source-input守卫落在新ignored证据目录；不通过后改写被测
计划来制造已通过的源码身份。只有全部Required precommit checks真正通过后
才能创建上述唯一双父本地commit。源码冻结和commit均不产生完整Creator PASS。
committed-head Creator full129／8／runtime JSON retention：UNRUN（后续独立 Task）。

### Pinned 134 inherited upstream 路径（全部 mode/type/blob 等于 e220）

以下状态是 exact b62→756 first-parent delta；五个 owning 路径已在上方列出。

```text
A	.agents/pitfalls/shared-temporary-staging-ownership.md
A	.agents/pitfalls/skipped-job-name-retains-expression.md
A	.agents/pitfalls/subagent-timeout-is-not-termination.md
M	.agents/skills/issue-done/SKILL.md
M	.github/pull_request_template.md
M	.github/workflows/pr-contract.yml
M	AGENTS.md
M	CLAUDE.md
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/application-facade.html
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/application-facade.svg
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/audio-runtime.html
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/audio-runtime.svg
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/authoring-domain.html
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/authoring-domain.svg
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/foundation.html
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/foundation.svg
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/lmdj-core.html
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/lmdj-core.svg
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/lmdj-product.html
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/lmdj-product.svg
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/project-cooker.html
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/project-cooker.svg
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/project-io.html
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/project-io.svg
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/provider-sdk.html
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/provider-sdk.svg
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/web-runtime-platform.html
A	apps/architecture-portal/static/versions/2.0.89.0/diagrams/web-runtime-platform.svg
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/assembly/lmdj.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/contracts/artifact-audio.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/contracts/assembly.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/contracts/capability.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/contracts/cardputer-transfer.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/contracts/error-module-version.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/contracts/overview.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/contracts/project-bundle.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/contracts/project.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/contracts/runtime-snapshot.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/contracts/slice-points.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/contracts/soundset-catalog.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/contracts/soundset.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/core/modules/application-facade.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/core/modules/audio-runtime.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/core/modules/authoring-domain.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/core/modules/foundation.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/core/modules/project-cooker.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/core/modules/project-io.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/core/modules/provider-sdk.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/core/modules/web-runtime-platform.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/core/overview.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/history/legacy-patch-architecture.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/hosts/cardputer-host.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/hosts/core-cli.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/hosts/core-mcp.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/hosts/creator-interactions.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/hosts/creator-web.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/hosts/native-host.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/hosts/overview.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/hosts/web-runtime.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/operations/creator-changelog.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/operations/documentation-governance.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/operations/runtime-changelog.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/operations/testing-and-proof.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/operations/version-and-release.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/overview/index.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/platform/input.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/platform/native-audio.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/platform/storage.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/platform/web-runtime.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/product/capability-map.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/product/positioning.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/product/workflows.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/providers/local-proof-stem.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/providers/local-proof.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/providers/local-sample-slice.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/providers/overview.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/releases/1.0.61.0.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/releases/1.0.66.0.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/releases/2.0.87.0.mdx
A	apps/architecture-portal/versioned_docs/version-2.0.89.0/releases/index.mdx
A	apps/architecture-portal/versioned_metadata/version-2.0.89.0.json
A	apps/architecture-portal/versioned_sidebars/version-2.0.89.0-sidebars.json
M	apps/architecture-portal/versions.json
M	apps/cardputer-host/CMakeLists.txt
M	apps/creator-web/src/app.tsx
M	apps/creator-web/src/components/sequence_touch_workspace.tsx
M	apps/creator-web/src/runtime/pattern_transport_actions.ts
A	apps/creator-web/src/state/seq_snap_preference.ts
M	apps/creator-web/src/styles.css
M	apps/creator-web/test/pad_colour.test.tsx
M	apps/creator-web/test/pattern_transport_actions.test.ts
A	apps/creator-web/test/seq_snap_preference.test.ts
M	apps/creator-web/test/sequence_surface.test.tsx
M	apps/creator-web/test/workspace_shell.test.tsx
M	apps/docs-site/diagrams/audio-runtime.architecture.json
M	apps/docs-site/docs/assembly/lmdj.mdx
M	apps/docs-site/docs/contracts/project.mdx
M	apps/docs-site/docs/core/modules/audio-runtime.mdx
M	apps/docs-site/docs/operations/testing-and-proof.mdx
M	apps/docs-site/docs/platform/web-runtime.mdx
M	apps/docs-site/static/diagrams/audio-runtime.html
M	apps/docs-site/static/diagrams/audio-runtime.svg
M	contracts/project/lmdj.project.v5.schema.json
M	docs/governance/git-workflow.md
M	docs/plans/2026-10-09-creator-desktop-final-followup.md
M	docs/plans/2026-10-10-pattern-switch-and-count-in.md
A	docs/plans/2026-10-11-lmdj-daily-ci-simplification.md
A	docs/plans/2026-10-11-lmdj-daily-verification-obligation.md
A	docs/plans/2026-10-11-project-v5-live-controls-cut.md
M	docs/quality/2026-10-09-creator-desktop-followup-acceptance.md
M	packages/audio-runtime/include/lmdj/audio/realtime_engine.hpp
M	packages/audio-runtime/src/realtime_engine.cpp
M	packages/web-runtime-platform/src/control_runtime.cpp
M	packages/web-runtime-platform/test/control_runtime_test.cpp
M	packages/web-runtime-platform/test/protocol.test.mjs
M	packages/web-runtime-platform/test/runtime_session.test.mjs
M	packages/web-runtime-platform/web/protocol.mjs
M	packages/web-runtime-platform/web/runtime_session.mjs
M	packages/web-runtime-platform/web/runtime_types.d.ts
M	products/lmdj/assembly.json
M	products/lmdj/assembly.lock.json
M	products/lmdj/generated/web-runtime-identity.json
M	products/lmdj/generated/web-runtime-identity.mjs
M	products/lmdj/src/cardputer_assembly.cpp
M	products/lmdj/src/compiled_assembly.cpp
M	products/lmdj/version.json
M	tests/build/ci_review_wait_test.py
M	tests/build/ci_workflow_topology_test.py
M	tests/build/version_test.py
M	tests/conformance/schema_contract_test.py
M	tests/core/audio/realtime_engine_test.cpp
A	tests/fixtures/contracts/project-v5-live-controls-invalid.json
A	tests/fixtures/contracts/project-v5-live-controls-valid.json
M	tests/platform/web/creator/creator_web_sequence.spec.mjs
```

## 保留的 S4 收敛与原 Task 历史

以下原文逐字保留；其“当前”、候选和检查状态属于旧候选，不覆盖上面的新Task。

## 2026-10-11 S4 main 收敛 Task（当前）

- fresh fetch 的实际 main 与本工作树起点均为
  `e220c98ca1b0f4a3c08646bfeb328ffa186a263d`；已包含 S4 Engine／Host／SDK／Portal，
  没有 cherry-pick 产品变更或回退 main。
- 只重命名本次新建分支为 `feat/perform-oracle-main-convergence`，无 main upstream。
  原 Root 工作树、两次提交及失败证据保持；此收敛形成一个新 Conventional Commit。
- read-only PR #2010 head 为 `b62f810eb89ae9076d6937741c65446e91289303`、OPEN、
  non-draft、CONFLICTING；原两个 Task 的完整五文件范围已核对。
  其他开放 PR 的完整文件列表已保存：#2011 与本 spec 重叠，但其 quick-profile
  修改不属于本 Task；#2001／#2008／#2014／#2017 当前列表无五文件交集。
- 当前 base 已有命名 Filter／Delay／Reverb=500、MASTER=42 的 S4 replay-neutral
  检查，原“所有 slider=500”缺陷已经交付修复，不重做产品实现。
  尚缺的是原 Root 更早的 MASTER=37 接受断言和两个 transient pending 回调；
  两页仍有 MASTER 未实现的旧句。这些剩余事实均在实际 e220 source 核对。

### 当前五文件范围与完整旅程

1. `apps/docs-site/docs/hosts/creator-interactions.mdx`
2. `apps/docs-site/docs/hosts/creator-web.mdx`
3. `docs/plans/2026-10-11-perform-launch-pending-sampling.md`
4. `docs/plans/2026-10-11-perform-replay-neutral-fx-monitor-oracle.md`
5. `tests/platform/web/creator/creator_web_perform.spec.mjs`

replay-stop 在 importActivateAndPerform 后、assignThenMovePattern／record／save／
replay 前只设置和回读一次 MASTER=37，使用既有 AUDIO_TRANSITION_TIMEOUT_MS
就绪预算；删除较晚的 42 设置。实际 Stop Replay 后独立断言三个命名 FX=500、
MASTER=37、HOLD=false 和 Launch Pattern 2 idle；完整录制／保存／回放／Stop
各腿、原 300000 ms／6000 ms／30000 ms 等预算保持。

原 Launch1014 的两个回调与 b62 逐字相同：existing accessible locator 的
nonblocking evaluateAll，恰好一个匹配元素才返回其 literal data-launch，
否则 null；50 ms intervals、各 5000 ms deadline。其完整选择／排队／撤回／
重排应用／Stop／三次真实收据／Truth 相等／no-record 各腿及原预算保持。
S4 新 SEQ SNAP 旅程、所有其他 poll 与断言保持；无新增 gate 或 broad test。

两页移除两个旧 MASTER 缺席句，独立陈述监听音量保持与 neutral replay；
保留当前 S4 SEQ SNAP 手册与后续 S3／S5／count-in／K2／M1 路线。
不改产品、Core、App、SDK、fixture、runner、worker、lock、manifest、policy、
timeout、selection 或任何其他 tracked 文件。

### 当前验证政策、冻结与证据边界

按实际 main 的 AGENTS／CLAUDE、issue-done §0 与 git-workflow 刷新前提。
普通合并需要 owning Task 风险与声明旅程，无 blanket full-lane gate；本 Goal
明确要求 complete Creator，因此本次完整检查仍是必做且在真正通过前未完成。
先经 Root 明确 heavy-window 回复才安装／构建／Portal／Browser；普通 UID501，
原 pinned EMSDK 6.0.5、Node26、locked Playwright。按 shared-temporary-staging-ownership
使用本 worktree 的 task-owned child TMPDIR／TMP／TEMP，不改变共享目录权限。

提交前运行 Node syntax、既有 ownership77／pitfall15、完整
`scripts/docs-site.sh check` 和 staged diff 检查；只暂存上述五文件，检查非 main
分支、完整 staged diff、commit 文件清单和 clean status。完整 Creator 必须随后在
该 clean committed HEAD 顺序运行官方 `scripts/creator-web.sh proof`：原八组、
当前完整 case inventory（含 S4）、原 workers／timeout／strict assertions 和所有腿。
保存 full raw log、实际 child.wait 与 wrapper exit、时刻、每组结果、所有失败
trace／error、source HEAD／tree／tracked status 与 installed-input 前后守卫。
先落盘原日志和真实退出，再计算辅助 SHA；不制造 local-ci PASS key。

候选冻结前已获 Root 的原问题 `relay_fb670b265101` 串行窗口回复；fresh boundary
`2026-10-11T04:22:36.955Z` 为 UID501／18,682,281,984 free bytes，没有活跃
native／Wasm／Playwright test runner；两个既有 headed cliDaemon 保持且不推断退出。
Creator／Web／Portal 分别从当前 lock 真正 npm ci，实际 exit0；六份 package／lock
source SHA 未变。Host Node26.7.0、Playwright1.62.1、既有 Chromium1234／WebKit2336
及 EMSDK6.0.5 实际核对，SDK verifier exit0；没有替代工具链或旧 dist／fixture。
完整 Portal `bash scripts/docs-site.sh check` 实际从 `2026-10-11T04:24:58.709Z`
至 `2026-10-11T04:25:38.864Z`，child.wait／outer exit0，生产构建与50条路由／
内部链接完成；原日志与退出收据保存在 `.local/perform-oracle-convergence/portal/`。
提交前再 fetch main 为 `43e347626406c43a028fc3b7b26e8e329f862c7f`，唯一变化为
Build89 snapshot witness，不与五文件相交；四份治理文件逐字相同。依 Root 明确
指示保留选定 e220 base，不把无冲突 main movement 变成 strict-update gate。

候选冻结时 complete proof 尚待 committed HEAD；本文件的提交不表示 Goal PASS。
同一提交之后的实际结果写入本 worktree ignored
`.local/perform-oracle-convergence/` 报告和 raw receipts，避免改变被测源码。
失败先保留并汇报，不扩大范围。Root 保留现有 PR2010 的 push／PR 更新／
current-head 独立评审／findings／conversation／保护与 guarded merge；worker
不发布、不采用 review、不 waive、不 cleanup，也不建重复 PR。

### 必须保留的历史输入（不是本候选 PASS）

- 原 `96871218d7d5ceadf168b9fef5decebf32c091f8` complete Creator：
  114PASS／2FAIL／11SKIP，exit1。
- 原 `b62f810eb89ae9076d6937741c65446e91289303` 官方八组 complete：
  112PASS／4FAIL／11SKIP，child.wait 与 wrapper exit1；
  `2026-10-11T02:07:26.966Z` 至 `2026-10-11T02:29:25.768Z`，whole logSHA
  `e55cad606ef1810bc5f54ad85907930be60b5d7d1e61cdbc94b17d19306e6c91`。
  Metronome120／Lifecycle463／Perform1632／Sequence768 为 FAIL；ENOSPC
  诊断错误可能掩盖 primary error，没有 PASS key。Root 日志位于
  `/Users/endaye/Projects/lmdj-followup-evidence/2026-10-11-perform-replay-monitor-oracle-implementation/committed-full-creator-b62f/`；
  本 worker 只从 dispatch 和 live PR 读取这些历史数据，未声称检查 Root 原日志。
- S4 `680a118` complete proof 118PASS／0FAIL／11SKIP 是历史产品／测试输入，
  不是本候选、integrated newmain 或 Build89 验收。
- 旧 EEF／native receipt-delay 原因仍 UNKNOWN；focused 结果不清 full debt。
  物理设备、听感、whole-main、V1 与版本验收债均不由本 Task 结清。

## Version Management（当前累计）

Version impact: none — 仅收敛内部观察／严格独立预期与已实现事实手册；
没有 API／ABI、Contract、Host 实现、Assembly／lock 或身份变更，不分配版本。

## Documentation Impact（当前累计）

Documentation impact: required
Affected portal pages: `/hosts/creator-interactions/`、`/hosts/creator-web/`。
两份计划共享此单一五文件收敛 Task 的累计声明；历史 sampling-only 的 none
不替代当前 required。身份仍由 active manifests 派生，不手填版本或生成 snapshot。

## 原 Task 计划历史（从 frozen b62 保留）

以下原文属于原 968／b62 的 Task 历史：其中“当前”、起点、分支、focused
结果、当时待办和交付顺序均指原候选。当前 source／验证政策／范围以上述
S4 收敛 Task 为准；不把旧身份或 proof 改写成新候选证据。

- 日期：2026-10-11
- 当前阶段：源码与原同名完整 focused GREEN 已完成；新 committed Creator 和当前 head 评审尚未执行。
- 实际起点：`96871218d7d5ceadf168b9fef5decebf32c091f8`，保留原 replay-neutral Task 提交。
- 刷新 integration base：`deb95de722b845d708371e90bcac138ae5e25e01`。
- 分支：已有隔离 `fix/perform-replay-monitor-oracle`，同 PR #2010 的独立第二 Task。

## 当前前提与声明文件

fresh fetch 后，main 与本工作树的原完整 Launch 用例逐字节相等，两处 pending
仍用默认 locator 采样。#2008 当前 `3043df09597356251324813be9e1f1fd8e517c5b`
仍 OPEN，只涉及 Performance adapter、时钟和对应录制测试；不能据此认定普通
Pattern switch 或本用例已修复。K1 仍拥有同一 spec 的键盘映射工作，owner 已
协调顺序；本 Task 不修改映射 hunk。

已完成的 committed 968 完整 Creator 实际为 114 passed、2 failed、11 skipped，
exit 1，没有通过键。原 Launch 定义 1014 在 pending 断言 1124 失败；后续
withdraw、再次排队、Stop、Truth 和 no-record 断言未达。旧完整 FAIL、trace 和
error-context 保留，不能被 replay-neutral 或 owner-loss 的通过替代。

真实 trace 的 pending 预期为原 5000 ms。292973.165 读取 idle，293478.046
读取 acknowledged；间隔 504.881 ms。中间 293103.992 的原 JPEG 明确显示
QUEUED SLOT 02 和第二槽 Queued，293320.349 已 Playing。原 late locator
采样错过真实短暂状态；native 回执迟延和旧 EEF boot 失败原因仍 UNKNOWN。

原 trace SHA：`5246fc1d2ef6bd001f7ae90356e884227e9810b8e0b56fffde068b448ff8e654`。
queued 原 JPEG SHA：`1695d4150a7594b45e0412642075f7de87b4f63b1f69d619769217dcfd31317c`。

本 Task 只声明两个文件，不改两页 Portal 或原 MASTER 计划：

1. `tests/platform/web/creator/creator_web_perform.spec.mjs`
2. 本计划文件。

## 最小修改与完整旅程

只将两个 pending 断言改为 `expect.poll`：同一 existing accessible locator 的
`evaluateAll` 读取当前匹配数组，恰好一个元素才返回其实际 `data-launch`，
缺失或多匹配返回 null；预期仍为字面量 pending。期限保持 5000 ms，间隔
50 ms；不使用元素出现的内部等待，不增加 helper、probe、Facade 请求或 observer。
真实 read／IPC 延迟仍存在，不宣称 50 ms 调度保证。

| 原旅程腿 | 保留的远端断言 |
| --- | --- |
| 导入、激活、建第二 Pattern、两槽分配 | 原 helper、Pattern 身份及 revision readback |
| 空槽、停止时两次选槽 | 空槽无流量；实际 snapshot.reload 收据和对应 counter |
| Play、earlyBar | 第一槽 acknowledged；原真实 session／inspect，30000 ms 和原 barFrames / 5 窗口 |
| 首次排队 | pending 在原 5000 ms 内；QUEUED SLOT 02、当前第一 Pattern、第一槽 acknowledged、counter 01 |
| 撤回 | 点击正在播的槽；pending_switch null、第二槽 idle、当前第一 Pattern |
| 再次排队并应用 | 第二次 pending；原 30000 ms 内 playing、非录制、pending 清空、当前第二 Pattern；双方槽状态、cue、counter 02 |
| Stop 和完整收尾 | playing false、第二槽 idle；三次 switch 收据 [second, first, second] 且 ok；无 live reload／record 流量；Truth 相等、Performance idle |

用例标题、Chromium 边界、原 traffic observer、整条 180000 ms、earlyBar 已有
50 ms 采样、5000／30000 ms 预算和所有上述腿均保留；不更改产品、音频或点击。

## 验证与交付

最低层 RED 是上述同名完整用例在真实 committed 968 的原失败及阳性原帧。
修改后先运行同名完整 Launch 单例，保留全部原断言；使用独立新 `--output`
目录，不能清空原完整套件 trace／error-context。绑定当前 own 产品 dist 的
真实十文件 inventory、未变化的产品输入和原 fixture SHA／size；固定测试
数据复用必须明确，不声称重新构建 runtime 或生成数据。

本 Task 的真实完整 focused 结果为 1 passed（18.6 s），audio wrapper
child.wait 与其真实命令退出码均为 0；两次 pending 及所有原收尾断言执行完成。
源码、索引、own dist 和 installed dependency 前后守卫相等，旧 full trace／
error-context 保留；原 retain-on-failure 策略未生成 Green trace，不虚构录像。
此结果只证明同名完整单例；旧 968 full FAIL、新 head full UNRUN 及 native
回执迟延 UNKNOWN 均保留，不能从本次结果推导新的完整 lane 通过键。

完整 focused GREEN 后，暂存两声明文件，运行既有 ownership 77 和 pitfall 15
检查及 diff 检查，创建独立 Conventional Commit，不 amend 原 968。
随后在实际新 committed head 运行完整已选 Creator lane，原八组及所有预算
保留，记录实际结果与官方 input key；focused 不能产生 full lane 通过键。
按真实 scope 与 Portal provenance 结算其余既有检查，不添加新 gate。

新 head 必须取得新的独立／正式 current-head review，处理实际 findings、
conversation、protection 和 batch evidence。旧 968 的 publisher 重试即使
通过，也不能证明新 head。owner 负责最终采用与合并；作者不自评、waive 或
接受风险。不删除原日志、缓存、源码、Git 或其它工作树。

## Version Management

Version impact: none — 仅修正两个内部 Browser 观察回调和独立计划；不改产品
实现、公开 API／ABI、Contract、Host 行为、Assembly／lock 或身份，不分配版本。

## Documentation Impact

Documentation impact: none — 只修内部观察采样，保留现有产品状态、严格预期、
全部预算与旅程；不改变 Portal 已记载的行为、边界、版本、Proof／CI 政策或
操作流程。两页当前 Queued／Playing 事实仍准确，无需重复编辑。
PR #2010 总体仍保留原 Task 的 `Documentation impact: required` 和
`/hosts/creator-interactions/`、`/hosts/creator-web/`；本 Task 的 none 不替代
其原文档交付、检查或来源义务。
