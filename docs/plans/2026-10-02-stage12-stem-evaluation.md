# Stage 12B Stem：候选可行性评测与实施前清单

日期：2026-10-02。状态：**T1 可评审交付；T2 等待范围、环境、预算批准**。
交付 [#1171](https://github.com/endaye/lmdj/issues/1171)；
Relates to #1172、#1164、#472。
配套：[最小范围、候选固定身份与许可](../design/2026-10-02-stage12-stem-scope.md)。
规范：[已批准 benchmark 设计](../design/2026-08-31-lmdj-stage12-provider-benchmark-design.md)
S12B-D1–D9；[报告工具](../../tools/provider-benchmark/README.md)。

## 1. 本 Task 的精确交付与最低层验证

只新增以下两份 retained 文档，日期占位按实际准备日期替换：

- `docs/design/2026-10-02-stage12-stem-scope.md`
- `docs/plans/2026-10-02-stage12-stem-evaluation.md`

T1 验证：逐项对照 S12B-D1–D9、检查两份文档的本地相对链接、读取发布方
固定 revision 的候选/许可材料并核对元数据 digest；暂存后运行
`python3 tests/build/ci_change_scope_test.py` 与 `git diff --cached --check`。
PR 使用 `scripts/local-ci.sh --declaration-only --pr-body BODY.md` 检查
Documentation impact 声明。这里不新增代码、fixture、harness 或门禁，不执行
模型，不以 docs/site 或 Core 全量运行代替本 Task 的资料审查。

## 2. 执行前条件与建议预算

任务负责人先确认范围文档 §5，再为每个后续 Task 声明精确文件与批准边界。
**文档合并不是模型下载或执行批准**。必须保留审批的候选集合、输入集合、
执行区、主机身份、依赖锁、资源上限及质量判定口径；缺项即保持 blocked。

| 项目 | 首轮提案；全部待批准 |
| --- | --- |
| 环境 | 专用 Linux x86_64 CPU；Python 3.11；C1 固定源码；PyTorch/NumPy/audio I/O 版本和所有 wheel SHA-256 由兼容性预检冻结，不用 latest 或未验证的版本猜测 |
| 权限 | 模型/依赖取得是单独的联网阶段；离线推理禁止 Network，仅输入可读、私有输出可写；单作业、4 CPU 线程，无 GPU、remote 或付费资源 |
| 下载/存储 | C1 四权重 142551184 bytes；包含依赖总下载上限 2 GiB，私有临时区 4 GiB；超限停止申请调整；受限音频另批，不默认下载 MUSDB |
| 总运行 | 首轮 C1：有效输入 12 个、错误输入 4 个；有效输入各两次冷启动及一次同 child 内热运行，共 36 次有效推理；另做隔离控制器故障注入；总 wall-clock 上限 2 小时 |
| 单次限制 | 每个 cold/warm measurement 独立记录；一次 owned child group 最多 600 s（包含加载），TERM 后 2 s KILL grace；采样间隔 50 ms，进程树观测 RSS 上限 4 GiB |
| 成本 | 服务费预算 0；本地占用不等于免费；不能默许 GPU、云服务、上传或训练；C2 加入需另核许可/字节数/预算并批准 |
| 盲听 | 3 名评审，每人最多 30 分钟；不自动联系或发送素材；未提供评审人员就保留听感缺口，不由代理代填 |

600 s/4 GiB 是探索性资格配置的建议，不是产品延迟或内存承诺。采样 peak
RSS 是以固定 cadence 对完整进程树同时求和的**观测峰值**，不是连续时间
绝对峰值；不能声称证明瞬态内存永未越界。若要求硬内存约束，环境还须
提供已验证的 OS 限额机制与违规事件证据，独立声明其配置。
预算耗尽保留已完成/失败/未执行项，不删用例或提高上限得到 green。

## 3. 语料、真值与输入身份

生成代码及 seed 可入仓，受限真实音频只留 manifest；所有输入与四路真值
记 digest、byte length、采样率、声道、帧数、精确区间、许可和可允许用途。
角色标签固定，不用 best-permutation 匹配掩盖交换；混合使用已知线性系数，
保留共同增益，防止相加削波。固定 44.1 kHz stereo，不事后优化重采样器。

| 层/ID | 数量与内容 | 判定能力 |
| --- | --- | --- |
| smoke S01–S04 | 4 个 5 s：全静音；孤立鼓；bass+other 无 vocals；四路受控混合 | 有/无角色、音频结构、长度、串音和 fail-closed；合成 oscillator 不能证明真实音乐质量 |
| evaluation E01–E06 | 6 个：两组不同合法自有 stem，在 5/15/30 s 各混合一次；组 A 干声瞬态，组 B 长尾重叠/立体声差异 | 已知混合真值、按角色 SI-SDR、重构误差、长度及窗口接缝；manifest 冻结两组来源，数据未提供即未执行 |
| restricted R01–R02 | 2 个 30 s 权利获准真实混音：稀疏节奏/密集有声；仅 manifest 入仓 | 无独立真值时只盲听，不能标成客观 SI-SDR；无上传/再分发授权，不入公共 PR artifact |
| failure F01–F04 | 缺失输入、截断 WAV、坏 WAV 头、60 s 超限 | 消费边界 fail-closed；每次都验证无可采纳输出、无 Truth 写入 |

独立控制器注入：child 无响应、拒 TERM 的 descendant、部分四路输出、
错误角色/输出形状、非法 Schema、超 RSS、digest/length 不符、禁止类别的
非确定性。用伪 worker 验证控制器是**harness 测试**，不是模型评测证据。
先跑原始输入再跑错误输入；保留拒绝原因与 cleanup 后的进程/产物断言。

[MUSDB18 发布方资料](https://sigsep.github.io/datasets/musdb.html) 列明其多源
素材许可、访问及学术用途限制。首轮不依赖其下载；如后续获准用 MUSDB18-HQ，
锁定记录 DOI `10.5281/zenodo.3338373`、split、track/区间、每轨条款及 SHA-256，
与模型训练重叠情况一起记录；不能把训练集结果称作泛化验收。只有授权混音
且同版独立 stem 真值完整时才能计算客观指标；否则回到 restricted 盲听。

## 4. 指标互相独立，硬拒绝先于质量

| 维度 | 方法、far-side 证据与限制 |
| --- | --- |
| 输出完整性 | execute 消费方校验四路结构/角色/frames、各路 hash+length、PCM 合法性；partial 不排名；事后文件存在不等于执行中消费方校验 |
| SI-SDR | 非静音真值 s 与估计 y，去均值；alpha=dot(y,s)/dot(s,s)，10 log10(sum((alpha*s)^2)/sum((y-alpha*s)^2))；每路/每 case 列出，并与输入混音作同法 baseline 比较；不搜索最佳 shift/增益/角色，不把它称为 BSSEval SDR |
| 静音/退化 | 真值能量为 0、估计投影为 0 或误差为 0 记录 undefined/infinite 分类及原因，JSON 数值为 null；另测输出 RMS/峰值；不造有限高分，也不在总体均值中静默丢弃 |
| 重构/增益 | 固定时间轴，四路相加与原混音的归一化残差能量；同时报告绝对峰值、增益变化/削波、接缝；它不能单独证明分离质量 |
| 确定性 | 同 source/weights/fixture/params/seed/环境两次独立冷启动，核对包含角色、格式、hash+length 的完整输出集；deterministic 或 seeded 按已批准类别字节比较；nondeterministic 显式标记，不能事后降类别躲避拒绝 |
| RTF | harness monotonic wall elapsed / (frames/sample_rate)；cold 包含进程创建、加载、execute、编码/校验，warm 单列且保留运行顺序；下载不混入推理 elapsed，费用/准备时间另记 |
| 资源 | `subprocess_sandbox` 外部完整进程树采样、deadline/kill evidence、采样 identity/revision/cadence、host load；GPU = N/A；Provider 自报只进 supplemental |

单一相同 case 下的 SI-SDR 可对比；每组/角色分布、失败率、尾部耗时及置信
区间优先于一个总分。失败/超时仍在完整 case 清单内。无真值真实素材不能
凭估计残差充当真值评估；没有批准质量阈值就只陈述差异，不能宣布 go。
把耗时与冷/热资源分开，将不同执行区或不同输入身份分组，不用 N/A=0 排名。

## 5. 双盲听感程序

固定片段/角色/候选与合法真值/原混音对照，在生成听感包前冻结试验设计。
独立包管理员产生随机不透明标签、平衡播放顺序，答案 key 保存在私有区；
听者及结果汇总者在答卷冻结前均不知道候选映射。C2 未准入时只能评审
C1 与真值/混音对照，不能伪造跨模型排名。

每位听者分别记录：目标声部可用性、他声部串音、瞬态/尾音损伤、音乐噪声、
立体声稳定性，各 1–5 分并附时间位置及原因；允许“无法判断”。试听响度
可用共同的预注册播放增益，必须记录，原输出不被改写；禁止每路独立归一化
掩盖增益问题。加入一次重复片段检查一致性，保留全部答卷与弃答原因。
原混音用于上下文，不冒充分离真值；盲听得分不自动换算生产资格。

公开仓库仅保留合法索引/汇总及 digest；受限包不入仓、不公开上传。
无人参与、人数不足或未双盲须标记限制及未执行，不能以模型输出替代人工。

## 6. 报告格式与执行区规则逐项对照

现有 `provider-benchmark-report` v1 只支持资源指标与 Slice precision/recall/F1，
**不能直接塞 SI-SDR 或宣称已有 Stem execute**。下列新增格式/CLI 都是
T2 的 tooling 提案，尚未存在；不改 active Contract，不扩大现有 Schema。
先独立保存 Stem quality JSON 并交叉绑定输入/输出 digest；将资源和 SDK
execute 证据用现有报告校验器验证。若格式需要变化，独立 review，不能绕过
closed fields。没有真实 SDK execute/正式 Contract identity 的研究 CLI
结果只能是探索性资料，不能伪装 `--require-measured` 的资格证明。

| 已批准规则 | 本计划的落实 |
| --- | --- |
| D1/D2 | §3 分层；精确生成 seed/source/license/hash+length；失败输入与输出注入 |
| D3 | §4 固定确定性类、消费方校验、required outputs、失败输入拒绝；违约先淘汰 |
| D4 | §2/4 隔离整次 execute；group deadline/TERM/KILL、tree sampler；direct 资源 not_enforceable；remote 服务端 N/A |
| D5 | 环境/权重/输入/输出/harness/采样/限额身份齐全；Provider 自报不作接受依据；无绝对路径、secret 或受限字节 |
| D6 | §5 双盲标签、答卷、key 隔离、冻结后解盲；未做就保留缺口 |
| D7 | 正式资格运行必须经过 Registry + AttemptStore + ArtifactSource/output sink，并在受控 child 内完成；直接模型 CLI 仅探索 |
| D8 | 报告淘汰或陈述差异；生产选择须独立决策，no-go/补证据是有效结论 |
| D9 | 固定 candidate source/weight hash+length/license、依赖锁和 bench/harness revision；缺适用身份不能比较 |

## 7. T2 实施前 Task inventory

以下是建议施工单，**本次不创建这些文件**。T2 开工前把选定的 Task/file
清单及批准记录补入 #1172；每项一份可评审 commit。共有的 README/CMake/
scope routing 由一个 Task 持有；并行不意味着争用这些文件。既有 routing
若不覆盖新路径，先单独声明 `scripts/ci/scope_policy.json` 和
`tests/build/ci_change_scope_test.py` 的精确变更，不能默许追加路径。

### T2-A — 固定候选、环境与合法输入

精确提案文件：

- `tools/provider-benchmark/stem/candidates.json`
- `tools/provider-benchmark/stem/requirements.lock`
- `tools/provider-benchmark/stem/fixtures.json`
- `tools/provider-benchmark/stem/generate_fixtures.py`
- `tools/provider-benchmark/stem/tests/fixtures_test.py`
- `docs/quality/evidence/stage12-stem/README.md`

最低层验证：`python3 tools/provider-benchmark/stem/tests/fixtures_test.py`。
一事实一测试：seed 重建身份、混合真值/frames、每路 byte length、非法输入、
受限字节不入仓。权重取得命令和每个 artifact SHA-256 在已批准环境中冻结；
requirements.lock 不能带 placeholder。真实音乐素材未获准即保留未执行。
Version impact: none；Documentation impact: none（只研究工具与证据）。

### T2-B — 质量计分与双盲打包

精确提案文件：

- `tools/provider-benchmark/stem/score.py`
- `tools/provider-benchmark/stem/quality.schema.json`
- `tools/provider-benchmark/stem/blind_pack.py`
- `tools/provider-benchmark/stem/tests/score_test.py`
- `tools/provider-benchmark/stem/tests/blind_pack_test.py`

最低层命令：分别 `python3 tools/provider-benchmark/stem/tests/score_test.py`
与 `python3 tools/provider-benchmark/stem/tests/blind_pack_test.py`。自有解析
fixture 验证 SI-SDR 恒等、串音、静音/退化、角色交换、frames 错误；独立
实现复算至少一个非退化 case，不仅比较同一函数的输出。包测试分别证明
标签映射完整、公开索引无答案 key、受限素材无公开复制。新增本地 validator
捕获身份不符/非 finite 伪分数等确定缺陷，失败需 why/remedy；不添加产品
质量阈值门禁。Version impact: none；Documentation impact: none。

### T2-C — 隔离控制器与探索性离线 runner

精确提案文件：

- `tools/provider-benchmark/stem/run.py`
- `tools/provider-benchmark/stem/worker.py`
- `tools/provider-benchmark/stem/tests/runner_test.py`

最低层：`python3 tools/provider-benchmark/stem/tests/runner_test.py`；在批准
Linux 环境验证 no-network policy、完整 child tree、timeout/TERM/KILL、RSS
采样、cleanup、partial 不接受、重复执行身份。deadline/rss 缺证据拒绝资格，
不可只測成功路径。该 runner 调用模型不等于 Provider 产品实现，也不满足
D7；探索性包必须显式注明其资格缺口。Version impact: none；Documentation
impact: none。权限/限额机制若需额外源码，先增补 exact files，不放大此清单。

### T2-D — 正式 execute 资格前置，先决策再列源码

先提案以下精确设计文件：

- `docs/design/2026-10-02-stage12-stem-contract-proposal.md`
- `docs/plans/2026-10-02-stage12-stem-execute-proof.md`

决策需覆盖 Capability 输入/输出、determinism、Typed Error、required roles、
音频量化、Lineage、quota、超限/partial/cancel，以及 §2 产品旅程。最低层
验证是 Contract/SDK 不变量逐项设计审查，不是虚构 conformance pass。
Version impact: none；Documentation impact: none（提案不改当前接口）。

**正式 Provider/Contract 源文件尚未授权或定稿**；上述计划必须先给出
来自 active manifest 的身份、每个 exact source/test 路径、最低层测试、
版本与 Portal impact，然后另行批准实施。落实 D7 的 real execute 和消费方
validator 后才能产出有效的资格报告；不为消除阻塞复活旧 Worker/demo。
T2-A/B/C 可先准备研究工具，T2 的完整可复现资格结论等待这一前置。

### T2-E — 真跑、人工证据与后续产品拆分

精确提案文件：

- `docs/quality/2026-10-02-stage12-stem-feasibility.md`
- `docs/plans/2026-10-02-stage12-stem-implementation.md`
- `docs/quality/evidence/stage12-stem/c1-resource.json`
- `docs/quality/evidence/stage12-stem/c1-quality.json`
- `docs/quality/evidence/stage12-stem/blind-index.json`
- `docs/quality/evidence/stage12-stem/listening-summary.json`

这些日期是 T2 提案命名，若实际执行日期变化，在实施前统一更新 #1172
和 inventory；C2 未批准不生成 c2 报告。私有原始 logs/输出/答卷/key
不算公共声明文件，保存位置、访问权限与保留期限必须先获准。

在 A–D 落地、批准条件通过之后，命令接口提案如下（**目前不存在，不能运行**）：

```bash
python3 tools/provider-benchmark/stem/generate_fixtures.py --manifest tools/provider-benchmark/stem/fixtures.json --out "$STEM_RUN_DIR/inputs"
python3 tools/provider-benchmark/stem/run.py --candidate c1 --zone subprocess_sandbox --manifest tools/provider-benchmark/stem/fixtures.json --out "$STEM_RUN_DIR"
python3 tools/provider-benchmark/stem/score.py --run "$STEM_RUN_DIR" --out "$STEM_RUN_DIR/quality.json"
python3 tools/provider-benchmark/stem/blind_pack.py --run "$STEM_RUN_DIR" --out "$STEM_PRIVATE_LISTEN_DIR"
python3 tools/provider-benchmark/validate_report.py "$STEM_RUN_DIR/resource.json" --require-measured
```

`STEM_RUN_DIR` 和 `STEM_PRIVATE_LISTEN_DIR` 指向经批准的私有临时区域；模型
cache 只通过本地配置定位，不写入 retained report。runner 的正式 SDK
接口由 D 的施工单确定并重审以上命令，不能拿 C 的 raw CLI 输出伪造 D。
quality.schema 的独立 validator、身份审计和盲听冻结/解盲步骤由 B 的实现
写入 evidence README；现有 validator 的 green 只证明内部一致性，必须
另核来源和实际 execute 证据。

报告同时列通过、淘汰、失败、未执行和适用执行区限制；人工质量未完成不写
全通过。允许 no-go 或补证据结论。若进入产品实施，先分别拆 Contract、
Provider/隔离执行、Stem Candidate/Lineage/配额、Facade/Host、Product Assembly
及完整验收 Tasks；各自定稿 exact files/tests/version/Portal impact。此处不
把未来目录当无限施工权限，不分配或猜产品身份，不执行 Release/部署。
Version impact: none；Documentation impact: none（retained 研究结果和提案）。

## Version Management

Version impact: none
Reason: T1 两份规划文档没有产品身份影响。T2 研究工具本身无身份；正式
Contract/Provider/API/Assembly 实施需独立分配实际版本，Build/Assembly 更改
必须更新 Portal 并履行不可变快照义务，不能继承这里的 none。

## Documentation Impact

Documentation impact: none
Reason: 本次只交付 retained 设计与计划；不改变 Portal 当前可用性、源图、
投影身份或文档工具。后续活动源事实变化由自己的实施 Task 声明。
