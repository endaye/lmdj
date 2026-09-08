# LMDJ Polanyi Living Instrument UI 设计

- 日期：2026-07-27
- 状态：本分支已实现并通过自动化验证；待 PR / CI
- 目标落点：`apps/web/`
- 设计范围：我的歌曲 → 上传 / 处理 → Creator Workbench → Creator Export
- 实施优先级：Creator Workbench 演奏体验优先，流程一致性其次

## 1. 结论

本轮将 LMDJ 设计成一件 **Living Instrument（活的乐器）**：

- 用户通过稳定的 Pad 位置、键位、边框、播放头与一拍轨迹形成动作记忆；
- 界面说明在用户开始操作后降低存在感，但状态、错误与阻塞始终显性；
- 同一套确定性生成视觉语法贯穿歌曲记录、处理、演奏与导出；
- 所有 UI 组件保持直角、无阴影，以极度克制的平面网格承载音乐与生成艺术；
- Kawaii 角色、Chameleon、表情和高度亲和的叙事舞台集中到未来独立层，不进入本轮。

本轮保留项目总方向中的 Generative Art，但只吸收 Kumaleon 研究里的：

```text
严格版式
  ×
受控随机
```

不在当前 UI 中实现：

```text
可爱角色
  ×
动态角色表面
```

## 2. 设计依据与边界

### 2.1 依据

