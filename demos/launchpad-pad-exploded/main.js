import * as THREE from "three";
import { LAYER_ORDER, LAYERS, MACHINES, SENSING, TECH, COMPARE, SINGLE_LAYERS, SINGLE_ORDER, REFERENCES, ALGO } from "./data.js";
import { techSvg, signalChainSvg } from "./diagrams.js";

// ---------------------------------------------------------------------------
// DOM
// ---------------------------------------------------------------------------
const glCanvas = document.getElementById("gl");
const overlay = document.getElementById("overlay");
const octx = overlay.getContext("2d");
const labelsEl = document.getElementById("labels");
const stageEl = document.getElementById("stage");
const explodeInput = document.getElementById("explode");
const explodeOut = document.getElementById("explodeOut");
const clipInput = document.getElementById("clip");
const spinInput = document.getElementById("spin");
const labelsInput = document.getElementById("showLabels");
const resetBtn = document.getElementById("resetView");
const layerListEl = document.getElementById("layerList");
const layerInfoEl = document.getElementById("layerInfo");
const machineTabsEl = document.getElementById("machineTabs");
const scopeCanvas = document.getElementById("scope");
const scopeOut = document.getElementById("scopeOut");

// ---------------------------------------------------------------------------
// Renderer / scene / camera
// ---------------------------------------------------------------------------
const renderer = new THREE.WebGLRenderer({ canvas: glCanvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;

const scene = new THREE.Scene();
scene.background = new THREE.Color("#0b0c10");
scene.fog = new THREE.Fog("#0b0c10", 600, 1400);

const camera = new THREE.PerspectiveCamera(36, 1, 1, 4000);

scene.add(new THREE.HemisphereLight("#cfd6e6", "#1a1c22", 0.9));
const key = new THREE.DirectionalLight("#ffffff", 1.6);
key.position.set(180, 320, 220);
scene.add(key);
const fill = new THREE.DirectionalLight("#9fb3ff", 0.5);
fill.position.set(-260, 140, -180);
scene.add(fill);
const rim = new THREE.DirectionalLight("#ffd9a0", 0.35);
rim.position.set(0, 60, -400);
scene.add(rim);

const grid = new THREE.GridHelper(900, 45, "#1c1f28", "#15171d");
grid.position.y = -40;
scene.add(grid);

const clipPlane = new THREE.Plane(new THREE.Vector3(0, 0, -1), 0);

// ---------------------------------------------------------------------------
// Minimal orbit controls (no addon dependency)
// ---------------------------------------------------------------------------
class Orbit {
  constructor(dom, cam) {
    this.dom = dom;
    this.cam = cam;
    this.target = new THREE.Vector3(0, 30, 0);
    this.theta = 0.7;
    this.phi = 1.02;
    this.radius = 380;
    this.home = { theta: this.theta, phi: this.phi, radius: this.radius };
    this.pointers = new Map();
    this.pinchDist = 0;
    this.dragged = false;
    dom.addEventListener("pointerdown", (e) => this.down(e));
    dom.addEventListener("pointermove", (e) => this.move(e));
    dom.addEventListener("pointerup", (e) => this.up(e));
    dom.addEventListener("pointercancel", (e) => this.up(e));
    dom.addEventListener("wheel", (e) => this.wheel(e), { passive: false });
    dom.style.touchAction = "none";
  }
  setHome(radius, targetY) {
    this.home.radius = radius;
    this.radius = radius;
    this.target.set(0, targetY, 0);
  }
  reset() {
    this.theta = this.home.theta;
    this.phi = this.home.phi;
    this.radius = this.home.radius;
  }
  down(e) {
    this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    this.dragged = false;
    this.dom.setPointerCapture(e.pointerId);
    if (this.pointers.size === 2) this.pinchDist = this.pinch();
  }
  pinch() {
    const [a, b] = [...this.pointers.values()];
    return Math.hypot(a.x - b.x, a.y - b.y);
  }
  move(e) {
    const p = this.pointers.get(e.pointerId);
    if (!p) return;
    const dx = e.clientX - p.x;
    const dy = e.clientY - p.y;
    p.x = e.clientX;
    p.y = e.clientY;
    if (Math.abs(dx) + Math.abs(dy) > 2) this.dragged = true;
    if (this.pointers.size === 1) {
      this.theta -= dx * 0.006;
      this.phi = THREE.MathUtils.clamp(this.phi - dy * 0.006, 0.12, 1.5);
    } else if (this.pointers.size === 2) {
      const d = this.pinch();
      if (this.pinchDist > 0) this.zoom(this.pinchDist / d);
      this.pinchDist = d;
    }
  }
  up(e) {
    this.pointers.delete(e.pointerId);
    try {
      this.dom.releasePointerCapture(e.pointerId);
    } catch (_) {
      /* ignore */
    }
  }
  wheel(e) {
    e.preventDefault();
    this.zoom(Math.exp(e.deltaY * 0.0012));
  }
  zoom(f) {
    this.radius = THREE.MathUtils.clamp(this.radius * f, this.home.radius * 0.35, this.home.radius * 2.6);
  }
  update() {
    const s = Math.sin(this.phi);
    this.cam.position.set(
      this.target.x + this.radius * s * Math.sin(this.theta),
      this.target.y + this.radius * Math.cos(this.phi),
      this.target.z + this.radius * s * Math.cos(this.theta)
    );
    this.cam.lookAt(this.target);
  }
}
const orbit = new Orbit(glCanvas, camera);

// ---------------------------------------------------------------------------
// Geometry helpers
// ---------------------------------------------------------------------------
function roundedRectPath(PathClass, cx, cy, w, h, r) {
  const p = new PathClass();
  const x = cx - w / 2;
  const y = cy - h / 2;
  p.moveTo(x + r, y);
  p.lineTo(x + w - r, y);
  p.quadraticCurveTo(x + w, y, x + w, y + r);
  p.lineTo(x + w, y + h - r);
  p.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  p.lineTo(x + r, y + h);
  p.quadraticCurveTo(x, y + h, x, y + h - r);
  p.lineTo(x, y + r);
  p.quadraticCurveTo(x, y, x + r, y);
  return p;
}

// 沿 Y 方向挤出（shape 定义在 XZ 平面）
function extrudeUp(shape, depth, opts = {}) {
  const geo = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: false, curveSegments: 6, ...opts });
  geo.rotateX(-Math.PI / 2);
  return geo;
}

function plastic(color, extra = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.75, metalness: 0.05, side: THREE.DoubleSide, ...extra });
}

// ---------------------------------------------------------------------------
// Canvas textures
// ---------------------------------------------------------------------------
function makeCanvas(size) {
  const c = document.createElement("canvas");
  c.width = size;
  c.height = size;
  return c;
}

function padCenters(m) {
  const n = m.grid;
  const pitch = m.padSize + m.gap;
  const out = [];
  for (let j = 0; j < n; j++) {
    for (let i = 0; i < n; i++) {
      out.push({ i, j, x: (i - (n - 1) / 2) * pitch, z: (j - (n - 1) / 2) * pitch });
    }
  }
  return out;
}

