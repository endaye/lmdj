# 已发布的 prerelease Build 如何晋级到 `stable`？

- 范围：Release 控制面，Channel promotion
- 状态：开放
- 为什么重要：`docs/governance/version-management.md` §3 允许同一 Build 从 `canary` 晋级到
  `stable`，且晋级不移动 tag、不生成新 Build。发布管线设计 D6 规定 `stable` 的 GitHub Release
  是 `prerelease=false`，而 D8 规定已发布 Release 不可变，正常工具拒绝切换 `prerelease`。
  一个以 `canary`/`dev`/`beta` 发布的 Release 因此无法在不违反 D8 的前提下满足 `stable` 的
  Release 形态。Channel promotion 机制（Issue #572）已实现 `dev` 与 `beta`，并对 `stable`
  明确拒绝，等待本问题裁决。
- 候选方向：
  1. 晋级只改记录，Release 的 `prerelease` 永远反映发布时的 Channel；`stable` 只能由一开始就以
     `stable` intent 发布的 Build 获得，等于 `stable` 需要新 Build。这与 §3"同一 Build 可晋级到
     `stable`"冲突，需要修订 §3。
  2. 为 promotion 开一个 D8 的显式例外：`promote TAG stable` 是一次单独授权的 Release mutation，
     只允许把 `prerelease` 从 `true` 改为 `false` 并按 ledger 显式字段设置 `latest`，其他字段与资产
     仍不可变，并在 audit 中以记录的晋级时间解释这次改动。需要修订 D8 与 `_release_problem` 的
     prerelease 比对逻辑。
  3. `stable` 不再映射到 `prerelease=false`，改用 Release 名称或 body marker 表达 Channel。需要修订
     D6 与 Channel 映射表。
- 处理时点：M1 之后、首个 Build 需要进入 `beta` 之前；M1 的 `max_channel` 是 `dev`，本问题不阻塞
  当前发布。
