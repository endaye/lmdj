# 已确认：Pad 类别提供默认色，用户可从五色调色板覆盖并恢复默认

- 日期：2026-10-07
- 解决的问题：[#1821](https://github.com/endaye/lmdj/issues/1821)。Owner 在讨论中确认采用方案 3。
- 补充：[Sequence 硬件界面修订](2026-10-04-sequence-hardware-ui-revision.md)结论第 3 项的颜色来源；其余结论不变。
- 视觉来源：Figma Desktop Final D02 的 Pad 矩阵（节点 88:1376）；五个类别色沿用该稿。

## 结论

1. **类别提供默认色，用户选择覆盖默认色。** 分离得到的 stem 或分配的 sample 在有类别时使用对应默认色；不再以 Pad Slot 编号轮换颜色。颜色覆盖不改变素材类别。
2. **调色板固定为五色。** 用户可以选择其中任意一色，不输入任意 RGB 或 hex 值。

   | 类别 | 默认色 |
   |---|---|
   | DRUMS（鼓） | `#F3B580` |
   | BASS（贝斯） | `#DFF779` |
   | MELODIC（旋律） | `#B49DE8` |
   | VOCAL（人声） | `#94D2DC` |
   | TEXTURE（纹理） | `#E6ED98` |

3. **手动覆盖属于 Pad 的 authoring state，保存进 Project Truth。** 保存的是稳定的调色板索引，不是任意颜色字符串。类别默认与显式覆盖必须能区分，不能仅保存最终显示色而丢失用户是否覆盖的事实。
4. **重新分离保留用户覆盖。** 没有覆盖时，显示色随类别默认色变化；用户可执行“恢复类别默认色”清除覆盖，之后重新跟随类别。
5. **同一 Pad 使用同一个有效颜色。** Pad 矩阵边框、Sequence 上屏轨道行与触控网格音符共享“用户覆盖优先，否则类别默认”的结果。
6. **选中状态使用白色边框与亮绿点。** BASS 的 `#DFF779` 与全局选中亮绿 `#DDF478` 接近，不能只靠颜色区分选中与类别。选中状态同时保留可访问的状态语义。

## 原因

- 类别默认色让分轨一眼可辨，用户覆盖允许按自己的编排组织 Pads。
- 固定五色沿用 D02 在深色面板上的视觉设计，避免任意颜色破坏可读性。
- 保留覆盖来源，才能在重新分离后尊重用户选择，并让恢复默认具有明确含义。

## 实施边界与待设计项

本 Task 只记录产品决策并更新依赖；没有修改 Project Contract、Core、Facade、Host 协议或 Creator 渲染。当前按 Slot 轮换颜色的实现仍存在。

- **独立 Contract/Core 计划先行。** 确定类别与可选颜色覆盖的字段、稳定索引映射、旧 Project 迁移、命令、Undo/Redo、保存重开与 Facade inspection projection；由 Core 维护 Truth，Host 仅使用 Facade。
- **未知或未分类素材不被自动当作 TEXTURE。** 空 Pad、无类别 sample、Provider 的不同 stem 标签如何映射，以及旧 Project 的默认值，留给该计划明确提出并评审；本决策不猜测这些默认规则。
- **重新分离的对应关系仍须设计。** 产品不变量是保留用户覆盖；输出如何对应既有 Pad、assign/replace/clear/move 的字段保留规则在 Contract/Core 计划中明确。
- **T7 后续实施。** 在 Contract/Core 与 Host projection 完成后，通过同一颜色解析结果更新矩阵、总览和网格，并提供五色选择及恢复默认。控件位置由实施设计确定。
- **验收路线。** 后续 Task 应验证类别默认 → 手动覆盖 → 重新分离仍保留 → 保存重开仍保留 → 恢复默认重新跟随类别，并在每一步读取 Truth 及三处显示结果；Undo/Redo 与旧 Project 迁移另有对应验证。这些是后续要求，本次未执行。

## Version Management

Version impact: none

Reason: 本次只有决策、计划与门户状态文档，不改变任何 active manifest 或 Contract。持久化颜色的后续实施需要独立的 Contract 兼容性评审与相应版本管理。

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/
Reason: Creator 的 Pad 配色规则已获批准，门户需明确记录 designed 状态与尚未实施的 Contract/Core 依赖。
