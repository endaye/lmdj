// 机型与分层数据。所有几何尺寸单位为 mm，属于基于公开拆解与维修配件资料的
// 示意性重建，不是任何厂商的官方 CAD 数据。

export const LAYER_ORDER = [
  "cap",
  "frame",
  "pill",
  "sensor",
  "pcb",
  "stiffener",
  "chassis",
];

export const LAYERS = {
  cap: {
    name: "Pad 帽 / 硅胶键垫",
    en: "Pad cap · silicone keymat",
    color: "#f2b134",
    role: "手指直接敲击的部件。既是操作面，也是力的传导件、LED 的扩散体和回弹弹簧。",
    material:
      "半透明硅胶（绝缘级硅胶 Shore A 40–80 可选，pad 常见偏软的一端）或 TPU；表面做哑光蚀纹或 PU 涂层防指纹、耐磨。",
    detail: [
      "MPC 类：16 个 3–4 mm 厚的\"厚胶垫\"，通常整片一体成型，四周有薄裙边（skirt）兼做回弹。",
      "Launchpad 类：64 pad + 外围按键一片硅胶成型（keymat），pad 更薄（约 2 mm），靠 pad 下方的\"网状/伞状\"结构回弹。",
      "帽体加白色母粒或 TiO₂ 做匀光，让下方 RGB LED 均匀点亮整块。",
    ],
  },
  frame: {
    name: "Pad 框 / 上盖开孔",
    en: "Pad frame · bezel",
    color: "#7d8fa8",
    role: "把每个 pad 侧向限位，规定行程止点，防止相邻 pad 被牵连（串击）。",
    material: "ABS/PC 注塑，或直接是上壳的一部分；MPC X 等高端机用金属面板。",
    detail: [
      "开孔比 pad 帽大约 0.3–0.6 mm 单边间隙：太小会卡滞，太大会晃动、露光。",
      "孔壁做 3–5° 拔模斜度，配合 pad 帽的倒角，边缘敲击时不易卡边。",
      "框体下方的十字肋压住 keymat 的裙边，是 keymat 的固定点与防尘密封。",
    ],
  },
  pill: {
    name: "导电胶粒 / 触发头",
    en: "Conductive carbon pill",
    color: "#4a4a4f",
    role: "把手指的力转化为与电极的接触面积变化，是电阻式传感的\"可变部分\"。",
    material:
      "掺炭黑的导电硅胶（键垫行业典型：Shore A 60，体积电阻率约 3 Ω·cm，接触电阻 <200 Ω）；标准冲切直径 2–5 mm，pad 类为了接触面积常用更大直径（示意），与 pad 帽二次硫化成一体。",
    detail: [
      "力越大 → 胶粒越压扁 → 与叉指电极接触面积越大 → 等效电阻越低。",
      "胶粒底面常做微小圆弧（crown）而非平面，让\"接触面积-力\"曲线更平滑、低力段更线性。",
      "老化表现：胶粒表面氧化/污染 → 电阻抬高 → \"要用力敲才响\"，这是老 MPC 换 pad 的主要原因。",
    ],
  },
  sensor: {
    name: "传感层（FSR 薄膜 / 叉指电极）",
    en: "Sensor layer · FSR film / interdigitated electrodes",
    color: "#e0862b",
    role: "把压力变成可测电阻。两种主流实现：印刷 FSR 薄膜，或直接在 PCB 上做叉指电极。",
    material:
      "FSR 薄膜：PET/PI 基材 + 印刷银浆电极 + 半导电油墨层，厚 0.2–0.4 mm，带 FPC 尾线。叉指电极：PCB 铜层 ENIG 镀金或印碳膜防氧化。",
    detail: [
      "叉指（interdigitated）：两组梳状电极交错，间距 0.2–0.3 mm，靠胶粒把它们\"短接\"。",
      "印刷 FSR（Interlink 式）：胶粒可以是普通硅胶，导电部分在薄膜里；一致性更好、可整片更换。",
      "Akai 现代 MPC 把它做成独立备件\"pad sensor\"；Launchpad Pro/X 则在主板上直接布叉指电极。",
    ],
  },
  pcb: {
    name: "Pad PCB（电极 + RGB LED + 扫描）",
    en: "Pad PCB · electrodes, RGB LEDs, scan mux",
    color: "#2e9e63",
    role: "承载电极、每 pad 一颗（或多颗）RGB LED、以及模拟多路开关/ADC 扫描电路。",
    material: "FR-4 1.6 mm，2–4 层；LED 为 2020/3528 顶发光 RGB 或侧发光配导光柱。",
    detail: [
      "LED 一般放在 pad 正中，电极环绕 LED 布置成环形叉指；或 LED 放角上、电极占中心。",
      "扫描：16/64 路模拟量经 CD4051/74HC4067 多路器进 MCU ADC，每 pad 采样率 1–4 kHz。",
      "为了 RGB 亮度均匀，LED 用恒流驱动（如 IS31FL37xx / TLC59xx），PWM ≥ 1 kHz 避免拍摄闪烁。",
    ],
  },
  stiffener: {
    name: "加强板 / 支撑板",
    en: "Stiffener plate",
    color: "#9aa4b1",
    role: "让 PCB 在敲击下不弯曲：任何形变都会改变胶粒预压力，直接变成灵敏度漂移。",
    material: "1.0–1.5 mm 钢板 / 铝板，或壳体内的密肋。",
    detail: [
      "加强板与 PCB 之间常垫 PORON 泡棉，吸收敲击冲击、降低\"啪啪\"的机械噪声。",
      "MPC X / Push 3 这类重型机把加强板与金属底壳合一。",
    ],
  },
  chassis: {
    name: "底壳",
    en: "Chassis",
    color: "#3d4046",
    role: "结构基座，也是整机的质量块——机身越重，敲击时能量越少反弹回手指。",
    material: "ABS 注塑或钣金；底部防滑胶脚。",
    detail: [
      "螺柱把 PCB + 加强板 + 上盖夹紧，夹紧力决定 keymat 的预压：这是产线要校准 pad 阈值的原因之一。",
    ],
  },
};

