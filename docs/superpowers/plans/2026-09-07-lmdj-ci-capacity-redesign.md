# LMDJ 乐观合并与每日自测实施计划

日期：2026-09-07
状态：待实施；本次仅提交计划，不改变线上 CI 或合并规则。

设计依据：[CI Capacity Redesign spec（固定修订）](https://github.com/endaye/lmdj/blob/c6c3f0f00ac41a2f4313c8d5092231226e3889fd/docs/superpowers/specs/2026-09-07-lmdj-ci-capacity-redesign.md)，
[spec PR #752](https://github.com/endaye/lmdj/pull/752)。
计划检查基线：`0d713914`；各 Task 开始前重新读取最新 `origin/main` 和现行治理，
不得覆盖其他任务刚落地的 CI、release hydrate 或审查监控修复。
本计划以 spec PR #752 合入为前提；spec 若在评审中修订，先更新本文的依据修订再实施。

2026-09-07 评审修订：以 #724 的每日 sweep 为现任自测入口（§3.1、T2）；取消 T0，
登记随各自 workflow 的 Task 进行；T5 拆为 T5a／T5b；O1 对旧手动入口的目标绑定
改为定论并把 T7 提前到 O2 之前；O2 写明保护规则前置判据；补齐 spec §5.1 的
“无新 main 则跳过”与 §9 的统计口径归属。

## 1. 交付结果与边界

目标流程是：PR 当前 head 的 AI review／人工接管 → 明确授权后合并；
每天和重要节点对固定 main SHA 做全量自测 → 失败提出或更新 issue；
Owner 手动选择版本候选 → 核验该 SHA 的完整证据 → 分别授权发布操作。

- 日测不是每日发布。绿色日测不创建 tag、Release、部署或 Channel promotion。
- 普通产品缺陷使自测为红、候选不可发布，但不暂停普通 PR 或修复 PR 合并。
- 不用新的 merge queue、全量本地 pre-push 或长时间 AI 状态轮询替代旧瓶颈。
- 这是有意接受 main 短时不稳定的策略；生效时同步修改“main 始终可部署”的旧治理。
- 保留短分支、隔离 worktree、PR、冲突处理、审查对话以及逐步操作授权。
- 不改变测试断言、覆盖率底线、stress 重复次数、签名或不可变版本快照规则。

本计划不是远端操作授权。代码提交、push、PR、merge、规则修改、受控故障演练
以及 release 操作分别遵循当时有效的授权边界。下文复选框均未完成。

## 2. 最短落地路径

| 顺序 | 交付 | 退出证据 |
| --- | --- | --- |
| T1–T2 | 固定 SHA 全量自测的清单与入口 | 完整套件清单；一个真实目标的终态报告 |
| T3–T4 | 去重 issue 报告、AI review 独立入口 | 失败可定位且可重试；review 不依赖重型任务 |
| O1 | 切换前受控验收 | 自测、报告、旧手动候选路径均可用 |
| T7 | 新日测证据接入发布验证器 | 精确完整证据可复用；无效证据拒绝；候选可指定旧 main SHA |
| T5a/T5b + O2 + T6 | 切换规则、停止重复触发、退役队列 | 落后但无冲突的 PR 不 update、不等全量即可合并 |
| T8 + O3 | 资源收缩、统计口径与稳定性验收 | 无重型 merge 等待；日测问题反馈持续有效；§9 指标有数据来源 |

T1–T4 期间现有门禁仍生效。新自测先仅手动演练，不同时开启两套每日全量任务。
O1 通过后由维护者确定一个有开始、截止和回退负责人的切换窗口；不无限期双跑，
也不为采样而强制等待七天。T7 排在 O2 之前（见 O1 第四项的定论）；T8 不应延迟
已具备反馈和候选路径的合并政策切换。

每个 T Task 是一个 reviewable Conventional Commit，使用独立短分支及 worktree。
若文件范围实际过大，在实现前按行为边界拆 Task，而不是合为一个巨型控制面 PR。
O Task 是远端操作与证据检查点，不通过空 commit 伪装成代码交付。

## 3. 实现约定

### 3.1 保持一个全量定义

当前清单来自 `scripts/ci/scope_policy.json` 的 14 个 logical lanes：

`docs_static`、`portal`、`ci_contract`、`core_ubuntu`、`core_asan`、
`core_coverage`、`core_macos`、`web_toolchain`、`web_runtime_host`、
`creator`、`web_runtime_lab`、`deploy_contract`、`chameleon_lab`、`package`。

另须纳入 `core-nightly.yml` 当前执行的 TSan stress 和 Release stress
（`--repeat until-fail:20`）。不要把 `core.sh test dev full` 或 `proof`
误称为上述全量；它们排除 stress。Linux ASan 保留 full + stress 和 Python-hosted
覆盖；macOS 保留 native sanitizer 覆盖。Mac runner 选择／fallback 的控制分支
可以按明确定义跳过，但对应 logical suite 必须有真实成功结果。

T1 为此定义一个权威的自测套件清单和校验器。旧 scope policy 在兼容期用于旧 CI，
用 parity test 对照两个入口；不得长期手工维护两份互不校验的“全量”列表。

现任入口是 #724 的每日 sweep：`ci.yml` 的 `schedule: "0 16 * * *"` 已对 main tip 的
固定 SHA 运行完整 manifest，带同 run 的 Change Scope／PR Gate 裁决、保留的 scope
manifest 和 release verifier 认识的 `Core CI` 身份。它与本计划的自测只差三件事：
Nightly 的 TSan／Release stress 未并入同一批次；手动 dispatch 不能指定旧 main SHA；
verifier 不接受 `schedule` 事件。**本计划以扩展这条路径为默认实现**，不新建平行的
`self-test.yml` 复制十余个 job 定义；若实施中发现必须分离 workflow，须在 T2 的 PR
里写明复制优于扩展的理由和消除复制的 Task。

### 3.2 固定目标，不伪造事件身份

自测证据区分 `control_revision`、`target_revision`、run ID、run attempt、
suite ID、policy revision、结论、产物摘要和开始／结束时间。
所有目标都是完整 40 位 SHA，并证明属于 main 历史；checkout 后实际 HEAD 必须一致。

定时事件选择一个 main 目标后不再漂移。手动重要节点和候选可明确选择旧 main SHA，
但 GitHub run 的 head SHA 可能是控制工作流修订，不能覆盖成候选 SHA 来“满足”旧验证器。
T7 使用新协议显式验证两者及可信 resolver、checkout、suite 结果的绑定。
产物命名包含目标、run ID 和 attempt；重跑追加观察，不能覆盖旧失败记录。

### 3.3 无长驻排队控制器

执行中的批次不因新 main 取消。普通日测 pending 可合并为最新尚未覆盖的目标；
显式节点／候选请求不可被普通 pending 替换，重复同 SHA 请求可复用有效结果或订阅同批次。
当天 main 没有新提交时，普通定时自测跳过并保留上一完整结论（spec §5.1）；
跳过本身记录为一次观察，不算漏跑，也不把旧结论的日期改成今天。

优先采用短生命周期的入口／结束回调加 Actions 状态查询，不增加数据库或常驻服务。
不要在自托管 runner 上保留数小时 polling job。原生 pending 替换不保证业务目标
按新旧顺序保留：resolver 必须在启动时检查规范目标与未完成请求，延迟旧事件不得吞掉新目标。
有限容量溢出必须明确拒绝并给重试办法，不能静默丢掉显式候选。

### 3.4 日测结果与报告状态分开

独立 suite 失败不取消其他独立 suite；构建失败的下游为 blocked/not-run，
缺失结果、异常取消、超时或 artifact 失效均不算全量通过。
reporter 失败不改变测试 verdict；自身产生可见的 reporting-error。

去重键是稳定 suite/test ID + 规范化错误类别，SHA 和日期属于观察记录而非问题身份。
并发与重试通过单写者短报告任务和幂等 observation key
（run ID / attempt / suite / failure fingerprint）收敛到同一个 issue。
日志只作数据，截断、脱敏、转义；不得执行 artifact 内容或让 AI 指令获得写入权限。

## 4. Tasks

### T1：自测清单、身份及终态协议

**分支／commit：** `feat/ci-self-test-contract` /
`feat(ci): define exact-revision self-test evidence`

**新增文件（计划路径）：** `scripts/ci/self_test_policy.json`、
`scripts/ci/self_test.py`、`tests/build/ci_self_test_test.py`。

- [ ] 先写测试：完整集合成功、缺 suite、重复身份、未知 mandatory suite、错误 SHA、
  混合 run attempt、上传失败、空结果、合法 Mac 分支跳过和 required suite 跳过。
- [ ] 实现 resolve / aggregate 的纯逻辑接口；协议版本是 CI 内部证据版本，
  不是 Product 或跨语言 Contract 版本，不向 `contracts/` 添加新产品 Contract。
- [ ] 清单涵盖 §3.1 的全部现存覆盖，parity test 在旧 policy 增减 lane 时失败并指出 remedy。
- [ ] 判定明确区分 test failure、infrastructure failure、blocked、expected supersession；
  普通失败保留可行动的 why / remedy，不借分类把失败改成通过。
- [ ] 固定输出及 digest；外部 API、时间和存储的测试替身按
  `.agents/pitfalls/fake-tool-stub-strictness.md` 现行指引构造：测试显式调用的方法
  镜像生产工具的参数形状，按墙钟触达的方法另行处理；不在本计划另写一套替身规则。
- [ ] 去重键同时决定“无新 main 则跳过”：resolve 收到与上一完整结论相同的目标时
  返回 skip 观察而非新批次；显式候选与节点请求不受此规则影响。

**验证：** `python3 tests/build/ci_self_test_test.py`，
`python3 tests/build/ci_change_scope_test.py`。
Documentation impact: none；此时协议尚未接入任何执行或发布入口。

### T2：把 sweep 扩展为固定目标的自测入口

T2 接手修订边界：先启用手动空 dispatch 的固定目标批次，旧每日 sweep 与 Nightly
cron 均保持现状，O1/T5a 才切换每日入口与去重。显式请求按 run ID 独立保留，仍使用
现有重型资源锁；独立 suite 的先后顺序保留，但不因前一个 suite 失败而取消后一个。
本阶段仅接受 attempt 1；诊断重试必须新建同 target 的 dispatch，避免 Actions 局部
rerun 继承旧成功结果。resolver 和 verdict 都拒绝后续 attempt，日后若支持完整 rerun，
须先证明所有 suite 的真实 attempt。产物名含 target/run/attempt，旧失败不覆盖。
解析前另保留 self-test-request 记录，未验证 target 只供识别请求，不构成测试证据。

**分支／commit：** `feat/ci-self-test-runner` /
`feat(ci): run complete self-tests on a fixed main revision`

**修改：** `.github/workflows/ci.yml`（手动 dispatch 路径）、
`.github/workflows/core-nightly.yml`、`.github/workflows/architecture-portal.yml`、
`scripts/ci/change_scope.py`、`scripts/ci/hosted_runner_policy.json`、
`scripts/ci/self_test.py`；`tests/build/ci_self_test_test.py`、
`tests/build/ci_change_scope_test.py`、`tests/build/ci_workflow_topology_test.py`、
`tests/build/ci_runner_fallback_test.py`、`tests/build/release_hydrate_test.py`
（允许 resolver 精确 fetch main，仍禁止内联 intent hydrate）；
`apps/architecture-portal/docs/operations/testing-and-proof.mdx`、
`docs/quality/core-test-policy.md`、`docs/governance/git-workflow.md`、本文。
**新增：** `tests/build/ci_self_test_workflow_test.py`、
`scripts/ci/self_test_evidence.py`、`tests/build/ci_self_test_evidence_test.py`。
后两项提供 T3 共用的只读消费校验器，严格核对身份、digest、suite/job 集合与结论。
新文件沿现有 scripts/ci full 规则与 ci_*_test.py 所有权登记；验证后若存在缺口，
同 Task 更新 `scripts/ci/scope_policy.json`，不另设 T0。

- [ ] 在 #724 的 sweep 路径上增加 `target` 输入：手动 dispatch 可指定 main 历史上的
  完整 SHA，checkout 该 SHA 而非 ref tip，scope manifest 记录 `target_revision`；
  `schedule` 的新目标解析延至 T5a 接线。`workflow_dispatch` 的 ref 只能是分支或 tag，
  所以“指定旧 SHA”只能靠输入＋校验实现，不能靠 ref。
- [ ] 把 Nightly 的 TSan stress 与 Release stress 并入同一批次报告；Nightly 自己的
  cron 在 T5a 停用前保留，新批次暂不接 schedule，避免两套自动任务重复同一 SHA；
  Owner 显式手动验证同 SHA 不属于自动重复，需保留独立请求与结论。
  TSan suite 依赖主机 `vm.mmap_rnd_bits ≤ 28`（`scripts/ci/host/configure-sanitizer-aslr.sh`，
  操作者 sudo）；前提缺失按 infrastructure failure 报告，不记为 blocked 或通过。
  保留现有资源锁、工具链、LFS 和 release hydrate 调用。
- [ ] 不复制 job 定义。若某个 suite 确实必须从 `ci.yml` 分离，本 PR 写明理由、
  原 job 到新 suite 的对应关系、parity test 和消除复制的 Task。
- [ ] 当前控制代码负责解析、checkout、清单和汇总；测试进程无 issues/PR/contents 写权限，
  无签名、发布或部署凭证。不得在高权限 `pull_request_target` 中执行 PR 代码。
- [ ] 测试工件与报告放在 checkout 之外，避免弄脏目标让 package 拒绝或记录错误 revision。
- [ ] 加入 failure collection 与最终汇总；按真实 build 依赖串联，独立 suite 继续运行。
  默认矩阵 fail-fast 不得取消其余覆盖。
- [ ] 验证 main A 测试中出现 B 时，全部 suite 和 package 仍指向 A；
  错误／非 main 目标被拒绝。先不改 release verifier。
- [ ] 门户准确标注“手动自测现可指定目标并含 Nightly 套件，旧 sweep/Nightly cron
  与门禁仍生效，日测尚未迁移”，
  不提前宣布乐观合并已上线。

**验证：** T1/T2 测试；现存 `ci_workflow_topology_test.py`、
`ci_nightly_workflow_test.py`、`ci_toolchain_pin_test.py`、
`ci_change_scope_test.py`；CI contract 的 pinned actionlint；portal check。
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/

### T3：失败 issue 闭环与漏跑告警

**分支／commit：** `feat/ci-self-test-reporting` /
`feat(ci): report self-test failures idempotently`

**新增：** `.github/workflows/self-test-report.yml`、
`scripts/ci/self_test_report.py`、
`tests/build/ci_self_test_report_test.py`、
`tests/build/ci_self_test_report_workflow_test.py`。
新 workflow 的路径登记先由独立 [路由 PR #760](https://github.com/endaye/lmdj/pull/760)
交付；本功能 PR 不再携带 `scripts/ci/scope_policy.json` 控制面改动。
**修改：** `scripts/ci/hosted_runner_policy.json`、测试门户页面；
`docs/governance/github-work-management.md`、本文、
`.agents/pitfalls/fake-tool-stub-strictness.md`（真实 Actions API 的动态 run name
与 fixture 不同，记录复现；稳定 workflow ID/path 才是身份）。

T3 实施边界：当前先按 suite/class 归集故障观察，尚未抽取真实 test ID 或日志错误
指纹，维护者可拆分同桶内的不同缺陷；下述根因级去重验收仍待补齐，不因本地测试
通过而勾选。报告器只信任 Actions bot 发布的归集与观察 marker；目标和控制 revision
分别核对 main 历史，展示名不作为 workflow 身份。真实 GitHub 创建、重送与恢复验证
仍留在 O1，不将 fake API 的绿色当作远端闭环证明。

2026-09-07 迁移复审（只读真实 API，补入原验收依据）：

- 查询 `ci.yml`、`main`、`completed`、`created>=2026-08-08`：
  `workflow_dispatch` 共 38 条（36 success、1 failure、1 cancelled），`schedule` 为 0；
  main run 展示名为 22 条 `Core CI` 与 16 条 `Core CI / main`。不限定分支的 dispatch
  共 188 条，最新 10 条为任务分支上的 `Core CI / mq:...`。因此当时并非 main 窗口
  已被 100 条旧 queue 填满，不能把全分支总数误作 reporter 的实际输入。
- 但 [旧 run 31902121850](https://github.com/endaye/lmdj/actions/runs/31902121850)
  的 Change Scope failure，以及
  [旧 run 33246108574](https://github.com/endaye/lmdj/actions/runs/33246108574)
  的 cancelled／空 jobs，都会在原 30 天整窗扫描中被误判为新自测启动失败。
  两个 control 都仍属于 main 历史；用只允许 GET 的真实 API adapter 执行原
  `report_run` 已复现 `reporting-error`，不是用 fixture 代替远端行为。
  旧兼容 run 的原读取链路实测为 5 GET；38 条整窗补扫估算约 192 GET，未含新批次、
  issue 查询与重试，不能把“满窗可见”称为可恢复机制。
- 可信 producer 下界采用已核验 [PR #757](https://github.com/endaye/lmdj/pull/757)
  的 squash `22247897e9163a3f34e15f564bec133419d1f177`。提交时间是
  `2026-09-07T12:20:36Z`，GitHub `merged_at` 是 `12:20:37Z`；扫描保守从前者开始，
  避免 main ref 先于 PR 元数据可见的边界漏扫。时间只优化查询，不能作权限判据。
- 每个 run 另核对 producer→control：`ahead`／`identical` 才进入新协议，`behind`
  才明确跳过为旧实现；`diverged`／未知须显示 why/remedy。control→main 的验证保留。
  因此旧 control 的新 rerun 不会升级成新自测，部署后的启动失败也不会被一起吞掉。
  修改后的 GET-only 复验使上述两条旧 run 明确 skipped、无 error、无写入；这仅证明
  迁移过滤，不证明真实 issue 闭环已经验收。
- 用代码 `recovery_created_filter()` 实际产出的 `>=2026-09-07T12:20:36Z` 调用
  GitHub API，带时分秒的 created 过滤被接受；本次 main completed 查询中 dispatch
  与 schedule 均返回 0 条，原 38 条部署前运行不再进入自动补扫。适配器拒绝所有
  非 GET 与下载请求，只发出两条 GET；未创建 issue、未触发 workflow。
- `workflow_run` 在触发过滤和 job 条件两处限定 main；手动 reporter dispatch 默认
  `reconcile: false`，接入 CLI 的 `--no-reconcile`，允许指定 run 独立恢复；只有主动
  勾选 `reconcile: true` 才整窗补查。自动回调与每日检查仍补扫部署后的保留期窗口，
  保留 100 条上限及显式溢出错误，不承诺自动恢复无限期或任意规模积压。

本轮验证先观察迁移与 workflow 回归为红，再修复到绿；覆盖两条真实 legacy 形态、
旧 control 新 rerun、exact producer 边界、部署后启动失败、未知 ancestry、
实际 CLI 不调用 reconciliation 的隔离重试、真实 Bash 参数接线与非 main 回调过滤。
尚未创建测试 issue、触发自测或完成 O1；根因级指纹与五分钟远端反馈仍未验收。
本轮轻量验证：55 项 reporter、10 项 workflow、6 项 hosted runner policy 测试通过；
集成复验：完整 808 项 CI contracts、pinned actionlint、staged ownership 及 whitespace
检查通过；完整门户检查通过，42 个必需路由及内部链接有效。以上不替代 O1 远端验收。

- [ ] 用受保护默认分支代码处理 workflow completion 和显式重试（`workflow_run`
  只为默认分支上的 workflow 触发，这是安全前提也是部署约束）；
  校验 repository、稳定 workflow 身份、允许事件、run ID/attempt、目标和 artifact。
  不从被测 checkout 加载可执行 reporter；下载解压拒绝路径穿越。
- [ ] 单独 job 最小权限 `contents: read`、`actions: read`、`issues: write`；
  不给测试执行 job issue 写权限，不借用 Queue 的 merge 凭证。
- [ ] 正常 API 下失败后 5 分钟内创建或更新 issue，列 SHA、suite/test、日志／artifact、
  未运行集合、分类、严重程度、负责人和下一步；默认负责人使用明确配置的维护者。
- [ ] 两天同一缺陷只更新一条 issue；同一 observation 重送不重复评论。
  已关闭问题再现可重新打开并记录新观察；一次偶然绿色不自动关闭 flaky issue。
  单写者串行化不能用会丢 pending 的默认队列吞掉通知；短任务须核对未报告 run，
  重启后补齐遗漏 observation，并测试两个不同失败几乎同时完成的情况。
- [ ] API 故障有限退避，保留失败报告和 reporting-error 供显式重试；
  测试红色不因 reporter job 绿色而被摘要掩盖。
- [ ] 完成回调覆盖异常取消／启动失败；另设轻量检查发现“应有日测但根本没启动”，
  不把完全依赖同一个重测试队列的 watchdog 叫独立检测。其自身运行缺失须有
  维护者检查途径，不能声称 Actions 完全不可用时它仍必然告警。
- [ ] 规定每日值守人查看报告，产品缺陷与基础设施故障分别 triage；
  高严重度问题影响适用候选资格，不影响普通 PR 合并。

**验证：** reporter 两套新增测试；恶意日志、重复通知、并发首报、API 403/429/5xx、
丢 artifact、异常取消、漏跑、关闭后复现 fixtures；portal check。
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/

### T4：准备不依赖重测试的 AI review 入口

**分支／commit：** `feat/ci-pr-review-entry` /
`feat(ci): prepare independent PR review feedback`

**新增：** `.github/workflows/pr-review.yml`、
`.github/scripts/pr_review_target.py`、
`tests/build/ci_pr_review_workflow_test.py`。
**修改：** `scripts/ci/scope_policy.json`（登记新 workflow 与 target/publisher 脚本）、
`.github/scripts/advisory_review_liveness.py`、`.github/scripts/grok_review.py`、
`tests/build/ci_advisory_review_liveness_test.py`、
`apps/architecture-portal/docs/operations/testing-and-proof.mdx`、本计划的 T4 范围与验证说明。
旧 `.github/scripts/retire_clean_review_threads.py` 与 Claude command 不改；
现存 Claude／Grok／thread 测试作为兼容性回归运行。

- [ ] 提取现有后端选择、Claude/Grok review 与线程处理所需能力，
  新入口先仅手动验证；不得与旧入口对同一 PR head 长期双写审查。
- [ ] 审查结果绑定 PR 当前 head，过期 head、缺失、超时、API 故障均真实显示；
  给出明确人工接管方法，不用无限自动重试等待 AI 自己通过。
- [ ] 重型 lane 不依赖 review，新 review 也不依赖 scope/full-test/queue ticket。
  不增加不可接管的“解析模型自由文本为通过／拒绝”的硬门禁。
- [ ] 限制审查凭证与 agent 工具能力；仓库文本、PR 描述不能授权 push/merge，
  不让带高权限的 AI 任意执行 PR 提供的代码。
  实现采用可信控制 checkout＋只读模型生成＋独立可信 publisher：Claude 使用
  固定 action 的结构化输出，Grok 增加无评论写入的结构化输出模式；publisher
  验证数据并在发布前后复核 head，以固定 `commit_id` 发布 `COMMENT` review。
  模型不持 PR 写凭据、不执行待审代码、不自行签发完成标记。
- [ ] 监控以确切 workflow run 和 head 绑定为准，空 check rollup、NEUTRAL 或旧 head
  不算审查完成；保留最新主干已修复的 merge-ref 可见性约束。
- [ ] 写明 AI 线程与 `required_conversation_resolution` 的关系：切换后 Pre-heavy Gate
  的线程准入随重型 lane 消失，但 conversation resolution 仍是 required，AI 线程因此
  仍阻塞合并，直到人工 resolve——这就是 spec §4.1 的“人工接管”，不是新门禁。
  clean review 不得留下未解决线程（#707 的约束继续有效）。
  新 publisher 对 clean review 使用 `comments=[]`，不依赖旧清理脚本；
  新入口证据绑定 repository／PR／head／run／attempt／backend，监控核对 bot review
  与 publisher 结果。dispatch 的控制 SHA 不冒充被审查 head，旧 CI 路径保持兼容。

**验证：** `ci_pr_review_workflow_test.py`、`ci_advisory_review_liveness_test.py`、
`ci_grok_review_workflow_test.py`、`ci_claude_review_workflow_test.py`、
`ci_retire_clean_review_threads_test.py`、`ci_change_scope_test.py`、
`ci_workflow_topology_test.py`（均在 `tests/build/`，用 `python3` 执行）；
`pr-review.yml` 的 actionlint；集成提交前 portal check。
行为测试覆盖错误身份／跨 run 或 attempt／伪签名、发布前 stale 拒绝、
发布过程中 head 变化、模型文本只作数据、缺凭据不复用旧产物、clean 无 inline thread。
本地测试不代表真实 review 已完成；O1 仍需授权验证第三方后端结构化输出、
dispatch→artifact→发布→liveness、运行期间 head 更新、缺凭据／API 故障及人工 resolve。
固定 action 的 [agent mode 源码](https://github.com/anthropics/claude-code-action/blob/fa2b2666b747000bf42767d1f332065b375e3c8f/src/modes/agent/index.ts)
与 [action 接口](https://github.com/anthropics/claude-code-action/blob/fa2b2666b747000bf42767d1f332065b375e3c8f/action.yml)
支持显式 prompt／`structured_output`；其 buffered inline publisher 不从 dispatch inputs
取得 PR_NUMBER，因此本实现不伪造事件，而由独立 publisher 显式接收已解析的 PR 身份。
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/

### O1：切换前验收，尚不移除 required checks

- [ ] 维护者授权一个真实 main SHA 的新全量批次；记录 suite 完整集合和终态。
  产品已知失败可以如实报告，但必须证明整套调度／汇总／报告链路可工作。
- [ ] 授权隔离演练目标与测试 issue，复演首报 → 重送 → 再现 → API 故障 → 重试；
  不将 mock 通过描述为真实 GitHub side effects 已验证，不污染正式问题列表。
- [ ] 验证 review 新入口同一 head、过期 head、人工接管三条路径。
- [ ] 旧 `ci.yml` 手动 full 入口**只能证明 dispatch 那一刻的 main tip**：
  `workflow_dispatch` 的 ref 不能是 SHA，旧 verifier 又要求 `run.head_sha == target`。
  这是定论，不是待核实项。因此 **T7 排在 O2 之前**：切换后的第一个候选就能指定
  任意已自测的 main SHA。若 T7 确实来不及，过渡期规则只有一种：候选 = dispatch 时的
  tip，且操作者在候选记录里人工附上同 SHA 的 TSan／Release stress run 链接，
  因为旧 full manifest 不证明 Nightly 已覆盖。不伪造 event/head_branch 绕过验证器，
  也不切换到没有可用候选验证路径的状态。
- [ ] 记录双跑截止、操作者、现行保护规则备份、现有队列 ticket 处置清单、
  scheduled 时间与资源预算。证据缺失时停在这里，旧门禁保持有效。

### T5a：工作流切换 diff

**分支／commit：** `feat/ci-optimistic-merge-cutover` /
`feat(ci): separate optimistic PR merges from self-tests`

**修改文件：** `.github/workflows/ci.yml`、`core-nightly.yml`、
`merge-queue.yml`、`advisory-review-liveness.yml`、`pr-review.yml`、
`self-test-report.yml`；对应 workflow contract tests。

T5 按§2 的规则拆成 T5a（工作流）与 T5b（治理、skill、模板、preflight、门户），
两者在同一 O2 窗口内先后合入；T5a 不带治理文本，T5b 不带 workflow。

- [ ] 提交可审查的切换 diff 和 O2 runbook。此 PR 的 `pull_request` run 执行的是
  PR 自己的 `ci.yml`；一旦它不再在 PR 事件产出 `PR Gate`、`core (ubuntu-latest)`、
  `core (macos-latest)`，在旧保护规则下永远不能绿。因此本 PR **在 O2 移除这三个
  required contexts 之后才合入**，见 O2 的前置判据。
- [ ] 切换后 PR 仅自动做 AI review 和可选轻量 advisory；普通 main push 不再启动产品全量。
  保留旧 `ci.yml` 的显式 full 候选入口及其真实 scope/gate，直至 T7 迁移通过。
  同次切换启用新 review 的 PR 事件并停用旧 review，避免对同一 head 重复审查。
- [ ] 自测入口（T2 扩展后的 sweep）接管每日 16:00 UTC 及重要节点；同时停用其余
  自动全量与队列 cron：`merge-queue.yml` 每 15 分钟、`core-nightly.yml` 19:00；
  接线 T1 的无新目标去重，并实现普通日测 pending 的目标核对，不能吞掉显式请求；
  `advisory-review-liveness.yml` 21:00 改为监视新 review 入口或一并退役，不能留着
  监视一个已不存在的 job。不保留两套自动全量。显式候选仍独立于普通 pending 的合并规则。
- [ ] 停止旧 queue 新 ticket 入口和 watchdog 自动补发；明确已在途 ticket 的完成、
  停止或人工交接，旧 label 不再被任何新代码解释为新的合并授权。

**验证：** 全 `ci_*_test.py`，release CI evidence 回归；
静态扫描所有活跃消费者的 queue/required/strict/full-test 假设。
Documentation impact: none — 工作流 diff 的门户说明由 T5b 同窗口交付；
若 T5b 不能在同一窗口合入，T5a 不得单独留在 main 上过夜。

### T5b：治理、skill、模板与 preflight 的一致说明

**分支／commit：** `docs/ci-optimistic-merge-governance` /
`docs(ci): describe optimistic merges and self-tests as the current workflow`

**修改文件：** `AGENTS.md`、`CLAUDE.md`（若有同义约束）、
`docs/governance/git-workflow.md`、`architecture-portal.md`、
`github-work-management.md`、`docs/quality/core-test-policy.md`；
`.agents/skills/issue-done/SKILL.md`、`issue-list/SKILL.md`、
`.github/pull_request_template.md`、`scripts/ci/local_preflight.py`；
对应 skill/preflight contract tests 及两个 operations 门户页面。

- [ ] 更新 skills 与 PR 模板：不再为合并等待全量／反复 update main／发 queue ticket；
  task-specific 本地验证保留，但不得强制执行所有产品 lanes 后才允许 push/merge。
- [ ] pre-push 的重型检查变为显式 opt-in；已有 hook 的迁移给出可识别、可恢复方案，
  只替换本工具安装的 hook，不覆盖个人 hook，不自动遍历修改用户 worktree。
- [ ] 调整 portal check 的位置与治理说明：仍是受影响任务的本地验证和自测 suite，
  不留下“全量门户生产构建必须远端绿色才能 merge”的隐形门禁。
- [ ] 门户区分 main 集成状态与版本资格；涉及的内嵌流程图随页面更新，
  若现有架构源图实际引用旧流程则同 Task 更新，禁止改历史快照或手写生成图。
- [ ] 治理文本以 O2 实际切换为生效点；在 T5a 合入前不得先落地“main 允许暂时不稳定”
  的表述。

**验证：** skill/preflight contract tests，portal check。
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/ /operations/version-and-release/

### O2：明确授权后的规则切换

- [ ] 再次读取 live protection/rulesets，确认没有其他约束覆盖此次修改；保存精确旧配置。
- [ ] 停止队列接收新请求，逐个核对既有 ticket 的授权与状态，不批量盲目合并。
- [ ] 在新自测、报告、review 和 T7 候选证据 ready 的前提下，移除旧三个 required
  contexts，关闭 strict up-to-date；保留 PR、冲突、必要对话和其他未获准修改的保护。
- [ ] **前置判据**：`gh api repos/endaye/lmdj/branches/main/protection` 的
  `required_status_checks.contexts` 不再含 `core (ubuntu-latest)`、`core (macos-latest)`、
  `PR Gate`，且 `strict` 为 `false`——满足后才合入 T5a，再合入 T5b。
  不在 YAML 上创建假的同名成功 context 来填空。
- [ ] 若 T5a／T5b 不能在约定窗口内合入／生效，恢复备份并停止，不把中间状态留到无人值守。
- [ ] 复核六个已获各自合并授权、当前 head 已审查、无冲突的 PR：即便落后 main，
  日测在途或红色，也可合并；记录每次实际 merged SHA 和等待时间。
- [ ] 本步骤完成后停止；不顺带发布、删除用户分支或变更 runner 主机。

### T6：删除已退役的队列依赖

**分支／commit：** `fix/ci-retire-merge-queue` /
`refactor(ci): retire integration queue control paths`。

**目标文件：** `.github/workflows/merge-queue.yml`、
`scripts/ci/merge_queue.py`、`github_queue_api.py`、`merge_queue_watchdog.py`；
`ci.yml` 中 queue 输入、ticket 工件与 pre-heavy review gate；
`scripts/ci/change_scope.py`、`pr_gate.py`、`phase_gate.py`、
`scope_policy.json`、对应 queue/phase/classification tests、受影响门户页面。

- [ ] 先列引用和现有消费者，确认无在途旧授权；仅删除确实专属 queue 的文件与测试。
  通用 GitHub API 或新 self-test 已复用的逻辑先迁移，不能连新报告一起删掉。
  因为 T2 扩展的是 `ci.yml` 而非平行 workflow，本 Task 不含“消除复制的 job 定义”；
  若 T2 最终分离了 workflow，把该项加回这里。
- [ ] 保留旧手动 full 入口在 T7 前仍需的 Change Scope、PR Gate 和 scope artifact；
  名称虽有 PR，当前仍是 release 证据依赖，不能按名称一并删除。
- [ ] 保留测试资产而非盲删所有旧测试：有效身份、安全、所有权与 failure readability
  断言移到新控制面；只退休旧 queue 行为断言。
- [ ] 不在本 Task 增加新的 merge controller，也不顺手提高物理主机并发。

**验证：** 全 CI contract + release evidence 回归；无活跃 queue 调用；
portal check。
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/ /operations/version-and-release/

### T7：发布验证器接入完整日测证据（排在 O2 之前）

**分支／commit：** `feat/ci-self-test-release-evidence` /
`feat(release): verify complete self-test evidence for exact candidates`

**修改文件：** `tools/release/ci_evidence.py`、`github_api.py`、
`model.py`、`policy.json` 及实际消费它们的 audit/prepare 接口；
`tests/build/release_ci_evidence_test.py`、`release_github_api_test.py`、
`release_audit_test.py`、`release_prepare_test.py`、`release_model_test.py`；
`.agents/skills/lmdj-release/SKILL.md`、`docs/governance/version-management.md`、
release pipeline spec、版本发布门户页面；必要时修改 T1/T2 的证据 producer。

- [ ] 实现新旧显式版本分支，不仅扩大 event allow-list：新证据核验可信稳定 workflow、
  控制修订、目标 main SHA、run/attempt、完整 policy suite 集合、全部 required 结果、
  artifact 摘要和有效保留期；workflow 名称或绿色总结文本不是证据。
- [ ] 允许可信 schedule 或手动 self-test 被 Owner 为同 SHA 候选显式引用；
  `target_revision` 来自受信 manifest，不能从新 target input 猜测其等于
  GitHub `run.head_sha`——T2 之后两者对旧 SHA 候选必然不同。
- [ ] 优先单批次汇总全套 suites；若平台实现必须跨 runs，枚举每个成员的
  workflow/run/attempt/target 和结论，不用任意两个绿色 run 拼成“全量”。
- [ ] 缺少 TSan/Release stress、requested/focused、失败、未运行、错误 SHA、
  不可信控制代码、过期／不可读 artifact、混合 attempt 一律拒绝。
- [ ] 保留历史已发布 intent 的只读审计语义；证据保留期到期不改写已发布历史。
  新候选缺失有效证据则重新补测，不能借历史豁免绕过 prospective 核验。
- [ ] 旧兼容入口仅在新 producer + consumer 真实演练通过后退休；
  当切换 prospective policy 时不再允许只含旧 14 lanes 的证据绕过新全量定义。
- [ ] release 操作者仍先做 fresh exact-tag remote audit，沿稳定 `scripts/release.sh`
  接口逐边界执行；测试通过不调用 prepare/push-tag/create-draft/publish/deploy/promote。
  保留刚落地的显式 `hydrate` 与只读 audit 分离。
- [ ] 不自动修改 release intent、分配 Product Build 或产出永久门户快照。

**验证：** 全 `release_*_test.py` + 新 self-test 协议测试、skill tests、
portal check；真实候选的只读证据演练需另获授权，不以测试替身代替。
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/ /operations/version-and-release/

### T8：按测量收缩资源与重复执行

**分支／commit：** `fix/ci-self-test-capacity` /
`perf(ci): bound self-test work to measured host capacity`

**声明范围：** 新 self-test workflow、实际使用的 reusable actions、
`scripts/ci/host/` 的相关配置（如需）、对应 runner/topology tests、
测试门户页面；实施前按实测选定精确文件。

- [ ] 回看七天历史可用数据并报告样本数、负载来源、冷／热缓存、排队与执行耗时；
  PR #737 的拥堵样本只作为 burst，不把它当平日均值。
- [ ] 列物理主机上的 Native/Web/Portal/Nightly 共驻关系。
  保留现有隔离直到替代方案被验证；只给 TSan 加锁不代表主机独占。
- [ ] 如果合并 native 阶段到一次 admission，验证父任务持锁不会等待同锁子任务；
  不为节约等待把覆盖率 profile 或构建目录跨并发批次共享。
- [ ] 删除已经无消费者的旧自动全量副本、轮询和多余触发；不先采购主机或取消安全锁。
- [ ] 主机安装／systemd／ASLR 修改属于单独授权的运维动作，不由 PR 合并隐式执行。
- [ ] 承接 spec §9 的统计口径：runner 分钟、日测结论年龄、未完成请求、问题去重与
  修复耗时的数据来源与保留位置在本 Task 定下（可以只是 artifact 或 issue 评论模板），
  O3 据此报数；没有数据来源的指标不写进 O3。

**验证：** 受影响 contract tests、同主机重叠运行的受控测量、portal check。
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/

## 5. O3：最终验收矩阵

下列是实施后证据，不是本计划文档检查的结果。

| Spec 场景 | 负责 Task | 必须看到的后置事实 |
| --- | --- | --- |
| 落后 main 无冲突 PR | T5a/O2 | 不 update、不等全量，当前 head 审查后实际 merged SHA 可查 |
| review 缺失／失败／旧 head | T4/O1 | 可见真实状态，人工接管有记录，旧结论不冒充当前 |
| 六 PR 与重型日测并行 | O2/T8 | 各自授权的合并完成，重型等待不出现在 merge 依赖中 |
| A 运行时 B 合入 | T2/O1 | A 全部结果仍属于 A；B 未被假记为已覆盖 |
| 重复／延迟触发 | T1/T2 | 最新普通目标保留，显式候选不被替换 |
| 同缺陷连续两天 | T3/O1 | 同一个 issue 两次观察，重送不增重复 issue/comment |
| build 失败 | T2/T3 | 全批未通过且列 not-run 集合；普通 PR 仍可合并 |
| issue API 故障 | T3/O1 | 测试 verdict 不变，reporting-error 可见，恢复重试只写一次 |
| 修复后节点自测 | T2/T3 | 固定新 SHA 完整报告，旧失败仍可查 |
| 日测通过但无发布指令 | T2/T7 | 无 tag/Release/deploy/promotion 调用和实际变更 |
| 选择已验证候选 | T7 | 同 SHA 完整有效证据可复用，构建产物仍绑定该候选 |
| 新／失败候选 | T7 | 候选拒绝或补测，不影响普通 PR |
| schedule 协议迁移 | T7 | 旧协议明确拒绝，新协议仅接受完整可信证据 |
| 混合重型负载 | T8 | 物理隔离实测成立，断言、floor、stress 次数未削弱 |
| §9 指标可报数 | T8/O3 | 每项指标有数据来源与样本数；缺样本的指标标为未测而非达标 |

初始观测目标：产品全量导致的 PR merge 等待为 0；review 完成且获授权后无冲突
合并通常不超过 3 分钟；AI review p90 目标 10 分钟（含故障接管统计）。
每个有新 main 的日测日有目标结论或明确漏跑告警；正常 API 下失败报告 5 分钟内。
全量执行 p90 先以 90 分钟为优化目标，排队单列；没有足够样本不宣称已达到。

回退仅针对新自动化自身失效（漏跑不报、错误证据被接受、越权 mutation、报告风暴等），
普通产品测试失败不是恢复全量 PR 门禁的理由。若必须恢复旧门禁，
先恢复并验证其 producer，再恢复 required contexts/strict；不能制造永远 pending 的检查。

## 6. Documentation Impact

本次计划文档 Task：
Documentation impact: none
Reason: 仅新增实施计划，不修改 current 门户页面、实际 CI、发布资格或产品行为。

执行本计划：
Documentation impact: required
Affected portal pages: /operations/testing-and-proof/ /operations/version-and-release/
Reason: T2 起的操作行为及 T5/T7 的合并、测试和发布证据边界必须同步反映到 current 页面。
每个 Task 按上文范围修改页面及实际受影响的源图；不改写 immutable snapshots。

## Version Management

Version impact: none
Reason: 本计划及所列 CI 控制面重构不改变 Product、Module、Host、Provider、
Contract、Assembly 或 Channel 身份；不分配 Product Build，不创建 tag。
CI 内部 evidence schema 演进按 producer/consumer 兼容迁移处理，不冒充产品 Contract 变更。

若后续候选准备需要 Product Build 或 Assembly 变更，另开版本 Task，
遵循现行 version policy 和不可变门户快照义务，不混入本计划的 CI Task。

## 7. 提交与验证约定

每个 Task：核对非 main 分支 → task-specific tests → portal check →
仅 stage 声明文件 → 完整 staged diff 与 whitespace 检查 →
有新文件时在 staging 后运行 ownership suite → Conventional Commit →
核对 committed files 与 clean status。push/PR/merge 不从本地 commit 推导授权。

本次声明文件仅为：
`docs/superpowers/plans/2026-09-07-lmdj-ci-capacity-redesign.md`。

本次文档验证：
`git diff --cached --check`；
`python3 tests/build/ci_change_scope_test.py`（stage 后）；
`scripts/architecture-portal.sh check`；
核对计划引用与 spec 的 14 条验收覆盖。
这些检查不证明上述未来 workflow 或远端流程已实现。

实施 Task 的共用回归命令：

```bash
python3 -m unittest discover -s tests/build -p 'ci_*_test.py'
python3 -m unittest discover -s tests/build -p 'release_*_test.py'
scripts/architecture-portal.sh check
```

只运行与 Task 风险相称的组合；未来新增测试路径在对应 Task 创建后才可执行。
actionlint 使用仓库 CI contract 固定版本及既有 schema 例外，不另装随意版本。

Pitfall impact: none — reason: 本计划应用现有容量、身份、报告与发布顺序知识，
没有执行新的远端故障或把历史观察当作新 recurrence。实施时新发现按 ledger 另行记录。
