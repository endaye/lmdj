# 已确认：Release stress tier 在受信的裸机 macOS runner 上执行，不再在 KVM 主机上

- 日期：2026-09-19
- 关联：GitHub issue #1558；修订
  [2026-09-16 的决定](2026-09-16-master-fx-stress-attribute-guest-stolen-time.md)
  中"排除计费盲主机"被否定的那一项，原决定的门禁语义与预算不变。

## 结论

1. `core-nightly.yml` 的 `core-stress` job（自测批次中的 Self-test Release
   stress suite）以字面标签 `self-hosted`、`macOS`、`ARM64`、`lmdj` 路由到受信的
   裸机 macOS runner；TSan 仍留在 `ci-core`。两者继续加入 `lmdj-native-heavy`
   队列。
2. `master_fx_stress` 的 2,666,666 ns 回调期限、"恰好零未归因超限"的界、20 次
   连续重复且首败即停，全部不变；归因层保留（Linux 上仍编译、macOS 上为空）。
3. Owner 2026-09-19 在会话中确认（"2 和 3 都做"），选择的是 #1558 列出的方案 b。

## 原因

- 2026-09-16 的归因层依赖 `/proc/stat` 的 steal/IRQ/softirq 计数器，粒度是
  `USER_HZ=100` 的 **10 ms tick**；该决定自己记录了"亚 tick 事件不被计数，
  仍可能假红"的残余风险。
- 自 2026-09-18 起该 suite 在 netcup 上**没有一次通过**：连续四个 main 批次
  （35419357786、35425785114、35435898163、35441297299）同一形态，每次
  `1 of 3750 callbacks`，worst 分别 ≈8–9、4.74、4.74、9.0 ms，
  `steal 0 / irq 0 / softirq 0`——全部落在亚 tick 盲区。同一时段该物理主机上
  总有 3–4 条 Web lane 在编译。
- 同一 Release 构建在 M1 上 `--repeat until-fail:20` 20/20 通过，每次 20–60 ms。
- 原决定否定"排除计费盲主机"的理由是"没有哪台 CI 主机按设计是安静的，排除
  等于把 stress tier 迁出全部现有 runner"；现在有一台受信裸机 runner 承担
  macOS gates，它没有 hypervisor 可偷时间，前提已变。
- 备选方案的代价：给 guest 内核打开 `CONFIG_PARAVIRT_TIME_ACCOUNTING` 需要换
  内核（主机运维轨道 #1551 可并行推进；开启后归因层自然变无操作）；换亚 tick
  归因源只能看见 guest 内调度延迟，看不见 hypervisor steal。

## 影响

- Release stress 的可用性跟随该 runner：它离线时 suite 排队而非改跑别处
  （与 macOS gates 的 offline 语义一致，见 portal 页 testing-and-proof）。
- 该 runner 同时承担 macOS gates；两者未共享并发组，若观察到争用再决定是否
  把 macOS gates 也加入 `lmdj-native-heavy`。
- `docs/quality/core-test-policy.md` 与 portal 页同步更新；
  `tests/build/ci_nightly_workflow_test.py` 钉住路由、自托管 Python 检查与
  重复命令。
