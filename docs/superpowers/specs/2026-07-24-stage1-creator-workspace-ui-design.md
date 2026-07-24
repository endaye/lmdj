# LMDJ Stage 1 Creator Workspace UI 设计

- 日期：2026-07-24
- 状态：已评审设计，尚未实施
- 目标落点：`apps/web/`
- 视觉基准：1440×900，自适应到不同宽高比

## 1. 设计结论

Stage 1 使用 **Instrument-first Canvas**：

- `Pattern` 在上，`16-pad` 在下。
- 16 个 Pad 是工作台的视觉和交互中心。
- 桌面宽屏采用左侧 Creator Tools、中间 Pattern + Pad、右侧上下文 Inspector。
- Pad 尽量保持 1:1 正方形；空间不足时先调整外部 margin、Pattern 高度和面板呈现方式，不拉伸 Pad。
- 600–959px 使用 4×4 Pad；四行和四列共享同一个 gap token，行距与列距必须相等。
- 视觉语言参考 Kumaleon 的米白画布、粗黑边界、超大标题、高饱和色块和生成图形，但颜色和图形必须服从可学习的产品规则。
- Source、Processing、Patch、Play/Take、Export 都在同一台“乐器”中发生，不切换成无上下文的后台页面。
- 失败、质量不足和部分导出必须显性呈现；不以假数据或静默回退制造成功。

## 2. 已落地、部分接入与本设计边界

### 2.1 已落地

- 浏览器上传 → API → Audio Worker → Patchify → `patch.json` → Web Patch View 的链路已跑通。
- Web 已通过唯一入口 `loadPatch` 读取并校验 `patch.json`。
- 当前 Patch View 已支持 8-pad 显示、触发、静音和 Pattern 回放。
- `lmdj.patch.v1` Schema 的 `pads` 是数组，Schema 本身未限制为 8 个。

### 2.2 部分接入

- 当前前端可遍历 `patch.pads`，但 `PAD_KEYS`、测试、Focus Slot 语义和视觉布局仍以 8-pad 为前提。
- 当前 Schema 可容纳 16 个 Pad，但 Patchify 的 `FOCUS_SLOTS` 和 `map_focus_pads` 固定产出 8 个。
- Source、Processing 和 API 状态已存在基础页面，但尚未形成本文定义的统一 Instrument-first 状态系统。

### 2.3 仅设计，尚未实施

- 16-pad Stage 1 语义与映射。
- 本文定义的 Creator Tools、上下文 Inspector、AI Preview、Take 和 Creator Export UI。
- Kumaleon 启发的视觉系统、生成图形签名和动效。
- 600px 以下的正式移动端工作台。
- Generate、Line-in、AI Variation 与 Creator Export 的完整后端能力。

实现不得把“Schema 能解析任意数量的 pads”误报成“16-pad 端到端已支持”。16-pad 必须由 producer、共享契约语义、Web、CLI/Worker/API 相关测试一起迁移。

## 3. 设计输入

