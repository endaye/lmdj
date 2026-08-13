# Stage 7 Creator Editor Review — 2026-08-12

- 审查对象：Stage 7 Creator Editor 设计与交付，包括设计规格
  `docs/superpowers/specs/2026-08-07-lmdj-stage7-creator-editor-design.md`、实施计划
  `docs/superpowers/plans/2026-08-07-lmdj-stage7-creator-editor.md`，以及实现范围
  `packages/web-runtime-platform`、`apps/creator-web`、`packages/project-io` Bundle
  导入路径、`packages/application-facade` 导入能力、
  `contracts/project/lmdj.project-bundle.v1.schema.json`、Stage 7 测试与 Proof、
  版本与 Portal 快照。
- 审查基线：首轮 `main` revision `0b5d2d6`（Stage 7 交付提交为 PR #97
  `c39d8b6`、PR #101 `488ffa7`、PR #102 `38a8c13`）；第二轮复核 `main`
  revision `5bf4ace`（新增 #117 Stage 6 hardening squash 合入、#118 squash
  witness、#119–#125 deploy 修复）。
- 方法：首轮五个并行方向独立取证后交叉汇总——①计划-规格一致性、②Platform 与
  Creator Host 实现符合性、③Bundle 导入契约与安全、④测试覆盖与证据链、
  ⑤版本与治理合规。第二轮四个并行方向对首轮全部 37 项发现逐条复核，并对
  #117 触及 Stage 7 表面的改动做增量审查。所有发现均带 `file:line` 或提交级
  证据。
- 性质：本文件是评审记录，不是实施计划。需要修复的事项应另行进入实施计划与
  Pull Request。第二至六节为首轮记录，其中的"现值/现状"措辞以首轮基线
  `0b5d2d6` 为准；第七节记录第二轮复核后的现状，以 `5bf4ace` 为准。

## 一、总体结论

Stage 7 的实现质量高：所有硬边界——Creator 只经
`web-runtime-platform`/Application Facade、Platform 产品中立、Bundle 导入
fail-closed 与原子发布、Audio 手势激活、无 `innerHTML`、privacy-safe allowlist、
资源清理链——均有代码与自动化测试双重证据，未发现边界穿透或伪造成功状态。
`lmdj.project-bundle.v1` 以 `compression: "none"` 从根上消除解压炸弹，hash 在落盘
后回读验证，Native `RENAME_NOREPLACE` 与 Web R1 intent 协议与规格逐条对应。

第二轮复核（基线 `5bf4ace`，含 Stage 6 hardening #117 合入）确认：#117 对
Creator 面零功能改动（仅身份常量同步），首轮 37 项发现中 **36 项仍成立、
1 项已解决**（G5，由 #118 的 squash witness 机制解决）；增量审查另发现
1 中 3 低共 4 项新问题。两处 Web OPFS 中危缺陷（F1/F2）的修复已在
`fix/opfs-publication-recovery` 分支完成但未合入。

主要问题仍集中在三类：

- **收尾证据缺口（1 项高危）**：手动 canary 验收仍无任何记录（T1）。
  G1 原被本报告升为高危，理由是"tag 已打而前置证据缺失"；该前提经第三轮
  取证证伪，已降级为记录缺口（见第十一节）。
- **Web OPFS 发布层两处可用性缺陷（F1/F2）**：main 上原样存在；修复待合入。
- **文档漂移**：Stage 7 规格/计划自首轮起零提交，五项漂移原样保留；两份验收
  记录（Stage 7 与 hardening）的 External state 均已与 main 实况脱节。

下表保留第二轮统计，并加入第三轮事实更正；当前整改 closure 以第十节为准：

| 严重度 | 数量 | 说明 |
| --- | --- | --- |
| 高 | 1 | T1（维持） |
| 中 | 15 | 首轮 14 项仍成立 + 新增 N1；G1 降级后计入本档 |
| 低 | 23 | 首轮 20 项仍成立（G5 已解决移出）+ 新增 N2/N3/N4 |
| 已解决 | 1 | G5，由 #118 squash witness 机制化解决 |
| 编辑·信息 | 若干 | 正文列出，无需单独排期 |

## 二、设计与计划文档评审

### 值得保持的实践

- 规格自带 Rejected Directions（§16）与 Self-review Checklist（§18），
  Non-goals（§5）明确到功能粒度；计划自带 Requirement-to-Task 覆盖表，§4 十二项
  范围、S7-D1–D9 决策、§13.1 十四门、15 条 portal 路由全部可逐一落到具名
  Task/测试，全文无待办占位符。
- R1 OPFS publication 修订（writer lease、pending→committed intent、≤1 MiB 分块
  复制、逐字节比较、枚举隐藏与恢复三规则）在计划中被逐要素忠实展开。
- Build 重分配规则被正确预置：计划 Task 11 Step 1 以
  `git tag --list 'lmdj-v1.0.16.*'` 实际验证下一个未用 Build，符合规格 §14
  "已用或放弃编号不得复用"。
- `project_bundle.py pack` 被明确限定为 Native fixture 工具、不入分发包，守住了
  Non-goal "`.lmdj` 导出" 的边界。

### 文档漂移与计划缺陷

| ID | 严重度 | 内容 |
| --- | --- | --- |
| D1 | 中 | 计划 Task 2 Step 4（行 510–536）与 Task 5R1（行 861–961）重复定义同一 R1 发布协议且时序矛盾：Task 2 已完整实现七步协议并期望 fault 断言 GREEN，后置的 Task 5R1 Step 2 却期望 RED（"journaled publication/fault recovery is absent"）。按序执行的 worker 会在 TDD RED 门卡住。这是 R1 修订就地并入 Task 2 后未清理 5R1 原始叙事的痕迹。 |
| D2 | 中 | 五个 post-freeze 纠正候选（1.0.16.1–1.0.16.5，计划行 215–307）只存在于计划，规格未回写；规格 §17（行 620 附近）完成定义仍钉死 "`1.0.16.0 · canary` current docs 与不可变 Portal snapshot 匹配"，与最终交付 1.0.16.5 不符，审计线索断在计划内部。 |
| D3 | 中 | 计划正文与其自身矫正记录矛盾：Task 8（行 1201）写 "closes it once on terminal unmount/pagehide"，而第三次矫正节（行 244–267）已判定 "persisted `pagehide` incorrectly closed the shared Runtime" 是缺陷。按正文实现会复现 1.0.16.3 修掉的 bug。实现已正确区分（`apps/creator-web/src/runtime/runtime_context.tsx:132-137` 仅非 persisted 才 close）。 |
| D4 | 低 | 纠正候选 1.0.16.2/.4/.5 三节只有叙事段落，无 Task 级结构（无 Files/Steps/RED-GREEN），与计划其余部分的可执行粒度不一致。 |
| D5 | 低 | 计划把 Bundle 内部路径收窄为 ASCII 子集 `[A-Za-z0-9._/-]`（行 68），规格 §7.2 写 "使用 UTF-8 路径"。方向 fail-closed、理由成立（受管名均为生成名），但属计划内发生的 Contract 级收窄，应回流规格措辞。 |
| D6 | 低 | §13.1 第 6 门的 reload/reopen 段落依赖 `creator_web_lifecycle.spec.mjs`，但计划 Task 10 未写出该 spec 的具体断言，打包浏览器层的 reload→reopen 断言内容在计划文本中留白。 |
| D7 | 低 | §13.1 第 7 门要求 burst 断言 "16 admissions、16 outcomes、0 rejection、Host 保持 running"；计划 burst 句只写前两项。实现实际断言了全部四项（`tests/platform/web/creator/creator_web_browser.spec.mjs:71-92`），属计划措辞缺口。 |
| D8 | 低 | 规格 §8.4 "旋转、resize 和 browser chrome 高度变化不得关闭 Project 或 Audio Session" 无任何显式测试映射；Task 10 accessibility 仅断言三视口无溢出。 |
| D9 | 低 | 规格 §10 错误表中 `HOST_PROTOCOL_MISMATCH`、`IO_ERROR`、`INTERNAL_ERROR` 三行的 Creator 行为无显式 Creator 侧测试（其余七行均有映射）。 |
| D10 | 低 | 规格 §11 要求 close/restart 释放 "Worker、MIDI listener、BroadcastChannel、AudioContext"；计划测试清单未点名 BroadcastChannel（实现有清理：`packages/web-runtime-platform/web/web-runtime-pre.js:263,321,1242`）。 |

