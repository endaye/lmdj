# Review：LMDJ Playable Beat Instrument 与新内核设计

日期：2026-07-30

评审对象：
[docs/design/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md](../specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)
（commit `047d6a06`，含同批 decision-log 三条新决策）

评审性质：设计文档评审（read-only），不改变设计结论本身。

## 1. 总体结论

设计方向健康，核心架构决策（单一 Authoring Domain + 派生 Runtime Snapshot、
统一 Application Facade、Capability/Provider 分离、四层独立契约、Attempt 级
失败隔离）相互一致，且与 §24 被拒绝方向逐条对应，能看出是对旧 Patch /
Materials 万能契约耦合教训的直接修正。**设计可以作为实施计划的输入。**

但有两处**文档自引用不成立**（修订说明承诺的内容在正文和 open-questions.md
中不存在），应在进入实施计划前修复；另有若干核心风险建议在 Proof 或实施
计划阶段显式处理，详见下文。

## 2. 设计优点

- **单一真相 + 派生 Runtime（§11）**：Authoring Project → Cook → Immutable
  Snapshot → Audio Runtime 的单向数据流，直接消除了旧系统"一份 JSON 服务
  所有消费者"的耦合根源；Snapshot 可丢弃、失败不回写，与 §18 的事务恢复
  模型自洽。
- **Facade 平权（§10、§12）**：UI / CLI / MCP / 测试 Host 走同一入口，
  Editor 无内部特权，这让 §21.4 的共享行为 Fixture 和 §22 Proof 的
  "CLI 与 MCP 查询相同 Project State" 成为可验证承诺而不是口号。
- **Raw Take 持久化边界（§6.5）**：识别出"用户演奏不可再现、丢失成本与
  可重跑 AI Job 不对称"，因此 Take 不走 Candidate → Commit 流程而是尽早
  落盘 Journal——这是本次修订中最有价值的补充，正确地把用户演奏放在了
  数据保护优先级的最高层。
- **四层契约独立版本（§17）**：Project / Runtime Snapshot / Capability I/O /
  Assembly 各自演进，跨边界只传 Content-Hash Artifact Ref，明确拒绝旧契约
  Compatibility Adapter，边界干净。
- **禁止静默回退 + Typed Error（§16、§18）**：重试/换 Provider 一律产生新
  Attempt，UI 只能翻译不能改变错误语义，可追踪性设计完整。
- **§25 的设计/实施分界**：明确列出哪些选择可以机械确定、哪些必须回到设计
  评审，为后续并行开发划了清晰的护栏。

## 3. 发现的问题

### P1 — 进入实施计划前必须修复

1. **open-questions.md 缺少设计文档引用的两个条目。**
   文档两处（修订说明；§6.5 末条）声称以下问题"记入 open-questions.md"：
   - 素材 BPM 与 Project BPM 的关系（Time-stretch）；
   - 录音进行中的并发 Command 与 Expected Revision 的交互语义。

   实际检查 `docs/prd/open-questions.md`（commit `047d6a06` 及当前
   `origin/main`）：**两条均不存在**。引用落空意味着这两个待决问题目前没有
   任何跟踪载体，而它们都不是边缘问题（见 P2-2、P2-3）。

2. **修订说明与 §23 正文不一致。**
   修订说明称 §23 交付顺序已补充"第 0 步旧产品处置、Web 实时音频 Spike、
   首个用户价值里程碑"，但 §23 正文只有 12 步交付列表：没有第 0 步、没有
   Spike、也没有标记任何用户价值里程碑。要么补正文，要么改修订说明，
   二者取一。

### P2 — 核心风险，建议在 Proof / 实施计划阶段显式处理

1. **用户价值出现太晚。** 按 §23 现有顺序，Creator Editor 是第 7 步，
   Sample / Sequence / Perform 在其后。前 6 步（Foundation → Web WASM）
   全部是基建。对一个"三分钟做出第一个 Beat"（§3.2）的产品承诺来说，
   如果没有 P1-2 中缺失的"首个用户价值里程碑"，很容易演变成长期只有
   Headless 内核而无可演示产品的状态。建议在修复 P1-2 时，把该里程碑
   锚定到一个具体交付步骤上（例如第 6 步 Web Runtime Lab 必须能在浏览器
   里真实敲 Pad 出声）。

