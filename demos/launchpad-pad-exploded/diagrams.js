// 横截面示意 SVG。每张图左侧为 pad 剖面，右侧为该方案的特征曲线。

const W = 400;
const H = 210;

function svgOpen(title) {
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${title}" xmlns="http://www.w3.org/2000/svg">`;
}

// 手指 + 力箭头
function finger(x = 150, y = 8) {
  return `
    <path d="M${x - 14} ${y} q14 -4 28 0 v22 h-28z" fill="#d9a48a" opacity="0.9"/>
    <path class="d-line" d="M${x} ${y + 24} v14"/>
    <path class="d-arrow" d="M${x - 4} ${y + 36} l4 7 l4 -7z"/>
    <text class="d-text" x="${x + 8}" y="${y + 40}">F</text>`;
}

// 通用的硅胶帽（顶部圆角、底部带裙边）
function cap(x = 90, w = 120, y = 60, h = 34, r = 10) {
  return `<path class="d-sil" d="M${x} ${y + h} v-${h - r} q0 -${r} ${r} -${r} h${w - 2 * r} q${r} 0 ${r} ${r} v${h - r} h-10 v-8 h-${w - 20} v8z"/>`;
}

function pcb(y = 128, x = 40, w = 220, h = 14) {
  return `<rect class="d-pcb" x="${x}" y="${y}" width="${w}" height="${h}"/>
    <text class="d-text" x="${x + 4}" y="${y + h + 12}">PCB</text>`;
}

// 右侧小图坐标系
function axes(x0 = 285, y0 = 150, w = 100, h = 100, xl = "F", yl = "R") {
  return `
    <path class="d-line-dim" d="M${x0} ${y0 - h} v${h} h${w}"/>
    <text class="d-text" x="${x0 + w - 6}" y="${y0 + 12}">${xl}</text>
    <text class="d-text" x="${x0 - 12}" y="${y0 - h + 8}">${yl}</text>`;
}

