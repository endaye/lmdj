# LMDJ Sequence Recording Semantics Design — 2026-08-22

日期：2026-08-22

修订：2026-08-23 补齐会话所有权、flush 幂等、恢复指纹、切槽音乐边界、
SR-D15 与 Stage 8B trimming、BPM 锚点、事件量化/overdub 不变量；复审后再锁定
manifest commit point、Swing、整数时钟、迁移归一化与 fingerprint 字节

状态：待用户再次 review；本文定义 Stage 9 Sequence 录音的产品与 Contract
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
从 Sequence 切到 Sample 会停录并 flush；未知 Authoring Command fail closed。
会话是 **Project 级** 的：落在 bundle Journal 上，受 writer lease 保护，CLI
与 MCP 与第二窗口看见同一份 active/recoverable 状态。

本设计由 2026-08-22 的 brainstorming 会话逐节批准；2026-08-23 按两轮 review
补入 SR-D20–D28，未改 SR-D1–D5 / D12 / D18 / D19 的方向。

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
| SR-D9 | 从 Sequence Record 切到 Sample：按 §8.6 flush 当前未写入音符，停 Record，Play 继续。之后才能改 Sample 或新开麦。 |
| SR-D10 | 再按 Record：停录并 flush，Play 继续。停 Play：同时停录并 flush。 |
| SR-D11 | 切到另一 Pattern 槽是 **selection request**。默认在下一 Bar 生效（新内核规格 §6.3）。在 **同一个** 音乐边界上：commit 旧槽、Journal 改目标、Runtime 改播放。生效前仍听旧 Pattern、仍录进旧槽。 |
| SR-D12 | 往已有音符的 Pattern 叠录（overdub），不整槽覆盖。 |
| SR-D13 | 新敲的音立刻能听、下一圈也有；写成 Project 只发生在 SR-D9–D11 与停 Play。 |
| SR-D14 | 录音中允许改 BPM、Quantize、Swing。Core rebase，录音继续。Quantize/Swing 只影响之后的新音。BPM 改变 tick→墙钟，已写入的 tick 不动。 |
| SR-D15 | 先武装空 Pad 收音，再进 Sequence Record：Capture 后台继续。收音 Pad 不进 Sequence。在 Sequence 页点该 Pad = **停采并进入 Stage 8B trimming overlay**（不切到 Sample 表面，不触发 SR-D9）。用户确认 ≤5 s 提交后，Pad 写入 rebase 会话；此后再敲才进 Sequence。 |
| SR-D16 | Record 仍 active 时，Trim / 换其他 Pad 采样 / 普通 `ImportAsset` 等 Sample 类 Command：Core 失败，Journal 继续，不 seal。Host 须先停录。 |
| SR-D17 | 崩溃、音频中断、Capture Ring 溢出、owner 丢失：已由 manifest head 提交的 flush 保持有效；未提交 tail 不写 Project 并 seal。每个已接受 Pad event 必须先把其 canonical recoverable tail 耐久写入 Journal，才可向 Host acknowledgement；未释放 press 以 §10.1 的 240-tick 默认时值进入 tail，release 以后一条单调 tail snapshot 替换时值。下次打开提示恢复。确认时按 SR-D22 匹配目标 Pattern，**禁止**仅凭新鲜 revision 写回。拒绝则丢未提交音符；partial/torn tail 必须保留并以可操作证据 fail closed，不得静默截断。 |
| SR-D18 | 选择性 rebase 只适用于 BPM、Quantize/Swing、以及「正在进行的 Pad Capture 写入武装中的目标 Pad」。未知 Authoring Command fail closed。 |
| SR-D19 | 实施时新增 Project Contract（新 Contract ID + Schema），删除 `takes`。禁止用空 `takes: {}` 假装兼容。Pattern 事件改为 Slot + tick + 力度 + 长度。 |
| SR-D20 | 一个 Project 同时只允许一个 active Sequence session。会话落在 bundle `recovery/active`，受 writer lease 保护。Authoring admission 必须在 **同一把写锁** 内检查 active Journal 与 `expected_revision`。 |
| SR-D21 | 每次 flush 有稳定 `session_id` + `flush_seq` + `command_id`。先把 flush 意图耐久写入 Journal，再写 Project。重复提交返回原 receipt。若一次 execute 在 commit point 前失败而录音继续，后续 flush 必须是先前 unresolved flush 与最新 tail 的 canonical 累积批次。任一 receipt 可见时按同一 session/pattern/expected-revision 的 canonical key/value coverage 双向 resolve：较晚 completion 可 supersede 它 key-cover 的较早批次；较早 completion 可 resolve 已耐久、event key/value 全被其精确覆盖的等价较晚 retry，并从非等价较晚批次中只扣除精确已提交 event、保留真正新增或同-key 不同值的 residual。只有 manifest head 已耐久且 reload 可见 receipt 才算 completed；Journal 只在全部 flush completed/superseded 或只剩未提交 residual 后删除/seal。 |
| SR-D22 | Journal 保存目标 Pattern 的 `pattern_id`、`bars`、以及上次耐久 flush（若无则 begin）时事件的 canonical fingerprint。恢复区分：指纹匹配可 append；不兼容变化给用户选新槽或放弃；删除/越界 fail closed 并保留恢复件。 |
| SR-D23 | 切槽的 commit、Journal 改目标、Runtime 改播放三者只在 SR-D11 的 effective transport boundary 发生，禁止点击瞬间换 Journal 而播放仍等到下一 Bar。 |
| SR-D24 | SR-D15 **不**推翻 Stage 8B 的 trimming / ≤5 s / 显式提交 / 冲突保留缓冲。只增加 Sequence 页内 overlay，避免走到 Sample 表面。 |
| SR-D25 | Transport 的 musical tick 是权威时钟。BPM Command 在生效点冻结不丢余数的整数有理数锚点；之后只从该锚点积分，禁止浮点或每段重新取整。 |
| SR-D26 | Pattern 事件边界与 overdub 合并是 Contract 不变量（见 §10.1），必须有跨语言测试向量。 |
| SR-D27 | Swing 是录入时烘焙进 **之后新写入事件** onset 的 Project 级设置，不是回放时重排旧事件的全局效果。Contract 字段为整数 `swing_percent`：50–75，默认 50（直拍）；仅在 Quantize 开时作用于奇数 1/16。 |
| SR-D28 | v2→新 Contract 是总迁移：缺失的 Quantize / Swing 分别取 `true` / `50`；旧 Pattern 的重复 `(slot, step)` 按原数组顺序 last-write-wins，再转 tick、补 duration、canonical 排序。 |

