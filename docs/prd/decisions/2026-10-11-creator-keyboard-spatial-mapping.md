# 已确认：Creator 四排键盘对应四行 Pad

- 日期：2026-10-11
- 来源：owner 明确采用 #1960 的四排映射，并确认 Q 从当前 Bank 的 01 改为 09，
  MIDI note 36–51 与 Pad 身份保持。
- 结论：默认键盘映射已批准；实现和验收仍待独立 Task。#1960 保持开放。
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

## 当前来源与交付边界

Inspected revision: `a98ae01c4f033c78221fc961f6207c7fe5cabfd7`。

- `packages/web-runtime-platform/web/input_adapters.mjs::DEFAULT_KEYBOARD_MAPPING`
  仍是 Q–I → 01–08、A–K → 09–16；四排默认映射尚未实现。
- `apps/creator-web/src/components/pad_surface.tsx` 从同一个默认映射派生
  key code 与可见键帽；实现必须同时更新数字键的显示，避免出现 Digit1 字样。
- `PAD_MATRIX_ORDER` 已按 13–16／09–12／05–08／01–04 显示。
  Creator MIDI adapter 已使用 noteStart 36、slotStart 0、slotCount 16；
  本决定不修改这些编号与范围。

本记录将 #1960 的「需要 owner 确认」处置为已批准、待实现，不构成键盘源码、
Portal 键盘表、现有浏览器断言或真实键盘输入验收的交付。
独立实现 Task 开始前刷新实际 producer／consumer、相关测试与 Portal 来源，
声明精确文件及最低层验证；按四排映射核对按下、释放、Bank 目标与可见键帽。
本决定不为 #1822 的其他页方向键或新 SHIFT 组合键分配行为。

## Version Management

Version impact: none — 仅记录产品决定，不修改 source、Contract、manifest 或
Product Build；对应实现 Task 负责版本结算。

## Documentation Impact

Documentation impact: none — 本记录描述已批准的未来行为，当前 Architecture
Portal 实现 source facts 未变。默认映射实现须同时更新实际受影响 Portal 页面。
