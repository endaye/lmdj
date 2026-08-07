# LMDJ Stage 7 Creator Editor Design

日期：2026-08-07

状态：规格已批准

目标渠道：`canary`
前置依赖：PR #94 的 `1.0.15.0` Web Runtime Host 修复必须先合入并在 `main`
重新验证；Stage 7 可以在叠加分支开发，但不得先于该依赖合入。

## 1. 结论

Stage 7 把 Stage 6 的产品中立诊断 Host 接入第一个正式 LMDJ Creator Editor。
它证明用户可以在 Desktop / Tablet Web 中打开浏览器本地 Project 或导入一个可移植
`.lmdj` Project Bundle，进入稳定工作台，激活真实 C++ Web Audio Runtime，并通过
Pointer、Keyboard 或 Web MIDI 演奏四个 Bank、共 64 个稳定 Pad Slot。

Stage 7 不是 Sample、Sequence 或 Perform 功能阶段。它只建立这些后续能力所需的
产品 Host、工作台信息架构、Project 入口、共享 Web Runtime Platform 与可重复 Proof。
用户演奏可以用于验证 Pad 与 Runtime，但本阶段不暴露 Take 录制、Pattern 编辑、
Momentary FX、Resample 或 Sound Set。

已批准的关键决策如下：

| ID | 决策 |
| --- | --- |
| S7-D1 | 新增独立产品 Host `apps/creator-web`，不把 Creator UI 塞进诊断 Host。 |
| S7-D2 | 从 Stage 6 抽出产品中立的 `packages/web-runtime-platform`；Creator 与诊断 Host 消费同一 Runtime Session 边界。 |
| S7-D3 | 工作台采用完整 Creator Workspace：顶部全局状态、左侧模式 Rail、中部模式 Surface、底部固定 4×4 Pad。 |
| S7-D4 | Stage 7 只启用 Project；Sample、Sequence、Perform 可见但不可聚焦、不可调用、不可伪装成已实现。 |
| S7-D5 | 用户入口为打开浏览器本地 Project 或导入现有 `.lmdj`，不创建空白 Project、不上传 WAV/MP3 生成 Project。 |
| S7-D6 | Stage 7 为 `canary`；五项实体 Web 物理门槛继续保持 `deferred / unverified`。 |
| S7-D7 | Take 属于 Stage 9。Stage 7 不利用 Stage 6 诊断能力提前暴露录制 UI。 |
| S7-D8 | PWA 安装、Service Worker、离线更新、云存储、账号和部署不进入本阶段。 |

## 2. 设计依据与阶段边界

权威新内核交付顺序为：

```text
Stage 6  Web WASM + AudioWorklet + OPFS
Stage 7  Creator Editor
Stage 8  Sample
Stage 9  Sequence
Stage 10 Perform
Stage 11 Sound Set
Stage 12 Stem / Slice / Pattern Intelligence Providers
```

Stage 9 完成后才构成“导入声音、裁剪、分配 Pad、亲手录出 Beat”的第一个用户价值
里程碑。Stage 7 不通过把 Stage 8–10 的按钮画出来而伪造该里程碑。

Stage 7 的成功命题是：

> 产品 UI 可以在不绕过 Application Facade、不复制 Web Core、不中断 Stage 6
> Conformance Proof 的前提下，可靠地承载真实 Project 和实时演奏。

## 3. 现有基线

Stage 7 设计基于 `1.0.15.0 · canary` 候选：

- `application-facade 1.2.0`；
- `project-io 0.4.0`；
- `audio-runtime 0.4.0`；
- `web-runtime-host 1.1.0`；
- Emscripten `6.0.5`；
- 512 MiB 固定共享 Wasm Heap；
- Dedicated Control Worker、Wasm AudioWorklet、SharedArrayBuffer、OPFS；
- Pointer、Keyboard 与 Web MIDI 的统一 Trigger 路径；
- Project create/open/inspect、Asset import、Pad assign、Snapshot reload；
- Stage 6 私有协议 `1` 与显式 typed error；
- Chromium 正向 Proof 与 WebKit capability-boundary Proof。

