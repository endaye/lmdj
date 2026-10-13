# Creator Perform：静默当前 Pad 方向导航

## Outcome and authority

只交付 Perform 页普通 ↑／↓ 的当前 Pad 轴：按 A01–D16 选择上一／下一
Pad，首尾停止，跨 Bank 时同步演奏矩阵和既有 Sequence 可见行；不触发声音、
不写 Project Truth 或 authoring history。复用 App 的 `stepSequencePad`、
同一个 reducer current Pad 和 `PadSurface.currentSlot` 高亮，不增加监听器、
状态副本或新的组件接口。

用户已批准的依据是
[三页导航决定](../prd/decisions/2026-10-11-creator-navigation-and-live-mute-tails.md)。
本 Task 是 [#1822](https://github.com/endaye/lmdj/issues/1822) 的独立部分交付，
不结算 K2、D04 或整个后续 Goal。Root 授权独立 worktree 的源码准备；初始
执行窗口由 D03 F1 拥有。K2a 合并后的初始 checkpoint 仍为 Source preparation，
依赖安装及产品验证当时均未执行；Source 检查完成、调度释放后沿既有 standing
authorization 完成 Task 验证、原子提交、PR、独立当前头评审及保护合并。

## Facts and premise dispositions

2026-10-12 22:54 UTC 的 fresh fetch 与 live main 均为
`cbd7f898604f4e0953cb912279976bf12badaecc`，本隔离 worktree 从该提交建立。
查询 #1822 的 live body/comments：Issue OPEN，无 assignee；历史提案不覆盖
上述已批准决定。当时 Source 的 ↑／↓ 只在 Sequence 接线；Perform 没有
`padStep`，也没有 current Pad 的矩阵高亮投影，因此本项尚未交付。

- 已交付：ENC4 与 Perform MASTER 共用同一个设备监听 preference/binding。
  本 Task 保留已有路径，不重复实现。
- 初始待集成：K2a [#2108](https://github.com/endaye/lmdj/pull/2108) 查询时 OPEN，
  head `fab52a5acfc4ce039d997e86f404882dad5ab345`，尚无 mergedAt/mergeCommit。
  它覆盖 Project／Sample 导航，并与本 Task 的 App、workspace、hardware、
  Portal、followup 文件重叠。后续 live 查询确认它于 23:02:39 UTC MERGED，
  squash `9534841424c04399bd0e94341ba96d38dd3dcbe4` 的 parent 为上述 cbd。
  本分支已正常 fast-forward 到该 committed main，完整保留 K2a 交付，
  再应用本 Task 的七路径补丁；未复制 draft 或修改它的 worktree。
- 仍未交付：Perform ←／→ 的完整 PRIMARY／FILTER／MORE 组轴依赖 W1/C1
  的真实滤波 producer/consumer。W1 [#2083](https://github.com/endaye/lmdj/pull/2083)
  查询时 OPEN，声明源范围无 Creator UI。当前 C1 worker ownership UNKNOWN，
  不能据此取得它的文件。本 Task 不修改其组件或建立假 FILTER 页。
- 保留：SHIFT＋←／→ 既有 Undo／Redo、ENC1–3 细调及 ENC4 全局监听。
  Perform SHIFT＋↑／↓ 未分配，System 中本次新增的 Pad 方向不可用。
- 保留：FX、HOLD、Performance 录制、transport、Replay 和音频生命周期；
  导航不会调用 release、stop、clearPressed 或 authoring mutation。

提交前和合并前再次按 issue-done §0 刷新相关 main/successor；不得把 Issue
关闭或 owner 声明当作 Source／实测交付。历史报告、失败、其他作者段落和
五个既有 stash 保留。

## Declared files

1. `apps/creator-web/src/app.tsx`
2. `apps/creator-web/test/workspace_shell.test.tsx`
3. `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
4. `apps/docs-site/docs/platform/input.mdx`
5. `apps/docs-site/docs/hosts/creator-interactions.mdx`
6. `docs/plans/2026-10-09-creator-desktop-final-followup.md`（仅追加本项事实）
7. `docs/plans/2026-10-13-creator-perform-pad-navigation.md`

新增第八文件或改变产品语义须先说明原因。PhysicalControls、PadSurface、
PerformSurface、FxSliderBank、SDK、Core、Replay 和身份 manifests 不在声明内。

## Acceptance journeys and lowest-tier verification

每一步保留 far-side assertion，不减少旧 case、原 timeout、lane 或旅程。

| Journey | 远侧断言 |
| --- | --- |
| Perform A01 → D16 → A01 | 每个 Pad 的唯一高亮、地址及 Bank 正确；空 Pad 可静默选择；A01 ↑／D16 ↓ disabled，边界不再移动。 |
| Perform 选 Pad → Sample → Sequence → Perform | 四处读取同一个 current Pad；Sample 编辑对象、Sequence 当前行和返回 Perform 的矩阵高亮一致。 |
| 普通导航 → SHIFT → 普通导航 → System → 返回音乐 | SHIFT 与 System 没有新增 Pad 方向；SHIFT＋←／→ 仍使用原 history owner；退出禁用层后恢复同一个 Pad。 |
| 已持有 FX/HOLD 和 ENC4 → Pad 步进／跨 Bank | 效果值、手势、HOLD、监听值和 transport/record owner 不因 Pad 选择发生变化；无额外 trigger/release/authoring 请求。 |
| 真实 browser 操作以上选择路径 | 实际 App rail 点击后检查高亮、共享选择、无 trigger 请求和完整 Project Truth 不变；观察器只记录请求并透传原真实 transport，不用制造的 handler 替代操作。 |

K2a committed main 已正常集成。资源窗口释放后，最低完整相关检查为：

```bash
npm --prefix apps/creator-web test -- --run test/workspace_shell.test.tsx test/hardware_console.test.tsx test/perform_surface.test.tsx test/input_controller.test.ts test/pad_surface_keyboard.test.tsx
cd apps/creator-web && npx tsc --noEmit
bash scripts/docs-site.sh check
```

上述五个 Vitest 文件分别覆盖 App 接线、rail modifier/boundary、持有效果与
录制 owner、输入 admission、键盘和 Pad 地址；保留完整注册而非只选新增 case。
workspace 原单 case 20 s 预算不变。TypeScript 检查 App/fixture 接口；Portal
检查两条 current 路由及其来源事实。

浏览器 owning check 为完整原 `creator_web_hardware_layout.spec.mjs`，在该
Task 新鲜 Source 构建出的 Creator 与真实 Runtime 上运行 Chromium；采用
现有 locked toolchain/browser、owned server 和 fixture。保留原 Project
125 s、Audio 35 s 预算及所有原 case。开发入口/打包必须遵守现有 clean-source
约束；不得复用其他工作区的 dirty artifact 或绕过 packager。若需要 WebKit
的真实 capability boundary，按既有策略保留它的明确结果，不冒称设备验收。

提交前另检查 declared range、原测试正文保留、相对链接、new-file ownership、
staged whitespace，以及 PR 的 `Documentation impact` 声明。每项结果绑定
实际 integrated HEAD/Source 和真实 exit；首次失败保留原日志并停止相关动作。

完整 Creator lane、native/ASAN/stress、真实键盘／触摸／听感、A1/A2、release、
deploy 和整个候选 full verification 不由本 Task 的局部结果结算。初始 Source checkpoint 的全部
Task 产品检查为 **UNRUN**；后续实际执行结果按下列 dated checkpoints 追加，
Source/diff 审查不是 Native、browser 或产品 PASS。

## Version Management

Version impact: Creator Host MINOR feature debt. 这是兼容新增的已批准导航能力，
不改变 Core Module、Provider 或 Contract API。本 Task 不手填或分配任何身份；
Creator Host MINOR 及最终 Product Build/snapshot 的协调结算保留给 followup V1。

## Documentation Impact

Documentation impact: required

Affected portal pages: /platform/input/ /hosts/creator-interactions/

Reason: Perform 普通 ↑／↓ 从 unavailable 变为静默 current Pad 导航；同步
当前操作说明、边界与 SHIFT/System 行为，并明确仍未交付的 FILTER/group 轴。
不改 source diagram 或 projected identity；followup 只追加本项事实，原历史、
N13、K2a、D04、A1/A2、V1/C1 及其他作者章节逐字保留。

## 2026-10-13 — 首次完整 five-file 负结果与 fixture 减法

Root 完整 Source 预检 findings=[] 后分配本 Task 执行窗口。UID 501、Node
26.8.1；锁定 Creator `npm ci` 自然 0。原 argv 的完整五文件 Vitest 于
23:18:56–23:20:36 UTC 自然 1，403 PASS／2 FAIL（4 文件 PASS／1 FAIL），
不是完成验收。完整原 stdio/source/自然退出 receipt 保留在 Root 外部
`2026-10-13-perform-pad-navigation-task-execution/02-whole-five-vitest.*`。
后续 TypeScript、Portal、build/package/browser、commit/shipping 均未启动。

两处失败均在本次新增测试准备中。Sequence 实际 grid 是带
`data-testid="sequence-grid"` 的命名 section，既有 owner 测试使用该入口；
新增测试误找不存在的 ARIA `grid` role。FX case 复用的 recovery fixture
明确 `unconfigured`，而 App 原 encoder gate 需要 master capture 配置，
所以 slider 出现不表示 ENC1 已可用。修正为既有 configured status/subscriber
与真实 `{applied: true}` 回执形状，并等待原 App ENC1 binding 再转动。
产品 App 不变，不制造 handler，不修改 capability gate，不提高 timeout，
完整 64 Pad 往返、共享编辑对象、Truth/trigger 零变更、510/42/HOLD、历史、
transport/record counter 和每个原 journey/assertion 保留。下一步仍完整重跑
原五文件，而非仅选择失败 case；其余检查保持 UNRUN 直到 owning gate 通过。

## 2026-10-13 — Light owning checkpoint / clean candidate preparation

在上述最小 fixture/selector 修正后，原五文件完整重跑于 23:23:35–23:25:10
UTC 自然 0：5 文件 PASS、405 tests PASS、0 FAIL／0 skip（94.99 s）。完整
TypeScript `npx tsc --noEmit` 自然 0（2.13 s）；整套 Portal check 自然 0
（62.67 s）：177 tests、52 pages、10 source diagrams／20 outputs、50 routes
及内部 links。三个命令的声明 Source7 前后字节一致；首次 403P／2F 的
负结果及完整 stdio 保留，不用后续 PASS 覆盖。

命令、PID、自然 wait、stdio SHA 与 Source before/after receipts 位于 Root
外部 `2026-10-13-perform-pad-navigation-task-execution/03-*`、`04-*`、`06-*`。
UID 501、Node 26.8.1。新的 fresh fetch 仍是 main
`9534841424c04399bd0e94341ba96d38dd3dcbe4`；#2108 MERGED，#1822 OPEN。
下一步创建合法干净 Task 候选，再以 pinned Emscripten 6.0.5／locked
Playwright 1.62.1 新鲜构建 Creator + Runtime、真实 CLI Project fixture 和
owned server，执行完整原 hardware Chromium（workers 1）。这部分目前
**UNRUN**，不复用 foreign/dirty artifact，不删减 browser gate。

提交前 staged new-file ownership `python3 tests/build/ci_change_scope_test.py`
自然 0（77 tests），包括 `test_every_tracked_path_has_explicit_ownership_or_full_rule`；
无 unclassified tracked paths。七路径 staged whitespace 自然 0，原 main953
workspace/hardware/followup 完整字节前缀 retained。锁定 web 测试依赖 `npm ci`
自然 0，Playwright 1.62.1；实际 browser 执行仍待新鲜合法候选产物。

## 2026-10-13 — Complete owning hardware Chromium checkpoint

合法七路径原子 Task 候选 `f705e1657c919fa5e04cdd3a974bf106ec36d9f7`
在 clean worktree 上正常 public Creator/Runtime build 自然 0（91.88 s），
正常 package 自然 0；pinned Emscripten 6.0.5 verifier、Node 26.8.1 和 locked
Playwright 1.62.1 均按现有入口使用。随后仅 configure dev／build
`lmdj_core_cli` fixture target，自然 0；未执行任何 Core native test lane。
原 public script 的 exact fixture heredoc 通过真实 CLI 创建 Project、import
Asset、assign 全 64 Pad、create Pattern，每个 request 的 `ok` 与准确 revision
严格检查。两次正常 bundle pack 自然 0 且 `cmp` 自然 0。

owned distribution server 在 kernel-assigned `http://127.0.0.1:53802` 服务，
ready PID／nonce／argv 完整匹配。实际执行：

```bash
cd tests/platform/web
LMDJ_CREATOR_WEB_EXTERNAL_SERVER=1 LMDJ_CREATOR_WEB_FULL_CHROMIUM=1 \
LMDJ_CREATOR_WEB_BASE_URL=http://127.0.0.1:53802 \
LMDJ_CREATOR_WEB_BUNDLE=/Users/endaye/Projects/lmdj-followup-evidence/2026-10-13-perform-pad-navigation-task-execution/real-cli-fixture-f705/first.lmdj \
LMDJ_WEB_RESULTS_SLOT=perform-pad-navigation-hardware-chromium-f705 \
npm test -- --project=chromium --workers=1 creator/creator_web_hardware_layout.spec.mjs
```

完整原 hardware suite 于 23:36:12–23:37:22 UTC 自然 0：
**10 PASS／0 FAIL／0 skip**（70.16 s），原八个 case 与新增两个 case 全部注册。
默认 30 s、原 Project 125 s／Audio 35 s 和所有原 journeys/assertions 保留。
真实 UI 的 64 Pad 往返、首尾停止、跨 Bank 高亮、共享 Sample/Sequence
current Pad、SHIFT/System boundaries、完整 Truth 和 trigger 零变更均通过；
第二旅程验证真实 transport 接受 FX/HOLD 后，Pad 步进保留 510、HOLD 和
ENC4/MASTER 值，没有新的 FX/record/transport 或 authoring 请求。
Source7 在整个命令前后字节一致；完成后只停止自己的 nonce/PID/argv
确认过的临时 server，明确记录 intentional SIGTERM，不把 server 的 -15
当作产品 test PASS 或 FAIL。

全部 command/wait/stdio/source receipts 位于 Root 外部
`2026-10-13-perform-pad-navigation-task-execution/10-*` 至 `19-*`；fresh
artifact map、fixture body identity、owned server receipt 另行保留。原五文件
失败仍保留。此后本 commit 只追加真实结果到两份声明 plan/followup，产品
App、全部 Vitest/browser bodies 和两页 Portal bytes 与通过的 f705 候选一致。
Canonical clean-Task CI plan 自然 0：focused，selected `creator docs_static
portal`；Creator 为 batch_only ownership，其完整 lane 仍是候选/full debt。

当前自动 Task owning acceptance 已通过，远端 PR review/保护合并仍须以实际
最终 head 和 live facts 执行。完整 Creator、native/ASAN/stress、WebKit、物理
键盘/触摸/听感、A1/A2、V1 MINOR/Product Build、FILTER/group 和 Goal 仍未
由本项结算；本项仅是 #1822 的独立 Pad 轴部分交付，保持 Issue OPEN。
