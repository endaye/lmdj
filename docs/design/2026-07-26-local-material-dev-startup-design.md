# Local Material Pipeline Dev Startup 设计

状态：设计讨论已批准，书面 Spec 待用户复核

日期：2026-07-26

## 1. 背景

Material Pipeline V1 已实现并合并到 `main`，但本地 `scripts/dev.sh dev`
启动的 API 没有显式设置 `LMDJ_PIPELINE`，因此应用使用生产安全默认值
`legacy`。当前 `ensure_dev_dependencies` 也固定检查冻结 demo venv，而不会检查
Material Pipeline 所需的 API DSP 依赖和 HT Demucs runner venv。

结果是：Creator Workbench 已有 16 个数据位置，但本地上传仍生成 legacy Patch，
把 Kick、Snare、Hat 聚合为一个 Drums Pad。

## 2. 目标

- `scripts/dev.sh dev` 在本地默认启动 `materials-v1`；
- 用户仍可通过 `LMDJ_PIPELINE=legacy scripts/dev.sh dev` 显式启动旧链；
- 不修改 `apps/api` 的生产默认值；
- 提供一个可重复执行的 `scripts/dev.sh setup-materials`，准备本地 Material
  API 与 HT Demucs 依赖；
- `dev` 启动前按实际选择的 pipeline 校验依赖并给出准确修复命令；
- 启动完成后打印实际 Pipeline、Separator 和 Device；
- 本次准备环境或验证时不替用户重启当前服务器。

## 3. 方案比较

### 方案 A：修改 API 全局默认值

把 `runner_from_env()` 的缺省值从 `legacy` 改为 `materials-v1`。该方案会同时改变
本地、部署和未显式配置的运行环境，提前绕过尚未完成的生产晋升门槛，因此拒绝。

### 方案 B：每次要求用户手写环境变量

保留所有代码不变，要求每次使用：

```bash
LMDJ_PIPELINE=materials-v1 scripts/dev.sh dev
```

该方案不会误改生产，但容易再次忘记，且不能解决 DSP 和 Separator 环境缺失，
因此拒绝。

### 方案 C：本地 dev 显式默认 Material（采用）

只在 `scripts/dev.sh dev` 边界将未设置的 pipeline 解析为 `materials-v1`，并把
解析后的值显式传给 API 子进程。应用自身仍默认 legacy。配套增加
`setup-materials` 和 pipeline-aware preflight。

## 4. 命令行为

### 4.1 `setup-materials`

`scripts/dev.sh setup-materials` 必须幂等完成：

1. 创建或复用 `apps/api/.venv`；
2. 按顺序安装 editable `core-models`、`patchify`；
3. 使用 `workers/audio/config/parity-constraints.txt` 安装
   `workers/audio[pfs]`，让 API 进程具备 Timing 与 Material Extractor 的
   `numpy / soundfile / librosa / scikit-learn / pretty_midi` 依赖；
4. 安装 editable `apps/api`；
5. 复用现有 `setup-sep-demucs` 建立隔离 HT Demucs runner venv；
6. 验证 API venv 可以导入 `CreatorPipelineRunner` 和 DSP 模块；
7. 验证 registry 中默认 HT Demucs command 的 Python 可执行文件存在。

命令只准备环境，不启动 API 或 Web，也不处理用户上传。

### 4.2 `dev`

`scripts/dev.sh dev` 解析：

```text
LMDJ_PIPELINE 未设置  → materials-v1
LMDJ_PIPELINE=materials-v1 → materials-v1
LMDJ_PIPELINE=legacy       → legacy
其他值                      → 启动前失败
```

Material 分支默认使用：

```text
LMDJ_SEPARATOR_ID=htdemucs
LMDJ_SEPARATOR_DEVICE=mps
```

用户显式设置的 Separator ID 或 Device 优先。解析后的 Pipeline、Separator 和
Device 必须作为环境变量传给 API 子进程。

