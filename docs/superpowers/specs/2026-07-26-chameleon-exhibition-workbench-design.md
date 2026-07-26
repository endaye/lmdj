# LMDJ Chameleon 展览式工作台设计

- 日期：2026-07-26
- 状态：用户已逐节确认；尚未实施
- 目标落点：`apps/web/`
- 视觉方向：Kumaleon 启发的 Exhibition Workbench
- 角色资产：当前 2D 线稿，未来 SVG 与可选 3D

## 1. 设计输入与权威边界

本设计综合以下已经存在的输入：

- [LMDJ 产品版本运行时可见性设计](./2026-07-26-product-version-runtime-visibility-design.md)；
- [Kumaleon 视觉技术研究](../../research/2026-07-26-kumaleon-visual-technology-study.md)；
- [LMDJ Stage 1 Creator Workspace UI 设计](./2026-07-24-stage1-creator-workspace-ui-design.md)；
- [Chameleon 可换皮肤贴图规范 v1](../../prd/assets/chameleon/chameleon-skin-system-v1.md)；
- [Chameleon 3D 造型三视图 v1](../../prd/assets/chameleon/chameleon-3d-turnaround-v1.md)；
- 已批准的
  [Chameleon 线稿 PNG](../../prd/assets/chameleon/chameleon-line-logo-approved-v1.png)。

Stage 1 Creator Workspace UI 继续负责 Pattern、16 Pad、Inspector、Export
和响应式工作台的信息架构。本设计不重写 Creator Core，而是进一步定义：

1. 首页与工作台之间的角色连续性；
2. Chameleon 的位置、交互、状态和渲染器边界；
3. Kumaleon 视觉语言在首页和工作台中的不同使用强度；
4. 产品版本展签与角色 UI 的关系；
5. 当前 2D 到未来 SVG、3D 的无破坏替换方式。

## 2. 已落地、已有资产与尚未实施

### 2.1 已落地

- Web 已具有 Source、Processing、Loaded 和 Failed 等真实产品状态；
- API / Audio Worker 已公开
  `queued / separating / extracting / patchifying / completed / failed /
  cancelled / interrupted` 等 Job 状态；
- Creator Workbench 已具有固定 16 Pad、Pattern、播放、MIDI 和 Export；
- 页面右下角已显示产品 SemVer 或 `dev`，浏览器 Console 和 API `/health`
  提供工程构建身份；
- 已批准 Chameleon 线稿、廓形标志、基础 3D 造型方向和单网格多皮肤资产边界。

### 2.2 已有资产但不能误报为运行时

- `chameleon-line-logo-approved-v1.png` 是当前可用的批准线稿；
- `chameleon-line-logo-master-v1.svg` 是仓库已有 SVG 资产，但不自动视为用户未来
  提供的最终 SVG；
- `chameleon-3d-turnaround-v1.png` 只是建模参考，不是同一网格的精确投影；
- 皮肤规范是 `approved-for-modeling`，不代表模型、Rig、动画、GLB 或 WebGL
  Runtime 已完成。

### 2.3 本设计批准、尚未实施

- 首页中央 Chameleon 上传入口；
- 首页到工作台 Assistant Dock 的角色位置转换；
- Visual State Adapter、Visual Signature 和 Chameleon Controller；
- 当前 PNG 的 2D 无框悬浮状态；
- 工作台右上角 Assistant Dock；
- `ready` 和 `error` 的单次自动展开；
- 本文定义的展览式页面表面、生成纹理和动效规则；
- SVG 局部动画与 3D Renderer。

## 3. 核心设计结论

LMDJ 采用 **Exhibition Workbench（展览式工作台）**：

- 首页是 Gallery Stage，负责建立品牌世界和上传入口；
- 工作台是 Creator Instrument，负责稳定、清晰地完成音乐创作；
- Chameleon 是连接两个空间的同一角色，也是 AI 处理状态的可视化界面；
- 产品版本是低调的展签，不与角色争夺视觉注意力；
- 纸张负责空间，黑线负责秩序，颜色负责音乐，Chameleon 负责状态。

不采用：

