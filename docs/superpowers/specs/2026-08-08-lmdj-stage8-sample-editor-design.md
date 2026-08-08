# LMDJ Stage 8 Sample Editor Design

日期：2026-08-08

状态：设计已批准；书面规格待审核

目标渠道：`canary`

设计基线：`feat/stage7-creator-editor` 的 Product Build `1.0.16.2`。Stage 8
可以在 stacked branch 开发，但不得早于 Stage 7 合入 `main`。

## 1. 结论

Stage 8 在 Stage 7 Creator Workspace 中启用正式 Sample 模式，让用户把 PCM16 WAV
导入任一稳定 Pad Slot，看到由真实音频计算的波形，以非破坏方式调整 Start、End、
触发方式、Loop、Mute 与 Volume，并立即试听结果。

Stage 8 不复制 Project parser、WAV Runtime 或可写 Project state 到 React。Project
Truth 增加每 Pad 播放参数；Application Facade 仍是所有查询与修改的唯一入口；Runtime
Snapshot 仍是不可变派生状态。连续拖动只创建 Runtime audition override，松手时才通过
`expected_revision` 提交一个 Project revision。

Stage 8 不包含麦克风或声卡录音。Koala 式 Pad Capture 被明确拆为紧随其后的
Stage 8B；Stage 9 仍负责把 Pad 演奏事件记录为 Take / Pattern。

## 2. Approved Decisions

| ID | 决策 |
| --- | --- |
| S8-D1 | Stage 8 参数集为 WAV import/replace、真实 waveform、Start/End、One-shot/Gate、Loop/Hold、Mute、Volume 与 Reset。 |
| S8-D2 | 播放参数属于 Pad Slot，不属于 Asset；同一不可变 WAV 可以在多个 Pad 上使用不同参数。 |
| S8-D3 | 拖动期间 Runtime 试听 draft；pointer/key release 通过 `expected_revision` 自动提交一个 revision，不提供 Apply。 |
| S8-D4 | Stage 8 不提供通用 Undo/Redo；`Reset Pad to Defaults` 是需要确认的普通 Authoring Command。 |
| S8-D5 | Replace 原子完成 Asset import、Pad assignment 与参数重置；旧 Asset 不立即删除，Artifact GC 延后设计。 |
| S8-D6 | 输入只接受 PCM16 WAV、mono/stereo、44.1/48 kHz；保存原始字节，Core 确定性准备 48 kHz Runtime PCM。 |
| S8-D7 | Loop 关闭时触发按钮为 One Shot；Loop 开启时同一按钮改为 Hold，不保存互相矛盾的多个布尔开关。 |
| S8-D8 | Sample Surface 采用波形在上、参数居中、完整 4×4 Pad 在下的结构，继承 Stage 7 Creator Shell。 |
| S8-D9 | 波形是以零线为中心、上下镜像的真实 peak envelope，不是背景图片或频谱图。 |
| S8-D10 | 支持双指/触控板缩放、横向平移和 Fit；这些 viewport 状态不进入 Project Truth。 |
| S8-D11 | 已分配 Pad 的 pointerdown 同时选择并触发；空 Pad 像 Koala 一样打开文件选择器，也接受直接拖入。 |
| S8-D12 | 替换已分配 Pad 前明确确认；取消或失败不改变 Project、Asset、Pad 或 revision。 |
| S8-D13 | Stage 8B 独立实现麦克风/声卡 Pad Capture；Stage 8 只预留复用边界，不提前请求录音权限。 |

## 3. Stage Boundary

权威阶段顺序变为：

```text
Stage 6   Web WASM + AudioWorklet + OPFS
Stage 7   Creator Editor shell and playable Project
Stage 8   WAV import and per-Pad Sample Editor
Stage 8B  microphone / audio-input Pad Capture
Stage 9   Take and Pattern recording
Stage 10  Perform
Stage 11  Sound Set
Stage 12  Stem / Slice / Pattern Intelligence Providers
```

