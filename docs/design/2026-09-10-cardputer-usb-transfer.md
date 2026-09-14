# Cardputer USB 内容传输：D1 工程规范

日期：2026-09-10。产品权威：[首版 Decision](../prd/decisions/2026-09-10-cardputer-runtime-host-first-slice.md)。
范围：[Runtime Host 设计](2026-09-10-cardputer-runtime-host.md)的 USB 工程接口；
这不是已发布 Contract，也不改变进程内 Runtime Facade。
C1 将本规范落实为 `lmdj.cardputer-transfer.v1` / `1.0.0`、schema、独立读写器与
正反例；D1 不创建 active schema/manifest，不向门户投影未注册身份。

## 1. Frame

所有整数 unsigned little-endian。请求只有一项在途，响应序号与请求相同；禁止
pipeline、压缩、路径、URL、代码执行或跨帧隐式对象。每帧由下表与末尾校验构成：

| Offset | Bytes | 字段 |
| --- | --- | --- |
| 0 | 4 | ASCII `LMCP` |
| 4 | 1 | wire major，恰好 1 |
| 5 | 1 | opcode：HELLO=1、STATUS=2、BEGIN=3、DATA=4、COMMIT=5、ABORT=6 |
| 6 | 2 | payload byte length，0..1024 |
| 8 | 4 | request ID，1..4294967295 |
| 12 | 16 | session nonce；HELLO 请求全零，其余为设备握手返回值 |
| 28 | N | payload，恰好 N bytes |
| 28+N | 4 | CRC-32/ISO-HDLC，覆盖 offset 0 到 27+N，输出 little-endian |

CRC 采用 reflected polynomial `0xedb88320`、init/xorout `0xffffffff`，与
`binascii.crc32` 的完整缓冲结果相同；它只用于分帧错误检测。整帧最大 1056 bytes。
响应 opcode 为请求 opcode OR `0x80`；响应 payload 前 2 bytes 始终为 result code，
后面仅为该操作成功时规定的数据。任何失败响应只有这 2 bytes。
除 HELLO 成功响应外，响应 header 原样回显请求 ID 与 nonce，包括 stale-session。
未知 opcode、错误长度/version、CRC mismatch 不得传到 Core 或按伪造长度分配。
串口 boot log 不属于协议；接收器在有界缓冲中找 magic，验证完整长度与 CRC 后才
处理帧，损坏时逐字节有界重同步。Frame assembly 5 秒无新增字节丢弃；它与有效
DATA 推进的事务时钟分开，噪声/重复包不能维持一份内容的接收区。

除 HELLO 外，只有当前 session 的 exact-next request ID 可执行。通过该校验的请求，
成功或有结构响应的业务失败都消耗 request ID；仅相同 ID 且完整请求 bytes 相同的最近一次重试，
可返回缓存的同一响应，不重复副作用。较旧或跳号返回 bad-request-id；same ID
不同 bytes 返回 conflicting-retry，二者不改变内容/offset，也不消费当前 exact-next ID。
缓存最多一项完整请求
与响应（各 ≤1056 bytes），纳入平台预算。ID 耗尽要求新 HELLO，禁止 wrap。
CRC/长度/未知版本无法确立合法请求，不消耗 ID；错 nonce 同样不消费当前会话 ID。

## 2. Session 与设备确认

HELLO 请求 payload 恰好为空，request ID 恰好为 1。设备生成新的非零 128-bit
session nonce，成功响应的 frame header 携带它，payload 为 result=0、最大 payload
u16=1024。nonce 来自 SDK 随机源；C1 必须验证选用 SDK 的启动熵配置与跨重启采样，
不得使用固定 seed、时间戳或 RuntimeEpoch 地址。nonce 是概率隔离标记，不是密钥。

