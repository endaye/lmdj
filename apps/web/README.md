# LMDJ Web Patch View

`lmdj.patch.v1` 的第一个消费者：8-pad Focus View 工作台原型。设计文档见
`docs/superpowers/specs/2026-07-07-lmdj-web-patch-view-design.md`。

## 运行

```bash
npm install
npm run make-example   # 首次；前置：仓库根目录 scripts/dev.sh smoke
npm run dev            # http://localhost:5173
```

拖入任意 patchify 产出的 package 目录，或点击"加载示例 patch"。
操作：▶ 播放/停止；点击 pad 或按 `A S D F / Z X C V` 触发；右键 pad 静音整组。

## 测试与契约

```bash
npm test                 # 全部单测（Vitest + RTL）
npm run check-contract   # schema 拷贝与 types.ts 未漂移
npm run sync-contract    # core-models 契约变更后重新同步
```

契约纯度：本应用只读 `patch.json`，不读 `lanes.json`/`chart.mid`。
