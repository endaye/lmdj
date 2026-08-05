// Renderer and UI wiring for Chameleon Lab. The geometry comes from the pure
// model in chameleon.js; this file only paints it and handles input.

import {makeRng, randomSeedText} from './rng.js';
import {PALETTES, PATTERNS, SPEEDS, paletteAt, patternAt, rollTraits} from './palette.js';
import {buildChameleon} from './chameleon.js';

const canvas = document.getElementById('stage');
const context = canvas.getContext('2d');
const readout = document.getElementById('trait-readout');
const reduceMotion = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

const state = {
  seed: randomSeedText(),
  paletteIndex: null,
  patternIndex: null,
  speedIndex: null,
  traits: null,
  start: performance.now(),
};

const SPEED_SCALE = {drift: 0.55, stride: 1, dart: 1.9};

function refreshTraits() {
  const locks = {};
  if (state.paletteIndex !== null) locks.paletteIndex = state.paletteIndex;
  if (state.patternIndex !== null) locks.patternIndex = state.patternIndex;
  if (state.speedIndex !== null) locks.speedIndex = state.speedIndex;
  state.traits = rollTraits(state.seed, locks);
  state.paletteIndex = state.traits.paletteIndex;
  state.patternIndex = state.traits.patternIndex;
  state.speedIndex = state.traits.speedIndex;
  const palette = paletteAt(state.paletteIndex);
  readout.textContent =
    `seed ${state.seed} · ${palette.name} · ${patternAt(state.patternIndex)} · ${SPEEDS[state.speedIndex]}`;
}

function resizeCanvas() {
  const ratio = globalThis.devicePixelRatio || 1;
  const {clientWidth, clientHeight} = canvas;
  const width = Math.max(1, Math.floor(clientWidth * ratio));
  const height = Math.max(1, Math.floor(clientHeight * ratio));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
}

// Maps normalized model coordinates into the canvas.
function projector() {
  const scale = Math.min(canvas.width, canvas.height) * 0.36;
  const cx = canvas.width * 0.5;
  const cy = canvas.height * 0.46;
  return {
    scale,
    point: ({x, y}) => [cx + x * scale, cy - y * scale],
  };
}