- 在首页和工作台都铺满高强度随机海报元素；
- 只靠角色外观替代可读 Job、错误或导出信息；
- 在正式模型完成前生成或实现一个临时伪 3D Chameleon；
- 为了模仿 Kumaleon 提前加入 Wallet、NFT 或 Web3；
- 让 Web 读取 `materials.json`、stems、`lanes.json`、`chart.mid` 或 Worker
  私有文件。

## 4. 页面结构

### 4.1 首页：Gallery Stage

首页使用暖纸色全屏画布和黑色展览网格：

- 顶部保留 LMDJ Wordmark 和必要的轻量辅助信息；
- 巨型标题或短文案作为空间结构，不覆盖主要交互；
- 已批准的 Chameleon 线稿位于页面中央；
- 角色与其附近的上传文案共同构成一个语义明确的上传按钮；
- 点击、Enter 或 Space 打开文件选择；
- 拖入音乐时整个角色区域成为可见的拖放目标；
- 受控生成纹理只位于角色后方和页面边缘；
- 上传限制、文件名和错误仍以可读文字呈现。

桌面端角色视觉宽度为 `360–480px`。当前 PNG 只使用整体位移、轻微倾斜、
缩放和透明度变化，不伪造眼球、尾巴或身体局部动画。

### 4.2 首页到工作台

上传被接受后，角色沿明确路径缩小并进入右上角 Assistant Dock，不突然消失。
Reduced Motion 模式下用无路径的交叉淡化和位置切换替代该动画。

### 4.3 工作台：Creator Instrument

工作台继续以 Pattern、16 Pad、Inspector 和 Export 为核心：

- Chameleon 默认收进顶栏右上角的 Assistant Dock；
- Dock 是正式布局槽位，不以固定浮层压住工作区；
- 产品版本继续位于右下角；
- Dock 激活后，角色向左下方展开；
- 当前 2D 展开尺寸为 `140–180px`；
- 未来 3D 展开尺寸为 `240–300px`；
- 展开状态无装饰性卡片外框，但必须带短状态文字和明确关闭控制；
- 点击工作区、主动关闭或进入密集编辑时可以收回 Dock；
- Pattern、Pad、Inspector、Export 和错误操作不得被角色覆盖。

移动端不使用自由悬浮角色，而是在顶栏下方使用受约束的状态层。

## 5. 视觉语言

### 5.1 双表面系统

现有主题色继续作为权威色板：

| Token | 色值 | 用途 |
| --- | --- | --- |
| Paper | `#F6F2E8` | 首页、页面背景、说明和主要内容画布 |
| Ink | `#11110F` | 文字、边框、网格和 Chameleon 线稿 |
| Graphite | 现有 `--panel / --well / --raised` | 真正的硬件凹槽和监测区域 |

Graphite 不再默认覆盖整个页面；它只用于需要表达乐器硬件层次的区域。

### 5.2 音乐语义颜色

沿用现有 Drums、Bass、Harmony、Lead、Loop 和 Action 色。颜色主要用于：

- Pad 角色；
- 播放状态；
- Chameleon 背后的生成纹理；
- 有限的状态强调。

错误和警告继续使用独立语义色，并同时提供图标和文字。

### 5.3 字体

- `Chakra Petch`：品牌标题、Pad 名称和短标题；
- `IBM Plex Mono`：状态、BPM、版本、文件名和展签；
- `IBM Plex Sans`：说明、错误解释和较长正文。

巨型排版属于首页。进入工作台后，标题恢复为紧凑的工具尺度。

### 5.4 形状与网格

- 工具界面使用直角、`2px` 黑边和硬质偏移阴影；
- 圆角主要保留给 Assistant Dock，以区分“角色”和“工具”；
- 首页使用 12 栏展览网格；
- 工作台继续服从 4×4 Pad 和现有内容层级；
- 生成纹理来自确定规则，同一输入与状态不能在每次 React 渲染时跳变；
- 正文、错误和关键控制下方不得铺设高对比纹理。

### 5.5 运动

- 普通 UI 反馈：`120–240ms`；
- 2D 角色环境动作：`4–6s` 的低幅呼吸、倾斜或视差；
- 上传、完成和错误才允许更明显的状态动作；
- Reduced Motion 下关闭呼吸、视差、脉冲和路径动画。

## 6. Chameleon 状态协议

### 6.1 统一状态

