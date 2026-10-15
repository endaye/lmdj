# 已确认：Release stress 钉在 M1；macOS gates 按机器选择并进入该机器的队列

- 日期：2026-10-15
- 关联：GitHub issue #2278；修订
  [2026-09-19 的决定](2026-09-19-release-stress-on-bare-metal.md) 中 Release
  stress 的路由标签，以及
  [2026-10-15 的主机级队列决定](2026-10-15-per-host-native-heavy-queues.md)
  中的 `lmdj-native-heavy-macos`。

## 结论

1. 每台受信 Mac 带一个主机标签：M1（`endaye-mbp-m1`）为 `lmdj-mac-m1`，M4 Pro
   （`endaye-mbp-m4-pro`）为 `lmdj-mac-m4`。Mac 只有同时带角色标签
   `ci-macos-gates` 时才会被选去跑 macOS gates。
2. Release stress 以 `self-hosted, macOS, ARM64, lmdj, lmdj-mac-m1` 路由，队列为
   `lmdj-native-heavy-macos-m1`。它的 2.67 ms 期限只在 M1 上验证过，M4 Pro 不接。
3. `select-macos-runner` 的选择顺序：空闲且已获准的 M4 Pro → 在线且已获准的 M1
   （busy 则排队）→ busy 但已获准的 M4 Pro → GitHub-hosted macOS。它同时输出所选
   Mac 的队列（`lmdj-native-heavy-macos-m1` / `-m4`），`macos-primary` 使用该队列；
   hosted 路径沿用 M1 的队列槽位。
4. M4 Pro 注册时只带 `self-hosted, macOS, ARM64, lmdj-mac-m4`，不带 `lmdj`，也不带
   `ci-macos-gates`；benchmark 验收通过后，再经 Runner API 添加 `ci-macos-gates`。
5. Owner 2026-10-15 在会话中确认（"同意，先做第 1 步"）。

## 原因

- 原选择器按名字检查 M1，但输出的是通用标签 `self-hosted, macOS, ARM64, lmdj`，
  `core-stress` 也用同一组标签。第二台带 `lmdj` 的 Mac 注册后会直接接到 Release
  stress 和 gates，既没有 benchmark，也不在自己的队列里。
- M4 Pro 不总是开机：只在空闲时优先选它，job 会在选择后数秒内开始；忙时让给常开
  的 M1，避免 job 卡在一台随时可能合盖的机器上。
- 两台 Mac 不共享 CPU：gates 在 M4 Pro 上跑时，Release stress 可以同时在 M1 上跑。
- 标签按精确相等比较；jq 的 `contains` 是子串匹配，会让 `lmdj-mac-m1` 满足 `lmdj`。

## 影响

- 合并前已经通过 Runner API 给 M1 加上 `lmdj-mac-m1` 与 `ci-macos-gates`，因此合并
  后 Release stress 与 gates 仍会落在 M1 上。
- `tests/build/ci_runner_fallback_test.py` 用伪造的 Runner API 回复真实执行选择器，
  覆盖各分支；`tests/build/ci_build_acceleration_test.py` 继续跨 workflow 钉住每个
  成员的队列与路由主机一致。
- `docs/quality/core-test-policy.md`、portal 页 testing-and-proof 与
  shared-host-runner-capacity pitfall 同步更新。