本地使用 MPS 是为了避免当前 Mac 默认落到耗时的 CPU 分离；这不修改 API 类或
部署环境的默认值。

## 5. 依赖校验

公共校验继续检查：

- API Python 与 uvicorn；
- API package 存在性 probe 固定使用 `LMDJ_PIPELINE=legacy`，避免在所选
  pipeline 的专项校验前构造 Material runner；
- Web Vite 与 npm；
- curl。

随后按 pipeline 分支：

### materials-v1

- API venv 可以导入
  `numpy / soundfile / librosa / sklearn / pretty_midi`；
- API venv 可以导入 `CreatorPipelineRunner`；
- 默认或显式 Separator 必须能从 registry 解析；
- registry command 对应的 runner Python 必须存在；
- Material DSP 或默认 HT Demucs runner 缺失时指向
  `scripts/dev.sh setup-materials`；
- 支持的非默认 Separator runner 缺失时分别指向所选 ID 对应的
  `setup-sep-scnet`、`setup-sep-bs-roformer` 或
  `setup-sep-mel-roformer`；
- 未知 Separator ID 或不支持的 Device 保留 registry 专项错误，不回退为通用
  API 环境提示。

### legacy

- demo venv Python 和 `song-pipeline` 存在；
- demo venv 可以导入 torch 与 demucs；
- 失败信息继续指向 `scripts/dev.sh setup-demo`。

Material 启动不再要求 demo venv；legacy 启动也不要求 Material DSP 或 Separator
venv。

## 6. 启动输出

就绪输出至少包含：

```text
==> LMDJ local dev ready
    Web: http://localhost:5173
    API: http://localhost:8000
    Pipeline: materials-v1
    Separator: htdemucs
    Device: mps
```

legacy 模式显示 `Pipeline: legacy`，Separator 和 Device 显示为不适用。

## 7. 错误处理

- 非法 `LMDJ_PIPELINE` 在创建子进程前失败；
- Material 依赖不完整时不尝试启动任一服务；
- Separator registry 条目缺失或 runner venv 不存在时不启动服务；
- setup 命令任何 pip 或 runner 安装失败都返回非零；
- API 或 Web 在运行期间退出时，沿用现有双子进程清理规则；
- 不在 Material 失败后静默启动 legacy。

## 8. 测试

扩展 `scripts/tests/test_dev_command.sh`，覆盖：

- 未设置 pipeline 时默认 `materials-v1`；
- 默认值传入 API 子进程；
- 默认 Separator 为 `htdemucs / mps`；
- Material 缺少 API DSP 依赖时失败并提示 `setup-materials`；
- Material 缺少 Separator runner 时失败；
- Material 模式不要求 demo venv；
- 显式 legacy 仍要求 demo venv；
- 显式 legacy 不要求 Material 依赖；
- 非法 pipeline 启动前失败；
- ready 输出包含实际 Pipeline、Separator、Device；
- 既有 TERM/HUP 和子进程退出清理测试继续通过。

为 `setup-materials` 增加 shell fixture 测试，使用 fake Python/pip 和 fake registry
runner，验证命令顺序、幂等入口和失败传播，不在 CI 下载真实 Demucs。

验证命令：

```bash
bash scripts/tests/test_dev_command.sh
bash scripts/tests/test_creator_smoke.sh
scripts/dev.sh test
```

实现完成后，在主 checkout 运行真实 `scripts/dev.sh setup-materials`，再执行只读
import/runner readiness 检查。当前 API/Web 服务保留给用户自行重启。

## 9. 非目标

- 不把 production API 默认 Runner 晋升为 Material；
- 不运行固定曲库、盲听、实体 MIDI 或 Ableton 发布证据；
- 不自动启动或重启本地服务器；
- 不删除 legacy pipeline；
- 不改变 Material 提取算法、质量门槛或 16 槽契约。
