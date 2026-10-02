# Stem / Slice：Provider Contract 与 Koala 功能边界

日期：2026-10-03。状态：架构与功能方向已确认，活动接口尚未实施。
依据：[确认记录](../prd/decisions/2026-10-03-stem-slice-provider-boundary.md)。
基线：`887752c8f7c3dec9007218da26a4f5e3035020b4`；源码事实只针对该 revision。
交付顺序见[计划](../plans/2026-10-03-stem-slice-provider-delivery.md)。

## 1. Koala 参考与 LMDJ 选择

2026-10-03 阅读发布方 [Sample 手册 §4.7、4.9、4.10](https://manual.koalasampler.com/mobile/4-sample/)。
参考其 Tools 入口、三种切片方式、标记编辑、试听、保留原样本及四声部分离。
以下是 LMDJ 自己的范围与交付顺序，不声称已验证 Koala 的实现或性能。

| 功能 | LMDJ 决定 | 交付边界 |
| --- | --- | --- |
| 工具入口 | 选中 Pad 后从 Sample → Tools 操作；移除独立 Slice 模式 | #1670；保留现有公开 Facade 控制面 |
| Chop | 瞬态、等分、播放打点；支持标记增删移动和逐片试听 | 先现有瞬态；其余为有独立测试的后继 Task |
| 切片落点 | 默认提出空 Pad 映射，保留原 Pad，确认后原子采纳 | 不能用自动选位代替用户采纳；满位拒绝 |
| 播放选项 | One Shot、Choke Group、Play Thru 是功能目标 | 不属于 Provider 参数；播放语义独立实施 |
| Stem | 鼓、贝斯、人声、其他四路，分别试听和选择 | 完整结果集成功后允许只采纳部分角色 |
| 输入编辑 | 所选范围与可支持的 Sample 编辑效果先固化为音频 Artifact | 单独的 Facade 输入准备 Task；未支持的效果明确拒绝 |
| 原音频 | 默认始终保留；首个增量不提供隐式替换原 Pad | 替换须后续明确交互与原子命令 |

与 Koala 的显式差异：LMDJ 保留候选确认和可追溯采纳；首轮 Stem 工程评测
沿用 T1 的 5–30 s、44.1 kHz stereo 范围，它不是整曲处理支持或永久产品上限。
原有「导入歌曲后执行 Tools」目标仍需长音频/分段评测，不在短片段结果后宣称达成。
本轮不复制 Koala 的付费划分，也不推断其未公开的结果放置、模型或容器格式。

## 2. 分层和执行

```text
Sample Tools → Facade 准备不可变输入 → 隔离执行 owner
              → 子进程内 SDK Registry / AttemptStore → Provider → 验证完整 Candidate
              → Workspace 候选与试听 → 用户确认 → 原子采纳 → Project Truth
```

输入准备保存原 Asset 身份、revision、范围、编辑参数及准备后的 ArtifactRef。
分析既有原始 Asset 的路径继续可用；准备后 Artifact 不能冒充原始 Asset bytes。
准备结果由 Workspace owner 持有并按配额计费；取消或未采纳不写 Project Truth。
Sample 效果的具体可固化集合由输入准备 Task 按实际 Core 功能声明，不默默忽略。

Provider 只能获得已校验 ArtifactSource、不可变参数和 output sink；不获得
Project、bundle 路径或 Pad 写权限。API 继续同步 run；执行 owner 把整条真实
Registry + AttemptStore execute 放入受控子进程，管理进程树及 IPC 终态。
Source/sink 回调仍只在 run 原线程有效，不跨进程传函数指针或延长其生命周期。
API 的 timeout 数字不冒充强制杀进程能力。Browser 不能直接创建 Linux 子进程；
浏览器本地实现或显式远端桥接是后继 Host Task，不用 native bench 代替浏览器验收。

## 3. Stem 输入输出

概念 Capability 名称沿用 `stem.split`；正式 ID、版本和清单由 C2 实施时分配，
不在研究文件中冒充已注册接口。输入端口 `source_audio`，一个 PCM16 WAV。
输出为 `drums`、`bass`、`vocals`、`other` 四个命名端口，各 required、max_count=1。
一个 SDK Candidate 拥有四个 binding；一个 Stem Workspace set 展开为四个角色候选。

正式音频 profile 复用已存在的 PCM16 WAV 边界，并增加与输入 shape 的一致性验证：
采样率、声道、帧数与时间起点完全相同。角色来自端口，不依赖数组位置或文件名。
每路消费方校验完整 digest、byte length 和 WAV；缺路、重复角色、未知角色、
错位或坏输出使整个 Attempt 失败。静音角色仍输出正常长度的静音音频，不能省略。

浮点推理到 PCM16 的首个适配规则：拒绝 NaN/Inf；四路共享单位增益；不自动
normalize、移位或削波；把浮点值乘 32768，以 ties-to-even 舍入，结果须在
[-32768,32767]，越界失败。适配器必须为该量化规则和增益行为保存可复现证据。
若模型需要其他增益策略，必须显式版本化，不能悄悄改变输出以通过测试。
该保守规则可能淘汰候选；不把首轮成功率当已批准的产品质量阈值。

参数、determinism 类别、typed errors 和执行限额必须进入正式 descriptor/适配器
定义。首个 Stem Contract 预先声明 `nondeterministic`，不承诺逐字节复现；
评测仍保留重复运行的逐字节差异与质量稳定性。未来若要承诺 deterministic 或
seeded，须以实测证据和独立版本决策收紧，不能在一次评测失败后改类别。
这与 deterministic Slice 分开，也避免正式 execute 依赖尚未执行的模型证明。
重试或换模型/参数产生新 Attempt。

## 4. 角色和内容身份分离

当前 SDK 在 output sink 和 terminal output validation 中按 digest 全局去重。
合法反例是四个静音角色具有同一 WAV 内容。新规则如下：

- 一个逻辑 binding 是 `(port, 完整 ArtifactRef)`；同端口重复 binding 拒绝。
- 不同端口允许共享同一完整 Ref。相同 digest 却声明不同 media type 或 length
  拒绝；每个端口的类型、Schema、required 和 max_count 校验独立执行。
- 同 digest 的耐久内容只发布一份；Candidate / minted bindings 保留每个角色，
  必须逐 binding 完全相等，不把集合比较退化成 digest 比较。
- StagingBudget 按实际持有的缓冲和 lease 计费；在证明共享不可变缓冲前不减账。
  max_output_bytes 按逻辑输出累计，防止重复引用绕过既有限额。
- 失败清理和崩溃恢复按 Attempt 所有权处理共享 blob，不能清理另一 Attempt。
  成功后逐角色读取仍校验完整内容身份；旧 terminal 必须继续可读。
- 输入端口的全局内容唯一性保持现状。该 Task 不引入任意 Project 引用或全局 GC。

这改变现有跨输出端口 duplicate_mint 测试的业务预期，必须以新的正向反例和
同端口/错误 Ref/漏绑/多绑负例替代，不能简单删除去重测试。先证明旧 reader 对
新 terminal 的行为，再决定兼容版本；旧格式不被无证据地当作兼容载体。

## 5. 候选、编辑与采纳

共用生命周期：Job 串行 Attempt；失败/取消保留旧 active set；成功耐久发布才
替换；discard/supersede 不改 terminal。结果解释分别为 Slice intervals 与
Stem roles，不把 Stem 写进 `SliceIntervalRecipe`。

手动调整切片点在 Workspace 创建新的 recipe/set revision，保留来源 Attempt
和编辑证据；自动分析证据不被改写。等分/播放打点可由确定性 Core 操作产生
recipe，不为纯用户编辑额外调用模型。Play Thru 会改变区间尾点，须版本化 recipe。

Stem 采纳的封闭 Lineage 至少记录源 Asset/Artifact、准备输入及 recipe（若有）、
Provider/模型身份、参数摘要、Attempt、输出角色和完整输出 ArtifactRef。
用户选择一路或多路并确认目标 Slot；一次确认的所有写入为一个原子 revision。
Preview 与停止不改变 Truth；Pattern 仍引用 Slot，原源和未选 Slot 保留。

自动提出目标的顺序：当前 Bank 的空 Pad 按 Slot 顺序，再访问后续 Bank，
到末尾后回绕到尚未访问的 Bank，每个 Bank 最多一次。已占用、下载中、处理中、
失败占位均不可用。确认时重验；目标发生变化则显示新方案并重新确认。
处理占位是 Workspace 状态；删除处理占位取消其 Job 并释放全部未提交目标，
不会删除已有源 Asset，也不能把其他 Job 的占位释放。失败不自动重试或换 Provider。

不改变既有 quota 的逻辑计费：共享物理 bytes 不意味着多个采纳 Asset 免费。
临时输出的保留、discard/supersede 与回收沿既有 owner 规则；引入回收器须独立 Task。

## 6. 完整验收旅程

| 转换 | far-side 断言 |
| --- | --- |
| 选择/准备 → 请求 | 源与准备 Artifact 身份固定；范围/编辑证据可重读；Truth 不变 |
| 请求 → 执行 | Attempt/Provider/模型身份对应；仅 Artifact 权限；音频播放仍可继续 |
| 执行 → 结果 | 四路完整验证；同内容角色保留；partial/错角色/坏 WAV 均无可采纳结果 |
| 结果 → 试听 → 停止 | 实际播放选定角色或区间；停止无残留；Truth 不变 |
| 标记修改 → 重开候选 | 新 recipe revision 与音频边界一致；原 Attempt 未改写 |
| 确认 → 采纳 | 目标、source 和配额重验；全部成功或全部不写；只改选定 Slot |
| 满位/占位变化 → 拒绝 | 明确提示且无覆盖、无部分写入 |
| 失败/取消 → 重试 | 旧结果可解释；无孤儿进程或半成品采纳；新 Attempt 身份 |
| discard/supersede → 再采纳旧结果 | 旧结果被拒绝；原 Project 不变；按规则释放占位 |
| 保存 → 刷新/关闭 → 重开 | 内容与完整 Lineage 一致；Slot/Pattern 保留；Runtime 重新派生 |

自动化、真机试听、Linux 隔离、浏览器后台/锁屏恢复分别记录；设计通过和
native execute 不代替完整产品验收。Koala 功能目标中的未实现项持续保留。

## Version Management

Version impact: none
Reason: 本文是已确认边界的设计描述，不是 active Contract 或产品实现。
后续 SDK/音频/Project/Host 语义按真实兼容性分配独立版本，不能复用此 none。

## Documentation Impact

Documentation impact: none
Reason: 不修改 Portal 当前实现事实；后续 Tasks 随实际功能更新相关页面和源图。