Stage 8 的成功命题是：

> 用户可以在不绕过 Application Facade、不修改原始 WAV、不建立第二份 Project
> Truth 的前提下，为任意稳定 Pad 导入、裁剪、设置播放行为并可靠试听。

Stage 8B 的输入权限、设备选择、录音监控、反馈抑制、capture interruption、录音质量
与实体设备门槛不进入 Stage 8 实施或验收。

## 4. Scope

Stage 8 实现：

1. Creator Sample mode 与 Stage 7 Mode Rail enablement；
2. PCM16 WAV import、empty-Pad assignment 与 assigned-Pad replacement；
3. 由 Artifact 内容派生的确定性 waveform metadata 与多分辨率 peak cache；
4. Start/End 非破坏选区；
5. One-shot、Gate、Loop Gate、Loop Toggle 四种 Runtime 触发语义；
6. 每 Pad Mute 与 `-60.0..+6.0 dB` Volume；
7. session-local audition override 与 release-time Authoring commit；
8. `lmdj.project.v1` read migration 与新的 `lmdj.project.v2` writer；
9. Runtime Snapshot、Audio Runtime 与 Host transport 的必要兼容扩展；
10. Desktop / Tablet 响应式、Keyboard、Pointer 与触控交互；
11. Core、Facade、Web、Playwright 与人工听感验收；
12. Product Assembly、版本、Architecture Portal current truth 与不可变 canary snapshot。

## 5. Explicit Non-goals

Stage 8 不实现：

- 麦克风、声卡、系统音频或内部 Resample；
- Take、Pattern、Sequence、Quantize、Swing 或录音恢复；
- Slice、Chop、Stem、Reverse、Pitch、Pan、Attack、Release、Tone 或 Time-stretch；
- Asset Library、Asset delete、Artifact GC、Swap、Copy、Merge 或 Export；
- Asset/Pad rename、持久化 source file name 或用户自定义 label；
- 多 Pad 参数编辑、Choke Group、Polyphony 设置或 Velocity curve；
- 通用 Undo/Redo、命令历史浏览或自动 rebase；
- PWA、云同步、账号、协作、Beta、Stable、发布或 Channel promotion；
- JavaScript Audio fallback、第二套 WAV decoder 或 Host-side Project parser；
- 修改、翻译或重新引入已退役的 `lmdj.patch.v1`、`lmdj.materials.v1`。

## 6. Architecture

### 6.1 Ownership graph

```text
apps/creator-web
  Sample Surface / View Model / gesture drafts
                 │
                 ▼
packages/web-runtime-platform
  typed Sample session + audition transport
                 │
                 ▼
packages/application-facade
  inspect / waveform query / atomic Authoring Commands
          │                    │
          ▼                    ▼
packages/project-io     packages/project-cooker
  v1 read + v2 write      immutable Runtime Snapshot
          │                    │
          ▼                    ▼
packages/authoring-domain  packages/audio-runtime
  Project Truth             voices / trigger modes
```

Creator 只保存 render View Model、当前 Pad、波形 viewport、gesture draft 与 pending
action。它不解析 Project bundle，不直接读取 Project checkpoint，不持有可写 Project
副本，也不把 waveform cache、active voice 或 provider failure 写入 Project Truth。

### 6.2 Application Facade surface

实施计划必须以 typed C++ API 为源，再通过现有 C ABI JSON boundary 暴露等价操作。
建议的行为边界为：

- `sample.inspect`：查询 Pad playback、Asset metadata、source frame count 与 cache identity；
- `sample.waveform`：按 source-frame window 与目标 bucket 数查询 peak envelope；
- `sample.import_assign`：原子 import、assign 与 defaults；
- `sample.update_pad`：提交完整 Pad playback value，而不是部分 JSON patch；
- `sample.reset_pad`：显式恢复 defaults；
- Runtime session preview：set/clear audition override，不是 Authoring Command。

