# LMDJ Stage 12 Provider Benchmark and Fixture Corpus Design — 2026-08-31

日期：2026-08-31

状态：**已评审，待实施**——本文是
[#466](https://github.com/endaye/lmdj/issues/466) 的设计半部：定义 Stem /
Slice / Pattern Intelligence 的评估问题、fixture 语料策略、指标与硬拒绝
阈值、复现身份与报告格式。不选定任何生产 checkpoint，不实现 Provider。

评审结论（2026-09-03）：S12B-D1–D9 获准进入分阶段实施。首个实施切片是
[`2026-09-03-lmdj-stage12-sample-slice-smoke-fixtures.md`](../plans/2026-09-03-lmdj-stage12-sample-slice-smoke-fixtures.md)，
只交付 `sample.slice` 的合成 smoke 输入、ground truth 与失败场景，先解锁
#467；benchmark host、报告、Stem/Pattern 语料与盲听包继续作为 #466 后续
独立 Task，不得被首个切片的完成状态代替。

评审修正（2026-08-31）：硬 timeout、进程树 RSS 与 GPU 归因必须按执行区
分别定义。直接 in-process 执行只提供确定性、Schema 与 elapsed observation，
不能宣称可强杀或精确归因资源；subprocess/sandbox、remote 各用自己的可执行
门禁。报告必须携带 execution zone 与 measurement source，Provider 自报值只
能作补充证据。

关联 Issue：[#472](https://github.com/endaye/lmdj/issues/472)（umbrella）、
[#466](https://github.com/endaye/lmdj/issues/466)、
[#467](https://github.com/endaye/lmdj/issues/467)（消费本文的代表性
smoke fixture）。

保留问题输入：`docs/prd/questions/production-separator-checkpoint.md`、
`docs/prd/questions/canonical-timing-analyzer-precedence.md`、
`docs/prd/questions/key-analysis-confidence-threshold.md`。
`docs/design/2026-07-15-multi-separator-benchmark-design.md`
是研究输入，不是 active source 权威。

## 1. 结论

Stage 12 的 Provider 选型必须由证据而非印象驱动。本文建立三条原则：

1. **合成优先**：能用仓库脚本确定性合成、从而按构造获得完美 ground truth
   的 fixture，一律合成；受权利限制的真实素材只以 manifest（来源、License、
   校验和、本地获取步骤）入库，字节永不入仓。
2. **硬拒绝先于比较**：确定性违约、超时、资源超限、坏输出 Schema、部分
   输出——任何一条即取消候选资格，不参与质量排名。
3. **benchmark 不晋级**：报告只产生证据；生产 Provider/checkpoint 的选定
   永远是证据评审后的显式决策（对齐 `production-separator-checkpoint` 的
   处理时点）。

analysis-bench 原型（`tools/analysis-bench/`，2026-08 已验证 Registry +
Capability v2 端口绑定 + AttemptStore 能承载多个可插拔分析工具并与独立
ground truth 对比）是本文的机制先例：Stage 12 bench 沿用「`tools/` 下、
无产品身份、走生产 execute 路径」的形态。

## 2. 评估问题清单（按 capability）

| Capability | 评估问题 | ground truth 来源 |
| --- | --- | --- |
| `sample.slice` | 切片点命中率（容差窗口内的 precision/recall/F1）、确定性、RTF、按 execution zone 可归因的 peak RSS | 合成：已知 onset 位置拼接的打击序列（间距、力度、重叠受控）；含静音、尾音重叠、极短间距的对抗用例 |
| `stem.split` | 分离质量（对合成混音可算 SI-SDR 类指标；真实素材走盲听包）、确定性类别符合性、RTF、按 execution zone 可归因的 peak RSS | 合成：由已知 stem 线性混合，分离结果与原 stem 直接对比；真实素材仅 manifest |
| `pattern.suggest` | 结构合法性（输出过 Schema 与领域校验：槽位引用、tick 界内）、与声明 role/BPM/Key 的一致性、seeded 复现性、候选多样性 | 规则可判定部分用校验器；音乐性走盲听/人工评审包 |

`canonical-timing-analyzer-precedence` 与 `key-analysis-confidence-threshold`
两个保留问题在指标层预留承载位：timing 一致性与 key 置信度分布是报告的
标准列，阈值裁决属各自决策，不在本文。

## 3. Proposed Decisions（待评审）

| ID | 决策 | 依据 |
| --- | --- | --- |
| S12B-D1 | fixture 分三层：**smoke**（每 capability 数个、小型、合成、可再分发、入仓）——同时是 #467 conformance 的代表性成功/失败用例；**评估**（合成为主，脚本 + 种子入仓，字节可再生）；**受限**（真实素材，仅 manifest 入仓）。 | §1 原则 1 |
| S12B-D2 | 每个 fixture 记：生成脚本 + 参数 + 种子（或来源 + License + sha256 + revision）、预期结构性质（onset 表、stem 构成、容差）、允许用途。smoke 失败用例覆盖：缺失/截断输入、坏 WAV 头、超长输入、非法输出 Schema、禁止类别的非确定性、部分输出；timeout 注入仅在 subprocess/sandbox 与 remote deadline zone 声明为强制用例，direct in-process 只观测 elapsed。 | #466 验收 |
| S12B-D3 | 跨 execution zone 的无条件硬拒绝：deterministic 双跑字节不一致；seeded 同种子不一致；输出未过 execution 中消费方 Schema validator；required output 不完整；失败输入未 fail closed。时间/内存/GPU 门禁必须按 S12B-D4 的 zone matrix 解释，不能把不可执行或不可归因的观测伪装为硬拒绝。 | §1 原则 2 |
| S12B-D4 | execution zone matrix：`in_process_reference` 只记录 SDK execute 的 determinism/schema/elapsed，无法安全中断同进程，也无法把进程 RSS/GPU 与单次 Attempt 隔离，因此 timeout/RSS/GPU acceptance = `not_enforceable`；若候选要过这些硬门禁，必须把整次 execute 放入 `subprocess_sandbox`。该 zone 用 wall-clock deadline，超时向独立 process group 先 TERM、宽限后 KILL，并以拥有的完整进程树 peak RSS 计量；GPU 只有独占设备/可归因进程采样器时才可判门禁，否则 N/A。`remote` 用客户端 request deadline + cancel，deadline 到即失败但不声称杀死服务端；local RSS/GPU = N/A。 | 操作系统可执行的隔离与归因边界 |
| S12B-D5 | 报告是 JSON（schema 随实施定稿）：环境身份 + 逐 fixture 逐指标结果 + 硬拒绝清单；每个 measurement 必带 `execution_zone`、`measurement_source`、`unit`、`value` 或明确 `not_enforceable|not_applicable`。Provider 自报 elapsed/RSS/GPU/服务端完成状态只可放 `supplemental_provider_reported`，不能单独使 acceptance 通过。不含绝对路径、密钥、模型缓存路径、受限音频字节。retained 报告与盲听包索引落 `docs/quality/`。 | #466 验收「retained 报告」与可审计测量 |
| S12B-D6 | 盲听/人工评审包：对客观指标不足的维度（stem 音质、pattern 音乐性）产出双盲对照包（随机化标签 + 答题表 + 判定规则），结论作为证据附在决策 Issue，不自动换算成分数排名。 | `production-separator-checkpoint` 处理时点 |
| S12B-D7 | bench 宿主沿 analysis-bench 形态：`tools/` 下、无 module.json、无产品身份、构造 Provider 走 `provider::Registry` + `AttemptStore` 生产 execute 路径；#467 的 Provider v2 `ArtifactSource` 落地后改用正式输入口，Host 注入桥接不复活。执行控制器在此路径外选择 S12B-D4 的 zone：direct in-process 是 reference；需要硬资源门禁时把整条生产 execute 路径放进受控 child process，而不是在 Provider API 内伪造 kill/RSS 能力。 | 2026-08-24 决策点 2 |
| S12B-D8 | 结果的效力边界：报告可以淘汰候选（硬拒绝）与陈述量化差异，不能晋级任何候选；生产选定是显式决策文件 + 独立 Issue。 | §1 原则 3 |
| S12B-D9 | 复现身份：报告必须记 OS/kernel/architecture、CPU/内存、accelerator + driver（如适用）、工具链与依赖锁、bench Git revision、Capability Contract identity，以及候选的 publisher + provider version + 不可变 checkpoint revision + sha256 + License 证据。测量还需记 harness revision、sampler 与 cadence、deadline/kill grace 配置。缺任一适用身份的运行结果无效，不能进入跨候选比较。 | #466 验收「checkpoint 候选可追溯」 |

## 4. 与 #467 的接口

#467 只消费 S12B-D1 的 smoke 层（代表性成功/失败用例），不等评估层与
受限层；两个 Issue 由此并行。smoke fixture 的 Schema 断言以 #467 定稿的
`lmdj.slice-points.v1` 为准，先行草案按其字段形状预置。

报告比较必须按 execution zone 分组。`in_process_reference` 的 elapsed 可以
发现回归，但没有 timeout/RSS/GPU 的资格结论；`subprocess_sandbox` 才能产生
本地强 timeout 与 process-tree RSS；`remote` 只能对 request deadline 和本地
客户端资源负责。不同 zone 的 `not_enforceable` / N/A 不得按 0 参与排名。

## 5. Version Management

Version impact: none——研究与 benchmark 设计、合法 fixture manifest 与
测试数据；不改任何 Product、Module、Host、Provider、Contract、Assembly、
Channel 或快照身份（`tools/` 不被 Portal 与 release 工具扫描）。

## 6. Documentation Impact

Documentation impact: none——本次只修订 retained 研究/评审材料，current
Portal unchanged；未来任何 Provider 或 capability 身份变更由其自身 Task
按实际身份变化声明 Portal 影响。

## 7. 拒绝的替代

### 7.1 下载版权音频入仓做评估

拒绝。受限素材只以 manifest 表示（S12B-D1/D2）。

### 7.2 用 bench 分数自动选定生产 Provider

拒绝（S12B-D8）。规格 §16：Provider 选择属 Workspace/Host 策略与显式
决策，benchmark 只是证据。

### 7.3 复活 references/demos 或旧 Worker 计划作为 bench 权威

拒绝。冻结参考不是 active source；2026-07-15 benchmark 设计只作研究输入。

### 7.4 跳过合成层直接盲听

拒绝。盲听昂贵且不可回归；凡可按构造判定的先按构造判定（§1 原则 2）。

### 7.5 在 direct in-process execute 内宣称 hard timeout 或单 Attempt RSS

拒绝。同进程强杀会同时杀死 bench，进程 RSS 也混合 runner、SDK 与其他工作。
需要门禁时隔离整次 execute 到受控 process group。

### 7.6 用 Provider 自报资源值通过验收

拒绝。自报值可辅助诊断，但不能替代 harness 拥有的 deadline、process-tree
sampler 或明确 N/A；remote 服务端尤其不能靠自报证明本地不可观测的事实。

## 8. 实施入口（前置条件）

1. 本文评审通过后落笔实施拆分：fixture 生成脚本、smoke 层入仓、bench
   宿主扩展、报告 schema、盲听包模板，各自声明 Version 与 Documentation
   impact。
2. smoke 层交付即解锁 #467 的 conformance 用例；评估层与受限层按各
   capability 的候选出现节奏推进。
