# Perform Launch 短暂排队状态的采样

- 日期：2026-10-11
- 当前阶段：源码与原同名完整 focused GREEN 已完成；新 committed Creator 和当前 head 评审尚未执行。
- 实际起点：`96871218d7d5ceadf168b9fef5decebf32c091f8`，保留原 replay-neutral Task 提交。
- 刷新 integration base：`deb95de722b845d708371e90bcac138ae5e25e01`。
- 分支：已有隔离 `fix/perform-replay-monitor-oracle`，同 PR #2010 的独立第二 Task。

## 当前前提与声明文件

fresh fetch 后，main 与本工作树的原完整 Launch 用例逐字节相等，两处 pending
仍用默认 locator 采样。#2008 当前 `3043df09597356251324813be9e1f1fd8e517c5b`
仍 OPEN，只涉及 Performance adapter、时钟和对应录制测试；不能据此认定普通
Pattern switch 或本用例已修复。K1 仍拥有同一 spec 的键盘映射工作，owner 已
协调顺序；本 Task 不修改映射 hunk。

已完成的 committed 968 完整 Creator 实际为 114 passed、2 failed、11 skipped，
exit 1，没有通过键。原 Launch 定义 1014 在 pending 断言 1124 失败；后续
withdraw、再次排队、Stop、Truth 和 no-record 断言未达。旧完整 FAIL、trace 和
error-context 保留，不能被 replay-neutral 或 owner-loss 的通过替代。

真实 trace 的 pending 预期为原 5000 ms。292973.165 读取 idle，293478.046
读取 acknowledged；间隔 504.881 ms。中间 293103.992 的原 JPEG 明确显示
QUEUED SLOT 02 和第二槽 Queued，293320.349 已 Playing。原 late locator
采样错过真实短暂状态；native 回执迟延和旧 EEF boot 失败原因仍 UNKNOWN。

原 trace SHA：`5246fc1d2ef6bd001f7ae90356e884227e9810b8e0b56fffde068b448ff8e654`。
queued 原 JPEG SHA：`1695d4150a7594b45e0412642075f7de87b4f63b1f69d619769217dcfd31317c`。

本 Task 只声明两个文件，不改两页 Portal 或原 MASTER 计划：

1. `tests/platform/web/creator/creator_web_perform.spec.mjs`
2. 本计划文件。

## 最小修改与完整旅程

只将两个 pending 断言改为 `expect.poll`：同一 existing accessible locator 的
`evaluateAll` 读取当前匹配数组，恰好一个元素才返回其实际 `data-launch`，
缺失或多匹配返回 null；预期仍为字面量 pending。期限保持 5000 ms，间隔
50 ms；不使用元素出现的内部等待，不增加 helper、probe、Facade 请求或 observer。
真实 read／IPC 延迟仍存在，不宣称 50 ms 调度保证。

| 原旅程腿 | 保留的远端断言 |
| --- | --- |
| 导入、激活、建第二 Pattern、两槽分配 | 原 helper、Pattern 身份及 revision readback |
| 空槽、停止时两次选槽 | 空槽无流量；实际 snapshot.reload 收据和对应 counter |
| Play、earlyBar | 第一槽 acknowledged；原真实 session／inspect，30000 ms 和原 barFrames / 5 窗口 |
| 首次排队 | pending 在原 5000 ms 内；QUEUED SLOT 02、当前第一 Pattern、第一槽 acknowledged、counter 01 |
| 撤回 | 点击正在播的槽；pending_switch null、第二槽 idle、当前第一 Pattern |
| 再次排队并应用 | 第二次 pending；原 30000 ms 内 playing、非录制、pending 清空、当前第二 Pattern；双方槽状态、cue、counter 02 |
| Stop 和完整收尾 | playing false、第二槽 idle；三次 switch 收据 [second, first, second] 且 ok；无 live reload／record 流量；Truth 相等、Performance idle |

用例标题、Chromium 边界、原 traffic observer、整条 180000 ms、earlyBar 已有
50 ms 采样、5000／30000 ms 预算和所有上述腿均保留；不更改产品、音频或点击。

## 验证与交付

最低层 RED 是上述同名完整用例在真实 committed 968 的原失败及阳性原帧。
修改后先运行同名完整 Launch 单例，保留全部原断言；使用独立新 `--output`
目录，不能清空原完整套件 trace／error-context。绑定当前 own 产品 dist 的
真实十文件 inventory、未变化的产品输入和原 fixture SHA／size；固定测试
数据复用必须明确，不声称重新构建 runtime 或生成数据。

本 Task 的真实完整 focused 结果为 1 passed（18.6 s），audio wrapper
child.wait 与其真实命令退出码均为 0；两次 pending 及所有原收尾断言执行完成。
源码、索引、own dist 和 installed dependency 前后守卫相等，旧 full trace／
error-context 保留；原 retain-on-failure 策略未生成 Green trace，不虚构录像。
此结果只证明同名完整单例；旧 968 full FAIL、新 head full UNRUN 及 native
回执迟延 UNKNOWN 均保留，不能从本次结果推导新的完整 lane 通过键。

完整 focused GREEN 后，暂存两声明文件，运行既有 ownership 77 和 pitfall 15
检查及 diff 检查，创建独立 Conventional Commit，不 amend 原 968。
随后在实际新 committed head 运行完整已选 Creator lane，原八组及所有预算
保留，记录实际结果与官方 input key；focused 不能产生 full lane 通过键。
按真实 scope 与 Portal provenance 结算其余既有检查，不添加新 gate。

新 head 必须取得新的独立／正式 current-head review，处理实际 findings、
conversation、protection 和 batch evidence。旧 968 的 publisher 重试即使
通过，也不能证明新 head。owner 负责最终采用与合并；作者不自评、waive 或
接受风险。不删除原日志、缓存、源码、Git 或其它工作树。

## Version Management

Version impact: none — 仅修正两个内部 Browser 观察回调和独立计划；不改产品
实现、公开 API／ABI、Contract、Host 行为、Assembly／lock 或身份，不分配版本。

## Documentation Impact

Documentation impact: none — 只修内部观察采样，保留现有产品状态、严格预期、
全部预算与旅程；不改变 Portal 已记载的行为、边界、版本、Proof／CI 政策或
操作流程。两页当前 Queued／Playing 事实仍准确，无需重复编辑。
PR #2010 总体仍保留原 Task 的 `Documentation impact: required` 和
`/hosts/creator-interactions/`、`/hosts/creator-web/`；本 Task 的 none 不替代
其原文档交付、检查或来源义务。