## 3. 明确非目标

- 把 Proof 的严格 revision 规则提升为产品规则。
- 在 Sequence 身份里保存音频 bounce / 混音 WAV。
- 恢复或继续使用 Raw Take 作为 Project 对象。
- Stage 9 实现 Quantize 的非破坏「隐藏 Raw Take」。
- 通用 auto-rebase、last-write-wins、Host 私自 merge。
- Perform Stereo WAV、主菜单 Bounce Sequence 到 Pad 的完整产品（可在 Play 且未 Record 时后续做；与 Sequence 身份分离）。
- 推翻 Stage 8B 的 trimming、5 s 选区、显式提交、冲突保留缓冲（SR-D24）。允许的只是 Sequence 页内 overlay。
- 崩溃后自动 resume 同一 session（必须走恢复确认）。
- 切槽时立即改 Journal 目标、播放仍等到下一 Bar。
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
| 先开 Pad 收音再打 Sequence | SR-D15 / SR-D24 |
| SEQ SNAP / 下一 Bar 再切 Sequence | SR-D11 / SR-D23（LMDJ 默认下一 Bar） |
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
`recovery/sealed` 职责，不再叫 Take）至少包含：

- `session_id`（begin 时 Host 提供的 UUID）。
- 当前目标 `pattern_id`；已 flush 的槽不再出现在未提交事件里。
- 捕获并随 rebase 更新的 `expected_revision`。
- 当时的 BPM / Quantize / Swing。
- 尚未 commit 的事件。
- 单调 `tail_seq` / `input_sequence` 与每次已 acknowledgement 后的 canonical
  tail snapshot；press 未释放时使用 §10.1 的 240-tick 默认时值，release snapshot
  替换同一事件的真实时值。
- 目标 Pattern 在上次耐久 flush（若无则 begin）时的 `bars` 与
  `pattern_fingerprint`（见 §8.7）。
