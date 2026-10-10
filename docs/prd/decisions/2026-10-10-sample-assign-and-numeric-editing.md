# 已确认：Sample 的已有素材 Assign 与精确数值编辑

- 日期：2026-10-10
- 来源：owner 批准 D03 的两个推荐方案：当前工程已有 Asset 加明确 A01–D16
  目标；精确输入立即试听、Apply／Enter 一次保存／Undo。
- 解决的问题：[Creator Desktop Final 后续计划](../../plans/2026-10-09-creator-desktop-final-followup.md)
  D4 的 Assign 对象／目标和参数细调确认方式。#1822 的其他页方向键、D04
  MASTER／独立滤波／Mute／Solo／meter 仍未由本决定解决。

## Assign

1. ASSIGN 浏览并选择**当前工程已经保留的 Asset**，明确选择目标 A01–D16。
   新文件导入与 Candidate 采用继续使用现有独立入口。
2. Assign 增加目标 Pad 对同一不可变素材的引用，不移动来源，不删除素材，
   不改变来源 Pad。目标已分配素材时先确认替换；取消不改变 Project Truth。
3. 实际保存通过 Facade authoring admission、command identity 与 expected
   revision 执行；完成后刷新目标 Pad／工程与 Runtime。错误和冲突保留真实
   结果，不把失败或未知提交显示成已分配，也不以旧视图猜测提交成功。
4. 用户确认的是素材来源、目标和替换／取消行为；目标 playback 的重置或
   保留规则须在实施前核对既有 Assign Contract，不能凭文件导入的文案推导
   另一种行为。

## 精确数值编辑

1. 点击 Volume、Pitch、Pan、Attack、Release、Tone 数值打开精确输入。
   合法输入立即试听；Apply 或 Enter 确认一次 authoring 保存，形成一次 Undo。
   回到原值不保存；非法或超出既有范围的输入不能提交。
2. Esc、切目标或离开编辑上下文取消尚未提交的 draft，恢复已保存参数；
   同样保留已发出保存的真实结果，不能把它当成可撤回的本地试听。
3. 采用现有单位、精度和边界：Volume dB、Pitch st、Pan 左／中／右的数值、
   Attack／Release ms、Tone 的现有双向值。Start／End 保留已有 frame 精度输入。
   本决定不增加独立 LP／HP／BP 或 resonance。
4. 旋钮继续采用已批准的 400 ms 合并保存与 SHIFT 细调；现有 touch slider
   继续 release／blur 提交、Esc／pointercancel 取消。新增精确输入不改写这些
   已有手势语义。

## 原因

已有文件导入和 Candidate 采用入口无需重复；Assign 补全同一工程内素材
复用，并让目标与覆盖行为可见。显式确认使用户可以完整输入一个数值后才
保存，避免停顿 400 ms 把尚未输入完整的数字提交。

## 能力与实施边界

检查基线：`e9dae833d1c609bb203030a62053dee39b9d8b61`。
Facade `project.inspect` 已返回 `assets`；Creator `project_actions.ts::projectView`
目前只保留素材数量，须提供真实目录给新的选择流程，Host 不解析 bundle。
Host 的完整注册表已有 `pad.assign`，实际 handler 通过 Facade 持久化引用；
Web Session 公开对象与 Creator 尚无完整 Assign journey。

`sample.update_pad`、`sample.preview.set/clear` 和当前 slider 已实现参数试听与
保存；`ValueSlider` 的数值 output 不是输入框。`WaveformEditor` 的 Start／End
精确输入已有交付，不重复实现。后续独立 Task 在 fresh main 上锁定声明文件，
复用以上能力，验证正常、替换拒绝、取消、冲突／失败、Undo／Redo 和 reopen。
本 Task 只记录决定，不宣称新增入口或人工试听已经完成。

## 影响

Version impact: none — 此 Task 只记录决定与实施边界，无 source、Contract、
manifest 或 Product Build 变更；实际实现债务由实施 Task 和父计划 V1 结算。

Documentation impact: none — 此 Task 不修改当前 Architecture Portal 页面、
source facts 或 diagrams；实现时更新相关 Portal routes。
