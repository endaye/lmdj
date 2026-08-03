# Core Review 积压整理（截至 Product Build 1.0.11.0）

- **来源**：`docs/quality/2026-08-01-core-review.md` 与
  `2026-08-03-build-1.0.7.0-review.md` ~ `2026-08-03-build-1.0.11.0-review.md`
- **性质**：这是**分诊文档**，不是实施计划。每个工作单元真正动手前，
  仍需按 `CLAUDE.md` 在 `docs/superpowers/plans/` 下写独立计划，
  并各自包含 `## Version Management` 段落。
- **口径更正**：1.0.11.0 报告正文写"未处理中危 11 项"，
  但该表同时包含 11 条 `⬜` 与 1 条新提出的 `🆕`。
  **准确数字是 12 项完全未处理 + 1 项部分处理。**

---

## 一、当前状态

| 严重度 | 数量 | 说明 |
| --- | ---: | --- |
| 高 | **0** | 两条历史高危已在 1.0.7.0 / 1.0.8.0 关闭 |
| 中（未处理） | **12** | 见下表 |
| 中（部分处理） | **1** | RealtimeEngine 线程契约：机制已修，头文件未声明 |
| 低（未处理） | 约 10 | 分散在各报告，不在本文档排期 |

### 类型分布才是重点

| 类别 | 项数 | 占比 |
| --- | ---: | ---: |
| 验证基础设施（测试执行、sanitizer、门禁） | 4 | 33% |
| 发行治理（打包、产物完整性、边界） | 4 | 33% |
| 契约执行与输入加固 | 3 | 25% |
| **核心逻辑缺陷** | **1** | **8%** |

**12 项里只有 1 项是核心逻辑缺陷**（磁盘 JSON 读路径无深度限制）。
其余全部属于"证明系统正确"的那一层，而不是"系统本身"。

这与逐个 build 的观感一致：实现质量持续很高，围绕实现的保障机制在掉队。
这些问题不会让今天的代码出错，但它们共同的后果是——
**明天改坏了没人会发现。**

---

## 二、四个工作单元

按"一个可评审 Conventional Commit"的粒度分组。同组的项共享代码路径或共享机制，
分开做会重复改同一批文件。

### 单元 A — CI 门禁修复

> 最便宜，且提升之后所有改动的安全网。**建议第一个做。**

| # | 来源 | 问题 |
| --- | --- | --- |
| A1 | 1.0.10.0 发现 1 | Apple-only 的 833 行代码碰不到任何 sanitizer——所有 sanitizer job 都是 `ubuntu-24.04` |
| A2 | 1.0.10.0 发现 2 | `audio.realtime_spsc_stress` 在全部 PR-blocking job 上都被排除 |
| A3 | 1.0.7.0 发现 4 | `scripts/core.sh test` 默认排除 stress，但 `CLAUDE.md` 仍把它写成标准入口 |
| A4 | 1.0.10.0 发现 3（部分） | `realtime_engine.hpp` 不声明线程前提；spec 里已写清，只是没搬上 API |

**动作**：新增 macOS ASan/UBSan job；把 spsc stress 恢复到至少一个 PR-blocking job；
同步 `CLAUDE.md` 的命令语义说明；把 spec 第 44/46/180/193/200 行的线程前提
搬成 `realtime_engine.hpp` 的方法注释。

**Version impact**：none。CI、文档与注释，无 Module API 或 Contract 变化。

**为什么排第一**：A4 是零设计成本纯收益（设计已存在，只是没暴露）；
A1/A2 补上的正是验证后续三个单元所需要的安全网。

---

### 单元 B — Contract Schema 执行器

> 最高杠杆。它的缺失**直接导致**了组内第二项。

| # | 来源 | 问题 |
| --- | --- | --- |
| B1 | 1.0.8.0 发现 2 | 仓库无任何 JSON Schema validator，`capability-v2-invalid.json` 从未被 Schema 校验过 |
| B2 | 1.0.8.0 发现 1 | 端口名校验四层不一致，只有注册层符合 Contract 的 `^[a-z][a-z0-9_]*$` |

**动作**：写一个覆盖本仓库 Schema 所用子集的最小校验器
（`type` / `required` / `pattern` / `enum` / `const` / `minItems` / `minimum` /
`additionalProperties` / `$ref` / `uniqueItems`），**保持 Python 侧零第三方依赖**；
让 `tests/fixtures/contracts/*` 真正跑一遍正负向；
然后把 `port_name` 规则统一到 `application.cpp`、`attempt_store.cpp` 读回、
MCP `server.py` 三处，并把"未知端口"从泛化错误消息中分离。

**Version impact**：Contract 无变化（只是开始执行既有 Schema）。
`application-facade` / `core-mcp` 收紧 Host 边界校验——
拒绝结果不变，只是更早且错误信息更准，按 patch 处理。

**依赖**：B2 应在 B1 之后，让新校验器直接覆盖它。

**顺带**：validator 落地后补两个当前未覆盖的负向 case——
重名端口（Schema 的 `uniqueItems` 抓不到）与跨端口重复 Artifact。

---

### 单元 C — foundation 输入加固

> 唯一包含真实逻辑缺陷的一组。三项共享同一批代码路径。