| Visual State | 真实来源 | 2D 表现 | 自动展开 |
| --- | --- | --- | --- |
| `idle` | 首页无任务 | 低幅呼吸，黑色线稿 | 否 |
| `drag-ready` | 文件进入拖放区域 | 向指针轻倾，背景网格收拢 | 已在首页 |
| `uploading` | 浏览器上传请求进行中 | 环绕扫描线和文件名 | 已在首页 |
| `queued` | API `queued` | Dock 内显示真实队列位置 | 否 |
| `separating` | API `separating` | 背景纹理分为音轨色带 | 否 |
| `extracting` | API `extracting` | 色带变为颗粒和切片 | 否 |
| `patchifying` | API `patchifying` | 颗粒排列为 4×4 网格 | 否 |
| `ready` | `completed` 且 Patch 加载成功 | 确认脉冲和 `PATCH READY` | 是 |
| `playing` | 真实 Pad / Transport 播放 | 按实际音乐角色改变节奏和背景色 | 否 |
| `error` | 上传、解码、API 或终止错误 | 一次克制后退动作和明确错误文字 | 是 |

`generating` 和 `rendering` 等未来公开状态可以加入映射，但没有真实来源时不得显示
伪阶段或虚构百分比。

### 6.2 优先级

状态冲突时使用：

```text
error → ready event → playing → processing → interaction → idle
```

错误覆盖装饰动作；完成事件结束后，真实播放可以接管角色表现。

### 6.3 展开生命周期

- `ready` 每个 Job 自动展开一次，约 4 秒后收起；
- `error` 每个错误事件自动展开一次，并保持到用户关闭或查看详情；
- 用户手动召唤时不自动关闭；
- 相同 Job 的后续轮询不得重复播放自动展开；
- 切换到另一个 Job 后建立新的事件边界。

## 7. 数据与组件边界

```text
AppState / JobStatus ─┐
Drag / Upload ────────┼─→ Visual State Adapter ─→ Chameleon Controller
AudioEngine playback ─┘                               │
                                                     ├─→ 2D Renderer
patch_id / public Patch ─→ Visual Signature ─────────┤
                                                     ├─→ optional 3D Renderer
                                                     └─→ accessible status text
```

### 7.1 Visual State Adapter

Adapter 是纯函数，输出渲染器无关的状态：

```ts
type ChameleonVisualState = {
  phase:
    | "idle"
    | "drag-ready"
    | "uploading"
    | "queued"
    | "separating"
    | "extracting"
    | "patchifying"
    | "ready"
    | "playing"
    | "error";
  placement: "stage" | "dock" | "floating";
  label: string;
  tone: "neutral" | "active" | "success" | "danger";
  motion: "still" | "ambient" | "processing" | "celebrate" | "recoil";
};
```

Renderer 不读取 Job、上传或 AudioEngine，也不自行猜测进度。

### 7.2 Chameleon Controller

Controller 只负责：

- 展开、收起和手动召唤；
- `ready / error` 的单次自动展开；
- 用户关闭后的重复事件抑制；
- Reduced Motion；
- 将点击转换为 `choose-file / toggle-assistant / dismiss / view-details`
  等意图。

Controller 不直接上传、重试、播放或解析 Patch。

### 7.3 Visual Signature

- 首页空状态使用固定品牌种子；
- 上传阶段只使用公开文件类型和当前阶段；
- Patch 完成后使用公开 `patch_id` 和 Patch 中已有 Pad 角色；
- 同一 Patch 和状态产生稳定纹理；
- 不读取内部 Material、stem、lane 或 MIDI 文件。

### 7.4 建议代码边界

```text
apps/web/src/chameleon/
  model.ts
  adapter.ts
  controller.ts
  ChameleonSurface.tsx
  visualSignature.ts
  renderers/
    Chameleon2D.tsx
    Chameleon3D.tsx    # 未来
```

产品版本展签继续属于 `AppFrame`，不进入 Chameleon 状态系统。

## 8. 2D、SVG 与 3D 替换规则

### 8.1 当前 PNG

