# Stage 12 独立交付与剩余任务计划

日期：2026-09-10。状态：用户已同意独立立项并要求创建任务、更新核心重设计 §23。
总追踪 [#472](https://github.com/endaye/lmdj/issues/472)。
依据：[范围决策](../prd/decisions/2026-09-10-stage12-independent-delivery.md)；
[核心重设计 §23](../design/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md#23-交付顺序)。

## 目标与完成边界

保留 Stage 12 原有 Slice、Stem、Pattern 三项总目标，以 12A/12B/12C
分别规划和验收，不重新编号 Stage 0–11。12A 可形成独立交付结论；
总追踪仍等待三个分支各自的完整验收，不能由 Slice 完成替代。
先推进 Slice 验收；Stem 可行性设计、Pattern 产品设计可并行准备。
设计开始不代表对应模型、Contract、运行环境或采纳语义已批准。

已有 K1–K5（#1033–#1037）、L1–L5（#1038–#1042）全部 CLOSED；
它们是 Slice 参考执行与采纳链路的实现证据，不是生产质量结论。
已确认的 [Slice 决策](../prd/decisions/2026-09-09-stage12-contract-candidate.md)
保留 reference/test 平台边界、单 SDK Candidate 与 Facade Workspace recipe
所有权。当前算法无模型 checkpoint；同进程 elapsed 观测不证明硬 timeout 或
单次 Attempt 独立 RSS。现有 smoke 标签/容差和严格性保持不变。

#466 虽已关闭，原始 benchmark 范围中的完整语料、执行区资源测量与
Stem/Pattern 人工评测仍须按下表归属；S5 核对历史状态与责任，不能倒推
全部完成。#467/#471 仍是设计父任务，S5 按其自己的验收核销。

## 任务列表与依赖

| 分支 | Issue | 交付边界 |
| --- | --- | --- |
| 12A | [#1163](https://github.com/endaye/lmdj/issues/1163) | Slice 参考能力验收与独立交付 |
| 12B | [#1164](https://github.com/endaye/lmdj/issues/1164) | Stem 分离独立设计、评测与交付 |
| 12C | [#1165](https://github.com/endaye/lmdj/issues/1165) | Pattern Intelligence 独立产品设计与交付 |

| Task | Issue | 状态/依赖 | 输出 |
| --- | --- | --- | --- |
| S1 | [#1166](https://github.com/endaye/lmdj/issues/1166) | Ready Machine | S1 整理固定候选的完整验收包与判定口径 |
| S2 | [#1167](https://github.com/endaye/lmdj/issues/1167) | Physical / Manual; after S1 | S2 完成 Windows Creator 实际操作与听感验收 |
| S3 | [#1168](https://github.com/endaye/lmdj/issues/1168) | Blocked on S1 | S3 扩展代表性语料并测量切片质量与耗时 |
| S4 | [#1169](https://github.com/endaye/lmdj/issues/1169) | Architecture / decision after S2/S3 | S4 裁定参考算法适用范围与后续产品化任务 |
| S5 | [#1170](https://github.com/endaye/lmdj/issues/1170) | Blocked on S4 and blocking fixes | S5 对齐验收结果、Portal 与设计父任务状态 |
| T1 | [#1171](https://github.com/endaye/lmdj/issues/1171) | Ready design preparation; decisions explicit | T1 定义最小使用场景、执行边界与评测计划 |
| T2 | [#1172](https://github.com/endaye/lmdj/issues/1172) | Blocked on approved T1 | T2 运行可复现候选评测并形成实施拆分 |
| P1 | [#1173](https://github.com/endaye/lmdj/issues/1173) | Ready design preparation; product confirmation required | P1 定义候选范围、预览与安全采纳语义 |

顺序：S1 → S2 与 S3 → S4 → 阻塞缺陷修复/重验（若有）→ S5。
T1 → 获评审的范围/环境/预算 → T2 → 选型及后续实施计划。
P1 → 产品确认 → 后续 Contract/实现/音乐性验收任务。
S2 是人工任务；S4 是产品决策；T1/P1 的研究准备可由代理完成，
未决产品语义仍需确认。#535 是模型生成 Pattern 事件的既有问题，继续复用。

共享文件不能并行争用：S1 拥有 Slice acceptance 初稿，S5 在其完成后更新；
S2/S3 用独立报告；T1/P1 分别使用独立设计/计划文件。新增 source/harness/
fixture 路径在实施前补齐精确清单，不能把下面的边界理解为无限文件授权。

## 每项任务的文件与最低层验证

### S1 — 整理固定候选的完整验收包与判定口径

从已合并版本中核定一个可追溯候选，整理既有 K/L 证据、合法素材、Windows 浏览器操作步骤、失败场景与结果模板。在评测前明确质量用例、判定口径及平台范围；未确认的产品阈值标为待确认，相关结果仅作探索性证据。S4 按既定口径裁定适用性，不能看完结果再降低标准。

声明文件：

- `docs/quality/2026-09-10-stage12-slice-acceptance.md`
- `docs/quality/evidence/stage12-slice/README.md`

验收：

- 记录 Build、完整 source commit、分发物 digest/长度和快照来源；从 manifest 获取身份，不猜数字，不在本任务重新分配 Build。
- 逐步列出成功、失败、取消/重试、discard/supersede、停止、刷新、重启/重开，每步有转换后的状态断言。
- 明确原素材 hash/length、目标 Assets/Lineage、Project revision、原 Pattern 事件的前后证据。
- 区分执行过的自动化、预期失败/跳过、物理听感和未执行平台；不将 WSL 测试标为 Windows 浏览器测试。

验证：检查现有测试/报告的 exact-source 适用性与完整旅程映射；Markdown 相对链接、docs-site check。没有产品行为变化，不重跑无关全量 CI。

Version impact: none（以上规划/评测/验收文件）；如产生产品代码修复则独立
Task 按当时 manifest 分配版本，不沿用旧号。
Documentation impact: none
Reason: 保留设计、计划或验收材料；实际产品源事实/可用性变化另按受影响页面声明。

### S2 — 完成 Windows Creator 实际操作与听感验收

由用户在真实 Windows 浏览器操作和听音，代理协助复现、检查与留证。使用 S1 固定候选和合法素材；环境不支持时如实记录 capability refusal。Windows 可测不等于已经支持或验收通过。

声明文件：

- `docs/quality/2026-09-10-stage12-slice-windows-acceptance.md`
- `docs/quality/evidence/stage12-slice/windows/README.md`

验收：

- 记录 OS、浏览器、设备/音频输出、Build/source/distribution 身份、origin 与浏览器能力检查；WSL 构建环境单列。
- 实际走分析→候选→试听→停止→明确目标→采纳一次→保存→刷新/重开；每一步核对实际音频/状态，不能以 played 回执替代听音。
- 覆盖无 onset、重复目标、stale/source/unavailable、配额拒绝及未知提交结果先 inspect；难以 UI 触发的腿引用固定候选的 companion 自动化证据并标明边界。
- 重开后核实源 hash/length、完整 lineage、原 Pattern 事件和一次 revision；失败整体零变更。
- 每个缺陷有复现与责任 Issue；不声称 Windows 覆盖 macOS/iPadOS Safari 或 Native 物理音频。

验证：完整人工旅程与录屏/结果表，精确候选上的 companion 自动化日志；对修复只重验受影响腿并保留全旅程适用性。

Version impact: none（以上规划/评测/验收文件）；如产生产品代码修复则独立
Task 按当时 manifest 分配版本，不沿用旧号。
Documentation impact: none
Reason: 保留设计、计划或验收材料；实际产品源事实/可用性变化另按受影响页面声明。

### S3 — 扩展代表性语料并测量切片质量与耗时

复用已交付 score_slice.py、validate_report.py 和真实 Registry/AttemptStore 执行；增加可再现的评估素材，保留既有 smoke 标签/容差。运行入口或 elapsed collector 有缺口时先补精确文件清单，再实施；不重建通用 benchmark 框架。

声明文件：

- `tools/provider-benchmark/generate_sample_slice_evaluation.py`
- `tools/provider-benchmark/tests/sample_slice_evaluation_test.py`
- `tests/fixtures/provider-benchmark/sample-slice-evaluation/manifest.json`
- `tests/fixtures/provider-benchmark/sample-slice-evaluation/LICENSE.md`
- `tools/provider-benchmark/README.md`
- `docs/quality/2026-09-10-stage12-slice-evaluation.md`

验收：

- 覆盖力度差异、尾音重叠、密集瞬态、静音、单/双声道及支持采样率；按构造有独立真值和明确 License。
- 报告逐类 TP/FP/FN、precision/recall/F1、重复输出字节和 elapsed/RTF，身份包含候选、参数、素材、环境、harness。
- in_process_reference 的硬 timeout/独立 RSS/GPU 记 not_enforceable 或适用的 N/A，不能报 0/pass；需要硬资源保证另立隔离执行任务。
- 不把 smoke F1 或自报资源当作生产资格；针对 S1 预定口径保留失败，不改标签或放宽阈值。

验证：新增 generator/component 测试验证真值与再生一致；现有 report_test.py、score_slice_test.py；真实 execute 双跑并以既有 scorer/validator 检查；新增路径 staged ownership。

Version impact: none（以上规划/评测/验收文件）；如产生产品代码修复则独立
Task 按当时 manifest 分配版本，不沿用旧号。
Documentation impact: none
Reason: 保留设计、计划或验收材料；实际产品源事实/可用性变化另按受影响页面声明。

### S4 — 裁定参考算法适用范围与后续产品化任务

依据实际操作、听感和代表性报告裁定 Slice 的适用范围。当前实现是确定性算法，不需要模型 checkpoint。提出保留 reference/test、改进算法或经平台实测后扩展支持的可评审选项。

声明文件：

- `docs/prd/decisions/YYYY-MM-DD-stage12-slice-availability.md`

验收：

- 产品负责人确认用途、质量结论与平台范围，决策引用不可变的实测证据。
- 未达标项逐个拆小缺陷/改进任务，列精确文件、最低层测试、版本/Portal 影响；既有缺陷先去重。
- 生产声明仍不满足时明确记录 reference-only 结论和独立责任任务；不得把“暂无阻塞”当作生产通过。
- 平台 token/default policy/硬资源保证的变更都单独设计与验证，不随评测自动晋级。

验证：证据—结论交叉审查；产品确认后才写已确认 decision；文档链接和 docs-site check（若影响当前源事实）。

Version impact: none（以上规划/评测/验收文件）；如产生产品代码修复则独立
Task 按当时 manifest 分配版本，不沿用旧号。
Documentation impact: none
Reason: 保留设计、计划或验收材料；实际产品源事实/可用性变化另按受影响页面声明。

### S5 — 对齐验收结果、Portal 与设计父任务状态

逐条核对 #467/#471 的设计与计划验收，更新已过时的 Provider/Host 说明、12A 完成矩阵及 #472 追踪关系。S4 的阻塞修复完成并重验后才结算 12A；生产后续任务保持可见。

声明文件：

- `docs/quality/2026-09-10-stage12-slice-acceptance.md`
- `docs/plans/2026-09-10-stage12-independent-delivery.md`
- `apps/docs-site/docs/providers/overview.mdx`
- `apps/docs-site/docs/providers/local-sample-slice.mdx`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `apps/docs-site/docs/product/workflows.mdx`

验收：

- 每个验收条目有固定源证据；设计父任务的关闭依据是自身完整验收，不是子 Issue 都关闭。
- Portal 反映真实已交付 Slice 流程及 reference/test 限制，身份从清单派生；必要的实际受影响页面/图先加入文件清单。
- 12A 只声明其明确验收范围；#472 在 Stem/Pattern 未交付时继续开放，既有未执行平台和生产缺口不被删除。
- 核对 #466 历史关闭与剩余 benchmark 责任，缺失项指向 12A/B/C 具体任务；无法归属的工作保留为缺口，不追认完全交付。

验证：scripts/docs-site.sh check、PR declaration/closing-directive lint；live Issue acceptance 对照。

Version impact: none（以上规划/评测/验收文件）；如产生产品代码修复则独立
Task 按当时 manifest 分配版本，不沿用旧号。
Documentation impact: required
Affected portal pages: /providers/ /providers/local-sample-slice/ /hosts/creator-web/ /product/workflows/

### T1 — 定义最小使用场景、执行边界与评测计划

制定独立 Stem 可行性评测方案，提出一种分离配置的首版建议。比较本地/隔离进程/远端的约束，明确可用音频长度、输出角色、资源/成本和许可要求；不默认云端、GPU 或下载模型。

声明文件：

- `docs/design/2026-09-10-stage12-stem-scope.md`
- `docs/plans/2026-09-10-stage12-stem-evaluation.md`

验收：

- 目标用户场景与输入/输出范围可评审；checkpoint/执行环境/阈值等未确认项逐项列出。
- 候选清单有可追溯来源、不可变 revision/checksum 和许可适用性，不复活旧 demo 作为产品实现。
- 评测设计区分客观 stem 真值、盲听、确定性、RTF、适用 execution-zone 资源测量。
- T2 获得精确文件、运行命令、环境、预算及需要的批准边界；研究可以并行于 Slice 验收，不宣称生产可用。

验证：设计与已批准 benchmark execution-zone 规则逐项对照；链接、许可/身份材料审查；形成实现前 Task inventory。

Version impact: none（以上规划/评测/验收文件）；如产生产品代码修复则独立
Task 按当时 manifest 分配版本，不沿用旧号。
Documentation impact: none
Reason: 保留设计、计划或验收材料；实际产品源事实/可用性变化另按受影响页面声明。

### T2 — 运行可复现候选评测并形成实施拆分

按获评审的 T1 计划运行候选评测，提交可行性结论与下一批实现任务。实际 harness/fixture/受限素材 manifest 的精确路径由 T1 先定稿，本 Issue 在那之前不可当作代码施工单。

声明文件：

- `docs/quality/2026-09-10-stage12-stem-feasibility.md`
- `docs/plans/2026-09-10-stage12-stem-implementation.md`

验收：

- 留存可复现环境/不可变候选/许可/输入身份，真实质量与性能测量、盲听材料及适用的人工结果。
- 资源测量遵循执行区边界；未授权付费算力、服务或模型条款须先解决，不自行扩大范围。
- 报告可淘汰候选但不自动晋级；产品选择单独确认，未选择可记录 no-go 或补证据结论。
- 若进入实现，创建 Contract、Provider/执行、Stem Candidate/Lineage/配额、Host、Assembly/验收等依赖明确任务；每个先写 exact files/tests/versions/Portal impact。

验证：T1 指定的真实 execute、报告 validator、独立指标与盲听程序；失败与未执行项显式保留。

Version impact: none（以上规划/评测/验收文件）；如产生产品代码修复则独立
Task 按当时 manifest 分配版本，不沿用旧号。
Documentation impact: none
Reason: 保留设计、计划或验收材料；实际产品源事实/可用性变化另按受影响页面声明。

### P1 — 定义候选范围、预览与安全采纳语义

独立设计 Pattern Intelligence，先评审规则 Drum Groove/Fill 和新 Pattern Slot 的最小方案。评估预览上下文、Pad Role/BPM/Key、tick 边界、来源持久化、revision/配额与拒绝语义；Merge/替换不暗中实现。

声明文件：

- `docs/design/2026-09-10-stage12-pattern-candidates.md`
- `docs/plans/2026-09-10-stage12-pattern-implementation.md`

验收：

- 将已确认规则与首版建议分开；#535 保持模型事件生成的唯一产品问题，不因本 Issue 开始而提前关闭。
- 明确不覆盖原用户演奏事件的可测试定义，所有事件引用 Pad Slot；Pattern 采纳不照搬音频 recipe 或 Asset.lineage。
- 明确候选保存/预览/丢弃/重启与新槽、Merge、替换的首版支持及延期边界，先获得产品确认。
- 按批准范围创建 Contract/领域校验、候选与采纳、Host/UI、音乐性/持久化验收任务，逐项 exact files/tests/versions/Portal impact。

验证：设计的成功/冲突/失败矩阵与原 Pattern 保存不变量审查；链接与文档验证，未批准前无产品实现。

Version impact: none（以上规划/评测/验收文件）；如产生产品代码修复则独立
Task 按当时 manifest 分配版本，不沿用旧号。
Documentation impact: none
Reason: 保留设计、计划或验收材料；实际产品源事实/可用性变化另按受影响页面声明。


## 本次规划变更

一个 documentation Task，声明文件：

- docs/design/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md（§23）
- docs/plans/2026-07-30-lmdj-headless-core-proof.md（当前交付入口链接，保留 Proof 历史）
- docs/plans/2026-09-10-stage12-independent-delivery.md（本计划）
- docs/prd/decisions/2026-09-10-stage12-independent-delivery.md
- docs/quality/2026-08-17-machine-task-todo.md（当前任务入口）
- docs/quality/2026-08-17-manual-verification-todo.md（人工/决策入口）

GitHub：创建上表 3 个 umbrella 与 8 个任务，更新 #472 的目标/已交付/剩余
关系，并回读验证。保留已有设计父任务和产品问题；此 Task 不执行它们的
验收或产品设计。不预先制造“算法必须重写”等没有复现证据的缺陷任务。

最低层检查：修改文档的相对链接、任务 Issue/父子/依赖映射、§23 与总追踪
的一致性；staged 新文件执行 `python3 tests/build/ci_change_scope_test.py`；
PR body 执行 `python3 tests/build/ci_pr_body_lint.py --body-file ...` 与
`scripts/local-ci.sh --declaration-only --pr-body ...`。
因计划引用已交付源事实，执行 `scripts/docs-site.sh check`。
不新增门禁或产品测试；每个后续 Task 若新增门禁，须命名其捕获缺陷。
Pitfall impact: none；应用完整旅程、实际听音与安全相关 Issue 引用规则。

## Version Management

Version impact: none
本次只有计划、范围决策和任务入口，不修改 Product、Module、Provider、
Contract 或 Assembly 身份，不分配测试 Build、快照或 Release。
S1 选择已有可追溯候选；需要新 Build 时另行计划身份与不可变快照。
未来实现的 Module/Contract 版本、依赖闭包与 Product Build 按实际改动分配。

## Documentation Impact

Documentation impact: none
Reason: 本次修改 retained 设计/计划/任务入口，不改变当前 Portal 可用性、
页面或身份。已存在的过时 Provider 页面明确由 S5 修正；本次不宣称修正完成。
未来产品、Assembly/Build 变更必须在同一 Task 更新受影响 Portal 页面、
必要 source diagrams 和不可变快照；不允许以计划链接替代这些义务。