最终 operation 名可在实施计划中按现有 Facade naming convention 收敛，但不得改变上述
ownership、原子性、revision 或 Project/Runtime 边界。

## 7. Project Truth v2

### 7.1 Contract decision

Stage 8 新增 `lmdj.project.v2` `2.0.0`，并在 Assembly 中同时保留
`lmdj.project.v1` `1.0.0`。不修改 v1 Schema 来伪装 forward compatibility：Stage 7
reader 对 Pad 使用 exact-key validation，写入未知字段会使旧 reader 拒绝 Project。

`lmdj.project-bundle.v1` 保持 `1.0.0`，仍只携带 v1 Project。Stage 8 可以导入该
bundle，然后在第一次成功 Authoring mutation 时迁移；Stage 8 不增加 Bundle export。

### 7.2 Pad playback value

每个 v2 Pad 都包含完整 playback value，即使 `asset_id` 为 `null`：

```json
{
  "pad": 0,
  "asset_id": null,
  "playback": {
    "trim_start_frame": 0,
    "trim_end_frame": null,
    "trigger_mode": "one_shot",
    "gain_millidb": 0,
    "muted": false
  }
}
```

字段语义：

- frame 是 source audio frame，不是 interleaved sample index 或 48 kHz prepared frame；
- Start inclusive；End exclusive；`null` End 表示 source 末尾；
- 非空 Pad 必须在 Facade command 与 Cook 时满足 `start < resolved_end <= frame_count`；
- `gain_millidb` 范围 `-60000..6000`，UI 步进 100 millidB；
- `trigger_mode` 只允许 `one_shot`、`gate`、`loop_gate`、`loop_toggle`；
- defaults 为完整选区、`one_shot`、0 dB、unmuted。

空 Pad 不保留上一个 Asset 的参数。Unassign、Replace 与 Reset 都产生明确、可测试的
defaults；同一 Asset 分配到其他 Pad 时不共享 playback value。

### 7.3 v1 migration

打开、inspect 或播放 v1 Project 只在内存中投影 defaults，不写文件、不增加 revision。
任何成功 Authoring Command 在持有 writer lease 后：

1. 读取并验证当前 v1 revision；
2. 为 64 Pad 注入 defaults；
3. 应用本次 command；
4. 以一个 Project I/O transaction 写入 v2；
5. revision 只增加一次。

取消、验证失败、`REVISION_CONFLICT`、I/O 失败或 lease 失败都不得留下半迁移 Project。
Project I/O journal、checkpoint recovery 与 inspect 必须同时覆盖 v1 input 和 v2 truth。

## 8. WAV Import and Replacement

### 8.1 Accepted input

Stage 8 只接受 RIFF/WAVE integer PCM16：

- mono 或 stereo；
- 44,100 Hz 或 48,000 Hz；
- 有效且唯一的 PCM `fmt`、有界 `data` 与一致的 block/byte rate；
- byte length、decoded frame count 与 prepared Runtime bytes 均满足现有 Core/Web 上限。

原始 WAV 字节作为 Artifact 保存。44.1 kHz input 由 Core 在 Cook/prepare 阶段以固定、
测试锁定的算法转换为 48 kHz Runtime PCM；该 prepared PCM 不是用户可见 Derived Asset，
不改变原始 Artifact SHA，也不写回 Project Truth。Source Start/End 到 Runtime frame 的
映射由 Cooker 以整数有理边界确定性完成，Host 不自行换算。

### 8.2 Atomic import-assign

空 Pad import 与 assigned Pad Replace 使用同一原子边界：

1. Browser `File` 写入 Project 外的有界 staging；
2. Core 验证 WAV、完整解码并生成 metadata / waveform cache input；
3. Replace 时 UI 显示目标 Pad、源文件显示名与参数重置警告；
4. Facade 在 writer lease 内重新验证 `expected_revision`；
5. 发布 Artifact、注册新 Asset、assign Pad 并写入 defaults；
6. Project revision 增加一次；
7. Cook 并发布新的 immutable Runtime Snapshot；
8. 删除 staging。