// 叉指电极图案（透明背景，覆在 PCB 上）
function electrodeTexture(m, W) {
  const size = 1024;
  const c = makeCanvas(size);
  const ctx = c.getContext("2d");
  const s = size / W;
  const p = m.padSize;
  const r = p * 0.36 * s;
  const step = Math.max(4, r / 7);
  for (const pc of padCenters(m)) {
    const cx = size / 2 + pc.x * s;
    const cy = size / 2 + pc.z * s;
    // 两条弧形母线
    ctx.lineWidth = step * 0.5;
    ctx.strokeStyle = "#d9a441";
    ctx.beginPath();
    ctx.arc(cx, cy, r, Math.PI * 0.55, Math.PI * 1.45);
    ctx.stroke();
    ctx.strokeStyle = "#efc86b";
    ctx.beginPath();
    ctx.arc(cx, cy, r, -Math.PI * 0.45, Math.PI * 0.45);
    ctx.stroke();
    // 交错梳指
    const rows = Math.floor((2 * r) / step);
    for (let k = 0; k < rows; k++) {
      const y = cy - r + (k + 0.5) * step;
      const half = Math.sqrt(Math.max(0, r * r - (y - cy) * (y - cy)));
      if (half < step) continue;
      const even = k % 2 === 0;
      ctx.strokeStyle = even ? "#d9a441" : "#efc86b";
      ctx.lineWidth = step * 0.42;
      ctx.beginPath();
      if (even) {
        ctx.moveTo(cx - half, y);
        ctx.lineTo(cx + half - step * 1.1, y);
      } else {
        ctx.moveTo(cx - half + step * 1.1, y);
        ctx.lineTo(cx + half, y);
      }
      ctx.stroke();
    }
    // LED 中心留空
    ctx.save();
    ctx.globalCompositeOperation = "destination-out";
    ctx.beginPath();
    ctx.arc(cx, cy, p * 0.09 * s, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

// FSR 薄膜图案：琥珀色 PET，圆形有效区，银浆走线汇到尾部
function filmTexture(m, W) {
  const size = 1024;
  const c = makeCanvas(size);
  const ctx = c.getContext("2d");
  const s = size / W;
  ctx.fillStyle = "#c8791e";
  ctx.fillRect(0, 0, size, size);
  const p = m.padSize;
  const centers = padCenters(m);
  const busY = size - 40;
  ctx.strokeStyle = "#e6e9ee";
  ctx.lineWidth = 2.2;
  for (const pc of centers) {
    const cx = size / 2 + pc.x * s;
    const cy = size / 2 + pc.z * s;
    ctx.beginPath();
    ctx.moveTo(cx + (pc.i % 2 ? 6 : -6), cy + p * 0.36 * s);
    ctx.lineTo(cx + (pc.i % 2 ? 6 : -6), busY);
    ctx.stroke();
  }
  ctx.lineWidth = 6;
  ctx.beginPath();
  ctx.moveTo(size * 0.12, busY);
  ctx.lineTo(size * 0.88, busY);
  ctx.stroke();
  for (const pc of centers) {
    const cx = size / 2 + pc.x * s;
    const cy = size / 2 + pc.z * s;
    ctx.fillStyle = "#4a2c0d";
    ctx.beginPath();
    ctx.arc(cx, cy, p * 0.36 * s, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#e6e9ee";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(cx, cy, p * 0.36 * s, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = "#c8791e";
    ctx.beginPath();
    ctx.arc(cx, cy, p * 0.1 * s, 0, Math.PI * 2);
    ctx.fill();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

// PCB 丝印
function pcbTexture(m, W) {
  const size = 1024;
  const c = makeCanvas(size);
  const ctx = c.getContext("2d");
  const s = size / W;
  ctx.fillStyle = "#0f5a38";
  ctx.fillRect(0, 0, size, size);
  ctx.strokeStyle = "rgba(255,255,255,0.55)";
  ctx.lineWidth = 2;
  ctx.font = `${Math.round(11 * s)}px monospace`;
  ctx.fillStyle = "rgba(255,255,255,0.6)";
  const p = m.padSize;
  for (const pc of padCenters(m)) {
    const cx = size / 2 + pc.x * s;
    const cy = size / 2 + pc.z * s;
    const w = p * 0.88 * s;
    ctx.strokeRect(cx - w / 2, cy - w / 2, w, w);
    ctx.fillText(`P${pc.j * m.grid + pc.i + 1}`, cx - w / 2 + 4, cy - w / 2 + 12 * s);
    ctx.strokeRect(cx - 3 * s, cy - 3 * s, 6 * s, 6 * s);
  }
  // 走线
  ctx.strokeStyle = "rgba(200,240,210,0.28)";
  ctx.lineWidth = 1.4;
  for (const pc of padCenters(m)) {
    const cx = size / 2 + pc.x * s;
    const cy = size / 2 + pc.z * s;
    ctx.beginPath();
    ctx.moveTo(cx + 8, cy + p * 0.44 * s);
    ctx.lineTo(cx + 8, size - 26);
    ctx.stroke();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

// ---------------------------------------------------------------------------
// Assembly
// ---------------------------------------------------------------------------
let assembly = null; // { group, layers: Map<id, {group, thickness, restY, index, meshes}>, W, m, caps: [], order, spacing }
let currentMachineId = "mpc";
let viewMode = "machine"; // "machine" | "single"
const defs = () => (viewMode === "single" ? SINGLE_LAYERS : LAYERS);
const REF_INDEX = new Map(REFERENCES.map((r, i) => [r.id, i + 1]));

function disposeAssembly() {
  if (!assembly) return;
  scene.remove(assembly.group);
  assembly.group.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    if (o.material) {
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      for (const mt of mats) {
        if (mt.map) mt.map.dispose();
        mt.dispose();
      }
    }
  });
  assembly = null;
}

function buildAssembly(m) {
  disposeAssembly();
  const n = m.grid;
  const pitch = m.padSize + m.gap;
  const margin = 9;
  const W = n * pitch - m.gap + 2 * margin;
  const centers = padCenters(m);
  const sensing = SENSING[m.sensing];

  const T = {
    chassis: 2.0,
    wall: 11,
    stiffener: 1.2,
    pcb: 1.6,
    sensor: sensing.sensorLayer === "film" ? 0.4 : 0.15,
    pill: 1.0,
    cap: m.capHeight,
  };
  T.frame = Math.max(2.4, m.capHeight * 0.72);

  const group = new THREE.Group();
  const layers = new Map();
  const caps = [];

  const addLayer = (id, thickness, restY, index) => {
    const g = new THREE.Group();
    g.userData.layerId = id;
    layers.set(id, { group: g, thickness, restY, index, meshes: [] });
    group.add(g);
    return g;
  };
  const tag = (mesh, id) => {
    mesh.userData.layerId = id;
    layers.get(id).meshes.push(mesh);
    return mesh;
  };

  let y = 0;

  // chassis
  {
    const g = addLayer("chassis", T.wall, y, 0);
    const mat = plastic("#20222a", { roughness: 0.6 });
    const outer = W + 6;
    const floor = new THREE.Mesh(new THREE.BoxGeometry(outer, T.chassis, outer), mat);
    floor.position.y = T.chassis / 2;
    g.add(tag(floor, "chassis"));
    const wallT = 2.2;
    const wallGeoX = new THREE.BoxGeometry(outer, T.wall, wallT);
    const wallGeoZ = new THREE.BoxGeometry(wallT, T.wall, outer - 2 * wallT);
    for (const sgn of [-1, 1]) {
      const wx = new THREE.Mesh(wallGeoX, mat);
      wx.position.set(0, T.wall / 2, sgn * (outer / 2 - wallT / 2));
      g.add(tag(wx, "chassis"));
      const wz = new THREE.Mesh(wallGeoZ, mat);
      wz.position.set(sgn * (outer / 2 - wallT / 2), T.wall / 2, 0);
      g.add(tag(wz, "chassis"));
    }
    // 螺柱
    const bossGeo = new THREE.CylinderGeometry(2.2, 2.6, T.wall - 3, 12);
    const bossMat = plastic("#2b2e37");
    for (const sx of [-1, 1]) {
      for (const sz of [-1, 1]) {
        const b = new THREE.Mesh(bossGeo, bossMat);
        b.position.set(sx * (W / 2 - 4), (T.wall - 3) / 2 + T.chassis, sz * (W / 2 - 4));
        g.add(tag(b, "chassis"));
      }
    }
    y = T.chassis;
  }

  // stiffener
  {
    const g = addLayer("stiffener", T.stiffener, y, 1);
    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(W - 3, T.stiffener, W - 3),
      new THREE.MeshStandardMaterial({ color: "#a9b1bd", metalness: 0.75, roughness: 0.35, side: THREE.DoubleSide })
    );
    mesh.position.y = T.stiffener / 2;
    g.add(tag(mesh, "stiffener"));
    y += T.stiffener;
  }

  // pcb
  {
    const g = addLayer("pcb", T.pcb, y, 2);
    const top = new THREE.MeshStandardMaterial({ map: pcbTexture(m, W), roughness: 0.6, metalness: 0.1, side: THREE.DoubleSide });
    const side = plastic("#0c4a2e");
    const board = new THREE.Mesh(new THREE.BoxGeometry(W - 1, T.pcb, W - 1), [side, side, top, side, side, side]);
    board.position.y = T.pcb / 2;
    g.add(tag(board, "pcb"));
    // LEDs
    const ledGeo = new THREE.BoxGeometry(2.2, 0.9, 2.2);
    const ledHousing = new THREE.BoxGeometry(3.2, 0.7, 3.2);
    const housingMat = plastic("#e9ecef");
    centers.forEach((pc, k) => {
      const col = new THREE.Color(m.ledPalette[(pc.i + pc.j * 3) % m.ledPalette.length]);
      const h = new THREE.Mesh(ledHousing, housingMat);
      h.position.set(pc.x, T.pcb + 0.35, pc.z);
      g.add(tag(h, "pcb"));
      const led = new THREE.Mesh(
        ledGeo,
        new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 1.6, roughness: 0.3, side: THREE.DoubleSide })
      );
      led.position.set(pc.x, T.pcb + 0.8, pc.z);
      led.userData.padIndex = k;
      g.add(tag(led, "pcb"));
    });
    // MUX / 驱动 IC 与连接器
    const icMat = plastic("#15171c", { roughness: 0.5 });
    const icGeo = new THREE.BoxGeometry(6, 1.2, 6);
    for (let k = 0; k < Math.max(2, n / 2); k++) {
      const ic = new THREE.Mesh(icGeo, icMat);
      ic.position.set(-W / 2 + 10 + k * 10, T.pcb + 0.6, W / 2 - 5);
      g.add(tag(ic, "pcb"));
    }
    const conn = new THREE.Mesh(new THREE.BoxGeometry(18, 3, 5), plastic("#f1f1f1"));
    conn.position.set(W / 2 - 16, T.pcb + 1.5, W / 2 - 5);
    g.add(tag(conn, "pcb"));
    y += T.pcb;
  }

  // sensor layer
  {
    const g = addLayer("sensor", T.sensor, y, 3);
    if (sensing.sensorLayer === "film") {
      const mat = new THREE.MeshStandardMaterial({
        map: filmTexture(m, W),
        roughness: 0.4,
        metalness: 0.05,
        transparent: true,
        opacity: 0.92,
        side: THREE.DoubleSide,
      });
      const film = new THREE.Mesh(new THREE.BoxGeometry(W - 8, T.sensor, W - 8), mat);
      film.position.y = T.sensor / 2;
      g.add(tag(film, "sensor"));
      // FPC 尾线
      const tail = new THREE.Mesh(new THREE.BoxGeometry(14, T.sensor, 12), plastic("#c8791e", { transparent: true, opacity: 0.9 }));
      tail.position.set(W / 2 - 22, T.sensor / 2, W / 2 - 2);
      g.add(tag(tail, "sensor"));
    } else if (sensing.sensorLayer === "coil") {
      const ringGeo = new THREE.TorusGeometry(m.padSize * 0.3, 0.25, 8, 40);
      const ringGeo2 = new THREE.TorusGeometry(m.padSize * 0.18, 0.25, 8, 32);
      const matA = plastic("#4dabf7", { emissive: "#1c4f7a", emissiveIntensity: 0.6 });
      const matB = plastic("#64d2ff", { emissive: "#1c5f7a", emissiveIntensity: 0.6 });
      for (const pc of centers) {
        const r1 = new THREE.Mesh(ringGeo, matA);
        r1.rotation.x = Math.PI / 2;
        r1.position.set(pc.x, T.sensor, pc.z);
        g.add(tag(r1, "sensor"));
        const r2 = new THREE.Mesh(ringGeo2, matB);
        r2.rotation.x = Math.PI / 2;
        r2.position.set(pc.x, T.sensor + 0.3, pc.z);
        g.add(tag(r2, "sensor"));
      }
    } else {
      const mat = new THREE.MeshStandardMaterial({
        map: electrodeTexture(m, W),
        transparent: true,
        alphaTest: 0.2,
        roughness: 0.35,
        metalness: 0.6,
        side: THREE.DoubleSide,
      });
      const plane = new THREE.Mesh(new THREE.PlaneGeometry(W, W), mat);
      plane.rotation.x = -Math.PI / 2;
      plane.position.y = T.sensor;
      g.add(tag(plane, "sensor"));
    }
    y += T.sensor;
  }

  // pills
  {
    const g = addLayer("pill", T.pill, y, 4);
    const kind = sensing.sensorLayer;
    const r = kind === "coil" ? m.padSize * 0.28 : Math.min(m.padSize * 0.2, 5.2);
    const geo = new THREE.CylinderGeometry(kind === "coil" ? r : r * 0.92, r, kind === "coil" ? 0.5 : T.pill, 32);
    const mat =
      kind === "coil"
        ? new THREE.MeshStandardMaterial({ color: "#b8c4d0", metalness: 0.8, roughness: 0.3, side: THREE.DoubleSide })
        : plastic(kind === "electrodes" ? "#2a2a2e" : "#8a6a3a", { roughness: 0.9 });
    for (const pc of centers) {
      const pill = new THREE.Mesh(geo, mat);
      pill.position.set(pc.x, T.pill / 2, pc.z);
      g.add(tag(pill, "pill"));
    }
    y += T.pill;
  }

  const capBaseY = y;

  // frame（框底坐在传感层/PCB 边缘）
  {
    const frameBottom = capBaseY - T.pill;
    const g = addLayer("frame", T.frame, frameBottom, 5);
    const shape = roundedRectPath(THREE.Shape, 0, 0, W, W, 4);
    const clearance = 0.9;
    for (const pc of centers) {
      shape.holes.push(roundedRectPath(THREE.Path, pc.x, pc.z, m.padSize + clearance, m.padSize + clearance, m.padCorner + 0.4));
    }
    const mesh = new THREE.Mesh(extrudeUp(shape, T.frame), plastic("#2a2c33", { roughness: 0.7 }));
    g.add(tag(mesh, "frame"));
  }

  // caps
  {
    const g = addLayer("cap", T.cap, capBaseY, 6);
    const bevel = Math.min(1.0, T.cap * 0.25);
    const shape = roundedRectPath(THREE.Shape, 0, 0, m.padSize - 2 * bevel, m.padSize - 2 * bevel, Math.max(0.5, m.padCorner - bevel));
    const geo = new THREE.ExtrudeGeometry(shape, {
      depth: T.cap - 2 * bevel,
      bevelEnabled: true,
      bevelThickness: bevel,
      bevelSize: bevel,
      bevelSegments: 3,
      curveSegments: 6,
    });
    geo.rotateX(-Math.PI / 2);
    geo.translate(0, bevel, 0);
    centers.forEach((pc, k) => {
      const col = new THREE.Color(m.ledPalette[(pc.i + pc.j * 3) % m.ledPalette.length]);
      const mat = new THREE.MeshPhysicalMaterial({
        color: "#2b2c31",
        roughness: 0.55,
        metalness: 0.0,
        clearcoat: 0.25,
        clearcoatRoughness: 0.6,
        transparent: true,
        opacity: 0.94,
        emissive: col,
        emissiveIntensity: 0.22,
        side: THREE.DoubleSide,
      });
      const cap = new THREE.Mesh(geo, mat);
      cap.position.set(pc.x, 0, pc.z);
      cap.userData.padIndex = k;
      cap.userData.ledColor = col;
      cap.userData.press = 0;
      g.add(tag(cap, "cap"));
      caps.push(cap);
    });
  }

  // 整体居中：让装配体中心大约在原点
  const totalH = capBaseY + T.cap;
  group.position.y = -totalH / 2;
  scene.add(group);

  assembly = { group, layers, W, m, caps, totalH, T, order: LAYER_ORDER, spacing: W * 0.12 + 6 };
  orbit.setHome(W * 2.55, 30);
  applyExplode();
}

// ---------------------------------------------------------------------------
// Single-pad detail assembly（真实比例；参数见 SINGLE_LAYERS）
// ---------------------------------------------------------------------------
function silverElectrodeTexture(p, base = null) {
  const size = 512;
  const c = makeCanvas(size);
  const ctx = c.getContext("2d");
  if (base) {
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, size, size);
  }
  const s = size / p;
  const cx = size / 2;
  const cy = size / 2;
  const r = Math.min(6.35, p * 0.36) * s; // FSR 402 有效区 12.7 mm
  const step = Math.max(6, r / 9);
  ctx.lineWidth = step * 0.5;
  ctx.strokeStyle = "#dfe3e8";
  ctx.beginPath();
  ctx.arc(cx, cy, r, Math.PI * 0.55, Math.PI * 1.45);
  ctx.stroke();
  ctx.strokeStyle = "#f4f6f8";
  ctx.beginPath();
  ctx.arc(cx, cy, r, -Math.PI * 0.45, Math.PI * 0.45);
  ctx.stroke();
  const rows = Math.floor((2 * r) / step);
  for (let k = 0; k < rows; k++) {
    const y = cy - r + (k + 0.5) * step;
    const half = Math.sqrt(Math.max(0, r * r - (y - cy) * (y - cy)));
    if (half < step) continue;
    const even = k % 2 === 0;
    ctx.strokeStyle = even ? "#dfe3e8" : "#f4f6f8";
    ctx.lineWidth = step * 0.42;
    ctx.beginPath();
    if (even) {
      ctx.moveTo(cx - half, y);
      ctx.lineTo(cx + half - step * 1.1, y);
    } else {
      ctx.moveTo(cx - half + step * 1.1, y);
      ctx.lineTo(cx + half, y);
    }
    ctx.stroke();
  }
  // 尾线
  ctx.lineWidth = step * 0.5;
  ctx.strokeStyle = "#dfe3e8";
  ctx.beginPath();
  ctx.moveTo(cx - step, cy + r);
  ctx.lineTo(cx - step, size);
  ctx.moveTo(cx + step, cy + r);
  ctx.lineTo(cx + step, size);
  ctx.stroke();
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function buildSinglePad(m) {
  disposeAssembly();
  const p = m.padSize;
  const W = p + m.gap + 6; // 一个 pad 位的 PCB 瓦片
  const kind = SENSING[m.sensing].sensorLayer;
  const order = SINGLE_ORDER[m.sensing];
  const group = new THREE.Group();
  const layers = new Map();
  const caps = [];
  const idx = (id) => order.length - 1 - order.indexOf(id);

  const addLayer = (id, thickness, restY) => {
    const g = new THREE.Group();
    g.userData.layerId = id;
    layers.set(id, { group: g, thickness, restY, index: idx(id), meshes: [] });
    group.add(g);
    return g;
  };
  const tag = (mesh, id) => {
    mesh.userData.layerId = id;
    layers.get(id).meshes.push(mesh);
    return mesh;
  };
  const box = (id, w, t, d, mat, y0 = 0) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, t, d), mat);
    mesh.position.y = y0 + t / 2;
    return tag(mesh, id);
  };

  let y = 0;
  // 加强板 1.2 mm（0.5–3 mm 范围内）
  {
    const g = addLayer("stiffener", 1.2, y);
    g.add(box("stiffener", W, 1.2, W, new THREE.MeshStandardMaterial({ color: "#a9b1bd", metalness: 0.75, roughness: 0.35, side: THREE.DoubleSide })));
    y += 1.2;
  }
  // 泡棉 0.8 mm（示意）
  {
    const g = addLayer("foam", 0.8, y);
    g.add(box("foam", W - 1, 0.8, W - 1, plastic("#55606e", { roughness: 1 })));
    y += 0.8;
  }
  // PCB 1.6 mm
  {
    const g = addLayer("pcb", 1.6, y);
    const top = plastic("#0f5a38", { roughness: 0.6 });
    g.add(box("pcb", W, 1.6, W, top));
    // 丝印方框
    const ringShape = roundedRectPath(THREE.Shape, 0, 0, p * 0.9, p * 0.9, 1.5);
    ringShape.holes.push(roundedRectPath(THREE.Path, 0, 0, p * 0.9 - 0.6, p * 0.9 - 0.6, 1.2));
    const silk = new THREE.Mesh(extrudeUp(ringShape, 0.03), plastic("#e9ecef"));
    silk.position.y = 1.6;
    g.add(tag(silk, "pcb"));
    // 分压电阻 + 多路器（示意元件）
    const icMat = plastic("#15171c", { roughness: 0.5 });
    const ic = new THREE.Mesh(new THREE.BoxGeometry(4.4, 0.9, 4.4), icMat);
    ic.position.set(-W / 2 + 4.5, 1.6 + 0.45, W / 2 - 4.5);
    g.add(tag(ic, "pcb"));
    const res = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.5, 0.8), plastic("#222"));
    res.position.set(-W / 2 + 4.5, 1.6 + 0.25, W / 2 - 9);
    g.add(tag(res, "pcb"));
    y += 1.6;
  }
  // LED
  {
    const g = addLayer("led", 1.5, y);
    const col = new THREE.Color(m.ledPalette[0]);
    g.add(box("led", 3.5, 0.6, 2.8, plastic("#e9ecef")));
    const chip = box("led", 2.4, 0.9, 1.8, new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 1.6, roughness: 0.3, side: THREE.DoubleSide }), 0.6);
    chip.userData.padIndex = 0;
    g.add(chip);
    // LED 与传感层共面，不叠加厚度
  }
  // 传感层
  const active = Math.min(12.7, p * 0.7); // 有效区，参照 FSR 402
  if (kind === "film") {
    const s0 = y;
    {
      const g = addLayer("sensorBottom", 0.18, s0);
      const mat = new THREE.MeshStandardMaterial({ map: silverElectrodeTexture(p * 0.86, "#c8791e"), roughness: 0.45, side: THREE.DoubleSide });
      const side = plastic("#c8791e");
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(p * 0.86, 0.18, p * 0.86), [side, side, mat, side, side, side]);
      mesh.position.y = 0.09;
      g.add(tag(mesh, "sensorBottom"));
      const tail = box("sensorBottom", 6, 0.18, 6, plastic("#c8791e"));
      tail.position.set(0, 0.09, p * 0.43 + 2.5);
      g.add(tail);
    }
    {
      const g = addLayer("sensorSpacer", 0.09, s0 + 0.18);
      const shape = roundedRectPath(THREE.Shape, 0, 0, p * 0.86, p * 0.86, 1.5);
      shape.holes.push(roundedRectPath(THREE.Path, 0, 0, active + 1.5, active + 1.5, 1.0));
      const mesh = new THREE.Mesh(extrudeUp(shape, 0.09), plastic("#f4d7a1", { transparent: true, opacity: 0.9 }));
      g.add(tag(mesh, "sensorSpacer"));
    }
    {
      const g = addLayer("sensorTop", 0.18, s0 + 0.27);
      const ink = plastic("#3a2410");
      const pet = new THREE.MeshStandardMaterial({ color: "#e0862b", roughness: 0.35, transparent: true, opacity: 0.85, side: THREE.DoubleSide });
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(p * 0.86, 0.18, p * 0.86), [pet, pet, pet, ink, pet, pet]);
      mesh.position.y = 0.09;
      g.add(tag(mesh, "sensorTop"));
    }
    y = s0 + 0.45; // FSR 402: 0.45 mm
  } else if (kind === "electrodes") {
    const g = addLayer("electrodes", 0.05, y);
    const mat = new THREE.MeshStandardMaterial({ map: silverElectrodeTexture(p * 0.86), transparent: true, alphaTest: 0.2, color: "#d9a441", roughness: 0.35, metalness: 0.6, side: THREE.DoubleSide });
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(p * 0.86, p * 0.86), mat);
    plane.rotation.x = -Math.PI / 2;
    plane.position.y = 0.05;
    g.add(tag(plane, "electrodes"));
    y += 0.05;
  } else {
    {
      const g = addLayer("coilPos", 0.12, y);
      const mat = plastic("#4dabf7", { emissive: "#1c4f7a", emissiveIntensity: 0.6 });
      for (let i = 0; i < 4; i++) {
        const ring = new THREE.Mesh(new THREE.TorusGeometry(p * 0.14 + i * 1.6, 0.12, 8, 48), mat);
        ring.rotation.x = Math.PI / 2;
        ring.position.y = 0.06;
        g.add(tag(ring, "coilPos"));
      }
      y += 0.12;
    }
    {
      const g = addLayer("coilForce", 0.12, y + 0.05);
      const mat = plastic("#64d2ff", { emissive: "#1c5f7a", emissiveIntensity: 0.6 });
      for (let i = 0; i < 3; i++) {
        const ring = new THREE.Mesh(new THREE.TorusGeometry(p * 0.08 + i * 1.2, 0.12, 8, 40), mat);
        ring.rotation.x = Math.PI / 2;
        ring.position.y = 0.06;
        g.add(tag(ring, "coilForce"));
      }
      y += 0.17;
    }
  }
  // 触发件
  {
    if (kind === "film") {
      const g = addLayer("nub", 1.0, y);
      const mesh = new THREE.Mesh(new THREE.CylinderGeometry(active / 2 - 0.3, active / 2, 1.0, 40), plastic("#8a6a3a", { roughness: 0.9 }));
      mesh.position.y = 0.5;
      g.add(tag(mesh, "nub"));
      y += 1.0;
    } else if (kind === "electrodes") {
      const g = addLayer("pill", 1.0, y);
      const mesh = new THREE.Mesh(new THREE.CylinderGeometry(3.7, 4.0, 1.0, 40), plastic("#2a2a2e", { roughness: 0.95 }));
      mesh.position.y = 0.5;
      g.add(tag(mesh, "pill"));
      y += 1.0;
    } else {
      const g = addLayer("target", 0.5, y + 0.6);
      const mesh = new THREE.Mesh(new THREE.CylinderGeometry(p * 0.26, p * 0.26, 0.5, 48), new THREE.MeshStandardMaterial({ color: "#b8c4d0", metalness: 0.85, roughness: 0.3, side: THREE.DoubleSide }));
      mesh.position.y = 0.25;
      g.add(tag(mesh, "target"));
      y += 1.1;
    }
  }
  // 回弹膜（斜壁）
  const capBase = y;
  {
    const h = m.travel + 0.6;
    const g = addLayer("membrane", h, capBase - h + 0.2);
    const geo = new THREE.CylinderGeometry(p * 0.40, p * 0.47, h, 48, 1, true);
    const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: "#e8c877", roughness: 0.7, transparent: true, opacity: 0.85, side: THREE.DoubleSide }));
    mesh.position.y = h / 2;
    g.add(tag(mesh, "membrane"));
    // 裙边（base/apron）
    const apron = roundedRectPath(THREE.Shape, 0, 0, p + m.gap, p + m.gap, 2);
    apron.holes.push(roundedRectPath(THREE.Path, 0, 0, p * 0.94, p * 0.94, 2));
    const ap = new THREE.Mesh(extrudeUp(apron, 0.5), new THREE.MeshStandardMaterial({ color: "#e8c877", roughness: 0.7, transparent: true, opacity: 0.85, side: THREE.DoubleSide }));
    g.add(tag(ap, "membrane"));
  }
  // Pad 帽
  {
    const T = m.capHeight;
    const g = addLayer("cap", T, capBase);
    const bevel = Math.min(1.0, T * 0.25);
    const shape = roundedRectPath(THREE.Shape, 0, 0, p - 2 * bevel, p - 2 * bevel, Math.max(0.5, m.padCorner - bevel));
    const geo = new THREE.ExtrudeGeometry(shape, { depth: T - 2 * bevel, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel, bevelSegments: 3, curveSegments: 6 });
    geo.rotateX(-Math.PI / 2);
    geo.translate(0, bevel, 0);
    const col = new THREE.Color(m.ledPalette[0]);
    const cap = new THREE.Mesh(
      geo,
      new THREE.MeshPhysicalMaterial({ color: "#2b2c31", roughness: 0.55, clearcoat: 0.25, clearcoatRoughness: 0.6, transparent: true, opacity: 0.92, emissive: col, emissiveIntensity: 0.16, side: THREE.DoubleSide })
    );
    cap.userData.padIndex = 0;
    cap.userData.ledColor = col;
    g.add(tag(cap, "cap"));
    caps.push(cap);
    y = capBase + T;
  }

  group.position.y = -y / 2;
  scene.add(group);
  assembly = { group, layers, W, m, caps, totalH: y, order, spacing: 6.5 };
  orbit.setHome(W * 3.1, 12);
  applyExplode();
}