编辑性小项：规格 §17 首行写 "D1–D8 决策均由实现与测试覆盖"，遗漏 R1 修订新增的
D9（计划与实现实际覆盖了 D9）；计划 `LocalProjectSummary.bundleDigest` 的获取方式
（重算 vs 落盘）未写明，因锁定格式可确定性重算，不构成第二数据库。

## 三、实现符合性矩阵（逐项核对通过）

| 设计要求 | 核对结果与位置 |
| --- | --- |
| §6.1 Host 边界：Creator 不解析 Bundle、不触 Project I/O、不建第二 Snapshot | `apps/creator-web/src` 全部 Runtime/Project 操作经 `@lmdj/web-runtime-platform`；grep 无 `navigator.storage`/OPFS/project-io/`.lmdj` 解析。`project_actions.ts:33` 的 contract 校验只针对 Facade inspect 响应 |
| §6.2 Platform 产品中立 | platform `web/` 无 React/CSS/Creator 字符串/`innerHTML`（`source_boundary_test.py:64` 自动化禁止）；DOM 仅限 runtime 装载（`runtime_session.mjs:222,528-540`）；diagnostic coordinator 在 Host 侧 |
| §6.3 Runtime Session 表面 | `runtime_session.mjs:1640-1655` 覆盖 12 项语义；`preflight()` 并入 `start()`，新增 `requestMidi`/`diagnostics`，责任边界未变 |
| §9.1 状态模型 | `creator_state.ts:13-57` 含规格 12 态全集另加 `recovering`；Project/Runtime/Audio/Transfer 四子状态独立建模，无单一红绿灯（但见 F4） |
| §8.2 禁用未来模式 | `mode_rail.tsx:14-27`：`disabled` + `tabIndex={-1}` + `aria-label="… available in Stage N"`，无 handler/路由/假数据；`workspace_shell.test.tsx:44-47` 断言 |
| §8.3 Pad 表面 | `styles.css:85` `minmax(44px,1fr)`；64 唯一 Pad 地址由 packaged Chromium E2E 校验（`creator_web_browser.spec.mjs:37-70`） |
| §9.2 手势激活、无 autoplay | `input_adapters.mjs:8-24`（`isTrusted` + WeakSet 一次性消费）；`runtime_session.mjs:1303-1311`；restart 后 audio 重置 `inactive`（`creator_state.ts:138`）；recovery 从不调用 `audioContext.resume()`；`audio_lifecycle.test.tsx:115,193` |
| §7.2 传输契约 | `contracts/project/lmdj.project-bundle.v1.schema.json` 1.0.0；64 MiB/entry、512 MiB 总量、4096 entries、index 4 MiB 双端强制；`compression` const `"none"` 使解压炸弹路径不存在 |
| §7.2 拒绝项 | `project_bundle_transfer.cpp:131-151`（绝对/空/`..`/NUL/超长）、`:277-281`（重复与大小写折叠）；symlink/device 在 `native/storage_platform.cpp:590-630` 与全程 `O_NOFOLLOW`；未声明 entry 由发布前 inventory digest 复算等效拒绝（`:797-803`） |
| §7.3 原子导入 | staging→逐块落盘后回读重算 SHA-256（`:680-689,754-762`）→load/replay 复验→destination lease→碰撞检查→`publish_directory_if_absent`；同 digest 幂等（`:829-846`）、`DUPLICATE_ID`（`:836-842`）；失败清 staging，重启遗留由 `application.cpp:1020-1024` 清理 |
| §7.3 R1 Web 发布协议 | `library_opfs_storage.js`：destination lease（`:520-523,687-706`）、intent 位置与字段（`:9,237-297`）、≤1 MiB 分块复制（`:429-466`）、逐字节比较（`:468-514`）、`createWritable`+`close()` swap 唯一 commit point（`:387-414`）、枚举隐藏（`:106-109`，损坏 intent 视为 pending `:311-319`）、mutation 前恢复（`:330-344,714`） |
| Native 发布 | `storage_platform.cpp:389-417,2208-2243`：`renameatx_np(RENAME_EXCL)` / `renameat2(RENAME_NOREPLACE)`，rename 前后复验、双向 fsync，其余平台 fail-closed |
| §11 安全与隐私 | 三处代码树无 `innerHTML`/`dangerouslySetInnerHTML`；MIDI 仅 "Enable MIDI" 按钮触发；`acceptance_report.ts` 全 allowlist；错误 message 均为常量字符串，无绝对路径 |
| 资源清理 | `terminalCleanup`（`runtime_session.mjs:800-822`）→ `runtime_loader.mjs:26-73`（transport/worker/worklet/AudioContext）；`input_controller.dispose` 移除全部 8 个监听；pagehide 链路经广播 `release-and-close` 释放全部 lease（`web-runtime-pre.js:255-266,1213-1244`，5 秒兜底） |
| 诊断 Host 复用 Platform | `apps/web-runtime-host/src/main.mjs:1-7` 直接 import platform，无私有副本 |
| 退役 Contract | `lmdj.patch.v1`/`lmdj.materials.v1` 零新引用（仅守卫测试与冻结参考材料命中） |
| 版本与 Assembly | `products/lmdj/version.json` = 1.0.16.5；assembly.json 含 `creator-web 1.0.2` 与 `web-runtime-platform 0.1.2`；assembly.lock 与 portal `versions.json` 一致；1.0.16.0 快照 metadata 逐项等于规格 §14 目标，漂移链（.1 facade 1.3.1 依赖传播、.3 platform 0.1.2）完整可解释，无未解释漂移 |
| Portal 快照 | 1.0.16.0–.5 六个 Build 三套产物齐全（`versioned_docs`/`static/versions`/`versioned_metadata`），编号单调无复用，.4 被取代但证据保留 |
| Documentation impact | PR #97/#101 body 均声明 `required`，#97 的 route 清单与规格 §14 十五条逐项一致 |

## 四、代码发现