- 本次评审原型：[Stage 1 Creator Workspace UI 视觉参考](./2026-07-24-stage1-creator-workspace-ui-references/README.md)。
- 飞书 PRD：`LMDJ 软件 MVP Stage 1–4 与团队协作 Memo｜2026-07-18`，文档 revision 63。
- PRD 硬件参考：2×8 Pad、Pad 上方 21:9 屏幕、左侧高频控制区。
- 视觉参考：[Kumaleon](https://kumaleon.com/)。
- 当前 Web Patch View 与 `2026-07-07-lmdj-web-patch-view-design.md`。
- 当前产品边界：消费者只读取 `patch.json`，不读取 `lanes.json` 或 `chart.mid`。

视觉参考用于提炼语言，不复制角色、Logo、插画或品牌资产。

## 4. 目标与非目标

### 4.1 目标

1. 让 DAW 创作者从 Source 到可演奏 Patch，再到 Creator Export，在一个可理解的工作台内完成。
2. 让 16-pad 在软件、通用 MIDI Controller 和未来硬件之间建立稳定空间映射。
3. 让 AI 变化可见、可试听、可比较、可撤销，不覆盖可信的手动状态。
4. 让布局适配不同尺寸，同时保护 Pad 的正方形触点、编号顺序和一致 gap。
5. 让质量不足、处理中断和部分导出都有真实、可恢复的状态。

### 4.2 非目标

- 完整 DAW Timeline、Automation 或 Song Arrangement。
- Stage 3 Learn / Arcade QTE。
- 社区、Marketplace、跨用户 Fork。
- 自研硬件工程实现。
- 在 Stage 1 内完成所有生成 Provider、Line-in 和 DAW 工程格式。

## 5. 1440×900 信息架构

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ LMDJ | Project / BPM / Key | Undo Save Play Rec | Export                │
├────────────┬─────────────────────────────────────────────┬───────────────┤
│ Creator    │ MAKE IT PLAYABLE                            │ Context       │
│ Tools      │                                             │ Inspector     │
│            │ Pattern / playhead / pattern tabs           │               │
│ Source     │                                             │ selected Pad  │
│ Chop       │ [01][02][03][04][05][06][07][08]            │ waveform      │
│ AI         │ [09][10][11][12][13][14][15][16]            │ parameters    │
│ Loop       │                                             │ AI Preview    │
│ Takes      │                                             │ compare/apply │
├────────────┴─────────────────────────────────────────────┴───────────────┤
│ Bank / Patch readiness / MIDI connection / blockers / zoom              │
└──────────────────────────────────────────────────────────────────────────┘
```

### 5.1 Top App Bar

固定显示：

- LMDJ Wordmark。
- Project 名称、BPM、Key、时长。
- Undo、Save、Play、Record。
- Creator Export 入口。

顶部不承担复杂编辑；它只保留跨模式稳定动作。

### 5.2 Creator Tools

左栏是稳定工具模式：

| 模式 | 职责 |
|---|---|
| Source | Generate、Upload、Line-in、原始素材与 Stems |
| Chop | Slice、Swap、Start/End、Loop、One-shot、Pad Mapping |
| AI | Generate、Replace、Variation、Compare、Accept、Discard |
| Loop | Pattern、量化、Roll、循环播放 |
| Takes | Record、Replay、Take 列表 |

切换工具模式不改变 Pad 的空间位置或演奏语义。

### 5.3 Pattern Surface

- 永远位于 Pad 上方。
- 显示当前 Pattern、播放头、节拍网格和 Pattern A–D。
- 默认不是完整编曲 Timeline。
- 低高度窗口先压缩 Pattern 高度，再允许页面纵向滚动；不得压缩 Pad 为不可演奏尺寸。

### 5.4 16-pad Surface

- 桌面默认 8×2。
- Pad 顺序固定为 01–16。
- 顶排默认键盘提示为 `1 2 3 4 5 6 7 8`。
- 底排默认键盘提示为 `Q W E R T Y U I`。
- 通用 8-pad Controller 使用 Bank A/B 映射；UI 必须同时显示逻辑 Slot 与当前硬件 Bank。
- 16-pad Grid 的整体宽高比为 4:1；每个 Pad 使用 `aspect-ratio: 1`。

### 5.5 Context Inspector

只显示当前上下文：

- 未选中对象：Patch 摘要、质量、未映射项、Export blocker。
- 选中 Pad：声音名、角色、波形、Start/End、Mode、Volume、Mute、Swap。
- AI Preview：原素材与候选素材的 Compare、Accept、Discard。
- 窄屏：右侧抽屉或全高 Sheet，不占据常驻列。

### 5.6 Status Bar

显示：

- 当前 Bank。
- Patch Ready / Partial / Needs Review。
- MIDI 与音频设备连接状态。
- Export blocker 数量。
- 缩放。

流程进度以状态呈现，不在主工作台上保留大型 Stepper。

## 6. 响应式规则

响应式由 Workbench 容器宽高决定，不依赖设备名称。

| 容器宽度 | 布局 | Pad |
|---|---|---|
| ≥1280px | 左侧文字工具栏 + 中央 Canvas + 常驻 Inspector | 8×2 |
| 960–1279px | 图标工具栏 + 中央 Canvas；Inspector 抽屉 | 8×2 |
| 600–959px | 工具栏移到底部；Inspector 覆盖式抽屉 | 4×4 |
| 360–599px | 紧凑 Top Bar + 底部模式栏；参数为全高 Sheet | 4×4 |

### 6.1 Square Pad 规则

```css
.pad {
  aspect-ratio: 1;
}
```

- Pad 不因容器高度被纵向拉伸。
- 8×2 能维持可点击尺寸时不切换。
- 小于 960px 时按行连续重排为 4×4，编号顺序不变。
- 360px 以下不是 Stage 1 保证范围。

### 6.2 Uniform Gap 规则

4×4 使用一个变量同时控制行列间距：

```css
.pad-grid {
  --pad-gap: clamp(8px, 1.4cqw, 16px);
  column-gap: var(--pad-gap);
  row-gap: var(--pad-gap);
}
```

实现时必须验证 computed `row-gap === column-gap`。空间不足时按顺序处理：

1. 收缩 16-pad Grid 外部 margin。
2. 收缩 Pattern 的非必要高度。
3. 收起 Inspector。
4. 允许 Workbench 纵向滚动。

不得单独压缩 row-gap，也不得让相邻 Pad 边框重合。

### 6.3 超宽屏

- 左栏和 Inspector 设置最大宽度。
- 多余宽度优先给 Pattern 和 Pad Surface。
- 不因 21:9 增加新的常驻信息密度。
- Pad 仍为正方形；无法继续放大时由 Canvas 留白吸收空间。

## 7. 视觉系统

### 7.1 基础色

| Token | 值 | 用途 |
|---|---:|---|
| `paper` | `#F6F2E8` | 主画布、空白、面板底 |
| `ink` | `#11110F` | 粗边框、主文字、硬阴影 |
| `drums` | `#FF4F31` | Drum Role |
| `bass` | `#8A4AF3` | Bass Role |
| `harmony` | `#46C79B` | Harmony Role |
| `lead` | `#FFD21C` | Lead / Vocal Role |
| `loop` | `#32C7E9` | Loop Role |
| `action` | `#FF69C8` | Fill / Drop / Roll / FX / Variation |
| `muted` | `#D5CFC2` | Muted / inactive |

状态不能只依赖颜色；必须同时使用边框、文字、图案或图标。

### 7.2 Pad 图形签名

每个 Asset 获得确定性图形签名：

- 输入：`asset_id`、`source_type`、Role 与可用的音频特征。
- 同一个 Asset 跨刷新、参数编辑和版本保持同一签名。
- Replace 产生新 Asset，因此产生新签名。
- 参数编辑不改变 Asset 身份，不改变签名。
- 图形使用圆、方、线、条纹等基础几何；不使用 Kumaleon 的角色或品牌资产。

V1 可先以 `asset_id` 哈希驱动几何组合，音频特征接入作为后续增强。

### 7.3 信息层级

Pad 内优先级：

1. Slot 编号与音乐角色。
2. 声音名。
3. 键位提示。
4. Mode、音量、时长等元数据。

演奏态不显示完整参数；参数属于 Inspector。

## 8. Pad 状态与动效

| 状态 | 视觉 |
|---|---|
| Idle | 角色色 + 图形签名 |
| Hover / Focus | 上移 3px + 黑色硬阴影；键盘 focus 同等可见 |
| Playing | 压缩 7% 后轻微回弹；外圈闪一次 |
| Selected | 双层黑框；Inspector 头部同步使用角色色 |
| Muted | 降彩度 + `MUTED` + 删除线，不移除原角色轮廓 |
| AI Preview | 原/候选双色条纹 + `AI PREVIEW` |
| Missing / Error | 米白底 + 红色虚线边框 + 错误图标 |
| Empty | 米白底 + Slot 编号 + `EMPTY`，不可伪装成可播放 |

### 8.1 动效时长

- Trigger：120ms。
- Hover / Focus：80–120ms。
- Inspector 切换：160ms。
- AI Preview Morph：320ms。
- Loop 内部图形：按一拍缓慢运动；不让整个 Pad 持续闪烁。

`prefers-reduced-motion` 下取消位移、回弹和 Morph，只保留静态状态变化。

## 9. Stage 1 页面状态

### 9.1 Empty / Source

同一 Source 面板提供：

- Generate。
- Upload。
- Line-in。

Upload 在处理前显示格式、时长与体积限制。原始音频进入项目后必须持久保留。

### 9.2 Processing

显示真实阶段：

```text
Input Validated → Stem Separation → Chop + Map → Patch Verify
```

每阶段显示：

- 状态：waiting / running / completed / failed。
- 已完成产物数量。
- 真实耗时。
- 可恢复动作。

未知进度不显示伪造百分比。用户可离开页面，项目状态必须保留。

### 9.3 Patch Ready

进入本文主工作台：

- Pattern 在上。
- 16-pad 在下。
- 可通过点击、键盘或 MIDI 触发。
- Pad 选择驱动 Inspector。
- Take、AI Preview 和 Export 使用相同 Patch 状态。

### 9.4 Quality Needs Review

分轨或切片质量不足时：

- 保留原始音频与已成功产物。
- 标记受影响的 Pad 或 Stem。
- 提供 Keep Original Layer、Retry、Manual Remap。
- 不自动用假素材填满 16 个 Pad。

### 9.5 Failed

- Source 不丢失。
- 显示失败阶段与可读原因。
- 可重试失败步骤或返回 Source。
- Provider 失败时允许切换 Upload，不改变已保存项目。

### 9.6 Creator Export

Export 是清单，不是单一成功 Toast：

| 项目 | 状态 |
|---|---|
| Stems | Ready / Review / Missing |
| Samples / Slices | Ready / Review / Missing |
| MIDI | Ready / Missing |
| Full Take | Ready / Missing |
| BPM / Key / Time Signature / Loop Metadata | Ready / Missing |
| DAW-specific project | Available / Unsupported / Failed |

部分导出必须标为 Partial，并列出缺失项。

## 10. 数据流与组件边界

```text
Source UI
  → API job/status
  → patch.json + audio files
  → loadPatch
  → PatchBundle
  → WorkbenchViewModel
      ├─ PatternSurface
      ├─ PadMatrix16
      ├─ ContextInspector
      ├─ CreatorTools
      └─ ExportChecklist
  → AudioEngine
```

### 10.1 契约纯度

- Web 仍只读取 `patch.json` 和其中引用的文件。
- 不读取 `lanes.json`、`chart.mid` 或 `report.json` 来补 UI。
- 处理质量、Export blocker、Asset 来源等新信息必须进入正式产品契约或 API 状态模型。

### 10.2 16-pad 契约迁移

当前真实基线：

- Schema 接受任意长度 `pads`。
- Patchify 固定产出 8 个 Focus Slots。
- Web 默认键位和测试固定为 8。

本设计决定继续使用 `lmdj.patch.v1` 的可变长度 `pads`，正式支持 8-pad 旧 Patch 与 16-pad Stage 1 Patch。仅增加 Pad 数量不创建新 Schema 版本；若实施需要新增必填字段或改变既有字段语义，则必须另行评审 Schema 版本。

实现 16-pad 时必须：

1. 在 Decision Log 确认 16 个 Slot 的正式语义和 reserved/live action。
2. 原子更新 Core Models、Patchify、Audio Worker、API fixture、Web Contract 输出与测试。
3. 保留对旧 8-pad Patch 的兼容展示：8 个 Pad 正常显示，其余 Slot 为 Empty；不得伪造音频。
4. `npm run sync-contract` 后以 `npm run check-contract` 防止生成物漂移。

### 10.3 主要 UI 单元

| 单元 | 职责 | 依赖 |
|---|---|---|
| `WorkbenchShell` | App Bar、三栏/抽屉/底栏响应式编排 | Workbench ViewModel |
| `CreatorToolRail` | 稳定工具模式切换 | UI state |
| `PatternSurface` | Pattern、播放头、Pattern tabs | Patch + AudioEngine clock |
| `PadMatrix16` | 8×2 / 4×4 排列、触发、选择、状态 | pads + input mapping |
| `PadButton` | 单 Pad 视觉、ARIA、动效 | Pad ViewModel |
| `ContextInspector` | 当前 Pad / Asset / Patch 编辑 | selection + actions |
| `SourcePanel` | Generate / Upload / Line-in | API client |
| `ProcessingPanel` | 真实 Job 状态与恢复动作 | job status |
| `ExportChecklist` | 导出项与 Partial 结果 | export manifest |

每个单元只依赖明确的 ViewModel，不直接读取 pipeline 原始文件。

## 11. 错误处理

| 情况 | UI 行为 |
|---|---|
| 文件格式、时长或体积不支持 | 处理前拒绝，显示支持范围 |
| Provider 超时 | 保留项目，重试或切换 Upload |
| 分轨/切片失败 | 保留 Source 和成功产物，标记受影响对象 |
| 只有部分 Pad 可播放 | 可播放 Pad 正常工作；其余为 Empty/Error |
| 音频文件缺失或解码失败 | 对应 Pad Error；Pattern 数据不删除 |
| AI Preview 失败 | 当前 Pad 不变，候选标 Failed，可重试 |
| Export 部分失败 | 清单标 Partial，允许导出已完成项 |
| 未知 Job 状态 | 显示可读的 Unknown 状态和原始阶段名，不重置进度 |

## 12. 可访问性

- 每个 Pad 是可聚焦 button，并有可读名称：`Pad 06, Harmony, Chord Slice, selected`。
- Playing、Muted、Preview、Error 同时使用文字/图标与颜色。
- 默认键盘映射可在设置中重映射，UI 提示从 Input Mapping 读取，不散落硬编码。
- Touch target 不小于 44×44 CSS px。
- Focus 样式不被 Hover 覆盖。
- 支持 `prefers-reduced-motion`。
- Pattern 与状态列表提供非视觉文本摘要。
- 颜色组合需达到 WCAG AA；大面积彩色 Pad 上的文字按角色色选择黑或白。

## 13. 测试与验收

### 13.1 合同测试

- 8-pad 旧 Patch 兼容。
- 16-pad 新 Patch 完整渲染。
- `scene.pad_indexes` 覆盖 0–15。
- reserved / unknown action 仍为 disabled/no-op。
- Web 只读 `patch.json`。

### 13.2 组件测试

- 渲染恰好 16 个 Slot。
- Pattern 在 DOM 与视觉顺序上位于 Pad Grid 之前。
- 选中 Pad 更新 Inspector。
- AI Preview 不替换当前 Asset，Accept 后才切换。
- Missing / Error / Muted 不只依赖颜色。
- Keyboard 与 MIDI 映射触发正确逻辑 Slot。

### 13.3 响应式测试

自动检查：

- 1440×900。
- 1280×720。
- 1024×768。
- 768×1024。
- 390×844。

断言：

- 每个 Pad 的宽高差不超过 1 CSS px。
- 600–959px 时 computed `row-gap === column-gap`。
- 任意相邻 Pad 不重叠。
- 8×2 与 4×4 断点正确。
- Inspector 抽屉不遮挡当前触发反馈。
- 低高度窗口可以滚动，Pad 不被压扁。

### 13.4 端到端验收

1. Upload 一首真实音频并看到真实处理阶段。
2. 得到 16 个逻辑 Slot；没有素材的 Slot 明确显示 Empty。
3. 点击、键盘和 MIDI 触发一致。
4. Pattern 位于 Pad 上方并跟随播放头。
5. AI Variation 可 Compare、Discard、Accept，原素材在 Accept 前不变。
6. 录制 Take 后可回放。
7. Export 清单可区分 Ready、Review、Missing 和 Partial。
8. 质量不足或处理失败时，Source 和成功产物不丢失。

## 14. 实施顺序建议

1. 记录 16-pad Slot 与契约迁移决策。
2. 更新 producer、fixture 与 contract tests。
3. 建立视觉 token、WorkbenchShell 和响应式骨架。
4. 实现 Pattern 上 / Square Pad 下的 16-pad Surface。
5. 实现 Context Inspector 与 Pad 状态。
6. 整合 Source、Processing 与失败状态。
7. 实现 AI Preview、Take 与 Export Checklist。
8. 完成响应式、可访问性与真实浏览器验收。

这份文档定义产品与 UI 设计，不替代逐文件实施计划。