任一步在 Project commit 前失败都保持原 Pad 与旧 Asset 不变。Replace 不自动删除旧
Asset；未引用 Asset 与 Artifact GC 属于后续独立设计。File name 只作为当次 picker /
Replace confirmation 中经过转义、长度受限的临时显示值，不进入 Project Truth；reload
后 UI 使用 Pad address、短 Asset ID 与 WAV metadata，绝不把 source file name 变成
bundle path 或 Artifact identity。

## 9. Waveform

### 9.1 Visual contract

Sample Surface 显示 zero-centered mirrored peak waveform：每个 source-frame bucket
取所有 channel 的最大绝对 PCM amplitude，向中心零线的上、下两侧镜像填充。它是随
时间变化的真实振幅包络，不是 spectrogram、装饰背景或静态图片。

Start 与 End 之间是当前选区；两侧压暗。Preview playhead、Start/End handle 与时间轴
叠加在波形上，但不得覆盖可访问名称或缩小 handle 的 44 px hit target。

### 9.2 Derived cache

Peak cache key 至少包含：

```text
Artifact SHA-256
+ waveform algorithm version
+ source channel fold mode (max-abs-mirror)
+ frames per bucket
```

缓存属于 Workspace Cache，不属于 Asset、Project Truth 或 Runtime Snapshot。Facade 返回
有界整数 peak buckets；Creator 不接收原始 Project path。缓存缺失可以确定性重建；SHA、
算法版本、bucket count 或 source metadata 不一致时拒绝复用。

支持有界多分辨率 level、window query、双指/触控板缩放、横向平移，以及可聚焦的
Zoom In、Zoom Out、Fit controls。Zoom、pan、hover、selection focus 和 playhead 都是
session state，reload 后无需恢复。

## 10. Playback and Audition

### 10.1 Runtime Snapshot

Cooker 为每个 resolved Pad 生成：

- immutable prepared PCM；
- source-to-runtime resolved Start/End；
- explicit trigger mode；
- linear Runtime gain，由 millidB 确定性换算；
- muted state。

Pattern Event 继续只引用 `PadSlotId`，不引用 Asset。Runtime transport、active Voice、
loop latch、playhead、cache hit 与 audition override 永不持久化为 Project Truth。

### 10.2 Trigger semantics

| Runtime mode | UI | Pointer / key behavior |
| --- | --- | --- |
| `one_shot` | Loop off, One Shot on | press 从 Start 播放到 End，release 不截断 |
| `gate` | Loop off, One Shot off | press 开始，release 停止 |
| `loop_gate` | Loop on, Hold off | press 在选区循环，release 停止 |
| `loop_toggle` | Loop on, Hold on | 第一次 press 开始循环，再次 press 停止 |

Loop 开启时，UI 把 One Shot 控件原位改名为 Hold；不同时显示两个具有重叠意义的按钮。
选择其他 Pad 不隐式停止 `loop_toggle`；正在播放的 Pad 显示 active indicator，再次触发
该 Pad 停止。Visibility loss、page blur、Audio suspend、Host restart 或 Project reopen
停止全部 Voice，包括 latched loops。

### 10.3 Draft preview and commit

Start、End、Volume、Mute 与 trigger controls 在 gesture 期间写入 Runtime session-local
audition override。Audio thread 只消费预分配 control messages，不分配、不锁、不访问
Project I/O。Creator 始终保存 gesture 开始时的 Project revision 与完整 proposed value。

Pointer/key release 时：

1. 提交完整 `sample.update_pad` value；
2. 成功则清除 override，Cook 并发布新 Snapshot；
3. 失败则清除 override 并恢复最后发布的 Snapshot；
4. 一次 gesture 最多产生一个 Project revision。

