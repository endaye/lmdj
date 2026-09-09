# 已确认：Cardputer 首版以 USB 装载后独立演奏的四 Pad 鼓机构成最小闭环

- 日期：2026-09-10。
- 来源：用户在审阅 [D1 草案 PR #1112](https://github.com/endaye/lmdj/pull/1112)
  及“USB 装载、拔线演奏、4 Pad／合计 1 秒鼓音／至少 4 声部、30 分钟稳定运行”
  的确认请求后答复“批准”。本条记录产品范围批准，不把它解释为容量、测试或评审通过。
- 结论：首版采用电脑命令行导出与 USB 有线内容传输；用户在设备确认接收，信任
  物理连接的本机，不提供密码学发送者认证。成功装载后，在电池等供电持续的情况下
  拔线仍可通过本地键盘演奏单 Pattern 与实时 Pad；接收中断丢弃未完成事务，保持
  empty，重连后从头传输。复位 empty、不自动播放、不保存 Project Truth 或掉电续播。
- 能力目标：4 个 One Shot Pad、总计 1 秒的不同鼓音、至少 4 个声音实际重叠、
  单个两小节 Pattern；完整音乐、输入、显示与 USB 活动共同负载下连续运行
  30 分钟。精确 fixture 与测量口径由配套设计固定；目标不等于已支持的容量。
- 交互边界：首版有实体 Pad、播放/停止、音量/静音、接收确认与最小状态显示。
  暂不包含 Wi-Fi、蓝牙、SD 导入、Creator 新界面、设备编辑/录音/采样。
- 原因：从指定单音探针推进到可独立演奏的真实音乐闭环，先固定价值与验收口径，
  再以同口径暴露资源问题，而不是按现有小夹具能通过的范围定义产品。
- 影响：完成 [D1 #1105](https://github.com/endaye/lmdj/issues/1105) 的产品确认前置，
  后续按 [设计](../../design/2026-09-10-cardputer-runtime-host.md)和
  [实施计划](../../plans/2026-09-10-cardputer-runtime-host.md)推进。
  R1 若未满足目标，保留负结果并拆根因修复；不能降低目标或提前解除 H1 的容量前置。
  正式真机验收前必须有可追溯测试 Build 与同 Build 不可变快照。

沿用 [Runtime Content 首切片](2026-09-08-runtime-content-first-slice.md)与已实现的
Facade 生命周期，不重新批准另一套 Core epoch/sequence/receipt 语义。
Pad 键位、音量档位、framing 字节布局及错误枚举是本范围下的可审查工程细节，
不是声称用户逐项指定的原话。新传输 Contract 不修改现有 Runtime Content 或 Project
Contract，也不把传输 nonce 变成 Runtime epoch。

本次批准覆盖首版实现与正常 Task 交付；不启动 tag、Release、部署、Channel 晋级
或备份清理。解决的开放选择由 D1 Issue 承载，没有需要删除的独立 questions 文件。
