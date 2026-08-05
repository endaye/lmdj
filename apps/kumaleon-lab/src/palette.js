// Palettes and trait generation for the Kumaleon Lab generative engine.
// All colors are original to this lab; traits are a pure function of the seed.

import {makeRng} from './rng.js';

export const PALETTES = [
  {
    name: 'Canopy Dusk',
    background: '#0c1410',
    ground: '#152a1e',
    body: ['#3fae6a', '#1f7a4d'],
    accent: '#e8d44d',
    ink: '#071009',
    detail: '#b7f0c8',
  },
  {
    name: 'Neon Reef',
    background: '#0a1024',
    ground: '#14204a',
    body: ['#35c4d8', '#1a6fb8'],
    accent: '#ff7ad9',
    ink: '#05081a',
    detail: '#a8ecff',
  },
  {
    name: 'Ember Savanna',
    background: '#1a0e0a',
    ground: '#33201a',
    body: ['#e8873a', '#b4502a'],
    accent: '#5fd6a0',
    ink: '#120705',
    detail: '#ffd9a8',
  },
  {
    name: 'Ultraviolet Bloom',
    background: '#140a1e',
    ground: '#281442',
    body: ['#9a6ae8', '#5d34b0'],
    accent: '#7de86a',
    ink: '#0d0518',
    detail: '#e0c8ff',
  },
  {
    name: 'Monsoon Glass',
    background: '#081418',
    ground: '#123038',
    body: ['#8fd8c0', '#3f9a86'],
    accent: '#f2e35c',
    ink: '#04100f',
    detail: '#d8fff2',
  },
  {
    name: 'Sakura Static',
    background: '#180d14',
    ground: '#301a28',
    body: ['#e87aa8', '#a83a68'],
    accent: '#6ac8e8',
    ink: '#10060c',
    detail: '#ffd0e4',
  },
];

export const PATTERNS = ['spots', 'stripes', 'mesh'];

export const SPEEDS = ['drift', 'stride', 'dart'];

/**
 * Rolls the full trait set for one creature from its seed.
 * @param {string|number} seed
 * @param {{paletteIndex?: number, patternIndex?: number, speedIndex?: number}} [locks]
 *   Optional explicit choices that override the rolled values.
 * @returns {{
 *   seed: string, paletteIndex: number, patternIndex: number, speedIndex: number,
 *   tailCurl: number, bodyRoundness: number, headSize: number, spikeCount: number,
 *   patternDensity: number, eyeScale: number, huePhase: number
 * }}
 */
export function rollTraits(seed, locks = {}) {
  const seedText = String(seed);
  const rng = makeRng(`traits:${seedText}`);
  const paletteIndex = locks.paletteIndex ?? Math.floor(rng() * PALETTES.length);
  const patternIndex = locks.patternIndex ?? Math.floor(rng() * PATTERNS.length);
  const speedIndex = locks.speedIndex ?? Math.floor(rng() * SPEEDS.length);
  return {
    seed: seedText,
    paletteIndex: ((paletteIndex % PALETTES.length) + PALETTES.length) % PALETTES.length,
    patternIndex: ((patternIndex % PATTERNS.length) + PATTERNS.length) % PATTERNS.length,
    speedIndex: ((speedIndex % SPEEDS.length) + SPEEDS.length) % SPEEDS.length,
    tailCurl: 1.6 + rng() * 1.6,
    bodyRoundness: 0.75 + rng() * 0.5,
    headSize: 0.85 + rng() * 0.4,
    spikeCount: 5 + Math.floor(rng() * 6),
    patternDensity: 0.4 + rng() * 0.6,
    eyeScale: 0.85 + rng() * 0.45,
    huePhase: rng() * Math.PI * 2,
  };
}

/**
 * @param {number} paletteIndex
 * @returns {(typeof PALETTES)[number]}
 */
export function paletteAt(paletteIndex) {
  return PALETTES[((paletteIndex % PALETTES.length) + PALETTES.length) % PALETTES.length];
}

/**
 * @param {number} patternIndex
 * @returns {string}
 */
export function patternAt(patternIndex) {
  return PATTERNS[((patternIndex % PATTERNS.length) + PATTERNS.length) % PATTERNS.length];
}