// ---------------------------------------------------------------------------
// Explode / highlight
// ---------------------------------------------------------------------------
let explodeT = 0.6;
let explodeTarget = 0.6;

function applyExplode() {
  if (!assembly) return;
  const spacing = assembly.spacing;
  for (const L of assembly.layers.values()) {
    L.group.position.y = L.restY + explodeT * spacing * L.index;
  }
}

let hoverLayer = null;
let selectedLayer = null;

function setHighlight() {
  if (!assembly) return;
  const active = hoverLayer || selectedLayer;
  for (const [id, L] of assembly.layers) {
    const on = id === active;
    for (const mesh of L.meshes) {
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const mt of mats) {
        if (!mt.userData.baseEmissive) {
          mt.userData.baseEmissive = mt.emissive.clone();
          mt.userData.baseIntensity = mt.emissiveIntensity;
        }
        if (id === "cap" || mesh.userData.padIndex !== undefined) {
          // pads 与 LED 本来就自发光，高亮时只加强
          mt.emissiveIntensity = on ? mt.userData.baseIntensity * 1.8 : mt.userData.baseIntensity;
        } else {
          mt.emissive.copy(on ? new THREE.Color(defs()[id].color).multiplyScalar(0.35) : mt.userData.baseEmissive);
        }
      }
    }
    // 非活动层在有选择时略微透明化
    const dim = active && !on;
    for (const mesh of L.meshes) {
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const mt of mats) {
        if (mt.userData.baseOpacity === undefined) {
          mt.userData.baseOpacity = mt.opacity;
          mt.userData.baseTransparent = mt.transparent;
        }
        if (dim) {
          mt.transparent = true;
          mt.opacity = Math.min(mt.userData.baseOpacity, 0.35);
        } else {
          mt.transparent = mt.userData.baseTransparent;
          mt.opacity = mt.userData.baseOpacity;
        }
      }
    }
  }
  document.querySelectorAll(".layer-list li").forEach((li) => li.classList.toggle("active", li.dataset.layer === active));
  document.querySelectorAll(".label").forEach((el) => el.classList.toggle("active", el.dataset.layer === active));
}

