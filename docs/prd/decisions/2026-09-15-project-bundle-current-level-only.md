# 已确认：开发期 Project Bundle 只支持 writer 当前级别

- 日期：2026-09-15。
- 关联：GitHub issue #897；本条确认其调研结论的处置方向。

## 结论

1. 开发期 Project Bundle 只支持 writer 当前 Project Contract 级别（现为
   `lmdj.project.v5`），不做旧版本兼容。`lmdj.project-bundle.v1` 的
   `project_contract` 枚举收窄为只剩 writer 当前级别，容器版本与
   Contract 版本同步升到 `2.0.0`；旧容器版本与旧 Project 级别在边界
   一律拒绝。
2. `lmdj.project.v1`–`v4` 的 schema 定义退役：[`contracts/project/`](../../../contracts/project/)
   只保留当前级别与 Bundle envelope。旧 checkpoint 仍可由 Host 直接
   载入（loader 手写结构校验并完成确定性迁移），但不能打包或导入为
   Bundle。
3. 遇到不兼容就修复到支持当前级别：不为旧 envelope 或旧级别加兼容
    shim。实施落点包括
   [`packages/project-io/src/project_bundle_transfer.cpp`](../../../packages/project-io/src/project_bundle_transfer.cpp)
   的 parse_index allowlist、Python 打包工具与浏览器 reader，三处共享
   同一份当前级别事实。

## 原因

#897 的调研结论：

- v1/v2 只有 Stage 8 之前的开发 Build 写过，不存在需要兼容的真实
  分发面；
- Bundle 的枚举广告与各 reader 的实现长期不一致（#784、#900 都是
  枚举停在旧级别而 writer 已前移导致的断链），广告一个并不真实
  支持的级别比拒绝它更有害；
- 统一为只命名 writer 当前级别，消除了 schema 枚举、C++ reader、
  Python 工具与浏览器 reader 四份枚举拷贝之间的同步成本——下一次
  级别移动只改一处事实，绑定测试立即变红而不是静默漂移。

## 影响

- 声明旧容器（`1.0.0`–`1.3.0`）或旧级别（`lmdj.project.v1`–`v4`）
  的 Bundle 从"可读"变为拒绝；导入侧不再把枚举可接受性误当作旧版本
  迁移证据。
- 退役级别保留迁移读取：Project I/O 的 loader 继续按手写结构校验
  读取 v1–v4 checkpoint 并在首次持久化时晋升到当前级别。
- 下一次 Project Contract 级别移动是一次 Bundle Contract MAJOR：
  枚举、三处 reader allowlist 与绑定测试在同一切版中一起移动。