Start/End handle 不可交叉，最小选区为一个 source frame。方向键移动一帧；Shift 按
source sample rate 移动 10 ms 对应的最近整数 frame。Pointer cancellation、Escape 或
component unmount 取消 draft，不提交。Loop、trigger mode、Mute 与 Reset 等离散 control
不等待 pointer release batching；每次明确 activation 即提交一次完整 value。

## 11. Creator Interaction

### 11.1 Layout

Stage 8 继承 Stage 7 top status、left Mode Rail 与 Product Runtime status。Sample mode
中部纵向结构固定为：

```text
Selected Pad identity + short Asset ID + WAV metadata + Replace
Zero-centered waveform + Start/End + playhead
Sample controls + Reset
Bank selector
Complete 4 x 4 playable Pad surface
```

Desktop 使用完整 Rail；Tablet 收窄为有 accessible name 的图标 Rail。参数可以换行，
但波形始终在 Pad 上方，Pad 不折成隐藏 carousel。Start/End handle、Pad、toggle 与确认
按钮维持至少 44 px 触控目标。

该层级参考 Koala Sample Editor 的“选 Pad → 波形优先 → 参数紧邻”工作流，但不复制
Koala 的品牌外观、颜色、进阶参数或手机三页 controls。

参考：<https://manual.koalasampler.com/mobile/4-sample/>

### 11.2 Pad and file behavior

- assigned Pad `pointerdown` 同时选择并触发；重复触发已选 Pad 不需要额外 Preview；
- gate modes 在 `pointerup`/keyup 释放；keydown repeat 不重复触发；
- empty Pad click 直接打开文件选择器；取消是正常 no-op；
- WAV 可以拖到 empty Pad；拖到 assigned Pad 进入相同 Replace confirmation；
- Replace、Mute 或 Reset 正在发声的 Pad 时，先停止该 Pad 的 active Voice；
- unsupported file 不改变当前选择，错误与格式要求显示在 Sample Surface 内；
- audio suspended 时允许 import/edit/commit，但显示 `Activate Audio to preview`。

### 11.3 Controls

Start/End 同时提供 handle 与可聚焦数值 control。Volume 以 dB 显示，范围
`-60.0..+6.0`、步进 `0.1`；Mute 独立，不用 `-∞ dB` 代替。

`Reset Pad to Defaults` 与 Replace 都要求确认。Reset 保留 Asset，恢复完整选区、
One-shot、Loop off、0 dB、Mute off，并产生一个 revision。Stage 8 不提供通用 Undo。

## 12. Concurrency and Lifecycle

每个 Authoring Command 必须携带 `command_id` 与 `expected_revision`。Facade 在 writer
lease 内验证 revision；没有 auto-rebase、last-write-wins 或 Host merge。

`REVISION_CONFLICT` 时：

1. 清除 audition override；
2. 恢复最后发布的 Runtime Snapshot；
3. 重新 inspect authoritative Project；
4. 显示“Project changed; review and try again”；
5. 不自动重放用户 command。

`restart-required`、writer lease lost 或 `PROJECT_BUSY` 时禁止新的 mutation。UI 不显示
optimistic success，不在 localStorage 排队 Authoring Commands；用户必须 reopen/reload。

Project commit 与 Runtime publish 是两个可观察阶段。若 Project 已提交但 Cook 返回
`COOK_FAILED`，UI 必须显示“Saved at revision N; Runtime is still revision N-1”，保留旧
Snapshot，并允许显式 Retry Prepare。不得伪造回滚，也不得把 Runtime failure写入 Project。

## 13. Error Model

Stage 8 复用 `lmdj.error.v1`，不新增只为 UI 文案服务的 public error code：

| Condition | Typed outcome | Project effect |
| --- | --- | --- |
| picker cancelled / confirmation cancelled | normal cancellation | none |
| wrong WAV encoding, channels, rate, shape or Web limit | `UNSUPPORTED_AUDIO` | none |
| invalid Start/End, gain or trigger mode | `INVALID_ARGUMENT` | none |
| stale revision | `REVISION_CONFLICT` | none |
| Artifact disappeared | `MISSING_ASSET` | none |
| staging or OPFS failure | `IO_ERROR` | none before commit |
| immutable Snapshot cannot be prepared | `COOK_FAILED` | committed truth remains authoritative |
| unexpected invariant failure | `INTERNAL_ERROR` | fail closed |

