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
  assert.match(review, /G1[^\n]+corrected/);
  assert.match(review, /1\.0\.18\.0[^\n]+abandoned \/ unshipped/);
  assert.match(review, /1\.0\.19\.0[\s\S]+步骤 1/);
});

test('Stage 7 current closure audit accounts for every review finding exactly once', async () => {
  const acceptance = await readRepo('docs/quality/2026-08-07-stage7-creator-editor-acceptance.md');
  const review = await readRepo('docs/quality/2026-08-12-stage7-creator-editor-review.md');
  const evidence = await readRepo('docs/release-evidence/2026-08-13-stage7-remediation-canary.md');
  const remediationDesign = await readRepo('docs/superpowers/specs/2026-08-13-lmdj-stage7-review-remediation-design.md');
  const remediationPlan = await readRepo('docs/superpowers/plans/2026-08-13-lmdj-stage7-review-remediation.md');
  const audit = review.match(
    /### Final finding closure audit\n(?<body>[\s\S]+?)\n### Remaining integration gates/,
  )?.groups?.body;
  assert.ok(audit, 'current final finding closure audit is missing');

  const resolved = [
    ...Array.from({length: 10}, (_, index) => `D${index + 1}`),
    ...Array.from({length: 15}, (_, index) => `F${index + 1}`),
    ...Array.from({length: 6}, (_, index) => `T${index + 2}`),
    ...Array.from({length: 4}, (_, index) => `G${index + 2}`),
    ...Array.from({length: 4}, (_, index) => `N${index + 1}`),
  ];
  for (const finding of resolved) {
    assert.equal(
      (audit.match(new RegExp(`^\\| ${finding} \\|`, 'gm')) ?? []).length,
      1,
      `${finding} must have exactly one current audit row`,
    );
    assert.match(audit, new RegExp(`^\\| ${finding} \\| resolved`, 'm'));
  }
  assert.equal((audit.match(/^\| T1 \|/gm) ?? []).length, 1);
  assert.match(audit, /^\| T1 \| open — corrected candidate must restart at step 1 \|/m);
  assert.equal((audit.match(/^\| G1 \|/gm) ?? []).length, 1);
  assert.match(audit, /^\| G1 \| corrected — historical Proof recovered \|/m);

  for (const body of [acceptance, review, evidence]) {
    assert.match(body, /31327104838/);
    assert.match(body, /31529410253/);
    assert.match(body, /38a8c130e5f1ced6f27d8fd7d2cba2fd1d70f97f/);
    assert.match(body, /336a27c0799035b2f8d6455b32259ee227df20f6/);
  }
  assert.match(review, /documentation binding gap[\s\S]+not a Proof execution gap/);
  assert.match(review, /1\.0\.19\.0[\s\S]+merged-main Proof/);
  assert.match(evidence, /1\.0\.18\.0[^\n]+abandoned and unshipped/);
  for (const body of [remediationDesign, remediationPlan]) {
    assert.match(body, /G1[\s\S]+historical Proof recovered/);
    assert.match(body, /1\.0\.18\.0/);
    assert.match(body, /1\.0\.19\.0/);
    assert.doesNotMatch(body, /T1 or G1 (?:is|remains?) open/);
  }
  assert.match(remediationDesign, /abandoned \/ unshipped/);
  assert.match(remediationPlan, /immutable failed-candidate evidence/);
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
