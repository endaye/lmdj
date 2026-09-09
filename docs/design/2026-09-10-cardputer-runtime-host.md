# Cardputer ADV 最小 Runtime Host

日期：2026-09-10。状态：产品范围已批准；工程设计接受当前提交评审，尚未实现。
GitHub Issue: [D1 #1105](https://github.com/endaye/lmdj/issues/1105)，隶属
[Umbrella #1104](https://github.com/endaye/lmdj/issues/1104)。
配套[实施计划](../plans/2026-09-10-cardputer-runtime-host.md)。

## 1. 已批准事实与首版范围

[首切片 Decision](../prd/decisions/2026-09-08-runtime-content-first-slice.md)
已经固定：电脑保留 Project Truth；派生内容包含单 Pattern 与实时 Pad 所需材料；
PCM16；不做 Pattern 切换；换内容走 stop → unload → load；失败 empty；不做掉电续播。
本设计不改变这些规则，也不重新设计已实现的
[Runtime Facade 生命周期](../plans/2026-09-09-runtime-facade-lifecycle.md)。

以下是[已确认的整体首版范围](../prd/decisions/2026-09-10-cardputer-runtime-host-first-slice.md)，
不是已实现能力或硬件容量承诺：

| 选择 | 首版方案 | 首版明确不包含 |
| --- | --- | --- |
| 电脑到设备 | USB 有线传输完整派生内容；电脑命令行导出与发送 | Wi-Fi、蓝牙、SD 卡导入、Creator 新 UI |
| 信任边界 | 用户选择物理连接的设备，并在设备上确认进入接收模式；无密码学发送者认证 | 网络远程控制、把 SHA-256 当鉴权 |
| 离线演奏 | 成功装载后可拔线，在供电持续的情况下继续 Pattern 与本地 Pad 演奏 | 从 USB 丢失推断应停音、电脑连续流式供音 |
| 接收中断 | 单次事务中断或超时即丢弃，保持 empty；重连查询后从头重传 | 断点续传、偷偷回滚旧内容、重放旧会话命令 |
| 设备交互 | 4 个 One Shot Pad；播放/停止、音量与静音、装载确认、状态显示 | 设备编辑 Project、录音、采样、菜单式文件管理 |
| 音乐目标 | 4 个不同鼓音，样本合计 1 秒，至少 4 个同时发声，单个两小节 Pattern | 用单音或 50 ms 短夹具替代正常演奏 |

用户于 2026-09-10 批准本组合，确认记录进入上述 Decision。D1 Issue 承载当前讨论，
本文件不维护 live issue status。后续改变产品范围必须有新的明确决定。

## 2. 为什么容量验证仍是硬前置

源码基线为 `5b1db20980280b7e9ce0088939c2baea88426ef8`。
当前接口见 [Runtime Facade](../../packages/application-facade/include/lmdj/facade/runtime_facade.hpp)
与 [Content limits](../../packages/project-cooker/include/lmdj/cooker/runtime_content_types.hpp)：
admission 是准备峰值模型加平台 reserve，不是 allocator 强制配额。
`load` 同步借用完整不可变 bytes；返回成功后 Core 才拥有全部播放数据。
不能只计算 PCM 文件大小或静态 BSS，也不能在 Host 私改 Core 来缩小报表。

[已有听测报告](../research/2026-09-09-cardputer-audio-hearing.md)记录的是另一精确
源码 `32d8ff6f48d7215aaa7fdf9b56ea8b9c5c49c268`：单 Pad、无 Pattern events、
50 ms 内容 admission 326465 bytes，cap 331176 bytes，reserve 32768 bytes；
短时最差 block 余量约 0.91%。相同模型的 750 ms 内容估算为 729665 bytes。
这些是历史指定镜像的结果，不能平移为当前 main 的实测，也不支持 4 Pad 承诺。

R1 必须先按下节目标固定 fixture，再测当前 exact revision 的完整预算与运行。
预计可能暴露准备期多份样本或固定 Runtime 成本问题；这只是待验证的原因假设。
若真实目标不满足，保留负结果、建立有最小回归的修复 Task，再以同口径复测。
R1 作为研究结案也不能自动解除 H1 的正向容量前置条件。

## 3. 固定验收口径

以下数值是先于测量固定的**验收目标**，不是已经测得的上限；不得为通过而
缩短素材、降低并发、削减 reserve、扩大 deadline 或省略旅程。

### 3.1 音乐 fixture 与内容容量

- 48 kHz、mono PCM16：kick 250 ms、snare 250 ms、closed hat 100 ms、clap 400 ms。
  4 个不同声音，总计 48000 frames / 96000 PCM bytes；每个声音有实际衰减尾音。
  使用有明确许可的仓库素材或可复现的原创鼓音，不用纯正弦替代音乐素材。
- 一个 4/4、120 BPM、两小节循环 Pattern，固定 32 个事件与明确步位；R1 同时
  固定事件表、生成方法、素材/导出物完整 digest 与 byte length，再开始测量。
- 演奏脚本必须包含 Pattern 叠加本地 Pad、至少 4 个声音实际重叠的区间及释放/
  重触发；记录实际峰值 voice 数。4 声部是最低可用目标，不是删除桌面 128 voices
  不变量的授权，也不代表必须把平台容量配置成 4。
- 内容 B 使用不同鼓音或明显不同节奏与不同完整身份，覆盖换内容后确实改变声音。
  不以重新装载 A 代替 A → B。
- 对超出已验证设备 profile 的内容明确拒绝；不得静默截样、丢事件或换音色。
  最终 encoded/frames/pads/events cap 由 R1 正向证据绑定；不得从 wire 宽度推断。

### 3.2 性能与稳定性

- 基线输出 48 kHz、256-frame block，周期 5333.333 µs。CPU 服务测量分别覆盖
  Core render、格式转换、提交开销与调度唤醒延迟；阻塞等待 DMA 空位单列，不能
  与 CPU 工作混成一个“render 时间”，也不能从真实 deadline 统计里删掉等待。
- 最差 CPU 服务时间目标 ≤ 4266.666 µs（保留周期的 20%）；记录原始样本数量、
  最大值与 nearest-rank p99.9。另按目标 DMA 交付时刻统计实际 late/underrun，
  连续 30 分钟音乐 + Pad + 屏幕 + USB 状态流量下均为零。
- 30 分钟至少约 337500 blocks，覆盖热启动/稳态；报告采样遗漏、计时器精度和
  观测开销。若无法可靠观测 underrun，结果为 unverifiable，不以“没听到”记零。
- 物理按键闭合 → 模拟音频首个有效样本目标 p99 ≤ 20 ms，至少 1000 次触发。
  逻辑分析仪/同步采集同时观察触点或键盘控制器的已标定事件与输出；单纯注入
  软件事件只能证明后半段。缺测量设备就保留物理时延 gap，不冒充全链路 PASS。
- 至少 100 次完整装载/播放/停止/卸载循环；持续记录最小 free heap、最大连续块、
  分配峰值、任务 stack high-water、DMA/显示/USB 成本，端点 heap integrity 通过。
  重复相同稳态的资源不得持续净减少；报告实际差值，不能只凭最后一次成功宣称无泄漏。
- 平台 reserve 下限沿用已有 32768 bytes，新增 Host/显示/USB/键盘成本必须另计
  并实测；它不是给任意新 Host 的总预算。最坏情况下也不得靠该 reserve 容纳内容。

## 4. Host 边界与音频生命周期

新增独立 `apps/cardputer-host/`，不把桌面 Native Host 改名或复用为设备身份。
Host 只使用窄 Application Facade，负责硬件 I/O、有限缓冲与 UI；Product wiring
归 `products/lmdj/`。设备不读 Project Bundle、不加载 Provider、不保存 Project Truth。
R1 探针仍是研究工具，不被正式产品 include/link。

一条串行 control executor 拥有 Facade 控制调用与命令序列；键盘、USB 和 UI 事件
通过有界消息进入它。只有一个音频任务调用 `render`；ISR 只通知，不做 Core 调用、
日志、分配、I2C 或屏幕操作。`RuntimeEpoch` 是进程内对象，绝不序列化或伪造。
键盘命令由 control executor 分配当前 epoch/sequence；queue full 不消耗 sequence，
已接收命令通过 `poll` 的实际 receipt 判定，不把 accepted 当作已发声。

Driver 建立 MCLK/BCLK/LRCK 与静音预热，准备好后才放出有效 PCM；停止时先停止
新内容与触发，完成 Facade drain，再向物理 DMA 送足静音并确认输出端静音，最后
按驱动顺序停钟/停 DMA。Facade stopped 不单独证明 DMA 已空。销毁 Facade 之前
Host 必须保证再无 `render` 调用。启动/停止/复位及设备错误都不自动播放。

音量属于 Host 输出设置，不改 Project 和样本内容；0–10 档、默认 2、最大数字
增益不超过 unity，静音独立、增益变化有短 ramp。启动不恢复旧音量或播放状态。
ES8311 模拟增益/输出限幅由 H1 记录并固定；历史 tone 没有破音不等于真实音乐
声学验收。首版验收内置扬声器，不默认覆盖耳机、外接功放或声压安全认证。

## 5. USB 事务与失败行为

使用 USB Serial/JTAG 的有界二进制 framing；它是串口传输，不是 USB 音频或 U 盘。
Espressif 明确说明该硬件为固定串口/JTAG 功能，且无电脑读取时日志缓冲可能造成
等待，因此协议与诊断不得阻塞音频或 control executor。
[ESP-IDF v6.0.2 文档](https://docs.espressif.com/projects/esp-idf/en/v6.0.2/esp32s3/api-guides/usb-serial-jtag-console.html)
只作为机制依据，不替代 H1/C1 对 EIM 管理的实际 SDK revision 的构建与设备验证。

事务操作为 HELLO / STATUS / BEGIN / DATA / COMMIT / ABORT；wire version、
boot/session nonce、transfer ID、offset/length 与完整内容身份相互独立。
nonce 用于隔离过期事务，不宣称身份认证。配套
[USB 传输工程规范](2026-09-10-cardputer-usb-transfer.md)固定字节序、封包上限、
校验范围、未知版本/操作拒绝、重复包规则与正反例责任；C1 将它落实为跨语言 Contract。
不得直接暴露 Facade epoch、C++ struct 布局或指针。

1. 开机 empty、静音，屏幕提示连接电脑；电脑显式选择设备端口并查询 Host/Build/
   revision、capability/profile 和当前完整内容身份，不自动刷机或切换下载模式。
2. 用户在设备确认接收模式；若已有内容，屏幕先提示本操作将停止并丢弃它。
   确认后 stop → physical silence/drain → unload → empty，再允许 BEGIN。
3. BEGIN 校验总长度及目标 profile 后分配有界接收区；DATA 必须按确认 offset
   顺序接收，精确重复已确认 chunk 可重发确认；本事务内容冲突/越界立即拒绝并清空。
   错会话包不能改变新的有效事务，只返回 stale-session；不能借过期包清空新内容。
4. 默认 5 秒无有效进展取消事务；USB 断开未被立即检测到时也由该超时回收。
   重复包不延长“有效进展”。该超时是用户可见传输策略，不是放宽音频 deadline。
5. COMMIT 只有在收到全部 bytes、核对 SHA-256 + byte length 且 Core load 成功后
   回 ready；不自动 start。坏格式/资源不足/准备失败均 empty，显示原因与重试动作。
6. COMMIT 回包丢失时，电脑先 STATUS 核对完整身份和 phase，不能盲目重做装载。
   新连接建立新会话，不重播缓存命令；重连本身不卸载已成功装入的内容。
7. 接收中拔线最终 empty；成功装载后拔线保留 ready/running/stopped，持续本地演奏。
   真实断电/复位才回 empty。保留电池供电的拔线与断电复位必须分别验收。

授权只依赖用户的物理操作与本机信任，恶意物理连接电脑仍在威胁范围之外；解析器
仍须把任何输入当不可信字节验证。接收模式外拒绝内容替换，USB 不提供远程 Pad/
播放控制，避免再增加一套网络化 epoch/receipt 产品语义。

## 6. 最小键盘与显示

A/S/D/F 映射 4 个 Pad，Space 播放/停止，M 静音，减号/等号调音量，Enter
确认接收，Esc 取消接收。Pad 只在 running 接受，按下沿触发一次，自动重复不连发；
释放仍传给 Facade。ready/stopped 按 Pad 显示“先播放”，不隐式 start。
映射依 Core 返回的 canonical Pad Slot 顺序，不把物理第一个键误当 Asset 或固定
Bank 0。H1 补充控制侧 `content_summary()`，返回有界 Pad Slot/trigger-mode 摘要；
Host 不自己解码 Runtime Content。profile 只接纳 1–4 个 One Shot Pad，R1/A1 的
达标内容必须用满 4 个；其余格式即使通用 Core 合法也报本设备不支持并卸载到 empty。
Host 的 ready 只能在 profile 检查完成后公布，中间 Core ready 不暴露为装载成功。
本轮只承诺 One Shot 操作；键盘 FIFO overflow 或丢失释放事件必须停止/清除本地
按键状态并给出错误，不能靠猜测补按键。

屏幕显示 empty/receiving/ready/running/stopped/error、Pattern 播放状态、4 Pad 活动、
音量/静音、USB 会话状态与简短错误；身份页显示 Product Build/Host/revision 与
内容短 digest/长度，完整身份由电脑 STATUS 输出。身份来自生成 manifest，不手填。
显示活动以处理回执或 Runtime 状态为准；错误信息要给下一步，不只显示数值码。

M5 官方说明确认 ADV 使用 ES8311、56 键键盘和显示屏；
[硬件说明](https://docs.m5stack.com/en/core/Cardputer-Adv)不证明按键映射、组合键
或驱动时序已经验收。H1/I1 必须固定该型号实际原理图与供应商源版本，不能套用
原版 Cardputer 的音频/键盘驱动。

## 7. 完整交付旅程与批准边界

电脑从真实 Project 经 Facade 导出 A → USB 接收并核对完整身份 → 本机播放 Pattern
与 Pad → stop 后实测静音/DMA drain → unload → 接收 B 并核对新身份与新声音 →
坏输入失败 empty → 重试成功 → 接收中拔线/超时 empty → 重连重传成功 → 演奏中
拔线继续 → 重连无隐式播放或替换 → 复位 empty → 再装载成功。
每腿必须保留转移后的可观察证据，电脑 Project Truth 的完整身份在前后保持不变。

B1 必须在正式 A1 验收前提供精确 Product Build、Assembly、firmware hash、source
revision 和同 Build 不可变门户快照；R1/H1 研究镜像不能代替它。A1 需要真实物理
操作、人耳音乐质量和量化仪器证据。缺任一腿或性能测量，Umbrella 仍未完成。
本设计不启动 Release、tag、部署、Channel 晋级或删除旧备份。
