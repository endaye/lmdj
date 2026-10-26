# 已确认：录音会话的 ProjectStore 复用已重放的历史，只重放新追加的交易

- 日期：2026-10-26
- 关联：[#2504](https://github.com/endaye/lmdj/issues/2504)（本决策解决的问题）、
  [#2422](https://github.com/endaye/lmdj/issues/2422)、
  [#2503](https://github.com/endaye/lmdj/pull/2503)。Owner 于 2026-10-26 在会话中
  选择选项 A（信任不可变性，仅限 Sequence Journal 活跃时的 load）。
- 结论：录音会话的 IO owner 为其 `ProjectStore` 打开重放前缀缓存。该 store 记住最近
  一次已与 head checkpoint 比对通过的重放结果；之后的 load 只要 manifest 的交易列表
  以缓存列表开头，就从缓存状态起只重放新追加的交易。缓存的前缀不重读：已提交的交易
  文件以 `create_immutable` 写出、从不改写。head checkpoint 比对、Asset 字节校验、
  recovery 与提交路径不变。manifest 不再延伸缓存列表、换了 bundle、或任何一次 load
  失败时，退回完整重放。其他 store 与每次进程启动仍从 checkpoint 0 完整重放。
- 原因：录音中切换 Pattern 时，一次分段步骤在 OPFS 上耗时 630–770 ms（空闲 M1），
  负载下约 1 s；耐久写只占约 8 ms，其余几乎都是每次 load 从 checkpoint 0 重放全部
  历史，且历史随每次录音 flush 增长。迟到的 release 与切换后的 press 都等这一步，
  所以录音切换 journey 从未在 main 批次通过。#2503 去掉一次多余 load 后，本地两 worker
  A/B 只从 4/12 变为 5/12。
- 接受的取舍：同一进程内被原地破坏的旧交易文件不再被后续 load 发现；下一个进程仍会
  完整重放并发现它。字节比对（选项 B）保留这一检测但只省约一半开销，未采用。
- 非目标：不改 Project Bundle Contract、交易格式或 manifest；不对普通编辑会话启用。
- 影响：`ProjectStore::enable_replay_prefix_cache`（Project I/O 新公开方法）、
  `PatternTransportIoOwner` 在构造时启用；Project I/O portal 页记录该行为。
