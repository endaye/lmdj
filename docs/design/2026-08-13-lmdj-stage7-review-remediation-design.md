# LMDJ Stage 7 Review Remediation Design

日期：2026-08-13

状态：已实施；closure evidence 已记录，剩余 physical matrix rows 明确保留

目标分支：`fix/stage7-review-remediation`

基线：`origin/main` at `3ebe27aa53bdc7c8221a01324c9e3862aa5a07eb`

## 1. 结论

本 Task 关闭
`docs/quality/2026-08-12-stage7-creator-editor-review.md` 中的全部 Stage 7 review
条目，而不是只处理两个已知 OPFS 缺陷。关闭单位是 review finding ID：每个
`D1-D10`、`F1-F15`、`T1-T7`、`G1-G5`、`N1-N4` 都必须在 closure ledger 中绑定到
实现提交、测试证据、文档修订、人工证据或明确保留的非通过边界。

PR #127 已把 F1、F2 的产品修复合入当前 `main`，G5 所需的 squash witness 机制也已
进入代码库。本 Task 不复制这些实现；它从当前树回归验证，并把结果纳入同一份闭环
记录。书面设计自审同时发现：当前顶层 merge `3ebe27a` 使 1.0.16.9 snapshot 被识别为
从 merge first parent 新引入，却没有相应 authenticated witness，现行 Portal release-docs
门因此失败。G5 只有在该实际基线断点修复并回归后才能关闭。

完成整改不等于授权 push、Pull Request、merge、tag、Release、deployment 或 Channel
promotion。这些状态变化仍分别需要明确授权。

## 2. 范围与非目标

### 2.1 范围内

1. 修复 Creator restart、reducer、错误呈现、Project Surface 与动作互斥问题；
2. 收敛 Web Host 身份、输入映射、完整性工具与 Runtime 输入所有权；
3. 加固 native/Web storage 的 hardlink、lease ownership、错误优先级和状态映射；
4. 删除或收敛 Stage 8/9 预留死代码；
5. 补齐 review 指出的浏览器、组件、状态机、生命周期与清理测试；
6. 回写 Stage 7 规格、实施计划、版本治理、验收记录和架构门户；
7. 生成逐 finding 的可审计闭环记录，并从最终 merged `main` 重跑 required Proof；
8. 为人工 canary 生成 privacy-safe 记录，且保持五项实体设备门为
   `deferred / unverified`。

### 2.2 非目标

- 不新增 Stage 8 Sample、Stage 9 Take/Sequence 或 Stage 10 Perform 能力；
- 不改变 `lmdj.project.v1` 或 `lmdj.project-bundle.v1` Contract 语义；
- 不把诊断 Host 改造成 Creator Host；
- 不用新的 UI 行为掩盖底层 Project I/O 或 Runtime 错误；
- 不把合成 bfcache、合成 MIDI、Playwright key event 或视觉检查描述成真实 Safari、
  iPadOS、物理 MIDI、听感或实体设备通过；
- 不在本 Task 内自动创建 tag、发布 Release、部署或晋级 Channel。

## 3. 当前基线与证据边界

整改以当前 `main` 为唯一代码基线，不以 review 当时的 `5bf4ace` 或历史 Stage 7 tag
作为实现起点。基线已经包含：

- PR #127 的 F1/F2 OPFS recovery 修复及对应 Product Build 传播；
- G5 的 squash projection witness 与 fail-closed 校验实现；当前 `3ebe27a` merge 对
  1.0.16.9 缺少可验证的 introducing-revision binding，仍需修复；
- 后续 Web Runtime hardening 和 active-tree 校验变更；
- Product Build `1.0.16.9` 的当前 manifests 与 Portal snapshot。

因此 review 原文是发现来源，不是当前状态真相。整改开始时先重放每条 finding 的最小
复现或结构检查；已被当前 `main` 解决的条目只补回归证据，不反向恢复旧实现。

证据严格分层：

| 层级 | 能证明什么 | 不能证明什么 |
| --- | --- | --- |
| Unit/component | reducer、错误投影、映射、清理与边界条件 | packaged browser journey |
| Packaged browser | 用户可见 Creator control 与真实 Worker/Wasm/OPFS 路径 | 实体 Safari、物理 MIDI、听感 |
| Full Proof | 当前 revision 的 Core、Host、Creator 与治理门禁 | merged `main` 的 revision truth |
| Merged-main Proof | 合并后 `main` 的可重复门禁 | 人工/实体设备结果 |
| Manual canary | 指定 clean package 上的人工 Creator journey | 五项实体设备门，除非逐项真实执行 |

