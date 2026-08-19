# `core-mcp` 何时从 MCP 2025-11-25 升级到 2026-07-28 之后的无状态协议？

- 范围：新内核（Playable Beat Instrument）
- 状态：延后
- 来源：2026-08-19 对 `apps/core-mcp` 协议版本的评估
- 为什么重要：MCP 2026-07-28 是该协议发布以来最大的改版——移除
  `initialize`/`initialized` 握手，协议版本与客户端能力改为随每个请求的
  `_meta.io.modelcontextprotocol/*` 字段携带，并新增取消通知与可缓存的
  list 结果。`core-mcp` 是手写的零依赖 stdio 适配器，升级不是改常量：
  要拆除 `Server` 的 NEW/READY 状态机与 `-32002` 语义，改为逐请求协商，
  并重写 `tests/host/mcp_stdio_test.py` 的 lifecycle fixture 与 parity
  测试，是一个完整 Task。同时新版的核心收益（HTTP 负载均衡下的无状态
  横向扩展、header 路由）对客户端拉起的本地 stdio 子进程几乎没有价值，
  而官方向后兼容矩阵让新客户端自动回退到 initialize 握手，弃用窗口承诺
  至少 12 个月（约至 2027-07），2025-11-25 在此期间保持可用。过早跟进
  意味着为一份发布仅数周、客户端支持仍在铺开的规范承担手写实现的全部
  勘误成本。
- 处理时点：满足任一条件即启动升级 Task——(1) Claude Code 或其他依赖的
  主要客户端公布 initialize 回退路径的移除时间表；(2) `workers/` 的
  out-of-process Provider Host 需要 HTTP transport（无状态核心届时才有
  真实价值）；(3) 弃用窗口过半（约 2027 年初）作为兜底。届时按 Contract
  变更走独立计划，不在实现 Task 内顺手切换协议版本。
