# 实时 3D ASCII 渲染技术研究

> 研究对象：[zanwei.guo 发布的 3D ASCII 短片](https://x.com/zanweiguo/status/2092268513452757133)
>
> 研究日期：2026-08-26
>
> 用途：解释实时 3D ASCII 效果的常见实现，评估可复现路线与对 LMDJ 的潜在价值
>
> 状态：技术研究与工程建议，不代表原作者实现披露，也不代表 LMDJ 已批准或已实现相关能力

## 0. 结论先行

该短片最可能不是“用字符直接搭出 3D 模型”，而是采用一条更常见的屏幕空间管线：

```text
3D 模型 + 相机 + 材质 + 灯光
               ↓
        常规 3D 画面
               ↓
       降采样为字符网格
               ↓
      亮度映射到字符密度
               ↓
      HTML 文本或 GPU 字符图集
```

视频中的头部轮廓、眼窝、侧面和背面遮挡会随旋转保持一致，说明空间关系首先由普通 3D 渲染解决；ASCII 主要负责把最终图像重新编码为字符。它本质上是**常规 3D 渲染之后的风格化后处理**，而不是一套特殊的 3D 建模方法。

最适合快速验证的路线是 Three.js 官方 `AsciiEffect`。它把 WebGL 画面缩小到字符网格，读取像素亮度，再生成等宽 HTML 字符。最适合正式实时产品的路线则是 GPU glyph-atlas shader：仍然先渲染普通 3D 场景，但字符选择与绘制全部留在 GPU，避免逐帧读回像素和重建 DOM。

对 LMDJ 而言，这种效果适合作为短时、非关键的品牌视觉或状态反馈，不适合覆盖波形、Pad、时间线、错误信息等核心操作表面。

## 1. 研究范围与证据边界

### 1.1 本文回答的问题

1. 这类效果的“3D”和“ASCII”分别在哪里产生。
2. CPU/DOM、GPU shader 和真正的字符网格 3D 渲染有什么差异。
3. 视频中的横向扫描线、黑色空洞和明暗层次从哪里来。
4. 如何用 Three.js 做出一个最小可运行版本。
5. 如果把它用于产品，性能、稳定性和可访问性需要注意什么。
6. 它与 LMDJ 现有 ASCII 摄像头视觉方向是什么关系。

### 1.2 证据等级

| 等级 | 证据 | 本文中的用法 |
| --- | --- | --- |
| A | X 短片的逐帧可见画面 | 判断对象旋转、遮挡、字符行结构、颜色和背景 |
| A | Three.js 官方文档与固定提交源码 | 解释 CPU/DOM `AsciiEffect` 的真实数据流和参数 |
| A | 开源 GPU ASCII effect 的固定提交源码 | 解释字符图集、网格量化和 fragment shader 路线 |
| C | 基于画面和公开实现的工程推断 | 判断短片最可能采用的管线和调参范围 |

### 1.3 已确认、可推断与未知

**从短片可直接确认：**

- 主体是一个持续旋转的头骨、面具或相近头部模型。
- 眼窝、面部开口、侧面与背面轮廓随视角连续变化。
- 输出是黑底、白色字符，背景基本不产生字符。
- 字符沿规则的水平行排列，亮部更密，暗部更稀或完全消失。
- 发布内容是约 7 秒的视频，因此只能证明最终视觉，不能证明上传前是否实时运行。

**高可信工程推断：**

- 遮挡和透视先由普通 3D 引擎完成，ASCII 是屏幕空间转换。
- 明暗主要来自 3D 材质与灯光，而不是模型表面预先画好的字符纹理。
- 黑色背景在字符映射时被反相或设置为空格/透明，从而不会填满高密度字符。

**无法由现有证据确认：**

- 原作者使用的是 Three.js、其他 WebGL 框架、桌面引擎还是离线渲染工具。
- 使用的是官方 `AsciiEffect`、自定义 shader，还是视频导出后的二次转换。
- 模型来源、材质、灯光数量、字符集和精确参数。

因此，本文描述的是**最可能且最常见的实现**，不把工程推断写成原作者的源码事实。作者后续也只将其称为“ascii 效果”，没有在公开帖文中给出实现细节。

## 2. 核心原理：3D 负责空间，ASCII 负责重新编码图像

### 2.1 常规 3D 阶段

首先按照普通实时 3D 场景工作：

- 从 GLB、glTF、OBJ 或程序化几何加载 mesh；
- 相机执行透视投影；
- 深度缓冲解决前后遮挡；
- 法线、材质与灯光产生表面亮度；
- 每帧更新模型或相机旋转；
- 输出一张正常的 RGB/RGBA 画面。

这一阶段不需要知道后面会使用 ASCII。轮廓、眼窝和背面是否正确，首先取决于模型拓扑、相机、深度和光照。

### 2.2 字符网格阶段

随后把屏幕划分成固定大小的格子。每个格子对应一个字符：

```text
原始画面：  1920 × 1080 像素
字符格：       8 ×   12 像素
输出网格：   240 ×   90 字符
```

字符不是方形像素。等宽字体的字符通常高于宽，因此纵向格子要更大，或者纵向采样数量要减少。Three.js 官方实现直接每隔两行采样一次，这正是为了补偿字符宽高比。

### 2.3 亮度映射阶段

对每个格子取中心像素、平均颜色或预先降采样后的像素，再计算亮度：

```text
luminance = 0.299 × R + 0.587 × G + 0.114 × B
```

之后将亮度量化为字符索引：

```text
暗                                                     亮
空格  .  :  -  =  +  *  #  %  @
```

不同字符在字面上没有特殊意义，重要的是它们在选定字体中的**墨量覆盖率**。更严谨的实现会用目标字体实际栅格化每个字符，再按照覆盖率排序；随手排列的字符集在换字体后可能不再保持单调亮度。

### 2.4 字符绘制阶段

最终有两种主流输出：

1. CPU 生成字符串，以 `<pre>`、`<table>` 或 Canvas 2D 文本显示。
2. GPU 从预制 glyph atlas 中选择字符小图，在 fragment shader 中直接合成像素。

两者看起来可以相近，但运行成本和输出语义完全不同。

## 3. 三种实现路线

### 3.1 路线 A：CPU/DOM `AsciiEffect`

Three.js 官方 `AsciiEffect` 是最直观的参考实现。它每帧执行：

1. 用 `WebGLRenderer` 正常渲染场景。
2. 把 WebGL Canvas 缩放绘制到更小的 2D Canvas。
3. 通过 `getImageData()` 读取每个像素的 RGBA。
4. 计算亮度并选择字符。
5. 拼接包含换行和可选颜色 `<span>` 的 HTML。
6. 替换承载元素的 `innerHTML`。

官方默认字符集是 `" .:-=+*#%@"`，默认 `resolution` 为 `0.15`，并提供 `color`、`alpha`、`block`、`invert` 和字符分辨率等选项。

**优点：**

- 接入成本最低，适合验证视觉方向。
- 输出是真实字符，可以选择、复制或检查。
- 字符集、字号、颜色和分辨率容易调整。
- 小面积、低字符数场景通常足够流畅。

**限制：**

- `getImageData()` 会把图像数据带回 CPU。
- 每帧拼字符串和重建 DOM 容易触发布局与垃圾回收压力。
- 彩色字符需要大量内联 `<span>`，成本显著增加。
- 全屏、高密度、移动端或多个效果并存时不适合作为默认生产路线。

**适用：**小型原型、静态海报、低帧率装饰、需要真实文本输出的场景。

### 3.2 路线 B：GPU glyph-atlas shader

GPU 路线先把全部字符画进一张规则纹理：

```text
┌────┬────┬────┬────┐
│ 空 │ .  │ :  │ -  │
├────┼────┼────┼────┤
│ =  │ +  │ *  │ #  │
├────┼────┼────┼────┤
│ %  │ @  │ …  │ …  │
└────┴────┴────┴────┘
```

每个 fragment 根据屏幕坐标确定所在字符格，采样该格的场景亮度，计算字符索引，再用格子内部坐标读取 glyph atlas。开源项目 `emilwidlund/ASCII` 的 shader 正是这条路径：

- `floor(uv / grid)` 把屏幕量化为字符格；
- 用 RGB 点积计算灰度；
- 按灰度选择字符序号；
- 从 16×16 的字符图集定位 glyph；
- 用 `NearestFilter` 保持字符边缘不被线性插值污染；
- 最后乘以统一字符颜色并输出。

**优点：**

- 不需要逐帧把整张画面读回 CPU。
- 不重建 DOM，适合全屏、高密度和高帧率。
- 更容易与 bloom、CRT、色差、噪声和拖影等后处理组合。
- 可以进一步读取 depth、normal 或 motion texture，做轮廓增强和时间稳定。

**限制：**

- 输出是 Canvas 像素，不是真实可复制文本。
- 需要维护 shader、字符图集、分辨率和设备兼容性。
- 字符纹理的字体、基线、边距和采样错误会直接表现为抖动或串格。

**适用：**正式网页体验、全屏背景、实时交互、音频驱动视觉和移动端性能敏感场景。

### 3.3 路线 C：真正的终端/字符网格 3D rasterizer

第三种路线不先生成 RGB 画面，而是直接把 3D 三角形投影到字符网格：

1. 顶点经过模型、视图、投影矩阵。
2. 三角形在字符网格上 rasterize。
3. 每个字符格维护 z-buffer。
4. 根据表面法线与灯光计算亮度。
5. 将亮度写成 ASCII 或 ANSI 字符。

它可以在真正的 Terminal 中运行，也可以输出纯文本帧，但需要自己处理裁剪、透视插值、深度、光照和终端刷新。

**优点：**字符是第一等输出，可在终端、日志、SSH 或文本文件中工作。

**限制：**开发成本最高；字体宽高、终端颜色、刷新和闪烁都需要额外处理；很难直接获得现代 3D 引擎已有的材质、阴影和资产生态。

**适用：**终端 demo、ASCII 游戏、远程低带宽显示、文本导出。它不是该 X 短片最可能采用的路线。

### 3.4 路线比较

| 维度 | CPU/DOM | GPU glyph atlas | 字符网格 3D rasterizer |
| --- | --- | --- | --- |
| 3D 来源 | 常规 WebGL | 常规 WebGL | 自己投影与 rasterize |
| 字符输出 | HTML/文本 | Canvas 像素 | 文本/ANSI |
| 接入成本 | 低 | 中 | 高 |
| 全屏实时性能 | 较弱 | 最强 | 取决于实现与网格大小 |
| 可复制文本 | 是 | 否 | 是 |
| 现代材质与资产支持 | 直接继承 | 直接继承 | 需要自行实现 |
| 推荐用途 | 快速原型 | 正式视觉效果 | 终端原生体验 |

另外还有“把每个字符做成 3D sprite/粒子”的视觉路线。它适合字符飞散、景深和空间爆炸，但如果目标只是复现短片中稳定的二维字符行，会增加排序、透明度和 draw-call 复杂度，不是首选。

## 4. 为什么短片呈现出这种视觉

### 4.1 水平扫描线

视频中的连续横线不是 wireframe，主要由以下因素叠加产生：

- 字符严格按文本行排列；
- 字符高度大于宽度；
- 字符集里 `.`、`-`、`=` 等横向笔画占比较高；
- 录屏上传后的缩放和视频压缩会把相邻短横进一步连成线；
- 很小的行距让黑色行间隙形成类似 CRT 扫描线的节奏。

### 4.2 黑色背景保持为空

若把黑色直接映射到最密字符，整个背景会充满 `@`。要得到视频中的纯黑背景，通常采取其中一种做法：

- 字符坡度以空格作为最暗值，并启用正确的 `invert` 方向；
- 使用源画面的 alpha，在透明区域直接丢弃 fragment；
- 设置亮度阈值，低于阈值的格子输出透明或黑色；
- 单独用 object mask 限制 ASCII 只出现在主体上。

Three.js 官方 `AsciiEffect` 的默认索引方向会把低亮度选到字符集末端，因此黑底白字配置通常需要 `invert: true`。

### 4.3 眼窝与开口保持干净

眼窝不是“少画一些字符”手工挖出来的。模型几何、背面剔除、深度缓冲和光照首先产生黑色区域，ASCII 阶段只是把这些暗格映射为空格。因此旋转到侧面时，眼窝和颌部仍能保持连续的空间关系。

### 4.4 形体是否清楚主要取决于光照

ASCII 丢失了大量颜色和亚像素细节，必须依赖强轮廓和明确明暗：

- 主光负责面部体积；
- 边缘光帮助侧面从黑底中分离；
- 高光过宽会让表面变成一整片高密字符；
- 环境光过强会填平眼窝等关键暗部；
- 模型在画面中太小，字符数量不足，五官会立刻消失。

对这种效果，调整灯光往往比增加模型面数更有效。

## 5. Three.js 最小复现

以下骨架使用官方 `AsciiEffect`。它适合先验证模型、构图、字符集和灯光，不代表最终生产实现：

```js
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { AsciiEffect } from 'three/addons/effects/AsciiEffect.js';

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x000000);

const camera = new THREE.PerspectiveCamera(
  35,
  window.innerWidth / window.innerHeight,
  0.1,
  100
);
camera.position.set(0, 0, 5);

const renderer = new THREE.WebGLRenderer({ antialias: true });
const effect = new AsciiEffect(renderer, ' .:-=+*#%@', {
  invert: true,
  resolution: 0.18,
  scale: 1,
  color: false
});

effect.setSize(window.innerWidth, window.innerHeight);
effect.domElement.style.color = '#fff';
effect.domElement.style.backgroundColor = '#000';
effect.domElement.setAttribute('aria-hidden', 'true');
document.body.appendChild(effect.domElement);

scene.add(new THREE.HemisphereLight(0xffffff, 0x000000, 0.25));

const key = new THREE.DirectionalLight(0xffffff, 2.5);
key.position.set(-2, 3, 4);
scene.add(key);

const rim = new THREE.DirectionalLight(0xffffff, 1.2);
rim.position.set(3, 1, -2);
scene.add(rim);

const root = new THREE.Group();
scene.add(root);

const gltf = await new GLTFLoader().loadAsync('/models/head.glb');
root.add(gltf.scene);

function resize() {
  const width = window.innerWidth;
  const height = window.innerHeight;
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  effect.setSize(width, height);
}

window.addEventListener('resize', resize);

renderer.setAnimationLoop((time) => {
  root.rotation.y = time * 0.00045;
  effect.render(scene, camera);
});
```

验证顺序应是：

1. 暂时关闭 ASCII，确认普通 3D 画面的轮廓和灯光成立。
2. 打开 ASCII，以较低密度确认亮度方向和背景阈值。
3. 提高字符密度，修正字符宽高比和主体尺寸。
4. 最后才加入扫描线、噪声、bloom、色差或音频响应。

如果一开始就堆 CRT 特效，很难判断问题来自模型、灯光、采样还是字符映射。

## 6. 视觉调参

### 6.1 字符密度

字符密度是最重要的参数：

- 密度太低：轮廓有力量，但五官和材质信息消失。
- 密度太高：看起来更像经过锐化的灰度图，ASCII 身份减弱。
- 主体越小，越需要减少字符种类并增强轮廓。

短片中的主体在画面占比不大，但仍保留眼窝，说明源模型轮廓明确、对比度高，字符格也没有粗到只剩几十个采样点。

### 6.2 字符坡度

字符集应该按照目标字体的覆盖率排序。可先使用：

```text
 .:-=+*#%@
```

若希望更接近短片的横向感，可以减少圆形和块状字符，提高横向字符权重：

```text
  ._:-=+≡#
```

但这时已经不再是严格 ASCII；Unicode 字符在不同平台上的字体回退和宽度可能不同。产品实现应固定字体，并把 glyph 预烘焙进图集。

### 6.3 时间稳定

当一个格子的亮度在两个字符阈值之间波动时，会产生字符闪烁。常用缓解方法包括：

- 在选字符前对源画面做小范围平均或低通滤波；
- 使用固定 cell center，避免相机亚像素移动改变采样位置；
- 对字符索引加入轻微迟滞，不在单帧内来回跳变；
- 使用有序抖动而不是每帧变化的随机噪声；
- GPU 路线结合 motion vector 或低成本 temporal accumulation。

有意设计的 shimmer 可以制造生命感，但应与采样噪声区分；前者有节奏，后者只会让轮廓发脏。

### 6.4 轮廓增强

仅按亮度映射容易丢失暗部边缘。正式 shader 可以额外读取：

- depth texture：检测物体与背景、前景与后景的深度断层；
- normal texture：检测法线快速变化的折角；
- object mask：保证主体之外不产生字符；
- Sobel edge：把轮廓映射到 `/`、`\\`、`|`、`_` 等方向字符。

轮廓增强应是补充，不应替代正确的灯光与主体尺寸。

## 7. 性能、移动端与可访问性

### 7.1 性能预算

CPU/DOM 路线的成本大致随字符格数量增长：

```text
字符数 = 屏幕宽度 / cellWidth × 屏幕高度 / cellHeight
```

从 120×60 提高到 240×120，不是增加一倍，而是把字符数量放大到四倍。彩色 DOM 模式还会为大量字符生成 `<span>`，应避免用在全屏持续动画。

GPU 路线通常更适合生产，但仍应：

- 限制内部 render target 分辨率；
- 在高 DPR 屏幕上封顶 pixel ratio；
- 页面隐藏时停止动画；
- 根据设备性能降低 cell 密度和后处理数量；
- 避免与多个高成本 blur/bloom pass 无预算地叠加。

### 7.2 移动端输入与热量

持续旋转的全屏 WebGL 即使帧率稳定，也可能带来发热和耗电。移动端可以采用：

- 静止时降到 24–30 fps；
- 用户交互后短时恢复高帧率；
- 进入后台或离开视口时暂停；
- 小屏使用更大 cell，而不是盲目追求桌面密度；
- 首屏优先显示静态 poster，资源就绪后再渐进启用实时效果。

### 7.3 可访问性

实时变化的 ASCII 文本不应被屏幕阅读器逐帧朗读：

- 纯装饰效果设置 `aria-hidden="true"`；
- 若它表达状态，另提供稳定的文本状态标签；
- 遵守 `prefers-reduced-motion`，停止旋转、冻结画面或替换为静态图；
- 不把错误、进度、按钮标签只编码进字符密度或颜色；
- 保证背景效果不降低前景操作的对比度与可读性。

GPU Canvas 本身也不是语义内容，仍需独立的 DOM 文本说明。

## 8. 对 LMDJ 的适用性

### 8.1 与现有 ASCII Matrix Camera 的关系

LMDJ 已有的 [ASCII Matrix Camera Prototype](2026-07-06-ascii-matrix-camera-visual-direction.md) 研究的是“摄像头帧 → 字符”的 2D 输入。本文研究的是“3D 场景 → 字符”。两者的输入不同，后半段可以共享同一抽象：

```text
摄像头视频 ─┐
            ├─→ 降采样 → 亮度/边缘 → 字符选择 → ASCII 输出
3D Render ──┘
```

这不意味着应立即合并两套方向。现有文档记录的是已确认的黑绿摄像头原型；本文只是独立技术研究，不改变其视觉决定。

### 8.2 适合的产品场景

- 启动、等待或导出完成时的短时品牌视觉。
- Chameleon/AI 伙伴的某一种可选表现材质。
- 音频输入驱动的背景视觉：字符密度、光照或旋转速度响应能量。
- 分享卡片、循环短片或演出模式中的视觉层。
- 低信息密度的空状态或展览式页面。

### 8.3 不适合的产品场景

- 覆盖 Creator 的 Pad、波形、时间线、Inspector 或错误信息。
- 用字符动画替代明确进度、失败原因或 Provider Attempt 状态。
- 长时间满屏运行而没有帧率、功耗和 reduced-motion 降级。
- 仅凭风格吸引力改变 Project Truth、Runtime Snapshot 或 Provider 边界。
- 把一次视觉 demo 当作已批准的产品能力或正式架构。

### 8.4 推荐路线

如果未来获得单独批准，建议分两步验证：

1. **视觉 spike：**用官方 `AsciiEffect` 快速确定模型、灯光、字符集、网格密度和品牌适配性。
2. **生产评估：**若效果确实进入持续实时界面，再换成 GPU glyph-atlas shader，建立移动端、reduced-motion 和性能预算。

不要为一次短片预先建设真正的终端 rasterizer，也不要把字符做成 3D 粒子，除非产品明确需要终端输出、空间飞散或逐字符深度交互。

本文不决定未来实现所在目录。任何正式产品实现仍须遵守 Active Source Boundaries：Host 视觉属于相应 `apps/` 边界，可复用且产品中立的模块才考虑 `packages/`；`references/demos/` 只保留参考证据，不能成为正式产品源。

## 9. 推荐验收指标

若后续批准技术 spike，建议预先记录以下指标，避免只凭“看起来好玩”判断：

| 类别 | 建议验证 |
| --- | --- |
| 视觉可读性 | 正面、45°、侧面三个视角都能辨认主体；关键孔洞不被噪声填平 |
| 时间稳定 | 固定相机时轮廓无无规则闪烁；字符变化来自模型/灯光/音频，而非采样漂移 |
| 性能 | 目标桌面与移动设备分别记录平均帧率、P95 帧时间和内部字符网格大小 |
| 功耗降级 | 页面隐藏、离开视口、reduced-motion 和低性能设备都有明确降级 |
| 可访问性 | 装饰 Canvas/文本不进入读屏流；状态另有稳定文字表达 |
| 产品边界 | 不遮挡核心操作，不修改 Project Truth，不把视觉失败写入项目数据 |

## 10. 版本与文档影响

**Version impact: none.** 本次只新增技术研究文档，没有修改 Product Build、Core Module、Provider、Contract 或 Assembly 身份。

**Documentation impact: none.** 本文不改变当前产品架构、运行时行为或任何 Architecture Portal route；它是 `docs/research/` 下的独立参考资料，因此不更新 Portal 当前页或版本快照。

## 11. 来源与进一步阅读

### 11.1 直接研究对象

- [zanwei.guo：3D ASCII 短片](https://x.com/zanweiguo/status/2092268513452757133)，2026-08-25 发布；本文于 2026-08-26 逐帧检查。
- [zanwei.guo：后续说明“我就发个 ascii 效果”](https://x.com/zanweiguo/status/2092224974857945538)，只确认作者对其称谓，不提供源码证据。

### 11.2 实现证据

- [Three.js `AsciiEffect` 官方文档](https://threejs.org/docs/pages/AsciiEffect.html)：构造参数、默认字符集和公开选项。
- [Three.js `AsciiEffect` 固定提交源码](https://github.com/mrdoob/three.js/blob/768a10b473e90404085c6dd3594ae69972b723ba/examples/jsm/effects/AsciiEffect.js)：Canvas 降采样、`getImageData()`、亮度公式、字符映射与 HTML 输出；研究基线提交 `768a10b473e90404085c6dd3594ae69972b723ba`。
- [`emilwidlund/ASCII` 固定提交源码](https://github.com/emilwidlund/ASCII/blob/e0ef82c08610aeaa2c6fd06fd242bdc10fd25951/src/index.ts)：GPU 网格量化、字符 atlas、灰度映射和 fragment shader 输出；研究基线提交 `e0ef82c08610aeaa2c6fd06fd242bdc10fd25951`。
- [Three.js 官方 ASCII 示例](https://threejs.org/examples/webgl_effects_ascii.html)：CPU/DOM 路线的可运行视觉参考。

这些链接用于解释通用实现，不证明 X 短片直接使用了其中任一份代码。
