# LMDJ 硬件导向 UI：布局、控件与上下文工作区参考

日期：2026-09-11

状态：设计参考（designed），未在本文中实施 Creator UI 或真实硬件。

跟踪：[UI 迭代 Umbrella #1207](https://github.com/endaye/lmdj/issues/1207)。
关联：[Creator 视觉语言 #522](https://github.com/endaye/lmdj/issues/522)。

## 1. 定位与开放边界

本说明保留本轮 Figma 迭代的布局、双语命名、各区职责与交互方向，供后续设计和有明确范围的实现任务引用。目标是让 LMDJ 像一台可演奏的乐器，而非普通网页仪表盘。它不是当前 Creator 的实现说明，也不覆盖现有产品决策、Application Facade 或 Contract。

**稳定的是四区的空间身份与输入能力；开放的是两个屏幕显示什么、何时切换，以及具体操作语义。**

- 左侧是实体控制；下方左侧是 16 个实体 Pad。
- 上部屏幕只显示，不能点击、滑动、拖动波形或调整参数。
- 下方右侧是触摸控制屏，可按上下文生成不同控件。
- Project、Sample、Sequence、Perform 不是四套固定屏幕内容模板。两个屏幕的内容可以根据当前模式、选中对象、用户操作及编辑阶段切换。
- 本轮四页、数值、工程名、波形、段落和滤波响应都是示例；没有连接可拖动原型，也没有对应的软件／DSP 实现与真机验收证据。

本文不宣称 #522 的阶段验收已经完成；对现有 Host 的最终映射、产品规则变更与实现拆分，仍需在后续 Issue 中明确。仅合并本文不足以完成任一设计 Umbrella。

## 2. Figma 入口与迭代索引

[Figma 总文件](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO)。链接保留原文件访问权限；仓库文档不授予 Figma 权限。节点编号是画板标识，不是 Product Build 或软件版本。Figma 内容可继续修改，以下是本文记录时的设计基线，不是不可变发布快照。

| 画板 | 用途 | 链接 |
| --- | --- | --- |
| 15 / Hardware Sequence | 四区布局、实体控件、Pad 和上屏基线 | [编序基线](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=69-666) |
| 15d / Naming Reference | 中英文名称对照表 | [名称对照](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=82-676) |
| 16 / Project | 较早的工程页方案 | [工程基线](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=83-676) |
| 17 / Sample | 较早的采样页方案 | [采样基线](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=83-1539) |
| 18 / Perform | 较早的演奏页方案 | [演奏基线](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=83-2402) |
| 19 / Touch-first Sequence | 推子、Bars／Grid 分段选择 | [编序触摸新版](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=88-706) |
| 20 / Touch-first Project | 工程卡片和主次操作 | [工程触摸新版](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=88-1569) |
| 21 / Touch-first Sample | 触摸波形、裁切、试听与分配 | [采样触摸新版](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=88-1892) |
| 22 / Touch-first Perform | 段落触发、纵向推子、滤波曲线 | [演奏触摸新版](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=88-2389) |
| 22b / Filter Response States | 低通、高通、带通状态对照 | [滤波曲线](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=95-746) |

后续讨论优先使用 15 的布局和 19–22 的触摸方向；16–18 保留为比较稿，不混称为已经上线的页面。

## 3. 四区结构与尺寸

所有尺寸均为 Figma 设计单位，**不是毫米、屏幕采购规格或真实面板分辨率**。

```text
880 × 592
┌───────────┬───────────────────────────────────┐
│ 实体控制区 │ 上部显示屏：752 × 176，只读          │
│ 80 × 560  ├─────────────────┬─────────────────┤
│ Logo      │ 打击垫区         │ 触摸控制屏       │
│ 四旋钮    │ 368 × 368       │ 368 × 368       │
│ 双列按键  │ 4 × 4 Pads      │ 随上下文变化     │
└───────────┴─────────────────┴─────────────────┘
```

图示不是比例图。整机外边距及四区间距统一为 16。

| 区域／容器 | 英文 | 尺寸 | 相对整机左上角位置 | 输入能力 |
| --- | --- | --- | --- | --- |
| 硬件控制台 | Hardware Console | 880 × 592 | 0, 0 | 整体容器 |
| 实体控制区 | Physical Control Panel | 80 × 560 | 16, 16 | 实体按键与旋钮 |
| 上部显示屏 | Overview Display | 752 × 176 | 112, 16 | 只读 |
| 打击垫区 | Pad Matrix | 368 × 368 | 112, 208 | 实体打击垫 |
| 触摸控制屏 | Touch Control Screen | 368 × 368 | 496, 208 | 触摸 |

在 Sequence 页，上部显示屏具体称为 **Sequence Display / 编序显示屏**；跨页讨论使用 Overview Display，避免误认为它只能显示编序。

网格关系：

- 实体小按钮 32 × 32，双列宽度 `32 + 16 + 32 = 80`。
- 每个 Pad 80 × 80，相当于 2 × 2 个小按钮及中间间距。
- Pad 区 `4 × 80 + 3 × 16 = 368`。
- 上屏高度 `2 × 80 + 16 = 176`，等于两行 Pad 的高度。
- 右侧宽度 `368 + 16 + 368 = 752`；右侧高度 `176 + 16 + 368 = 560`。
- 整机宽度 `16 + 80 + 16 + 752 + 16 = 880`；高度 `16 + 560 + 16 = 592`。
- 上屏内边距 16，内容区 720 × 144；触摸屏内边距 16，内容区 336 × 336。
- 触摸区不受实体按钮正方形限制，当前示例使用 8／12 的内部间距、40／44 高的操作按钮和 56 高的段落块。最终手指命中区需要按实际屏幕尺寸验证，不能凭设计单位宣称达标。

## 4. 实体控制区

Logo 使用透明背景的 LMDJ 矢量标识，在 80 × 80 区域贴合主体。它保留设置入口的设计意图；真实硬件如何触发该入口（独立实体件、组合键等）尚未定义，不假定印刷 Logo 可以点击。

Logo 下是 2 × 2 的旋钮示意，单个占位 32 × 32，间距 16。Encoder 1–4 / K1–K4 的固定／上下文映射、旋转精度、是否可按压、触摸感应、复位手势仍开放。圆形旋钮不适用“实体按键必须正方形”的约束。

实体按键自上而下排列，整体与 Pad 区对齐：

| 行 | 左键 | 右键 | 组名／职责 |
| --- | --- | --- | --- |
| 1 | Project / 工程 | Sample / 采样 | Page Navigation Keys / 页面导航键 |
| 2 | Sequence / 编序 | Perform / 演奏 | Page Navigation Keys / 页面导航键 |
| 3 | A | B | Pad Bank Keys / 打击垫组选择键 |
| 4 | C | D | Pad Bank Keys / 打击垫组选择键 |
| 5 | − / 减少 | + / 增加 | Value Adjustment Keys / 数值调整键 |
| 6 | ↑ / 上 | ↓ / 下 | Directional Navigation Keys / 方向导航键 |
| 7 | ← / 左 | → / 右 | Directional Navigation Keys / 方向导航键 |
| 8 | Record / 录音 | Play / 播放 | Transport Keys / 录放控制键 |

八行按键高 `8 × 32 + 7 × 16 = 368`，每两行对齐一行 Pad。模式切换不移动实体控件或改变 Pad 的空间身份。数值键作用于什么参数、方向键移动哪个焦点、录放键在不同上下文的行为，不在本说明中定死。

## 5. 上部显示屏：总览与反馈，不承载操作

Sequence 当前信息从上到下排列：

1. Information Header / 信息区。
   - Primary Status Row / 主状态行：模式／对象、BPM、播放状态、位置。
   - Sequence Context Row / 编序上下文行：Bar 范围、Step 数、网格、轨道范围、Bank、Pad。
2. Track Sequence Overview / 轨道编序总览。
   - Track Label Column / 轨道标识列。
   - Step Event Grid / 步进事件网格。
   - Track Lane / 轨道行；Step Cell / 步进单元。

当前编序总览示意为 8 轨、4 Bar、64 Step，较小文字与窄色块提高密度；这是示例容量，不是产品轨道数量或时间分辨率上限。信息集中在顶部，编序网格位于下方。当前纵轴是音色／轨道，不是音高，因此正式名称不是 Piano Roll；未来音高编辑可单独使用 Piano Roll / 钢琴卷帘。

上屏允许显示选区、选中项、曲线、进度、电平、待切换段落等反馈，但不应把它们画成必须触摸才能操作的按钮或手柄。用户操作发生在实体控件、Pad 或触摸屏；上屏反映结果。具体反馈字段和提示优先级仍待后续设计。

## 6. 打击垫区：空间稳定与视觉主体对齐

每行称 Pad Row / 打击垫行；每个 Pad 是一个槽位，不等同于某个 Asset。Bank A 的示例编号为 A01–A16，其他 Bank 的槽位语义仍遵循现有产品边界，本文不改变它。

| Pad 元素 | 英文名称 | 用途 |
| --- | --- | --- |
| 槽位编号 | Slot Label | 左上角 A01 等空间身份 |
| 快捷键提示 | Shortcut Hint | 右上角 Q、W 等软件键盘提示；非硬件刻字定稿 |
| 音色类别图标 | Sound Category Icon | 鼓、Bass、Melodic、Vocal、Texture 等角色 |
| 音色类别标签 | Sound Category Label | 下方文字，辅助非颜色识别 |
| 状态指示 | State Indicator | 选中边框、圆点、空槽等状态反馈 |

图标不能只按 SVG／图片边界框居中。主体锚点对齐 Pad 中心 `(40, 40)`：鼓按鼓心圆圈；Melodic 按中间琴键主体；Bass／Wave 按波形中轴；Vocal 按内部声波中心；Texture 按中央椭圆中心。装饰音符、鼓槌等允许产生不对称外边界。

当前画板展示 12 个已分配 Pad 和 4 个空 Pad，只是一个示例工程。角色色不是播放／错误状态的替代物；空、禁用、录制、播放、静音、错误、选中等完整状态和非颜色提示需要继续补齐。Pad 的演奏触发与进入编辑／选择的关系也须单独确认，不能因为触摸屏示例选中了 A03，就推断每次敲击都必须切换编辑对象。

## 7. 触摸控制屏：可变内容，而非固定 Inspector

Touch Control Screen 是硬件区域名。Sequence Editor / 编序编辑器、Pad Inspector / 打击垫检查器等是它显示的一种上下文，不是整块区域的永久名称。

通用内容名称：Context Header / 上下文标题栏、Parameter Controls / 参数控制区、Action Controls / 操作区。具体页面可使用工程卡片、横向推子、纵向推子、分段单选、触摸波形、曲线等，不强制排成四个方形操作键。

### 7.1 当前四页示例

| 页面 | 上屏示例（只读） | 触摸屏示例（可操作的设计意图） |
| --- | --- | --- |
| Project / 工程 | 当前工程、内容数量、保存状态 | 整张卡片选择工程；Open、Save、New、Save As |
| Sample / 采样 | 全局波形、格式、时长、选区与目标 Pad | 局部波形起止手柄、数值精调、Audition、Trim、Browse、Assign |
| Sequence / 编序 | 当前对象、播放信息、轨道事件总览 | Tempo／Swing 横向推子、Bars／Grid 分段选择、New、Copy、Pad 编辑入口 |
| Perform / 演奏 | 当前／待切换段落、播放进度、输出电平 | 段落触发块、Master／Filter／Delay 纵向推子、选中 Pad 的 Mute／Solo、详细效果入口 |

这些是当前认可的视觉方向，不是已固定的操作清单：

- Project：提案将选择与打开分开，避免单次误触替换当前工程；未保存内容的确认路径待定义。
- Sample：提案让上屏显示全局、触摸屏负责局部裁切；命中区可以大于可见手柄。裁切提交、撤销、试听范围、分配确认及缩放规则尚未形成实现合同。
- Sequence：推子表达连续参数，分段选择表达离散值。Tempo／Swing 范围、精度、Grid 与 Quantize 的关系以及适用对象须明确后再实现。
- Perform：示例用实色加 PLAYING 表示当前段落，描边加 QUEUED 表示待切换段落；“下一小节切换”是提案，不覆盖既有 Perform 语义。Master 的作用域与 Filter／Delay 的目标、Mute／Solo 行为必须明确标注和验证。

### 7.2 滤波曲线

Perform 的 Filter 推子上方增加响应曲线，当前展示 LP；滑块形状一致，类型由文字和曲线表达。

| 类型 | 中文 | 曲线表达 | 参数示意 |
| --- | --- | --- | --- |
| LP / Low-pass | 低通 | 低频通过，高频衰减 | 截止频率 |
| HP / High-pass | 高通 | 低频衰减，高频通过 | 截止频率 |
| BP / Band-pass | 带通 | 中间频段通过，两侧衰减 | 中心频率 |

横轴从低频到高频，纵轴示意通过量。曲线不是实际 DSP 测量结果，也不定义阶数、斜率、Q／共振、频率标度、参数范围或音量补偿。类型选择拟位于详细效果工作区，实际入口和曲线联动仍待原型。当前静态图中的 2.4 kHz 不能当成经校准的频率坐标。

## 8. 视觉语言与状态

- 主体使用石墨灰，保留透明背景 LMDJ Logo 与既有角色图标。
- 实体按键沿用浅底深图标表示选中、深底浅图标表示未选中；Record 用和谐红色圆点，Play 用荧光色三角。
- 触摸新版用青柠（编序）、浅蓝（工程）、浅紫（采样）、暖橙（演奏）作为页面／操作强调色；主要操作的实色强调不等于一个开关已开启。
- 触摸区不强求方形按钮；推子滑块、选区手柄应显得可拖动，纯读数与上屏图形应显得不可操作。
- 选中、播放、排队、失败不能仅靠颜色区分；字体、对比度、触摸目标、焦点、键盘替代、减弱动态效果等需要后续可访问性验收。

参考资料：[Ableton Move 官方手册](https://www.ableton.com/en/move/manual/)用于理解实体控制与显示反馈的分工；[Akai MPC 官方手册](https://cdn.inmusicbrands.com/akai/mpc-touch/MpcTuiManual.pdf_b8811aa4b3238af92939b042c61e1f68.pdf)是触摸音乐设备的交互参考。它们不是 LMDJ 的功能或外观合同，本文不复制其产品能力。

## 9. 后续需明确的上下文与验收

下一步应把以下问题转为有边界的设计／实现子任务，而非由本文擅自填满：

| 开放项 | 后续需要回答的问题 |
| --- | --- |
| 双屏上下文 | 模式、对象、操作阶段变化时，哪个屏幕切换？哪些信息始终保留？ |
| 返回与编辑状态 | 返回时恢复哪个焦点、选区和参数？未提交内容如何处理？ |
| 实体映射 | 四旋钮、方向键、−／+ 作用于什么？是否和触摸控件一一对应？ |
| Pad 选择与演奏 | 触发声音和进入编辑如何区分？模式／Bank 切换是否影响选中对象？ |
| 参数及效果 | 值域、步长、单位、作用域、滤波类型与曲线如何映射？ |
| 失败与恢复 | 空工程、无采样、加载中、失败、禁用、未保存、撤销如何呈现？ |
| 设备适配 | 设计单位如何映射真实面板、毫米与触摸命中区？软件键鼠如何适配？ |
| 实现边界 | 当前 Host 可用能力有哪些？需要哪个产品决策、Facade 或实现子任务？ |

后续验收至少应观察：模式切换后 Pad 空间身份保持；所有屏幕操作均能在触摸区完成而不依赖上屏点击；操作后上屏反馈对象和值一致；选择／确认／取消／返回等路径完整且不丢失未提交状态；真实触摸设备可用。本文只记录这些验收方向，**不声称上述交互路径已经通过测试**。

## 10. 本次文档交付边界

本 Task 仅新增本文件并创建关联 Umbrella；不修改产品代码、Figma 画板、运行时、Provider、Project Truth、Contract 或版本清单。文档验证包括中英文命名与尺寸公式核对、Figma 节点链接核对、Git diff 检查、新增路径 ownership 检查与 PR 声明检查。自动审查及合并结果记录在 PR，不能由此推出 UI 已实现或可用性已验收。

### Version Management

Version impact: none

Reason: 仅保留未来 UI 设计参考，不分配 Product Build、Host、Module、Provider 或 Contract 版本，也不发起发布。

### Documentation Impact

Documentation impact: none

Reason: 本文件位于 `docs/design/`，是未实施的设计参考，不修改架构门户、已实现行为或版本投影。后续正式设计决策或实现任务须重新评估 `/hosts/creator-web/` 等门户页面；本文不是 #522 的最终 Phase 3 交付。
