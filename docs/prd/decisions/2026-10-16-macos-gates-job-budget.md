# 已确认：macOS primary job 的挂死检测上限校准为 40 分钟

- 日期：2026-10-16
- 关联：[问题 #2283](https://github.com/endaye/lmdj/issues/2283)。Owner 在协调者
  会话中选择「A：上限调到 40 分钟」，协调者将这一预算决定转达给执行 worker。
- 结论：只将 `.github/workflows/ci.yml` 的 `macos-primary.timeout-minutes`
  从 30 改为 40。**上限是挂死检测，不是性能目标。**

## 已测量的原因

M1 的主要耗时是串行 ASan native CTest 工作量。两次有完整日志的超时运行
缓存命中率已超过 98%，编译并不是主要成本。最近一次 M1 成功运行在缓存
100% 命中时仍花了 29 分 34 秒，距原 job 上限只剩 26 秒。

下表单位为秒；configure/build 合计取两段 CMake 首条输出到 CTest 开始的
日志时间差，省略亚秒级启动时间，包含 ASan 的 Apple target 检查。

| Run / job | Runner / job 结论 | Job 总计 | configure/build 合计 | Core CTest | ASan native CTest | ccache 命中 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [38588990296 / 115942282428](https://github.com/endaye/lmdj/actions/runs/38588990296/job/115942282428) | M1 / cancelled | 1915 | 46.97 | 125.71 | 1710.95 | 524/530 |
| [38619404365 / 116053993315](https://github.com/endaye/lmdj/actions/runs/38619404365/job/116053993315) | M1 / cancelled | 1904 | 35.53 | 127.50 | 1691.18 | 529/530 |
| [38662185311 / 116188198978](https://github.com/endaye/lmdj/actions/runs/38662185311/job/116188198978) | M1 / success | 1577 | 54.99 | 127.58 | 1339.41 | 525/530 |
| [38842939814 / 116794145441](https://github.com/endaye/lmdj/actions/runs/38842939814/job/116794145441) | M4 Pro / success | 1320 | 198.75 | 118.05 | 931.61 | 277/530 |
| [38860143940 / 116842395250](https://github.com/endaye/lmdj/actions/runs/38860143940/job/116842395250) | M1 / success | 1653 | 47.16 | 136.90 | 1414.87 | 526/530 |
| [38880015551 / 116906584110](https://github.com/endaye/lmdj/actions/runs/38880015551/job/116906584110) | M1 / success | 1774 | 51.38 | 144.94 | 1497.37 | 530/530 |

两个超时 job 的 `facade.pattern_count_in_stress` 各耗时约 625–629 秒。
[#2272](https://github.com/endaye/lmdj/pull/2272) 已交付独立轮次的并行执行；
其合并提交 `b5f5d78ac553477134c0ebfaa70ffb930733f784` 就是表中第一次后续
M1 通过运行的目标。随后八次 M1 job 全部通过，耗时 1468–1774 秒，count-in
单项为 190.24–279.14 秒。这个已交付修复不再重复实施。

M4 与 run `38860143940` 的 M1 检出同一个目标
`183f90241c6d4d7499433cb78a44e3197f03a21d`。M1 的 native CTest 多花
483.26 秒，却少花 151.59 秒编译；candidate-store stress、count-in stress、
web-control runtime 三项合计贡献 320.07 秒的测试差值。这是跨主机观察，
不是隔离负载的硬件基准；日志不能确定热状态或本机负载造成的波动。

完整 [14 天清单与前提核验](../../plans/2026-10-16-lmdj-macos-gates-timeout.md)
保留 77 个 job，包括失败和跳过。三份历史执行日志返回 404，其 phase 仍未知；
首行另有 `provider.conformance` 失败，预算调整不会修复它。历史 job 结论不等于
完整测试通过，也不因本决定而清除验证欠账。

## 运行边界与再评估

- 测试选择、CTest timeout、编译并发、队列、runner 标签和 `macos-fallback`
  都保持不变；没有重跑旧批次或派发新批次。
- 自 [#2278](https://github.com/endaye/lmdj/issues/2278) 起，已准入的 M4 Pro
  空闲时优先接 gates；M4 忙或离线时由在线 M1 执行。M4 在 run `38842939814`
  的 gates step 耗时 1265 秒，约 21 分钟；这不取消 M1 的执行预算需求。
- **任何 M1 `Run macOS Core gates` step 超过 35 分钟，下一步必须是测试优化，
  不再继续提高 job 上限。** 这是人工再评估触发条件，不添加自动 CI gate。
- 根因工作继续由 [#2306](https://github.com/endaye/lmdj/issues/2306)
  （candidate-store stress）和 [#2284](https://github.com/endaye/lmdj/issues/2284)
  （journal save）承接。本决定只提供执行余量，不声称减少了测试工作量。
- Portal 完整检查由协调者在另一台机器的新 clone 上对精确推送 head 执行，
  在 PR 记录结果；M1 不运行这个重型检查。修改后的真实 CI 运行仍待观察。
