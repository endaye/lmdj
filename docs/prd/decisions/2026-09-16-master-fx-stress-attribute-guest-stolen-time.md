# 已确认：master_fx_stress 的实时门禁归因 guest 被计费时间，而不是容忍它

- 日期：2026-09-16。
- 关联：GitHub issue #666；本条确认其评论链末段三个候选方案中的
  「归因而非容忍」方案。

## 结论

1. `tests/core/audio/master_fx_stress_test.cpp` 的实时门禁保持**恰好零
   超限**，但超限被分成两类：渲染窗口内渲染线程所在 vCPU 的
   steal/IRQ/softirq 计数器没有前进的，记为未归因超限，门禁继续断言
   其为零；计数器有前进的，记为已归因超限，只报告、不计入门禁。
2. 归因数据来自每个渲染窗口首尾对 `/proc/stat` 的采样（Linux 限定；
   非 Linux 主机上该层编译为空，行为与之前一致）。窗口内线程未迁移时
   用所在 vCPU 的 per-CPU 计数器，迁移时退回聚合计数器并在报告中
   保持可见。
3. **不提高任何 deadline、budget 或 threshold。** 2,666,666 ns 的回调
   期限不动；被否定的是测量在 guest 上的有效性，不是预算。
4. 失败输出同时报告两类计数与各归因计数器总量；通过但发生归因时
   也留一行 note，防止归因静默掩盖真实回归。

## 原因

#666 的评论链已经把证据走完了：

- 两台自托管主机（contabo、netcup）都是 KVM guest，且两者内核均未
  编译 `CONFIG_PARAVIRT_TIME_ACCOUNTING` 与
  `CONFIG_IRQ_TIME_ACCOUNTING`(`/boot/config-6.8.0-*` 实测）。两者
  任一关闭时，hypervisor 偷走的时间和硬中断时间会被计入当时正在运行
  的线程的 `task_sched_runtime`，也就是 `CLOCK_THREAD_CPUTIME_ID`。
- 测试自己的注释声称的免疫力（"shared CI runner may deschedule this
  thread … so the production timing gate uses thread CPU time"）对内
  核调度成立，对 guest 不成立：一次多毫秒级的 steal/IRQ 事件落在一次
  `engine.render()` 内，就会把 ~36 µs 的真实工作记成超过
  2,666,666 ns 的"超限"——这正是裸机上需要 70× 膨胀、而 contention
  无法合法产生的幅度（#692 的测量），由计费而不是工作产生。
- 失败形状与归因假说完全吻合：负载触发、空闲通过、两台 guest 都
  出现、容量队列无法隔离 hypervisor、除 `callback_overruns != 0` 外
  一切断言正常。

被否定的两个候选：

- **钉线程 / 排除"计费盲"主机**：钉住线程不能阻止 vCPU 被
  hypervisor 偷走；而且没有哪台 CI 主机按设计是安静的，排除等于把
  stress tier 迁出全部现有 runner。
- **给 runner 镜像打开两个内核选项**：方向上正确，采纳后归因层
  自然变为无操作（计数器不再前进，门禁直接测到干净量），无需再改
  测试；但镜像不在本仓库控制面内，不能作为本 issue 的关闭条件。

## 影响

- 门禁语义从「`CLOCK_THREAD_CPUTIME_ID` 零超限」修正为「回调实际消耗
  CPU 零超限」——这才是该测试要守的性质；在 guest 上由计费错位产生
  的假失败停止阻塞 nightly stress。
- 残余风险如实记录：真实回归的超限窗口恰好撞上无关计数器前进时会
  被误归因（按实测计数器速率估算每次超限约 1–3% 的概率）；若 FX 路径
  真实退化，绝大多数超限仍未归因，门禁依旧会红，且失败与通过路径都
  报告归因总量供人审阅。
- 测量粒度上限：USER_HZ=100，计数器 tick 为 10 ms；亚 tick 的
  steal/IRQ 事件可能不被计数（漏归因，即仍可能假红），不会误归因。
- Contabo 的 steal 计数器自启动起为零（paravirt steal clock 未暴露）,
  该主机上 steal 腿不可测量，IRQ 腿仍然有效；netcup 两腿都有效。
- `docs/quality/core-test-policy.md` 中「nightly stress 失败是 sibling
  contention」的旧归因按 #666 验收要求一并更正。