| ID | 严重度 | 位置 | 内容 |
| --- | --- | --- | --- |
| F1 | 中 | `packages/project-io/src/web/library_opfs_storage.js:556-561` | 发布失败清理顺序缺陷：catch 中 `removeTreeParts(destinationParts).catch(() => {})` 吞掉 destination 删除失败后仍无条件删除 intent。若删除失败（配额/瞬态 OPFS 错误）而 intent 删除成功，留下无 intent 保护的半成品 destination：枚举不再隐藏，且 `list_local_projects` 对任一目录 summarize 失败即整体报错（`project_bundle_transfer.cpp:549-553`），整个本地项目列表被打瘫且无自动恢复。正确顺序应为 destination 删除确认成功后才删 intent，否则保留 pending intent 交给恢复流程。 |
| F2 | 中 | `packages/project-io/src/web/library_opfs_storage.js:633-666` | 损坏的 `lmdj.storage.intent.v1` 使项目永久锁死：`recoverIntents` 对解析失败/无法归类的 intent 直接 throw（`:637` 的 `TextDecoder` 未用 `fatal:true`，与 `:303` 不一致）；intent 用 sync handle 增量写（`:590`），崩溃可留半截 JSON，此后该 project 每次 `acquireWriter` 永久失败，需人工清 OPFS。对比 publication intent 的"损坏视为 pending 可恢复"，此处 fail-closed 一致性安全但无可用性出口；torn intent 只可能产生于 destination 未被触碰前，理论上可安全自动清除。 |
| F3 | 中 | `apps/creator-web/src/runtime/runtime_context.tsx:68,117-124` | `HOST_RESTART_REQUIRED` 自动重建只允许一次且计数永不复位；第二次进入 restart-required 时 UI 停在该状态，ErrorPanel（`app.tsx:375-386`）只对 `PROJECT_BUSY` 提供 Retry，用户只能整页刷新。防重启循环合理，但缺手动重试出口，与规格 §10 部分不符。 |
| F4 | 中 | `apps/creator-web/src/state/creator_state.ts:101-182` | reducer 对每个 action 无条件接受（如 `failed` 下 `pad-pressed` 静默改状态）；合法性完全依赖上游 selector（`:221-248`）+ 按钮 disabled + `isAssigned` 前置。非法调用确实在到达 Platform 前被拦（Platform 端另有权威状态机兜底），但规格 §9.1 字面要求 "每个 UI action 在 reducer/state machine 中有明确合法源状态"，防御深度少一层。 |
| F5 | 中 | `apps/creator-web/src/main.tsx:12-52`、`apps/web-runtime-host/src/main.mjs:10-94` | Assembly 身份与 manifest 常量（productBuild、platformVersion、heapBytes、resource limits、emscripten pin）在两个 Host 手工重复，需逐字节一致才能过 manifest gate；版本升级需同步两处，存在偏移风险，且与 "身份由 manifest 派生、不手工输入" 的治理要求相抵。 |
| F6 | 中 | `apps/creator-web/src/components/error_panel.tsx:6-15` | `WEB_RUNTIME_RESOURCE_LIMIT` 只渲染 typed code，丢弃 details 中的数值；规格 §10 要求显示 observed/limit。 |
| F7 | 低 | `packages/project-io/src/native/storage_platform.cpp:624` | managed-tree 校验未检测 hardlink（regular file 未检查 `st_nlink > 1`）。wire 格式无法表达 hardlink、导入文件均由 importer 自建，实际不可经 Bundle 注入；仅本地既有树可能含 hardlink，规格拒绝清单该项在 native 侧无显式实现。 |
| F8 | 低 | `packages/web-runtime-platform/web/project_bundle_reader.mjs:17-18` | `PATH_PATTERN` 负向前瞻写错（`(?:^\/)` 应为 `(?:^|/)`），该前瞻为死代码；被 `:174` 显式 `.`/`..` 段检查与 C++ 权威端复验兜底，无实际漏洞，属防御层退化。 |
| F9 | 低 | `packages/web-runtime-platform/web/runtime_session.mjs:983-1001` | `beginTake` 完整实现但未进入冻结 session 对象（`:1640-1655`），零调用；`state_machine.mjs` 的 `allowsOperation`/`stopTake` 同样仅测试触达。Stage 8/9 预留死代码，未构成提前暴露。 |
| F10 | 低 | `apps/creator-web/src/runtime/input_controller.ts:16-33` vs `runtime_session.mjs:560-579` | 键盘映射常量逐字重复，两处维护。 |
| F11 | 低 | `runtime_session.mjs:1510-1566` | Creator 传入空映射后 session 仍执行 `wireInputs()`：注册 window 级监听并创建内部三 adapter，与 Creator 自建的 `input_controller` 并存为第二套闲置布线。空映射使 session 侧无功能（无双触发）、close 时两套均正确清理，但与 §11 "不能留下第二个活跃输入消费者" 的精神打擦边；session 的 `requestMidi` 与内部 midiAdapter 在 Creator 中未使用。 |
| F12 | 低 | `runtime_session.mjs:174-218` vs `project_bundle_reader.mjs:61-100` | `sha256`/`canonicalJson`/`exactKeys` 双份实现，语义相同细节略异。 |
| F13 | 低 | `apps/creator-web/src/runtime/runtime_context.tsx:91-101` | recovery probe 以 16 ms `setTimeout` 轮询 `session.diagnostics()`；功能正确但属轮询式补丁，本可由事件通知驱动。 |
| F14 | 低 | `apps/creator-web/src/app.tsx:148-163` | restart 重建后的自动重开不占用 `beginProjectAction` 互斥令牌，与用户同时点击 Open/Import 存在小概率 UI 状态交错（Platform 侧串行化兜底）。 |
| F15 | 低 | `apps/creator-web/src/components/project_surface.tsx:71-76` | 规格 §8.1 Project Surface 应含 BPM，实现中 BPM 仅在 StatusBar；§8.1 布局中的 "Save Local" 不存在。Stage 7 无 mutation 功能可解释为有意裁剪，但规格未记录该偏差。 |

信息级：platform `pre.js:200,1204` 的 BroadcastChannel 名
`lmdj.web-runtime-host.terminal.v1` 带诊断 Host 命名（清理完整，仅命名瑕疵）；
`project_bundle_transfer.cpp:849` commit 前先释放 staging lease 存在被并发
`cleanup_incomplete` 抢删的微小窗口，结果 fail-safe；`used_tokens`（`:453`）进程内
单调增长，量级可忽略；Web 配额失败归入通用 `IO_ERROR`（`web/storage_platform.cpp:42-56`
未特判 `-6`），行为符合规格、错误码粒度略粗（第二轮注：#117 已补 `-6` 的
`quota_exceeded` 类型化条件，见第七节）。

## 五、测试与证据链评审

### 十四项自动化门覆盖

11 项完整覆盖、3 项部分覆盖、0 项缺失。完整覆盖包括：Platform 76 项
unit/contract、Creator 单测、schema 正/负例
（`tests/conformance/project_bundle_contract_test.py`）、Bundle 安全矩阵与 11 个
fault point 的 Web fault matrix（`tests/platform/web/project_io/project_io_web_faults.mjs:6-19`
与规格措辞逐点对应）、packaged Chromium 全旅程含 64 唯一 Pad 地址与 16-key burst
四项断言（`creator_web_browser.spec.mjs:37-92`，零 `page.evaluate` 旅程替代）、
MIDI synthetic/拒权/清理、WebKit capability boundary（诚实标注 "not physical
acceptance"，skip 不计 pass）、双次 clean package 逐字节比较
（`scripts/creator-web.sh:356-366`）。部分覆盖的 3 项见下表 T3/T4，及验收点
dependency gate 的 `ENVIRONMENT BLOCKED`（记录诚实、以 pinned hash 缓解）。

验收记录中的全部测试计数（Vitest 38、Platform 76、packaged Chromium 10+1 skip、
WebKit 1/1、package 7、server 3）与源码静态核对一致。五项实体物理行保持
`deferred / unverified`，无冒进声明。

### 发现

