# References

这个目录存放 LMDJ 脑暴、技术验证和视觉探索阶段的参考材料。

这里的内容 **不纳入正式产品源码边界**。它们可以被阅读、运行、拆解、迁移或作为 fixture 使用，但不默认决定 LMDJ 的最终目录结构、服务边界、API、数据模型或产品 contract。

## demos/

### ascii-matrix-camera

视觉互动 demo。当前价值是参考黑底绿色 ASCII、摄像头输入和动态视觉气质。

使用时先进入：

```bash
cd references/demos/ascii-matrix-camera
python3 -m http.server 4173
```

### launchpad-pad-exploded

主流 pad 控制器（Akai MPC、Novation Launchpad、Ableton Push 3、NI Maschine）
pad 机构的 3D 爆炸图与传感技术方案。当前价值是参考：

- 整机与单 pad 两种比例的分层爆炸视图。
- 胶粒 / FSR 薄膜 / 压电 / 双触点 / 电容 / 霍尔 / 电感七类传感方案的取舍。
- 带出处的单 pad 工程参数（FSR 数据手册、硅胶键垫设计指南、备件目录、专利）。
- FSR 分压 → ADC → Δt 速度的敲击模拟。

使用时先进入：

```bash
cd references/demos/launchpad-pad-exploded
python3 -m http.server 4173
```

注意：3D 几何为示意性重建，标为"示意"的数值没有一手出处。

### lmdj-song-pipeline

高嘉丰提供的音频 pipeline 参考项目。当前价值是参考：

- 音频生成 / 上传后的处理链路。
- Demucs 分轨。
- loop finding。
- sample slicing。
- MIDI chart 和 `lanes.json` 输出。
- validation 和测试 fixture。

使用时先进入：

```bash
cd references/demos/lmdj-song-pipeline
```

注意：

- 可以复用其中的能力和代码片段。
- 不默认继承它的 package contract、API、CLI、状态模型或目录结构。
- LMDJ 正式系统应围绕自己的 `Patch / Pad / Scene / Element` 产品对象设计。