Stage 6 的 `apps/web-runtime-host` 同时包含产品中立 Runtime 代码和诊断页面装配。
Stage 7 必须抽取可复用边界，但不能改变 Project Truth、Runtime Snapshot、Audio Thread
或现有诊断 Proof 的语义。

## 4. Approved Scope

Stage 7 实现：

1. `packages/web-runtime-platform` 产品中立 Module；
2. `apps/creator-web` 正式 LMDJ 产品 Host；
3. 浏览器本地 Project 枚举与打开；
4. 可移植 `.lmdj` Bundle 的有界、隔离、原子导入；
5. Project inspect 与当前 revision、BPM、Pad/Asset 占用状态展示；
6. 四个 Bank 与每 Bank 16 个稳定 Pad Slot；
7. Pointer、Keyboard、Web MIDI 输入；
8. 用户手势触发的 Audio 激活与显式 suspend；
9. reload、restart-required、Host 重建与 Project reopen；
10. Desktop / Tablet 响应式工作台、键盘焦点和触控目标；
11. deterministic static distribution、COOP/COEP server 和独立 Creator Proof；
12. Product Assembly、版本、Architecture Portal current truth 和不可变 canary 快照。

## 5. Explicit Non-goals

Stage 7 不实现：

- 空白 Project 创建；
- WAV/MP3 上传、录音采样、裁剪、Slice、Stem 或 Pad 重新分配；
- Take、Pattern、Sequence、Quantize、Swing 或录音恢复 UI；
- Perform 模式、Momentary FX、Performance Capture、Stereo WAV 或 Resample；
- Sound Set Catalog、下载、安装或 Marketplace；
- Intelligence Provider、生产 Provider 或云 Job；
- Project rename、Key 编辑或其他尚未进入 `lmdj.project.v1` 的字段；
- `.lmdj` 导出；
- Service Worker、安装提示、离线更新或 PWA 图标；
- 登录、账号、云同步、协作、遥测或部署；
- JavaScript Audio fallback、第二套 Project 解析器或第二套 Web Audio Runtime；
- `beta`、`stable`、签名 tag、GitHub Release 或 Channel promotion。

## 6. Architecture

### 6.1 Module graph

```text
products/lmdj/assembly.json
          │
          ├───────────────┐
          ▼               ▼
apps/creator-web   apps/web-runtime-host
          │               │
          └───────┬───────┘
                  ▼
packages/web-runtime-platform
                  │
                  ▼
packages/application-facade
          ┌───────┼────────┐
          ▼       ▼        ▼
   project-io  cooker  audio-runtime
```

`creator-web` 是 LMDJ 产品 UI，可以读取明确传入的 Product Assembly 身份；它仍然
没有内核特权。`web-runtime-host` 继续保持产品中立诊断 Host。两者都不得解析
`.lmdj` 内部文件、直接调用 Project I/O、读取兄弟 Module 私有文件或构造第二个
Runtime Snapshot。

### 6.2 `web-runtime-platform` ownership

新 Module 拥有：

- Runtime manifest/preflight 校验；
- Control Worker 与 browser-main 生命周期；
- C++ Control Bridge / Control Runtime 的产品中立装配；
- Wasm AudioWorklet 与固定共享内存启动；
- OPFS Storage Platform 接入；
- Runtime Session 状态机与 typed error；
- Trigger submission serialization 与 runtime outcome 分发；
- 可配置的 Pointer、Keyboard、MIDI adapter primitives；
- Project discovery、bundle staging 与 Facade 导入调用；
- privacy-safe、allowlisted Host facts。

它不拥有：

- DOM、React component、CSS 或 LMDJ 视觉语言；
- Creator 的模式导航、Bank 选择或按键文案；
- Diagnostic Project coordinator；
- 产品专属 Provider 选择；
- Project Truth 的替代缓存。

### 6.3 Public Runtime Session surface

Stage 7 锁定下列语义；实施可机械确定 TypeScript 名称，但不得改变责任边界：

