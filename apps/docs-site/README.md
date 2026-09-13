# LMDJ Docs

LMDJ 文档站：使用与开发说明、架构和交付规范的发布源码。
现包含 Host prepared 日志及 Product release 日志投影；没有公开回执的版本不会补造日志。
构建需要 Node 22 和 Python 3.11+：Product 日志复用 Python Release renderer，避免两端正文漂移。

```bash
scripts/docs-site.sh install
scripts/docs-site.sh dev
scripts/docs-site.sh check
```

经审查的公开记录更新后，在本目录运行 `npm run release-changelogs` 生成版本页和索引。
新版本页需在同一 Task 同步快照的独立页数清单；生成器拒绝覆盖既有版本页。
生产仍由正常 Git-triggered workflow 发布，生成成功不代表网站已上线。

旧命令 `scripts/architecture-portal.sh` 兼容转发到新命令。

## 历史快照存储

`apps/architecture-portal/` 仅保留不可变快照和版本目录，不再是可运行项目。
本目录通过相对符号链接读取这些存档；Git 中的原路径、文件字节和来源证明保持不变。
后续冻结仍使用该稳定存储位置，但源文档与站点实现来自 `apps/docs-site/`。
不要批量重写旧快照、来源哈希或已发布版本中的历史路径。

CI lane、工作流文件名、Cloudflare Environment 与 Worker 身份保留兼容名称；
构建输入已指向本目录。项目重命名不授权远端资源重建或部署。
