# 已确认：native 重型队列按物理主机划分，不再是仓库级单一队列

- 日期：2026-10-15
- 关联：GitHub issue #2277；修订
  [2026-09-19 的决定](2026-09-19-release-stress-on-bare-metal.md)
  中"两者继续加入 `lmdj-native-heavy` 队列"与 `macos-primary` 加入该队列的措辞。
  Release stress 的路由、期限与界不变。

## 结论

1. 原仓库级 concurrency group `lmdj-native-heavy` 拆为两个主机级 group：
   - `lmdj-native-heavy-linux`：Linux 主机上的全部重型 job——Architecture
     Portal、Core Ubuntu、Core package、Linux ASan、coverage、四条 Web lane、
     TSan stress、Core benchmark；
   - `lmdj-native-heavy-macos`：受信裸机 Mac 上的 Release stress 与 macOS gates
     （`macos-primary`）。
2. 每个 group 保持 `queue: max` 与 `cancel-in-progress: false`。"同一物理主机上
   一次只运行一个重型 job"的不变量不变；只去掉两台不共享 CPU 的主机之间的串行。
3. 新主机承接重型工作时使用自己的队列，不复用既有主机的角色标签或 group。
4. Owner 2026-10-15 在会话中确认（"行，你帮我写一个 plan，然后来处理这件事吧"），
   此前已确认诊断：等待来自全局锁而非 runner 数量。

## 原因

- 近 7 天（截至 2026-10-15）352 个 job 中，netcup/contabo 普通 job 排队
  p50≈0、p90≈0.1 分钟；netcup baseline 四个 runner 采样时三个空闲。
- 长等待只出现在锁成员上：`core (ubuntu-latest)` 160–199 分钟、`core-tsan`
  68–139 分钟、`core-stress` 78–98 分钟、macOS gates 129–169 分钟。
- self-test run `38588990296`：macOS gates 15:31 入队，前一个锁持有者
  `core-stress` 17:40:43 结束，5 秒后 gates 开始；run `38619404365` 同形态
  （TSan 22:08:51 结束 → gates 22:08:56 开始）。M1 在线且空闲，等待全部来自
  跨主机的锁。
- 2026-09-19 决定把 `macos-primary` 加入队列，是为防止 gate 与 Release stress
  在同一台 Mac 上并行；主机级 group 保留了这一目的。

## 影响

- 一个完整批次中，Mac 上的 Release stress（约 31 分钟）与 macOS gates（约 32
  分钟）可与 Linux 序列并行，预计每批缩短约 60 分钟；Linux 主机内部仍串行。
- 走 hosted fallback 时 `macos-primary` 仍占 macOS 队列的一个槽位，与原语义一致。
- `docs/quality/core-test-policy.md`、portal 页 testing-and-proof 与
  shared-host-runner-capacity pitfall 同步更新；
  `tests/build/ci_build_acceleration_test.py` 跨全部 workflow 钉住每个成员的
  group 与其路由主机一致。
- 第二台 Mac（#2278）与 Win11 WSL runner（#2279）上线时，各自需要独立的主机级
  队列。