## 4. Closure Contract

每条 finding 只有满足下列一种闭环形态才可标为 closed：

1. **Code + test**：产品修复与失败先行的回归测试同时落地；
2. **Test-only**：实现已经正确，但缺失的显式断言已补齐；
3. **Documentation/governance**：行为正确，规格、计划、版本或发布叙事被修正；
4. **Verified upstream fix**：修复已经在当前 `main`，本 Task 记录当前树的复现消失与
   回归门禁；
5. **Explicit boundary**：工具无法产生真实证据时，保留 `deferred / unverified`，记录
   原因、责任人和解除条件。该状态不是 pass，也不能关闭本来要求通过的 T1。

Closure ledger 至少包含：finding ID、原严重度、处理类别、变更文件、验证命令、证据
revision、结果和剩余边界。任何 ID 缺行、使用模糊的“相关测试已过”或把未验证状态写成
通过，都会使整改失败。

### 4.1 Finding ownership map

| ID | Primary owner | 预期闭环 |
| --- | --- | --- |
| D1 | Stage 7 plan | 合并重复的 R1 Task 与 TDD 时序 |
| D2 | Stage 7 spec/plan | 回写 post-freeze Build 历史与最终身份 |
| D3 | Stage 7 plan | 修正 persisted/non-persisted pagehide 叙事 |
| D4 | Stage 7 plan | 把纠正候选收敛为可审计 Task 记录 |
| D5 | Stage 7 spec | 成文 managed ASCII Bundle path subset |
| D6 | lifecycle browser spec | 明确 reload/reopen 用户旅程 |
| D7 | burst browser spec | 补齐四项 burst 断言映射 |
| D8 | responsive browser spec | 活动 Session 中 resize/旋转回归 |
| D9 | Creator error tests | 三个缺失 typed error 行为 |
| D10 | Runtime cleanup tests | BroadcastChannel 显式清理证据 |
| F1 | Project I/O regression | 验证 PR #127 publication cleanup 顺序 |
| F2 | Project I/O regression | 验证 PR #127 torn intent recovery |
| F3 | Creator runtime | 手动 restart retry 与 epoch reset |
| F4 | Creator reducer | 显式合法源状态与 fail-closed action |
| F5 | Assembly tooling | 从 manifests/locks 生成共享 identity |
| F6 | Creator ErrorPanel | observed/limit 与 storage condition 投影 |
| F7 | native Project I/O | managed-tree hardlink rejection |
| F8 | Bundle reader | 修正 segment-aware path guard |
| F9 | Runtime session/state machine | 删除未进入 active Facade 的 Take 死代码 |
| F10 | Web input module | 单一 keyboard mapping truth |
| F11 | Runtime session | 显式 Host input ownership，零闲置 listener |
| F12 | Web integrity module | 单一 hash/canonical/exact-key truth |
| F13 | Runtime lifecycle | event notification 取代 16 ms polling |
| F14 | Creator project actions | auto-reopen 共用互斥 ownership lane |
| F15 | Project Surface/spec | 显示 BPM；成文无虚假 Save Local |
| T1 | Manual canary evidence | 真实人工十步记录；未执行前保持 open |
| T2 | lifecycle browser spec | 有界 retry，去 fixed sleep，恢复 alert 断言 |
| T3 | accessibility browser spec | keyboard-only import/open/Bank journey |
| T4 | Creator packaged browser | restart-required/reopen/audio inactive |
| T5 | input controller tests | visibilitychange 释放 pressed state |
| T6 | acceptance evidence | 标注 synthetic bfcache 证明边界 |
| T7 | acceptance evidence | 标注 synthetic key-repeat 证明边界 |
| G1 | merged-main evidence | historical Proof recovered and bound; current Build keeps a separate exact-merge gate |
| G2 | Stage 7 acceptance | current external state addendum |
| G3 | version governance | BUILD/PATCH Assembly 规则消歧 |
| G4 | version/release evidence | 权威 tag 与 source/snapshot/Proof binding chain |
| G5 | Portal provenance regression | 修复 1.0.16.9 merge provenance，并验证 witness 机制 |
| N1 | Web Project I/O | publish lease owner binding |
| N2 | Web Project I/O | 保留 already-exists 错误优先级 |
| N3 | Web status adapter | 集中 owner-mismatch 状态映射 |
| N4 | Project I/O Web tests | 复用 mutation result helper |

