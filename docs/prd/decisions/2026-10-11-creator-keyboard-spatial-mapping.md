# 已确认：Creator 四排键盘对应四行 Pad

- 日期：2026-10-11
- 来源：owner 明确采用 #1960 的四排映射，并确认 Q 从当前 Bank 的 01 改为 09，
  MIDI note 36–51 与 Pad 身份保持。
- 结论：默认四排键盘映射已由 [PR #2058](https://github.com/endaye/lmdj/pull/2058)
  交付，#1960 已关闭；真实设备／键盘输入及听感验收未执行。
  [#2060](https://github.com/endaye/lmdj/issues/2060) 的 Ctrl／Cmd 隔离策略已于
  2026-10-12 由 owner 确认，并由 Creator Input Controller 实施。
- 原因：键盘从上到下的四排对应屏幕从上到下的四行 Pad，避免一排键拆成
  两行 Pad，以及上下空间关系倒置。

## 默认映射

每个 Bank 使用相同的局部 Pad 编号，键与 Pad 从左到右一一对应：

| 键盘行（从上到下） | 当前 Bank 的 Pad（从左到右） |
| --- | --- |
| 1 2 3 4 | 13 14 15 16 |
| Q W E R | 09 10 11 12 |
| A S D F | 05 06 07 08 |
| Z X C V | 01 02 03 04 |

Q 对应当前 Bank 的 09，Z 对应当前 Bank 的 01。此决定替代 #1913 为
旧默认键盘保留的 Q=01 选择；既有左下角 01 的 Pad 显示顺序保持。
仅改变默认键盘输入与对应键帽提示，不重排或迁移 Pad 身份、Asset 引用、
Pattern 引用或工程数据。MIDI note 36–51 的映射不变。

## 来源与交付边界

批准时的历史来源（不代表当前实现）：

Inspected revision: `a98ae01c4f033c78221fc961f6207c7fe5cabfd7`。

- `packages/web-runtime-platform/web/input_adapters.mjs::DEFAULT_KEYBOARD_MAPPING`
  仍是 Q–I → 01–08、A–K → 09–16；四排默认映射尚未实现。
- `apps/creator-web/src/components/pad_surface.tsx` 从同一个默认映射派生
  key code 与可见键帽；实现必须同时更新数字键的显示，避免出现 Digit1 字样。
- `PAD_MATRIX_ORDER` 已按 13–16／09–12／05–08／01–04 显示。
  Creator MIDI adapter 已使用 noteStart 36、slotStart 0、slotCount 16；
  本决定不修改这些编号与范围。

批准时，本记录只将 #1960 的「需要 owner 确认」处置为已批准、待实现。

2026-10-12，[PR #2058](https://github.com/endaye/lmdj/pull/2058) 已合并为
`b503688d637789569ea985a4af79cc1454a5facc`，交付四排默认映射、数字键帽、
相关测试／浏览器断言及 Portal 键盘表；#1960 已关闭，不再重复实现。
本次状态复查绑定 `origin/main` = `33364e8359c5c8ab6209e3f66b13ee66c0e748ef`，
该交付已在其 ancestry 中。源码与自动化交付不构成真实设备／键盘输入或
听感验收；这些验收未执行，仍须保留按下、释放、Bank 目标与可见键帽的边界。

## 修饰键策略（2026-10-12 已确认）

owner 明确确认 [#2060](https://github.com/endaye/lmdj/issues/2060) 的限定策略：
Creator 在 Pad 准入前忽略带 `ctrlKey` 或 `metaKey` 的映射按键 `keydown`，
包括同时按住 Alt／Shift 的组合，以保留应用及浏览器快捷键。抑制的按下不激活
音频、不选择或触发 Pad、不停止 armed Capture，也不发起空 Pad 采样／导入。
只带 Alt／Shift 而没有 Ctrl／Cmd 的按键保留现有行为；`keyup` 不受此过滤，
先前无修饰键开始的 Gate 演奏在按住 Ctrl／Cmd 后松手仍正常释放。

策略由 Creator Input Controller 的公开 `keyDown` 与 window 监听共用，
不改 shared adapter、四排 mapping、Undo／Redo、MIDI、Pointer 或 Project Truth。
源码／组件回归不构成实体键盘、浏览器原生快捷键或听感验收；这些验收未执行。
合并与交付状态以 #2060 关联 PR 的实际记录为准。
四排映射的历史批准本身不包含这项后续策略。
本决定不为 #1822 的其他页方向键或新 SHIFT 组合键分配行为。

## Version Management

Version impact: Creator Host bugfix — Ctrl／Cmd 准入修复产生 Host patch 版本债，
由后续独立 identity-only allocation cut 结算；本 Task 不修改 manifest、Contract、
Product Build 或 Assembly，不分配新构建、快照、tag、Release 或 Channel。

## Documentation Impact

Documentation impact: required
Affected portal pages: /platform/input/ /hosts/creator-interactions/ /hosts/creator-web/
Reason: Creator 修饰键准入及 Undo／Redo 共存的 source facts 随本 Task 同步；
不改变架构边界或图，也不分配永久版本快照。
