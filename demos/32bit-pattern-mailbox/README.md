# 32-bit Pattern mailbox experiments

独立 Python 3.9+ 顺序一致（SC）有限模型，不导入 Core、不改变产品协议。

```bash
python3 demos/32bit-pattern-mailbox/model.py
python3 demos/32bit-pattern-mailbox/boundary_test.py
```

## 两个不同的证明问题

1. **Claim 进度。** 把一次 fetch_or 分解成底层无无故失败的 CAS 循环，允许
   三次串行控制替换任意插入。对照不设 admission 与音频单方关闭 admission 的
   模型。控制每次修改前必须重新检查；音频不等待控制确认，空 Q 也经过清空与
   重新开放出口。只读等待自环不重复枚举，但不会跳过被挡住的修改操作。
2. **Cancel/activate 所有权。** 从音频已认领并持有完整 64 位 generation 的
   entry 开始，穷举取消 CAS 与激活 CAS、音频最终处理、控制回收和同槽新
   generation 复用。验证唯一胜者，激活后 current 不回收，取消后由音频释放
   才允许回收。错误变体让控制在取消成功后立即回收，必须被检测出来。

SC admission 的一般顺序论据：音频关闭后，在它重新开放之前的控制检查不能
看到开放值；而关闭前已经通过检查、尚未执行修改的操作最多一个，因为控制自身
串行。音频因此最多受到该操作的一次成功修改干扰，不要求这个控制线程及时恢复。
这是条件式论据，不是把有限的三次尝试扩大成穷举所有执行。

## 仍未证明

- 不是弱内存模型；admission 与 Q 的跨原子排序仍须匹配这个 SC 前提。
- 模拟的是无无故失败、失败后更新预期值的 CAS，不涵盖 LL/SC 中断、cache 或
  调度时延，不能称为目标 wait-free 或实时 deadline 证明。
- 两个模型彼此独立，不能相乘当成完整协议的证明。queued replace/cancel 与
  claim 的全链、Q→A 交接、跨多轮 admission 的旧在途操作、真实槽 payload
  内存序、完整 authority 三元组、帧 boundary 与 Transport 仍需验证。
- Cancel 模型用不可变旧 generation 和有效 authority 的前提隔离回收竞态，
  不模拟错误用户 authority 校验，也不模拟活动 Voice 的退役生命周期。
- 不包含 C++ Pattern 实现、TSan、ESP-IDF 构建或真机实验。

这两个实验用于检验设计候选，不授权接入 Engine，也不替代原有 Core stress 测试。

## 本轮结果（2026-09-08）

运行上述命令退出 0：

| 初始 Q | admission | 去重状态 | 最大音频 CAS 失败次数 | 终态 |
| --- | --- | --- | --- | --- |
| 空 | 无 | 289 | 3 | 22 |
| 空 | 有 | 139 | 1 | 10 |
| 非空 | 无 | 291 | 3 | 22 |
| 非空 | 有 | 141 | 1 | 10 |

取消/激活/回收模型为 38 个状态，两种胜者与安全槽位复用均可达。立即回收的
错误版本以 `control reclaimed an audio-owned slot` 被拒绝。

## 帧边界与跨通道顺序

`boundary_test.py` 保存六项缩减检查（不是完整 Engine 模型）：

- 现有 `publication_claim_race_preserves_the_claimed_boundary_and_phase` 场景：
  callback 从 95,999 开始，长度 2；待激活 Pattern 的起点为 96,000，bar 长度
  128,000。控制应读取 callback 开始时推进的前沿 96,001，安排到 224,000。
  若仅在 callback 尾发布 Transport，旧前沿 95,999 会错误算出 96,000。
- 源码 `apply_published_pattern` 先更新 origin，再清 audio-pending descriptor。
  候选 Transport 也必须在清 A 的 release 前发布 origin。检查明确枚举反例：
  清 A → 控制看见 A 空 → 控制仍读旧 origin → 音频才发布新 origin。
- Claim 交接必须先发布 A 再清 Q；空 Q 的 claimed 标志不代表有效槽位或身份。

对照源码：`packages/audio-runtime/src/realtime_engine.cpp` 的
`render`、`apply_published_pattern`、`publish_pattern_view_impl`，以及
`tests/core/audio/realtime_engine_test.cpp`。检查基线是实验分支父基线
`694b983b3a6b9de7be780d1399072b9b2afdf5cc`；本轮未运行产品测试，未宣称
已经重现产品缺陷。错误的是上述候选变体，不是现有源码。

2026-09-08：六项缩减检查通过。跨域 release/acquire 的真实 C++ 实现、完整
控制重试与 authority 校验仍需后续验证；数字样例和 SC 合并顺序不证明它们。
