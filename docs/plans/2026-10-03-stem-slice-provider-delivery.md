# Stem / Slice Provider 路径：决策落盘与分阶段交付

日期：2026-10-03。依据：[决策](../prd/decisions/2026-10-03-stem-slice-provider-boundary.md)
和 [Contract 设计](../design/2026-10-03-stem-slice-provider-contract.md)。
Relates to #1163、#1164、#1172、#1670、#1654、#472。

用户已授权按此路径推进及 push / PR / merge；各 Task 仍独立验证、评审并
提交一个 Conventional Commit。真实评测需要具名环境，产品模型选择需要
测量结果；不把这里的规划交付当作这些前置已经满足。

## D0 — 当前 Task：确认功能、Contract 边界和依赖

精确声明文件：

- `docs/prd/decisions/2026-10-03-stem-slice-provider-boundary.md`
- `docs/design/2026-10-03-stem-slice-provider-contract.md`
- `docs/plans/2026-10-03-stem-slice-provider-delivery.md`
- `docs/design/2026-10-02-stage12-stem-scope.md`
- `docs/plans/2026-10-02-stage12-stem-evaluation.md`
- `docs/design/2026-09-29-creator-user-workflow-design.md`
- `docs/design/2026-09-29-creator-user-workflow-guide.md`

最低层验证：相对链接与 Markdown 表结构；逐项对照当前源码和官方 Koala 手册；
暂存新文件后运行 `python3 tests/build/ci_change_scope_test.py`；提交后运行
`scripts/local-ci.sh --lanes docs_static`、PR body lint、declaration-only 与
batch-evidence-only。没有新门禁。当前 Task 不修改活动接口或运行模型。

## C1 — 下一源码 Task：输出端口共享内容

依赖 D0 的 current-head review。先在基线增加最小复现：两个 required 端口
输出相同合法 bytes，经真实 execute 成功后重开，分别读取全部角色。
预期旧代码在第二个 sink 写入处拒绝；记录确切红点再修复。

功能源码/测试的精确范围：

- `packages/provider-sdk/src/attempt_store.cpp`
- `tests/core/provider/conformance_test.cpp`
- `tests/core/provider/output_validation_test.cpp`
- `tests/core/provider/attempt_output_read_test.cpp`
- `tests/core/provider/execution_crash_test.cpp`
- `tests/core/provider/callback_stress_test.cpp`
- `docs/plans/2026-10-03-provider-shared-output-bindings.md`（实施前新建施工单）

逐项证明：跨端口同 Ref 成功；同端口重复拒绝；同 hash 不同 Ref 拒绝；
每个角色 Schema 独立验证；漏绑/多绑/换绑拒绝；output/staging 限额不变；
失败清理、崩溃重开和共享内容读取保持完整身份；旧成功/失败 terminal 仍可读。
使用旧基线 reader 读取新 terminal 的兼容性实验决定持久化格式与 SemVer，
不凭 wire shape 相同推断兼容。

最低层测试：`provider.conformance`、`provider.output_validation`、
`provider.attempt_output_read`、`provider.execution_crash`、
`provider.attempt_isolation`、`provider.artifact_source`、`provider.spec_regression`；
变动触及 callback 共享状态时运行 `provider.callback_stress` 及适用 sanitizer。
新用例防止角色被内容去重丢失和共享 blob 绕过身份/配额校验，不新增 CI gate。

Version impact: required。预计为 SDK 新公开能力；若持久化兼容实验失败，按
MAJOR/新格式处理。施工前从最新 manifests 计算并逐项列出 SDK、Provider、
消费方依赖、Assembly、版本锁和生成文件的精确级联清单；禁止遗漏身份文件
或直接降低版本检查。该清单未冻结前，此节是功能范围，不是可立即提交的完整 Task。
Documentation impact: required；至少 `/core/modules/provider-sdk/`、
`/contracts/capability/` 和受级联影响的 Assembly/Host 页面，Product Build
分配随实现完成，使用正式 snapshot 命令并验证 squash provenance。

## 后继 Task 依赖与施工单要求

下表是依赖图，不把目录或示例路径当无限施工授权。每个 Task 开工前在最新
main 核实已交付内容，并新增独立施工单，冻结 exact files、测试、版本级联
和 Portal 路由；复用已有能力，不重复实施 K/L 系列已经交付的 Slice 链路。

