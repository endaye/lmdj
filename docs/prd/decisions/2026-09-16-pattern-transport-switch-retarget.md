# 已确认：Pattern transport 绑定在 applied switch 后重锚到引擎当前 Pattern

- 日期：2026-09-16。
- 关联：GitHub issue #1403（#1370 的后续，#1230 家族）；本条确认其
  "switch 后重锚" 问题的处置方向（选项 1：retarget）。

## 结论

1. Facade Pattern transport 协调器在打开新 journal 的 Record 请求上，先把
   vendored 的 Pattern 绑定重锚到引擎当前 Pattern（两者不同时）：journal
   的 begin、admission preparation 与后续 fence 都以引擎当前 Pattern 命名，
   Record-after-applied-switch 直接可用，不再触发确定性的
   `invalid admission fence authority` 把 engagement 停进 `error` 相。
2. 重锚信息来自端口新增的
   [`PatternTransportAudioPort::current_pattern()`](../../../packages/application-facade/include/lmdj/facade/pattern_transport_controller.hpp)：
   返回 `std::nullopt` 表示没有重锚信息（引擎没有当前 Pattern 或端口不
   知道），协调器保持 vendored 绑定——此时越身份改换仍按 #1370 的确定性
   失败停机语义处理。默认实现返回 `std::nullopt`，既有端口实现与测试
   fixture 不需要改动。
3. journal 活跃（录制中）时永不重锚：跨 switch 的结清仍由既有 close 机制
   （`retain_switch` / `reconcile_switch` / `drain_source_prefix` /
   `drain_target_segment`）拥有，本决策不改变那条路径。
4. #1370 的 playing 状态越身份 `snapshot.reload` 拒绝保持不变：重锚只覆盖
   "switch 已在 Bar 边界应用、transport 仍在播放" 的情形。

## 原因

- 协调器在 vending 时绑定 Pattern 且永不重锚，而引擎的当前 Pattern 可以
  在 playing 状态下经 switch 发布在 Bar 边界易主；此后第一次 Record 的
  admission fence 以 receipt 的 Pattern（新）命名，preparation 以绑定
  Pattern（旧）命名，`fence_valid` 确定性失败，engagement 停进 `error`
  相后只能重开 Project 恢复——会话中 playing 录制实际上不可用。
- 三个选项（重锚 / 诚实拒绝 / 混合）是产品级取舍，#1370 刻意未在本任务
  内定夺；选项 1 让 Record-after-switch 直接工作，与引擎的接收语义一致
  （fence 永远以当前 Pattern 命名），且不削弱任何既有不变量：fence 与
  preparation 的身份一致性仍然由 `fence_valid` 机械校验。
- 诚实拒绝（选项 2）把可恢复的常规操作变成用户可见的失败，且需要新增
  恢复面；混合（选项 3）在 switch 应用前的静止点重锚与选项 1 在打开
  journal 时重锚等价，但多引入一个时序概念。

## 影响

- `application-facade` 公开端口新增一个纯追加的默认方法，Module SemVer
  MINOR 升到 `6.1.0`；依赖它的模块与 Host 只做依赖 pin 跟随的 PATCH
  级联，Product Assembly 分配 Build `1.0.59.0`。
- 回归钉在两层：Facade 层
  （`tests/core/facade/pattern_transport_controller_test.cpp` 的
  `record_after_an_applied_switch_retargets_the_bound_pattern` 与负例
  `applied_switch_mid_recording_settles_through_the_close_path`）与 Host 层
  （`packages/web-runtime-platform/test/control_runtime_test.cpp` 的
  `test_transport_record_after_applied_switch_retargets`）；端口不报当前
  Pattern 时的确定性停机行为由
  `deterministic_fence_mismatch_parks_the_engagement_in_error` 保留。