| ID | 严重度 | 内容 |
| --- | --- | --- |
| T1 | 高 | **规格 §13.3 手动 canary 验收无任何记录**：计划 Task 14 三个步骤复选框全部为 `[ ]`；全仓 git 历史（含 `--all`）无约定的记录提交；`docs/quality/evidence/` 无 Stage 7 条目；验收记录第 72–74 行自认 "remains a locally proven canary candidate until … manual canary acceptance is recorded"。而实现已合入 `main` 且签名 tag `lmdj-v1.0.16.5` 已存在。按规格 §17，Stage 7 不能被声明为完成。 |
| T2 | 中 | `38a8c13`（#102，唯一直接落 main 的测试修改）删除了 "Retry 后 alert 被清除" 断言（`await expect(alert).toHaveCount(0)`），改为盲等 250 ms；现行 `creator_web_lifecycle.spec.mjs:28-48` 在 120 s 上限内重试轮数无上界。解释（下一个 `PROJECT_BUSY` 在 Playwright 观察到空渲染前替换 alert）是可信的观测竞态，且每轮仍强制 alert 文本为 `PROJECT_BUSY`、最终必须成功；但测试不再约束 writer lease 释放的重试轮数，属轻度断言弱化。此前四次稳定化提交（`991e89f`/`d9c7703`/`c93875e`/`dd5067d`）核查为合法竞态修复与真实产品修复的配套，非掩盖。 |
| T3 | 中 | §13.2 "仅用 Keyboard 完成 import/open 与 Bank 选择" 无完成型测试：`creator_web_accessibility.spec.mjs:79-88` 仅验证 5 步 Tab 焦点序，import/open/Bank 旅程均为 click/upload。 |
| T4 | 中 | 十四门第 9 项（restart-required 后 reopen 且 Audio 不自动激活）仅有 JSDOM 组件级覆盖（`audio_lifecycle.test.tsx:115-146`），packaged 浏览器层无 Creator 的 restart-required 旅程。 |
| T5 | 低 | `input_controller.ts:230` 注册了 `visibilitychange` 释放 press state，但全仓无任何测试触发它；§13.2 "blur/visibility 释放" 的 visibility 半边未测（blur 已覆盖）。 |
| T6 | 低 | bfcache persisted 生命周期靠 `page.evaluate` 合成派发 `pagehide/pageshow(persisted:true)`（`creator_web_lifecycle.spec.mjs:77-80,142-144`）；Playwright 无法真实触发 bfcache，情有可原，但证明力弱于真实往返。 |
| T7 | 低 | 浏览器级 key-repeat 防重依赖组件测试（Playwright 不产生 OS auto-repeat），浏览器层长按断言证明力有限。 |

### 验收记录时效

验收记录 `docs/quality/2026-08-07-stage7-creator-editor-acceptance.md` 锚定
1.0.16.3 与 revision `ee14a280`（squash 后不在 `main` 历史上），External state 表
仍记 "Merge: not authorized / not performed"、"Draft PR #97 open"，且该文件在
`main` 上仅有 `c39d8b6` 一次提交、合并后从未更新。记录自身声明了时点性质，措辞
诚实，但按其自身条款，合并后的两个后续条件（merged-main Proof 与手动 canary）
均无落档证据（见 T1 与 G1）。

## 六、版本与治理

Build 轨迹：1.0.16.0（spec 目标，仅存在于分支）→ .1/.2/.3（分支内纠正候选，
`c39d8b6` 合入 main 时 tree 为 .3，验收记录绑定此版）→ .4（#101 分支内中间候选）
→ .5（`488ffa7` 合入 main）。六个 Build 快照齐全、revision 互不相同、编号单调
无复用，.4 证据保留未删除，符合规格 §15。模块版本 main 现值与验收记录实际值
完全一致（creator-web 1.0.2、platform 0.1.2、web-runtime-host 1.2.2、facade
1.3.1、project-io 0.5.0、core-cli 1.0.7、core-mcp 1.1.4、native-test-host 1.0.5），
无未解释漂移。

| ID | 严重度 | 内容 |
| --- | --- | --- |
| G1 | 中（偏高） | **规格 §17 要求 "从 merged `main` 重跑 required Proof"，仓库内无任何 Stage 7 post-merge Proof 记录**。`docs/quality/` 无 stage 7 merged-main 文档（对照 Stage 6 有 `b400351` merged-main acceptance 与 `5a7f0ca` review）；签名 tag `lmdj-v1.0.16.5` 已打，但缺少 merged-main 证据文档支撑该 tag。 |
| G2 | 中 | 验收文档 External state 表整体过期（见第五节"验收记录时效"），需 post-merge addendum 对齐 1.0.16.5、merge 事实与 tag。 |
| G3 | 中 | 政策张力：`docs/governance/version-management.md` §2.4 明文 "依赖升级、Assembly 变化必须分配新 Build 而非增加 PATCH"，但纠正候选 .1/.3 改变了 assembly.json 内容（facade 1.3.0→1.3.1、platform 0.1.0→0.1.2 及 host PATCH 传播）。按 "同一 Build 内缺陷修复 + 依赖 PATCH 传播" 的精神解读可接受（无公开能力/Contract 变化），但严格字面构成偏离，应明确解释先例。 |
| G4 | 低 | 签名 tag `lmdj-v1.0.16.5` 指向 `38a8c13`（#102），而 .5 在 `488ffa7` 分配、快照 provenance revision 为 `63fbc6fd`——同一 Build 身份跨 3 个 SHA。#102 仅改 1 个测试文件、产品源一致，tag 打在测试稳定后可辩护，建议文档明确 tag 为权威绑定。 |
| G5 | 低 | .0/.1/.2/.4 只存在于 pre-squash 分支 revision，从未是 main 提交；政策 §2.3 对 BUILD 层成立，但未明说 PATCH 候选是否也须落 main，快照 provenance revision 在 squash 后不可从 main 历史核验。 |

合规确认：三个 PR 均为单一 squash commit、分支命名合规、无 develop/release
分支；PR #97/#101 的 Version/Documentation impact 声明齐全且 route 清单与规格
一致；`lmdj.project-bundle.v1` 1.0.0 已注册于 assembly 与 lock；退役 Contract 零
新引用；#115/#116 无 Stage 7 版本影响。

## 七、第二轮复核 — 基线 `main` `5bf4ace`

### 基线变化

首轮之后 main 新增 8 个提交。与 Stage 7 结论相关的是前两个：

- `7555cfd` #117：`fix/web-runtime-hardening` 的 squash 合入（266 文件、
  +12848 行）。对 Creator 面**零功能改动**（`apps/creator-web` 仅同步身份常量
  与测试版本串）；实质行为变化在 platform/project-io 层：全部字节级变更
  （append/replace/create_immutable 及其 intent）绑定 writer lease 持有者的
  `platformIdentity`（`appendDurable` 从完全无租约检查变为强制绑定，关闭一个
  旧缺口）；新增类型化存储条件 `-5 → invalid_state`、`-6 → quota_exceeded`
  （`web/storage_platform.cpp:55-59`）；协议层对不相关 request_id 的响应
  fail-closed 为 `HOST_PROTOCOL_MISMATCH`（`protocol.mjs:425-430` 与
  `web-runtime-pre.js:406-412` 双处，Creator 会话路径生效）。Build 轨迹推进
  至 1.0.16.8（.6/.7 为 abandoned、unshipped candidate，Portal current 明文
  记录）。
- `336a27c` #118：squash witness 机制（`versioned_provenance/` +
  `architecture-portal.sh witness` 子命令 + fail-closed 验证器），使 squash
  后的快照 provenance 可从 main 认证——恰好解决首轮 G5。
- #119–#125 为 deploy 修复，无 Stage 7 影响。

现值：Product Build `1.0.16.8`；facade 1.3.3、project-io 0.5.2、platform
0.1.5、creator-web 1.0.5、web-runtime-host 1.2.5、core-cli 1.0.9、core-mcp
1.1.6、native-test-host 1.0.7；Portal 快照 14 个（1.0.13.0–1.0.16.8）；签名
tag `lmdj-v1.0.16.8` → `336a27c`（验签通过）；platform 测试 76→78（#117 新增
2 个 protocol fail-closed 测试）。

### 逐项复核结果

37 项首轮发现全部复核，证据行号以 `5bf4ace` 为准：

