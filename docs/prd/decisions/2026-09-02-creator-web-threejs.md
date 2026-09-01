# 已确认：Creator Web 使用 Three.js 作为视觉层渲染器

- 日期：2026-09-02
- GitHub Issue: [#522](https://github.com/endaye/lmdj/issues/522)
- 结论：`apps/creator-web` 将使用 Three.js 渲染乐器视觉层。这是 Host 视觉栈约束，不是把 Chameleon Lab 并进 Creator，也不是现在就把依赖写进产品。
- 原因：Web Creator 需要在浏览器里承载确定性几何、演奏反馈和可选远景状态物；现役 Host 只有 DOM/CSS，Chameleon Lab 是独立 2D 实验，不能当产品渲染器。Three.js 是这条视觉层的既定渲染器。
- 影响：
  1. [#522](https://github.com/endaye/lmdj/issues/522) Phase 1 标本必须给 WebGL 层留位置，但仍是静态稿，不引入 `three` 依赖、不改 `apps/creator-web`。
  2. Three.js 服务 Pad 身份、演奏反馈和远景状态物，不替代 DOM 工作台，不覆盖 Pad 触点、波形编辑、错误与状态文字。
  3. 变色龙仍不能当主视觉；3D 皮肤系统和 kawaii 向导仍禁。不复制 Kumaleon 的模型、字体、皮肤或官网资产。
  4. 实现时（#522 Phase 4 或后续有边界 Issue）才把 `three` 加进 Creator 的 npm 边界，并处理单一 WebGL context、与 AudioWorklet / Wasm 共存、`prefers-reduced-motion` 和 WebGL 失败的 2D fallback。React Three Fiber 是否采用留给那时的 spec，本文不锁。
  5. `apps/chameleon-lab` 继续是产品中立实验站，不是 Creator 的渲染实现。