// 传感层实现方式
export const SENSING = {
  pillOnPcb: {
    label: "导电胶粒 + PCB 叉指电极",
    short: "胶粒/叉指",
    sensorLayer: "electrodes", // 传感层画成电极图案，而不是薄膜
  },
  fsrFilm: {
    label: "印刷 FSR 薄膜",
    short: "FSR 薄膜",
    sensorLayer: "film",
  },
  inductive: {
    label: "电感式非接触（力层 + 位置层）",
    short: "电感式",
    sensorLayer: "coil",
  },
};

export const MACHINES = {
  mpc: {
    name: "Akai MPC（Live II / One / X）",
    short: "Akai MPC",
    grid: 4,
    padSize: 26,
    gap: 4.5,
    padCorner: 3.5,
    capHeight: 4.0,
    travel: 1.2,
    sensing: "fsrFilm",
    ledsPerPad: 1,
    ledPalette: ["#ff3b30", "#ff9500", "#ffcc00", "#34c759", "#00c7be", "#007aff", "#af52de", "#ff2d55"],
    notes: [
      "16 个厚胶垫，速度 + 压力（aftertouch）敏感，RGB 背光。",
      "现代 MPC 的传感层是独立的 FSR 薄膜备件（服务手册称 pad sensor），可以整片更换。",
      "菜单里有 Pad Threshold / Sensitivity / Velocity Curve，本质上是在软件里补偿胶粒与薄膜的个体差异。",
      "老一代（MPC 2000XL/1000）用的是胶粒 + 柔性电路上的叉指银浆电极，长期使用后要换 pad。",
    ],
    tags: ["4×4", "厚胶垫", "Velocity", "Aftertouch", "RGB"],
  },
  launchpad: {
    name: "Novation Launchpad（Pro MK3 / X）",
    short: "Launchpad",
    grid: 8,
    padSize: 20,
    gap: 3.2,
    padCorner: 2.0,
    capHeight: 2.4,
    travel: 0.8,
    sensing: "pillOnPcb",
    ledsPerPad: 1,
    ledPalette: ["#ff2d55", "#ff9500", "#ffd60a", "#30d158", "#64d2ff", "#0a84ff", "#bf5af2", "#ffffff"],
    notes: [
      "64 pad + 外围功能键一片硅胶 keymat 成型；pad 薄、行程短、手感偏\"点击\"。",
      "Pro / X 系列每个 pad 下是导电胶粒 + 主板叉指电极，做速度与压力（Pro 支持 poly aftertouch）。",
      "Mini MK3 的 pad 只是开关（胶粒短接两个触点），没有速度感应，机构相同但传感层退化为触点。",
      "8×8 密排下 LED 与电极要挤在 20 mm 见方里，因此 LED 常放 pad 中心、电极做环形叉指。",
    ],
    tags: ["8×8", "薄键垫", "Velocity", "Poly AT (Pro)", "RGB"],
  },
  push: {
    name: "Ableton Push 3",
    short: "Push 3",
    grid: 8,
    padSize: 22,
    gap: 3.0,
    padCorner: 2.5,
    capHeight: 3.0,
    travel: 1.0,
    sensing: "inductive",
    ledsPerPad: 1,
    ledPalette: ["#ff6b6b", "#ffa94d", "#ffd43b", "#69db7c", "#38d9a9", "#4dabf7", "#9775fa", "#f783ac"],
    notes: [
      "64 个 MPE pad：每 pad 独立压力（pressure）、pad 内滑动（slide）与逐音 pitch bend。",
      "传感为 Ableton 自研并申请专利的电感式非接触方案（Oliver Harms、Ralf Suckow），分两层：一层测力、一层测手指位置；X/Y 连续，pad 之间的间隙也能感知。",
      "为了让手指能在 pad 之间滑动，Push 3 压低了 pad 高度并缩小了 pad 间隙。",
      "线圈几何、目标片材料与扫描频率未公开；本页 3D 中的线圈层为示意重建。",
    ],
    tags: ["8×8", "MPE", "电感式", "Pressure", "X/Y Slide", "RGB"],
  },
  maschine: {
    name: "Native Instruments Maschine MK3 / +",
    short: "Maschine",
    grid: 4,
    padSize: 27,
    gap: 4.0,
    padCorner: 4.0,
    capHeight: 3.6,
    travel: 1.1,
    sensing: "fsrFilm",
    ledsPerPad: 1,
    ledPalette: ["#ff5e57", "#ffa801", "#ffd32a", "#0be881", "#00d8d6", "#3c40c6", "#c56cf0", "#ffffff"],
    notes: [
      "16 个大 pad（约 27 mm），速度 + aftertouch，RGB。",
      "MK3 相比 MK2 加大了 pad、降低了触发阈值，属于同一类 FSR 方案的手感调优。",
      "Maschine 软件的 Pad Sensitivity 与 MPC 一样是对传感一致性的软件补偿。",
    ],
    tags: ["4×4", "大胶垫", "Velocity", "Aftertouch", "RGB"],
  },
};