// ---------------------------------------------------------------------------
// Picking
// ---------------------------------------------------------------------------
const raycaster = new THREE.Raycaster();
const pointerNdc = new THREE.Vector2();
let pointerInside = false;

function pick(clientX, clientY) {
  const r = glCanvas.getBoundingClientRect();
  pointerNdc.set(((clientX - r.left) / r.width) * 2 - 1, -((clientY - r.top) / r.height) * 2 + 1);
  raycaster.setFromCamera(pointerNdc, camera);
  const hits = raycaster.intersectObjects(assembly ? [assembly.group] : [], true);
  for (const h of hits) {
    // 尊重剖切：被裁掉的一半不可选
    if (clipInput.checked && h.point.z > 0) continue;
    return h.object;
  }
  return null;
}

glCanvas.addEventListener("pointermove", (e) => {
  pointerInside = true;
  if (orbit.pointers.size > 0) return;
  const obj = pick(e.clientX, e.clientY);
  const id = obj ? obj.userData.layerId : null;
  if (id !== hoverLayer) {
    hoverLayer = id;
    setHighlight();
    if (!selectedLayer) renderLayerInfo(hoverLayer);
  }
  glCanvas.style.cursor = obj ? "pointer" : "grab";
});
glCanvas.addEventListener("pointerleave", () => {
  pointerInside = false;
  hoverLayer = null;
  setHighlight();
  if (!selectedLayer) renderLayerInfo(null);
});
glCanvas.addEventListener("click", (e) => {
  if (orbit.dragged) return;
  const obj = pick(e.clientX, e.clientY);
  if (!obj) {
    selectLayer(null);
    return;
  }
  if (obj.userData.layerId === "cap" && obj.userData.padIndex !== undefined) {
    strikePad(obj.userData.padIndex);
  }
  selectLayer(obj.userData.layerId);
});

