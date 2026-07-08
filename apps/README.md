# apps/

正式产品应用入口放在这里。

当前规划：

- `apps/web/`：LMDJ Web App。负责 idea input、song upload、job progress、Patch View、render/share/remix 入口。已落地：Patch View 工作台原型（消费 `patch.json`，见 `apps/web/README.md`）。
- `apps/api/`：LMDJ App Backend。早期建议是模块化 monolith，对 Web 和 CLI 暴露同一套产品 API。

约束：

- 不从 `references/demos/` 继承目录结构或 API 形态。
- Web / CLI / API 共享 LMDJ 自己的 `Project / Patch / Pad / Scene / Element` 产品对象。
- 音频、生成、渲染重任务不在 Web 或同步 API request 中执行。