| ID | 严重度 | 复核状态 | 现证据与说明 |
| --- | --- | --- | --- |
| T1 | 高 | 仍成立 | 手动 canary 仍零记录：计划 Task 14 复选框全 `[ ]`、`docs/quality/evidence/` 无条目、`git log --all --grep="manual canary"` 为空 |
| G1 | 中偏高→**高**（第三轮撤回，见第十节） | 前提证伪 | Stage 7（1.0.16.5）merged-main Proof 仍无记录；复核期间同一模式对 1.0.16.8 第二次成立——hardening 计划行 456–459 明文 "only after … merged-main Proof … may the Integration Owner create signed annotated tag lmdj-v1.0.16.8"，签名 tag 已存在（→`336a27c`），而 hardening 验收锚定合并前分支 revision `56b7260` 且其 External state 自记 "Merge not performed"；main 上无任何 #117 之后从 main 运行的 Proof 记录。违反前置的 tag 已发生两次，升级为高 |
| D1–D5 | 中×2低×3 | 全部仍成立 | spec 与 plan 两文件自 `0b5d2d6` 起零提交 |
| D6 | 低 | 仍成立 | lifecycle spec 现行断言结构见 `creator_web_lifecycle.spec.mjs:28-48,60-68` |
| D7 | 低 | 仍成立 | 计划措辞缺口不变 |
| D8 | 低 | 仍成立 | 全 tests/ 仍无活动会话中的 resize/旋转测试（唯一 `setViewportSize` 在 goto 前，`creator_web_accessibility.spec.mjs:48`） |
| D9 | 低 | 仍成立（局部变化） | #117 新增的 `HOST_PROTOCOL_MISMATCH` 测试全在 platform 侧（`protocol.test.mjs`）与诊断宿主侧（`realtime_failure.spec.mjs`）；Creator 侧三错误码行为测试仍为零 |
| D10 | 低 | 仍成立 | #117 未新增 BroadcastChannel 清理测试；Creator src/test 仍不含 BroadcastChannel |
| F1 | 中 | 仍成立 | `library_opfs_storage.js:564-571`，catch 块原样；#117 仅改同函数 `:528` 的 `activeLease`→`coveringLease` 改名。修复已在 `fix/opfs-publication-recovery` `a393ed1`（未合入） |
| F2 | 中 | 仍成立（症状变化） | `:641-648` 逻辑未变、`TextDecoder` 仍无 `fatal:true`；#117 使该失败对宿主呈现为类型化 `IO_ERROR/invalid_state`（`storage_platform.cpp:56`），项目仍打不开。对照组：#117 把 publication intent 路径容错化（`fatal:true` + 解析失败按 pending 回滚），恰反衬 per-file intent 路径该修。修复已在 `039399d`（未合入） |
| F3 | 中 | 仍成立 | `runtime_context.tsx:68,118-124`；`app.tsx:377-385` |
| F4 | 中 | 仍成立 | `creator_state.ts:101-182` |
| F5 | 中 | 仍成立 | `main.tsx:12-36` / `main.mjs:10-34`；#117 把值更新为 1.0.16.8/0.1.5 但重复未消除（恰好演示了该发现的维护成本） |
| F6 | 中 | 仍成立 | `error_panel.tsx:6-14`；#117 新增的 quota/invalid_state 类型化条件同样止步 platform 层，Creator UI 无 `storage_condition` 消费（grep 零命中） |
| F7 | 低 | 仍成立 | `storage_platform.cpp:544-631`（`:998,:1016` 他处有 nlink 检查，此函数无） |
| F8 | 低 | 仍成立 | `project_bundle_reader.mjs:17-18` |
| F9 | 低 | 仍成立 | `runtime_session.mjs:983-988,1640-1655`；`state_machine.mjs:155,204` |
| F10–F14 | 低 | 全部仍成立 | 位置同首轮（F14 现 `app.tsx:148-162`） |
| F15 | 低 | 部分变化 | BPM 已出现在项目选择列表行（`project_surface.tsx:88`），打开后 summary `<dl>` 仍缺 BPM（`:71-76`）；"Save Local" 仍不存在 |
| T2 | 中 | 仍成立 | `creator_web_lifecycle.spec.mjs:34,41-45`：`toHaveCount(0)` 仍缺失、`waitForTimeout(250)` 仍在；#117 未触及该文件 |
| T3 | 中 | 仍成立 | `creator_web_accessibility.spec.mjs:79-88`，导入仍走点击+filechooser |
| T4 | 中 | 仍成立 | #117 新增的 `realtime_failure.spec.mjs` 目标是诊断宿主页（`window.lmdjWebRuntimeHost`），非 Creator UI；Creator restart-required 仍仅 JSDOM 级 |
| T5 | 低 | 仍成立 | `input_controller.ts:230,250` 注册/注销在，触发它的测试仍为零（host 侧派发的两处测的是宿主运行时） |
| T6/T7 | 低 | 仍成立（未变） | 同首轮 |
| G2 | 中 | 仍成立（差距扩大） | Stage 7 验收文档零变更；main 实况已推进两个 Build 与两个 tag |
| G3 | 中 | 仍成立（第三次使用） | #117 的计划再次以 PATCH 递增承载 assembly 变化（.6→.7→.8 移动 9 个模块身份），仍无对 §2.4 的显式豁免或政策修订；`version-management.md` 零变更 |
| G4 | 低 | 仍成立（新事实） | 新 tag `lmdj-v1.0.16.8` → `336a27c`（#118），而快照 proof revision 为 `56b7260`（#117 的分支源）——Build 身份跨 SHA 的绑定链仍靠 plan+witness 而非单一权威记录 |
| G5 | 低 | **已解决** | #118 squash witness：`versioned_provenance/version-1.0.16.8-squash-witness.json` + fail-closed 验证器 + `docs/governance/architecture-portal.md` 新增 10 行规则；来源关系收敛为 direct-parent / byte-identical squash projection / 显式 witness 三种 |

### 新增发现（#117 触及面增量审查）

| ID | 严重度 | 位置 | 内容 |
| --- | --- | --- | --- |
| N1 | 中 | `library_opfs_storage.js:528` | 发布路径未纳入 platformIdentity 绑定：`publishDirectoryIfAbsent` 用新拆出的 `coveringLease(destination)`（只查租约存在），而 `replaceComplete`/`createImmutable`/`appendDurable`/`createIntent` 全部改走带身份校验的 `activeLease(destination, platformIdentity)`（`:237-243`）。同页面另一 platform 实例仍可在他人租约覆盖的目标上执行目录发布。旧代码同样不校验，非 #117 回归，但 #117 目标"mutations bound to lease owner"明确豁免了发布路径，且新增 `distinct_platform_mutation_ownership` conformance 不覆盖 publish。应补绑定或成文豁免理由。 |
| N2 | 低 | `library_opfs_storage.js:795-796` | `createImmutable` 错误优先级变化：租约/身份检查前置到 already-exists 检查之前——无租约 + 目标已存在，旧返回 `-4 already_exists`，现返回 `-5 invalid_state`（或他人租约 `-3 project_busy`）。依赖 already_exists 幂等语义的宿主重试逻辑需注意可观察错误码变化。 |
| N3 | 低 | `library_opfs_storage.js:911,984-1046` | `-7 → -3` 重映射在 7 处 extern 包装内联手写；`storage_platform.cpp` 的 `web_error` 不识别 `-7`。未来新增 extern 若漏掉重映射，会落成无 storage_condition 的裸 `IO_ERROR`。宜集中到 `status()` 或 `web_error`。 |
| N4 | 低 | `tests/platform/web/project_io/project_io_web_test.cpp:278-289` | `distinct_platform_mutation_ownership` 分支手写重复了同文件 `:89` 的 `mutation_result()` JSON 组装。 |

增量审查未发现边界违规或生产包死代码：`submitUntrackedHostStatus` 等测试
seam 仅在 conformance gate 下安装（`web-runtime-pre.js:1272-1276`），生产包
不含。

### F1/F2 修复分支状态

修复已在 `fix/opfs-publication-recovery` 分支完成三个提交（`a393ed1`
Task 1、`039399d` Task 2、`376f8e1` 计划记录），该分支叠加在 hardening 合并前
分支头 `2ce4c8a` 上，与 #117 的 main 内容树等价，预期可干净 rebase。已核实
两点适配事项：

