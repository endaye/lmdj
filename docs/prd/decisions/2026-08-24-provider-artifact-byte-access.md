# 已确认：Provider 的 Artifact 字节访问由 provider-sdk 以 capability 门控的对称 Source/Sink 接口提供，首个真实消费方出现前不实现

- 日期：2026-08-24
- 解决的问题：`docs/prd/questions/provider-artifact-byte-access.md`
  （原状态 *待架构设计*，已按约定在本决策的同一个 Task 删除），GitHub Issue
  [#206](https://github.com/endaye/lmdj/issues/206)，machine-task 清单
  [D3](../../quality/2026-08-17-machine-task-todo.md)。
- 结论：
  1. **输入侧正式接口在 provider-sdk 层。** 形状是与 `ArtifactSink` 对称的
     `ArtifactSource` 读取回调，随 `Provider::run` 传入，仅能解析本次
     `CapabilityRequest` 显式声明的输入端口（端口与 sha256 绑定由
     AttemptStore 在调用前校验）。Provider 不获得任何 ambient 文件系统权限，
     `CLAUDE.md` 不变量「Provider code receives Artifact inputs and an
     Artifact output sink」的输入半由此成真。
  2. **输出侧字节访问口同样落在 provider-sdk 层**，与输入 resolver 同一次
     设计、同一次 Contract Review 落地。Host 按
     `.lmdj-workspace/attempts/` 私有磁盘布局重建路径的做法停留在原型；重申
     [decision-log 2026-08-16 条目](../decision-log.md)：analysis-bench 原型
     的 Host 注入桥接是临时方案，不得毕业为正式接口。
  3. **Schema 验证边界不变。** `ArtifactRef` 不增加 Schema provenance 字段，
     `lmdj.capability.v2` 不因此升级。端口身份由 binding 选择的显式端口声明
     （`schema_id` / `schema_version`），AttemptStore 继续只做端口、数量与
     media type 门禁，不把端口身份校验伪装成字节级 Schema 校验；后者由消费
     方（Provider 与获批的 Artifact Schema 验证器）负责，与 resolver 设计
     同期评审（沿用
     [2026-08-01 Provider 多端口决策](../../architecture/2026-08-01-provider-multi-port-contract-decision.md)
     划定的边界）。
  4. **时序：刻意不现在实现。** 首个必须解析结构化 Artifact bytes 的正式
     Capability 实现前，以独立 Task、独立 Contract Review 落地；provider-sdk
     MINOR 及依赖级联在那时支付。在此之前没有真实消费方，提前落地只会让一
     个未经消费者检验的 API 冻结进 SDK。
  5. **永久否决选项 C（经 `parameters` 传 fixture 根路径）。** parameters
     只哈希、不存储，Attempt 记录无法说明实际读了哪些字节；且它把 ambient
     文件系统权限交给 Provider 代码，正是 artifact-port 模型要消除的东西。
     不得以任何名义复活。
  6. **选项 B（fixture 字节嵌入 `src/provider.cpp`）获准作为确定性 Attempt
     重放 Provider 的临时方案。** 嵌入字节被 provider source-package 哈希
     覆盖、自验证；仅限小型 proof fixture，正式 Provider 不得沿用。重放计划
     [`2026-08-19-lmdj-attempt-replay-provider.md`](../../superpowers/plans/2026-08-19-lmdj-attempt-replay-provider.md)
     的 Task 0 就此解除阻塞，按 Tasks 1–4 继续；`ArtifactSource` 落地后再
     评估重放 Provider 是否迁移到正式接口。
- 原因：缺口是双向的且有两个独立消费方（首个解析结构化字节的正式
  Capability、重放 Provider）撞上同一面墙。三个候选中，A 是唯一让既定架构
  不变量成真、又不需要给 Provider 任何特权的答案；B 只对小型 proof fixture
  可行，作为退路使等待可承受；C 同时破坏 Attempt 记录的可审计性与
  artifact-port 权限模型。首个真实消费方尚无紧迫性，故现在只冻结方向与
  否决项，不支付 API 变更级联。
- 影响：本条只记录结论，不修改 Contract、SDK 或任何版本身份。D3 不再
  blocked on decision，但其实现工作保持 deferred 至上述触发时点；重放
  Provider 计划解除 Task 0 阻塞，按选项 B 继续。`ArtifactSource` 与输出侧
  访问口的 API 形状、校验边界与对现有实现/mock 的影响，属于触发时点后的
  独立 Task。
