# Build Manifest 是随归档内嵌，还是与归档并列 detached 发布？

- 范围：新内核（Playable Beat Instrument）
- 状态：待决
- 来源：[2026-07-30 新内核设计](../../superpowers/specs/2026-07-30-lmdj-playable-beat-instrument-core-redesign.md)评审
- 为什么重要：`create_zip()` 已固定时间戳、排序与文件模式以求可复现，但 `build-manifest.json` 在归档内且含 `build_time`，于是同一源码每次打包的 ZIP 字节都不同，"下载方自行重建并比对 hash"无法实现。`build_time` 是 version-management.md §4 明文要求的，所以这不是实现缺陷，而是两个都正确的要求装进了同一个容器。选项：manifest 改为 detached 并列发布；或从归档内剔除可变字段并保留 detached 副本；或接受不可复现并明确放弃该验证手段。这会改变已发布产物的形态。
- 处理时点：首个对外分发（进入 `dev` 及以上 Channel）之前的发行治理评审。