```text
createSession(manifest, assemblyIdentity)
  preflight()
  listLocalProjects()
  importProject(bundleSource)
  openProject(projectId, patternId)
  inspectProject()
  reloadSnapshot(patternId)
  activateAudio(userGestureToken)
  suspendAudio()
  trigger(slot, velocity, source)
  close()

  subscribeHostState(listener)
  subscribeRuntimeOutcome(listener)
```

所有改变 Project Truth 的动作仍由 Facade Command 执行。Stage 7 UI 没有可改变
Project Truth 的产品功能；Bundle import 是把已经存在的完整 Project 原子安装到本地
Workspace，不是重放 UI 自行解释的 Commands。

## 7. Project Entry and Bundle Import

### 7.1 Local Project discovery

`listLocalProjects()` 只从受管 OPFS Project 根目录发现 `.lmdj` Bundle，并通过
Project I/O / Facade inspect 验证。结果按 `project_id` 排序，不依赖浏览器目录枚举
顺序。

Stage 7 不把最近打开时间、文件名或 UI label 写进 Project Truth，也不维护不可重建
的第二份项目数据库。UI 显示短 Project ID、revision、BPM 与 Pad 占用；Key 显示为
明确的 `—`，不猜测分析结果。

### 7.2 Portable transfer contract

Stage 7 新增 `lmdj.project-bundle.v1`，用于可移植 `.lmdj` 文件的传输封装；它不替代
`lmdj.project.v1` Project Truth。封装必须：

- 携带 `lmdj.project.v1` manifest、Assets、History 与 Recovery 文件；
- 记录每个 regular file 的规范相对路径、字节长度和 SHA-256；
- 使用 UTF-8 路径和稳定排序；
- 拒绝绝对路径、`..`、空路径、重复路径、大小写折叠冲突、NUL、symlink、hardlink、
  device node 与未声明 entry；
- 每个 Project Artifact 继续受 64 MiB Project I/O 上限约束；
- 总解包字节上限为 512 MiB，entry 总数上限为 4096；
- 压缩后或未压缩封装都不得绕过解包字节上限；
- 在导入完成前不成为 `listLocalProjects()` 的可见结果。

容器压缩和索引的具体实现属于新内核设计 §25 允许在实施计划中机械确定的事项；
实施计划必须选择一个跨 Chromium、Safari、Native CLI fixture 可重复生成和验证的
单一格式，不能按浏览器分叉 Contract。

### 7.3 Atomic import

```text
Browser File
  → private OPFS staging
  → transfer inventory validation
  → Project I/O managed-tree validation
  → lmdj.project.v1 load/replay/hash validation
  → destination collision check
  → atomic publish to managed Project root
  → Facade inspect
  → Creator Project list
```

导入规则：

- 相同 `project_id` 且完整 Bundle digest 相同：幂等成功并打开现有 Project；
- 相同 `project_id` 但 digest 不同：返回 `DUPLICATE_ID`，不覆盖、不重命名；
- 验证、配额、中断或 publish 失败：删除或隔离 staging，现有 Project 不变；
- 浏览器重启后遗留 staging 是可清理 Workspace Cache，不是 Project Truth；
- 任何失败都不能留下可被 Project list 发现的半成品目录。

## 8. Creator Workspace

### 8.1 Desktop layout

工作台采用已批准的完整 Creator Workspace：

```text
┌─────────────────────────────────────────────────────────┐
│ LMDJ · Project ID · BPM · Key — · Save Local · Audio   │
├────────────┬────────────────────────────────────────────┤
│ Project    │                                            │
│ Sample S8  │              Mode Surface                  │
│ Sequence S9│                                            │
│ Perform S10│                                            │
├────────────┴────────────────────────────────────────────┤
│ Bank A / B / C / D · fixed 4×4 playable Pad surface   │
└─────────────────────────────────────────────────────────┘
```

与 2026-07-30 总设计相比，本设计明确把模式入口放入左侧 Rail；顶部只保留全局状态和
Audio 状态。这个位置变化由 Stage 7 视觉评审批准。中部 Surface 与底部固定 Pad
原则保持不变。

Stage 7 的 Project Surface 提供：

- `Open local`；
- `Import .lmdj`；
- current Project ID、revision、BPM；
- local/validating/ready/resource-rejected 状态；
- Pad occupancy 汇总；
- 对 Stage 8–10 的只读阶段说明。