- 每个 pending/completed flush：`flush_seq`、`command_id`、目标
  `pattern_id`、该批事件、状态。

停录、切 Sample、切槽 flush、停 Play 之后，**不得**在 Project 耐久 commit
之前删除 Journal。中断或 owner 丢失则 seal 为恢复件，不进入 `patterns`，
直到用户确认或拒绝。

## 6. 会话与数据流

```text
Pad 打击
  → transport musical tick（权威；见 SR-D25）
  → Quantize 开则 onset 按 §10.1 吸格
  → 先耐久写入会话 Journal tail，再 acknowledgement 并发布 Runtime 叠录音符
  → 下一圈即可听到
  → 到 flush 边界：Journal 先记下 command_id，再一条 Command 写入 Pattern
  → revision +1 → Cook Snapshot
  → 确认 manifest head 耐久且 reload 可见 receipt 后才结束/清理 Journal
```

Runtime 在 Record 期间播放的是 §10.1 定义的 **committed Pattern 与 Journal
按 (slot, onset_tick) 合并结果**。未提交音符不是 Project Truth。

权威时钟（SR-D25）：不以「会话开始墙钟 × 当前 BPM」换算 tick。BPM Command
在写锁内生效时冻结锚点 `(audio_frame F, musical_tick_numerator N, bpm B)`。
固定分母 `D = 48000 * 60 = 2880000`；`N` 是以 `1/D tick` 为单位的非负整数。
之后只做 checked integer arithmetic：

```text
tick_numerator(frame) = N + (frame - F) * B * 960
raw_tick(frame) = floor(tick_numerator(frame) / D)
```

在 BPM Command 的生效 frame `F2`，先按旧锚点算出 **完整** `N2`，再建立
`(F2, N2, new_bpm)`；不把 `N2 / D` 取整后再开新段。已写入 Journal / Pattern
的 tick 不因后来的 BPM 重算。Quantize 关时事件 onset 取 `raw_tick`，即分数 tick
向更早的整数 tick 取整；改 BPM 后时间连续、余数连续，不得跳格。实现禁止用
float / double 代替上述整数算法。

边界：

| 动作 | 会话 | Project |
| --- | --- | --- |
| 再按 Record | 停 Record，Play 继续 | flush 当前槽后清理 Journal |
| 停 Play | 停 Record 与 Play | 同上 |
| 切到另一 Pattern 槽 | 下一 Bar（默认）同时改 Journal 目标与 Runtime | 边界上 flush 旧槽 |
| 从 Sequence 切到 Sample | 停 Record，Play 继续 | flush 当前槽后清理 Journal |
| 崩溃 / 音频中断 / Ring 溢出 / owner 丢失 | 结束，不自动 commit 未提交 tail | 已提交 flush 不变；未提交 tail seal 为恢复件 |

Host 不得在一条 Command 里「先 commit Sequence 再改 Sample」。必须先完成停录
flush（§8.6），再发 Sample 类 Command。Core 在 **持有写锁且 Journal active**
时拒绝 Sample 类 Command（SR-D16），对 CLI/MCP/第二窗口同样生效。

## 7. 与 Pad Capture 叠加

两条独立管线：

1. Sequence 会话：打击 Journal，不占用麦克风。
2. Pad Capture：麦克风或「从 App 混音」进 **某个 Pad**（Stage 8B 及后续
   Resample）。

允许的顺序（SR-D15 / SR-D24）：

```text
Sample：空 Pad 开始收音（不发声）
  → Sequence：开 Record，敲 *其他* Pad
  → 收音后台继续；收音 Pad 的按下不进 Journal
  → Sequence 页再点该 Pad：停采 → Stage 8B `trimming` overlay
     （仍在 Sequence 表面，不触发 SR-D9）
  → 用户选出 ≤240,000 帧并确认提交
  → sample.import 用当刻 expected_revision 写入该 Pad
  → 成功则 Sequence 会话 rebase；冲突则缓冲保留、用户重试、会话继续
  → 提交成功后该 Pad 可演奏；之后的敲击进入当前 Sequence
```

停采那一下不是音符，也 **不是** Pad 写入。未确认 trimming 之前 Pad 仍视为空，
不进 Sequence。

禁止的顺序：已经在 Sequence Record 中，再切回 **Sample 表面** 去改采样或
**新开** 麦。这走 SR-D9，会话结束。

