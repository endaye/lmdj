# Stage 12A Slice 固定候选验收包

核定日期：2026-09-22。文件名保留 S1/S5 计划中的稳定路径。
S1 [#1166](https://github.com/endaye/lmdj/issues/1166) 的交付是验收准备；
Windows 操作/听感 S2、代表性评测 S3、产品裁定 S4、状态对齐 S5 尚未完成。
依据：[独立交付计划](../plans/2026-09-10-stage12-independent-delivery.md)、
[已确认 Contract/Candidate 决策](../prd/decisions/2026-09-09-stage12-contract-candidate.md)。
证据入口、素材完整身份、复现命令和结果模板见[证据 README](evidence/stage12-slice/README.md)。

## 1. 固定候选与适用边界

本轮只使用以下已合入 main 的候选。S2/S3 开始前重新验证下载的字节；
不得用滚动生产 URL、最新 main、同名本地重建或新的补丁替换它。
若需更换候选，先形成新核定记录，再重验受影响旅程；保留旧失败。

| 身份 | 核定值及来源 |
| --- | --- |
| Product Build | `1.0.61.0`，候选的 `products/lmdj/version.json` 与 ZIP 内 `dist/host-manifest.json` 一致 |
| source commit | `07044d2950c3ee6ff382468a536d6be87e5cd5d8`，已合入 main；固定 tag `lmdj-v1.0.61.0` 的目标 |
| Creator / Platform | `creator-web` `4.4.0` / `web-runtime-platform` `5.3.1`，分发 manifest |
| 分发物 | `lmdj-creator-web-4.4.0-product-1.0.61.0.zip`，2,348,994 bytes |
| 分发物 SHA-256 | `743ec10a965b1288fb59d9b780044e151b878179c0184775192cf27b1eaa5858`；本地实际字节与 Release asset digest/size 一致 |
| Assembly lock SHA-256 | `47d5be5993fddb94f27ca40badd7770993d19df728cb1d0985c6b8fd681f8a8c`，候选源文件实际字节 |
| Provider | `local.sample.slice` `1.0.2`，API 3，SDK `2.2.0`；候选 `providers/local-sample-slice/module.json` |
| Capability / output | `sample.slice.v1` `1.0.0` / `lmdj.slice-points.v1` `1.0.0`；候选 Contracts |
| 快照 | `apps/architecture-portal/versioned_metadata/version-1.0.61.0.json`，canary；冻结源 `4057a4a1ed5e1aa27cef520a54fb93cb6839fea4`，冻结时间 `2026-09-18T04:11:16.091Z` |
| 快照来源闭合 | 同目录树 `versioned_provenance/version-1.0.61.0-squash-witness.json`；introducing revision `e4ac00629916e1a95e35b2cd53500ee1aa31cf18`。冻结源、引入提交、候选源是不同身份，不能互填 |

[固定 Release 与下载](https://github.com/endaye/lmdj/releases/tag/lmdj-v1.0.61.0)，
Release ID `392944682`。本包选取既有分发物，不分配 Build、快照或 Release，
不改变 Channel。ZIP manifest 本身没有 source SHA；source 由不可变 tag、
release plan/发布审计与 archive digest 绑定，不能声称 manifest 含有该字段。

当前实现仍是同进程、确定性的 reference/test 算法，`model_identity: null`，
没有 checkpoint。Creator 显式选择 Provider、授予 `sample.slice.execute`、
确认 public audio，使用 `platform=test`、`region=local`。这不证明 Windows
平台支持策略已晋级，也不把 Contract 的资源声明当作可强制执行的保证。

## 2. K/L 实现和 exact-source 证据地图

以下 10 个关闭 Issue 的实际合入 SHA 均经 `git merge-base --is-ancestor`
核实位于候选历史中。关闭状态只表明任务交付，产品质量仍待 S2–S4。
完整合入 SHA 与当前候选 CI 记录见证据 README。

| 阶段 / Issue / 合入 PR | 当前候选上的核查入口 | 覆盖边界 |
| --- | --- | --- |
| K1 / #1033 / [#1049](https://github.com/endaye/lmdj/pull/1049) | `tests/conformance/` 的 Slice schema/context vectors | 输入、输出 Contract；不证明音质 |
| K2 / #1034 / [#1075](https://github.com/endaye/lmdj/pull/1075) | `tests/core/provider/artifact_source_test.cpp` | owned bytes、lease、输出验证与终态 |
| K3 / #1035 / [#1079](https://github.com/endaye/lmdj/pull/1079) | `tests/core/provider/sample_slice_test.cpp` | Registry/AttemptStore 真执行、负例、重复字节；历史 scorer 数值单列 |
| K4 / #1036 / [#1084](https://github.com/endaye/lmdj/pull/1084) | `products/lmdj/assembly.lock.json`、`tests/core/facade/assembly_loader_test.cpp` | 注册、身份与拒绝；不更改默认授权 |
| K5 / #1037 / [#1091](https://github.com/endaye/lmdj/pull/1091) | `tests/core/facade/provider_owner_test.cpp`、`tests/platform/web/provider_owner_journey.mjs` | Host→Facade→owner→Attempt，重开后完整输入/输出身份 |
| L1 / #1038 / [#1113](https://github.com/endaye/lmdj/pull/1113) | `tests/core/facade/candidate_job_test.cpp`、`candidate_store_test.cpp` | Workspace Job/history/active set、进程恢复 |
| L2 / #1039 / [#1141](https://github.com/endaye/lmdj/pull/1141) | `tests/core/facade/candidate_adoption_test.cpp` | 明确目标、配额、单 revision、整体原子性 |
| L3 / #1040 / [#1126](https://github.com/endaye/lmdj/pull/1126) | `tests/core/domain/candidate_adoption_test.cpp`、`tests/core/project_io/candidate_adoption_test.cpp` | 完整 lineage、保存/加载 |
| L4 / #1041 / [#1143](https://github.com/endaye/lmdj/pull/1143) | `candidate_job_test.cpp`、`candidate_store_test.cpp` | 取消、discard、supersede、失败重试、并发所有权与 crash/restart |
| L5 / #1042 / [#1147](https://github.com/endaye/lmdj/pull/1147) | `tests/platform/web/creator/creator_web_candidate.spec.mjs`、`tests/platform/web/candidate_journey.mjs` | 真 UI/Host 预览、停止、采纳、重开；物理听音另验 |

已读取 [2026-09-21 候选运行](https://github.com/endaye/lmdj/actions/runs/35564190757)
attempt 1 的原始日志：请求 target 和实际 checkout 都是上面的完整 source SHA，
控制 workflow 的 head 是 `7c54aea3d68a1b0eeba2164562ab6f6f8557c513`，不可混用。

- Core Ubuntu job `106229286312`：208/208 CTest passed；包含
  `provider.sample_slice`、`provider.artifact_source`、`facade.provider_owner`、
  `facade.candidate_job`、`facade.candidate_store_recovery`、`facade.candidate_audition`、
  `facade.candidate_adoption`、domain/project_io candidate adoption。
  另有 Slice 40 vectors + 4 boundary cases。此处没有把 full 当成 stress。
- Creator job `106228094309`：Vitest 35 files / 594 tests passed；Chromium 主组
  56 discovered / 55 passed / 1 skipped，其中 Slice UI 8、共享 Candidate journey 6
  全部实际执行，源码无 `test.fail`/`skip`/`fixme` 标记。跳过的其他测试不算通过。
  其余浏览器组分别为 3 passed/1 skipped、1 passed、7 passed/1 skipped、
  1 passed/7 skipped、1 passed；这些摘要不扩展 Slice 覆盖范围。
- Headless WebKit 只选 capability-boundary 检查，不能据此声明 Safari Slice 成功。
  CI 的 Linux Chromium、模拟音频与页面 reload 不等于 Windows 听感或 OS/浏览器进程重启。
- S1 未重跑这些产品测试；它核查既有 exact-source 日志和源断言。
  CI proof 构建与正式发布 ZIP 是同源的独立构建；未证明 CI 使用的 ZIP 与发布 ZIP
  逐字节相同。S2 必须实际消费上表发布 ZIP。

[K3 历史报告](2026-09-09-stage12-k3-reference-results.md) 的 smoke 结果为
TP/FP/FN=4/0/1、precision=1、recall=0.8、F1=8/9；overlap 的第二 onset 漏检。
报告没有独立的完整执行 SHA/raw scorer 输出绑定，不能直接称为本候选新测量。
候选保留相同 smoke manifest digest，K3 实现提交在其历史内；S3 仍须在候选上
真实双跑并保存 scorer/validator 原始输出，不从这段摘要填造报告。

## 3. 评测前锁定的判定口径

### 已确认的不变量

每次成功采纳必须是明确选择的唯一目标 Pad 集合，一次命令、一次 revision；
重复 recipe 可去不同 Pad，重复目标不能通过。原 Asset 的完整 ArtifactRef 和字节
不变；原 Pattern 对象/事件逐项不变。事件仍引用 Pad Slot，所以覆盖已占用 Pad
可以改变该槽的音色，不能因此要求音频听起来完全不变。
分析、试听、停止、取消、discard 和失败本身不得修改 Project Truth。
失败采纳应零部分写入；未知结果必须先 inspect，不得盲目生成新命令重试。

无 onset 是成功的空 recipe 集，不允许伪造 whole-source fallback。
成功重试发布新 set 并 supersede 旧 set；失败或取消的重试保留旧 active set。
discard 保留 history、终态和已经采纳的 Assets/lineage，不进行隐式 GC。

### 质量与性能用例（S3 在运行前冻结扩展 manifest）

| 类别 | 固定观测/计分方式 | 产品阈值 |
| --- | --- | --- |
| 既有 basic / overlap / silence | 保留原 onset labels 与各自 480/240/480 frame tolerance；使用现有一对一 scorer，逐类 TP/FP/FN 和 micro 指标；静音零分母为 N/A | smoke 仅回归与观察；不得用更宽 tolerance 掩盖漏检 |
| 力度差异 | 相同时间布局，不同整数峰值，包括阈值两侧；真值来自独立构造，不能按检测结果生成 | 可接受漏检率待确认，S3 探索性结果 |
| 尾音重叠 / 密集瞬态 | 分别改变 tail 与 onset 间隔，包含 refractory 两侧；保留漏检和误检 | 分类别最低 recall/F1 待确认 |
| 单/双声道、44.1/48 kHz、静音 | 独立真值，右声道独有瞬态、无信号；不支持输入记录拒绝 | 正确通道/采样率/边界与无伪输出是现有不变量 |
| 重复执行 | 相同原始输入、参数与候选两次真实 execute；比较完整输出字节及 digest/length | 确定性要求严格相等 |
| elapsed / RTF | harness 在真实 execute 前后计时，保存原始 elapsed；RTF=elapsed/(frames/sample_rate)，声明包含的阶段与重复次数 | 最大耗时/RTF、样本量及统计目标待确认 |
| 听感 | 同一源/切片对照，记录漏瞬态、断尾、边界点击声、噪声与可演奏性；每片先听再打评语 | 用途、可接受缺陷比例/评分待产品负责人确认 |

`in_process_reference` 只能 `observation_only`。硬 timeout 与单 Attempt 独立 RSS
不可强制证明；RSS/GPU 按既有 validator 的 `not_enforceable`/null，sampler/deadline/
kill grace 为 `not_applicable`；不得写 0 或 pass。耗时观察不等于硬超时验收。
不新增门禁，不降低现有标准。未确认阈值在 S4 中保持未确认，S4 可以据此裁定
reference-only/no-go 或要求补证据；不能看完结果才设一个刚好通过的生产阈值。

## 4. Windows S2 操作前准备

1. 在真实 Windows Chrome 或 Edge 的独立测试 profile 操作。记录 Windows build、
   浏览器完整版本、设备、输出设备/采样率、origin、操作者和 UTC 时间。
   WSL 只可作为构建/本地服务环境，其 OS 与工具链单列，浏览器必须运行在 Windows。
2. 按证据 README 下载并校验 ZIP，使用仓库既有 distribution server 提供隔离头。
   固定 `http://127.0.0.1:4175` origin，保持同一 profile。保存 manifest、HTTP 隔离头、
   `isSecureContext`、`crossOriginIsolated`、SharedArrayBuffer、OPFS 与 AudioWorklet
   实际 preflight 结果。能力拒绝就记录 BLOCKED 和错误，不绕过 preflight。
3. 按证据 README 用候选的既有 CLI fixture generator 准备含非空 Pattern 的可丢弃
   bundle；在 Creator 点 `Import .lmdj` 导入。其 A1 已有声音，Pattern 已引用 A1。
   在 Sample 的空 C1 导入 CC0 basic 素材，完成区间选择/提交后将该 Asset 作为 Slice
   Source；停止录制/transport。记录生成命令、CLI 身份及 bundle digest/length，
   不使用无来源现成包。该候选没有通用 Project 导出按钮；基线由公开 inspect 和
   只读 OPFS 取证保存，不能把 `Export report` 当成 Project 导出。
4. 定义 `P0` 为导入、分配和 Pattern 准备完成后的完整 Project inspection；记 revision
   `r0`、源 Asset ID/ArtifactRef、源 bytes、全部 banks/pads、完整 patterns。
   若导入转码，磁盘原文件和 Project 内 WAV 是两个身份；分别保存 hash/length，
   Candidate 绑定后者。不能拿磁盘 fixture hash 冒充 Project Asset hash。
5. 每次操作后、下一次操作前留证。Project/Job/Attempt 查询走公开 Host/Facade；
   持久化字节可以只读导出检查，禁止手改 Project bundle 来构造通过结果。

## 5. 完整成功旅程

每行单独判定；不能用最后一次重开替代中间转换。当前 Windows 结果全部 NOT_RUN。

| ID | 操作 | 下一操作之前必须观察的状态 |
| --- | --- | --- |
| W01 | 打开 Slice，选择 Source 和 Local reference detector | source 与 P0 一致；未授权时 Analyze 不可用，Project=P0 |
| W02 | Grant analysis permission，确认 public audio，再 Analyze | 新 Attempt/Job，记录实参 `{}` 及实际默认 threshold=4096/refractory=240；active set 指向成功终态，完整 source/output refs 与 recipes 匹配；Project=P0 |
| W03 | 先在未激活音频时 Preview，再 Activate audio 后 Preview | 第一次 played=false 不得写成已听见；第二次实际听到指定区间，记录听感与输出设备；Project=P0、无新 Asset |
| W04 | Stop preview；另一次试听后切换模式 | 在刷新/下一试听之前确认输出停止；stop 回执与实际听音分列。模式卸载也停止，Project=P0 |
| W05 | 页面刷新并 Open Project，再进 Slice | 不自动重分析、不自动播放；原 active set/history 可 inspect；Project 与源 bytes 仍等于 P0 |
| W06 | Add target，两行明确选择同一非静音 recipe→B1、B2 | 行初始为空；记录 recipe/set ID 与目标；若故意选同一 Pad 两次，提示重复且不可提交，revision=r0 |
| W07 | 修正重复目标后只点一次 Adopt selected slices | 只一条 adopt 命令；revision=r0+1；B1/B2 各生成不同 Asset ID，PCM 符合 recipe；原 Asset、全部 Pattern 逐项等于 P0，其他 Pad 不变；完整 lineage 与 set/Attempt 对应 |
| W08 | 在 reload 之前击打 B1/B2 并停止 | 当场听到新切片，不能靠重新加载才更新声音；占用 Pad A1 的替换用另一份独立基线重复 W01–W11，不能在本次 W09 前多做一次采纳 |
| W09 | 核对采纳提交后的持久化字节 | 公开 inspect 与只读 OPFS 中完整 Project manifest、源/派生 WAV hashes/lengths 可复核；不得凭 UI success 推断已落盘；没有额外 Save 按钮，不要重复采纳来“保存” |
| W10 | 页面刷新→重开 Project | revision=r0+1、完整 banks/assets/lineage/patterns 与 W09 相等；每份源/派生 WAV digest/length 一致；不恢复试听 |
| W11 | 关闭浏览器进程，再启动同一 profile/origin→重开 | 单独核验 W10 的全部条件；记录这是真实浏览器重启，不将 page.reload 标为进程重启 |
| W12 | Discard slices 后再次重开 | active pointer 清除、set discarded/history 保留；W09 已采纳资产/lineage/Pattern/revision 和 bytes 不变 |

Lineage 比较必须包含 `source.kind=asset_artifact`、`artifact_sha256`、分析时的 source
`project_revision`（本成功旅程为 r0；不替换成后来的 revision）；
`derivation.kind=capability_adoption`、capability/provider 完整身份、
`model_identity`、`parameters_sha256`、`attempt_id`、`source_asset_id`、完整
`output_artifact`，以及 recipe 的 `kind/start_frame/end_frame/frame_rate`。
按候选真实对象检查字段，不只比较 kind 或 media_type。

## 6. 失败、取消、恢复与重试旅程

每个分支从独立的已保存基线开始。`P` 表示该次操作前 Project 与持久化文件；
外部合法编辑后重新取 P，不能要求合法编辑也被回滚。所有 Windows 行仍 NOT_RUN。

| ID | 触发与转换 | 立即 far-side 与重开后断言 | companion / 无法 UI 触发时的处置 |
| --- | --- | --- | --- |
| F01 | 静音→Analyze→刷新/重开 | success、零 recipes、无整源 fallback、不可采纳，Project=P | Slice UI zero-onset 用例 |
| F02 | 缺授权/错误 source binding/不可用源→失败→inspect | 准确拒绝；不产生可采纳 set，无 Project 变化；终态/拒绝边界按实际记录 | provider_owner journey；源文件缺失可能使 inspect 报 INVALID_PROJECT，比较故障后的文件集合，修复故障后再 inspect/reopen |
| F03 | 有 active set→参数拒绝导致 retry failed→重新 inspect→合法 retry | 失败时旧 active set 保留；显式新 Attempt 成功后新 set active、旧 set superseded；Project=P，旧终态 bytes 不变 | `failed_retry_retains_active`；UI 不提供任意参数，使用真实 Facade companion，不伪造 UI 故障 |
| F04 | pending/interrupted Attempt→Cancel→Provider 后返回→重开→Retry | 精确取消 Attempt，取消结果不发布；旧 active set 保留；重启仍 cancelled，新 retry 有新 Attempt ID | L4 recovery/独立进程测试。UI Cancel 只在 pending/interrupted 可见；同步执行很快，未抓到窗口记 NOT_RUN，不用已完成 Attempt 冒充 |
| F05 | published Attempt→Cancel；旧取消请求晚于新 retry | 完成的 Attempt 明确拒绝取消；迟到取消不影响新 Attempt；Project=P | `lifecycle_dispatch_and_tombstone`、L4 store recovery |
| F06 | 成功 retry（也含零 onset）→supersede→尝试旧 set 试听/采纳→重开 | 旧 set unavailable，零 onset 新 set 仍替换旧集；无隐式恢复旧结果，无 Project 变更 | `empty_success_supersedes`、共享 Candidate superseded journey |
| F07 | 失败/取消后 Discard→重开 | 即使输出不可用也可落 tombstone；active pointer 清除、history/终态保留；Project=P | `unavailable_bytes_do_not_prevent_discard`、L4 store recovery |
| F08 | 修改 Project revision/替换源 binding→旧候选采纳 | stale/source-changed 拒绝、全 Pad/Asset/revision/文件等于操作前 P；先 Refresh 再决定后续动作 | Slice stale UI；`early_freshness_and_unrelated_edit`、`source_binding_replaced` |
| F09 | 重复目标或配额超限→采纳拒绝→inspect→减少选择后显式重试 | 没有部分 Asset/Pad/revision 写入；配额边界保持原值；成功重试才增加一次 revision | UI duplicate；`strict_selections`、`quota(true/false)`；配额 UI 难构造时用固定候选 companion，记录平台缺口 |
| F10 | 采纳写盘失败/第二份输出失败→discard/重开 | 失败整体零变更，释放 lease，discard 成功持久化，源/Pattern 不变 | `save_failure_and_lease_unwind`、`second_artifact_failure_is_atomic`、L4 真实 commit race |
| F11 | adopt 已发送但响应/投影丢失→Refresh inspect→重开 | UI 阻止再次采纳（含 source 切换）；查询实际 revision/Assets/lineage，判定零次或恰好一次提交；禁止盲重试，未知即保留 UNKNOWN | `candidate_surface.test.tsx` 的 committed adoption / pending adoption 用例是 mock companion；真实传输中断与 Windows 结果仍未验收 |
| F12 | intent/terminal/publication 边界 crash→进程恢复→inspect→cancel/retry/discard | 无半发布、无重复 set、终态不可变；各恢复点分别核验 active/history/Project；后续 lifecycle 操作可完成并持久化 | `candidate_store_test.cpp` 独立进程断点，不能用 graceful reopen 代替 crash |

companion 证明的是它实际执行的边界；mock、独立进程测试、浏览器故障注入与人手操作
分别标记。不能为了做 UI 演示而在产品包加入故障开关。新 harness/fixture/修复先另列
精确文件和 Task；S1 不扩写产品。失败收集复现、原始错误、受影响 leg 和既有 Issue
去重结果，由 S4 拆缺陷；S5 才对齐最终状态。

## 7. 本 Task 的验证与交付边界

声明文件仅本文件和 `docs/quality/evidence/stage12-slice/README.md`。
最低层验证：候选 manifest/archive/快照来源与 K/L ancestry、exact-source CI 日志和
源断言交叉核查、两份 Markdown 相对链接、`scripts/docs-site.sh check`，新增文件 staged
ownership 及 PR declaration/closing-directive 检查。没有产品行为变更或新门禁。
Pitfall impact: none；应用完整旅程、立即观测与 expected-failure 不算通过的既有规则，
未新增过程缺陷或伪造 recurrence。

## Version Management

Version impact: none。选择已有候选并记录验收材料，不修改 Module、Provider、Contract、
Host、Assembly 或 Product 身份，不分配 Build/快照，不执行发布或晋级。

## Documentation Impact

Documentation impact: none。
Reason: retained 验收包不更改当前 Portal 页面/可用性；S5 保留 Portal 对齐责任。
按 S1 验证要求仍执行 docs-site check，其通过不代表产品验收通过。
