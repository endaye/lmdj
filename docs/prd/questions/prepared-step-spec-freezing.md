# 一键发版的 `prepared` / `tag` 步骤如何在写入前冻结 spec？

- 范围：Release 控制面，一键发版驱动（M1 完整入口）
- 状态：开放
- GitHub Issue: [#1404](https://github.com/endaye/lmdj/issues/1404)
- 为什么重要：这两步的 spec 绑定 `plan_sha256` 与 `tag_object_id`，而两者都由 `prepare()` 自己产出
  —— 它先创建签名本地 tag，再用该 tag 状态生成计划文档并算出摘要。仓库没有写入前的投影 API，intent
  账本 42 行也不记录计划摘要，注解 tag 的对象 id 因签名含时间戳而不可预知。因此按现状这两个 spec 是
  结果绑定的：只能验证一个已 prepare 的发布，尚未 prepare 的请求会让这两步永远停在 `pending`，
  `release.sh run` 无法走完 14 步，M1 的「一条命令走完全链」在这两步上不成立。
- 候选方向：
  1. 这两步在驱动里只做验证：写入继续由既有的 `release.sh prepare` / `push-tag` 承担，`run` 在未
     prepare 时如实停在 `pending` 并提示。代价是一键语义不完整。
  2. 收窄 closed spec 契约：只绑定写入前可知的值（tag、target、signer，以及新增干跑投影得到的预期
     计划摘要），`tag_object_id` 改为 advance 后用本步产出核对。需要改动 `prepared_step` /
     `tag_step` 的 spec 与其校验。
  3. in-advance 两阶段：carrier 先驱动 prepare，再用其产出冻结并核对 spec；等于承认 spec 结果绑定，
     需要说明 reviewed intent 究竟绑定了什么。
- 处理时点：M1 收尾之前（剩余登记切片里 `prepared` 与 `tag` 相邻），不阻塞 `intent` / `changelog` /
  `promotion` 的登记。
