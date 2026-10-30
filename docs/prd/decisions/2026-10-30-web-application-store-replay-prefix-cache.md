# 已确认：Web control runtime 的 Application store 也复用已重放的历史

- 日期：2026-10-30
- 关联：[#2518](https://github.com/endaye/lmdj/issues/2518)（本决策解决的问题）、
  [#2504](https://github.com/endaye/lmdj/issues/2504) 与
  [2026-10-26 决策](2026-10-26-project-load-replay-prefix-cache.md)（本决策扩展其范围）、
  [#2422](https://github.com/endaye/lmdj/issues/2422)。Owner 于 2026-10-30 在会话中选择
  “扩展 #2506 的缓存”，未选择“已知 Pad 跳过 inspect”（需要改 `project.inspect`
  Contract 或在客户端缓存触发模式）。
- 结论：Web control runtime 构造 Application 时打开
  `ApplicationConfig::project_replay_prefix_cache`，让 Application 的 `ProjectStore`
  像录音 IO owner 的 store 一样只重放 manifest 新追加的交易。其他 Host 默认关闭；
  2026-10-26 决策的全部校验与回退（head checkpoint 比对、Asset 字节校验、manifest
  不再延伸缓存列表或任何 load 失败即完整重放）不变。
- 原因：Creator 每次 pad press 先调用 `sample.inspect`，再发出输入请求。空闲 M1 上，
  录音切换 journey 中 Application store 的每次 load 都从 checkpoint 0 重放 66–77 条交易
  （平均 134 ms、最大 378 ms），`sample.inspect` 中位 307 ms、最大 716 ms，使 press 越过
  1 秒输入预算；同一时刻有缓存的 IO owner store 每次只重放 0–1 条。OPFS 目录句柄缓存的
  A/B（各 12 次）失败率不变（5/12 对 6/12），说明瓶颈不在目录查找。
- 接受的取舍：与 2026-10-26 决策相同，同一进程内被原地破坏的已重放交易文件不再由
  Application store 的后续 load 发现；下一个进程仍完整重放并发现它。
- 非目标：不改 Project Bundle Contract、交易格式、manifest、`project.inspect` 或
  Creator 输入路径；不改任何超时或预算；native/CLI Host 不启用。
- 影响：`ApplicationConfig` 末尾新增 `project_replay_prefix_cache`（默认 false）；
  `ControlRuntime` 构造时打开；Project I/O portal 页记录该范围。

## 补充：录音结束后的 Runtime 准备共享同一缓存（同日）

- 关联：[#2422](https://github.com/endaye/lmdj/issues/2422)。Owner 于 2026-10-30 在会话中
  选择“共享重放缓存”，未选择“只在准备内部去重”。
- 结论：Application 打开 `project_replay_prefix_cache` 时，`make_runtime_snapshot_preparer`
  返回的分离式准备器捕获 Application store 的缓存句柄（`ProjectStore::replay_prefix_cache`），
  它在 worker 上新建的 store 通过 `ProjectStore::share_replay_prefix_cache` 共享这份缓存；
  缓存自带互斥锁。未打开时句柄为空，准备器照旧完整重放。准备器仍不捕获 Application、
  authoring history、会话登记或 writer lease。
- 原因：录音关闭后，Host 在 worker 上准备新的 Runtime 视图，期间 `publish_pending` 挡住
  count-in ticket 的消费。空闲 M1 上该准备耗时 350–650 ms，其中两次从 checkpoint 0 的完整
  重放占 85–90%（各 150–300 ms），cook 只占 40–70 ms，使 COUNT-IN 录音切换 journey 越过
  1 秒消费窗口。
- 接受的取舍、非目标：与上文相同；不改任何超时或预算。