### 8.2 Disabled future modes

Sample、Sequence、Perform 在 Rail 中展示阶段编号，但使用真正的 disabled 语义：

- 不进入 Tab 顺序；
- 不响应 Pointer、Keyboard 或路由；
- 不渲染假数据、空编辑器或成功状态；
- Accessible name 明确包含 `available in Stage N`；
- 自动化必须证明不存在相应 Command、Job 或 storage mutation。

### 8.3 Pad surface

- 一次只显示一个 4×4 Bank；
- Bank A–D 覆盖 64 个稳定 Slot；
- Pad 显示 Bank/Pad 地址、键盘映射和 empty/assigned 状态；
- empty Pad 是真实 disabled trigger target，不触发占位声音；
- Pointer/Touch target 最小 `44 × 44 CSS px`；
- Keyboard 与 MIDI mapping 由 Creator 配置注入共享 input adapter；
- 所有输入最终调用同一个 serialized `trigger()` 路径；
- UI press feedback 来自 admission/outcome，不用计时器伪造声音成功。

### 8.4 Responsive boundary

- Desktop：完整 Rail、Project Surface、8-column visual Pad row 可以折为 4×4；
- Tablet：Rail 收缩为带 Accessible name 的图标列，Pad 保持 4×4；
- 最小保证 viewport：`768 × 1024 CSS px` portrait 与 `1024 × 768 CSS px`
  landscape；
- 小于 768 CSS px 的手机布局不是 Stage 7 保证范围；
- 旋转、resize 和 browser chrome 高度变化不得关闭 Project 或 Audio Session。

## 9. State Model and Data Flow

### 9.1 Creator states

Creator UI 使用单一显式状态模型：

```text
booting
  → unsupported
  → empty
  → importing
  → opening
  → ready
  → activating
  → running
  → suspended
  → restart-required
  → failed
  → closed
```

`Project`, `Runtime`, `Audio` 与 `Import` 子状态必须能独立表达；不得仅靠一个绿色或
红色顶层状态隐藏具体失败来源。每个 UI action 在 reducer/state machine 中有明确
合法源状态，非法调用在到达 Platform 前即被拒绝并进入测试。

### 9.2 Open and play journey

```text
preflight
  → list/open or import
  → Facade inspect
  → cook/publish Runtime Snapshot
  → ready
  → user gesture activates AudioContext
  → running
  → Pointer/Keyboard/MIDI Trigger
  → admission
  → runtime outcome
  → visual release
```

Audio 激活永远要求当前用户手势。Reload、Host rebuild、visibility recovery 或
restart-required 恢复后不得自动恢复声音；UI 返回 `ready` 并要求再次激活。

### 9.3 No second truth

React state 只保存 render 所需的 View Model、当前选择和短期 pending action。Project
内容来自 Facade Query/Event；Runtime 状态来自 Platform；UI 不缓存一份可写 Project
对象，不从 Bundle 文件推导 Pad/Asset，也不把 Workspace settings 写回 Project Truth。

## 10. Failure and Recovery

| Error/state | Creator behavior |
| --- | --- |
| `UNSUPPORTED_WEB_RUNTIME` | 显示缺失 capability；不加载 Wasm、不提供 fallback。 |
| `INVALID_PROJECT` | 导入失败，展示安全摘要，清理 staging；现有 Project 不变。 |
| `DUPLICATE_ID` | 明确说明本地已有不同内容的同 ID Project；不覆盖。 |
| `WEB_RUNTIME_RESOURCE_LIMIT` | Project 可 inspect；Audio publish/不支持的 import 被拒绝，显示 observed/limit。 |
| `PROJECT_BUSY` | 保留当前 UI，提供重试；不夺取另一个 writer lease。 |
| `HOST_TIMEOUT` | 请求失败并进入 restart-required；不把未知结果显示为成功。 |
| `HOST_RESTART_REQUIRED` | 关闭旧 Session、重建 Worker、重新打开 Project；Audio 回到 ready。 |
| `HOST_PROTOCOL_MISMATCH` | terminal failed；禁止继续向未知协议发送请求。 |
| `IO_ERROR` | 显示 Project/Import 范围和恢复动作；不泄露绝对路径。 |
| `INTERNAL_ERROR` | terminal failed；保留 OPFS Project，不自动删除用户数据。 |

