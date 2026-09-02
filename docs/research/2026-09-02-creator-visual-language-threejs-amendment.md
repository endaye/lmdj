# Creator 视觉语言 Brief 增补：Three.js

> 研究日期：2026-09-02
>
> 用途：把「Web Creator 使用 Three.js」写进 [#522](https://github.com/endaye/lmdj/issues/522) Phase 1 条件。不回改 [2026-09-01 brief](./2026-09-01-creator-visual-language-brief.md)。
>
> 状态：约束已确认。不是设计规格，不是把 `three` 写进 `apps/creator-web` 的实施授权。

权威决策：[2026-09-02 Creator Web Three.js](../prd/decisions/2026-09-02-creator-web-threejs.md)。

## 0. 看过什么

| 位置 | 事实 |
| --- | --- |
| `apps/creator-web/package.json` | 只有 React 19 与 Vite。没有 `three`。 |
| `apps/chameleon-lab` | 现役是 2D Canvas 程序化变色龙，无 Three.js 依赖。 |
| `docs/superpowers/specs/2026-08-05-chameleon-lab-design.md` | 曾规划 Vite + React + 原生 Three.js + `CanvasTexture` 茶壶实验；未按该规格落地到现役 Lab。 |
| Kumaleon 研究 | 可借鉴的结构是 Canvas 2D → `THREE.CanvasTexture` → 稳定 3D 轮廓；不可借模型、字体、皮肤。 |
| 实时 3D ASCII 研究 | Three.js 适合短时、非关键品牌/状态反馈，不适合盖住 Pad、波形、错误信息。 |

仓库里目前没有任何 `package.json` 声明 `three`。

## 1. 增补到 brief 的条件

在 2026-09-01 brief 的已锁约束上增加：

- Creator 的视觉层渲染器是 Three.js，落点是 `apps/creator-web`。
- 3D/WebGL 是乐器的一层，不是另一个 App。Pad 仍是身体；只有 Pad 区可以高饱和、高密度。
- 变色龙 / 3D 皮肤 / kawaii 仍不能当主视觉。远景、低对比、不抢 Pad 的 3D 状态物仍是可选标本，不是必做。
- 不把 chameleon-lab 当 Creator 实现，不把 Lab 的页面编排复制进工作台。

## 2. 对 Phase 1 标本的要求

三份互斥标本除原 brief 的壳、状态和参考覆盖外，还必须：

- 画出 WebGL 层的位置（Pad 内几何、远景状态物、或 Surface 背景舞台均可，三份可以互斥）。
- 该层不得挡住 Pad 触点、Bank、波形 handle、错误面板或模式 Rail。
- 静态 HTML 或图即可；标本不运行 Three.js，不新增 npm 依赖。
- `prefers-reduced-motion` 下该层必须有静止读法（静态帧或关闭），信息不依赖持续旋转。

开放轴因此多一条：**3D 层放在哪**（Pad 内 / 远景 / Surface 背景）。材料、字体、Pad 身份几何、动效仍开着。

## 3. 明确还不做

- 不改 `apps/creator-web`。
- 不在本增补里选择 React Three Fiber 或原生 Three.js 封装。
- 不选择具体 GLB、变色龙网格或 ASCII 后处理。
- 不把 WebGL 失败伪装成可演奏成功态；实现阶段必须有 2D fallback，那是 Phase 4 的事。

## 4. 版本与文档

- Version impact: none。约束记录，不分配 Host 版本。`creator-web` 引入 `three` 时再 bump。
- Documentation impact: none。不改变 Architecture Portal 当前页。Phase 3 spec 若落地 Three.js，再点名 `/hosts/creator-web/`。