每个完整有效 HELLO 建立新会话，后续 request ID 从 2 开始；HELLO 自身不参与旧
响应缓存。HELLO 重传可能产生另一个 nonce，电脑只采用最后收到的有效响应。
设备只有一项会话；新 HELLO 取消旧接收事务、清除接收授权，但不卸载已成功装载
的 ready/running/stopped 内容，不改变播放状态。新 HELLO 后由用户在设备重新确认
接收：Host 完成 stop/drain/unload，再设置一次性接收授权。USB 没有远程 start/Pad。
设备复位清除会话、授权与内容；新会话拒绝全部旧 nonce。

接收授权也采用 5 秒无有效进展到期，屏幕明确显示确认/超时状态；电脑应先打印
“请在设备确认”并轮询 STATUS，看到 armed 才 BEGIN。没有授权不得卸载内容。
HELLO 不等于用户确认；电脑开串口时不得操作 DTR/RTS 进入下载模式。

## 3. 操作 payload

本表仅列请求和成功响应 result code **之后**的 bytes。每种长度均恰好匹配，禁止
额外字段或 trailing bytes；transfer ID 是电脑生成的非零 16-byte 事务标记。

| 操作 | 请求 | 成功响应 |
| --- | --- | --- |
| STATUS | 空 | 下节固定状态记录 |
| BEGIN | transfer ID[16] + encoded length u64 + raw SHA-256[32] | transfer ID[16] + next offset u64=0 |
| DATA | transfer ID[16] + offset u64 + chunk[1..1000] | transfer ID[16] + next offset u64 |
| COMMIT | transfer ID[16] | content byte length u64 + raw SHA-256[32] |
| ABORT | transfer ID[16] | 空 |

BEGIN 只在已 armed 且 Core empty 时接受，成功后消耗接收授权并进入 receiving。
超限/分配失败清除授权并保持 empty；不接受零总长度。cap 来自 B1/R1 profile，
不是 u64 最大值。若已有当前事务，新的 BEGIN 返回 wrong-state，不替换它。
DATA 的 offset 必须等于 next offset，chunk 不得越过完整长度；回包前 bytes 已写入
唯一接收区且 next offset 已推进。上节 exact retry 不重写数据。当前事务的错 offset、
内容越界或错 transfer ID 属于 invalid-transfer：清空接收区并回 empty。
错 session 则只拒绝，不可影响另一会话正在接收的内容。

COMMIT 只有 next offset 等于 encoded length 才启动校验与 Core `load`。
校验完整 encoded SHA-256/byte length 后，control executor 同步调用 Facade；期间
接收器只保留有界 frame，不开始第二事务。成功后 ready，释放传输输入；回包携带
实际 Facade 发布的完整身份。所有 load 失败清空内容/接收区，显示 Core 错误并回 empty。
同 session 丢 ACK 用 exact retry；重新连接则 HELLO → STATUS，先核对完整已装载
身份，不能盲目重做 BEGIN。未收完的 COMMIT 返回 invalid-transfer 并清空。

ABORT 对当前 receiving transfer ID 取消到 empty；对非当前 ID 返回 invalid-transfer
且不触碰已发布内容。完成/取消后的 exact retry 由请求缓存幂等处理；新 session 的
ABORT 无权清空 ready 内容。接收超时、键盘 Esc 或本地复位都释放未完成输入；
取消结果与之后 STATUS 一致。接收完成后不把“会话过期”变成自动停音条件。

## 4. STATUS 与错误

STATUS 不修改状态。记录格式依次为：

1. Host phase u8：empty=0、receiving=1、ready=2、running=3、draining=4、stopped=5；
   armed u8=0/1、muted u8=0/1、volume u8=0..10；Pad count u8=0..4，随后固定
   4 对 bank u8/pad u8，按 A/S/D/F 顺序；未使用的对均为 `255/255`。
2. last error u16（下列 result code），reserved u16=0。
3. 最大 encoded bytes u64、最大 PCM bytes u64、最大 sample frames u32、最大 Pads
   u32、最大 events u32；这些是 profile 的准入限制，不是本次内容占用。