// 技术方案（横截面卡片）
export const TECH = [
  {
    id: "pill",
    title: "A · 导电胶粒 + 叉指电极（电阻式）",
    used: "Novation Launchpad Pro/X、经典 Akai MPC、多数廉价 pad 控制器",
    how:
      "pad 帽下的炭黑硅胶粒压在两组交错的梳状电极上。力增大 → 接触面积增大 → 两电极间电阻从 >1 MΩ 降到几 kΩ。MCU 用分压 + ADC 读出电压。",
    velocity: "从电阻开始下降到过第二阈值的时间差（Δt），或 ADC 上升斜率峰值。",
    pressure: "有：稳态电阻即压力（aftertouch / poly AT）。",
    pros: ["最便宜，零件只有胶粒与铜箔", "传感与键垫一体，装配简单", "天然支持连续压力"],
    cons: ["胶粒个体差异大，需要逐 pad 校准", "迟滞、蠕变、温漂明显", "表面氧化后灵敏度下降，需要换 pad"],
    svg: "pill",
  },
  {
    id: "fsr",
    title: "B · 印刷 FSR 薄膜（电阻式）",
    used: "现代 Akai MPC（pad sensor 备件）、NI Maschine、Ableton Push 2、Sensel Morph（高密度阵列）",
    how:
      "PET 基材印银浆电极，再覆一层半导电聚合物油墨（分流模式）；或两片薄膜面对面（穿透模式）。压力越大，油墨与电极的微观接触点越多，电阻越低。胶粒不必导电。",
    velocity: "同 A：Δt 或斜率法。",
    pressure: "有，而且线性度与一致性优于胶粒方案。",
    pros: ["整片可更换，一致性好", "可做高密度阵列（Sensel ~20k 传感点）", "厚度 <0.4 mm，不占行程"],
    cons: ["仍有迟滞与蠕变", "薄膜边缘/折弯处易失效", "对 PCB 平整度与预压敏感，需要加强板"],
    svg: "fsr",
  },
  {
    id: "piezo",
    title: "C · 压电片 / 压电薄膜（冲量式）",
    used: "Roland SPD 系列电子打击垫、电鼓 trigger、部分 DIY pad",
    how:
      "压电陶瓷片或 PVDF 薄膜贴在 pad 下方或壳体上。敲击产生的形变速率 → 电荷脉冲，峰值电压与敲击速度近似成正比。",
    velocity: "极好：直接读脉冲峰值，响应 <1 ms。",
    pressure: "没有：压电只对变化率响应，按住不动输出归零。",
    pros: ["速度动态范围最大，打鼓手感最真实", "无接触磨损，寿命长", "对灵敏区无需精细装配"],
    cons: ["无 aftertouch / 压力", "串扰（crosstalk）严重，需要隔振与软件抑制", "需要高阻输入与保护电路"],
    svg: "piezo",
  },
  {
    id: "dual",
    title: "D · 双触点膜片（飞行时间式）",
    used: "键盘类：几乎所有合成器琴键；部分 pad 控制器早期方案",
    how:
      "同一 pad 下有两层触点，深度不同。按下时先闭合第一层、后闭合第二层，两次闭合的时间差 Δt 反推速度。",
    velocity: "有，分辨率取决于扫描频率与两层间距。",
    pressure: "无（可再加第三层 FSR 补 aftertouch）。",
    pros: ["数字量，不需要 ADC，抗干扰", "手感可以很轻", "成本低"],
    cons: ["行程要够（≥1.5 mm）才能拉开两层，pad 会\"深\"", "无压力", "触点数翻倍，扫描复杂"],
    svg: "dual",
  },
  {
    id: "cap",
    title: "E · 电容式 / 形变电容（连续式）",
    used: "ROLI Seaboard / Lightpad（配合硅胶形变）、部分 MPE 表面（示意归类）",
    how:
      "硅胶下方是电容电极阵列；手指靠近改变电容（触摸），硅胶被压缩使电极间距变化（压力）。可同时得到位置、面积和压力。",
    velocity: "可从电容变化速率推出，但不如电阻/压电直接。",
    pressure: "有，且可测 X/Y 位置——MPE 的天然方案。",
    pros: ["同一层同时给位置 + 压力 + 面积", "无机械触点，寿命长", "可做任意形状的连续表面"],
    cons: ["电路复杂、成本高", "对手套/戴戒指/湿手敏感", "需要屏蔽，靠近 LED 驱动时干扰大"],
    svg: "cap",
  },
  {
    id: "hall",
    title: "F · 霍尔 / 光学（无接触位移式）",
    used: "Wooting 等模拟键盘（霍尔）；ROLI Lumi 等（光学）；pad 领域属于新兴方案",
    how:
      "pad 帽内嵌小磁铁，PCB 上霍尔传感器读磁场强度 → 位移；或用红外发射/接收对读遮光量。位移与力通过硅胶的弹性曲线换算。",
    velocity: "极好：连续位移直接微分。",
    pressure: "有（以位移代压力）；可做可编程触发点。",
    pros: ["零磨损、零漂移，不需要校准", "位移连续，触发点可软件定义", "不受氧化影响"],
    cons: ["每 pad 一颗传感器 + 磁铁，64 pad 成本高", "磁铁互相干扰，密排需要屏蔽", "行程需 ≥2 mm 才有足够分辨率"],
    svg: "hall",
  },
  {
    id: "inductive",
    title: "G · 电感式非接触（Ableton Push 3）",
    used: "Ableton Push 3（自研专利，Oliver Harms / Ralf Suckow）",
    how:
      "PCB 上的平面线圈以高频激励，pad 内的导电/铁磁目标片靠近时改变线圈电感（涡流效应）。Push 3 用两层传感：一层测力（目标片下压距离），一层测手指位置（多线圈重心），X/Y 连续、可感知 pad 之间。",
    velocity: "位移连续 → 直接微分得到速度。",
    pressure: "有；以下压距离代替压力，且同时给出连续 X/Y（MPE 三维）。",
    pros: ["非接触、无磨损、不受氧化与硅胶老化影响", "同一机构给出压力 + 连续位置", "无需逐 pad 更换传感薄膜"],
    cons: ["线圈阵列 + 激励/解调电路成本高", "对附近金属与 LED 驱动噪声敏感，需屏蔽与频率规划", "目前只有 Ableton 一家在 pad 上量产"],
    svg: "inductive",
  },
];

