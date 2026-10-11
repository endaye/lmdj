# Perform replay-neutral FX 与设备监听音量验收

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
