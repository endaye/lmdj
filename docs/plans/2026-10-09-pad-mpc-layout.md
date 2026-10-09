# Creator 4×4 Pad 的 MPC 式显示排列（#1911）

## Task premises

Base: `502932e345b621abc5533431e61adf0d0253a189`，2026-10-09 fetch 的
`origin/main`。Issue #1911 尚未实施；同题未发现独立后继交付。
`selectVisiblePads` 构造连续槽位，`PadSurface` 直接遍历并放入四列 CSS
Grid；Sound Set preview 也直接遍历 `selectPadPlan`。事件已传稳定槽位。
因此剩余工作是空间显示遍历，而不是槽位身份或音频行为改造。

用户授权实现、PR 与合并。采用 Issue 建议的首版边界：快捷键及 MIDI
映射保留；Sequence 的 A01–D16 导航沿用已确认决定。

## Scope and declared files

- `apps/creator-web/src/state/view_model.ts`：唯一的 16 格显示遍历顺序。
- `apps/creator-web/src/components/pad_surface.tsx`：DOM 按显示顺序生成，
  回调、状态与键帽仍来自原槽位。
- `apps/creator-web/src/components/soundset_surface.tsx`：同样的空间遍历。
- `apps/creator-web/test/pad_surface_keyboard.test.tsx`：各 Bank 的绝对地址
  顺序、重排后的原槽位回调与原键帽；已有空 Pad 键盘捕获测试按地址定位。
- `apps/creator-web/test/soundset_surface.test.tsx`：独立绝对顺序与安装目标。
- `apps/creator-web/test/workspace_shell.test.tsx`：保留逐地址键帽断言，
  更新现有 DOM 键帽顺序到新的空间排列。
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`：实际
  几何角落、命中目标、Tab 顺序、Q 提示，覆盖 A–D Bank。
- `tests/platform/web/creator/creator_web_accessibility.spec.mjs`：保留完整
  实体控制区 Tab 旅程，将首个 Pad 的预期同步到屏幕左上角 A13。
- `docs/design/2026-09-29-creator-user-workflow-guide.md`：用户的排列说明。
- `apps/docs-site/docs/hosts/creator-web.mdx`：当前行为及设备验收边界。
- 本计划。

只有空间矩阵重排；序列行、普通列表、Runtime Host、Project/Contract
和持久化编号均在本任务之外。不增加公开 API，不分配测试 Build。

## Verification

最低层：Creator 的 Pad、Sound Set、状态与输入组件测试。绝对顺序
oracle 独立于两个 consumer 共用的常量，防止共同错误导致 parity 假绿。
临时将共享顺序恢复为旧顺序，确认两个 consumer 的绝对断言各自失败，
恢复源码后重新运行。

浏览器：各 Bank 切换后检查所有地址、四角几何与命中；D13 Tab 到
D14；D01 仍显示 Q。这证明空间排列与浏览器访问，不等于真实触摸或 MIDI。

完整现有 `scripts/creator-web.sh proof` 覆盖指针/键盘/MIDI、采样/录音、
Pattern 录放、保存重开和 Sound Set 的既有旅程；逐项保留其结果与失败，
不以布局测试代替持久化测试。运行 `scripts/docs-site.sh check`，新文件
stage 后运行 `python3 tests/build/ci_change_scope_test.py`。
在 committed head 上按分类运行每个 batch-only lane，并在 PR 记录 key。

人工边界：真实触控、物理 MIDI 与实际听音仍是 Issue 的设备验收缺口；
实现 PR 使用 Relates to #1911，保留 Issue，不能因模拟输入而勾选这些项。

## Version Management

Version impact: none — 本次是 Creator 内部视图遍历的调整，公开 Host
API/ABI、持久化语义与 Package 身份不变。未发布新 Package 或分配
Product Build；正式切版另按版本政策进行。

## Documentation Impact

Documentation impact: required
Affected portal pages: /hosts/creator-web/
Reason: 默认 Pad 空间排列和键盘位置改变，更新当前页与用户指南。

## Pitfall disposition

此任务的布局/槽位不变量由产品测试表达，不产生过程 ledger 条目。
Web proofs 在本 worktree 顺序执行；模拟输入与真实设备边界明确保留。
