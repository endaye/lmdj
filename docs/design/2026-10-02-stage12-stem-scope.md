# Stage 12B Stem：最小使用范围与执行边界

日期：2026-10-02。状态：**T1 可评审建议；产品范围、环境和预算待确认**。
后续状态（2026-10-03）：Provider 架构、四路角色和显式采纳方向已按
[确认记录](../prd/decisions/2026-10-03-stem-slice-provider-boundary.md) 定稿；
[交付计划](../plans/2026-10-03-stem-slice-provider-delivery.md) 先推进 Contract/SDK。
本文保留 T1 评测提案；`vienna` 已作为候选主机检查，环境隔离资格、实测结果
和生产 checkpoint 尚未取得。
交付 [#1171](https://github.com/endaye/lmdj/issues/1171) 的设计准备；
Relates to #1164、#1172、#472。
依据：[独立交付计划](../plans/2026-09-10-stage12-independent-delivery.md)、
[核心重设计](2026-07-30-lmdj-playable-beat-instrument-core-redesign.md) §16、§19、§23、
[已批准 benchmark 规则](2026-08-31-lmdj-stage12-provider-benchmark-design.md) S12B-D1–D9。
配套：[T2 评测计划与 Task inventory](../plans/2026-10-02-stage12-stem-evaluation.md)。

## 1. 首版使用场景建议

用户持有可合法处理的短混音，希望提取鼓或低音作为 Beat 素材；在 Sample
工作流中显式请求一次离线分离，分别试听结果，再把某一路采纳到指定 Pad
Slot。建议首版只有一种四路配置：`drums`、`bass`、`vocals`、`other`。
角色是分离目标的标签，不承诺某乐器在混音中客观存在，也不保证完全无串音。
不以双路 karaoke、六路乐器或实时分离扩大首轮范围。

以下数字都是**评测提案**，不改变现有产品输入限制或新增正式 Contract：

| 项目 | 建议范围 | 超出范围时 |
| --- | --- | --- |
| 可用音频长度 | 5–30 秒；先测 5、15、30 秒；60 秒作为超限拒绝用例 | 不自动裁剪或偷偷改参数；返回可解释的范围失败 |
| 输入 | 已校验的音频 Artifact；评测统一为 44,100 Hz、双声道 PCM16 WAV | 导入解码属于既有输入链路；mono/其他采样率转换须单独记录，首轮不隐式转换 |
| 输出 | 恰好四路；同采样率、声道数、帧数、时间起点；角色唯一 | 缺路、重复角色、坏 WAV、长度偏差不能形成可采纳完整结果 |
| 数值 | 推理可用 float；分离结果检查 finite、幅度、增益后显式编码为音频 Artifact | 禁止未记录的每路归一化、削波或移位；量化规则待 Contract 决策 |
| 执行 | 一次离线 Attempt；一个候选/一种参数/一个执行区 | 换模型、参数或执行区创建新 Attempt，不静默回退 |
| 采纳 | 用户试听并选择一路和目标 Slot；覆盖需明确交互 | 不自动铺满 Bank；不改既有 Pattern 的 Slot 引用 |

WAV Artifact 当前格式依据
[PCM16 WAV 文档](../../contracts/artifact-audio/lmdj.audio.pcm16-wav.v1.md)。
这里不命名新的 Stem Contract ID 或分配版本。活动树尚无 Stem Capability
实例、输出结果 Contract 或真实 Stem Provider；`stem.split` 是设计中的能力
名称，不是已交付接口。它们的定稿和身份分配属于后续独立设计/实施 Task。

## 2. 产品旅程及后续验收义务

此处定义将来必须保留的旅程，T1 没有执行这些步骤：

| 转换 | 转换后的可观察断言 |
| --- | --- |
| 选择输入 → 请求 | 输入 digest/byte length 与参数固定；显示候选、位置、权限、成本；Project Truth 未变 |
| 请求 → 执行 | Attempt identity 与执行区对应；Provider 仅收到 ArtifactSource 和 output sink，无 Project bundle 路径 |
| 执行 → 完整结果 | 四路均通过消费方校验；各自 digest/byte length、角色与音频形状可核对；部分输出不可采纳 |
| 完整结果 → 试听 → 停止 | 试听确实使用目标结果；停止后没有残留声音；试听不改变 Project Truth |
| 试听 → 显式采纳 | 仅选定 Slot 的 Asset/Lineage 改变；原输入及未选 Slot 保留；Pattern 仍引用 Slot |
| 失败/取消 → 重试 | Typed Error 留在 Attempt；无半成品写入 Truth；新 Attempt 不冒充旧 Attempt 的成功 |
| 结果 → discard/supersede | 原 Project 不变；旧结果不可误采纳；删除/保留遵循所有权及配额规则 |
| 采纳 → 保存 → 刷新/关闭 → 重开 | 重新读取的 Asset 内容身份与完整 Lineage 相符；已采纳 Slot 和 Pattern 保留；Runtime Snapshot 重新派生 |

多路结果的原子完成标记、每路采纳、Lineage（源 digest、分离参数、候选及
执行身份）、取消后的临时产物、配额/垃圾回收仍需产品级决策。Provider
选择属于 Workspace/Host 设置；失败属于 Attempt；模型结果不直接写 Truth。
原型或 bench 成功不能代替这个完整旅程，也不能复活旧分离 demo 为产品源。

## 3. 三种执行区的取舍

| 执行区 | 输入/资源/故障边界 | 本轮建议及限制 |
| --- | --- | --- |
| `in_process_reference` | 与宿主共享进程；elapsed 可观测，不能安全强杀，RSS/GPU 无单 Attempt 归因 | 仅参考观察；timeout/RSS/GPU 为 `not_enforceable`；不进入音频实时线程 |
| `subprocess_sandbox` | 整次 Registry + AttemptStore execute 放入受控进程组；只读输入、私有临时输出；需权限隔离 | **首轮建议**：专用 Linux CPU 环境、禁止网络推理、单并发；wall-clock deadline 后 TERM，宽限后 KILL；完整拥有的进程树 RSS 采样 |
| `remote` | 上传或短期访问；客户端 deadline/cancel；不能证明服务端已被杀死；Provider RSS/GPU = N/A | 只比较约束，首轮不运行；先确认 Region、Retention/删除回执、费用、上传权利和 provider/model 固定身份 |

独立进程不等于已实现文件/网络 Sandbox。T2 必须证明实际隔离策略、子孙进程
归属和清理；只有 root PID 的 RSS 不够。没有可归因资源测量就保留缺口，
不能改成同进程或 Provider 自报值来取得资格。GPU 默认不用；只有明确授权
且独占设备或可归因进程采样器可验证时才讨论 GPU gate。

本地无服务费仍消耗设备时间、电力、存储及依赖下载流量；remote 有额外的
排队、传输、服务计费和保留风险。不能从厂商 README 推断本机 RTF 或内存。
Creator/browser、Windows、macOS、Cardputer/ESP32 的可用性均未被 CPU bench
证明；后续平台 Host 接入与物理验收独立安排。

## 4. 候选清单、来源与许可适用性

2026-10-02 只读取发布方源码/许可/记录元数据，**未下载或反序列化权重**。
候选身份固定如下；并非产品选型。源码 SHA 与发布权重身份分别保留。

### C1 — Open-Unmix `umxhq`：首个评测建议

- 发布方：SigSep / Inria；源码
  [`fb672c9584997c2b05e148eeaa65b4c23ed4693b`](https://github.com/sigsep/open-unmix-pytorch/tree/fb672c9584997c2b05e148eeaa65b4c23ed4693b)。
- 四路与加载配置见固定
  [`openunmix/__init__.py`](https://github.com/sigsep/open-unmix-pytorch/blob/fb672c9584997c2b05e148eeaa65b4c23ed4693b/openunmix/__init__.py)；
  SHA-256 `2e06b8ddbbd02024661374c22ea6eff98e2950f0f14c7348586cbfdc28437cef`。
- 代码 [MIT LICENSE](https://github.com/sigsep/open-unmix-pytorch/blob/fb672c9584997c2b05e148eeaa65b4c23ed4693b/LICENSE)，
  SHA-256 `4f7b047ffafb9fbb39a40d605bab961b9b030711addce6e9d23886c2ae3b105e`。
- 权重固定在 [Zenodo 3370489，版本 1.0.1](https://zenodo.org/records/3370489)，
  DOI `10.5281/zenodo.3370489`；[发布记录 API](https://zenodo.org/api/records/3370489)
  的 `metadata.license.id` 为 `mit-license`。这是发布方许可材料；研究及未来
  分发需保留声明，不把数据集许可或输入内容权利自动合并进 MIT。

| 发布文件 | 发布方 MD5 | 字节数 |
| --- | --- | --- |
| `bass-8d85a5bd.pth` | `8cc37d31903fe48306468ee968f4b1b6` | 35637796 |
| `drums-9619578f.pth` | `cebf76e196e73e85d247f462c31e36fc` | 35637796 |
| `other-b52fbbf7.pth` | `8637606623ed7c74986789c3b1f94bc6` | 35637796 |
| `vocals-b62c91ce.pth` | `d918985fad0fedf6d9ce89e279aa7218` | 35637796 |

MD5 仅记录发布身份，不充当运行证据要求的 SHA-256。四文件共 142551184
字节；T2 获准取得后必须核对上述长度/MD5、计算完整 SHA-256，并在执行前
冻结权重 manifest。当前运行用 SHA-256 **未取得**，所以不能产生有效的
measured candidate 比较。禁止用默认 `umxl` 代替：其
[固定 README](https://github.com/sigsep/open-unmix-pytorch/blob/fb672c9584997c2b05e148eeaa65b4c23ed4693b/README.md)
明确将 `umxl` 权重限定为 CC BY-NC-SA 4.0；它不是 C1。

### C2 — Demucs `htdemucs`：有许可缺口的研究对照

- 发布方：Meta / facebookresearch；源码
  [`e976d93ecc3865e5757426930257e200846a520a`](https://github.com/facebookresearch/demucs/tree/e976d93ecc3865e5757426930257e200846a520a)。
- 固定 [`htdemucs.yaml`](https://github.com/facebookresearch/demucs/blob/e976d93ecc3865e5757426930257e200846a520a/demucs/remote/htdemucs.yaml)
  指向模型 `955717e8`，SHA-256
  `239c445d0b14454d541ad8bd9bb271c9e536d267e8a4625208744cbb2e7bb66c`。
  固定 [`files.txt`](https://github.com/facebookresearch/demucs/blob/e976d93ecc3865e5757426930257e200846a520a/demucs/remote/files.txt)
  列出 `hybrid_transformer/955717e8-8726e21a.th`，SHA-256
  `7258eee911e5963e6270983d7072832e90e1ed96b25bb26aadf12f9867109bf9`。
  文件名短后缀不是完整权重 SHA-256；权重长度和完整 digest 未取得。
- 代码 [MIT LICENSE](https://github.com/facebookresearch/demucs/blob/e976d93ecc3865e5757426930257e200846a520a/LICENSE)
  SHA-256 `cf9b17822d1fcd4ff32ccbe14183386fb3adf6f2ff92dc184130823f7fc28173`。
  [作者的权重许可说明](https://github.com/facebookresearch/demucs/issues/327#issuecomment-1134828611)
  表示权重不由代码 MIT 覆盖、用途限于科学研究。该说明早于 v4，不能当作
  `htdemucs` 专属商用授权；适用条款尚需确认，**C2 不获商用/产品分发资格**。
- [固定 README](https://github.com/facebookresearch/demucs/blob/e976d93ecc3865e5757426930257e200846a520a/README.md)
  描述四路、随机 shifts、分段和输出重缩放。若研究用途获准，建议 CPU、
  `shifts=0`、单作业、固定 overlap/segment、显式增益处理；这些参数及数值
  复现性要测量，不能由模型名称推断。C2 权重取得和费用另行确认。

## 5. 待确认清单与完成判据

| 决策 | 本文建议 | 在何时由谁确认 |
| --- | --- | --- |
| 输入长度/格式与四路使用场景 | 5–30 秒、44.1 kHz stereo、四路 | 产品负责人在 T2 开始前确认评测范围；不自动升级成产品 Contract |
| 候选与下载 | 先 C1；C2 暂列对照 | 任务负责人确认模型取得、权重条款及下载上限；SHA-256 冻结先于执行 |
| 执行环境 | Linux x86_64 CPU、独立进程、无推理网络 | 环境负责人确认主机、依赖锁、隔离/采样可行性；不默认已有该环境 |
| 时间/资源预算 | 配套计划的探索性上限 | 设备/预算负责人明确接受；没有确认不跑；无付费服务/GPU/remote 授权 |
| 质量/RTF/RSS 产品阈值 | 尚无产品阈值；先收集分布 | 产品负责人在结果解盲前确认任何接受阈值；结果后不得调低既定标准 |
| 确定性类别及浮点/PCM 输出规则 | CPU 重跑测量；尚未宣称 deterministic | Contract 决策在正式 execute 资格评测前确认；seeded 必须固定种子和参数 |
| 多路结果/Lineage/配额及采纳 | §2 完整旅程 | 独立产品决策与精确文件实施 Task；T1 不默默定稿 |
| 生产 checkpoint | 仍未选择 | 复用 [production-separator-checkpoint](../prd/questions/production-separator-checkpoint.md)，T2 证据评审后独立决定 |

T1 完成意味着范围、候选资料、评测方法及实施前清单可评审；不要求上述
建议已获准运行，也不使 #1172 自动解锁。#1164 与 #472 继续追踪真正 Stem
产品交付。Slice 验收可独立继续，Stem 研究不改变 Slice 的严格性。

## Version Management

Version impact: none
Reason: 本次只有规划/研究材料，不分配 Product、Module、Host、Provider、
Contract、Assembly 或 Channel 身份。后续正式接口和实现分别按实际影响分配。

## Documentation Impact

Documentation impact: none
Reason: 仅保留未来范围和研究提案，不改当前 Architecture Portal 页面、源事实、
投影身份或产品可用性；没有 Product Build 分配及快照义务。