4. 已发布内容 byte length u64 + SHA-256[32]；不存在则 length 与 digest 都为零。
5. 当前 transfer ID[16] + received bytes u64 + expected bytes u64；无当前接收则全零。
6. Build identity JSON 的 UTF-8 byte length u16 + 相应 bytes（≤512），字段固定为
   `product_build`、`host_version`、`revision`、`assembly_lock_sha256`、`profile_sha256`。
   正式 B1 均为生成的精确身份；前期未装配研究构建前两项及 Assembly hash 为 null，
   不假借已有 Product Build。其余字段为完整 SHA-256 或 Git 40 位 SHA；JSON 无重复
   key、无额外字段，不包含 HTML 或用户素材名。

成功=0、wrong-state=1、not-armed=2、stale-session=3、bad-request-id=4、
conflicting-retry=5、invalid-transfer=6、budget-exceeded=7、allocation-failed=8、
invalid-content=9、preparation-failed=10、timeout=11、cancelled=12、internal-error=13、
unsupported-content=14（通用内容合法但不符合本设备 One Shot/Pad profile，卸载到 empty）。
未知版本/非法 opcode/CRC 错误丢帧，由电脑超时和 STATUS 定位，不生成猜测会话的响应。
status phase 与 last error 分离：接收失败显示错误，但 Core phase 确实 empty。
电脑保留数字码、简洁解释和具体恢复动作，不能只有通用“失败”。

## 5. H1/I1/C1 的内部边界

- H1 的 `runtime_host.hpp` 定义唯一控制端：`handle_key(KeyEvent)`、
  `begin_receive()`、`cancel_receive()`、`load_received(span, identity)` 与
  `read_status()`。它们只从串行 executor 调用，load 借用范围在返回前保持不可变。
  H1 负责 Facade epoch/sequence/receipt、播放 stop/drain、音量及状态投影。
  它消费新增控制侧 `RuntimeFacade::content_summary()` 的固定容量摘要，最多
  64 个 `(bank, pad, trigger_mode)`，empty 时 count=0；只读不分配、不修改 Truth。
  摘要归 Core，Host 只按 Assembly profile 检查/映射，不自行解析内容。
- I1 只产生按下/释放/overflow 的 `KeyEvent`，通过固定容量队列送给 executor；
  显示读取其有界状态副本，不在 I2C/显示线程调用 Facade，不拥有 RuntimeEpoch。
- C1 负责上述 wire 状态、字节/完整身份及 bounded receive buffer；完成接收后只向
  executor 交接不可变输入，不在 USB worker 调用 Facade。USB worker 的两个 frame
  缓冲与单次 receive allocation、超时/取消回收责任不转移给音频 callback。
- 音频 driver 只接收 executor 的启停/音量意图和专用 render 入口；真正的 callback
  quiescence、DMA 静音完成由 driver 回报。stop ACK 不提前于物理输出端的静音边界。
- 最终 shared 文件 owner：H1 初建 main/RuntimeHost/构建；I1 先落键盘与显示接线，
  C1 后落 transfer 接线；B1 最后注入 profile/生成身份。各项按合并顺序更新同一
  注册文件，不以分支并行写入冒充独立文件所有权。

## 6. C1 最低 conformance inventory

Python 与 C++ 对同一 hex fixtures 独立验证：HELLO、STATUS、BEGIN/DATA/COMMIT 成功；
wrong CRC/version/length、超限、零/错 nonce、request ID 重复一致/冲突/跳号/耗尽、
分片边界与零 chunk、错 offset/transfer、半包超时、无进展重试超时、ABORT、
丢 COMMIT ACK 后 exact retry、重连 STATUS 恢复、旧 session 不改变新事务。
每个 negative case 断言精确错误/不响应及后续 phase/identity/offset，而非只断言非零退出。
在真实 USB 上另验拔线供电、串口关闭/重开、boot log/重同步与日志阻塞隔离；PTY
只能证明 framing 与进程边界，不替代这些 USB/电池副作用。
