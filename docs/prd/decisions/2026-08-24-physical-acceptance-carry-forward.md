# 已确认：物理/人工验收通过的跨 Product Build 结转规则（P1）

- 日期：2026-08-24
- 来源：GitHub Issue [#236](https://github.com/endaye/lmdj/issues/236)；
  Human TODO 决策项 P1（[2026-08-17-manual-verification-todo.md](../../quality/2026-08-17-manual-verification-todo.md)）。
- 结论：一次物理/人工验收通过只对它记录的确切身份有效。跨 Product Build
  结转只允许走显式记录的未变树推导；trigger 树有变更时默认在被测 Build 上
  重跑，唯一例外是人审签的逐 commit 豁免推导。历史证据永远标注其原始
  Build，绝不重述为当前 Build 结论。
- 原因：物理行是唯一能看见 silence、clipping、channel swap、sample-rate
  错误和实体输入失效的门（Chromium 假设备对这些结构性不可见）。没有书面
  失效规则时，历史通过会被静默当成当前结论，未验证假设随每个 Build 累积。
  身份绑定加树级推导用最低的行政成本让每条"已验收"声明可审计；行为性变更
  的分类不是机械判断，所以豁免推导保留给人审，而不是放宽默认规则。
- 影响：Human TODO 的 P1 决策项结清，"Any new Product Build" 重跑触发行
  有了答案；M2 无可结转（它从未通过），M6 确认为重跑行；四个历史通过
  （`1.0.11.0`、`1.0.20.0`、`1.0.21.0`、`1.0.23.0`）维持各自 Build 的有效
  证据。本规则不授权任何 tag、Release、部署或 Channel promotion，Human
  TODO 的 Deferral boundary 不变。P1 只存在于 Human TODO，`docs/prd/questions/`
  下无对应问题文件需要删除。

## 通过绑定的最小身份

一次物理/人工验收通过至少绑定以下身份，缺一不可：

1. **Product Build**：`MILESTONE.MINOR.BUILD.PATCH` 全四段，加 Channel。
2. **Host/Module 版本**：被测表面涉及的 Module SemVer（如 `creator-web`、
   `web-runtime-host`）与 Assembly Lock SHA-256。
3. **实现修订**：被测产物构建自的确切 git commit。
4. **平台/浏览器/设备类别**：OS 及版本、浏览器及版本、输入设备类别（如
   实体 MIDI controller、内置/有线麦克风）、输出类别（内置或有线；
   Bluetooth 只作信息记录，永不替代）。
5. **证据哈希**：每份导出报告/证据文件的 SHA-256。

通过只对这一身份声明有效。对任何其他 Build 的声明只有两条合法路径：
身份精确匹配的通过，或按下文记录的结转/豁免推导。

## 失效触发类

以下任一类变更发生在通过修订与目标修订之间，该行即失效，需重跑：

- **音频路径**：渲染引擎、AudioWorklet、capture 管线、采样准备/PCM、
  输出路由。
- **输入映射**：MIDI/Pointer/Keyboard 的 admission、映射、channel/note
  处理。
- **生命周期**：Session、AudioContext、后台/前台/锁屏、suspend/resume、
  恢复。
- **打包/CSP**：分发打包、CSP、内容哈希资产、Service Worker/manifest、
  serving 层。
- **Project/Runtime 行为**：该行 journey 实际经过的 Project Truth
  Contract、Runtime Snapshot、Facade 命令语义。
- **相关依赖变更**：进入交付产物或其构建工具链的依赖升级（如 emsdk、
  运行时依赖、Creator/Web 平台锁定依赖）。纯测试或文档工具的变更不算。

## 命名表面（affected surfaces/modules）

Web/Creator 行的 trigger 树按以下命名表面取并集：

| 表面 | 树 |
| --- | --- |
| `audio-path` | `packages/audio-runtime/`、`packages/project-cooker/`、`apps/web-runtime-host/src/` |
| `capture` | `apps/creator-web/src/capture/`、`apps/creator-web/src/components/capture_panel.tsx`、`apps/creator-web/src/state/capture_state.ts` |
| `input` | `packages/web-runtime-platform/web/input_adapters.mjs`、`apps/creator-web/src/runtime/input_controller.ts` |
| `lifecycle` | `packages/web-runtime-platform/web/runtime_session.mjs`、`packages/web-runtime-platform/web/protocol.mjs`、`packages/web-runtime-platform/web/state_machine.mjs`、`apps/creator-web/src/runtime/runtime_context.tsx` |
| `packaging-csp` | `apps/web-runtime-host/deploy/`、`apps/web-runtime-host/tools/`、`apps/web-runtime-host/index.html`、`tools/web-runtime/` |
| `project-runtime` | `contracts/`、`packages/authoring-domain/`、`packages/application-facade/`、`packages/project-io/` |
| `surface-ui` | `apps/creator-web/src/components/`、`apps/creator-web/src/styles.css` |
| `dependencies` | `tools/web-runtime/emscripten.lock.json`、`apps/creator-web/package-lock.json` 及进入交付产物或构建工具链的同类锁定文件 |

各行的 trigger 集合：

| 行 | trigger 集合 |
| --- | --- |
| L1–L5（lab） | `apps/web-runtime-lab/` 自身 + `audio-path` + `input` + `lifecycle` + `packaging-csp` + `project-runtime` + `dependencies` |
| M1（capture → commit → 回放） | `capture` + `surface-ui` + `audio-path` + `packaging-csp` + `project-runtime` + `dependencies` |
| M2（听感与主观音质） | `audio-path` + `capture` + `surface-ui` + `project-runtime` + `dependencies` |
| M3（Pointer 输入） | `input` + `audio-path` + `dependencies` |
| M5（外置声卡输入） | `capture` + `audio-path` + `dependencies` |
| M6（实体 MIDI controller） | `input` + `lifecycle` + `audio-path` + `packaging-csp` + `dependencies` |
| M7（Safari capture 行为） | `capture` + `audio-path` + `packaging-csp` + `dependencies` |
| M8（Safari Pointer + 听感） | `input` + `audio-path` + `dependencies` |
| M9（iPadOS capture） | `capture` + `audio-path` + `packaging-csp` + `dependencies` |
| M10（触屏人体工学） | `input` + `surface-ui` + `dependencies` |
| M11（后台/锁屏/恢复生命周期） | `lifecycle` + `audio-path` + `dependencies` |
| Native Host 七步物理门 | `apps/native-test-host/` + `audio-path` + `project-runtime` + `dependencies`（native 工具链） |
| Keyboard canary | `input` + `audio-path` + `dependencies` |
| MIDI canary | `input` + `lifecycle` + `audio-path` + `dependencies` |

新物理行在加入 Human TODO 时声明自己的 trigger 集合；表中没有的表面变更
（如 `docs/`、纯 CI、其他 app）不使任何行失效。

## 未变树结转与其推导记录

仅当通过修订与目标修订之间、该行全部 trigger 树的 `git diff` 为空时，
通过可结转到后续 Build。结转必须显式记录推导（derivation），字段为：

1. 源证据：证据文件路径 + SHA-256；
2. 源实现修订与 Product Build；
3. 目标实现修订与 Product Build；
4. 对每棵 trigger 树执行的 diff 命令及其为空的输出；
5. 日期与记录人。

推导记录在目标 Build 的验收记录或 `docs/release-evidence/` 中。没有这条
记录，结转声明不存在。

## 触发树有变更时的豁免推导

trigger 树有变更时默认重跑。唯一豁免是逐 commit 分类推导：列出每个介入
commit，并证明它机械地落在该行的触发类之外——只触文档、测试，或该行
journey 不可达的代码路径。豁免推导由人审签，记录字段与未变树推导相同。
任一 commit 无法机械分类，该行即按失效处理。行为性变更（改了该行可到达
代码的运行时语义）永不豁免。

## 当前 Build 声明与证据链接

- 某行对 Build B 声称"当前已验收"，只能凭身份精确匹配 B 的通过，或一条
  记录完整、覆盖到 B 的结转/豁免推导。
- 每次通过声明链接 `docs/release-evidence/` 的证据文件及其 SHA-256；每次
  结转/豁免推导同时链接源证据与 diff 记录。
- 历史证据在引用时永远携带其原始 Build 编号；不得省略 Build 把它们写成
  未限定的"已通过"。

## 对 M2 与 M6 的应用

**M2（Human hearing and subjective audio quality）**：没有可通过。M2 于
2026-08-17 在 check 1 停止，trim 边界可闻咔哒（F6）与 trim 手柄无法瞄准
（F5）均为实测失败，行保持 `unverified`；部分过程是诊断上下文，不是证据。
P1 对 M2 没有可结转的东西。F5/F6 落地后按 Re-verification 表在当时当前
Build 上整行重跑，通过即按上文绑定完整身份。

**M6（Physical MIDI controller）**：`1.0.21.0` 的 MIDI canary 是有效历史
通过（证据
[2026-08-13-stage7-midi-channel-canary-1.0.21.0.md](../../release-evidence/2026-08-13-stage7-midi-channel-canary-1.0.21.0.md)，
reload/reopen 报告 SHA-256 `b0491e…603`），绑定集成 commit
`5613158240f7e31385ccb5d175bded3c245ae33b`。对 M6 的 trigger 树执行
`git diff --name-only 56131582..611f8ab4`（当前 `main`，Product Build
`1.0.30.0`）结果非空：`packages/web-runtime-platform/web/input_adapters.mjs`
（pointer-cancel 语义）、`runtime_session.mjs`、`protocol.mjs`、Stage 8/8B
的 Creator runtime 与 capture 管线、`apps/web-runtime-host/tools/release_bundle.py`
等均有变更。未变树推导不可用，也未记录豁免推导。结论：**M6 是需要在被测
Build 上重跑的行**；canary 证据对 `1.0.21.0` 仍然成立，但不满足 M6，也
不构成对任何后续 Build 的当前声明。

## Version impact

None——本决策不改变任何 Product Build、Module、Host、Provider 或 Contract
版本。后续的复验执行或产品变更各自声明自己的版本影响。

## Documentation impact

Required——本决策文件与 Human TODO checklist
（[2026-08-17-manual-verification-todo.md](../../quality/2026-08-17-manual-verification-todo.md)）
在同一个 Task 内更新；不涉及 Portal 路由变更。
