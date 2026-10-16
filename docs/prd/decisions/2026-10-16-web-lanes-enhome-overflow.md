# 已确认：四条 Web lane 在 en-home 工作站空闲时溢出到它，否则回落 netcup

- 日期：2026-10-16
- 关联：GitHub issue #2279；在
  [2026-10-15 主机级队列决定](2026-10-15-per-host-native-heavy-queues.md)
  的基础上新增一个主机队列。

## 结论

1. en-home（Owner 的 Windows 工作站）里 WSL2 发行版 `LMDJ-Runner-Ubuntu` 中的 runner
   `win11-wsl-lmdj-linux` 带主机标签 `lmdj-wsl-enhome`；只有同时带准入标签
   `ci-web-overflow` 时，才能接 Web lane。
2. 新增 `select-web-runner`。en-home 在线、空闲并且标签精确匹配时，它输出 en-home 的标签
   集合和队列 `lmdj-native-heavy-enhome`；其他情况一律输出 netcup 的 `ci-web-heavy`
   与 `lmdj-native-heavy-linux`，包括工作站忙、离线、未准入，token 缺失，以及 Runner API
   失败。Linux 没有 hosted 回落。
3. 四条 Web lane（Web Toolchain、Web Runtime Host、Creator、Web Runtime Lab）都使用
   选择器的输出；netcup 的标签和队列是表达式的字面默认值。
4. 工作站并非常开，准入标签就是开关：长时间离线前先撤下 `ci-web-overflow`。已经派过去的
   lane 会等它回来，不会改派。
5. Owner 2026-10-16 在会话中选择"4 条 Web lane (Recommended)"。

## 原因

- 一个角色标签不能同时出现在两台主机上。GitHub 在 concurrency group 确定之后才选 runner，
  共用角色要么让两台主机重新串行，要么让 lane 占着另一台主机的槽位（见主机级队列决定，以及
  #2285 修复的 Portal 问题）。
- 工作站会睡眠、会重启，不能把 lane 固定给它：固定之后它一离线，批次就会停住。按空闲选择、
  否则回落 netcup，只会增加并行度，不会降低可用性。
- 四条 Web lane 是批次里最长的 Linux 任务，单条 25–44 分钟。它们在 en-home 上依次跑的同时，
  netcup 跑 native-heavy lane。

## 影响

- 主机侧：在 WSL 里安装了 git-lfs、Playwright 1.62.1 依赖的 Chromium/WebKit 系统库，以及
  emsdk、浏览器、npm 的持久缓存目录，写入 runner 的 `.env`。`install-system-deps` 保持
  `"false"`。
- `tests/build/ci_runner_fallback_test.py` 用伪造的 Runner API 回复真实执行选择器；
  hosted 支出策略测试只因选择器从不输出 hosted 标签集合，才允许 Web lane 使用动态
  `runs-on`。
- 风险：Owner 在工作站上的日常负载可能让浏览器测试的固定预算抖动；验收要以真实批次为准。
