# Creator 产品视觉语言 Brief

> 研究日期：2026-09-01
>
> 用途：锁定 [#522](https://github.com/endaye/lmdj/issues/522) 经 grilling 确认的产品约束，作为 Phase 1 灵感发散的 brief。不是设计规格，不是实施授权。
>
> 状态：约束已确认；Phase 1 标本尚未开始。后续标本与「看过什么 / 为什么还没选」写入新的日期产物，不回改本文。

## 0. 结论先行

`apps/creator-web` 要成为一件**乐器**，不是 Stage 6 诊断控制台。16 个正方形 Pad 是身体；顶栏、Mode Rail 和模式 Surface 是结构。

这次程序先发散、再收敛、再出 spec、最后才落地。本文只锁 brief。Phase 1 用静态标本比赛，不改产品 CSS。

## 1. 权威与边界

- 生命周期：GitHub Issue [#522](https://github.com/endaye/lmdj/issues/522)
- 现役壳：Stage 7 S7-D3，见 `docs/design/2026-08-07-lmdj-stage7-creator-editor-design.md`
- 现役实现：`apps/creator-web`（`#101216`、薄荷绿 `#b7ffc5`、Inter、圆角卡；Pad 仅显示地址 / Assigned|Empty / 键帽）
- 历史输入，**不当标本**：
  - `docs/design/2026-07-24-stage1-creator-workspace-ui-design.md`
  - `docs/design/2026-07-27-polanyi-living-instrument-ui-design.md`
  - `docs/design/2026-07-24-stage1-creator-workspace-ui-references/`
  - `docs/research/2026-07-26-kumaleon-visual-technology-study.md`
- 变色龙是独立层：`docs/prd/assets/chameleon/`、`docs/design/2026-08-05-chameleon-lab-design.md`

本文不改变 Core、Contract、Runtime、Project Truth 或 Architecture Portal 当前页。

## 2. 已锁约束

### 2.1 对象与人

- Creator 是乐器。打开后应立刻读成可演奏的物体，而不是配置软件或展览海报。
- 主使用者：桌面 DAW prosumer；实体 8/16 Pad 是验收手。设计者本人是日常手。
- 不是现场舞台、不是 iPad-first、不是演示海报。Stage 10 Perform 不定义这次的房间。

### 2.2 壳

沿用现役 Host，不重做信息架构：

```text
顶部 Status Bar
左侧 Mode Rail（Project / Sequence / Sample；Perform 可见但禁用）
中部模式 Surface
底部固定 4×4 Pad + Bank
```

- 切模式不移动 Pad 的空间身份。
- 不改 Pad 数量、Bank 语义、键位或 MIDI 映射。
- 要桌面 8×2、三栏或常驻 Inspector，另开产品 Issue。
- Perform 继承同一套语法。暗场 / 远距离可读的例外另开 Issue，#522 不预留第二套皮。

### 2.3 颜色语义

现役 Pad 数据没有 Drum / Bass / Harmony 角色字段。颜色不绑音乐角色。

| 绑定 | 来源 |
| --- | --- |
| Empty / Assigned / Capturing / Playing / Error | 真实状态 |
| Assigned 的稳定身份色 | `assetId`；无 asset 则 slot。确定性，跨刷新稳定 |

角色色若要回来，另开产品 Issue，等 Project 真有该字段。

### 2.4 信息层级

只有 Pad 区可以高饱和、高密度。顶栏、轨、Surface 是结构线。波形和 Pattern 网格是中景，不能比 Pad 更响。

### 2.5 禁区

- 变色龙 / 3D 皮肤 / kawaii **不能当主视觉**。远景、低对比、不抢 Pad 的状态物可作可选标本，不是必做。
- 不复制 Kumaleon 的角色、字体、皮肤、Logo、官网逐像素版式。网格、纸面、生成几何语法可以当研究。
- 不以现役 `#101216` + 薄荷绿 + Inter 圆角卡作为方向。
- 不用通用「米白衬线 + 陶土强调」模板。
- 不为未实现能力画可点入口。
- Project / Sample / Sequence 不做两套皮。
- 7 月 Workspace / Polanyi **稿件**不当标本。直角、零阴影仍是开放轴，不是法律。

## 3. 留给 Phase 1 的开放轴

标本必须在这些轴上真正互斥，而不是换个字体：

- 画布材料（纸面 / 深色面板 / 第三种）
- 字体配对
- Pad 身份几何
- 动效，包括是否使用直角、硬阴影或倒角

纸面乐器仍允许，但必须按现役 4×4 壳重画，不得把 7 月 HTML 当标本文件提交。

## 4. Phase 1 出口

三份互斥乐器标本 + 一篇新的日期研究简报，在 #522 链接。那篇简报写：看过什么、每份的签名、禁区自检、为什么还没选。本文不被那篇简报回改。

### 4.1 每份标本

- 完整壳：Status + Rail + Surface + 4×4 + Bank。
- 静态 HTML 或图。不改 `apps/creator-web`。
- Pad 状态至少：idle / empty / assigned / capturing / playing / error。
- 看得出切换模式时 Pad 不动。

三份合起来覆盖 Project、Sequence（Pattern 在 Pad 上）、Sample（波形在 Pad 上）。不必每份都画全模式。

### 4.2 参考覆盖

三份标本的参考强制覆盖这三类，一类可以对应一份，也可以交叉，但不能三类只落在同一份上：

1. 实体 Pad 控制器
2. 印刷 / 面板 / 海报
3. 一个密、但不像 DAW、也不像 SaaS 的演奏 UI

### 4.3 视口

- 主稿 1440×900
- 每份另给一个约 768–1024 宽的同一壳（仍是 4×4）
- 不保证 360px 手机

## 5. 后续阶段（本文不启动）

| 阶段 | 出口 | 仍禁止 |
| --- | --- | --- |
| 2 方向 | 2–3 个命名方向里选出一个；改产品规则先写 `docs/prd/decisions/` | 产品 CSS |
| 3 设计 | `docs/design/` 下的批准 spec + 视觉稿；点名 Portal 路由 | 产品 CSS |
| 4 落地 | 有边界的实现 Issue；不与 Stage 10 Perform（#435）混在同一分支 | 改 Runtime / Contract |

## 6. 版本与文档

- Version impact: none。研究 brief，不分配 Product / Host / Module 版本。
- Documentation impact: none。不改变 Architecture Portal 当前页、快照或产品身份；Portal 路由由 Phase 3 spec 点名。