- 品牌源文件保留在 `docs/prd/assets/chameleon/`；
- Product Web 使用不改变视觉内容的优化派生图；
- 原批准 PNG 当前约 `934KB`，运行时派生图目标约 `200KB`；
- 首页和工作台复用同一资源；
- 图片加载失败时保留上传文字、轮廓占位和全部核心操作。

### 8.2 未来 SVG

- 用户提供的正式 SVG 替换 PNG，不改变布局、事件或状态接口；
- 只有 SVG 明确提供稳定的眼睛、尾巴、身体等可寻址图层时，才增加局部动画；
- 不根据路径顺序猜测部件；
- 无稳定图层时继续把 SVG 当作整体图像处理。

### 8.3 未来 3D

- `Chameleon3D` 是独立懒加载模块；
- 3D 加载前始终先显示 2D；
- WebGL 失败、低性能设备或无动作偏好时可回退 2D；
- 3D 状态只读取统一 Visual State，不读取业务内部数据；
- 皮肤与状态分离：皮肤定义常态外观，状态只叠加动作、灯光和有限材质参数；
- 3D 角色收进 Dock 或页面进入后台时停止连续渲染。

首个原型以 `GLB ≤ 500KB` 为目标，但这是需要实测验证的原型预算，不修改
Chameleon 皮肤规范中“最终预算待 Runtime 选型后验证”的边界。

## 9. 响应式规则

| 宽度 | 首页角色 | Dock | 展开角色 |
| --- | --- | --- | --- |
| `≥1200px` | `360–480px` | `48px` | 2D `140–180px`；3D `240–300px` |
| `768–1199px` | `280–360px` | `48px` | 2D 适配；3D `200–240px` |
| `<768px` | `200–280px` | `44px` | 顶栏下方受约束状态层 |

390px、768px 和 1440px 是首轮视觉验收宽度。所有安全区和软键盘场景下，
角色都不得遮挡主要控制。

## 10. 可访问性与失败回退

- 首页角色使用真实 Button / File Input 语义；
- 点击、Enter、Space 和拖放都能启动上传；
- Dock 提供当前状态的可访问名称；
- `ready` 使用普通 live region，`error` 使用 alert；
- 颜色之外始终存在文字或图形区别；
- 角色不能替代现有队列、错误、Patch 和 Export 文本；
- 2D、SVG 或 3D 任一资产失败都不能阻断 Creator Core；
- Reduced Motion 下保留状态变化和文字，不保留装饰运动。

## 11. 产品版本展签

页面右下角继续只显示产品 SemVer 或 `dev`：

```text
LMDJ · v0.2.0
LMDJ · dev
```

版本使用 9–10px 单色等宽字体，不发光、不参与角色状态。Git SHA 继续只进入
浏览器 Console 和 API `/health`。

## 12. 验收标准

1. 首页线稿角色可通过点击、键盘和拖放启动上传；
2. 角色状态只来自真实上传、Job、Patch 和播放状态；
3. `ready / error` 对每个事件只自动展开一次；
4. 工作台角色不覆盖 Pattern、Pad、Inspector、Export 或错误操作；
5. 同一 Patch 和状态的生成纹理保持稳定；
6. Reduced Motion 下没有呼吸、视差、脉冲或路径移动；
7. 390px、768px 和 1440px 三个宽度不存在关键遮挡；
8. PNG、SVG 或 3D 加载失败时，核心工作流仍完整可用；
9. Web 不读取内部 Material、stem、lane 或 MIDI 文件；
10. UI 只显示产品 SemVer，SHA 只进入 Console 和 `/health`；
11. 自动化测试覆盖状态映射、单次展开、键盘上传、回退与可访问名称；
12. 初始 2D 版本不引入 Three.js、React Three Fiber 或 GLB 依赖。

## 13. 后续实施边界

后续实施计划应按以下阶段拆分，但本设计批准不代表这些阶段已经完成：

1. 2D Gallery Stage、Assistant Dock、状态 Adapter 和回退；
2. 用户提供的正式 SVG 原位替换；
3. 独立评审并接入 3D 模型、Rig、动画和 Runtime；
4. 在真实设备上验证模型、纹理、GPU、帧率和内存预算。

开始实现前需基于本文另写实施计划。任何 3D Runtime 选型、模型资产制作和皮肤
发布流程都需要单独评审，不能从本文推导为已批准的库或资产交付。