## 5. 产品与平台整改设计

### 5.1 Creator recovery 与状态机（F3、F4、F14）

`HOST_RESTART_REQUIRED` 保留“一次自动恢复”的循环保护，同时增加明确的人工
`Retry Runtime` 出口。自动恢复预算属于一次 failure epoch；成功进入稳定 running 后
清零。人工 Retry 创建新的恢复 epoch，但不会在无用户动作时无限重建。

Creator reducer 用显式 transition table 定义每个 UI action 的合法源状态。非法 action
在 reducer 边界 fail closed，既不改变 UI truth，也不到达 Platform。上游 selector、
disabled control 和 Platform 权威状态机继续保留，形成三层一致防御。

restart 后的自动 reopen 与用户 Open/Import 共用一个 project-action ownership lane。
同一时刻只能有一个 Project 动作改变 Creator 状态；过期 generation 的异步完成不能
覆盖新 generation。

### 5.2 Error presentation（F6、D9）

Creator ErrorPanel 对公开 typed error 做穷举投影：

- `WEB_RUNTIME_RESOURCE_LIMIT` 显示资源名、observed 与 limit；
- Project I/O 错误显示 `storage_condition`，包括 quota 与 invalid-state；
- `HOST_PROTOCOL_MISMATCH`、`IO_ERROR`、`INTERNAL_ERROR` 有稳定、可操作且不泄漏
  内部路径的用户文案；
- Retry 只在动作确实可恢复时出现，restart retry 与 project-busy retry 语义分离。

测试直接输入结构化 details，断言可见文本和按钮语义，不只断言 error code 字符串。

### 5.3 Identity 与共享常量（F5、F10、F12）

Host 不再手写共享 Assembly 数值。构建工具从 active Product/Module/Host manifests、
Assembly lock、资源限制和 Emscripten lock 生成一个确定性的 Web Runtime identity
artifact。Creator 与诊断 Host 只声明各自的 host-specific contract 和 expected assets，
共享的 Product Build、Platform version、heap、resource limits 和 toolchain identity
从生成物消费。校验器在生成物过期或与 manifests 不一致时 fail closed。

Keyboard mapping 移入单一产品中立模块，Creator controller 和 Runtime 默认 adapter
消费同一冻结值。`sha256`、canonical JSON 与 exact-key 检查移入无 Host 依赖的共享
完整性工具，Bundle reader 与 Runtime session 不再维护分叉副本。

### 5.4 Runtime ownership 与 lifecycle（F9、F11、F13、D10）

Creator 显式选择由自己拥有 Pointer/Keyboard/MIDI adapters；Runtime session 在该模式
下不注册第二套 window listener 或内部 adapters。诊断 Host 继续使用 session-owned
输入，两个 Host 的所有权选择均可测试且 close/restart 对称释放。

Stage 8/9 尚未进入 active Facade 的 `beginTake`、`stopTake` 和仅测试可达分支从 Stage 7
运行面删除；未来阶段按其批准设计重新引入，不以死代码预埋。

recovery probe 从 16 ms polling 改为 session-owned lifecycle notification。订阅在 Host
generation 建立时注册，在 close/restart/unmount 时注销；过期 generation 的通知被丢弃。
清理测试显式覆盖 Worker、MIDI listener、BroadcastChannel、AudioContext 和 lifecycle
subscriber。

### 5.5 Project surface 与规格一致性（F15）

已打开 Project 的 summary 显示 BPM，与 Project list 和 Status Bar 的同一 Project Truth
投影一致。Stage 7 没有 Project mutation 和显式 save 操作，因此不添加假的
`Save Local` control；原规格改写为“已打开浏览器本地 Project 的状态与持久化说明”，
并明确保存能力属于后续有 mutation 的阶段。

### 5.6 Storage hardening（F1、F2、F7、F8、N1-N4）

F1/F2 使用 PR #127 已合入实现，只补当前树 fault/recovery 回归。其余 storage 处理如下：

- native managed-tree 对 regular file 拒绝 `st_nlink > 1`，与 wire 无 hardlink 表达能力
  保持一致；
