# 已确认：被拒绝的音频激活是非破坏 no-op，Activate audio 只在 Runtime 可接受手势时可用

- 日期：2026-08-24
- 结论：回答 GitHub Issue
  [#178](https://github.com/endaye/lmdj/issues/178) 的两个产品行为问题。
  1. 一次被拒绝或失败的音频激活是非破坏 no-op：表面回到尝试之前的
     audio phase；`"Audio inactive"` 不再作为激活被拒绝的结果进入，它只
     表示初始/项目刚打开后尚未激活的状态。若激活尝试期间 Runtime 已经
     发布了新的 Host 状态，以该发布为准，不回写。
  2. `Activate audio` 在 Runtime 不可能接受手势时保持禁用：输入控制器
     已卸载（handler 缺失），或 Host 未停在 `audio-suspended`。表面永远不
     提供一个注定被拒绝的动作。
- 原因：旧行为把被拒绝的激活显示为 `"Audio inactive"`，而
  `creator_state.ts` 的 `canApply` 只接受从 `suspended` 进入
  `recovering`，进入 `inactive` 后该恢复周期内没有任何 Runtime 发布能
  把表面带回 `recovering`，表面被永久楔死；同时按钮的 `disabled` 只看
  `selectCanActivateAudio`，在 handler 已卸载或 Host 不在
  `audio-suspended` 时仍然可用，点击注定被拒绝并触发楔死。
- 影响：`apps/creator-web/src/app.tsx` 的 `activateAudio` 在 plain 拒绝
  （无 `error_code`）与不可信手势（`TypeError`）时恢复尝试前 phase，且仅
  在当前 phase 仍为 `activating` 时回写；`status_bar.tsx` 的 Activate
  按钮在 handler 缺失或 `audioActivationReady === false`（Host 未停在
  `audio-suspended`）时禁用；控制器重建后通过新增 state 触发重渲染，
  保证禁用窗口会结束。回归测试见
  `apps/creator-web/test/audio_lifecycle.test.tsx`（拒绝不楔死恢复周期、
  按钮仅在 Host 停在 `audio-suspended` 时可用）与
  `apps/creator-web/test/workspace_shell.test.tsx`（无 session 时按钮禁用
  且不进入 Tab 序）。本决策解决 Issue #178，无对应
  `docs/prd/questions/` 问题文件需要删除。
