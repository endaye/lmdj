# 已确认：Build Manifest 改为与归档并列的 detached 资产，不再内嵌进 ZIP

- 日期：2026-08-24
- 结论：`build-manifest.json` 从 Core 归档内部移出，作为并列资产
  `<package-name>.build-manifest.json` 与 `<package-name>.zip`、
  `<package-name>.zip.sha256`、`<package-name>.zip.sha256.asc` 一起发布。
  Manifest 的 Contract 与字段不变——`lmdj.build-manifest.v1` 仍含
  `build_time` 与 `platform`，满足 version-management.md §4；改变的只是
  位置，不是形状，因此 Contract SemVer 不变。detached Manifest 进入
  Release 的精确资产清单，与其他资产一样被 release plan 的逐资产 sha256
  绑定、参与 audit 重算。归档内容自此全部来自源码与工具链派生物，
  `create_zip()` 已固定的时间戳、排序与文件模式真正生效，同一源码在同一
  工具链下重复打包应字节一致；“下载方（或 CI）重建并比对”从此在原理上
  成立，后续可以为 Core 包增加与 Web Host 一致的 two-clean-build 门禁
  （是否增加由实现 Task 决定，本决策不强制）。
- 原因：这是两个都正确的要求装进了同一个容器，而不是实现缺陷。§4 要求
  Manifest 记录构建时间与构建平台；可复现性要求同一源码产出同一归档字节。
  内嵌含 `build_time` 的 Manifest 使两者永远无法同时成立。三个选项中，
  detached 发布是唯一让两者同时成立且不引入新歧义的方案：剔除归档内可变
  字段并保留 detached 全量副本会让同一 Contract 存在两种 Manifest 形状，
  副本之间有发散与相互矛盾的风险；接受不可复现并放弃“重建并比对”，放弃
  的是项目在所有 Web 产物上已经坚持（two-clean-build 字节一致门禁）、且
  在首个对外分发前最有价值的性质。detached 还顺带加强了供应链断言：今天
  Manifest 在归档内，“能改归档的人也能改 Manifest”，逐文件 sha256 不是
  out-of-band 信号；移出后它本身成为可被 release plan 绑定、可被消费者
  独立核验的包外证明。
- 影响：已发布产物的形态改变——每个归档的资产集在 ZIP、校验和、签名之外
  增加一个并列 Manifest；时限不变，仍须在首个对外分发（`dev` 及以上
  Channel）之前完成。实现是机器任务 A3
  （`docs/quality/2026-08-17-machine-task-todo.md`），需要自己的实施计划与
  `## Version Management` 章节，预期触及 `scripts/package-core.py`、
  `tools/release/` 的资产清单（profiles/audit/prepare）、
  `packaging/core/README.md`、`tests/distribution/` 与 `tests/build/` 的
  相关测试，以及标准发行流水线设计文档中的资产清单示例。消费者在解包后
  仍可按 detached Manifest 的逐文件 sha256 校验包内每个文件。
- 解决的问题：
  [`../questions/build-manifest-embedding.md`](../questions/)（已按约定在
  本 Task 删除）；GitHub Issue
  [#211](https://github.com/endaye/lmdj/issues/211)。
