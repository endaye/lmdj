import assert from 'node:assert/strict';
import test from 'node:test';
import {checkDocumentationImpact} from '../scripts/check-doc-impact.mjs';

test('implementation change requires a concrete impact declaration', () => {
  assert.deepEqual(checkDocumentationImpact({
    body: 'Documentation impact: none\nReason: ',
    changedFiles: ['packages/audio-runtime/src/engine.cpp'],
  }), ['documentation impact reason is empty']);
});

test('affected implementation accepts required routes', () => {
  assert.deepEqual(checkDocumentationImpact({
    body: 'Documentation impact: required\nAffected portal pages: /core/modules/audio-runtime/\nReason: trigger state changed',
    changedFiles: [
      'packages/audio-runtime/src/engine.cpp',
      'apps/architecture-portal/docs/core/modules/audio-runtime.mdx',
    ],
  }), []);
});

test('none rejects unrelated portal churn and required needs a portal page', () => {
  assert.deepEqual(checkDocumentationImpact({
    body: 'Documentation impact: none\nReason: internal comment only',
    changedFiles: ['packages/audio-runtime/src/engine.cpp', 'apps/architecture-portal/docs/product/workflows.mdx'],
  }), ['documentation impact is none but current portal pages changed']);
  assert.deepEqual(checkDocumentationImpact({
    body: 'Documentation impact: required\nAffected portal pages: /core/modules/audio-runtime/\nReason: public behavior changed',
    changedFiles: ['packages/audio-runtime/src/engine.cpp'],
  }), ['documentation impact is required but no current portal page changed']);
});