Stage 8B 状态机（`recording` → `trimming` → `committing` / `commit-error`）
保持有效。本设计只规定 overlay 的宿主表面是 Sequence，以及提交成功后必须
rebase 会话。

## 8. 并发分类

录音会话钉在当前 `expected_revision` 上。Facade 仍要求每条成功 Authoring
Command 带 `expected_revision` 且原子执行。

### 8.0 所有权（SR-D20）

一个 Project **同时只有一个** active Sequence session。

| 主体 | 如何发现 | 写权限 |
| --- | --- | --- |
| 持有 writer lease 的 Host | Facade Query `sequence.record.status` 返回 session | begin / append / flush / 白名单 rebase |
| 其他窗口、CLI、MCP | 同一 Query：`active` 或 `recoverable` | 没有 lease → 既有 Host `PROJECT_BUSY`；不得 begin |
| 任意 Host | Query 列出 sealed 恢复件 | 确认/拒绝需要 lease |

Begin / append / flush / 一切 Authoring Command 的 admission **必须**在
Facade 已持有的 writer lease 内：先读 active Journal，再验
`expected_revision`，再执行。禁止无锁检查会话、禁止只在发起录音的进程内存里
记 session。

第二次 `sequence.record.begin`：

- 无 lease：`PROJECT_BUSY`（Host 既有语义）。
- 同一 lease、已有 active session：`INVALID_ARGUMENT`，details 含
  `reason=sequence_session_active` 与 `session_id`。不 seal、不覆盖 Journal。
- 前一 owner 崩溃、lease 已释放、磁盘上仍有 active Journal：打开 Project 并
  取得 lease 时，先按 §8.6 用 **当前 manifest head** reconcile 每个 pending
  flush；已有 receipt 的只完成/清理。仅当 reconcile 后仍有未提交事件，才把
  Journal seal 为 `owner_lost`，再允许其他 Command。不自动 resume。之后走
  SR-D17 恢复，不走第二次 begin。

非 owner 发来的 Sample / 未知 Authoring Command：先被 lease 挡成
`PROJECT_BUSY`。只有 **当前 owner** 在 session active 时误发这些 Command 才
走 SR-D16（`INVALID_ARGUMENT` + `reason=sequence_session_active`，录音继续）。

不新增只为文案服务的公开 error code。`PROJECT_BUSY` 仍是 Host 对 lease 失败
的正规化；Core 公开码沿用 `lmdj.error.v1`。

### 8.1 不占 Project revision

Query；Workspace / Host 设置；Provider 选择；失败 Attempt；Snapshot Cook；
节拍器与纯 Transport 显示。

### 8.2 可 rebase（录音继续）

- BPM
- Quantize / Swing（只作用于之后新写入 Journal 的音）
- 正在进行的 Pad Capture **commit 到已武装的目标 Pad**

Core 把会话的 `expected_revision` 收到新 head。不是通用 rebase。

### 8.3 冲刷并继续（SR-D11 / SR-D23）

用户点另一 Pattern 槽只产生 **selection request**（UI 可标 pending）。默认
effective boundary 是 **下一 Bar**（§6.3）。Beat / Pattern End 若在 Stage 9
开放，规则相同：三者同一边界。

在该边界上 **同一把写锁** 内顺序发生：

1. 按 §8.6 把旧槽未提交事件 flush 成一条 Pattern Command；
2. Journal 目标改为新槽，刷新 fingerprint 为新槽当前 Pattern；
3. Runtime 改为播放新槽（已提交音符 ∪ 此后 Journal）。

生效前：继续听旧 Pattern，新敲的音仍进旧槽 Journal。禁止点击瞬间改 Journal
目标而播放仍等到下一 Bar。

### 8.4 停录并 commit

再按 Record；切到 Sample；停 Play。

### 8.5 Record 仍 active 时失败（录音继续，不 seal）

`AssignPad`、Trim、`UpdatePadPlayback`、`ResetPadPlayback`、
`ImportAssignSample`、普通 `ImportAsset`、对 **非武装目标** 的 Pad 写入，以及
任何未知 Authoring Command。

失败不丢 Journal，不把会话变成恢复件。

### 8.6 Flush 幂等（SR-D21）

