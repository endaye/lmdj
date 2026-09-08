# Provider 多端口 Capability Contract 决策

日期：2026-08-01

状态：已批准

批准记录：2026-08-01，四项决策全部确认。

## 要决定什么

在进入 Stem、Slice、Export 等多输入或多输出 Capability 之前，明确 Artifact
属于哪个命名端口，以及 Request、Artifact Sink、Candidate、Attempt 记录如何保存并
校验该绑定。

本决策本身不修改现有 Contract、Provider SDK 或 Product Assembly。实现必须按
[Capability v2 端口绑定实施计划](../plans/2026-08-01-lmdj-capability-v2-port-bindings.md)
独立执行、验证和分配版本。

## 当前事实

- `ArtifactPortDescriptor` 已声明端口 `name`、media type、Artifact Schema、
  `required` 和 `max_count`。
- `CapabilityRequest.inputs` 和 `Candidate.outputs` 都只是扁平的
  `ArtifactRef` 数组，没有端口名。
- `ArtifactSink` 只接收 bytes 和 media type，Provider 生成 Artifact 时也无法声明
  输出端口。
- 当前请求校验只对所有端口的 media type 做并集判断，数量校验只读取第一个输入
  端口；Candidate 数量校验同样只读取第一个输出端口。
- 因此当前数据结构无法无歧义表达多端口结果。直接把 `.front()` 改为循环仍无法
  区分两个接受相同 media type 或 Schema 的端口。

证据见 [Core Review](../quality/2026-08-01-core-review.md) 和当前
`packages/provider-sdk` 的 `capability.hpp`、`attempt_store.cpp`。

## 必须保持的边界

- Project Truth 不保存 Provider 选择、Attempt 失败或未采用 Candidate。
- Provider 只接收 Artifact 输入和 Artifact 输出 sink，不接收可变 Project 或
  Project bundle 路径。
- 端口身份必须显式、稳定并进入 canonical evidence；数组顺序不得承担端口语义。
- 每个端口独立执行 `required`、`max_count`、media type 和 Artifact Schema 校验。
- Provider 返回无效绑定时只失败当前 Attempt，不得产生 Project mutation。

## 选项

| 选项 | 说明 | 结论 |
| --- | --- | --- |
| A. 数组位置隐式对应端口 | 用 Descriptor 顺序切分扁平 Artifact 数组 | 否决；可选端口和多 Artifact 端口会使边界不唯一，重排也会改变语义。 |
| B. 按 media type 或 Schema 推断 | Artifact 自动匹配第一个兼容端口 | 否决；端口允许重叠类型，推断会把 Provider 错误伪装成合法结果。 |
| C. 每个 Artifact 显式绑定端口 | Request、Sink、Candidate 和 Attempt 都携带稳定端口名 | 批准；语义明确，可逐端口验证，也能稳定 canonicalize。 |

## 已批准的 v2 形态

新建 `lmdj.capability.v2`，不原地改变 `lmdj.capability.v1`：

```text
ArtifactBinding {
  port: string
  artifact: ArtifactRef
}

CapabilityRequest.inputs: ArtifactBinding[]
ArtifactSink.write(port, bytes, media_type): ArtifactRef
Candidate.outputs: ArtifactBinding[]
```

Attempt evidence 同时保存 Request input bindings、minted output bindings 和
Candidate output bindings。Canonical 顺序按 `port`，再按 Artifact 的
`sha256`、`media_type`、`byte_length` 排序；调用方输入顺序不影响身份。

## 已批准的验证语义

### Descriptor 注册

- 输入端口名在输入集合内唯一，输出端口名在输出集合内唯一。
- `max_count >= 1`；`required=true` 表示 `min_count=1`，否则为 `0`。
- Candidate-producing Capability 至少声明一个输出端口；所有输出端口均可选时，
  零 Artifact Candidate 可以成功。
- v1 只允许单输入端口和单输出端口；不得继续宣称支持 v1 多端口。

### Request

- 每个 binding 必须引用已声明输入端口，且 Artifact 必须满足该端口的 media type；
  binding 同时选择该端口声明的 Artifact Schema 身份，字节级验证边界见下文。
- 每个端口独立计算数量，缺少 required 端口、超过 `max_count`、未知端口和未绑定
  Artifact 均返回 `INVALID_ARGUMENT`，Provider 不得被调用。
- 初始 v2 保留当前全局输入 Artifact 唯一性：同一 Artifact Ref 不得重复绑定；若
  产品以后需要一份 Artifact 承担多个角色，另行做 Contract Review。

### Sink 与 Candidate

- Sink 只接受已声明输出端口，并在写入时校验该端口允许的 media type。
- Terminal validation 对每个输出端口独立检查数量和 Schema。
- 每个成功 mint 的 Artifact 必须在 Candidate 中恰好出现一次并绑定同一端口；
  Candidate 不得引用未 mint、重复或未知端口 Artifact。
- 无输出端口 Descriptor 在注册期拒绝，消除“注册成功、执行期必失败”的不一致。

### Schema 验证边界

`ArtifactRef` 当前只携带 hash、media type 和 byte length，不携带 Schema provenance，
AttemptStore 也没有可解析输入 bytes 的 Artifact resolver。因此本次 v2 实现必须验证
binding 选中的端口及其声明的 `schema_id` / `schema_version`，但不得声称已经完成
输入 Artifact 字节级 Schema 校验。后者保留为独立架构问题；在 resolver 和具体
Artifact Schema 验证器获批前，不阻塞显式端口、逐端口数量和 media type 门禁。

## 不在本次决定内

- `Partial` Attempt 的用户产品语义、恢复和 Commit 策略；
- Timeout、取消、重试和跨进程 Provider Host；
- 具体 Stem、Slice、Export Capability 的端口名称和 Schema；
- Project 如何采用一个或多个 Candidate Artifact。

## 实施门禁

- 两个端口接受相同 media type 时仍能按显式端口正确区分；
- 第二个 required 输入或输出缺失时失败；
- 任一非首端口超过 `max_count` 时失败；
- 未知端口、重复绑定、错误 Schema 端口、错误 media type 均有负向测试；
- Sink 端口与 Candidate 端口不一致时失败并清理 staged Artifact；
- 所有可选输出端口均为空时有明确成功测试；
- 输入顺序和输出顺序变化不改变 canonical evidence；
- v1 Schema 不变性、Attempt 隔离和 Project bundle 不变性继续通过。

## 已确认项

1. 采用选项 C，并以 `lmdj.capability.v2` 表达显式端口绑定。
2. 拒绝无输出端口的 Candidate-producing Capability。
3. 允许所有可选输出端口均为空的成功 Candidate。
4. 初始 v2 继续禁止同一 Artifact Ref 绑定多个端口。

四项已于 2026-08-01 全部确认。决策同步写入
[`docs/prd/decision-log.md`](../prd/decision-log.md)，多端口开放问题不再保留为待决。

## Version Management

Version impact: none

Reason: 本提交只确认 Contract 决策并新增实施计划，不修改 Product、Module、
Contract、Provider 或 Model 身份。实施计划分配 `lmdj.capability.v2` `2.0.0`、
受影响 Module / Provider 版本和 Product Build `1.0.8.0`；这些身份只在后续实现
提交中生效，本决策提交不创建 Product Build 或 tag。
