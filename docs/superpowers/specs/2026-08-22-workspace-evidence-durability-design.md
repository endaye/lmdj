# LMDJ Workspace Evidence Durability Design

日期：2026-08-22

状态：待用户 review 批准；本文只定义后续 implementation 的边界

关联任务：[Issue #203](https://github.com/endaye/lmdj/issues/203)、
triage G2（`docs/quality/2026-08-17-machine-task-todo.md`）

## 1. 结论

Workspace 写盘的耐久性跟数据角色走，不跟 `write_bytes` 这一个原语走。

| 数据 | 写路径 | 耐久 | 丢失时的产品语义 |
| --- | --- | --- | --- |
| 终端 Attempt 记录 | `persist_attempt` → `write_new_atomic` | 与 Project Truth 同级：文件 `fsync` + 发布后父目录 `fsync` | 审计链断裂；“Provider failure belongs to Attempt state” 失去物理证据 |
| minted artifact 字节 | Attempt output sink 当前独立 `ofstream` | 同上 | 记录声称存在、磁盘没有；ledger invariant 报违规 |
| `host-settings.json` | `set_provider_selection` → `write_replace_atomic` → `write_bytes` | 保持 `flush` + `close` + `rename`，不 `fsync` | 无默认、无静默回退；下次读取走显式 `PROVIDER_NOT_FOUND`，用户再选一次 |

Native 上证据路径改用 POSIX `open` / `write` / `fsync` / `close`，不继续用 `std::ofstream`。`provider-sdk` 继续只依赖 `foundation`，不引入 `project-io`。Web / Emscripten 不新增存储抽象：`Application` 在 MEMFS 上构造空 Registry 与 default-deny policy，本来就不能跑 Provider；该平台上 `fsync` 是成功 no-op。

G3（Host settings 锁崩溃恢复）不在本次范围。

## 2. 背景

Runtime invariant harness 把 G2 记成 `host-settings.json` 没 `fsync`。Issue #203 修正了范围：`write_bytes` 只有两个调用方，artifact sink 还另有一条 `ofstream`，所以受影响的是三类数据，不是一类。

对照已经存在的耐久先例：

- Project I/O writer-lease：`packages/project-io/src/native/storage_platform.cpp` 对文件和目录都 `fsync`。
- Application Facade 离线渲染 staging：写入后 `::fsync` 再 `describe_artifact`。
- `provider-sdk` 的 `write_bytes`：`flush` + `close`，字节只到 kernel page cache。

不对称看起来是遗漏，不是“配置可以更弱”的书面决定。本次把这个决定写进设计：证据付耐久成本，配置不付。

## 3. 范围

### 3.1 做

- 在 `packages/provider-sdk/src/attempt_store.cpp` 增加证据专用 durable 写与目录 sync，不导出新的公开 C++ API。
- `persist_attempt` / `write_new_atomic` 走 durable 写 + `hard_link` 发布 + 父目录 `fsync`。
- Artifact sink 删除独立 `ofstream`，同样走 durable 写；`rename` 到 `staging/artifacts/<sha256>` 后父目录 `fsync`。
- `write_bytes` 与 `write_replace_atomic` 保持现状，专供 `host-settings.json`。
- Native 测试覆盖成功路径、失败不发布、配置路径不升级耐久。
- `provider-sdk` PATCH 与完整 Product Build 级联、current Portal 页、immutable snapshot。

### 3.2 不做

- 不修 G3 锁恢复，不给 `.host-settings.lock` 加 pid / 时间戳 / 过期。
- 不把 `provider-sdk` 链到 `project-io`，不把 POSIX helper 抽到 `foundation`（本次只有这一个调用方，抽公共模块会扩大 SemVer 面）。
- 不改 Attempt JSON 形状、Artifact 身份、Host settings schema、公开错误码语义。
- 不在 Web / OPFS / MEMFS 上做第二套耐久实现。
- 不测真实掉电或 kernel 崩溃；CI 不能证明那个。
- 不关闭 Issue #203（需要单独授权）。

## 4. 写路径

### 4.1 易失路径（不变）

`write_bytes(path, bytes)` 继续：拒绝已存在或 symlink 的目标 → `ofstream` trunc → `write` → `flush` → `close` → 失败则删文件。

`write_replace_atomic` 继续：sibling 临时文件 `write_bytes`，再 `rename` 到 `host-settings.json`。不 `fsync` 文件，不 `fsync` 目录。

### 4.2 证据路径（新增，匿名命名空间，不公开）

```text
reject symlink / existing temp
  -> POSIX open(O_CREAT|O_EXCL|O_WRONLY|O_NOFOLLOW)
  -> write 全部字节（EINTR 重试）
  -> fsync 文件描述符
  -> close
  -> 发布：Attempt 记录 hard_link；artifact rename
  -> fsync 父目录
  -> 删除 temp sibling（hard_link 路径）
```

文件 `fsync` 必须发生在目录项可见之前，避免“名字已经在、内容还是截断”。

目录 `fsync` 失败时 fail-closed：

- `hard_link` 之后：删除已发布名和 temp，返回 `io_error`。调用方看不到半发布 Attempt。
- `rename` 之后：删除已发布名，返回 `io_error`。mint 失败；调用方不得把该 Artifact 算进 minted。

`fsync` / `write` / `open` 失败映射为现有 `ErrorCode::io_error`，带 repo 风格的 path context；不引入新错误码。

Emscripten：调用同一 POSIX 序列。该 libc 上 `fsync` 返回 0 且不刷盘，这是正确语义，不要 `#ifdef` 出第二条写路径。

### 4.3 谁调用哪条

- `persist_attempt` → `write_new_atomic` → durable 写。
- Artifact sink → durable 写 + `rename`；禁止再直接 `std::ofstream`。
- `set_provider_selection` → `write_replace_atomic` → `write_bytes`。

用源码断言钉死这张表，防止下次有人把 settings 接到 durable helper，或把 Attempt 接回 `write_bytes`。

## 5. 测试

平台：native provider 测试。Web 不增加耐久断言。

1. **成功 persist**：执行一次成功或失败的 Proof Attempt，终端 `attempts/<id>.json` 存在、canonical JSON、`inspect` 可读、ledger invariant 仍成立。
2. **成功 mint**：sink 写出的 artifact 在 `staging/artifacts/<sha256>`，`describe_artifact` 与记录一致。
3. **失败不发布**：对 durable helper 抽出的 `sync_descriptor` 用非法 fd 得到 `io_error`（覆盖 `fsync` 失败映射，不需要生产代码里的 test hook）。对只读/冲突目标走完整 persist 或 mint，断言最终路径不出现、temp sibling 被删。
4. **配置不升级**：`spec_regression` 断言 `write_bytes` 函数体不含 `fsync`；`write_replace_atomic` 调用 `write_bytes`；`write_new_atomic` 与 artifact sink 不调用 `write_bytes`。
5. **不测**：真实掉电、内核崩溃、Emscripten 是否真的刷盘。

## 6. Version Management

Version impact: required.

`provider-sdk` 无公开 API 变化，行为从“证据可能在崩溃后截断”变为“native 证据提交前 fsync”。这是 PATCH：`1.1.2` → `1.1.3`。

Assembly 成员版本变化必须分配新 Product Build：`1.0.24.0` → `1.0.25.0`。级联形状与 G1/G4（`1.1.1` → `1.1.2` / `1.0.23.0` → `1.0.24.0`）相同：

- 直接依赖：`application-facade`、`local.proof.success`、`local.proof.failure` 升 PATCH，并钉 `provider-sdk 1.1.3`。
- 经 Facade 传递的 Host / Web Runtime Platform 按现有 lockstep 规则升 PATCH 并更新依赖边。
- `products/lmdj/version.json`、`assembly.json`、compiled assembly、`scripts/version.py lock` 生成的 lock、Runtime identity、gate tables、current Portal 文案。
- `assembly.lock.json` 只允许 `python3 scripts/version.py lock` 生成，禁止手改。

Contract、Capability、Project schema 不变。

## 7. Documentation Impact

Documentation impact: required。

Product Build 与 Assembly 变化禁止 `none`。同一 Task 更新 current 页，并在授权的 implementation 步骤用

`scripts/architecture-portal.sh version 1.0.25.0 CHANNEL`

做 immutable snapshot（CHANNEL 按当时发布通道，不在本设计里选定）。

Affected portal pages:

- `/core/modules/provider-sdk/` — Attempt 记录与 minted artifact 的 native 耐久；Host settings 明确非耐久。
- `/providers/overview/` — 失败归属 Attempt 现在有与 Project Truth 同级的 native 落盘承诺。
- `/product/capability-map/`、`/operations/version-and-release/`、`/assembly/lmdj/` — 仅加法记录 `1.0.25.0` 级联原因；不改写 `1.0.24.0` 及更早证据。

不改 `project-io` 存储页：那是 Project Truth / lease，不是 Attempt Store。

## 8. 验收

Implementation 完成当且仅当：

- Native 上成功 Attempt 的终端记录与 minted artifact 在返回成功前已经文件 `fsync` 且父目录 `fsync`。
- 任一 durable 步骤失败都不会留下最终路径或残留 temp sibling。
- `host-settings.json` 仍走 `write_bytes`，源码断言锁住。
- 公开 API、错误码、JSON 形状不变。
- `provider-sdk 1.1.3` 与 Product Build `1.0.25.0` 级联一致，Portal current 页与 snapshot 同步。
- 计划与最终报告写明：未证明真实掉电；G3 仍开放。
