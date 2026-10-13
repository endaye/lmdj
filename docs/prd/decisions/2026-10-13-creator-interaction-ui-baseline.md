# 已确认：Interaction UI 使用单列工程列表和 32 可见面／44 最小命中区

- 日期：2026-10-13
- 关联：[#2112](https://github.com/endaye/lmdj/issues/2112) 的 D0、U01、U04。
- 设计目标：[Figma 04 · Interaction UI / 2026-10-12](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO?node-id=400-67)。2026-10-13 读取该页；这是可变设计来源，不是不可变交付凭证。
- 来源：owner 在长期 Goal 中分别选择「采用单列和上述新导航」与「32 可见面，至少 44 命中区」。
- 状态：行为和尺寸已批准；本决定不表示实现、浏览器或设备验收已经完成。

## Project 列表与方向导航

Project 使用单列工程卡片。普通 ↑／↓ 选择上一／下一工程，首尾停止；
普通 ←／→ 暂不分配。卡片与 ENC1 仍只改变选择，只有明确按 Open 才打开
工程。ENC2 保持列表滚动，ENC4 保持设备监听。

这替代 [2026-10-11 导航决定](2026-10-11-creator-navigation-and-live-mute-tails.md)
中 Project 的三列列表、↑／↓ 跨一行和普通 ←／→ 相邻选择规则。Sample、
Sequence、Perform 的规则不变。SHIFT + ←／→ 仍为全局 Undo／Redo，
Project SHIFT + ↑／↓ 仍不分配。导航不演奏、不打开工程、不写 Project Truth。

U04 同时更新三列导航实现、焦点顺序的 owning tests 和当前门户；不能只改
CSS 留下跨三项的方向键。0、1、多项、末项、长标题和滚动后的选择必须可见。

## 控件尺寸与可读性

新界面的普通触摸动作和硬件键使用 32 设计单位的可见面；交互命中区域至少
44，保留明确的 focus、selected、disabled 和 danger 状态。文字采用图稿的
IBM Plex Mono 9／13，圆角 6；更长文字可以扩大控件宽度，不截断重要操作含义。

这解决该页组件定义的 32 与 Four regions 说明板的「36 可见面／44 命中区」
冲突，后续以 32 可见面为准。实现必须把可见面和命中区域分开测量，命中区
不得被父级裁剪，也不得重叠后把邻近操作触发为另一动作。

在已有固定 880 × 592 控制台及缩放布局下，必须实测受支持视口的有效命中区
和输入落点。设计单位不自动等于屏幕 CSS px；若缩放和密度使最小命中区无法
同时成立，提交具体冲突与布局方案再决定，不通过缩小目标或省略控件达标。

## 保留的交互边界

- Capture、Import、Numeric 的外观可向右侧工作区对齐，原有模态、焦点限制、
  返回焦点、固定录入目标和允许的背景演奏输入仍由各自已批准流程决定。
- Sound Set 安装保留当前 Keep／Replace 的全局占用策略；单个示例槽不批准
  逐槽混合策略。浏览、试听、映射预览和安装仍是不同操作。
- 未在静态画板出现的 Loop、Provider、恢复、权限、离线、quota、owner lost
  和未知持久化结果分支仍需保留并验收。
- 主干已交付的 Numeric、键盘映射及导航不因图稿旧的 NOT IMPLEMENTED 文案
  被重复实现。功能状态按当前源码、实际合并和验证证据分别记录。

## Version Management

Version impact: none — 本 Task 只记录决定与执行边界，不更改 manifest、
Product Build、Contract 或 Runtime。U01／U04 实施分别声明实际版本影响。

## Documentation Impact

Documentation impact: required
Affected portal pages: /platform/input/

门户明确当前三列实现与下一步单列批准规则的差别；实施合入时更新当前事实。