`HOST_STATE_INVALID`、`PROJECT_BUSY` 与 `UNSUPPORTED_WEB_RUNTIME` 继续属于现有 Web Host
normalization/lifecycle surface，不写入 Project Truth。Public messages 不包含 absolute path、
raw Project document、sample bytes 或不受限的 platform exception。

未能即时删除的 staging 由下次启动的 bounded scavenger 按已验证 root 和 age 回收。它
不是 Asset、Attempt 或 Project record，cleanup failure 不得制造假 revision。

## 14. Security, Bounds, and Realtime Safety

- Browser File name 只在当次 picker/confirmation 中转义后显示；Core identity 使用 UUID
  与 Artifact SHA；
- staging、cache 与 Project roots 使用既有 safe-path、no-symlink 与 writer lease 规则；
- import 在 decode 前验证 declared bytes，在 decode 后验证 actual frames/prepared bytes；
- waveform query 的 window、bucket count、zoom level 与 response bytes 有固定上限；
- fixed Wasm heap 与 Stage 6 Runtime preparation constants 是权威，不另猜产品上限；
- AudioWorklet 不 decode WAV、不计算 waveform、不写 cache、不分配或加锁；
- audition control queue overflow fail closed，清除 draft 并报告 Runtime preview failure；
- drag/drop、paste 或 picker 不扩大允许格式；MIME hint 不能替代 RIFF/WAV 验证；
- no source maps、debug filesystem paths 或 raw audio content 进入 acceptance report。

## 15. Testing and Proof

### 15.1 Core and Contract

- v1 open-without-write、first-mutation v2 migration、v2 round trip 与 recovery；
- 64 Pad defaults、per-Pad independence、invalid playback value rejection；
- import/assign/reset atomicity、one-revision rule、duplicate command 与 conflict；
- PCM16 mono/stereo 44.1/48 positive fixtures；wrong format/rate/bits/chunk/size negatives；
- source-frame trim 与 deterministic 48 kHz mapping；
- peak envelope exact golden vectors、stereo max-abs fold、cache-key invalidation；
- Runtime Snapshot complete resolved parameters；
- Audio Runtime one-shot/gate/loop-gate/loop-toggle、gain/mute、voice stop 与 queue bounds；
- CLI/MCP/Native Host exact Application Facade dependency and C ABI parity propagation。

### 15.2 Creator and Platform

- View Model does not contain writable Project document or bundle parser；
- Loop label switches One Shot ↔ Hold without invalid state；
- empty/assigned Pad, picker cancellation, drag/drop and Replace confirmation；
- zoom/pan/Fit、focusable handles、keyboard increments、44 px targets；
- gesture preview emits no Authoring mutation until release and exactly one after release；
- Escape/pointercancel/unmount/conflict clears override；
- audio-suspended edit、Cook-failed saved state、restart-required and Project busy；
- blur/visibility/suspend stops every active and latched voice；
- privacy-safe acceptance report records identities and outcomes, not file name/path/audio。

### 15.3 Packaged browser proof

`scripts/creator-web.sh proof` must use packaged output and a real Facade-created fixture:

1. import/open a v1 Project and confirm open does not migrate it；
2. select empty Pad and import a valid WAV；
3. prove one v2 revision contains Asset、assignment、defaults；
4. render content-derived mirrored waveform and exercise zoom/Fit；
5. adjust Start/End and prove one release-time revision；
6. exercise four trigger modes, Volume, Mute and Reset；
7. cancel Replace, then confirm Replace and prove atomic reset；
8. inject unsupported WAV、revision conflict and Cook failure；
9. reload/reopen and prove persisted playback plus no duplicate import；
10. run Chromium positive Proof and WebKit capability-boundary Proof。

