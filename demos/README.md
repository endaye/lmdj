# Demos

统一存放独立 demo、实验和原型，方便集中管理。源码纳入 Git 版本管理，
允许持续迭代、暂停和长期保留；不是冻结档案，也没有必须删除的期限。
不另设 `experiments/` 或 `prototypes/` 平行目录。

## 管理边界

- 项目独立运行，不依赖 LMDJ 底层实现；正式产品代码也不得依赖这里的代码。
- 不属于正式产品构建、打包或发布输入。每个项目自带运行、依赖与验证说明，按需单独测试。
- 源码、必要配置、依赖锁文件和可复现验证脚本提交 Git；本地环境、构建输出、缓存和密钥不提交。
  各项目按需补充精确的 `.gitignore`，不要忽略整个项目。
- CI 将本目录归入 `docs_static`，不代表 demo 的功能或硬件验证已经通过。
- demo 的格式和结论不自动成为产品 Contract。进入正式产品的能力应另开任务，遵守当前架构与测试规范，不得恢复退役 Contract。
- 新增项目放在 `demos/<project-name>/`，并在这里登记用途和说明入口。

## 项目

| 项目 | 用途 | 说明 |
| --- | --- | --- |
| `ascii-matrix-camera` | 黑绿 ASCII、摄像头输入与视觉互动探索 | [README](ascii-matrix-camera/README.md) |
| `launchpad-pad-exploded` | Pad 控制器 3D 爆炸图与传感方案；几何为示意重建 | [README](launchpad-pad-exploded/README.md)、[研究来源](launchpad-pad-exploded/RESEARCH.md) |
| `lmdj-song-pipeline` | 高嘉丰提供的音频生成、分轨、loop finding、切片、MIDI 与 validation 参考工具 | [README](lmdj-song-pipeline/README.md)、[使用说明](lmdj-song-pipeline/SETUP_AND_USAGE.md) |

## 路径迁移

2026-09-08 将 `references/demos/<project-name>/` 整体迁到 `demos/<project-name>/`，
保留项目源码、素材和 Git 历史。历史计划、发布证据和不可变门户版本中的旧路径保持原样；
查阅其当前项目时，去掉路径开头的 `references/` 即可。迁移没有恢复任何旧产品架构。
