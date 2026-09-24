# TRMNL Framework 设计系统研究

> 研究日期：2026-09-24
> 研究对象：[TRMNL Framework](https://trmnl.com/framework)，以 [3.3 文档](https://trmnl.com/framework/docs/3.3)为基准。
> 发布参照：3.3.2，官方标注发布于 2026-09-18。
> 源码取证：官方仓库 `main` 在调研时的 `8f2703e66899ef733a8a62e5c90516c4873e48ea`；这是源码快照，不宣称它等于 3.3.2 tag。
> 范围：公开文档、公开源码、浏览器示例观察；不包含实体电子纸测试或 LMDJ 集成实验。

## 0. 核心判断

**TRMNL 最值得研究的是“让有限屏幕稳定表达信息”的完整方法。** 它把排版、设备能力、内容压缩和最终绘制放在同一套规则里，视觉上的克制因此有明确的工程基础。

本文的采用建议分三层：

| 层次 | 判断 | 原因 |
| --- | --- | --- |
| 信息设计方法 | 值得借鉴 | 主值突出、标签辅助、重复项对齐，缩小视图时重新选择内容 |
| 设备适配与渲染架构 | 值得做小范围实验 | 设备能力、主题、DOM 与图表绘制共享规则，减少各处自行适配 |
| 整套框架用于通用交互产品 | 暂不建议直接采用 | 固定画布、内容裁剪和截图就绪机制服务于信息展示，尚未证明适合连续编辑、触控或实时反馈 |

以上是研究判断，不是 TRMNL 官方对其他产品的适用性承诺，也不构成 LMDJ 产品决策。

## 1. 证据边界与版本

本文使用四种证据标记：**官方事实**、**源码确认**、**浏览器观察**、**分析/建议**。未知事项集中列在第 10 节；文档承诺不视为实测结果。

**官方事实：**框架从 3.2 起开源；截至调研日，发行页最新版本为 3.3.2。3.3.2 的说明针对 iframe 中无父 Mashup 的 `.mashup-cell` 处理。本文不使用旧版 2.x 教程推断当前行为。[Open Source](https://trmnl.com/framework/docs/3.3/open_source)、[Releases](https://trmnl.com/framework/releases)

**源码确认：**下文源码链接固定到本次 `main` 快照，便于复查。在线文档可能继续修改；尤其是字体、主题和设备渲染说明，应与真正采用的发布包一起验证。[源码快照](https://github.com/usetrmnl/trmnl-framework/tree/8f2703e66899ef733a8a62e5c90516c4873e48ea)

## 2. 它解决什么问题

**官方事实：**TRMNL Framework 服务于插件屏幕，针对 1-bit、2-bit、4-bit 和有限色电子纸设计，提供 CSS、JavaScript Runtime、设计 tokens 与文档站。[Open Source](https://trmnl.com/framework/docs/3.3/open_source)

**分析：**它的设计起点是“一个给定尺寸、给定色彩能力的画面如何读得清”，这与无限滚动页面不同。由此产生三个优先级：

1. **先读懂，再装饰。** 读者应先看到温度、金额或状态，再找到单位、时间和来源。
2. **先保证当前画面完整，再容纳更多信息。** 一屏放不下时，需要选择、缩写或重新分栏。
3. **视觉效果必须能在目标面板上表达。** 浏览器里的柔和灰色，不一定能直接变成电子纸上的同一观感。

电子纸约束的具体体现是像素对齐：灰色抗锯齿边缘转成黑白时，可能造成字重不均。框架的 Pixel Perfect 机制通过逐行处理和宽度对齐改善这类问题，而不只是换一款“复古字体”。[Pixel Perfect](https://trmnl.com/framework/docs/3.3/pixel_perfect)

本次没有测刷新率、残影、耗电或阅读距离，不能据此给出这些硬件层面的收益。

## 3. 视觉语言：重点来自秩序

### 3.1 真实示例观察

**浏览器观察：**2026-09-24 在官方 Shopify 示例的默认 TRMNL OG 2-bit 预览中，Full View 用 `$159,022` 占据主要视觉权重，`763`、`254` 是次级指标。点阵状竖向 meta 标记、细虚线横分隔、黑实线与灰色点阵比较曲线共同组织信息。[Shopify 示例](https://trmnl.com/framework/examples/shopify)

同页 Quadrant 显示 `$159.0k`，图表移到主值右侧，订单信息排成两列，日期放在底部，未显示 AOV。各尺寸示例有不同模板，不能把全部变化归功于自动缩放。

**分析：**它保住“金额 → 趋势 → 订单”的阅读顺序，再削减次要细节。适配的对象包括内容优先级，不只是字号和容器宽度。

**浏览器观察：**WeatherAPI 示例完成渲染后，上排以大太阳轮廓、超大 `77°` 和较小的 `80° / 45% / Sunny` 形成主次；下排通过水平虚线分隔，两天的天气、UV、低高温按列对齐。粗轮廓图标、大数值、小标签与重复 meta 标记形成一致节奏。[天气示例](https://trmnl.com/framework/examples/weather?variant=weatherapi)

这些观察限于浏览器中的默认设备预览，未操作所有设备、主题组合，也不代表实体面板验收。

### 3.2 可以提炼的设计规则

以下为上述观察的分析，不是官方逐条公布的品牌规范：

| 规则 | 视觉作用 | 迁移时应保留什么 |
| --- | --- | --- |
| 一个区域有一个主读数 | 快速找到重点 | 数值、单位、说明之间的层级差，而非固定照搬字号 |
| 同类信息共享列与基线 | 降低逐项搜索成本 | 数值对齐、标签位置和稳定的阅读顺序 |
| 分隔线承担分组 | 避免每块内容都需要卡片外壳 | 分隔的语义，不必复制所有点阵纹理 |
| 黑白也能区分主次 | 减少对色相的依赖 | 大小、位置、字重、线型等冗余编码 |
| 小视图重新取舍信息 | 保持可读性 | 明确哪些字段必须出现，哪些可以省略 |

它的“系统感”主要来自重复关系，而不是每个组件都被边框圈住。复制像素字体、虚线或黑白配色，只能得到表面风格。

### 3.3 字体、字号与间距

**官方事实：**3.3 在未指定字体包时默认 TRMNL。低密度设备使用所选像素字体包；高密度设备使用 Inter Variable。Scale 或 Text Scale 不是 Regular 时，也会转向 Inter，避免任意缩放像素字体。[Font Family](https://trmnl.com/framework/docs/3.3/font_family)

| 字体组 | 原生角色与尺寸 | 设计含义 |
| --- | --- | --- |
| TRMNL12 / TRMNL16 / TRMNL21 | 12 / 16 / 21 px，提供 Regular、Bold | 小字、正文与标题有专门绘制的像素规格 |
| Classic：NicoPups / NicoClean / BlockKie | 16 / 16 / 26 px，单字重 | 老视觉语言仍可显式选择 |
| Inter Variable | 高密度与较大字号等场景 | 清晰度优先于维持统一的像素造型 |

字体规格与角色来自两个随包 README：[TRMNL bundle](https://github.com/usetrmnl/trmnl-framework/blob/8f2703e66899ef733a8a62e5c90516c4873e48ea/public/fonts/bundles/trmnl/README.md)、[Classic bundle](https://github.com/usetrmnl/trmnl-framework/blob/8f2703e66899ef733a8a62e5c90516c4873e48ea/public/fonts/bundles/classic/README.md)。

字号不能只凭后缀猜测：`text--xlarge` 是 26 px，而 `value--xlarge` 是 74 px。两者是不同语义角色的尺寸阶梯。新代码应使用 `text--*`，官方已将旧 `font--*` 别名标为弃用。[Text Size](https://trmnl.com/framework/docs/3.3/text_size)

间距也不是笼统的 8 px 网格。Gap 的基础 tokens 包括 5、7、16、20、30、40 px 等值；它们还会受到设备与缩放规则影响。借鉴时应先理解角色和节奏，不能把所有示例概括成单一倍数体系。[Gap](https://trmnl.com/framework/docs/3.3/gap)

## 4. 结构与组件：先定义画面，再装内容

**官方事实：**基础结构是 `Screen → 可选 Mashup → View → Layout`，可选 Title Bar 与 Layout 同级；每个 View 只有一个 Layout。平台插件由平台提供外层，自建环境则要自己提供完整结构。[Structure](https://trmnl.com/framework/docs/3.3/structure)

```text
Screen：设备与显示环境
└── Mashup：可选，多插件画面组合
    ├── View：一个插件占据的区域
    │   ├── Layout：内容组织
    │   └── Title Bar：来源、标题、实例信息
    └── View：另一个插件区域
```

结构的价值是让“谁负责尺寸”明确：屏幕不由组件自行猜测，插件也不拥有整台设备的布局。

| 层次 | 主要能力 | 研究理解 |
| --- | --- | --- |
| Foundation | Screen、View、Layout、Columns、Mashup | 分开设备画布、插件区域和区域内排版 |
| Elements | Title、Value、Label、Description、Divider | 优先表达信息角色 |
| Components | Rich Text、Item、Table、Chart、Map、Progress | 以重复内容和数据展示为中心 |
| Utilities | Size、Spacing、Gap、Flex、Grid、Visibility 等 | 在共同规则内精调布局 |

该分类依据官方目录；“以数据展示为中心”是对目录和示例的分析，不等于完整交互组件库承诺。[文档目录](https://trmnl.com/framework/docs/3.3)

Table 提供不同密度规格，并可使用 `data-table-limit` 处理受限高度。Progress 同时提供连续条与离散点，后者区分已完成、当前与未到达状态。[Table](https://trmnl.com/framework/docs/3.3/table)、[Progress](https://trmnl.com/framework/docs/3.3/progress)

Chart 的 `TRMNLCharts` 是适配层，示例使用 Highcharts；Map 的 `TRMNLMaps` 使用 MapLibre GL JS 与 OpenStreetMap 矢量数据，目标是静态绘制，文档明确不提供交互地图。[Chart](https://trmnl.com/framework/docs/3.3/chart)、[Map](https://trmnl.com/framework/docs/3.3/map)

**分析：**组件的边界与用途很集中。本次查阅目录未发现足以认定其具备完整表单、焦点管理、复杂编辑器和触控交互体系的证据；不应因其叫 Framework 就默认这些能力存在。

## 5. 响应式：不只看宽度

**官方事实：**`md:`、`lg:` 等前缀依据设备携带的 size class，而不是测量浏览器 viewport 后自动选取像素断点。方向与位深还可以参与组合，例如 `md:portrait:2bit:label--filled`；各组件支持的维度不同。[Responsive](https://trmnl.com/framework/docs/3.3/responsive)

可将其理解为三个分开的决策：

| 决策 | 回答的问题 | 对设计的影响 |
| --- | --- | --- |
| 设备尺寸等级与方向 | 有多少可用空间？ | 列数、排列方向、可见信息 |
| 显示模式与调色板 | 能画出哪些颜色？ | 灰阶、抖动、线条和图表系列 |
| View / Mashup 配额 | 当前插件实际占多大？ | 全屏、半屏、象限及对应内容方案 |

**分析：**通用 Web 容器若只改变 CSS 宽度，不同步 TRMNL 的设备与视图环境，不能期待它像常见媒体查询系统一样自动完成全部适配。引入前必须先决定谁负责这些 class 和环境状态。

## 6. 灰阶、色彩与主题

### 6.1 “黑白风格”背后的绘制规则

**官方事实：**当前 Rendering Modes 说明将 1-bit 作为黑白抖动基线；2-bit 仍可在四种灰度之间抖动；4-bit 灰阶 tokens 使用实色。有限色模式把颜色映射到固定油墨集合，全彩模式直接绘制颜色值。因此不能简单写成“2-bit 起都不抖动”。[Rendering Modes](https://trmnl.com/framework/docs/3.3/rendering_modes)

颜色系统还有 `primary`、`success`、`error`、`warning` 这类语义角色，供内容表达意图；设备能力决定它们最终如何显示。[Colors](https://trmnl.com/framework/docs/3.3/colors)

**分析：**品牌色、业务语义和实际像素是不同层。跨设备系统可以借鉴这一点：先写“警告”，再由主题和设备决定其颜色、纹理或其他呈现。重要状态仍应配文字/形状，不能认为色彩退化后语义自然保留。

### 6.2 主题有受控边界

**官方事实：**主题以额外 stylesheet 与 `screen--theme-<id>` 启用，已提供 Black and Yellow、Dark、White and Red。主题接管配色后，普通 `screen--dark-mode` 默认不再改变其效果，除非主题自行定义组合规则。[Themes](https://trmnl.com/framework/docs/3.3/themes)

需要注意一处官方文档不一致：Themes 概述仍将主题描述为只改变颜色；更具体的 3.3 Authoring / Slots 页面已经允许通过 factors 调整留白、圆角、Title Bar 和 Progress 的结构比例，并有矢量字重偏移、文本大小写与字距接口。[Authoring Themes](https://trmnl.com/framework/docs/3.3/theme_authoring)、[Theme Slots](https://trmnl.com/framework/docs/3.3/theme_slots)

**源码确认：**本次源码快照确有 `layout-factors`、`font-weight-shift`、`text-modifiers`、`spacing-slots` mixins。本文因此采用“受约束的主题能力”，不采用“主题绝不改变布局”的绝对表述。[主题源码](https://github.com/usetrmnl/trmnl-framework/blob/8f2703e66899ef733a8a62e5c90516c4873e48ea/app/assets/stylesheets/framework/mixins/_theme-slots.scss)

**分析：**可借鉴的是所有权：主题可以改变被允许的默认表现，设备、字体度量和用户缩放仍有自己的边界。直接覆盖任意内部 CSS 变量会破坏这种分工。

### 6.3 DOM 与图表共享绘制结果

`TRMNLPaint` 向 JavaScript 提供 CSS 当前计算后的颜色、边框和排版结果，覆盖当前设备与主题；Canvas、SVG、图表等可以使用它，而不必维护另一张颜色映射表。[Paint API](https://trmnl.com/framework/docs/3.3/paint_api)

**分析：**这是比某款配色更值得迁移的设计。若一个产品既有 HTML 控件，也有自绘图形，应该明确共同的样式事实来源，防止两边的暗色、状态色和线条粗细逐渐偏离。

## 7. Runtime：内容适配是设计系统的一部分

**官方事实：**Framework Runtime 测量当前屏幕并执行适配，包括图片准备、数值格式化与 fitting、间隙调整、溢出处理等。动态注入内容后可调用 `terminalize()`；截图服务可等待 `TRMNL_PLUGINS_READY`。[Framework Runtime](https://trmnl.com/framework/docs/3.3/framework_runtime)

| 机制 | 解决的设计问题 | 必须保留的产品判断 |
| --- | --- | --- |
| 数字格式化 / Fit Value | 长数字超出原有空间 | 金额、单位、精度何时允许缩写 |
| Overflow / Table Overflow | 列表、表格超过一屏预算 | 哪些条目可以隐藏，是否提示剩余数量 |
| Clamp / Content Limiter | 长文本占满局部区域 | 截断后是否仍能理解关键信息 |
| Pixel Perfect | 像素字体与容器的亚像素错位 | 只在适用的字体、尺寸和渲染模式中启用 |

各机制入口见 [Runtime 目录](https://trmnl.com/framework/docs/3.3)、[Overflow](https://trmnl.com/framework/docs/3.3/overflow)、[Pixel Perfect](https://trmnl.com/framework/docs/3.3/pixel_perfect)。

Overflow 默认不显示末尾隐藏数量，需要显式启用 `data-overflow-counter="true"`。这意味着“画面没有溢出”不证明“内容都已显示”。[Overflow](https://trmnl.com/framework/docs/3.3/overflow)

Runtime 的 stats 事件可报告耗时和错误；某个 engine 失败后，其余步骤仍会执行，ready 也可能变为 true。因此验收应同时看最终画面、遗漏内容和错误信息，不能只检查 ready 标志。[Framework Runtime](https://trmnl.com/framework/docs/3.3/framework_runtime)

**分析：**自动适配解决几何约束，不替产品决定信息的重要性。它适合展示内容；若用于可编辑数据或关键状态，自动隐藏和缩写必须另外定义规则。

## 8. 技术栈、分发与接入成本

### 8.1 区分框架资源与文档站

**官方事实：**框架主要由 Sass 编译后的 CSS 和 JavaScript Runtime 构成。可以加载官方静态发布包，也可以从源码构建；文档与开发环境位于一个无数据库的 Rails 应用中。[Sass API](https://trmnl.com/framework/docs/3.3/sass_api)、[Open Source](https://trmnl.com/framework/docs/3.3/open_source)

**源码确认：**`package.json` 的 `private: true`、描述和 scripts 表明它承担构建与 Playwright 验证，不能据此虚构 `npm install` 即可接入的 React 组件 API。Gemfile 将文档站 Tailwind 工具列入开发/测试依赖，不能把文档站样式等同于电子纸框架实现。[package.json](https://github.com/usetrmnl/trmnl-framework/blob/8f2703e66899ef733a8a62e5c90516c4873e48ea/package.json)、[Gemfile](https://github.com/usetrmnl/trmnl-framework/blob/8f2703e66899ef733a8a62e5c90516c4873e48ea/Gemfile)

**分析：**在已有 Web 项目中展示一个 TRMNL 屏幕，不必先迁移后端到 Rails。真正的接入工作主要是资源管理、规定的 DOM 结构、设备配置、字体、Runtime 生命周期与宿主样式共存。

### 8.2 有具体依据的成本

3.3.2 发行页列出的大小如下；这是官方资源大小，不是本次网络性能实测，也不含字体及额外图表/地图库。[Releases](https://trmnl.com/framework/releases)

| 资源 | 未压缩大小 | Brotli 资源大小 |
| --- | --- | --- |
| `plugins.min.css` | 14.7 MB | 229.7 KB |
| `plugins.min.js` | 108.6 KB | 27.2 KB |

**分析：**传输可压缩，并不等于 CSS 解析与内存成本消失。全量资源是否适合交互应用，需要实测；不要因名称中有 `min` 就当作很轻的基础样式包。

Sass 提供 `tn--*` cascade layers 和公开 mixins；内部 paint 变量不是稳定扩展接口。自建 stack 可使用发布资源，不必维护源码分支。[Sass API](https://trmnl.com/framework/docs/3.3/sass_api)

建议的接入层次：

| 目标 | 建议路径 | 成本判断 |
| --- | --- | --- |
| 研究视觉与信息层级 | 仿照规则制作一页自有内容样稿 | 低，不需要接入框架 |
| 制作 TRMNL 插件 | 使用平台结构与版本对应的资源 | 中，重点在数据和各 View 模板 |
| 自建静态屏幕渲染 | 锁定发布包，管理字体和截图就绪 | 中，需要拥有渲染环境 |
| 改造完整交互产品 | 先做隔离实验，评估生命周期与控件缺口 | 高，尚无可行性结论 |

以上是范围判断，不是工期估算。本次没有安装或运行上游测试，也没有测量 LMDJ 的集成性能。

### 8.3 许可不是单一 MIT 标签

| 资产 | 本次核验的许可/边界 | 接入时的处理 |
| --- | --- | --- |
| 框架自有代码 | MIT | 随分发保留相应声明 |
| TRMNL / Inter / Nico 字体 | SIL OFL 1.1 | 保留对应字体版权与许可文件 |
| BlockKie | CC BY 3.0 | 单独核对署名与修改说明 |
| Highcharts | 商业库；框架只提供适配器 | 自建 stack 不能推断继承 TRMNL 的授权 |
| MapLibre GL JS | BSD 3-Clause | 保留其 notice；地图数据另有归属和条件 |
| 示例品牌 Logo | 不在框架 MIT 授权内 | 不作为可自由复用的自有品牌资产 |

依据：[LICENSE](https://github.com/usetrmnl/trmnl-framework/blob/8f2703e66899ef733a8a62e5c90516c4873e48ea/LICENSE)、[THIRD_PARTY_NOTICES](https://github.com/usetrmnl/trmnl-framework/blob/8f2703e66899ef733a8a62e5c90516c4873e48ea/THIRD_PARTY_NOTICES.md)、[Chart](https://trmnl.com/framework/docs/3.3/chart)。表格记录项目自身声明，不替具体分发场景作法律结论。

## 9. 对 LMDJ 的有限启发

这里只讨论研究可以启发的界面方法；未审核 LMDJ 当前界面，也不指定替换现有设计系统。

| 可借鉴方向 | 可能适用的展示内容 | 不宜直接照搬的部分 |
| --- | --- | --- |
| 主读数与辅助信息分层 | Tempo、时长、当前 Pattern 的摘要 | 同一屏所有值都放大 |
| 无彩色也能理解状态 | 选中、播放、静音等状态的冗余表达 | 只依赖灰阶或点阵区别状态 |
| 小空间独立取舍 | 紧凑状态栏、分享图、预览卡 | 自动隐藏用户正在编辑的内容 |
| CSS 与自绘区域共享 tokens | DOM 控件和自绘可视化的一致性 | 在高频音频/渲染路径中反复读取 DOM 样式 |
| 设备能力与内容数据分离 | 让同一摘要用于不同展示环境 | 把显示主题或设备选择写入作者数据 |

**研究判断：**最有价值的下一步是拿一个真实内容样例验证层级和密度；现阶段没有理由因喜欢其外观，就引入整套 Runtime 或变更产品架构。

## 10. 尚未验证，以及下一步怎么验证

| 问题 | 本次状态 | 最小验证动作与通过标准 |
| --- | --- | --- |
| 中文与混合文字 | 未逐字检查字体覆盖或 fallback | 用中文标题、中英混排、标点、负数与长单位做样稿；无缺字、错行或意外截断 |
| 真机清晰度 | 未测试实体面板 | 在目标面板显示相同图；小字、点阵和相邻曲线能在目标距离辨认 |
| 主题/设备组合 | 仅浏览默认示例 | 固定一份数据，比较灰阶、有限色、暗色与不同 View；关键语义始终保留 |
| 数据异常与内容裁剪 | 未注入极值 | 长标题、零/空值、超大值和长列表逐项验证；隐藏信息有明确规则 |
| 宿主框架共存 | 未接入 LMDJ | 隔离页反复更新、挂载/卸载；不重复包装 DOM、不遗留监听或产生 layout 错误 |
| 性能 | 仅核对资源大小 | 记录 CSS 解析、首屏与 `terminalize` 耗时；是否达标由目标产品预算决定 |
| 可访问性 | 未做键盘、读屏或缩放测试 | 若用于交互 Web，另测语义、焦点、状态宣告和缩放；不能由截图外观推定 |

优先顺序建议：先做一个“主值 + 次级状态 + 小列表”的中文样稿，分别排成完整与紧凑两版；确认取舍合理后，再决定要不要使用 TRMNL 的代码。只有目标明确为电子纸时，才把面板渲染和截图流水线作为下一轮研究重点。

## 11. Version Management

Version impact: none。本文只记录外部设计系统研究，不修改 LMDJ Product、Module、Host、Provider 或 Contract 的实现与版本。

Documentation impact: none。本文是独立研究记录，不改变当前架构、产品行为、门户页面或由 active manifests 投影的事实，因此无门户路由更新或版本快照需求。