| Task | 依赖与具体交付 | 最低层验证 / 捕获的缺陷 | 版本与文档影响 |
| --- | --- | --- | --- |
| C2 Stem Capability 与 validator | C1；正式 descriptor、四路 PCM profile/量化、typed errors、模型身份；真实 SDK proof Provider | Schema 正反例、四路静音、缺/重复角色、错 shape、NaN/Inf、削波拒绝、终态重开；防止无效音频进入候选 | Contract 新身份、SDK/Provider 实际影响；Portal Contract/Provider 路由 required |
| E1 隔离执行与 C1 模型适配 | C2；具名 Linux CPU 环境、锁定权重/依赖、真实 execute 子进程、无推理网络、deadline/tree RSS/清理 | controller 注入 + 真实模型重复运行分别记录；TERM-resistant descendant、cancel、超限和 partial；防止孤儿/失控执行冒充成功 | 适配器独立 Provider 身份；执行 Host 依影响；Portal required |
| E2 评测与 checkpoint 决策 | E1；沿 #1172 T2-A/B/E 的精确工具和 corpus 范围执行；报告通过、淘汰、未执行 | 输入/权重/输出身份、SI-SDR、RTF/RSS、盲听；禁止 synthetic 或参考进程冒充生产资格 | tooling/report 无版本；模型产品选择独立记录 |
| W1 Stem 候选与 Lineage | C2；Facade 角色展开、封闭派生类型、原子采纳、配额、旧 Slice 兼容 | candidate store/job/audition/adoption、domain codec、Project I/O save/reopen；验证完整设计旅程 | Domain/Project/Facade 按兼容性分配；相关 Portal required |
| W2 编辑输入与 Chop 模式 | D0、既有 Slice；固化选区/编辑效果、等分、播放打点与标记 revision；Play Thru 等播放目标逐项验收 | Prepared Artifact 身份、区间帧边界、点位编辑重开、原 Attempt 不变、实际试听 stop | 输入准备与 recipe/Facade/播放涉及版本；相关 Portal required |
| H1 Sample Tools 与结果放置 | W1/W2、#1670；空位映射、确认、后台占位/进度/取消、移除独立 Slice 模式；可先交付已有 Slice 的完整增量 | Creator component/state + packaged Host 旅程，满位、占位竞争、删除取消、失败重试、保存重开；真机试听单列 | Host/Facade 按实际变化；`/hosts/creator-web/` 等 required |
| P1 Assembly 与产品验收 | E2/W1/H1；按平台资格注册，首次模型取得/离线可用，完整功能验收矩阵 | assembly lock/依赖、真实可支持平台完整 journey、能力不可用提示；不以注册冒充可用 | Product Build 与 immutable snapshot required；无自动 release |

E1 使用具名且验证合格的环境后才下载或运行；用户提出 `ssh vienna` 作为候选，
其只读检查结果见下节，尚不具备已验证的隔离评测环境。首轮候选保持 T1 固定的
Open-Unmix `umxhq`，预算与数据范围沿 T1，任何付费/GPU/remote/额外数据
另有明确授权。模型权重 SHA-256 必须在运行前从实际字节冻结。Linux 不可用时
继续 C1/C2/W1 的机器可执行部分；不降低隔离证据标准或把本机 macOS 当 Linux。

E2 人工盲听需要实际人员与合法素材；未执行就保留缺口。#1654 的可安装代码、
签名/撤销、云端策略保持独立，不阻塞 closed-world 的本地参考 Provider proof，
但阻塞依赖它的安装/云功能产品交付。Browser/native/Cardputer 平台支持分别验证。

## vienna 候选主机检查（2026-10-03）

通过已有 SSH 配置、BatchMode 与严格 host-key 检查，只读查询系统与权限：

- Ubuntu 24.04.5 LTS、x86_64、Linux 6.8；16 个 AMD EPYC-Genoa vCPU，
  约 62.8 GiB RAM；第一次观测 MemAvailable 约 53.7 GiB；home/tmp 所在盘
  余量约 1.26 TiB。硬件容量适合首轮 CPU 评测，但不是实测模型资源结论。
- 主机同时运行五个 LMDJ Actions runner；`lmdj-ci.slice` 的 CPU 上限为
  14 CPU、MemoryMax 为 48 GiB。两次 loadavg 的 1 分钟值约 12.4 / 23.5；
  不能把 16 CPU 总数或当前可用内存当可独占的评测预算。
- 默认 Python 为 3.12.3，未发现 `python3.11`；`bwrap`、`podman` 不在 PATH。
  Docker CLI 存在，但当前 SSH 用户读取系统 socket 返回 permission denied；
  该用户默认 rootless socket 不存在，用户级 docker.service inactive。
- cgroup v2 存在，用户 service 委派 cpu/memory/pids；用户 namespace 与 AppArmor
  限制均开启。这些配置读数不证明实际 no-network、只读输入、写目录隔离、
  kill/cleanup 或硬资源限额已经通过控制测试。

结论：选为候选硬件；E1 仍需独立运行环境（含固定 Python/依赖）、实际隔离
控制验证，以及与 CI 不竞争的具名运行窗口/资源安排。当前没有安装、下载、
运行模型、调整 CI 配额、重启服务或更改 Docker 权限。性能报告必须保留宿主
负载，不能在这些共享高负载观测下宣称专用环境测量。C1/C2 的开发继续独立推进。

## Version Management

Version impact: none for D0。
Reason: 当前只新增/同步 retained 决策和规划；C1 及之后按每个 Task 的上述规则
从最新 active manifests 分配，不提前占用版本或更改 Assembly。

## Documentation Impact

Documentation impact: none for D0。
Reason: 当前不变更 Architecture Portal 的活动源事实；后继源码 Task 的 required
声明、路由和快照不能沿用 D0 的 none。