// 对比表
export const COMPARE = [
  ["机型", "阵列", "Pad 尺寸", "传感方案", "速度", "压力", "MPE / X-Y", "LED"],
  ["Akai MPC Live II / One / X", "4×4", "≈26 mm 厚垫", "FSR 薄膜", "✓", "✓ 单 pad AT", "✗", "RGB 单颗"],
  ["Novation Launchpad Pro MK3", "8×8", "≈20 mm 薄垫", "胶粒 + 叉指", "✓", "✓ Poly AT", "✗", "RGB 单颗"],
  ["Novation Launchpad X", "8×8", "≈20 mm 薄垫", "胶粒 + 叉指", "✓", "✓ Poly AT", "✗", "RGB 单颗"],
  ["Novation Launchpad Mini MK3", "8×8", "≈20 mm 薄垫", "胶粒触点（开关）", "✗", "✗", "✗", "RGB 单颗"],
  ["Ableton Push 3", "8×8", "≈22 mm（示意）", "电感式非接触，力层 + 位置层", "✓", "✓ Poly", "✓ 连续 X/Y", "RGB"],
  ["NI Maschine MK3 / +", "4×4", "≈27 mm 厚垫", "FSR 薄膜", "✓", "✓ 单 pad AT", "✗", "RGB"],
  ["Roland SPD-SX Pro", "9 区", "大面板", "压电 trigger", "✓✓", "✗", "✗", "RGB 条"],
  ["Sensel Morph", "连续", "整面", "高密 FSR 阵列", "✓", "✓ 多点", "✓ 位置", "✗"],
];