function tracePath(points, project) {
  context.beginPath();
  points.forEach((point, index) => {
    const [x, y] = project.point(point);
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  context.closePath();
}

function drawBackground(palette) {
  context.fillStyle = palette.background;
  context.fillRect(0, 0, canvas.width, canvas.height);
}

function drawGround(palette, project) {
  const [cx, cy] = project.point({x: 0, y: -0.55});
  context.save();
  context.globalAlpha = 0.55;
  context.fillStyle = palette.ground;
  context.beginPath();
  context.ellipse(cx, cy, project.scale * 1.15, project.scale * 0.16, 0, 0, Math.PI * 2);
  context.fill();
  context.restore();
}

function drawTail(model, palette, project) {
  const {points, startWidth, endWidth} = model.tail;
  context.lineCap = 'round';
  for (let i = 1; i < points.length; i += 1) {
    const t = i / (points.length - 1);
    const width = startWidth + (endWidth - startWidth) * t;
    const [x0, y0] = project.point(points[i - 1]);
    const [x1, y1] = project.point(points[i]);
    context.beginPath();
    context.moveTo(x0, y0);
    context.lineTo(x1, y1);
    context.lineWidth = Math.max(1, width * project.scale);
    context.strokeStyle = palette.body[t > 0.5 ? 0 : 1];
    context.stroke();
  }
}

function drawBody(model, palette, project) {
  const gradient = context.createLinearGradient(
    0,
    project.point({x: 0, y: 0.4})[1],
    0,
    project.point({x: 0, y: -0.4})[1],
  );
  gradient.addColorStop(0, palette.body[0]);
  gradient.addColorStop(1, palette.body[1]);
  tracePath(model.outline, project);
  context.fillStyle = gradient;
  context.fill();
}

function drawCasque(model, palette, project) {
  const {apex, back, front} = model.casque;
  tracePath([back, apex, front], project);
  context.fillStyle = palette.body[1];
  context.fill();
  context.strokeStyle = palette.ink;
  context.lineWidth = Math.max(1, project.scale * 0.008);
  context.stroke();
}

function drawSpikes(model, palette, project) {
  context.fillStyle = palette.accent;
  for (const spike of model.spikes) {
    const half = spike.height * 0.45;
    tracePath(
      [
        {x: spike.x - half, y: spike.y + half * 0.4},
        {x: spike.x, y: spike.y + spike.height},
        {x: spike.x + half, y: spike.y + half * 0.4},
      ],
      project,
    );
    context.fill();
  }
}

function drawLegs(model, palette, project) {
  context.strokeStyle = palette.body[1];
  context.lineCap = 'round';
  for (const leg of model.legs) {
    context.lineWidth = project.scale * leg.radius;
    context.beginPath();
    const [hx, hy] = project.point(leg.hip);
    const [kx, ky] = project.point(leg.knee);
    const [fx, fy] = project.point(leg.foot);
    context.moveTo(hx, hy);
    context.lineTo(kx, ky);
    context.lineTo(fx, fy);
    context.stroke();
    context.fillStyle = palette.body[1];
    for (const toe of leg.toes) {
      const [tx, ty] = project.point(toe);
      context.beginPath();
      context.arc(tx, ty, project.scale * 0.012, 0, Math.PI * 2);
      context.fill();
    }
  }
}

function drawPattern(model, palette, patternName, project) {
  for (const dot of model.pattern.points) {
    const [x, y] = project.point(dot);
    const radius = project.scale * dot.radius;
    context.save();
    context.globalAlpha = 0.25 + dot.tone * 0.45;
    if (patternName === 'spots') {
      context.fillStyle = dot.tone > 0.5 ? palette.accent : palette.detail;
      context.beginPath();
      context.arc(x, y, radius, 0, Math.PI * 2);
      context.fill();
    } else if (patternName === 'stripes') {
      context.strokeStyle = dot.tone > 0.5 ? palette.accent : palette.detail;
      context.lineWidth = Math.max(1, radius * 0.7);
      context.beginPath();
      context.moveTo(x - Math.cos(dot.angle) * radius * 2, y - Math.sin(dot.angle) * radius * 2);
      context.lineTo(x + Math.cos(dot.angle) * radius * 2, y + Math.sin(dot.angle) * radius * 2);
      context.stroke();
    } else {
      context.strokeStyle = dot.tone > 0.5 ? palette.accent : palette.detail;
      context.lineWidth = Math.max(1, radius * 0.4);
      context.beginPath();
      context.arc(x, y, radius * 1.6, 0, Math.PI * 2);
      context.stroke();
    }
    context.restore();
  }
}

function drawEye(model, palette, project) {
  const {eye} = model;
  const [x, y] = project.point(eye);
  const radius = project.scale * eye.radius;
  const openness = Math.max(0.08, eye.blink);
  context.save();
  context.translate(x, y);
  context.scale(1, openness);
  context.fillStyle = palette.detail;
  context.beginPath();
  context.arc(0, 0, radius, 0, Math.PI * 2);
  context.fill();
  context.strokeStyle = palette.accent;
  context.lineWidth = Math.max(1, radius * 0.22);
  context.beginPath();
  context.arc(0, 0, radius * 0.66, 0, Math.PI * 2);
  context.stroke();
  context.fillStyle = palette.ink;
  context.beginPath();
  context.arc(
    eye.pupilDx * project.scale,
    -eye.pupilDy * project.scale,
    radius * 0.4,
    0,
    Math.PI * 2,
  );
  context.fill();
  context.restore();
}

function render(nowMs) {
  resizeCanvas();
  const palette = paletteAt(state.paletteIndex);
  const speed = SPEED_SCALE[SPEEDS[state.speedIndex]] ?? 1;
  const time = reduceMotion ? 0 : ((nowMs - state.start) / 1000) * speed;
  const model = buildChameleon(state.traits, time);
  const project = projector();

  drawBackground(palette);
  context.save();
  const [cx, cy] = project.point({x: 0, y: 0});
  context.translate(cx, cy);
  context.scale(1, model.breathe);
  context.translate(-cx, -cy);
  drawGround(palette, project);
  drawLegs(model, palette, project);
  drawTail(model, palette, project);
  drawBody(model, palette, project);
  drawPattern(model, palette, patternAt(state.patternIndex), project);
  drawSpikes(model, palette, project);
  drawCasque(model, palette, project);
  drawEye(model, palette, project);
  context.restore();
}

function frame(nowMs) {
  render(nowMs);
  if (!reduceMotion) requestAnimationFrame(frame);
}

// ---------- trait controls ----------

document.getElementById('trait-palette').addEventListener('click', () => {
  state.paletteIndex = (state.paletteIndex + 1) % PALETTES.length;
  refreshTraits();
});

document.getElementById('trait-pattern').addEventListener('click', () => {
  state.patternIndex = (state.patternIndex + 1) % PATTERNS.length;
  refreshTraits();
});

function hatchNew() {
  state.seed = randomSeedText();
  state.paletteIndex = null;
  state.patternIndex = null;
  state.speedIndex = null;
  refreshTraits();
}

document.getElementById('trait-seed').addEventListener('click', hatchNew);
document.getElementById('hatch-button').addEventListener('click', () => {
  hatchNew();
  document.getElementById('hero').scrollIntoView({behavior: reduceMotion ? 'auto' : 'smooth'});
});

document.getElementById('trait-speed').addEventListener('click', () => {
  state.speedIndex = (state.speedIndex + 1) % SPEEDS.length;
  refreshTraits();
});

// ---------- overlay menu ----------

const overlay = document.getElementById('menu-overlay');
document.getElementById('menu-open').addEventListener('click', () => {
  overlay.hidden = false;
  document.getElementById('menu-close').focus();
});
document.getElementById('menu-close').addEventListener('click', () => {
  overlay.hidden = true;
});
overlay.addEventListener('click', (event) => {
  if (event.target instanceof HTMLAnchorElement) overlay.hidden = true;
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && !overlay.hidden) overlay.hidden = true;
});

// ---------- boot ----------

refreshTraits();
if (reduceMotion) {
  render(performance.now());
  globalThis.addEventListener('resize', () => render(performance.now()));
} else {
  requestAnimationFrame(frame);
}

// Kept for manual poking in devtools; harmless in production.
globalThis.chameleonLab = {state, makeRng};