- Bundle path 负向前瞻修正为 segment-aware 形式，并保留权威 C++ 复验；
- `publishDirectoryIfAbsent` 必须验证 covering lease 的 `platformIdentity`，不得只验证
  租约存在；
- `createImmutable` 在不发生 mutation 时保留 `already_exists` 的既有可观察优先级，
  真正写入前仍必须通过 lease owner 校验；
- Web 内部 owner-mismatch 状态在单一适配点转换为公开 `project_busy`，extern wrapper
  不再逐处手写 `-7 -> -3`；
- C++ Web tests 复用统一 `mutation_result()` JSON 组装 helper。

## 6. 测试整改设计

### 6.1 缺失行为覆盖（D6-D10、T2-T5）

新增或加强的 packaged-browser/component 覆盖必须包括：

1. reload 后通过可见 control reopen Project，restart-required 后 reopen 且 Audio 不自动
   activate；
2. 16-key burst 的 16 admissions、16 outcomes、0 rejection 与 Host running；
3. ready/active Project 中发生 viewport resize、portrait/landscape 变化后 Project 与
   Audio session 均不关闭；
4. Creator 对三类缺失 error code 与完整 details 的呈现；
5. close/restart 后 BroadcastChannel 与其他四类资源的零残留；
6. `PROJECT_BUSY` retry 有明确 attempt/deadline 上限，不用固定 250 ms 盲等；每轮保留
   typed error 断言，成功后断言 alert 最终清除；
7. 仅用 Keyboard 完成 Import、Open 和 Bank selection 的完整 journey；
8. `visibilitychange` 与 blur 均释放 pressed state；
9. packaged Creator 的 restart-required journey，不用诊断 Host 替代。

### 6.2 工具能力边界（T6、T7）

Playwright 的合成 persisted `pagehide/pageshow` 和程序化 key repeat 继续作为自动化
contract test，但测试名、注释和验收记录必须说明其模拟边界。它们不能声称真实 bfcache
导航、OS auto-repeat 或物理键盘通过。能在稳定 CI 中增加真实 browser traversal 时再
升级证据，不以不稳定 sleep 模拟真实能力。

### 6.3 Manual canary（T1）

最终 clean Creator package 生成带 revision、Product Build、manifest hash、浏览器版本、
步骤结果与 privacy-safe report hash 的 canary 表。人工操作者按原规格 §13.3 完成十步，
特别记录听到的地址/声音、重复/漏触发、卡住 press、autoplay 和 Project 数据保持。

在人工操作者实际执行并签署前，T1 保持 open；自动截图、日志或 headless browser 不得
代替听感与用户动作。五项 Stage 6 实体设备 rows 仍单独保持
`deferred / unverified`，不因 T1 完成而自动升级。

## 7. 规格、计划与治理回写

### 7.1 Stage 7 spec/plan（D1-D7）

原设计和实施计划改成“已交付规格 + 纠正 addendum”的单一一致叙事：

- 删除 Task 2 与 Task 5R1 的重复/逆序 TDD 协议；
- 把 post-freeze 候选和最终 Product Build 历史回写规格，不再钉死 `1.0.16.0`；
- pagehide 文字明确为 persisted 时保留共享 Runtime，非 persisted terminal pagehide 才
  close；
- 1.0.16.2/.4/.5 纠正段补成可审计的 Files/Steps/RED-GREEN 记录，或归并进其实际
  owning Task；
- Bundle path Contract 明确为受管 ASCII path subset，而不是泛称任意 UTF-8 path；
- reload/reopen、burst、resize、错误码和 BroadcastChannel 均建立明确 test mapping。

历史计划的已执行事实不会被伪装成事前计划；addendum 标明 retrospective correction、
实际 commit/PR 与为何需要修订。

### 7.2 Version governance（G2-G4）

版本政策消除“PATCH 可承载 Assembly 变化”的歧义：Product Assembly 或依赖身份变化
必须分配新 BUILD；PATCH 仅用于不改变 Assembly identity/lock 和公开 Contract 的同一
Build 缺陷修复。历史 `1.0.16.x` 作为已发生事实保留，并在验收 addendum 解释，不重写
tag 或 snapshot。

发布证据建立单一 binding chain：Product Build、权威 signed tag、tag revision、合并
PR、source revision、snapshot provenance、squash witness（如适用）和 merged-main Proof
revision。tag 指向测试-only follow-up 的历史事实可以记录，但新流程必须在 merged-main
Proof 成功后才允许创建 Product tag。