- [KUMALEON 视觉、3D、生成艺术与 Web3 技术研究](../research/2026-07-26-kumaleon-visual-technology-study.md)
- [LMDJ Stage 1 Creator Workspace UI 设计](2026-07-24-stage1-creator-workspace-ui-design.md)
- [Kumaleon 官网](https://kumaleon.com/)
- 当前 `apps/web` 的 16-pad、Pattern、My Songs、上传状态、Inspector 与 Creator Export 实现

### 2.2 参考边界

可以吸收：

- 暖米白纸面与黑色结构线；
- 瑞士网格、表格式分区、巨型字与小型系统标签；
- 严格版式和受控生成图形的对比；
- 稳定身份与确定性视觉变化；
- 不同页面使用同一语法、不同舞台。

不得复制：

- KUMALEON 角色轮廓、Logo、字体、原始皮肤或品牌文案；
- 官网逐像素版式；
- 3D 模型、钱包、NFT 或 Web3 交互；
- 未核实授权的生成艺术代码。

### 2.3 规范优先级

本 Spec 是
[LMDJ Stage 1 Creator Workspace UI 设计](2026-07-24-stage1-creator-workspace-ui-design.md)
的增量视觉覆盖：

- 保留其 Instrument-first 信息架构、Pattern / Pad 顺序、响应式断点、
  Square Pad、Uniform Gap、状态真实性与可访问性要求；
- 覆盖其中关于圆角、硬阴影、Hover 上移、缩放回弹和持续环境动效的规则；
- 两份 Spec 冲突时，本 Spec 的直角、无阴影和平面反馈规则优先；
- 两份 Spec 都未定义的产品范围继续以 Stage 1 Creator Core 和当前实现为准。

## 3. 当前状态与本设计增量

### 3.1 已落地

- 16-pad Creator Workbench；
- Pattern、播放头、播放、静音、键盘与 Web MIDI；
- `PadButton` 的确定性几何签名基础；
- My Songs、独立上传、真实 Job 状态、刷新恢复；
- Creator Export Checklist；
- 1280 / 960 / 600 / 360px 容器布局与响应式回归；
- Web 只读取 `patch.json` 和公开产品状态。

### 3.2 本设计新增

- 波兰尼默会知识理论驱动的交互层级；
- 全流程共享的 `VisualSignature` 语法；
- 直接演奏触发的一拍 `PerformanceTrace`；
- 全部 UI 直角、无阴影的统一表面规则；
- My Songs、Processing、Workbench 与 Export 的视觉连续性；
- 对上述规则的单元、组件和浏览器验收。

### 3.3 本轮边界

- 视觉重构与 Performance Trace 已在本轮落地；以下内容仍明确不在本轮范围内；
- Chameleon 2D / 3D、角色状态机和皮肤系统不在本轮；
- 不修改 Audio Worker、API、Patchify 或共享契约。

## 4. 波兰尼理论的界面转译

波兰尼的默会知识理论强调：人能够借助近端线索，注意并理解远端整体；熟练行动也不依赖把每一步都转换成显式规则。

在 LMDJ 中：

| 层次 | 产品对应 |
|---|---|
| 近端线索 | Pad 位置、键位、角色色、边框、按压反馈、播放头、一拍轨迹 |
| 远端整体 | 正在演奏什么、节奏如何组织、Patch 是否可继续制作或导出 |

设计遵守四项原则。

### 4.1 空间稳定

- Pattern 永远在 Pad 上方；
- Pad 顺序与硬件 / 键盘映射不随模式变化；
- Creator Tools、Canvas、Inspector 和 Status Bar 保持稳定职责；
- 状态改变内容，不搬动核心演奏控件。

### 4.2 说明退后，反馈保留

- 初次进入保留键位、Slot 和状态文字；
- 用户开始演奏后，说明降低视觉优先级；
- 按压、声音、播放头和轨迹成为主要反馈；
- 错误、质量问题和 Export blocker 永不退后或隐藏。

### 4.3 动作与结果闭环

```text
看见可行动线索
  → 预测结果
  → 触发 Pad
  → 立即听见并看见反馈
  → 在 Pattern 中理解节奏关系
```

界面教授动作与结果的关系，不依赖教程覆盖层。

### 4.4 生成艺术服务理解

生成图形只承担：

- 稳定身份；
- 直接演奏反馈；
- 真实处理阶段的视觉连续性；
- 项目导出的视觉印章。

生成图形不承担：

- 伪造进度；
- 替代错误说明；
- 承载核心操作；
- 盖住 Pad、Pattern、Inspector 或 Export。

## 5. 选定方向

### 5.1 Living Instrument

完整流程被视为同一件乐器的不同状态：

```text
歌曲进入
  → 视觉种子建立
  → 真实处理阶段组装图形
  → 演奏留下短暂轨迹
  → Export 凝结为项目印章
```

### 5.2 未采用方向

| 方向 | 未采用原因 |
|---|---|
| Instrument Skin | 只改 Workbench 表面，无法解决流程页与演奏页割裂 |
| Generative Gallery | 艺术层成为第一视觉层，会削弱演奏效率、状态真实性与长期可用性 |
| Kawaii Guide Signals | 更像助手教学；当前阶段应让乐器本身成为主角 |
| Peripheral Field | 持续背景运动会增加注意负担，不如直接演奏轨迹精确 |

## 6. 视觉系统

### 6.1 总体语言

```text
暖米白纸面
  + 黑色结构网格
  + 角色 / 状态功能色
  + 确定性 2D 几何
  + 零圆角
  + 零阴影
```

### 6.2 直角规则

以下所有 UI 表面使用 `border-radius: 0`：

- App Bar；
- Creator Tool Rail；
- Pattern 与 Step Grid；
- Pad；
- Inspector；
- Status Bar；
- Button、Toggle、Badge、Tab；
- Dialog、Sheet、Backdrop 内面板；
- Song Card、Upload、Processing 和 Export Checklist。

圆、弧线、波形和自由曲线只能出现在生成艺术层，不得改变控件轮廓或命中区域。

### 6.3 无阴影规则

当前范围内所有 UI 使用：

```css
box-shadow: none;
```

层级由以下手段建立：

1. 边框粗细；
2. 网格分区；
3. 留白；
4. 字号和字重；
5. 功能性色块；
6. 必要的平面遮挡。

不得使用硬阴影制造悬浮卡片，也不得用 `box-shadow` 模拟 Focus Ring。

### 6.4 色彩

- `paper / ink` 承担绝大部分 UI；
- 高饱和色只用于音乐角色、真实状态、选择反馈和生成图形；
- 非必要容器保持米白或白色；
- 状态必须同时使用文字、图标、边框或纹理，不能只靠颜色。

### 6.5 排版

- 巨型 `LMDJ` 或短项目标识可以作为低对比远景，不承担操作文字；
- 系统标签、编号和状态使用等宽字体；
- 项目名、声音名和主要标题使用现有产品字体；
- 正文、错误与状态信息不得复刻展览网站的小字号；
- 视觉装饰不得截断关键操作标签。

### 6.6 三层深度

| 层 | 内容 | 约束 |
|---|---|---|
| 远景 | 低对比品牌字、确定性项目图形 | 不接收交互，不影响可读性 |
| 中景 | Pattern、Pad、Processing Stage | 核心视觉与操作区域 |
| 近景 | 结构线、状态、Focus、Inspector、Export | 始终保持最高可读性 |

没有 3D 模型时，不用阴影模拟 3D 深度。

## 7. Visual Signature

### 7.1 语法

```text
视觉结果
  = 固定图元集合
  × 有限调色板
  × 稳定 seed
  × 状态参数
```

图元允许：

- 圆；
- 方；
- 线；
- 条纹；
- 波形段；
- 规则网格；
- 有限角度与偏移。

### 7.2 稳定身份

- API 上传项目：以 browser-owned `submissionId` 作为流程 seed，并在 Loaded / Export 状态继续携带；
- 本地 Patch 与内置示例：以公开 `patch_id` 作为项目 seed；
- Pad：沿用公开的 `element_id ?? slot`；
- 不使用 `materials.json`、stems、`lanes.json`、`chart.mid` 或 Worker 私有字段；
- 本轮不从音频分析推导密度或颜色，避免新增假语义。

### 7.3 跨页面用法

| 页面 | Visual Signature 用法 |
|---|---|
| My Songs | 一条克制的固定高度签名带，不做大面积艺术卡片 |
| Upload | 空网格与 seed 入口，不显示角色 |
| Processing | 根据真实阶段组装图元，不伪造百分比 |
| Workbench | Pad Signature 与直接演奏轨迹 |
| Export | 缩成项目印章，Checklist 仍是主体 |

## 8. Performance Trace

### 8.1 输入

`PerformanceTrace` 只消费：

- 直接用户操作导致的 Pad Press；
- Pad index / role；
- BPM；
- 当前播放头；
- 项目 `VisualSignature`；
- `prefers-reduced-motion`。

鼠标、触控、键盘和 MIDI 进入同一 Pad Press 路径。Pattern 自动播放不生成演奏轨迹，避免把系统播放误报成用户动作。

### 8.2 生命周期

- 新 Pad Press 生成一条轨迹；
- 单条轨迹生命周期为 `60000 / bpm` 毫秒；
- 轨迹在生命周期内只降低透明度，不做弹跳或弹性回弹；
- 播放头进入新小节时清除上一小节残留轨迹；
- 同时存在的轨迹数量设上限，避免快速演奏造成 DOM 无界增长；
- 轨迹层使用 `pointer-events: none`，并裁切在 Instrument Canvas 内。

### 8.3 Reduced Motion

- 不绘制移动路径；
- 只对触发 Pad 做一次静态高对比状态变化；
- 不持续呼吸、漂浮、闪烁或跟随指针。

## 9. 流程页面

### 9.1 My Songs

- 保留“正在处理 / 最近歌曲”分组；
- 文件名、真实状态、时间和动作优先于签名；
- 视觉签名只能作为识别带；
- Delete / Remove / Continue 等动作使用直角、无阴影控件；
- 失败原因继续存在于可展开的真实详情中。

### 9.2 Upload

- 使用严格网格和大面积留白；
- WAV / MP3、200 MiB、600 秒限制保持显性；
- 高级 Patch 导入继续后置在 `details`；
- 不增加 Generate、Line-in、角色或假入口。

### 9.3 Processing

- 只显示 API / Job 的真实阶段；
- `queued` 显示真实 queue position；
- 没有真实百分比时不显示百分比；
- 未知阶段保留原始状态名；
- 用户可以返回 My Songs，处理继续在后台进行；
- 生成图形变化不能替代文件名、阶段文字或失败恢复。

### 9.4 Workbench

- Pattern 在上，16-pad 在下；
- 桌面 8×2，窄屏 4×4；
- Pad 是唯一高密度高饱和主区域；
- Inspector 和 Status Bar 保持上下文与真实性；
- Performance Trace 位于 Canvas 内，不能进入 Inspector 或状态区域。

### 9.5 Export

- Checklist、Ready / Review / Partial 和 blocker 是主体；
- Visual Signature 仅作为项目印章；
- 不用图形完成态掩盖缺失文件或服务器错误；
- 不改变现有 Export API 语义。

## 10. 平面交互语言

| 状态 | 表现 |
|---|---|
| Idle | 米白 / 角色色、固定结构边框 |
| Hover | 黑白反色，80–100ms |
| Pressed | 边框向内加粗；最多 1px 位移；无阴影、无缩放回弹 |
| Selected | 固定内框或侧边识别条 |
| Focus | 现有结构边框加独立 `outline` 构成双层轮廓，不使用阴影 |
| Muted | 降彩度、删除线、`MUTED` 文字 |
| Missing / Error | 红色结构线、图标、文字和恢复动作 |
| Empty | 米白底、Slot 编号、`EMPTY`，不可伪装为可播放 |

颜色与透明度过渡保持 80–160ms。除一拍轨迹外，本轮不增加持续环境动画。
交互控件使用 `box-sizing: border-box`；Pressed 边框必须向内增长，不得改变
Grid 尺寸、相邻 gap 或页面布局。

## 11. 响应式

沿用现有容器断点：

| 宽度 | 布局 | Pad |
|---|---|---|
| ≥1280px | Tool Rail + Canvas + 常驻 Inspector | 8×2 |
| 960–1279px | 紧凑 Tool Rail + Canvas；Inspector 覆盖 | 8×2 |
| 600–959px | Tool Rail 移到底部；Inspector 覆盖 | 4×4 |
| 360–599px | 紧凑 App Bar；全高 Inspector Sheet | 4×4 |

硬规则：

- Pad 顺序不变；
- Pad 保持正方形；
- 4×4 行列使用同一个 gap token；
- 生成层裁切在 Canvas 内；
- 低高度窗口允许可预期滚动；
- 不发生横向页面溢出；
- Inspector 打开时维持现有 Focus Trap、`inert` 和 Escape 恢复。

## 12. 状态、错误与恢复

- 错误不能只靠红色；
- Missing Pad 使用结构线、图标和文字；
- Processing Error 必须保留真实原因与恢复动作；
- Export Error 不得显示完成印章；
- 未知 Job 状态原样显示；
- 生成视觉失败时，DOM Creator Core 仍完整工作；
- Performance Trace 失败不得影响 Pad 触发或 AudioEngine；
- 本轮不建立视觉层错误上报 API。

## 13. 可访问性

- 所有核心操作继续使用真实 DOM button；
- 颜色不是唯一状态载体；
- Focus 使用 `outline`，不因零阴影规则消失；
- `prefers-reduced-motion` 禁用轨迹运动；
- 生成图形使用 `aria-hidden="true"`；
- 状态文本与错误使用现有语义和 live region；
- 不朗读每一帧播放头或轨迹变化；
- Touch target 和键盘 / MIDI 路径保持现有验收。

## 14. 性能

- 不新增 Three.js、p5.js、Canvas Runtime 或其他运行时依赖；
- 优先使用 CSS / SVG 与纯 TypeScript；
- 生成签名为确定性纯函数；
- 轨迹节点数量有上限并按生命周期释放；
- 不新增连续 `requestAnimationFrame` 循环；
- 不读取音频 PCM 或创建新的 AudioContext；
- 后台页面不运行持续视觉动画；
- 视觉失败不阻塞上传、播放、MIDI 或 Export。

## 15. 建议组件边界

### 15.1 新增

- `apps/web/src/ui/generative/visualSignature.ts`
- `apps/web/src/ui/generative/visualSignature.test.ts`
- `apps/web/src/ui/generative/ProjectSignature.tsx`
- `apps/web/src/ui/generative/ProjectSignature.test.tsx`
- `apps/web/src/ui/generative/PerformanceTraceLayer.tsx`
- `apps/web/src/ui/generative/PerformanceTraceLayer.test.tsx`

### 15.2 修改

- `PadButton.tsx`
  - 抽取现有哈希 / 几何语法；
  - 保留交互语义；
  - 改为直角、无阴影平面反馈。
- `PadMatrix16.tsx`
  - 保持现有 Press / Release 入口；
  - 向 Trace 层提供直接 Pad Press 事实。
- `App.tsx`
  - 保留 `submissionId` 到 Loaded 状态；
  - 向流程页面提供同一 Visual Signature seed。
- `MySongsView.tsx`
  - 增加克制的 Project Signature 带。
- `ProcessingPanel.tsx`
  - 增加真实阶段驱动的签名组装视图。
- `PatternSurface.tsx`
  - 提供 BPM / playhead 语境，不拥有 Trace 状态。
- `ExportChecklist.tsx`
  - 增加项目印章，不改变 Checklist 逻辑。
- `theme.css`
  - 统一零圆角、零阴影与平面状态。

组件名称与文件拆分可在 Implementation Plan 中按现有测试边界微调，但数据边界和职责不得改变。

## 16. TDD 与验证

实施使用 Red → Green → Refactor。

### 16.1 单元测试

- 相同 seed 得到相同 Visual Signature；
- 不同 seed 得到可观察差异；
- Pad Signature 迁移后保持当前确定性；
- Project seed 只使用公开身份；
- 一拍时长正确；
- 小节边界清理正确；
- Reduced Motion 不生成移动轨迹。

### 16.2 组件测试

- Pad Press 后出现 Trace；
- 一拍后 Trace 消失；
- Trace 不接收 Pointer Event；
- My Songs / Processing / Export 使用同一项目 seed；
- 未知 Job 状态原样显示；
- Missing、Error 和 blocker 不被图形替代；
- 鼠标、键盘和 MIDI 行为不变。

### 16.3 浏览器测试

沿用现有视口：

- 1920×1080；
- 1440×900；
- 1280×720；
- 1024×768；
- 768×1024；
- 390×844；
- 360×640。

新增断言：

- 关键 UI `border-radius === 0px`；
- 关键 UI `box-shadow === none`；
- 4×4 `row-gap === column-gap`；
- Trace 不超出 Instrument Canvas；
- Trace 不遮挡 Pad、Inspector、Error 或 Export；
- Reduced Motion 下没有移动轨迹；
- 页面无横向溢出；
- Inspector Focus Trap 和 `inert` 行为不变。

### 16.4 完整验证

```bash
cd apps/web
npm test
npm run check-contract
npm run build
npm run test:e2e -- workbench-responsive.spec.ts
```

如果新建独立 E2E 文件，Implementation Plan 必须把它加入最终 Playwright 命令。

## 17. 验收标准

### 17.1 视觉

- 所有 UI 表面为直角；
- 所有 UI 表面无阴影；
- 基础界面以米白、黑线和网格为主；
- 高饱和色集中在角色、状态与生成图形；
- Kawaii 角色与表情不进入本轮；
- 不复制 KUMALEON 品牌资产。

### 17.2 交互

- 用户可以通过稳定位置、反色、边框和一拍轨迹形成动作记忆；
- Trace 只表示直接用户演奏；
- Trace 生命周期为一拍，并在小节边界清理；
- Reduced Motion 路径完整；
- 视觉层不改变 AudioEngine 行为。

### 17.3 状态真实性

- 只使用公开产品状态；
- 不读取内部 Material / Separation / Worker 文件；
- 不伪造处理进度；
- Error、Needs Review、Partial 和 blocker 始终显性；
- Creator Core 在生成视觉失败时仍可用。

### 17.4 工程

- 不修改 `lmdj.patch.v1`；
- 不新增运行时依赖；
- 单元、组件、契约、构建和响应式回归通过；
- 实现提交只包含本设计范围内文件。

## 18. 明确非目标

- Chameleon 2D / 3D；
- Kawaii 角色状态与宠物交互；
- Three.js、React Three Fiber、GLB 或 WebGL；
- p5.js 持续生成画布；
- 皮肤、账户权益、钱包或 NFT；
- Generate、Line-in、Sampler Edit、Take Recording；
- 新的音频分析或 Worker 阶段；
- API、Patchify 或 Schema 修改；
- 将视觉签名写入 Creator Export 合同。

## 19. 决策记录

本轮用户已确认：

1. 主流程与演奏都纳入视觉统一，但演奏工作台优先；
2. 生成艺术采用直接演奏轨迹；
3. 轨迹保留一拍，并在小节边界清理；
4. 选用 Living Instrument，而不是保守换肤或 Generative Gallery；
5. Kumaleon 研究是正式视觉参考；
6. 所有 UI 使用直角；
7. 所有 UI 去除阴影；
8. 当前阶段保持极度克制和理性；
9. 高度 Kawaii 的角色层集中后置；
10. 本轮不实现 Chameleon、3D、皮肤或 Web3。

## 20. 本分支实现验证

实现范围：

- 共享确定性 Visual Signature；
- My Songs / Processing / Workbench / Export 的同 seed 视觉连续性；
- 直接 Pad Press 的一拍 Performance Trace；
- 全部 UI 直角、零阴影和平面反馈；
- Reduced Motion、响应式、状态真实性与契约纯度回归。

验证命令：

```bash
cd apps/web
npm test
npm run check-contract
npm run build
npm run test:e2e -- workbench-responsive.spec.ts
```

该状态只表示本实现分支通过本地自动化验证，不表示已推送、已创建 PR、已合并
或已部署。
