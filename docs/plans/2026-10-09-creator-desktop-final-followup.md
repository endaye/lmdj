# Creator Desktop Final：后续功能、缺陷修复与验收收尾

## Outcome and authority

逐项完成 Creator Desktop Final 后续范围：修复已确认缺陷，确认尚未决定的产品
行为并实现，验收四页交互，结算版本，再清理有完整保留证明的本地资源。
用户于 2026-10-09 授权执行本计划的 Goal，包括 Task 的 commit、push、PR、
当前 head 评审和 squash merge，以及证明安全后的相关本地工作区/分支清理。
本计划不授权 tag、Release、部署、Channel promotion、远端分支或云主机资源清理。

[原计划](2026-10-06-creator-desktop-final-ui.md) T1–T11（含 T1b、T5a）已完成。
用户明确确认以该计划为准完成原目标；本 Goal 不重做原任务。历史 Claude
会话的额度耗尽和 Goal 结束检查不构成产品未交付的证据。

产品决定优先于 Figma。Desktop Final 是桌面布局/视觉依据，不能凭图中的控件
推导运行时能力或持久化语义。Mobile/iPad 设计扩展不在本计划中；现有布局的
真实 Safari/iPad 输入与设备验收仍须保留适用证据。

## Facts and premise dispositions

初始调查绑定 `origin/main` = `0d7c178b2bc4d277ff34424bb5f42c78aee7ef9d`。
在每个 Task 开始、提交前和最终合并检查时刷新 main 及其相关继任交付。

| 前提 | 当前证据与处置 |
| --- | --- |
| 原 UI Task 未交付 | 已反证：相关实现 PR 全部 merged，最后 #1900 → `1f20e8f63`、#1901 → `0d7c178b2`；不重复实现。 |
| #1905 连续提交刷新丢失 | 仍待修复。`app.tsx` 的 grid/structure/colour 成功提交路径无参数调用 `refreshPerformProject()`；该函数从 render ref 取 token 的 baseRevision。`creator_state.ts` 拒绝与当前 revision 不同的 token。现有双颜色测试只检查请求与 fixture Truth，未检查最后画面。R1 先复现再修。 |
| #1868 导入偶发停在 0 B | Issue open；尚未建立原因。R2 是条件调查，只有验收受阻时才启用，不把一次重跑通过当作修复。 |
| #1873 测试问题仍未修 | 已反证：Issue closed，相关修复已合并；本 Goal 不重做。 |
| #1822 其余控件映射已有决定 | 仍未决定：Issue open；`physical_controls.tsx` 对未绑定旋钮禁用，原决策只批准 Sequence ENC2–4 和左右键。D1 等待 owner。 |
| 400 ms 规则已正式确认 | 原计划 T6 仍记录为待 owner 确认的提案。D2 需正式决定，不把实现存在当作产品批准。 |
| D01/D03/D04 图示能力均可直接接线 | 未建立。D3–D5 分别调查真实 Host dispatch、请求/状态前提和既有测试；无操作时先设计 Core/Contract Task。 |
| 合并/自动化可代替人工验收 | 不成立。原验收台账保留真实输入、听感、辅助技术和生命周期缺口；A1/A2 分开记录。 |

开放 PR #1904 是 audition golden 计划；开始涉及 audition 的 Task 时重新核对其
交付与文件范围。原 Claude 主会话没有进行中的实现任务；监视器不取得新 Task
工作区所有权。新 Task 使用自己的隔离工作区，不共享旧构建目录。

## Progress and order