2. **Web 实时音频可行性未被正文覆盖。** 首发平台是 Desktop/Tablet Web/PWA
   （§3.4），意味着 64-Pad Sampler + Momentary FX 必须跑在
   WASM + AudioWorklet 上，而这条路径受 SharedArrayBuffer / COOP+COEP、
   AudioWorklet 线程约束、OPFS 性能等浏览器条件制约。§20.1 的 C ABI 与
   线程模型若按 Native 习惯设计，有在 AudioWorklet 环境返工的风险。修订
   说明里提到的 "Web 实时音频 Spike" 正是对症的动作——但它目前只存在于
   修订说明里（P1-2）。建议 Spike 排在 C ABI 定稿之前。

3. **Expected Revision × 录音中写入是核心并发问题，不是实施细节。**
   §12.1 要求 Command 原子且带 Expected Project Revision（乐观并发），
   §6.5 要求录音事件持续写入 Journal。录音进行中若其他 Command 推进了
   Revision，`RecordTake` 完成时的提交语义（重排？合并？拒绝？）直接
   决定 Domain 的事务模型。它被列为 open question 是对的（但见 P1-1，
   目前并未真正记录），建议在 Proof 之前解决——否则 §22 第 4 步"创建
   一个用户演奏 Pattern"验证的就不是最终语义。

4. **Pad-slot 引用 × Sound Set 安装的组合有静默破坏面。** §6.6 规定
   Pattern 引用 Pad 位置而非 Asset（Sampler 惯例，本身合理），§5.4 允许
   把 Sound Set 安装到用户选定的 Bank。二者组合：安装一个 Set 会立即
   改变所有引用该 Bank 的既有 Pattern 的声音，且 Lineage 按 §6.6 明确
   不记录 Pattern×音色的历史组合，事后不可考。建议实施计划中为"安装到
   已被 Pattern 引用的 Bank"增加预览/确认步骤，或提示先 Resample 冻结。

5. **流程重量与团队规模的匹配。** Module Manifest（§15）、Assembly
   Pipeline、Conformance Suite、Policy Engine + Execution Zones（§19）
   作为目标状态都对，但在首个 Proof（§22）阶段全量落地会显著推迟第一行
   可听代码。建议实施计划明确各机制的"最小可用版本"（例如 Proof 阶段
   Manifest 只需 Module ID / Deps / Test Command 三项，Policy Engine 先
   以静态白名单替代）。

### P3 — 缺失细节，可在实施计划内补齐（不构成设计缺陷）

- 演奏输入的延迟目标与抖动预算（Touch / MIDI / Keyboard 各不相同），
  以及录制时的时间戳来源（Audio Clock vs Input Event Time）；
- Voice Pool 的 voice-stealing 策略与每 Pad 复音数上限；
- Mixer / Gain Staging 与 Momentary FX 的路由位置（Per-Pad / Bus / Master）；
- Metronome、Count-in 与 §6.2 录制长度的交互；
- Time-stretch 决策（P1-1 第一条）对 §3.2 核心承诺的影响：完整歌曲导入后
  若不做 stretch，"可演奏素材"与 Project BPM 的关系需要产品层面的答案。

## 4. 建议动作

1. 补 `docs/prd/open-questions.md` 两个条目（P1-1），或删除文档中的失效
   引用——推荐前者；
2. 修正 §23 与修订说明的不一致（P1-2），并显式标注首个用户价值里程碑；
3. 实施计划中将 Web 实时音频 Spike 排在 C ABI / 线程模型定稿之前（P2-2）；
4. 在 Proof 实施计划中先解决录音并发语义（P2-3）；
5. 为 Sound Set 安装到已引用 Bank 设计确认/预览交互（P2-4）；
6. 为 Manifest / Policy / Conformance 定义 Proof 阶段最小版本（P2-5）。

## 5. 事实核查附录

| 检查项 | 结果 |
| --- | --- |
| decision-log 2026-07-30 三条决策与 spec 结论一致 | ✅ 一致（重启定位 / 契约不兼容 / 永久 Monorepo） |
| §6.5、§6.6、§13、§22 修订内容存在于正文 | ✅ 存在 |
| §23 修订内容（第 0 步 / Spike / 里程碑）存在于正文 | ❌ 不存在（P1-2） |
| open-questions.md 含 Time-stretch 条目 | ❌ 不存在（P1-1） |
| open-questions.md 含录音并发语义条目 | ❌ 不存在（P1-1） |
| spec commit `047d6a06` 已在 `origin/main` | ✅ 已合入 |