const DIAGRAMS = {
  pill(title) {
    let fingers = "";
    for (let i = 0; i < 10; i++) {
      const x = 100 + i * 10;
      fingers += `<rect class="${i % 2 ? "d-cu2" : "d-cu"}" x="${x}" y="122" width="6" height="6"/>`;
    }
    return `${svgOpen(title)}
      ${finger(150, 6)}
      ${cap(90, 120, 62, 40)}
      <rect class="d-pill" x="118" y="102" width="64" height="20" rx="4"/>
      <text class="d-text" x="188" y="118">导电胶粒</text>
      ${fingers}
      <text class="d-text" x="205" y="128">叉指电极</text>
      ${pcb(128)}
      <path class="d-line" d="M40 100 h34"/><text class="d-text" x="40" y="96">硅胶帽</text>
      ${axes(285, 150, 100, 100, "F", "R")}
      <path class="d-curve" d="M288 60 C 300 130, 330 145, 383 148"/>
      <text class="d-text" x="290" y="170">R ≈ k / F</text>
      <text class="d-text" x="290" y="184">1 MΩ → 几 kΩ</text>
    </svg>`;
  },

  fsr(title) {
    let el = "";
    for (let i = 0; i < 12; i++) {
      el += `<rect class="${i % 2 ? "d-cu2" : "d-cu"}" x="${94 + i * 9}" y="121" width="5" height="3"/>`;
    }
    return `${svgOpen(title)}
      ${finger(150, 6)}
      ${cap(90, 120, 62, 40)}
      <rect class="d-nub" x="122" y="102" width="56" height="12" rx="3"/>
      <text class="d-text" x="184" y="112">触发凸台（不导电）</text>
      <rect class="d-ink" x="60" y="115" width="180" height="6"/>
      <rect class="d-film" x="60" y="121" width="180" height="4"/>
      ${el}
      <rect class="d-film" x="60" y="124" width="180" height="3"/>
      <path class="d-line" d="M240 118 h20"/><text class="d-text" x="262" y="121">半导电油墨</text>
      <path class="d-line" d="M240 125 h20"/><text class="d-text" x="262" y="131">银浆电极 / PET</text>
      ${pcb(128)}
      ${axes(285, 150, 100, 100, "F", "R")}
      <path class="d-curve" d="M288 58 C 296 120, 320 140, 383 146"/>
      <path class="d-curve2" d="M288 58 C 300 128, 326 146, 383 148" stroke-dasharray="4 3"/>
      <text class="d-text" x="290" y="170">实线加压 / 虚线卸压</text>
      <text class="d-text" x="290" y="184">迟滞比胶粒小</text>
    </svg>`;
  },

  piezo(title) {
    return `${svgOpen(title)}
      ${finger(150, 6)}
      ${cap(90, 120, 62, 40)}
      <rect class="d-foam" x="96" y="102" width="108" height="14"/>
      <text class="d-text" x="208" y="112">泡棉传力/隔振</text>
      <rect class="d-piezo" x="110" y="116" width="80" height="4"/>
      <rect class="d-ceramic" x="118" y="120" width="64" height="4"/>
      <text class="d-text" x="196" y="126">压电陶瓷 + 黄铜片</text>
      <path class="d-line" d="M150 124 v4"/>
      ${pcb(128)}
      ${axes(285, 150, 100, 100, "t", "V")}
      <path class="d-curve" d="M288 120 h20 C 312 60, 318 60, 324 120 C 328 140, 334 140, 340 120 C 346 110, 352 128, 383 120"/>
      <text class="d-text" x="290" y="170">脉冲峰值 ∝ 速度</text>
      <text class="d-text" x="290" y="184">按住不动 → 0</text>
    </svg>`;
  },

  dual(title) {
    return `${svgOpen(title)}
      ${finger(150, 6)}
      ${cap(90, 120, 56, 40)}
      <rect class="d-pill" x="140" y="96" width="20" height="18" rx="2"/>
      <text class="d-text" x="164" y="104">柱塞</text>
      <rect class="d-film" x="70" y="114" width="160" height="3"/>
      <rect class="d-cu" x="136" y="112" width="28" height="3"/>
      <rect class="d-foam" x="70" y="117" width="160" height="4" opacity="0.5"/>
      <rect class="d-film" x="70" y="121" width="160" height="3"/>
      <rect class="d-cu2" x="136" y="121" width="28" height="3"/>
      <path class="d-line" d="M232 115 h20"/><text class="d-text" x="254" y="118">触点 A（先闭合）</text>
      <path class="d-line" d="M232 123 h20"/><text class="d-text" x="254" y="132">触点 B（后闭合）</text>
      ${pcb(128)}
      ${axes(285, 150, 100, 100, "t", "")}
      <path class="d-curve" d="M288 100 h30 v-16 h65"/>
      <path class="d-curve2" d="M288 140 h50 v-16 h45"/>
      <path class="d-line-dim" d="M318 60 v90 M338 60 v90"/>
      <text class="d-text" x="322" y="70">Δt</text>
      <text class="d-text" x="290" y="170">v ∝ 1 / Δt</text>
      <text class="d-text" x="290" y="184">纯数字，无 ADC</text>
    </svg>`;
  },

  cap(title) {
    let el = "";
    for (let i = 0; i < 8; i++) {
      el += `<rect class="${i % 2 ? "d-cu2" : "d-cu"}" x="${78 + i * 18}" y="122" width="12" height="4"/>`;
    }
    return `${svgOpen(title)}
      ${finger(150, 6)}
      ${cap(90, 120, 62, 40)}
      <rect class="d-sil" x="70" y="102" width="160" height="20" opacity="0.6"/>
      <text class="d-text" x="234" y="112">可压缩硅胶介质</text>
      <path class="d-field" d="M96 122 q54 -30 108 0 M114 122 q36 -20 72 0 M132 122 q18 -10 36 0"/>
      ${el}
      <text class="d-text" x="226" y="128">电容电极阵列</text>
      ${pcb(128)}
      ${axes(285, 150, 100, 100, "x/F", "C")}
      <path class="d-curve" d="M288 140 C 320 130, 340 100, 383 60"/>
      <text class="d-text" x="290" y="170">C ∝ ε·A / d</text>
      <text class="d-text" x="290" y="184">位置 + 面积 + 压力</text>
    </svg>`;
  },

  hall(title) {
    return `${svgOpen(title)}
      ${finger(150, 6)}
      ${cap(90, 120, 56, 44)}
      <rect class="d-mag" x="140" y="90" width="20" height="10" rx="1"/>
      <text class="d-text" x="164" y="98">磁铁</text>
      <path class="d-field" d="M150 100 q-22 12 0 24 M150 100 q22 12 0 24 M150 100 q-40 14 0 28 M150 100 q40 14 0 28"/>
      <rect class="d-ic" x="141" y="120" width="18" height="8" rx="1"/>
      <text class="d-text" x="164" y="127">霍尔 IC</text>
      <path class="d-line" d="M40 100 h34"/><text class="d-text" x="40" y="96">硅胶帽</text>
      <path class="d-line" d="M100 104 v20"/><path class="d-arrow" d="M96 122 l4 7 l4 -7z"/>
      <text class="d-text" x="82" y="118">行程</text>
      ${pcb(128)}
      ${axes(285, 150, 100, 100, "d", "B")}
      <path class="d-curve" d="M288 60 C 300 120, 330 140, 383 146"/>
      <text class="d-text" x="290" y="170">B ∝ 1 / d³</text>
      <text class="d-text" x="290" y="184">无接触，无漂移</text>
    </svg>`;
  },
};