沿用 Proof：`successful commit deletes the active journal only after Project
commit`，以及 duplicate `command_id` 回放原 receipt。

每个 flush（停录、停 Play、切 Sample、切槽边界）：

0. 事件 acknowledgement 之前，Journal 已耐久保存最新 canonical tail；flush
   record 消费该 tail，二者事件必须逐项相同。crash 落在两者之间时仍由 tail 恢复；
   flush record 已耐久后 tail 不再单列，避免同一事件成为两份恢复输入。
1. 在 Journal 耐久写入 pending flush：`session_id`、`flush_seq`、
   `command_id`（Host UUID）、目标 `pattern_id`、本批事件、
   `expected_revision`。
2. 在同一 writer lease 内执行 Pattern 写入 Command。已存在该 `command_id`
   的 receipt 时返回原 receipt，不二次 overdub。
3. transaction / checkpoint 文件本身不是 commit point。仅当 `manifest.json`
   已原子发布并完成适用的目录同步，且从该 manifest head reload 能查到对应
   receipt，才把该 flush 标为 completed。
4. 若较早 flush 在 commit point 前失败，Runtime 保留同一 pending batch；后续
   flush 必须等于「全部 unresolved flush 依序 merge 最新 durable tail」的 canonical
   结果。该后续 flush completed 时，它覆盖的较早 `flush_seq` 同时标记为
   superseded/resolved，不得再进入 recovery。这样同 key 的新 event 可替换旧 event，
   但不同 key 的旧 event 不能被遗漏。
5. 反向 completion 不能只看 `flush_seq`：若 F0 先 completed，已经耐久的较晚 retry
   只有在 session、Pattern、`expected_revision` 相同，且每个 canonical event 的
   key/value 都被 F0 精确覆盖时才同时 resolved。较晚 batch 中精确匹配 F0 的 event
   从 recovery residual 扣除；新增 key 或同-key 不同 duration/velocity 保留未提交。
6. 会话结束且 **全部** flush completed 或 superseded 之后，才删除 active Journal。

重启判定：

| 磁盘 | 行为 |
| --- | --- |
| Journal pending flush，Project 无该 `command_id` | 未提交。seal/恢复，不得当已成功 |
| Journal pending/active，Project 已有该 receipt | 已提交，仅待清理：回放 receipt，删除或完成 Journal，**禁止**再 apply 事件 |
| Journal 已删，Project 有 receipt | 正常终态 |
| active Journal，无 live owner | **先逐个 reconcile receipt**；清掉已提交批次；仅当仍有未提交事件时 seal `owner_lost`，走恢复 |

禁止先删 Journal 再写 Project。禁止 Project 已提交后把同一批事件再当
uncommitted 恢复。

### 8.7 恢复匹配（SR-D22）

`pattern_fingerprint` 是目标 Pattern 在 begin 或上次 completed flush 时的精确
字节摘要，不是当时的 revision 数字。哈希前像固定为：

```json
{"bars":1,"events":[]}
```

上例是空 Pattern 的精确哈希前像；非空 Pattern 的 `events` 放入 §10.1 排序后的
Contract event objects。先按 Project Contract 的字段形状构造 `{bars, events}`，
再编码为 canonical JSON：
object key 按 UTF-8 字节词典序排列、无多余空白、整数用无前导零十进制、布尔值为
`true` / `false`、UTF-8 无 BOM、末尾 **无换行**。最终值为
`lowercase_hex(SHA-256(canonical_json_bytes))`。实现不得直接 hash 内存 struct、
平台本地 JSON dump 或完整 Pattern（不得包含 `pattern_id`）。Native / Web 与迁移器
共享 fingerprint golden vectors。

用户确认恢复时，用 **当前** Project 的该 `pattern_id` 与 Journal 指纹比较：

| 目标 Pattern | 结果 |
| --- | --- |
| 存在、`bars` 不变、fingerprint 一致 | 允许 append；Command 带 **当刻** `expected_revision`（只防并发竞态，不替代指纹） |
| 存在，但已清空、改写、fingerprint 不一致 | 不得静默 append。Query 报告 `reason=pattern_changed`。用户选：写入 **新的** Pattern id，或拒绝 |
| `bars` 变短，任一恢复 `onset_tick` ≥ 新长度 | fail closed，保留恢复件，`INVALID_PROJECT` / details `reason=events_out_of_range` |
| `pattern_id` 已删除 | fail closed，保留恢复件，`NOT_FOUND` |

