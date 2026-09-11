# Creator 新 UI 渐进迁移计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 Creator 的可用功能逐步迁入硬件导向四区布局，先闭合 Sequence 流程，再覆盖全部工作区，最后验证默认切换与旧布局退场。

**Architecture:** 新旧布局复用同一 Runtime session、Application Facade、Project 投影和输入控制器；仅改变呈现和导航。上屏只读，触摸区承载上下文操作；迁移期旧布局仍是同 origin 内的回退呈现，不是第二套产品或第二条数据链路。

**Tech Stack:** 当前 Creator 的 React、TypeScript、CSS、Vitest / Testing Library 和 Playwright；沿用锁定工具链，不为本次规划增加依赖。

**Spec:** [硬件 UI 布局参考](../design/2026-09-11-lmdj-hardware-ui-layout-reference.md)；[Figma 总文件](https://www.figma.com/design/GPFarNiZNsjLQzfG9kR8DO)，以 15 的布局、19–22 的触摸方向为输入。U0 负责把参考转为可实施切片规范，不能把参考图当成完整功能合同。

跟踪：[Umbrella #1207](https://github.com/endaye/lmdj/issues/1207)；视觉设计项目 [#522](https://github.com/endaye/lmdj/issues/522)。
盘点基线：`ed4afbcb5003be9879c52c42fa2f15e1695cc4c5`；日期 2026-09-11。Issue 状态是盘点时观察，开工前必须重新核对。
本次交付仅是计划和任务对齐；不实施 U0–U8 产品改动，不宣称其验收通过。

## Global Constraints

- 整体参考 880 × 592；四区间距与外边距 16。
- 左侧实体控制区 80 × 560；实体小按钮 32 × 32、间距 16；四旋钮占位为 2 × 2。
- 上部显示屏 752 × 176，只显示，不能点击、滑动、拖动波形或调整参数。
- 打击垫区与触摸控制屏均为 368 × 368；16 个 Pad 为 4 × 4、单个 80 × 80。
- 图标视觉主体锚点对齐 Pad 中点，不能只按 SVG 边界框居中。角色图标须来自已有可靠数据；未知类别使用中性图标，不暗中加入自动分类 Provider。
- 上述尺寸是设计单位，不是毫米或设备分辨率；浏览器缩放与真实手指命中区必须另验。
- Project、Sample、Sequence、Perform 的屏幕内容不是四套永久模板。上屏/触摸区随模式、对象、编辑阶段切换；只确认每个即将实施切片所需的上下文。
- Hosts 只通过 Application Facade 使用产品能力；不得解析 Project bundle、修改 Contract 或改变 Project Truth / Runtime Snapshot 权威关系。
- UI 布局偏好不写入 Project Truth。新旧 UI 不同时创建输入订阅、音频上下文或录音管线。
- 不因为 Figma 有 Copy、Save As、Mute/Solo 或 LP/HP/BP 就假定运行时具备它；缺少能力先在原领域任务确认。
- 不借布局迁移解决 #725 的触发入队问题、#536 的 AI 采纳策略或 #961 的跨 origin 工程迁移。
- 每个实施 Task 单独声明文件、最低层测试与验收缺口，独立 worktree、一个可审查 Conventional Commit；不在总任务中一口气重写应用。
- 本计划不授权自动运行后续实现、不授权发布、部署、删除旧站点或浏览器数据；后续实施先满足本阶段的设计与证据前置条件。

## 1. 路径选择与成功定义

选择渐进替换：先同运行时 opt-in 新壳，再完成 Sequence 首条真实流程，然后迁移其余工作区。
一次性替换会把导航重构、生命周期回归和功能遗漏混在一起；独立 demo 能校验外观，却不能证明真实状态与数据安全，因此都不作为主迁移路径。

成功不是“长得像 Figma”，而是旧操作均有可达去处、上屏真正只读、Pad 空间身份稳定、完整操作和恢复路径不丢失，最后可以安全移除旧呈现。
保留旧布局只为过渡回退，不复制业务逻辑，也不永久维护两套 UI。
这不是固定工期承诺；以阶段退出条件而非日期推进。

## 2. 现有功能 → 新布局映射（U0 评审输入）

下表的新入口是迁移提案，不是对开放产品问题的最终裁定。

| 当前源 / 能力 | 新上屏 | 新触摸区 / 实体区 | 不得遗漏的边界 |
| --- | --- | --- | --- |
| `status_bar.tsx`：运行时、音频、MIDI、报告 | 身份、状态、错误摘要 | 触摸区系统/恢复操作；软件设置入口由 U0 确认 | 音频启动必须保留浏览器用户手势；MIDI拒绝、重试和报告不能消失 |
| `mode_rail.tsx`：六个 CreatorMode | 当前上下文名称 | 四个物理模式键；Slice / Sound Sets 拟为触摸子工作区 | 不删六模式能力；返回后选中对象和编辑状态可预期 |
| `pad_surface.tsx`、Bank | 当前 Bank/对象反馈 | 固定 4×4 Pad、ABCD | 触发、选择、释放/取消区分；不重复触发，不改变 #725 未决语义 |
| `sequence_surface.tsx` | 轨道事件、播放/录制、选区、flush反馈 | Pattern选择/创建、Tempo/Swing/Quantize、录制/停止/恢复 | 先沿用现有值域、提交时机与边界；Grid 不冒充 Quantize |
| `project_surface.tsx` | 当前工程、版本投影、加载/失败 | 现有列表、导入、打开及可用操作 | Figma 的 New/Save/Save As 与现有能力逐项核对；不发明数据格式 |
| `sample_surface.tsx` / `waveform_editor.tsx` | 全局波形、选区、格式/配额 | 局部波形、试听、参数、分配、裁切 | 触摸区内完成编辑；长素材与播放头缺口继续追踪 |
| `capture_panel.tsx` / `long_source_editor.tsx` | 采集/准备/失败状态 | 开始/停止、提交、丢弃、重试 | 失焦和真实音频中断后保留 take；可访问对话框不能仅视觉搬移 |
| `candidate_surface.tsx` | Attempt/候选/目标摘要 | Slice候选预览、明确采纳、取消/丢弃 | 预览不写 Project Truth；采纳后持久化与重开验证 |
| `soundset_surface.tsx` | Set/目标Bank/拒绝摘要 | 列表、安装、替换和返回 | Set有声试听仍按 #773/#799 的实际交付能力，不显示假成功 |
| `perform_surface.tsx` / `pattern_launch_strip.tsx` / `fx_slider_bank.tsx` | 当前/排队段落、FX/录音/回放状态 | Launch、HOLD、FX、保存/丢弃、回放/停止/恢复/重采样 | 滤波曲线与实际效果对应；#746 旧poll覆盖终态不能随迁移遗忘 |

## 3. 交付次序与 Issue

本计划细化[四线总计划的 Web Creator 主线](2026-09-11-parallel-product-roadmap.md)：
W1/W2 → U0（映射、状态及稳定切片原型评审）；W3 → U1；W4 → U2–U6；W5 → 各阶段验收及U7；U8是条件化退场。
用户本轮认可先做Sequence闭环，因此该顺序替代四线总计划先Project/Sample的建议，不改变其他三条主线。

| Task | Issue | 交付 | 硬依赖 | 当前可做 |
| --- | --- | --- | --- | --- |
| U0 | [#1214](https://github.com/endaye/lmdj/issues/1214) | U0 确认功能映射、上下文与状态规范 | 无 | 盘点与设计评审 |
| U1 | [#1215](https://github.com/endaye/lmdj/issues/1215) | U1 实现可回退四区外壳与稳定 Pad | U0 | 等待依赖交付 |
| U2 | [#1216](https://github.com/endaye/lmdj/issues/1216) | U2 迁移 Sequence 完整编序流程 | U1、全局 Pattern transport #1230 | 等待依赖交付 |
| U3 | [#1217](https://github.com/endaye/lmdj/issues/1217) | U3 迁移 Project 与全局恢复入口 | U2 | 等待依赖交付 |
| U4 | [#1218](https://github.com/endaye/lmdj/issues/1218) | U4 迁移 Sample、采集与裁切恢复 | U2 | 等待依赖交付 |
| U5 | [#1219](https://github.com/endaye/lmdj/issues/1219) | U5 纳入 Slice 与 Sound Sets 工作区 | U3, U4 | 等待依赖交付 |
| U6 | [#1220](https://github.com/endaye/lmdj/issues/1220) | U6 迁移 Perform、效果与录音回放 | U2 | 等待依赖交付 |
| U7 | [#1221](https://github.com/endaye/lmdj/issues/1221) | U7 完成迁移验收并切换默认布局 | U3, U4, U5, U6 | 等待依赖交付 |
| U8 | [#1222](https://github.com/endaye/lmdj/issues/1222) | U8 按退场条件移除旧布局 | U7 | 等待依赖交付 |

依赖关系：U0 → U1 → U2；U2 之后 U3 / U4 / U6 可按需要排队，U5 等 U3 + U4；U7 等 U3–U6；U8 等 U7 与实际观察结论。
它们并非天然可并行：`app.tsx`、样式、共享状态和门户页必须一次只有一个整合负责人。依赖就绪后优先按 U3、U4、U5、U6 顺序交付；若并行，先确认声明文件无重叠并安排共享文件集成。
U7 是验收与默认策略交付，不是发布任务；U8 的默认切换观察必须来自实际使用证据，合并 U7 本身不启动观察计时。

## 4. 薄呈现接口与状态所有权

现有 `app.tsx` 保持 Runtime / actions 的编排职责；不要为迁移先重构全部状态机。
U1 的新容器只负责布局，建议接口如下，U0 评审确认后由 U1 生产，后续任务消费：

```tsx
import type {ReactNode} from "react";

export interface HardwareConsoleProps {
  physicalControls: ReactNode;
  overview: ReactNode;
  pads: ReactNode;
  touchWorkspace: ReactNode;
}
export function HardwareConsole(props: HardwareConsoleProps) {
  return (
    <div className="hardware-console">
      <aside aria-label="Physical controls">{props.physicalControls}</aside>
      <section aria-label="Overview display">{props.overview}</section>
      <section aria-label="Pad matrix">{props.pads}</section>
      <section aria-label="Touch workspace">{props.touchWorkspace}</section>
    </div>
  );
}
```

这是计划中的接口示意，不是已提交产品代码。Overview 的投影组件只接收读取数据，不接操作回调；容器的 ReactNode 本身不能保证只读，必须检查最终 DOM 与真实事件效果。
触摸组件继续调用当前父组件提供的回调（例如 Sequence 的 `onRecord()`、`onStop()`、`onSwitch(patternId)`、`onSettingsChange(changes)`），不新增第二套调用 Facade 的链路。
所有草稿/焦点状态明确归属：布局切换不可借卸载组件丢弃 take 或候选；若安全保持做不到，明确阻止切换并提供结束/取消入口，不偷偷停止录音。
新旧布局选择器的入口与持久化位置由 U0 确认；仅是 Host 呈现偏好，不改变 origin、项目存储和版本身份。
尚未迁移的模式明确显示“使用现有布局”入口；不得把旧交互页面挤入只读上屏或假装已完成新触摸适配。

## 5. 各 Task 的文件、动作与验收

每个任务开工时先读取本计划、布局参考和其依赖的实际交付。下列新增路径是拟创建文件，现有路径以盘点基线为准。
后续各 Task 的具体控件和测试 fixture 应服从 U0 获批的切片规范；本计划不提前伪造尚未裁定的交互值域。

### U0 — U0 确认功能映射、上下文与状态规范（[#1214](https://github.com/endaye/lmdj/issues/1214)）

**依赖：** 无，可开始盘点；规范须经用户确认。

**交付范围：** 对照当前六个 CreatorMode 和所有可见操作，形成旧入口→新区域→返回/失败/禁用路径表；确认 Sequence 首条流程、Pad 选择与触发分工、四旋钮及录放/方向键上下文、软件设置入口、可访问性与缩放边界。先锁可实施切片，不固定双屏所有未来内容。对齐 #522 的已交付材料和缺项，不宣称历史阶段自动完成。

**Files（拟创建或修改，测试路径已列入）：**

- `docs/superpowers/specs/2026-09-11-creator-hardware-migration-design.md`

**输入 / 输出：** 消费当前代码、Figma参考和已有问题；产出获评审的入口/状态映射、可实施Sequence切片和设计缺口清单。

**操作与最低层验证：**

- [ ] 逐项盘点上节源文件中的所有可达操作，为每项填写原入口、新入口、返回、未提交状态、拒绝与恢复路径。
- [ ] 检查 #522 各阶段的实际材料；记录可复用部分和缺项，提交上述设计规范供用户评审，不自动核销历史阶段。
- [ ] 明确首条 Sequence 切片；用已存在的值域/动作设计，任何语义变化先记录产品决定。确定设备目标、缩放策略、状态非颜色提示、键鼠替代和 reduced-motion。
- [ ] 在设计规范中链接稳定切片的可交互原型与节点清单，补空、加载、失败、禁用和恢复态；观察选择→操作→反馈→取消/返回，并记录真实触摸预验或其明确缺口。布局、焦点与状态方案须用户批准后交给U1；不得跳过原W2以静态画板替代。
- [ ] 对矩阵运行人工完整性检查，所有现有模式与系统操作均有去处；执行 `git diff --check` 和新增路径 ownership 测试。
- [ ] 文件声明与差异检查后提交 `docs(creator): specify hardware UI migration slice`；获批规范是 U1 的入口，提交本身不等于获批。

**远端结果 / 退出条件：** 每个现有操作都有新入口或可用的旧布局回退；启动音频、MIDI、重试、诊断报告均可达；需要产品裁定的变更明确记录，未裁定项不得进入实现。

**复用现有追踪：** [#522](https://github.com/endaye/lmdj/issues/522)、[#725](https://github.com/endaye/lmdj/issues/725)、[#536](https://github.com/endaye/lmdj/issues/536)、[#961](https://github.com/endaye/lmdj/issues/961)；这是相关性/条件依赖，不是自动关闭授权。

### U1 — U1 实现可回退四区外壳与稳定 Pad（[#1215](https://github.com/endaye/lmdj/issues/1215)）

**依赖：** U0。

**交付范围：** 新增 opt-in 四区外壳，默认保留现有布局；同一运行时/状态/输入控制器只有一份。上屏是只读投影，启动/恢复等操作位于触摸区；Pad 保持4×4与Bank空间身份；32/16/80/368设计几何和角色图标视觉锚点落实。不得仅CSS隐藏上屏可交互元素。

**Files（拟创建或修改，测试路径已列入）：**

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/src/components/hardware_console.tsx`
- `apps/creator-web/src/components/overview_display.tsx`
- `apps/creator-web/src/components/physical_controls.tsx`
- `apps/creator-web/src/components/pad_surface.tsx`
- `apps/creator-web/test/hardware_console.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/creator-web/test/input_controller.test.ts`
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`

**输入 / 输出：** 消费U0规范与现有Workspace状态/actions；产出上节四插槽HardwareConsole及可回退的唯一Runtime呈现。

**操作与最低层验证：**

- [ ] 先在上述最低层测试文件中增加一条针对本阶段缺口的失败断言；每条断言只锁一个事实，浏览器几何不以 jsdom 冒充。
- [ ] 运行 `npm --prefix apps/creator-web test -- --run test/hardware_console.test.tsx test/workspace_shell.test.tsx test/input_controller.test.ts`，确认失败源于新增行为尚未实现，而非缺少工具链/fixture。
- [ ] 在声明组件内接入现有状态和回调，完成本节交付范围；保留既有失败、取消、恢复处理，不改 runtime 或输入队列规则来让 UI 测试通过。
- [ ] 重跑同一命令至通过，再执行声明的打包浏览器旅程；完整验证入口与执行边界见第 7 节。
- [ ] 更新 `/hosts/creator-web/` 的实际实现/迁移状态；运行门户检查和路径 ownership 检查后，以一个 `feat(creator): u1 hardware UI migration` 提交交付。U7/U8 未满足实际验收条件时停在证据缺口，不进行默认切换/删除。

**远端结果 / 退出条件：** 切换布局不创建第二AudioContext/session，不重置Project或写入Project Truth；未迁移工作区有明确旧布局入口。上屏无可聚焦操作，Pad取消/释放/键盘/MIDI既有断言保留；200%缩放/小视口有可达路径。

**复用现有追踪：** [#725](https://github.com/endaye/lmdj/issues/725)、[#741](https://github.com/endaye/lmdj/issues/741)、[#742](https://github.com/endaye/lmdj/issues/742)；这是相关性/条件依赖，不是自动关闭授权。

### U2 — U2 迁移 Sequence 完整编序流程（[#1216](https://github.com/endaye/lmdj/issues/1216)）

**依赖：** U1，以及 [#1230](https://github.com/endaye/lmdj/issues/1230) 的全局 Pattern transport。

2026-09-12 更新：用户已确认独立 Play/Stop、Record 两键的关联状态表；停止后启动从当前 Pattern 开头开始，无预备拍；播放中开关 Record 不重置播放。Record 写入当前 Pattern 的 Pad 操作，不是 Sample 采集或 Performance 音频录制。按[获批架构方案](../superpowers/specs/2026-09-11-global-pattern-transport-design.md)实施；首个独立子系统见[音频基础实施计划](../superpowers/plans/2026-09-12-pattern-transport-audio.md)。其后仍需持久化暂存、Facade 协调、运行时接口和 Creator 接入，不能把现有 `stopSequence` 当作播放停止，也不能以完成音频基础代替 U2 全流程验收。U0–U8 原有范围及退出条件不变。

**交付范围：** 首个完整新UI切片：上屏轨道/进度只读，触摸区编辑现有Tempo/Swing/Quantize、Pattern选择与创建；录制、叠录、切换、停止、持久化和恢复复用既有actions。新视觉控件不得改变当前提交时机、参数范围或flush边界；图中Copy等未核实能力不作为已实现。

**Files（拟创建或修改，测试路径已列入）：**

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/sequence_surface.tsx`
- `apps/creator-web/src/components/sequence_transport.tsx`
- `apps/creator-web/src/components/sequence_overview.tsx`
- `apps/creator-web/src/components/sequence_touch_workspace.tsx`
- `apps/creator-web/test/sequence_surface.test.tsx`
- `apps/creator-web/test/sequence_actions.test.ts`
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`

**输入 / 输出：** 消费已交付四区容器、U0映射及当前组件回调；产出本阶段可复用只读投影和触摸工作区，不新增领域Contract。

**操作与最低层验证：**

- [ ] 先在上述最低层测试文件中增加一条针对本阶段缺口的失败断言；每条断言只锁一个事实，浏览器几何不以 jsdom 冒充。
- [ ] 运行 `npm --prefix apps/creator-web test -- --run test/sequence_surface.test.tsx test/sequence_actions.test.ts`，确认失败源于新增行为尚未实现，而非缺少工具链/fixture。
- [ ] 在声明组件内接入现有状态和回调，完成本节交付范围；保留既有失败、取消、恢复处理，不改 runtime 或输入队列规则来让 UI 测试通过。
- [ ] 重跑同一命令至通过，再执行声明的打包浏览器旅程；完整验证入口与执行边界见第 7 节。
- [ ] 更新 `/hosts/creator-web/` 的实际实现/迁移状态；运行门户检查和路径 ownership 检查后，以一个 `feat(creator): u2 hardware UI migration` 提交交付。U7/U8 未满足实际验收条件时停在证据缺口，不进行默认切换/删除。

**远端结果 / 退出条件：** 打开含素材Project→录制→叠录→切Pattern→停止/flush→重开逐腿有远端状态断言；恢复候选应用/丢弃/失败重试可达；上屏无需点击，Bank/模式切换保持Pad空间身份。

**复用现有追踪：** [#360](https://github.com/endaye/lmdj/issues/360)、[#362](https://github.com/endaye/lmdj/issues/362)、[#363](https://github.com/endaye/lmdj/issues/363)、[#364](https://github.com/endaye/lmdj/issues/364)、[#365](https://github.com/endaye/lmdj/issues/365)、[#366](https://github.com/endaye/lmdj/issues/366)；这是相关性/条件依赖，不是自动关闭授权。

### U3 — U3 迁移 Project 与全局恢复入口（[#1217](https://github.com/endaye/lmdj/issues/1217)）

**依赖：** U2。

**交付范围：** 迁移已实现Project列表/导入/打开流程以及音频启动、MIDI授权、诊断与恢复。只读上屏显示身份、加载、失败和运行时状态。新建/Save As/完整工程导出若现有Host不支持，显式缺口而非假按钮或悄悄新增Contract。

**Files（拟创建或修改，测试路径已列入）：**

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/project_surface.tsx`
- `apps/creator-web/src/components/status_bar.tsx`
- `apps/creator-web/src/components/error_panel.tsx`
- `apps/creator-web/src/components/project_touch_workspace.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/creator-web/test/project_actions.test.ts`
- `apps/creator-web/test/audio_lifecycle.test.tsx`
- `tests/platform/web/creator/creator_web_browser.spec.mjs`
- `tests/platform/web/creator/creator_web_lifecycle.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`

**输入 / 输出：** 消费已交付四区容器、U0映射及当前组件回调；产出本阶段可复用只读投影和触摸工作区，不新增领域Contract。

**操作与最低层验证：**

- [ ] 先在上述最低层测试文件中增加一条针对本阶段缺口的失败断言；每条断言只锁一个事实，浏览器几何不以 jsdom 冒充。
- [ ] 运行 `npm --prefix apps/creator-web test -- --run test/workspace_shell.test.tsx test/project_actions.test.ts test/audio_lifecycle.test.tsx`，确认失败源于新增行为尚未实现，而非缺少工具链/fixture。
- [ ] 在声明组件内接入现有状态和回调，完成本节交付范围；保留既有失败、取消、恢复处理，不改 runtime 或输入队列规则来让 UI 测试通过。
- [ ] 重跑同一命令至通过，再执行声明的打包浏览器旅程；完整验证入口与执行边界见第 7 节。
- [ ] 更新 `/hosts/creator-web/` 的实际实现/迁移状态；运行门户检查和路径 ownership 检查后，以一个 `feat(creator): u3 hardware UI migration` 提交交付。U7/U8 未满足实际验收条件时停在证据缺口，不进行默认切换/删除。

**远端结果 / 退出条件：** 选择与实际打开的状态区分；导入/打开失败保留当前工程；音频拒绝/恢复/MIDI拒绝有可操作出口；同origin切换新旧UI保留编辑后工程，跨origin迁移仍归#961。

**复用现有追踪：** [#915](https://github.com/endaye/lmdj/issues/915)、[#961](https://github.com/endaye/lmdj/issues/961)、[#741](https://github.com/endaye/lmdj/issues/741)、[#992](https://github.com/endaye/lmdj/issues/992)；这是相关性/条件依赖，不是自动关闭授权。

### U4 — U4 迁移 Sample、采集与裁切恢复（[#1218](https://github.com/endaye/lmdj/issues/1218)）

**依赖：** U2。

**交付范围：** 上屏全局波形只读，触摸区局部波形/裁切/试听/分配与采集操作；长素材及配额路径不丢。迁移现有提交、取消和恢复语义，保留可访问对话框；不得借UI改版重写采集生命周期。

**Files（拟创建或修改，测试路径已列入）：**

- `apps/creator-web/src/components/sample_surface.tsx`
- `apps/creator-web/src/components/sample_controls.tsx`
- `apps/creator-web/src/components/waveform_editor.tsx`
- `apps/creator-web/src/components/capture_panel.tsx`
- `apps/creator-web/src/components/long_source_editor.tsx`
- `apps/creator-web/test/sample_controls.test.tsx`
- `apps/creator-web/test/waveform_editor.test.tsx`
- `apps/creator-web/test/capture_panel.test.tsx`
- `tests/platform/web/creator/creator_web_capture.spec.mjs`
- `tests/platform/web/creator/creator_web_sample_editor.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`

**输入 / 输出：** 消费已交付四区容器、U0映射及当前组件回调；产出本阶段可复用只读投影和触摸工作区，不新增领域Contract。

**操作与最低层验证：**

- [ ] 先在上述最低层测试文件中增加一条针对本阶段缺口的失败断言；每条断言只锁一个事实，浏览器几何不以 jsdom 冒充。
- [ ] 运行 `npm --prefix apps/creator-web test -- --run test/sample_controls.test.tsx test/waveform_editor.test.tsx test/capture_panel.test.tsx`，确认失败源于新增行为尚未实现，而非缺少工具链/fixture。
- [ ] 在声明组件内接入现有状态和回调，完成本节交付范围；保留既有失败、取消、恢复处理，不改 runtime 或输入队列规则来让 UI 测试通过。
- [ ] 重跑同一命令至通过，再执行声明的打包浏览器旅程；完整验证入口与执行边界见第 7 节。
- [ ] 更新 `/hosts/creator-web/` 的实际实现/迁移状态；运行门户检查和路径 ownership 检查后，以一个 `feat(creator): u4 hardware UI migration` 提交交付。U7/U8 未满足实际验收条件时停在证据缺口，不进行默认切换/删除。

**远端结果 / 退出条件：** 导入或采集→试听→裁切→提交/丢弃→重开逐腿验证；权限拒绝/配额不足/失焦/音频中断后未提交take、重试和丢弃可达。旧缺陷保留身份并在相关新UI路径重验。

**复用现有追踪：** [#625](https://github.com/endaye/lmdj/issues/625)、[#605](https://github.com/endaye/lmdj/issues/605)、[#741](https://github.com/endaye/lmdj/issues/741)、[#742](https://github.com/endaye/lmdj/issues/742)、[#341](https://github.com/endaye/lmdj/issues/341)、[#359](https://github.com/endaye/lmdj/issues/359)、[#242](https://github.com/endaye/lmdj/issues/242)、[#244](https://github.com/endaye/lmdj/issues/244)、[#246](https://github.com/endaye/lmdj/issues/246)；这是相关性/条件依赖，不是自动关闭授权。

### U5 — U5 纳入 Slice 与 Sound Sets 工作区（[#1219](https://github.com/endaye/lmdj/issues/1219)）

**依赖：** U3、U4。

**交付范围：** 按U0映射将两类已有工作区放入触摸导航/子工作区，保留返回父上下文和状态；不为硬件左栏擅自增键。候选预览不改Project Truth，只有明确采纳才写入；保留取消/丢弃/失败以及Sound Set安装/拒绝。

**Files（拟创建或修改，测试路径已列入）：**

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/components/mode_rail.tsx`
- `apps/creator-web/src/components/candidate_surface.tsx`
- `apps/creator-web/src/components/soundset_surface.tsx`
- `apps/creator-web/test/candidate_surface.test.tsx`
- `apps/creator-web/test/soundset_surface.test.tsx`
- `tests/platform/web/creator/creator_web_candidate.spec.mjs`
- `tests/platform/web/creator/creator_web_candidate_runtime.spec.mjs`
- `tests/platform/web/creator/creator_web_soundset.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`

**输入 / 输出：** 消费已交付四区容器、U0映射及当前组件回调；产出本阶段可复用只读投影和触摸工作区，不新增领域Contract。

**操作与最低层验证：**

- [ ] 先在上述最低层测试文件中增加一条针对本阶段缺口的失败断言；每条断言只锁一个事实，浏览器几何不以 jsdom 冒充。
- [ ] 运行 `npm --prefix apps/creator-web test -- --run test/candidate_surface.test.tsx test/soundset_surface.test.tsx`，确认失败源于新增行为尚未实现，而非缺少工具链/fixture。
- [ ] 在声明组件内接入现有状态和回调，完成本节交付范围；保留既有失败、取消、恢复处理，不改 runtime 或输入队列规则来让 UI 测试通过。
- [ ] 重跑同一命令至通过，再执行声明的打包浏览器旅程；完整验证入口与执行边界见第 7 节。
- [ ] 更新 `/hosts/creator-web/` 的实际实现/迁移状态；运行门户检查和路径 ownership 检查后，以一个 `feat(creator): u5 hardware UI migration` 提交交付。U7/U8 未满足实际验收条件时停在证据缺口，不进行默认切换/删除。

**远端结果 / 退出条件：** Slice导入→候选→预览→明确采纳或取消/丢弃→重开验证；Sound Set列表/安装/拒绝/返回可达。#773/#799未满足时不可宣称Set有声试听已完成，#1167的听感验收不可用截图替代。

**复用现有追踪：** [#773](https://github.com/endaye/lmdj/issues/773)、[#799](https://github.com/endaye/lmdj/issues/799)、[#994](https://github.com/endaye/lmdj/issues/994)、[#1163](https://github.com/endaye/lmdj/issues/1163)、[#1167](https://github.com/endaye/lmdj/issues/1167)、[#536](https://github.com/endaye/lmdj/issues/536)；这是相关性/条件依赖，不是自动关闭授权。

### U6 — U6 迁移 Perform、效果与录音回放（[#1220](https://github.com/endaye/lmdj/issues/1220)）

**依赖：** U2。

**交付范围：** 迁移Launch/HOLD/既有FX、录音/停止/保存/丢弃、WAV输出、回放/停止/恢复/重采样。上屏反映已确认状态，触摸区操作。Figma LP/HP/BP只映射运行时已支持并经确认的类型、单位和值域，不以静态曲线虚构DSP能力或改变排队语义。

**Files（拟创建或修改，测试路径已列入）：**

- `apps/creator-web/src/components/perform_surface.tsx`
- `apps/creator-web/src/components/pattern_launch_strip.tsx`
- `apps/creator-web/src/components/fx_slider_bank.tsx`
- `apps/creator-web/src/components/filter_response.tsx`
- `apps/creator-web/test/perform_surface.test.tsx`
- `apps/creator-web/test/filter_response.test.tsx`
- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `apps/docs-site/docs/hosts/creator-web.mdx`

**输入 / 输出：** 消费已交付四区容器、U0映射及当前组件回调；产出本阶段可复用只读投影和触摸工作区，不新增领域Contract。

**操作与最低层验证：**

- [ ] 先在上述最低层测试文件中增加一条针对本阶段缺口的失败断言；每条断言只锁一个事实，浏览器几何不以 jsdom 冒充。
- [ ] 运行 `npm --prefix apps/creator-web test -- --run test/perform_surface.test.tsx test/filter_response.test.tsx`，确认失败源于新增行为尚未实现，而非缺少工具链/fixture。
- [ ] 在声明组件内接入现有状态和回调，完成本节交付范围；保留既有失败、取消、恢复处理，不改 runtime 或输入队列规则来让 UI 测试通过。
- [ ] 重跑同一命令至通过，再执行声明的打包浏览器旅程；完整验证入口与执行边界见第 7 节。
- [ ] 更新 `/hosts/creator-web/` 的实际实现/迁移状态；运行门户检查和路径 ownership 检查后，以一个 `feat(creator): u6 hardware UI migration` 提交交付。U7/U8 未满足实际验收条件时停在证据缺口，不进行默认切换/删除。

**远端结果 / 退出条件：** 演奏/FX手势结束释放→录制→停止→保存→回放→停止后不被旧poll覆盖；中断恢复、失败重试/丢弃均验证；曲线类型/值/目标与runtime一致，未支持类型不显示可执行控件。

**复用现有追踪：** [#746](https://github.com/endaye/lmdj/issues/746)、[#721](https://github.com/endaye/lmdj/issues/721)、[#716](https://github.com/endaye/lmdj/issues/716)、[#717](https://github.com/endaye/lmdj/issues/717)、[#718](https://github.com/endaye/lmdj/issues/718)、[#719](https://github.com/endaye/lmdj/issues/719)、[#720](https://github.com/endaye/lmdj/issues/720)；这是相关性/条件依赖，不是自动关闭授权。

### U7 — U7 完成迁移验收并切换默认布局（[#1221](https://github.com/endaye/lmdj/issues/1221)）

**依赖：** U3、U4、U5、U6。

**交付范围：** 完成六工作区功能覆盖对照、真实设备/键鼠/触摸/辅助技术验收、同origin回退演练；满足证据后才将新布局设为默认，仍保留旧布局回退。复用已有设备验收Issue，针对新UI补当前精确候选证据，不批量关闭历史任务。

**Files（拟创建或修改，测试路径已列入）：**

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `tests/platform/web/creator/creator_web_hardware_layout.spec.mjs`
- `tests/platform/web/creator/creator_web_accessibility.spec.mjs`
- `docs/quality/2026-09-11-creator-ui-migration-acceptance.md`
- `apps/docs-site/docs/hosts/creator-web.mdx`

**输入 / 输出：** 消费已交付四区容器、U0映射及当前组件回调；产出本阶段验收记录与默认布局选择，不新增领域Contract。

**操作与最低层验证：**

- [ ] 先在上述最低层测试文件中增加一条针对本阶段缺口的失败断言；每条断言只锁一个事实，浏览器几何不以 jsdom 冒充。
- [ ] 运行 `npm --prefix apps/creator-web test -- --run test/workspace_shell.test.tsx`，确认失败源于新增行为尚未实现，而非缺少工具链/fixture。
- [ ] 在声明组件内接入现有状态和回调，完成本节交付范围；保留既有失败、取消、恢复处理，不改 runtime 或输入队列规则来让 UI 测试通过。
- [ ] 重跑同一命令至通过，再执行声明的打包浏览器旅程；完整验证入口与执行边界见第 7 节。
- [ ] 更新 `/hosts/creator-web/` 的实际实现/迁移状态；运行门户检查和路径 ownership 检查后，以一个 `feat(creator): u7 hardware UI migration` 提交交付。U7/U8 未满足实际验收条件时停在证据缺口，不进行默认切换/删除。

**远端结果 / 退出条件：** 完整creator proof及本次新增旅程通过；相关真实设备任务有适用候选证据；无不可达关键功能/不可恢复编辑丢失/假成功。失败则保持opt-in，不降低测试或以UI切换代表发布。

**复用现有追踪：** [#248](https://github.com/endaye/lmdj/issues/248)、[#249](https://github.com/endaye/lmdj/issues/249)、[#251](https://github.com/endaye/lmdj/issues/251)、[#243](https://github.com/endaye/lmdj/issues/243)、[#250](https://github.com/endaye/lmdj/issues/250)、[#360](https://github.com/endaye/lmdj/issues/360)、[#721](https://github.com/endaye/lmdj/issues/721)、[#1167](https://github.com/endaye/lmdj/issues/1167)、[#961](https://github.com/endaye/lmdj/issues/961)；这是相关性/条件依赖，不是自动关闭授权。

### U8 — U8 按退场条件移除旧布局（[#1222](https://github.com/endaye/lmdj/issues/1222)）

**依赖：** U7。

**交付范围：** U7实际默认版本完成用户认可的观察周期、无迁移阻断且回退记录齐备后，列出精确旧布局专用符号/文件清单再删除。仅移除旧呈现分支/专用样式，不删除复用业务组件、runtime、数据或回归测试。

**Files（拟创建或修改，测试路径已列入）：**

- `apps/creator-web/src/app.tsx`
- `apps/creator-web/src/styles.css`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `docs/quality/2026-09-11-creator-ui-migration-acceptance.md`
- `apps/docs-site/docs/hosts/creator-web.mdx`

**输入 / 输出：** 消费已交付四区容器、U0映射及当前组件回调；产出本阶段经过保留性验证的新UI单一路径，不新增领域Contract。

**操作与最低层验证：**

- [ ] 先在上述最低层测试文件中增加一条针对本阶段缺口的失败断言；每条断言只锁一个事实，浏览器几何不以 jsdom 冒充。
- [ ] 运行 `npm --prefix apps/creator-web test -- --run test/workspace_shell.test.tsx`，确认失败源于新增行为尚未实现，而非缺少工具链/fixture。
- [ ] 在声明组件内接入现有状态和回调，完成本节交付范围；保留既有失败、取消、恢复处理，不改 runtime 或输入队列规则来让 UI 测试通过。
- [ ] 重跑同一命令至通过，再执行声明的打包浏览器旅程；完整验证入口与执行边界见第 7 节。
- [ ] 更新 `/hosts/creator-web/` 的实际实现/迁移状态；运行门户检查和路径 ownership 检查后，以一个 `refactor(creator): u8 hardware UI migration` 提交交付。U7/U8 未满足实际验收条件时停在证据缺口，不进行默认切换/删除。

**远端结果 / 退出条件：** 逐项证明旧专用代码无消费者，新布局全流程及持久化重开通过，保留故障恢复入口。代码退场不授权删部署、origin存储、远端分支或历史记录；出现回退需求重新打开迁移评估。

**复用现有追踪：** [#1207](https://github.com/endaye/lmdj/issues/1207)；这是相关性/条件依赖，不是自动关闭授权。

## 6. 既有 Issue 的复用与阻塞边界

- **设计母项：** #522 保留视觉语言完整阶段；#1207 管此次硬件迁移；本计划不另建第三个 Umbrella。
- **输入：** #725 仍是产品并发问题。保持现有行为的布局工作不需先裁定；若 U0 想改变按压/释放/选择语义，则相应实现等待明确决定。
- **Sample/生命周期：** #625、#605、#741、#742 先查现有代码和复现证据。开放状态不直接等于当前代码仍有缺陷；新UI出现同一症状复用原Issue，实际阻断该旅程就阻止该旅程验收。
- **Project：** #915、#992 保留合同/导入覆盖；#961 是跨 origin 完整工程导出/导入设计，不作为同 origin 换壳的普遍前置条件。不得以旧站点回滚，因为旧托管已被删除。
- **Sound Set：** #773/#799 承接有声试听能力，#994 承接golden-audio证据。U5可迁移已实现列表/安装，不得在缺少能力时宣称全套试听体验完成。
- **Slice：** #1163/#1167 延续固定候选与Windows实际操作/听感验收；新的图标类别不隐式纳入 #1189 自动标签 Provider。
- **Perform：** #746 按现有状态竞态证据处理；#721及#716–#720承接真实录音/回放/设备路径，U6不吞并DSP或生命周期缺陷修复。
- **跨页人工验收：** #248/#249/#251、#243、#360及其#362–#366、#721与#1167作为原追踪入口；U7记录新UI精确候选与覆盖范围，不为同一设备动作再建一批重复任务。
- 不要求把全仓库所有开放缺陷清零才开始迁移。默认切换前，对本次支持范围内每个剩余缺口记录严重度、用户影响、退出/回退路径与获批处置；数据丢失、无法停止声音/录音、恢复死路、关键入口缺失不能靠“已记录”消除。

## 7. 验证分层与远端断言

“远端”指操作发生之后的真实结果，不是网络远程：点击之后必须确认状态/数据/声音预期，而非只断言按钮收到点击。

### 最低层

U1 容器测试的具体断言示例：

```tsx
import {render, screen, within} from "@testing-library/react";
import {expect, test} from "vitest";
import {HardwareConsole} from "../src/components/hardware_console";

test("overview contains no action while touch workspace remains actionable", () => {
  render(<HardwareConsole
    physicalControls={<button>Play</button>}
    overview={<output>Stopped</output>}
    pads={<button>Pad A01</button>}
    touchWorkspace={<button>Activate audio</button>}
  />);
  const display = screen.getByRole("region", {name: "Overview display"});
  expect(within(display).queryAllByRole("button")).toHaveLength(0);
  expect(within(screen.getByRole("region", {name: "Touch workspace"}))
    .getByRole("button", {name: "Activate audio"})).toBeDefined();
});
```

该例只覆盖结构事实，不足以证明真实页面只读。U1还须对实际Workspace投影检查所有交互元素、Tab路径、指针/拖动对state的影响，并在浏览器以bounding box验证32/16/80/368和四区位置。
U2–U6每个回调的拒绝、失败、旧响应及返回路径沿用原测试fixture；不能通过删旧测试/放宽断言来通过迁移。

### 完整旅程（每条记录逐腿结果）

| 阶段 | 输入与连续动作 | 最后结果与异常分支 |
| --- | --- | --- |
| U1 | 同工程旧→新→旧、切Bank/模式、键鼠/MIDI按下→释放/取消 | 工程身份/修改保留、只有一个session和输入处理器、Pad地址不漂移、不遗留声音 |
| U2 | 有素材工程→录制→叠录→切Pattern→停止/flush→重开 | 各Pattern事件与目标槽位正确；崩溃/恢复应用、恢复失败再试、丢弃均有结果 |
| U3 | 导入→打开→编辑→同origin换壳→重开 | 编辑后的完整真值保持；失败导入不损坏当前工程，权限拒绝与系统恢复可达 |
| U4 | 导入/真实采集→试听→裁切→提交或丢弃→重开 | 资产完整身份/字节长度与范围正确；中断后take保留，恢复/重试/丢弃均可达 |
| U5 | 候选→预览→取消/明确采纳→重开；Set列表→安装→返回 | 预览不改真值，采纳后目标Pad正确；能力拒绝可见，缺少有声试听不冒充成功 |
| U6 | Launch/FX/HOLD→录制→停止→保存→回放→停止；中断→恢复 | 排队与确认反馈一致；终态不被旧poll覆盖；WAV/录音重开和丢弃正确 |
| U7/U8 | 六工作区完整流程→切默认→实际观察→回退演练→退场 | 无功能遗漏与数据损失；新候选证据可追溯，旧UI专用代码才可移除 |

### 稳定执行入口

```bash
scripts/creator-web.sh test
scripts/creator-web.sh proof
scripts/docs-site.sh check
python3 tests/build/ci_change_scope_test.py
git diff --check
```

- `test`是局部反馈，不包含完整打包浏览器旅程；`proof`需锁定Node/Emscripten/Playwright、真实fixtures和干净已提交源树，按Creator README执行。
- 各Task先跑其最低层测试，再按影响跑打包旅程。U7汇总完整Creator proof及新增旅程；若新增浏览器文件未被当前proof发现，Task须显式声明并修改实际测试发现入口，不能只创建未执行的文件。
- 原始的真实触摸/录音/MIDI/屏幕阅读器任务保留独立证据；synthetic blur不能证明AudioContext真实中断，自动音频fixture不能证明听感。
- 不为本计划增加全仓库合并门槛，不降低覆盖率/超时/验收腿；临时环境缺工具报告未执行，不计通过。
- 每个新增路径在stage后跑ownership；每个新门禁必须说明它捕获的具体缺陷，否则作为建议检查。
- 受控软件验收与真实硬件面板采购规格分开；32设计单位按钮不能直接当作足够大的物理触摸目标。

## 8. 默认切换、回退与退场

U7 前始终保留旧默认；U1 的可选新壳只用于开发/验证，不等于发布到用户。
默认切换需要：U0映射所有现有操作有去处；U2–U6流程证据满足；支持设备范围与实际验收明确；无上述不可接受回归；同origin回退经验证。
回退不切旧域名、不重新导入原始素材代替编辑后的Project、不清IndexedDB/OPFS、不创建新Runtime。
U8前由用户根据实际候选使用记录确认观察充分与旧UI无必要用途；无预设“过几天自动删”。
代码合并、候选分配、发布、部署、默认对真实用户生效是不同事实，分别记录；不把merged当deployed。
U8删除前逐符号证明无消费者，精确清单随PR，不批量删整个components目录。保留仍用的组件及所有有效回归覆盖。

## Version Management

Version impact: none — 本次仅新增规划并更新任务入口，不改产品代码、Host/Module/Provider/Contract清单、不分配Product Build。

U0仍是文档设计任务。U1–U8实施时依[版本策略](../governance/version-management.md)评估Creator Host SemVer与兼容性；团队测试或发布分配Product Build走正式流程，不能把“UI改动”一律视为版本无影响。
不预填下一个版本号；版本身份从active manifests读取。若发生Product Build/Assembly变化，同一任务必须声明并履行门户/快照义务；发布另外授权。

## Documentation Impact

Documentation impact: none — 本次规划与两个工作台账在docs目录，不改当前架构门户或已实现行为。

U1–U8实施预期 Documentation impact: required，Affected portal pages: /hosts/creator-web/。
按具体实现更新 `apps/docs-site/docs/hosts/creator-web.mdx`，需要变更测试说明时追加 `/operations/testing-and-proof/`；不得修改旧快照来让新实现看起来早已上线。
U0若作出影响当前产品事实的决定，重新评估门户影响。本计划不是#522已批准最终设计的替代物。

## 本次规划 Task 的验证与边界

声明文件：本计划、`docs/plans/2026-09-11-parallel-product-roadmap.md`、`docs/quality/2026-08-17-machine-task-todo.md`、`docs/quality/2026-08-17-manual-verification-todo.md`。
检查：现有路径与新增路径标注、Issue/依赖回读、尺寸与设计一致性、stage后的ownership、docs_static及PR正文声明检查。
本轮不运行产品交互验收，不执行U0–U8，不改变Figma，不以规划Issue的创建/关联标记实现已完成。
