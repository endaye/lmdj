# LMDJ Sequence Recording Semantics Design — 2026-08-22

日期：2026-08-22

状态：待用户 review 批准；本文定义 Stage 9 Sequence 录音的产品与 Contract
边界，不分配 Product Build，不改代码

关联任务：[Issue #238](https://github.com/endaye/lmdj/issues/238)（D4 + D5）

解决的问题：

- `docs/prd/questions/recording-concurrency-semantics.md`
- `docs/prd/questions/take-event-vs-audio-bounce.md`

## 1. 结论

Stage 9 的演奏录音对标 Koala Sequence，**不是** Headless Core Proof 里的 Raw
Take。

Project Truth 只保存 Pattern 里的音符。没有独立的 Take 对象，没有录音会话的
音频 bounce。用户与 Facade 的产品语言是 **录 Sequence / Pattern**，不再使用
Take 或 Raw Take。

录音是往 **当前 Pattern 槽** 写入打击事件的会话。事件记 Pad Slot、音乐时间
（PPQ 960）、力度和音符长度。默认 BPM 120，Quantize 默认开，新音吸到最近
1/16。Quantize 关时按敲到的 tick 写入，**不**另存一份未吸格档案。

Pattern 引用 Pad Slot，不引用 Asset：换采样后，已有 Sequence 用新声音回放。
冻住当时听到的声音属于后续 Resample / Bounce 进 Pad，或 Perform Stereo WAV，
不是 Sequence 的身份。

Proof 规则「录音中任何 revision 变化都 `REVISION_CONFLICT` 并 seal Take」
不得作为产品规则。产品规则是分类并发：少数 Command 可 rebase 且录音继续；
从 Sequence 切到 Sample 会停录并 commit；未知 Authoring Command fail closed。

本设计由 2026-08-22 的 brainstorming 会话逐节批准。

## 2. Approved Decisions

| ID | 决策 |
| --- | --- |
| SR-D1 | Project Truth 不包含 Raw Take / Take 对象。录音结果只写入 `patterns`。 |
| SR-D2 | 产品与 Facade 表面只说 Sequence / Pattern 录音，不再暴露 Take。 |
| SR-D3 | Sequence 录音只记打击事件，不录麦克风，不把混音写入 Pattern。 |
| SR-D4 | Pattern 事件引用 Pad Slot。录完后改该 Pad 采样，Sequence 跟新采样走。 |
| SR-D5 | Quantize 开：新录 onset 吸到最近 1/16，原始时间丢弃。关：按敲到的 tick 写。不保留第二份 unquantized 档案。 |
| SR-D6 | 新 Project 默认 BPM 120，Quantize 默认开。 |
| SR-D7 | 音乐时间用固定 PPQ：**960 tick / 四分音符**（1/16 = 240 tick）。音符长度同为 tick。Koala 未公开内部 PPQ；960 提供与其 1/16 Quantize 对齐的公开格子。 |
| SR-D8 | Play 时可改 Sample。Play + Record 可同时开。 |
| SR-D9 | 从 Sequence Record 切到 Sample：自动 commit 当前未写入音符，停 Record，Play 继续。之后才能改 Sample 或新开麦。 |
| SR-D10 | 再按 Record：停录并 commit，Play 继续。停 Play：同时停录并 commit。 |
| SR-D11 | 切到另一 Pattern 槽：当前槽未提交音符先 commit，Record 转到新槽，不停 Record。 |
| SR-D12 | 往已有音符的 Pattern 叠录（overdub），不整槽覆盖。 |
| SR-D13 | 新敲的音立刻能听、下一圈也有；写成 Project 只发生在 SR-D9–D11 与停 Play。 |
| SR-D14 | 录音中允许改 BPM、Quantize、Swing。Core rebase，录音继续。Quantize/Swing 只影响之后的新音。BPM 改变 tick→墙钟，已写入的 tick 不动。 |
| SR-D15 | 先武装空 Pad 收音，再进 Sequence Record：Pad Capture 后台继续。收音 Pad 不进 Sequence。在 Sequence 页点该 Pad = 停采并把音频 rebase 写入该 Pad，Record 不停。此后再敲，打击才进当前 Sequence。 |
| SR-D16 | Record 仍 active 时，Trim / 换其他 Pad 采样 / 普通 `ImportAsset` 等 Sample 类 Command：Core 失败，Journal 继续，不 seal。Host 须先停录。 |
| SR-D17 | 崩溃、音频中断、Capture Ring 溢出：不写 Project。下次打开提示恢复；确认则写入对应 Pattern，拒绝则丢未提交音符。 |
| SR-D18 | 选择性 rebase 只适用于 BPM、Quantize/Swing、以及「正在进行的 Pad Capture 写入武装中的目标 Pad」。未知 Authoring Command fail closed。 |
| SR-D19 | 实施时新增 Project Contract（新 Contract ID + Schema），删除 `takes`。禁止用空 `takes: {}` 假装兼容。Pattern 事件改为 Slot + tick + 力度 + 长度。 |

## 3. 明确非目标

- 把 Proof 的严格 revision 规则提升为产品规则。
- 在 Sequence 身份里保存音频 bounce / 混音 WAV。
- 恢复或继续使用 Raw Take 作为 Project 对象。
- Stage 9 实现 Quantize 的非破坏「隐藏 Raw Take」。
- 通用 auto-rebase、last-write-wins、Host 私自 merge。
- Perform Stereo WAV、主菜单 Bounce Sequence 到 Pad 的完整产品（可在 Play 且未 Record 时后续做；与 Sequence 身份分离）。
- 改变 Stage 8B Pad Capture 的采集管线本身；本设计只规定它与 Sequence 会话的叠加顺序。
- 拍号（Beats per Bar）、Pattern 槽数量、最大小节数：仍以新内核规格 §6.2 为准（16 槽；1/2/4/8 小节），不在本次评审扩大到 Koala 的 32 槽 / 64 小节。
- 分配 Product Build、改活动 manifest、改 Portal current 页（留给决策落地 / Stage 9 实施 Task）。

## 4. 与 Koala 的对应

| Koala | LMDJ Stage 9 |
| --- | --- |
| 录 Sequence | 往当前 Pattern 写音符的会话 |
| Sequence 音符 | Pattern 事件（tick，非音频帧） |
| Quantize 开 → 最近 1/16 | SR-D5 |
| 改 BPM，Sequence 跟着变快变慢 | tick 不变，墙钟随 BPM 变 |
| 换 Pad 采样，Sequence 用新声音 | Slot 引用（已有 §6.6） |
| Resample / Bounce 到 Pad | 后续把混音采进 Pad，不是 Sequence 身份 |
| Record Song | Perform Stereo WAV（更后） |
| 无独立 Take 文件 | SR-D1 |
| 录 Sequence 时切去改 Sample，Record 停 | SR-D9 |
| 先开 Pad 收音再打 Sequence | SR-D15 |
| Overdub | SR-D12 |

## 5. 身份与数据

持久化（Project Truth）：

- Pattern：id、小节数、事件列表。
- 事件：`slot`、`onset_tick`、`duration_tick`、`velocity`（1–127）。
- Project 级：BPM、Quantize 开关、Swing。录音中改这些会占 revision。

不持久化到 Project：

- 录音会话、Journal、未确认的恢复件。
- Take id、Raw Take、音频 bounce。

录音中 Journal（bundle 内 recovery，对标现有 `recovery/active` 与
`recovery/sealed` 职责，不再叫 Take）：

- 目标 Pattern id（切槽后为新目标；已冲刷的槽已 commit）。
- 会话开始时捕获的 `expected_revision`，以及每次成功 rebase 后的 head。
- 当时的 BPM / Quantize / Swing。
- 尚未 commit 的事件。

停录、切 Sample、切槽冲刷、停 Play 之后删除 active Journal。中断则 seal 为
恢复件，不进入 `patterns`，直到用户确认。

## 6. 会话与数据流

```text
Pad 打击
  → Audio Clock → 当前 BPM 换成 tick（PPQ 960）
  → Quantize 开则 onset 吸到 240 的倍数
  → 写入会话 Journal + Runtime 叠录音符
  → 下一圈即可听到
  → 到边界：一条 Authoring Command 把本槽未提交音符写入 Pattern
  → revision +1 → Cook Snapshot
```

Runtime 在 Record 期间播放 **已提交 Pattern ∪ 本会话未提交音符**。未提交音符
不是 Project Truth。

边界：

| 动作 | 会话 | Project |
| --- | --- | --- |
| 再按 Record | 停 Record，Play 继续 | commit 当前槽 |
| 停 Play | 停 Record 与 Play | commit 当前槽 |
| 切到另一 Pattern 槽 | Record 转到新槽 | 先 commit 旧槽 |
| 从 Sequence 切到 Sample | 停 Record，Play 继续 | commit 当前槽 |
| 崩溃 / 音频中断 / Ring 溢出 | 结束，不自动 commit | 不变；seal 恢复件 |

Host 不得在一条 Command 里「先 commit Sequence 再改 Sample」。必须先完成停录
commit，再发 Sample 类 Command。Core 在会话仍 active 时拒绝 Sample 类
Command（SR-D16），作为双保险。

## 7. 与 Pad Capture 叠加

两条独立管线：

1. Sequence 会话：打击 Journal，不占用麦克风。
2. Pad Capture：麦克风或「从 App 混音」进 **某个 Pad**（Stage 8B 及后续
   Resample）。

允许的顺序（SR-D15）：

```text
Sample：空 Pad 开始收音（不发声）
  → Sequence：开 Record，敲 *其他* Pad
  → 收音后台继续；收音 Pad 的按下不进 Journal
  → Sequence 页再点该 Pad：停采，音频 rebase 写入该 Pad
  → 该 Pad 从空变为可演奏；之后的敲击进入当前 Sequence
```

停采那一下不是音符。

禁止的顺序：已经在 Sequence Record 中，再切回 Sample 去改采样或 **新开** 麦。
这走 SR-D9，会话结束。

## 8. 并发分类

录音会话钉在当前 `expected_revision` 上。Facade 仍要求每条成功 Authoring
Command 带 `expected_revision` 且原子执行。

### 8.1 不占 Project revision

Query；Workspace / Host 设置；Provider 选择；失败 Attempt；Snapshot Cook；
节拍器与纯 Transport 显示。

### 8.2 可 rebase（录音继续）

- BPM
- Quantize / Swing（只作用于之后新写入 Journal 的音）
- 正在进行的 Pad Capture **commit 到已武装的目标 Pad**

Core 把会话的 `expected_revision` 收到新 head。不是通用 rebase。

### 8.3 冲刷并继续

切到另一 Pattern 槽：对旧槽发出一次 Pattern 写入 Command，然后会话目标换成
新槽。

### 8.4 停录并 commit

再按 Record；切到 Sample；停 Play。

### 8.5 Record 仍 active 时失败（录音继续，不 seal）

`AssignPad`、Trim、`UpdatePadPlayback`、`ResetPadPlayback`、
`ImportAssignSample`、普通 `ImportAsset`、对 **非武装目标** 的 Pad 写入，以及
任何未知 Authoring Command。

失败不丢 Journal，不把会话变成恢复件。

### 8.6 中断恢复

Seal Journal。下次打开列出恢复件：确认则把事件写入记录的 Pattern 槽（该写入
带当时的新鲜 `expected_revision`）；拒绝则删除恢复件。确认前 Project 不变。

## 9. 结构

```text
Creator / CLI / MCP / Native Host
  → Application Facade（Sequence 录音会话 + 既有 Pad/Sample Command）
  → authoring-domain（Pattern 事件、BPM/Quantize、无 RawTake Command）
  → project-io（Pattern 持久化；会话 Journal / 恢复件）
  → project-cooker → audio-runtime
```

Host 不解析 `.lmdj`。现有 `take.begin` / `take.append` / `take.commit` 与
`RecordTake` 退出产品表面，由 Sequence 会话操作替换。Journal 实现可以演进自
`TakeJournal`，但对外名称与 Project schema 不得再出现 Take。

## 10. Contract

实施 Stage 9 时引入 **新的 Project Contract**（新 Contract ID，例如继
`lmdj.project.v2` 之后的下一档；精确 ID 由实施计划按
`docs/governance/version-management.md` 分配，本文不手填）。

相对 v2 的破坏性变化：

- 删除 required `takes` 与 `$defs.raw_take` / `raw_take_event`。
- Pattern 事件由 `{slot, step, velocity}` 改为
  `{slot, onset_tick, duration_tick, velocity}`。
- Project 级增加 Quantize 与 Swing 的权威字段（若实施时它们已是 Host-only，
  则退回本设计：它们在录音中可 rebase，必须是 Project Truth）。

禁止：

- 把 `takes` 留成永远为空的 `{}`。
- 继续用 48 kHz `frame_offset` 作为 Sequence 事件时间。
- Host 从音频帧推导格子后只把 step 交给 Domain 却声称 Quantize 关仍保留手感。

Facade / error Contract：`REVISION_CONFLICT` 仍用于真正的 stale revision。
录音中被拒绝的 Sample 类 Command 使用既有 typed error（例如会话 active 时的
`INVALID_ARGUMENT` 或明确的录音会话冲突码——实施计划选定一个，不新增只为
文案服务的公开码）。恢复列表走 Query，不走 Candidate→Commit 的 AI Job 路径。

## 11. 迁移

Headless Core Proof 的 `RecordTake` 已同时写入 Pattern。迁移已有 v2 bundle：

1. 保留 `patterns`；
2. 丢弃 `takes`；
3. 把整数 `step` 转为 `onset_tick = step * 240`（在 16 step/小节、4/4、
   PPQ 960 下），`duration_tick` 用实施计划选定的默认（建议一格 240 tick，
   与 one-shot 触发兼容，后续可再编辑长度）。

没有 Take 列表可展示或恢复。未提交的旧 Take Journal 若仍存在于
`recovery/`，实施计划须规定：要么按本设计提示恢复进当时的 Pattern id，要么
在无法安全对应 Pattern 时 fail closed 并保留文件待人工处理。不得静默删用户
演奏。

## 12. 测试

Stage 9 实施必须覆盖：

- 默认 120 + Quantize 开：格子外的敲击写入最近 1/16（240 tick 网格）。
- Quantize 关：保留 onset tick；Project 中无第二份事件列表。
- 叠录：下一圈听得到；停录前 revision 不变；停录后 Pattern 含新旧音且
  revision +1。
- 录音中改 BPM：rebase，录音不停；已记 tick 不变。
- 录音中关 Quantize：之后的音不吸格；之前已吸格的音不重排。
- 切槽：旧槽已 commit，新槽继续录。
- 切 Sample：停录 commit；随后 Trim 成功。
- Record active 时发 Trim：Command 失败，Journal 仍在。
- SR-D15：收音 Pad 不进 Pattern；停采 rebase 后该 Pad 可敲进 Sequence。
- 从 Record 中切 Sample 再试图新开麦：会话已结束，不再叠加。
- 崩溃恢复：确认写入 Pattern，拒绝则丢；确认前 Project 字节不变。
- 旧 Proof bundle：无 `takes`，Pattern step→tick 后可 Cook。
- Journal / Capture Ring 路径跑 `scripts/core.sh test dev stress`。

## 13. Version Management

- **本文提交（设计规格）**：Version impact: none。纯文档，不触碰活动
  manifest、Module 版本、Contract 或 Product Build。
- **决策落地 Task**（PRD 决策文件、删除问题文件、规格 §6.2/§6.5 勘误、
  Portal current 页）：仍不分配 Product Build；Version impact: none，除非
  该 Task 同时改 Assembly 或 Product 身份。
- **Stage 9 实施**（独立 Plan，不得在本决策未合入前开始）：
  - 新 Project Contract（破坏性）
  - `authoring-domain`、`project-io`、`application-facade` SemVer 主版本
  - CLI / MCP / Creator / Web Runtime / Native Host 操作名与恢复 UI
  - Product Build 必升；经 `scripts/architecture-portal.sh version` 冻结
    snapshot，禁止对该实施报 `Documentation impact: none`

精确版本号不在本文手填。

## 14. Documentation Impact

本文提交：

```text
Documentation impact: none
Reason: design spec only under docs/superpowers/specs/; durable PRD decision,
question-file removal, redesign-spec errata, and Portal current pages belong
to the follow-up decision-recording Task
```

决策落地 Task（writing-plans 产出的下一 Task）必须：

```text
Documentation impact: required
Affected portal pages: Sequence / Project Truth / Application Facade 的当前路由
（实施时从 Portal 清单派生，不手猜 path）
Reason: approved product recording model removes Raw Take and replaces the
Proof concurrency rule
```

同一 Task 还须：

- 新增 `docs/prd/decisions/YYYY-MM-DD-sequence-recording-semantics.md`
- 删除上述两个 `docs/prd/questions/` 文件
- 勘误
  `docs/superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md`
  §6.2 / §6.5（Journal 只服务会话；Record 完成写入 Pattern，不创建 Take）
- 把 `products/lmdj/README.md` 的 Proof-only 并发说明标为已被本决策取代
- 链到 Stage 9 实施 Plan / Issues；决策合入后再关 #238

## 15. 拒绝的替代

### 15.1 把 Proof 严格冲突当产品规则

拒绝。无关 Command 或 MCP 写入会把一轨演奏打成恢复件。#238 明确排除此选项。

### 15.2 Sequence 提交时必带音频 bounce

拒绝。与 Koala Sequence、§6.6 Slot 引用、§7 Perform WAV 分离冲突，并把 Web
混音录制拖进 Stage 9。

### 15.3 吸格但内部另存 Raw Take

拒绝。用户选择完全按 Koala 录音层：Quantize 开则原始时间丢弃。LMDJ 规格原
「Quantize 非破坏」由本决策在 Stage 9 录音层推翻；勘误写进 §6.2/§6.5。

### 15.4 空 `takes: {}` 留在 Project v2

拒绝。会让 Raw Take 假活着，并卡住 Pattern 事件从 `step` 迁到 tick。

## 16. 后续

1. 用户 review 本规格。
2. writing-plans：决策落地 Task（PRD + 问题文件 + 勘误 + Portal）与 Stage 9
   实施 Plan。Stage 9 不得在决策合入前把本语义写进代码。