新鲜 revision **不得**单独构成「可以写回原槽」的理由。确认前 Project 不变。
拒绝则删除该恢复件。

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
- 字段固定为 `quantize_enabled: boolean` 与 `swing_percent: integer`；
  `swing_percent` 范围 50–75，默认 50。两者只控制之后新录事件的 onset 变换，
  不在 Cook / 回放时重排已有事件。

禁止：

- 把 `takes` 留成永远为空的 `{}`。
- 继续用 48 kHz `frame_offset` 作为 Sequence 事件时间。
- Host 从音频帧推导格子后只把 step 交给 Domain 却声称 Quantize 关仍保留手感。

Facade / error Contract：`REVISION_CONFLICT` 仍用于真正的 stale revision。
录音中被拒绝的 Sample 类 Command、第二次 begin 使用 `INVALID_ARGUMENT` +
`details.reason`。无 lease 由 Host 正规化为 `PROJECT_BUSY`。不新增只为文案
服务的公开 error code。恢复列表走 Query，不走 Candidate→Commit 的 AI Job
路径。

### 10.1 事件不变量（SR-D26）

4/4 下 `pattern_length_ticks = bars * 3840`。`onset_tick` 落在
`[0, pattern_length_ticks)`。

从 transport tick 到循环内 onset：

1. `t = raw_tick(frame)`；`onset_mod = ((t % L) + L) % L`，
   `L = pattern_length_ticks`。
2. Quantize 关：`onset_tick = onset_mod`。
3. Quantize 开，网格 `G = 240`。只用整数运算：令
   `base = onset_mod / G`（整数除法）、`remainder = onset_mod % G`；
   `remainder <= 120` 时 `q = base`，否则 `q = base + 1`。因此是最近倍数，
   **恰好半格**时向更早的格子（较小 tick）取整。
   - `onset_tick = q * G`；若结果等于 `L`，wrap 到 `0`。
   - 再应用 Swing。`pair_start = floor(onset_tick / 480) * 480`；偶数 1/16
     保持不动，奇数 1/16 改为
     `pair_start + floor((480 * swing_percent + 50) / 100)`。50 得 240 tick
     （直拍），75 得 360 tick。该整数公式是唯一允许的舍入规则。
4. Quantize 关时不应用 Swing。

`duration_tick`：

- 最小 `1`。
- 最大 `L - onset_tick`（clamp，音符不跨循环缝）。
- Journal 另记不持久化的绝对 `raw_attack_tick`。看到 Pad 释放时，以同一 SR-D25
  整数时钟取得绝对 `raw_release_tick`；
  `duration_tick = clamp(raw_release_tick - raw_attack_tick, 1, max)`。Quantize /
  Swing 移动 onset 不改变演奏时长。
- flush 时仍未释放：`duration_tick = clamp(240, 1, max)`。
- 播放仍遵守 Pad 的 One-shot / Gate；duration 是 Sequence 数据，不改 Pad
  模式。

Overdub 与「Pattern ∪ Journal」：

- 合并键：`(bank, pad, onset_tick)`。
- 后写入替换先写入（更新 velocity 与 duration）。同一格子多次敲击不保留
  重复事件，也不另建 event id。
- 多圈叠到同一键：仍是一条事件（后一次替换）。
- 写入 Project 前 canonical 排序：
  `(onset_tick, bank, pad, duration_tick, velocity)`。
  相同键不得出现两次。

这些规则是 Contract 不变量。C++ Domain、Web Host 与 v2→新 Contract 迁移器
必须对同一输入产生相同 Project 字节；实施计划提供共享测试向量。

## 11. 迁移

Headless Core Proof 的 `RecordTake` 已同时写入 Pattern。迁移已有 v2 bundle：

1. 保留 BPM；新增 `quantize_enabled = true`、`swing_percent = 50`。
2. 丢弃 `takes`。
3. 对每个旧 Pattern，按 v2 JSON `events` 的原数组顺序遍历，以
   `(bank, pad, step)` 为键执行 last-write-wins；不得先排序再决定 winner。
