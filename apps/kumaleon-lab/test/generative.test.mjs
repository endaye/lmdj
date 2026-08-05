import assert from 'node:assert/strict';
import test from 'node:test';

import {hashSeed, makeRng, mulberry32, randomSeedText} from '../src/rng.js';
import {PALETTES, PATTERNS, SPEEDS, paletteAt, patternAt, rollTraits} from '../src/palette.js';
import {buildChameleon, modelBounds} from '../src/chameleon.js';

test('mulberry32 is deterministic and stays in [0, 1)', () => {
  const first = mulberry32(42);
  const second = mulberry32(42);
  for (let i = 0; i < 100; i += 1) {
    const value = first();
    assert.equal(value, second());
    assert.ok(value >= 0 && value < 1);
  }
});

test('hashSeed is stable and distinguishes strings', () => {
  assert.equal(hashSeed('kumaleon'), hashSeed('kumaleon'));
  assert.notEqual(hashSeed('kumaleon'), hashSeed('chameleon'));
  const rngA = makeRng('seed-a');
  const rngB = makeRng('seed-a');
  assert.equal(rngA(), rngB());
});

test('randomSeedText produces distinct seeds', () => {
  const seeds = new Set(Array.from({length: 20}, () => randomSeedText()));
  assert.equal(seeds.size, 20);
});

test('rollTraits is deterministic and yields valid indices', () => {
  const a = rollTraits('specimen-1');
  const b = rollTraits('specimen-1');
  assert.deepEqual(a, b);
  assert.ok(a.paletteIndex >= 0 && a.paletteIndex < PALETTES.length);
  assert.ok(a.patternIndex >= 0 && a.patternIndex < PATTERNS.length);
  assert.ok(a.speedIndex >= 0 && a.speedIndex < SPEEDS.length);
  assert.ok(a.spikeCount >= 5 && a.spikeCount <= 10);
});

test('rollTraits honors explicit trait locks', () => {
  const traits = rollTraits('specimen-2', {paletteIndex: 2, patternIndex: 1, speedIndex: 0});
  assert.equal(traits.paletteIndex, 2);
  assert.equal(traits.patternIndex, 1);
  assert.equal(traits.speedIndex, 0);
  assert.equal(paletteAt(2).name, PALETTES[2].name);
  assert.equal(patternAt(1), PATTERNS[1]);
});

test('palette and pattern lookups wrap around', () => {
  assert.equal(paletteAt(PALETTES.length).name, PALETTES[0].name);
  assert.equal(paletteAt(-1).name, PALETTES[PALETTES.length - 1].name);
  assert.equal(patternAt(PATTERNS.length), PATTERNS[0]);
});

test('static geometry is deterministic for the same traits', () => {
  const traits = rollTraits('specimen-3');
  const first = buildChameleon(traits, 0);
  const second = buildChameleon(traits, 0);
  assert.deepEqual(first.outline, second.outline);
  assert.deepEqual(first.pattern.points, second.pattern.points);
  assert.equal(first.spikes.length, traits.spikeCount);
});

test('different seeds hatch different creatures', () => {
  const a = buildChameleon(rollTraits('alpha'), 0);
  const b = buildChameleon(rollTraits('beta'), 0);
  assert.notDeepEqual(a.outline, b.outline);
});

test('only animated fields depend on time', () => {
  const traits = rollTraits('specimen-4');
  const early = buildChameleon(traits, 0.5);
  const late = buildChameleon(traits, 3.25);
  assert.deepEqual(early.outline, late.outline);
  assert.deepEqual(early.pattern.points, late.pattern.points);
  const eyeMoved =
    early.eye.pupilDx !== late.eye.pupilDx ||
    early.eye.pupilDy !== late.eye.pupilDy ||
    early.eye.blink !== late.eye.blink;
  assert.ok(eyeMoved, 'eye must animate over time');
  assert.notEqual(early.breathe, late.breathe);
});

test('model stays inside sane normalized bounds', () => {
  for (const seed of ['bounds-a', 'bounds-b', 'bounds-c', 'bounds-d']) {
    const model = buildChameleon(rollTraits(seed), 0);
    const bounds = modelBounds(model);
    assert.ok(bounds.minX > -1.4 && bounds.maxX < 1.4, JSON.stringify(bounds));
    assert.ok(bounds.minY > -1.4 && bounds.maxY < 1.4, JSON.stringify(bounds));
    assert.ok(model.outline.length >= 100);
    for (const point of model.pattern.points) {
      assert.ok(point.x >= bounds.minX - 0.01 && point.x <= bounds.maxX + 0.01);
      assert.ok(point.y >= bounds.minY - 0.01 && point.y <= bounds.maxY + 0.01);
    }
  }
});

test('pupil stays inside the eye and blink stays in (0, 1]', () => {
  const traits = rollTraits('specimen-5');
  for (let t = 0; t < 12; t += 0.37) {
    const {eye} = buildChameleon(traits, t);
    const pupilTravel = Math.hypot(eye.pupilDx, eye.pupilDy);
    assert.ok(pupilTravel < eye.radius, `pupil escaped at t=${t}`);
    assert.ok(eye.blink > 0 && eye.blink <= 1, `blink out of range at t=${t}`);
  }
});