对当前基线，1.0.16.9 metadata 记录的 source revision 是 `b2294005c09975d8414105861a0b4c0939cabd7f`，
而 snapshot metadata path 在现行拓扑中由单父提交
`ea2293448b374d7963e029db6c0eb1fb11002e04` 首次加入；后续双父 merge
`3ebe27aa53bdc7c8221a01324c9e3862aa5a07eb` 不是 provenance 校验器定义的 introducing
revision。第一项治理 Task 必须用现有 authenticated generator 为精确的
source/introducing revision 对创建
1.0.16.9 authenticated witness，验证它能重建 source commit/tree；不得重写 immutable
snapshot 或 metadata 来让门禁变绿；现有 release-docs verifier 对错误 identity 保持
fail closed。

Stage 7 acceptance External state 更新为查询当时的准确状态，不把旧的“未合并”叙述
保留为 current truth。历史事实与 current state 分栏，避免时间漂移。

### 7.3 Merged-main Proof（G1）

2026-08-13 的 GitHub Actions 原始记录更正了 review 的历史前提：签名 tag
`lmdj-v1.0.16.5`/`lmdj-v1.0.16.8` 的精确 revisions 已分别有 successful
full-mode `main` push run `31327104838`/`31529410253`。因此 G1 是
documentation binding gap, not a Proof execution gap；本整改 evidence/ledger
完成 historical Proof recovered binding，不再把历史运行写成未执行。

这个更正不放宽当前 Product Build 的集成门禁。分支 Proof 只能证明候选；
当前纠正后的 `1.0.19.0` 代码合并后仍必须从 exact merged `main` revision 重跑 required Proof，
并提交独立 evidence addendum。由于创建该 evidence commit 会再次推进 `main`，
记录必须区分：

1. 被验证的 product/source merge revision；
2. 只新增 evidence 的 documentation revision；
3. 门禁命令、runner/toolchain identity 与日志摘要。

任何 Product tag 必须晚于并绑定这条 merged-main Proof；本整改 Task 本身不自动创建
或移动 tag。

## 8. 数据与控制流

```text
active manifests + assembly lock + toolchain lock
                    |
                    v
       generated Web Runtime identity
          |                         |
          v                         v
     Creator Host            Diagnostic Host
          |                         |
          +------ Runtime Session -+
                    |
          explicit input owner mode
                    |
       Project/Audio lifecycle events
                    |
          Creator reducer transition table
                    |
          user-visible state and errors
```

Project Truth、Runtime Snapshot 和 Attempt state 的既有边界不变。错误 details 属于
Attempt/UI projection，不写回 Project Truth；generated identity 属于 Product Assembly
构建输入，不进入 Project bundle。

## 9. Implementation and Commit Strategy

实施计划把整改拆成可独立 review 的短 Task；每个实施 Task 恰好形成一个 reviewable
Conventional Commit，并只包含该 Task 声明的 finding 与文件。开发过程使用 TDD：先写
能复现 finding 的最小失败测试，确认失败原因正确，再写最小实现并运行 Task-specific
gate。Task 之间按依赖顺序推进，不能把尚未验证的后续整改混入当前提交。

推荐执行顺序：

1. closure harness 与 F1/F2/G5 当前树基线；
2. storage hardening；
3. Creator state/recovery/error/ownership；
4. identity 与共享模块收敛；
5. packaged-browser coverage；
6. spec/plan/governance/Portal 回写；
7. version allocation、snapshot、full candidate Proof；
8. 人工 canary；
9. 经授权 PR/merge 后的当前 Product Build future merged-main Proof 与 evidence addendum。

### 9.1 Human Canary correction addendum

第一次 `1.0.18.0` 人工 Canary 证明了一个此前自动化未覆盖的 generation ownership
缺口：Import 被 Runtime Session replacement 中止后，旧 generation 仍必须清理自己拥有的
transient transfer UI state。action token 只负责拒绝旧异步结果，不得同时阻止该 cleanup；
否则新 Session 虽已完成 startup/list，Creator 仍会永久显示 `importing` 并禁用操作。

