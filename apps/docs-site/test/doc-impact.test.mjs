import assert from 'node:assert/strict';
import test from 'node:test';
import {checkDocumentationImpact} from '../scripts/check-doc-impact.mjs';

test('implementation change requires a concrete impact declaration', () => {
  assert.deepEqual(checkDocumentationImpact({
    body: 'Documentation impact: none\nReason: ',
    changedFiles: ['packages/audio-runtime/src/engine.cpp'],
  }), ['documentation impact reason is empty — add a "Reason: <why this impact level is correct>" line to the PR body']);
});

test('affected implementation accepts required routes', () => {
  assert.deepEqual(checkDocumentationImpact({
    body: 'Documentation impact: required\nAffected portal pages: /core/modules/audio-runtime/\nReason: trigger state changed',
    changedFiles: [
      'packages/audio-runtime/src/engine.cpp',
      'apps/docs-site/docs/core/modules/audio-runtime.mdx',
    ],
  }), []);
});

test('none rejects unrelated portal churn and required needs a portal page', () => {
  assert.deepEqual(checkDocumentationImpact({
    body: 'Documentation impact: none\nReason: internal comment only',
    changedFiles: ['packages/audio-runtime/src/engine.cpp', 'apps/docs-site/docs/product/workflows.mdx'],
  }), ['documentation impact is none but current portal pages changed — either declare "Documentation impact: required" with "Affected portal pages:" routes, or drop the apps/docs-site/docs/ edits from this PR']);
  assert.deepEqual(checkDocumentationImpact({
    body: 'Documentation impact: required\nAffected portal pages: /core/modules/audio-runtime/\nReason: public behavior changed',
    changedFiles: ['packages/audio-runtime/src/engine.cpp'],
  }), ['documentation impact is required but no current portal page changed — update the affected pages under apps/docs-site/docs/ in this PR, or declare "Documentation impact: none" with a reason if no portal truth changes']);
});

test('product build and assembly changes cannot opt out of current documentation', () => {
  assert.deepEqual(checkDocumentationImpact({
    body: 'Documentation impact: none\nReason: version metadata only',
    changedFiles: ['products/lmdj/version.json'],
  }), ['Product Build or Assembly changes require documentation impact: required — declare "Documentation impact: required", list "Affected portal pages:" routes, and update the current portal pages plus the immutable snapshot obligation in the same Task']);

  assert.deepEqual(checkDocumentationImpact({
    body: 'Documentation impact: none\nReason: lock regeneration only',
    changedFiles: ['products/lmdj/assembly.lock.json'],
  }), ['Product Build or Assembly changes require documentation impact: required — declare "Documentation impact: required", list "Affected portal pages:" routes, and update the current portal pages plus the immutable snapshot obligation in the same Task']);

  assert.deepEqual(checkDocumentationImpact({
    body: 'Documentation impact: none\nReason: product wiring only',
    changedFiles: ['products/lmdj/src/compiled_assembly.cpp'],
  }), ['Product Build or Assembly changes require documentation impact: required — declare "Documentation impact: required", list "Affected portal pages:" routes, and update the current portal pages plus the immutable snapshot obligation in the same Task']);

  assert.deepEqual(checkDocumentationImpact({
    body: 'Documentation impact: required\nAffected portal pages: /assembly/lmdj/\nReason: allocate a testable Product Build',
    changedFiles: [
      'products/lmdj/version.json',
      'products/lmdj/assembly.lock.json',
      'apps/docs-site/docs/assembly/lmdj.mdx',
    ],
  }), []);
});

const REQUIRED_WITHOUT_PAGE = 'documentation impact is required but no current portal page changed — update the affected pages under apps/docs-site/docs/ in this PR, or declare "Documentation impact: none" with a reason if no portal truth changes';
const CUT_BODY = 'Documentation impact: required\nAffected portal pages: /operations/version-and-release/\nReason: reserve a new BUILD with PATCH 0; no product fixes included.';
const CUT_FILES = [
  'apps/architecture-portal/static/versions/1.0.64.0/diagrams/foundation.svg',
  'apps/architecture-portal/versioned_docs/version-1.0.64.0/assembly/lmdj.mdx',
  'apps/architecture-portal/versioned_metadata/version-1.0.64.0.json',
  'apps/architecture-portal/versioned_sidebars/version-1.0.64.0-sidebars.json',
  'apps/architecture-portal/versions.json',
  'products/lmdj/assembly.json',
  'products/lmdj/assembly.lock.json',
  'products/lmdj/generated/web-runtime-identity.json',
  'products/lmdj/generated/web-runtime-identity.mjs',
  'products/lmdj/src/compiled_assembly.cpp',
  'products/lmdj/version.json',
];

test('a candidate cut carrying its own Build snapshot satisfies required without a current page edit', () => {
  assert.deepEqual(checkDocumentationImpact({body: CUT_BODY, changedFiles: CUT_FILES, productBuild: '1.0.64.0'}), []);
});

test('a cut that also changes other source still needs a current page edit', () => {
  assert.deepEqual(checkDocumentationImpact({
    body: CUT_BODY,
    changedFiles: [...CUT_FILES, 'packages/application-facade/module.json'],
    productBuild: '1.0.64.0',
  }), [REQUIRED_WITHOUT_PAGE]);
});

test('a snapshot for a Build other than the current one does not stand in for a current page', () => {
  assert.deepEqual(checkDocumentationImpact({body: CUT_BODY, changedFiles: CUT_FILES, productBuild: '1.0.65.0'}), [REQUIRED_WITHOUT_PAGE]);
});

test('a snapshot path of another Build does not belong to the current Build\'s cut', () => {
  assert.deepEqual(checkDocumentationImpact({
    body: CUT_BODY,
    changedFiles: [...CUT_FILES, 'apps/architecture-portal/versioned_metadata/version-1.0.65.0.json'],
    productBuild: '1.0.64.0',
  }), [REQUIRED_WITHOUT_PAGE]);
});
