# LMDJ CI 吞吐与双节点 Self-hosted Runner 设计

日期：2026-08-14

状态：设计已由 Owner 确认；正式实施计划与任何基础设施变更待后续单独审核和授权

## 1. 结论

LMDJ 采用“减少不必要工作 + 双节点 Linux self-hosted 池”的组合方案：

1. 采购一台仅用于 CI 的 netcup VPS 8000 G12，承接 Web Toolchain、Formal Web
   Runtime Host 与 Creator 等重型 Web lane；
2. 保留现有 Contabo Singapore 项目主机上的两个 Runner service，但先把它们从拥有
   `NOPASSWD: ALL` 的部署用户迁移到无 sudo、无 Docker、无部署目录权限的专用 Runner
   用户，再用于 Core、ASan、Coverage、Package 与轻量控制任务；
3. Linux workflow 按真实角色标签调度，不再要求所有 Linux Runner 冒充 `contabo`；保持
   现有 busy -> queue 行为，并取消 token 不可用、Runner 状态 API 失败或无 online Runner
   时的自动 GitHub-hosted Ubuntu workload fallback；
4. Ready PR 继续使用已落地的风险分类；`main` push 改为对精确 `before..after` diff 运行同一
   fail-closed 分类，不再无条件 full；
5. Product Build 候选、release、中央 CI、Product Assembly、Contract、未知路径和显式
   dispatch 继续要求 exact-main full CI，focused main 结果不能替代该证据；
6. 新节点先通过单任务、双任务并发和连续 Web Proof benchmark，再逐 lane 切换。失败只回滚
   路由或 main scope 策略，不静默启用付费 Runner，也不放宽 correctness gate。

这里的“专用 CI 节点”表示该 VPS 只运行 CI，不表示其 vCore 是物理独占核心。netcup VPS
8000 G12 提供的是共享 vCore；调度并发必须以实测吞吐与稳定性为准。

## 2. 背景与当前证据

### 2.1 CI 关键路径

2026-08-14 审计的近期 `main` run 显示：

- docs-only merge 的完整 run `31759349040` 用时约 37 分钟；
- 另一成功 main run `31688172806` 用时约 38.5 分钟；
- `scripts/ci/change_scope.py` 当前对普通 `push` 与未指定 lane 的
  `workflow_dispatch` 无条件加入 full 原因；
- docs-only merge 因此仍运行 14 个正式 lane；
- `web-runtime-host` 是 self-hosted 池上的主要关键路径，曾运行约 25 至 33 分钟；
- self-hosted Linux job 还出现约 11 分钟排队，证明容量与调度共同放大了端到端时间。

现有 risk-based CI 已经解决 Ready PR 的大部分过度执行，也已经提供 Draft 轻量反馈、
`ci:full`、fail-closed 未知路径、lane manifest 与聚合 `PR Gate`。本设计不重建第二套分类器；
它扩展现有控制面，使 merge 后 main 也复用同一所有权政策，并重新设计 Runner 路由。

### 2.2 Contabo 主机实测

通过现有 `sg` SSH 入口对正在运行的 Contabo Singapore 主机进行了只读检查：

| 项目 | 2026-08-14 实测 |
| --- | --- |
| Host | `vmi3444835` |
| OS | Ubuntu 24.04，x86_64，kernel `6.8.0-124-generic` |
| CPU | 8 vCPU，AMD EPYC Processor |
| Memory | 25,199,181,824 bytes，约 24 GiB |
| Disk | 300 GiB SSD；检查时根卷约 283 GB 可用 |
| 常驻服务 | Docker、`lmdj-app-1`、`lmdj-caddy-1` |
| Runner | `contabo-lmdj-linux` 与 `contabo-lmdj-linux-02`，均在线 |
| Cache | `/var/cache/lmdj-ccache`，检查时约 658 MB |
| Runner 限额 | CPU、Memory 均未设置 systemd 上限 |
| Runner 用户 | 两个 service 均使用 `lmdjadmin` |

检查时两个应用容器合计只占约 120 MiB 内存，CPU 低于 4%，但这只是瞬时观测，不构成
容量保证。更重要的是，`lmdjadmin` 同时拥有 `(ALL) NOPASSWD: ALL`。因此当前 Runner job
虽然不能直接读取 `/opt/lmdj/shared/.env` 或 Docker socket，却可以通过 sudo 获得 root；这是
线上项目与 CI 共机时必须先消除的权限穿透。

