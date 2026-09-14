# 已确认：Stage 12 首个 Slice 消费方采用有界、同步、terminal 门控的字节访问

- 日期：2026-09-09
- 确认依据：用户在 #467/#471 决策与 Issue 分解讨论中，对 C-Q1～C-Q5
  推荐方案回复「确定」。
- 关联：#467、#471、#472。
- 原因：让首个真实输入字节消费方检验 SDK 边界，同时保持失败隔离、
  确定性和 Project Truth 的唯一性。

## 结论与确认边界

本条确认下列五项。细节依据
[Capability 设计 §10.5](../../design/2026-08-31-lmdj-stage12-capability-artifactsource-design.md#105-可直接评审的推荐方案仍未批准)
的推荐方案解释；旧文的未批准状态是此前历史，本条仅覆盖这里列明的范围。
未在会话中明确列出的公开身份、token 和配方行为仍需下述收口工作，
不得把一句确认扩展为整个 Candidate 设计已批准。

| 决策 | 已确认规则 | 实施验证义务 |
| --- | --- | --- |
| C-Q1 | 首个消费方为 sample.slice，输入 PCM16 WAV；SDK 校验 Artifact 绑定、权限、hash 和长度，Provider 解码 WAV；输出 Schema validator 由消费方拥有并由 execution 调用 | WAV chunk/padding/截断矩阵；未授权或不完整字节不能进入 run；SDK 不推导路径 |
| C-Q2 | 参考检测器使用整数 threshold_pcm16 与 refractory_frames，默认 4096 和 240；参考输出只用整数 frame/rate，保持原始采样率；结构化切片建议交给 Core 采纳路径 | 上下限、bool/未知参数拒绝、静音空点、源绑定、确定性字节；质量实测不能以 fixture 代替 |
| C-Q3 | memory_mib=64，聚合输入 16 MiB，聚合输出 256 KiB，timeout_ms=1000，max_attempts=1；显式预算注入 | 数值是参考实现待测起点。direct in-process timeout 仅观测，不宣称 hard deadline 或总 RSS 限制；保留 handle 的 lease 释放前不归还预算 |
| C-Q4 | source/sink 持有共享控制块、不借用 execute 栈；仅 run 线程同步调用；run 返回关闭回调，迟到调用返回错误且不改 terminal | 跨线程、保存回调、run-return 竞态；active first-error latch 使被 Provider 忽略的失败仍影响终态；已返回拥有型 bytes 保持安全 |
| C-Q5 | 私有 staging/reservation；已验证且耐久 terminal 是 outputs 对外可见性的提交标志；不扫描 blob 发现 Candidate、不回写旧 terminal | 在 publish/terminal 各交界中断独立进程，再启动 inspect 断言无半成品；无 terminal 残留保留为中断证据，GC/自动清理另议 |

C-Q1 不授权 Provider 取得 Project、bundle 或 Workspace 路径。
C-Q4 不要求销毁已返回的不可变拥有型 handle。
C-Q5 区分 bytes 落盘和对外发布，不承诺多个路径 rename 构成原子事务。

## 仍需精确收口的内容

用户确认的摘要没有逐项列出 profile ID/版本、平台和权限 token、
参数范围/可选输出字段上限、领域错误白名单。保留原设计 §10.2–10.5
作为这些值的具体提案，由下列计划中的 R1 逐项确认和记录后再开始 K1。
C-Q1～C-Q5 的方向决策不再重复提问；不能把未展示的常数称为用户已批准。

#471 的 CandidateSet/JobRecord API、recipe 端点补全、重试竞争规则、
重复采纳与到期策略未被这次 C-Q 确认覆盖。L1～L5 是待评审的任务边界，
不是已授权的产品或并发实现决定。Pattern Merge 与 Project Bin 继续保留
原开放问题边界。

## 版本与后续任务

替换 Provider 纯虚 run 是 MAJOR 变化，遵循
[既有字节访问决策修正](2026-08-24-provider-artifact-byte-access.md)；
SDK 2.0.0 是实施分配候选，不是本次修改 manifest 的结果。
K2 与候选 API Task 必须独立核对实际版本，不能各自预占 2.0.0。

任务收口与拆分见
[实施任务包](../../plans/2026-09-09-stage12-decision-followups.md)。

## Version Management

Version impact: none。本条记录决定，不改 active Contract、Module、
Provider、Host、Assembly、Product Build 或 Channel。

## Documentation Impact

Documentation impact: none。仅 retained 决策/计划；当前 Portal availability
与 manifest 派生身份不变。