| # | 来源 | 问题 |
| --- | --- | --- |
| C1 | 1.0.7.0 发现 1 | 7 处磁盘 JSON 读路径无深度限制；try/catch 对栈溢出无效 |
| C2 | core review #3 | `project_store.cpp` JSON 读路径缺与 `read_artifact()` 对称的 `O_NOFOLLOW` |
| C3 | 1.0.7.0 发现 3 | `parse_bounded_json` 三份逐字复制、常量 `= 64` 三处独立定义；`valid_utf8` 两份 |

**动作**：把深度受限解析与 `valid_utf8` 下沉到 `packages/foundation`；
让 `project-io`（`project_store.cpp:540,1739`、`take_journal.cpp:431,469,834`）
与 `provider-sdk`（`attempt_store.cpp:572,1040`）全部改用；
同时给这些读路径补 `O_NOFOLLOW`。

**Version impact**：`foundation` minor（新增公共函数）；
`project-io` / `provider-sdk` / `application-facade` / `core-cli` 依赖传导；
Product Build +1。无 Contract 变化。

**注意**：C1 的威胁模型依据是——本仓库自己的 core review 已把 project bundle
当作信任边界（C2 就是同一批文件的符号链接问题）。同一份文件，
符号链接算安全问题、嵌套深度也应该算。

---

### 单元 D — 发行治理

> 四项都关于"什么会被发出去，以及 manifest 声称了什么"。
> **其中两项需要先做决策，不能在实施 Task 里顺手 settle。**

| # | 来源 | 问题 | 需先决策 |
| --- | --- | --- | :-: |
| D1 | 1.0.9.0 发现 1 | `scripts/core.sh package` 不跑任何测试，产物却标 `channel: canary`，与 policy §3 门禁矛盾 | |
| D2 | 1.0.9.0 发现 3 | `--build-root` 不受校验；`_git_revision()` 不检测脏工作树 → manifest 的 `git_revision` 可双向失真 | |
| D3 | 1.0.9.0 发现 2 | `build_time` 在归档内部，抵消 `create_zip()` 的全部确定性努力，ZIP 无法字节复现 | ✅ |
| D4 | 1.0.11.0 发现 1 | 名为 `native-test-host` 的组件进入 Product Assembly 与分发包 | ✅ |

**D1 / D2 可直接实施**：`package` 串上 `ctest --preset release -L '^(unit|component)$'`；
`_git_revision()` 增加 `git status --porcelain` 检查；
为 `build_root` 与源码修订建立可校验绑定。顺带补 detached `.sha256`
（policy 只在 `stable` 要求签名，但校验和成本近乎为零）。

**D3 需要决策**：`build_time` 是 policy §4 **明文要求**的
（"构建时间与构建平台"）。这不是打包器写错，是两个都正确的要求装进了同一个容器。
可选方案——把 `build-manifest.json` 改为 detached 与 ZIP 并列发布，
或从归档内剔除可变字段。**这改变了已发布产物的形态，属于发行治理决策。**

**D4 需要决策**：Assembly 成员资格是产品级问题。
要么承认它是产品面组件并改名 `native-host`（module id 与二进制名统一），
要么从 Assembly 与发行包移出、退回 `tests/`。
按 `CLAUDE.md`"不得在实施 Task 里静默解决开放的产品级 Contract 问题"，
这条应当先进 `docs/prd/decision-log.md`，像 capability v2 那样。

**同时应补一条书面准则**：什么可以进分发包。
1.0.9.0 到 1.0.11.0 之间，包内容已经从"CLI + MCP + 库"扩张到包含一个测试 Host，
而没有任何准则约束这个扩张。

**Version impact**：D1/D2/D3 是 Product 层面（打包工具），Module 不变；
D4 若改名则是 Module 重命名 + Assembly 变更，为 breaking。

---

## 三、建议顺序

```
A（CI 门禁）──► B（Schema 执行器）──► C（输入加固）──► D1/D2（发行治理·可直接做）
   便宜             最高杠杆            唯一逻辑缺陷
                                                    D3/D4 ──► 先决策，再实施
```

理由：

1. **A 先**——最便宜，且 B/C/D 的改动都会因为 A 补上的安全网而更容易验证。
   A4 尤其应该立刻做，它只是把已有的 spec 文字搬到头文件上。
2. **B 次之**——它的缺失是 B2 的成因，也是所有未来 Contract 变更的保护伞。
   在 C 之前做，意味着 C 引入的新 foundation 函数从第一天起就有 Schema 侧的对照。
3. **C 第三**——唯一的真实逻辑缺陷在这里，但它需要 A 的 sanitizer 覆盖来验证。
4. **D 最后**——D1/D2 可直接做；**D3/D4 先写决策再动手**，
   不要在实施过程中顺手定了发行形态与 Assembly 边界。

---

## 四、不建议的做法

- **不要一个 PR 打包全部 12 项。** 每个单元跨越不同模块与版本影响，
  混在一起会让 `## Version Management` 无法写清，也无法单独回滚。
- **不要在加新能力的 build 里顺手夹带这些修复。**
  1.0.7.0 和 1.0.10.0 已经各出现过一次"两个不相干工作流打进同一个 Product Build"，
  1.0.7.0 那次导致回滚 JSON 修复就等于回滚整套质量门禁。
- **不要把 D4 当作纯改名。** 它牵动 Assembly 成员、发行包清单与
  `package_acceptance_test.py` 的精确清单断言，需要一次完整的版本传导。