function selectLayer(id) {
  selectedLayer = id;
  setHighlight();
  renderLayerInfo(id || hoverLayer);
}

// ---------------------------------------------------------------------------
// Pad strike simulation（电阻式：胶粒 / FSR 分压 → ADC）
// ---------------------------------------------------------------------------
const strikes = new Map(); // padIndex -> { t0, peakF }
let lastScope = null;

function strikePad(k) {
  const peakF = 1.5 + Math.random() * 7; // N
  strikes.set(k, { t0: performance.now(), peakF });
  lastScope = simulateStrike(peakF);
  drawScope(lastScope);
}

// 力曲线：25 ms 上升，110 ms 下降（近似手指敲击）
function forceAt(tMs, peakF) {
  if (tMs < 0) return 0;
  if (tMs < 25) return peakF * (tMs / 25) ** 1.6;
  if (tMs < 135) return peakF * Math.exp(-(tMs - 25) / 38);
  return 0;
}

// FSR 模型：R(F) = R0 · F^-0.9（F 以 N 计），下限 3 kΩ；断开 >2 MΩ。
// 分压：Vout = Vcc · Rl / (Rl + R)，Rl = 10 kΩ，12 bit ADC。
function adcOf(F) {
  const R = F < 0.05 ? 2e6 : Math.max(3e3, 90e3 * F ** -0.9);
  const Rl = 10e3;
  return Math.round((4095 * Rl) / (Rl + R));
}

