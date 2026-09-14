# 一键发布开发收敛计划

日期：2026-09-14

状态：用户已要求按精简方向调整计划；实现和真实发版验收尚未完成。
本次仅更新计划与任务跟踪，不恢复暂停的开发 goal，不启动发布。

跟踪任务：[一键发版与部署 #1301](https://github.com/endaye/lmdj/issues/1301)。

## 目标与优先级

唯一交付目标：用户说一次“发版本”，完成固定 `web-hosts-dev` 范围的一键发版加部署，
包括 GitHub Release changelog 与 doc-site 的逐版本 changelog。
正常路径不逐步索要授权；失败、外部认证、必需审批或范围不明时明确停止。

本计划取代 R1/R2/R2b 及候选准备后续工作的碎片化推进顺序，不改写历史验收记录。
已经完成的实现按需复用，不重新开发；未提交的候选准备代码保留，不能整包视为已验收。
CI 可靠性项目 #1089、PR-Agent 迁移、Cloudflare 迁移与产品开发保持原范围，
不作为本计划默认扩写项，也不关闭它们尚未完成的缺陷或验收任务。

## 完整交付链：不删步骤

冻结请求与 main 输入 → 新 BUILD / source / immutable snapshot → 切版 PR、独立审查、
squash 与官方 witness → 固定实际 candidate SHA → 完整 16-suite 测试或复用有效同目标证据
→ reviewed intent 与冻结 changelog → remote audit → prepare / 双角色签名
→ 单一 immutable tag push → Draft / 六资产验证 → protected publication / verify-published
→ published ledger 与同源 doc-site changelog PR → Git-triggered 网站内容验证
→ Runtime 部署及验证 → Creator 部署及验证 → reviewed dev promotion
→ 回读 Release、双站、渠道、changelog 和 immutable snapshot 路由并汇报。

每次转换保留实际结果断言。发布、网站、两个部署、晋级分别报告；一个成功不替代另一个。
网站失败不得重复发布 Release；单 Host 失败不得晋级，也不擅自回滚另一个成功 Host。

## 实现收敛

- 一个用户入口：`scripts/release.sh run / status / resume`。这些是待接通的交付目标，
  不是本计划已实现的命令。
- 一个顺序总控：优先接通已有 `orchestration_driver.py`、journal 和稳定 release 接口，
  不再加一个总控来包住另一个总控。底层 verifier、签名、发布和部署 workflow 继续复用。
- 一份主要发布进度记录：保留 scope、执行前意图、真实对象/run ID 和证据引用。
  底层工具必要的原始日志与恢复记录保留；避免父子层重复保存整份回执作为多套业务真相。
  合并记录前先证明未知写结果不会重放、原始历史缺失仍停止、并发写仍被拒绝。
- 状态查询核对已有对象和证据，不默认再走材料生成、临时 index 与对象写入全路径。
  先检查真实调用成本，再缩小查询实现；不能只相信缓存、文件存在或 completed 标记。
  原始输入、内容、路径、模式、提交身份和授权验证必须等价保留。
- 删除确实未使用的 import；不为两行清理单开交付里程碑，也不以净减行数作为验收目标。
- 暂不做全仓库 audit、大规模删除、通用插件体系、多产品/多渠道框架或新增常驻服务。
  如已有执行载体能承担流程，直接使用；运行必须独立于聊天存活并支持原请求恢复。

`ponytail-review` 仅作限定 diff 的复杂度建议，不加入 required CI，不替代正确性审查，
不要求其他开发者安装，也不启用全局 hooks 或 ultra 模式。

## 三个交付里程碑

里程碑不是三个必须一次性提交的大 PR；每个实现 Task 仍是声明文件的一次可审查提交。
只按实际依赖拆 Task，不再为每个内部辅助层单独扩展计划。下列为候选文件范围；
实现前固定该 Task 的精确文件和最低层测试，新增范围须解释对完整入口的直接必要性。

| 里程碑 | 文件范围与复用点 | 最低层验证与完成标准 |
| --- | --- | --- |
| M1 可运行完整入口 | `scripts/release.sh`、`tools/release/cli.py`、`orchestration_driver.py`、`orchestration.py`；按需整合既有 `candidate_preparation.py` / `candidate_workspace.py` / `candidate_material.py`；对应 `tests/build/release_*_test.py`、`release_candidate_portal_journey.py`、必要 CMake 注册 | CLI 测试证明三命令实际连到同一总控；临时 Git / fake API / 测试 signer 从真实入口走完整交付链，各腿验证实际产物；中断恢复证明不重分配、不重签覆盖、不重复外部写。交付可复制命令，而非只有 helper 或协议桩。 |
| M2 真实执行环境就绪 | 复用现有 release policy、签名入口、publish 与两个 deploy workflows；只有确认缺少 exact request/run 关联时，才修改对应 workflow 与契约测试 | 先只读检查权限、配置、工具链；在适用授权下验证冷启动非交互双角色签名和恢复。测试凭据/平台条件不证明已发布。认证或保护问题如实阻塞，不另造状态框架绕过。 |
| M3 一次真实完整验收 | 既有切版/intent/发布记录/changelog/晋级生成器；实际生成的 Product、snapshot、ledger、Portal 页面和 `docs/release-evidence/` 文件 | 一次单独明确的发版请求覆盖完整序列；真实 exact-target CI、公开签名 Release、doc-site 内容、双站 HTTP/browser、dev 晋级与重启恢复逐腿验证并给链接。缺任一腿不得报告完成。 |

M1 只证明完整离线编排，不证明真实凭据、服务器或生产发布成功。
M2 不迁移私钥、不降低保护，不把本次计划更新当作新增外部配置或实际发版授权。
M3 的具体生成文件由冻结版本与官方工具决定，不预先猜测 Build、tag 或 revision。

## 验证与成本控制

- 开发循环运行与改动相关的最低层测试；集成时跑完整组合路径；提交前运行适用的
  Task 检查、路径归属与 current-head 独立审查。后续修复重跑受影响集合，不机械重跑所有检查。
- 保留断点恢复、未知结果、缺历史、撤销授权、对象漂移、网站未发布及部分部署失败验证。
  不降低 coverage floor、不放宽 timeout、不跳过测试、不缩小保守 lane selection。
- Portal 页面、生成器、身份或已文档化源码事实变化时，同 Task 更新相关页面并执行
  `scripts/docs-site.sh check`；与其无关的纯未来计划修改不因此运行全站构建。
- 不新增 required gate；若确需新增，先明确它捕获的具体缺陷，而非为满足抽象层而造检查。
- 不再报告“60%”等主观比例，只报告 M1 可运行、M2 环境就绪、M3 真实验收的事实与缺口。
- 下一实施阶段曾建议 50,000-token 上限；该数字仍是待确认建议，不视为已配置预算。
  实施前确定预算与停止点；达到上限或无法交付该里程碑时停下汇报，不自动扩预算或加层。

## Goal 对齐文本与状态

拟用于产品 goal 的目标文字：

> 按本收敛计划完成 LMDJ 一键发版加部署：复用既有 release.sh、唯一顺序总控与必要记录，
> 交付 run/status/resume，完整保留候选冻结、测试、独立审查、双角色签名、不可变发布、
> changelog/doc-site、Runtime/Creator 验证与 dev 晋级。按 M1/M2/M3 交付，不增加无必要框架，
> 不降低验证要求；真实发布等待单独发版请求，阶段预算确认后再恢复开发。

本次读取到原 goal 为 paused，仍指向本地 2026-09-13 single-command 设计。
当前工具只能读取 goal 或标记完成/阻塞，不能编辑 objective、预算或暂停状态。
因此此处是拟更新文字，不冒充产品 goal 已更新，也不将未完成旧 goal 标记完成来重建它。

## 本次文档 Task

提交文件：本计划与 `docs/plans/2026-09-13-release-orchestration-r2b.md` 的后续工作指针。
同时在原本地设计草稿和候选准备 WIP 计划中加收敛指针，保留原暂存区、实现与历史记录，
不把这些未完成堆叠分支夹带进本次提交。

验证：`git diff --check`、新增文件暂存后的 `python3 tests/build/ci_change_scope_test.py`、
计划相对链接存在性、PR body lint 与 documentation-impact declaration；独立文档审查。
本 Task 不运行产品、签名、部署或完整发版测试。

## Version Management

Version impact: none

Reason: 仅调整未来开发计划与跟踪，不改变 Product、Assembly、Module、Host、Provider、
Contract 或模型身份，不分配版本与快照。

## Documentation Impact

Documentation impact: none

Reason: 仅调整未来实施顺序与收敛约束，不改变当前命令、workflow、配置或 Portal 源码事实。
后续实现对 `/operations/version-and-release/` 等页面的同步义务仍保留。
