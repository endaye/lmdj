import assert from 'node:assert/strict';
import test from 'node:test';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {readRepoFacts} from '../scripts/lib/repo-facts.mjs';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');

test('facts match the current locked product composition', async () => {
  const facts = await readRepoFacts({repoRoot, revision: 'abcdef123456', channel: 'canary'});
  assert.equal(facts.product.version, '1.0.23.0');
  assert.equal(facts.revision, 'abcdef123456');
  assert.equal(facts.channel, 'canary');
  assert.deepEqual(facts.modules.map(({id}) => id), [
    'application-facade',
    'audio-runtime',
    'authoring-domain',
    'foundation',
    'project-cooker',
    'project-io',
    'provider-sdk',
    'web-runtime-platform',
  ]);
  assert.deepEqual(facts.hosts.map(({id, version}) => ({id, version})), [
    {id: 'core-cli', version: '1.0.12'},
    {id: 'core-mcp', version: '1.1.9'},
    {id: 'creator-web', version: '1.3.0'},
    {id: 'native-test-host', version: '1.0.10'},
    {id: 'web-runtime-host', version: '1.2.9'},
  ]);
  assert.equal(facts.providers.length, 2);
  assert.equal(facts.contracts.length, 8);
});

test('facts reject an assembly identity mismatch', async () => {
  const fixtureRoot = path.join(repoRoot, 'apps/architecture-portal/test/fixtures/mismatched-repo');
  await assert.rejects(
    readRepoFacts({repoRoot: fixtureRoot, revision: 'abcdef123456', channel: 'canary'}),
    /portal facts error: product version mismatch/,
  );
});
