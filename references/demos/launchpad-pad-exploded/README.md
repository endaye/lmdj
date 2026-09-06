# Launchpad Pad 爆炸机构图

Reference prototype under `references/demos/`. It is frozen reference
material and is not part of the formal product source boundary.

一个可交互的 3D 页面，用来理解主流 pad 控制器（Akai MPC、Novation Launchpad、
Ableton Push 3、NI Maschine）的 pad 是怎么做出来的：分层机构、传感方案、
工程参数与固件算法。

## 内容

- **整机爆炸**：4×4 / 8×8 pad 阵列自上而下七层（pad 帽、框、触发件、传感层、
  PCB + RGB LED、加强板、底壳），可拖动旋转、滚轮缩放、剖切、自动旋转。
- **单 pad 细节**：一个 pad 位的真实比例分层。FSR 方案拆成顶膜 / 间隔胶 /
  底膜三层（总厚 0.45 mm，参照 Interlink FSR 402）；胶粒方案是导电胶粒 +
  PCB 叉指电极；Push 3 是两层电感线圈 + 目标片。每层附工程参数与出处角标。
- **敲击模拟**：点击任意 pad，用 FSR 分压模型生成 2 kHz 采样的 ADC 曲线，
  显示 Δt 法速度、稳态压力与最大斜率。
- **文档区**：分层说明、七类传感技术横截面（胶粒 / FSR 薄膜 / 压电 /
  双触点 / 电容 / 霍尔 / 电感）、单 pad 工程参数总表、固件算法参数、机型对比、
  信号链、工程要点、参考资料。

## 数据来源与可信度

页面里带 `[n]` 角标的数值来自数据手册、设计指南、备件目录、专利与拆解报道，
出处列在页末"参考资料"。主要一手来源：

- Interlink FSR 402 Data Sheet 与 FSR 400 Series Integration Guide
  （力程、电阻、迟滞、漂移、寿命、三层结构、间隔胶厚度、分压电路）。
- J.W. Electronic Components《Design guide for rubber keypads》
  （硅胶硬度、行程、触发力、snap ratio、接触电阻、寿命、公差）。
- MPCstuff 的 Akai 16 键 FSR 备件（1AOTFSR16KEY-AD33 / -AD4A）。
- CDM 对 Ableton Push 3 的技术报道（两层电感式非接触传感）。
- Yamaha US 9,142,202、Roland JP 2017-083535 专利；ISSI IS31FL3733 手册；
  edrumulus 与 HelloDrum 的算法文档；Sensel Morph API primer。

标为"示意"的数值没有一手出处，是行业常见值或本页的重建假设。所有 3D 几何
都是示意性重建，不是任何厂商的官方 CAD。

## 运行

```bash
cd references/demos/launchpad-pad-exploded
python3 -m http.server 4173
```

然后访问 `http://localhost:4173`。页面通过 import map 从 jsDelivr 加载
Three.js 0.160，需要联网；其余全部为本地文件，无构建步骤。

## 文件

| 文件 | 作用 |
| --- | --- |
| `index.html` | 页面骨架与文档区静态文字 |
| `styles.css` | 样式（深色主题） |
| `main.js` | Three.js 场景、两种装配体、交互、标注、敲击模拟、文档渲染 |
| `data.js` | 机型、分层、传感方案、单 pad 参数、算法参数、参考资料 |
| `diagrams.js` | 七张传感横截面 SVG 与信号链 SVG |

调试句柄：`window.lmdjPadDemo`（`orbit`、`setMode`、`switchMachine`、`assembly`）。
