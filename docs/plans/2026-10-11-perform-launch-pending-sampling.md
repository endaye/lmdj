# Perform Launch 短暂排队状态的采样

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
