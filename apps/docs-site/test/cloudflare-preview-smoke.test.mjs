import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {verifyArtifactFiles} from '../scripts/cloudflare-preview-smoke.mjs';

const origin = 'https://12345678-portal-preview.lmdj.workers.dev';
const bytes = Buffer.from('verified file');
const receipt = {url: origin, files: [{path: 'assets/example.js', bytes: bytes.length,
  sha256: createHash('sha256').update(bytes).digest('hex')}]};
const response = (body, url = `${origin}/assets/example.js`) => ({status: 200, url,
  body: (async function* () { yield body; })()});

test('Preview artifact bytes and digest match', async () => {
  assert.deepEqual(await verifyArtifactFiles(receipt, async () => response(bytes)), []);
});
test('changed asset fails even with successful HTTP', async () => {
  assert.equal((await verifyArtifactFiles(receipt, async () => response(Buffer.from('tampered')))).length, 1);
});
test('redirect to a foreign origin fails with identical bytes', async () => {
  assert.equal((await verifyArtifactFiles(receipt, async () => response(bytes, 'https://foreign.example/asset'))).length, 1);
});

test('oversized response stops consuming after the first excess chunk', async () => {
  let reads = 0;
  const result = await verifyArtifactFiles(receipt, async () => ({status: 200,
    url: `${origin}/assets/example.js`, body: (async function* () {
      reads += 1;
      yield Buffer.alloc(bytes.length + 1);
      reads += 1;
      yield Buffer.alloc(1024);
    })()}));
  assert.equal(result.length, 1);
  assert.equal(reads, 1);
});
