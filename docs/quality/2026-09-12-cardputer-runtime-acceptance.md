# Cardputer Runtime Host：A1 验收状态记录

日期：2026-09-12（Asia/Shanghai）
范围：Umbrella [#1104](https://github.com/endaye/lmdj/issues/1104) 的 A1
（[#1111](https://github.com/endaye/lmdj/issues/1111)）。本记录只整理已发生的
操作者观察与待测门禁，不把 source-candidate 结果改记为固定 Product Build 的通过。

## 身份边界

B1 已合入的测试身份为 Product Build `1.0.56.0`，其 Assembly witness 绑定
合并提交 `7575cdf7976eba23b0558143954258fb7df472c8`。本记录中的 2026-09-12
装载／播放观察是在后续 keypad-polarity source candidate 上完成；没有同一 Build
的不可变 ELF、完整工具链收据和输出路线绑定，因此不能作为该 B1 Build 的正式 A1
PASS。早期固定身份和失败证据均保留，不用新镜像回填旧记录。

## 已保留的 source-candidate 观察

以下摘要来自操作者的原始记录（对应 Issue #1111 评论），不包含稳定设备标识或
原始 Flash 备份：

- 内容 A：`96808` bytes，SHA-256
  `2b3ae5e4f1a1753acfd9e3039439e7ae07c6e2fd885fd8375233184821009d63`；装载、
  Space 播放、A/S/D/F 按下／释放／重按、M 静音切换和停止／重启均有正常听感，
  未报告停止时明显爆音。
- 停止后 Enter 得到 `EMPTY / armed=1 / content=0 / error=0`；内容 B：`96808`
  bytes，SHA-256
  `7ce684007a4d47e71a590a644f88ce0c81834c3343267e9682026e3a876424e9`，装载后
  回报 `READY / error=0 / pads=4 / content=96808`，听感与 A 可辨识不同，Pad A
  可重复触发。
- 修改保留 header 字节的恶意输入并重算传输 identity，在 COMMIT 被拒绝；远端
  回到 `EMPTY / content=0 / error=5 / armed=0`，没有发布半成品。随后正确的 B
  重试成功并进入 `RUNNING / error=0`。
- 只发送 B 的首个 128 bytes 后静置 6.2 秒（实现的 5 秒无进展边界）；远端回报
  `EMPTY / error=0 / armed=1 / content=0`，随后完整 B 重试成功。这证明本次候选
  的超时丢弃／正确重试行为，不证明真实 USB 断连恢复。
- 开关 ON 时拔出 USB 约 10 秒，操作者报告背景继续且 A Pad 仍可触发；重新插入
  后 macOS 未枚举 USB Serial，因此没有远端 reconnect STATUS，也没有把
  “无隐式重启／替换”填成通过。该观察是听感证据，非串口 far-side 证据。
- 物理复位后远端回到 `EMPTY / content=0 / error=0`，Enter 后重新装载 B 并播放；
  这支持无掉电续播的复位语义，但仍不是固定 B1 Build 的完整旅程。

## A1 门禁矩阵

| 验收腿 | 当前状态 | 说明 |
| --- | --- | --- |
| A 装载 → Pattern/Pad 播放与显示 | source-candidate partial | A、按键和 Ready/Running 状态已观察；未绑定固定 B1 Build、未完成显示方向和时延测量。 |
| 停止、静音／drain、卸载、不同 identity 的 B | source-candidate partial | A→B 与停止后 empty 已观察；每个转移的仪器/回执链和固定 Build 证据仍缺。 |
| 坏输入拒绝、无半成品、正确重试 | candidate observed | COMMIT 拒绝后的 empty 与 B retry 有 far-side 状态；不是产品候选准入。 |
| 接收中断、断连／重连、复位恢复 | partial / pending | ON 状态电池播放为正向听感；USB 重连未枚举，断连期间 far-side 状态和无隐式替换未证实。 |
| D1 代表性负载、时长、p99.9、underrun、端到端延迟 | pending | 没有把短时音乐或软件计时当作仪器 PASS。 |
| heap、最大连续块、控制／音频栈 | pending | 资源 API 与 source ledger 已存在，但没有本 Build 的完整运行采样。 |
| H1 启动 click 与模拟静音 | pending | 既有 startup-click 失败记录仍有效；本记录没有重新定位或豁免该门禁。 |
| 固定 Build／ELF／素材／工具链／输出路线 | pending | 需要同一不可变候选和快照后重新执行完整旅程。 |

## 结论与复测入口

A1/#1111 保持 OPEN，Umbrella/#1104 不结案。下一次验收必须先建立精确的
Build、ELF、素材、工具链和输出身份，再由单一操作者按 D1 的完整顺序执行；每
一腿记录转移后的远端状态、原始日志或录音 hash、测量条件和未执行项。失败保留
原行，修复后分配新 Build，不能改写本记录的 source-candidate 结果。

## Version Management

Version impact: none。本文不分配 Build、不修改 Module/Contract/Assembly 身份，
也不创建 tag、Release 或部署记录。

## Documentation Impact

Documentation impact: required — `/hosts/cardputer-host/`、`/platform/native-audio/`
和 `/platform/input/` 链接本状态记录，并保持未完成门禁可见。

## Pitfall Impact

Pitfall impact: none。source-candidate 听感、串口远端状态和正式固定 Build 验收
在本文分开记录，避免把局部正向观察扩张成产品 PASS。