Stage 7 不捕获异常后静默继续，不播放占位声音，不把 Netlify/浏览器错误改写成 Core
成功，也不把诊断信息中的 UUID、路径、素材名或音频内容发送到外部。

## 11. Security and Privacy

- Creator distribution 必须保持 Cross-Origin Isolation；
- manifest hash、Product/Host/Platform identity 与 Assembly Lock 在加载 Runtime 前
  fail closed；
- Bundle entry 验证发生在 publish 前；
- UI 不使用 `innerHTML` 渲染 Bundle 或错误文本；
- MIDI 权限只由显式用户动作请求；
- 文件选择、MIDI device、Project ID 和素材数据不进入遥测；Stage 7 不加入遥测；
- privacy-safe diagnostics 只包含 allowlisted capability、版本、状态、计数和 typed
  error code；
- OPFS staging、Workspace metadata 与 Project managed root 使用不同 namespace；
- Host close/restart 释放 Worker、MIDI listener、BroadcastChannel 和 AudioContext；
  不能留下第二个活跃输入消费者。

## 12. Build and Distribution

Stage 7 新增稳定入口：

```bash
scripts/creator-web.sh configure
scripts/creator-web.sh build
scripts/creator-web.sh test
scripts/creator-web.sh proof
scripts/creator-web.sh package
scripts/creator-web.sh serve --port PORT
scripts/creator-web.sh clean
```

Creator UI 使用固定版本的 React、React DOM、TypeScript 与 Vite；依赖和 Node/npm
版本必须锁定。选择 React 是因为 Stage 8–12 会在同一 Editor 中增加多个状态复杂的
Surface；UI framework 不得进入 `web-runtime-platform`。

Package 必须：

- 从 clean source 构建；
- 复用同一份 pinned Emscripten Runtime 产物；
- 使用 content-hashed JS/CSS/Wasm assets；
- 生成 `lmdj.creator-web.distribution.v1` manifest；
- 记录 Product Build、Creator Host、Platform、Web Runtime Host compatibility、
  protocol、heap/resource limits 和完整 asset inventory；
- 两次 clean package 字节一致；
- 自带只服务 package root、拒绝 traversal/symlink、发送 COOP/COEP 的本地 server；
- 不包含 source map、测试 fixture、诊断 Project 或未声明文件。

## 13. Testing and Acceptance

### 13.1 Automated gates

每个 Stage 7 集成候选必须通过：

1. `web-runtime-platform` unit/contract tests；
2. Creator reducer、view-model、input mapping 和 disabled-mode unit tests；
3. `.lmdj` transfer schema positive/negative tests；
4. Bundle traversal、duplicate、case-fold、symlink、hash、entry-count、byte-limit、
   collision、中断和 atomic-publish tests；
5. `creator-web` component/build/package/server tests；
6. Chromium packaged E2E：import/open → ready → activate → 4 Banks → 64 Pad
   address verification → reload/reopen；
7. 同步 16-key burst：16 admissions、16 outcomes、0 rejection、Host 保持 running；
8. Web MIDI synthetic mapping、permission rejection 和 listener cleanup；
9. restart-required 后 Project reopen，且 Audio 不自动激活；
10. WebKit capability-boundary tests，不能把 skip 说成 Safari physical pass；
11. `scripts/web-runtime-host.sh proof` 全量回归；
12. `scripts/core.sh proof` 全量回归；
13. dependency、active-tree、version、Assembly Lock 与 Architecture Portal gates；
14. deterministic clean package comparison。

浏览器测试必须操作用户可见 Creator controls，不得从 `page.evaluate()` 直接调用内部
Bridge 代替产品 Journey。

### 13.2 Accessibility and responsive acceptance

