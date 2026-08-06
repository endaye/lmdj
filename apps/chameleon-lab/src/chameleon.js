// Pure geometry model for the Chameleon Lab chameleon.
// Everything here is deterministic: the static body is a pure function of the
// traits, and only the declared animated fields depend on time. The renderer
// (main.js) turns this model into canvas calls; tests run it under Node.
//
// Model space: +x is right (toward the head), +y is up (toward the back).

import {makeRng} from './rng.js';

const TAU = Math.PI * 2;
const SPINE_SAMPLES = 64;
const TAIL_SAMPLES = 48;
const PATTERN_SAMPLES = 220;

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function smoothstep(edge0, edge1, x) {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

/**
 * Builds the body center-line from the tail base to the snout, with the local
 * body radius at each sample. The back arches gently upward.
 * @returns {Array<{x: number, y: number, r: number}>}
 */
function buildSpine(traits) {
  const points = [];
  const roundness = traits.bodyRoundness;
  const head = traits.headSize;

  for (let i = 0; i < SPINE_SAMPLES; i += 1) {
    const t = i / (SPINE_SAMPLES - 1);
    let x;
    let y;
    let r;
    if (t < 0.72) {
      // Torso: tail base to shoulders, belly bulging downward.
      const local = t / 0.72;
      x = lerp(-0.58, 0.34, local);
      y = 0.08 + Math.sin(local * Math.PI) * 0.1;
      r = 0.06 + Math.sin(local * Math.PI) * 0.24 * roundness;
    } else {
      // Neck and head: rising slightly toward the snout.
      const local = (t - 0.72) / 0.28;
      x = lerp(0.34, 0.86, local);
      y = lerp(0.08, 0.2, local);
      r = lerp(0.1, 0.05, local) + Math.sin(local * Math.PI) * 0.13 * head;
    }
    points.push({x, y, r});
  }
  return points;
}

/**
 * The curled tail: a spiral that starts at the tail base and winds inward to
 * its tip. Rendered as a tapering stroke, kept separate from the body outline
 * so the spiral arms never self-intersect the fill.
 * @returns {{points: Array<{x: number, y: number}>, startWidth: number, endWidth: number}}
 */
function buildTail(traits) {
  const points = [];
  const base = {x: -0.58, y: 0.08};
  const center = {x: -0.86, y: -0.02};
  const startRadius = Math.hypot(base.x - center.x, base.y - center.y);
  const startAngle = Math.atan2(base.y - center.y, base.x - center.x);
  for (let i = 0; i < TAIL_SAMPLES; i += 1) {
    const t = i / (TAIL_SAMPLES - 1);
    const angle = startAngle + t * traits.tailCurl * TAU;
    const radius = startRadius * (1 - t * 0.92);
    points.push({
      x: center.x + Math.cos(angle) * radius,
      y: center.y + Math.sin(angle) * radius,
    });
  }
  return {points, startWidth: 0.1, endWidth: 0.014};
}

/**
 * Turns the body center-line into a closed outline polygon.
 */
function buildOutline(spine) {
  const upper = [];
  const lower = [];
  for (let i = 0; i < spine.length; i += 1) {
    const previous = spine[Math.max(0, i - 1)];
    const next = spine[Math.min(spine.length - 1, i + 1)];
    const dx = next.x - previous.x;
    const dy = next.y - previous.y;
    const length = Math.hypot(dx, dy) || 1;
    const nx = -dy / length;
    const ny = dx / length;
    const point = spine[i];
    upper.push({x: point.x + nx * point.r, y: point.y + ny * point.r});
    lower.push({x: point.x - nx * point.r, y: point.y - point.r});
  }
  return [...upper, ...lower.reverse()];
}

/**
 * Dorsal spikes standing on the back, between the shoulders and the neck.
 */
function buildSpikes(spine, traits) {
  const spikes = [];
  const start = Math.floor(SPINE_SAMPLES * 0.18);
  const end = Math.floor(SPINE_SAMPLES * 0.62);
  for (let i = 0; i < traits.spikeCount; i += 1) {
    const index = Math.floor(lerp(start, end, i / Math.max(1, traits.spikeCount - 1)));
    const point = spine[index];
    const crown = Math.sin((i / Math.max(1, traits.spikeCount - 1)) * Math.PI);
    const height = 0.05 + 0.12 * point.r * (0.5 + 0.5 * crown);
    spikes.push({x: point.x, y: point.y + point.r, height});
  }
  return spikes;
}

/**
 * The casque: the chameleon's signature head crest, one rounded triangle
 * rising above the head.
 */
function buildCasque(spine, traits) {
  const headIndex = Math.floor(SPINE_SAMPLES * 0.86);
  const head = spine[headIndex];
  const scale = traits.headSize;
  return {
    apex: {x: head.x - 0.04 * scale, y: head.y + head.r + 0.2 * scale},
    back: {x: head.x - 0.2 * scale, y: head.y + head.r * 0.5},
    front: {x: head.x + 0.13 * scale, y: head.y + head.r * 0.45},
  };
}

/**
 * Four legs with three-toed feet, hanging below the belly.
 */
function buildLegs(spine, traits) {
  const anchors = [0.3, 0.42, 0.55, 0.66].map((t) => {
    const index = Math.floor(t * (SPINE_SAMPLES - 1));
    const point = spine[index];
    return {x: point.x, y: point.y - point.r * 0.75};
  });
  return anchors.map((hip, index) => {
    const front = index >= 2;
    const knee = {x: hip.x + (front ? 0.06 : -0.06), y: hip.y - 0.17};
    const foot = {x: knee.x + (front ? -0.02 : 0.08), y: knee.y - 0.13};
    const toes = [-1, 0, 1].map((toe) => ({
      x: foot.x + toe * 0.028,
      y: foot.y - 0.03 - Math.abs(toe) * 0.008,
    }));
    return {hip, knee, foot, toes, radius: 0.02 + traits.bodyRoundness * 0.008};
  });
}

/**
 * Skin pattern sample points, deterministic for a given seed. Every point
 * sits within the local body radius of its spine sample.
 */
function buildPattern(traits, spine) {
  const rng = makeRng(`pattern:${traits.seed}`);
  const count = Math.floor(PATTERN_SAMPLES * traits.patternDensity);
  const points = [];
  for (let i = 0; i < count; i += 1) {
    const t = 0.06 + rng() * 0.86;
    const index = Math.min(SPINE_SAMPLES - 1, Math.floor(t * SPINE_SAMPLES));
    const center = spine[index];
    const angle = rng() * TAU;
    const distance = Math.sqrt(rng()) * center.r * 0.8;
    points.push({
      x: center.x + Math.cos(angle) * distance,
      y: center.y + Math.sin(angle) * distance,
      radius: 0.008 + rng() * 0.02,
      angle: rng() * TAU,
      tone: rng(),
    });
  }
  return {points};
}

/**
 * Builds the full creature model.
 * @param {ReturnType<import('./palette.js').rollTraits>} traits
 * @param {number} timeSeconds animation time in seconds
 */
export function buildChameleon(traits, timeSeconds = 0) {
  const spine = buildSpine(traits);
  const outline = buildOutline(spine);
  const tail = buildTail(traits);
  const spikes = buildSpikes(spine, traits);
  const casque = buildCasque(spine, traits);
  const legs = buildLegs(spine, traits);
  const pattern = buildPattern(traits, spine);

  const headIndex = Math.floor(SPINE_SAMPLES * 0.86);
  const head = spine[headIndex];
  const eye = {
    x: head.x + 0.02,
    y: head.y + head.r * 0.35,
    radius: 0.05 * traits.eyeScale,
    pupilDx: Math.cos(timeSeconds * 0.6 + traits.huePhase) * 0.016,
    pupilDy: Math.sin(timeSeconds * 0.83 + traits.huePhase * 1.7) * 0.012,
    blink: 1 - smoothstep(0.94, 1, Math.sin(timeSeconds * 1.9 + traits.huePhase) * 0.5 + 0.5),
  };

  return {
    outline,
    tail,
    spikes,
    casque,
    eye,
    legs,
    pattern,
    breathe: 1 + Math.sin(timeSeconds * 1.4 + traits.huePhase) * 0.012,
    tailTip: tail.points[TAIL_SAMPLES - 1],
  };
}

/**
 * Axis-aligned bounds of the whole model, used for framing tests.
 */
export function modelBounds(model) {
  const xs = model.outline.map((p) => p.x).concat(model.tail.points.map((p) => p.x));
  const ys = model.outline.map((p) => p.y).concat(model.tail.points.map((p) => p.y));
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
}
