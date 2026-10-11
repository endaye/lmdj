# Perform replay-neutral FX 与设备监听音量验收

- 日期：2026-10-11
- 初始候选状态：实现与 focused GREEN 已完成；完整 Creator、当前 head 评审
  和合并按下述顺序推进，实际候选证据记录在 PR 与外置验收收据中。
- 实际起点：`46045119801d9f03707aaa6f8ed50fbd651e8e95`，包含 #2006。
- 分支：`fix/perform-replay-monitor-oracle`；使用独立工作树。

## 当前前提与范围

#2000 已通过 `116280f9209245b4757a814fcf3155002b025269` 交付 MASTER
consumer：范围 0–100%，与 ENC4 共用本设备监听值。它不进入 FX 手势、HOLD、
Performance 事件、Project Truth 或 Undo，不改变录音、重采样、导出 PCM。
本 Task 复用这一行为，不修改 App、Core、监听 producer 或 wiring。

原完整 replay-stop 用例仍对所有 slider 断言 FX 中点 500；新增的第四个
MASTER slider 默认是 100。旧 aa1 候选的真实 RED 仅作为历史；本 Task 先在
上述 clean main 的独立工作树全新 configure、build、package，再运行未改的
同名原用例。实际定义行 1699、失败行 1723，第四个控件明确是 MASTER，
expected 500 / received 100。原 trace 证明 replay playing → stopped · neutral
及三个 FX=500 成功；HOLD／Pattern 尾部断言因第四个 slider 失败而未达。

当前两页 Portal 仍有 MASTER 缺席陈述。#2006 已修正 interactions 附录 A4
中的 MASTER consumer 状态，本 Task 保留该段及其完整验收边界；只修正
第 6 章触摸入口、第 10 章缺席句和 creator-web 的同一事实矛盾。

K1 仍拥有相同 Perform spec 和两页 Portal 的键盘映射工作，owner 已协调
顺序集成；不同 hunk 不等于没有归属重叠。保留 #2006 的导航已批准／未接线、
BPM、Bank 和 live Mute/Solo 状态，不实施其它 K2／M1 行为。

初始外置提案曾声明三个文件；首次实现编辑前，owner 明确增加 creator-web
同一 MASTER 事实修正，最终只有下列四个文件：

1. `tests/platform/web/creator/creator_web_perform.spec.mjs`
2. `apps/docs-site/docs/hosts/creator-interactions.mdx`
3. `apps/docs-site/docs/hosts/creator-web.mdx`
4. 本计划文件。

## 一个 Task，一个独立预期

原同名用例在导入／激活后、分配和录制前，将 MASTER 设置为非默认 37 并
断言已接受。停止回放后，分别按独立 accessible name 断言 Filter、Delay、
Reverb 为字面量 500，再断言 MASTER 仍为 37。保留原 HOLD=false 和 Pattern
Launch 2 idle 断言；不从共享控件元数据推导预期，不增加 Facade 检查或探针。

原用例标题、300,000 ms 整条预算、6,000 ms 录制尾段、playing／stopped 的
30,000 ms 等待、5,000 ms 数值预期、boot／activation／retry／launch 预算、
项目和 capability 边界均不改。MASTER 就绪使用既有音频转换等待预算。

| 旅程腿 | 必须保留的远端断言 |
| --- | --- |
| 导入／激活／进入 Perform | 原准备 helper 成功，MASTER 可用且接受 37 |
| 分配／移动 Pattern | 原分配和移动的 readback／槽位断言 |
| 演出录制 | 原首个 A01 hit、Filter 630／HOLD、6,000 ms 后第二个 hit |
| 停止／保存 | 原 sealed 状态及 busy-retry 保存，Replay 出现保存条目 |
| 播放 | 原 Replay status 为 playing，排除自然完成代替 Stop 路径 |
| Stop Replay／回到 Live | stopped · neutral，三个命名 FX=500，MASTER=37 |
| 完整收尾 | HOLD aria-pressed=false，Launch Pattern 2 data-launch=idle |

## 验证与交付

最低层证明是全新 own-main 原同名用例真实 RED，然后完整修改用例 GREEN；
focused 结果只证明该完整旅程。源码和索引守卫、实际 canonical 三步终态、
own CMAKE_HOME_DIRECTORY、实际 JS／WASM／dist SHA 与固定测试输入均留在
任务外置证据目录，不能把旧 aa1 dist 冒充新 main。

初始候选的实际最低层结果：canonical configure／build／package 均为 0；
未改原用例为上述匹配 RED；修改后的同名完整用例为 1 passed（21.4 s），
包含录制前 MASTER=37、Stop Replay 后三个 FX=500／MASTER=37 及原 HOLD／
Pattern 尾部断言。两次运行源码、索引和实际 dist 前后守卫均相等。

验证顺序：

1. 实际 fresh configure／build／package 与未改原用例 RED。
2. 四文件修改后的完整 focused GREEN；原每腿断言均执行。
3. `scripts/docs-site.sh check` 完整 Portal；新计划实际暂存后运行既有
   `python3 tests/build/ci_change_scope_test.py`（77）和
   `python3 tests/build/ci_pitfall_ledger_test.py`（15）；检查暂存范围与 diff。
4. 一个 Conventional Commit，精确检查 committed 四文件和工作树。
5. 完整已选择 Creator lane 在 committed head 上运行，保留原全部八组
   Browser 旅程及真实 batch-only `pass key=`；focused 不替代完整 lane。
6. 当前 head 独立／正式评审、实际 findings／conversation disposition、
   live protection／conflict／batch evidence 检查后，由 owner 继续合并。

不新增 gate，不降低严格性、超时或 lane／旅程覆盖。新 main 若改变相关
producer／consumer／验收证据，按 issue-done §0 刷新实际前提再继续。

## 环境与保留证据

使用普通 UID501、既有 pinned EMSDK 6.0.5、Host Node 26 与锁定 Playwright
1.62.1。依赖仅在六份 package／lock source byte-equal 后 APFS COW 至本
工作树；独立 regular inode、相对有效 symlink、hidden lock 及 donor 前后
守卫均核对，不复制 donor CMakeCache、absolute graph、runtime／UI／dist。

原固定 Project fixture SHA
`66262c9187cb264a006e29d077751186acdeb02a30fc4bc497482049297e938f`、
767,554 bytes 及 producer 输入与当前 main 实际字节一致，明确复用原固定
测试数据；不声称本头重新生成或旧完整 suite PASS。初始可用空间约 1.48 GiB，
保留真实 ENOSPC 风险，不造任意磁盘门槛，不删其它缓存／日志／源码／Git。

旧 EEF 完整八组仍为 FAIL（114 passed／2 failed／11 skipped）；首次 fresh
owner boot 失败原因仍 UNKNOWN。1698 NoTestsFound、aa1 focused owner PASS
和 aa1 replay RED 均保留各自边界，不能推导 full8、听感、release 或 Goal 完成。

## Version Management

Version impact: none — 仅修正 Browser 独立预期和已实现 MASTER 的当前文档
事实；不改 API、Contract、active manifest、Assembly 或身份，不分配版本。

## Documentation Impact

Documentation impact: required
Affected portal pages: `/hosts/creator-interactions/`、`/hosts/creator-web/`。
同一 Task 更新两页当前 MASTER／Stop Replay 事实；身份继续从 active manifest
派生，不手填 Build／版本，不创建 snapshot 或 release。
