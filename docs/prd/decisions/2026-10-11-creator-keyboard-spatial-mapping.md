# 已确认：Creator 四排键盘对应四行 Pad

- 日期：2026-10-11
- 来源：owner 明确采用 #1960 的四排映射，并确认 Q 从当前 Bank 的 01 改为 09，
  MIDI note 36–51 与 Pad 身份保持。
- 结论：默认四排键盘映射已由 [PR #2058](https://github.com/endaye/lmdj/pull/2058)
  交付，#1960 已关闭；真实设备／键盘输入及听感验收未执行。
  修饰键冲突 [#2060](https://github.com/endaye/lmdj/issues/2060) 仍开放待 owner 决定。
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

修饰键与 Pad 输入的冲突见 [#2060](https://github.com/endaye/lmdj/issues/2060)：
Issue 仍开放，过滤哪些修饰键及由 shared adapter 还是 Creator 层处理仍待
owner 决定。四排键位批准与交付不批准该策略，也不表示冲突已修复。
本决定不为 #1822 的其他页方向键或新 SHIFT 组合键分配行为。

## Version Management

Version impact: none — 仅同步既有决定的交付状态，不修改 source、Contract、
manifest 或 Product Build，不分配或判定版本身份。

## Documentation Impact

Documentation impact: none — 当前 Architecture Portal 已描述交付后的四排映射
及 #2060 修饰键限制；本次只同步决定／问题状态，不改变 Portal 页面、
图、工具、投影身份或已记录的 source facts。