- #117 引入的签名变化（`activeLease` 拆分、`createIntent` 增
  `platformIdentity` 参）在修复基座中已存在，修复代码与之兼容；
- #117 将"合法 intent + 目标损坏成两边都不匹配"的 conformance 期望改为
  `IO_ERROR/invalid_state`（main spec `:457-461`）——该用例属于修复刻意保留
  fail-closed 的"结构完整但不可接受"类，修复分支上该期望原样保留
  （fix 分支 spec `:506-508`），撕裂 intent 的新用例独立存在（`:689-704`），
  无矛盾。

验证缺口不变：修复的浏览器 conformance 用例与新增 C++ action 尚未在任何
emsdk + Playwright 1.62.1 环境编译执行；本地仅有 `node --check` 与桩件驱动的
RED→GREEN 逻辑验证（14 项断言，修复前文件恰好 5 项针对性失败）。

## 八、建议（按复核后优先级）

1. **止血证据缺口（T1、G2；G1 已降级）**：T1 是唯一高危。从当前 `main`
   merged-main 记录已落档（`docs/quality/2026-08-13-merged-main-proof.md`，
   覆盖 1.0.16.5、1.0.16.8 的既有绿色 run 与 1.0.16.9 的当前 Proof）；剩下的是
   执行并记录 Stage 7 §13.3 手动
   canary 验收；为两份验收文档（Stage 7 与 hardening）各追加 post-merge
   addendum，对齐 merge 事实与 tag。在此之前不应再创建任何新的签名 tag。
2. **合入 F1/F2 修复**：将 `fix/opfs-publication-recovery` 的两个修复提交
   rebase 到当前 `main`，在具备 emsdk + Playwright 的环境跑
   `web-runtime-host.sh proof` 与 `creator-web.sh proof` 验证新增用例，再做
   版本传播（注意：不可机械替换——`testing-and-proof.mdx` 把 Build 号与证明
   它的 revision 绑在同句，abandoned/superseded 判定是治理决定）。
3. **N1 发布路径身份绑定**：把 `publishDirectoryIfAbsent` 纳入
   platformIdentity 校验，或在 Portal storage 页成文豁免理由，并把 publish
   纳入 `distinct_platform_mutation_ownership` conformance。
4. **Creator 可用性（F3、F6）**：restart-required 手动重试出口；
   RESOURCE_LIMIT 展示 observed/limit——#117 的类型化存储条件（quota/
   invalid_state）已到 platform 层，顺路把它们接入 Creator 错误面。
5. **治理回写（D2、D5、G3、G4、规格 §17 笔误）**：1.0.16.1–.8 的纠正候选
   轨迹回写规格；修正 §17；PATCH-as-corrective 先例已使用三次，应在
   `version-management.md` 成文（含 tag 权威绑定规则）。
6. **测试补强（T2–T5、D8、D9）**：恢复 busy 重试有界断言；keyboard-only
   完成型旅程；packaged restart-required 旅程；`visibilitychange` 释放；
   resize/rotation 会话存活；Creator 侧三错误码行为测试。
7. **清理（D1、D3、F5、F9–F12、N2–N4）**：计划陈旧叙事；双 Host 身份常量单一
   来源（F5 在 #117 中再次付出双改成本）；死代码与重复工具；`-7→-3` 重映射
   集中化；`createImmutable` 错误优先级变化在 Portal storage 页记录。

## 九、审查环境

| 项目 | 值 |
| --- | --- |
| 首轮审查日期 | 2026-08-12 |
| 首轮基线 | `main` `0b5d2d6`（含 #97/#101/#102/#115/#116） |
| 首轮 Product Build | `1.0.16.5 · canary`（签名 tag `lmdj-v1.0.16.5` → `38a8c13`） |
| 第二轮复核日期 | 2026-08-12 |
| 第二轮基线 | `main` `5bf4ace`（新增 #117/#118/#119–#125） |
| 第三轮更正日期 | 2026-08-13 |
| 第三轮更正基线 | `main` `d1d8bb6`；证据 run 31327104838 / 31529410253 / 31634688566 |
| 第二轮 Product Build | `1.0.16.8 · canary`（签名 tag `lmdj-v1.0.16.8` → `336a27c`） |
| 设计规格 | `docs/superpowers/specs/2026-08-07-lmdj-stage7-creator-editor-design.md`（两轮间零变更） |
| 实施计划 | `docs/superpowers/plans/2026-08-07-lmdj-stage7-creator-editor.md`（两轮间零变更） |
| 验收记录 | `docs/quality/2026-08-07-stage7-creator-editor-acceptance.md`（锚定 1.0.16.3，两轮间零变更） |
| 相关修复分支 | `fix/opfs-publication-recovery`（F1/F2 修复，未合入） |
| 参照体例 | `docs/quality/2026-08-11-stage6-web-runtime-host-review.md` |

## 十、Remediation status — 2026-08-13

本节是第三次、以修复分支为对象的增量记录；不会改写上述两轮审查在各自基线下的
历史结论。实时刷新时 `origin/main` 为 `d1d8bb6`；PR #97/#101/#102/#117/#118
均已合并，签名 tag `lmdj-v1.0.16.5` 与 `lmdj-v1.0.16.8` 验签通过。当前
`fix/stage7-review-remediation` 仍是未 push、无 PR、未 merge 的 branch-local
candidate。完整自动候选门禁已在 clean revision
`c44517bc7bde30cea4a40a7cab495a081028eb7e` 通过，但仍不是 merged-main
Proof；精确命令、工具链身份、结果与未执行的人工表单见
`docs/release-evidence/2026-08-13-stage7-remediation-canary.md`。

### G1 factual correction

第二轮把 G1 升为高危时，用“仓库内没有 Proof 文档”推断“Proof 没有执行”，再推断
两个签名 tag 违反前置条件。GitHub Actions 原始记录直接否定该推断：

| Product Build | Signed tag revision | `main` push run | Result |
| --- | --- | --- | --- |
| `1.0.16.5` | `38a8c130e5f1ced6f27d8fd7d2cba2fd1d70f97f` | `31327104838` | `success`; 12 success / 1 designed fallback skip |
| `1.0.16.8` | `336a27c0799035b2f8d6455b32259ee227df20f6` | `31529410253` | `success`; 20 success / 1 designed fallback skip |

两个 annotated tag 均通过 GPG 验签。`.github/workflows/ci.yml` 在 push 到 `main`
时运行，`scripts/ci/change_scope.py` 把 `push` 强制为 `full` 且要求 full manifest
选择全部 lane。G1 是 documentation binding gap, not a Proof execution gap；这个
历史事实更正不能替代当前 Product Build `1.0.19.0` 在未来合并 revision 上的
future merged-main Proof。

### Candidate automated Proof and Canary correction

Product Build `1.0.18.0` 的 full/stress/coverage/Core Proof、Web Toolchain
Conformance Proof、Web Runtime Host Proof、Creator Web Proof、完整 Portal check、
vendored dependency、active-tree 与 version/Assembly Lock 门禁均在上述精确 revision
通过。Creator packaged Chromium 为 13 passed/1 designed physical-MIDI skip，
WebKit capability boundary 为 1 passed；自动 Chromium 是 Google Chrome for
Testing `151.0.7922.34`。这些结果只关闭 branch-local automated candidate
boundary，不能替代人工听感、实体输入、Safari/iPadOS 或 merged-main Proof。

不可变 `1.0.18.0 · canary` Portal snapshot 绑定 pre-snapshot source revision
`561fa2d6324d2fe2025eaf692026e5eedcb350bb` 与 Assembly Lock SHA-256
`3cd490099b7e7f15204d7af719f73bf7983077fe208e7644ce55cdc8c2809407`；
schema-2 provenance 在测试 revision 上验证通过。证据文档晚于受测 revision，
不会伪称其 documentation commit 本身已经运行产品 Proof。

