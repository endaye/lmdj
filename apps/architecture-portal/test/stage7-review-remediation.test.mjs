import assert from 'node:assert/strict';
import test from 'node:test';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {readFile} from 'node:fs/promises';

const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(portalRoot, '../..');

async function readRepo(relativePath) {
  return readFile(path.join(repoRoot, relativePath), 'utf8');
}

test('Stage 7 retrospective closes every documented design drift', async () => {
  const plan = await readRepo('docs/superpowers/plans/2026-08-07-lmdj-stage7-creator-editor.md');
  const spec = await readRepo('docs/superpowers/specs/2026-08-07-lmdj-stage7-creator-editor-design.md');

  assert.match(plan, /Retrospective correction addendum/);
  for (let finding = 1; finding <= 10; finding += 1) {
    assert.match(plan, new RegExp(`D${finding}\\b`));
  }
  assert.doesNotMatch(plan, /### Task 5R1:/);
  assert.doesNotMatch(plan, /closes it once on terminal unmount\/pagehide/);
  assert.match(plan, /persisted `pagehide`[^\n]+retains the shared Runtime/);
  assert.match(plan, /non-persisted terminal `pagehide`[^\n]+close/);
  assert.match(plan, /16 admissions[^\n]+16 outcomes[^\n]+0 rejection[^\n]+`running`/);
  assert.match(plan, /768x1024[^\n]+1024x768/);
  assert.match(plan, /BroadcastChannel[^\n]+AudioContext/);

  assert.match(spec, /managed Bundle paths[^\n]+ASCII segment subset/);
  assert.match(spec, /Project payload text remains UTF-8/);
  assert.match(spec, /1\.0\.16\.0[^\n]+1\.0\.16\.9/);
  assert.match(spec, /synthetic lifecycle[^\n]+automated contract only/);
  assert.match(spec, /physical\/hearing\/Safari\/iPadOS\/MIDI[^\n]+deferred \/ unverified/);
});

test('Stage 7 acceptance and review distinguish historical, candidate, and external truth', async () => {
  const acceptance = await readRepo('docs/quality/2026-08-07-stage7-creator-editor-acceptance.md');
  const review = await readRepo('docs/quality/2026-08-12-stage7-creator-editor-review.md');

  assert.match(acceptance, /Historical acceptance/);
  assert.match(acceptance, /Current remediation candidate/);
  assert.match(acceptance, /PR #97[^\n]+MERGED/);
  assert.match(acceptance, /branch-local[^\n]+not merged-main Proof/);
  assert.match(acceptance, /Manual canary[^\n]+open/);

  assert.match(review, /Remediation status/);
  for (let finding = 1; finding <= 10; finding += 1) {
    assert.match(review, new RegExp(`\\| D${finding} \\|[^\n]+resolved`));
  }
  assert.match(review, /T1[^\n]+open/);
  assert.match(review, /G1[^\n]+open/);
});

test('release governance forbids PATCH assembly drift and binds release evidence', async () => {
  const governance = await readRepo('docs/governance/version-management.md');
  const release = await readRepo('apps/architecture-portal/docs/operations/version-and-release.mdx');

  for (const body of [governance, release]) {
    assert.match(body, /PATCH may not change Product Assembly identity or `assembly\.lock`/);
    assert.match(body, /module\/provider\/Host\/dependency identity change[^\n]+new BUILD/);
    assert.match(body, /Historical `1\.0\.16\.x` events[^\n]+not rewritten/);
    assert.match(body, /Product Build[^\n]+signed tag[^\n]+tag revision[^\n]+merged PR[^\n]+source revision[^\n]+snapshot provenance\/witness[^\n]+merged-main Proof revision[^\n]+evidence-only documentation revision/);
  }
  assert.match(governance, /New Product tags require merged-main Proof first/);
});

test('current Portal maps the corrected Creator lifecycle and automated evidence limits', async () => {
  const creator = await readRepo('apps/architecture-portal/docs/hosts/creator-web.mdx');
  const runtime = await readRepo('apps/architecture-portal/docs/platform/web-runtime.mdx');
  const storage = await readRepo('apps/architecture-portal/docs/platform/storage.mdx');
  const proof = await readRepo('apps/architecture-portal/docs/operations/testing-and-proof.mdx');

  assert.match(creator, /persisted `pagehide`[^\n]+retains the shared Runtime/);
  assert.match(creator, /non-persisted terminal `pagehide`[^\n]+close/);
  assert.match(runtime, /BroadcastChannel[^\n]+AudioContext/);
  assert.match(storage, /managed Bundle paths[^\n]+ASCII segment subset/);
  assert.match(storage, /Project payload text remains UTF-8/);
  assert.match(proof, /reload[^\n]+16 admissions[^\n]+16 outcomes[^\n]+0 rejection[^\n]+resize/);
  assert.match(proof, /synthetic lifecycle[^\n]+automated contract only/);
  assert.match(proof, /physical\/hearing\/Safari\/iPadOS\/MIDI[^\n]+unverified and deferred/);
  assert.equal((proof.match(/deferred \/ unverified/g) ?? []).length, 5);
});
