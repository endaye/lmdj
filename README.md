# LMDJ

LMDJ 当前是一个脑暴与 PRD 快速迭代工作区。这里先沉淀素材、问题、决策和工作版 PRD，再逐步收敛到可执行方案。

## 项目结构

```text
lmdj/
├── apps/                    # 正式产品应用入口：web / api
├── docs/                    # PRD 迭代、素材、决策与开放问题
├── packages/                # 正式共享 package：core-models / patchify
├── references/              # 不纳入正式产品的参考素材和 demo
│   └── demos/
│       ├── ascii-matrix-camera/
│       └── lmdj-song-pipeline/
├── workers/                 # 正式异步 worker：audio / generation / render
├── AGENTS.md                # Codex 协作说明
└── CLAUDE.md                # Claude Code 协作说明
```

## 文档入口

- [docs/README.md](docs/README.md)：文档系统总览与脑暴阶段工作流。
- [docs/prd/working-prd.md](docs/prd/working-prd.md)：当前工作版 PRD，允许快速改写。
- [docs/prd/source-materials.md](docs/prd/source-materials.md)：外部输入、demo、参考资料和素材索引。
- [docs/prd/open-questions.md](docs/prd/open-questions.md)：待讨论问题池。
- [docs/prd/decision-log.md](docs/prd/decision-log.md)：已经确认的产品/技术决策。
- [references/README.md](references/README.md)：参考素材和 demo 的边界说明。
- [references/demos/lmdj-song-pipeline/README.md](references/demos/lmdj-song-pipeline/README.md)：高嘉丰参考项目的快速上手和接口说明。

## 当前定位

`references/demos/` 里的项目都是参考素材，不纳入正式产品源码边界。`lmdj-song-pipeline` 是高嘉丰给到的可运行参考项目和技术素材库；`ascii-matrix-camera` 是视觉互动方向的小 demo。它们的价值是提供技术和体验证据，后续正式系统需要在独立 app / package / worker 中定义自己的边界。

正式产品源码从 `apps/`、`packages/` 和 `workers/` 开始沉淀。Patchify 后续应作为 LMDJ-owned package 重写在 `packages/patchify/`，可以读取参考 pipeline 的输出，但不在 `references/demos/lmdj-song-pipeline/` 内继续追加正式功能。

```text
PRD 素材
  -> 工作版 PRD
  -> 开放问题
  -> 决策记录
  -> 原型 / 技术验证
```

## 脑暴阶段原则

- 素材不等于定稿：高嘉丰 PRD、demo 工具、外部参考都先进入素材池。
- 工作版 PRD 可以频繁变化：先保证观点清楚，再追求完整。
- 决策单独记录：一旦确认，就写进 decision log，避免反复讨论。
- 问题显式管理：未定问题进入 open questions，不在正文里含糊带过。

## 本地开发脚本

根目录一键脚本 `scripts/dev.sh`（任意位置可执行）：

```bash
scripts/dev.sh all                  # setup + 全部测试 + 端到端冒烟
scripts/dev.sh test                 # core-models + patchify 测试
scripts/dev.sh patchify <包目录>     # 对 pipeline package 生成 patch.json
scripts/dev.sh song <音频> <id>      # demo pipeline 处理一首歌并 patchify（需先 setup-demo）
scripts/dev.sh smoke                # testsong → patch.json → 摘要
```

## Demo 工具常用命令

需要跑高嘉丰 demo 时，在 `references/demos/lmdj-song-pipeline/` 内执行：

```bash
cd references/demos/lmdj-song-pipeline

python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m pytest tests/ -q

.venv/bin/song-pipeline run input.mp3 --song-id mysong --fast
.venv/bin/song-pipeline gen --bpm 85 --style "lofi hiphop beat" --seconds 30 --seed 42 --fast --run
.venv/bin/song-pipeline serve --port 8000
```

本地开发默认带 `--fast`，除非明确需要更慢但更准的 `htdemucs_ft`。