function simulateStrike(peakF) {
  const fs = 2000; // Hz
  const dt = 1000 / fs;
  const samples = [];
  let t1 = null;
  let t2 = null;
  let maxSlope = 0;
  let peak = 0;
  const T1 = 4095 * 0.04;
  const T2 = 4095 * 0.22;
  for (let i = 0; i < 300; i++) {
    const t = i * dt;
    const adc = adcOf(forceAt(t, peakF));
    samples.push(adc);
    peak = Math.max(peak, adc);
    if (i > 0) maxSlope = Math.max(maxSlope, (adc - samples[i - 1]) / dt);
    if (t1 === null && adc > T1) t1 = t;
    if (t1 !== null && t2 === null && adc > T2) t2 = t;
  }
  const dtMs = t1 !== null && t2 !== null ? t2 - t1 : null;
  // Δt 法：Δt 越短速度越高（示意映射）
  const velocity = dtMs === null ? 0 : Math.round(THREE.MathUtils.clamp(127 * (1 - Math.log(dtMs / 1.2 + 1) / Math.log(12)), 1, 127));
  const aftertouch = Math.round(THREE.MathUtils.clamp((peak / 4095) * 127 * 1.15, 0, 127));
  return { samples, dt, peakF, peak, dtMs, velocity, aftertouch, T1, T2, t1, t2, maxSlope };
}

