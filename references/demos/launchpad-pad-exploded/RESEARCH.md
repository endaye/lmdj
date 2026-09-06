# Pad 传感机构研究笔记

整理日期：2026-09-06。这是 `launchpad-pad-exploded` demo 背后的研究记录：
打击垫怎样感知按压、主流机型各自用什么方案、每个数值从哪里来、哪些内容
仍是示意或推断。demo 页面里的 `[n]` 角标与本文末尾的资料编号一致。

本文和 demo 一样属于 `references/` 冻结参考材料，不是产品代码，也不决定
LMDJ 的 Contract 或数据模型。

## 1. 打击垫是怎么感受到按压的

绝大多数 pad 控制器（Akai MPC、Novation Launchpad、NI Maschine）走电阻式
这一条链：**力 → 接触面积 → 电阻 → 电压 → 数字 → 速度 / 压力**。

### 1.1 硅胶先把力"整形"

pad 帽是一整片硅胶（keymat），每个 pad 下有一圈斜壁薄膜（裙边 /
membrane）。按下时薄膜先弯折，再把力传到 pad 帽底部中央的凸台或炭黑胶粒。
硅胶做两件事：把面积不定的手指力集中到一个固定小区域；提供回弹。键垫设计
指南要求回弹力至少 30 gf，否则会粘键 [3]。

键垫行业的可设计范围 [3]：行程 0.25–5.0 mm，触发力 20–350 gf（推荐
80–150 gf），绝缘硅胶 Shore A 40–80，寿命约 100 万次，工作温度
−40…+85 °C。样板对照：100 gf 键在 0.8 / 1.0 / 1.2 / 1.4 mm 行程下的
snap ratio 分别为 35 / 60 / 75 / 85%。snap ratio =(F1 − F2)/F1，40–60% 手感
最好，低于 40% 手感弱但寿命更长；pad 类为了线性和寿命通常取低 snap
（这一句是推断）。

### 1.2 力变成接触面积

两种主流实现：

- **导电胶粒 + PCB 叉指电极**（Launchpad Pro / X、经典 MPC）。PCB 上两组
  交错梳状铜电极互不相连，掺炭黑的导电硅胶粒压上去把它们短接。力越大胶粒
  越扁，接触面积越大。键垫行业的胶粒标准直径 2–5 mm，电阻常规
  100–150 Ω，加金粉可到 10 Ω [4]；接触电阻在 Au/Ni 镀层 PCB 上 <200 Ω，
  导电硅胶 Shore A 60、体积电阻率约 3 Ω·cm，接触抖动 <12 ms [3]。
- **印刷 FSR 薄膜**（现代 MPC、Maschine、Push 2）。两片柔性薄膜（PET /
  聚酰亚胺），一片印叉指银浆电极，另一片内侧涂 FSR 炭基油墨，周边一圈
  0.03–0.15 mm 的间隔胶隔出空气隙。轻压时只有油墨表面最高的微观凸起碰到
  电极，力增大时接触点增多，电阻与力成反比；高力段饱和，把力分散到更大
  的凸台可以推高饱和点 [2]。

### 1.3 接触面积变成电阻

Interlink FSR 402 的数据 [1]：不加载 >10 MΩ；力程 0.1–10 N（系列
~0.2–20 N [2]）；开关行程 0.05 mm；迟滞 +10%；长期漂移 <5% /
log10(time)（1 kg，35 天）；重复性单件 ±2%、件间 ±6%；上升时间
<3 µs；寿命 1000 万次（1 kg，4 Hz 点击后 −10% [2]）；温度 −30…+70 °C；
厚 0.45 mm（标称 0.55），外径 18.28 mm，有效区 12.7 mm。

开关行程只有 0.05 mm，所以手感上约 1 mm 的行程几乎全部来自硅胶，而不是
传感器。

### 1.4 电阻变成电压、电压变成数字

FSR 与固定电阻 RM 串成分压器：Vout = V+ · RM / (RM + RFSR)，力越大 Vout
越高；RM 决定力程与灵敏度，集成指南给出 +5 V 下多种 RM 的 F–Vout 曲线族
[1][2]。多通道时也可用 RC 定时法，用 RMIN / RMAX 校准零点和满量程后分区
[2]。16 或 64 路经模拟多路器轮流进 MCU 的 ADC，每 pad 每秒采样一两千次
（这一数值是行业常见值，无一手出处）。

### 1.5 从数字序列里读出"敲多重"和"按多紧"