Playwright DOM assertions do not prove physical touch-to-sound latency or human hearing.

### 15.4 Manual acceptance

- Chrome 实机听感：16 Pad、trim、四种 trigger、Volume/Mute、Replace、reload；
- 触控设备：pinch zoom、pan、Start/End handle、Pad press/release、无卡住声音；
- Safari 按实际 capability boundary 单独记录，不用 Chromium 结果代替；
- Stage 6 五项实体 Web physical rows 继续 `deferred / unverified`；
- 它们不阻塞 Stage 8 canary implementation merge，但阻塞 physical-pass、Beta、Stable；
- Stage 8B microphone/input quality 不计入 Stage 8 acceptance。

## 16. Version Management

本表以 Stage 7 当前 stacked baseline `1.0.16.2` 为依据：

| Identity | Baseline | Target | Reason |
| --- | --- | --- | --- |
| Product Build | `1.0.16.2` | `1.0.17.0` | 新 Project Contract、Sample mode 与可运行播放行为。 |
| `lmdj.project.v1` | `1.0.0` | unchanged | 保留 legacy read/import identity。 |
| `lmdj.project.v2` | absent | `2.0.0` | 新 per-Pad playback truth 与明确 migration boundary。 |
| `authoring-domain` | `0.1.1` | `0.2.0` | Pad playback value 与 commands。 |
| `project-io` | `0.5.0` | `0.6.0` | v1 read/v2 write、migration 与 atomic Sample mutation。 |
| `project-cooker` | `0.2.1` | `0.3.0` | trim、trigger、gain、mute 与 44.1 kHz deterministic prepare。 |
| `audio-runtime` | `0.4.0` | `0.5.0` | 四种 trigger、loop voice 与 audition controls。 |
| `application-facade` | `1.3.1` | `1.4.0` | Sample query、atomic commands 与 preview boundary。 |
| `web-runtime-platform` | `0.1.1` | `0.2.0` | typed Sample session、waveform 与 audition transport。 |
| `creator-web` | `1.0.1` | `1.1.0` | 启用完整 Sample mode。 |
| `web-runtime-host` | `1.2.1` | `1.2.2` | 精确 Platform dependency 传播，诊断 UI 不增加 Sample 功能。 |
| `core-cli` | `1.0.7` | `1.0.8` | 精确 Facade dependency 传播。 |
| `core-mcp` | `1.1.4` | `1.1.5` | 精确 Facade dependency 传播。 |
| `native-test-host` | `1.0.5` | `1.0.6` | 精确 Facade dependency 与 parity coverage。 |
| `lmdj.project-bundle.v1` | `1.0.0` | unchanged | Stage 8 只 import legacy v1 bundle，不新增 export。 |
| `lmdj.error.v1` | `1.0.0` | unchanged | 复用现有 typed errors。 |

实施计划必须在写任何版本文件前重新读取 merged `main`。若后续 Build 或组件版本已被
占用，分配下一个合法版本；已使用或放弃的 Product Build 不得复用。

Stage 8 分配 Product Build，因此必须在 clean committed source boundary 执行：

```bash
scripts/architecture-portal.sh version 1.0.17.0 canary
```

Tag、tag push、PR、merge、deploy、publication 与 Channel promotion 仍分别需要授权。

## 17. Documentation Impact

Documentation impact: required

Affected portal pages:

- `/`；
- `/core/overview/`；
- `/core/modules/authoring-domain/`；
- `/core/modules/project-io/`；
- `/core/modules/project-cooker/`；
- `/core/modules/audio-runtime/`；
- `/core/modules/application-facade/`；
- `/core/modules/web-runtime-platform/`；
- `/hosts/overview/`；
- `/hosts/creator-web/`；
- `/contracts/project/`；
- `/platform/web-runtime/`；
- `/platform/input/`；
- `/platform/storage/`；
- `/assembly/lmdj/`；
- `/operations/testing-and-proof/`；
- `/operations/version-and-release/`；
- affected module/host/contract diagram sources and generated outputs。