function drawScope(s) {
  const ctx = scopeCanvas.getContext("2d");
  const dpr = Math.min(window.devicePixelRatio, 2);
  const cw = scopeCanvas.clientWidth || 300;
  const ch = scopeCanvas.clientHeight || 120;
  if (scopeCanvas.width !== cw * dpr) {
    scopeCanvas.width = cw * dpr;
    scopeCanvas.height = ch * dpr;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cw, ch);
  const padL = 28;
  const padB = 14;
  const gw = cw - padL - 6;
  const gh = ch - padB - 6;
  ctx.strokeStyle = "#23262f";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padL, 6);
  ctx.lineTo(padL, 6 + gh);
  ctx.lineTo(padL + gw, 6 + gh);
  ctx.stroke();
  ctx.fillStyle = "#9aa3b2";
  ctx.font = "10px ui-monospace, Menlo, monospace";
  ctx.fillText("4095", 2, 12);
  ctx.fillText("0", 18, 6 + gh);
  ctx.fillText("0", padL, ch - 2);
  ctx.fillText("150 ms", padL + gw - 36, ch - 2);
  if (!s) return;
  const xOf = (i) => padL + (i / (s.samples.length - 1)) * gw;
  const yOf = (v) => 6 + gh - (v / 4095) * gh;
  // 阈值
  ctx.strokeStyle = "rgba(242,177,52,0.35)";
  ctx.setLineDash([3, 3]);
  for (const T of [s.T1, s.T2]) {
    ctx.beginPath();
    ctx.moveTo(padL, yOf(T));
    ctx.lineTo(padL + gw, yOf(T));
    ctx.stroke();
  }
  ctx.setLineDash([]);
  // 曲线
  ctx.strokeStyle = "#f2b134";
  ctx.lineWidth = 1.8;
  ctx.beginPath();
  s.samples.forEach((v, i) => (i ? ctx.lineTo(xOf(i), yOf(v)) : ctx.moveTo(xOf(i), yOf(v))));
  ctx.stroke();
  // Δt 区间
  if (s.dtMs !== null) {
    const x1 = xOf(s.t1 / s.dt);
    const x2 = xOf(s.t2 / s.dt);
    ctx.fillStyle = "rgba(100,210,255,0.18)";
    ctx.fillRect(x1, 6, Math.max(2, x2 - x1), gh);
    ctx.fillStyle = "#64d2ff";
    ctx.fillText(`Δt ${s.dtMs.toFixed(1)} ms`, Math.min(x2 + 4, padL + gw - 70), 16);
  }
  scopeOut.textContent =
    `峰值力 ${s.peakF.toFixed(1)} N · ADC 峰值 ${s.peak} / 4095\n` +
    `Δt 法速度 ${s.velocity} · 稳态压力(AT) ${s.aftertouch} · 最大斜率 ${Math.round(s.maxSlope)} LSB/ms`;
}

function updateStrikes(now) {
  if (!assembly) return;
  const travel = assembly.m.travel;
  for (const [k, st] of strikes) {
    const t = now - st.t0;
    const F = forceAt(t, st.peakF);
    const cap = assembly.caps[k];
    if (!cap) {
      strikes.delete(k);
      continue;
    }
    const depth = Math.min(1, F / 6);
    cap.position.y = -travel * depth;
    cap.material.emissiveIntensity = 0.22 + depth * 1.6;
    if (t > 160) {
      cap.position.y = 0;
      cap.material.emissiveIntensity = 0.22;
      strikes.delete(k);
    }
  }
}

// ---------------------------------------------------------------------------
// Labels + leader lines
// ---------------------------------------------------------------------------
const labelEls = new Map();

function buildLabels() {
  labelsEl.innerHTML = "";
  labelEls.clear();
  for (const id of assembly.order) {
    const el = document.createElement("div");
    el.className = "label";
    el.dataset.layer = id;
    el.style.setProperty("--lc", defs()[id].color);
    el.innerHTML = `${layerDisplayName(id)}<small></small>`;
    el.addEventListener("click", () => selectLayer(id));
    el.addEventListener("pointerenter", () => {
      hoverLayer = id;
      setHighlight();
      if (!selectedLayer) renderLayerInfo(id);
    });
    el.addEventListener("pointerleave", () => {
      hoverLayer = null;
      setHighlight();
      if (!selectedLayer) renderLayerInfo(null);
    });
    labelsEl.appendChild(el);
    labelEls.set(id, el);
  }
}

function layerDisplayName(id) {
  if (viewMode === "single") return SINGLE_LAYERS[id].name;
  const kind = assembly ? SENSING[assembly.m.sensing].sensorLayer : "film";
  if (id === "pill") {
    if (kind === "film") return "触发凸台（非导电）";
    if (kind === "coil") return "感应目标片";
  }
  if (id === "sensor") {
    if (kind === "film") return "FSR 传感薄膜";
    if (kind === "coil") return "电感线圈层（力 + 位置）";
    return "叉指电极（PCB 铜层）";
  }
  return LAYERS[id].name;
}

const tmpV = new THREE.Vector3();
function updateLabels() {
  const show = labelsInput.checked && assembly;
  labelsEl.style.display = show ? "" : "none";
  octx.clearRect(0, 0, overlay.width, overlay.height);
  if (!show) return;
  const rect = glCanvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio, 2);
  const items = [];
  for (const [id, L] of assembly.layers) {
    const worldY = assembly.group.position.y + L.group.position.y + L.thickness / 2;
    tmpV.set(assembly.W / 2 + 4, worldY, 0).project(camera);
    if (tmpV.z > 1) continue;
    const sx = ((tmpV.x + 1) / 2) * rect.width;
    const sy = ((1 - tmpV.y) / 2) * rect.height;
    items.push({ id, sx, sy, ly: sy, thickness: L.thickness });
  }
  // 去重叠：按 y 排序，强制最小间距
  items.sort((a, b) => a.sy - b.sy);
  const minGap = 26;
  for (let i = 1; i < items.length; i++) {
    if (items[i].ly - items[i - 1].ly < minGap) items[i].ly = items[i - 1].ly + minGap;
  }
  for (let i = items.length - 2; i >= 0; i--) {
    if (items[i + 1].ly - items[i].ly < minGap) items[i].ly = items[i + 1].ly - minGap;
  }
  const labelX = Math.min(rect.width - 600, Math.max(...items.map((it) => it.sx)) + 46);
  octx.save();
  octx.scale(dpr, dpr);
  octx.lineWidth = 1;
  for (const it of items) {
    const el = labelEls.get(it.id);
    el.style.left = `${labelX}px`;
    el.style.top = `${it.ly}px`;
    el.querySelector("small").textContent = `${it.thickness.toFixed(2).replace(/0$/, "")} mm`;
    octx.strokeStyle = defs()[it.id].color;
    octx.globalAlpha = 0.7;
    octx.beginPath();
    octx.moveTo(it.sx, it.sy);
    octx.lineTo(labelX - 14, it.ly);
    octx.lineTo(labelX - 2, it.ly);
    octx.stroke();
    octx.beginPath();
    octx.arc(it.sx, it.sy, 2.2, 0, Math.PI * 2);
    octx.fillStyle = defs()[it.id].color;
    octx.fill();
  }
  octx.restore();
}

// ---------------------------------------------------------------------------
// Panel rendering
// ---------------------------------------------------------------------------
function renderLayerList() {
  layerListEl.innerHTML = "";
  for (const id of assembly.order) {
    const L = assembly.layers.get(id);
    const li = document.createElement("li");
    li.dataset.layer = id;
    li.innerHTML = `<span class="sw" style="background:${defs()[id].color}"></span><span class="t">${layerDisplayName(id)}</span><span class="mm">${L.thickness.toFixed(2).replace(/0$/, "")} mm</span>`;
    li.addEventListener("click", () => selectLayer(selectedLayer === id ? null : id));
    li.addEventListener("pointerenter", () => {
      hoverLayer = id;
      setHighlight();
      if (!selectedLayer) renderLayerInfo(id);
    });
    li.addEventListener("pointerleave", () => {
      hoverLayer = null;
      setHighlight();
      if (!selectedLayer) renderLayerInfo(null);
    });
    layerListEl.appendChild(li);
  }
}

