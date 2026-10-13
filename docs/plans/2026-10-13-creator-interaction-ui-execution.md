# Creator Interaction UI 长期执行计划

执行清单与证据索引：[#2112](https://github.com/endaye/lmdj/issues/2112)。
本计划执行完整 35 屏、U01–U12、F01–F08、B01 和最终候选验收，不以某个
UI 里程碑替代 Goal 完成。初始基线为 `9fb83ce0f70de1bc9114711bf9e854dfa6bb7081`。

## 已复核前提

- 主干已有四区、主要 Sample／Sequence／Perform 流程及精确数值编辑。
  #2112 的逐屏矩阵是差距索引；每项开工按 issue-done 刷新实际源码和在途 PR。
- Project 单列、↑／↓ 相邻、普通 ←／→ 暂不分配和显式 Open 已由 U04
  PR #2120 合入 `50ecc7107a3347878e1d5aa7f72b031d7d58eb98`；不得重复实现。
  [本日决定](../prd/decisions/2026-10-13-creator-interaction-ui-baseline.md)仍为交互依据。
- Figma 控件组件为 32，说明板仍为 36／44；同一决定已选择 32 可见面／
  至少 44 命中区。后续 owner 已批准小屏自适应布局和外边距，宽屏继续对齐图稿；
  U01 必须测量实际至少 44 CSS px、裁剪与邻接目标，而非只断言 CSS 文本。
- owner 已批准新五色在 Pad、Sequence 和颜色选择器同步更新，已有稳定索引不变。
  U02b 先刷新颜色来源、现有覆盖和 S6 所有权，不复制调色板或重写 Truth。
- B01 当前项取消排队入口已由 PR #2115 合入
  `544efcf159d980dd65f4ecca428df43e67541756`；真实 audio-claimed 结果仍由
  transport 投影决定，UI 不推断取消已经生效。
- ASSIGN、独立 Filter 和 count-in 已有其他 owner 的在途工作；不得重写或
  根据分支、Issue 标记推断验收通过。当前大运行与共享文件需先协调。

## 分工与顺序

| 波次 | Task／负责人 | 边界与完成证据 |
| --- | --- | --- |
| 0 | D0／主协调者 | 记录 owner 决定、保持当前／未来事实区分，Portal 机械检查与独立审查 |
| 1 | U01／control_kit agent | 公共控件与字体；styles.css、专属布局测试、Creator portal 与独立计划；禁止改 App 和业务 controller |
| 1 | B01／groove_cancel agent | touch_kit 的当前项取消入口、Sequence tests／journey、交互 portal 与独立计划；不改样式、Host 或 engine |
| 1 | F 依赖核验／capability_audit agent | 只读核对 F01–F08 的主干、在途 owner、真实运行和可续接边界；不接管现有 worker |
| 2 | U02–U04／主协调者分派 | 以 U01 和 D0 为基础，按 rail／Pad、overview、Project 分原子 Task；共享 CSS／App／Portal 明确单一 owner |
| 3 | U05–U12／逐项分派 | Sample／Perform 顺接原在途能力；其余页面和状态保留全部原流程，按具体文件判定可并行性 |
| 4 | F01–F08／原 owner 优先 | 分别保留 ASSIGN、Filter→live gate、meter、S6→S7、S3、S5、BPM 的真实依赖及原验收 |
| 5 | 最终候选／主协调者 | 35 屏完整状态对照、适用录放／重开／恢复、浏览器与真实设备证据；逐项 PASS／FAIL／UNRUN／UNKNOWN |

每个实施 Task 在编辑前声明精确文件、最低层检查和缺陷 oracle，一 Task 一
Conventional Commit。各 agent 使用独立 worktree；共享文件、重型测试和
合并由主协调者排队。子代理只有当前 Task 的权限，不能代写 owner review
attestation、跳过保护、释放其他工作或自行发布。

Task 交付含 commit、push、PR、当前头独立审查及受保护 squash merge。
验证失败先修根因，不缩减原 journey、不降低阈值、不重试到绿。未执行的
完整候选检查和真实设备验收仍为债务。release、部署和资源清理另行授权。

## D0 首轮 Task（已交付）

Declared files:

- `docs/prd/decisions/2026-10-13-creator-interaction-ui-baseline.md`
- `docs/plans/2026-10-13-creator-interaction-ui-execution.md`
- `apps/docs-site/docs/platform/input.mdx`
- `.agents/pitfalls/task-branch-upstream-tracks-main.md`

最低层检查：手动对照 owner 两项回答和当前 Project 导航源码；
`scripts/docs-site.sh check` 验证门户、链接、类型、构建及保留快照的机械
一致性；新文件运行 `python3 tests/build/ci_change_scope_test.py`；提交前
`git diff --cached --check` 和 declared-file 检查。没有新增产品 gate。
本 Task 不运行音频／Creator 产品验收，也不把 Portal PASS 当作产品已实现。

## D0 补充 Task：小屏与色板决定

主协调者使用独立 `docs/creator-ui-responsive-palette-decisions` worktree，
基线为 Sound Sets 已合入的 `613e23c26bb0ae54dccd75003b8858ac484b0faf`。
本轮两个原始回答已明确批准此前待决事项；代码尚未实现，历史通过不转为新
布局或新色板的通过。精确声明文件为：

- `docs/prd/decisions/2026-10-13-creator-interaction-ui-baseline.md`
- `docs/plans/2026-10-13-creator-interaction-ui-execution.md`
- `apps/docs-site/docs/platform/input.mdx`

最低层验证是逐项对照原始回答、已读 Figma 五色与既有稳定索引；完整
`scripts/docs-site.sh check` 覆盖当前门户和链接；提交前核对三文件和
`git diff --cached --check`。无新文件、新产品测试或新 gate。独立审查后按
既有授权提交、推送、PR 与受保护合并；实现和设备验收留给对应 Task。
本补充没有新增过程陷阱，不改首轮已记录的 pitfall 历史。

## Version Management

Version impact: none — D0 只记录批准与执行责任，不更改身份或产品代码。
后续 Task 分别声明 Creator／Module／Contract 影响，团队候选身份和永久
Portal snapshot 按正式版本流程结算，不在这里预填版本号。

## Documentation Impact

Documentation impact: required
Affected portal pages: /platform/input/

## Pitfall Impact

Pitfall impact: bumped `.agents/pitfalls/task-branch-upstream-tracks-main.md` —
D0 首轮协调者建立工作树时遗漏 `--no-track`，Task 分支继承了 `origin/main` upstream。
当时的 issue-done 检查在任何 push 前捕获此问题，已解除该首轮 Task 分支的错误
upstream；保留已吸收的检查机制。后续创建必须使用 `--no-track` 并立即回读。
没有向 main 直接提交或推送。继续执行 source-premise、完整 journey、worktree
cwd 与快照规则。