// ---------------------------------------------------------------------------
// 参考资料（工程参数的出处）。id 在 SINGLE_LAYERS[*].params[*].src 中引用。
// ---------------------------------------------------------------------------
export const REFERENCES = [
  { id: "fsr402", title: "Interlink Electronics — FSR 402 Data Sheet (P/N 30-81794)", url: "https://cdn.sparkfun.com/assets/8/a/1/2/0/2010-10-26-DataSheet-FSR402-Layout2.pdf", note: "力程、电阻、迟滞、漂移、寿命、厚度、有效区" },
  { id: "fsrGuide", title: "Interlink Electronics — FSR 400 Series Integration Guide", url: "https://www.pololu.com/file/0J749/FSR400-Series-Integration-Guide-13.pdf", note: "FSR 三层结构、间隔胶厚度、反幂律、分压电路、多通道接口" },
  { id: "jw", title: "J.W. Electronic Components — Design guide for rubber keypads", url: "https://www.jw-electronic-components.de/pdf/Design%20guide%20for%20rubber%20keypads.pdf", note: "硅胶键垫行程、触发力、snap ratio、硬度、接触电阻、寿命、公差" },
  { id: "pill", title: "Better Silicone — Carbon pill / conductive pill 规格页", url: "https://www.rubber-keypad.com/Carbon-Pill-Switch-Button-pd6979728.html", note: "炭粒标准直径 2–5 mm，电阻 100–150 Ω，加金粉可至 10 Ω" },
  { id: "akaiFsr", title: "MPCstuff — Akai Pad Sensors Sheet FSR 1AOTFSR16KEY-AD33 / -AD4A", url: "https://www.mpcstuff.com/fsr-16key-pad-sensor-sheet-akai-mpc-touch-live-x/", note: "MPC Live/X/Live II/Touch/Studio MK2/MPD226/232 与 MPC One/Key 的 16 键 FSR 备件" },
  { id: "cdmPush", title: "CDM — Inside the new Ableton Push: all the technical details so far", url: "https://cdm.link/inside-the-new-ableton-push/", note: "Push 3 两层电感式非接触传感，Harms / Suckow 专利，X/Y 连续" },
  { id: "abletonMpe", title: "Ableton — Getting Started with MPE on Push 3", url: "https://help.ableton.com/hc/en-us/articles/8831904851740-Getting-Started-with-MPE-on-Push-3", note: "pressure / slide / per-note pitch bend 三维表达" },
  { id: "sensel", title: "Sensel — Morph API primer", url: "http://guide.sensel.com/api/", note: "185×105 = 19,425 sensel，1.25 mm 间距，5 g–5 kg，125/500 Hz" },
  { id: "senselNime", title: "NIME 2019 — Enhancing the Expressivity of the Sensel Morph via Audio-rate Sensing", url: "https://www.nime.org/proceedings/2019/nime2019_paper057.pdf", note: "Morph 传感阵列与采样率的学术描述" },
  { id: "edrumulus", title: "edrumulus — doc/algorithm.md", url: "https://github.com/corrados/edrumulus/blob/main/doc/algorithm.md", note: "40–400 Hz 带通、~2 ms 滤波延迟、首峰检测、指数衰减重触发抑制、位置感知" },
  { id: "hellodrum", title: "HelloDrum Arduino Library — docs/sensing.md", url: "https://github.com/RyoKosaka/HelloDrum-arduino-Library/blob/master/docs/sensing.md", note: "threshold / sensitivity / scan time / mask time / 曲线类型 0–4" },
  { id: "yamaha", title: "US 9,142,202 B2 — Electronic percussion pad and method of manufacturing (Yamaha)", url: "https://patents.google.com/patent/US9142202B2/en", note: "PU 泡棉 5–20 mm，金属保持层 0.5–3 mm，Asker C 10–60" },
  { id: "roland", title: "JP 2017-083535 A — Electronic percussion instrument and striking position detector (Roland)", url: "https://patents.google.com/patent/JP2017083535A/en", note: "片状压力传感器 + 惯性质量块的击打位置检测" },
  { id: "is31", title: "ISSI / Lumissil — IS31FL3733 12×16 Dots Matrix LED Driver", url: "https://download.mikroe.com/documents/datasheets/31FL3733.pdf", note: "192 通道 = 64 RGB，8-bit PWM，1/12 扫描，256 级全局电流，1 MHz I²C" },
  { id: "lpTeardown", title: "Synthtopia — Novation Launchpad Pro Teardown Video", url: "https://www.synthtopia.com/content/2015/10/28/novation-launchpad-pro-teardown-video/", note: "Launchpad Pro 拆解（keymat + 主板）" },
  { id: "lpGuide", title: "Novation — Launchpad Pro [MK3] hardware overview", url: "https://userguides.novationmusic.com/hc/en-gb/articles/25494505681042-Launchpad-Pro-MK3-hardware-overview", note: "64 个 RGB 速度 + 压力感应 pad" },
];

