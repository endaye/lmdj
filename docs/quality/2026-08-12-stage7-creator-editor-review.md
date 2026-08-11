# Stage 7 Creator Editor Review — 2026-08-12

- 审查对象：Stage 7 Creator Editor 设计与交付，包括设计规格
  `docs/superpowers/specs/2026-08-07-lmdj-stage7-creator-editor-design.md`、实施计划
  `docs/superpowers/plans/2026-08-07-lmdj-stage7-creator-editor.md`，以及实现范围
  `packages/web-runtime-platform`、`apps/creator-web`、`packages/project-io` Bundle
  导入路径、`packages/application-facade` 导入能力、
  `contracts/project/lmdj.project-bundle.v1.schema.json`、Stage 7 测试与 Proof、
  版本与 Portal 快照。
- 审查基线：`main` revision `0b5d2d6`；Stage 7 交付提交为 PR #97（`c39d8b6`）、
  PR #101（`488ffa7`）、PR #102（`38a8c13`）；参考后续 PR #115/#116（仅 CI，无
  Stage 7 版本影响）。
- 方法：五个并行方向独立取证后交叉汇总——①计划-规格一致性、②Platform 与
  Creator Host 实现符合性、③Bundle 导入契约与安全、④测试覆盖与证据链、
  ⑤版本与治理合规。所有发现均带 `file:line` 或提交级证据。
- 性质：本文件是评审记录，不是实施计划。需要修复的事项应另行进入实施计划与
  Pull Request。

## 一、总体结论

Stage 7 的实现质量高：所有硬边界——Creator 只经
`web-runtime-platform`/Application Facade、Platform 产品中立、Bundle 导入
fail-closed 与原子发布、Audio 手势激活、无 `innerHTML`、privacy-safe allowlist、
资源清理链——均有代码与自动化测试双重证据，未发现边界穿透或伪造成功状态。
`lmdj.project-bundle.v1` 以 `compression: "none"` 从根上消除解压炸弹，hash 在落盘
后回读验证，Native `RENAME_NOREPLACE` 与 Web R1 intent 协议与规格逐条对应。
版本轨迹 `1.0.16.0 → 1.0.16.5` 六个 Build 快照齐全、无编号复用，模块版本漂移全部
可由纠正候选的依赖传播解释。

主要问题集中在三类：**收尾证据缺口**（手动 canary 验收与 merged-main Proof 均无
记录，而签名 tag `lmdj-v1.0.16.5` 已存在）、**Web OPFS 发布层两处可用性缺陷**
（失败清理顺序可留下无 intent 保护的半成品、损坏 intent 使 writer 永久锁死）、
**就地修订留下的文档漂移**（1.0.16.1–.5 未回写规格、计划内两处自相矛盾的叙事）。

| 严重度 | 数量 | 处置 |
| --- | --- | --- |
| 高 | 1 | 未排期；应在任何 Stage 7 "完成" 声明前补录 |
| 中 | 15 | 未排期；建议按第七节优先级进入后续 Task |
| 低 | 21 | 未排期；可并入相邻 Task 顺带清理 |
| 编辑·信息 | 若干 | 正文列出，无需单独排期 |

## 二、设计与计划文档评审

### 值得保持的实践

- 规格自带 Rejected Directions（§16）与 Self-review Checklist（§18），
  Non-goals（§5）明确到功能粒度；计划自带 Requirement-to-Task 覆盖表，§4 十二项
  范围、S7-D1–D9 决策、§13.1 十四门、15 条 portal 路由全部可逐一落到具名
  Task/测试，全文无 `TBD`/`TODO`。
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
| F5 | 中 | `apps/creator-web/src/main.tsx:12-52`、`apps/web-runtime-host/src/main.mjs:10-94` | Assembly 身份与 manifest 常量（productBuild `"1.0.16.5"`、platformVersion、heapBytes、resource limits、emscripten pin）在两个 Host 手工重复，需逐字节一致才能过 manifest gate；版本升级需同步两处，存在偏移风险，且与 "身份由 manifest 派生、不手工输入" 的治理要求相抵。 |
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
未特判 `-6`），行为符合规格、错误码粒度略粗。

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

## 七、建议

1. **补录收尾证据（T1、G1、G2）**：在任何 Stage 7 "完成" 声明前，从当前 `main`
   重跑 required Proof 并记录 merged-main 文档，执行并记录 §13.3 手动 canary
   验收，为验收记录追加 post-merge addendum（对齐 1.0.16.5、merge 事实与签名
   tag 的权威绑定）。这是唯一的高危项及其配套。
2. **修复 Web OPFS 发布层两处中危（F1、F2）**：调整失败清理顺序为 destination
   删除确认成功后才删 intent；为损坏的 `lmdj.storage.intent.v1` 提供与
   publication intent 一致的安全自动恢复（并统一 `TextDecoder fatal:true`）。
3. **Creator 可用性（F3、F6）**：为 restart-required 提供手动重试出口；
   RESOURCE_LIMIT 展示 observed/limit。
4. **治理回写（D2、D5、G3、G4 及规格 §17 笔误）**：把 1.0.16.1–.5 纠正候选与
   最终身份回写规格；修正 §17 的 "D1–D8" 为 "D1–D9" 与 1.0.16.0 钉死值；在
   version-management 中明确 "同 Build 纠正候选的依赖 PATCH 传播" 先例与 tag
   权威绑定规则。
5. **测试补强（T2–T5、D8）**：恢复 busy 重试的有界断言（轮数上界或 lease 释放
   验证）；补 keyboard-only 完成型旅程、packaged restart-required 旅程、
   `visibilitychange` 释放、resize/rotation 期间 Session 存活断言。
6. **计划与代码清理（D1、D3、F5、F9–F12）**：清理计划 Task 2/5R1 重复叙事与
   pagehide 陈旧措辞；双 Host 身份常量收敛为单一生成来源；移除或注释
   `beginTake` 等预留死代码、收敛重复的键盘映射与 hash 工具、避免 Creator 场景
   下 session 内部输入布线空转。

## 八、审查环境

| 项目 | 值 |
| --- | --- |
| 审查日期 | 2026-08-12 |
| 审查基线 | `main` `0b5d2d6`（含 #97/#101/#102/#115/#116） |
| Product Build | `1.0.16.5 · canary`（签名 tag `lmdj-v1.0.16.5` → `38a8c13`） |
| 设计规格 | `docs/superpowers/specs/2026-08-07-lmdj-stage7-creator-editor-design.md` |
| 实施计划 | `docs/superpowers/plans/2026-08-07-lmdj-stage7-creator-editor.md` |
| 验收记录 | `docs/quality/2026-08-07-stage7-creator-editor-acceptance.md`（锚定 1.0.16.3） |
| 参照体例 | `docs/quality/2026-08-11-stage6-web-runtime-host-review.md` |