- 所有 control 有稳定 Accessible name 和可见 focus；
- Project import/open 和 Bank 选择可仅用 Keyboard 完成；
- Pad keydown/keyup 不重复触发，blur/visibility 释放 press state；
- disabled future modes 不进入 Tab 顺序；
- Playwright 覆盖 `768×1024`、`1024×768`、`1440×900`；
- 关键状态截图用于布局回归，但截图不能替代行为断言。

### 13.3 Manual canary acceptance

从 clean Creator package 执行：

1. 打开 Creator；
2. 导入正式 fixture `.lmdj`；
3. 观察 Project ID、revision、BPM 和 Pad occupancy；
4. 激活 Audio；
5. Pointer、Keyboard 各演奏 Bank A 的 16 Pad；
6. 切换 B/C/D 并抽样确认地址与声音；
7. suspend → activate；
8. reload → reopen → activate；
9. 确认无重复、漏触发、卡住 press、自动播放或 Project 数据丢失；
10. 导出 privacy-safe acceptance report。

五项 Stage 6 实体 Web physical rows 保持 `deferred / unverified`。它们不阻塞 Stage 7
canary implementation merge，但继续阻塞 physical-pass、`beta` 与 `stable`。

## 14. Version Management

Stage 7 的目标版本为：

| Identity | Baseline | Target | Reason |
| --- | --- | --- | --- |
| Product Build | `1.0.15.0` | `1.0.16.0` | 新增 Assembly-listed Creator Host、Platform Module 与 Project Bundle transfer Contract。 |
| `creator-web` | absent | `1.0.0` | 第一个正式 Creator Product Host。 |
| `web-runtime-platform` | absent | `0.1.0` | 新产品中立 Browser Runtime Session API，仍处于内部演进期。 |
| `web-runtime-host` | `1.1.0` | `1.2.0` | 向后兼容地改为消费公开 Platform Module，诊断协议语义不变。 |
| `application-facade` | `1.2.0` | `1.3.0` | 新增原子 Project Bundle import 能力。 |
| `project-io` | `0.4.0` | `0.5.0` | 新增 transfer inventory 验证、staging 和 atomic publish。 |
| `audio-runtime` | `0.4.0` | unchanged | Stage 7 不增加 DSP、Voice 或 realtime contract。 |
| `core-cli` | `1.0.5` | `1.0.6` | 精确 `application-facade` 依赖传播，不新增 CLI 命令。 |
| `core-mcp` | `1.1.2` | `1.1.3` | 精确 `application-facade` 依赖与 Python package identity 传播。 |
| `native-test-host` | `1.0.3` | `1.0.4` | 精确 `application-facade` 依赖传播，不改变 Native Host 行为。 |
| `lmdj.project.v1` | `1.0.0` | unchanged | Project Truth shape 不变。 |
| `lmdj.project-bundle.v1` | absent | `1.0.0` | 新增可移植 transfer envelope；不替代 Project Truth。 |

`1.0.16.0` 依赖 `1.0.15.0` 先在 `main` 成立。若另一个已批准 Product Assembly
Change 在 Stage 7 合入前占用后续 Build，实施计划必须在写入任何版本文件前重新分配
下一个未使用 BUILD；已用或放弃编号不得复用。

Stage 7 分配 Product Build，因此 Documentation impact 必须为 `required`，同步：

- `/`；
- `/core/overview/`；
- `/core/modules/application-facade/`；
- `/core/modules/project-io/`；
- 新增 `/core/modules/web-runtime-platform/`；
- `/hosts/overview/`；
- `/hosts/web-runtime/`；
- 新增 `/hosts/creator-web/`；
- 新增 `/contracts/project-bundle/`；
- `/platform/web-runtime/`；
- `/platform/input/`；
- `/platform/storage/`；
- `/assembly/lmdj/`；
- `/operations/testing-and-proof/`；
- `/operations/version-and-release/`；
- 对应 Module/Host diagram sources 与 generated outputs。

实施分支必须在 clean committed source boundary 运行：

```bash
scripts/architecture-portal.sh version 1.0.16.0 canary
```

Tag 创建、tag push、PR、merge、部署和 Channel promotion 仍分别需要授权。

## 15. Rollback and Compatibility