同一 implementation Task 更新 `docs/prd/decision-log.md`，关闭
`docs/prd/open-questions.md` 中 Sample Editor 最小参数集问题，并把 Stage 8B Pad
Capture 记录为未实施、未分配版本的后续阶段。文档不得把设计、实现、canary snapshot、
physical pass、Beta、Stable 或 release 混为一个状态。

## 18. Rollback and Compatibility

Stage 8 写出的 v2 Project 不能由只认识 v1 的 Stage 7 binary 安全打开。因此回滚采用
forward-compatible corrective build：

1. 保留 Stage 8 `authoring-domain`、`project-io`、`project-cooker`、Facade 与 Runtime；
2. 在 Creator 中关闭 Sample mutation entry 或回滚有问题的 UI；
3. 继续读取、Cook 和播放 v1/v2 Project；
4. 不把 Project 原地降级为 v1；
5. 不直接部署历史 `1.0.16.x` artifact 覆盖已迁移 workspace。

Project I/O 的原子 checkpoint/journal 是 crash recovery，不是产品 Undo 或 schema
downgrade。Canary 发布说明必须公开该 forward-only Project migration；Beta/Stable 前需要
完成 v2 compatibility、backup/restore 与 physical gates。

## 19. Rejected Alternatives

### 19.1 Host-local editable Project

拒绝。它会创建第二份可写 Truth，使 reload、conflict、Native/Web parity 与 recovery
分叉，并违反 Host-only-through-Facade 不变量。

### 19.2 Generic parameter automation in Stage 8

拒绝。未来 automation、modulation 与 Perform 状态需要独立 Contract；当前只实现固定
per-Pad playback value。

### 19.3 Store waveform or prepared PCM in Project Truth

拒绝。两者都是由 immutable Artifact 与算法版本派生的 cache/runtime data，会污染
authoring state 并制造不必要的 Project revisions。

### 19.4 Extend `lmdj.project.v1` in place

拒绝。现有 v1 exact-key reader 会拒绝新增字段；声称 minor-compatible 会制造不可验证
的 rollback 和跨版本读取承诺。

### 19.5 Add Pad recording now

拒绝进入 Stage 8。Pad Capture 与 Sample Editor 邻近但需要新的 input permission、capture
lifecycle、monitoring 和 physical evidence；它属于已批准的 Stage 8B。

## 20. Acceptance Checklist

- [ ] Creator 只通过 Web Runtime Platform / Application Facade 访问 Sample state；
- [ ] v1 open 不写入，首次成功 mutation 原子生成 v2 且 revision +1；
- [ ] 每 Pad playback independent，同一 Asset 可以有不同参数；
- [ ] PCM16 WAV 44.1/48 kHz mono/stereo 通过，其他输入 fail closed；
- [ ] original Artifact bytes/identity 保持不变，prepared PCM 不伪装成 Derived Asset；
- [ ] waveform 来自 deterministic mirrored peak envelope，支持 zoom/pan/Fit；
- [ ] Start/End、四种 trigger、Volume、Mute 与 Reset 进入 Runtime Snapshot；
- [ ] gesture draft 只影响 audition override，release 最多提交一个 revision；
- [ ] import/replace 原子，cancel/failure/conflict 不改变 Project；
- [ ] Cook failure 区分 saved Project revision 与 stale Runtime revision；
- [ ] blur/visibility/suspend/restart 停止全部 active/latched voices；
- [ ] Core、Facade、Creator、Chromium proof、WebKit boundary 与 Portal checks 通过；
- [ ] canary snapshot、Product/Module/Host/Contract identity 与 docs current truth 一致；
- [ ] Stage 6 physical rows 与 Stage 8B recording 保持 truthful deferred boundary；
- [ ] 没有 `lmdj.patch.v1`、`lmdj.materials.v1`、Host Project parser 或 JS Audio fallback。
