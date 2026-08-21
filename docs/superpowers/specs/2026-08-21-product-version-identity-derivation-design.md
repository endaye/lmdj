# LMDJ Product Version Identity Derivation Design

日期：2026-08-21

状态：待用户 review 批准；本文只定义后续 implementation 的边界，不分配 Product Build

关联任务：[Issue #207](https://github.com/endaye/lmdj/issues/207)、
[Issue #165](https://github.com/endaye/lmdj/issues/165)

## 1. 结论

LMDJ 保持 `products/lmdj/version.json` 为四段 Product Build Version 的唯一源码真相，
并按消费方语义把其他版本出现分成三类：

1. **必须派生的 current identity**：构建定义、当前仓库一致性测试、打包/门户事实与
   Runtime identity 一律读取已提交的权威输入，不复制当前 Product Build 字面量；
2. **与 current identity 无关的行为 fixture**：使用显眼且稳定的 synthetic identity，
   例如 `9.8.7.6`，证明值的验证或传播，不随下一次 Product Build allocation 修改；
3. **必须显式保留的 exact identity**：`assembly.json` 的 Contract 声明、reviewed release
   intent 与 immutable Portal snapshot 继续保存精确版本，不能被 mutable HEAD 派生值替代。

所有 unavoidable mismatch 都必须在最早可判定的 gate 中报告 authority、expected、found、
consumer path 与可复制的 remedy。Creator Web 另增加 `module.json`、`package.json` 与
`package-lock.json` 的三方 Host version 一致性门禁。

本设计不新增 allocation 命令，不修改任何 Product/Module/Host/Provider/Contract/Model
身份，不写 `version.json`、Assembly、lock、release intent 或 snapshot，也不把
`HOST_PROTOCOL_MISMATCH` 的公开 Contract 扩成新的产品错误语义。

```text
products/lmdj/version.json
            |
            +--> CMake compile definitions
            +--> version.py -> compiled assembly + assembly lock
            +--> Runtime identity generator -> JSON + MJS
            +--> Portal repo facts -> BuildIdentity
            +--> current-repository tests

stable synthetic Product Build
            |
            +--> pure behavior tests only

exact reviewed identity
            |
            +--> assembly declaration / release intent / immutable snapshot
```

## 2. 背景与问题修正

Issue #207 的“七个手工位置加五个派生产物”来自 `1.0.23.0` allocation 的历史取证，
不是当前 `origin/main` 上仍然成立的静态数量。若 implementation 继续以 Issue 标题作为
验收清单，会重复修复已经完成的工作，并可能把 intentional exact records 错改为 mutable
派生值。

截至 `origin/main` `2acda3659016b9946bf6cfbbe9364793fa02792a`，以下历史风险已经收敛：

- `products/lmdj/CMakeLists.txt` 从 `version.json` 计算 Web Product Build compile
  definition；
- `apps/native-test-host/CMakeLists.txt` 从 `version.json` 计算 Native Product Build；
- `tests/host/native_host_test.py` 从 `version.json` 得到期望 Product Build；
- `tests/platform/web/host/web_runtime_host_lifecycle.spec.mjs` 从 generated Runtime
  identity 构造 Host fixture；
- `scripts/version.py lock` 原子生成 `products/lmdj/src/compiled_assembly.cpp` 与
  `products/lmdj/assembly.lock.json`，两者不再是独立手改步骤；
- Architecture Portal 的 `BuildIdentity` 与 repo facts 已从 active manifests/lock 派生。

当前剩余问题不是“找到七处并全部删掉”，而是：

- current-repository tests 仍有多处把当前 `1.0.24.0` 写成 expected fixture；
- pure behavior tests 也使用了看起来像 current truth 的 `1.0.24.0`，导致 allocation
  时被机械更新；
- mismatch/stale failures 多数只说“不匹配”或只给 `AssertionError`，没有 expected、
  found 和路径；
- Creator Web 的 npm package identity 没有与 Host `module.json` 闭合，历史上已经发生
  `package.json` 为 `1.3.0`、lock 仍为 `1.2.0` 的漂移；
- current Portal prose、release intent 与 immutable snapshots 中的精确版本具有语义，
  不能为了减少 grep 结果而自动替换。

因此，Issue #207 的验收基准必须从历史数量改成“每个 current consumer 有明确分类，
可派生者不复制，显式记录者有精确门禁，失败能直接指出版本与修复动作”。

## 3. 目标

- 让下一次 Product Build allocation 只修改真正的权威输入和必需的 reviewed exact records，
  不再修改与 current identity 无关的行为 fixture。
- 让 current-repository tests 读取 committed truth，同时继续独立验证消费者与权威输入一致。
- 让 Assembly、lock、compiled assembly、Runtime identity、Portal facts 和 Host runtime
  identity 的漂移在构建或测试阶段被定位，不等到浏览器启动后只看到
  `HOST_PROTOCOL_MISMATCH`。
- 让每条 Product Build mismatch 诊断至少包含 expected、found、authority 和 consumer。
- 给 Creator Web 的 `module.json`、`package.json`、`package-lock.json` 建立闭合、可负例测试
  的 Host version 门禁。
- 保留 release intent、immutable snapshots 和 build-specific Portal prose 的 exact semantics。
- 在不改变 Product Assembly 或任何版本域的前提下完成机械 hardening。
- 明确与 Issue #165 共享 release audit tests 的串行实施和集成顺序。

## 4. 非目标

本设计不包含：

- 分配、递增或预留新的 Product Build；
- 修改 `products/lmdj/version.json`、`assembly.json`、`assembly.lock.json` 或任一
  Module/Host/Provider manifest 的身份；
- 新增 `version.py allocate`、一键 bulk rewrite 或自动生成 Portal 语义 prose；
- 删除 `lmdj.assembly.v2` 中的 `product.version` 字段，或创建新的 Assembly Contract；
- 把 release intent 改成从 current HEAD 推导，或改写历史 intent disposition/target；
- 重写、删除或重新冻结既有 Portal snapshots；
- 生成新的 `versions/PRODUCT_BUILD/`、versioned metadata、sidebar 或 diagram assets；
- 改变 `HOST_PROTOCOL_MISMATCH` 的 Error Contract、公开 UI 文案或隐私边界；
- 处理 Issue #165 的 18 条远端 audit findings、修改 GitHub Release metadata，或执行任何
  release mutation；
- push branch、创建 Pull Request、merge、tag、Release、deploy 或 Channel promotion；
- 在本规格阶段编写 implementation plan 或实现代码。

## 5. Current Authority Inventory

### 5.1 唯一 Product Build source

`products/lmdj/version.json` 是 Product Build Version 的唯一源码真相。它以
`milestone`、`minor`、`build`、`patch` 四个整数保存身份。所有 current consumer 必须通过
现有 `ProductVersion`/repo-facts/parser 模式得到点分字符串，不能在消费者中再写一份当前值。

`version.json` 的权威性不意味着其他 exact records 可以删除。它只决定“当前 source 的
Product Build 是什么”；它不能代替 Assembly Contract、release authorization、snapshot
provenance 或历史 evidence 回答各自的问题。

### 5.2 Intentional explicit declarations

以下位置必须继续保存精确版本：

| 位置 | 原因 | 规则 |
| --- | --- | --- |
| `products/lmdj/assembly.json` 的 `product.version` | `lmdj.assembly.v2` 的声明字段，是 reviewed Product Assembly 输入 | 保留显式值；`version.py` 必须与 `version.json` 比较并给出精确 mismatch |
| `docs/release-evidence/release-intents.json` | reviewed exact identity、target、disposition、channel 与 evidence 的授权记录 | 不从 HEAD 派生，不由本任务改写；release audit 独立验证 |
| `apps/architecture-portal/versioned_*`、`static/versions/*`、`versions.json` | immutable Product Build 说明书及 provenance | 只由 snapshot workflow 生成或验证，不改写既有版本 |
| current Portal 的 build-specific prose | 说明某个 Build 实际交付/未交付什么，版本是语义的一部分 | 保留人工 review；不能用一个自动 token 代替整段事实审查 |
| 历史 plan、acceptance 与 evidence | 记录当时的 exact identity 和边界 | 永不随 current version bump 更新 |

当前含 build-specific `1.0.24.0` prose 的完整 current Portal 路径为：

- `apps/architecture-portal/docs/assembly/lmdj.mdx`；
- `apps/architecture-portal/docs/hosts/creator-web.mdx`；
- `apps/architecture-portal/docs/hosts/overview.mdx`；
- `apps/architecture-portal/docs/hosts/web-runtime.mdx`；
- `apps/architecture-portal/docs/operations/testing-and-proof.mdx`；
- `apps/architecture-portal/docs/operations/version-and-release.mdx`；
- `apps/architecture-portal/docs/overview/index.mdx`；
- `apps/architecture-portal/docs/platform/input.mdx`；
- `apps/architecture-portal/docs/platform/web-runtime.mdx`；
- `apps/architecture-portal/docs/product/capability-map.mdx`。

这些页面在 future allocation 中仍须按 Portal policy 审查整段 current truth；本设计只禁止把
它们当作可无脑搜索替换的 gate table。

`products/lmdj/README.md` 当前写死的“source of truth for Product Build `1.0.24.0`”不属于
上述 exact records；README 应改成稳定说明：`version.json` 是 Product Build source，
Assembly 显式声明必须匹配，lock/compiled identity 由工具生成。

### 5.3 Existing derived consumers

以下既有模式是后续 implementation 应复用的设计先例：

| Consumer | 当前派生路径 |
| --- | --- |
| Web Host compile identity | `products/lmdj/CMakeLists.txt` 读取 `version.json` 四段并定义 `LMDJ_WEB_PRODUCT_BUILD` |
| Native Host compile identity | `apps/native-test-host/CMakeLists.txt` 读取同一文件并定义 `LMDJ_NATIVE_PRODUCT_BUILD` |
| Compiled Assembly + lock | `scripts/version.py lock` 从 version + assembly 原子渲染生成 pair |
| Web Runtime identity | `tools/web-runtime/generate_runtime_identity.py` 读取 version、assembly、lock 与 Host manifests，生成 JSON/MJS |
| Creator/Web packaging | packaging tools 读取 version 或 generated identity，不使用 package version 充当 Product Build |
| Portal current facts | `repo-facts.mjs` 读取 version、assembly、lock；`BuildIdentity.tsx` 消费 generated facts |
| Native Host current test | Python fixture 从 `version.json` 计算 `PRODUCT_BUILD` |
| Web lifecycle current test | Playwright fixture import `WEB_RUNTIME_IDENTITY` |

这些路径继续保持 Product Assembly 和 Product-specific wiring 的现有边界；不引入新的共享
generated constants 文件。

### 5.4 Current-bound test literals to remove

下列 tests 校验 active repository 或错误地把 current identity 当行为 fixture，当前仍包含
`1.0.24.0`：

- Portal current facts：`apps/architecture-portal/test/repo-facts.test.mjs`；
- Assembly/lock：`tests/conformance/version_lock_test.py`、
  `tests/core/facade/assembly_loader_test.cpp`；
- Release/current docs：`tests/build/release_audit_test.py`、
  `tests/build/release_prepare_test.py`、
  `tests/build/web_runtime_public_deployment_docs_test.py`；
- Creator behavior tests：`acceptance_report.test.ts`、`audio_lifecycle.test.tsx`、
  `input_controller.test.ts`、`project_actions.test.ts`、`runtime_context.test.tsx`、
  `workspace_shell.test.tsx`；
- Web behavior tests：`apps/web-runtime-host/test/main_shell.test.mjs`、
  `packages/web-runtime-platform/test/runtime_session.test.mjs`；
- `tests/build/version_test.py` 的 CMake negative assertion 本身也复制了当前值。

处理规则不是统一 import 一个新 constant：

- 真正验证 active repository 的 test 直接从 `version.json`、Assembly 或 generated identity
  计算 expected；
- 只验证数据传播、报告形状、状态机或错误处理的 test 使用局部 stable synthetic identity；
- 同一测试文件若同时包含两种语义，必须用命名区分，例如 `current_product_build()` 与
  `TEST_PRODUCT_BUILD`，不能让 synthetic fixture 被误解为 current truth；
- release tests 中复制真实 static authority 的 integration case 派生 current identity，
  纯 model/error case 使用 synthetic identity；
- historical version literals 不进入清理范围。

## 6. 方案比较

### 6.1 推荐：就地派生 + synthetic fixtures + 精确 diagnostics

每个 current consumer 在自己的语言和既有边界内读取 committed truth；pure behavior tests
使用 stable synthetic value；显式 exact records 保持不变。校验器在发现 drift 时给出结构化、
可行动诊断。

优点：

- 不新增生成步骤或生成物；
- 不改变任何运行时或公开 Contract；
- 一次机械清理后，future allocation 不再触碰无关 fixture；
- 每个负例可在临时目录或内存 fixture 中确定性验证；
- 与现有 CMake、Portal、packaging 和 lifecycle 派生模式一致。

代价：

- Python、Node 和 C++ tests 各自在窄边界读取 committed truth，而不是共享一个跨语言 helper；
- build-specific Portal prose 仍须人工 review，因为其内容不只是版本 token。

### 6.2 备选：生成跨语言 current-version constants

由一个 generator 输出 Python、TypeScript、CMake 和 JSON constants，消费者全部 import。

不采用，原因是它增加新的生成顺序、tracked outputs 和 stale-state failure。Product Build
已经有 `version.json` 和多种成熟 reader；再生成一层只会把 Issue 所述“五个派生产物”扩大。

### 6.3 备选：`version.py allocate` 批量重写

一个命令递增 Product Build，并重写 Assembly、tests、release fixtures 与 Portal prose。

不采用，原因是 allocation 是独立产品身份与授权决定，不应被一个机械 hardening Task 隐式执行；
工具也无法安全决定 release intent disposition、snapshot provenance 或 build-specific prose。
批量 rewrite 会保留重复真相，只是把漏改风险换成 mutation 风险。

## 7. 组件设计

### 7.1 Product Build reader 与 current-repository tests

现有 `scripts.version.ProductVersion`、Runtime identity reader 与 Portal repo-facts reader 继续是
各自边界的 parser。后续 implementation 不创建一个新的通用 identity service。

current-repository tests 必须独立读取权威输入并验证消费者：

- Python tests 可以复用 `scripts.version.load_version()` 或直接读取四段 JSON 后格式化；
- Node tests 读取 `version.json` 或 import generated Runtime identity，选择与被测边界最接近的
  committed truth；
- C++ fixture 已接收 parsed Assembly 时，直接使用 `assembly.product.version` 构造 catalog，
  不复制 current value；
- negative source scan 使用四段版本 pattern 或语义标记，不把当前值写在 assertion 中。

派生 expected 不能让测试变成同源自证。例如 Portal fixture 仍要用独立 mismatched repository
证明 `version.json`、Assembly 与 lock 的差异会失败；Assembly loader 仍验证 compiled catalog
与 declarative Assembly 的关系。变化只是删除“当前数字必须恰好等于某字面量”这一无价值断言。

### 7.2 Synthetic behavior fixtures

pure behavior tests 使用合法但显眼的 `TEST_PRODUCT_BUILD`，默认值为 `9.8.7.6`。该值：

- 满足四段数字格式；
- 不代表任何已分配、候选或未来 Product Build；
- 只测试透传、冻结、报告、渲染、状态机或 mismatch 行为；
- 不得写入 active manifests、build artifacts、release intent、Portal current facts 或 snapshots；
- 不得在 future allocation 中机械更新。

若 test 必须同时断言 match 与 mismatch，基线使用 `TEST_PRODUCT_BUILD`，变异值使用另一个
synthetic value，例如 `9.8.7.5`。测试名称和 helper 名必须表明它是 synthetic fixture。

### 7.3 Version/Assembly/lock diagnostics

`scripts/version.py` 的 verify/lock 边界在比较 version、Assembly、compiled assembly 和 lock
时应先做 identity-specific checks，再做完整 document/hash equality。这样 operator 首先看到根因，
而不是无关 hash mismatch。

标准 human diagnostic 形状：

```text
Product Build mismatch: expected 1.0.24.0 from products/lmdj/version.json,
found 1.0.23.0 in products/lmdj/assembly.json;
remedy: update the reviewed products/lmdj/assembly.json declaration to the
approved Product Build, then regenerate the compiled assembly and lock with
the stable scripts/version.py lock command
```

规则：

- `expected` 来自已验证的 `version.json`；
- `found` 来自被比较 consumer，缺失字段显示 `<missing>`，非法或不可解析内容显示
  `<invalid>`，不猜值；
- path 使用 repo-relative path，临时 fixture 可显示调用方提供的规范化路径；
- remedy 只建议恢复派生物或修正声明，不自动执行 mutation；
- declaration mismatch 的 remedy 先指向具体 reviewed declaration；只有 declaration 匹配后，
  才建议运行稳定 generator；
- 对 compiled assembly 或 generated Runtime identity 的 stale failure，remedy 指向现有稳定
  generator；
- 完整 hash/document drift 仍保留原门禁，但 identity mismatch 必须先于泛化错误；
- version 值不是 secret，可完整显示；诊断仍不得泄露环境变量、token 或绝对用户路径。

`tools/web-runtime/generate_runtime_identity.py --check` 对 JSON/MJS stale 输出 expected Product
Build 与可解析的 found Product Build；若 MJS 不能安全解析，只报告 `<invalid>` 和 path，不用正则
猜测任意脚本语义。

### 7.4 Portal repo facts diagnostics

`apps/architecture-portal/scripts/lib/repo-facts.mjs` 继续从 version、Assembly 和 lock 构建 facts，
但 mismatch 必须按 consumer 分开报告。例如 Assembly 与 lock 同时错误时，错误至少明确当前
被拒 consumer；不把两者折叠成一个无法定位的 `product version mismatch`。

Portal public page 继续只渲染安全的 identity facts。诊断增强属于 build/check surface，
不改变 published Portal information architecture。

### 7.5 Creator triple consistency

Creator Web Host version 的权威输入是 `apps/creator-web/module.json`。以下值必须精确相等：

```text
module.json.version
    == package.json.version
    == package-lock.json.version
    == package-lock.json.packages[""].version
```

门禁放在现有 version/module graph conformance 路径，而不是 npm install 的副作用中。它必须：

- 验证三个 JSON document 的闭合必要字段；
- 对每个 consumer 分别输出 expected Host version、found 值和 repo-relative path；
- 同时检查 package name：`lmdj.module.v1` 没有 npm name 字段，expected name 从
  `module.json` 的 `module` 字段派生为 `@lmdj/<module>`（当前即 `@lmdj/creator-web`）；
  `package.json.name`、`package-lock.json.name` 与 `package-lock.json.packages[""].name`
  必须与之精确相等，避免 lock root 指向另一个 package。门禁中不得出现没有权威来源的
  手写 name 字面量；
- 用负例 fixture 分别覆盖 top-level lock version、root package version、package.json version
  与 name drift；
- 只读取，不自动运行 `npm install` 或改写 lockfile。

这项门禁管理的是 Creator Host/package SemVer，不把 npm package version 当 Product Build。

### 7.6 Native/Web runtime failure boundary

Native Host test 已派生 expected Product Build，但 `ready.result.product_build` 断言仍须附带
expected/found/message。Web lifecycle fixture 已派生 current identity，不再需要另一个 Product
Build source。

Runtime manifest gate 仍可对不可信或不兼容 manifest 返回稳定公开 code
`HOST_PROTOCOL_MISMATCH`。本设计不把 internal expected/found versions 暴露给用户界面；
准确版本信息由 earlier build/conformance gates 和 test assertion 提供。这保留 Error Contract
与公开隐私边界，同时消除 allocation 漏改直到浏览器 boot 才被发现的路径。

## 8. 数据流与失败顺序

正常流：

```text
version.json validated
  -> assembly explicit version compared
  -> compiled assembly rendered
  -> lock rendered from exact assembly + compiled bytes
  -> Runtime identity rendered from exact committed inputs
  -> CMake/packagers/Portal/tests consume derived identity
  -> runtime manifest gate validates packaged identity
```

验证流必须遵循由具体到泛化的顺序：

```text
document readable and shape valid?
  -> Product/Host identity expected == found?
  -> generated bytes current?
  -> source/package hashes current?
  -> full inventory/document equality?
```

因此一次漏改 `assembly.json` 不会先表现为 Assembly hash mismatch；一次 stale Runtime identity
也不会只显示“generated file stale”；Creator lock drift 不会等到 npm tooling 或 package output
中偶然暴露。

## 9. 文件边界

后续 implementation 预计只允许修改以下类别；implementation plan 必须从当时最新
`origin/main` 重新确认精确列表。

### 9.1 Identity checker 与 generator

- `scripts/version.py`
- `tools/web-runtime/generate_runtime_identity.py`
- `apps/architecture-portal/scripts/lib/repo-facts.mjs`

### 9.2 Conformance/current-repository tests

- `tests/build/version_test.py`
- `tests/conformance/version_lock_test.py`
- `tests/conformance/module_graph_test.py`
- `tests/core/facade/assembly_loader_test.cpp`
- `tests/host/native_host_test.py`
- `apps/architecture-portal/test/repo-facts.test.mjs`
- `tests/build/release_audit_test.py`
- `tests/build/release_prepare_test.py`
- `tests/build/web_runtime_public_deployment_docs_test.py`

### 9.3 Synthetic behavior fixtures

- `apps/creator-web/test/acceptance_report.test.ts`
- `apps/creator-web/test/audio_lifecycle.test.tsx`
- `apps/creator-web/test/input_controller.test.ts`
- `apps/creator-web/test/project_actions.test.ts`
- `apps/creator-web/test/runtime_context.test.tsx`
- `apps/creator-web/test/workspace_shell.test.tsx`
- `apps/web-runtime-host/test/main_shell.test.mjs`
- `packages/web-runtime-platform/test/runtime_session.test.mjs`

### 9.4 Stable explanatory docs

- `products/lmdj/README.md`
- Portal current route `/operations/version-and-release/`
- Portal current route `/operations/testing-and-proof/`

### 9.5 Explicit exclusions

本 Task 不得修改：

- `products/lmdj/version.json`、`assembly.json`、`assembly.lock.json`、
  `src/compiled_assembly.cpp`；
- `products/lmdj/generated/web-runtime-identity.json` 或 `.mjs`；
- 任何 Module/Host/Provider manifest、Contract schema 或 model identity；
- `docs/release-evidence/release-intents.json`；
- `apps/architecture-portal/versions.json`、`versioned_docs/`、`versioned_metadata/`、
  `versioned_sidebars/`、`static/versions/`；
- historical plans、acceptance 或 release evidence。

若 implementation 发现必须修改任一 exclusion，说明本设计假设不再成立；停止该 Task，重新做
设计/版本影响审查，不把扩展 silently 合入。

## 10. 与 Issue #165 的共享测试串行化

Issue #165 要让 release audit 的 18 条既有 findings 暴露具体 exact-target validation detail。
它与本设计至少共享 `tests/build/release_audit_test.py`，并可能因 target-validation fixture
调整触及 `tests/build/release_prepare_test.py`。两项工作不能在并行 branches 中各自重排同一组
fixture 后再依靠最终 merge 解决。

默认集成顺序为：

1. Issue #165 先完成 release diagnostic/threading 及其 shared tests；
2. Issue #207 implementation 从包含 #165 的最新 `origin/main` 创建 fresh worktree；
3. #207 只把 shared tests 中的 current Product Build 输入改为派生或 synthetic fixture，保留
   #165 新增的 finding/detail assertions；
4. 两项各自独立运行 release audit/prepare tests，最终仍由 repository Integration Queue
   串行验证与 merge。

如果 #207 已先进入 implementation，规则对称：#165 必须等待 #207 merge 后从 fresh main 开始。
“PR 最终排队串行”不能替代 branch work 的文件所有权串行化；在第二项任务开始前，第一项必须已经
merge 或明确释放 shared test ownership。

#207 不处理 #165 的远端 findings，不修改 historical exceptions，不调用 remote release API，
也不把 #165 的失败状态当成本地 identity gate 的测试数据。

## 11. TDD 与验证设计

### 11.1 RED：诊断契约

先在临时 fixture 中分别制造：

- `version.json` 与 `assembly.json` Product Build 不同；
- compiled assembly 中的 Product Build 或内容 stale；
- lock 的 `product.version` 或 `product_assembly.version` stale；
- generated Runtime identity JSON/MJS stale；
- Portal fixture 的 Assembly/lock Product Build 与 version 不同；
- Native Host ready response 返回另一个 Product Build。

每个 test 先要求失败文本包含 authority、expected、found、consumer path；现有实现因 generic
message 或 bare assertion 而 RED。随后才修改 checker/generator。

### 11.2 RED：Creator triple gate

用独立 fixture 逐个变异：

- `package.json.version`；
- `package-lock.json.version`；
- `package-lock.json.packages[""].version`；
- package name。

现有 conformance 没有该门禁，因此 RED 必须证明每个 drift 目前未被目标 checker 精确拒绝。
GREEN 后错误包含从 `module.json` 派生的 expected version 或 expected name、found 值和
具体 consumer path。

### 11.3 RED：current literals 与 synthetic fixtures

current-repository tests 先改为从 committed truth 计算 expected，并保留独立 mismatch fixture；
pure behavior tests 将 current-looking value 改为命名的 `TEST_PRODUCT_BUILD`。测试必须证明：

- current facts 随临时 version fixture 改变，而不是钉住仓库当前数字；
- synthetic value 被完整传播到 report/diagnostics/state，但与 active source 无关系；
- generic source assertion 不复制当前 Product Build 字符串；
- historical literals 和 reviewed exact records 未被修改。

### 11.4 GREEN 与 regression verification

最小目标验证：

```bash
python3 tests/build/version_test.py
python3 tests/conformance/version_lock_test.py
python3 tests/conformance/module_graph_test.py
python3 tests/build/release_audit_test.py
python3 tests/build/release_prepare_test.py
npm --prefix apps/creator-web test -- --run
node --test apps/web-runtime-host/test/main_shell.test.mjs
node --test packages/web-runtime-platform/test/runtime_session.test.mjs
npm --prefix apps/architecture-portal test
```

集成验证：

```bash
scripts/core.sh configure dev
scripts/core.sh build dev
scripts/core.sh test dev fast
scripts/architecture-portal.sh check
```

本变更不修改 lock-free/concurrent production code，不要求 stress tier。若当时 test registration
把受影响 test 提升到更高 tier，implementation plan 必须使用最新 policy 而不是本文缓存。

## 12. Acceptance Criteria

- `products/lmdj/version.json` 仍是唯一 current Product Build source。
- active Assembly explicit Product Build 被保留并有 expected/found/path 诊断。
- compiled assembly、lock 与 Runtime identity 保持生成物，不出现新的手改 current constant。
- current-repository tests 不复制当前 Product Build 字面量。
- pure behavior tests 使用命名 synthetic Product Build，并明确禁止随 allocation 更新。
- Creator `module.json`、`package.json`、lock top-level 与 root package version/name 有闭合门禁。
- Product Build/Host version mismatch failures 包含 expected、found、authority 和 consumer；
  generated stale failure 还包含稳定 remedy。
- public `HOST_PROTOCOL_MISMATCH` Contract 和 UI 隐私边界不变。
- release intent、historical evidence 与 immutable snapshots 无改动。
- #165 与 #207 的 shared release tests 按第 10 节串行拥有和集成。
- targeted tests、Core fast tier 和 Architecture Portal check 全部通过。
- implementation diff 不包含任何版本分配、snapshot、release、deployment 或 Channel promotion。

## 13. Version Management

Version impact: none

Reason: 本设计只派生已提交身份、重构测试 fixture、增加一致性门禁并改进 build-time
diagnostics；它不改变公开产品行为、Product Assembly、Module/Host/Provider API、Contract、
Model identity 或依赖身份。implementation 不修改 `version.json`、任何 manifest、Assembly 或
lock，因此不分配 Product Build，不创建 tag，也不改变 Channel。

允许状态只到 `designed`，以及后续经独立计划完成后的 `implemented/committed`。本文不授权
push、Pull Request、merge、tag、Release、deployment 或 Channel promotion。

## 14. Documentation Impact

Documentation impact: required

Affected portal pages:

- `/operations/version-and-release/`
- `/operations/testing-and-proof/`

Reason: implementation 将改变 Product Build allocation 的一致性门禁、测试 fixture 规则和
operator-visible failure diagnostics，属于版本/测试流程事实。Portal current pages 必须说明：
`version.json` 的 authority、intentional exact records、synthetic fixture 边界、Creator triple
gate，以及 mismatch 的 expected/found/remedy 形状。

本设计不改变 Product Build、Assembly、lock 或组件边界，所以：

- 不更新架构 source diagrams；
- 不运行 `scripts/architecture-portal.sh version`；
- 不生成或修改任何 immutable snapshot；
- 只在 implementation Task 中更新上述两个 current routes，并运行
  `scripts/architecture-portal.sh check`。

## 15. 设计完成边界

本文件记录已批准设计。它不是 implementation plan，也不授权实现。spec commit 后停在用户
review gate；只有用户再次明确批准进入 planning，才可调用 writing-plans 并从当时最新
`origin/main`、Issue/PR 状态与 #165 集成状态重新生成 Task 顺序。
