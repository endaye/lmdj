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

# Perform replay-neutral FX 与设备监听音量验收

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
- 初始候选状态：实现与 focused GREEN 已完成；完整 Creator、当前 head 评审
  和合并按下述顺序推进，实际候选证据记录在 PR 与外置验收收据中。
- 实际起点：`46045119801d9f03707aaa6f8ed50fbd651e8e95`，包含 #2006。
- 分支：`fix/perform-replay-monitor-oracle`；使用独立工作树。

## 当前前提与范围

#2000 已通过 `116280f9209245b4757a814fcf3155002b025269` 交付 MASTER
consumer：范围 0–100%，与 ENC4 共用本设备监听值。它不进入 FX 手势、HOLD、
Performance 事件、Project Truth 或 Undo，不改变录音、重采样、导出 PCM。
本 Task 复用这一行为，不修改 App、Core、监听 producer 或 wiring。

原完整 replay-stop 用例仍对所有 slider 断言 FX 中点 500；新增的第四个
MASTER slider 默认是 100。旧 aa1 候选的真实 RED 仅作为历史；本 Task 先在
上述 clean main 的独立工作树全新 configure、build、package，再运行未改的
同名原用例。实际定义行 1699、失败行 1723，第四个控件明确是 MASTER，
expected 500 / received 100。原 trace 证明 replay playing → stopped · neutral
及三个 FX=500 成功；HOLD／Pattern 尾部断言因第四个 slider 失败而未达。

当前两页 Portal 仍有 MASTER 缺席陈述。#2006 已修正 interactions 附录 A4
中的 MASTER consumer 状态，本 Task 保留该段及其完整验收边界；只修正
第 6 章触摸入口、第 10 章缺席句和 creator-web 的同一事实矛盾。

K1 仍拥有相同 Perform spec 和两页 Portal 的键盘映射工作，owner 已协调
顺序集成；不同 hunk 不等于没有归属重叠。保留 #2006 的导航已批准／未接线、
BPM、Bank 和 live Mute/Solo 状态，不实施其它 K2／M1 行为。

初始外置提案曾声明三个文件；首次实现编辑前，owner 明确增加 creator-web
同一 MASTER 事实修正，最终只有下列四个文件：

1. `tests/platform/web/creator/creator_web_perform.spec.mjs`
2. `apps/docs-site/docs/hosts/creator-interactions.mdx`
3. `apps/docs-site/docs/hosts/creator-web.mdx`
4. 本计划文件。

## 一个 Task，一个独立预期

原同名用例在导入／激活后、分配和录制前，将 MASTER 设置为非默认 37 并
断言已接受。停止回放后，分别按独立 accessible name 断言 Filter、Delay、
Reverb 为字面量 500，再断言 MASTER 仍为 37。保留原 HOLD=false 和 Pattern
Launch 2 idle 断言；不从共享控件元数据推导预期，不增加 Facade 检查或探针。

原用例标题、300,000 ms 整条预算、6,000 ms 录制尾段、playing／stopped 的
30,000 ms 等待、5,000 ms 数值预期、boot／activation／retry／launch 预算、
项目和 capability 边界均不改。MASTER 就绪使用既有音频转换等待预算。

| 旅程腿 | 必须保留的远端断言 |
| --- | --- |
| 导入／激活／进入 Perform | 原准备 helper 成功，MASTER 可用且接受 37 |
| 分配／移动 Pattern | 原分配和移动的 readback／槽位断言 |
| 演出录制 | 原首个 A01 hit、Filter 630／HOLD、6,000 ms 后第二个 hit |
| 停止／保存 | 原 sealed 状态及 busy-retry 保存，Replay 出现保存条目 |
| 播放 | 原 Replay status 为 playing，排除自然完成代替 Stop 路径 |
| Stop Replay／回到 Live | stopped · neutral，三个命名 FX=500，MASTER=37 |
| 完整收尾 | HOLD aria-pressed=false，Launch Pattern 2 data-launch=idle |

## 验证与交付

最低层证明是全新 own-main 原同名用例真实 RED，然后完整修改用例 GREEN；
focused 结果只证明该完整旅程。源码和索引守卫、实际 canonical 三步终态、
own CMAKE_HOME_DIRECTORY、实际 JS／WASM／dist SHA 与固定测试输入均留在
任务外置证据目录，不能把旧 aa1 dist 冒充新 main。

初始候选的实际最低层结果：canonical configure／build／package 均为 0；
未改原用例为上述匹配 RED；修改后的同名完整用例为 1 passed（21.4 s），
包含录制前 MASTER=37、Stop Replay 后三个 FX=500／MASTER=37 及原 HOLD／
Pattern 尾部断言。两次运行源码、索引和实际 dist 前后守卫均相等。

验证顺序：

1. 实际 fresh configure／build／package 与未改原用例 RED。
2. 四文件修改后的完整 focused GREEN；原每腿断言均执行。
3. `scripts/docs-site.sh check` 完整 Portal；新计划实际暂存后运行既有
   `python3 tests/build/ci_change_scope_test.py`（77）和
   `python3 tests/build/ci_pitfall_ledger_test.py`（15）；检查暂存范围与 diff。
4. 一个 Conventional Commit，精确检查 committed 四文件和工作树。
5. 完整已选择 Creator lane 在 committed head 上运行，保留原全部八组
   Browser 旅程及真实 batch-only `pass key=`；focused 不替代完整 lane。
6. 当前 head 独立／正式评审、实际 findings／conversation disposition、
   live protection／conflict／batch evidence 检查后，由 owner 继续合并。

不新增 gate，不降低严格性、超时或 lane／旅程覆盖。新 main 若改变相关
producer／consumer／验收证据，按 issue-done §0 刷新实际前提再继续。

## 环境与保留证据

使用普通 UID501、既有 pinned EMSDK 6.0.5、Host Node 26 与锁定 Playwright
1.62.1。依赖仅在六份 package／lock source byte-equal 后 APFS COW 至本
工作树；独立 regular inode、相对有效 symlink、hidden lock 及 donor 前后
守卫均核对，不复制 donor CMakeCache、absolute graph、runtime／UI／dist。

原固定 Project fixture SHA
`66262c9187cb264a006e29d077751186acdeb02a30fc4bc497482049297e938f`、
767,554 bytes 及 producer 输入与当前 main 实际字节一致，明确复用原固定
测试数据；不声称本头重新生成或旧完整 suite PASS。初始可用空间约 1.48 GiB，
保留真实 ENOSPC 风险，不造任意磁盘门槛，不删其它缓存／日志／源码／Git。

旧 EEF 完整八组仍为 FAIL（114 passed／2 failed／11 skipped）；首次 fresh
owner boot 失败原因仍 UNKNOWN。1698 NoTestsFound、aa1 focused owner PASS
和 aa1 replay RED 均保留各自边界，不能推导 full8、听感、release 或 Goal 完成。

## Version Management

Version impact: none — 仅修正 Browser 独立预期和已实现 MASTER 的当前文档
事实；不改 API、Contract、active manifest、Assembly 或身份，不分配版本。

## Documentation Impact

Documentation impact: required
Affected portal pages: `/hosts/creator-interactions/`、`/hosts/creator-web/`。
同一 Task 更新两页当前 MASTER／Stop Replay 事实；身份继续从 active manifest
派生，不手填 Build／版本，不创建 snapshot 或 release。
