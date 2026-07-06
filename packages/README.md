# packages/

正式产品共享 package 放在这里。

当前规划：

- `packages/core-models/`：LMDJ 产品对象与序列化 contract，例如 `Project`、`Patch`、`Pad`、`Scene`、`Element`、`Render`、`Lineage`。
- `packages/patchify/`：Patchify Core。把 idea / audio pipeline package 转成 LMDJ-owned `patch.json` 和后续可持久化对象。

约束：

- `packages/patchify/` 是正式源码，不写入 `references/demos/lmdj-song-pipeline/`。
- 可以读取参考 pipeline 的输出 contract，例如 `samples/*.wav`、`chart.mid`、`lanes.json`、`report.json`。
- 不默认继承参考 demo 的 package contract、CLI、API、状态模型或目录结构。