DIAGRAMS.inductive = function (title) {
  let coils = "";
  for (let i = 0; i < 3; i++) {
    const r = 10 + i * 8;
    coils += `<rect class="d-cu" x="${150 - r}" y="121" width="${2 * r}" height="2" rx="1"/>`;
  }
  let pos = "";
  for (let i = 0; i < 5; i++) pos += `<rect class="d-cu2" x="${78 + i * 36}" y="126" width="26" height="2" rx="1"/>`;
  return `${svgOpen(title)}
    ${finger(150, 6)}
    ${cap(90, 120, 56, 44)}
    <rect class="d-metal" x="128" y="92" width="44" height="3" rx="1"/>
    <text class="d-text" x="176" y="97">导电目标片</text>
    <path class="d-field" d="M150 100 q-24 10 0 20 M150 100 q24 10 0 20 M150 98 q-38 12 0 24 M150 98 q38 12 0 24"/>
    ${coils}
    <text class="d-text" x="192" y="124">力线圈（下压距离）</text>
    ${pos}
    <text class="d-text" x="262" y="136">位置线圈阵列</text>
    ${pcb(130, 40, 220, 12)}
    <path class="d-line" d="M40 100 h34"/><text class="d-text" x="40" y="96">硅胶帽</text>
    ${axes(285, 150, 100, 100, "d", "L")}
    <path class="d-curve" d="M288 60 C 305 110, 335 135, 383 142"/>
    <text class="d-text" x="290" y="170">涡流 → L 随 d 变化</text>
    <text class="d-text" x="290" y="184">X/Y 由多线圈重心</text>
  </svg>`;
};

export function techSvg(id, title) {
  const fn = DIAGRAMS[id];
  return fn ? fn(title) : "";
}

// 信号链
export function signalChainSvg() {
  const stages = [
    ["Pad", "胶粒 / FSR / 压电"],
    ["前端", "分压 · 保护 · 上拉"],
    ["MUX", "16:1 / 64:4 模拟多路"],
    ["ADC", "12 bit · 1–4 kHz / pad"],
    ["触发", "阈值 · 去抖 · 邻 pad 抑制"],
    ["速度", "Δt 或斜率峰值 · 曲线映射"],
    ["压力", "稳态 · 低通 · 迟滞补偿"],
    ["MIDI", "Note On · Poly AT · MPE"],
  ];
  const bw = 104;
  const gap = 14;
  const total = stages.length * bw + (stages.length - 1) * gap;
  const x0 = 10;
  const width = total + 20;
  let out = `<svg viewBox="0 0 ${width} 130" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="pad 信号链">`;
  stages.forEach((s, i) => {
    const x = x0 + i * (bw + gap);
    const hi = i === 5 || i === 6;
    out += `<rect class="${hi ? "d-box-hi" : "d-box"}" x="${x}" y="30" width="${bw}" height="62"/>
      <text class="d-text-b" x="${x + bw / 2}" y="54" text-anchor="middle" font-weight="600">${s[0]}</text>
      <text class="d-text" x="${x + bw / 2}" y="74" text-anchor="middle">${s[1]}</text>`;
    if (i < stages.length - 1) {
      out += `<path class="d-line" d="M${x + bw} 61 h${gap - 4}"/><path class="d-arrow" d="M${x + bw + gap - 6} 57 l6 4 l-6 4z"/>`;
    }
  });
  out += `<text class="d-text" x="${x0}" y="118">模拟域 ⟵ ── ── ── ── ── ── ── ── ── ── ── ── ── ⟶ 数字域（MCU 固件）</text>`;
  out += `</svg>`;
  return out;
}