第一次人工 Canary 在 `1.0.18.0` 上执行到步骤 7 前暴露了新的 release blocker：
Import 期间发生 Runtime Session replacement 时，旧导入虽被 AbortSignal 中止，旧
generation 的 `finally` 却因 action token 已失效而跳过 `transfer-ended`。新 Session
能够启动并列出本地 Project，但 Creator reducer 永久保留 `transfer.phase = importing`，
于是 Project 与 Audio actions 持续禁用。真实渲染回归测试先得到
`expected ready, received importing`，最小修复使 retiring Session cleanup 在中止旧导入
时同步清理其临时 transfer UI state，随后同一测试通过。

因此 `1.0.18.0` 是 abandoned / unshipped failed-canary candidate；操作者报告的步骤
1–6 只作为缺陷诊断观察，不构成 T1 部分通过，也不得从步骤 7 继续。修复分配 Creator
Web `1.1.1` 与 Product Build `1.0.19.0`，Contract、Project I/O、Web Runtime Platform、
Web Runtime Host 与 Provider identities 不变。`1.0.19.0` 已在 clean revision
`213023d096522de0bbe5e02e6699d775a45e67a6` 完成 full candidate Proof、不可变
snapshot 与独立 evidence；仍必须从步骤 1 重跑全部十步人工 Canary。

人工表执行前又发现默认实体键盘上下行与视觉 Pad 顺序反向。新的空间映射修复分配
Product Build `1.0.20.0`、Web Runtime Platform `0.2.1`、Creator Web `1.1.2`
与 Formal Web Runtime Host `1.2.8`：`Q W E R T Y U I` 对应 Pad 1–8，
`A S D F G H J K` 对应 Pad 9–16，Pad 键帽从同一 mapping truth 派生。
`1.0.19.0` 的 branch-local Proof 仍是其精确 revision 的历史事实，但不能替代
`1.0.20.0` 自动化、人工或 merged-main 证据；T1 继续从步骤 1 开始。

`1.0.20.0` 随后通过完整十步人工 Canary。独立的实体 MIDI 行在 macOS Chrome
获得权限后没有 Trigger；CoreMIDI 抓包确认受测 MPD218 在 PAD BANK A 的
PAD1/PAD16 分别发送 Channel 10 Note 36/51，而 Creator 额外硬编码 Channel 1。
修复分配 Product Build `1.0.21.0` 与 Creator Web `1.1.3`，移除 Creator 的单
channel filter；Platform `0.2.1`、Formal Host `1.2.8`、Project Truth、Contract、
Provider 与 Model identity 不变。自动化 Channel 10 回归不替代候选上的实体复验。

### Final finding closure audit

下列是当前修复分支的唯一现行 closure ledger；第二至七节仍保留各历史基线下的
原始发现与复核，不应被当作当前状态。`1.0.18.0` 的旧门禁仍绑定
`c44517bc7bde30cea4a40a7cab495a081028eb7e`；修复后的 `1.0.19.0` 完整候选门禁
绑定 `213023d096522de0bbe5e02e6699d775a45e67a6`，详见
[`2026-08-13-stage7-remediation-canary-1.0.19.0.md`](../release-evidence/2026-08-13-stage7-remediation-canary-1.0.19.0.md)。

| ID | Status | Current evidence |
| --- | --- | --- |
| D1 | resolved | Stage 7 plan 将后置 R1 段标为 retired/non-executable，Task 2 成为唯一执行定义；`6103c35`。 |
| D2 | resolved | Spec 回写 `1.0.16.0`–`1.0.16.9` 历史轨迹并解除固定 `.0` 完成条件；`6103c35`。 |
| D3 | resolved | Plan/Portal 统一 persisted `pagehide` 保留 Runtime、non-persisted terminal `pagehide` close；`6103c35`、`f4722de`。 |
| D4 | resolved | `.2/.4/.5` 已标成 retrospective candidate record，并记录触发、身份、门禁与授权边界；`6103c35`。 |
| D5 | resolved | Spec/plan/Portal 统一 managed Bundle ASCII segment subset，Project payload text 保持 UTF-8；`6103c35`。 |
| D6 | resolved | Packaged reload -> reopen same Project/revision -> explicit activate -> running；`f4722de`。 |
| D7 | resolved | Packaged synthetic burst 固定 16 admissions、16 outcomes、0 rejection、`running`；`f4722de`。 |
| D8 | resolved | Active Session 在 `768x1024`/`1024x768` 间 resize 后 Project/revision/Audio/counters 连续；`f4722de`。 |
| D9 | resolved | Creator 对 `HOST_PROTOCOL_MISMATCH`、`IO_ERROR`、`INTERNAL_ERROR` 的 allowlisted details/transition 测试；`0e921be`、`ef2b06b`。 |
| D10 | resolved | Replacement 前旧 generation 的 Worker/transport、MIDI listener、BroadcastChannel、AudioContext 与 lifecycle listener 归零；`767eeae`、`f4722de`。 |
| F1 | resolved | PR #127 / `ea22934` 已使 publication rollback 仅在 destination 确认删除后移除 intent；当前树 conformance 与完整 candidate Proof 通过。 |
| F2 | resolved | PR #127 / `ea22934` 已使 torn per-file intent 安全恢复、未知完整 Contract 继续 fail-closed；当前树 conformance 与完整 candidate Proof 通过。 |
| F3 | resolved | Runtime 自动重建次数在 running 后复位，并提供 guarded `Retry runtime`；`ef2b06b`。 |
| F4 | resolved | `isCreatorActionAllowed` 在 reducer 内拒绝非法源状态，覆盖非法 transition；`0e921be`。 |
| F5 | resolved | 两个 Host 从 generated Runtime identity 消费 Product/Platform/toolchain truth；`6292648`。 |
| F6 | resolved | ErrorPanel allowlist 显示 resource observed/limit 与 storage condition；`0e921be`。 |
| F7 | resolved | Native managed regular file 要求 `st_nlink == 1`，hardlink contract test 保证拒绝且不改树；`6c26153`。 |
| F8 | resolved | Shared integrity module 使用 segment-aware dot-segment guard，positive/negative path tests 通过；`6d21a63`。 |
| F9 | resolved | 未进入 active Facade 的 `beginTake`/`stopTake`/`allowsOperation`/`activeTake` Web dead surface 已删除；`6d21a63`。 |
| F10 | resolved | Creator 与 Platform 共用 `DEFAULT_KEYBOARD_MAPPING` 单一 truth；`767eeae`。 |
| F11 | resolved | Creator 显式拥有输入 wiring，Platform 不再创建第二套闲置 listener；`767eeae`。 |
| F12 | resolved | `canonicalJson`/`exactKeys`/SHA-256 收敛到 `integrity.mjs`，两消费者共用；`6d21a63`。 |
| F13 | resolved | `subscribeDiagnostics` 事件通知取代 16 ms diagnostics polling；`ef2b06b`。 |
| F14 | resolved | 自动 reopen 与用户 Open/Import 共用 generation/session-bound Project action lane；`0e921be`。 |
| F15 | resolved | Opened Project Surface 显示 BPM；spec 明确自动持久化且无虚假 `Save Local` command；`0e921be`。 |
| T1 | resolved — `1.0.20.0` ten-step Canary passed | endaye 在当前任务中确认十步全部完成且无问题；实体键盘空间顺序、逐键听感、Bank B/C/D、Suspend/reactivate、reload/reopen 与报告导出均通过。报告 SHA-256 `7e2a2b…333a`，28 admissions / 28 outcomes / 0 rejection / no error；实体 MIDI、Safari、iPadOS 保持独立 `deferred / unverified`。 |
| T2 | resolved | Busy retry 上限 8 次、transition-based waits、最终 alert count 0；`8553467`。 |
| T3 | resolved | Packaged keyboard-only Import、reload 后 Open、Bank selection 完成型旅程；`8553467`。 |
| T4 | resolved | Packaged outcome timeout -> restart-required -> old generation cleanup -> replacement -> explicit activation；`f4722de`。 |
| T5 | resolved | Hidden visibility 与 blur 均清 held key，重复 cleanup 幂等且后续 keydown 可重新 admission；`8553467`。 |
| T6 | resolved | Persisted lifecycle 仍明确为 synthetic contract boundary；产品断言与文档均禁止把它写成真实 bfcache/Safari pass；`f4722de`、`6103c35`。 |
| T7 | resolved | Component 直接覆盖 `repeat:true` rejection，packaged burst 明确标为 synthetic；不冒充 OS auto-repeat physical evidence；`f4722de`、`6103c35`。 |
| G1 | corrected — historical Proof recovered | Run `31327104838`/`31529410253` 精确绑定签名 tag revisions；原高危“Proof 未执行”结论撤回，文档绑定缺口由本 ledger/evidence 补齐。 |
| G2 | resolved | Acceptance External state 已分离历史 PR/tag/Proof、当前 branch-local candidate 与未授权外部状态；`6103c35` 及本次更正。 |
| G3 | resolved | Governance 明确 PATCH 不得改变 Assembly/lock，任一 module/provider/Host/dependency identity change 分配新 BUILD；`6103c35`。 |
| G4 | resolved | Product Build -> signed tag -> tag revision -> merged PR -> source -> snapshot witness -> Proof -> evidence revision 权威链已成文；`6103c35`。 |
| G5 | resolved | Squash witness/fail-closed provenance 已存在，`1.0.16.9` 的实际 merge-parent断点由 authenticated witness 修复；`217dc10`。 |
| N1 | resolved | `publishDirectoryIfAbsent` 要求 exact `platformIdentity` owner，distinct-platform publish regression 覆盖；`6c26153`。 |
| N2 | resolved | `createImmutable` 先保留 existing-file `ALREADY_EXISTS`，absent/no-owner 才 `PROJECT_BUSY`；`6c26153`。 |
| N3 | resolved | Owner mismatch 到 public `PROJECT_BUSY` 集中在单一 JS status adapter，删除七份 inline remap；`6c26153`。 |
| N4 | resolved | Web Project I/O conformance actions 共用 generic `mutation_result` JSON helper；`6c26153`。 |