### 2.3 Contabo API 状态

本机安装的 Contabo CLI 命令为 `cntb`，但当前合并配置中的 OAuth2 client id、client
secret、user 与 password 为空，无法从 API 查询实例 SKU、账单或数据中心字段。本设计以
主机实测容量为调度依据，并把以下只读检查列为实施前置条件：

```text
cntb authentication valid
  -> instance list succeeds
  -> vmi3444835 is mapped to one exact instance id
  -> SKU, region, lifecycle and billing fields are recorded without credentials
```

OAuth 凭据只进入 Owner 管理的本机 secret store 或临时环境，不写入仓库、计划、Actions
secret summary 或 Runner 工作目录。API 认证缺失不改变已实测的主机容量，但在正式迁移前
必须补齐资产归属记录。

### 2.4 netcup 采购基线

Owner 已选择购物车中的
[`VPS 8000 G12 1M Rabatt`](https://www.netcup.com/de/server/vps/vps-8000-g12-1m-rabatt)：

| 项目 | 采购基线 |
| --- | --- |
| CPU | 16 x86 vCore，KVM，共享计算资源 |
| Memory | 64 GB DDR5 ECC |
| Disk | 2,048 GB NVMe |
| Network | IPv4 + IPv6，Traffic Flatrate |
| Contract | 最短 12 个月，12 个月 billing period |
| Cart price | 首月 EUR 0；第 2 月起 EUR 40.28/月 |
| First-year estimate | 11 x EUR 40.28 = EUR 443.08 |

下单前以最终 checkout invoice 为准；公开产品页价格与购物车优惠可能不同。采购本身、付款、
账户验证和任何不可逆合约确认均由 Owner 执行，不属于仓库 commit 的授权。

## 3. 目标

- routine trusted Linux workload 不再自动消耗 GitHub-hosted Ubuntu minutes；Change Scope、
  PR Gate 与既有 macOS selector 保留最小 GitHub-hosted Ubuntu 控制面；
- docs-only Ready PR 与 docs-only main merge 的端到端目标均为 3 至 5 分钟；
- full CI 的稳定目标为 median 不超过 20 分钟、P95 不超过 25 分钟；
- 空闲池的 job queue 目标不超过 30 秒；
- Web timing-sensitive lane 在新节点上保持原有 assertion、behavior timeout、No-Retry 和
  clean-room Proof 语义；
- Contabo 上的 CI 不再拥有 root、Docker、部署密钥或项目运行目录写权限；
- CI 高负载期间 LMDJ staging 应用无 OOM、无容器重启、无健康检查回归；
- exact-main release/full 证据保持可审计，focused main 不能被误报为 release full；
- Runner 注册、在线、被选中、job 成功与 release evidence 继续分别报告。

## 4. 非目标

本设计不包含：

- Product、Module、Provider、Host 或 Contract behavior 变更；
- Product Build 分配、tag、Release、部署、Channel promotion 或 production publication；
- 降低 coverage floor、删除 sanitizer/stress、缩短测试行为 timeout 或自动 retry 红色测试；
- 把 external fork 的任意代码直接放到 self-hosted Runner；
- 承诺共享 VPS vCore 等同于独占 CPU；
- 在本设计文档 Task 中购买服务器、配置 sudo、停止 Runner、修改 branch protection 或
  改写 workflow；
- 改造 macOS self-hosted/hosted fallback。M1 仍由既有独立政策管理；macOS 成本优化可在
  Linux 迁移稳定后另立 Task。

## 5. 方案比较

### 方案 A：只扩容

采购 VPS，但保持所有 main push full、保持 hosted-pinned Web lane 与自动 hosted fallback。
实施简单，却继续为 docs merge 运行无关矩阵，也不能消除 hosted bill。

### 方案 B：只改 scope

main push 按风险分类，但继续使用当前 Contabo 两槽池和 hosted-pinned Web lane。成本最低，
docs merge 会变快，但 feature/full CI 的 Web 关键路径与队列不会解决。

### 方案 C：scope + 双节点池（采用）

同时引入 focused main、netcup Web 节点、加固后的 Contabo Core 节点、角色标签、无自动付费
fallback 和 benchmark rollout。它需要最多迁移工作，但同时解决无效执行、容量、Hosted
预算与生产主机权限风险，并且每层都可独立回滚。

## 6. 目标拓扑

```text
trusted PR / main / explicit dispatch
                |
                v
  GitHub-hosted control plane
  Change Scope + trust classification
                |
        +-------+----------------------+------------------+
        |                              |                  |
        v                              v                  v
  ci-general / ci-core          ci-web-heavy        macOS native
  Contabo Singapore             netcup CI VPS        M1 self-hosted
  2 isolated services           2 services first     existing policy
  8 vCPU / 24 GiB               16 vCore / 64 GB
        |                              |
        +---------------+--------------+
                        v
       GitHub-hosted same-run PR Gate
```

初始总 Linux concurrency 为四个 service：Contabo 两个、netcup 两个。netcup 只有在双并发
benchmark 不降低成功率、且 full CI 仍因 Web 排队超过目标时，才允许增加第三个 service；
增加 service 必须同时降低单 job build parallelism，使总编译并发保持在实测安全范围内。

## 7. Runner 身份与标签

标签必须表达事实和角色，而不是为满足旧 selector 伪装来源。

### 7.1 共享标签

所有可信 Linux service：

```text
self-hosted, Linux, X64, lmdj-linux, lmdj-linux-pool
```

### 7.2 来源与角色标签

| 节点 | 来源标签 | 角色标签 | 初始工作 |
| --- | --- | --- | --- |
| Contabo service 01/02 | `contabo`, `shared-with-staging` | `ci-general`, `ci-core` | Docs、Portal、Core、ASan、Coverage、Package |
| netcup service 01/02 | `netcup`, `ci-only-host` | `ci-general`, `ci-web-heavy` | Web Toolchain、Web Runtime Host、Creator、Web Runtime Lab |
| M1 | 既有 `lmdj`, `macOS`, `ARM64` | 既有 native 角色 | macOS Core/native ASan |
| WSL2 | `wsl`, `win11-host` | `ci-overflow` | 当前离线，不计入承诺容量 |

`contabo` 不再是 Linux pool 的共享选择条件。WSL2 不增加 `contabo` 标签；注册与 online 状态
也不等于已被 CI 使用，必须以真实 job 的 `runner_name` 证明。

### 7.3 Job 路由

- Web Toolchain、Formal Web Runtime Host、Creator 与 Web Runtime Lab 要求
  `ci-web-heavy`；
- Core Ubuntu、Linux ASan、Coverage 与 Package 要求 `ci-core`；
- Change Scope 与 PR Gate 保留 `ubuntu-24.04`；既有 `select-macos-runner` 也保持 Hosted，
  因为本设计不改 macOS fallback；
- trusted Docs/static、Portal、CI Contract、Deploy Contract 与 Chameleon Lab 使用
  `ci-general`；
- 只有显式 emergency dispatch 才能改变某次 run 的角色路由；普通 event 不因 busy、offline、
  token/API error 自动改成 `ubuntu-24.04`；
- fork 或不可信 head 不进入上述 self-hosted 标签；具体执行机制由 §8.1 固定。正式 merge
  证据必须在受信同仓库分支上重建；Owner 若要临时使用 hosted fallback，必须显式触发并
  接受该次费用。

现有 `select-ubuntu-runner` 的 provider-specific 输出将被角色路由替代；不能继续让一次
API snapshot 决定整个 run 是否购买 Hosted。本设计新增 trust 字段并改变 support job 集合，
因此内部 scope manifest 明确从 `lmdj.ci-scope.v1` 升级为
`lmdj.ci-scope.v2`；producer、Gate、contract tests 与 artifact consumer 必须同一 Task
原子迁移，拒绝混合版本。

### 7.4 最小 Hosted 控制面

Change Scope 继续在 GitHub-hosted Ubuntu 上执行，原因是它必须在任何 self-hosted Linux
Runner 离线时仍发布精确 diff、scope、trust 与升级原因。PR Gate 也继续 Hosted，使它不受
被裁决 workload 主机权限影响。两者运行 PR head 中的分类/Gate 代码时也不接触 self-hosted
主机。

这两项是预算中的显式豁免，不属于“routine Linux workload minutes”。实施后 summary 与
billing 统计必须把以下类别分开：

- hosted control plane：Change Scope、PR Gate，以及本设计不改动的 macOS selector；
- self-hosted workload：Docs/Core/Web/Creator/Package 等正式 lane；
- explicit hosted fallback：Owner 单次授权的 workload。

控制面目标是每次普通 run 合计不超过 5 个 GitHub-hosted Ubuntu job-minutes，不把它写成 0。
若 control plane 自身持续超过该目标，应优化 checkout/script，而不是迁移到可能离线或承接
不可信代码的 workload 主机。

## 8. 信任与主机隔离

### 8.1 Private fork 的执行门

仓库当前是 private、允许创建 fork，但 GitHub 的 private-fork workflow 设置为：

```text
run_workflows_from_fork_pull_requests=false
send_write_tokens_to_workflows=false
send_secrets_and_variables=false
```

这是外部 fork 不进入 self-hosted Runner 的主安全边界，必须在迁移前通过 GitHub API
重新验证，并在观察周检查没有漂移。private repository 不支持 public-repository 使用的
outside-collaborator approval endpoint，因此本设计不依赖一个对本仓库返回 422 的设置。

workflow 再做纵深防御：

1. Hosted Change Scope manifest 输出闭合布尔字段 `trusted_head`，job 同时输出
   `trusted-head`；只有非 PR event 或
   `github.event.pull_request.head.repo.full_name == github.repository` 才为 true；
2. 每个 self-hosted job 的 `if` 必须同时要求 selected lane 与
   `needs.change-scope.outputs.trusted-head == 'true'`；
3. Hosted PR Gate 将“selected self-hosted lane 因 untrusted head skipped”裁决为 failure，并
   在 summary 明确写 `untrusted fork blocked from self-hosted CI`；
4. external fork 如需正式 merge evidence，由 maintainer 把 exact patch 带入受信同仓库分支，
   在新 SHA 上重新建立正式 CI，不能继承 fork run。

workflow `if` 不是唯一安全边界，因为 fork 可以修改自己的 workflow 文件；private-fork
workflow 禁止执行才是阻止该文件开始运行的仓库级门禁。若未来 Owner 要开启 private-fork
workflow，必须先另立安全设计，当前双节点路由在该设置开启时视为不满足前置条件。

### 8.2 Contabo Phase 0 硬门禁

在 Contabo 承接任何新增工作前：

1. 为两个 service 创建独立、无登录或受限登录的 Runner 用户和独立工作目录；
2. 用户不属于 `sudo`、`docker` 或部署管理 group；
3. 用户不能读取 `/opt/lmdj/shared/.env`、部署 SSH keys、Caddy private state 或其他 Runner
   工作区；
4. 用户不能写 `/opt/lmdj`、systemd unit、Docker socket、`/etc` 或其他系统目录；
5. service 设置 `NoNewPrivileges`、`PrivateTmp`、kernel/control-group protection 与闭合的
   `ReadWritePaths`；
6. runner registration token 仅用于注册，完成后不保存在 shell history 或仓库；
7. 先停一个旧 service、迁移并验证，再迁移第二个；始终保留可回滚 service，不同时停止
   两个 Runner；
8. 用真实 CI job 证明新 `runner_name`、labels、无 sudo、无 Docker、无部署目录访问，再删除
   旧 root-capable service。

在此门禁完成前，当前两个 Runner 只能维持既有容量，不增加新 lane、service 或权限。

### 8.3 netcup 基线

- Ubuntu 24.04 LTS，最小安装；
- SSH key only，关闭密码登录和 root 远程登录；
- 默认拒绝入站，只开放 Owner 管理所需 SSH；Actions Runner 仅需出站连接；
- 每个 Runner 独立用户、service 与 `_work` 目录；
- 在基础镜像阶段预装 Playwright 所需系统库；CI job 不通过 `sudo` 或
  `playwright install --with-deps` 临时修改主机；
- 无 release signing key、production token、部署 `.env` 或 Docker socket；
- 系统更新、磁盘水位、Runner service 与 Actions 连通性有明确检查命令；
- 快照不是 cache/证据的替代，也不包含短期 registration token。

## 9. 资源与缓存

### 9.1 Contabo 资源保留

两个 Runner 进入统一 `lmdj-ci.slice`，初始总上限：

- CPUQuota：最多约 600%，为应用与 OS 保留至少约 2 vCPU；
- MemoryMax：最多 16 GiB，为应用、OS 与突发保留至少约 8 GiB；
- `CMAKE_BUILD_PARALLEL_LEVEL=3` 保持不变；
- ccache 设置有限 max size，并保留定期清理与命中统计；
- CI 期间持续检查 OOM、container restart、应用 health 与磁盘水位。

这些数值是初始安全限额，不是性能目标。若应用观测恶化，先降低 CI 并发或限额；不得以
放宽线上资源保护来满足 CI SLO。

### 9.2 netcup 资源保留

两个 Web service 进入统一 CI slice：

- 初始合计最多使用约 14 vCore 等价 quota 与 48 GB memory；
- 为 OS、SSH、监控和缓存维护保留约 2 vCore 与 16 GB；
- 初始每 job build parallelism 为 4 或 5，benchmark 比较后固定；
- 两个 service 拥有独立 workspace，不能同时写同一可变 toolchain tree。

### 9.3 持久缓存

- native Core 使用独立于 checkout 的持久 ccache；
- emsdk 按 revision + SDK version 安装为不可变目录；
- Playwright browser cache 按 lockfile 与平台身份隔离；
- npm download cache 可共享，`node_modules` 不跨 checkout 复用；
- 每个 job 仍执行 locked install、exact toolchain identity 与 clean build/byte identity gate；
- cache miss 只影响耗时，不改变输出合同；corrupt cache 必须可删除并冷启动；
- cache、workspace 与 artifact 分开设置容量与保留期，磁盘达到高水位时先清 workspace 和
  可再生 cache，不删除 release evidence。

## 10. Main scope 与 release authority

### 10.1 PR 语义

保留现有语义：

- Draft：Docs/static + CI Contract，不建立 merge 证据；
- Ready：按完整 base/head diff 运行 focused lane；
- `ci:full`、中央控制面、高风险或未知路径：full；
- 同一 PR 新 commit 可取消旧 run；同一 head 的正式 Gate 必须完整发布。

### 10.2 Main push

删除“所有 push 无条件 full”的特殊规则。`main` 使用 event 的精确 `before` 与 `sha`：

- 普通 docs merge：只运行路径政策选中的 docs/portal/control lane；
- 单一执行面：运行该执行面全部正式消费者；
- Product Assembly、Contract、root/shared CMake、CI scope/Gate/runner control、未知顶层、
  diff 不完整、force push、零 SHA 或无法验证 ancestry：full；
- 每个 main SHA 使用 non-cancelling concurrency；focused 不允许后一个 push 取消前一个
  SHA 的证据；
- main manifest 必须明确记录 `focused` 或 `full`、exact before/head 和升级原因。

### 10.3 Full exact-main

未指定 lane 的 `workflow_dispatch` 继续表示 full。以下状态只能接受 exact-main full：

- Product Build 被分配为 team testing 或 release candidate；
- release prepare、tag、draft Release、publication 或 Channel promotion 前置审计；
- CI/runner routing 正式切换后的迁移证明；
- Owner 显式要求完整回归。

release tooling 必须验证目标 SHA 存在成功的 full manifest 与同 run Gate，不能把 focused
main、PR head、旧 SHA 或一次局部 dispatch 当作 full 证据。此规则只建立证据前置条件，不
授权 tag、Release、部署或 promotion。

## 11. Hosted fallback 政策

- Change Scope、PR Gate 与既有 macOS selector 是 §7.4 的显式 Hosted 控制面；
- routine trusted Linux workload 的默认 hosted fallback 为关闭；
- 保持现有 busy -> queue 行为；这项能力已经实现，不列为迁移待办；
- Runner API/token failure 表示 observability failure，不表示付费切换；
- 全部匹配 Runner 离线时，job 保持 queued/blocked 并通知，不在无人确认时消耗预算；
- emergency hosted fallback 必须通过显式 dispatch input 或单独授权的 repository variable
  开启，summary 记录原因、Owner、run id 与预计 lane；
- fallback 只影响该次 run，不修改永久默认；
- hosted 运行的成功结果仍是有效 CI 结果，但费用和触发原因必须作为运营证据单独报告。

零 workload 自动付费的代价是池完全离线时 job 会排队；Hosted Change Scope 仍能发布本次
scope/trust 证据，但不能代替 workload。GitHub 对 self-hosted job 的 queue 上限是 24 小时，
超过后自动取消，因此最终状态是 fail/cancelled，而不是无限等待
（[GitHub Actions limits](https://docs.github.com/en/actions/reference/limits)）。故“空闲 queue 不超过
30 秒”的 SLO 只在至少一个匹配 Runner online 时成立；完全离线由 Runner heartbeat/运维
告警处理，不能用自动账单隐藏故障。

## 12. 迁移阶段

### Phase 0：基线与安全

- 记录至少三次近期 full/main run 的 queue、execution、critical path 与 billed minutes；
- 恢复只读 `cntb` 认证并记录 Contabo exact SKU；
- 通过 GitHub API 证明 private-fork workflow、write token 与 secret forwarding 均为关闭；
- 将 Contabo Runner 从 `lmdjadmin` 迁移到受限用户；
- 加入 resource slice，验证 staging health 与真实 runner assignment；
- 未通过安全门禁时停止，不继续扩容路由。

### Phase 1：netcup provisioning

- Owner 完成购买；
- 安装、加固、监控、toolchain 与两个 Runner service；
- 注册真实 `netcup`/`ci-web-heavy` 标签；
- 运行不执行产品 workload 的 inventory/preflight，证明 OS、CPU、RAM、NVMe、网络、权限与
  cache 目录。

### Phase 2：benchmark，不切正式路由

- 新增独立的 dispatch-only benchmark workflow；它要求 exact trusted revision 与闭合 lane
  allowlist，直接选择 `ci-web-heavy`，不发布 PR Gate、不满足 branch protection，也不改变
  正式 workflow 的 `runs-on`；
- 该 workflow 调用与正式 lane 相同的 pinned toolchain setup、stable script 与 artifact/trace
  收集入口，禁止复制一套可能漂移的测试命令；
- 分别运行 Web Toolchain、Web Runtime Host、Creator 的 benchmark dispatch；
- 至少覆盖一次 cold cache、三次 warm cache；
- 覆盖单 Runner idle 与两个 Runner 并发；
- 保留 Playwright trace、runner name、queue、execution、load、memory、cache 与失败分类；
- semantic failure 不自动 rerun；环境修正后的新 run 单独记录。

### Phase 3：逐 lane 切换

1. Web Toolchain；
2. Creator；
3. Web Runtime Host；
4. Web Runtime Lab 与其他适用 Web workload；
5. Linux control/light job；
6. 取消 token/API/no-online 条件下的 routine GitHub-hosted Ubuntu workload fallback；busy ->
   queue 保持不变；

每一步至少连续三次绿色并满足资源门槛后才进入下一步。某 lane 失败只回滚该 lane 路由，
不同时回滚 scope、其他 lane 或测试 assertion。

### Phase 4：focused main

- 先以 contract tests 证明 push diff、zero SHA、unknown path、full rules 与 dispatch full；
- 再启用 main focused；
- 用 docs-only、单 Core、单 Web 与 CI-control 四类真实 main SHA 证明 manifest；
- 单独 dispatch exact-main full，证明 release authority 未被 focused 结果替代。

### Phase 5：观察周

连续七天记录：

- docs/feature/full wall-clock；
- 每 host queue、worker time、CPU、memory、disk 与 cache hit；
- Web timing failure 与 Playwright trace 分类；
- Contabo 应用 health、5xx、container restart 与 OOM；
- GitHub Actions Linux hosted minutes；
- 手动 fallback 次数及授权原因。

观察周通过后才把新路由写成长期运营基线。

## 13. 验收标准

### 13.1 Correctness

- 所有 scope/runner/Gate contract tests 通过；
- unknown、unclassified、truncated diff 与 manifest version mismatch 均 fail closed；
- Web 三条重型 lane 在新节点至少连续三次成功，其中包括双并发；
- exact-main full dispatch 的 14 lane 与同 run Gate 成功；
- release audit 拒绝 focused main 替代 full exact-main；
- 不修改 behavior timeout、coverage floor、sanitizer/stress 或 Proof inventory。

### 13.2 Performance

- docs-only PR/main：目标 3 至 5 分钟；
- full CI：至少五次代表性 run 的 median 不超过 20 分钟，P95 不超过 25 分钟；
- 匹配 Runner online 且 idle 时 queue 不超过 30 秒；
- 若两个 netcup service 竞争导致单 job 比 idle 慢超过 25%，先降低 build parallelism 或并发，
  不直接增加第三个 service。

### 13.3 Cost

- 观察周 routine trusted Linux workload 的 GitHub-hosted Ubuntu minutes 为 0；
- Change Scope、PR Gate 与既有 macOS selector 单独记为 Hosted control plane，每次普通 run
  目标合计不超过 5 个 Ubuntu job-minutes；
- 任何 control plane 之外的 hosted Linux workload minutes 都能映射到一次显式 emergency
  authorization；
- netcup 首年实际 invoice 与 checkout 记录一致；
- Contabo 为既有成本，不把沉没成本重复计入 CI 增量费用。

### 13.4 Production-host safety

- Contabo Runner 用户无 sudo、无 Docker、无部署 secret/tree 权限；
- CI slice 之外始终保留约 2 vCPU 与 8 GiB memory；
- full/并发 benchmark 期间无 OOM、无应用容器重启、无健康检查失败；
- 任一安全断言失败即停止 Contabo CI，并将 workload 移回 netcup/blocked 状态；不通过恢复
  `lmdjadmin` root-capable Runner 来应急。

## 14. 失败处理与回滚

| 失败 | 默认处理 | 禁止行为 |
| --- | --- | --- |
| netcup offline | Web job queued/blocked；告警；按授权决定 emergency hosted | 自动购买 Hosted |
| netcup timing regression | 降低并发/parallelism；保留 trace；回滚单 lane | 放宽 behavior timeout |
| Contabo 应用资源回归 | 停止 Contabo Runner，保留 staging；路由 Core 到已批准节点 | 抢占应用保留资源 |
| scope 分类错误 | 恢复 main unconditional full，修复 classifier | 静默跳过 lane |
| Gate/schema 不一致 | 整个 run fail closed，原子回滚 producer/Gate | 接受混合 schema |
| cache corrupt | 删除可再生 cache，执行 cold run | 用旧 artifact 冒充新证据 |
| Runner 凭据泄露 | 移除 Runner、吊销 token、轮换相关 secret、保留事件证据 | 只重启 service |

由于 netcup 优惠是 12 个月合约，性能不达标时不能假设一个月无成本退出。回滚 CI 路由后，
Owner 可在合约范围内把节点降并发、改作 Core/overflow 或等待供应商处理；不得因沉没成本降低
测试门槛。

## 15. Version Management

Version impact: none.

理由：本设计与未来实施只改变 CI scope、Runner 基础设施、缓存、调度和证据验证，不改变
任何 Product Build、Core Module、Provider、Host 或正式 Contract 的运行身份。CI scope
manifest 若升级为 v2，是仓库内部 CI schema 迁移，不是 active product Contract SemVer，且
必须由 producer/Gate/tests 原子切换。

## 16. Documentation impact

本设计文档 Task 的 Documentation impact: none。

理由：本 commit 只记录已批准的未来设计，不改变当前 workflow、Runner、运行状态、Portal
事实页或 Product Build，因此不把 designed state 写成 implemented state，也不创建 Portal
snapshot。

未来实施 Task 的 Documentation impact: required，至少同步：

- `docs/governance/git-workflow.md`：focused main、full exact-main 与 emergency fallback；
- `docs/quality/core-test-policy.md`：双节点标签、角色、队列、资源与 Runner evidence；
- `apps/architecture-portal/docs/operations/testing-and-proof.mdx`：当前 CI scope、routing、
  Hosted policy 与 evidence；
- `apps/architecture-portal/docs/operations/version-and-release.mdx`：release 所需 exact-main
  full 证据；
- Contabo staging 运维文档：Runner/部署权限隔离和资源保留。

实施计划必须逐 Task 声明确切 affected portal routes，并在相关 commit 前运行
`scripts/architecture-portal.sh check`。普通 CI 或本地 Portal build 不创建永久 snapshot；本次
CI/infrastructure 变更不分配 Product Build。

## 17. 权限边界

本设计获批只授权撰写设计与实施计划，不授权：

- 购买或取消 netcup/Contabo 合约；
- 写入 Contabo OAuth 凭据；
- 创建、停止、删除或重新注册 Runner；
- 修改 sudoers、systemd、firewall、branch protection 或 Actions secrets；
- push、PR、merge、release、deployment 或 Channel promotion。

每个基础设施 mutation、远端 Git 状态转换和 release boundary 仍需按仓库治理单独授权、验证
并报告。
