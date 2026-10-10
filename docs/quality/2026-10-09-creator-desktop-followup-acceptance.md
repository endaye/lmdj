# Creator Desktop Final 后续验收台账

本记录是 **2026-10-10 的未完成验收快照**。工作区基于
`133939a945b3ea10f7686ab1f0a9f8d58c998aee`；提交前重新检查的 main 为
`59a121b78db1486b01f482ba2726eb8fd05cb0f6`。四旋钮 consumer 为 Draft PR
[#1936](https://github.com/endaye/lmdj/pull/1936) 的
`65b237cdb4bdf0d9046ab3de4e92ef9b80d934d1`，基于
`a2a43cc088ab35e40297e80eecb7ef048923a154`。consumer 的证明不覆盖后来合并的
Foundation 修复、main 的本地 Catalog 启动修复或 #1966 的 fixture CLI 构建
缩减。它们都没有补出本轮 browser 的联合证明。没有为这次验收分配新的
Product Build；源码证明以实际 revision 为身份。

[后续计划](../plans/2026-10-09-creator-desktop-final-followup.md) 的完整目标保留。
以下“通过”只覆盖对应证据列；未执行、进行中、失败、待决定均未完成。
Source merge、组件测试和某次浏览器成功不能代替人工听感或整个 Goal 的验收。

## 决定与交付边界

| 要求 | 已有决定/交付 | 剩余义务 |
| --- | --- | --- |
| 原 T1–T11 | 原计划已合并，保持交付 | 不重复实施；最终功能仍需 A1/A2 核对 |
| R1 / #1905 | [#1907](https://github.com/endaye/lmdj/pull/1907) → `0b333d3bd5c1a935a6c481551fb4d885abc78dc8`；连续提交投影修复 | 四页最终整合与人工验收 |
| Sequence 导航 | [#1909](https://github.com/endaye/lmdj/pull/1909) → `502932e345b621abc5533431e61adf0d0253a189`；ENC1 按小节、↑/↓ 当前 Pad | 当前 consumer 整合与完整旅程；其他页方向键待决定 |
| 逐页旋钮 | 已批准 ENC1–3 随页/组变化、SHIFT 细调、固定 ENC4 监听音量 | #1936 为 Draft；完整证明、BPM 可听预览、评审及合并未完成 |
| 监听 producer | [#1910](https://github.com/endaye/lmdj/pull/1910) → `9119a7f90262e1c8ada92ac6b894f5014a5c0cab` | producer 已交付；设备偏好、metronome 与旋钮 consumer 验收仍属 #1936/A1/A2 |
| 400 ms | Sample/BPM 立即预览；停转合并一次保存/Undo；脱离目标取消；Perform 依 HOLD 释放 | Sample controller 通过；BPM 当前仅预览读数，实时可听 producer 未交付；播放位置选择待 owner |
| D01 | 已批准 DUPLICATE；[#1932](https://github.com/endaye/lmdj/pull/1932) → `1992e258b066152e7d08cf5382bf94d21f1d95d1` | 新身份、打开副本、自动保存、独立编辑与 reopen 的最终 A1/A2 |
| D03 | 原有导入/替换/trim 可复用 | Assign 的来源/目标/替换语义及数值细调的 Apply/400 ms 待决定、实现和验收 |
| D04 | ENC4 为设备监听量，保持工程与录音/导出电平 | 独立滤波类型、Mute/Solo、电平表及超出监听的 MASTER 语义待决定、producer/consumer 与验收 |
| #1822 新 SHIFT 建议 | 2026-10-10 评论提出瞬时/一次粘滞、静默选 Pad、组合键 | 是提案；不能从已批准的细调与 Undo/Redo 推导为实现授权 |
| #1868 | 仍 open；历史导入 0 B 停滞未证实因果 | 当前完整证明若受阻，绑定原始 fixture/trace 调查；某次成功或负载相关性不构成根因关闭 |
| A1 / A2 | 见下文 | 完整四页、视觉及真实人工验收未完成 |
| V1 | 当前 active identities 未为 Goal 结算 | 最终 manifests、版本消费者、Portal snapshot 与实际 squash provenance |
| C1 | 已清理项保留原记录；本记录不新增删除 | 活跃、dirty、未保留及身份不清的工作区保护；逐个证明安全后清理 |

## 直接证据及适用范围

证据根目录（仅为该执行机的保留位置）：
`/Users/endaye/Projects/lmdj-followup-evidence/2026-10-09-monitor-output/`。
下列路径相对该目录。SHA-256 和完整 byte length 从实际冻结文件读取；它们是
报告身份，不是 Project Bundle 或音频 Artifact 身份。原输入仍需其自身的
digest、长度及格式验证，不能用报告 digest 代替。

| 报告 | 完整身份 | 证明与限制 |
| --- | --- | --- |
| `consumer-main-a2a43-integration/precommit-terminal.json` | 1850 bytes；`a9832f371299db83e91d6ed66af02405556d36846b86c144de418b88e4cf3049` | 65b 的冻结输入：TypeScript、77 ownership、72 文件/1230 组件测试、50-route Portal 均通过；不是浏览器/听感验收 |
| `consumer-main-a2a43-integration/commit-verification.json` | 2514 bytes；`5dfd2da98e7da412768e46d0fdb048b732e789ef20ad99ddb465de74daf121af` | 36 declared files、commit/head/base 与 clean 状态；仅计划结果段在验证后追加 |
| `consumer-main-a2a43-integration/draft-pr-head-body-refresh.json` | 440 bytes；`01d76ec918508ad853eef1052faaec9f0f6744fb22dfe6e2684ecf671eca5f3f` | expected-head lease 推送 #1936；postcommit ownership 77 通过；PR 仍 Draft |
| `committed-monitor-ui-web-official-launcher/monitor/web_toolchain-terminal.json` | 574 bytes；`64e42695ca1558328d410fd213a5ce9b52cc8661873f2989dd7edd8c2ca76cec` | 精确 `80cae9d63b93b939acc72662dd7ad6cddfa277fe` 的完整 Web Toolchain 通过 637.202 s；仅该输入 |
| `committed-monitor-ui-web-official-launcher/monitor/web_runtime_host-terminal.json` | 583 bytes；`2005d418be4ed1f4e5d9fe22186fb3ba3a0f11a97243e10c54651e4462b807d0` | 同一 80ca 输入完整 Web Runtime Host 通过 849.301 s；固定原容差与原旅程，非 physical Safari |
| `transport-replay-publication-fence/reported-publication-frame-correction/commit-verification.json` | 1709 bytes；`96c0eaad67707943d0427ba8e677cdc5dd84051d5babb3c6084b1ecca0926a5b` | 精确 `b741da4afd1912debbf7d80640f9fb205229fa21`：原完整 native group 通过 59.89 s，原 120 s 上限；不是浏览器失败根因关闭 |
| `json-depth-immediate-refusal/final-five-file-input/native-precommit-terminal.json` | 2150 bytes；`e9992e96beb7445c6079cb36ada542e6a6987e494241c94bb84898d3c7456bf4` | 0fda 最终输入的原五个 Foundation case：GNU dev/ASan 通过，原 10/30 s 上限；不是全部 sanitizer 健康 |
| `json-depth-immediate-refusal/final-five-file-input/wasm-precommit-terminal.json` | 1696 bytes；`d3e645726a8299da1ec729a50f586180f705ce377d8ca84ca38591b4da68ff63` | 同一原五 case，pinned Emscripten 与 Node 26 执行通过；私有拒绝信号被包含 |
| `json-depth-immediate-refusal/committed-linux-lanes/core_ubuntu-terminal.json` | 856 bytes；`e59774269774ee431dbafddbee8712deb199050bb53ac5c9847d0382550c5b31` | 精确 `0fda15f1c33bd43973d6b167bbcbc79f72afb226` 的完整 Ubuntu lane：225/225 与 Core proof 通过，623.093 s；非 current-main 联合证明 |
| `json-depth-immediate-refusal/live-postmerge-state.json` | 569 bytes；`bdbf6e2057ef51ca815544b64ff221275e0c669e902b7581427e2fbab952c631` | #1956 已合并 `133939a945b3ea10f7686ab1f0a9f8d58c998aee`；全 batch 验收未完成 |
| `consumer-65b237cd-complete-creator/terminal.json` | 729 bytes；`e3943a2c15d9d784990a3df2bb68f0a224b3c5a10e3f6045641ef03191829eab` | 精确 65b 的原完整 Creator lane 七组全部结束，exit 1，1987.298 s；112 passed / 2 failed / 11 skipped；不是整体验收通过 |

当前 Creator 原完整验证绑定 65b，冻结输入未改：原 general/candidate、Catalog、
Sample、WebKit boundary、capture、denied capture、Sample WebKit 七次调用必须
全部结束并检查各自终态。执行时使用锁定 npm/browsers、官方 OPFS WebKit
`pw_run.sh` 和 pinned SDK；早先 raw app launcher 的失败/取消保留为无效启动
证据。65b 的临时目录为 `/private/tmp/lmdj-ui-65b-e6x_ai4d`；实际生成 fixture
观察值保留在 `consumer-65b237cd-complete-creator/live-original-fixtures/`。
完整 lane 已终止失败，不填写 pass key；fixture 观察身份保留在该 inventory，
不能把观察值直接认作完整 Bundle 验收。

该轮 general Chromium 子组已终止为 87 passed / 2 failed / 1 skipped
（13.4 分钟）；Catalog 4 passed；Sample Chromium 10 passed / 1 skipped；
WebKit boundary 1 passed；capture 8 passed / 1 skipped；denied capture
1 passed / 8 skipped；Sample WebKit boundary 1 passed。七组全部结束。
两项失败保留原 trace：硬件 identity 场景的 System 点击开始后约 0.31 s
即触及整个原 30 s case deadline，期间 workspace 截获 pointer；这尚不能
证明持续的 CSS 遮挡。Sequence 场景在 Pattern switch 后点击 Record 却仍
重发旧 Stop command ID，出现 pending-publication/refusal；需要定位旧请求
何时应完成，不能以已合并的 retainer 修复或新 timeout 推定解决。
trace/error-context 位于 65b 工作区的原 `tests/platform/web/test-results/`，
局部 trace 事件保留在证据目录的
`consumer-65b237cd-complete-creator/hardware-brand-intercept-diagnostic/`。

0fda 的原完整 ASan/full+stress、coverage、package、Deploy Contract 验证也未全部
终止；旧 6ec 的完整失败和两个超时 Deploy shard 仍保留。JSON 的深层拒绝
原因有直接证据，不能据此宣称其他 74 个历史失败都已解决。主分支已有修复
不改变冻结 proof 的实际源码身份，也不补出过去未执行的合并检查。
0fda 原完整组中 `foundation.json` 已通过（0.03 s），但 MCP/CLI 与
headless proof 已出现其他失败；各自 timeout、输入和终态仍需单独定位。

## 四页旅程逐段核对

| 页面/边界 | 正常路径与 far-side 观测 | 拒绝/失败/取消/历史/重开路径 | 当前覆盖 |
| --- | --- | --- | --- |
| Project | ENC1 选择、ENC2 滚动；选择只改视图，OPEN 后才改变 active Project | 复制新身份并打开；副本/原工程独立编辑；自动保存后 reload 指向副本；拒绝不能投影成功 | 65b controller 和 Duplicate browser journey 通过；整组仍失败，人工未执行 |
| Sample Trim/Sound | 同一 Pad 的 start/end/pitch/gain/pan/tone 旋钮即时 preview；停转 400 ms 后一次 authoring/Undo；no-op 不保存 | 换 Pad/页/工程/System/Esc、Undo/Redo、所有权/录音锁先取消；sent result 正常 ack；取消不产生晚到提交；failure 恢复完整 readback/Truth；Undo/Redo/reopen 保留完整 sound identity | 原 helper/controller 通过；65b 真实 packaged contextual encoder、parity/history/Pad Delete 的 Chromium 组 10 passed / 1 skipped；DSP 听感未执行 |
| Sequence | 一小节/一行导航；↑/↓ 选 current Pad 不发声且不改 event selection/Truth；BPM/Swing touch readback 与 encoder 保持一致 | SETUP/离页禁用相关导航；cancel/refusal 恢复两处 BPM 读数；authoring 历史及 reopen 均核对完整 pattern/event 身份 | component 与既有导航交付；BPM 即时可听预览尚未实现，因此 D2 未通过；65b browser 的旧 Stop/Pattern switch 旅程失败 |
| Perform | 三个主 FX 与三个更多 FX 的真实 gesture；停转/切组保持值；触摸接管沿用同一 Core gesture | 离页依 HOLD 关闭；录音中 rotary→touch→leave 后 open-FX count 为零；Stop 后真正封 WAV，Save 后完整 binding/长度/digest，reopen/replay 保留 FX；失败保留 durable prefix；discard 删除 temp WAV | controller 与 65b recorded rotary takeover、原 complete/discard/crash/recovery/replay browser journeys 通过；听感/真实生命周期未执行 |
| 全局 ENC4 | 0–100；任意页/System 同一设备偏好；恢复后再启用，较晚 turn 优先；metronome 入同一 monitoring destination | corrupt/refused/never-settling storage 有 bounded fallback；录音/导出/Project Truth/history 独立；reload 记住包括 zero 的值 | 65b helper/controller、routing 和 preference reload 断言通过；80ca 原监测图证明通过；实体输出/录音对比未完成 |
| 输入/视觉 | 各页字体、8-row fit、readback、实际 console viewport/scale 与命中位置 | disabled 不积存命令；SHIFT fine/Undo/Redo；System focus 返回；pointer owner 转移有 far-side assertion；窄屏不裁切错误/恢复操作 | 新整合 controller/布局断言通过；旧 b07 的 Figma 14/18 仅历史诊断，不能作为 65b fidelity；真实键盘/旋钮、Safari/iPad、辅助技术未执行 |

每一行均需完整路径，不能只取成功终点。组件中的模拟副作用不代表真实 OS
输入或 AudioContext interruption；浏览器 capability boundary 也不代表真实
Safari/iPad。未决定的功能没有可接受的最终期望，不能用当前未渲染状态验收。

## A2 人工执行步骤（均未执行）

前置：先完成产品决定和实现，选择含 #1953 本地 Catalog 配置及 Goal 最终
整合结果的 clean source；记录完整 revision、由 manifests/report 读取的身份、
设备/浏览器版本、实际操作者与日期，按 Creator README 配好锁定 SDK、Node 与
browser 前置。使用 `scripts/creator-web.sh package`，
再 `scripts/creator-web.sh serve --port 9000`，打开 `http://localhost:9000`。
package/serve 成功后记录实际 report 的完整 digest/byte length；不要把当前
65b 或旧 Build 偷换成该最终来源。

| 操作 | 步骤 | far-side 预期与需保存证据 |
| --- | --- | --- |
| Project | 创建、编辑、等待 autosave；DUPLICATE；分别编辑原/副本；reload；拒绝操作后返回 | 新且不同 identity；当前副本正确；原/副本完整内容独立；拒绝不投影成功；截图与完整 Project 身份 |
| Sample | 四个物理旋钮/真实键盘与触摸逐个修改；快速跨参数转动，停止；切 Pad/System/Esc/Undo；Redo、重新打开 | 实际声音/波形与合法单位一致；每轮 400 ms 一次 Undo；未提交预览在所有取消边界消失；完整参数与 persisted Truth；步骤时间与听感记录 |
| Sequence | 横/纵导航、当前 Pad、BPM 转动、触摸取消/拒绝、Swing SETUP；Undo/Redo/reopen | 导航只改视图/选中；BPM 转动立即可听且位置符合 owner 决定；400 ms 仅一次保存/Undo；取消恢复；完整 pattern/event 身份 |
| Perform | 主/更多 FX 转动，停转与切组；HOLD on/off 离页；录音中旋钮转到触摸；Stop、Save、reopen、replay、discard | 听感正确；同一 gesture owner；离页按 HOLD；无重复 capture；实际 WAV 完整 binding/digest/长度与 replay 一致；discard 后临时件消失 |
| 监听/录音隔离 | 先导入确定样本，录内部 master；ENC4 100→50→0，再恢复；打开 metronome；重新打开 | 可听输出/节拍器随 ENC4，zero 静音；相同工程参数下内部录音/导出电平不因 monitoring 改变；设备偏好恢复；实测 WAV 身份/电平和设备路由 |
| Safari/iPad/窄屏 | 实际 Safari 与 iPad：首次 gesture、触摸旋钮/slider、portrait/landscape、System/回页、background/foreground | 实际 AudioContext 与设备恢复状态；无控件/错误遮挡；真实触摸命中；截图、版本及 lifecycle 日志 |
| 辅助技术/拒绝 | 用真实 Tab/Shift+Tab 与屏幕阅读器操作四页；导入下方生成的无效 bundle，确认拒绝后继续打开原工程；浏览器站点权限拒绝麦克风后尝试 Sample 输入录音，再恢复权限并 retry | focus/name/state 可操作；真实拒绝不改原 Project，不留 ghost capture；retry 后实际新 capture/Truth 与 reopen 正确；保留诊断、设备权限与各段观察 |
| Owner loss/recovery | 在单独的测试工程里启动内部 master 录音，关闭该浏览器窗口；重新打开同一 profile/工程，按恢复入口分别验证保留/丢弃 | 一份 recoverable durable prefix、无第二 capture owner；保留后完整 WAV/Project 身份正确；丢弃后 temp 删除；两条路径都需 reopen 后断言 |

无效 bundle 在系统临时目录创建，输出其路径后用 Project Import 选择该文件：

```bash
python3 -c 'from pathlib import Path; import tempfile; p = Path(tempfile.mkdtemp(prefix="lmdj-refusal-")) / "refused.lmdj"; p.write_bytes(b"not a project bundle"); print(p)'
```

Quota/storage failure 的真实设备条件与安全注入步骤尚未建立，仍是独立缺口；
不能用无效导入、permission refusal 或成功 retry 替代其完整失败/恢复路径。

当前无以上人工结果、操作者记录或最终 Build 身份。要求真实设备或 owner
操作的步骤不能由自动化、计划文字或预期推定为完成。

## 收尾审计

Goal 保持未完成。待 owner 选择的播放位置、其他页方向键、Assign/细调、D04
范围不因暂缓或提案消失。后续补证必须追加实际 terminal report 和输入身份，
重新核对当时 main、PR head、完整评审/讨论、版本债务及 provenance。V1 后
必要的身份敏感复验与 C1 的每个安全删除证明仍保留；本台账不授权或执行 tag、
Release、部署、Channel、远端分支或云资源清理。