4. 把归一化后的整数 `step` 转为 `onset_tick = step * 240`（在 16
   step/小节、4/4、PPQ 960 下）；`duration_tick = min(240,
   pattern_length_ticks - onset_tick)`。
5. 按 §10.1 canonical 排序并验证相同 `(slot, onset_tick)` 不再重复，再写新
   Contract。任何合法 v2 bundle 都必须得到合法、确定的新 Project；迁移器不得
   因合法重复 step 生成无效输出。

没有 Take 列表可展示或恢复。未提交的旧 Take Journal 若仍存在于
`recovery/`，实施计划须规定：要么按本设计提示恢复进当时的 Pattern id，要么
在无法安全对应 Pattern 时 fail closed 并保留文件待人工处理。不得静默删用户
演奏。

## 12. 测试

Stage 9 实施必须覆盖：

- 默认 120 + Quantize 开：格子外的敲击写入最近 1/16；半格向更早；末格 wrap
  到 0（共享测试向量）。
- Quantize 关：保留 onset tick；Project 中无第二份事件列表。
- Swing 50 不移动事件；Swing 75 把奇数 1/16 从 pair 的 240 tick 移到 360；
  改 Swing 只影响之后新录事件，已有事件与 Cook 输出位置不被重排。
- 同一 `(slot, onset_tick)` 两击：后一次替换，canonical 排序后无重复键。
- 叠录：下一圈听得到；停录前 revision 不变；停录后 Pattern 含合并结果且
  revision +1。
- 录音中改 BPM：rebase；整数分母余数跨锚点连续，不跳格；已记 tick 不变；
  Native / Web 对非整 tick frame 产生同一 `raw_tick`。
- 录音中关 Quantize：之后的音不吸格；之前已吸格的音不重排。
- 切槽：下一 Bar 之前仍录旧槽；边界上旧槽已 commit，此后录新槽。
- 切 Sample：停录 flush；随后 Trim 成功。
- Record active 时发 Trim（含 CLI/MCP 持同一或另一入口）：Command 失败，
  Journal 仍在。无 lease 的第二 Host 得到 `PROJECT_BUSY`。
- 第二次 begin：`INVALID_ARGUMENT` / `sequence_session_active`。
- Owner 崩溃后下一 lease：先 reconcile 已提交 receipt；只把剩余未提交 tail seal
  为 `owner_lost`，不 resume。
- 真正子进程在 `press/release/press` 三个 event acknowledgement 后由 `SIGKILL`
  终止（最后一个 press 未释放）：下一 owner
  seal 恰一个 `owner_lost` candidate；显式恢复保持事件 identity/canonical 顺序且
  Project revision 只增加一次。测试不得调用 destructor 或 graceful close。
- Journal 末尾 partial record、checksum 损坏或 tail sequence/order 不合法时 fail
  closed，保留 active 文件，并返回 path、durable prefix、observed length、reason 与
  repair/discard remedy；不得把 torn bytes 静默截掉后继续录音。
- transaction/checkpoint 已写、manifest 未发布：flush 仍未提交，Journal 不得标
  completed。
- Project manifest 已提交、Journal 未完成/未删：重启先按 receipt 清理，不 seal
  已提交批次、不二次 overdub。
- F1 在 append 后、commit point 前失败，继续录音并由累积 F2 成功：F2 receipt
  同时 resolve F1；owner loss 只能 seal F2 之后真正未提交的 tail。apply 不得再次
  写入 F1，也不得用 F1 的旧同-key event 覆盖 F2 的新值；discard 不改变 revision。
- F0…F31 等价 retry 已全部耐久、F0 先 completed：32 条均 resolved，reconcile 不得
  产生 candidate。若 F0 已 commit 但 completion 报错，随后 append 等价 F1，重启按
  F0 receipt completion 也必须 resolve F1，Project revision 仍只增加一次。
- F0 先 completed、较晚 batch 同时含精确已提交 event、新 event 与同-key 新值：只
  后两者进入 owner-loss residual；精确已提交 event 不得再次成为 candidate。
- SR-D15：收音 Pad 不进 Pattern；停采进入 trimming overlay；确认提交后
  rebase，再敲才进 Sequence。提交冲突保留缓冲。
- 从 Record 中切 Sample 表面再试图新开麦：会话已结束，不再叠加。
- 恢复：fingerprint 一致可 append；Pattern 已改不可静默写回；删除/越界
  保留恢复件。确认前 Project 字节不变。