// ---------------------------------------------------------------------------
// 单 pad 细节视图的分层。thickness 单位 mm；标 "示意" 的数值没有一手出处。
// params: [{ k, v, src? }]，src 为 REFERENCES.id；无 src 即为示意/推断。
// ---------------------------------------------------------------------------
export const SINGLE_LAYERS = {
  cap: {
    name: "Pad 帽（硅胶）",
    en: "Pad cap · silicone",
    color: "#f2b134",
    role: "操作面、匀光体与力传导件。厚度按机型（MPC ≈4 mm 厚垫，Launchpad ≈2.4 mm 薄垫，示意）。",
    params: [
      { k: "硅胶硬度", v: "绝缘级 Shore A 40–80（±5）；导电级 60", src: "jw" },
      { k: "键程（可设计）", v: "0.25–5.0 mm；样板 0.8 / 1.0 / 1.2 / 1.4 mm", src: "jw" },
      { k: "触发力 F1", v: "可设计 20–350 gf；推荐 80–150 gf；样板 100–250 gf", src: "jw" },
      { k: "回弹力 F3", v: "≥30 gf，防止粘键", src: "jw" },
      { k: "寿命", v: "约 1,000,000 次（键垫典型）", src: "jw" },
      { k: "工作温度", v: "−40 … +85 °C", src: "jw" },
      { k: "尺寸公差", v: "16–25 mm 键：±0.20 / ±0.25 / ±0.50 mm（超精 / 精 / 普通）", src: "jw" },
      { k: "拉伸强度 / 撕裂", v: "55–75 kg/cm² / 8–12 kg/cm", src: "jw" },
    ],
  },
  membrane: {
    name: "回弹膜 / 裙边",
    en: "Membrane · flex wall (skirt)",
    color: "#e8c877",
    role: "与 pad 帽一体成型的斜壁薄膜，决定 F1、F2、snap ratio 与回弹。pad 多做低 snap 以换线性与寿命。",
    params: [
      { k: "Snap ratio 定义", v: "(F1 − F2) / F1；40–60% 手感最佳，<40% 手感弱但寿命更长", src: "jw" },
      { k: "样板对照", v: "100 gf 键：行程 0.8 / 1.0 / 1.2 / 1.4 mm → snap 35 / 60 / 75 / 85%", src: "jw" },
      { k: "压缩永久变形", v: "11–22%（175 °C，22 h）", src: "jw" },
      { k: "通气", v: "底部至少两侧开 air channel，避免压缩空气顶起 pad", src: "jw" },
      { k: "壁厚 / 角度", v: "约 0.4–0.6 mm，倾斜 30–45°（示意）" },
    ],
  },
  pill: {
    name: "导电胶粒",
    en: "Conductive carbon pill",
    color: "#4a4a4f",
    role: "把力变成与叉指电极的接触面积。胶粒方案（Launchpad Pro/X、经典 MPC）的传感元件就是它。",
    params: [
      { k: "标准直径", v: "2–5 mm 冲切；圆形为主，也有椭圆/矩形", src: "pill" },
      { k: "接触电阻", v: "<200 Ω（Au/Ni 镀层 PCB）", src: "jw" },
      { k: "炭粒电阻", v: "常规 100–150 Ω；加金粉可至 10 Ω", src: "pill" },
      { k: "导电硅胶", v: "Shore A 60，体积电阻率 ≈3 Ω·cm", src: "jw" },
      { k: "接触抖动", v: "<12 ms", src: "jw" },
      { k: "额定接触", v: "30 mA @ 12 VDC（0.5 s）", src: "jw" },
      { k: "绝缘电阻", v: ">100 MΩ @ 500 VDC", src: "jw" },
      { k: "pad 用直径", v: "6–10 mm（为增大接触面积，示意）" },
    ],
  },
  nub: {
    name: "触发凸台（非导电）",
    en: "Actuator nub",
    color: "#8a6a3a",
    role: "FSR 方案里胶粒不必导电，只负责把力集中到薄膜有效区。凸台底面越平、越大，饱和点越高。",
    params: [
      { k: "作用", v: "把 F 施加到 FSR 有效区；扩大接触面可推高饱和点", src: "fsrGuide" },
      { k: "直径", v: "≈ 有效区直径（FSR 402 为 12.7 mm）（示意）", src: "fsr402" },
    ],
  },
  target: {
    name: "感应目标片",
    en: "Inductive target",
    color: "#b8c4d0",
    role: "电感式方案中嵌在 pad 帽内的导电/铁磁片；靠近线圈时通过涡流改变电感。",
    params: [
      { k: "方案", v: "Ableton 专利，非接触电感式，两层传感", src: "cdmPush" },
      { k: "材料 / 尺寸", v: "未公开（示意）" },
    ],
  },
  sensorTop: {
    name: "FSR 顶膜（PET + 炭基油墨）",
    en: "FSR top membrane · PET + FSR ink",
    color: "#e0862b",
    role: "柔性薄膜内侧涂 FSR 炭基油墨；受压时油墨的微观凸起越多地短接下膜叉指，电阻按反幂律下降。",
    params: [
      { k: "基材", v: "PET / 聚酰亚胺等柔性薄膜", src: "fsrGuide" },
      { k: "传感机理", v: "低力只有最高凸起接触；力增大接触点增多；R ∝ 1/F；高力饱和", src: "fsrGuide" },
      { k: "上升时间", v: "<3 µs（钢球落下测得）", src: "fsr402" },
      { k: "最大电流", v: "1 mA / cm²（受力面积）", src: "fsrGuide" },
    ],
  },
  sensorSpacer: {
    name: "间隔胶（空气隙）",
    en: "Spacer adhesive · air gap",
    color: "#f4d7a1",
    role: "周边一圈压敏胶，既把上下膜粘在一起，又留出空气隙；它的厚度决定触发力和 0.05 mm 的开关行程。",
    params: [
      { k: "厚度", v: "0.03–0.15 mm", src: "fsrGuide" },
      { k: "开关行程", v: "0.05 mm（典型）", src: "fsr402" },
      { k: "触发力（break force）", v: "≈0.2 N min（系列）；FSR 402 标称 0.1 N", src: "fsrGuide" },
      { k: "工艺", v: "丝印 PSA、模切 PSA 膜或组合", src: "fsrGuide" },
    ],
  },
  sensorBottom: {
    name: "FSR 底膜（叉指银浆电极）",
    en: "FSR bottom membrane · interdigitated silver",
    color: "#d9a441",
    role: "两组电气独立的叉指电极，各自接到尾线；商用参照件 Interlink FSR 402。Akai 把 16 个这样的区做成一整片备件。",
    params: [
      { k: "电极", v: "银浆 PTF 丝印；也可用镀金铜（柔性板）", src: "fsrGuide" },
      { k: "参照件 FSR 402", v: "外径 18.28 mm，有效区 12.7 mm，厚 0.45 mm（标称 0.55）", src: "fsr402" },
      { k: "力程", v: "0.1–10 N（402）；系列 ~0.2–20 N", src: "fsr402" },
      { k: "未加载电阻", v: ">10 MΩ", src: "fsr402" },
      { k: "迟滞", v: "+10%（(RF+ − RF−)/RF+）", src: "fsr402" },
      { k: "长期漂移", v: "<5% / log10(time)（1 kg，35 天）", src: "fsr402" },
      { k: "重复性", v: "单件 ±2%；件间 ±6%", src: "fsr402" },
      { k: "寿命", v: "10,000,000 次（1 kg，4 Hz，−10%）", src: "fsrGuide" },
      { k: "温度", v: "−30 … +70 °C", src: "fsr402" },
      { k: "Akai 备件", v: "1AOTFSR16KEY-AD33（Live/X/Live II/Touch/Studio MK2/MPD226/232）、-AD4A（One/Key），16 键整片，约 $27.5", src: "akaiFsr" },
    ],
  },
  electrodes: {
    name: "叉指电极（PCB 铜层）",
    en: "Interdigitated electrodes on PCB",
    color: "#d9a441",
    role: "胶粒方案把传感做在主板上：两组梳状铜电极，表面镀金或印碳膜防氧化。",
    params: [
      { k: "接触电阻", v: "<200 Ω（Au/Ni 镀层）", src: "jw" },
      { k: "指宽 / 间距", v: "≈0.3 / 0.3 mm（示意）" },
      { k: "Launchpad Pro", v: "拆解显示 keymat + 单主板结构，电极图形未公开", src: "lpTeardown" },
    ],
  },
  coilForce: {
    name: "力感应线圈层",
    en: "Force coil layer",
    color: "#64d2ff",
    role: "电感式方案的第一层：测目标片下压距离 → 力 / 速度。",
    params: [
      { k: "方案", v: "两层非接触电感传感之一（力）", src: "cdmPush" },
      { k: "线圈几何 / 频率", v: "未公开（示意）" },
    ],
  },
  coilPos: {
    name: "位置感应线圈层",
    en: "Position coil layer",
    color: "#4dabf7",
    role: "第二层：多线圈重心给出手指 X/Y，连续且能感知 pad 之间。",
    params: [
      { k: "方案", v: "两层非接触电感传感之二（位置），X/Y 连续，可感知 pad 之间", src: "cdmPush" },
      { k: "MPE 维度", v: "pressure、slide、per-note pitch bend", src: "abletonMpe" },
    ],
  },
  led: {
    name: "RGB LED",
    en: "RGB LED",
    color: "#ff6b6b",
    role: "pad 中心一颗顶发光 RGB；64 pad 面板正好一颗 12×16 矩阵驱动。",
    params: [
      { k: "驱动参照 IS31FL3733", v: "12×16 = 192 通道 = 64 颗 RGB，1/12 扫描", src: "is31" },
      { k: "调光", v: "每颗 8-bit PWM（256 级）+ 256 级全局电流", src: "is31" },
      { k: "接口 / 供电", v: "I²C 1 MHz；2.7–5.5 V；开路/短路检测", src: "is31" },
      { k: "封装", v: "3528 / 2020 顶发光 RGB（示意）" },
    ],
  },
  pcb: {
    name: "Pad PCB",
    en: "Pad PCB",
    color: "#2e9e63",
    role: "承载 LED、电极或线圈、多路器与分压电阻。",
    params: [
      { k: "板厚", v: "FR-4 1.6 mm（通用规格）" },
      { k: "分压读出", v: "Vout = V+ · RM / (RM + RFSR)；RM 决定力程与灵敏度", src: "fsr402" },
      { k: "RM 曲线族", v: "以 +5 V 给出多种 RM 的 F–Vout 曲线，仅供参考", src: "fsrGuide" },
      { k: "多通道接口", v: "RC 定时法：用 RMIN / RMAX 校准零点与满量程后分区", src: "fsrGuide" },
      { k: "扫描率", v: "每 pad 1–4 kHz（示意；Δt 法需要 ≥1 kHz）" },
    ],
  },
  foam: {
    name: "缓冲泡棉",
    en: "Foam cushion",
    color: "#55606e",
    role: "吸收敲击冲击、降低机械噪声；打击垫类产品用更厚的 PU 泡棉作为整块击打层。",
    params: [
      { k: "打击垫参照", v: "PU 泡棉 5–20 mm，Asker C 10–60（优选 30–50），孔隙率 30–80%", src: "yamaha" },
      { k: "pad 控制器", v: "PORON 类 0.5–1.0 mm（示意）" },
    ],
  },
  stiffener: {
    name: "金属加强板",
    en: "Stiffener plate",
    color: "#9aa4b1",
    role: "让 PCB 不随敲击弯曲；FSR 对基底平整度敏感（须贴在洁净、平整、刚性表面）。",
    params: [
      { k: "金属保持层", v: "0.5–3 mm 铁 / 钢 / 镀锌钢 / 铝", src: "yamaha" },
      { k: "FSR 安装要求", v: "安装胶面贴在洁净、光滑、刚性的表面", src: "fsrGuide" },
    ],
  },
};