- **速度（velocity）**：看 ADC 上升多快。Δt 法：跨低阈值到跨高阈值的
  时间差，越短越猛；斜率峰值法：触发后几毫秒窗口内 d(ADC)/dt 的最大值。
  HelloDrum 的做法是 threshold 起扫、scan time 内取峰值、峰值在
  threshold…sensitivity 之间映射到 0–127，再套 0–4 号速度曲线 [11]。
- **压力（aftertouch）**：Note On 后继续读稳态 ADC，低通后映射到 0–127。
  电阻式的迟滞让"放松"比"按紧"反应慢，固件通常加下降补偿（推断）。
- **抗误触**：mask time 禁止重扫 [11]；edrumulus 对压电信号做
  40–400 Hz 带通（约 2 ms 群延迟，用 FIFO 补偿），检测后减去指数衰减曲线
  抑制重触发 [10]。
- **校准**：胶粒与薄膜件间差 ±6% [1]，装配夹紧力又移动零点，所以 MPC /
  Maschine 都有 pad threshold / sensitivity 菜单，产线做逐 pad 校准
  （菜单存在是事实，产线流程是推断）。

老 MPC"越用越要用力敲"的原因：胶粒表面氧化 / 污染后同样的力换来更少接触，
电阻曲线整体抬高。这也是 Akai 把传感薄膜做成独立备件的动机。

## 2. 其他传感方案

| 方案 | 原理 | 速度 | 压力 | 代表 |
| --- | --- | --- | --- | --- |
| 压电片 / 薄膜 | 形变速率产生电荷脉冲，峰值 ∝ 速度 | 极好 | 无 | Roland SPD、电鼓 trigger；Yamaha 专利的 PU 泡棉 5–20 mm + 金属保持层 0.5–3 mm + 压电 [12] |
| 双触点膜片 | 两层触点闭合时间差 Δt | 有 | 无 | 键盘琴键 |
| 电容式 | 硅胶压缩改变电极间距与手指耦合 | 可推出 | 有，带 X/Y | ROLI 类（示意归类） |
| 霍尔 / 光学 | 磁铁位移或遮光量 | 极好 | 以位移代压力 | Wooting 键盘等，pad 领域新兴 |
| 电感式非接触 | 目标片改变线圈电感（涡流） | 位移微分 | 有，带连续 X/Y | Ableton Push 3 [6] |

Push 3 的细节 [6][7]：Ableton 自研并申请专利（Oliver Harms、Ralf Suckow）
的两层非接触电感传感，一层测力、一层测手指位置；X/Y 连续，pad 之间的间隙
也能感知；MPE 三维为 pressure、slide、per-note pitch bend。线圈几何、目标
片材料与扫描频率未公开，demo 中的线圈层为示意重建。

高密度阵列的极端例子是 Sensel Morph [8][9]：185 × 105 = 19,425 个 FSR
传感点，1.25 mm 间距，每点 5 g–5 kg，帧率 125 Hz（8 ms）或 500 Hz（2 ms）。

## 3. 主流机型的传感与备件

| 机型 | 阵列 | 传感 | 依据 |
| --- | --- | --- | --- |
| Akai MPC Live / Live II / X / Touch / Studio MK2、MPD 226 / 232 | 4×4 | 16 键整片 FSR 薄膜 | 备件 1AOTFSR16KEY-AD33，约 $27.5 [5] |
| Akai MPC One / MPC Key | 4×4 | 16 键整片 FSR 薄膜 | 备件 1AOTFSR16KEY-AD4A [5] |
| Akai MPC 2000XL / 1000 等老款 | 4×4 | 胶粒 + 柔性电路叉指电极 | 备件目录 [5]（"pad sensors with ribbon"） |
| Novation Launchpad Pro / X | 8×8 | 胶粒 + 主板叉指电极，速度 + 压力 | 拆解视频显示 keymat + 单主板 [15]；官方规格 [16]；电极图形未公开 |
| Novation Launchpad Mini MK3 | 8×8 | 胶粒短接触点，开关式，无速度 | 官方规格（无 velocity） |
| Ableton Push 3 | 8×8 | 两层电感式非接触 | [6][7] |
| NI Maschine MK3 / + | 4×4 | FSR 薄膜（推断，与 MPC 同类） | 无一手拆解资料 |

pad 尺寸（MPC ≈26 mm、Launchpad ≈20 mm、Push ≈22 mm、Maschine ≈27 mm）
均为估值，厂商未公开单 pad 尺寸。

## 4. LED 与驱动