function renderLayerInfo(id) {
  if (!id) {
    layerInfoEl.innerHTML = `<p class="muted">悬停或点击任一层查看说明。</p>`;
    return;
  }
  const L = defs()[id];
  if (!L) {
    layerInfoEl.innerHTML = "";
    return;
  }
  const body = L.params
    ? `<div class="params">${L.params.map((pr) => `<div><span>${pr.k}</span><span>${pr.v}${srcBadge(pr.src)}</span></div>`).join("")}</div>`
    : `<dl>
      <dt>材料 / 工艺</dt><dd>${L.material}</dd>
      <dt>设计细节</dt><dd><ul>${L.detail.map((d) => `<li>${d}</li>`).join("")}</ul></dd>
    </dl>`;
  layerInfoEl.innerHTML = `
    <h3 style="color:${L.color}">${layerDisplayName(id)}</h3>
    <div class="en">${L.en}</div>
    <p>${L.role}</p>
    ${body}`;
}

function srcBadge(src) {
  if (!src) return `<span class="est" title="无一手出处，行业常见值或本页假设">示意</span>`;
  const n = REF_INDEX.get(src);
  return `<a class="src" href="#ref-${src}" title="${REFERENCES[n - 1].title}">[${n}]</a>`;
}

function renderMachineTabs() {
  machineTabsEl.innerHTML = "";
  for (const [id, m] of Object.entries(MACHINES)) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = m.short;
    b.classList.toggle("active", id === currentMachineId);
    b.addEventListener("click", () => switchMachine(id));
    machineTabsEl.appendChild(b);
  }
}

function renderMachineNotes() {
  const m = MACHINES[currentMachineId];
  const el = document.getElementById("machineNotes");
  el.innerHTML = `
    <h2>${m.name}</h2>
    <div class="tags">${m.tags.map((t) => `<span class="tag">${t}</span>`).join("")}<span class="tag">${SENSING[m.sensing].label}</span></div>
    <div class="two-col">
      <ul>${m.notes.map((n) => `<li>${n}</li>`).join("")}</ul>
      <ul>
        <li><strong>阵列：</strong>${m.grid}×${m.grid}，pad 约 ${m.padSize} mm，间距 ${m.gap} mm</li>
        <li><strong>Pad 帽厚度：</strong>约 ${m.capHeight} mm；<strong>行程：</strong>约 ${m.travel} mm</li>
        <li><strong>传感：</strong>${SENSING[m.sensing].label}</li>
        <li><strong>LED：</strong>每 pad ${m.ledsPerPad} 颗 RGB，pad 中心底部</li>
      </ul>
    </div>`;
}

function renderStaticDocs() {
  document.getElementById("layerTable").innerHTML = LAYER_ORDER.map((id) => {
    const L = LAYERS[id];
    return `<article class="layer-card" style="--lc:${L.color}">
      <h3>${L.name}</h3>
      <div class="en">${L.en}</div>
      <p>${L.role}</p>
      <p><span class="k">材料 / 工艺：</span>${L.material}</p>
      <ul>${L.detail.map((d) => `<li>${d}</li>`).join("")}</ul>
    </article>`;
  }).join("");

  document.getElementById("techCards").innerHTML = TECH.map(
    (t) => `<article class="tech-card">
      ${techSvg(t.svg, t.title)}
      <div class="tech-body">
        <h3>${t.title}</h3>
        <div class="used">应用：${t.used}</div>
        <p>${t.how}</p>
        <div class="kv"><span>速度</span><span>${t.velocity}</span><span>压力</span><span>${t.pressure}</span></div>
        <div class="pros-cons">
          <ul class="pros">${t.pros.map((p) => `<li>${p}</li>`).join("")}</ul>
          <ul class="cons">${t.cons.map((c) => `<li>${c}</li>`).join("")}</ul>
        </div>
      </div>
    </article>`
  ).join("");

  const [head, ...rows] = COMPARE;
  document.getElementById("compareTable").innerHTML = `<table>
    <thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody>
  </table>`;

  document.getElementById("signalChain").innerHTML = signalChainSvg();

  const allSingle = [...new Set(Object.values(SINGLE_ORDER).flat())];
  document.getElementById("paramTables").innerHTML = allSingle
    .map((id) => {
      const L = SINGLE_LAYERS[id];
      return `<article class="param-card" style="--lc:${L.color}">
        <h3>${L.name}</h3>
        <div class="en">${L.en}</div>
        <p>${L.role}</p>
        <div class="params">${L.params.map((pr) => `<div><span>${pr.k}</span><span>${pr.v}${srcBadge(pr.src)}</span></div>`).join("")}</div>
      </article>`;
    })
    .join("");

  document.getElementById("algoTable").innerHTML = `<table>
    <thead><tr><th>参数</th><th>含义 / 典型值</th><th>出处</th></tr></thead>
    <tbody>${ALGO.map((a) => `<tr><td>${a.k}</td><td style="white-space:normal">${a.v}</td><td>${srcBadge(a.src)}</td></tr>`).join("")}</tbody>
  </table>`;

  document.getElementById("refList").innerHTML = REFERENCES.map(
    (r) => `<li id="ref-${r.id}"><a href="${r.url}" target="_blank" rel="noopener">${r.title}</a><br/><span class="note">${r.note}</span></li>`
  ).join("");
}

function switchMachine(id) {
  currentMachineId = id;
  selectedLayer = null;
  hoverLayer = null;
  strikes.clear();
  if (viewMode === "single") buildSinglePad(MACHINES[id]);
  else buildAssembly(MACHINES[id]);
  renderMachineTabs();
  renderLayerList();
  buildLabels();
  renderLayerInfo(null);
  renderMachineNotes();
  setHighlight();
}

// ---------------------------------------------------------------------------
// UI events
// ---------------------------------------------------------------------------
explodeInput.addEventListener("input", () => {
  explodeTarget = explodeInput.value / 100;
  explodeOut.textContent = `${explodeInput.value}%`;
});
clipInput.addEventListener("change", () => {
  renderer.clippingPlanes = clipInput.checked ? [clipPlane] : [];
});
resetBtn.addEventListener("click", () => orbit.reset());
const modeMachineBtn = document.getElementById("modeMachine");
const modeSingleBtn = document.getElementById("modeSingle");
function setMode(mode) {
  if (mode === viewMode) return;
  viewMode = mode;
  modeMachineBtn.classList.toggle("active", mode === "machine");
  modeSingleBtn.classList.toggle("active", mode === "single");
  switchMachine(currentMachineId);
  orbit.reset();
}
modeMachineBtn.addEventListener("click", () => setMode("machine"));
modeSingleBtn.addEventListener("click", () => setMode("single"));

// ---------------------------------------------------------------------------
// Resize / loop
// ---------------------------------------------------------------------------
function resize() {
  const w = stageEl.clientWidth;
  const h = glCanvas.clientHeight || stageEl.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  const dpr = Math.min(window.devicePixelRatio, 2);
  overlay.width = w * dpr;
  overlay.height = h * dpr;
}
window.addEventListener("resize", resize);

let last = performance.now();
function frame(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  explodeT += (explodeTarget - explodeT) * Math.min(1, dt * 8);
  applyExplode();
  if (spinInput.checked && orbit.pointers.size === 0 && !pointerInside) orbit.theta += dt * 0.12;
  orbit.update();
  updateStrikes(now);
  renderer.render(scene, camera);
  updateLabels();
  requestAnimationFrame(frame);
}

// 调试句柄（demo 用）
window.lmdjPadDemo = {
  orbit,
  setMode,
  switchMachine,
  get assembly() {
    return assembly;
  },
};

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
resize();
renderStaticDocs();
switchMachine(currentMachineId);
drawScope(null);
requestAnimationFrame(frame);