| ID | 工作 | 初始状态 | 依赖/完成条件 |
| --- | --- | --- | --- |
| P0 | 本后续计划 | 实施中 | 链接、路径 ownership、声明检查；PR 评审并合并。 |
| R1 | #1905 连续 authoring 提交刷新 | 可实施 | 减小复现；同类与不同类连续操作显示最新 Truth；回归测试、验证、评审、合并。 |
| R2 | #1868 导入稳定性条件调查 | 待调查（条件项） | 若阻碍本计划验收，保留 trace 并定位请求/读取/提交边界；证实原因后独立修复。 |
| D1 | #1822 统一原则及逐页映射 | 原则已确认；逐页待决 | owner 已选统一原则；再逐页确定具体参数、当前 Pad、边界/播放/录音/SHIFT 行为。 |
| D2 | 400 ms 连续旋钮提交 | 待 owner 决策 | 确认预览、提交、取消、离页、锁定、Undo 语义。 |
| D3 | D01 Save / Save As / 未保存提示 | 待调查及 owner 决策 | 与现有立即持久化一致；确认保存对象、复制身份、取消与失败。 |
| D4 | D03 audition/trim/browse/assign 与细调 | 待调查及 owner 决策 | 明确现有行为、目标确认、数值单位/范围、Undo/Redo、取消/失败。 |
| D5 | D04 MASTER/滤波类型/Mute/Solo/电平 | 待调查及 owner 决策 | 明确作用域、Truth 与 live 状态归属、真实投影及 DSP 能力；不画假读数。 |
| I1–I5 | D1–D5 的对应实现 | 等待相应决定 | 每项批准后追加精确 Task，再实施和合并；不得以此编号捆成一个大 PR。 |
| A1 | 四页自动化与视觉核对 | 待验收 | I1–I5 完成或 owner 明确取消相应范围；保留每个 journey 的 far-side assertion。 |
| A2 | 真实设备及人工验收 | 待验收 | 具体设备、来源、身份、步骤和结果；缺失 leg 保持未验收。 |
| V1 | 协调版本结算与 snapshot | 待实施 | 读取最终 manifests 和版本政策；独立 version Task、Portal snapshot 及合并后 provenance。 |
| C1 | 本地工作区/分支收尾 | 待调查 | 完整改动保留、干净（含 untracked）、未锁定且无人使用；逐个安全移除。 |

执行顺序为 P0 → R1，之后依次完成 D1/I1、D2/I2、D3/I3、D4/I4、D5/I5，
再 A1/A2、V1、C1；人工等待时可推进不依赖该结果的调查或实施。R2 仅在
适用条件出现时加入。每个产品问题一次给出少量选项、建议及影响，收到明确
回答后记录 decision。决定不做可以完成该范围的处置；暂缓仍是未完成，除非
owner 明确同意移出本 Goal。

2026-10-09 owner 已确认统一原则：旋钮 1/2 管视图位置，旋钮 3/4 管当前页
主要数值，方向键做导航，SHIFT 保留撤销/重做并支持粗调。此回答只确认
原则，具体页的参数、当前 Pad 与步长尚未批准；不以它推导完整映射。

## P0 — ship this bounded plan

**Declared files:** only `docs/plans/2026-10-09-creator-desktop-final-followup.md`。

**Lowest-tier verification:** 检查相对链接与 declared files；新增文件 stage 后运行
`python3 tests/build/ci_change_scope_test.py`；运行实际选择的 docs_static；
PR body lint 与 declaration-only 检查。本 Task 不改变产品事实或 Portal 页面，
不新增产品测试或 required gate。

## R1 — latest projection after consecutive authoring commits (#1905)

**Behaviour:** 连续 authoring 操作按 tail 顺序提交，后一次投影不能被 render ref
滞后丢弃。每次请求仍使用正确 expectedRevision，Project 切换后的旧结果仍被
拒绝；不放宽 reducer 的跨 Project/Pattern/token 身份保护。成功提交后的
刷新失败沿用现有 error/current 清空策略，authoring tail 保留已提交 revision，
不能重发已提交操作；本 Task 不改变失败投影的契约。

**Declared files:**

- `apps/creator-web/src/app.tsx`；
- `apps/creator-web/test/workspace_shell.test.tsx`；
- 若 reducer 复现需要，`apps/creator-web/test/creator_state.test.ts`，不预先改 reducer；
- `apps/docs-site/docs/hosts/creator-web.mdx`；
- 本计划（更新 R1 状态及验证证据）。

**Lowest-tier verification:** App component 测试先显示 red：两个同步进入 tail 的
颜色操作都已提交后，Pad 呈现第二个颜色；另外两种不同操作（例如 grid edit
和 Pad colour）连续执行后同时呈现最新事件和颜色。保留当前 stale token/
Project 切换拒绝测试。断言分别检查请求 revision、fixture Truth 和最终 UI，
不能只检查两个请求都成功。修复后这些检查通过，revert/mutation 证明失败
确实落在新显示断言。再执行 Creator unit/typecheck、Portal check，以及最终
committed head 实际选择的 batch-only creator lane。

