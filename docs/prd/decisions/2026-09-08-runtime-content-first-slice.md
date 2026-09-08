# 已确认：B2 首切片为单 Pattern 与实时 Pad 的派生运行内容

- 日期：2026-09-08
- 来源：用户在 T1 合并后确认本条范围；前置设计为
  [ESP32 B2 Runtime-only](../../design/2026-09-08-lmdj-esp32-runtime-only-b2.md)。
- 结论：电脑保留 Project Truth；首切片导出单个 Pattern，并保留实时 Pad 触发所需
  材料，不实现 Pattern 切换。材料使用未压缩 PCM16，携带完整内容身份与校验。
  设备容量由后续真实预算测量决定，不把桌面默认值、测试夹具或 wire 字段宽度当硬件承诺。
- 装载体验：后续设备生命周期采用 stop → unload → load；新装载失败保持 empty，
  不自动恢复旧内容。不新增掉电续播或 Project 持久化。
- 本轮实施：T2 交付编码、读取验证与电脑侧 Core/Facade 导出入口；传输、设备命令、
  firmware、驱动、Product Assembly 集成与刷机留在后续 Task。本条不批准它们实施。
- 原因：先闭合可跨语言验证、可精确绑定来源 revision 的材料边界，再验证设备准入与
  render 生命周期；不把 ABI 内存镜像当成协议，也不让 Host 解析 Project Bundle。
- 影响：T2 的工程格式、校验规则和精确文件清单由
  [实施计划](../../plans/2026-09-08-runtime-content-export.md) 固定；schema、正反例、
  独立 reader 与 C++ codec 同 Task 评审。Digest 仅证明一致性，不代表鉴权。

本条确认上述产品选择，不表示用户逐项指定了编码偏移、C++ 签名或 Contract 名称。
这些属于 T2 的可审查工程实现，不应反写成用户的原话。尚未确定的传输、信任根、
断连行为、设备资源上限和 volatile 命令 epoch/receipt 协议继续保留，不能由 T2 补定。
