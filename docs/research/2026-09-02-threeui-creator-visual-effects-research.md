# ThreeUI 与 Creator Three.js 视觉底层调研

> 研究日期：2026-09-02
>
> 研究对象：[ThreeUI](https://threeui.com/)、[ThreeUI Community](https://github.com/MengTo/threeui)
>
> 关联工作：[Creator 产品视觉语言 #522](https://github.com/endaye/lmdj/issues/522)、
> [Creator 产品视觉语言 Brief](./2026-09-01-creator-visual-language-brief.md)
>
> 研究性质：Phase 1 灵感与技术可行性输入。不是视觉方向选择、依赖批准、设计规格或产品实施授权。

## 0. 结论先行

ThreeUI 值得作为 LMDJ 未来 UI 工作的**效果词典、原型起点和实现反例库**长期保留。
它不是一套普通组件库，而是把 Three.js、raw WebGL、Canvas 2D、CSS 3D、DOM/CSS
和完整页面模板放进同一个可检索目录，并为大量条目提供实时预览、参数控制、变体和源码。

对 Creator 最有价值的不是直接复制某个完整页面，而是以下四类视觉原语：

1. Pad 的材质、边缘光、按下回弹和短生命周期反馈；
2. Bank / Mode 切换时不改变空间位置的结构性动效；
3. 位于 Pad 之后、低对比、可暂停的程序化场；
4. 可由真实音频或演奏状态驱动、但不承载业务语义的品牌或状态图形。

Three.js 也确实可能成为 Creator 的视觉底层，但要把“底层”说准确：

> **建议把 Three.js 定义为 Creator 可选 GPU 视觉层的标准渲染底座，而不是把整个
> Creator、16 个 Pad 或业务控件重写成一个 3D Canvas。**

Creator 仍以 React + 语义 HTML 作为布局、控件、焦点、输入和状态的权威层；Three.js
Canvas 只做渐进增强。Canvas 默认不接管 Pointer，不能成为 Pad 是否可触发的唯一表达，
也不能反向修改 Project Truth 或预测 Facade 成功。

这个边界符合当前产品现实：Creator 已有稳定的 Pointer / Keyboard / MIDI 路径、
AudioWorklet、SVG / Canvas 波形、严格 CSP、同源离线分发和 iPadOS Safari 验收要求。
视觉计算必须让位于音频实时性；WebGL 不可用、上下文丢失、降低动态效果或视觉层崩溃时，
乐器仍必须可以完整演奏。

本研究不选择 #522 Phase 2 的视觉方向，也不批准向 `apps/creator-web` 增加 `three`
依赖。建议在 Phase 3 方向批准后，另开一个有性能预算和降级验收的 Creator 视觉渲染
Spike，再决定是否进入生产依赖。

---

## 1. 研究范围与证据边界

### 1.1 本次检查

- ThreeUI 当前公开目录、分类、条目说明和安装入口；
- ThreeUI Community 官方仓库在提交
  [`68802d5`](https://github.com/MengTo/threeui/commit/68802d5428071ada5c20db8094b1649e6bb770ed)
  的源码、目录元数据、运行时依赖和授权文件；
- Community 条目的渲染循环、DPR、页面可见性、IntersectionObserver、资源释放、
  `prefers-reduced-motion` 和外部资产模式；
- 当前 `apps/creator-web` 的依赖、输入路径、音频生命周期、Canvas / SVG 使用、
  分发 CSP 和打包资产白名单；
- #522 已锁的产品边界：4×4 Pad 空间稳定、只有 Pad 区可高饱和、颜色绑定真实状态和
  稳定身份、三份 Phase 1 标本先于方向选择。

### 1.2 未完成的实证

本环境没有可用的 `agent-browser` 可执行文件，因此本次无法做自动化页面点击、逐条实时
预览录屏或 GPU 时间测量。本文对效果外观的判断来自官网公开预览和官方条目描述；对运行时
的判断来自 Community 源码。

以下事项仍属于后续原型验证：

- ThreeUI 条目在 LMDJ 的 macOS Safari、macOS Chrome、iPadOS Safari 上的帧时间、
  GPU 内存、功耗和长时间稳定性；
- 与当前 Web Audio / AudioWorklet 同时运行时是否出现听感或触发时序退化；
- WebGL Context Lost / Restored、后台恢复、锁屏恢复和低内存设备行为；
- Pro 条目源码、资产和商业使用的具体授权条件；
- 某个效果能否在 #522 的 1440×900 与 768–1024 宽标本上保持相同语义层级。

### 1.3 快照会变化

2026-09-02 官网公开页显示完整目录为 385 项；Community 仓库内的 2026-08-31 同步报告
记录 43 个 Community Parent、104 条 Community Route 和 163 个 Community Variant。
仓库的完整目录摘要仍记录 378。三者属于不同更新时间与可见边界，不应把数量写成长期产品
Contract。选型时应记录具体 URL、变体、源码提交和授权快照。

---

## 2. ThreeUI 是什么

ThreeUI 的公开分类包括 Landing Pages、Hero、Three.js、Motion Design、Sections、
Backgrounds、Buttons、Text Animation、UI Elements 和 CSS。目录混合多种实现方式：

| 实现方式 | 目录中的典型用途 | 对 LMDJ 的意义 |
| --- | --- | --- |
| Three.js | 粒子场、程序化地形、布料、3D 物件、ShaderMaterial | 适合统一管理需要 3D Scene / Camera / Geometry 的视觉层 |
| Raw WebGL / WebGL2 | 全屏 Shader、流体、折射、激光、后处理 | 体积可小，但资源和生命周期管理更底层，不能因“不是 Three.js”而默认更安全 |
| Canvas 2D | 粒子、文字、波纹、诊断图形、波形式反馈 | 对单个 Pad 或局部反馈可能比 Three.js 更便宜、更容易降级 |
| DOM / CSS / CSS 3D | 按钮、Toggle、Dock、仪表、纸张与卡片 | 最适合保留语义、焦点和自动化测试；很多“3D 感”并不需要 Three.js |
| Full HTML / iframe | 完整 Landing Page、Hero、作品集 | 适合观察构图，不适合直接嵌入 Creator 产品壳 |

Community 以 React 包 `@designcodeio/threeui` 发布，同时公开完整 Community 源码。
当前仓库声明 React 18–19 Peer、`three >=0.149 <1` Peer，并为历史条目同时保留
Three r128 与 r165 的别名依赖。目录元数据也能看到 r128、r134、r149、r160、r165
等多代 Three.js 实现并存。

因此，ThreeUI 更接近**经过展示包装的效果档案馆**，不是已经替 LMDJ 做好版本统一、
性能预算、无障碍和宿主生命周期的 Design System。条目应该逐个选择和适配，不应把完整
目录包当作 Creator 的默认基础设施。

---

## 3. 对 Creator 有价值的效果族

### 3.1 第一优先：Pad 触感与真实状态反馈

| ThreeUI 参考 | 可借鉴 | 必须改写 / 拒绝 |
| --- | --- | --- |
| [Rectangle Buttons](https://threeui.com/buttons/rectangle-buttons) | 边框、内凹、表面高光、按下形变和明确 Focus 的组合 | 不照搬 CTA 文案、胶囊轮廓或持续发光；16 个 Pad 不能各自启动独立重型 Renderer |
| [Liquid Metal Button](https://threeui.com/buttons/liquid-metal-button) | 指针落点产生短暂局部波纹，材质与边缘分层，键盘也有反馈 | 不能让金属反射掩盖 Empty / Error；不能仅靠 Shader 表达按下或播放 |
| [Skeuomorphic Toggle](https://threeui.com/ui-elements/skeuomorphic-toggle) | 同一控件可比较 CSS、Three.js 和 Shader 三种材质成本；保留真实 Toggle 语义 | Pad 不是 Toggle；不要把全局灯光跟随 Pointer 变成每个控件的常驻循环 |
| [Spark Badge](https://threeui.com/backgrounds/spark-badge) | Capturing / Commit 成功时的短生命周期粒子边缘 | 17 秒循环太长；Credential 造型不属于乐器；粒子不能替代文字或图标状态 |

最值得吸收的是“状态先有可读几何，效果再增强”的层次，而不是某种金属皮肤。Pad 的
Empty、Assigned、Capturing、Playing、Error、Disabled 必须先由 DOM、文字 / 图标、
边界和结构共同表达；GPU 层只增加触感、能量和身份。

### 3.2 第二优先：不移动空间身份的 Mode / Bank 动效

[Animated Top Dock](https://threeui.com/css/animated-top-dock) 同时展示 Pointer Proximity、
Keyboard Focus、Active Selection、Reduced Motion 和移动端静态模式，值得作为 Mode Rail
状态转换的交互清单。

但它的邻近放大和项目位移不能直接用于 Creator：#522 已锁“切换模式不移动 Pad 的空间
身份”，Mode Rail 也应尽量保持肌肉记忆。可以借用光、边、材质和进入 / 退出节奏，拒绝
会推动相邻项目的 Dock Magnification。

### 3.3 第三优先：低对比程序化场

以下条目适合研究“深色面板但不是通用 SaaS”的第三种画布材料：

- [Predictive Arc](https://threeui.com/backgrounds/predictive-arc)：同一族比较 Canvas 2D、
  raw WebGL 与 Three.js，适合做技术成本对照；
- [Structure Flow](https://threeui.com/three-js/structure-flow)：粒子穹顶、轨道、矩阵、
  拓扑和流体等 13 个场景，可观察几何密度与品牌辨识度；
- [Constellation Field](https://threeui.com/backgrounds/constellation-field)：细线、节点、
  Gateway 和 Topography，适合研究结构层如何存在但不抢 Pad；
- [Portal Field](https://threeui.com/backgrounds/portal-field)：同族跨 Three.js、raw WebGL
  和 Canvas 2D，可比较是否真的需要 3D；
- [Bell Field](https://threeui.com/backgrounds/bell-field)：Chladni 式节点图形与 Strike
  行为和音乐产品相关，但必须改成由真实演奏事件触发，而不是自动定时表演。

这些效果若进入 Creator，应位于 Pad 之后、低对比、`pointer-events: none`，离屏、页面
隐藏、Reduced Motion 或视觉预算不足时可停。它们不应成为 Project / Sequence / Sample
的不同皮肤，也不应造成模式切换后像进入另一个产品。

### 3.4 第四优先：声音与身份图形

[Article Headings](https://threeui.com/text-animation/article-headings) 中的 Audio Wordmark、
Particle Wordmark，以及 [Typography Vortex](https://threeui.com/text-animation/typography-vortex)
展示了文本轮廓、粒子和 Pointer 交互如何形成记忆点。

Creator 可以借鉴这种“一个签名元素”，但不能把持续动画 Logo 放在主操作区。更合理的
用途是首次进入、空闲态、成功 Commit 或演奏间隙的短反馈；若音频驱动，应读取已有的
只读 Meter / Analysis 数据，不能在视觉组件里建立第二套音频事实或新的 AudioContext。

---

## 4. 明确不作为 Creator 方向的内容

| 效果族 | 不采用的原因 |
| --- | --- |
| 完整 Landing Pages / Hero | 为叙事、滚动和 Marketing 构图，信息架构与固定 4×4 乐器壳冲突 |
| [Diagnostics Panel](https://threeui.com/ui-elements/diagnostics-panel) | #522 的目标正是离开诊断控制台；只能作为“不要退回这里”的反例 |
| [CRT](https://threeui.com/backgrounds/crt) | 扫描线、故障和噪声降低长时可读性，也容易把 Error 变成装饰而不是诚实状态 |
| [Performance Gauges](https://threeui.com/css/performance-gauges) | 可借刻度、数值和仪器精度，但汽车仪表语义会把 Creator 带向 Dashboard / Simulator |
| [Koi Studies](https://threeui.com/css/koi-studies) 与 Character Carousel | 角色、卡片堆和收藏展示抢夺 Pad 的主体地位；与 #522 的 Mascot 禁区相撞 |
| 高密度全屏粒子 / 后处理 Bloom | 与 16 个高饱和 Pad 争夺层级，并会和 AudioWorklet 竞争移动设备资源 |
| 每个模式一套 3D 世界 | 破坏 Project / Sequence / Sample 共用同一乐器身体的原则 |

“不作为方向”不等于禁止研究其中单个技术手法。例如 Performance Gauges 的极坐标刻度、
Koi Studies 的 Reduced Motion、CRT 的 Canvas → WebGL 合成方式都可作为实现知识，但不能
把其视觉隐喻原样带入 Creator。

---

## 5. Three.js 是否应成为 Creator 的底子

### 5.1 建议架构

```text
Application Facade / Host View Model（权威状态）
                    │
          React + semantic HTML
   布局 / Pad 按钮 / Focus / ARIA / Pointer / Keyboard
                    │ 单向、只读视觉输入
          Creator Visual Adapter
   motion preference / visibility / quality / lifecycle
                    │
   Three.js shared renderer 或更便宜的 Canvas/CSS 实现
       背景场 / Pad 表面增强 / 短生命周期反馈
```

这里的关键不是强制所有效果都用 Three.js，而是建立一个一致的视觉层 Contract：

- 需要 Scene / Camera / Geometry / ShaderMaterial 的效果以 Three.js 为首选底座；
- CSS 或 Canvas 2D 能更便宜完成的效果不升级到 Three.js；
- Raw WebGL 只有在经过测量、能显著降低成本或实现 Three.js 难以表达的 Shader 时才采用；
- 视觉层只能消费不可变 View Model / Event，不获得 Project Bundle 路径，不修改 Project Truth；
- 视觉层失败只损失增强效果，不能损失输入、状态、错误说明或声音。

### 5.2 为什么不做单一 3D Canvas UI

把所有 Pad 和控件画进一个 Canvas 会立刻重建浏览器已经提供的能力：

- 键盘 Focus、屏幕阅读器名称、按钮禁用与表单语义；
- Pointer Capture、Touch Target、文本选择和浏览器缩放；
- Playwright / Testing Library 可观察的真实控件状态；
- 高对比、Reduced Motion、字体和系统辅助技术适配；
- WebGL Context Lost 后仍能操作的降级界面。

当前 Creator 的 Pointer / Keyboard / MIDI 已统一进入 Host 输入路径。把 Pad 命中测试迁进
Three.js 会把视觉选择扩大成输入与产品语义重写，不符合 #522 的 Phase 1 范围，也没有
用户价值上的必要性。

### 5.3 Renderer 所有权

若未来采用，优先一个 Host 级共享 Renderer / Canvas 或极少数明确隔离的 Canvas，不为
16 个 Pad 分别创建 WebGL Context。视觉适配层统一负责：

- Renderer、Scene、Geometry、Material、Texture 的创建和 `dispose()`；
- ResizeObserver、DPR 上限与质量档；
- 页面隐藏、离屏、后台和 Host 卸载时暂停；
- `prefers-reduced-motion` 的静态帧或 CSS 退化；
- `webglcontextlost` / `webglcontextrestored` 与不可恢复时的 HTML Fallback；
- 不把每帧 React State 更新作为动画驱动。

ThreeUI 中较成熟的条目已经展示 DPR 封顶、IntersectionObserver、`visibilitychange`、
取消 RAF 和资源释放；也有不少较老的自包含 HTML 只持续 RAF、依赖不同 Three 版本或远程
CDN。不能把目录条目都当成同等生产质量。

---

## 6. 与当前 Creator 分发边界的冲突

### 6.1 CSP 与同源离线要求

当前 Web Host 分发 CSP 为：默认拒绝；Script、Connect、Style、Image 只允许同源；
同时启用 COOP / COEP / CORP。ThreeUI Community 的部分条目使用远程预览媒体、CDN 库或
ThreeUI 托管资源，直接复制会被当前策略拒绝，也会破坏离线与可复现分发。

生产候选必须：

- 不在运行时访问 ThreeUI、Google Fonts 或第三方 CDN；
- 把获准资产和 License Notice 一同纳入仓库与分发；
- 不使用 Blob / Data URL 规避当前 CSP；
- 在 COEP `require-corp` 下验证所有 Worker、Image、Video、Texture 和 Font；
- 把视觉层所需的新增文件类型显式纳入打包、哈希和验证 Contract。

### 6.2 当前 Creator 打包白名单

Creator 的内容哈希资产验证目前只接受 CSS、JS / MJS 和 Wasm；`img-src 'self'` 虽允许
同源图片，但打包 Contract 并未自动接收 ThreeUI 的 WebP、JPEG、MP4、Font 或 Texture。
因此第一轮 Spike 应优先选择**无外部资产的程序化效果**。若产品方向确实需要纹理、模型、
视频或字体，必须把打包 / 授权 / 哈希 / 缓存 / 离线验证作为独立实现范围，不能把文件悄悄
塞进 UI PR。

### 6.3 授权边界

- ThreeUI Community 的应用代码、Community 组件代码和 ThreeUI 自有 Community 图片按
  MIT 发布；复制或修改时保留 Copyright 与 License；
- 随包开放字体仍是 SIL OFL 1.1，Three.js Runtime 仍是 MIT，应保留各自 Notice；
- 官网远程 Thumbnail / Preview 不由 Community 仓库 MIT 授权，不能当 LMDJ 资产复制；
- Pro / Beta 源码不在 Community 包内。把 Pro 条目作为灵感参考不等于取得实现和资产授权；
- 每个入选条目仍需做逐文件 Asset Inventory，不能只看仓库根 License。

---

## 7. 性能、实时音频与无障碍门槛

视觉层进入产品前，至少要证明以下顺序：

```text
音频触发与持续播放
  > Pointer / Keyboard / MIDI 可用性
  > 错误与真实状态可读
  > 视觉反馈同步
  > 视觉细节、粒子数量、DPR 和后处理质量
```

视觉质量是第一个可降级项。建议未来 Spike 明确测量并留下证据：

| 门槛 | 必须观察 |
| --- | --- |
| 音频 | 加载视觉层前后 Trigger Miss / Duplicate、Launch Ack、听感爆音与长时间稳定性 |
| 主线程 | Pad 连打、Mode / Bank 切换、Waveform 拖动时的长任务和输入响应 |
| GPU | Frame Time、DPR、Context 数、Texture / Buffer 生命周期、Context Lost 恢复 |
| 页面生命周期 | Hidden、Background / Foreground、Lock / Unlock、Resize、Route / Mode 切换 |
| 无障碍 | HTML 控件仍可 Keyboard / Screen Reader 操作；状态不是 Color / Motion Only |
| 动效偏好 | Reduced Motion 下不只减速，而是停为可理解静态状态 |
| 降级 | WebGL 不可用、初始化抛错、Shader 编译失败后仍可完整演奏和保存 |

不要先写一个固定 FPS 或粒子数量作为政策；先用现有 Creator Proof 设备和 Journey 测出
Baseline，再由后续 Issue 批准预算。对于 iPadOS Safari，应同时观察 GPU 与 AudioWorklet，
不能只在没有声音的 Visual Demo 中判定“流畅”。

---

## 8. 采用方式建议

### 8.1 作为参考目录

未来每个 UI Issue 若考虑动态效果，可在设计说明中记录：

```text
ThreeUI reference URL:
Exact component / variant:
Borrowed principle:
Rejected parts:
Runtime family: CSS | Canvas 2D | Three.js | Raw WebGL
Source boundary: Community MIT | Pro reference-only | unknown
Assets and notices:
Reduced-motion / no-WebGL fallback:
Performance evidence required:
```

这样可以选“手法”而不是无意中选中整套网站风格。

### 8.2 对 #522 Phase 1 的用法

ThreeUI 只应进入三份静态标本中的一部分，不能三份都变成深色粒子面板。建议覆盖：

- 一份把 Rectangle / Liquid Metal 的局部触感翻译为 Pad 身份几何；
- 一份用 Structure Flow / Constellation Field 研究低对比程序化结构；
- 第三份保持非 GPU 的印刷 / 面板方向，确保发散仍然真实。

Phase 1 仍然输出静态标本，不把 ThreeUI 代码安装进 `apps/creator-web`，也不因为看到效果
目录就提前选择“深色 + Bloom + 粒子”作为最终方向。

### 8.3 未来生产 Spike

视觉方向获批后，建议只开一个最小 Spike：

1. 选一个无外部资产、无后处理链的效果；
2. 由共享 Visual Adapter 驱动一个低对比背景或一个 Pad 区反馈；
3. HTML Pad 保持原位和完整语义；Canvas `aria-hidden` 且默认不接管 Pointer；
4. Three.js Chunk Lazy Load，初始化失败可回到静态 CSS；
5. 跑当前 macOS / iPadOS Web Proof 与音频 Journey，再决定依赖；
6. 若通过，单独批准 `three` 版本、Bundle Budget、升级政策和 Portal 文档影响。

不要以直接安装整个 `@designcodeio/threeui` 作为 Spike 成功标准。可以先参考或移植一个
Community MIT 条目的最小算法，同时保留 Notice；最终选择 Package Import、项目内适配或
原创重写，应由依赖体积、版本统一、源码可维护性和授权清单共同决定。

---

## 9. 决策状态

本研究支持以下**待后续批准的方向**：

- ThreeUI：加入 LMDJ UI 参考库，作为效果检索和原型来源；
- Creator：保留 React + 语义 HTML 为产品 UI 底座；
- Three.js：作为隔离、可降级、音频优先的 GPU 视觉层候选标准；
- 首个生产用例：优先 Pad 区局部反馈或低对比程序化场，不是完整 3D Workspace；
- 来源：优先无外部资产的 Community MIT 条目；Pro 先按 Reference Only 处理。

尚未批准：

- `apps/creator-web` 新增 `three` 或 `@designcodeio/threeui`；
- 具体 Three.js 版本、Bundle / Frame / GPU Budget；
- 三份 Phase 1 标本中的某份获胜；
- Canvas 接管 Pad Hit Testing 或任何输入语义；
- Product、Host、Runtime、Contract 或 Project Truth 变更。

## 10. Version Management

Version impact: none。本文是研究输入，不修改 Product、Host、Core Module、Provider 或
Contract 身份，也不分配 Product Build。

## 11. Documentation impact

Documentation impact: none。本文位于 `docs/research/`，不改变 Architecture Portal 当前产品
事实、Host 行为或发布快照。若 Phase 3 批准 Three.js 视觉层，设计 Spec 必须点名至少
`/hosts/creator-web/` 的影响；任何 Product Build 或 Assembly 变更按治理规则创建不可变快照。

---

## 12. 主要来源

### ThreeUI 官方来源

- [ThreeUI 公开目录](https://threeui.com/)
- [ThreeUI Community 官方仓库](https://github.com/MengTo/threeui)
- [Community README 与安装 / 发布边界](https://github.com/MengTo/threeui/blob/main/README.md)
- [Package 依赖与导出](https://github.com/MengTo/threeui/blob/main/package.json)
- [MIT License](https://github.com/MengTo/threeui/blob/main/LICENSE)
- [Asset Licenses](https://github.com/MengTo/threeui/blob/main/ASSET-LICENSES.md)
- [Font Licenses](https://github.com/MengTo/threeui/blob/main/FONT-LICENSES.md)
- [Third-party Notices](https://github.com/MengTo/threeui/blob/main/THIRD_PARTY_NOTICES.md)

### LMDJ 权威输入

- [Creator 产品视觉语言 Brief](./2026-09-01-creator-visual-language-brief.md)
- [Stage 7 Creator Editor Design](../superpowers/specs/2026-08-07-lmdj-stage7-creator-editor-design.md)
- `apps/creator-web/package.json`
- `apps/creator-web/src/components/pad_surface.tsx`
- `apps/creator-web/src/runtime/input_controller.ts`
- `apps/creator-web/src/styles.css`
- `tools/web-runtime/serve_distribution.py`
- `apps/creator-web/tools/package.py`