- 旧 Proof bundle：无 `takes`，默认 Quantize/Swing 已补；重复 `(slot, step)` 按
  原数组最后一项胜出；Pattern step→tick 后可 Cook。
- `pattern_fingerprint` Native / Web golden vectors 逐字节一致，含 key 顺序、无
  末尾换行和空 Pattern。
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
Proof concurrency rule; Sequence-page capture overlay is an additional
Host path on top of Stage 8B trimming, not a replacement of S8B-D3/D6
```

同一 Task 还须：

- 新增 `docs/prd/decisions/YYYY-MM-DD-sequence-recording-semantics.md`
- 删除上述两个 `docs/prd/questions/` 文件
- 勘误
  `docs/superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md`
  §6.2 / §6.5（Journal 只服务会话；Record 完成写入 Pattern，不创建 Take；
  Quantize / Swing 在录入时破坏性写入之后的新事件，不保留隐藏原始 timing）
- 把 `products/lmdj/README.md` 的 Proof-only 并发说明标为已被本决策取代
- 链到 Stage 9 实施 Plan / Issues；决策合入后再关 #238

## 15. 拒绝的替代

### 15.1 把 Proof 严格冲突当产品规则

拒绝。无关 Command 或 MCP 写入会把一轨演奏打成恢复件。#238 明确排除此选项。

### 15.2 Sequence 提交时必带音频 bounce

拒绝。与 Koala Sequence、§6.6 Slot 引用、§7 Perform WAV 分离冲突，并把 Web
混音录制拖进 Stage 9。

### 15.3 吸格但内部另存 Raw Take

拒绝。用户选择完全按 Koala 录音层：Quantize 开则原始时间丢弃；Swing 也只
烘焙进之后的新事件。LMDJ 规格原「Quantize 和 Swing 非破坏」由本决策在 Stage 9
录音层推翻；勘误写进 §6.2/§6.5。

### 15.4 空 `takes: {}` 留在 Project v2

拒绝。会让 Raw Take 假活着，并卡住 Pattern 事件从 `step` 迁到 tick。

### 15.5 停采即写入 Pad，跳过 Stage 8B trimming

拒绝。与 S8B-D3/D6 的 ≤5 s 选区、显式提交、冲突保留缓冲冲突。SR-D15 只把
trimming 放进 Sequence overlay。

### 15.6 崩溃后自动 resume 同一 session

拒绝。lease 丢失后磁盘 Journal 可能落后于用户对工程的后续编辑。必须 seal
并确认。

### 15.7 切槽瞬间改 Journal 目标

拒绝。与 §6.3「默认下一 Bar 生效」叠加会出现听旧录新。

## 16. 实施入口

实施计划：
[2026-08-23-lmdj-stage9-sequence-recording.md](../plans/2026-08-23-lmdj-stage9-sequence-recording.md)。

GitHub 工作项：

- umbrella：[Issue #265](https://github.com/endaye/lmdj/issues/265)
- 决策落地：[Issue #266](https://github.com/endaye/lmdj/issues/266)
- Project v3 / Domain：[Issue #267](https://github.com/endaye/lmdj/issues/267)
- Journal / Project I/O：[Issue #268](https://github.com/endaye/lmdj/issues/268)
- Cooker / Audio Runtime：[Issue #269](https://github.com/endaye/lmdj/issues/269)
- Application Facade：[Issue #270](https://github.com/endaye/lmdj/issues/270)
- CLI / MCP / Native Host：[Issue #271](https://github.com/endaye/lmdj/issues/271)
- Web Runtime / Web Host：[Issue #272](https://github.com/endaye/lmdj/issues/272)
- Creator：[Issue #273](https://github.com/endaye/lmdj/issues/273)
- 版本 / Assembly / Portal current / automated acceptance：
  [Issue #274](https://github.com/endaye/lmdj/issues/274)
- immutable Portal snapshot / final local acceptance：
  [Issue #275](https://github.com/endaye/lmdj/issues/275)

实施门禁不变：#266 的决策文件与勘误合入后才能关闭 #238；#267 及之后的
产品代码 Task 不得在该决策落地前开始。Push、PR、merge、Release、部署与 Channel
promotion 仍各自需要独立授权。
