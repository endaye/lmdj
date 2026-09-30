# Creator P0.1：会话内创作 Undo/Redo（#1659）

状态：实现已提交；完整验证与交付状态以本 Task 的 Pull Request 证据为准。语义依据为 [#1655 决策](../prd/decisions/2026-09-30-creator-undo-redo-semantics.md)。
本 Task 实现既有创作操作的统一历史、Core/Facade 操作与 Creator 控件；长按录音、Pad 管理和网格编辑的新交互由各自 Task 实现。

## 实施边界

1. Authoring Domain 提供带前值校验的类型化创作差分，覆盖 Pad、Asset、Pattern、Pattern Slot、Performance 和工程序列参数；只修改差分中的内容，revision 递增，工程身份与 Contract 不倒退。
2. Project I/O 在真实提交边界接入由 Facade 持有的会话历史。所有现有写入入口和 Pattern transport 的 Store 共享同一对象；重复命令不重复记账，发布前失败不移动栈，发布后未知结果先对账。Undo/Redo 也通过正常 journal/checkpoint/manifest 提交，重开可读恢复后的 Truth，但不恢复会话栈。
3. 会话按成功打开工程建立，关闭、替换或失去所有权失效。首版保留最多 100 个用户动作；只存类型化内容差分及 Artifact 引用，不复制音频。满栈淘汰最早动作；保留的 Undo/Redo 引用参与既有未引用素材清理，失去历史引用不越过其他持有者。
4. 现有 Sample 编辑器以预览加手势结束提交实现一次拖动一条历史；安装、采纳与声音导入本身为原子事务。Sequence 内部 flush 按实际录制段合并，Record-off、Stop 和真实目标切换封闭分组，不因重试产生新组。
5. Facade 暴露历史状态、Undo 与 Redo，包含预期 revision、命令身份、会话身份、动作名及禁用原因。未结算录音、待恢复事务和未知提交结果保持守卫。Web 平台更新投影并沿用既有 Runtime 发布路径；Creator 跨页面提供按钮，显示真实不可用原因，不保存工程快照。
6. 不实现选择性协作撤销、跨设备栈、历史持久化、物理 GC 或 AI 授权策略。未实现的后续操作不得在门户写成已支持。

## 声明文件与最低层验证

- Domain：`packages/authoring-domain/` 的差分头文件、实现、构建注册及 `tests/core/domain/` 的往返、冲突、原子性与内容覆盖测试。
- Project I/O：`packages/project-io/` 的历史组件、Store 编码／提交／清理接入、构建注册及 `tests/core/project_io/` 的提交故障、重试、资源保留与重开测试。
- Facade：`packages/application-facade/` 的会话、守卫、控制器共享历史与录制分组；`tests/core/facade/` 覆盖普通、失败、取消、恢复、外部变更及跨会话隔离。
- Web：`packages/web-runtime-platform/` 的控制协议、会话类型和序列化接口，`apps/creator-web/` 的统一控件与投影刷新，现有测试目录中的协议、组件与真实浏览器旅程。
- 文档及身份：本计划、受影响模块／Host 清单及依赖、Assembly 及 Runtime identity 生成物、当前门户页面和架构源图、Host package 身份、version/module graph/Host boundary 身份清单测试；身份变更按下节执行，不改历史决策。
- 流程经验：`.agents/pitfalls/web-proofs-share-destructive-build-root.md` 记录同一工作树 Web proof 的共享清理边界；不改变测试门禁。
- 覆盖率登记：根 `CMakeLists.txt` 将新增 Domain 与 Project I/O 测试登记到既有 coverage target inventory，保持完整收集与原有阈值。
- Web 测试夹具：`tests/platform/web/project_io/CMakeLists.txt` 启用栈越界检查，捕获固定栈预算内的内存覆盖；替换／重开及其他分发动作使用禁止内联的独立函数，历史步骤仅保留后续断言所需内容，避免优化编译把大型状态帧叠加到其他路径，保留所有故障点与远端断言。
- Web 验证诊断：`tests/platform/web/project_io/webkit_protocol_timeline{,_test}.mjs`、`scripts/web-toolchain-conformance.sh` 与 `.agents/pitfalls/playwright-retains-protocol-before-sidecar.md` 修复完整验证暴露的 runner 原始协议 stderr 无界保留；真实 runner 回归固定零保留、完整导航诊断与失败状态，不增加堆预算或减少浏览器案例。

每个测试固定一个缺陷；用户旅程每次转换之后立即断言。验证至少包含 A→B→Undo A→Redo B 的内容与递增 revision、Redo 分叉、重复请求、无变化、清空 Pad 保留事件、同一产物重做、Sequence 分组、录制／恢复守卫、保存与重开、所有权变化、素材保留及持久化故障。
运行相关 CTest unit/component、Web 平台与 Creator 单元测试、Creator/Web proof、文档检查和最终 lane 分类要求的验证；并发路径变更补充对应 stress/ASan 验证。真实设备听感与生命周期只记录实际执行结果，不以自动化替代。

## Version Management

新增向后兼容能力分配 Authoring Domain 4.2.0、Application Facade 6.3.0、Web Runtime Platform 5.4.0 与 Creator Host 4.6.0；Project I/O 新增旧 reader 无法识别的私有 journal 命令，按持久化兼容性边界分配 5.0.0。精确依赖消费者同步 PATCH。Project Truth 与便携 bundle schema 不加入历史栈。
本 Task 最初分配 1.0.68.0，避开并行 Task 已保留的 1.0.67.0。随后 main 的 #1700 正式启用 M2 / 2.0 四区工作流能力列车，因此整合 #1694 的 Project duplicate 后分配下一个未占用 Build 2.0.69.0；旧 1.0.68.0 快照完整保留在原候选提交 4478667c 中，并非 Release 或部署；本 PR 最终仅引入匹配合并树的 2.0.69.0 快照。版本及精确依赖从 manifests 推导，使用 `scripts/version.py lock` 生成 Assembly，同步 current 门户并按 `scripts/docs-site.sh version PRODUCT_BUILD canary` 冻结本次说明书。最终验证以 PR 的输入绑定证据为准。
版本与快照是独立验证边界；本任务不授权 tag、Release、Runtime 部署或 Channel 晋级。

## Documentation Impact

Documentation impact: required
Affected portal pages: /product/workflows/ /core/modules/authoring-domain/ /core/modules/project-io/ /core/modules/application-facade/ /core/modules/web-runtime-platform/ /hosts/creator-web/
Reason: 统一历史的所有权、持久化、资源保留与用户工作流从已决策进入实现；每个页面只声明其实际完成与验证部分。

## 交付

完成 Task-specific verification 后按 issue-done 提交、推送、创建 PR，取得当前 head 独立审查，处理所有意见后 guarded squash merge。保留其他 Task 与 #536；未完成验收不以关闭 Issue 掩盖。用户工作区原有暂存文件不纳入本 Task，清理与发布另行授权。