64 pad 面板正好对应一颗 12×16 矩阵驱动：IS31FL3733 提供 192 通道
（= 64 颗 RGB），每颗 8-bit PWM 256 级，1/12 扫描，256 级全局电流，
1 MHz I²C，2.7–5.5 V，开路 / 短路检测 [14]。具体机型用哪颗驱动未核实，
这里只作为参照件。

## 5. 研究过程中的纠正

- 最初把 Push 3 画成 FSR 薄膜方案。查到 CDM 的报道后改为电感式非接触
  两层方案 [6]，demo 的机型数据、对比表与技术方案卡（新增 G 类）均已更新。
- 最初把胶粒直径写成 6–10 mm。键垫行业标准是 2–5 mm [4]；pad 类更大的
  直径没有一手出处，改标为"示意"。
- 硅胶硬度最初写 Shore A 40–60，改为设计指南的 40–80 可选 [3]，pad 取偏软
  一端为推断。

## 6. 仍是示意或推断的内容

- 所有 3D 几何、分层厚度（除 FSR 402 的 0.45 mm 与拆分比例外）。
- pad 尺寸、胶粒直径、叉指指宽 / 间距、扫描率、泡棉厚度、LED 封装。
- Maschine 的具体传感实现；Launchpad 的电极图形；Push 3 线圈几何。
- 产线校准流程、pad 类取低 snap ratio、迟滞补偿等固件细节。

## 7. 未查到、值得继续找的资料

- Ableton 电感式 pad 的专利原文（检索 Harms / Suckow 未直接命中专利号）。
- Novation Launchpad Pro 主板电极的高清照片（Synthtopia 视频未逐帧核对）。
- Akai / Novation 的 pad 传感专利；Roland 的 pad 位置检测专利只看了摘要 [13]。
- 各机型 pad 的实测尺寸与行程。

## 8. 参考资料

1. Interlink Electronics — FSR 402 Data Sheet (P/N 30-81794).
   <https://cdn.sparkfun.com/assets/8/a/1/2/0/2010-10-26-DataSheet-FSR402-Layout2.pdf>
2. Interlink Electronics — FSR 400 Series Integration Guide.
   <https://www.pololu.com/file/0J749/FSR400-Series-Integration-Guide-13.pdf>
3. J.W. Electronic Components GmbH — Design guide for rubber keypads.
   <https://www.jw-electronic-components.de/pdf/Design%20guide%20for%20rubber%20keypads.pdf>
4. Better Silicone — Carbon pill / conductive pill.
   <https://www.rubber-keypad.com/Carbon-Pill-Switch-Button-pd6979728.html>
5. MPCstuff — Akai Pad Sensors Sheet FSR 1AOTFSR16KEY-AD33 / -AD4A.
   <https://www.mpcstuff.com/fsr-16key-pad-sensor-sheet-akai-mpc-touch-live-x/>
6. CDM — Inside the new Ableton Push: all the technical details so far.
   <https://cdm.link/inside-the-new-ableton-push/>
7. Ableton — Getting Started with MPE on Push 3.
   <https://help.ableton.com/hc/en-us/articles/8831904851740-Getting-Started-with-MPE-on-Push-3>
8. Sensel — Morph API primer. <http://guide.sensel.com/api/>
9. NIME 2019 — Enhancing the Expressivity of the Sensel Morph via Audio-rate Sensing.
   <https://www.nime.org/proceedings/2019/nime2019_paper057.pdf>
10. edrumulus — doc/algorithm.md.
    <https://github.com/corrados/edrumulus/blob/main/doc/algorithm.md>
11. HelloDrum Arduino Library — docs/sensing.md.
    <https://github.com/RyoKosaka/HelloDrum-arduino-Library/blob/master/docs/sensing.md>
12. US 9,142,202 B2 — Electronic percussion pad and method of manufacturing
    electronic percussion pad (Yamaha). <https://patents.google.com/patent/US9142202B2/en>
13. JP 2017-083535 A — Electronic percussion instrument and striking position
    detector (Roland). <https://patents.google.com/patent/JP2017083535A/en>
14. ISSI / Lumissil — IS31FL3733 12×16 Dots Matrix LED Driver.
    <https://download.mikroe.com/documents/datasheets/31FL3733.pdf>
15. Synthtopia — Novation Launchpad Pro Teardown Video.
    <https://www.synthtopia.com/content/2015/10/28/novation-launchpad-pro-teardown-video/>
16. Novation — Launchpad Pro [MK3] hardware overview.
    <https://userguides.novationmusic.com/hc/en-gb/articles/25494505681042-Launchpad-Pro-MK3-hardware-overview>