// 三种传感方案下，单 pad 视图自上而下的层序
export const SINGLE_ORDER = {
  fsrFilm: ["cap", "membrane", "nub", "sensorTop", "sensorSpacer", "sensorBottom", "led", "pcb", "foam", "stiffener"],
  pillOnPcb: ["cap", "membrane", "pill", "electrodes", "led", "pcb", "foam", "stiffener"],
  inductive: ["cap", "membrane", "target", "coilForce", "coilPos", "led", "pcb", "foam", "stiffener"],
};

// 固件 / 算法参数（有出处）
export const ALGO = [
  { k: "触发阈值 threshold", v: "扫描起点，同时是速度下限", src: "hellodrum" },
  { k: "灵敏度 sensitivity", v: "峰值上限；峰值在 threshold…sensitivity 之间线性映射到 0–127", src: "hellodrum" },
  { k: "scan time", v: "过阈值后取最大值的窗口（ms）", src: "hellodrum" },
  { k: "mask time", v: "触发后禁止重扫的时间（ms），抑制振动重触发", src: "hellodrum" },
  { k: "速度曲线", v: "类型 0–4（线性 / 对数 / 指数等）", src: "hellodrum" },
  { k: "带通预滤波", v: "40–400 Hz（压电 pad 信号约 200 Hz），约 2 ms 群延迟用 FIFO 补偿", src: "edrumulus" },
  { k: "重触发抑制", v: "检测后从信号中减去指数衰减曲线；衰减量随击打位置调整", src: "edrumulus" },
  { k: "位置感知（压电）", v: "峰值处低通 / 原始信号功率比", src: "edrumulus" },
  { k: "高密阵列帧率", v: "Sensel Morph 125 Hz（8 ms）/ 500 Hz（2 ms）", src: "sensel" },
];