**Documentation:** `/hosts/creator-web/` 描述成功 authoring 后投影刷新的一致性。
**Version:** Creator 修复至少欠 PATCH，纳入 V1；不在修复 Task 猜测身份。
**Pitfall:** 产品逻辑的回归测试是其出口；不为该逻辑错误新增流程 pitfall。

## Decision and implementation Task contract (D1–D5 / I1–I5)

每个 D Task 在决定前核实真实源码与 dispatch/handler/payload/state 前提，
记录 inspected revision、已有能力、仍需实现和未确认部分。既有能力的正向
控制与实际 authoritative registration 必须先检查，再报告缺失。

Decision Task 声明自己的 `docs/prd/decisions/` 文件、decision-log/open-questions
更新、本计划，以及适用 Portal 页面；路径在该 Task 开始前锁定。决定之后，
在本计划追加实现 addendum，列出精确文件、最低层测试、每个状态/转移的
验收与影响。Core/Contract/Host producer 与 Creator consumer 有实际依赖时
分开 Task；未决定或未声明文件的 I Task 不进入实施。

## Acceptance (A1/A2)

**Declared evidence file:** `docs/quality/2026-10-09-creator-desktop-followup-acceptance.md`，
另加本计划；自动化发现的产品/测试问题使用独立修复 Task 声明文件。

四页分别覆盖正常、拒绝、失败、取消、Undo/Redo、reload/reopen。核对字体、
布局、缩放命中、键盘、控件状态与 Figma/decision；Figma fidelity 是实际
比较结果，不从功能测试推断。现有 journey 不删 leg、放宽阈值或伪造输入。
真实 Safari/iPad 输入、听感、辅助技术和生命周期分别记录；需要 owner 操作
时给出可执行步骤与预期结果，收到实际证据前保持未验收。

验收记录包含源码/Build/Host 身份（来自 manifests 或 report）、来源、设备、
浏览器、操作人/日期、逐 leg 观测和 report digest。未分配 Build 的源码验证
明确写源码 revision，不用旧 Build 证明新功能。V1 的 snapshot 不能倒推
此前人工验收绑定到新 Build；必要时在 V1 后复验身份敏感的验收。

## Version Management

Version impact: none — P0 仅建立计划，不修改 active manifest、Build 或 Contract。

实现 Task 各自记录 PATCH/MINOR/Contract 兼容性，V1 按最终实际影响协调结算。
原计划已记载 Creator 及相关 Core/Web 模块的版本债务；读取现行 manifest 和
继任版本提交后再确定剩余债务，不手填旧版本或预分配号码。

V1 在执行前声明确切 manifests、消费者、测试、Build/Channel 与 snapshot 文件。
Product Build/Assembly 改动同步更新当前 Portal、生成不可变 snapshot，合并后
验证实际 introducing SHA 的 provenance；必要 witness 走官方 generator 的
独立后续 Task。此过程不启动 Release 或部署。

## Documentation Impact

Documentation impact: none
Reason: P0 只记录计划与进度，不修改 Architecture Portal 或宣称新产品事实。
R1 和各实现 Task 按实际影响更新 Portal；Build/Assembly Task 必须 required。

## Verification and completion

每个 Task 先证实原因和当前前提，再跑最低层测试。stage 仅声明文件，确认非
main、ownership、cached diff check，创建 Conventional Commit；在 clean committed
head 分类，执行所有实际选择的 batch-only lane，PR 记录 pass key。评审、修复、
最终 main/governance 刷新、完整 conversation/closing relation 和 expected-head
保护均按 issue-done。失败后端/旧 head/过期证据不是独立评审。

本 Goal 的每项范围均完成决定、实现、验证、合并和适用验收，或者经 owner
明确取消/移出后，才可结束。保留最终 PR/SHA、验证/人工证据、版本/snapshot
状态、清理结果与范围处置；等待、额度、PR 创建或一段 green journey 不表示完成。

## Pitfall Impact

Pitfall impact: none — P0 规划不引入新流程知识。执行中按 Task area 查阅 pitfall，
特别保留共享构建目录、环境相关性归因及真实输入完成证据的既有要求。