### Remaining integration gates

| Gate | Status | Current evidence |
| --- | --- | --- |
| T1 human canary | `passed on 1.0.20.0` | endaye 独立重跑全部十步并确认无问题；实体键盘与听感通过，报告 SHA-256 `7e2a2b…333a`。实体 MIDI、Safari 与 iPadOS 不在该通过范围内。 |
| Product Build `1.0.19.0` historical branch-local Proof | `passed, superseded for current mapping acceptance` | clean revision `213023d` 完整 Task 13 门禁通过；snapshot source `35c0905`，Assembly Lock `24a341…0689`。 |
| Product Build `1.0.20.0` branch-local Proof | `passed` | clean revision `7d409b5`：Creator、Formal Host、Core、dependency/identity 与 Portal 全量 Proof 通过；snapshot source `6a1cd97`，Assembly Lock `85c607…913`；详见 `docs/release-evidence/2026-08-13-stage7-keyboard-mapping-canary-1.0.20.0.md`。 |
| Product Build `1.0.20.0` merged-main Proof | `in progress` | 另一个进程已直接 push candidate history 到 `origin/main` `ccd0aec`，无关联 PR；full `main` push run `31665186166` 正在运行，尚无 terminal success。人工验收 addendum `95ae181` 仍只在本地。 |
| Product Build `1.0.21.0` branch-local candidate | `in progress` | Creator `1.1.3` 已通过 synthetic Channel 10 regression；full Proof、immutable snapshot 与候选实体 MIDI 复验尚未完成。 |
| macOS Chrome physical MIDI | `failed on 1.0.20.0 / pending on 1.0.21.0` | MPD218 PAD BANK A raw input confirmed Channel 10 Note 36/51; old Creator filtered it before Trigger admission. |
| macOS Safari Bundle import | `manual observation passed` | endaye 未遇到导入 `stage7-canary.lmdj` 后超过 20 秒仍停在 `importing`；不推导 Safari Pointer 或 iPadOS 通过。 |

因此当前源代码、branch-local 自动化、文档与历史 G1 更正都已纳入 closure ledger，
T1 的十步键盘/听感 Canary 已在 `1.0.20.0` 关闭，但实体 MIDI 缺陷要求新的
`1.0.21.0` 候选。该候选的 full Proof、snapshot 与实体复验仍未完成，本修复任务
不能报告为最终完成，也没有授权 push、tag、Release、deployment 或 Channel promotion。

## 十一、第三轮更正 — G1 降级（2026-08-13）

### 撤回的结论

本报告第二轮把 G1 从"中（偏高）"升为"高"，理由是"签名 tag 已创建而其明文前置
条件 merged-main Proof 在仓库内查无记录"，并称该模式对 `lmdj-v1.0.16.5` 与
`lmdj-v1.0.16.8` 重复两次。**该前提不成立，结论撤回。**

### 证伪它的证据

`.github/workflows/ci.yml` 声明 `on: push: branches: [main]`，而
`scripts/ci/change_scope.py` 对 `push` 事件强制 **full 模式（全部 lane）**。因此
每次合并到 `main` 之后，全量 Proof 都会在被合并的 revision 上自动运行——它不是
需要谁记得触发的动作。按两个 tag 各自指向的 revision 直接查 CI：

| Product Build | 签名 tag → revision | `main` `push` run | 结果 |
| --- | --- | --- | --- |
| `1.0.16.5` | `lmdj-v1.0.16.5` → `38a8c13` | 31327104838 | success（12 绿 / 1 设计跳过） |
| `1.0.16.8` | `lmdj-v1.0.16.8` → `336a27c` | 31529410253 | success（20 绿 / 1 设计跳过） |

两次唯一的非成功作业都是 `macOS gates (GitHub-hosted fallback)`，它在
`macOS gates (primary)` 于受信 Mac 上通过时按设计 `skipped`。两次均为 full
模式；作业数差异只反映期间新增的 lane，不是更窄的选择。

**两个 tag 的前置条件都没有被违反。** 缺的从来只是"从 tag 到 run"的文档绑定。
完整证据与 `1.0.16.9` 的当前 merged-main Proof 记录在
`docs/quality/2026-08-13-merged-main-proof.md`。

### 更正后的 G1

| ID | 严重度 | 内容 |
| --- | --- | --- |
| G1 | 中 | merged-main Proof 的 run 一直存在且在 tag 指向的 revision 上为绿，但从未有文档把它们绑定到 Build 身份；且 2026-08-12 期间连续四次 `main` push run 为红（依赖限流、快照 provenance 未认证、`LICENSE` 未分类）而无人处置或记录。真正的缺口是"红的 merged-main run 被放置不管"，不是"Proof 未运行"。 |

### 方法论教训

第二轮的错误来自**用文档缺失推断动作缺失**：没有找到 Proof 记录，就断定 Proof
未运行，进而推断 tag 违反前置条件。正确做法是直接查 tag 指向 revision 上的 CI
结论——一次 API 查询即可证伪。本报告其余以 `file:line` 或 run 级证据为锚的发现
不受影响；受影响的只有这一条以"仓库内查无记录"为唯一依据的推断。

对后续审查的约束：**"查无记录"只能支持记录缺口类结论，不能支持行为未发生类
结论**，除非同时给出该行为若发生必然留下的痕迹也不存在。