该实现修复将 Creator Web Host 从 `1.1.0` 提升为兼容 bugfix `1.1.1`。按 Assembly
identity 治理，已冻结且经过人工缺陷复现的 Product Build `1.0.18.0` 不得重写或复用，
因此分配 `1.0.19.0`。Contract、Project I/O、Web Runtime Platform、Web Runtime Host、
Provider 与 model identities 不变。`1.0.18.0` 保留为 abandoned / unshipped
failed-canary 历史记录；其首轮步骤 1–6 只能作为诊断观察。纠正后的 `1.0.19.0`
必须重新完成 snapshot、完整 automated candidate Proof，并从步骤 1 执行全部十步 T1。

## 10. Version Management

Version impact: required.

原因：本 Task 修改 Product Assembly 消费的 Creator Host、Web Runtime Platform、
Project I/O 与生成身份，并更新相关模块/Host identity。根据当前治理规则，它必须分配
新的 Product BUILD，而不能继续增加 `1.0.16.9` 的 PATCH。独立 Module/Host 版本按其
公开或实现变化分别分配 SemVer PATCH/MINOR；Contract identity 不变。

具体版本号不得在设计阶段猜测。实施计划开始前从 current `main` 的 tags、
`products/lmdj/version.json`、active manifests、Assembly lock 和已分配/放弃表计算下一个
可用 BUILD，并在第一次版本写入前锁定。任何其他 PR 先占用编号时必须重新分配，编号
不得复用。

准备团队 canary 时，在 clean committed source boundary 运行：

```bash
scripts/architecture-portal.sh version PRODUCT_BUILD canary
```

该快照不授权 tag、Release、deployment 或 Channel promotion。

## 11. Documentation Impact

Documentation impact: required.

Affected portal pages:

- `/hosts/creator-web/`
- `/hosts/web-runtime/`
- `/core/modules/project-io/`
- `/core/modules/web-runtime-platform/`
- `/platform/input/`
- `/platform/storage/`
- `/assembly/lmdj/`
- `/operations/testing-and-proof/`
- `/operations/version-and-release/`

Reason: Creator lifecycle/error behavior、Web storage ownership、Host identity source、
测试证据、版本/发布门禁和 Product Assembly identity 都发生变化。current pages、diagram
sources、generated outputs 与新 Product Build snapshot 必须在同一 Task 保持一致。

## 12. Verification Gates

候选至少运行并记录：

```bash
bash scripts/verify-core-dependencies.sh
bash tests/build/test_active_tree.sh
python3 tests/build/version_test.py
python3 scripts/version.py verify --version-file products/lmdj/version.json
scripts/core.sh proof
scripts/web-runtime-host.sh proof
scripts/creator-web.sh proof
scripts/architecture-portal.sh check
```

另外运行所有被修改 Module/Host 的 unit/component tests、native/Web Project I/O fault
matrix、Chromium packaged Creator journeys、WebKit capability-boundary、deterministic clean
package comparison和 stress/ASan lanes 中与并发或 storage ownership 有关的测试。最终
完成声明必须引用本次新鲜输出，不引用历史绿色结果。

## 13. Completion Criteria

本 Task 只有在以下条件全部满足时才完成：

- 41 个 review ID 全部出现在 closure ledger；
- F1/F2 以 current-main 证据闭环，G5 的 1.0.16.9 provenance 断点已修复，其余 finding
  有对应修复、测试或治理记录；
- T1 有真实人工 canary 记录；五项实体设备 rows 仍准确标为
  `deferred / unverified`；
- 新 Product Build、Module/Host versions、Assembly lock、current Portal 与 immutable
  snapshot 一致；
- candidate full Proof 通过；
- 经授权合并后，exact merged `main` 的 required Proof 与 evidence addendum 通过；
- 不存在未解释的测试弱化、固定 sleep、未拥有的 listener 或手填 Assembly identity；
- 未经授权不发生 push、PR、merge、tag、Release、deployment 或 Channel promotion。

## 14. Self-review Checklist

- [x] 全部 finding families 有明确 owner 和闭环形态。
- [x] PR #127 与 G5 的既有修复不被重复实现。
- [x] 人工、自动化、merged-main 和实体设备证据边界分离。
- [x] Product Build、Module、Host、Contract 与 Channel 身份未被猜测。
- [x] Version impact 与 Documentation impact 均有具体理由。
- [x] Stage 8/9/10 能力未被带入整改范围。
- [x] 外部状态变化仍保留独立授权门。
