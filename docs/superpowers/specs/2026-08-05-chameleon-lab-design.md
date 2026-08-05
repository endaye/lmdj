# Chameleon Lab 动态 3D 贴图实验站设计（参考 Kumaleon）

- 日期：2026-08-05
- 状态：用户已确认；尚未实施
- 目标落点：`apps/chameleon-lab/`
- 性质：独立视觉技术实验，不是 LMDJ Product Assembly 或 Core Host
- 参考对象：[Kumaleon](https://kumaleon.com/)

## 1. 目标

建立一个可独立运行的静态首页实验站，复现 Kumaleon 最值得研究的技术关系，
而不是复制其品牌或美术：

1. React 页面负责展览式首页、导航和皮肤选择控件；
2. Three.js 在浏览器内渲染程序化茶壶几何体；
3. Canvas 2D 持续生成动态纹理；
4. `THREE.CanvasTexture` 将动态纹理实时映射到茶壶材质；
5. 用户选择皮肤时，3D 材质、页面背景和 UI 强调色同步变化；
6. 桌面和移动布局分别调整 DOM、相机、模型比例和交互方式。

本实验的成功标准是让开发者可以直接阅读、运行和修改这条数据流，验证动态
贴图切换机制，而不是完成一个可发布的 LMDJ 产品页面。

## 2. 权威边界

- 不下载、复制或重新分发 KUMALEON 的模型、Logo、字体、纹理、图标、文案或
  其他品牌资产。
- 3D 主体使用 Three.js examples 提供的程序化 `TeapotGeometry`，不引入外部
  GLB 或第三方角色模型。
- 页面只借鉴“严格网格 + 生成艺术 + 中央 3D 展示体”的关系，使用本项目自己的
  中性文字、色板和几何符号。
- 不加入 Wallet、NFT、Web3、账户、后台、分析或内容管理功能。
- 不读取 Project Truth、Runtime Snapshot、Artifact、Provider 或任何 LMDJ Core
  数据，也不声明 Host、Module、Provider、Contract 或 Assembly 身份。
- 实验目录不得添加 `module.json`，避免被架构门户误识别为正式组件。

## 3. 技术方案

采用 `Vite + React + TypeScript + 原生 Three.js`。

不采用 React Three Fiber，因为本实验需要直接暴露 renderer、scene、camera、
texture、render loop 和资源释放的完整生命周期。不采用纯 Three.js 页面，因为
React 更适合管理首页 DOM、响应式导航、皮肤选择和无障碍状态。

项目是独立 npm 边界，拥有自己的 `package.json`、lockfile、TypeScript 和 Vite
配置，不依赖仓库根部 JavaScript workspace。

## 4. 模块边界

```text
apps/chameleon-lab/src/
  app/              首页组合、状态与页面级样式
  patterns/         确定性 Canvas 2D 动态纹理生成器
  three/            场景、茶壶、CanvasTexture、渲染循环与资源释放
  ui/               导航、皮肤选择器、说明和 WebGL fallback
  test/             浏览器环境测试支持
```

### 4.1 `patterns/`

首版提供四种原创程序化皮肤：条纹、轨道、网格和波场。每种皮肤由稳定 ID、
色板、种子和时间输入决定，同一 ID 与种子产生可复现的基础构图。时间只驱动
连续运动，不在 React 重渲染时随机跳变。

生成器接收 Canvas 2D context、逻辑尺寸、时间和 reduced-motion 状态，不依赖
React 或 Three.js。Reduced Motion 下使用固定时间采样，保留换肤而停止持续动画。

### 4.2 `three/`

`ThreeStage` 独占 WebGL 生命周期：创建 renderer、scene、camera、灯光、茶壶和
requestAnimationFrame；在卸载时取消帧循环并 dispose geometry、material、texture
和 renderer。

`CanvasTextureBridge` 持有一个受控 Canvas 和一个长期存在的
`THREE.CanvasTexture`。每帧先由选中的 Pattern 绘制 Canvas，再设置
`texture.needsUpdate = true`。切换皮肤时替换 Pattern 配置，不重复创建 renderer、
geometry 或 texture。

纹理使用 sRGB 色彩空间、线性过滤和明确的 UV 方向。首版不使用 GPU picking、
后处理、阴影贴图或多个 WebGL canvas。

### 4.3 `app/` 与 `ui/`

React 只保存当前皮肤 ID、菜单状态和 reduced-motion 偏好。皮肤选择器使用原生
button，并通过 props 将选择传给 `ThreeStage`。Three.js 不直接查询或修改 DOM。

静态首页包含：粗线外框、顶部网格导航、巨型背景标题、中央 3D 舞台、围绕舞台
排列的四个皮肤按钮、技术说明和移动端全屏菜单。它不复用 Kumaleon 的品牌名称
作为本项目标识。

## 5. 数据流

```text
用户选择皮肤
  -> React 更新 skinId
  -> ThreeStage 接收新的 Pattern 配置
  -> PatternEngine 按时间绘制受控 Canvas
  -> CanvasTextureBridge 标记纹理更新
  -> Three.js 在下一帧把纹理映射到同一个茶壶材质
  -> React 同步更新页面背景与强调色
```

鼠标移动只影响有上限的相机视差；触摸拖动只影响模型旋转。窗口尺寸变化更新
renderer 像素比、Canvas 尺寸、相机比例和模型尺度。像素比上限为 2，避免高 DPI
设备无意义地放大 GPU 成本。

## 6. 错误处理与可访问性

- WebGL 不可用或 renderer 初始化失败时，保留完整页面、皮肤说明和一张由同一
  PatternEngine 生成的 2D Canvas fallback，并显示明确提示。
- Pattern 绘制失败时停止该帧更新，保留最近一次有效纹理，不伪造成功状态。
- Canvas 提供可读替代文本；皮肤按钮具有选中状态、键盘焦点和明确名称。
- 颜色变化不是唯一反馈，当前皮肤名称同时显示为文字。
- `prefers-reduced-motion` 关闭环境动画、相机视差和纹理时间推进。

## 7. 验证

自动验证包括：

- Pattern 确定性、不同皮肤差异和 reduced-motion 固定采样的单元测试；
- React 皮肤选择、键盘操作、选中状态和 fallback 的组件测试；
- Three.js 生命周期测试，证明切换皮肤不会重建 renderer，并验证 dispose；
- TypeScript 类型检查和 Vite production build；
- Playwright 桌面与移动 smoke，验证 WebGL 页面可见、皮肤切换和无运行时错误。

本地验收还需要在真实浏览器中观察至少两次皮肤切换，确认动态纹理连续、茶壶
材质更新、布局不溢出，并检查 reduced-motion。自动化通过不等同于跨设备 GPU
兼容性已经完成。

## 8. GitHub CI 边界

该实验不加入独立 GitHub workflow。现有通用 CI 和架构门户 workflow 应将
`apps/chameleon-lab/**` 作为 app-only 变更的忽略路径；当同一提交同时修改其他受管
路径时，原有 CI 仍正常运行。仓库保护规则和本地验证不因 CI 排除而取消。

## 9. Documentation Impact

Documentation impact: none

理由：该项目是没有 `module.json` 的独立视觉技术实验，不改变正式 Host、Core、
Provider、Contract、Product Assembly、平台能力或架构门户公开身份。设计与实现
说明保留在 `docs/superpowers/` 和项目自身 README，不新增或修改门户路由。

实施前后仍需运行 `scripts/architecture-portal.sh check`，证明实验未被误纳入正式
架构清单。

## 10. Version Management

Version impact: none

理由：实验不属于 LMDJ Product Assembly，不改变 Product Build、Module、Provider
或 Contract 身份，也不分配 Product Build 或 Release Channel。项目 package 使用
私有的 `0.0.0` 开发版本，仅用于 npm 工具链，不代表产品版本或可发布版本。

## 11. 首版验收标准

1. `apps/chameleon-lab/` 可通过单一 npm 命令启动并通过 README 独立理解；
2. 首页在桌面和移动视口都可用，不依赖 KUMALEON 美术资产；
3. 茶壶使用一个持续存在的 `CanvasTexture` 显示动态程序化纹理；
4. 四个皮肤按钮都能切换纹理，并同步页面视觉变量；
5. Reduced Motion、键盘操作和 WebGL fallback 有真实实现与测试；
6. 类型检查、单元/组件测试、production build 和浏览器 smoke 通过；
7. app-only 变更不会触发仓库 GitHub CI，其他路径的既有 CI 行为不变；
8. 架构门户检查通过，且实验不会出现在正式组件清单中。