- `creator-web` 可以从 Assembly 移除而不改变 `lmdj.project.v1`；
- 已导入 OPFS Project 保持有效，后续兼容 Host 可重新打开；
- `web-runtime-host 1.2.0` 必须保持 Stage 6 private protocol `1` 与诊断 Journey；
- `lmdj.project-bundle.v1` 导入不得升级或重写 Project Truth；
- rollback 到 `1.0.15.0` 不删除 Project，但没有 Creator UI；
- 不移动或复用 tag，不删除失败 Build 的证据。

## 16. Rejected Directions

### 16.1 把 Creator 模式加入诊断 Host

拒绝。它会把产品视觉、路由和未来 Surface 带入产品中立 Conformance Host，使诊断
Proof 与产品行为无法独立演进。

### 16.2 Creator 复制 Stage 6 Bridge

拒绝。重复的 Worker、OPFS、AudioWorklet 和 Trigger 状态机会形成第二套 Web Core，
使一个修复无法同时保护两个 Host。

### 16.3 UI 直接读取 Bundle

拒绝。它绕过 Facade/Project I/O，建立第二个 Project parser，并使 Native/Web 对
恢复、path safety 和 revision 的理解分叉。

### 16.4 Stage 7 提前启用 Take 或 Sample Editor

拒绝。Take 并发是 Stage 9 的正式设计问题，Sample 是 Stage 8；提前暴露会把未解决
Contract 塞进 Editor 基础设施 Task。

### 16.5 自动恢复 Audio

拒绝。Browser autoplay policy 和用户可预期性要求每次新 Session 都由明确手势激活。

## 17. Definition of Stage 7 Complete

Stage 7 只有在以下证据全部成立时才完成：

- 本文的 D1–D8 决策均由实现与测试覆盖；
- `web-runtime-platform` 是唯一共享 Browser Runtime Session 实现；
- `web-runtime-host` 仍是独立产品中立诊断 Host，现有完整 Proof 通过；
- `creator-web` 进入 active `apps/` 和 Product Assembly；
- Creator 只使用 Platform/Application Facade，不解析 Bundle 或调用 Project I/O；
- 本地 Project discovery 与 `.lmdj` import 通过确定性、path safety 和 atomicity gates；
- Project Surface、左 Rail、固定 4×4 Pad 与四 Bank 响应式工作台实现；
- Sample/Sequence/Perform 保持真实 disabled 且无 mutation；
- Pointer、Keyboard、MIDI 共用 Trigger path，admission/outcome 完整；
- reload/restart-required recovery 保留 Project 且不自动激活 Audio；
- Creator clean package 可重复、可本地 serve，并通过 Chromium/WebKit 自动化边界；
- Core Proof、Web Runtime Host Proof、Creator Proof、版本、依赖、Assembly 与 Portal
  门禁全部通过；
- `1.0.16.0 · canary` current docs 与不可变 Portal snapshot 匹配；
- 分支经 Review、squash merge 到 `main`，并从 merged `main` 重跑 required Proof；
- 五项实体物理门槛继续准确标为 `deferred / unverified`；
- 没有把 tag、Release、deployment、`beta` 或 `stable` 伪装成 Stage 7 完成结果。

## 18. Spec Self-review Checklist

- Stage 7 与 Stage 8–12 边界明确，无提前实现的 Take/Sample/Perform 功能。
- Creator、Platform、Diagnostic Host、Facade 和 Project I/O ownership 单一。
- UI 没有第二份可写 Project Truth。
- Portable transfer Contract 不替代 `lmdj.project.v1`。
- Bundle import 对 traversal、collision、quota、interruption 和 publish fail closed。
- UI 不显示猜测的 Project Name 或 Key。
- Audio 激活始终需要用户手势。
- Disabled future modes 不可聚焦、不调用、不持久化。
- 自动化 WebKit 不被描述为实体 Safari 验收。
- Product Build、Module、Host 和 Contract 版本身份彼此独立。
- Documentation impact、快照、tag、merge、deployment 和 Channel 权限边界明确。
- 文档没有 `TBD`、`TODO`、占位门槛或未说明的成功状态。
