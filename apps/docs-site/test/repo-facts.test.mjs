import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {cp, readdir, mkdtemp, mkdir, readFile, rm, writeFile} from 'node:fs/promises';
import os from 'node:os';
import test from 'node:test';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {readRepoFacts} from '../scripts/lib/repo-facts.mjs';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');

async function currentProductBuild() {
  const version = JSON.parse(await readFile(path.join(repoRoot, 'products/lmdj/version.json'), 'utf8'));
  return ['milestone', 'minor', 'build', 'patch'].map((field) => version[field]).join('.');
}

async function identityFixture(t, mutate) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'lmdj-portal-identity-'));
  t.after(() => rm(root, {recursive: true, force: true}));
  const productRoot = path.join(root, 'products/lmdj');
  await mkdir(productRoot, {recursive: true});
  const version = {
    contract: 'lmdj.product-version.v1', product: 'lmdj',
    milestone: 9, minor: 8, build: 7, patch: 6,
  };
  const assembly = {
    product: {id: 'lmdj', version: '9.8.7.6'},
    modules: [], hosts: [], providers: [], contracts: [],
  };
  const lock = {
    product: {id: 'lmdj', version: '9.8.7.6'},
    product_assembly: {id: 'lmdj', version: '9.8.7.6', sha256: '0'.repeat(64)},
    modules: [], hosts: [], providers: [], contracts: [],
  };
  mutate({assembly, lock});
  const assemblyBytes = `${JSON.stringify(assembly)}\n`;
  lock.assembly_sha256 = createHash('sha256').update(assemblyBytes).digest('hex');
  await writeFile(path.join(productRoot, 'version.json'), `${JSON.stringify(version)}\n`);
  await writeFile(path.join(productRoot, 'assembly.json'), assemblyBytes);
  await writeFile(path.join(productRoot, 'assembly.lock.json'), `${JSON.stringify(lock)}\n`);
  return root;
}

function assertProductMismatch(error, {found, consumer}) {
  assert.match(error.message, /portal facts error: Product Build mismatch/);
  assert.match(error.message, /expected 9\.8\.7\.6/);
  assert.match(error.message, new RegExp(`found ${found.replaceAll('.', '\\.')}\\b`));
  assert.match(error.message, /products\/lmdj\/version\.json/);
  assert.match(error.message, new RegExp(consumer.replaceAll('/', '\\/').replaceAll('.', '\\.')));
  return true;
}

test('facts match the current locked product composition', async () => {
  const facts = await readRepoFacts({repoRoot, revision: 'abcdef123456', channel: 'canary'});
  assert.equal(facts.product.version, await currentProductBuild());
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
    {id: 'cardputer-host', version: '1.0.0'},
    {id: 'core-cli', version: '3.3.5'},
    {id: 'core-mcp', version: '3.4.0'},
    {id: 'creator-web', version: '4.3.0'},
    {id: 'native-host', version: '3.4.0'},
    {id: 'web-runtime-host', version: '4.3.0'},
  ]);
  assert.equal(facts.providers.length, 3);
  assert.equal(facts.contracts.length, 14);
});

test('facts name each Product Build consumer that mismatches authority', async (t) => {
  const cases = [
    {
      consumer: 'products/lmdj/assembly.json',
      mutate: ({assembly}) => { assembly.product.version = '9.8.7.5'; },
    },
    {
      consumer: 'products/lmdj/assembly.lock.json',
      mutate: ({lock}) => { lock.product.version = '9.8.7.5'; },
    },
    {
      consumer: 'products/lmdj/assembly.lock.json',
      mutate: ({lock}) => { lock.product_assembly.version = '9.8.7.5'; },
    },
  ];
  for (const current of cases) {
    const fixtureRoot = await identityFixture(t, current.mutate);
    await assert.rejects(
      readRepoFacts({repoRoot: fixtureRoot, revision: 'abcdef123456', channel: 'canary'}),
      (error) => assertProductMismatch(error, {found: '9.8.7.5', consumer: current.consumer}),
    );
  }
});


test('registered Slice validator and binary profile remain authenticated', async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'lmdj-slice-facts-'));
  t.after(() => rm(root, {recursive: true, force: true}));
  for (const directory of ['products', 'providers', 'contracts']) {
    await cp(path.join(repoRoot, directory), path.join(root, directory), {recursive: true});
  }
  for (const directory of ['packages', 'apps']) {
    await mkdir(path.join(root, directory), {recursive: true});
    for (const entry of await readdir(path.join(repoRoot, directory))) {
      const relative = `${directory}/${entry}/module.json`;
      const source = await readFile(path.join(repoRoot, relative)).catch(() => null);
      if (!source) continue;
      await mkdir(path.dirname(path.join(root, relative)), {recursive: true});
      await writeFile(path.join(root, relative), source);
    }
  }
  const inspect = () => readRepoFacts({repoRoot: root, revision: 'abcdef123456', channel: 'canary'});
  assert.equal((await inspect()).providers.length, 3);
  for (const relative of ['providers/local-sample-slice/src/validation.cpp',
    'providers/local-sample-slice/include/lmdj/providers/local_sample_slice/validation.hpp']) {
    const file = path.join(root, relative);
    const original = await readFile(file);
    await writeFile(file, Buffer.concat([original, Buffer.from('\n// identity mutation\n')]));
    await assert.rejects(inspect, /providers source hash mismatch for local.sample.slice/);
    await writeFile(file, original);
  }
  const requiredSource = path.join(root, 'providers/local-sample-slice/src/provider.cpp');
  const savedSource = await readFile(requiredSource);
  await rm(requiredSource);
  await assert.rejects(inspect, /source-package file is unavailable/);
  await writeFile(requiredSource, savedSource);
  const profile = path.join(root, 'contracts/artifact-audio/lmdj.audio.pcm16-wav.v1.md');
  const original = await readFile(profile, 'utf8');
  await writeFile(profile, original.replace('contract_version: 1.0.0', 'contract_version: 9.0.0'));
  await assert.rejects(inspect, /contract profile identity mismatch/);
});
