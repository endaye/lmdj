// Deterministic seeded randomness for the Kumaleon Lab generative engine.
// Every creature is a pure function of its seed, so the same seed always
// hatches the same chameleon.

/**
 * FNV-1a 32-bit hash, used to turn text seeds into numeric seeds.
 * @param {string} text
 * @returns {number} unsigned 32-bit integer
 */
export function hashSeed(text) {
  let hash = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

/**
 * mulberry32 pseudo-random generator.
 * @param {number} seed unsigned 32-bit integer
 * @returns {() => number} generator producing floats in [0, 1)
 */
export function mulberry32(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Accepts a number or a string and returns a deterministic generator.
 * @param {number|string} seed
 * @returns {() => number}
 */
export function makeRng(seed) {
  const numeric = typeof seed === 'string' ? hashSeed(seed) : seed >>> 0;
  return mulberry32(numeric);
}

/**
 * Deterministically derives a fresh random seed string.
 * @returns {string}
 */
export function randomSeedText() {
  const cryptoObject = globalThis.crypto;
  if (cryptoObject && typeof cryptoObject.getRandomValues === 'function') {
    const buffer = new Uint32Array(2);
    cryptoObject.getRandomValues(buffer);
    return `kuma-${buffer[0].toString(36)}-${buffer[1].toString(36)}`;
  }
  return `kuma-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e9).toString(36)}`;
}
