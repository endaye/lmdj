# Maks Surguy 的 ESP32 多屏同步生成艺术装置

> 日期：2026-09-06
>
> 对象：Maks Surguy（[@msurguy](https://x.com/msurguy)）2026-09-04 发布的多块
> ESP32 彩屏「触摸同步无限画布」演示
>
> 文档性质：外部硬件/交互调研。不是已批准的产品范围、Contract、硬件选型、
> 实施计划或排期承诺。
>
> 证据边界：基于公开推文、作者自报购买链接、官方板卡规格、以及对该 33 秒
> 视频逐帧观察。作者未开源该固件；同步协议、渲染器和镜头模型均为推断，
> 文中按置信度标注。未做真机复刻、烧录或延迟测量。

## 0. 结论先行

这是一套 **多块廉价 ESP32 彩屏共享同一张程序化无限画布** 的装置，不是一块
会播动画的电子相框。

圆形触摸屏是输入主机。手指拖、捏之后，四块方形小屏几乎同时跟上同一幅
低多边形/彩绘玻璃图案。同步的不是像素，而是 **镜头状态**：每块板用同一个
seed 和同一个 camera 在本地把当前可见格子画出来。

对 LMDJ 的可借鉴点是交互与同步模式，不是把这些板子当成音频 Runtime：

| 可能用途 | 判断 | 说明 |
| --- | --- | --- |
| 多块 ESP32 视觉伴侣 / Pad 状态灯 / 可视化从机 | 模式可借鉴 | 只广播很小的共享状态，各板本地渲染，带宽和内存都可控 |
| T-QT Pro 或 1.75" 圆屏上跑当前完整 Core | 不可行 | 与已有 ESP32 评估一致：内存、音频 IO、产品范围都不匹配 |
| 把「每块屏是大画布上的一扇窗」做成演奏可视化墙 | 未验证，值得记一笔 | 作者目前是所有屏看同一视口；评论建议的拼墙是下一步，不是现成能力 |

本仓库已有
[ESP32 Core 可行性评估](2026-08-27-esp32-core-feasibility-assessment.md)
与
[Cardputer Adv 评估](2026-09-03-cardputer-adv-feasibility-analysis.md)。
本文不替代它们，只补充一条 **多设备视觉同步** 的外部样本。

## 1. 来源

主帖：

- 作者：Maks Surguy（[@msurguy](https://x.com/msurguy)），generative / plotter
  艺术家，前 Amazon Design Technologist
- 链接：<https://x.com/msurguy/status/2095686740384395713>
- 时间：2026-09-04 01:33 UTC
- 视频：33 秒，1080×1098，无台词
- 原文：从 Claude Code meetup 坐公交回家的路上，把 ESP32 触摸屏接到已有的
  mini art displays 上，「Now they're all in sync via touch」

作者后续自报硬件（以这条为准，不要靠外形猜）：

- 圆屏：Waveshare AMOLED 1.75
  <https://x.com/msurguy/status/2095910459987914991>
- 小屏 Amazon ASIN `B0BG7YHTJL`：
  [LILYGO T-QT Pro](https://www.amazon.com/LILYGO-ESP32-S3-GC9107-Display-Development/dp/B0BG7YHTJL)
  （0.85" 128×128 正方形，不是 T-Dongle-S3）

相关作者上下文：

- 2026-04：已把生成艺术 / shader 引擎移植到 ESP32，复位出新图
- 2026-07：开源 [`triangles`](https://github.com/msurguy/triangles)，确定性
  Delaunay 低多边形背景，同一 seed 任意分辨率结果一致
- 同帖回复 [@steveruizok](https://x.com/steveruizok)（tldraw）：
  「infinite canvas achieved」
- 评论建议做成「每块屏是巨大画布上的小视口」；那是建议，不是当前行为

## 2. 视频里实际在发生什么

地毯上：一块黑色圆形触摸屏，USB-C 从侧面出来。

手里：四块 USB-C 小方屏。其中一块边框印有 `LILYGO`。有的经 USB-A 转接头供电。

行为：

1. 手指在圆屏上拖 / 点 / 捏。
2. 圆屏上的几何色块放大、平移、变成更大的多边形。
3. 四块小屏几乎同步显示同一构图，不是四段不同动画。
4. 放大时色块变大，不是把位图拉糊；平移时新色块从边缘进入。

当前所有屏幕看的是 **同一个视口**。还不是拼墙。拼墙只需要给每块板一个固定
viewport offset，渲染器不必换。

## 3. 硬件（已核对）

T-QT Pro 是 **开发板**，不是外接显示器。USB-C 只供电和烧录；画面由板上
ESP32-S3 自己画。

### 3.1 触摸主机：Waveshare ESP32-S3-Touch-AMOLED-1.75

视频形态对应带壳的 `-B` 变体。

| 项 | 值 |
| --- | --- |
| 产品 | [ESP32-S3-Touch-AMOLED-1.75](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.75) |
| MCU | ESP32-S3R8，双核 LX7 @ 240 MHz |
| 内存 | 8 MB PSRAM + 16 MB Flash |
| 屏 | 1.75" 圆 AMOLED，466×466，CO5300，QSPI |
| 触摸 | CST9217，I2C，电容，至少两点 |
| 其它 | AXP2101 PMIC、QMI8658 IMU、RTC、Wi-Fi / BLE |

圆屏分辨率高、有 PSRAM、有电容触控，适合当 **输入主机 + 高密度视口**。

### 3.2 从机：LILYGO T-QT Pro，不是 T-Dongle-S3

早期分析曾把 ASIN `B0BG7YHTJL` 误认成 T-Dongle-S3（0.96" **160×80** 长条屏、
USB-A 公头）。视频否掉了这个判断：

- 小屏是 **正方形**，不是 2:1 长条。
- 接口是 **USB-C 母座**（可再转 USB-A），不是 T-Dongle 那种 USB-A 公头棒。
- 一块板的边框能读到 `LILYGO`，与 T-QT 外观一致。
- 作者给出的 ASIN 商品名就是
  「LILYGO T-QT ESP32-S3 0.85 inch GC9107 … (T-QT Pro)」。

| 项 | T-QT Pro（视频里的小屏） | T-Dongle-S3（易混淆，未使用） |
| --- | --- | --- |
| 形态 | 约 33×18 mm 小板，USB-C | USB-A 公头 dongle |
| 屏 | 0.85" **128×128 正方形** IPS | 0.96" **160×80 长条** ST7735 |
| 驱动 | GC9107（固件里常走 GC9A01 路径） | ST7735 |
| MCU | ESP32-S3FN4R2（4 MB Flash + **2 MB PSRAM**）或 ESP32-S3FN8（8 MB Flash，无 PSRAM） | ESP32-S3，16 MB Flash，**无 PSRAM** |
| 供电 | USB-C；Pro 带 LiPo 充放电 | 插 USB-A 口 |
| 资料 | [lilygo.cc/products/t-qt-pro](https://lilygo.cc/products/t-qt-pro)、[GitHub T-QT](https://github.com/Xinyuan-LilyGO/T-QT) | [T-Dongle-S3 wiki](https://wiki.lilygo.cc/products/t-dongle-series/t-dongle-s3/) |

T-QT Pro 的显示区约 15.2×15.2 mm，262K 色，SPI。128×128 整帧 RGB565 只有
32 KiB，即便选无 PSRAM 的 FN8 变体，只画当前视口也够用。

后续复刻或采购时以 Amazon 链接和 128×128 正方形为准，不要再写成 T-Dongle-S3。

## 4. 画面与无限画布

视觉是饱和色、深色描边的不规则三角/多边形，和作者的 `triangles` 库同一路：
**确定性 Delaunay / 低多边形网格**。同一 seed，任意分辨率应画出同一张世界。

行为比风格更重要：

- 缩放改变的是格子在屏幕上的大小，不是纹理过滤。
- 平移会让新格子进入画面。
- 466×466 圆屏和 128×128 方屏构图对得上。

这要求世界是 **按格子现场生成** 的，而不是一张大位图。ESP32 没有 GPU；
T-QT 即使有 2 MB PSRAM，也不该存整张无限网格。合理做法：

1. 无限确定性格子（抖动网格 / Poisson / Worley / Delaunay）。
2. 每个格子的形状和颜色 = `hash(格子坐标, seed)`。
3. 每块板只光栅化 **当前镜头看得到的格子**。
4. 镜头变了，可见集合变了，画面就变了。

圆屏裁成圆形后，部分缩放级别会看起来像万花筒；这更像视口形状造成的，
不必另假设一套极坐标着色器。未读到固件，渲染器实现标为推断。

「Infinite canvas」在这里的含义：camera 是无界 2D 变换；不同尺寸、形状的屏
只是同一世界里的不同视口。作者 @ 了 tldraw 作者，说的是这个模型，不是
tldraw 跑在了 ESP32 上。

## 5. 同步架构（高置信推断）

**几乎不可能在传视频。** 466×466 RGB 一帧就上百 KB；ESP-NOW 一包大约 250
字节；T-QT 也没有能力当显示器收图。视频却几乎没有拖影。

更合理的是同步 **镜头**，各板本地画：

```text
圆屏 CST9217 触摸
        │
        ▼
  更新 camera {x, y, zoom}（外加 seed）
        │
        ▼
  ESP-NOW 或 UDP 广播，载荷十几到几十字节
        │
        ├──────────────┬──────────────┬──────────────┐
        ▼              ▼              ▼              ▼
   圆屏本地画     T-QT 1 本地画    T-QT 2 本地画    T-QT N
   同一 seed + 同一 camera → 同一世界切片
```

置信度：

| 判断 | 置信度 | 依据 |
| --- | --- | --- |
| 各板本地渲染，不共享 framebuffer | 高 | 带宽、内存、跟手程度、分辨率差 |
| 广播 camera / seed，而不是图 | 高 | 同上；无限画布语义 |
| 通道是 ESP-NOW，或圆屏 SoftAP + UDP | 中高 | ESP32 上最省事；公交上也不需要路由器 |
| 渲染器是 `triangles` 的嵌入式移植 | 中 | 视觉和作者过往项目吻合，无源码 |
| 当前所有屏同一视口，不是 tiled wall | 高 | 视频逐帧对比 |

「公交上用 Claude Code 赶出来」也支持这条路径：Arduino / PlatformIO、
LovyanGFX 或 Arduino_GFX、现成触摸例程、ESP-NOW 广播结构体。这是推断，
不是作者声明。

## 6. 对 LMDJ 的意义

不要把这套装置读成「ESP32 上可以跑 LMDJ」。音频 Runtime 的内存、I2S、
容量模型仍以既有 ESP32 / Cardputer 评估为准。T-QT Pro 最多 2 MB PSRAM，
低于那些评估建议的首个 spike 门槛。

值得记下的是 **状态很小、渲染在本地** 的多设备模式：

1. **视觉从机群。** Pad 触发、Bank、播放头、电平可以变成 `{pad, bank, phase}`
   之类的短包，多块小屏各自画格子、波形或 Pad 矩阵。不需要把 Creator Web
   或 Runtime framebuffer 推到设备上。
2. **共享视口 vs 拼墙。** 今天这个演示是镜像视口。若以后做可视化墙或
   「每块屏看工程的不同区域」，给每块板一个 offset 即可，协议不必升级成
   传图。
3. **确定性生成。** 同一 seed 在 128×128 和 466×466 上对齐，和「一份权威
   状态、多种分辨率呈现」是同一类约束。LMDJ 若做设备端可视化，应同步
   权威状态，而不是同步像素。
4. **输入主机可以不是音频主机。** 圆屏只负责触摸和镜头；声音完全可以仍在
   电脑 / Web Host / 另一块带 codec 的板上。这和 Cardputer 评估里的
   「远程控制终端」是同一分法。

未批准、也不应从本文推出的结论：

- 采购 T-QT Pro 或 Waveshare 1.75 作为 LMDJ 产品硬件；
- 在这些板上跑 Application Facade、Project IO 或 Provider；
- 把生成艺术网格当作 Creator 视觉语言；
- 现在就做多屏可视化墙。

若以后要做设备端可视化 spike，应另开设计和计划，并显式引用本文与两份
ESP32 评估，而不是把本文件当成选型。

## 7. 若要复刻，最小闭环

这不是实施计划，只是把视频还原成可验证的实验步骤：

1. 一块 Waveshare ESP32-S3-Touch-AMOLED-1.75（或同等电容圆屏）当主机。
2. 若干 LILYGO T-QT Pro 当从机。
3. 共享 `hash(格子, seed) → 颜色/多边形`，只画当前 camera 的可见集。
4. 主机读 CST9217，广播 `{x, y, zoom, seed}`。
5. 先验证镜像视口；拼墙再加每板 offset。

显示栈候选：LovyanGFX / Arduino_GFX + 各板官方例程。同步候选：ESP-NOW。
未在真机上验证。

## 8. Version Management

Version impact: none。本文是研究输入，不修改 Product、Host、Core Module、
Provider 或 Contract 身份，也不分配 Product Build。

## 9. Documentation impact

Documentation impact: none
Reason: internal research note under docs/research/; does not change product behavior, public boundaries, versions, evidence, or operations

本文不改变 Architecture Portal 当前产品事实。若未来批准设备端可视化或
Embedded 从机，对应 Spec / PR 再声明受影响的门户路由。

---

## 10. 主要来源

### 演示与作者

- [主帖与视频](https://x.com/msurguy/status/2095686740384395713)
- [作者确认硬件](https://x.com/msurguy/status/2095910459987914991)
- [「infinite canvas」回复](https://x.com/msurguy/status/2095753704142197223)
- [`triangles` 库](https://github.com/msurguy/triangles)

### 硬件规格

- [Waveshare ESP32-S3-Touch-AMOLED-1.75 文档](https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.75)
- [Waveshare 产品仓库](https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-1.75)
- [LILYGO T-QT Pro 产品页](https://lilygo.cc/products/t-qt-pro)
- [LILYGO T-QT GitHub](https://github.com/Xinyuan-LilyGO/T-QT)
- [Amazon ASIN B0BG7YHTJL（T-QT Pro）](https://www.amazon.com/LILYGO-ESP32-S3-GC9107-Display-Development/dp/B0BG7YHTJL)
- [T-Dongle-S3 wiki（对照，未使用）](https://wiki.lilygo.cc/products/t-dongle-series/t-dongle-s3/)

### 仓库内相关评估

- [ESP32 Core 可行性评估](2026-08-27-esp32-core-feasibility-assessment.md)
- [Cardputer Adv 可行性分析](2026-09-03-cardputer-adv-feasibility-analysis.md)
